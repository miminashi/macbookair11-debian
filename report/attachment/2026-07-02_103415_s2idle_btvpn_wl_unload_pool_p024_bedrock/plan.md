# s2idle+WiFi-off+wl 完全 unload の cycle 拡大 — (b'') tight bedrock 化 (統計有意化)

## Context

130206 セッション (2026-07-01) で「WiFi-off + `rmmod wl` (cfg80211 存置) + BT-PAN + VPN + 手動 lid close/wake」を 30 cycle 駆動し、**30/30 BT-PAN-VALID cycle 全数 clean、hang 0、boot_id 不変、`unregister_netdevice: waiting` 0** を確認した。同時に advisor 諮問で全 6 セッションが単一変数「wl-loaded-AND-radio-off」で綺麗に分離される tight reading (candidate **(b'')**) が浮上した:

- wl-unloaded (130206): 0/30 clean
- wl-loaded, radio-on (061553/041006): 0/52 clean
- wl-loaded, radio-off (063543/043251/102907): 5/56 hang (~9%)

しかし 130206 単独の 30/30 は決定的ではない。base rate ~4.3-5% (043251 1/20 + 102907 1/26 = pooled 2/46 ≈ 4.3%) で **(0.957)³⁰ ≈ 27%** の確率で wl 無関係でも 30/30 clean が偶然起きる。Fisher exact (5/56 vs 0/30) 片側 p ≈ 0.11 で有意水準未達。

本セッションは 130206 と**完全同一設計**で追加 cycle を回し、pool した clean arm 数で有意化を狙う。

### cycle 数の設計判断 (advisor 事後指摘反映)

hang arm を 3 セッション pool (5/56 = 063543+043251+102907) している以上、clean arm も対称に 130206 (0/30) を pool するのが論理的整合。pooling を認めると:

| 選択肢 | 新規 cycle | pool 後 clean arm | Fisher exact (vs 5/56) | 所要時間 (Phase B-4 のみ / 全体) |
|---|---|---|---|---|
| **主案 (advisor 推奨)** | **+30** | 0/60 (30 新+30 pool) | 片側 p ≈ **0.024** | ~30-60 分 / ~50-90 分 |
| 代替案 (ユーザ選択可) | +60 | 0/90 (60 新+30 pool) | 片側 p ≈ **0.007** | ~60-120 分 / ~90-180 分 |

(130206 実測 pace ~55 秒/cycle、上限は user 休憩込みで 2-3 分/cycle)

主案 (+30) を採る根拠:
- hang arm 3 セッション pool の対称性 = 統計的整合
- 130206 の 0/30 は同一設計・同一実機・直前セッションで捨てるのが勿体ない
- 130206 プラン Risk 表「ユーザ疲労 (60 cycle × 2-3 時間)」を直接除去
- 有意水準 p < 0.05 到達は主案でも達成

代替案 (+60) の理由・使い分け:
- **(B1) +60 して pool 0/90** (Context 表の代替案): 主案より圧倒的に強い証拠 (p ≈ 0.007)。ユーザが time-cost を惜しまず「より確実に決着したい」場合
- **(B2) +60 して pool しない fresh 0/60** (代替の代替): 実験は同じ +60 cycle だが reporting で 130206 の 0/30 を discard。主案と同じ p ≈ 0.024 だが optional-stopping 批判に robust。厳格な事前登録 confirmatory publication 相当を目指す場合 (本実験は exploratory なので差は小さい)

いずれの代替案も cycle 数を 60 に上書きするだけで実験手順は変更不要 (reporting は B-5 の headline 段で選択)。

**以下のプランは主案 (+30, pool) 前提で書く**。ExitPlanMode 承認時にユーザが代替案を希望する場合は Phase B-4 の目標 cycle を 30 → 60 に、B-5 集計の期待 count を +30 → +60 に上書きする。

### 結果の非対称性 (130206 継承、ユーザ事前案内で明記)

- **1+ hang** → 「wl 完全除去でも再現 = wl 非依存」bedrock。決定的、強い結論。次は S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) で dpm_suspend stall device 特定へ
- **主案 30/30 clean (pool 0/60)** → Fisher p ≈ 0.024 で有意、**(b'') tight bedrock 化**
- **代替案 B1 60/60 clean (pool 0/90)** → Fisher p ≈ 0.007 でより strong (但し pool 前提なので optional-stopping 批判の余地は主案と同じ)
- **代替案 B2 60/60 clean (fresh 0/60, pool しない report)** → Fisher p ≈ 0.024 (主案と同水準)、optional-stopping 批判に完全 robust
- どの clean 分岐でも次は (ii) 041006 の btusb arm を WiFi-off で N 拡大 or (iii) non-btusb driver 除去 (H6 vs H7 判別)
- **hang の catch 確率**: 主案 +30 cycle で ~73%、代替案 +60 cycle で ~93% (base rate 4.3%) ← 主案で 27% / 代替案で 7% は ambiguous な clean の余地

## 主要参照ファイル

- 直近 report: `report/2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md` (本セッション設計の直接の親)
- 直近 plan: `report/attachment/2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint/plan.md` (本プランはこれを cycle 数のみ変更して継承)
- 前々セッション report (WiFi-off hang): `report/2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md`
- カーネルソース解析 (H1/H2/H4): `report/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md`
- CLAUDE.md (ssh 手順 + レポート作成ルール)

## 環境情報 (実験開始時点、実機 baseline 確認済 2026-07-02)

- 機種: MacBook Air 11" (Early 2015) / Debian 13 trixie / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks (baseline): `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の 3 個
- 電源: 全 cycle AC
- BT/テザリング: `btusb` / `hci0` (98:E0:D9:8D:20:5E)、peer = iPad、BT-PAN 172.20.10.13/28
- VPN: NM `GSNet` = strongSwan IPsec/IKEv2 (charon-nm, GW 160.16.210.47, inner 192.168.83.1/32)
- WiFi (baseline): `wl` DKMS (broadcom-sta 6.30.223.271), `wlp3s0` UP, `OpenWrt` 接続中, refcount=0
- baseline (2026-07-02 実機確認): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (**130206 と同一 = hang なし継続の証拠**)、suspend_stats 31/0、NM autoconnect 両方 no、OpenWrt route-metric -1 & autoconnect yes、transient units 全 inactive、`unregister_netdevice: waiting` 0 件、h4-probe 累計 237 pre / 59 snapshot-only.PRE、mode=beta
- 130206 の残置物 (durable evidence): `/var/log/h4-probe/wl-unload.status` = `epoch=1782876623 rc=0` (前回の証拠、本セッションでは smoke test 前に **削除**して混同防止)

## Phase 構成 (~50-90 分 主案 / ~90-180 分 代替案、hang 早期終了可)

**基本方針**: 130206 の Phase B-0 〜 B-6 を完全継承し、以下の差分のみ:
1. Phase B-4 の cycle 数を wall-clock **30** (主案) or **60** (代替案) に設定
2. Phase B-1 冒頭で 130206 の `wl-unload.status` を削除 (前回証拠と本セッション証拠の epoch 境界を明確化)
3. Phase B-2 事前案内の統計 wording を「pool 前提の p ≈ 0.024」に更新
4. scratchpad session_start_epoch のパスを本セッション UUID (`692508fb-8bea-43c2-b667-7b4cfd656e72`) に更新

以下、変更のあるフェーズのみ詳細を記載。無変更フェーズ (B-3/B-6) は 130206 プランを完全に踏襲する (B-1 は冒頭に `wl-unload.status` 削除 1 行を追加するのみ)。

### Phase B-0: baseline 確認 + wl blacklist 未設定確認 + SESSION_START 捕捉 (~3 分)

130206 と同一。追加で `wl-unload.status` の残置状態を情報として確認する:

```bash
ssh miminashi@macbookair2015.lan '
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
ls /usr/lib/systemd/system-sleep/
sudo cat /var/lib/h4-probe/mode
nmcli -t -f connection.autoconnect,ipv4.route-metric con show OpenWrt
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
cat /proc/sys/kernel/random/boot_id
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
systemctl is-active vpn-watcher.service cycle-watcher.service wifi-off-and-wl-unload.service 2>&1
lsmod | grep -E "^wl |^cfg80211 "
sudo lsof /sys/module/wl 2>/dev/null | head -5
cat /etc/modprobe.d/*.conf 2>/dev/null | grep -Ei "blacklist wl( |$)" || echo "no wl blacklist"
sudo cat /var/log/h4-probe/wl-unload.status 2>&1 | head -20
'
```

期待値 (130206 継承 + baseline 確認済):
- カーネル `6.12.94+deb13-amd64`, `[s2idle] deep`
- hooks 50/60/70 の 3 個, mode=beta
- NM autoconnect BT-PAN/GSNet=no, OpenWrt=yes/-1
- **boot_id `8963e774...` = 130206 と不変** (hang なし継続)
- suspend_stats **31/0** (130206 終了時と同じ、追加 suspend なし)
- transient units 全 inactive
- `wl 6459392 0`, `cfg80211 ... 1 wl`
- `no wl blacklist`
- 前回 `wl-unload.status` 残置 (rc=0、情報のみ、B-1 で削除)

**SESSION_START_EPOCH 捕捉** (scratchpad 保存):

```bash
SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
echo "$SESSION_START_EPOCH" > /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/692508fb-8bea-43c2-b667-7b4cfd656e72/scratchpad/session_start_epoch.txt
```

### Phase B-1: hook + transient units デプロイ (~7 分)

130206 と完全同一。冒頭で前回の `wl-unload.status` を削除:

```bash
ssh miminashi@macbookair2015.lan '
# 130206 の証拠は既に report/attachment に取り込み済のため削除
sudo rm -f /var/log/h4-probe/wl-unload.status
'
```

これで B-3 の `wl-unload.status` epoch が本セッション用のものだけになり、B-5 集計で smoke / 実 cycle 境界として使える。

以降 (58-snapshot-only デプロイ、smoke test、transient units 起動、NM 設定) は 130206 プラン Phase B-1 を完全に踏襲する。

### Phase B-2: BT-PAN+VPN セットアップ + ユーザ事前案内 (~5 分)

130206 と同一構造、事前案内の統計 wording のみ **pool 前提** に更新:

> **本セッションは 130206 の wl 完全 unload 実験の cycle 拡大版です (主案: 追加 30 cycle、代替: 追加 60 cycle)。**
>
> - **hang 発生 (1 cycle でも) → 決定的**。「wl 非依存」bedrock、機序探究は BT/USB/xfrm 側へ (S4 段 DPM_WATCHDOG カーネル)
> - **主案 30/30 clean (pool 0/60) → Fisher p ≈ 0.024 で有意水準 p<0.05 到達、(b'') tight bedrock 化**
> - **代替案 60/60 clean (pool 0/90) → Fisher p ≈ 0.007 でより strong**
> - **hang の catch 確率**: 主案 (+30) で ~73%、代替案 (+60) で ~93% (base rate 4.3%) ← 残余の ambiguous 確率あり
>
> **連続 ping 絶対禁止** (102907/130206 と同じ、one-shot `ping -c 1` のみ可)
>
> **N cycle は BT-PAN-VALID cycle 数で数える** (source-IP gate 通過後、wall-clock は目標)。VPN が inactive のまま完走した cycle は無効、N に含めない
>
> **推定所要時間**: 主案 30 cycle で ~90 分、代替案 60 cycle で ~180 分。休憩を挟んでよい (休憩中は蓋を開けたまま放置する = 実験前提を破壊しないため)
>
> **失敗兆候**:
> - wake 後 15 秒経っても GSNet が activated にならない → iPad hotspot が自動 OFF になった可能性、iPad 側で確認・再有効化
> - `nmcli con up GSNet` が「有効なシークレットはありません」で失敗 → GUI から手動 up で secrets 再 cache
> - iPad 側で BT-PAN が切れた場合 → BT を off/on か iPad 再起動、cycle 数え直しは不要 (invalid cycle として source-IP gate で自動除外)
>
> **Phase B-3 実行直後、コンソール前で以下のゲートを必ず通過** (blocking):
> ```
> sudo cat /var/log/h4-probe/wl-unload.status
> lsmod | grep -c '^wl '   # → 0 なら go、1 なら STOP
> ```

xfrm src 確認 (moot、B-3 で wl unload するので):

```bash
ssh miminashi@macbookair2015.lan '
nmcli -t -f NAME,DEVICE,TYPE,STATE con show --active
ip -br addr show enx98e0d98d205e
sudo ip xfrm state | grep -E "^src " | head -2
'
```

### Phase B-3: WiFi-off + wl unload = ssh 切断ポイント (~2 分 + ユーザゲート)

130206 と完全同一。`detached systemd-run` + `rmmod wl` (**not** `modprobe -r wl`) + durable marker file (`/var/log/h4-probe/wl-unload.status`) の三層構造。

コード変更なし、130206 プラン Phase B-3 (Line 244-266) をそのまま実行。

### Phase B-4: 手動 cycle 駆動 — **主案 30 cycle** (~30-60 分、代替 60 cycle で ~60-120 分、hang 早期終了可)

**変更点は cycle 数のみ**。他は 130206 と同一。

ユーザ操作 (1 cycle):
1. 蓋 close (= s2idle 突入)
2. 10-30 秒待つ
3. 電源ボタン短押し (= wake、lid open は s2idle で構造的に効かない)
4. ログイン → 10-15 秒待つ (vpn-watcher が GSNet 再 activate)
5. VPN 疎通確認は `ping -c 1 10.0.0.1` の **one-shot** のみ、連続 ping 絶対禁止
6. cycle 番号確認: `watch -n 1 cat /dev/shm/cycle-progress`

`/dev/shm/cycle-progress` の cycle 番号は suspend_stats.success の delta で単純 increment (VPN inactive cycle も含む)。体感 N (30 or 60) を目標に、事後 filter で valid を数える構造。

**Cycle 1 canary チェック** (130206 継承、blocking):
- 1 cycle 目の suspend/wake 完了後、コンソールで:
  ```
  sudo tail -20 /var/log/h4-probe/*.snapshot-only.PRE | tail -20
  ```
- 期待:
  - **`wl_loaded=NO`** (最新 PRE、= wl unload 継続)
  - **`xfrm_state=2 xfrm_policy=14`** (= VPN が BT-PAN 経由で再確立、下限)
  - **`bnep_netdev=MISSING`** (= suspend 直前 bnep teardown 完了)
- どれかが期待外れ → STOP、Claude 通知、abort or ssh 復旧して原因調査

**代替案 60 cycle 時のみ: Cycle 30 中間 canary** (blocking、主案では不要):
- 30 cycle 完了時点で再度最新 PRE を確認 (spontaneous re-bind、iPad hotspot 沈黙、VPN cache 失効の中間監査)
- 期待は cycle 1 canary と同一

Hang 発生 → 強制電源断 → reboot:
- login 後 wl は DKMS + udev で自動再ロードされる (blacklist 未設定を B-0 で確認済)
- `lsmod | grep wl` で確認、無ければ `sudo modprobe wl`
- `sudo nmcli radio wifi on; sudo nmcli con up OpenWrt` で ssh 復活
- Claude に通知

N cycle clean 完走 → **reboot 不要**、以下を手動:
```
sudo modprobe wl
sudo nmcli radio wifi on
sudo nmcli con up OpenWrt
```
その後 Claude に通知。

### Phase B-5: 復帰後 durable evidence 回収 + 集計 (~10 分)

130206 と同一構造。期待 count が cycle 数増加分 (smoke 1 + 実 cycle N = 主案 31 pair / 代替 61 pair) に増える点のみ差分:

```bash
SESSION_START_EPOCH=$(cat /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/692508fb-8bea-43c2-b667-7b4cfd656e72/scratchpad/session_start_epoch.txt)

ssh miminashi@macbookair2015.lan "
echo '=== boot 履歴 ==='
journalctl --list-boots | tail -3

echo '=== suspend_stats (期待: 130206 終了の 31/0 から +N+1 = 主案 62/0 or 代替 92/0) ==='
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail

echo '=== snapshot 増分 (SESSION_START 以降、期待: 各 N+1) ==='
ls /var/log/h4-probe/*.pre 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.post 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.snapshot-only.PRE 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.snapshot-only.POST 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l

echo '=== wl-unload.status ==='
sudo cat /var/log/h4-probe/wl-unload.status

echo '=== wl_loaded 集計 (期待: SMOKE 1, CYCLE wl_loaded=NO x N) ==='
WL_UNLOAD_EPOCH=\$(sudo grep -oE 'epoch=[0-9]+' /var/log/h4-probe/wl-unload.status | cut -d= -f2)
echo \"wl-unload epoch: \$WL_UNLOAD_EPOCH\"
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename \"\$f\" .snapshot-only.PRE)
  [ \"\$TS\" -ge $SESSION_START_EPOCH ] || continue
  if [ \"\$TS\" -lt \"\$WL_UNLOAD_EPOCH\" ]; then TAG=SMOKE; else TAG=CYCLE; fi
  echo \"\$TAG \$(sudo grep -oE 'wl_loaded=[A-Z]+' \"\$f\")\"
done | sort | uniq -c

echo '=== ping_running 集計 (PRE、期待: N+1 NO) ==='
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename \"\$f\" .snapshot-only.PRE)
  [ \"\$TS\" -ge $SESSION_START_EPOCH ] || continue
  sudo grep -oE 'ping_running=[A-Z]+' \"\$f\"
done | sort | uniq -c

echo '=== xfrm 集計 (期待: SMOKE 1 (state=0), CYCLE state=2 policy=14 x N) ==='
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename \"\$f\" .snapshot-only.PRE)
  [ \"\$TS\" -ge $SESSION_START_EPOCH ] || continue
  sudo grep -oE 'xfrm_state=[0-9]+ xfrm_policy=[0-9]+' \"\$f\"
done | sort | uniq -c

echo '=== unregister_netdevice waiting (期待: 依然 0) ==='
sudo journalctl --no-pager 2>/dev/null | grep -c 'unregister_netdevice: waiting'
"
```

**Retro-classify (source-IP gate + order-based pair matching)** も 130206 と同一。期待:
- N CYCLE BT_PAN_VALID (src=172.20.10.*)
- WIFI_KNOWN_CLEAN 0 件 (wl 消失で構造的に不可能)
- 1 SMOKE VPN_INACTIVE
- pair matching で total hangs = 0

### Phase B-5 の headline: pool を優先

レポートの headline は **pool 前提** で書く:
- 主案 (+30 clean): pool 0/60 → Fisher p ≈ 0.024
- 代替案 (B1) (+60 clean, pool 選択): pool 0/90 → Fisher p ≈ 0.007
- 代替案 (B2) (+60 clean, fresh-only 選択): fresh 0/60 → Fisher p ≈ 0.024 (optional-stopping 批判に robust)
- 「新規 N/N clean」と pool 版の両方を report で並記、advisor 指摘に従い 130206 の 30 clean を discount しない

### Phase B-5 の Hang signature 解析 (hang があった場合のみ)

130206 と同一構造、8 項目 + `wl_loaded=NO` の signature 比較。

### Phase B-6: クリーンアップ (~5 分)

130206 と完全同一。130206 プラン Phase B-6 をそのまま実行。

期待 final 状態も同一 (hooks 50/60/70、autoconnect 復帰、transient units inactive、wl+cfg80211 loaded、WiFi radio enabled、`wl-unload.status` 残置)。

## 検証 (実験の end-to-end 完走判定)

1. **Baseline 期待値一致**: B-0 の全項目が期待通り (7 項目 + wl blacklist 無 + boot_id 8963e774 不変)
2. **58-snapshot-only smoke test**: PRE 1 件で `wl_loaded=YES ping_running=NO` を確認
3. **B-3 ゲート通過**: `wl-unload.status rc=0` + `lsmod | grep -c '^wl '` = 0
4. **Cycle 1 canary**: 最初の PRE で `wl_loaded=NO` かつ `xfrm_state=2 xfrm_policy=14`
5. **(代替案のみ) Cycle 30 中間 canary**: 同上
6. **実 cycle 全数 wl_loaded=NO**: B-5 集計で `CYCLE wl_loaded=YES` = 0 件 (SMOKE 分は wl_loaded=YES で OK)
7. **BT_PAN_VALID cycle 数**: 主案 30 or 代替案 60、未達なら追加 cycle 判断
8. **Hang 判定**: order-based pair matching で pre-only epoch を hang 判定、期待は 0
9. **統計判定** (clean 完走時): pool 前提で主案 Fisher p ≈ 0.024、代替案 p ≈ 0.007
10. **Final cleanup**: B-6 期待値全一致

## 統計的評価 (事前 projection、advisor 検証済)

- **base rate 想定 ~4.3%** (043251 1/20 + 102907 1/26 = pooled 2/46 ≈ 4.3%)
- **主案 +30 clean、pool 0/60**: (0.957)³⁰ ≈ 27% で偶然、Fisher exact (5/56 vs 0/60) 片側 p ≈ **0.024**
- **代替案 (B1) +60 clean、pool 0/90**: (0.957)⁶⁰ ≈ 7.3% で偶然、Fisher exact (5/56 vs 0/90) 片側 p ≈ **0.007**
- **代替案 (B2) +60 clean、fresh 0/60 (pool しない)**: Fisher exact (5/56 vs 0/60) 片側 p ≈ **0.024** (主案と同じ有意水準だが optional-stopping に robust)
- pool の対称性: hang arm 3 セッション pool (5/56 = 063543+043251+102907) と同一基準で clean arm 2 セッション pool (主案 0/60 = 30+30 / 代替 B1 0/90 = 60+30)
- **optional-stopping への caveat**: 主案は「130206 で clean を見た後に追加を回している」ので mild な optional-stopping。厳格な事前登録の confirmatory publication では代替案 (B2) が cleaner。本実験は exploratory research なので主案で妥当と判断

## リスク一覧 (130206 継承 + N=30/60 の差分)

| リスク | 影響 | 対処 |
|---|---|---|
| B-3 で `rmmod wl` が busy 失敗 | N cycle 全無効 | ユーザゲートで 0 確認、失敗時 abort/再試行 (130206 継承) |
| Recovery reboot で wl 自動ロードされず | ssh 復活不可 | B-0 で blacklist 未設定確認 (130206 継承) |
| iPad hotspot timeout | 途中 cycle で VPN_INACTIVE 化 | N BT_PAN_VALID cycle 目標 (wall-clock ではない)、代替案時は cycle 30 中間 canary |
| NM VPN secrets cache 失敗 | 途中 cycle で VPN_INACTIVE 化 | GUI 手動 up で復旧 (130206 継承) |
| **ユーザ疲労** (主案 ~90 分 / 代替案 ~180 分) | 途中断念 → 部分データ | 主案採用でリスク顕著に低減、代替案時は事前案内で「休憩可、蓋を開けたまま放置」明記 |
| spontaneous PCI re-bind | セッション部分無効化 | cycle-1 canary、代替案時は cycle-30 も |
| blacklist 誤投入 | recovery 失敗 | **絶対に `/etc/modprobe.d/*` を触らない** (130206 継承) |
| log directory 累積 | 将来的な運用負荷 | 本セッション完了後 logrotate 検討を report に明記 |
| cfg80211 未登録が dpm chain に痕跡 | wl-only unload の attribution 弱化 | 130206 継承、cfg80211 存置を毎 cycle 記録 |
| **optional-stopping 批判** | 統計解釈の弱化 | 主案・代替案 (B1) は pool 前提で mild な批判余地あり、report で明示。批判に完全 robust なのは代替案 (B2) = +60 cycle かつ fresh 0/60 の report |

## 次セッション以降の分岐

- **hang 発生分岐** (途中 1+ hang): wl 非依存 bedrock、次は S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) で dpm_suspend stall device 特定 (推奨手 (iv))
- **N/N clean 分岐 (pool 有意化)**: (b'') tight bedrock 化、次は:
  - (ii) 041006 の btusb arm を WiFi-off で N 拡大 → 「btusb 必要 (H6)」vs「wl-radio-off 必要 (tight reading)」discriminate
  - (iii) non-btusb driver (xfrm/bnep) 事前 teardown → H6 vs H7 discriminate
  - (i-ii-iii のどれも clean な場合) → 最終的に (iv) S4 DPM_WATCHDOG カーネルで dpm_suspend の詳細特定
