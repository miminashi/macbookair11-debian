# s2idle「BT-PAN × VPN」lid close ハングを Claude 駆動で再現する

## Context（なぜやるか）

[2026-06-28_063543 レポート](../../projects/macbookair11-debian/report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)で、**真の s2idle・AC** でも「**BT-PAN テザリングをトランスポートにした VPN(GSNet/strongSwan)**」を併用して lid close すると数回以内にハングすることを **3/3 で手動再現**した（単独要素はすべてクリーン: BT-PAN単独 25/25・VPN-over-WiFi 11/11・無線なし 9/9）。ただしこの再現は**ユーザが実機の前で手動 lid close + 物理電源断**で行ったもので、Claude は read-only 観測のみだった。

本タスクの狙いは、この相互作用ハングを **Claude が ssh 越しに driver で自動駆動して再現する**こと。これにより (1) lid close を介さず `systemctl suspend` でも同条件が再現するか（＝トリガーが lid 固有か device-suspend 段の汎用経路かを切り分け）、(2) 失敗サイクルと条件を durable ログで精密に捕捉、が得られ、次の仮説検証（btusb module unload で BT-PAN を device-suspend 経路から除去 / 残留 xfrm device の確認）の土台になる。

前回 [2026-06-28_021019](../../projects/macbookair11-debian/report/2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) は同じ driver 方式（`rtcwake -m no` でアラーム → `systemctl suspend` → 復帰後 POST、PAN を毎サイクル `nmcli con up`）で **VPN 無し** BT-PAN を 10/10 クリーンに走らせた。**新規要素は「BT-PAN 上に VPN を載せる」工程のみ**で、既存 driver をその分だけ拡張する。

## 運用形態（ユーザ確認済み・2026-06-28）

- **start-and-leave（ユーザ不在運用）**: ユーザはセットアップ直後に**外出**し、driver は detached で走り続ける。ハングしたら実機は**そのまま停止状態で放置**され、Claude は ssh 不通になる（リアルタイム観測は不可）。**ユーザが帰宅後に物理電源ボタン長押しで電源断 → 再起動 → 「続行」と伝える**。そこで Claude が durable ログを読んで**ハングを確定**し、必要ならレポート化／追加サイクルを再投入する。
- **電源状態**: **AC のみ**（proven condition = AC・素 suspend と一致）。battery/STH は別セル（後述）。
- **テザリング元 = iPhone ではなく別ホットスポット端末**: ユーザは iPhone を持ち出し、**別の BT-PAN(NAP) テザリング対応端末を実機のそばに置いて**外出する。
  - 含意1: 既存 NM 接続 `iMiminashiSE ネットワーク`(peer `CC:60:23:AF:2C:60`) は iPhone 固定。**別端末は別ペアリング＋別 NM bluetooth 接続**になり、**PAN 接続名・サブネット(IP)が変わりうる**（PAN iface 名はローカル hci0 MAC 由来＝`enx98e0d98d205e` のままの可能性が高いが、変動も想定し setup 時に実値を確定する）。→ driver はこれらを**パラメータ化**し、セットアップ時に実機で実値を検出して渡す。
  - 含意2: 代替端末は **Bluetooth PAN(NAP) テザリングに対応している必要**がある（WiFi 専用モバイルルータ等は不可）。peer 識別子は変わるが、ハング機序は MacBook 側（btusb/bnep の device-suspend × xfrm/charon）にあり peer 依存ではないため、**active な BT-PAN 上に VPN が載っていれば条件は成立**する見込み（厳密 bit 一致ではない点は留意）。

## 重要な制約

- **再現成功＝実機ハング**。停止位置は device-suspend 段（`PM: suspend exit` 欠落）で、RTC アラームでは復帰しない。**復帰には物理電源ボタン長押しの強制電源断が必須**で Claude には不可能（→ 上記 start-and-leave 運用で吸収）。
- ハング後に電源断 → 再起動すると、実機は s2idle ロールバック状態（deep 再アサートする timer/cron なし）に戻る＝**状態は durable で安全**。ログ（`/var/log/susp-test.log`, `/var/log/s3-soak.log`）も再起動後に読める。
- **VPN は必ず BT-PAN 経由**にする（端点が代替端末の PAN サブネット内 IP になる）。現状 WiFi(wlp3s0) がデフォルト経路なので、**WiFi off → BT-PAN up → VPN up** の順で張り、GW(`160.16.210.47`)への egress dev が**当該 BT-PAN iface** であることを検証する。
- **最初のハングで driver は停止**（不在中は 1 回のハングまでしか進まない）。1 回の Claude 駆動ハングで再現は確定するので十分。追加サイクルは帰宅・電源断後に再投入。
- **不在運用のリスク**: 不在中に iPad のホットスポットがスリープ／BT-PAN が落ちると、その後のサイクルは条件未成立のまま空回り（`vpnup=fail`）し、ハングせず N 回完走しうる。帰宅後に per-cycle の `panup=`/`vpnup=`/`vpn_ep=` を読んで「条件成立サイクルが実在したか」を必ず検証する（成立サイクルが 0 なら再現失敗ではなく**条件喪失**＝再投入）。iPad 側は可能なら自動ロック/スリープを抑止して外出してもらう。

## 実機の現状（本セッションで read-only 確認済 2026-06-28 06:55 JST）

- boot_id `3aa09ac0-...`、uptime ~27分、AC online=1 / BAT 87%
- `mem_sleep=[s2idle] deep`（s2idle 選択）、`LID0 *enabled`、`s3-deep-apply.service` disabled
- NM 接続: `GSNet`(vpn, GW 160.16.210.47)、`iMiminashiSE ネットワーク`(bluetooth/iPhone)、いずれも現在 inactive
- 現在の default route = `wlp3s0`(192.168.33.145)。WiFi radio = enabled
- `/usr/local/bin/susp-test-driver.sh`(v2) 残存、フック `50-kbd-backlight`・`60-s3-soak-log`（deep 強制は無効化済）
- **代替テザリング元（ユーザが本日ペアリング済・BT テザリング動作確認済）**: `iMiminashiPadPro`、peer `34:42:62:16:03:F6`、NM 接続名 **`iMiminashiPadPro ネットワーク`**(UUID `fd2a3edb-9800-4d5c-a775-d8055e7e623e`, type=bluetooth)。現在 inactive。**up 時に iface 名・PAN サブネットが確定**（iPad Personal Hotspot も既定 `172.20.10.x/28` 圏の見込みだが実値は setup 時に検出）。btusb/hci0(`98:E0:D9:8D:20:5E`) UP RUNNING、bnep ロード済。
  → driver の `PAN_CON` = `iMiminashiPadPro ネットワーク`、`PAN_IFACE` は setup 手順2で確定した実 iface を渡す。

## アプローチ

既存 `susp-test-driver.sh` (v2) を拡張した **v3 (`susp-btvpn-driver.sh`)** を新規配置して使う。v2 の `pan_up()`（毎サイクル BT-PAN を `nmcli con up` し iface に IP が付くまで待つ）に、対をなす **`vpn_up()`** を追加するだけ。検出ロジック・PRE/POST durable ログ・`rtcwake`/`systemctl suspend` 構造は v2 を踏襲する。

### v3 driver の差分（v2 からの追加点のみ）

- **Phase 開始時**: `nmcli radio wifi off`（VPN が WiFi に逃げないよう強制）。
- **`vpn_up()`**（新規、`pan_up()` と同型。GW IP と PAN iface は driver 引数で受ける）: `nmcli con up GSNet` → 最大 ~25s 待ち、
  (a) `nmcli ... con show --active` に GSNet が出る、かつ
  (b) `ip route get <GW_IP>` の egress dev が 引数の `$PAN_IFACE`
  の両方を満たしたら `ok`、その egress dev を `vpn_ep` として記録。満たさなければ `fail`（VPN が BT-PAN 経由でない＝条件未成立を検出）。
- **各 iteration の PRE 行**に `vpnup=` と `vpn_ep=`(egress dev) を追記。`pan_up()`→`vpn_up()` の順で毎サイクル張り直す（resume 後に NM が自動再接続しない前提＝v2 で BT について実証済の罠を VPN にも適用）。
- **（任意）active 通信**: VPN tunnel 越しに background ping（`systemd-run --unit=bt-vpn-ping --collect ping -i 1 <内部到達先>`）。前回 Phase B が「active 通信」を持続 ping で担保したのに倣う。なくても IKE_SA 確立で条件は満たすが、実使用に寄せるため付ける。

### 実行手順（承認後）— セットアップ〜起動はユーザが外出する前に完了させる

1. **前提状態の最終確認**（read-only）:
   ```bash
   ssh miminashi@macbookair2015.lan 'cat /sys/power/mem_sleep; grep LID0 /proc/acpi/wakeup; systemctl is-enabled s3-deep-apply.service'
   # 期待: [s2idle] / LID0 *enabled / disabled
   ```
2. **代替ホットスポット(`iMiminashiPadPro`)の BT-PAN を確立 & 実値検出**（端末は本日ペアリング済。Claude が ssh で）:
   ```bash
   # WiFi を落として BT-PAN をデフォルト経路にする → PAN を上げる → iface・IP を確定
   sudo nmcli radio wifi off
   sudo nmcli con up "iMiminashiPadPro ネットワーク"      # 要 sudo: polkit 回避
   nmcli -t -f NAME,TYPE,DEVICE con show --active | grep bluetooth   # iface を確定
   ip -4 -br addr show <iface>                                       # PAN の IP/サブネットを確定
   ```
   → ここで得た **PAN_IFACE / PAN サブネット** を driver に渡す（`PAN_CON` = `iMiminashiPadPro ネットワーク`）。
3. **v3 driver を配置**（ローカルで生成 → scp → `sudo chmod +x`。`/usr/local/bin/susp-btvpn-driver.sh`）。
4. **VPN-over-BT-PAN の単発検証**（driver 投入前に 1 回手で確認）:
   ```bash
   sudo nmcli con up GSNet
   ip route get 160.16.210.47       # egress dev が <PAN_IFACE> であること＝VPN が BT-PAN 経由
   ```
5. **検出ベースライン取得**: boot_id, `s3-soak.log` 末尾の ss_ok カウンタ, `suspend_stats success` を記録。
6. **detached transient service で起動**（ssh 切断・suspend・外出を生存させる。root 実行で polkit `nmcli` 制約も回避）。PAN 接続名/iface は手順2で確定した実値を渡す:
   ```bash
   sudo systemd-run --unit=susp-btvpn --collect \
     /usr/local/bin/susp-btvpn-driver.sh BTVPN 15 on 30 15 \
       "iMiminashiPadPro ネットワーク" "<PAN_IFACE>" GSNet 160.16.210.47
   ```
   - WAKE=30s / GAP=15s / N=15。手動再現はサイクル 0/1/6 でハング＝**数回以内**に出る見込み。
7. **起動直後の健全性確認**（外出前に Claude が見る）: `susp-test.log` の最初の ITER PRE 行で `panup=ok` / `vpnup=ok` / `vpn_ep=<PAN_IFACE>` を確認 → **条件が成立した状態で suspend が始まったこと**を担保してからユーザに「外出 OK」を伝える。
8. **不在中**: Claude はリトライループで張り付かない（不在運用）。ハングすれば ssh 不通のまま放置される。

### 帰宅・電源断後（ユーザが「続行」）

- 再起動後に確定検出: `boot_id` 変化 + `uptime` リセット + `susp-test.log` で **PRE あり/POST 無し**の最終 iteration（その PRE 行で `vpnup=ok`/`vpn_ep=<PAN_IFACE>` を確認）+ `s3-soak.log` が **SLEEP→(WAKE 無し)→BOOT** + ハング boot の journal で `deleting IKE_SA GSNet … <PAN IP>`（VPN over BT-PAN）と PAN teardown を確認。→ **Claude 駆動ハングを確定**。
- 完走（ハング 0、N 回 PRE/POST 揃う）だった場合: `PM: suspend entry/exit` 件数一致・`suspend_stats success` 増分・soak `drm_err=0` を突合し、**「systemctl suspend では N 回再現せず」**と記録。その場合 lid 固有性を疑い、**fallback: 手動 lid close での確認**（前回 063543 の手順）へ切り替えるかをユーザに諮る。
- 追加サイクルが欲しければ手順6を再投入。

### フォールバック（自動で出ない場合）

`systemctl suspend` 駆動で N 回クリーンなら、トリガーが lid-close 固有（logind 経路や LID GPE 相乗りの差）の可能性。その場合は driver を止め、VPN+BT-PAN を張った状態で**ユーザに実 lid close を反復**してもらい（前回の手動プロトコル）、自動経路との差を切り分ける。

## 検証（このタスクの成否判定）

- **成功条件**: 上記 driver 駆動で実機がハングし、`susp-test.log` の PRE/POST 欠落 + `s3-soak.log` SLEEP→BOOT + ハング boot の journal で IKE_SA が**当該 BT-PAN の PAN IP** 経由（VPN over BT-PAN）であることで「BT-PAN × VPN・s2idle・AC」条件のハングを**Claude 駆動で確定再現**できること。
- 併せて、対照として直前または別 run で **VPN を WiFi 経由に変えた同 driver が完走（クリーン）**することを 1 回示せれば、相互作用条件への局在を Claude 駆動でも追認できる（任意・時間が許せば）。

## 触らないもの / 後始末

- `mem_sleep` / `LID0` / `60-s3-soak-log` フックは**変更しない**（s2idle ロールバック状態を維持）。実験終了後、WiFi radio を on に戻し、`bt-vpn-ping` / `susp-btvpn` unit を停止。driver は残置可。
- レポート: CLAUDE.md ルールに従い `report/` 直下に作成（`TZ=Asia/Tokyo date` でタイムスタンプ、063543 の続編としてリンク、添付に `susp-test.log`・`s3-soak.log` 実験窓・v3 driver を格納）。プランファイルも添付。

## 関連レポート

- [2026-06-28_063543 手動 factorial 切り分け（本件の親）](../../projects/macbookair11-debian/report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-28_021019 driver 方式・VPN 無し BT-PAN 10/10 クリーン](../../projects/macbookair11-debian/report/2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モード計4ハング・s2idle ロールバック決定](../../projects/macbookair11-debian/report/2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
