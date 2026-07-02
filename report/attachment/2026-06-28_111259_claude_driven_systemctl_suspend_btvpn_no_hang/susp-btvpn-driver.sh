#!/bin/bash
# suspend ハング再現ドライバ v3 (BT-PAN × VPN)
# 2026-06-28: 2026-06-28_063543 の「BT-PAN をトランスポートにした VPN 併用 s2idle lid close ハング」を
#             Claude 駆動で自動再現するための driver。v2(susp-test-driver.sh) に vpn_up() と wifi 切断を追加。
#
# 使い方: susp-btvpn-driver.sh <PHASE> <N> <BT> <WAKE> <GAP> <PAN_CON> <PAN_IFACE> <VPN_CON> <GW_IP> <WIFI_DEV>
#   PHASE     : ログ用フェーズ名
#   N         : suspend 回数。N=0 は dry-run(suspend せず precheck のみ→wifi 復帰→exit)
#   BT        : on|off (ログ表示用)
#   WAKE      : RTC 自動復帰秒
#   GAP       : 復帰後の待機秒
#   PAN_CON   : BT-PAN の NM 接続名 (毎 suspend 前に con up)
#   PAN_IFACE : PAN iface 名 (IP/xfrm src 照合用)
#   VPN_CON   : VPN の NM 接続名 (毎 suspend 前に con up)
#   GW_IP     : VPN ゲートウェイ IP (egress 経路確認用)
#   WIFI_DEV  : wifi デバイス名 (phase 開始時に dev disconnect=非永続。再起動で復活)
#
# ハング検出: PRE 行あり/POST 行無しが停止点。詳細 SLEEP/WAKE は 60-s3-soak-log が s3-soak.log に記録。
# wifi は dev disconnect(非永続) で落とすため、ハング→電源断→再起動で自動再接続し LAN 復帰する。
# 正常完走時は PHASE DONE で wifi を dev connect して LAN 復帰させる。

set -u
PHASE="${1:?phase}"; N="${2:?count}"; BT="${3:?bt}"; WAKE="${4:-30}"; GAP="${5:-15}"
PAN_CON="${6:?pan_con}"; PAN_IFACE="${7:?pan_iface}"; VPN_CON="${8:?vpn_con}"; GW_IP="${9:?gw}"; WIFI_DEV="${10:?wifi}"
LOG=/var/log/susp-test.log

ts() { TZ=Asia/Tokyo date +%Y-%m-%dT%H:%M:%S%z; }
state() {
  local ms lid ac
  ms=$(cat /sys/power/mem_sleep)
  lid=$(awk '/LID0/{print $NF}' /proc/acpi/wakeup)
  ac=$(cat /sys/class/power_supply/ADP1/online 2>/dev/null)
  echo "mem_sleep=\"$ms\" lid=$lid ac=$ac"
}
panip() { ip -4 -o addr show "$PAN_IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1; }

# PAN を再接続し iface に IPv4 が付くまで最大25s待つ。echo: ok/fail
pan_up() {
  nmcli con up "$PAN_CON" >/dev/null 2>&1
  local i=0
  while [ "$i" -lt 25 ]; do
    [ -n "$(panip)" ] && { echo "ok"; return; }
    sleep 1; i=$((i+1))
  done
  echo "fail"
}

# VPN を再接続。active かつ ESP SA の local src が PAN iface の IP(=BT-PAN 経由)なら ok。
# echo: "<ok|fail> <xfrm_src>"
vpn_up() {
  nmcli con up "$VPN_CON" >/dev/null 2>&1
  local i=0 pip saddr
  pip=$(panip)
  while [ "$i" -lt 25 ]; do
    if nmcli -t -f NAME con show --active 2>/dev/null | grep -qx "$VPN_CON"; then
      pip=$(panip)
      if [ -n "$pip" ] && ip xfrm state 2>/dev/null | awk '/^src/{print $2}' | grep -qx "$pip"; then
        echo "ok $pip"; return
      fi
    fi
    sleep 1; i=$((i+1))
  done
  saddr=$(ip xfrm state 2>/dev/null | awk '/^src/{print $2}' | grep -v "$GW_IP" | head -1)
  echo "fail ${saddr:-none}"
}

wifi_down() { nmcli dev disconnect "$WIFI_DEV" >/dev/null 2>&1; }
wifi_up()   { nmcli dev connect "$WIFI_DEV" >/dev/null 2>&1; }

# ---- phase start ----
echo "$(ts) ===== PHASE START phase=$PHASE N=$N bt=$BT wake=${WAKE}s gap=${GAP}s pan=$PAN_CON vpn=$VPN_CON wifi_dev=$WIFI_DEV $(state)" >> "$LOG"; sync
wifi_down

# ---- dry-run: precheck only, restore wifi, exit ----
if [ "$N" = "0" ]; then
  panst=$(pan_up)
  vres=$(vpn_up); vst=${vres%% *}; vsrc=${vres#* }
  gwdev=$(ip route get "$GW_IP" 2>/dev/null | awk '{for(j=1;j<=NF;j++) if($j=="dev"){print $(j+1); exit}}')
  echo "$(ts) DRYRUN PRECHECK phase=$PHASE panup=$panst pan_ip=$(panip) vpnup=$vst xfrm_src=$vsrc gw_dev=$gwdev $(state)" >> "$LOG"; sync
  nmcli con down "$VPN_CON" >/dev/null 2>&1
  wifi_up
  echo "$(ts) DRYRUN DONE phase=$PHASE (wifi restored)" >> "$LOG"; sync
  exit 0
fi

# ---- 本番: active 通信用に BT-PAN gw への持続 ping を起動 ----
systemd-run --unit=bt-vpn-ping --collect ping -i 1 172.20.10.1 >/dev/null 2>&1 || true

for i in $(seq 1 "$N"); do
  wifi_down                       # 冪等再アサート(resume 後の autoconnect 抑止)
  panst=$(pan_up)
  vres=$(vpn_up); vst=${vres%% *}; vsrc=${vres#* }
  ipnow=$(panip)
  echo "$(ts) ITER $i/$N phase=$PHASE bt=$BT PRE panup=$panst pan_ip=${ipnow:-none} vpnup=$vst xfrm_src=$vsrc $(state)" >> "$LOG"; sync
  /sbin/rtcwake -m no -s "$WAKE" >> "$LOG" 2>&1
  systemctl suspend
  sleep "$GAP"
  echo "$(ts) ITER $i/$N phase=$PHASE bt=$BT POST $(state)" >> "$LOG"; sync
done

systemctl stop bt-vpn-ping >/dev/null 2>&1 || true
echo "$(ts) ===== PHASE DONE phase=$PHASE (restoring wifi)" >> "$LOG"; sync
wifi_up
