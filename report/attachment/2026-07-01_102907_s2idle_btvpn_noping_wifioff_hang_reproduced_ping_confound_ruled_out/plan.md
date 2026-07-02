# s2idle+WiFi-off で 30 BT-PAN-valid cycle clean re-run (ping confound 排除 + N 拡大)

## Context

[2026-07-01_043251 セッション](../../../projects/macbookair11-debian/report/2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) で WiFi-off + BT-PAN+VPN + lid close を 20 BT-PAN-valid cycle 駆動した結果、**cycle 20 で 1 hang 発生** (063543 と同 signature: `xfrm_policy=14` 半分、`Network is unreachable` retransmit 3 回、`PM: suspend entry` で kernel ログ終端 = dpm_suspend stall)。

ただし**「WiFi-on protective」結論は二つの壁で establish されない** (043251 結論):

1. **Statistical power 不足**: 0/30 (061553, WiFi-on) vs 1/20 (043251, WiFi-off) は Fisher p ≈ 0.4 = 同じ hang rate と統計的に区別不能。**N=1 hang では何も言えない**
2. **Ping confound 未解消**: ユーザは 043251 で background `ping 10.0.0.1` を流していた。事後申告で「他セッション (061553 含む) でも ping は大体流していた、ただし全てかは覚えていない」。h4-probe pre snapshot に process list がないため直接検証不可

本セッション (この plan の対象) では二つの壁のうち **ping confound だけを構造的に排除** し、hang の独立再現を狙う非対称設計:

- **WiFi-off** (043251 と同じ条件)
- **連続 ping 明示禁止** (= confound 排除、ユーザ事前案内)
- **process list 追加** (= 事後検証可能化、58-snapshot-only で pgrep ping を logger + 永続ファイル両方に書く)
- **N=30 cycle で 1+ hang 出れば即勝ち**, 30/30 clean なら 60 cycle まで延長 (= 帰無側の power を稼ぐ。但し N=60 でも null 下 ~7.7% でほぼ何も言えない構造)

**結果の非対称性 (advisor 指摘で訂正、重要)**:

- **1+ hang 再現 = 強い勝ち**: power 不要、ping は hang に必須ではないことを証明、candidate (d)「ベースラインは ~0」説を更に弱める。**1 hang で headline 確定**
- **30/30 clean = inconclusive (= ほぼ無情報)**: P(0 hangs in 30 | 5% rate) ≈ 0.95^30 ≈ **21%** で null 下で全く普通の結果。043251 の 1/20 (point estimate ~5%) と全く矛盾しない。「WiFi-on protective」(vs 061553) も「ping load-bearing」(vs 043251) も支持しない。**clean は両方の interpretation について silent**

結果分岐 (訂正版):
- **N=30 で 1+ hang** → 即終了、レポート作成、候補 (d) を弱める bedrock 追加。機序探究 (H1/H2/H4 lab) へ移行判断
- **N=30 で 0 hang** → 60 cycle まで延長 (= statistical power を null 側に稼ぐ)。それでも 60/60 clean = N=60 null 下 ~7.7% で **依然 inconclusive**。ユーザに事前に「clean は無情報になる可能性が高い」と explicit に communicate
- **延長中に hang** → 即終了、上記と同じ headline

## Goal & 成否判定

**主要目的**: **ping 無し条件下で hang を独立再現する** (= 「043251 の hang は ping confound 由来」説を排除)。1+ hang 再現できれば本セッションは success、clean は無情報受容。

**事前ユーザコミュニケーション (= load-bearing)**:

> 本セッションは **hang を当てに行く** 実験です。  
> - hang が出る → 強い結論 (= ping 不要を示せる)、即終了  
> - 30/30 で出ない → 「ping が load-bearing だった」とも「WiFi-on が protective」とも結論できない、追加で 60 cycle まで延長して null 側の statistical power を稼ぐ (但し 60/60 でも ~7.7% で曖昧さは残る)  
> - 構造的に「clean = 何かの結論」にはなりにくいことを承知の上で実施

**成否判定 (= レポートに書く headline)**:
- (a) cycle 駆動完遂 (1+ hang で早期終了可、30/30 clean なら 60 まで延長を提案)
- (b) 全 cycle の pre snapshot で `pgrep -af "ping( |$)"` の有無を retro-classify (= durable file + journal 両方に記録)
- (c) source-IP gate (`xfrm state src=172.20.10.*` 確認) で WiFi 経由 VPN 混入を 0 件確認
- (d) hang 発生時は cycle 特定 + 063543/043251 signature との一致確認

## 環境前提

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks 開始時: `50-kbd-backlight` / `60-s3-soak-log` / `70-h4-probe` の 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2、GW `160.16.210.47`
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` → **Phase B-3 で `nmcli radio wifi off`**

## Phase 構成 (043251 の skeleton を継承、Phase A 除外)

### Phase B-0: baseline 確認 + SESSION_START 捕捉 (~3 分)

**SESSION_START の取得 (= advisor 指摘の retro-classify epoch bug 防止)**:

```bash
# 開発機側で本セッション開始時刻を捕捉 (UTC epoch、後の retro-classify で動的に使用)
SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
echo "$SESSION_START_EPOCH" > /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/915d0781-2b57-4594-967c-9c8b4214cb22/scratchpad/session_start_epoch.txt
echo "SESSION_START_EPOCH=$SESSION_START_EPOCH (JST: $(TZ=Asia/Tokyo date -d "@$SESSION_START_EPOCH"))"
```

これを保存しておき、B-5 で retro-classify する時に過去 180 件の `.pre` ファイルを誤って拾わない閾値として使う。**hardcode (043251 の 03:46:00) は絶対に使わない**。

baseline 7 項目確認:

```bash
ssh miminashi@macbookair2015.lan '
echo "=== alive + mem_sleep ==="
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
echo "=== system-sleep hooks (期待: 50/60/70 の 3 個) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== h4-probe infra (期待: mode=beta, snapshot ~180 pre) ==="
sudo cat /var/lib/h4-probe/mode
echo "snapshot count: $(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l) pre"
echo "=== NM autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
echo "=== boot_id (現在の起点、後で boot 跨ぎ判定用) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting"
echo "=== transient units 残存していないか ==="
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

期待値:
- カーネル `6.12.94+deb13-amd64`、`mem_sleep` で `[s2idle] deep`
- hooks 3 個、mode=beta
- NM autoconnect 両方 no、OpenWrt route-metric -1
- transient units 全 inactive
- unregister_netdevice: waiting 0 件
- boot_id 記録 (現在 `670cf7fd...` 想定、B-4 で hang 起きると変化、B-5 retro-classify で `-b -1` / `-b -2` の範囲決定に使用)

### Phase B-1: hook + transient units デプロイ (~5 分)

#### 58-snapshot-only hook (043251 と同一 + pgrep ping 追加 + durable file 出力)

**重要な追加 2 点 (advisor 指摘で構造化)**:

1. **`pgrep -af "ping( |$)"` セクション** を末尾に追加 (= 事後 ping 検証の可能化)
2. **logger だけでなく永続ファイル (`/var/log/h4-probe/<epoch>.snapshot-only.${PHASE}`) にも書く** (= advisor 指摘 #2、hang reboot を跨いで生き残らせる、journal は `-b -1` で読めるが durable file の方が retro-classify が単純)

```bash
ssh miminashi@macbookair2015.lan 'sudo tee /usr/lib/systemd/system-sleep/58-snapshot-only > /dev/null' <<'OUTER_EOF'
#!/bin/bash
# bnep statistics + kbnepd presence + netdev presence + xfrm count + process list
# 058 = NM teardown 完了直後、70-h4-probe より先に走る
# logger と /var/log/h4-probe/<epoch>.snapshot-only.${PHASE} の両方に書く
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

if pgrep -f "kbnepd" > /dev/null; then
  KBNEPD="alive"
else
  KBNEPD="NOT FOUND"
fi
logger -t snapshot-only "[$PHASE] kbnepd_session=$KBNEPD"

if ip link show bnep0 > /dev/null 2>&1; then
  BNEP_NETDEV="present"
else
  BNEP_NETDEV="MISSING"
fi
logger -t snapshot-only "[$PHASE] bnep_netdev=$BNEP_NETDEV"

XFRM_STATE=$(ip xfrm state | grep -c "^src ")
XFRM_POLICY=$(ip xfrm policy | grep -c "^src ")
logger -t snapshot-only "[$PHASE] xfrm_state=$XFRM_STATE xfrm_policy=$XFRM_POLICY"

# === 本セッション新規追加: ping process 検出 (confound 排除の事後検証用) ===
PING_PROCS=$(pgrep -af "ping( |$)" 2>/dev/null | grep -v "snapshot-only" || true)
if [ -n "$PING_PROCS" ]; then
  PING_RUNNING="YES"
else
  PING_RUNNING="NO"
fi
logger -t snapshot-only "[$PHASE] ping_running=$PING_RUNNING"
if [ -n "$PING_PROCS" ]; then
  echo "$PING_PROCS" | head -10 | while IFS= read -r line; do
    logger -t snapshot-only "[$PHASE] ping_proc: $line"
  done
fi

# === durable file 出力 (advisor #2 指摘: hang reboot を跨ぐ確実な記録) ===
{
  echo "phase=$PHASE epoch=$TS"
  echo "bnep_rx=$BNEP_RX bnep_tx=$BNEP_TX"
  echo "kbnepd_session=$KBNEPD"
  echo "bnep_netdev=$BNEP_NETDEV"
  echo "xfrm_state=$XFRM_STATE xfrm_policy=$XFRM_POLICY"
  echo "ping_running=$PING_RUNNING"
  echo "=== ping processes ==="
  echo "${PING_PROCS:-NONE}"
} > "$SNAP_FILE" 2>&1

sync
sleep 0.5
OUTER_EOF
ssh miminashi@macbookair2015.lan 'sudo chmod +x /usr/lib/systemd/system-sleep/58-snapshot-only'
```

#### Smoke test (デプロイ直後)

```bash
ssh miminashi@macbookair2015.lan '
sudo /usr/lib/systemd/system-sleep/58-snapshot-only pre suspend
echo "=== journal output ==="
sudo journalctl -t snapshot-only --no-pager -n 10
echo "=== durable file ==="
sudo ls -t /var/log/h4-probe/*.snapshot-only.PRE 2>/dev/null | head -1 | xargs sudo cat
'
```

期待:
- journal に `[PRE] bnep_rx=... bnep_tx=...`, `[PRE] kbnepd_session=...`, `[PRE] bnep_netdev=...`, `[PRE] xfrm_state=... xfrm_policy=...`, `[PRE] ping_running=...` の 5 + (ping_proc 行 0..N) 行
- durable file が `/var/log/h4-probe/<epoch>.snapshot-only.PRE` に作成されており、上記情報を含む

#### vpn-watcher + cycle-watcher 起動

```bash
ssh miminashi@macbookair2015.lan 'sudo systemd-run --unit=vpn-watcher --collect bash -c "
while true; do
  if ip -br link show enx98e0d98d205e 2>/dev/null | grep -q UP; then
    if ! nmcli -t -f NAME con show --active | grep -qx GSNet; then
      logger -t vpn-watcher \"BT-PAN up but GSNet inactive, re-activating\"
      nmcli con up GSNet 2>&1 | logger -t vpn-watcher
      sleep 5
    fi
  fi
  sleep 3
done
"'

ssh miminashi@macbookair2015.lan 'sudo systemd-run --unit=cycle-watcher --collect bash -c "
prev=\$(cat /sys/power/suspend_stats/success)
cycle_num=0
echo \"START prev=\$prev cycle=0\" > /dev/shm/cycle-progress
while true; do
  curr=\$(cat /sys/power/suspend_stats/success)
  if [ \"\$curr\" != \"\$prev\" ]; then
    cycle_num=\$((cycle_num + 1))
    delta=\$((curr - prev))
    TS=\$(TZ=Asia/Tokyo date +\"%H:%M:%S\")
    logger -t cycle-watcher \"cycle \$cycle_num: suspend_stats \$prev -> \$curr (delta=\$delta)\"
    echo \"\$TS cycle=\$cycle_num suspend_stats=\$prev->\$curr delta=\$delta\" >> /dev/shm/cycle-progress
    prev=\$curr
  fi
  sleep 5
done
"'
```

#### NM autoconnect=yes + WiFi metric 800 (= WiFi 経由 VPN 防止)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
'
```

(043251 で WiFi metric 600 < BT-PAN 750 の状態で setup したため一瞬 WiFi 経由 VPN が確立した。本セッションでは事前に 800 にして constructional に防止。WiFi-off 時には moot だが、setup 段階の cleanliness のため。)

### Phase B-2: BT-PAN + VPN セットアップ (~5 分) + ping 禁止ユーザ案内

ユーザ操作: iPad テザリング ON。NM autoconnect=yes により BT-PAN + GSNet が自動 up するはず。

Claude が ssh 経由で確認:
```bash
ssh miminashi@macbookair2015.lan '
echo "=== xfrm state src (期待: 172.20.10.13 のみ、192.168.33.* 不在) ==="
sudo ip xfrm state | grep "^src "
echo "=== active connections ==="
nmcli -t -f NAME con show --active
echo "=== default route (期待: BT-PAN 経由) ==="
ip route | grep default
'
```

**ユーザ事前案内 (= 本セッションの load-bearing communication)**:

> **重要 1: 本セッションは「hang を当てに行く」設計です**
>
> - 1 cycle でも hang 出れば本セッション勝ち (= 強い結論)、即終了
> - 30/30 で hang が出なければ「ping のせいだった」とも「WiFi-on が protective だった」とも結論できません (= 構造的に inconclusive)
> - 30/30 clean なら 60 cycle まで延長を提案しますが、それでも曖昧さは残ります
> - つまり「無事故で終わる」のが嬉しい結果ではないのが本セッションの特殊性です
>
> **重要 2: 本セッション中は連続 ping を一切流さないでください**
>
> - 043251 で background `ping 10.0.0.1` を連続実行されていましたが、これが confound 源として疑われています
> - 本セッションでは「ping 無しでも hang するか」を検証します
> - **VPN 疎通確認は wake 直後の `ping -c 1 10.0.0.1` (one-shot) のみ可** とします
> - **絶対に `ping 10.0.0.1` や `ping -i 1 ...` 等の連続 ping を立ち上げないでください**
> - 既存の terminal で background ping が走っていれば、Phase B-3 (WiFi off) の **前に** Ctrl+C で止めてください
> - 58-snapshot-only が pre snapshot で `pgrep ping` を実行し、ping が走っていれば journal + durable file で発覚します (事後検証可能)

ユーザに「了解」を確認してから Phase B-3 に進む。

### Phase B-3: WiFi-off (= ssh 切断ポイント, ~1 分)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con down OpenWrt
sudo nmcli radio wifi off
'
```

実行直後に ssh 切断 (期待動作)。これ以降 Claude は実機状態を観測不能。

### Phase B-4: ユーザ手動 cycle 駆動 (~60-90 分、hang 発生で早期終了可)

ユーザ操作 (1 cycle):
1. 蓋を閉じる (= s2idle 突入)
2. 約 10-30 秒待つ
3. 電源ボタン短押し (= wake、043251 で lid open は s2idle で構造的に動作しないため電源ボタンが必須)
4. wake 後 ~12 秒で vpn-watcher が GSNet を再 activate (= IKE_SA 再確立)
5. 必要なら `nmcli con show --active | grep GSNet` で active 確認 (one-shot コマンドのみ)
6. **連続 ping は絶対に走らせない** (B-2 で約束)
7. 上記を 30 cycle 繰り返す (= cycle 数は ユーザの体感カウントでよいが、最終的に Claude が durable evidence (`.pre`/`.post` ペア) で確定)

**Hang 発生時の判断 (advisor 訂正版 framing)**:

- **どこかで hang (= 蓋閉じ後 wake しない) 発生 → 強制電源断 → reboot → 手動で `nmcli radio wifi on` で WiFi 復活 → Claude に ssh 復活を伝える → 本セッション勝ち、Phase B-5 へ**。1 hang で headline (= ping なしでも hang する = candidate (d) を更に弱める) が確定するので、延長は不要。
- **30/30 hang なし完走 → 60 cycle まで延長を提案** (= advisor #1、null 側 power を稼ぐ。但し 60/60 でも null 下 ~7.7% で曖昧さは残ることをユーザに事前 communicate 済)。
- **60/60 hang なし → Phase B-5 へ、inconclusive を受容**。

注: 「hang 数 vs 30」で延長判断する logic は誤り (= advisor #1 で訂正)。hang はもう情報、延長は clean のみ意味がある。

### Phase B-5: 復活後 durable evidence 回収 + 集計 (~10 分)

ssh 復活後 Claude が実施:

```bash
# B-0 で保存した SESSION_START_EPOCH を再読込 (= advisor 指摘 #3、hardcode 排除)
SESSION_START_EPOCH=$(cat /tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/915d0781-2b57-4594-967c-9c8b4214cb22/scratchpad/session_start_epoch.txt)
echo "SESSION_START_EPOCH=$SESSION_START_EPOCH (JST: $(TZ=Asia/Tokyo date -d @$SESSION_START_EPOCH))"

ssh miminashi@macbookair2015.lan "
echo '=== boot_id 変化確認 ==='
cat /proc/sys/kernel/random/boot_id
echo '=== boot 履歴 (hang が 2 回以上起きた場合に必要) ==='
sudo journalctl --list-boots --no-pager | tail -5
echo '=== suspend_stats ==='
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo '=== snapshot count (本セッション分) ==='
echo 'pre total: '\$(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l)
echo 'post total: '\$(sudo ls /var/log/h4-probe/*.post 2>/dev/null | wc -l)
echo 'snapshot-only PRE: '\$(sudo ls /var/log/h4-probe/*.snapshot-only.PRE 2>/dev/null | wc -l)
echo 'snapshot-only POST: '\$(sudo ls /var/log/h4-probe/*.snapshot-only.POST 2>/dev/null | wc -l)
echo '=== unregister_netdevice: waiting 全 boot 集計 (期待: 依然 0) ==='
sudo journalctl --no-pager 2>/dev/null | grep -c 'unregister_netdevice: waiting'
"
```

注意 (advisor #3 補足): hang が 2 回以上起きると boot_id が 2 回以上変わるので、journal は `-b -1` だけでは足りない。`journalctl --list-boots` で boot 履歴を確認し、本セッション分の boot ID を全部洗い出してから per-boot で `ping_running=` を集計する。

#### Ping 集計 (= confound 排除の事後検証、advisor #2 = durable file 経由で確実に)

durable file をベースに集計 (= hang reboot 後も残る、here-doc で escaping を簡潔に):

```bash
ssh miminashi@macbookair2015.lan "bash -s" <<EOF
SESSION_START_EPOCH=$SESSION_START_EPOCH
echo "=== snapshot-only PRE durable file 集計 (ping_running) ==="
total=0; yes=0; no=0
for f in /var/log/h4-probe/*.snapshot-only.PRE; do
  TS=\$(basename "\$f" .snapshot-only.PRE)
  if [ "\$TS" -ge "\$SESSION_START_EPOCH" ]; then
    total=\$((total + 1))
    if sudo grep -q ping_running=YES "\$f"; then
      yes=\$((yes + 1))
      JST=\$(TZ=Asia/Tokyo date -d @\$TS +%H:%M:%S)
      echo "\$JST ping=YES file=\$f"
    else
      no=\$((no + 1))
    fi
  fi
done
echo "=== TOTAL: \$total / ping=YES: \$yes / ping=NO: \$no ==="
EOF
```

期待: ping=YES が **0 件** (= ユーザが約束を守って連続 ping を流さなかった証拠)。1+ なら confound 残存、レポート frame を softening。

#### source-IP retro-classify (全 cycle 分、SESSION_START_EPOCH を動的に注入)

```bash
ssh miminashi@macbookair2015.lan "bash -s" <<EOF
SESSION_START_EPOCH=$SESSION_START_EPOCH

for f in /var/log/h4-probe/*.pre; do
  TS=\$(basename "\$f" .pre)
  if [ "\$TS" -ge "\$SESSION_START_EPOCH" ]; then
    LOCAL_SRC=\$(sudo sed -n '/^=== ip xfrm state ===\$/,/^=== ip xfrm policy ===\$/{/^=== /d; p}' "\$f" | grep "^src " | awk '{print \$2}' | grep -v "^160\.16\.210\.47" | head -1)
    HAS_POST=\$(test -f "\${f%.pre}.post" && echo "OK" || echo "HANG")
    JST=\$(TZ=Asia/Tokyo date -d "@\$TS" +"%H:%M:%S")
    echo "\$JST cycle \$TS src=\${LOCAL_SRC:-INACTIVE} post=\$HAS_POST"
  fi
done
EOF
```

集計:
- **BT_PAN_VALID** (src=172.20.10.*): 真の N
- **WIFI_VPN** (src=192.168.33.*): 0 件必達 (1+ なら本セッション無効)
- **VPN_INACTIVE** (src 不在): 計上不可
- **HANG cycle** (post 欠落): 0 件 or 1+ (= hang ground truth)

#### Hang 発生時の signature 確認 (もし HANG cycle あれば、boot 跨ぎ対応)

hang が起きた boot range を `journalctl --list-boots` で特定し、各 boot で kernel ログを読む:

```bash
ssh miminashi@macbookair2015.lan '
# 本セッションで遭遇した boot を順に
for BOOT in -1 -2 -3; do
  echo "=== boot $BOOT ==="
  sudo journalctl -b $BOOT --no-pager -k 2>/dev/null | grep -E "PM: suspend (entry|exit)|charon-nm.*Network is unreachable|xfrm_state|xfrm_policy" | tail -50 || break
done
'
```

期待 (063543/043251 と同 signature の場合):
- `PM: suspend entry (s2idle)` 1 件
- `PM: suspend exit` 欠落 (= dpm_suspend stall)
- `charon-nm: error writing to socket: Network is unreachable` 1 〜 3 件 (retransmit 含む)
- snapshot-only PRE durable file: `xfrm_state=2 xfrm_policy=14` (= 半分)
- `unregister_netdevice: waiting` は依然 0 件 (= H1 negative continues)

### Phase B-6: クリーンアップ (~5 分)

```bash
ssh miminashi@macbookair2015.lan '
sudo systemctl stop vpn-watcher.service cycle-watcher.service 2>/dev/null || true
sudo rm -f /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
'
```

期待 final 状態 (= 本セッション開始時と同じ):

```bash
ssh miminashi@macbookair2015.lan '
echo "=== hooks (期待: 50/60/70 の 3 個) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
echo "=== transient units (期待: 全 inactive) ==="
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

## Critical files

- **新規作成 (本セッションのみ、B-6 で削除)**: `/usr/lib/systemd/system-sleep/58-snapshot-only` (043251 と同設計 + pgrep ping + durable file 出力追加)
- **副次的に作成され残置 (= durable evidence、削除しない)**: `/var/log/h4-probe/<epoch>.snapshot-only.{PRE,POST}` (本セッション cycle ごとに 2 個生成、累計 +60 ファイル想定、次セッション以降の retro-classify 素材)
- **触らない**: `/usr/lib/systemd/system-sleep/{50-kbd-backlight,60-s3-soak-log,70-h4-probe}` (既存、残置)
- **読むだけ**: `/var/log/h4-probe/*.pre` (累計 180 から +30 で 210 程度になる予定、retro-classify 素材)
- **transient (reboot で消失、B-6 で stop)**: `vpn-watcher.service` / `cycle-watcher.service` (systemd-run --collect)
- **設定変更 (B-6 で revert)**: NM autoconnect (BT-PAN/GSNet → yes), OpenWrt route-metric (-1 → 800), WiFi radio (B-3 で off, hang reboot 後にユーザ手動で on)
- **再利用**: 043251 plan の `vpn-watcher` / `cycle-watcher` systemd-run コマンド (上記 B-1 に再掲)

## 検証 (= verification, レポート前の必須項目)

レポート作成前にユーザに確認すべき点:

1. **ping_running の集計結果**: 全 cycle で `ping_running=NO` か? もし 1+ で YES なら confound 排除に失敗、結論は弱まる (但し直接証拠は得られた → 次セッションは設計を更に強化)
2. **source-IP gate の結果**: 全 cycle で src=172.20.10.* (= BT-PAN)、192.168.33.* (= WiFi) 混入 0 件か?
3. **valid cycle 数 vs hang count**: 例えば 28 BT-PAN-valid + 2 VPN_inactive で 1 hang なら「1 hang / 28 valid」と書く
4. **hang signature 一致**: hang が出たら 063543/043251 と全 6 項目 (Network unreachable retransmit 数、bnep teardown タイミング、xfrm_policy=14、PM:suspend entry の有無、PM:suspend exit 欠落、boot_id 変化、unregister_netdevice 0 件) で一致するか?

## 結果分岐 + 次セッション feed (= advisor 訂正版)

- **1+ hang (= 強い勝ち)**:
  - hang 数 / valid cycle 数 を分母分子で書く (例: 1 / 18 BT-PAN-valid)
  - 「ping 無し + WiFi-off で hang 独立再現 → candidate (d) 更に弱まる、ping は hang の必要条件ではない」が headline
  - 次セッション: 機序ラダー S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) で dpm_suspend の stall device 特定、または `modprobe -r wl` 実験で wl の関与切り分け
- **30/30 hang なし (= inconclusive)**:
  - 60 cycle まで延長 (= null 側 power 追加)
  - 60/60 でも null 下 P(0 hangs | 5% rate)^60 ≈ 0.046 = ~5% で「依然 inconclusive」
  - 「043251 の hang は ping confound 由来かもしれないし、統計的揺らぎかもしれない」が headline (= 結論しない、両解釈オープン)
  - 次セッション: WiFi-off + ping **復活** で repro 試行 (= ping load-bearing 説の直接検証)、または別の修飾変数 (peer, hook layer 等) を変える
- **延長中 (31〜60) で hang 発生**:
  - 上記「1+ hang」と同じ headline、cycle 数だけ追記

## レポート作成 (= 本セッションの納品物)

`report/yyyy-mm-dd_hhmmss_<英語名>.md` 形式で作成。タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得。プランファイル添付必須 (`attachment/<レポートファイル名>/plan.md` にコピー)。

レポートに必ず書く項目:
- 結論 (先に要約): valid cycle 数 / hang 数 / ping_running 集計 / source-IP gate 結果
- 通読版 (= 経緯と本セッションの位置づけ): 「043251 の二つの壁を解消する設計だった」「結果はこうだった」
- 前提・目的: 043251 の二つの壁解消が主目的
- 環境情報: 043251 と同条件 + ping 禁止 + process list 観測追加
- Phase B-0〜B-6 の実施詳細とタイムライン
- 機序評価: candidate (b) が強化されたか弱まったか
- 機序ラダーへの feed: H1/H2/H4 のどれが更新されたか
- 副次的発見: 観測知見、operations 上のフィードバック
- 残置物: 「実機側はクリーン、dev 機側未編集」
- 次セッション引継ぎ: メモリ更新内容、推奨次の手

メモリ更新 (本セッション終了時):
- `s2idle-btvpn-hang-mechanism-ladder`: 本セッション結果 (ping 禁止下の hang rate) を追記、candidate (b) の位置づけを更新
- `MEMORY.md`: index の description を本セッション結論に合わせて更新
