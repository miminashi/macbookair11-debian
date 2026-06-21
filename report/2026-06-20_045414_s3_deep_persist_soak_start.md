# S3(deep) 永続化（可逆方式）と 2週間 passive soak の開始

- **実施日時**: 2026年06月20日 04:54 (JST)
- **位置づけ**: 中間レポート（**永続化＝完了ではない**。本体は 2週間の passive soak。最終判定は別途）

## 添付ファイル

- [実装プラン](attachment/2026-06-20_045414_s3_deep_persist_soak_start/plan.md)
- [スモークログ（本セッションの BOOT/SLEEP/WAKE 全行）](attachment/2026-06-20_045414_s3_deep_persist_soak_start/s3-soak-smoke.log)

## 前提・目的

[2026-06-19 battery 駆動 S3 待機電力測定レポート](2026-06-19_094329_s3_battery_standby_power.md) で
**本取り組みの主目的＝待機電力低減は go** が確定した（battery S3 の待機電力 ~0.06–0.10 W、s2idle 0.70 W の
1/7–1/12）。同レポート末尾「未着手」3項目のうち、目標到達に直結し依存が無い **#1「永続化 + 1–2 週間 soak」**
に着手する。

- **目的**: deep を毎スリープ既定にする設定を**可逆な方式で永続化**し、**2週間の passive soak**（実運用の
  lid/電源ボタン復帰を観測）で **battery resume の長期信頼性**を検証する。
- **検証する未解決リスク（唯一の go/no-go 残件）**: deep の永続化は、2026-05-31 に s2idle へ退避する原因と
  なった**歴史的な S3 resume hang（週 0.7–0.8 件）を再武装する**。前回までの 21/21 健全データは AC 限定で、
  この発生率を統計的に排除できない。**だから soak が本体**であり、本セッションの設定変更はその準備にすぎない。
- **トレードオフ（採用の前提）**: この低消費は **LID0 wake 無効化（蓋を開けても起きない）が前提**。復帰は
  電源ボタン。なお lid wake は s2idle でも既に 0/3 で死んでおり、S3 で新たに失う物はない。
- **スコープ外**: #2（gpe70 spurious の機序解明＝lid wake 温存）、#3（低バッテリ連動ハイバネと S3 の干渉）、
  および **GRUB の deep 化（本採用）は soak 通過後**に回す。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.90+deb13-amd64`
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。物理操作（AC 抜き差し・lid・電源ボタン）はユーザ。
- **本セッションで 1 回再起動**（boot_id `86ba1c2d…` → `dd9c9218…`）。soak はこの新 boot から開始。
- 永続デフォルト（GRUB）は `mem_sleep_default=s2idle` の**まま据え置き**。deep は oneshot が runtime 選択。
- safety net: **睡眠中の電池保護は STH の時限ハイバネ（battery 時 logind `HandleLidSwitch=suspend-then-hibernate`、
  `SuspendEstimationSec=30min`）が唯一**。UPower の 2% 緊急ハイバネは**睡眠中は発火しない**（ポーラが寝ているため
  覚醒時のみ）。udev `BAT0 alarm=0` も既設。→ この STH→hibernate を deep 下で本セッションで実証済み（Part C-3）。
- 新規残置物（本セッションで設置）:
  - `/usr/local/sbin/s3-deep-apply.sh` … 起動時に deep 選択 + LID0 無効化（ガード付き冪等）+ BOOT マーカー記録
  - `/etc/systemd/system/s3-deep-apply.service` … 上記を起動時に走らせる oneshot（**enabled**、`After=sysinit.target`）
  - `/usr/lib/systemd/system-sleep/60-s3-soak-log` … 各 suspend/resume を `/var/log/s3-soak.log` に記録
  - `/var/log/s3-soak.log` … soak の ground truth ログ（journald とは別に on-disk・sync 付き）

## 実施内容と検証結果

### Part A — 可逆な永続化（oneshot service）

`s3-deep-apply.sh` + `s3-deep-apply.service` を設置し `enable --now`。要点:
- `/proc/acpi/wakeup` は**トグル**（idempotent write 不可）なので、`LID0.*\*enabled` の時だけ `echo LID0` する
  ガードで冪等化。**LID0 は2層独立**（デバイス層 `power/wakeup` と ACPI/GPE 層 `/proc/acpi/wakeup`）で、
  gpe70 を凍結させるのは後者。本 service は後者を操作する。
- **ロールバックは `systemctl disable --now s3-deep-apply.service` 一発**。GRUB は s2idle 据え置きなので、
  disable 後に再起動すれば deep 設定は一切残らない。

### Part B — passive soak 計測フック

`60-s3-soak-log`（system-sleep hook、既存 `50-kbd-backlight` と共存）を設置。
各 suspend の **pre** で `SLEEP` 行（type/ac/cap/charge_now/suspend_stats/gpe70）、**post** で `WAKE` 行
（同項目 + asleep 秒 + i915/DRM エラー件数 `drm_err` + LID0 状態）を記録。pre で deep+LID0 を再アサート（drift 防止）。
> 実装中に `grep -c … || echo 0` が "0" を二重出力して `drm_err` 値に改行混入するバグを検出し修正済み。

### Part C — fresh boot 適用 + battery スモーク（全項目パス）

1. **再起動後の自動適用**: 新 boot で `mem_sleep`=`s2idle [deep]`、`LID0 *disabled`、service active+enabled、
   `s3-soak.log` に新 boot_id の BOOT 行。→ oneshot は fresh boot で正しく適用される（新変数も同時に検証）。
2. **battery S3 スモーク 3/3 clean**（AC online=0 で実施）:

| # | 経路 | type | asleep_s | gpe70 | suspend_stats | drm_err | boot_id |
|---|---|---|---|---|---|---|---|
| 1 | systemctl suspend + RTC 25s | suspend | 27 | **0 凍結** | 1/0 | 0 | 不変 |
| 2 | systemctl suspend + RTC 25s | suspend | 27 | **0 凍結** | 2/0 | 0 | 不変 |
| 3 | **人手**: lid 閉 → 電源ボタン起こし | suspend-then-hibernate | 22 | **0 凍結** | 3/0 | 0 | 不変 |

   - **gpe70 は通算 0 のまま凍結**＝前回 battery で出た ~6s spurious wake（gpe70=LID0 _PRW 起因）が完全消失。
     asleep_s が RTC 設定どおり（25s+overhead）＝早期 spurious wake なしの裏付け。
   - **全サイクル boot_id 不変・drm_err=0・i915/DRM エラーなし**＝S3 resume 健全（画面黒なし、ユーザ目視も正常）。
   - 人手サイクルは `suspend-then-hibernate`（battery の lid 閉は logind STH 経路）で記録され、フックが両 type を
     正しく扱うことを確認。22s は STH の hibernate 遅延（30min）より十分短く、S3 suspend フェーズから電源ボタンで復帰。

3. **【安全網】deep 下の STH→hibernate(S4)→resume を実証**（C-3。無人 battery soak の唯一の睡眠中電池保護なので
   事前に1回観測）。一時的に `HibernateDelaySec=60s` の drop-in を入れ、battery で `systemctl suspend-then-hibernate`:
   - S3(deep) 入眠 → **60s 後に RTC wake → hibernate(S4 イメージ書込) → 電源オフ** → 電源ボタンで resume。
   - **S4 経由の決定的証拠**: resume 側カーネルログが `*_pm_restore` 系コールバック
     （`platform_pm_restore`/`pci_pm_restore`/`usb_dev_restore`/`hda_codec_pm_restore`）＋ `PM: hibernation:
     hibernation exit`＝**ハイバネ・イメージ復元経路**（通常 S3 resume の `_resume` ではない）。drm_err=0 で健全。
   - 検証後に drop-in は撤去済み（`SuspendEstimationSec=30min` のみに復元）。→ S3→RTC wake と S4 hibernate の
     **合成経路が deep でも完走**することを確認（個別には実証済みだったが合成は未観測だった点を closure）。

### 採用上の留意（lid wake と AC）

LID0 wake は**無条件で無効化**しているため、**AC 接続時も蓋を開けて起こせない**（deep の AC lid wake は前回 7/7 健全
だったが、本構成では使えない）。s2idle 運用でも lid wake は元々全環境で死んでいたので**新たな退化ではない**が、AC で
蓋開け復帰を期待すると面食らう点に注意。lid wake を AC でだけ温存したい場合は、将来 LID0 無効化を battery 限定に
スコープすることは可能（本 soak のスコープ外）。

### soak ログ解釈上の注意（本セッションで判明・チェックイン時に必須）

STH 検証ログから判明した、カウントを誤読しないための注意:

- **STH が hibernate まで進むと SLEEP/WAKE が「2 ペア」記録される**。systemd-suspend-then-hibernate は
  suspend フェーズと hibernate フェーズで system-sleep フックを別々に発火するため。実例（HibernateDelaySec=60s）:
  `SLEEP→WAKE(asleep_s=61, suspend フェーズ RTC 覚醒)` の直後に `SLEEP→WAKE(asleep_s=109, hibernate 復帰)` の
  2 組。→ **`s3-soak-report.sh` の sleeps/wakes/STH は実ユーザ睡眠回数より多く計上する**
  （hibernate まで進む STH は実測で 2 ペア。本番は HibernateDelaySec 未設定＝30min 推定のため、再 suspend を挟めば
  2 ペア超もあり得る）。ただし true_hang 判定（SLEEP の後に WAKE 無し→次 BOOT）の正しさには影響しない
  （ペアリングは保たれる）。S3 フェーズから電源ボタンで起こす（hibernate 未到達）と 1 ペアのまま
  （Part C-2 表の人手サイクル[#3]が実例, asleep_s=22）。
- **`suspend_stats/success` は S3 suspend のみ計数しハイバネは数えない**（STH 検証で suspend フェーズ覚醒時に
  3→4 へ増え、その後の hibernate 復帰では 4 のまま）。よって soak の `ss_ok` ≈ S3 入眠回数であってセッション数ではない。
- **`resume=` はカーネル cmdline に無い**が hibernate resume は initramfs 経由で正常動作（swap=`/dev/sda3` ≈3.73 GiB
  ＝RAM 同等）。6-18 と本日の S4 resume 実証どおり、resume 配線は健全。

## 現在の状態（soak 稼働中）

- deep + LID0 無効が**起動のたびに自動適用**される（oneshot, enabled）。ユーザは**普段どおり使うだけ**。
- 各 suspend/resume は `/var/log/s3-soak.log` に記録され、true hang は「SLEEP 行の後に WAKE 無し → 次が BOOT 行」
  のシーケンス + `journalctl --list-boots` の異常終了 boot で**事後検出**できる（journald は永続）。
- **ユーザ協力が必須の信号**: 復帰で画面が真っ黒/無反応になったら、**時刻**と「別ホストから ssh が届くか
  （届く=mode3 / 届かない=死）」をメモしてほしい。自動ログと突き合わせて分類する。

## 再現方法（実機手順）

```bash
# 設置物の確認
ssh miminashi@macbookair2015.lan 'systemctl is-enabled s3-deep-apply.service; \
  cat /sys/power/mem_sleep; grep LID0 /proc/acpi/wakeup'
# 期待: enabled / "s2idle [deep]" / "LID0 ... *disabled"

# battery スモーク（AC を抜いた状態で。フックを発火させるため rtcwake -m mem ではなく systemctl 経由）
ssh miminashi@macbookair2015.lan 'sudo rtcwake -m no -s 25; sudo systemctl suspend'
# 復帰後: boot_id 不変・gpe70=0・drm_err=0 を soak ログで確認
ssh miminashi@macbookair2015.lan 'sudo tail -2 /var/log/s3-soak.log'
```

### ロールバック（hang 観測時 / 中止時）

```bash
ssh miminashi@macbookair2015.lan '
  sudo systemctl disable --now s3-deep-apply.service
  echo s2idle | sudo tee /sys/power/mem_sleep
  grep -q "LID0.*disabled" /proc/acpi/wakeup && echo LID0 | sudo tee /proc/acpi/wakeup
  sudo rm -f /usr/lib/systemd/system-sleep/60-s3-soak-log'
# GRUB は s2idle 据え置きなので、再起動すれば deep 設定は一切残らない
```

## 結論と次の一手

- **可逆な永続化と passive soak の計測基盤を本番投入し、battery S3 スモーク 3/3 clean・gpe70 完全凍結・
  resume 健全を確認**した。fresh boot 自動適用も実証。**soak は本 boot（2026-06-20 04:49〜）から稼働中**。
- **次の一手（時間依存・別セッション）**:
  1. **中間チェックイン（~1週間後 = 2026-06-27 目安）**: `s3-soak.log` + `journalctl --list-boots` を分析し
     wake イベントを分類（正常 / mode3画面黒 / RTC・ハイバネ救済 / **true hang**）→ 中間判定。
  2. **最終判定（2週間後 = 2026-07-04 目安）**:
     - **クリーン継続なら本採用** = GRUB を `mem_sleep_default=deep` 化 + 完了レポート。
     - **true hang を観測したら即ロールバック**（上記）+ #2 gpe70 機序解明へ転回。
- **未着手（スコープ外・別タスク）**: #2 gpe70 spurious の機序解明（lid wake 温存）、#3 S3 睡眠中の
  低バッテリ連動ハイバネ干渉。

## 関連レポート

- [2026-06-19 battery 駆動 S3 待機電力測定（本件の親・主目的 go の決着）](2026-06-19_094329_s3_battery_standby_power.md)
- [2026-06-18 S3 復活検証（spurious=gpe70 特定・lid wake 構造）](2026-06-18_233837_s3_revival_evaluation.md)
- [2026-06-18 なぜ S3 を使っていないのか（s2idle 0.70W の出典・hang 史）](2026-06-18_142303_why_not_s3_deep_sleep.md)
- [2026-05-31 S3 hang により s2idle へ切替（再武装するリスクの原点）](2026-05-31_132125_s3_hang_switch_to_s2idle.md)
