# S3 (bnep 明示 teardown pre フック) 30 cycle 手動 lid close 検証

## Context

**前セッション**: [report/2026-06-29_064608](/home/miminashi/projects/macbookair11-debian/report/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) で driver path + heavy traffic でも 2/2 clean → 「lid close 経路が hang の必要条件」(141226 結論) を追補強。引継ぎは「**S2/S3 → S4**」順。

**実機現状** (本セッション開始時 ssh 確認、引継ぎ表と完全一致):
- mem_sleep=s2idle、boot_id `fcc3d4b0...` (1日41分稼働中、起動以来不変)、suspend_stats=125/0
- system-sleep hooks: 50-kbd-backlight, 60-s3-soak-log, 70-h4-probe の 3 個
- NM autoconnect 両方 no、route-metric -1、transient units 両方 inactive
- **`unregister_netdevice: waiting` カウント 0 件** (journald, 2026-06-01 以降) → **H1 判別子 negative 再確認**
- **実機に dkms コマンド無し** (`bash: dkms: コマンドが見つかりません`) → S4 で実機 autoinstall 不可、dev機で deb 化が必須
- mok キー (`/var/lib/dkms/mok.{key,pub}`) は存在

**機序仮説 (再掲)**:
- H1 (xfrm dev ref leak): journald 判別子 negative → **確度低**
- **H2 (non-freezable bnep_session kthread + xfrm GC system_wq)**: race 供給源として妥当 → **確度中** (←今回検証)
- H4 (btusb URB drain 永久 wait): S1 22/22 clean で経路上を確認済、共通経路で wedge 前提
- pre-freeze `hci_suspend_notifier` 経路: in-window 候補として未排除

**lid wake 機序の前提** (重要、記憶訂正済): 064608 line 12-13 で訂正済の通り、メモリ `s2idle-observation-phase.md` の旧結論「lid wake は s2idle で構造的に不可能」は 2026-06-18 S3 deep 評価期の文脈で、LID0 を `/proc/acpi/wakeup` で凍結していた状態の話。**現状は `LID0 *enabled` で s2idle 下でも lid open による wake が動作**する (141226 で 60 cycle 全 wake 成功)。本プランはこの「現状」を前提とする。

**目的**: S3 で「bnep_session の async teardown が device-suspend 段に重なる」可能性を pre フックで遮断し、0/30 clean なら **H2 もしくは teardown timing のいずれか** を支持。1+ hang なら S2 → S4 へ進む。

**判定強度と confound**:
- 過去 lid close + stock kernel の hang baseline = 3/31 ≒ **10%**。0/30 clean の達成確率 = `0.90^30 ≒ 4%` → ほぼ確定ライン
- **ただし confound あり** (bnep/xfrm 機序精読で確定): `bluetoothctl disconnect` は `hci_conn_count→0` で btusb traffic も quiesce する → 0/30 clean は「(a) H2 (bnep_session non-freezable kthread が in-flight) が原因」と「(b) btusb traffic 抑制で URB drain race が消失」を厳密分離できない。判定では「H2 もしくは teardown timing のいずれか」と書く必要あり。原因を絞り込みたい場合は別セッションで `bluetoothctl disconnect` を抜いた S3' を 30 cycle 追加で必要

## アプローチ

### Phase 0: 一時設定 (≈5 分)

実機 ssh で:
- `nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes`
- `nmcli con modify GSNet connection.autoconnect yes`
- `nmcli con modify OpenWrt ipv4.route-metric 800` + `nmcli con up OpenWrt` (VPN を BT-PAN 経由に強制)
- `/usr/local/bin/h4-mode alpha` (RTC 60s safety net)
- boot_id 記録、`suspend_stats` baseline 記録

ユーザ操作:
- iPad テザリング ON
- NM GUI で BT-PAN (`iMiminashiPadPro ネットワーク`) up
- NM GUI で GSNet up

確認 (ssh):
- `ip xfrm state | grep "src 172.20.10\."` で VPN outer IP が BT-PAN IP
- `ip route get 10.0.0.1` で `dev nm-xfrm-N src 192.168.83.1` (VPN tunnel 経由)
- BT-PAN metric < WiFi metric

### Phase 1: traffic generator + S3 フック投入 (≈10 分)

**traffic-gen** (ping ベース、前セッション v3 と同じ):
```bash
sudo systemd-run --unit=traffic-gen --collect bash -c '
while true; do
  ping -i 0.05 -s 1400 -O 10.0.0.1 > /tmp/ping-vpn.log 2>&1 &
  P1=$!
  ping -i 0.05 -s 1400 -O 172.20.10.1 > /tmp/ping-bt.log 2>&1 &
  P2=$!
  wait $P1 $P2 2>/dev/null
  sleep 1
done
'
```

**S3 フック** `/usr/lib/systemd/system-sleep/57-bnep-down` (実行権限 755):
```sh
#!/bin/sh
# Pre-suspend: 明示的に BT 接続を down → bnep_session kthread を確実に終了させる
# bnep_del_connection は async (terminate flag + wake) のため、netdev 消滅まで bounded poll
case "$1" in
  pre)
    nmcli -t -f UUID,TYPE con show --active 2>/dev/null | awk -F: '$2=="bluetooth"{print $1}' | \
      xargs -r -n1 nmcli con down 2>&1 | logger -t 57-bnep-down
    # iPad MAC を明示 (引数なしの bluetoothctl disconnect は複数 device 接続時に不確定)
    bluetoothctl disconnect 34:42:62:16:03:F6 2>&1 | logger -t 57-bnep-down
    for i in $(seq 1 50); do
      # 本機固有のデバイス名 (BT MAC 98:E0:D9:8D:20:5E 由来) を hardcode
      if ! ip -br link show 2>/dev/null | grep -qE '^(bnep0|enx98e0d98d205e)\s'; then
        logger -t 57-bnep-down "bnep netdev removed after ${i}*0.1s"
        break
      fi
      sleep 0.1
    done
    [ "$i" = "50" ] && logger -t 57-bnep-down "TIMEOUT waiting for bnep removal"
    ;;
esac
```

**設計上の注意** (今回の精読で確定):
- 元プラン (S3 節) の `sleep 1` を **bounded poll (最大 5s)** に置換。理由: `bnep_session` は non-freezable kthread で `bnep_del_connection` は `atomic_inc(&s->terminate)` + wake のみで return → 実 `unregister_netdev` は kthread 文脈で遅延実行 → `sleep 1` では device-suspend 段に teardown が重なるリスクが残る (= H2 を検証できない)
- `bluetoothctl disconnect` は iPad MAC `34:42:62:16:03:F6` を明示 (引数なしの場合の不確定性回避)
- ハードコードされたデバイス名 (`enx98e0d98d205e`) は本機固有 (BT MAC 由来)、他機種に転用時は要修正

**syntax check のみ** (実 suspend は行わない、smoke test 廃止の理由は下記):
- `sudo bash -n /usr/lib/systemd/system-sleep/57-bnep-down` で構文確認
- 実 suspend での hook 発火確認は **30 cycle の cycle 1 を smoke test 兼用** にする (= cycle 1 wake 後に `journalctl -t 57-bnep-down` で pre 発火 + bounded poll exit を確認、TIMEOUT 出なければ OK)

**smoke test 廃止の理由**: 実 suspend を 1 cycle 走らせると hook が BT-PAN/VPN をテアダウンし、その後 (BT-PAN renaming + IKE peer-dead で) 30 cycle 用の再 up が必要になる (064608 で実証済の構造的問題)。30 cycle 中の cycle 1 wake で hook 動作確認すれば smoke test の目的は果たせる

### Phase 2: 30 cycle 手動 lid close 駆動 (≈50 分)

**プロトコル** (1 cycle = ~70-90s):

1. **ユーザ**: 蓋を閉じる (BT-PAN+VPN active 状態で)
2. 60-70 秒待機 (h4-mode alpha の 60s RTC alarm が safety net として動作、lid open でも wake 可)
3. **ユーザ**: 蓋を開ける → 画面点灯 / キー押下で wake 確認
4. wake 確認後 5-10 秒以内に次 cycle へ (画面が点灯したら次 cycle 用に再閉)
5. 30 回繰り返し

**ユーザの cycle カウント支援** (進捗確認の手段):
- ssh で別端末に下記を流すと、suspend_stats success が +1 する度に echo → ユーザはこれで「何 cycle 走った」を確認できる:
  ```bash
  ssh miminashi@macbookair2015.lan '
  prev=$(cat /sys/power/suspend_stats/success)
  base=$prev
  while true; do
    cur=$(cat /sys/power/suspend_stats/success)
    if [ "$cur" != "$prev" ]; then
      echo "$(date +%H:%M:%S) cycle $((cur-base)) (success=$cur, fail=$(cat /sys/power/suspend_stats/fail), boot_id=$(cat /proc/sys/kernel/random/boot_id | cut -c1-8))"
      prev=$cur
    fi
    sleep 5
  done
  '
  ```

**hang 検出と evidence preservation**:
- ssh 切断 + 30 秒以上画面反応せず → ユーザにキー連打 wake 試行 (064608 H 項) → 反応無ければ **boot_id 変化を覚悟して強制電源断 (電源ボタン長押し)**
- 電源復旧後 ssh で **必ず以下を取得** (Phase 4 cleanup 前に保全):
  - `cat /proc/sys/kernel/random/boot_id` で boot_id 変化確認
  - `journalctl -b -1 -k | grep -E "(PM: suspend|57-bnep-down|kbd-backlight)" > /tmp/hang-evidence-$(date +%s).txt`
  - `sudo ls /sys/fs/pstore/ > /tmp/hang-pstore-$(date +%s).txt` (efi_pstore 残存確認)
  - `sudo tail -200 /var/log/s3-soak.log > /tmp/hang-soak-$(date +%s).txt`
  - `sudo cp -r /var/log/h4-probe /tmp/hang-h4probe-$(date +%s)/` (hang 直前の pre snapshot 保全)
- hang 発生 → 当該 cycle 番号と上記 evidence を記録 → ユーザと協議して continue/abort 判断

### Phase 3: 結果集計 (≈5 分)

- `cat /proc/sys/kernel/random/boot_id` → `fcc3d4b0...` から不変か
- `cat /sys/power/suspend_stats/{success,fail}` → success が +30
- `journalctl -k -b | grep -c "PM: suspend entry"` および `"PM: suspend exit"` → どちらも 30 ペア
- `sudo journalctl -t 57-bnep-down` → pre が 30 回発火、`bnep netdev removed after Ns` の N 分布、`TIMEOUT` 件数
- `/var/log/s3-soak.log` の SLEEP/WAKE ペア 30/30

**判定** (confound 明記):
- **0 hang / 30** → 「**H2 (bnep_session 非 freezable kthread が dpm_suspend 段に重なる)** または **teardown timing (bluetoothctl disconnect での btusb traffic quiesce)** のいずれかが効いた」と結論。両者の分離は本実験では不可能 (上記 confound 節参照)。次セッションで分離実験 (S3': bluetoothctl disconnect 抜きで bnep のみ teardown) を提案
- **1+ hang / 30** → bnep teardown では不十分 → S2 (xfrm flush pre フック、56-xfrm-flush) を投入し再 30 cycle、または直接 S4 (DPM_WATCHDOG kernel) へ
- **2-5 hang のグレーゾーン** (= baseline 10% より低いが完全 clean でない) → 確率的不在証明不能 → S4 へ進み backtrace 取得

### Phase 4: Cleanup (≈3 分、ただし hang 発生時は evidence 保全後)

**hang 発生時**: 必ず Phase 2 の evidence preservation (boot_id, journalctl, pstore, s3-soak.log, h4-probe snapshot コピー) を **完了してから** 以下を実行する。`/tmp/hang-*` 群は scp で dev 機に持ち帰り、レポート添付に使う。

```bash
sudo rm /usr/lib/systemd/system-sleep/57-bnep-down
sudo systemctl stop traffic-gen.service 2>/dev/null
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
sudo /usr/local/bin/h4-mode beta
sudo rm -f /tmp/ping-vpn.log /tmp/ping-bt.log
# /tmp/hang-* は残置 (レポート添付素材として保全)
```

### Phase 5: レポート作成

- `report/yyyy-mm-dd_HHMMSS_s2idle_btvpn_s3_bnep_teardown_30cycle.md`
- 添付: 本プランファイルを `report/attachment/<file>/plan.md` にコピー
- 必須セクション: 前提・目的、環境情報、実施内容、判定、機序評価 (confound 含む)、副次的発見、次セッション引継ぎ
- タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得

## Critical Files

**新規作成** (実機):
- `/usr/lib/systemd/system-sleep/57-bnep-down` (S3 hook、Phase 1 で投入 → Phase 4 で削除)
- transient unit `traffic-gen.service` (systemd-run、stop で消える)

**残置** (前セッションから、本実験で利用):
- `/usr/lib/systemd/system-sleep/70-h4-probe` (各 cycle pre/post snapshot)
- `/usr/lib/systemd/system-sleep/60-s3-soak-log` (SLEEP/WAKE durable log)
- `/usr/local/bin/h4-mode`, `/var/lib/h4-probe/mode` (mode=alpha に切替)

**参照** (read-only、確証根拠):
- `src/linux-6.12.y/net/bluetooth/bnep/core.c:501-563,673-695` (bnep_session non-freezable + async teardown)
- `src/linux-6.12.y/net/core/dev.c:10792-10850` (`netdev_wait_allrefs` の `unregister_netdevice: waiting` pr_emerg)
- `src/linux-6.12.y/net/xfrm/xfrm_state.c:858-895`, `xfrm_policy.c:1809-1845` (state/policy flush の限界)

## 検証 (Verification)

1. **Phase 2 cycle 1 wake 後** に `journalctl -t 57-bnep-down -b` で hook が pre 発火 + `bnep netdev removed after Ns` を確認 (= smoke test 兼用)。TIMEOUT 出るなら hook 機能不全 → cycle 駆動中止して原因調査
2. **Phase 2 cycle 終了後** boot_id 不変 = no hang
3. **suspend_stats success delta = 30** = 全 cycle が kernel 観点で完了
4. **journald PM entry/exit ペア = 30/30** = silent hang なし
5. **57-bnep-down log で `bnep netdev removed after Ns` 分布** → N が小さい (≤10 = 1秒以内) なら bnep teardown は十分速い、N=50 (TIMEOUT 5s) なら teardown 遅延が深刻 → S3 の前提条件が崩れ判定に注意
6. **s3-soak.log SLEEP/WAKE ペア = 30/30** = h4-probe 観点でも完走

判定後、結果に応じて次セッションを (a) 0/30 → S3' (bluetoothctl disconnect 抜き、H2 vs teardown timing 分離) → upstream patch 提案 (b) 1+ hang → S2 or S4 セッション へ進める。
