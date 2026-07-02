# s2idle+WiFi-off+wl 完全 unload で 30 BT-PAN-valid cycle 駆動 — wl-in-chain 切り分け実験

## Context

WiFi-off (`nmcli radio wifi off`) 状態での BT-PAN+VPN+lid close hang は 3 セッション連続で verified:

- 063543 (WiFi-off + 素 traffic): 3/10 hang, bedrock
- 043251 (WiFi-off + 連続 ping): 1/20 hang
- 102907 (WiFi-off + ping 明示禁止): 1/26 hang, `ping_running=NO` durable, ping confound 反証

これらは全て soft rfkill のみで、**wl モジュール自体は dpm_suspend chain にロードされたまま**。「wl-in-chain が hang の必要条件か」を切り分けるのが本セッションの目的。

`rmmod wl` (cfg80211 は存置) で wl のみ完全アンロード → 手動 30 BT-PAN-VALID cycle 駆動。

**結果の非対称性 (advisor 指摘、B-2 案内に反映)**:

- **1+ hang** → 「wl 完全除去でも再現 = wl 非依存」bedrock。決定的、強い結論。次は S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) で dpm_suspend stall device 特定へ進める
- **30/30 clean** → **弱い示唆にすぎない**。WiFi-off base rate ~5% (043251/102907 pooled 2/46 ≈ 4.3%) だと (0.957)³⁰ ≈ 21% で「wl 無関係でも 30/30 clean」が起きる確率。統計的 wall は 102907 と同じ。次は wl-unload N=60+ で bedrock 化する必要
- Hang の probability of catch は 30 cycle で ~79% ← 21% の確率で ambiguous な clean が出る (advisor 指摘、ユーザ事前案内で明記)

## 主要参照ファイル

- 前セッション report: `/home/miminashi/projects/macbookair11-debian/report/2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md`
- 前セッション plan: `/home/miminashi/projects/macbookair11-debian/report/attachment/2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out/plan.md` (58-snapshot-only hook 実装 + transient units + retro-classify を継承)
- 前々セッション report: `/home/miminashi/projects/macbookair11-debian/report/2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md`
- カーネルソース解析: `/home/miminashi/projects/macbookair11-debian/report/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md` (H1/H2/H4 仮説)
- CLAUDE.md (ssh 接続手順 + レポート作成ルール)

## 環境情報 (実験開始時点)

- 機種: MacBook Air 11" (Early 2015) / Debian 13 trixie / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`, GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks (baseline): `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の 3 個
- 電源: 全 cycle AC
- BT/テザリング: btusb / hci0 (98:E0:D9:8D:20:5E), peer = iPad, BT-PAN 172.20.10.13/28
- VPN: NM GSNet = strongSwan IPsec/IKEv2 (charon-nm, GW 160.16.210.47, inner 192.168.83.1/32)
- WiFi (baseline): wl DKMS ビルド (broadcom-sta 6.30.223.271), wlp3s0 UP, OpenWrt 接続中, refcount=0
- baseline (2026-07-01 10:29 JST 時点、Explore 確認済): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645`, suspend_stats 0/0, NM autoconnect 両方 no, OpenWrt route-metric -1, transient units 全 inactive, h4-probe 累計 206 pre / 28 snapshot-only.PRE, mode=beta

## Phase 構成 (~90 分、hang 早期終了可)

### Phase B-0: baseline 確認 + wl blacklist 未設定確認 + SESSION_START 捕捉 (~3 分)

1. **開発機側で SESSION_START_EPOCH 捕捉** (scratchpad 保存、hardcode 排除)
   ```bash
   SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
   echo "$SESSION_START_EPOCH" > /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/569accd3-f570-4242-99b3-a2f2fddb6456/scratchpad/session_start_epoch.txt
   ```

2. **実機 baseline 7 項目 + wl 系 3 項目確認**
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
   systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
   # 追加: wl 系
   lsmod | grep -E "^wl |^cfg80211 "
   sudo lsof /sys/module/wl 2>/dev/null | head -5
   cat /etc/modprobe.d/*.conf 2>/dev/null | grep -Ei "blacklist wl( |$)" || echo "no wl blacklist"
   '
   ```

期待値:
- カーネル `6.12.94+deb13-amd64`, `mem_sleep=[s2idle] deep`
- hooks 50/60/70 の 3 個, mode=beta
- NM autoconnect 両方 no, OpenWrt route-metric -1
- boot_id `8963e774...`, suspend_stats 0/0
- transient units 全 inactive
- `wl 6459392 0` (refcount 0), `cfg80211 ... 1 wl` (wl のみが持つ)
- `/sys/module/wl` lsof 0 行
- **`no wl blacklist`** ← post-hang reboot での自動再ロードの必要条件

**wl blacklist が設定されていた場合**: 実験中止、ユーザに blacklist 除去を依頼してから再開。

### Phase B-1: hook + transient units デプロイ (~7 分)

#### 58-snapshot-only hook

前セッション 102907 の実装に **wl / cfg80211 / wlp3s0 の 3 フィールドを追加**。他は同一。

```bash
ssh miminashi@macbookair2015.lan 'sudo tee /usr/lib/systemd/system-sleep/58-snapshot-only > /dev/null' <<'OUTER_EOF'
#!/bin/bash
case "$1/$2" in
  pre/suspend) PHASE="PRE" ;;
  post/suspend) PHASE="POST" ;;
  *) exit 0 ;;
esac
TS=$(date +%s)
SNAP_DIR=/var/log/h4-probe
mkdir -p "$SNAP_DIR"
SNAP_FILE="$SNAP_DIR/${TS}.snapshot-only.${PHASE}"

BNEP_RX=$(cat /sys/class/net/bnep0/statistics/rx_bytes 2>/dev/null || echo "0")
BNEP_TX=$(cat /sys/class/net/bnep0/statistics/tx_bytes 2>/dev/null || echo "0")
logger -t snapshot-only "[$PHASE] bnep_rx=$BNEP_RX bnep_tx=$BNEP_TX"

pgrep -f "kbnepd" > /dev/null && KBNEPD="alive" || KBNEPD="NOT FOUND"
logger -t snapshot-only "[$PHASE] kbnepd_session=$KBNEPD"

ip link show bnep0 > /dev/null 2>&1 && BNEP_NETDEV="present" || BNEP_NETDEV="MISSING"
logger -t snapshot-only "[$PHASE] bnep_netdev=$BNEP_NETDEV"

XFRM_STATE=$(ip xfrm state | grep -c "^src ")
XFRM_POLICY=$(ip xfrm policy | grep -c "^src ")
logger -t snapshot-only "[$PHASE] xfrm_state=$XFRM_STATE xfrm_policy=$XFRM_POLICY"

# ping 検出 (word-boundary anchor 必須, 102907 B-1 で発見した bug 反映)
PING_PROCS=$(pgrep -af "(^|[ /])ping( |$)" 2>/dev/null | grep -v "snapshot-only" || true)
[ -n "$PING_PROCS" ] && PING_RUNNING="YES" || PING_RUNNING="NO"
logger -t snapshot-only "[$PHASE] ping_running=$PING_RUNNING"

# === 本セッション新規: wl / cfg80211 / wlp3s0 状態 ===
# anchor: '^wl ' の末尾スペース必須 (wl_ 系との誤 match 防止)
lsmod | grep -q '^wl '        && WL_LOADED=YES || WL_LOADED=NO
lsmod | grep -q '^cfg80211 '  && CFG_LOADED=YES || CFG_LOADED=NO
ip link show wlp3s0 > /dev/null 2>&1 && WLP_PRESENT=YES || WLP_PRESENT=NO
logger -t snapshot-only "[$PHASE] wl_loaded=$WL_LOADED cfg80211_loaded=$CFG_LOADED wlp3s0_present=$WLP_PRESENT"

# durable file (hang reboot 越しの証拠)
{
  echo "phase=$PHASE epoch=$TS"
  echo "bnep_rx=$BNEP_RX bnep_tx=$BNEP_TX"
  echo "kbnepd_session=$KBNEPD"
  echo "bnep_netdev=$BNEP_NETDEV"
  echo "xfrm_state=$XFRM_STATE xfrm_policy=$XFRM_POLICY"
  echo "ping_running=$PING_RUNNING"
  echo "wl_loaded=$WL_LOADED cfg80211_loaded=$CFG_LOADED wlp3s0_present=$WLP_PRESENT"
  echo "=== ping processes ==="
  echo "${PING_PROCS:-NONE}"
} > "$SNAP_FILE" 2>&1
sync
sleep 0.5
OUTER_EOF
ssh miminashi@macbookair2015.lan 'sudo chmod +x /usr/lib/systemd/system-sleep/58-snapshot-only'
```

Smoke test で `wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES ping_running=NO` が出ることを 1 回確認してから進む。

```bash
# smoke test: 1 回 suspend + wake (systemctl start systemd-suspend.service --wait 経由)
ssh miminashi@macbookair2015.lan '
sudo rtcwake -m no -s 10 & sudo systemctl start systemd-suspend.service --wait
sudo tail -1 /var/log/h4-probe/*.snapshot-only.PRE | tail -1
'
```

#### transient units 起動 (102907 と同一)

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=vpn-watcher --collect bash -c "
while true; do
  if ip -br link show enx98e0d98d205e 2>/dev/null | grep -q UP; then
    if ! nmcli -t -f GENERAL.STATE con show GSNet | grep -q activated; then
      nmcli con up GSNet 2>&1 | logger -t vpn-watcher
    fi
  fi
  sleep 3
done
"

sudo systemd-run --unit=cycle-watcher --collect bash -c "
prev=\$(cat /sys/power/suspend_stats/success)
cycle_num=0
while true; do
  curr=\$(cat /sys/power/suspend_stats/success)
  if [ \"\$curr\" != \"\$prev\" ]; then
    cycle_num=\$((cycle_num+1))
    logger -t cycle-watcher \"cycle \$cycle_num: suspend_stats \$prev -> \$curr\"
    echo \"cycle \$cycle_num at \$(date -Iseconds)\" >> /dev/shm/cycle-progress
    prev=\$curr
  fi
  sleep 5
done
"
'
```

#### NM 設定 (102907 と同一 + **OpenWrt autoconnect=no**)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con modify OpenWrt connection.autoconnect no
'
```

`OpenWrt autoconnect=no` は本セッション追加 (wlp3s0 消失後の autoconnect 失敗 log spam 抑制、B-6 で revert)。

### Phase B-2: BT-PAN+VPN セットアップ + ユーザ事前案内 (~5 分)

ユーザに iPad テザリング ON を依頼、NM autoconnect=yes により BT-PAN+GSNet 自動 up。

**ユーザ事前案内 (= 本セッション load-bearing communication)**:

> **本セッションは wl 完全 unload の切り分け実験です。**
>
> - **hang 発生 (1 cycle でも) → 決定的**。「wl 非依存」bedrock、機序探究は BT/USB/xfrm 側へ進める
> - **30/30 clean → 弱い示唆にすぎない**。base rate ~5% で「wl 無関係でも 30/30 clean」が起きる確率は約 21%。統計的 wall は 102907 と同じ、次に N=60+ 拡大が必要
> - **hang の catch 確率は 30 cycle で ~79%** = 21% の確率で「wl 関係あっても hang が捕まらない」ケースあり
>
> **連続 ping 絶対禁止** (102907 と同じ、one-shot `ping -c 1` のみ可)
>
> **30 cycle は BT-PAN-VALID cycle 数で数える** (source-IP gate 通過後)。VPN が inactive のまま完走した cycle は無効、30 に含めない (advisor 指摘、iPad hotspot timeout + NM secrets cache の脆さ対策)
>
> **失敗兆候**:
> - wake 後 15 秒経っても GSNet が activated にならない → iPad hotspot が自動 OFF になった可能性、iPad 側で確認・再有効化
> - `nmcli con up GSNet` が「有効なシークレットはありません」で失敗 → GUI から手動 up で secrets 再 cache
>
> **Phase B-3 実行直後、コンソール前で以下のゲートを必ず通過** (blocking):
> ```
> sudo cat /var/log/h4-probe/wl-unload.status
> lsmod | grep -c '^wl '   # → 0 なら go、1 なら STOP
> ```
> このゲートを通らずに cycle 開始すると 30 cycle 丸ごと無効 (soft-rfkill と同じ実験) になります。

BT-PAN+VPN active 確認 (xfrm state 取れれば src 表示):
```bash
ssh miminashi@macbookair2015.lan '
nmcli -t -f NAME,DEVICE,TYPE,STATE con show --active
ip -br addr show enx98e0d98d205e
sudo ip xfrm state | grep -E "^src " | head -2
'
```

xfrm src が 192.168.33.* (WiFi 経由) でも、B-3 で wl unload するので moot (advisor 指摘: wl 消失後は WiFi-routed VPN 混入が **構造的に不可能**、retro-classify は 102907 より cleaner)。

### Phase B-3: WiFi-off + wl unload = ssh 切断ポイント (~2 分 + ユーザゲート)

**設計**:
- **`rmmod wl`** を使う (**not** `modprobe -r wl`)。理由: `modprobe -r` は依存を連鎖 unload するので cfg80211 まで外れる。目的は「wl-in-chain の切り分け」であり、cfg80211 も外すと clean 分岐で「wl か cfg80211 か」の attribution が不能になる。`rmmod` は名指しのみで、wl は refcount=0 の leaf なので安全
- **detached systemd-run で非 ssh 依存に**: ssh は wlp3s0 経由なので `nmcli con down OpenWrt` で切れる、systemd-run --unit --collect で切断後も完走
- durable marker file (`/var/log/h4-probe/wl-unload.status`) にゲート判定材料を書き込む

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=wifi-off-and-wl-unload --collect bash -c "
  sleep 3
  logger -t wl-unload starting
  nmcli con down OpenWrt 2>&1 | logger -t wl-unload
  nmcli radio wifi off 2>&1 | logger -t wl-unload
  sleep 2
  # rmmod (NOT modprobe -r) で cfg80211 連鎖 unload を防止
  rmmod wl 2>&1 | logger -t wl-unload
  RC=\$?
  {
    echo epoch=\$(date +%s)
    echo rc=\$RC
    echo === lsmod ===
    lsmod | grep -E \"^wl |^cfg80211 \" || echo NONE
    echo === wlp3s0 ===
    ip link show wlp3s0 2>&1 || echo MISSING
  } > /var/log/h4-probe/wl-unload.status 2>&1
  sync
  logger -t wl-unload done rc=\$RC
"
'
# ssh はこの直後に切れる (nmcli con down OpenWrt で)
```

**ユーザ検証ゲート (B-3 と B-4 の間、blocking)**:

コンソール前で:
```
sudo cat /var/log/h4-probe/wl-unload.status
# 期待: rc=0、lsmod セクションに "wl " 行が無い (cfg80211 のみ, or NONE)
sudo lsmod | grep -c '^wl '
# 期待: 0
```

- ゲート **NG** (rc≠0 or wl 残存) → cycle 開始せず、以下いずれか:
  - `sudo rmmod wl` 手動再実行
  - `sudo lsof /sys/module/wl` で保持プロセス確認
  - 復旧不可なら abort、Claude に ssh 復旧して report

### Phase B-4: 手動 cycle 駆動 (~50-70 分, hang 早期終了可)

**ユーザ体感の駆動目標は wall-clock 30 cycle**。B-5 で source-IP gate による retro-classify を実施し、`BT_PAN_VALID cycle 数 ≥ 30` を validity 判定基準とする (BT_PAN_VALID < 30 の場合は Phase B-5 冒頭で追加 cycle 判断)。「30 BT-PAN-VALID」はあくまで validity 目標であり、hang が発生した時点で早期終了。

ユーザ操作 (1 cycle):
1. 蓋 close (= s2idle 突入)
2. 10-30 秒待つ
3. 電源ボタン短押し (= wake, lid open は s2idle で構造的に効かない)
4. ログイン → 10-15 秒待つ (vpn-watcher が GSNet 再 activate)
5. **VPN 疎通確認は `ping -c 1 10.0.0.1` の one-shot のみ**、連続 ping 絶対禁止
6. cycle 番号確認: `watch -n 1 cat /dev/shm/cycle-progress`

`/dev/shm/cycle-progress` の cycle 番号は suspend_stats.success の delta で単純 increment されるので VPN inactive cycle も含む (体感 30 を目標に、事後 filter で valid を数える構造)。

**Cycle 1 完了時の canary チェック** (advisor 指摘、blocking):
- 1 cycle 目の suspend/wake が終わったら、ユーザにコンソールで:
  ```
  sudo tail -20 /var/log/h4-probe/*.snapshot-only.PRE | tail -20
  ```
- 期待項目:
  - **`wl_loaded=NO`** (最新 PRE、= wl unload 継続を確認)
  - **`xfrm_state=2 xfrm_policy=14`** (= VPN が BT-PAN 経由で再確立、下限)
  - **`bnep_netdev=MISSING`** (= suspend 直前 bnep teardown 完了、過去 hang signature と一致)
- **`wl_loaded=YES` が出ていたら STOP**、Claude 通知。原因は spontaneous udev/PCI re-bind 等の可能性、実験前提崩壊
- **`xfrm_state=0` が出ていたら STOP**、Claude 通知。VPN が復活していない = wl unload 後 vpn-watcher の再確立失敗、実験前提崩壊

Hang 発生 → 強制電源断 → reboot:
- login 後 wl は DKMS + udev で自動再ロードされる (blacklist 未設定を B-0 で確認済)
- `lsmod | grep wl` で確認、無ければ `sudo modprobe wl`
- `sudo nmcli radio wifi on; sudo nmcli con up OpenWrt` で ssh 復活
- Claude に通知

30/30 clean 完走 → **reboot 不要**、以下を手動:
```
sudo modprobe wl
sudo nmcli radio wifi on
sudo nmcli con up OpenWrt
```
その後 Claude に通知。

### Phase B-5: 復帰後 durable evidence 回収 + 集計 (~10 分)

```bash
SESSION_START_EPOCH=$(cat /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/569accd3-f570-4242-99b3-a2f2fddb6456/scratchpad/session_start_epoch.txt)

ssh miminashi@macbookair2015.lan "
echo '=== boot 履歴 ==='
journalctl --list-boots | tail -3

echo '=== suspend_stats ==='
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail

echo '=== snapshot 増分 (SESSION_START 以降) ==='
SESSION_START=$SESSION_START_EPOCH
ls /var/log/h4-probe/*.pre 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.post 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.snapshot-only.PRE 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l
ls /var/log/h4-probe/*.snapshot-only.POST 2>/dev/null | awk -F/ '{print \$NF}' | awk -F. '\$1 >= '\$SESSION_START | wc -l

echo '=== wl-unload.status ==='
sudo cat /var/log/h4-probe/wl-unload.status

echo '=== wl_loaded 集計 (PRE, SESSION_START 以降) ==='
# 期待: smoke test (B-3 前) は wl_loaded=YES、実 cycle (B-3 後) は wl_loaded=NO
# B-3 の wl-unload.status の epoch を境界にして分ける
WL_UNLOAD_EPOCH=\$(sudo grep -oE 'epoch=[0-9]+' /var/log/h4-probe/wl-unload.status | cut -d= -f2)
echo \"wl-unload epoch: \$WL_UNLOAD_EPOCH\"
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename \"\$f\" .snapshot-only.PRE)
  [ \"\$TS\" -ge $SESSION_START_EPOCH ] || continue
  if [ \"\$TS\" -lt \"\$WL_UNLOAD_EPOCH\" ]; then TAG=SMOKE; else TAG=CYCLE; fi
  echo \"\$TAG \$(sudo grep -oE 'wl_loaded=[A-Z]+' \"\$f\")\"
done | sort | uniq -c

echo '=== ping_running 集計 (PRE) ==='
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename \"\$f\" .snapshot-only.PRE)
  [ \"\$TS\" -ge $SESSION_START_EPOCH ] || continue
  sudo grep -oE 'ping_running=[A-Z]+' \"\$f\"
done | sort | uniq -c

echo '=== unregister_netdevice waiting (期待: 0) ==='
sudo journalctl --no-pager 2>/dev/null | grep -c 'unregister_netdevice: waiting'
"
```

#### Retro-classify (source-IP gate + order-based pair matching)

70-h4-probe の `.pre` から xfrm state src IP を抽出:
- `src 172.20.10.*` = BT_PAN_VALID
- `src 192.168.33.*` = WIFI_KNOWN_CLEAN (本セッションでは B-3 以降は構造的に 0 のはず)
- 無し = VPN_INACTIVE

Pair matching は **order-based** (102907 B-5 発見、`test -f "${f%.pre}.post"` は 70-h4-probe の独立 epoch と不整合):
- pre epoch 列と post epoch 列を昇順 sort
- pre 直後の未消費 post が次の pre より前なら OK
- pre の post が無ければその cycle = HANG

#### Hang signature 解析 (hang があった場合のみ)

前 boot -1 の journal から抽出:
- `PM: suspend entry (s2idle)` の最終行
- `PM: suspend exit` の有無 (期待: 欠落)
- `charon-nm ... Network is unreachable` retransmit 回数
- 該当時刻の 58-snapshot-only PRE durable file の全フィールド

063543/043251/102907 との signature 比較 (8 項目 + 本セッション新規 `wl_loaded=NO`):
- Network is unreachable retransmit 3 回
- bnep teardown 完了 (bnep_netdev=MISSING)
- xfrm_state=2 xfrm_policy=14 (半分)
- ping_running=NO (durable)
- **wl_loaded=NO** (本セッション新規、決定的)
- PM: suspend entry (s2idle) あり、exit 欠落
- boot_id 変化
- unregister_netdevice: waiting 0 件

### Phase B-6: クリーンアップ (~5 分)

```bash
ssh miminashi@macbookair2015.lan '
sudo systemctl stop vpn-watcher.service cycle-watcher.service 2>/dev/null || true
sudo systemctl stop wifi-off-and-wl-unload.service 2>/dev/null || true
sudo rm -f /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con modify OpenWrt connection.autoconnect yes
'
```

**期待 final 状態**:

| 項目 | 期待 |
|---|---|
| hooks | 50/60/70 の 3 個 |
| autoconnect (BT-PAN/GSNet) | 両方 no |
| OpenWrt autoconnect / route-metric | yes / -1 |
| transient units | 全 inactive |
| wl / cfg80211 | 両方 loaded (recovery 完了) |
| WiFi radio | enabled |
| `/var/log/h4-probe/wl-unload.status` | 残置 (durable evidence) |

## 検証 (実験の end-to-end 完走判定)

1. **Baseline 期待値一致**: B-0 の全項目が期待通り (7 項目 + wl blacklist 無)
2. **58-snapshot-only smoke test**: PRE 1 件で `wl_loaded=YES ping_running=NO` を確認
3. **B-3 ゲート通過**: `wl-unload.status rc=0` + `lsmod | grep -c '^wl '` = 0
4. **Cycle 1 canary**: 最初の PRE で `wl_loaded=NO` かつ `xfrm_state=2 xfrm_policy=14`
5. **実 cycle 全数 wl_loaded=NO**: B-5 集計で `CYCLE wl_loaded=YES` = 0 件 (SMOKE 分は wl_loaded=YES で OK)
6. **BT_PAN_VALID cycle 数 30**: source-IP gate 通過 30 件 (未達なら追加 cycle 判断)
7. **Hang 判定**: order-based pair matching で pre-only epoch を hang 判定
8. **Final cleanup**: B-6 期待値全一致

## リスク一覧

| リスク | 影響 | 対処 |
|---|---|---|
| B-3 で `rmmod wl` が busy 失敗 | 30 cycle 全無効 (soft-rfkill と同じ) | ユーザゲートで 0 確認、失敗時 abort/再試行 |
| B-3 途中で ssh drop 前に systemd-run 未起動 | wl unload されない | systemd-run は即 return するのでほぼ起きない、ゲートで検出 |
| Recovery reboot で wl 自動ロードされず | ssh 復活不可 | B-0 で blacklist 未設定確認、hang 分岐時 `sudo modprobe wl` の手順を B-2 案内で明記 |
| clean 分岐でユーザが誤って reboot | wl reload 手順を skip、次実験の baseline がずれる | B-2 案内で「clean 時は reboot 不要、手動 3 コマンド」明記 |
| iPad hotspot timeout | 途中 cycle で VPN_INACTIVE 化 | 30 BT_PAN_VALID cycle 目標 (wall-clock ではない)、失敗兆候をユーザ案内 |
| NM VPN secrets cache 失敗 | 途中 cycle で VPN_INACTIVE 化 | 同上、GUI 手動 up で復旧 |
| cfg80211 未登録が dpm chain に痕跡 | wl-only unload の attribution 弱化 | hook で `cfg80211_loaded=YES` を毎 cycle 記録、report で「wl 除去・cfg80211 存置」と正確に書く |
| blacklist 誤投入 | recovery 失敗 | **絶対に `/etc/modprobe.d/*` を触らない** |
| spontaneous PCI re-bind → wl 再ロード | セッション部分無効化 | cycle-1 canary + 毎 cycle wl_loaded 記録で監査、YES 出現時 STOP |

## 次セッション以降の分岐

- **hang 発生分岐**: wl 非依存 bedrock、次は S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) で dpm_suspend stall device 特定
- **30/30 clean 分岐**: wl-in-chain 決定因の可能性、次は wl-unload N=60+ 拡大 or wl+cfg80211 両 unload での confirmation
