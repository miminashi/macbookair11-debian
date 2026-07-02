# S3'' rerun: VPN watcher + 30 valid cycle で 030349 の真の続行を実施

## Context

直前セッション [report/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md](../../../projects/macbookair11-debian/report/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) は表面的に「S3'' (traffic-only off) 30/30 clean」を達成したが、retro-classify で **cycle 1 のみ VPN active (xfrm_state=2)、cycle 2-30 はすべて xfrm_state=0 (= VPN inactive、BT-PAN 単独状態)** と判明し、有効 trial が N=1 になっていた。同 confound は 200520 (S3 hook 32/32 clean → cycle 1 のみ valid) にも波及している。

本セッション開始時の Plan 立案フェーズ (Explore agent による過去 retro-classify) で、**041006 (S1 btusb pre-unload 22/22 clean) は 22/22 cycle すべて xfrm_state=2 で fully valid**、**064608 (driver path 25/25) は cycle 1 + cycle 13-25 = ~14 valid** と確定。つまり機序ラダーは「全 confound」ではなく、**S1 (btusb 除去) の証拠は依然 N=22 で有効、S3'' のみが N=1 confound**。

(注: 以下「Phase 0〜7」は本セッションの**実行 phase** を指す。Plan 立案中の Explore agent 調査は別カウントで、上記の baseline 確認と retro-classify はそこで既に完了している。)

本セッションは引継ぎ (ii) を実行する: **VPN watcher loop で各 cycle で VPN を確実に再接続させ、xfrm_state>0 を valid gate として 30 valid cycle を集める**。**S3 hook (57-bnep-down) は投入しない bare condition rerun** (= 030349 と同じ条件、bnep/VPN active 状態で suspend に進入する)。これにより:

- 元の hang 観測 (063543 の 3/3 hang) と **概ね同条件で N=30 valid** の hang 率を測定
- 0 hang / 30 valid → 元 hang との不一致 → 環境差分 (下記表) のいずれが効くかを再評価
- 1+ hang / 30 valid → 元の hang を valid 再現、機序仮説のラダーを次段 (S2/S4/S5) に進める材料

これは「S3 hook の効果測定」とは異なる: S3 hook (200520) の効果再検証 (= bnep teardown を能動的に挟む実験) は、本セッション結果次第で別途設計する。本セッションは **「063543 hang 条件が valid trial で再現するか」を確定する bare condition rerun** が目的。

### 063543 (= reproduce target) との条件差 (Phase 5 判定で重要)

063543 を改めて確認した結果 (advisor 指摘で実施):

| 項目 | 063543 (3/3 hang) | 本セッション計画 |
|---|---|---|
| BT-PAN peer | **iPhone** (`iMiminashiSE`, `CC:60:23:AF:2C:60`, BT-PAN IP `172.20.10.6/28`) | **iPad** (`iMiminashiPadPro`, `34:42:62:16:03:F6`, BT-PAN IP `172.20.10.13/28`) |
| WiFi | **off** (= 完全 BT-PAN 単独経路) | **on** (metric 800、BT-PAN 750 < WiFi 800 で routing は BT-PAN だが WiFi NIC は active = suspend 時に device-suspend 経由) |
| traffic | 素 traffic (= ユーザ実使用、ssh 操作程度) | 同等 (heavy traffic generator なし、watcher と snapshot hook の通信のみ) |
| AC | AC | AC |
| 駆動 | 手動 lid close + 電源ボタン wake (rtcwake 不使用) | 同上 |
| hook | 50/60 のみ | 50/60/70 + 58-snapshot-only (= 030349/200520 と同等の観測装置あり) |

→ **0 hang / 30 valid の場合の解釈**: (a) iPhone→iPad の peer 差で hang 消失、(b) WiFi off→on の active NIC 差、(c) 70/58 hook の active な suspend-time 処理が race を変えた、(d) 063543 baseline が想定より低い (3 hang は外れ値)、のいずれか。advisor 諮問で判定を sharpen する。

→ **1+ hang / 30 valid の場合**: iPad + WiFi 介在込みでも hang 再現 = 機序ラダーを次段 (S2/S4/S5) に進める。stuck signature を 70-h4-probe / 58-snapshot-only pre snapshot から retro-analyze。

## 進め方

### Phase 0: 開始時の前提確認 (5 分、ssh 1 回)

期待値:
- hooks: `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の 3 個
- h4-probe mode: `beta`
- NM autoconnect: BT-PAN/GSNet 両方 `no`、route-metric: `-1`
- suspend_stats: success=187, fail=0
- boot_id: `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変)
- transient units (vpn-watcher, cycle-watcher) 両方 inactive

Plan 立案中の Explore agent 調査で既に baseline 確認済 (全て期待通り、再起動なし)。Phase 0 は本セッションの実行開始時に 1 回だけ実施し、Plan 立案からの時間経過で何も変わっていないことを確認する safety check。

### Phase 1: 一時設定 (5 分、ssh 1 回 + ユーザ操作 1 回)

実機 ssh:
```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
```

ユーザ操作: iPad テザリング ON → NM GUI で `iMiminashiPadPro ネットワーク` (BT-PAN) up → GSNet (VPN) up。

確認 (ssh):
- `nmcli -t con show --active`: GSNet, BT-PAN, OpenWrt の 3 つ
- `ip xfrm state | grep -c "^src "` → 2 (= VPN active)
- `ip xfrm state | grep "^src "` で `src 172.20.10.13 dst 160.16.210.47` を確認 (= VPN が BT-PAN 経由)

### Phase 2: 58-snapshot-only hook + VPN watcher デプロイ (5 分、ssh 2 回)

#### 2a. 58-snapshot-only hook 投入

030349 で使用したものと同じ:
```sh
#!/bin/sh
case "$1" in
  pre)
    rx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    sleep 0.5
    rx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    logger -t 58-snapshot-only "bnep delta 500ms: rx=$((rx_after-rx_before))B tx=$((tx_after-tx_before))B"
    if pgrep -f kbnepd > /dev/null 2>&1; then
      logger -t 58-snapshot-only "bnep_session kthread alive (H2 driver present)"
    else
      logger -t 58-snapshot-only "WARN bnep_session kthread NOT FOUND"
    fi
    if ip -br link show 2>/dev/null | grep -qE "^(bnep0|enx98e0d98d205e)[[:space:]]"; then
      logger -t 58-snapshot-only "bnep netdev present"
    else
      logger -t 58-snapshot-only "WARN bnep netdev MISSING"
    fi
    xfrm_state=$(ip xfrm state 2>/dev/null | grep -c "^src ")
    xfrm_policy=$(ip xfrm policy 2>/dev/null | grep -c "^src ")
    logger -t 58-snapshot-only "xfrm: state=${xfrm_state} policy=${xfrm_policy}"
    ;;
esac
```

`sudo chmod 755 /usr/lib/systemd/system-sleep/58-snapshot-only`

#### 2b. VPN watcher 起動

```bash
sudo systemd-run --unit=vpn-watcher --collect bash -c '
while true; do
  if ip -br link show enx98e0d98d205e 2>/dev/null | grep -q "UP"; then
    if ! nmcli -t -f NAME con show --active | grep -qx "GSNet"; then
      logger -t vpn-watcher "BT-PAN up but GSNet inactive, re-activating"
      nmcli con up GSNet 2>&1 | logger -t vpn-watcher
      sleep 5
    fi
  fi
  sleep 3
done
'
```

3 秒間隔で BT-PAN netdev が UP かつ GSNet が inactive なら nmcli con up GSNet を発火、5 秒待って次の poll。

#### 2c. cycle-watcher 起動 (進捗ログ)

```bash
sudo systemd-run --unit=cycle-watcher --collect bash -c '
prev=$(cat /sys/power/suspend_stats/success)
while true; do
  curr=$(cat /sys/power/suspend_stats/success)
  if [ "$curr" != "$prev" ]; then
    logger -t cycle-watcher "suspend_stats success: $prev -> $curr (delta=$((curr-prev)))"
    prev=$curr
  fi
  sleep 5
done
'
```

### Phase 3: smoke test + reconnect 遅延測定 (15 分、ユーザ操作 2 cycle + ssh 数回)

VPN watcher が機能していることの確認と、**各 cycle で wake 後にユーザが何秒待ってから次 lid close すべきか**を実測する (advisor 指摘: BT-PAN rename + flaky charon-nm + watcher 3s poll + IKE handshake で reconnect は 15-20s 前後)。

#### smoke test 手順 (cycle 1)

1. ユーザに「**蓋閉じ → 30-60 秒待機 → 電源ボタン短押し**」を 1 回依頼
2. **wake 直後にユーザにすぐ蓋を閉じないよう依頼** (= wake → 次 cycle まで時間を空ける)
3. Claude が 30 秒間 ssh で 5 秒ごとに以下を測定:
   - `nmcli -t -f NAME con show --active | grep -c "^GSNet$"`
   - `ip xfrm state 2>/dev/null | grep -c "^src "`
4. ssh で reconnect 完了時刻を確認:
   - `journalctl -t vpn-watcher -S "10 minutes ago"` で `BT-PAN up but GSNet inactive, re-activating` から `Connection successfully activated` までの秒数を確認
   - `journalctl -t charon-nm` で `IKE_SA GSNet established` のタイムスタンプを確認
5. wake から GSNet active までの秒数 (= `T_reconnect`) を記録。Phase 4 で「**wake 後 T_reconnect + 5 秒待ってから次 lid close**」のガイドに使う

#### smoke test 判定 (cycle 2)

6. cycle 1 で T_reconnect を実測したら、その時間 + 5 秒待ってから cycle 2 (蓋閉じ + 待機 + 電源ボタン wake) を依頼
7. cycle 2 終了後、58-snapshot-only の `xfrm_state` を確認:
   - `journalctl -t 58-snapshot-only -S "@$CYCLE2_START_EPOCH"` で当該 cycle の xfrm_state を抽出
   - **xfrm_state≥1 なら gate 動作 OK** → Phase 4 へ
   - xfrm_state=0 なら watcher が間に合っていない → watcher の sleep を 1 秒に短縮、または T_reconnect を再計測して待機時間を増やす

#### 失敗時の対処

- `nmcli con up GSNet` が `Error: Connection activation failed` を返す → charon-nm の状態確認、必要なら `systemctl restart NetworkManager` (ただし NM 再起動は他の側面影響あるので最終手段)
- watcher が動いていない → `systemctl status vpn-watcher.service` で確認、journal が空なら再デプロイ
- BT-PAN 自体が wake で再接続しない → 別問題 (autoconnect=yes が機能していない)、NM GUI で手動 up

### Phase 4: 30 valid cycle 駆動 (~80-100 分)

#### 各 cycle のユーザ手順 (Phase 3 で実測した T_reconnect ベース)

1. 蓋を閉じる
2. 30-60 秒待機
3. 電源ボタン短押しで wake
4. **画面が点いたら "T_reconnect + 5 秒" 待ってから次 cycle の蓋閉じへ** (= VPN が再接続される時間を必ず確保)
5. 1 cycle ≒ 60-120 秒 (蓋閉じ + 待機 + wake + reconnect 待ち + 次の蓋閉じ)

#### Claude 側の管理 (各 cycle 後)

- `journalctl -t 58-snapshot-only -S "@$LAST_CYCLE_EPOCH"` で当該 cycle の xfrm_state を抽出
- valid (state>0) / invalid (state=0) を集計
- 30 valid 累積を target、invalid 混入なら追加 cycle で valid を集める (invalid 連続 ≥3 なら watcher が機能していないので一時中断 + debug)
- 進捗監視: 5-10 cycle ごとに `cycle-watcher.service` の journal を確認、ユーザに「いま何回目」を聞きながら進める。ユーザが疲れたら中断・再開可能 (transient unit 常駐)

#### hang 判定 (各 cycle 毎)

- boot_id 不変 + suspend_stats success +1 + `PM: suspend entry/exit` ペア完備 → clean
- いずれか欠落 → hang
  - 強制電源断 (電源ボタン長押し) → boot_id 変化
  - 必ず stuck signature を取る: 最終 `/var/log/h4-probe/*.pre` snapshot、最終 58-snapshot-only journal 行、`s3-soak.log` の SLEEP→(WAKE 欠落)→BOOT パターン、`journalctl -b -1` 末尾の dpm/charon-nm 行
  - pstore 確認も一応するが、stock kernel は DPM_WATCHDOG 無効のため backtrace は通常出ない (= 074509/041006 観察と整合)
  - hang 発生時点で本セッション目的達成 (= 元 hang を valid 再現) → Phase 4 を打ち切り Phase 5 へ

### Phase 5: 集計 + 機序評価 (10 分)

統計:
| 指標 | 期待 (0 hang clean 系) | 期待 (1+ hang) |
|---|---|---|
| boot_id | 不変 | 変化 (再起動) |
| suspend_stats success delta | +30 (+invalid 数) | +N (hang 前まで) |
| valid cycle 数 | 30 (gate 後) | (hang 発生時点の valid 累積) |
| hang 数 | 0 | 1+ |

判定 (Context line 30-32 の解釈枝と同一、ここで再掲):
- **0 hang / 30 valid** → 「素 traffic + bnep/VPN active + 手動 lid close」で 30 連続 clean → 063543 baseline (~10%) との不一致 → (a) iPhone→iPad の peer 差、(b) WiFi off→on の active NIC 差、(c) 70/58 hook の active 処理が race を変えた、(d) 063543 baseline が想定より低い (3 hang は外れ値) のいずれか、を advisor 諮問で sharpen
- **1+ hang / 30 valid** → 元 hang を valid 再現 → 機序仮説のラダーを次段に進める (S2 xfrm flush / S4 DPM_WATCHDOG / S5 btusb async)

### Phase 6: クリーンアップ (5 分、ssh 1 回)

#### 6a. clean 完走 (Phase 4 で 30 valid に到達) の cleanup

```bash
sudo systemctl stop vpn-watcher.service cycle-watcher.service
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
```

#### 6b. hang 発生後の cleanup (強制電源断 → 再起動後)

transient units (vpn-watcher / cycle-watcher) は再起動で自動消滅。残りは 6a と同じコマンドで revert:
```bash
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
```

ただし hang 直前の `/var/log/h4-probe/*.pre` 最終 snapshot と `/var/log/s3-soak.log` の SLEEP→(WAKE 欠落)→BOOT 行は Phase 7 で添付するため、cleanup 前に Claude が `scp` または ssh cat で取得しておく。

#### 期待 final 状態 (設定面のみ、本セッション開始時と同じ)

- hooks: `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の 3 個 (= Phase 0 期待値と同じ)
- transient units: vpn-watcher / cycle-watcher 両方 inactive (or unit not found)
- NM autoconnect: BT-PAN/GSNet 両方 no、OpenWrt route-metric -1

なお以下は本セッションで変化する (= 本セッション開始時とは異なる、これは正常):
- `suspend_stats success`: +30 (+invalid 数)、hang 発生時は再起動で 0 リセット → 再起動後の累積分
- `/var/log/h4-probe/*.pre` snapshot count: +30 ペア前後 (70-h4-probe 由来)
- `boot_id`: clean なら不変、hang 発生時は変化

### Phase 7: メモリ更新 + レポート作成 (20 分)

#### 7a. メモリ更新

- `s2idle-btvpn-hang-mechanism-ladder`: Phase 1 retro-classify 結果 (041006 N=22 valid、064608 ~14 valid、200520/030349 N=1) と本セッション S3'' rerun 結果を統合反映
- `MEMORY.md`: index の description を最新結果に合わせて訂正

#### 7b. レポート作成

`report/yyyy-mm-dd_hhmmss_<英語名>.md`:
- ファイル名は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (LLM 推測禁止)
- 英語名候補: `s2idle_btvpn_s3pp_vpn_watcher_<判定>_<valid_N>` 等
- 添付ディレクトリ: `report/attachment/<上記ファイル名 .md なし>/`
- 添付内容: 本プランファイル (`plan.md`)、Phase 1 retro-classify ログ、cycle 駆動ログ、58-snapshot-only 全発火ログ、vpn-watcher journal 抜粋

## 重要な設計判断 (advisor 諮問で確認済)

1. **S3 hook (57-bnep-down) は投入しない bare condition rerun**: 030349 と同条件 (snapshot のみ) で valid trial を集める設計。S3 hook の効果再検証 (200520 の confound) は本セッション結果に依存して別途設計
2. **valid gate は xfrm_state>0**: 030349/200520 で「cycle 1 のみ valid」だったのは watcher 不在で各 cycle resume 後に VPN が再接続されなかったため。本セッションは vpn-watcher で各 cycle に reconnect を保証、smoke test で実際の T_reconnect を測ってから本駆動
3. **判定の解釈**: 0 hang / 30 valid の解釈は Context line 30 と Phase 5 で同期した 4 候補 ((a)peer、(b)WiFi、(c)hook 影響、(d)baseline 低) を持つ → どちらの結果でも次セッション設計を出せる
4. **ユーザ拘束時間**: 30 valid cycle で ~80 分、watcher 失敗で invalid 混入なら +α、hang 発生で早期打ち切り。cycle-watcher.service が transient unit として常駐するので中断・再開可能 (ssh が切れても実機側は動き続ける)

## 検証方法 (各 phase の通過条件)

| Phase | 通過条件 | 失敗時の対処 |
|---|---|---|
| 0 | baseline 全項目 期待値一致 | 再起動・hook 残存・autoconnect 残存があれば修正 |
| 1 | 3 connections active + xfrm state ≥ 1 + VPN endpoint が BT-PAN IP | ユーザに NM GUI 操作のやり直し依頼 |
| 2 | 58-snapshot-only 手動 smoke (`sudo /usr/lib/.../58-snapshot-only pre suspend`) で 4 行正常出力 + vpn-watcher.service active | script 修正 (dash 互換、kbnepd 名等) |
| 3 | smoke test cycle で `vpn-watcher` log に reconnect イベント + xfrm_state>0 | watcher の sleep interval を 1 秒に短縮、nmcli の return code 確認 |
| 4 | 30 valid cycle 累積、各 cycle で boot_id 不変 | hang 発生時はユーザに強制電源断依頼、Phase 5 で hang 数集計 |
| 5 | 統計まとまる | (判定は中立) |
| 6 | hooks 3 個、transient units 全 inactive、autoconnect=no | 漏れあれば追加修正 |
| 7 | レポート + メモリ更新完了 | Discord 通知が来ない場合は PostToolUse hook 設定確認 |

## 関連ファイル / コマンド (再利用)

- 本プランファイル: `/home/miminashi/.claude/plans/report-2026-06-30-030349-s2idle-btvpn-s3-frolicking-pine.md` (本ファイル)
- 直前レポート: `report/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md`
- 直前プラン (S3'' の元): `report/attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/plan.md` (58-snapshot-only スクリプトの origin)
- 関連メモリ: `[[s2idle-btvpn-hang-mechanism-ladder]]`, `[[s2idle-observation-phase]]`, `[[s3-revival-evaluation]]`
- ssh wrapper: 通常の `ssh miminashi@macbookair2015.lan` (sudo NOPASSWD 設定済)

## 次セッション引継ぎ (本セッション完走後)

判定別:
- **0 hang / 30 valid** → advisor 諮問で baseline 再評価 + 「S3 hook の本来の効果測定」設計 (200520 retro-classify は確定済なので、別途 S3 hook + VPN watcher で 30 valid cycle を集める実験)
- **1+ hang / 30 valid** → 機序ラダーを次段へ:
  - 一次候補: **S4 DPM_WATCHDOG** (stuck 位置を kernel から取る、決定打)
  - 二次候補: **S2 xfrm flush** (H1 直接介入)、または **S5 btusb async URB** (H4 直接修正)
  - 041006 の N=22 valid (btusb 除去で hang 消失) は依然 H4 寄りの中等度証拠、S4 で確証
