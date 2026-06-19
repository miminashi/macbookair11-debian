# S3(deep) 永続化（可逆方式）+ 2週間 passive soak の開始

## Context（なぜ今これをやるのか）

`report/2026-06-19_094329_s3_battery_standby_power.md` で、**本取り組みの主目的＝待機電力低減は go** が確定した：
battery 駆動 S3(deep) の実待機電力は **~0.06–0.10 W**、s2idle の 0.70 W より **7–12 倍低い**。最も堅い論拠
（ゲージ非依存）は「8h で容量低下わずか 2pt（0.70W なら ~13pt 減るはず）」。hold も 16/16 安定、spurious 0。

報告書末尾「未着手」3項目のうち、**目標到達に直結し依存が無いのは #1「永続化 + 1–2 週間 soak」**。
#2（gpe70 spurious の機序解明＝lid wake 温存）と #3（低バッテリハイバネ干渉）は nice-to-have で目標を gate しない。

**重要な前提（pure-win ではない）**: deep の永続化は、2026-05-31 に s2idle へ退避する原因となった
**歴史的な S3 resume hang（週 0.7–0.8 件）を再武装する**。AC での 21/21 健全データではこの発生率を
統計的に排除できない（報告書の明言）。lid wake は s2idle でも既に 0/3 で死んでおり S3 で新たに失う物は
無い（電源ボタン復帰で代替）が、**未知機序の resume hang が実運用 battery で再発するか**が唯一の未解決
リスク。だから本タスクの本体は **passive soak（実運用での復帰信頼性の長期観測）**であり、設定変更はその準備。

## 意思決定（ユーザ確定済み）

- **永続化方式 = 可逆 oneshot**: 起動時 systemd oneshot が `mem_sleep=deep` + LID0 無効化を適用。
  **GRUB は `mem_sleep_default=s2idle` のまま据え置く**。ロールバックは `systemctl disable` 一発。
  soak 通過後に初めて GRUB を deep 化（＝本採用）する。
- **soak = 2週間 + 中間チェックイン**: 約1週間後に wake イベント分類で中間判定、2週間で最終判定。

## 実機の確定事実（本計画で調査済み・READ-ONLY）

- `/proc/cmdline` = `mem_sleep_default=s2idle`（永続デフォルトは s2idle、再起動で安全側へ）。
- **LID0 wake は2層独立**（要注意）:
  - デバイス層 `/sys/bus/platform/devices/PNP0C0D:00/power/wakeup` = `disabled`
  - **ACPI/GPE 層 `/proc/acpi/wakeup` LID0 = `*enabled`** ← gpe70 を凍結させたのはこちら。両者は連動しない。
  - `/proc/acpi/wakeup` は**トグル**（idempotent write 不可）。→ 永続化は「現在 enabled の時だけトグル」のガード必須。
- journald は**永続**（`/var/log/journal` 実在、`journalctl --list-boots` で 3 boot 履歴あり）
  → force-reboot からの true hang を**事後検出できる**。
- `pm_print_times=1`（tmpfiles で既設）→ hang 時に最後に suspend したデバイスが journal に残る。
- STH（battery 時 `HandleLidSwitch=suspend-then-hibernate`）/ UPower 2% Hibernate / udev alarm=0 は既設で不変。
- 既存 `s3-soak-measure.sh` は **rtcwake 強制ループ用**（16/16 を出したツール）。**passive soak の道具ではない**ので流用しない。
- 現 boot は 2026-06-15 から継続（再起動なし）。

## 実装（このセッションで実施）

### Part A — 可逆な永続化（oneshot service）

`/usr/local/sbin/s3-deep-apply.sh`（適用ロジック。ガード付き・冪等・BOOT マーカー記録）:
```sh
#!/bin/sh
set -e
LOG=/var/log/s3-soak.log
ts() { TZ=Asia/Tokyo date +%Y-%m-%dT%H:%M:%S%z; }
# 1) deep を runtime 選択（既に deep ならそのまま）
echo deep > /sys/power/mem_sleep
# 2) ACPI LID0 を無効化（*enabled の時だけトグル＝冪等）
if grep -q 'LID0.*\*enabled' /proc/acpi/wakeup; then echo LID0 > /proc/acpi/wakeup; fi
# 3) BOOT マーカー（soak ログに boot 境界を残す＝true hang 検出の起点）
printf '%s BOOT mem_sleep="%s" lid=%s boot_id=%s\n' "$(ts)" \
  "$(cat /sys/power/mem_sleep)" \
  "$(awk '/LID0/{print $3}' /proc/acpi/wakeup)" \
  "$(cat /proc/sys/kernel/random/boot_id)" >> "$LOG"; sync
```

`/etc/systemd/system/s3-deep-apply.service`（順序注意: `WantedBy` と同じ target を `After` にすると
自己依存ループになるため、`After` は `sysinit.target`（sysfs マウント済み）にする）:
```ini
[Unit]
Description=Apply S3(deep) + disable LID0 ACPI wake (reversible soak rollout)
After=sysinit.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/s3-deep-apply.sh
[Install]
WantedBy=multi-user.target
```
→ `systemctl enable --now s3-deep-apply.service`。**ロールバックは `systemctl disable` のみ**（GRUB 不変なので
再起動 → oneshot 無効化済みなら s2idle 既定に自然復帰）。

### Part B — passive soak 計測（実運用の lid/電源ボタン復帰を観測）

**rtcwake 強制ループではなく**、実際の毎日の suspend/resume を system-sleep フックで記録する。

> **注意（battery の lid 閉＝STH 経路）**: battery 時は logind `HandleLidSwitch=suspend-then-hibernate` のため、
> lid を閉じると plain S3 ではなく **STH（suspend→`SuspendEstimationSec=30min` 後 hibernate）**になる。
> よって soak で観測する battery の「正常 lid wake」は STH の suspend フェーズからの復帰を指す（type=
> suspend-then-hibernate でログされる）。plain S3 だけを単体で見たい時は電源ボタン/rtcwake を使う。
> これは異常ではなく実運用の素の挙動なので、分類表の「RTC/ハイバネ救済」行とあわせてそのまま観測する。

`/usr/lib/systemd/system-sleep/60-s3-soak-log`（pre/post で 1 行ずつ追記。既存 `50-kbd-backlight` と共存）:
- 引数 `$1`=pre|post, `$2`=suspend|hibernate|suspend-then-hibernate。
- **pre**: `SLEEP` 行 — ts / type / battery charge_now,capacity / suspend_stats success,fail / gpe70 count を記録、`sync`。
- **post**: `WAKE` 行 — 同項目 + 直近 pre からの経過秒（asleep 時間）+ resume 直後の i915/DRM エラー有無
  （`journalctl -k -b -p err --since "@<pre_epoch>"` を grep）を記録、`sync`。
- LID0/deep を**毎 suspend 前に再アサート**（ガード付き）して drift を防ぐ（保険）。

加えて pre 時刻を `/run/s3-soak-pre.epoch` に保存し、post で asleep 時間を算出。`/run` 揮発なので
「pre 後に post 無し → 次に BOOT 行」のシーケンス＝**寝たまま死んで force-reboot された＝true hang 候補**。

**分類スキーム**（中間/最終チェックイン時に `/var/log/s3-soak.log` + `journalctl --list-boots` で集計）:
| 分類 | ログ上の痕跡 |
|---|---|
| 正常 wake（lid/電源ボタン） | SLEEP→WAKE 対あり、i915 err なし、asleep 妥当 |
| mode3（ssh 届く画面黒） | WAKE 行あり（userspace 復帰）だが i915/DRM err あり or ユーザ報告で画面黒 |
| RTC/ハイバネ救済（STH 発火） | type=suspend-then-hibernate、journal に hibernation 痕跡、suspend_stats 変化 |
| **true hang** | SLEEP 行の後に WAKE 無し → 次が BOOT 行。`--list-boots` で異常終了 boot |

**ユーザ協力が必須の信号**（自動化不可）: 復帰で画面が真っ黒/無反応になったら、時刻と「別ホストから
ssh が届くか（届く=mode3 / 届かない=死）」をメモしてもらう。これと自動ログを突き合わせて分類する。

### Part C — 検証（soak 開始前のスモーク）

1. `systemctl enable --now s3-deep-apply` 後、**1 回再起動**して oneshot が fresh boot で
   deep + LID0 無効を適用するか確認（＝「S3 が fresh boot で健全か」という新変数も同時に検証）。
   - 再起動後: `cat /sys/power/mem_sleep` が `s2idle [deep]`、`grep LID0 /proc/acpi/wakeup` が `disabled`、
     `s3-soak.log` に BOOT 行が出ていること。
2. ユーザに AC を抜いてもらい、**battery で手動 2–3 サイクル**スモーク（lid 閉開 or 電源ボタン）。
   各サイクルで `s3-soak.log` に SLEEP/WAKE 対が記録され、gpe70 が凍結（spurious 0）、resume 健全を確認。
3. 問題なければ soak 本番へ（以後ユーザは普段どおり使うだけ）。

### Part D — 中間レポート（このセッション）+ チェックイン予約

- CLAUDE.md ルールに従い `report/` に**中間レポート**を作成（タイムスタンプは
  `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`、本プランを `attachment/<name>/plan.md` に添付）。
  「永続化＝完了ではなく、2週間 soak が本体」と明記。
- **約1週間後に中間チェックイン**、**2週間後に最終判定**を `/schedule`（cloud routine）で予約:
  分析スクリプトが `s3-soak.log` + `journalctl --list-boots` を集計し wake イベントを分類 → 判定。
  - クリーン継続なら最終で **GRUB を `mem_sleep_default=deep` 化（本採用）** + 完了レポート。
  - true hang を観測したら **即ロールバック**（下記）+ #2 gpe70 機序解明へ転回、を最終レポートに。

## ロールバック（hang 観測時 / 中止時）

```bash
ssh miminashi@macbookair2015.lan '
  sudo systemctl disable --now s3-deep-apply.service
  echo s2idle | sudo tee /sys/power/mem_sleep
  grep -q "LID0.*disabled" /proc/acpi/wakeup && echo LID0 | sudo tee /proc/acpi/wakeup  # 再 enable
  sudo rm -f /usr/lib/systemd/system-sleep/60-s3-soak-log'
# GRUB は最初から s2idle 据え置きなので、再起動すれば deep 設定は一切残らない
```

## 検証（このセッションの完了基準）

- `s3-deep-apply.service` が enable され、**再起動後**に `mem_sleep`=`s2idle [deep]` / LID0=`disabled` /
  `s3-soak.log` に BOOT 行。
- battery 手動スモークで SLEEP/WAKE 対がログされ gpe70 凍結・resume 健全。
- 中間レポートが `report/` に作成され、プランが添付され、Discord 通知が飛ぶ。
- 1週/2週チェックインが `/schedule` に登録される。

## スコープ外（本タスクでは追わない）

- **#2 gpe70 spurious の機序解明**（lid wake 温存）— soak が hang を出した時の転回先 or 別タスク。
- **#3 低バッテリ連動ハイバネと S3 の干渉**（S3 睡眠中 UPower 非稼働）— STH/RTC 経路は既設で機能、別タスク。
- **GRUB の deep 化（本採用）** — soak 通過を待ってから（このセッションでは実施しない）。
