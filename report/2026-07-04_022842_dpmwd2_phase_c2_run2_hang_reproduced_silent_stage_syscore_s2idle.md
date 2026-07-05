# Phase C-2 第 2 回 — dpmwd2 で hang 再現、late/noirq watchdog + hung_task_panic とも完全沈黙 → 停止段 ∈ {syscore, s2idle-enter} 確定

- **実施日時**: 2026年7月4日 02:03 〜 02:28 JST (hang 発生: 02:12:03)
- **位置づけ**: [2026-07-03_021628](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) の引継ぎ (Phase C-2 第 2 回、同一条件再演)。**hang を初回 cycle で再現し、dpmwd2 の判別能力を初めて対象 hang に適用した**。

## 概要

### 何をしたか

021628 と同一の hang-arm 条件 (wl loaded + `nmcli radio wifi off` + BT-PAN + VPN + 手動 lid close) でサイクルテストを再演した。ビルド・デプロイは不要 (dpmwd2 稼働中)、「セッション開始」手順のみで投入した。

### 結果 (主要成果)

1. **hang 再現: 有効 cycle 1/1 (BT_PAN_VALID)** — 引き渡し後の最初の lid close (02:12:03) で hang。journal は `Performing sleep operation 'suspend'...` を最後に途絶 (既知 signature)。
2. **dpmwd2 は完全沈黙**: hang 突入 (02:12:03) から強制電源断後の再起動 (02:22) まで **~10 分経過**したが、pstore は両所在とも空 (panic 未発火)。
   - DPM watchdog (main + **late/noirq 拡張**、60 秒) — 沈黙
   - `kernel.hung_task_panic=1` (発火 ~240 秒) — 沈黙
   - watchdog の実戦発火能力は [2026-07-04_012628](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md) (intel_pch_thermal noirq 偽陽性) で検証済みのため、「動いていなかった」可能性は排除できる
3. **事前定義の解釈マトリクス ([002608](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) / 021628 から不変) により、停止段 ∈ {syscore, s2idle-enter (= timekeeping 停止後、watchdog timer も止まる領域)} が確定**。002608 の「∈ {suspend_late, noirq, syscore, s2idle-enter}」から suspend_late / suspend_noirq が除外された (device callback の 60 秒超 stall は main/late/noirq/resume_early/resume_noirq のどこにも無い)。
4. 次段は事前定義どおり: **`/sys/power/pm_trace=1` 再演 (RTC hash 照合) または `pm_test` 段階分離**。

### 統計への影響

| プール | 更新前 | 更新後 |
|---|---|---|
| hang-arm (wl-loaded + radio-off) | 6/109 ≈ 5.5% | **7/110 ≈ 6.4%** (+ 本セッション 1/1) |
| clean-arm (radio-on / wl-unloaded) | 0/112 | 0/112 (不変) |

初回 cycle での hang は p≈5.5% に対し珍しい引き (そのものの確率 ≈5.5%) だが、幾何分布の裾として異常ではない。

## 添付ファイル

- [実装プラン](attachment/2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle/plan.md)
- [hang cycle の 70-h4-probe PRE スナップショット (1783098723.pre)](attachment/2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle/hang-cycle-1783098723.pre.txt)
- [前ブート journal 全文 (セッション開始 02:03 以降、hang 突入まで)](attachment/2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle/journal-b-1-session-full.txt)

## 前提・目的

- **背景**: Phase C-2 第 1 回 ([021628](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md)) は 0/29 clean で hang 未再現。dpmwd2 (watchdog late/noirq 拡張) の判別能力を対象 hang に適用するには再現が必要だった。
- **目的**: 同一 hang-arm 条件で hang を再演し、late/noirq 段で panic するか (→ stall device 確定) / なお沈黙か (→ {syscore, s2idle-enter} に絞り込み) を判別する。
- **役割分担**: セットアップ・回収・解釈は Claude (ssh)、テザリング・lid cycle・強制電源断はユーザ。

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd2** (DPM_WATCHDOG=y TIMEOUT=60 + late/noirq 拡張 commit `b90248d63`、cmdline `panic=15`、pm_trace=0)
- `intel_pch_thermal.delay_cnt=300` (012628 の偽陽性緩和、runtime + modprobe.d) — 本セッションで偽陽性は発生せず
- スリープ: `[s2idle] deep`、hooks: 50-kbd-backlight / 58-snapshot-only / 60-s3-soak-log / 70-h4-probe
- BT/テザリング: iPad (`iMiminashiPadPro`, BT-PAN `172.20.10.13/28` on `enx98e0d98d205e`)、VPN: GSNet (strongSwan IKEv2, `nm-xfrm` interface)
- WiFi: `wl` loaded のまま `nmcli radio wifi off` (tight reading (b'') 条件維持)、電源: AC (battery 81% 充電中)
- セッション中のみ: `kernel.hung_task_panic=1`、NM autoconnect (BT-PAN/GSNet=yes, OpenWrt=no/800)、vpn-watcher / cycle-watcher transient units

## 実験タイムライン (2026-07-04 JST)

| 時刻 | 内容 |
|---|---|
| 02:03 | Phase 0: 資材コピー、旧 pstore ダンプ (012628 の PCH 偽陽性、26 ファイル) を `~/pstore-recovered/20260704_020346/` へ退避後、両所在を削除。ゲート全項目通過 |
| 02:04:17 | SESSION_START (epoch 1783098257)。sysctl・NM 設定・watcher units 起動 |
| 02:04:44-55 | セットアップ smoke 1 cycle 通過 (`wl_loaded=YES ping_running=NO`、suspend success 3→4、radio-on のため WIFI_SRC) |
| 02:05:42 | detached systemd-run で OpenWrt down + radio off (wl 残置)。GSNet[1] (WiFi 経由) 削除 |
| 02:05:44-57 | vpn-watcher が GSNet 再接続 (1 回目 NeedSecrets timeout、2 回目成功 = GSNet[2] BT-PAN 経由 `172.20.10.13`) |
| 02:12:01.5 | ユーザ lid close (**有効 cycle 1 回目**)。NM sleep → BT-PAN/VPN 論理 teardown (正常動作、063543 既知) |
| 02:12:03.8 | `Performing sleep operation 'suspend'...` を最後に **journal 途絶 = hang** |
| 02:12〜02:2x | ユーザ待機 → 自動再起動なし → 電源ボタン長押しで強制電源断 |
| 02:22 | 再起動 (dpmwd2)。**pstore 空 = panic 未発火を確認** |
| 02:25-28 | Claude 回収: pstore/journal/h4-probe 解析、撤収 (NM 平常化)、本レポート |

## 証拠と検証

### hang の確定 (durable evidence)

- 58-snapshot-only / 70-h4-probe: セッション内 **PRE 2 / POST 1** — unpaired PRE = 1783098723 (02:12:03) が hang cycle。smoke (1783098284/1783098295) はペア成立
- 前ブート journal: `PM: suspend entry` 4 / `PM: suspend exit` 4 で均衡 (通常使用 3 + smoke 1)。hang cycle の kernel entry 行は flush されず (既知 signature)
- `last -x`: 前ブートは `crash` 終了、再起動 02:22

### hang cycle の条件成立 (BT_PAN_VALID)

- PRE スナップショットの `ip xfrm state`: `src 172.20.10.13 dst 160.16.210.47` (ESP, lastused 02:11:58) — **source-IP gate = BT_PAN_VALID**
- `wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES`、wlp3s0 state DOWN (radio off)、`ping_running=NO`
- PRE 時点で `bnep_netdev=MISSING`・enx インターフェース消滅済みなのは、lid close → NM sleep の論理 teardown (02:12:01.6-1.7) が sleep hook より先に走るためで、**毎 cycle 起きる正常動作** (063543 で確立済み: 「NM の論理 teardown は suspend 前に完了、hang はその後のカーネル段」)

### 沈黙判定の妥当性 (偽陰性の排除)

- hang 突入 02:12:03 → 再起動 02:22 = **~10 分** ≫ watchdog 60s + panic=15 (~75 秒) ≫ hung_task ~240 秒
- pstore 経路の生存は同カーネル・同構成で 012628 (noirq 段 watchdog panic → EFI pstore 25 パート → 回収) により実戦検証済み
- セッション開始前に旧ダンプを削除済みのため、pstore 空 = 「panic なし」と一意に解釈できる

### 解釈: 停止段の絞り込み (002608 からの前進)

| 段 | dpmwd1 (002608) | dpmwd2 (本セッション) |
|---|---|---|
| dpm_suspend (main) | 監視・沈黙 → 除外 | 監視・沈黙 → 除外 (再確認) |
| suspend_late | 未監視 (候補) | **監視・沈黙 → 除外** |
| suspend_noirq | 未監視 (候補) | **監視・沈黙 → 除外** |
| resume_early/noirq (β 側) | 未監視 | **監視・沈黙 → 除外** |
| syscore | 未監視 (候補) | 監視不可 → **残存候補** |
| s2idle-enter (timekeeping 停止後) | 未監視 (候補) | watchdog timer 自体が停止 → **残存候補** |

H4 (btusb URB drain = main phase) は 002608 に続き二度目の disfavor。device callback 起因の仮説群 (H1 の netdev_wait_allrefs も dpm main/late 段) はさらに苦しくなり、**「デバイス callback ではなく、より深い共通経路 (syscore ops / s2idle idle-enter / プラットフォーム firmware 待ち) での永久停止」**が主戦場になった。

## 再現方法

### セッション開始 (資材: scratchpad `phase-bc-materials/`、詳細は session-commands.md)

```bash
# Phase 0: 旧 pstore 退避 + 削除 → ゲート確認 (dpmwd2 / wl / delay_cnt=300 / pstore 空)
# Phase 1:
sudo sysctl -w kernel.hung_task_panic=1
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt connection.autoconnect no ipv4.route-metric 800
# vpn-watcher / cycle-watcher transient units (transient-units-commands.sh 逐語)
# smoke 1 cycle → wl_loaded=YES 確認
# Phase 2: iPad テザリング確認後
sudo systemd-run --unit=radio-off-detached --collect bash -c "sleep 5; nmcli con down OpenWrt; nmcli radio wifi off"
# ユーザ: コンソールゲート → 手動 lid cycle
```

### hang 後の判定

```bash
sudo ls /sys/fs/pstore/ /var/lib/systemd/pstore/   # 空 = 沈黙 / ダンプあり = panic デバイス判別 (012628 ルール)
sudo journalctl -b -1 -n 30                          # 'Performing sleep operation' 途絶 = hang signature
ls /var/log/h4-probe/ | tail                         # unpaired PRE = hang cycle
```

## 次セッション引継ぎ (Phase C-3)

事前定義の分岐に従い、候補 2 つ:

1. **pm_trace 再演 (推奨)**: `/sys/power/pm_trace=1` で再演。hang 後の再起動時に RTC に埋め込まれた hash から最後に触ったデバイス/関数を照合 (`dmesg | grep "Magic number"`)。**副作用: RTC 時刻破壊 → NTP で復旧** (計画済)。s2idle-enter/syscore 領域でも「どこまで進んだか」の手掛かりが得られる
2. **pm_test 段階分離**: `/sys/power/pm_test` = freezer/devices/platform/processors/core を順に固定して suspend し、どの段まで完走するかを二分探索。1 cycle ごとの再現率が p≈6% と低いため試行回数が嵩む点に注意

いずれも dpmwd2 のまま実施可能 (リビルド不要)。資材・フックは全残置。

## 残置物 (実機の現状、02:28 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd2 稼働 (saved default)。dpmwd1 / stock 残置 |
| NM autoconnect / route-metric | 平常化済み (BT-PAN/GSNet=no, OpenWrt=yes/-1) |
| kernel.hung_task_panic | 0 (再起動で揮発、revert 不要だった) |
| transient units | 消滅 (再起動で揮発) |
| pstore | 空。旧 012628 ダンプは `~/pstore-recovered/20260704_020346/` に退避済み |
| sleep hooks 4 本 / pstore-guard / panic=15 / delay_cnt=300 | 残置 (次セッションで使用) |
| /var/log/h4-probe | PRE+2 / POST+1 追加 (削除しないこと) |
| pm_trace | 0 (次段の主役候補) |

## 関連レポート

- [2026-07-03_021628 Phase C-2 第 1 回 0/29 clean (本セッションの引継ぎ元・手順の一次ソース)](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md)
- [2026-07-03_002608 dpmwd1 hang 再現・panic 沈黙・停止段 4 候補への絞り込み (解釈マトリクスの定義元)](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md)
- [2026-07-04_012628 intel_pch_thermal 偽陽性 (watchdog 実戦発火能力の検証、偽陰性排除の根拠)](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md)
- [2026-07-02_103415 (b'') tight reading bedrock (hang-arm 条件の統計的根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
- [2026-06-28_063543 BT-PAN×VPN lid close hang の手動再現 (論理 teardown 完了後のカーネル段 hang という機序の確立元)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
