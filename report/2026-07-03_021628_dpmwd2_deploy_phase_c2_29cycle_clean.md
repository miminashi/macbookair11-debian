# dpmwd2 (watchdog late/noirq 拡張カーネル) のビルド・デプロイ完了と Phase C-2 第 1 回 — 29 cycle (全 BT_PAN_VALID) clean、hang 未再現

- **実施日時**: 2026 年 7 月 3 日 00:54 〜 02:16 JST
- **位置づけ**: [2026-07-03_002608](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) の引継ぎを実行。watchdog を late/noirq 段へ拡張した `6.12.94-dpmwd2` をビルド・実機デプロイし、同一 hang-arm 条件で Phase C-2 第 1 回を実施した。**hang は再現せず (0/29)** — dpmwd2 の観測能力の検証は次回セッションへ持ち越し。

## 概要

### 何をしたか

1. **dpmwd2 ビルド完了**: 前セッションで「進行中」だったビルドは完了していなかった (deb 未生成) ため、準備済みのパッチ (commit `b90248d63`: `device_suspend_late/noirq` + `device_resume_early/noirq` の `dpm_run_callback` を `dpm_watchdog_set/clear` で挟む) と config (`DPM_WATCHDOG=y/60` + `PM_TRACE=y` + `PM_TRACE_RTC=y`) からビルドをやり直し、`linux-image-6.12.94-dpmwd2` (80 commits = Debian パッチ 79 + watchdog 拡張 1) を得た。
2. **実機デプロイ**: 182811 と同一手順 (dpkg -i → dkms wl 自動再ビルド → grub-reboot ワンショット + sync → 再起動)。ゲート (a) 全 9 項目・ゲート (a2) s2idle smoke を通過し、saved default を dpmwd2 に恒久化。crash テストは事前定義どおり省略 (経路は 182811 で 2 回検証済み)。
3. **Phase C-2 第 1 回**: 002608 と同一の hang-arm 条件 (wl loaded + radio off + BT-PAN + VPN + 手動 lid close) で 29 有効 cycle を駆動。

### 結果

- **hang 未再現: 0/29 (全 cycle BT_PAN_VALID、wl_loaded=YES 維持、drift なし)**
- suspend_stats success=31 / fail=0 (ゲート a2 smoke 1 + セットアップ smoke 1 + 有効 cycle 29)、journal の `PM: suspend entry/exit` は 31/31 で均衡
- pooled hang-arm rate は 6/80 (≈7.5%) → 6/109 (≈5.5%) に更新。0/29 clean の生起確率は p=0.075 として ≈10% で、条件の破れを示唆するものではない (単に今回は出なかった)
- **dpmwd2 の判別能力 (late/noirq stall の panic 自己申告) は未検証のまま** — hang 再現が前提のため、次回セッションで同一条件の再演が必要

### 実機の現状 (キャンペーン状態)

dpmwd2 が常用カーネルとして稼働中。stock と dpmwd1 も残置 (多段ロールバック可)。DPM watchdog は 60 秒超の device callback stall が無い限り inert、PM_TRACE_RTC はビルド時有効だが runtime は `/sys/power/pm_trace=0` (完全 inert、RTC 副作用なし)。日常使用中に hang が起きても panic → pstore → 自動再起動で自己申告される体制になった。

## 添付ファイル

- [実装プラン](attachment/2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean/plan.md)

## 前提・目的

- **背景**: [002608](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) で dpmwd1 (main phase のみ監視) 上の hang が ~18 分 panic 沈黙 → 停止段 ∈ {suspend_late, suspend_noirq, syscore, s2idle-enter} に絞り込まれた
- **目的**: watchdog を late/noirq 段へ拡張した dpmwd2 をデプロイし、同一条件で hang を再演して停止段をさらに判別する。late/noirq で panic すれば stall device 確定、なお沈黙なら {syscore, s2idle-enter} に絞られ pm_trace 再演へ
- **役割分担**: ビルド・デプロイ・ゲート・セットアップ・回収は Claude (ssh)、テザリング・コンソールゲート・cycle 駆動はユーザ

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd2** (本セッションで導入、DPM_WATCHDOG=y TIMEOUT=60 + late/noirq 拡張パッチ、PM_TRACE_RTC=y ビルド時有効・runtime off、panic=15)
- **開発機 (ビルド)**: akdx01 / Debian 13 / 12 コア
- スリープ: `[s2idle] deep`、hooks: 50-kbd-backlight / 58-snapshot-only / 60-s3-soak-log / 70-h4-probe
- BT/テザリング: iPad (`iMiminashiPadPro`, BT-PAN `172.20.10.13/28` on `enx98e0d98d205e`)、VPN: GSNet (strongSwan IKEv2)
- WiFi: `wl` loaded のまま `nmcli radio wifi off` (tight reading (b'') 条件維持)
- セッション中のみ: `kernel.hung_task_panic=1`、NM autoconnect (BT-PAN/GSNet=yes, OpenWrt=no/800)、vpn-watcher / cycle-watcher transient units

## 実験タイムライン

| 時刻 (JST) | 内容 |
|---|---|
| 00:54-01:10 | Phase 0: 開発機で dpmwd2 ビルド (検収ゲート通過後 `make -j12 LOCALVERSION= bindeb-pkg`)、deb 内 config 検収 |
| 01:11 | deb 2 個を scp (md5 照合)、dpkg -i (dkms が wl を dpmwd2 向け自動ビルド、initramfs、update-grub) |
| 01:13 | grub-reboot ワンショット (dpmwd2、フォールバック=dpmwd1) + sync → ssh 越し reboot |
| 01:14 | ゲート (a) 全 9 項目通過 (uname/config/cmdline/wl+WiFi/efi_pstore/pstore 空/pstore-guard/pm_trace=0/s2idle) |
| 01:14:42-57 | ゲート (a2) s2idle smoke 通過 → saved default を dpmwd2 に恒久化 + sync |
| 01:15:38 | SESSION_START (epoch 1783008938)、sysctl・NM 設定・transient units 起動 |
| 01:16 | セットアップ smoke 1 cycle (`wl_loaded=YES ping_running=NO` 確認、radio-on のため WIFI_SRC) |
| 01:17:05 | detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off` (wl 残置)、ssh 切断 |
| 01:48-02:12 | ユーザ手動 lid cycle 駆動 29 cycle、全 clean |
| 02:13 頃 | ユーザ WiFi 復旧、hang なし報告 |
| 02:14-16 | Claude 回収: 集計・source-IP gate・撤収 (sysctl/NM/units 平常化)、本レポート作成 |

## 証拠と検証

### cycle 集計 (durable evidence が正)

- 58-snapshot-only: SESSION_START 以降 **PRE 30 / POST 30 (unpaired なし = hang なし)**
  - 内訳: セットアップ smoke 1 (epoch 1783008968, radio-on) + 有効 cycle 29 (epoch 1783010896 [01:48] 〜 1783012323 [02:12])
- 70-h4-probe source-IP gate: **BT_PAN_VALID=29** (`src 172.20.10.*`) / WIFI_SRC=1 (セットアップ smoke のみ) / OTHER=0 — **有効 cycle は全件 BT-PAN 経由 VPN**
- wl drift check: セッション PRE 30 件すべて `wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES`
- ユーザ体感 30 cycle との差 1 は、cycle-watcher がセットアップ smoke を cycle 1 として計上していたため (suspend_stats 31 = a2 smoke + setup smoke + 29 で機械側整合)
- pstore: セッション終了時点で空 (panic なし、当然)

### デプロイ検収

- deb: `linux-image-6.12.94-dpmwd2_6.12.94-00080-gb90248d63a73-3_amd64.deb` (deb 内 config で `CONFIG_DPM_WATCHDOG=y/60` + `CONFIG_PM_TRACE_RTC=y` 確認)
- dkms: `broadcom-sta/6.30.223.271, 6.12.94-dpmwd2: installed`、`/lib/modules/6.12.94-dpmwd2/updates/dkms/wl.ko.xz` 存在
- grubenv: `saved_entry=...dpmwd2...` (grub-set-default 後に **sync 実施** — 182811 の教訓)

## 統計への影響

| プール | 更新前 | 更新後 |
|---|---|---|
| hang-arm (wl-loaded + radio-off) | 6/80 ≈ 7.5% (063543 + 043251 + 102907 + dpmwd1 C-1) | **6/109 ≈ 5.5%** (+ C-2 0/29) |
| clean-arm (radio-on / wl-unloaded) | 0/112 | 0/112 (不変) |

0/29 clean の生起確率は p=0.075 として (1-0.075)^29 ≈ 10% であり、「hang-arm 条件でも hang しないことがある」という既知の base rate の範囲内。(b'') tight reading (必要条件) と矛盾しない (十分条件ではないことは既知)。

## 再現方法

### Phase 0-1: ビルド・デプロイ

```bash
# 開発機 (src/linux-6.12.y, ブランチ dpmwd/6.12.94 HEAD=b90248d63)
make olddefconfig && make -j12 LOCALVERSION= bindeb-pkg
# 実機
sudo dpkg -i /tmp/linux-headers-6.12.94-dpmwd2_*.deb /tmp/linux-image-6.12.94-dpmwd2_*.deb
sudo grub-reboot "gnulinux-advanced-<UUID>>gnulinux-6.12.94-dpmwd2-advanced-<UUID>" && sudo sync && sudo reboot
# ゲート (a)(a2) 通過後
sudo grub-set-default "<同上 dpmwd2 エントリ>" && sudo sync
```

### Phase C-2 セッション (002608 と同一、session-commands.md 逐語)

```bash
sudo sysctl -w kernel.hung_task_panic=1
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt connection.autoconnect no ipv4.route-metric 800
# vpn-watcher / cycle-watcher transient units 起動 (systemd-run --collect)
# smoke 1 cycle → テザリング確認 → detached で "nmcli con down OpenWrt; nmcli radio wifi off" (rmmod しない)
# ユーザ: コンソールゲート (radio=disabled + lsmod に wl) → 手動 lid cycle
```

## 次セッション引継ぎ (Phase C-2 第 2 回)

- **dpmwd2 は稼働中・セットアップ資材はすべて残置** — 次回は「セッション開始」手順 (sysctl + NM + units + radio off) だけで再演可能
- 期待される分岐 (002608 から不変): late/noirq で panic → stall device 特定 / なお沈黙 → 停止段 ∈ {syscore, s2idle-enter} → `/sys/power/pm_trace=1` 再演 (RTC hash 照合、RTC 時刻破壊の副作用は NTP で復旧) か `pm_test` 段階分離
- P(≥1 hang in 30) ≈ 81-90% (p=5.5-7.5%)。出なければさらに 1 セッション
- キャンペーン中は dpmwd2 常用で問題なし (watchdog は inert、日常 hang も自己申告化)

## 残置物 (実機の現状、02:16 JST)

| 項目 | 状態 |
|---|---|
| kernel | **6.12.94-dpmwd2 稼働中 (saved default)**。dpmwd1 / stock 残置 (多段ロールバック) |
| 58-snapshot-only | 残置 (次セッションで使用) |
| NM autoconnect / route-metric | 平常化済み (BT-PAN/GSNet=no, OpenWrt=yes/-1) |
| kernel.hung_task_panic | 0 (revert 済み) |
| transient units | 停止済み (vpn-watcher / cycle-watcher / radio-off-detached) |
| pstore | 空 |
| pstore-guard / panic=15 / grub.bak-dpmwd | 182811 のまま残置 |
| /var/log/h4-probe | PRE/POST +30 追加 (削除しないこと) |
| pm_trace | 0 (inert、次段用に温存) |

## 関連レポート

- [2026-07-03_002608 dpmwd1 hang 再現・panic 沈黙・停止段絞り込み (本セッションの引継ぎ元)](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md)
- [2026-07-02_182811 dpmwd1 ビルド・デプロイ・pstore e2e 検証 (デプロイ手順の一次ソース)](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-07-02_103415 (b'') tight reading bedrock 化 (hang-arm 条件の根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
