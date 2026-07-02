# 2026-06-30 (c) WiFi-off で 30 valid cycle (one-variable-back) + 過去セッション source-IP retro-classify

## Context

### なぜこの実験を行うのか

前セッション [2026-06-30_061553](/home/miminashi/projects/macbookair11-debian/report/2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) は本プロジェクト初の verified N=30 BT-PAN-valid clean (hang 0) を達成したが、bedrock の 063543 (3/3 hang) を消した要因は **4 candidate のいずれも discriminate されない** 状態で終了:

- (a) BT-PAN peer: iPhone → iPad
- (b) WiFi: off → on (metric 800 で routing は BT-PAN 優先だが NIC active)
- (c) hook: 50/60 のみ → 50/60/70 + 58 (suspend entry で real work)
- (d) 063543 の baseline hang rate が想定より低い (corrosive、explicitly downweighted)

candidate を 1 つずつ潰す **one-variable-back** が正しい次の手。優先順位順で:

1. (b) WiFi-off ← **今回**
2. (a) iPhone peer
3. (c) hook minimal mode

### 本セッションで達成したいこと

- **Phase A (~10 分)**: 過去セッション 041006 (22/22 valid claim) と 064608 (~14 valid claim) を source-IP ベースで retro-classify。state count gate ベースの過去判定が source-IP gate でも維持されるか確定。bedrock 化
- **Phase B (~80-100 分)**: WiFi 完全 off + 他 (iPad, hook, vpn-watcher) は 061553 と同一条件で 30 valid cycle 駆動。結果に応じて:
  - **1+ hang** → 「WiFi-on が protective」確定 = candidate (b) 採用 → 機序解明 (= WiFi NIC の何が device-suspend chain を変えるか) へ
  - **0/30** → WiFi-off も clean → 次の variable (peer or hook) へ

### この実験で分かること / 分からないこと

**分かる**: WiFi 介在 (NIC active) が 063543 hang と本セッション 0/30 の差分要因かどうか。

**分からない**: 仮に 0/30 なら他の candidate (a)(c)(d) を絞り込めない。仮に 1+ hang なら「WiFi の何が」までは分からない (機序探求は別フェーズ)。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、LID0 `*enabled`
- system-sleep hooks (実験開始時): `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の 3 個
- 電源: 全 cycle AC 給電 (前回と同様)
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, BT-PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner `192.168.83.1/32`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` → **本セッションで完全 disable**
- baseline (実機実測 2026-07-01): boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変、061553 終了時から不変)、suspend_stats success=221 fail=0、snapshot count=160 pre、NM autoconnect 両方 no、route-metric -1

### 役割分担

- ssh で実機操作 (hook デプロイ、transient unit 起動、状態確認、retro-classify): **Claude**
- iPad テザリング ON/OFF + NM GUI 操作 (BT-PAN/GSNet up): **ユーザ**
- 物理 lid close + 電源ボタン wake: **ユーザ**
- iPad ペアリング再構成 (BT-PAN 詰まり時): **ユーザ**

WiFi-off により dev 機 (akdx01) からの ssh は完全不可になる。cycle 駆動中は実機側 transient unit が全部記録、ユーザに口頭で進捗報告依頼、WiFi を最後に enable して Claude が状態回収。

## Phase A: 041006 / 064608 source-IP retro-classify (~10 分)

### 目的

state count gate ベースで「22/22 valid」(041006) / 「~14 valid」(064608) と判定された過去結果を、source-IP gate でも検証して bedrock 化。WiFi 経由 VPN (= 192.168.33.* on outer) が混入していた cycle があれば、その分を invalid として再集計。

### セッション期間 (タイムスタンプ)

過去レポートから取得 (CLAUDE.md ルールで JST 厳守):

- 041006: 2026-06-29 03:25 〜 03:56 JST (報告ファイル名 `2026-06-29_041006_*`)
- 064608: 2026-06-29 05:43 〜 06:43 JST (同 `2026-06-29_064608_*`)

事前に各レポートの「Phase / タイムライン」セクションで開始-終了時刻を再確認 (本プラン作成時は推定で記載、実行時に grep で正確化)。

### 実行スクリプト (061553 Phase 5 の再利用)

```bash
ssh miminashi@macbookair2015.lan '
# 区切り文字を "|" にして timestamp の ":" 衝突を回避 (advisor 指摘で訂正)
for SESSION in "041006|2026-06-29 03:25 JST|2026-06-29 03:56 JST" \
               "064608|2026-06-29 05:43 JST|2026-06-29 06:43 JST"; do
  NAME=$(echo "$SESSION" | cut -d"|" -f1)
  START=$(echo "$SESSION" | cut -d"|" -f2)
  END=$(echo "$SESSION" | cut -d"|" -f3)
  EPOCH_START=$(date -d "$START" +%s)
  EPOCH_END=$(date -d "$END" +%s)
  echo "=== $NAME ($START 〜 $END, epoch $EPOCH_START〜$EPOCH_END) ==="
  RESULTS=""
  for f in /var/log/h4-probe/*.pre; do
    TS=$(basename "$f" .pre)
    if [ "$TS" -ge "$EPOCH_START" ] && [ "$TS" -le "$EPOCH_END" ]; then
      LOCAL_SRC=$(sudo sed -n "/^=== ip xfrm state ===$/,/^=== ip xfrm policy ===$/{/^=== /d; p}" "$f" | grep "^src " | awk "{print \$2}" | grep -v "^160\\.16\\.210\\.47" | head -1)
      if [ -z "$LOCAL_SRC" ]; then CLASS="VPN_INACTIVE"
      elif echo "$LOCAL_SRC" | grep -q "^172\\.20\\.10"; then CLASS="BT_PAN_VALID"
      elif echo "$LOCAL_SRC" | grep -q "^192\\.168\\.33"; then CLASS="WIFI_KNOWN_CLEAN"
      else CLASS="OTHER:$LOCAL_SRC"
      fi
      TS_JST=$(TZ=Asia/Tokyo date -d "@$TS" +"%H:%M:%S")
      RESULTS="${RESULTS}${TS_JST}\t${CLASS}\n"
    fi
  done
  echo -e "$RESULTS" | column -t
  echo "--- summary ---"
  echo -e "$RESULTS" | awk "{print \$2}" | sort | uniq -c
done
'
```

事前にレポートから正確な開始/終了タイムスタンプを `grep -E "Phase [0-9]" report/2026-06-29_041006_*.md` 等で抽出して上記スクリプトに当てはめる。

### 期待結果と解釈 (advisor 指摘訂正版)

| セッション | state count ベース判定 | source-IP 予測 | 注 |
|---|---|---|---|
| 041006 | 22/22 valid (xfrm count=2) | **多くが BT_PAN_VALID** | 過去 retro-classify で count=2 を確認済 = VPN active → outer src は 172.20.10.* (BT-PAN) が most likely |
| 064608 | 14 valid (xfrm count=2 の cycle 数) | 同じく多くが BT_PAN_VALID と予測 | 当時 WiFi 経由が混入していたら一部 WIFI_KNOWN_CLEAN になる |

**重要**: 予測は anchor として使わない。データに語らせる。WIFI_KNOWN_CLEAN が出たら過去 valid claim は縮小される。

### 解釈分岐

| 結果パターン | 解釈 |
|---|---|
| 041006 BT_PAN_VALID ≒ 22、WIFI 0 | state count gate と source-IP gate が一致。「22/22 BT-PAN-valid hang 0」を bedrock 化 |
| 041006 に WIFI_KNOWN_CLEAN 混入 | xfrm count=2 でも WiFi 経由だった cycle あり = valid 数を縮小、claim 訂正 |
| 041006 全 VPN_INACTIVE | xfrm 過去 count 観察 (=2) と矛盾 = retro-classify スクリプト or 既存データの bug。要原因究明 |
| 064608 BT_PAN_VALID ≒ 14、WIFI 0 | state count gate と一致、bedrock 維持 |
| 064608 BT_PAN_VALID が 14 より大きく減少 | WiFi 経由混入分が invalid 化、「driver path 14 valid 0 hang」claim も実質縮小 |

結果は本セッション最終レポートの retro-classify 表として記録。判定変更があった場合はメモリ `s2idle-btvpn-hang-mechanism-ladder` の「過去セッションの valid 性」表を更新。

## Phase B: WiFi-off で 30 valid cycle (~80-100 分)

### Phase B-0: 事前準備 (~5 分)

```bash
ssh miminashi@macbookair2015.lan '
echo "=== Phase B-0 baseline ==="
cat /proc/sys/kernel/random/boot_id
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
ls /usr/lib/systemd/system-sleep/
sudo cat /var/lib/h4-probe/mode
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting"
'
```

期待 (実機実測 2026-07-01 baseline):
- boot_id 不変、suspend_stats=221/0、hooks 3 個、mode=beta、autoconnect 両方 no、route-metric -1、unregister 0 件

### Phase B-1: hook + transient units デプロイ (~5 分)

#### 58-snapshot-only hook 投入 (061553 Phase 2 と同じ)

```bash
ssh miminashi@macbookair2015.lan '
sudo tee /usr/lib/systemd/system-sleep/58-snapshot-only > /dev/null <<\EOF
#!/bin/bash
# bnep statistics + kbnepd presence + netdev presence + xfrm count snapshot
# 058 = NM teardown 完了直後、70-h4-probe より先に走る
case "$1/$2" in
  pre/suspend)
    PHASE="PRE"
    ;;
  post/suspend)
    PHASE="POST"
    ;;
  *) exit 0 ;;
esac

# bnep delta (前 snapshot からの変化、初回は absolute)
BNEP_RX=$(cat /sys/class/net/bnep0/statistics/rx_bytes 2>/dev/null || echo "0")
BNEP_TX=$(cat /sys/class/net/bnep0/statistics/tx_bytes 2>/dev/null || echo "0")
logger -t snapshot-only "[$PHASE] bnep_rx=$BNEP_RX bnep_tx=$BNEP_TX"

# kbnepd kthread
if pgrep -f "kbnepd" > /dev/null; then
  logger -t snapshot-only "[$PHASE] kbnepd_session=alive"
else
  logger -t snapshot-only "[$PHASE] kbnepd_session=NOT FOUND"
fi

# bnep netdev
if ip link show bnep0 > /dev/null 2>&1; then
  logger -t snapshot-only "[$PHASE] bnep_netdev=present"
else
  logger -t snapshot-only "[$PHASE] bnep_netdev=MISSING"
fi

# xfrm state + policy count
XFRM_STATE=$(ip xfrm state | grep -c "^src ")
XFRM_POLICY=$(ip xfrm policy | grep -c "^src ")
logger -t snapshot-only "[$PHASE] xfrm_state=$XFRM_STATE xfrm_policy=$XFRM_POLICY"

sleep 0.5
EOF
sudo chmod +x /usr/lib/systemd/system-sleep/58-snapshot-only
# smoke test
sudo /usr/lib/systemd/system-sleep/58-snapshot-only pre suspend
sudo journalctl -t snapshot-only -n 4 --no-pager
'
```

#### vpn-watcher 起動

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=vpn-watcher --collect bash -c "
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
"
'
```

#### bt-pan-keepalive は投入しない (重要、advisor 指摘で訂正)

**当初は 10 秒間隔の ping を打つ bt-pan-keepalive を投入する計画だったが、これは second variable change になり one-variable-back が崩れる**:

- 061553 (clean, 30/30) は「素 traffic + vpn-watcher (on-demand のみ)」で実施。定期 BT 通信は無い
- bt-pan-keepalive を入れると `(WiFi-on, no-keepalive)` vs `(WiFi-off, +keepalive)` の二変数比較になる
- H4 (btusb URB drain) は in-flight URB が race 窓拡大要因と 074509 で指摘済 → keepalive は URB を増やす方向 → 仮に hang が出ても「WiFi-on protective」と「keepalive が race を増やした」が区別不能
- → **0/30 は OK (extra traffic でも clean は保守的結論)、1+ hang は poisoned**

ゆえに 061553 と同じ「on-demand のみ、hotspot 切れたら復旧手順」で運用。連続駆動で 16 分以内に 30 valid 集める or 切れたら復旧する想定。

#### cycle-watcher + cycle-progress ファイル書き出し

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=cycle-watcher --collect bash -c "
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
"
'
```

`/dev/shm/cycle-progress` は WiFi-off 中は読めないが、WiFi 復活後に Claude が回収。ユーザは「何 cycle 目か」を口頭で把握 (cycle-watcher の journal が直接見れないため、後述の TUI で状態表示する案も検討)。

#### NM autoconnect 設定

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
'
```

### Phase B-2: BT-PAN + VPN セットアップ (~5 分)

ユーザ操作:
1. iPad で Personal Hotspot を ON にする
2. macbook で NM GUI から「iMiminashiPadPro ネットワーク」を up (BT-PAN 確立)
3. macbook で NM GUI から GSNet を up (VPN 確立)

Claude 確認:
```bash
ssh miminashi@macbookair2015.lan '
nmcli con show --active
ip xfrm state | head -10
ip route get 160.16.210.47
'
```

期待:
- bnep0 / GSNet が active
- xfrm state count=2、src=172.20.10.13 dst=160.16.210.47 (= VPN over BT-PAN)
- route 160.16.210.47 が `dev bnep0 src 172.20.10.13`

### Phase B-3: WiFi-off (~1 分、ssh 切断ポイント)

**「WiFi off」の具体的方式**: 063543 はユーザが NM applet GUI で WiFi トグル OFF した = D-Bus 経由 `NetworkManager.WirelessEnabled=false` = `nmcli radio wifi off` と等価 (soft rfkill)。本セッションも同じソフトレベルで off にする。

```bash
ssh miminashi@macbookair2015.lan '
# WiFi soft rfkill (= 063543 と同じレベル、wl モジュールはロード状態のまま)
sudo nmcli con down OpenWrt
sudo nmcli radio wifi off
# 確認
echo "=== WIFI status (期待: disabled, wlp3s0 DOWN, OpenWrt 消失) ==="
nmcli -t -f WIFI radio
ip link show wlp3s0 | head -2
nmcli con show --active
echo "=== wl module (063543 と同じく load されたまま) ==="
lsmod | grep "^wl "
'
```

**重要 (advisor 指摘の事項)**: `nmcli radio wifi off` は soft rfkill であり wl ドライバはロード状態のまま dpm_suspend chain に参加し続ける。これは 063543 (NM applet トグル) と同じレベル。**もし「wl が dpm_suspend に参加すること自体」が hang の決定因なら本実験では discriminate されない**。それを切り分けるには `sudo modprobe -r wl` まで踏み込む別実験が必要 (= 三変数目になるので別セッション)。

**この時点以降、dev 機から実機への ssh は不可になる**。実機側で全 logic が走る。

### Phase B-4: cycle 駆動 (~60-80 分)

ユーザ操作 (口頭ガイド):
- 「lid close → wake (電源ボタン短押し) → 20 秒待ち → 次 lid close」を 30 valid cycle まで繰り返す
- 各 cycle の wake 時に「画面が ON になったら 20 秒数えてから次の lid close」と指示
- iPad hotspot が切れた疑いがあれば (体感: BT-PAN icon が消える等)、`bt-pan-keepalive` を信じて続行。10 分以上反応なければ復旧手順

進捗確認の方式 (3 案、優先順):
- **(優先) ターミナル常駐表示**: ユーザ自身の terminal (macbook 上の別ターミナル、ssh じゃない) で `watch -n 1 cat /dev/shm/cycle-progress` を見てもらう
- (代替) suspend 30 回 = 「目視で 30 回 lid close したらストップ」(invalid 混入で <30 valid の可能性あり、その場合は数 cycle 追加で補完)
- (緊急) ssh が必要なら、ユーザに `nmcli radio wifi on && nmcli con up OpenWrt` を実機で手動実行してもらう (= 実験 condition 崩壊、要再判断)

**重要 (hang 検出の ground truth) (advisor 指摘)**: 上記 `/dev/shm/cycle-progress` 表示と `suspend_stats/success` カウンタは hang → 強制電源断 → reboot で消える (tmpfs リセット + per-boot 値リセット)。さらに NM は `WirelessEnabled=false` を永続化するので reboot 後も WiFi off のまま = ssh 不可継続。したがって **hang の durable ground truth は `/var/log/h4-probe/<TS>.pre` が存在するのに対応する `<TS>.post` が無い (= 永続ディスク上の不整合ペア)** + `/var/log/journal` の `60-s3-soak-log` SLEEP/WAKE ペア欠落。ユーザに「hang したら手動で WiFi 戻して (`sudo nmcli radio wifi on && sudo nmcli con up OpenWrt`)」と事前に伝えておく。WiFi 復帰後に Claude が ssh で `.pre` / `.post` ペア検証で hang cycle を特定する。

#### 中断条件 (continue/stop の判断基準)

| 状況 | 対応 |
|---|---|
| 30 valid 集まる前に hang 1+ 発生 | **即停止**。boot_id 不変 = clean wake、boot_id 変化 = hang 復旧の強制電源断。hang 観測時点で「WiFi-on protective」確定、Phase B 終了 |
| iPad hotspot 切れ (cycle 5 以下) | bt-pan-keepalive 動作確認 (ping success rate)、不調なら復旧手順 → 再開 |
| iPad hotspot 切れ (cycle 10+ 集まってから) | 同上、復旧後 valid 数を上積み |
| bluetoothd `Operation already in progress` | 復旧手順: `nmcli con down` → `bluetoothctl disconnect` → `systemctl restart bluetooth.service` → iPad ペアリング再構成 (061553 で確立) |
| 30 cycle 試行で valid <20 | hotspot timeout 多発 = condition 維持困難、中間データで結論を保留 |
| 30 valid 達成 hang 0 | Phase B-5 へ |

### Phase B-5: 集計 + retro-classify (~5-10 分)

ユーザに「WiFi 戻して」依頼:
```bash
# macbook 上でユーザが実行 (あるいは Claude を ssh 経由で呼び戻すために WiFi 復活)
sudo nmcli radio wifi on
sudo nmcli con up OpenWrt
```

WiFi 復活後、Claude が ssh で集計:
```bash
ssh miminashi@macbookair2015.lan '
echo "=== boot_id (hang あれば変化) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== cycle progress ==="
cat /dev/shm/cycle-progress
echo "=== unregister_netdevice: waiting ==="
sudo journalctl --no-pager -b 2>/dev/null | grep -c "unregister_netdevice: waiting"
echo "=== snapshot count ==="
sudo ls /var/log/h4-probe/*.pre | wc -l
'
```

#### source-IP retro-classify (Phase B 期間限定)

```bash
ssh miminashi@macbookair2015.lan '
# Phase B 開始時刻 (Phase B-1 開始) と終了時刻 (Phase B-4 最終 wake) を Claude が把握
EPOCH_START=$(date -d "2026-XX-XX HH:MM JST" +%s)  # 実行時に置換
EPOCH_END=$(date -d "2026-XX-XX HH:MM JST" +%s)
RESULTS=""
for f in /var/log/h4-probe/*.pre; do
  TS=$(basename "$f" .pre)
  if [ "$TS" -ge "$EPOCH_START" ] && [ "$TS" -le "$EPOCH_END" ]; then
    LOCAL_SRC=$(sudo sed -n "/^=== ip xfrm state ===$/,/^=== ip xfrm policy ===$/{/^=== /d; p}" "$f" | grep "^src " | awk "{print \$2}" | grep -v "^160\\.16\\.210\\.47" | head -1)
    if [ -z "$LOCAL_SRC" ]; then CLASS="VPN_INACTIVE"
    elif echo "$LOCAL_SRC" | grep -q "^172\\.20\\.10"; then CLASS="BT_PAN_VALID"
    elif echo "$LOCAL_SRC" | grep -q "^192\\.168\\.33"; then CLASS="WIFI_KNOWN_CLEAN"
    else CLASS="OTHER:$LOCAL_SRC"
    fi
    TS_JST=$(TZ=Asia/Tokyo date -d "@$TS" +"%H:%M:%S")
    RESULTS="${RESULTS}${TS_JST}\t${CLASS}\n"
  fi
done
echo -e "$RESULTS"
echo "--- summary ---"
echo -e "$RESULTS" | awk "{print \$2}" | sort | uniq -c
'
```

期待: WiFi-off なので **WIFI_KNOWN_CLEAN は 0 件**、BT_PAN_VALID + VPN_INACTIVE のみ。WIFI_KNOWN_CLEAN が出たら実験設計の根本ミス (WiFi-off が機能していなかった) で要再検討。

### Phase B-6: クリーンアップ (~5 分)

```bash
ssh miminashi@macbookair2015.lan '
sudo systemctl stop vpn-watcher.service cycle-watcher.service
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
# WiFi は Phase B-5 で復活済、route-metric はそもそも -1 のまま
# 確認
ls /usr/lib/systemd/system-sleep/
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

期待 final 状態 (= 本セッション開始時と一致):
- hooks 3 個 (50/60/70)
- transient units 全 inactive
- NM autoconnect 両方 no
- WiFi 復活、OpenWrt active
- snapshot count = baseline + 30+ pre

## 結果判定と機序ラダー更新

### Phase B 結果別の解釈

| 結果 | 解釈 | candidate 判定 | 次セッション |
|---|---|---|---|
| 30/30 BT_PAN_VALID hang 0 | WiFi-off も clean | (b) WiFi-on は protective ではない、(a)(c)(d) が残候補 | (a) iPhone peer or (c) hook minimal mode |
| 1+ hang / 30 valid | WiFi-on が protective | (b) candidate 採用 | WiFi NIC の何が device-suspend を変えるか機序探求 (= H1/H2/H4 ラダー再開) |
| valid <20 で打ち切り | hotspot timeout で condition 維持困難 | 不確定、データ不足 | bt-pan-keepalive 強化 or peer 切替 |

### 0/30 の strength 定量化 (前セッション framing を継承)

- 063543 cell hang rate ≒ 30% (3/10) → (1−0.3)^30 ≒ 2e-5 = very strong evidence で同 condition でない
- candidate (d) (baseline 低い) を採用しても 10% 想定で (1−0.1)^30 = 4.2% = moderate evidence

### メモリ更新内容

`s2idle-btvpn-hang-mechanism-ladder`:
- 「過去セッションの valid 性」表に 041006/064608 の source-IP retro-classify 結果を反映
- 「本セッション結果」セクションを追加 (WiFi-off N=30 の結果)
- 「次の手」リストを Phase B 結果次第で更新

## 検証 (CLAUDE.md に従う)

### 実機状態の検証
- WiFi-off 中は ssh 不可なので、Phase B-5 で WiFi 復活後に状態回収
- boot_id 不変 = 再起動なし = hang 起きていない (or 起きたとしても manual reset していない)
- suspend_stats success delta = 試行 cycle 数
- `cat /dev/shm/cycle-progress` = cycle-watcher 内部記録、ハングまでの cycle 数

### 結果の妥当性検証
- source-IP retro-classify で全 cycle の outer source IP が 172.20.10.* または 無し であることを確認
- 192.168.33.* (WiFi) が 1 件でもあれば実験設計の失敗 = WiFi-off が機能していない

### レポート作成 (CLAUDE.md ルール準拠)
- ファイル名: `report/2026-XX-XX_HHMMSS_s2idle_btvpn_wifi_off_one_variable_back.md` (タイムスタンプは実機で `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得)
- 日時表記は JST
- プランファイルを `report/attachment/<basename>/plan.md` に添付
- 添付セクションを本文に記載
- 過去レポートへのリンク (061553、063543、074509 等)

## 想定所要時間

- Phase A: 10 分
- Phase B-0 ~ B-3: 15 分 (準備 + WiFi-off)
- Phase B-4: 60-80 分 (30 valid cycle、復旧分含めて余裕)
- Phase B-5 ~ B-6: 15 分 (集計 + クリーンアップ)
- レポート作成 + メモリ更新: 20-30 分
- **合計**: 約 2-2.5 時間

## 残留リスクと未解決課題

1. **soft rfkill vs hard unload の discriminate 限界**: `nmcli radio wifi off` は wl モジュールをロード状態のまま残す → dpm_suspend chain には依然参加する。「wl がスリープ chain に居ること自体」が決定因なら本実験では識別不能 (`sudo modprobe -r wl` まで踏み込む別実験で初めて identify)。本セッションは「063543 と同じ wifi off 方式」の範囲内で限定的に discriminate
2. **WiFi-off ssh 不可期間中の状態異常検出**: hang 起きたら user が気づく (画面が ON にならない、suspend_stats が増えない) しかない。`/dev/shm/cycle-progress` のローカル監視を user の terminal で `watch` してもらうのが現実的
3. **`nmcli radio wifi off/on` で broadcom-sta が再 init される可能性**: NIC を up/down することで wl ドライバが reload されたら、次回 WiFi 復活時に device-suspend chain が変わってる可能性。`lsmod | grep wl` の状態確認を Phase B-0 と B-5 で取得して比較
4. **iPad hotspot timeout は keepalive 無しで耐えるか不明**: 061553 では 16 分間隔で 1 回切れた (16 cycle + 復旧コスト)。本セッションは on-demand traffic のみで連続駆動するため、より早く切れる可能性がある。invalid 数許容を 10 程度に設定 (= 試行最大 40 cycle、それで 30 valid 集まらなければ打ち切り)。早期に切れる場合は別セッションで keepalive 入り再検証 (= second-variable 認識して decision table 修正)
5. **iPad ペアリングの bonding 喪失**: 061553 で発生した「ペアリング再構成必須」事態が再発した場合、Phase B 中断 → 復旧 → 再開で valid 数が一回リセットされる
6. **本実験は (b) しか discriminate しない**: 0/30 でも 1+hang でも (a)(c)(d) は同様に確定しない。「次の variable に進む」プロトコルが必要 (= 本セッション後に必ず別セッションで継続)
