# Phase C-2 第 2 回 — dpmwd2 上での hang 再演サイクルテスト

## Context

- [2026-07-03_021628](report/2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) の Phase C-2 第 1 回は **0/29 clean で hang 未再現** (生起確率 ≈10% の範囲内)。dpmwd2 の late/noirq panic 自己申告で停止段を判別するには hang 再現が前提のため、**同一条件での再演 (第 2 回)** が引継ぎ事項。
- 目的: hang-arm 条件 (wl loaded + radio off + BT-PAN + VPN + 手動 lid close) で hang を再現し、dpmwd2 の watchdog が late/noirq 段で panic するかを観測する。
  - panic + stall device → **停止段 + デバイス確定** (機序決着へ前進)
  - なお沈黙 → 停止段 ∈ {syscore, s2idle-enter} → 次段 = pm_trace 再演 / pm_test 段階分離
- ビルド・デプロイは不要 (dpmwd2 稼働中・saved default)。「セッション開始」手順のみで再演可能。

## 実機の現状 (2026-07-04 確認済)

| 項目 | 状態 | 対応 |
|---|---|---|
| kernel | 6.12.94-dpmwd2 稼働、cmdline に `panic=15`、`[s2idle] deep`、wl loaded、pm_trace=0 | そのまま |
| sleep フック | 4 本残置 (50-kbd-backlight / 58-snapshot-only / 60-s3-soak-log / 70-h4-probe) | 存在確認済み |
| `intel_pch_thermal.delay_cnt` | **300 (偽陽性緩和済み、012628)**。runtime + modprobe.d 両方確認済 (panic 再起動を跨いでも有効) | そのまま。panic 時は対象デバイス判別必須 |
| `/var/lib/systemd/pstore/1783080747` | **7/3 の PCH thermal 偽陽性ダンプが残存** (`/sys/fs/pstore` は空、確認済) | セッション前に ~/pstore-recovered/ へ退避 → 削除 (次回 hang 判定を汚さないため。内容は 012628 attachment に保全済) |
| hung_task_panic | 0 | セッション開始で 1 に |
| NM autoconnect | 平常 (BT-PAN/GSNet=no, OpenWrt=yes) | セッション開始で切替 |
| vpn-watcher / cycle-watcher | inactive | セッション開始で再作成 |
| pstore-guard | enabled (systemd-pstore が先に回収するため suspend ブロックは不作動 — 既知の穴、今回スコープ外) | そのまま |

資材: `phase-bc-materials/` (session-commands.md / transient-units-commands.sh 等) が前セッション scratchpad (`/tmp/claude-1001/.../faf320ea-.../scratchpad/phase-bc-materials/`) に残存 → 今セッションの scratchpad へコピーして使用。

## 手順

### Phase 0: セッション前クリーンアップ (Claude, ssh)

1. phase-bc-materials を今セッション scratchpad にコピー
2. 旧 pstore ダンプ退避 + 削除 (session-commands.md 手順 2 (1)(2) 逐語):
   `~/pstore-recovered/<ts>/` へ両所在を cp -a → 削除 (`/sys/fs/pstore` は空を確認済だが手順どおり両方対象)
3. ゲート確認: `uname -r`=dpmwd2 / wl loaded / delay_cnt=300 / pstore 空 / battery 残量

### Phase 1: セッション開始 (Claude, ssh — session-commands.md「1. セッション開始」逐語)

```
sudo sysctl -w kernel.hung_task_panic=1
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt connection.autoconnect no ipv4.route-metric 800
# vpn-watcher / cycle-watcher transient units (transient-units-commands.sh 逐語)
# smoke 1 cycle (rtcwake -m no -s 10 + systemd-suspend --wait) → snapshot で wl_loaded=YES 確認
# SESSION_START epoch 記録
```

注意 (021628 の教訓): cycle-watcher はセットアップ smoke を cycle 1 に計上する (体感と 1 ズレ)。集計は durable file (`/var/log/h4-probe/` PRE/POST) と suspend_stats を正とする。

### Phase 2: ユーザ依頼 → radio off → cycle 駆動

1. **ユーザ**: iPad テザリング ON → Claude が BT-PAN IP (172.20.10.x) + GSNet active を確認
2. **Claude**: detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off` (**rmmod しない** — tight reading (b'') 維持) → ssh 切断
3. **ユーザ**: コンソールゲート (`nmcli radio wifi`=disabled + `lsmod | grep wl` 残存を目視) → 手動 lid close/open cycle **目安 30 cycle** (cycle 1 で canary 確認)

### Phase 3: hang 発生時 (本命)

1. **ユーザ**: 即 lid open → **5 分以上待つ** (late/noirq watchdog 60s + panic=15 なら ~2 分弱、hung_task_panic 経由なら最大 ~4 分強で自動再起動)。再起動しなければ強制電源断 → 起動後 `nmcli radio wifi on` + `nmcli con up OpenWrt` (セッション中は autoconnect=no のため手動) で ssh 復旧
2. **Claude** 回収 (順序厳守): pstore 回収 → **panic 対象デバイス判別** (012628 ルール: `intel_pch_thermal ... unrecoverable failure` なら偽陽性・統計不計上、それ以外の suspend_late/noirq stack なら対象 hang = 停止段確定) → レコード削除 → pstore-guard stop → sysctl 再設定 → units 再作成 → (継続時) radio off 復帰
3. 解釈マトリクス (021628 plan から不変): late/noirq panic → stall device 確定 / resume 側 stack → β 判別 / hung_task panic → pre-freeze 段 / 沈黙 → {syscore, s2idle-enter} → 次段 pm_trace

### Phase 4: 撤収 + レポート

- 終了時 (session-commands.md「3. セッション終了」): hung_task_panic=0 / NM 平常化 (autoconnect 戻し + OpenWrt metric -1) / radio on / units stop。58-snapshot-only・pstore-guard・NM 接続定義は残置
- レポート: `report/` ルール準拠 (`TZ=Asia/Tokyo date` でタイムスタンプ)、本プランを attachment に添付、pstore dump があれば attachment に退避、統計 pool 更新 (現状 hang-arm 6/109 ≈ 5.5%)
- メモリ `s2idle-btvpn-hang-mechanism-ladder` に C-2 第 2 回の結果を反映

## 役割分担

| 作業 | 担当 |
|---|---|
| クリーンアップ・セットアップ・回収・解釈・レポート | Claude (ssh) |
| iPad テザリング ON・コンソールゲート・lid cycle・(必要時) 強制電源断 | ユーザ |

## 検証方法

- セットアップ smoke 1 cycle で snapshot (`wl_loaded=YES ping_running=NO`) と journal を確認
- cycle 集計は 58-snapshot-only の PRE/POST ペア + 70-h4-probe source-IP gate (BT_PAN_VALID) で機械検証
- hang 再現時: pstore dump に stall device 入り backtrace が回収できること (沈黙も判別情報として記録)
- 未再現 (0/30) の場合: p=5.5% 前提で生起確率 ≈18%、統計 pool を 6/139 に更新してさらに 1 セッション判断
