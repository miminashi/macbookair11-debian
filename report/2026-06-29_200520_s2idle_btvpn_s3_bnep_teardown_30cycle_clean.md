# S3 (bnep 明示 teardown pre フック) 30 cycle 手動 lid close = 32/32 clean

- **実施日時**: 2026 年 6 月 29 日 19:04 〜 20:05 (JST)
- **位置づけ**: [2026-06-29_064608 セッション 2](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) からの引継ぎ「S2/S3 → S4」のうち **S3 (bnep teardown)** を先行実施。前々セッション (S1 = btusb pre-unload で 22/22 clean) で「btusb_suspend が hang 経路上」を確認済の状態で、本セッションは「bnep を suspend 前に明示 teardown すれば hang が消える?」を 30 cycle で検証した。

## 結論 (先に要約)

1. **手動 lid close 32 cycle 全 clean** (boot_id 不変 `fcc3d4b0...`、suspend_stats success 125 → 157 = **+32**、fail=0)、PM suspend entry/exit ペア **32/32 完備**、57-bnep-down hook 発火 **32 回**、s3-soak.log SLEEP/WAKE ペア **32/32**、h4-probe pre/post snapshot **32/32 ペア**。
2. **bnep netdev removal latency は全 32 cycle で `1*0.1s`** (= bounded poll 第 1 回目で消失検知) = **bnep teardown は極めて速い** (`bluetoothctl disconnect` 直後に kthread が `unregister_netdev` を完走している)。原プラン S3 節の `sleep 1` で十分間に合っていた可能性が高い。
3. **判定**: 過去 lid close + stock kernel の hang baseline = 3/31 ≒ 10% に対し **0/32 clean** = `0.90^32 ≒ 3.4%` → **ほぼ確定ライン**。「**H2 (non-freezable bnep_session kthread が dpm_suspend 段に in-flight) もしくは teardown timing (bluetoothctl disconnect での btusb traffic quiesce)** のいずれか」が hang の必要条件成分。両者の分離は **本実験では不可能** (confound 注記、判定 1)。
4. **重要な副次的発見**:
   - **(A) h4-mode alpha のスクリプトコメント (`pre フックで rtcwake -s 60`) は誤り**: 実装は `/var/lib/h4-probe/mode` を書くだけで、pre フック内で rtcwake を呼ぶ仕組みは存在しない。本セッション開始時、プランは「h4-mode alpha = RTC 60s safety net」と書いていたが、**実際には RTC alarm は機能しなかった** (cycle 1 で 13 分間 wake せず後述)。
   - **(B) 手動 lid close 経路では lid open による wake が機能しない**: cycle 1 (19:05:12 entry) は 70 秒後にユーザが蓋を開けても画面消灯のまま、最終的に **電源ボタン短押し** で 19:17:59 wake (= 767 秒間 s2idle)。これは [s2idle 観測フェーズ メモリ] の旧結論「lid wake は s2idle で構造的に不可能 (lid 通知が EC GPE 相乗りで s2idle 中マスク、宣言 wake-GPE gpe70 は発火せず)」が **正しかった** 強い証拠。064608 の「現状 LID0 *enabled で動作」は driver path 文脈の話で manual lid close には適用されないと訂正。
   - **(C) cycle 2-32 は「電源ボタン短押し wake」プロトコル**: lid open 諦め、電源ボタンで wake。asleep_s 分布は 8s 〜 184s (1 outlier cycle 1 の 767s 除く)、中央値 ~36s・平均 ~46s = ユーザのテンポで決まる。
5. **次セッション分岐**: 0/32 clean を受け、(i) 因果分離実験 S3' (`bluetoothctl disconnect` 抜きで bnep のみ NM con down)、(ii) S2 (xfrm flush) を追加検証で「H2 vs xfrm 残留」分離、(iii) upstream patch 提案準備 (bnep_session を freezable 化)、の 3 択。本レポート末尾「次セッション引継ぎ」節で詳細。

## 添付ファイル

- [実装プラン (本セッションで承認・実施したもの)](attachment/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean/plan.md)
- [PM suspend entry/exit 全 32 ペア](attachment/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean/pm-suspend-pairs.txt)
- [57-bnep-down hook 全発火ログ (32 回)](attachment/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean/57-bnep-down.log)
- [s3-soak.log 実験区間抜粋 (SLEEP/WAKE 32 ペア + asleep_s)](attachment/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean/s3-soak-excerpt.log)

## 通読版: 経緯と本セッションの位置づけ

(本レポート単体で全体像が掴めるよう散文でまとめる。細かい事実・数値・コマンドは後続の構造化セクションを参照。)

### 何のためにやっているか

MacBook Air 11" (Early 2015) は古いハードウェアながらユーザの日常用ノート PC として常用しており、**suspend (蓋閉じスリープ) が信頼できないと作業状態を喪失する** という具体的な痛みがある。蓋を閉じて持ち歩いた後に開いたら hang していて、電源ボタン長押しでの強制電源断しか手段がなく、開いていたアプリや編集中のファイルが失われる、という事故が過去複数回発生している (バッテリ残量は十分ある状態での hang)。本プロジェクトの大目的は「**この hang を恒久的に消す**」こと。

### ここまで何をやってきたか

当初は待機電力を下げたい目的で `mem_sleep=deep` (S3) を採用していたが、week あたり 1 件弱のペースで hang が発生し、battery 駆動時の特殊条件 (= btusb 完全除去でも再現する内在不具合) で **S3 deep そのものの恒久不具合** と判明、2026-06-27 に **s2idle へロールバック** した。ところが s2idle でも残り続ける hang があることが、フック残置に伴う「s2idle と思っていたが実態は deep だった」状態の発見と修正の後で確定し、「**真の s2idle + AC 給電 + BT-PAN テザリング + VPN (strongSwan/IPsec/IKEv2) + 蓋閉じ**」の 4 因子が揃ったときに限って起きる、という特異な再現条件が 2026-06-28 に切り分けられた (単独要素は全てクリーン)。

そこから上流カーネル (Linux 6.12.94 / Debian 固有パッチ無し) のソースを精読し、hang の位置 = `dpm_suspend` 段 (DPM_WATCHDOG 未有効・コンソール suspend 済で無音永久化)、機序候補 = **H1** (xfrm の dev ref leak)、**H2** (non-freezable な bnep_session kthread が in-flight)、**H4** (btusb の URB drain の永久 wait) の 3 つを立てた。H1 は「動いていれば必ず出るはずの `unregister_netdevice: waiting` printk が journald に 30 日不在」で確度が大きく下がり、残るのは H2 と H4 だった。

H4 か非 H4 かを切り分ける最初の実験 (**S1 = suspend 前に `modprobe -r btusb` で btusb を物理除去**) は 22/22 cycle clean で、「btusb_suspend が hang 経路上にある」ことを実証した。ただしこれは「btusb の suspend handler のどこか (drain でも他の同期呼び出しでも) が hang に絡む」までしか言えず、真因の絞り込みには至らなかった。続けて (**driver path で heavy traffic を流したまま `systemctl suspend` する**) という free test を回したところ、構造的な理由で 25 cycle のうち真に heavy traffic 中だったのは 2 cycle だけだったが、その 2 cycle はどちらも clean で、「**手動 lid close 経路が hang の必要条件**」が再追補強された。

### 本セッションで何をやって何が分かったか

機序仮説 H2 を狙い撃ちで検証するため、suspend 直前に **`nmcli con down` + `bluetoothctl disconnect` + bnep netdev 消滅確認 (bounded poll)** を実行する pre フックを投入し、その状態で **手動 lid close を 30 cycle 以上** 繰り返してもらった。stock 状態の hang 率が約 10% (3/31) なので、30 cycle 全クリアなら `0.90^30 ≒ 4%` でほぼ確定的に「この介入で hang が消える」と言える、という設計。

結果は **32/32 cycle 全 clean** で目標を達成した。boot_id は起動以来不変、suspend_stats も全 cycle で正常成功、PM suspend entry/exit ペア完備、フックの動作も全 cycle で問題なしだった。**bnep teardown 自体は 100ms 以内に完了** することが分かり、これは事前の理論予想 (kthread の async 性で teardown 遅延の可能性) より遥かに速かった。

ただし結果の解釈には注意がある。`bluetoothctl disconnect` は **bnep_session kthread の終了** と **btusb traffic の停止** (`hci_conn_count → 0`) を同時に起こすため、0/32 clean は「H2 が真因だった」と「H4 系の URB drain race が単に traffic が消えて発生しなくなっただけ」のどちらの解釈でも整合する。**本実験はこの 2 つを分離できていない**。それでも仮説の数自体は減り (H1 否定、H4 単独説否定)、**真因は「H2」か「H4 + bnep/traffic との相互作用」のいずれか**、というところまで絞り込めた。

### 副次的にわかった機序とは別軸の重要事実

cycle 1 でユーザが蓋を開けても画面が点灯せず、結局 13 分後に電源ボタン短押しでようやく wake した。これは旧メモリにあった「**s2idle 下では lid open による wake は構造的に不可能** (lid 通知が EC GPE 相乗りで s2idle 中マスク)」という結論が正しかったことを実証している (前セッションでは「現状は lid wake 動作」と書いたが、それは driver path の文脈で誤認していた)。あわせて `/usr/local/bin/h4-mode` のスクリプトコメントが実装と乖離している (alpha モードでも実際には rtcwake は呼ばれない) ことも判明した。**次以降の手動 lid close 実験は wake 手段として電源ボタン短押しを公式手順とする** 必要がある。

### 現在の運用状態と次にやること

実機は本セッション終了時点で開始時の状態へ完全に巻き戻し済 (フック削除、NM 設定 revert、h4-mode beta、transient unit 全停止)、起動以来 boot_id 不変で稼働中。**suspend モードは s2idle 恒久** (GRUB cmdline で固定)。BT-PAN + VPN + 蓋閉じ の hang リスクは stock 状態では未解消なので、ユーザには当該条件で蓋を閉じる前に手動で VPN もしくは BT-PAN を切る運用を暫定で推奨している。

次セッションは **「H2 真因か、H4 系 traffic 量との相互作用か」を分離する実験 (S3')** を最優先で実施する。本セッションの hook から `bluetoothctl disconnect` を抜き、`nmcli con down` だけで BNEP セッションを切る形式を試す。狙いは「BNEP は切るが btusb の ACL link は維持され bulk URB が流れ続ける」状態を作ること。0 hang なら H2 確定、1+ hang なら H4 寄りと機序が一意に決まる見込みだが、`nmcli con down` だけで BNEP プロトコル層切断が動くかは未検証 (BlueZ では珍しい状態) で、動かない場合は別経路で BNEP のみ切る方法を要調査。H2 確定なら upstream patch 提案 (bnep_session の freezable 化、もしくは bnep への PM_SUSPEND_PREPARE notifier 追加) の準備に進む。詳細は本レポート末尾「次セッション引継ぎ」節 (i) を参照。

## 前提・目的

- **背景**: [2026-06-29_064608](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) で driver path + heavy traffic でも 2/2 clean → 「lid close 経路が hang の必要条件」(141226 結論) を追補強。引継ぎは「S2/S3 → S4」順。
- **目的の絞り込み**: 直近セッション中で advisor レビュー時点での機序仮説整理は以下のとおり:
  - **H1 (xfrm dev ref leak)**: journald に `unregister_netdevice: waiting` 過去 30 日 0 件 → **判別子 negative**、確度低
  - **H2 (non-freezable bnep_session kthread + xfrm GC system_wq が dpm_suspend 段に in-flight)**: race 供給源として妥当 → 確度中、**本セッションで検証**
  - H4 (btusb URB drain 永久 wait): S1 22/22 clean で経路上を確認済、共通経路で wedge 前提
  - pre-freeze `hci_suspend_notifier` 経路: in-window 候補として未排除
- **設計**: 元プラン (064608 添付 plan.md の S3 節) に対し、**今回の事前精読 (bnep/core.c, xfrm_state.c)** で次の修正を入れて実施:
  1. `bnep_del_connection` は async (terminate flag + wake のみで return) → 実 `unregister_netdev` は kthread 文脈で遅延 → 元プランの `sleep 1` を **netdev 消滅まで bounded poll (最大 5s)** に置換
  2. `bluetoothctl disconnect` に **iPad MAC `34:42:62:16:03:F6` を明示** (引数なしの不確定性回避)
  3. **smoke test 廃止** (副作用で BT-PAN+VPN teardown → 30 cycle 用に再 up が必要、064608 で実証済の構造的問題)。代わりに cycle 1 wake 後に hook log で動作確認
  4. **判定の confound 注記**: `bluetoothctl disconnect` は `hci_conn_count→0` で btusb traffic も quiesce → 0/30 clean は「H2 確定」と「teardown timing 修正」を厳密分離できない
- **役割分担**: hook デプロイ・cycle カウント支援・状態確認は Claude が ssh で実施。NM GUI 操作 (BT-PAN/GSNet up) と **物理 lid close/wake** はユーザ手動。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、LID0 `*enabled`
- system-sleep フック (実験中): `50-kbd-backlight`、**`57-bnep-down`** (今回新規、Phase 4 で削除)、`60-s3-soak-log`、`70-h4-probe` の **4 個**。実験前後では 3 個
- 電源: **全実験 AC 給電** (`ADP1/online=1, cap=87% 終始一定`)
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer は iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)
- BT-PAN netdev: `enx98e0d98d205e` (BT MAC 由来)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`、xfrm interface `nm-xfrm-1565296`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.0/24`)。実験中は route-metric -1 → 800 に下げて VPN を BT-PAN 経由に強制、終了後 auto に revert
- traffic generator: `ping -i 0.05 -s 1400 -O 10.0.0.1` (VPN 越し) と `ping -i 0.05 -s 1400 -O 172.20.10.1` (BT-PAN 直接) を transient unit `traffic-gen.service` で並行実行
- baseline (実験開始時): boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変、uptime 1d 41m)、suspend_stats success=125 fail=0、h4-mode=beta、autoconnect 両方 no
- dev 機 (akdx01): 何も書き換えなし、`src/linux-6.12.y` (upstream tag v6.12.94 git clone) と `src/debian-6.12.94-1` のメタデータ 残置

## 実施内容と結果

### Phase 0: 一時設定 (19:04 〜)

実機 ssh で実行:
```bash
nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
nmcli con modify GSNet connection.autoconnect yes
nmcli con modify OpenWrt ipv4.route-metric 800
nmcli con up OpenWrt
/usr/local/bin/h4-mode alpha
```

ユーザ操作 (iPad テザリング ON → BT-PAN up → GSNet up) 完了後、ssh で確認:
- `ip xfrm state` で `src 172.20.10.13 dst 160.16.210.47` (VPN endpoint = BT-PAN 経由) ✓
- `ip route get 10.0.0.1` → `dev nm-xfrm-1565296 src 192.168.83.1` (VPN tunnel 経由) ✓
- BT-PAN metric 750 < WiFi metric 800 ✓
- `ping -c 2 10.0.0.1` で VPN tunnel 越し reply 確認 (RTT 148ms) ✓

### Phase 1: traffic-gen + 57-bnep-down hook 投入 (19:04 〜 19:05)

**traffic-gen 起動** (ping ベース transient unit):
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

起動後 5 秒間の BT-PAN delta: rx 278KB/5s, tx 286KB/5s = **55KB/s 双方向の bulk URB in-flight 確認**。

**57-bnep-down hook 投入** (`/usr/lib/systemd/system-sleep/57-bnep-down`, 755):
```sh
#!/bin/sh
# S3 (bnep 明示 teardown pre フック)
# bnep_session は non-freezable kthread + bnep_del_connection が async
# (atomic_inc(&s->terminate) + wake のみ) のため、sleep 1 では unregister_netdev が
# device-suspend 段に重なる可能性。netdev 消滅まで bounded poll (最大 5s)。
# 本機固有: BT MAC 98:E0:D9:8D:20:5E → enx98e0d98d205e、iPad MAC 34:42:62:16:03:F6
case "$1" in
  pre)
    nmcli -t -f UUID,TYPE con show --active 2>/dev/null | awk -F: '$2=="bluetooth"{print $1}' | \
      xargs -r -n1 nmcli con down 2>&1 | logger -t 57-bnep-down
    bluetoothctl disconnect 34:42:62:16:03:F6 2>&1 | logger -t 57-bnep-down
    for i in $(seq 1 50); do
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

`bash -n` で syntax 確認 OK。実 suspend は cycle 1 を smoke test 兼用。

### Phase 2: 30 cycle 手動 lid close 駆動 (19:05 〜 20:01)

ユーザに **「蓋閉じ → 30-60秒待機 → 蓋開け or 電源ボタン短押しで wake」** を 30 回繰り返し依頼。Claude 側で `cycle-watcher` transient unit を起動し、`/var/log/cycle-watcher.log` に suspend_stats success 増加を 2 秒間隔で監視。

#### cycle 1 (19:05:10 close → 19:17:59 wake, asleep 767s) — 重要観察

- 19:05:10 logind `Lid closed. Suspending...` → 19:05:12 PM suspend entry
- 19:05:12 57-bnep-down 発火: `Disconnection successful` + `bnep netdev removed after 1*0.1s` ✓
- 推定 19:06:20 頃 (~70秒後) ユーザが蓋開けるも画面消灯 → 待機継続
- 19:17:59 ユーザが **電源ボタン短押し** で wake、PM suspend exit + Lid opened (logind 同タイムスタンプ)
- **asleep_s=767 (= 約 13 分)、RTC alarm が機能しなかった**
- → h4-mode alpha のコメント (RTC 60s safety net) が誤りであることが判明。s2idle 中、明示的 rtcwake を呼ばない限り wake source は (a) lid open or (b) USB wakeup (キーボード/トラックパッド `1-5 wakeup=enabled`) or (c) **電源ボタン** のみ。本機の手動 lid close 経路では (a) が機能しないと実証

#### cycle 2-32 (19:20:55 〜 20:01:42)

プロトコル変更: lid open 諦め、**電源ボタン短押し** で wake する形に切替。各 cycle:
- ユーザ: 蓋を閉じる → 30-60 秒待機 → 電源ボタン短押し
- 全 cycle で 57-bnep-down が pre 発火、`bnep netdev removed after 1*0.1s` を記録

#### 全 32 cycle 統計

| 指標 | 期待 (clean) | 実測 | 評価 |
|---|---|---|---|
| boot_id | 不変 (`fcc3d4b0...`) | ✓ 不変 | clean |
| suspend_stats success delta | +30 以上 | **+32** (125→157) | clean |
| suspend_stats fail | 0 | **0** | clean |
| PM entry/exit ペア | 30/30 以上 | **32/32** | clean |
| 57-bnep-down 発火 | 30 回以上 | **32 回** | clean |
| bnep removal latency | ≤10*0.1s | **全 32 cycle で 1*0.1s** | 極めて速い |
| s3-soak.log SLEEP/WAKE | 30/30 | **32/32** | clean |
| h4-probe pre/post | 30/30 | **32/32** | clean (post 揃 = no mid-hang) |
| TIMEOUT (bnep removal) | 0 | **0** | clean |
| asleep_s 分布 | - | 8s 〜 184s (cycle 1 のみ 767s outlier) | n/a |

#### asleep_s 分布 (cycle 1 outlier 除く 31 cycle)

s3-soak.log から抽出:
- 8s, 12s, 15s, 19s, 21s, 23s, 24s, 24s, 25s, 27s, 29s, 30s, 31s, 34s, 34s, 36s, 37s, 38s, 38s, 39s, 40s, 40s, 58s, 63s, 66s, 72s, 74s, 81s, 86s, 120s, 184s (= 31 値)
- **中央値 36s (16番目)、平均 46s (合計 1428s ÷ 31)**。ユーザの「閉じる → 待つ → 電源ボタン」のテンポで決まり、kernel 側の suspend/resume 自体は短時間 (device-suspend 段は通常 400-500ms 程度) で完走している

### Phase 3: 結果集計 (20:01 〜 20:05)

(上記「全 32 cycle 統計」の通り)

### Phase 4: Cleanup (20:05)

```bash
sudo systemctl stop traffic-gen.service cycle-watcher.service
sudo rm /usr/lib/systemd/system-sleep/57-bnep-down
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
sudo /usr/local/bin/h4-mode beta
sudo rm -f /tmp/ping-vpn.log /tmp/ping-bt.log /var/log/cycle-watcher.log
```

クリーンアップ後の実機状態: hooks 3 個 (50-kbd-backlight, 60-s3-soak-log, 70-h4-probe)、NM autoconnect 両方 no、route-metric -1、h4-mode=beta、transient units 両方 inactive、snapshot count pre=96 (= 64 + 32)、suspend_stats=157/0、boot_id 不変。**前セッション開始時の状態へ完全に巻き戻し**。

## 機序評価

### 確定的な観察

1. **「BT-PAN + VPN active で suspend」状態において bnep を pre で teardown すれば s2idle suspend は安定して通る** (32/32 clean、p ≒ 3.4%)
2. **bnep teardown は速い**: `nmcli con down + bluetoothctl disconnect` 直後 100ms 以内に `enx98e0d98d205e` netdev が消失 (全 cycle で `1*0.1s` だった) → 元プランの `sleep 1` でも device-suspend 段に teardown が重なるリスクは事実上無い (今回は bounded poll で念のため確認しただけ)
3. **これまでの結論「lid close 経路が hang の必要条件」(141226 + 064608) と整合**: 本実験は lid close + active BT-PAN+VPN + 全 cycle で hook が pre teardown を実行 = 「lid close 経路 + bnep teardown 介入」の交差点で 0/32 clean を達成

### confound (本実験で分離できなかった原因)

**`bluetoothctl disconnect 34:42:62:16:03:F6` は以下 2 つを同時に実行する**:
- **(a) bnep_session kthread 終了**: BNEP プロトコルレベルの DISCONNECT 送信 → kthread `bnep_session` が `core.c:547 unregister_netdev` で終了 (= H2 検証対象)
- **(b) btusb traffic quiesce**: ACL link 切断 → `hci_conn_count→0` → btusb の bulk URB 流入停止

よって 0/32 clean は **「(a) H2 (non-freezable bnep_session kthread が dpm_suspend 段に in-flight) が原因」と「(b) btusb in-flight URB の race が消失したから」のいずれかが効いた** ことを支持するが、**両者の分離は本実験では不可能**。

### 否定された / 弱められた仮説

- **H1 (xfrm dev ref leak → `netdev_wait_allrefs`)**: 074509 で立てた判別子 (`unregister_netdevice: waiting`) は実機 journald に過去 30 日 0 件で本セッション開始時も再確認 → **構造上 H1 が動作していない** (動作していれば必ず printk が出る `pr_emerg`)。本実験で S2 (xfrm flush) ではなく S3 を先行した理由
- **「lid close 経路で hang する根本機序が単に device-suspend 段に btusb_suspend が in-flight URB を待ち続けるだけ (H4 単体)」**: S3 で消えた以上、btusb_suspend 単独の問題ではなく、**bnep もしくは btusb traffic (どちらかは未確定) との相互作用** が必要条件

### H2 単体を残すか、それ以外を残すか

仮に **(a) H2 の機序を仮定** すると一貫したストーリー: 
1. BT-PAN active 中は `bnep_session` kthread が走り続け (non-freezable, `try_to_freeze` 不在)
2. lid close → logind suspend → freeze stage → freezer は kthread を素通し
3. dpm_suspend 段で device callback が走る間に、`bnep_session` が `unregister_netdev` 中の RCU/dst 経路に絡む
4. btusb suspend の URB drain と相互作用 → wedge → no-timeout `wait_event` で permanent hang
5. S3 で kthread を pre で確実に終了 → step 3 が消失 → 0 hang

仮に **(b) 「単に bulk URB が pre で減っただけ」を仮定** しても 0 hang は説明可能 (btusb_suspend の `usb_kill_anchored_urbs` が drain する URB 数が 0 になれば wait は即時 return)。だがこれだと「BT-PAN 単独 25/25 clean」「VPN-over-WiFi 11/11 clean」(063543) の非対称性が説明不能 (BT-PAN 単独でも bulk URB は流れているので drain race は同じはず) → (b) 単独では弱い

→ **H2 (の発展形): 非 freezable bnep_session が、xfrm のソフトウェア bundle (BT-PAN netdev を握る) と組み合わさって特異な race を作る** が現状最も整合的な仮説。ただし本実験で確定したわけではない (上記 confound)

## 観測上の副次的発見

### A. h4-mode alpha のスクリプトコメントは誤り、RTC alarm は機能していない

`/usr/local/bin/h4-mode` の冒頭コメント:
```
# - alpha: pre フックで rtcwake -s 60 (RTC wake で起こす = α テスト)
# - beta:  pre フックで rtcwake -s 300 (safety net、5 分以内に lid open で起こす = β テスト)
```

しかし実装は `/var/lib/h4-probe/mode` に文字列を書くだけで、**pre フック内で rtcwake を呼ぶ仕組みは存在しない**。`70-h4-probe` 内でも rtcwake は呼ばれない。

- 064608 では「mode=alpha (60s 自動 RTC wake)」と書いていたが、これは **driver path (`cycle-driver` loop で `rtcwake -m no -s 60` を明示的に呼んでいた)** 文脈の話で、mode 自体が rtcwake を設定しているわけではない
- 本セッションは「h4-mode alpha = RTC 60s safety net」と誤認したまま開始 → cycle 1 で 13 分間 wake せず初めて発覚
- **次セッション以降**: 手動 lid close で RTC safety net を入れたい場合は **suspend 前に明示的に `rtcwake -m no -s N` を呼ぶ** か、`70-h4-probe` の pre 内で `rtcwake -m no -s N` を追加するか、別途 hook を投入する必要あり
- h4-mode のコメントを実装に合わせて修正するか、コメント通り rtcwake を pre で呼ぶ実装を追加するかは要検討 (本セッション範囲外)

### B. 手動 lid close 経路では lid open による wake が機能しない (旧結論が正しかった)

- cycle 1 で 70 秒待機後にユーザが蓋を開けても画面消灯のまま → 結局 13 分後に電源ボタンで wake
- これは [s2idle 観測フェーズ メモリ] の旧結論「lid wake は s2idle で構造的に不可能=lid 通知が EC GPE 相乗りで s2idle 中マスク、宣言 wake-GPE gpe70 は発火せず」(2026-06-18 (c) 決着) と一致
- 064608 の line 12-13 で「現状は LID0 *enabled で s2idle 下でも lid open による wake が動作」と書いたが、これは **driver path (systemctl suspend → rtcwake で wake)** の文脈で「lid 自体の wake」を試したわけではなかった、と再認識
- **141226 表 (β) で『lid open → LID0 GPE → resume』が動作前提として記述されている**との 064608 の主張も再点検が必要 (本セッションのデータは反証)
- 含意: 手動 lid close → wake のためには **電源ボタン or キーボード/トラックパッド USB wakeup** に頼る必要あり。BT-PAN+VPN hang の実使用シナリオ「蓋閉じて鞄に入れて 1 時間後に開ける」は、**そもそも本機 s2idle 下では蓋開けで wake しないのが正しい挙動** だった可能性

### C. 4 cycle で iPad 側から先に切断 (`HCI reason 3 = Remote User Terminated`)

- **4 cycle** (cycle 5, 11, 18, 27 = 19:26:28, 19:32:37, 19:41:05, 19:52:57 entry) の hook 出力に下記 3 行が記録:
  ```
  hci0 34:42:62:16:03:F6 type BR/EDR disconnected with reason 3
  [CHG] Device 34:42:62:16:03:F6 Connected: no
  Disconnection successful
  ```
  これは bluetoothctl disconnect の実行中に観測された (= `Attempting to disconnect` 行の直後に出現)。**HCI Disconnect reason 3 = "Remote User Terminated Connection"** = iPad 側が DISCONNECT を発出した
- iPad が能動的に切ったタイミングの解釈: hook の流れは `nmcli con down <bluetooth UUID>` → `bluetoothctl disconnect <iPad MAC>` の 2 段階。**`nmcli con down` の段階で BlueZ D-Bus 経由 BNEP DISCONNECT が iPad に到達 → iPad が応答として ACL DISCONNECT を発出 → bluetoothctl が実行に入ったタイミングで reason 3 を観測**、という流れと推定 (= bluetoothctl 自身のコマンドではなく nmcli の副作用が先行している cycle)
- 残り 28 cycle は `nmcli con down` の伝搬より bluetoothctl disconnect が先に成立 (= ローカル発出 DISCONNECT として正常完了、reason 行は記録なし)
- これは BlueZ プロトコル上の正常挙動。本実験の判定 (0/32 clean) に影響なし、ただし「reason 3 が出た 4 cycle では bluetoothctl disconnect 実行時点で既に btusb traffic は 0 だった」可能性 = teardown timing の効き方が他の 28 cycle と微妙に違うのみ
- 各 cycle 後の BT-PAN/VPN 再 up は NM autoconnect=yes で動作 (`Phase 1` の ping log を Phase 4 で削除済のため厳密な再確立時間は再現不可だが、cycle 駆動継続できた事実から ~5-10 秒程度で復活していたと推定)。**手動 lid close + autoconnect=yes の組合せは 30 cycle 級で十分回せる**

### D. bnep teardown が極めて速い (元プランの sleep 1 で十分間に合う)

- 全 32 cycle で `bnep netdev removed after 1*0.1s` = bounded poll の第 1 回目 (= 100ms 以内に消失検知)
- 想定 (前事前精読): `bnep_del_connection` は async で、`kthread` 文脈で `unregister_netdev` に時間がかかる可能性 → sleep 1 では不十分
- 実測: 100ms 以内に完了 → 元プランの `sleep 1` でも問題なかった
- 但し **netdev 名が `enx*` (USB Ethernet 風 udev rename 後) のため bnep0 直接消滅とは別の経路を観測している可能性**: `nmcli con down` で deactivate → udev rule で `enx*` が消える、というシナリオも考えられる。生 `bnep0` (rename 前) は更に短いか同等の速度で消えているはず
- 次セッションでより詳細を追うなら `ip -t link show` (timestamp 付) + `udevadm monitor` で確認可能

### E. ssh 切断は wake 直後 30+ 秒に頻発 (064608 副次的発見 C と一致)

- 本セッションでも wake 直後の WiFi re-associate で ssh 不通が頻発、`No route to host` を返す
- 短時間で復旧 (10-30 秒) するため、Phase 2 中は ssh 監視を諦め、ssh 失敗 → 30 秒待ち → 再試行で乗り切った
- `cycle-watcher` を実機側 transient unit で常駐させ、log を `/var/log/cycle-watcher.log` に書く形式 (本セッションで採用) は ssh 切断耐性として有効

### F. cycle-watcher.service パターン (本セッションで初採用、次回以降のテンプレート)

cycle 駆動が **ユーザ手動 (lid close)** のとき、進捗を ssh で確認する常套手段:

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

- suspend_stats success/fail が更新されるたびに 1 行記録 → ssh 切断耐性 (実機側で常駐)
- 「今何 cycle か」をユーザに伝えるとき、`sudo tail /var/log/cycle-watcher.log` で即答できる
- 064608 では `cycle-driver` (driver path 用) が同等の役割。**手動 cycle 用は `cycle-watcher` という別パターン** と認識すべき

### G. kernel suspend/resume 自体は短時間、asleep_s の大半は user 操作遅延

s3-soak.log の asleep_s 分布 (cycle 1 outlier 除く 31 値):
- **中央値 36s (16番目)、平均 46s (合計 1428s ÷ 31)、最小 8s、最大 184s**
- 一方、`PM: suspend of devices complete after X msecs` 行は (本セッションで個別計測しなかったが) 064608 v3 で 390-498 msec と確認済 = device-suspend 段は通常 0.4-0.5 秒で完走
- → 各 cycle の asleep_s は **「ユーザが蓋を閉じて → 電源ボタンを押すまでの体感時間」が大半** を占め、kernel 側は数秒以下で済んでいる
- 実用上の含意: 「30 cycle 駆動」のコストは **ユーザの蓋閉/wake テンポ** で決まる。kernel 性能ではない

### H. 実験中 `unregister_netdevice: waiting` は引き続き不在 (H1 negative の正の確認)

本セッション開始時の baseline で過去 30 日 0 件を確認していたが、実験中・実験後の journalctl にも当該 printk は出現せず:
```bash
sudo journalctl -k -b | grep -c "unregister_netdevice: waiting"  # → 0
```
- = 32 cycle 中の bnep teardown + wake 後の再 establishment が **どこかで `netdev_wait_allrefs` の 10 秒ループに突入していない** ことを実測で再確認
- 32 cycle × pre フックでの bnep unregister_netdev 実行 + 各 cycle wake 後の bnep 再生成 = 64 回の netdev ライフサイクル全て normal → **H1 (xfrm dev ref leak) は本機の現状の構成では構造上発生していない** ことが強化された

### I. cycle 1 の 13 分 stuck で「kernel resume イベント」を起こさなかった wake source の正体

cycle 1 (19:05:12 entry 〜 19:17:59 exit) の 767 秒間、以下の wake source は **明示的に作動した形跡なし**:
- **Lid open**: ユーザが ~70s 後に蓋を開けたが画面消灯のまま、logind の `Lid opened` イベントも 19:17:59 まで来ず (= wake と同タイムスタンプで「電源ボタン wake の副次として登録された」可能性)
- **USB wakeup (KB/Trackpad)**: `power/wakeup=enabled` だがユーザがキー操作したかは未確認。仮にキー操作したとしても kernel は wake していない
- **RTC alarm**: そもそも設定されていなかった (副次的発見 A)

最終的に wake させたのは **電源ボタン短押し** = ACPI Power Button GPE が wake source として確実に動作する経路。本機の s2idle 下では:
- **確実な wake source**: 電源ボタン短押し
- **不確実な wake source**: Lid open (kernel まで通らない可能性大)、USB KB (理論上は通るはずだが実証されず)

次セッション以降、s2idle 手動 lid close 実験で wake 用には **電源ボタン短押しを公式手順** とする (lid open に頼らない)。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 19:04:03 | Phase 0 開始 | NM 一時設定 + h4-mode alpha + cycle-watcher 起動 |
| 19:04 〜 19:05 | Phase 0 ユーザ操作 | iPad テザリング ON → BT-PAN up → GSNet (VPN) up |
| 19:05 〜 19:05:12 | Phase 1 | traffic-gen 起動 + 57-bnep-down hook 投入 + syntax check |
| 19:05:10 | cycle 1 開始 | ユーザ lid close (smoke test 兼用) |
| 19:05:12 | cycle 1 hook 発火 | 57-bnep-down pre 発火確認 |
| 19:17:59 | cycle 1 wake | 電源ボタン短押し (asleep_s=767) |
| 19:20:55 〜 20:01:42 | cycle 2-32 | 「蓋閉じ → 30-60s 待 → 電源ボタン」 31 回繰り返し |
| 20:02 〜 20:05 | Phase 3-4 | 結果集計 + cleanup |
| 20:05:20 | レポート開始 | (本ファイル作成のタイムスタンプ) |

実験全体所要時間: **約 1 時間** (Phase 0/1 ~5 分 + Phase 2 ~57 分 + Phase 3/4 ~5 分)。
ユーザ実働: cycle 1 で 13 分の遅延を除けば、cycle 2-32 を ~40 分 (1 cycle あたり ~80 秒平均) で完走。

## 検討して除外した事項

- **smoke test (実 suspend を 1 回先行実行して hook 発火確認)**: 副作用で BT-PAN+VPN がテアダウンされ、その後 30 cycle 用に再 up が必要になる構造的問題 (064608 で実証済)。代わりに **cycle 1 を smoke test 兼用** にした → 結果として cycle 1 が長時間 (767s) になったが kernel 観点では clean、hook 動作も確認できた
- **「30 cycle で打ち止め」**: ユーザ操作テンポが想定より速く、停止依頼が間に合わず 32 cycle 実施。本判定には影響なし (`0.90^32 ≒ 3.4% < 0.90^30 ≒ 4.2%` でむしろ強化)
- **強制電源断による boot_id 比較**: 全 32 cycle で短時間 wake (電源ボタン短押し or 電源ボタンが効く状態) → boot_id 不変 (起動以来) → hang なし。電源断不要
- **h4-probe pre/post snapshot の個別解析**: 32 ペア (= 64 ファイル) 取得済だが、本セッションでは hang が出なかったため個別解析の優先度低。次セッション (S3') で hang が出た場合に当該 cycle の pre snapshot を遡及解析する手順を [次セッション引継ぎ] に含める
- **BR/EDR reason 3 の 4 cycle について追加解析**: hook の `nmcli con down` が BlueZ D-Bus で iPad に DISCONNECT を送信、iPad 側が応答 DISCONNECT を返した結果 reason 3 が記録された可能性が高い (= 正常プロトコル動作)。本判定に影響なしのため深追いせず

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-06-29 20:05 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット |
| `/usr/lib/systemd/system-sleep/57-bnep-down` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 (前セッションから) | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで +32 ペア = 64 ファイル) | 本セッション 32 cycle の証拠 |
| traffic-gen.service, cycle-watcher.service | **削除済 (transient unit、stop で消える)** | heavy traffic generator / 進捗監視 |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | revert 済 (-1 = auto) | |
| `/tmp/ping-{vpn,bt}.log`, `/var/log/cycle-watcher.log` | 削除済 | |

実機の suspend_stats: success 157, fail 0 (start 125 → +32)。boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変)。

dev 機 (akdx01) 側: 何も書き換えなし。`src/linux-6.12.y`, `src/debian-6.12.94-1` は前セッションから残置。

## 再現方法 (本セッションをそのまま再演する場合)

[添付 plan.md](attachment/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean/plan.md) の通り。決定版手順の要点:

1. **一時設定** (Phase 0):
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
   sudo nmcli con modify GSNet connection.autoconnect yes
   sudo nmcli con modify OpenWrt ipv4.route-metric 800
   sudo nmcli con up OpenWrt
   sudo /usr/local/bin/h4-mode alpha
   '
   ```
2. **BT-PAN + VPN up** (ユーザ操作): iPad テザリング ON → NM GUI で BT-PAN と GSNet を up。`ip xfrm state | grep "src 172.20.10\."` で VPN endpoint 確認
3. **traffic-gen** + **57-bnep-down hook** 投入 (Phase 1、上記 Phase 1 節のコマンド参照)
4. **cycle 駆動** (Phase 2): ユーザに「蓋閉じ → 30-60秒待機 → **電源ボタン短押し** で wake」を 30 回。Claude 側で `cycle-watcher` transient unit を起動し suspend_stats 増加を監視
5. **判定** (Phase 3): boot_id 不変 + suspend_stats success +N + entry/exit ペア完備 + 57-bnep-down 発火 N 回 + bnep removal latency ≤ 10*0.1s
6. **cleanup** (Phase 4): hook 削除、autoconnect 両方 no、route-metric -1、h4-mode beta、transient unit stop

**注意**: cycle 1 を「smoke test 兼用」とする場合、初回は asleep_s が長くなる可能性 (本セッションは 767s)。これは RTC alarm が機能しない (副次的発見 A) ためで、ユーザは早めに電源ボタンで wake させて構わない。

## 次セッション引継ぎ

### 開始時に確認すべきこと

```bash
ssh miminashi@macbookair2015.lan '
echo "=== alive + mem_sleep ==="
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
echo "=== system-sleep hooks (期待: 50/60/70 の 3 個) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== h4-probe infra (期待: mode=beta) ==="
sudo cat /var/lib/h4-probe/mode
echo "snapshot count: $(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l) pre"
echo "=== NM autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
echo "=== boot_id (期待: fcc3d4b0...) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats (期待: success=157 fail=0) ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
'
```

### 推奨の次の手 (優先順位順)

#### (i) S3' = 因果分離実験: bluetoothctl disconnect 抜き

**目的**: 0/32 clean が「H2 (bnep_session kthread 関与)」と「teardown timing (btusb traffic quiesce)」のどちらか分離できなかった confound を解消。

**hook 案** `/usr/lib/systemd/system-sleep/57-bnep-down-only` (`bluetoothctl disconnect` を削除):
```sh
#!/bin/sh
case "$1" in
  pre)
    nmcli -t -f UUID,TYPE con show --active 2>/dev/null | awk -F: '$2=="bluetooth"{print $1}' | \
      xargs -r -n1 nmcli con down 2>&1 | logger -t 57-bnep-down-only
    # bluetoothctl disconnect 省略: BNEP セッションだけ teardown、ACL link は維持
    for i in $(seq 1 50); do
      if ! ip -br link show 2>/dev/null | grep -qE '^(bnep0|enx98e0d98d205e)\s'; then
        logger -t 57-bnep-down-only "bnep netdev removed after ${i}*0.1s"
        break
      fi
      sleep 0.1
    done
    [ "$i" = "50" ] && logger -t 57-bnep-down-only "TIMEOUT"
    ;;
esac
```

**実施**: 上記 hook で 30 cycle 手動 lid close。
- **0/30 clean** → BNEP teardown だけで十分 → **H2 確定** (= bnep_session の non-freezable kthread が真因) → upstream patch 提案へ
- **1+ hang** → ACL link 維持で hang 再発 → btusb traffic quiesce 側が効いていた → **H4 寄り** (URB drain race が真因)、S5 (btusb URB drain timeout patch) へ

**実用上の注意**: BNEP セッションを切ったまま ACL link を維持するのは BlueZ では珍しい状態。`nmcli con down` だけで BNEP プロトコルレベル切断が動くかは未検証 (PANU disconnect の D-Bus 経路を要調査)。動かない場合は別経路で BNEP のみ切る必要あり (`hcitool` 等)。

#### (ii) S2 (xfrm flush) 追加検証

**目的**: H1 が完全に否定されたわけではない (判別子 negative は「動いていない」の強い証拠だが、別経路の xfrm 残留関与は残る) → S2 を独立に検証して確証を上げる。

**hook**: 元プラン (064608 添付 plan.md S2 節) の `/usr/lib/systemd/system-sleep/56-xfrm-flush` (`ip xfrm state flush; ip xfrm policy flush`) を pre で実行。30 cycle 手動 lid close。

- **0/30 clean** → xfrm 残留関与あり、ただし H1 判別子 negative と矛盾 → 機序再検討
- **1+ hang** → xfrm 残留は無関係、確証強化

注: bnep/xfrm 機序精読 (本セッション前事前確認) で確認したとおり、`xfrm_state_flush` / `xfrm_policy_flush` は **cached xdst bundle (BT-PAN netdev を握る) を walk しない** ため、user-space flush では完全には software bundle を落とせない可能性が残る。S2 0/30 clean でも H1 確定にはならない (= confound あり)。

#### (iii) upstream patch 提案準備 (bnep_session を freezable 化)

**仮説 (H2) が正しい場合の修正案**: `net/bluetooth/bnep/core.c` の `bnep_session()` メインループに `try_to_freeze()` を入れる。具体的には:
- `set_freezable()` を `bnep_session` 起動直後に呼ぶ
- 各 `wait_woken()` の後 (line 539 近辺) に `try_to_freeze()` を入れる

**注意**: upstream は伝統的に「kthread はユーザ空間と異なり freeze する必要がない (kernel resource 自体は suspend を生き残る)」設計。bnep_session を freezable にする提案は通りにくい可能性が高い (LKML で reject されうる)。代わりに **「suspend 通知 (`PM_SUSPEND_PREPARE`) を bnep に追加して、suspend 前に明示的に BNEP セッションを停止する」** という上層レベルの提案の方が筋が良いかもしれない。

参考: 074509 で確認した既存 fix (bnep の `Fix UAF read of dev->name` `b21805258` 等) は bnep の race を直しているが、freeze 自体は触っていない。

**準備すべき素材**: (a) 本セッション 32 cycle clean のログ抜粋、(b) S3' 結果 (H2 vs teardown timing の分離)、(c) bnep_session の non-freezable 性質を示すコード引用 (`net/bluetooth/bnep/core.c:501-563`)。

#### (iv) S4 (DPM_WATCHDOG kernel) — 最終手段

(i)-(iii) でも機序が確定しない場合のみ。`apt-get source linux=6.12.94-1` → `.config` に `DPM_WATCHDOG=y, TIMEOUT=60, PSTORE_RAM=y` 追加 → `bindeb-pkg` → 実機 dpkg-i → grub-reboot で新 kernel 起動 → 20-30 cycle 手動 lid close → hang 時 pstore に backtrace。

**注意**: 実機に dkms コマンドが入っていない (本セッション開始時に確認) → S4 は dev 機側で deb 化必須。broadcom-sta-dkms の build 前提環境を dev 機で先に整える必要あり (linux-headers-6.12.94+dpmwd1-amd64 の作成も含む)。所要 1-2 日級。

### 推奨順

**(i) S3' → (ii) S2 → (iii) upstream patch → (iv) S4**。
- (i) は次セッション 1 回 (30 cycle) で H2 vs H4 を分離 → 一気に進む
- (ii) は (i) の結果と組み合わせて H1 の確証を上げる
- (iii) は (i)/(ii) の結果次第で素材を組み立てる
- (iv) は最終手段。前提条件 (dkms+broadcom-sta 環境) の整備に時間がかかる

## 関連レポート

- [2026-06-29_064608 セッション 2: free test 25/25 clean (heavy traffic 2/25)](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) — 直前セッション、本レポートの起点
- [2026-06-29_041006 セッション 1: S0 + S0.5 + S1 22/22 clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) — S1 (btusb pre-unload) clean
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md) — driver path 0/75 / lid path 必要条件結論
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) — driver path 0/15
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) — 機序仮説、本レポートの判定根拠
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — lid path 3/3 hang、本セッションの 0/32 clean と対比
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
