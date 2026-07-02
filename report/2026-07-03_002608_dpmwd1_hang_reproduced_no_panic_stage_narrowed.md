# DPM_WATCHDOG カーネル上で hang 再現 (24 cycle 中 1 件) — 18 分間 panic 沈黙により停止段が「main phase より後」に絞り込まれ、H4/H2 が disfavor に転落

- **実施日時**: 2026 年 7 月 2 日 19:47 〜 7 月 3 日 00:26 JST
- **位置づけ**: [2026-07-02_182811](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md) で構築した DPM_WATCHDOG=y カーネル (`6.12.94-dpmwd1`) 上での初の hang 再現セッション (Phase C)。hang は再現したが **panic が発火せず**、これが事前定義した解釈マトリクスの第 4 行「非カバー段での停止」に該当し、大きな判別情報となった。

## 概要

### 何をしたか

hang arm と同一設計 (wl loaded + WiFi radio off + BT テザリング + VPN + 手動 lid close) を dpmwd1 カーネル上で再演した。今回は hang したら 60 秒で DPM watchdog が「どのドライバで止まったか」を panic メッセージに刻む想定だった。`kernel.hung_task_panic=1` も併用した。

### 何が起きたか

24 cycle 目で hang が再現した (1/24 ≈ 4.2%、過去の base rate ~4-9% と整合)。journal は 23:46:10 の `PM: suspend entry (s2idle)` で途切れ、これは過去 5 件の hang と同一 signature である。しかし **~18 分後にユーザが強制電源断するまで、DPM watchdog (60 秒) も hung_task (最大 ~240 秒) も一切 panic を発火させず、pstore は空**だった。

### これが意味すること (本セッションの主要成果)

panic の沈黙は事前定義した解釈マトリクスで「失敗ではなく判別情報」である:

1. **main phase (device_suspend / device_resume の callback) では止まっていない** — この段には watchdog が武装しており、60 秒超の stall は必ず panic するはずだった (panic → pstore 経路は 182811 の sysrq crash テストで実証済)
2. **pre-freeze 段の D-state stall でもない** — khungtaskd は freeze 前なら生きており、hung_task_panic=1 だった
3. **→ 停止段は suspend_late / suspend_noirq / syscore / s2idle-enter のいずれか** (6.12 では何も監視していない領域)

機序ラダーへの影響:

- **H4 (btusb URB drain)**: `btusb_suspend` は main phase の callback であり、そこで 60 秒超止まれば watchdog が panic したはず → **強く disfavor**
- **H2 (bnep_session kthread)**: hang cycle の PRE snapshot で `kbnepd_session=NOT FOUND` — kthread は suspend 時点で存在すらしていない → **disfavor**
- 探索対象は「より深い段 (late/noirq/syscore/s2idle-enter)」へ移動

### 次の手 (本セッション中に準備完了)

watchdog を late/noirq 段へ拡張する小パッチ (解釈マトリクスで事前定義済みの次段) を作成し、`6.12.94-dpmwd2` としてビルドした。加えて `PM_TRACE_RTC=y` も有効化 (dpmwd2 でも沈黙した場合の最終判別手段: RTC に device hash を刻み、強制電源断後の再起動で照合できる)。次セッションで dpmwd2 をデプロイして再演する。

## 添付ファイル

- [実装プラン (Phase A-C 共通)](attachment/2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed/plan.md)

## 前提・目的

- **背景**: [182811](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md) で dpmwd1 カーネル + panic=15 + pstore-guard + pstore end-to-end 検証が完了
- **目的**: hang arm 30 cycle を dpmwd1 上で再演し、hang 時の DPM watchdog panic で stall device を特定する
- **事前定義の解釈マトリクス** (182811 から継承): suspend 側 stack = 機序決着 / resume 側 = β 判別 / hung_task = pre-freeze 段 / **panic なし = 非カバー段 (それ自体が判別情報)** ← 今回はこれに該当
- **役割分担**: セットアップ・ゲート・回収は Claude (ssh)、cycle 駆動はユーザ手動 (WiFi off で ssh 切断中)

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd1** (DPM_WATCHDOG=y TIMEOUT=60, panic=15)
- スリープ: `[s2idle] deep`
- hooks: 50-kbd-backlight / **58-snapshot-only (本セッションで再デプロイ、残置)** / 60-s3-soak-log / 70-h4-probe
- BT/テザリング: iPad (`iMiminashiPadPro`, BT-PAN IP `172.20.10.13/28`)、VPN: GSNet (strongSwan IKEv2)
- WiFi: `wl` loaded のまま `nmcli radio wifi off` (rmmod しない — 103415 の tight reading (b'') 条件を維持)
- セッション中のみ: `kernel.hung_task_panic=1`、NM autoconnect (BT-PAN/GSNet=yes, OpenWrt=no/800)、vpn-watcher / cycle-watcher transient units

## 実験タイムライン

| 時刻 (JST) | 内容 |
|---|---|
| 19:47 | SESSION_START (epoch 1782989248)、baseline 13 項目確認 (dpmwd1、pstore 空、guard 正常) |
| 19:47-19:48 | 58-snapshot-only 再デプロイ、sysctl、NM 設定、transient units 起動 |
| 19:48 | smoke test 1 cycle (`wl_loaded=YES ping_running=NO` 確認) |
| ~19:50 | ユーザ確認: iPad テザリング ON 済 → BT-PAN `172.20.10.13` + GSNet active 確認 |
| ~19:52 | detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off` (wl は残置)、ssh 切断 |
| ~19:53 | ユーザコンソールゲート通過 (`radio=disabled` + lsmod に wl 残存) |
| 19:53-23:46 | ユーザ手動 cycle 駆動 (cycle 1 canary 3 項目通過報告あり)、23 cycle clean |
| **23:46:10** | **cycle 24 で hang** (journal 最終行 `PM: suspend entry (s2idle)`、過去 5 hang と同一 signature) |
| 23:46-00:03 | ユーザが蓋 open 後も **~18 分間無反応 (panic 発火なし)** |
| ~00:03 | ユーザ強制電源断 → 再起動 (00:04 boot) → WiFi 復旧 |
| 00:05-00:15 | Claude 回収: pstore 空を確認、durable evidence 集計、source-IP gate、NM 平常化 |
| 00:15-00:26 | watchdog late/noirq 拡張パッチ作成・commit、dpmwd2 config (PM_TRACE_RTC 追加)、ビルド開始、本レポート作成 |

## 証拠と検証

### 1. hang の実在と signature 一致

- boot 履歴: 7/2 18:26 boot が「crash」終了 (= 強制電源断)、7/3 00:04 現 boot
- 前 boot journal 最終行: `7月 02 23:46:10 kernel: PM: suspend entry (s2idle)` — exit 欠落 (063543 以来の hang signature と同一)
- suspend_stats: 現 boot で 0/0 (リセット)、前 boot 分は journal と snapshot で裏付け

### 2. hang cycle の validity (全ゲート通過)

hang cycle の PRE snapshot (epoch 1783003570 = 23:46:10 直前):

```
xfrm_state=2 xfrm_policy=14        ← VPN active、policy=14 は BT-PAN 経由プロファイル
ping_running=NO                     ← 連続 ping 混入なし
wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES  ← wl-loaded-radio-off 条件維持
bnep_netdev=MISSING                 ← 過去 hang と同じ teardown 状態
kbnepd_session=NOT FOUND            ← ★ H2 disfavor の直接証拠
```

70-h4-probe の .pre から xfrm src 抽出: `src 172.20.10.13` = **BT_PAN_VALID** (WiFi 経由 VPN の混入なし)。

### 3. セッション集計

- snapshot-only PRE 25 / POST 24 (SESSION_START 以降) = smoke 1 + 実 cycle 24、**unpaired PRE 1 = hang cycle**
- 全 25 PRE で `wl_loaded=YES` 維持 (条件 drift なし)
- hang rate 1/24 ≈ 4.2% (過去 pooled 5/56 ≈ 9%、043251/102907 ≈ 4-5% と整合)

### 4. panic 不発の確定

- `/sys/fs/pstore` 空、`/var/lib/systemd/pstore` 空 (pstore-guard も「no pstore record found」)
- hang 23:46:10 → 強制電源断 ~00:03 = **~17-18 分間、watchdog (60s) も hung_task (最大 ~240s) も沈黙**
- hung_task_panic=1 は同一 boot 内で設定済み (19:47 設定、hang まで reboot なし) — 有効だったことは確実
- panic → pstore → 自動再起動の経路自体は 182811 の sysrq テスト 2 回で実証済み → 「経路が壊れていた」可能性は排除

### 5. 解釈の補正 1 点 (記録)

事前プランは「khungtaskd は freeze されないため pre-freeze/notifier 段の stall も拾う」としていたが、正しくは **khungtaskd は freezable** (`kernel/hung_task.c` の watchdog ループが `set_freezable()` を呼ぶ) であり、hung_task が有効なのは freeze 完了前の段のみ。本セッションの結論には影響しない (freeze 前の stall なら hung_task が拾えたはずで、それも沈黙した、という論理は成立)。

## 機序ラダーの更新

| 仮説 | 更新 |
|---|---|
| H4 (btusb URB drain in `btusb_suspend`) | **強く disfavor**: main phase callback での 60 秒超 stall なら watchdog が panic したはず |
| H2 (bnep_session non-freezable kthread) | **disfavor**: hang cycle の suspend 時点で kbnepd 不在 (`NOT FOUND`) |
| H1 (xfrm dev ref leak) | 棄却圏継続 (六度目の negative 相当: 停止段が dpm 前半でないことと整合) |
| H6 / H7 | 未判別のまま、ただし探索段が late/noirq/syscore/s2idle-enter に移動したため要 reframe |
| **新規の絞り込み** | **停止段 ∈ {suspend_late, suspend_noirq, syscore, s2idle-enter}** (6.12 の非監視領域)。074509 の「dpm_suspend (main) 段で停止」推定は本結果と矛盾し要修正 |

## 再現方法

### セッションセットアップ (182811 の Phase C 手順)

```bash
# hook / sysctl / NM / transient units (詳細は 182811 レポートと attachment 参照)
sudo sysctl -w kernel.hung_task_panic=1
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800 connection.autoconnect no
# vpn-watcher / cycle-watcher transient units 起動 (systemd-run --collect)
# smoke 1 cycle → iPad テザリング ON 確認 → detached で radio off (rmmod しない)
```

### hang 時

即 lid open → 5 分以上待つ → 自動再起動しなければ強制電源断 → 起動後に pstore (`/sys/fs/pstore` と `/var/lib/systemd/pstore`) を確認。

## 次セッション引継ぎ (dpmwd2)

### 準備済み (開発機)

1. **watchdog late/noirq 拡張パッチ**: `drivers/base/power/main.c` の `device_suspend_late` / `device_suspend_noirq` / `device_resume_early` / `device_resume_noirq` の `dpm_run_callback` を `dpm_watchdog_set/clear` で挟む (commit b90248d63、dpmwd/6.12.94 ブランチ)
2. **config**: `LOCALVERSION="-dpmwd2"` + `PM_TRACE=y` + `PM_TRACE_RTC=y` 追加 (PM_TRACE は runtime で `/sys/power/pm_trace` を 1 にするまで inert。dpmwd2 でも沈黙した場合の最終判別手段 — RTC に直前 device の hash を刻み、強制電源断→再起動後の dmesg `Magic number:` 行で照合。使用時は RTC 時刻が壊れる副作用あり、NTP で復旧)
3. ビルドは本レポート作成時点で進行中 (incremental)

### dpmwd2 セッションの設計

- デプロイ手順は 182811 と同一 (dpkg -i → grub-set-default + **sync** → ゲート (a)(a2))。crash テストは省略可 (経路検証済み)
- 再演条件は本セッションと同一。**期待される分岐**:
  - **late/noirq で panic** → stall device 特定、機序決着へ前進
  - **なお沈黙** → 停止段は syscore / s2idle-enter / (watchdog timer も止まる領域) → `/sys/power/pm_trace` 有効化での再演 (RTC hash 照合) か、`pm_test` 段階分離へ

### 注意事項

- grubenv 変更後は必ず `sync` (182811 の教訓)
- 58-snapshot-only hook は実機に残置済み (再デプロイ不要)
- NM 設定は平常化済み (次セッションで再設定要)
- `kernel.hung_task_panic` は reboot で消える (再設定要、hang 後の継続時も同様)

## 残置物 (実機の現状、00:26 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd1 稼働中 (saved default) |
| 58-snapshot-only | **残置** (次セッションで使用) |
| NM autoconnect / route-metric | **平常化済み** (BT-PAN/GSNet=no, OpenWrt=yes/-1) |
| kernel.hung_task_panic | 0 (reboot でリセット、平常) |
| transient units | 消滅 (reboot、--collect) |
| pstore | 空 |
| pstore-guard / panic=15 / grub.bak-dpmwd | 182811 のまま残置 |
| /var/log/h4-probe | PRE +25 / POST +24 追加 (hang cycle の PRE 含む、削除しないこと) |

## 関連レポート

- [2026-07-02_182811 dpmwd1 ビルド・デプロイ・pstore e2e 検証 (本セッションの前提)](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-07-02_103415 (b'') tight reading bedrock 化](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
- [2026-07-02_092013 方法論監査 (S4 推奨)](2026-07-02_092013_hang_investigation_methodology_audit.md)
- [2026-06-28_074509 カーネルソース解析 (H1-H5、「dpm_suspend 段で停止」推定 — 本セッションで要修正と判明)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-07-01_102907 hang 直前 snapshot identical (観測限界の実証)](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md)
