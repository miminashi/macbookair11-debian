# s2idle BT-PAN+VPN lid close hang: 因果分離実験 S3'' (traffic-only off)

## Context

**直前セッション**: [report/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md](/home/miminashi/projects/macbookair11-debian/report/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) で **S3 (bnep teardown pre フック) 32 cycle 手動 lid close 全 clean** を達成 (`0.90^32 ≒ 3.4%`、ほぼ確定ライン)。判定:

> 真因は「**H2 (non-freezable bnep_session kthread が dpm_suspend 段に in-flight)**」か「**H4 + bnep/traffic との相互作用 (URB drain race)**」のいずれか。両者の分離は本実験では不可能 (confound)。

**200520 引継ぎ案 (i) S3' (bluetoothctl disconnect 抜き) は設計欠陥で却下**: bnep netdev を teardown すると netdev 経由の IP パケットが消え bulk URB が drained → H2 が真でも H4 が真でも 0 hang を予測 → **分離不能**。

**代替案 (本セッションで実施)**: **S3'' = traffic-only off** = bnep_session/xfrm/bnep netdev は完全 up のまま、**ping flood を最初から走らせない**条件 (063543 元再現条件と同じ「軽 traffic」) で 30 cycle 手動 lid close を実施する。pre フックは現状 snapshot のみで teardown は一切しない。

**実機現状** (本セッション開始時 ssh 確認):
- mem_sleep=s2idle、boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変)、suspend_stats=157/0
- system-sleep hooks 3 個 (50-kbd-backlight, 60-s3-soak-log, 70-h4-probe)、h4-mode=beta
- NM autoconnect 両方 no、route-metric -1、`unregister_netdevice: waiting` 0 件 (H1 判別子 negative 再確認)

**重要な背景** (063543 元再現条件):
- 元の 3/3 hang は **ping flood なしの実使用 traffic** (IKE keepalive のみ) で再現 → **「heavy traffic」は hang の必要条件ではない**
- これが既に H2 (bnep_session 存在自体が driver) 寄りの傍証

## 設計: H2 vs H4 を厳密分離する

### 戦略

**ping flood (traffic-gen) を最初から走らせない** で 30 cycle 手動 lid close を実施 = 063543 (元 3/3 hang 観測条件) と同じ「軽 traffic」(IKE keepalive + iPad↔Mac BT-PAN keepalive のみ) 条件を再現する。200520 (heavy traffic ありで bnep teardown 介入) とは別条件。

### pre フックの作用

`58-snapshot-only` は **何も teardown しない、何も停止しない、snapshot のみ**:
- bnep netdev rx/tx delta (500ms window) で軽 traffic 状況を記録
- bnep_session kthread 存在確認 (H2 driver 残存の証拠)
- bnep netdev 存在確認 (= netdev 経由 IP path 維持の証拠)
- xfrm state/policy counts (= VPN teardown 未発生の証拠)

`nmcli` `bluetoothctl` `hcitool` `traffic-gen stop` `pkill ping` は **一切呼ばない** (= bnep_session kthread, xfrm state/policy, bnep netdev, ACL link を全て保持して suspend 経路に進入)。

### 仮説と判定

| 結果 | 解釈 |
|---|---|
| **1+ hang / 30 cycle** | heavy traffic 不要 → **H2 (bnep_session 存在自体が driver) を強く支持**。即 upstream patch 提案準備へ |
| **0 / 30 clean** | H4 (in-flight URB volume が driver) を示唆だが `0.90^30 ≒ 4%` で bound するに留まる。即確定ではない。次セッションで S3'-orig (bluetoothctl disconnect で ACL も切る) か S2 (xfrm flush) を比較対照に走らせる |

**caveat** (advisor 指摘):
- baseline 10% は session 間比較 (matched within-session は hang destructive で取れない)
- 1+ hang の信号が圧倒的に鋭い。0/30 は弱い

## Phase 0: 一時設定 (≈5 分)

実機 ssh で:
```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
```
(h4-mode は beta のまま。200520 副次的発見 A で「alpha でも実際は rtcwake 呼ばれない」と判明済)

ユーザ操作:
- iPad テザリング ON → NM GUI で BT-PAN up → GSNet up
- `ip xfrm state | grep "src 172.20.10\."` で VPN endpoint が BT-PAN IP か確認
- `ip route get 10.0.0.1` で `dev nm-xfrm-N` 経由を確認

## Phase 1: snapshot-only フック投入 (≈3 分)

**`/usr/lib/systemd/system-sleep/58-snapshot-only`** (755):
```sh
#!/bin/sh
# S3''=traffic-only off: bnep/xfrm/btusb は完全 up のまま、in-flight bulk URB の量だけを観測
# (本実験では traffic-gen を一切走らせないため pre 介入は snapshot のみ)
case "$1" in
  pre)
    rx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    sleep 0.5
    rx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    logger -t 58-snapshot-only "bnep delta 500ms: rx=$((rx_after-rx_before))B tx=$((tx_after-tx_before))B"
    if pgrep -af 'kbnepd|\[bnep' > /dev/null 2>&1; then
      logger -t 58-snapshot-only "bnep_session kthread alive (H2 driver present)"
    else
      logger -t 58-snapshot-only "WARN bnep_session kthread NOT FOUND"
    fi
    if ip -br link show 2>/dev/null | grep -qE '^(bnep0|enx98e0d98d205e)\s'; then
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

検証: `sudo bash -n /usr/lib/systemd/system-sleep/58-snapshot-only`、`chmod 755`。実 suspend は cycle 1 を smoke test 兼用 (= cycle 1 wake 後に `journalctl -t 58-snapshot-only -b` で pre 発火と各行確認)。

## Phase 2: 30 cycle 手動 lid close 駆動 (≈50-60 分)

**cycle-watcher** (200520 と同じ pattern、実機側 transient unit):
```bash
sudo systemd-run --unit=cycle-watcher --collect bash -c '
prev=$(cat /sys/power/suspend_stats/success)
base=$prev
prev_fail=$(cat /sys/power/suspend_stats/fail)
exec > /var/log/cycle-watcher.log 2>&1
while true; do
  cur=$(cat /sys/power/suspend_stats/success)
  cur_fail=$(cat /sys/power/suspend_stats/fail)
  if [ "$cur" != "$prev" ] || [ "$cur_fail" != "$prev_fail" ]; then
    echo "$(date +%H:%M:%S) cycle $((cur-base)) (success=$cur, fail=$cur_fail, boot_id=$(cat /proc/sys/kernel/random/boot_id | cut -c1-8))"
    prev=$cur; prev_fail=$cur_fail
  fi
  sleep 2
done
'
```

**プロトコル** (200520 で確立):
1. ユーザ: 蓋を閉じる (BT-PAN+VPN active、ping flood なし、軽 traffic のみ)
2. 30-60 秒待機
3. ユーザ: **電源ボタン短押し** で wake (200520 副次的発見 B: 手動 lid close + s2idle では lid open による wake は機能しない)
4. wake 確認後 5-10 秒で次 cycle へ
5. 30 回繰り返し (200520 で 32 cycle 達成済、同程度を狙う)

**hang 検出と evidence preservation** (200520 と同じ):
- ssh 切断 + 30+ 秒無反応 → ユーザにキー連打 wake 試行 → 反応なければ強制電源断 (電源ボタン長押し)
- 電源復旧後、Phase 4 cleanup 前に **必ず以下を保全**:
  ```bash
  ssh miminashi@macbookair2015.lan '
  cat /proc/sys/kernel/random/boot_id
  sudo journalctl -b -1 -k | grep -E "(PM: suspend|58-snapshot-only|kbd-backlight)" > /tmp/hang-evidence-$(date +%s).txt
  sudo ls /sys/fs/pstore/ > /tmp/hang-pstore-$(date +%s).txt
  sudo tail -200 /var/log/s3-soak.log > /tmp/hang-soak-$(date +%s).txt
  sudo cp -r /var/log/h4-probe /tmp/hang-h4probe-$(date +%s)/
  '
  ```
- hang 発生 cycle 番号と evidence を記録 → ユーザと協議して continue/abort 判断

## Phase 3: 結果集計 (≈5 分)

| 指標 | 期待 (clean) | 評価ポイント |
|---|---|---|
| boot_id | `fcc3d4b0...` 不変 | 1+ 件で変化 → hang |
| suspend_stats success delta | +30 以上 | 不足 → silent hang or evidence loss |
| PM entry/exit ペア | 30/30 | 不一致 → 当該 cycle が hang |
| 58-snapshot-only 発火 | 30 回 | 不足 → hook 機能不全 |
| bnep delta 500ms | rx/tx <10KB 程度 (= 軽 traffic、IKE keepalive レベル) | 大きすぎ → 想定外の bnep tunnel traffic 源 (実験前提崩壊) |
| bnep_session kthread | 全 cycle で alive | NOT FOUND が 1 件でも → 実験前提崩壊 |
| bnep netdev | 全 cycle で present | MISSING が 1 件でも → 実験前提崩壊 |
| xfrm state/policy | 全 cycle で counts >0 | 0 → VPN teardown 既発生 (実験前提崩壊) |
| s3-soak.log SLEEP/WAKE | 30/30 ペア | 不一致 → hang |

**判定**:
- **1+ hang / 30** → **H2 確定 (に近い)**。upstream patch 素材として 200520 32 cycle clean + 今回 N/30 hang ログを揃える
- **0 / 30 clean** → H4 を示唆 (確率 4% で bound)。次セッションで S3'-orig (bluetoothctl disconnect で ACL 含めて切る) か S2 (xfrm flush) を比較対照に走らせる

## Phase 4: Cleanup (≈3 分)

```bash
sudo systemctl stop cycle-watcher.service 2>/dev/null
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
sudo rm -f /var/log/cycle-watcher.log
```
hang 発生時は `/tmp/hang-*` を残置 (レポート添付素材として保全)。

## Phase 5: レポート作成

- ファイル名: `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_s2idle_btvpn_s3pp_traffic_off_baseline.md`
  - レポート名英語例: `s2idle_btvpn_s3pp_traffic_off_baseline` (hang 出た場合) / `s2idle_btvpn_s3pp_h4_bound` (0/30 の場合)
- 添付: 本プランファイルを `report/attachment/<file>/plan.md` にコピー
- 必須セクション: 前提・目的、環境情報、実施内容、判定 (H2 vs H4)、機序評価 (confound 含む)、副次的発見、次セッション引継ぎ
- タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (LLM 推測禁止)
- Discord 通知は PostToolUse hook で自動

## Critical Files

**新規作成 (実機)**:
- `/usr/lib/systemd/system-sleep/58-snapshot-only` (Phase 1 投入 → Phase 4 削除)
- transient unit `cycle-watcher.service` (`systemctl stop` で消える)

**残置 (前セッションから利用)**:
- `/usr/lib/systemd/system-sleep/{50-kbd-backlight,60-s3-soak-log,70-h4-probe}`
- `/usr/local/bin/h4-mode`, `/var/lib/h4-probe/mode` (beta のまま、切替不要)

**参照 (read-only、確証根拠)**:
- `src/linux-6.12.y/net/bluetooth/bnep/core.c:501-563,673-695` (bnep_session non-freezable kthread, async teardown)
- `src/linux-6.12.y/drivers/bluetooth/btusb.c:1977-1981, 4272-4293` (btusb_suspend, autosuspend ゲート, no-timeout URB drain)
- `src/linux-6.12.y/drivers/usb/core/urb.c:713` (`wait_event(usb_kill_urb_queue, ...)` timeout 無し)

## 検証 (Verification)

1. **Phase 1 syntax**: `sudo bash -n /usr/lib/systemd/system-sleep/58-snapshot-only` で OK
2. **Phase 2 cycle 1 wake 後**: `journalctl -t 58-snapshot-only -b -n 20` で:
   - pre 発火 4 行 (delta + bnep_session alive + bnep netdev present + xfrm counts) を確認
   - bnep delta が想定範囲 (rx/tx <10KB / 500ms window、IKE keepalive 程度) で「軽 traffic」条件成立を確認
   - 1 つでも WARN が出たら実験前提崩壊 → cycle 駆動中止して原因調査
3. **Phase 2 完走後**:
   - boot_id 不変 + suspend_stats success +30 → no hang (= H4 寄り、0/30 clean)
   - boot_id 変化 1+ 件 → hang 発生 (= H2 強支持)
4. **判定 → 次手**:
   - 1+ hang → 次セッションで upstream patch 提案準備 (200520 32/32 clean + 今回 N/30 hang の対比ログ + bnep_session non-freezable コード引用を揃える)
   - 0/30 clean → 次セッションで S3'-orig (bluetoothctl disconnect で ACL 含めて切る) or S2 (xfrm flush) で比較対照

## 当初引継ぎ案からの変更点 (advisor confirmed)

| 項目 | 当初 S3' | 新 S3'' (本プラン) |
|---|---|---|
| pre フックの作用 | nmcli con down で bnep を teardown (`bluetoothctl disconnect` 抜き) | 何も teardown しない、snapshot のみ |
| traffic 状態 | heavy traffic 走行 | 軽 traffic (063543 baseline と整合) |
| bnep_session kthread | teardown → 消失 | **維持** |
| bnep netdev | teardown → 消失 | **維持** |
| in-flight bulk URB | netdev 消失で 0 | **heavy 量はゼロ (ping flood なし)、IKE keepalive 等の軽 traffic に対応する微小な in-flight 残あり** |
| H2/H4 分離力 | **不可能** (両方 0 hang 予測) | **可能** (1+ hang → H2、0 clean → H4 寄り) |
