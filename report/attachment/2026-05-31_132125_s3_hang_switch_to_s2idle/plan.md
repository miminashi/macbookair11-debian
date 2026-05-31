# S3 hang 対策: スリープモードを s2idle へ恒久切替

## Context（背景・目的）

MacBook Air 11" (Early 2015) / Debian 13 で、lid open でのスリープ復帰失敗 (S3 hang) が再発した。

- **今回の再発**: boot `-3` (2026-05-26 14:36 〜 2026-05-30 18:44) が hang。journal 末尾は `5/30 18:44:21 PM: suspend entry (deep)` で完全停止。翌朝 06:41 に強制起動 → 約 12h のギャップ。検出スクリプトでも `boot=33c46652 UNGRACEFUL [S3-HANG]` と確定。
- **これまでの経緯（全て失敗）**: `i915.enable_dc=0` (5/10) → `applespi` blacklist (5/22) → `pcie_aspm=off` + `pm_print_times=1` 永続化 (5/23)。当てずっぽうのカーネルパラメータを 3 つ適用したが hang は止まず、`pcie_aspm=off` 適用から約 7 日で再発。
- **判明した決定的事実（方針転換の根拠）**:
  1. hang は常に **deep S3 サイクルに紐づく**（journal 最終行は `PM: suspend entry (deep)`）。ただし最終行が suspend entry なのは resume 側ログが disk に届かないためでもあり、停止が suspend 側か resume 側かはログだけでは断定できない（ユーザ報告は「寝てから起きない」= resume hang）。いずれにせよ ACPI S3 deep の firmware 遷移（入る側/戻る側いずれも）が絡む。
  2. cold power-off で kernel ring buffer (RAM) が消失、かつ **pstore/ERST は本機に存在しない**（cold reboot を跨いで dmesg を残す経路ゼロ）。suspend 中のログは disk に flush されないため、journal では suspend hang と resume hang を区別できない。
  3. → **「1 パラメータ盲目適用 → 数週間観測」のループはフィードバックが原理的にゼロ**。netconsole / ramoops も本故障モード（早期 suspend/resume + cold off）には無力。
- **ユーザ確認結果**: 故障の見え方は「寝てから起きない」(resume hang)。スリープ時電源は「半々」(AC のときもバッテリーのときもある)。方針は **s2idle へ切替** を選択。
- **目的**: hang が起きる ACPI S3 deep の firmware 経路そのものを回避し、復帰失敗の症状を断つ。s2idle はこの遷移を一切行わない（機構的根拠）。同時に、s2idle のスリープ時消費電力増がバッテリー夜間運用で枯渇しないことを実測で確認する。

## 方針

スリープモードのデフォルトを **s2idle** に恒久切替する。あわせて、s2idle の消費電力を悪化させる失敗済み S3 用パラメータ (`pcie_aspm=off`, `i915.enable_dc=0`) を除去する。

### 実装中に判明した追加対応: spurious wakeup の永続抑止（必須）

s2idle は浅いスリープのため、enabled な wakeup ソース (XHC1=USB, RP01-06=PCIe/Wi-Fi) がネットワーク/USB トラフィックで **約 84 秒ごとに実機を起こしてしまう**ことが計測中に判明。`/proc/acpi/wakeup` の手動無効化は再起動で戻るため、deployed≠measured になる。`udev` ルールで boot 時に XHC1/RP01-06 の `power/wakeup` を `disabled` に永続化し、**lid open（と電源ボタン）でのみ復帰**するクリーンな挙動（S3 時代と同等）にする。トレードオフ（キー/USB/ネットワーク復帰の喪失）はユーザ承認済み。

- 計測結果（wakeup 抑止状態, 20 分実測）: **s2idle スリープ電力 0.70 W**（12h で 8.5 Wh=22%, 約 55.7h 持続）。抑止しない場合は 84s で起こされ wake-cycling/覚醒（awake 約 6.3W）となり実用不可。
- 実装: `/etc/udev/rules.d/90-s2idle-wakeup-suppress.rules`
  ```
  SUBSYSTEM=="pci", KERNEL=="0000:00:14.0", ATTR{power/wakeup}="disabled"  # XHC1 (USB)
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.0", ATTR{power/wakeup}="disabled"  # RP01
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.1", ATTR{power/wakeup}="disabled"  # RP02
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.2", ATTR{power/wakeup}="disabled"  # RP03
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.4", ATTR{power/wakeup}="disabled"  # RP05
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.5", ATTR{power/wakeup}="disabled"  # RP06
  ```
- 検証: 再起動後 `cat /proc/acpi/wakeup` で XHC1/RP0x が `disabled`、enabled は LID0 等のみであることを確認。

## 変更内容

### 1. カーネル cmdline (`/etc/default/grub` の `GRUB_CMDLINE_LINUX_DEFAULT`)

- 現在: `quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off`
- 変更後: `quiet no_console_suspend mem_sleep_default=s2idle`
  - **追加** `mem_sleep_default=s2idle`: boot 時に `/sys/power/mem_sleep` を `[s2idle] deep` にし、systemd の `suspend` (= `/sys/power/state` に `mem` を書く) が自動で s2idle を使うようになる（sleep.conf の追加設定は不要、kernel default が効く）。
  - **除去** `pcie_aspm=off`: S3 用に追加したが失敗。PCIe リンクが低電力 L-state に落ちられず、s2idle のスリープ時電力を大きく増やすため除去（今回の電力リスク対策の主眼）。
  - **除去** `i915.enable_dc=0`: 同じく失敗済み。Display Controller の DC5/DC6 を禁止し s2idle 時電力を増やすため除去。
  - **保持** `no_console_suspend`: 無害な debug 補助。s2idle で万一問題が出た際にコンソールへログが残る。
- 手順:
  1. バックアップ: `sudo cp /etc/default/grub /etc/default/grub.bak.$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)`
  2. `GRUB_CMDLINE_LINUX_DEFAULT` を編集
  3. `sudo update-grub`
  4. 再起動 → `cat /proc/cmdline` と `cat /sys/power/mem_sleep`（`[s2idle] deep` を確認）

### 2. 触らないもの（無害なので現状維持）

- `/etc/modprobe.d/disable-applespi.conf`（未使用ドライバ blacklist、電力影響なし）
- `/etc/tmpfiles.d/pm_print_times.conf`（`pm_print_times=1`。無害なので残す。deep より浅い s2idle なら resume 側 timing が flush される可能性は上がるが、保証はない）

## 検証

### A. 機能確認（s2idle で正常に suspend→resume するか / 即時）

実機 (AC 接続のまま) で runtime 切替 + RTC タイマ復帰を使い、deep を経由せず s2idle で復帰できることを確認する。**systemd の suspend は `/sys/power/state` に `mem` を書く**ので、`mem_sleep=s2idle` を設定した上で `rtcwake -m mem`（= `mem` を書く経路）を使い、本番と同じ経路を忠実に再現する（`-m freeze` は `mem_sleep` を無視して直接 s2idle に入る別経路なので使わない）。

```bash
ssh miminashi@macbookair2015.lan '
  echo s2idle | sudo tee /sys/power/mem_sleep    # /sys/power/state=mem 時の選択を s2idle に
  cat /sys/power/mem_sleep                         # [s2idle] deep を確認
  sudo rtcwake -m mem -s 60                         # mem(=s2idle) で 60s スリープ→RTC 復帰
  echo "resume OK: $(TZ=Asia/Tokyo date)"
  dmesg | grep -iE "PM: suspend (entry|exit)" | tail -4
'
```

- `PM: suspend entry (s2idle)` と `PM: suspend exit` のペアが出て ssh が生き残れば OK。
- 注: 60s の RTC 復帰テストは s2idle が「機能する」ことの確認であって、稀な resume hang を再現/解消するものではない（実証は D の長期観測で行う）。

### B. スリープ時消費電力の実測（バッテリー枯渇リスク検証 / バッテリー運用）

ユーザに **AC を抜いてもらった上で** 実施（discharge を測るため）。AC 接続中は充電中で測定不能。

```bash
ssh miminashi@macbookair2015.lan '
  echo s2idle | sudo tee /sys/power/mem_sleep
  cat /sys/class/power_supply/BAT0/energy_now    # 開始 (µWh)
  sudo rtcwake -m mem -s 1800                       # mem(=s2idle) で 30 分
  cat /sys/class/power_supply/BAT0/energy_now    # 終了 (µWh)
'
```

- 開始−終了 (µWh) ÷ 0.5h で平均消費電力 (W) を算出。`energy_full`（≈ 38Wh 級）に対し 12h 換算でどれだけ減るか試算。
- 目安: 約 12h 夜間スリープで満充電からデッドにならない（例えば 2〜3W 以下）なら許容。
- **許容できない場合のフォールバック**: `systemd` の `suspend-then-hibernate`（s2idle 後、`HibernateDelaySec` 経過 or バッテリー低下で hibernate に移行）を導入し drain を頭打ちにする。ただし hibernate は swap >= RAM とスワップ設定が前提で別途検証が必要なため、本計画では「B の結果次第の follow-up」として扱う。

### C. 検出スクリプトの整合性確認

`/usr/local/sbin/check-suspend-resume.sh` が `PM: suspend entry` を generic に数えているか確認（s2idle では `(s2idle)`、deep では `(deep)`）。deep 前提の grep になっていれば s2idle も拾うよう確認・必要なら微修正。

### D. 観測

- s2idle 恒久化後、通常運用で lid 開閉スリープを繰り返し、検出スクリプトで hang 0 件を確認していく。
- s2idle でも resume hang が出る場合は、deep 経路が原因ではなかったことになり、別仮説（特定 device の resume）へ切り替え。

## レポート

実装後、`report/yyyy-mm-dd_hhmmss_s3_hang_switch_to_s2idle.md` を作成（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。

- 前提・目的、今回の hang の確定根拠（boot -3 末尾 / pstore 不在 / 区別不能の論理）、s2idle 選択の機構的根拠、cmdline 変更差分、検証 A/B/C 結果、観測方針を記載。
- 過去レポート（`report/2026-05-23_144518_s3_hang_pcie_aspm_off.md` 等）へのリンク。
- 環境情報（MacBook Air 11" Early 2015 / Debian 13 / kernel 6.12.90+deb13-amd64）。
- 添付: `mkdir -p report/attachment/<レポート名>/` し、`cp /home/miminashi/.claude/plans/prancy-shimmying-russell.md report/attachment/<レポート名>/plan.md`、本文に `## 添付ファイル` でリンク。
- 最後に `./.ssh/git.sh` 経由で commit/push（ユーザ承認後）。
