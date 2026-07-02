#!/bin/bash
# suspend ハング再現ドライバ v2
# 使い方: susp-test-driver.sh <PHASE> <N> <BT_STATE> [WAKE] [GAP] [PAN_CON] [PAN_IFACE]
#   PHASE     : ログ用フェーズ名
#   N         : suspend 回数
#   BT_STATE  : on|off (ログ表示用)
#   WAKE      : RTC 自動復帰秒数 (既定 30)
#   GAP       : 復帰後の待機秒数 (既定 15)
#   PAN_CON   : (任意) NM接続名。指定時は毎suspend前に con up して iface に IP が付くまで待つ
#   PAN_IFACE : (任意) PAN iface 名 (IP 確認用)
#
# 各 iteration は suspend 前に PRE 行を sync 永続化。ハング時は PRE あり/POST 無しが停止点。
# 詳細 SLEEP/WAKE/drm_err は既存 60-s3-soak-log フックが /var/log/s3-soak.log に記録。

set -u
PHASE="${1:?phase}"; N="${2:?count}"; BT="${3:?bt}"; WAKE="${4:-30}"; GAP="${5:-15}"
PAN_CON="${6:-}"; PAN_IFACE="${7:-}"
LOG=/var/log/susp-test.log

ts() { TZ=Asia/Tokyo date +%Y-%m-%dT%H:%M:%S%z; }
state() {
  local ms lid ac
  ms=$(cat /sys/power/mem_sleep)
  lid=$(awk '/LID0/{print $NF}' /proc/acpi/wakeup)
  ac=$(cat /sys/class/power_supply/ADP1/online 2>/dev/null)
  echo "mem_sleep=\"$ms\" lid=$lid ac=$ac"
}
# PAN を再接続し iface に IPv4 が付くまで最大25s待つ。戻り値: ok/fail を echo
pan_up() {
  [ -z "$PAN_CON" ] && { echo "skip"; return; }
  nmcli con up "$PAN_CON" >/dev/null 2>&1
  local i=0
  while [ "$i" -lt 25 ]; do
    if ip -4 addr show "$PAN_IFACE" 2>/dev/null | grep -q 'inet '; then echo "ok"; return; fi
    sleep 1; i=$((i+1))
  done
  echo "fail"
}

echo "$(ts) ===== PHASE START phase=$PHASE N=$N bt=$BT wake=${WAKE}s gap=${GAP}s pan=${PAN_CON:-none} $(state)" >> "$LOG"; sync

for i in $(seq 1 "$N"); do
  panst=$(pan_up)
  ipnow=$(ip -4 -br addr show "$PAN_IFACE" 2>/dev/null | awk '{print $3}')
  echo "$(ts) ITER $i/$N phase=$PHASE bt=$BT PRE panup=$panst pan_ip=${ipnow:-none} $(state)" >> "$LOG"; sync
  /sbin/rtcwake -m no -s "$WAKE" >> "$LOG" 2>&1
  systemctl suspend
  sleep "$GAP"
  echo "$(ts) ITER $i/$N phase=$PHASE bt=$BT POST $(state)" >> "$LOG"; sync
done

echo "$(ts) ===== PHASE DONE phase=$PHASE" >> "$LOG"; sync
