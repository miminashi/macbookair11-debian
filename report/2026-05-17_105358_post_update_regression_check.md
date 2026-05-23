# 2026-05-17 Debian アップデート後デグレチェック・レポート

- **実施日時**: 2026年5月17日 10:30 〜 10:54 (JST)
- **対象ホスト**: `macbookair2015.lan` (MacBook Air 11" Early 2015 / MacBookAir7,1)
- **OS**: Debian GNU/Linux 13 (trixie)
- **アップデート操作実施者**: ユーザ (`packagekit role='update-packages'` 経由、2 回連続)
- **検証実施者**: 開発マシンから ssh 越し (READ-ONLY 検証 + `smartmontools` のみ新規 install)

## 添付ファイル

- [実装プラン](attachment/2026-05-17_105358_post_update_regression_check/plan.md)

## 参照レポート

- [カーネル更新で消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)](2026-05-05_000905_kernel_dkms_recovery.md) — 5/5 で入れた DKMS 自動追従恒久対策の検証対象
- [NetworkManager WPA-PSK-SHA256 パッチ適用レポート](2026-04-01_182006_networkmanager_patch.md) — `+broadcomfix1` パッチ版の維持確認対象
- [MacBook Air 2015 WiFi 接続問題 — 調査・修正レポート](2026-04-01_080116_wifi_fix.md) — 旧 wpa_supplicant ワークアラウンドの残骸有無確認
- [MacBook Air lid open 復帰失敗 (S3 hang) 切り分けと暫定対策](2026-05-10_055032_lid_open_resume_hang.md) — `i915.enable_dc=0` 継続観測中
- [SSD 健全性レポート (交換後)](2026-03-30_185423_sda_health_check.md) — SMART baseline (2026-03-30)

## 前提・目的

### 背景

2026-05-17 にユーザが `macbookair2015.lan` 上で Debian アップデート (`packagekit role='update-packages'`) を 2 回連続で実施した。

| 時刻 (JST) | アップデート種別 | 主な更新 |
|---|---|---|
| 10:19:38 〜 10:21:01 | packagekit update | **新カーネル `linux-image-6.12.86`** + `linux-headers-amd64` メタ 6.12.85→6.12.86 + libreoffice 25.2.3 deb13u3→u4 + firefox-esr 140.10.1→140.10.2 |
| 10:28:52 〜 10:29:41 | packagekit update | **新カーネル `linux-image-6.12.88`** + `linux-headers-amd64` メタ 6.12.86→6.12.88 + dnsmasq-base / libnghttp2 / libpng / libav* / liblcms2-2 / libopenjp2-7 |

→ 結果として 1 日のうちに **`6.12.85` → `6.12.86` → `6.12.88` の 2 段階カーネル昇格** が起きた。

### 目的

過去にこのプロジェクトで適用してきた以下のパッチ・ワークアラウンドが、今回の 2 段カーネル昇格を含むアップデートで失われていないかを確認する。特に以下 2 点が今回の関心事:

1. **5/5 で入れた DKMS 恒久対策 (`linux-headers-amd64` メタ投入) の初の実戦テスト**: 5/4 の障害 (`wl.ko` 消失) と同じ事象が再発しないか
2. **`i915.enable_dc=0` 継続観測フェーズ (5/10 起点 〜 6/7 目安) がアップデートで中断していないか**

### 前提条件

- ssh `miminashi@macbookair2015.lan` 経由で NOPASSWD sudo 可
- 検証は READ-ONLY を基本とし、`smartmontools` のみ新規 install (過去 baseline 比較のため必須)
- 開発マシンから操作する。実機側でコマンドを叩く

## 環境情報

| 項目 | 値 |
|---|---|
| ハードウェア | Apple MacBookAir7,1 (Broadwell-U, 11" Early 2015) |
| Wi-Fi | Broadcom BCM4360 802.11ac (`wlp3s0`, PCI 03:00.0) |
| SSD | APPLE SSD SM0128G (S/N: S2PBNYAGB28065, FW: BXW5TA0Q, 121 GB SATA 6Gb/s) |
| OS | Debian 13 (trixie) |
| カーネル (現用) | `6.12.88+deb13-amd64` (5/17 10:28 投入) |
| カーネル (旧 hold) | `6.12.74+deb13+1-amd64` (即時復旧経路として hold 維持) |
| 同居カーネル | `6.12.73`, `6.12.85`, `6.12.86`, `6.12.88` (`linux-image-amd64` メタ管理) |
| NetworkManager | `1.52.1-1+broadcomfix1` (apt-mark hold) |
| libnm0 | `1.52.1-1+broadcomfix1` (apt-mark hold) |
| broadcom-sta-dkms | `6.30.223.271-26` |
| Kernel cmdline | `BOOT_IMAGE=/boot/vmlinuz-6.12.88+deb13-amd64 ... ro quiet i915.enable_dc=0` |
| `smartctl` | 7.4-3 (今回 install) |

## 再現方法 (検証コマンド)

すべて開発マシンから ssh `miminashi@macbookair2015.lan` 経由で実機上で実行。

### 1. NM パッチ版 / hold 状態 / Wi-Fi 状態

```bash
ssh miminashi@macbookair2015.lan '
  dpkg -l network-manager libnm0 | grep -E "^[hi][i]"
  apt-mark showhold
  nmcli -f WIFI-HW,WIFI,STATE,CONNECTIVITY general status
  nmcli device status
  ip -4 addr show wlp3s0 | grep inet
  systemctl is-active systemd-networkd; systemctl is-enabled systemd-networkd
  systemctl is-active wpa_supplicant-nl80211@wlp3s0; systemctl is-enabled wpa_supplicant-nl80211@wlp3s0
  ls /etc/NetworkManager/conf.d/
'
```

### 2. DKMS / wl.ko / カーネルヘッダ メタ

```bash
ssh miminashi@macbookair2015.lan '
  uname -r
  sudo dkms status
  ls -la /lib/modules/$(uname -r)/updates/dkms/
  lsmod | grep -E "^wl|^b43|^bcma|^brcm"
  dpkg -l linux-headers-amd64 | grep -E "^ii"
'
```

### 3. `i915.enable_dc=0` / S3 suspend-resume 観測

```bash
ssh miminashi@macbookair2015.lan '
  cat /proc/cmdline
  grep ^GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub
  cat /sys/module/i915/parameters/enable_dc
  sudo /usr/local/sbin/check-suspend-resume.sh
'
```

### 4. SSD SMART (smartmontools install 含む)

```bash
ssh miminashi@macbookair2015.lan '
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y smartmontools
  sudo smartctl -i /dev/sda
  sudo smartctl -H /dev/sda
  sudo smartctl -A /dev/sda
  sudo smartctl -l error /dev/sda
'
```

## 結果

### 過去作業の維持状況サマリ

| 系統 | 検証項目 | 実機の現状 | 判定 |
|---|---|---|---|
| **NM パッチ (4/1)** | `network-manager` | `hi  1.52.1-1+broadcomfix1` | ✅ |
|  | `libnm0` | `hi  1.52.1-1+broadcomfix1` | ✅ |
|  | `apt-mark showhold` | `libnm0` / `network-manager` 残存 | ✅ |
|  | nmcli `WIFI-HW` | 有効 / WIFI 有効 / 接続済み / 完全 | ✅ |
|  | `wlp3s0` IP | `192.168.33.145/24` (OpenWrt, WPA2/WPA3, signal 100) | ✅ |
| **旧ワークアラウンドの残骸** | `systemd-networkd` | inactive / disabled | ✅ |
|  | `wpa_supplicant-nl80211@wlp3s0` | inactive / disabled | ✅ |
|  | `/etc/NetworkManager/conf.d/unmanage-wifi.conf` | 不在 | ✅ |
| **DKMS 恒久対策 (5/5)** | `linux-headers-amd64` メタ | `ii  6.12.88-1` (新カーネル追従済) | ✅ |
|  | `dkms status` | `broadcom-sta/6.30.223.271` が `6.12.74` / `85` / `86` / `88` 全て `installed` | ✅ |
|  | `wl.ko.xz` 配置 (現カーネル) | `/lib/modules/6.12.88+deb13-amd64/updates/dkms/wl.ko.xz` (mtime **5/17 10:29**) | ✅ |
|  | `lsmod` の `wl` | ロード済 (6459392 bytes) | ✅ |
| **i915.enable_dc=0 (5/10)** | `/etc/default/grub` | `GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"` | ✅ |
|  | `/proc/cmdline` | `... quiet i915.enable_dc=0` | ✅ |
|  | `/sys/module/i915/parameters/enable_dc` | `0` (実効) | ✅ |
|  | `/usr/local/sbin/check-suspend-resume.sh` | 設置済 (mtime 5/10 04:51) | ✅ |

**結論: 今回のアップデートによる過去作業のデグレなし。**

### DKMS 自動再ビルドの証跡 (5/5 恒久対策の初実戦テスト)

`wl.ko.xz` のタイムスタンプが **5/17 10:29** で、`linux-image-6.12.88` の install 完了時刻 (apt history `End-Date: 2026-05-17 10:29:41`) と一致した。これは `linux-headers-amd64` メタが `6.12.86-1 → 6.12.88-1` に同時アップグレードされた直後に `/etc/kernel/header_postinst.d/dkms` フックが走り、`broadcom-sta` を `6.12.88` 用に自動再ビルドしたことを示す。

```
$ ls -la /lib/modules/6.12.88+deb13-amd64/updates/dkms/
-rw-r--r-- 1 root root 1513420  5月 17 10:29 wl.ko.xz

$ sudo dkms status
broadcom-sta/6.30.223.271, 6.12.74+deb13+1-amd64, x86_64: installed
broadcom-sta/6.30.223.271, 6.12.85+deb13-amd64, x86_64: installed
broadcom-sta/6.30.223.271, 6.12.86+deb13-amd64, x86_64: installed
broadcom-sta/6.30.223.271, 6.12.88+deb13-amd64, x86_64: installed
```

5/4 の障害 (新カーネル投入時に `wl.ko` が作られず Wi-Fi 喪失) は、5/5 の恒久対策 (`linux-headers-amd64` メタ投入) によって、今回 1 日に 2 度の新カーネル投入があったにもかかわらず **一切再発しなかった**。これが本タスクで観測された最も重要な事実。

### S3 suspend / resume 観測 (5/10 以降)

```
boot=f9c35ab3 suspend=66 resume=66 diff=0    # 5/10 05:25 〜 5/17 10:19, kernel 6.12.85 + i915.enable_dc=0
boot=b154cd0f suspend=1  resume=1  diff=0    # 5/17 10:19 (10:21 reboot まで)
boot=0eb89502 suspend=1  resume=1  diff=0    # 5/17 10:21 (6.12.86 起動、10:28 reboot まで)
boot=b21337af suspend=1  resume=1  diff=0    # 5/17 10:28 (10:29 reboot まで)
boot=77cd5397 suspend=1  resume=1  diff=0    # 5/17 10:30 〜 現在 (6.12.88 起動)
```

- boot `f9c35ab3` (約 1 週間、`6.12.85` + `i915.enable_dc=0`) で **66 suspend / 66 resume / hang 0 件**。直近 1 週間で hang が 1 件も発生していない。
- 5/17 のアップデートに伴う短時間 boot 4 件はそれぞれ suspend/resume 1 サイクル成立で問題なし。
- 旧 hang 4 件 (`edea8161` / `b4415a38` / `8ffbacdb` / `139bb7e4`) は実験前のもので、journal に過去ログとして残っているだけ。実験後 (boot `f9c35ab3` 以降) は hang 0 件のまま。

**`i915.enable_dc=0` の継続観測は中断なく継続中。** 起点 5/10 + 4 週間 = **2026-06-07 が中間判定の目安、6 週間 = 2026-06-21 が最終判定の目安**。

### SSD SMART (今回取得 vs 2026-03-30 baseline)

```
SMART overall-health self-assessment test result: PASSED
SMART Error Log: No Errors Logged
```

| ID | 属性 | 2026-03-30 baseline | 2026-05-17 今回 | 差分 | コメント |
|---|---|---:|---:|---:|---|
| 1 | Raw_Read_Error_Rate | 0 | 0 | ±0 | ✅ 読み取りエラーなし維持 |
| 5 | Reallocated_Sector_Ct | 0 | 0 | ±0 | ✅ 代替セクタ未発生 (最重要) |
| 9 | Power_On_Hours | 37,133 h | 37,279 h | +146 h | 48 日間で約 6 日分稼働 (≈12.5% duty) |
| 12 | Power_Cycle_Count | 93 | 312 | +219 | 48 日で 219 cycle → 多くは S3 deep sleep が cycle として計上されている挙動 |
| 192 | Power-Off_Retract_Count | 20 | 21 | +1 | 通常電源 OFF はほぼ無し |
| 194 | Temperature_Celsius (current) | 39°C | 40°C | +1°C | 通常範囲 |
| 194 | Temperature Min/Max | 19 / 66 °C | 18 / 73 °C | Max +7°C | Max が +7°C 上昇したが、SSD の警戒帯 (典型 80°C 以上) には到達せず |
| 197 | Current_Pending_Sector | 0 | 0 | ±0 | ✅ 保留セクタ未発生 (最重要) |
| 199 | UDMA_CRC_Error_Count | 0 | 4 | **+4** | ⚠ SATA リンク CRC エラーが 4 件累積。normalized 199 / threshold 0 で警告域ではないが、baseline で 0 だったのは留意点 |

**SMART 判定**: overall PASSED、Error Log なし、最重要 2 指標 (Reallocated_Sector_Ct / Current_Pending_Sector) は 0 維持。SSD は健全。

**注意ポイント**:

- `UDMA_CRC_Error_Count` が `0 → 4` に増加。SATA リンクで CRC が 4 回再送になっており、ケーブル接触不良 / 電気的ノイズ / 振動などが典型原因。MacBook Air の内蔵 SSD はソケット直結なので物理的接触は変わらないはず。閾値未到達のため警報レベルではないが、次回モニタリング時にさらに増えていないか継続確認。
- `Temperature Max` が `66 → 73 °C` に上昇。SSD としては許容範囲だが、夏季に向けて筐体内温度の動向を見ておく。

## 教訓・観察

### 1. `linux-headers-amd64` メタによる DKMS 自動追従は実戦投入で機能した

5/5 のレポートで導入した恒久対策が、本日 (5/17) の **2 段階カーネル昇格 (6.12.85 → 6.12.86 → 6.12.88)** で初めて実戦テストを受け、いずれのカーネル投入時も DKMS post-install hook が自動で `broadcom-sta` を再ビルドし、再起動後に `wl.ko` が即座にロードされて Wi-Fi が継続使用できた。5/4 の障害 (`wl.ko` 消失) と同じ事象は今回再発していない。

これにより、5/5 レポートで掲げた予防策「DKMS モジュールを使うホストでは `linux-headers-amd64` メタを必ず入れる」は **理論だけでなく経験的にも validate された** ことになる。

### 2. NM `+broadcomfix1` hold の堅牢性

`apt-mark hold` で固定した `network-manager` / `libnm0` (`1.52.1-1+broadcomfix1`) は、今回の 2 度の `packagekit role='update-packages'` でも一切上書きされなかった。`packagekit` が hold を尊重することを実機で確認できた。

### 3. アップデート後の検証手順は本レポートの「再現方法」セクションをそのまま流用可能

今後同様のアップデートが入った場合、本レポート末尾の検証コマンド群を再実行することで同等のデグレチェックができる。チェック項目は (a) NM hold + Wi-Fi 接続、(b) DKMS 全カーネル installed、(c) `wl.ko.xz` の mtime がカーネル投入時刻と一致、(d) `i915.enable_dc=0` が GRUB と /proc/cmdline 両方に残存、(e) SMART overall PASSED + Reallocated/Pending 0、の 5 つ。

## 今後

### `i915.enable_dc=0` 継続観測

5/10 起点で 4-6 週間の観測フェーズを設定済み。今回のアップデート (5/17) でカーネルが `6.12.85 → 6.12.88` に上がっても **GRUB の `i915.enable_dc=0` は引き続き有効** (新カーネルでも `/sys/module/i915/parameters/enable_dc=0` を確認済) のため、観測は中断せず継続。

| マイルストーン | 日付 | アクション |
|---|---|---|
| 2 週間 | 〜2026-05-24 | hang 0 のまま → 確率 25% の偶然 |
| 4 週間 | 〜2026-06-07 | hang 0 のまま → 「効いている可能性が高い」(有意水準 ~6%) |
| 6 週間 | 〜2026-06-21 | hang 0 のまま → 恒久採用とみなしてよい |
| 任意時点で 1 件以上発生 | - | 次候補 (`applespi` blacklist) に進む。手順は 2026-05-10 レポート Phase B 候補 2 |

### 旧カーネル `6.12.74+deb13+1-amd64` の hold 解除候補時期

5/5 レポートでは「新カーネルが一定期間 (数週間) 安定稼働すれば解除」としていた。現状:

- `6.12.85` (5/4 投入): 5/4 〜 5/17 安定稼働 (13 日間)
- `6.12.86` (5/17 10:19 投入): 9 分間しか稼働せず (10:28 に `6.12.88` で起動)
- `6.12.88` (5/17 10:28 投入): 本日稼働開始、観測実績が短い

→ `6.12.88` で 1-2 週間程度問題なく稼働した時点 (目安 6/1 以降) で、`linux-image-6.12.74+deb13+1-amd64` と `linux-headers-6.12.74+deb13+1-amd64` の hold 解除を検討してよい。

```bash
sudo apt-mark unhold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
sudo apt autoremove --purge
```

### SMART モニタリング

`smartmontools` を今回 install したので、今後は smartctl で SMART 値を直接確認できる。次回の経過観察 (4 週間後あたり) で以下を確認:

- `Reallocated_Sector_Ct` / `Current_Pending_Sector` が 0 維持か
- `UDMA_CRC_Error_Count` が 4 から更に増えていないか (増えていれば SATA リンクの調査検討)
- `Temperature Max` が 73 °C を超えていないか

`smartd` (smartmontools) のデーモンも install と同時に enable された (`/etc/systemd/system/smartd.service`) ので、設定ファイル `/etc/smartd.conf` のチューニングは別タスクとして検討。

## ロールバック手順

今回のレポートは **検証のみ** で実機の永続設定変更を伴わない (`smartmontools` の追加 install のみ)。ロールバック対象は実質なし。

`smartmontools` を外したい場合:

```bash
ssh miminashi@macbookair2015.lan '
  sudo systemctl disable --now smartmontools.service
  sudo apt-get -y purge smartmontools
'
```

(現状は維持を推奨。今後の継続観測に必要)
