# S3 hang 対策: スリープモードを s2idle へ恒久切替 + spurious wakeup 抑止

- **実施日時**: 2026年05月31日 13:21 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-05-31_132125_s3_hang_switch_to_s2idle/plan.md)

## 前提・目的

MacBook Air 11" (Early 2015) / Debian 13 で、lid open でのスリープ復帰失敗 (S3 hang) が再発した。本レポートは、過去 3 段階のカーネルパラメータ対策（いずれも失敗）から方針を転換し、**スリープモードを ACPI S3 deep から s2idle へ恒久切替**した記録である。

- **背景**: lid open でのスリープ復帰失敗が週 ~0.7 件のペースで継続。過去対策（[2026-05-10 lid_open_resume_hang](2026-05-10_055032_lid_open_resume_hang.md) の `i915.enable_dc=0`、[2026-05-22 applespi_blacklist](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) の `applespi` blacklist、[2026-05-23 pcie_aspm_off](2026-05-23_144518_s3_hang_pcie_aspm_off.md) の `pcie_aspm=off` + `pm_print_times=1` 永続化）はいずれも効果がなかった。
- **目的**: hang が発生する ACPI S3 deep の firmware 遷移経路そのものを回避し、復帰失敗の症状を断つ。s2idle はこの遷移を行わない（機構的根拠）。あわせて s2idle のスリープ時消費電力がバッテリー夜間運用で許容範囲かを実測で確認する。
- **前提条件**: 操作対象は ssh 接続先の実機 `macbookair2015.lan`。すべての変更は ssh 越しに実施。

## 環境情報

- 機種: MacBook Air 11" (Early 2015)
- OS: Debian 13 (trixie)
- カーネル: `6.12.90+deb13-amd64`
- バッテリー: `BAT0`（`charge_*` (uAh) + `voltage_now` 形式、`charge_full` ≈ 4.673 Ah / 満充電 ≈ 39 Wh 級）
- 切替前 cmdline: `quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off`
- 切替後 cmdline: `quiet no_console_suspend mem_sleep_default=s2idle`

## 今回の hang の確定根拠

- 検出スクリプト `/usr/local/sbin/check-suspend-resume.sh` で `boot=33c46652 UNGRACEFUL [S3-HANG]` と確定。
- 該当 boot（2026-05-26 14:36 〜 2026-05-30 18:44）の journal 末尾:
  ```
   5月 30 18:44:21 ... systemd-sleep[148776]: Performing sleep operation 'suspend'...
   5月 30 18:44:21 ... kernel: PM: suspend entry (deep)
  ```
  この行を最後に完全停止。翌朝 06:41 に強制起動（約 12h のギャップ）。
- ユーザ報告は「寝てから起きない」= resume hang（スリープには入り、lid open で復帰せず）。
- `pcie_aspm=off` 適用（5/23 14:47）から約 7 日後の再発であり、同対策も無効と判明。

## 方針転換の根拠（診断ループのフィードバックがゼロ）

これまで「1 カーネルパラメータを盲目的に適用 → 数週間観測」を 3 回繰り返したが、本故障モードでは**hang 箇所の可視性が原理的にゼロ**であることが判明した。

1. **journal では停止位置を特定できない**: hang は `PM: suspend entry (deep)` 直後に出る。ただし最終行が suspend entry なのは、suspend/resume 中のカーネルログが disk に flush されないためでもある。実際に boot -3 のログでは、5/30 17:57 に一度 **正常復帰**しており（`pm_print_times` による device resume timing と `PM: suspend exit` が記録済み）、その後 18:44 に再スリープして hang していた。つまり `pm_print_times=1` は機能しているが、**suspend 経路の hang か resume 経路の hang かをログだけでは区別できない**（どちらも「最終行 = suspend entry」になる）。
2. **cross-reboot のログ保存手段がない**: cold power-off で kernel ring buffer (RAM) が消失。本機には **pstore/ERST が存在しない**（`/sys/fs/pstore` 空、dmesg に ERST 記載なし）ため、強制電源断を跨いで dmesg を残せない。
3. **netconsole / ramoops も無力**: 早期の suspend/resume hang ではネットワークデバイスが suspend 済みで netconsole が届かず、cold off で ramoops も消える。

→ 当てずっぽうの 1 パラメータ試行を続けても、再発しても何も学べない。そこで、hang が紐づく **ACPI S3 deep の firmware 遷移そのものを使わない s2idle** へ切り替える方針とした（ユーザ選択）。

## 変更内容

### 1. カーネル cmdline (`/etc/default/grub`)

```diff
-GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off"
+GRUB_CMDLINE_LINUX_DEFAULT="quiet no_console_suspend mem_sleep_default=s2idle"
```

- **追加** `mem_sleep_default=s2idle`: boot 時に `/sys/power/mem_sleep` を `[s2idle] deep` にする。systemd の suspend は `/sys/power/state` に `mem` を書くため、kernel default が s2idle なら自動で s2idle が選択される（`sleep.conf` の追加設定は不要）。
- **除去** `pcie_aspm=off` / `i915.enable_dc=0`: いずれも S3 hang 対策として追加したが失敗。さらに **どちらも s2idle のスリープ時消費電力を増やす**（PCIe リンクと Display Controller が低電力状態に落ちられない）ため、s2idle 方針では除去が必須。
- **保持** `no_console_suspend`: 無害な debug 補助として残置。
- バックアップ: `/etc/default/grub.bak.20260531_071219`
- `sudo update-grub` 実行 → 全カーネルエントリに反映。

### 2. spurious wakeup の永続抑止（実装中に判明した必須対応）

s2idle は浅いスリープのため、enabled な wakeup ソース **XHC1 (USB)** / **RP01-06 (PCIe, Wi-Fi)** がネットワーク/USB トラフィックで**約 84 秒ごとに実機を起こす**ことが計測中に判明（`/proc/acpi/wakeup` 手動無効化は再起動で戻るため deployed≠measured になる）。`udev` ルールで boot 時に該当デバイスの `power/wakeup` を `disabled` に永続化し、**lid open（と電源ボタン）でのみ復帰**するクリーンな挙動（S3 時代と同等）にした。

トレードオフ（キー入力・USB・ネットワークによる復帰の喪失）はユーザ承認済み。

- ファイル: `/etc/udev/rules.d/90-s2idle-wakeup-suppress.rules`
  ```
  SUBSYSTEM=="pci", KERNEL=="0000:00:14.0", ATTR{power/wakeup}="disabled"  # XHC1 (USB)
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.0", ATTR{power/wakeup}="disabled"  # RP01
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.1", ATTR{power/wakeup}="disabled"  # RP02
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.2", ATTR{power/wakeup}="disabled"  # RP03
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.4", ATTR{power/wakeup}="disabled"  # RP05
  SUBSYSTEM=="pci", KERNEL=="0000:00:1c.5", ATTR{power/wakeup}="disabled"  # RP06
  ```

### 3. 触らなかったもの（無害なので現状維持）

- `/etc/modprobe.d/disable-applespi.conf`（`applespi` blacklist、電力影響なし）
- `/etc/tmpfiles.d/pm_print_times.conf`（`pm_print_times=1`）

## 検証結果

### A. s2idle 機能確認（grub 変更前 / AC 接続）

runtime で `echo s2idle > /sys/power/mem_sleep` し、本番経路（`/sys/power/state` ← `mem`）を忠実に再現する `rtcwake -m mem -s 60` を実行。`PM: suspend entry (s2idle)` → `PM: suspend exit` のペアが出て ssh も生存。**s2idle suspend→resume は正常**。

### B. スリープ時消費電力の実測（バッテリー / wakeup 抑止状態, 20 分実測）

| 項目 | 値 |
|---|---|
| 実睡眠時間（kernel entry→exit） | 1201 s（20.0 分、早期 wake なし） |
| charge 消費 | 0.0280 Ah（平均 8.39 V） |
| 消費エネルギー | 0.235 Wh |
| **平均 s2idle スリープ電力** | **0.70 W** |
| 12h 夜間換算 | 8.5 Wh = バッテリーの 22% |
| 満充電からの持続 | 約 55.7 時間 |

→ **wakeup を抑止すれば s2idle の電力は完全に許容範囲**（優秀）。抑止しない場合は 84s ごとに起こされ、wake-cycling または蓋を閉じたまま覚醒（awake ≈ 6.3W）となり実用不可。これが §変更内容 2 の udev 抑止を必須とした理由。

### C. 検出スクリプトの整合性

`/usr/local/sbin/check-suspend-resume.sh` は `PM: suspend entry` / `PM: suspend exit` を部分一致 grep で数えており、`PM: suspend entry (s2idle)` も問題なくヒット。`[S3-HANG]` 判定 (`HANG_RE`) も同様。**修正不要**。

### D. クリーンブート後の最終検証（デプロイ済み構成）

再起動後（約 30s で復帰）、全項目合格:

- `/proc/cmdline`: `quiet no_console_suspend mem_sleep_default=s2idle`（`pcie_aspm`・`i915` 除去確認）
- `/sys/power/mem_sleep`: `[s2idle] deep`
- `/proc/acpi/wakeup`: **クリーンブートから enabled は `LID0` のみ**（udev ルールが boot 時に効いている）
- `pm_print_times`: `1`（維持）、`applespi`: 非ロード（維持）
- **静定後の s2idle 連続スリープ**: `rtcwake -m mem -s 180` で 181s 完走（早期 wake なし）。
  - 注: 再起動直後（uptime 3 分未満、ブートサービス活動中）には 50s で早期 wake する事象を観測したが、要因は IRQ 9 = ACPI SCI 経由のブート直後の一時的イベントであり、システム静定後（=実夜間スリープ相当）は full 完走することを確認した。

## 残課題・今後の観測方針

- **resume 信頼性の長期観測**: s2idle 恒久化後、通常運用で lid 開閉スリープを繰り返し、`check-suspend-resume.sh` で hang 0 件を確認していく。
- **s2idle でも resume hang が出る場合**: hang は ACPI S3 deep 経路が原因ではなかったことになり、device resume 起因の別仮説へ切り替える（その場合 s2idle は cycle 数が増えるため再発がむしろ増える可能性もある点に留意）。
- **バッテリー残量**: 一連のテストで覚醒時間が長く、計測終了時点でバッテリーは 63%（AC 未接続）。**実機の AC アダプタを再接続することを推奨**。

## 再現方法（実機での手順）

```bash
# 1. grub バックアップ + cmdline 変更
ssh miminashi@macbookair2015.lan '
  sudo cp /etc/default/grub /etc/default/grub.bak.$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)
  sudo sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet no_console_suspend mem_sleep_default=s2idle\"|" /etc/default/grub
  sudo update-grub
'

# 2. spurious wakeup 抑止 udev ルール作成
ssh miminashi@macbookair2015.lan 'sudo tee /etc/udev/rules.d/90-s2idle-wakeup-suppress.rules' <<EOF
SUBSYSTEM=="pci", KERNEL=="0000:00:14.0", ATTR{power/wakeup}="disabled"
SUBSYSTEM=="pci", KERNEL=="0000:00:1c.0", ATTR{power/wakeup}="disabled"
SUBSYSTEM=="pci", KERNEL=="0000:00:1c.1", ATTR{power/wakeup}="disabled"
SUBSYSTEM=="pci", KERNEL=="0000:00:1c.2", ATTR{power/wakeup}="disabled"
SUBSYSTEM=="pci", KERNEL=="0000:00:1c.4", ATTR{power/wakeup}="disabled"
SUBSYSTEM=="pci", KERNEL=="0000:00:1c.5", ATTR{power/wakeup}="disabled"
EOF

# 3. 再起動して反映 + 検証
ssh miminashi@macbookair2015.lan 'sudo systemctl reboot'
# 復帰後:
ssh miminashi@macbookair2015.lan '
  cat /proc/cmdline
  cat /sys/power/mem_sleep                       # [s2idle] deep
  cat /proc/acpi/wakeup | awk "NR==1 || /enabled/"  # LID0 のみ
'

# 4. (任意) s2idle スリープ電力の実測 (AC を抜いて実施)
ssh miminashi@macbookair2015.lan '
  CB=$(cat /sys/class/power_supply/BAT0/charge_now); VB=$(cat /sys/class/power_supply/BAT0/voltage_now)
  sudo rtcwake -m mem -s 1200
  CA=$(cat /sys/class/power_supply/BAT0/charge_now); VA=$(cat /sys/class/power_supply/BAT0/voltage_now)
  awk -v cb=$CB -v ca=$CA -v vb=$VB -v va=$VA "BEGIN{print (cb-ca)/1e6*(vb+va)/2e6/(1200/3600), \"W\"}"
'
```
