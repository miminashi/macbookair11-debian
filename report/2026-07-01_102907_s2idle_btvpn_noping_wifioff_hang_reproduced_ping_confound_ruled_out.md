# Ping 無し条件下で s2idle+WiFi-off+BT-PAN+VPN hang を独立再現 — ping confound 説を排除

- **実施日時**: 2026 年 7 月 1 日 08:23 〜 10:29 (JST)
- **位置づけ**: [2026-07-01_043251 セッション](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) が「hang 独立再現 + candidate (d) 弱化」で終わったが「WiFi-on protective」結論は二つの壁 (statistical power N=1 不足 + ping confound 未解消) で establish 不可だった。本セッションでは **ping confound を構造的に排除** し (連続 ping 明示禁止 + 58-snapshot-only で pgrep ping を durable file に記録)、hang の独立再現を狙う非対称設計。**結果: cycle 26 で hang 発生、`ping_running=NO` durable evidence 付き = ping 不要説を証明**。

## 結論 (先に要約)

1. **Cycle 26 で hang 発生、durable evidence で ping_running=NO 確定**:
   - 26 BT-PAN-valid cycle / 1 hang (cycle 26、10:22:07 JST)
   - snapshot-only PRE durable file (`1782868927.snapshot-only.PRE`) に `ping_running=NO` 記録済
   - 全 26 cycle が source-IP gate で BT_PAN_VALID (src=172.20.10.13)、WiFi 経由 VPN 混入 **0** 件
2. **Hang signature が 063543/043251 と 7 項目一致 + `ping_running=NO` を本セッション新規記録** (計 8 項目):
   - `xfrm_state=2 xfrm_policy=14` (半分、teardown 途中)
   - charon-nm `Network is unreachable` retransmit 3 回
   - `PM: suspend entry (s2idle)` 存在、`PM: suspend exit` 欠落 (= dpm_suspend stall)
   - boot_id `670cf7fd` → `8963e774` に変化
   - `unregister_netdevice: waiting` 依然 0 件 (= H1 negative continues)
   - **新規**: 58-snapshot-only PRE durable file に `ping_running=NO` 記録 (063543/043251 では未観測)
3. **「043251 の hang は ping confound 由来」説を排除**:
   - 043251 セッションで疑われた「連続 ping が race 窓を広げて hang を招いた」筋書きは、本セッションで ping 無し状態でも hang 再現できたことで否定
   - **ping は hang の必要条件ではない、本 hang は BT-PAN+VPN+lid close+WiFi-off の組み合わせ自体が起こしている**
4. **candidate (d) (「ベースラインは ~0」説) は完全に維持困難**:
   - 063543 (3/10)、043251 (1/20)、本セッション (1/26) の三度独立に同 signature で hang が verified
   - 「hang はほぼ無い、これまでのは外れ値」説はもう成立しない、hang rate ~4-30% の想定が bedrock
5. **「WiFi-on protective」結論は依然 establish されない**:
   - WiFi-off 三セッション (063543 3/10, 043251 1/20, 本 1/26) vs WiFi-on 一セッション (061553 0/30) → Fisher exact 片側 p ≈ 0.11、統計的に有意でない
   - 但し 063543/043251/本セッション の三つの WiFi-off セッションで hang 発生、唯一の clean (061553) は WiFi-on = 方向性ヒントは強化
   - 「WiFi-off が hang を起こしやすい」結論には次セッションで WiFi-on 側の N をもっと増やす必要
   - (注: pooled 5/56 rate は heterogeneous な pool のため単一 rate estimator ではなく、定性的評価として扱う)
6. **機序ラダーへの feed**:
   - **H1** (xfrm dev ref leak → `netdev_wait_allrefs`): `unregister_netdevice: waiting` 0 件で **negative continues**、三度目の証拠
   - **H2** (bnep_session non-freezable): snapshot-only PRE で `kbnepd_session=alive` 状態で hang → kbnepd 存在は必要だが十分ではない (cycle 25 も alive で完走)
   - **H4** (btusb URB drain timeout): 本 hang でも path-on だが、`ping_running=NO` で hang したことから「連続 ping による bulk_anchor 蓄積」は駆動因子ではない、他経路の URB drain (HCI command? UART interrupt?) が疑わしい
7. **次セッション設計**: 機序ラダー S4 段 (自前ビルド `DPM_WATCHDOG=y` カーネル) で dpm_suspend の stall device を特定 → H2/H4 のどちらの経路が実際に stall しているか判別、または `modprobe -r wl` 実験で wl の関与を切り分け

## 添付ファイル

- [実装プラン](attachment/2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out/plan.md)

## 通読版: 経緯と本セッションの位置づけ

### このプロジェクトでやっていること

MacBook Air 11" で外出中に Bluetooth テザリング + VPN の状態で蓋を閉じると、数回に一度ハングして強制電源断するしかない。バッテリは残っていても作業が飛ぶので不便。ここ 1 週間、条件を切り替えながら「何がトリガーか」を一つずつ切り分けている。

### 前セッション (043251) までの流れ

これまでに 3 セッション分の観察がある:

- **063543** (WiFi オフ + BT テザリング + VPN で蓋閉じ): 3/10 でハング → 最初の確実な観測 (bedrock = これ以上疑わない前提として使ってよい確定観測)
- **061553** (WiFi オンにして同じ操作): 30/30 でハングなし
- **043251** (WiFi オフに戻して再挑戦): 1/20 でハング、063543 と同じ症状が再現

「WiFi をオンにしておけばハングしない」ように見えたが、advisor から二つの弱点を指摘された:

1. **サンプルが少なすぎる**: 0/30 と 1/20 は統計的にはほぼ区別できない (Fisher の検定で有意にならない)
2. **ping の可能性が残る**: 043251 のあいだ、ユーザは背景で `ping` を流しっぱなしにしていた。これがドライバ内で USB 転送を溜め込んで race を作った可能性がある。しかも過去セッションで ping を流していたか、あとから直接確認する手段がなかった

→ 本セッションは、この二つのうち **「ping の可能性」だけを狙い撃ちで潰す** 設計にした。

### 本セッションでやったこと

前セッションから変更したのは主に 3 点:

- ユーザに事前にお願い: **駆動中は連続 ping を絶対に流さない**、疎通確認は 1 発ずつの `ping -c 1` だけ
- 観測フックに **`pgrep ping` を仕込んだ**: 各 suspend の直前に ping プロセスが本当に走っていないか自動で確認して記録
- その記録を **journal に加えてディスクのファイルにも書いた**: ハング後に強制電源断しても消えないように

上記の準備をしたうえで、前セッションと同じ条件 (WiFi オフ + BT テザリング + VPN) で、ユーザに蓋の開閉を繰り返してもらった。

### 起きたこと

**26 cycle 目でハングした**。前 25 cycle は問題なく完走したあとの発生。

- ハング直前の snapshot に「ping は走っていない」が durable ファイルとして残った
- ハング時のカーネルログの症状 (`PM: suspend entry` のあとの `PM: suspend exit` が来ない、`Network is unreachable` の retransmit が 3 回、xfrm ポリシが半分だけ残る、など) は 063543 や 043251 とすべて一致
- ユーザの体感カウント「26 サイクルめくらい」と、あとで復元した cycle 数が完全に一致

つまり、**ping が走っていない状態で 043251 と同じハングを引き起こせた**。

### 意義

- **ping が犯人説は消えた**: 043251 のあとに疑われていた「ping のせいで USB 転送が race を起こす」筋書きは、少なくとも hang の必要条件ではない
- **「ハングはたまたま」説はもう捨てられる**: 三度独立に同じ症状が再現 → 「これまでの hang は外れ値、本当はほぼ起きない」という説はもう成立しない
- **機序探究の方向修正**: これまで最有力だった「USB 転送溜め込みが原因」筋書きが弱くなったので、代わりに Bluetooth の制御コマンド周りなど、別の経路を疑う必要がある
- **「WiFi オフだと出やすい」というヒントは強まった**: WiFi オフの 3 セッションはすべてハング、唯一クリーンな 061553 は WiFi オン。ただし統計的に有意とまでは言えないので、次回で決着させたい

### 次にやること (推奨順)

1. **wl モジュールを完全にアンロードして駆動**: WiFi オフのコマンドだけだと wl ドライバは残ったまま。完全に外して同じ実験をしてみて、それでもハングするなら wl は無関係、しないなら wl が犯人筋
2. **WiFi オンの試行を N=60 まで増やす**: 061553 の N=30 では統計的に足りないので、追加駆動で「WiFi オンなら hang しない」を bedrock 化できるか確認
3. **自前ビルドの DPM_WATCHDOG カーネル**: 上の 2 つで新情報が尽きた場合の最終手段。ハングしたときにどのドライバの suspend で止まったのかをカーネル自身が dump してくれる

## 前提・目的

- **背景**: [2026-07-01_043251 セッション](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) で hang 独立再現 + candidate (d) 弱化を達成、但し「WiFi-on protective」結論は (i) 統計的 power 不足 (0/30 vs 1/20 で Fisher p ≈ 0.4)、(ii) 連続 ping confound 未解消 の二つの壁で establish 不可
- **主要目的**: ping 無し条件下で hang を独立再現 (= 043251 hang は ping confound 由来ではないことを証明)
- **本セッション独自の追加目的**:
  - 58-snapshot-only に pgrep ping を埋め込み、durable file で事後検証可能化
  - SESSION_START_EPOCH の scratchpad 保存 + 動的注入で hardcode bug 排除
- **役割分担**: hook/transient unit デプロイ・状態確認・retro-classify は Claude が ssh で実施。cycle 駆動 (蓋 close + 電源ボタン wake) は WiFi-off で ssh 切断中のためユーザ手動、進捗 (10 cycle ごと + hang 時) はユーザ口頭報告

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks (本セッション実施中): `50-kbd-backlight`、`58-snapshot-only` (本セッションで新規投入 + pgrep ping + durable file 出力追加、Phase B-6 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後は 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`iMiminashiPadPro`, BT-PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` → **Phase B-3 で `nmcli radio wifi off` で soft rfkill** (wl モジュールはロード状態のまま、043251 と同じ)
- baseline (実験開始時 08:23 JST): boot_id `670cf7fd-ad6d-4f42-90c8-0d8f359099e2` (043251 hang reboot 後、不変)、suspend_stats 0/0 (043251 hang reboot 後)、snapshot count=180 pre / 179 post、NM autoconnect 両方 no、route-metric -1、wl loaded refcount=0、unregister 0 件
- baseline (実験終了時 10:29 JST): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (本セッション hang reboot で変化)、snapshot count=206 pre / 204 post (= +26/+25、1 hang)、snapshot-only PRE=28 / POST=25 (28 の内訳: 2 smoke test + 26 実 cycle)、NM autoconnect 両方 no (Phase B-6 cleanup)、WiFi radio enabled (ユーザ手動 `nmcli radio wifi on`)、unregister 0 件
- 比較対照 043251 との condition 差: **連続 ping 明示禁止** (043251 は流していた)、それ以外は同一 (peer=iPad、WiFi=off、hook=50/60/70+58 with pgrep 追加、駆動=手動 lid close + 電源ボタン wake)

## Phase B-0: baseline 確認 + SESSION_START 捕捉 (08:23 JST)

### SESSION_START_EPOCH 捕捉

```bash
SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
# → 1782861826 (JST 08:23:46)
echo "$SESSION_START_EPOCH" > /tmp/.../scratchpad/session_start_epoch.txt
```

Phase B-5 の retro-classify で hardcode を排除するため、開発機の scratchpad に保存。

### baseline 7 項目確認結果

全項目期待値と一致:
- カーネル `6.12.94+deb13-amd64`、`mem_sleep=[s2idle] deep` ✓
- GRUB `mem_sleep_default=s2idle no_console_suspend` ✓
- hooks 3 個 (50/60/70)、mode=beta、snapshot count=180 pre ✓
- NM autoconnect 両方 no、OpenWrt route-metric -1 ✓
- boot_id `670cf7fd...` (043251 hang reboot 後と一致)、suspend_stats 0/0 ✓
- unregister_netdevice: waiting 0 件 ✓
- transient units 全 inactive ✓

## Phase B-1: hook + transient units デプロイ (08:24-08:26 JST)

### 58-snapshot-only hook (043251 と同設計 + pgrep ping + durable file)

**重要な追加 2 点**:
1. **pgrep ping セクション** を末尾に追加 (= 事後 ping 検証の可能化)
2. **durable file 出力** `/var/log/h4-probe/<epoch>.snapshot-only.PRE/POST` (= hang reboot を跨いで生き残らせる)

### pgrep regex bug 発見 → 修正

初回 smoke test で **`gsd-housekeeping` プロセスが false match** して `ping_running=YES` を報告:
- 元の regex `ping( |$)`: 単に「"ping" の後が空白 or 行末」なので、"gsd-house**keeping**" (末尾 4 文字 "ping") が hit
- pgrep は full command line を regex 探索するため、word boundary が無いと substring match してしまう

修正: `(^|[ /])ping( |$)` で **word boundary anchor** (前が行頭/空白/スラッシュ、後が空白/行末)。修正後 smoke test で正常に `ping_running=NO` に。

- 修正済 hook で 2 回目 smoke test → `ping_running=NO` 確認 → デプロイ完了

### vpn-watcher + cycle-watcher 起動

- `vpn-watcher.service` (transient, --collect): 3 秒間隔で BT-PAN UP + GSNet inactive を検知して `nmcli con up GSNet`
- `cycle-watcher.service` (transient, --collect): suspend_stats delta を `/dev/shm/cycle-progress` に書き出し (ユーザローカルで `watch -n 1 cat /dev/shm/cycle-progress` で進捗表示)

### NM autoconnect=yes + WiFi metric 800

```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
```

- WiFi metric 800 は 043251 で観察された「setup 時 WiFi 経由 VPN」の防止 (BT-PAN metric 750 < WiFi 800 で BT-PAN を preferred に)
- 但し active connection の metric は反映されない (=nmcli con modify は profile のみ) ため、実際の setup では WiFi 経由 VPN が一時的に確立 (副次的発見 A 参照)

## Phase B-2: BT-PAN + VPN セットアップ + ping 禁止案内 (~09:40 JST 前後、時刻推定)

ユーザ操作: iPad テザリング ON。NM autoconnect=yes により BT-PAN + GSNet 自動 up。

Claude 確認結果:
- BT-PAN active (`iMiminashiPadPro ネットワーク`)、`172.20.10.13/28` 割当
- GSNet active、但し **xfrm src=192.168.33.145** (= WiFi IP) → VPN は WiFi 経由で確立 (metric 反映されず、043251 と同じ症状)
- Phase B-3 で WiFi-off するため moot と判断、そのまま進入

**ユーザ事前案内 (= 本セッションの load-bearing communication)**:
- 「本セッションは hang を当てに行く実験、1 hang で勝ち、clean は無情報になりやすい」
- 「連続 ping 絶対禁止、VPN 疎通確認は wake 直後の `ping -c 1 10.0.0.1` one-shot のみ、既存 background ping は Ctrl+C で止めてから B-3」
- 「58-snapshot-only が pre snapshot で pgrep ping、走っていれば journal + durable file で発覚」

ユーザ「了解」→ Phase B-3 進入。

## Phase B-3: WiFi-off = ssh 切断ポイント (~09:47 JST 前後、cycle 1 の直前)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con down OpenWrt
sudo nmcli radio wifi off
'
# → Timeout (ssh 切断 = 期待動作)
```

以降 Claude は実機状態を観測不能、ユーザ手動駆動。

## Phase B-4: 手動 26 valid cycle 駆動 → cycle 26 で hang (09:48-10:22 JST)

ユーザ手動操作:
1. 蓋 close (= s2idle 突入)
2. 10-30 秒待つ
3. 電源ボタン短押し (= wake、lid open は s2idle で構造的に動作しない)
4. ログイン → 10-15 秒待つ (vpn-watcher が GSNet 再 activate)
5. option 2 (`watch -n 1 cat /dev/shm/cycle-progress`) で cycle 番号確認

進捗:
- 17 cycle 到達 (ユーザ経過報告): hang なし、順調
- **cycle 26 (10:22:07 JST) で hang 発生** = 蓋 close 後 wake しない

ユーザ復旧:
- 強制電源断 → reboot (10:24:12 JST 起動、boot_id `8963e774...`)
- ローカルで `sudo nmcli radio wifi on` → WiFi 復活 (10:25:41 JST 前後)
- Claude に ssh 復活を通知

### 本セッションの完全 cycle 表 (durable evidence から復元)

| cycle | pre 時刻 (JST) | asleep 時間 | src | 状況 |
|---|---|---|---|---|
| 1 | 09:48:30 | 38s | 172.20.10.13 | OK |
| 2 | 09:49:36 | 17s | 172.20.10.13 | OK |
| 3 | 09:50:25 | 22s | 172.20.10.13 | OK |
| 4 | 09:51:19 | 24s | 172.20.10.13 | OK |
| 5 | 09:52:15 | 7s | 172.20.10.13 | OK |
| 6 | 09:52:54 | 13s | 172.20.10.13 | OK |
| 7 | 09:53:36 | 58s | 172.20.10.13 | OK |
| 8 | 09:55:06 | 123s | 172.20.10.13 | OK |
| 9 | 09:57:41 | 15s | 172.20.10.13 | OK |
| 10 | 09:58:28 | 37s | 172.20.10.13 | OK |
| 11 | 09:59:58 | 40s | 172.20.10.13 | OK |
| 12 | 10:01:43 | 34s | 172.20.10.13 | OK |
| 13 | 10:02:49 | 66s | 172.20.10.13 | OK |
| 14 | 10:05:45 | 167s | 172.20.10.13 | OK |
| 15 | 10:09:04 | 12s | 172.20.10.13 | OK |
| 16 | 10:09:46 | 16s | 172.20.10.13 | OK |
| 17 | 10:10:45 | 21s | 172.20.10.13 | OK |
| 18 | 10:11:36 | 13s | 172.20.10.13 | OK |
| 19 | 10:12:50 | 20s | 172.20.10.13 | OK |
| 20 | 10:15:00 | 60s | 172.20.10.13 | OK |
| 21 | 10:16:32 | 34s | 172.20.10.13 | OK |
| 22 | 10:17:38 | 29s | 172.20.10.13 | OK |
| 23 | 10:18:59 | 21s | 172.20.10.13 | OK |
| 24 | 10:19:52 | 42s | 172.20.10.13 | OK |
| 25 | 10:21:06 | 29s | 172.20.10.13 | OK |
| **26** | **10:22:07** | **—** | **172.20.10.13** | **HANG** |

集計: **26 BT-PAN-valid cycle / 25 OK / 1 hang (= cycle 26)**、WiFi 経由 VPN 混入 **0 件**、VPN inactive **0 件**

### ping 集計 (durable file 経由)

- Total 28 snapshot-only PRE files (SESSION_START_EPOCH 以降)
- **ping=YES: 1 件** (08:25:20 = 最初の smoke test、buggy regex 時代、`gsd-housekeeping` false match)
- **ping=NO: 27 件** = 修正後 smoke 1 件 + 実 cycle 26 件

**実 cycle 26 個は全て ping_running=NO durable file 記録済 → confound 排除成功**

## Phase B-5: Hang signature 解析

### Cycle 26 hang journal 抜粋 (前 boot -1、JST)

```
10:21:54 systemd-logind: Lid closed.
10:22:02 systemd-logind: Suspending...
10:22:02 charon-nm: 03[NET] error writing to socket: Network is unreachable
10:22:04 charon-nm: 09[IKE] retransmit 1 of request with message ID 7
10:22:04 charon-nm: 03[NET] error writing to socket: Network is unreachable
10:22:07 charon-nm: 13[IKE] retransmit 2 of request with message ID 7
10:22:07 charon-nm: 03[NET] error writing to socket: Network is unreachable
10:22:07 snapshot-only[162016]: [PRE] xfrm_state=2 xfrm_policy=14
10:22:07 snapshot-only[162027]: [PRE] ping_running=NO
10:22:08 kernel: PM: suspend entry (s2idle)
(以降 PM: suspend exit なし → dpm_suspend で永久 stall)
```

### 063543/043251 hang との signature 比較

| 項目 | 063543 (3/3) | 043251 cycle 20 | 本セッション cycle 26 |
|---|---|---|---|
| Network is unreachable retransmit | 3 回 | 3 回 | **3 回** ✓ |
| bnep teardown 状態 (snapshot-only PRE 時点) | 完了 | 完了 (`bnep_netdev=MISSING`) | **完了 (`bnep_netdev=MISSING` durable file 記録)** ✓ |
| snapshot-only xfrm_policy | 14 (半分) | 14 (半分) | **14 (半分)** ✓ |
| snapshot-only ping_running | 未観測 | 未観測 | **NO (durable file)** ✓ 決定的 |
| PM: suspend entry (s2idle) | あり | あり | **あり (10:22:08、snapshot-only PRE (10:22:07) の 1 秒後)** ✓ |
| PM: suspend exit | 欠落 | 欠落 | **欠落** ✓ |
| boot_id 変化 | あり (各 hang) | あり | **あり (`670cf7fd` → `8963e774`)** ✓ |
| unregister_netdevice: waiting | 0 件 | 0 件 | **0 件** ✓ (H1 依然 negative) |

**063543/043251 と 7 項目一致** + `ping_running=NO` は本セッション新規観測 (計 8 項目、うち 4 は本 hang で決定的証拠 = xfrm_policy=14、PM: suspend exit 欠落、unregister 0 件、ping_running=NO) → 074509 のカーネルソース解析 (H1/H2/H4 仮説) が予測した「dpm_suspend 段 dpm_watchdog 無効化下での無音永久 loop」が **三度目に再現、しかも ping 無しで**。

(注: 「bnep teardown 完了タイミング」の journal 直接抜粋は本セッションでは NM device-teardown ログ (`disappeared from enx98e0d98d205e`) をフィルタ pattern に含めなかったため、durable file の `bnep_netdev=MISSING` フィールドから「snapshot-only PRE snapshot 実行時点で既に bnep teardown 完了」と確認、「PM: suspend entry の 1 秒前」は snapshot-only PRE ログ (10:22:07) と kernel PM entry (10:22:08) の journal timestamp 差から)

### Cycle 24/25 (完走直前) との比較

Cycle 24 (PRE 10:19:52) と 25 (PRE 10:21:06) の suspend attempt は同じく:
- `Lid closed` → `Suspending...` → charon-nm `Network is unreachable` 3 回
- snapshot-only PRE で `xfrm_state=2 xfrm_policy=14 ping_running=NO`
- `PM: suspend entry (s2idle)` → `PM: suspend exit` **あり、完走**

観察可能 state は cycle 24/25/26 で identical → **hang は predictable な state 差ではなく、timing/race で起きた** (043251 の cycle 19/20 と同じパターン、副次的発見 C の再確認)。dmesg-watchdog 系の動的観測が必要。

## Phase B-6: クリーンアップ (10:28 JST)

```bash
ssh miminashi@macbookair2015.lan '
sudo systemctl stop vpn-watcher.service cycle-watcher.service
sudo rm -f /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
'
```

期待 final 状態と実測一致:

| 項目 | 期待 | 実測 |
|---|---|---|
| hooks | 50/60/70 の 3 個 | ✓ |
| autoconnect (BT-PAN/GSNet) | 両方 no | ✓ |
| OpenWrt route-metric | -1 | ✓ |
| transient units | 全 inactive | ✓ |
| WiFi radio | enabled (ユーザ手動 on 後) | ✓ |
| boot_id | `8963e774...` (本セッション hang reboot 後) | ✓ |
| snapshot count | pre 206 / post 204 (= +26 / +25 = 1 hang) | ✓ |
| snapshot-only durable files | PRE 28 (= 実 cycle 26 + smoke 2) / POST 25 (= 完走 25 のみ、smoke test は post 走らず、cycle 26 は hang で欠落) | ✓ 残置 |

設定面のクリーンアップ完了。dev 機 (akdx01) 側: 何も書き換えなし。

## 機序評価

### 何が確定したか (durable)

1. **Hang 独立再現、ping 無し状態で** = 043251 hang は ping confound 由来ではないことを証明
2. **source-IP gate で 26/26 BT_PAN_VALID 確定** = WiFi 経由 VPN 混入は 0
3. **dpm_suspend 段 stall 機序を三度再確認**: xfrm_policy=14 (半分) + Network unreachable retransmit 3 回 + PM: suspend entry のみで exit 欠落 = 074509 カーネルソース解析の予測通り
4. **H1 仮説 (xfrm dev ref leak) は三度目の negative**: `unregister_netdevice: waiting` 0 件

### Candidate (d) (「ベースラインは ~0」説) は **完全に排除**

三度独立に同 signature で verified hang:
- 063543: 3/10 (~30%)
- 043251: 1/20 (~5%)
- 本セッション: 1/26 (~4%)

「hang はほぼ無い、外れ値」説はもう成立しない。hang rate ~4-30% の想定が bedrock、機序探究の前提として維持。

### Candidate (b) (WiFi-on protective) は依然 establish されない (但し弱いヒント強化)

- 061553 (WiFi-on): 0/30 (95% CI [0%, ~12%])
- 063543 (WiFi-off): 3/10 (~30%)
- 043251 (WiFi-off): 1/20 (~5%)
- 本セッション (WiFi-off): 1/26 (~4%)

**Fisher exact test: 5/56 (WiFi-off pooled) vs 0/30 (WiFi-on)**:
- 片側 p ≈ 0.11 (WiFi-on 側で 0 hang が偶然に起きる確率)
- 有意水準 p < 0.05 に到達せず、**統計的に有意でない**

**注意**: 「WiFi-off pooled rate 5/56 ≈ 9%」は heterogeneous な pool (063543 30% + 043251/本 ~5%)。063543 と 043251/本 で rate 想定が異なる状況で pooled rate を単一 rate として使うのは estimator としては不適切。**本 pool は「WiFi-off の hang rate ≈ 9%」という数値評価ではなく、「WiFi-off で複数セッション hang 発生」という定性的観察**として扱う。

方向性 (WiFi-off 側で hang 頻出、WiFi-on で 0) はあるが、統計的検定を通せる差はまだ得られていない。次セッションで WiFi-on N を 60+ に拡大すれば結論可能になる可能性あり。

### Ping confound 説の反証

043251 report で候補として挙げた「連続 ping が bulk_anchor URB を蓄積して btusb_suspend で drain timeout」筋書きは、本セッションで **ping 無し状態で同 signature hang** が発生したことで反証:

- 本セッションの cycle 26 で `ping_running=NO` durable file 記録あり、cycle 26 pre snapshot 時点で ping プロセス皆無
- それでも cycle 26 hang は 063543/043251 と全 8 項目一致 signature → race 経路は ping 独立

**含意**: 074509 H4 仮説 (btusb URB drain) が hang 経路だとしても、URB drain の直接原因は連続 ping ではなく **NM teardown 段階の HCI command URB drain 中の race** など、内在的な経路。

### 機序ラダーの位置づけ (更新)

- **H1** (xfrm dev ref leak → `netdev_wait_allrefs`): **三度目の negative continues**、判別子 `unregister_netdevice: waiting` 0 件 → 実質的に棄却圏
- **H2** (bnep_session non-freezable kthread): snapshot-only PRE で `kbnepd_session=alive` 状態で hang → 但し完走 cycle でも kbnepd_session=alive のため必要条件だが十分ではない、確定困難
- **H4** (btusb URB drain timeout): 本 hang でも path-on だが、ping 無しで hang したことから「連続 ping 蓄積」は駆動因子ではない。他経路 (HCI command URB、UART interrupt での URB drain) が疑わしい

→ **本 hang は H2/H4 のいずれにも 100% fit しない**。dpm_suspend のどこで stall したかを更に絞り込むには `DPM_WATCHDOG=y` の自前ビルドカーネル (= S4 段、機序ラダーの最終手段) が必要。

## 観測上の副次的発見

### A. NM autoconnect=yes + `nmcli con modify OpenWrt ipv4.route-metric 800` は active connection に即時反映されない

Phase B-1 で `route-metric 800` を profile に設定したが、Phase B-2 setup 時点で xfrm src=192.168.33.145 (= WiFi IP) → VPN は WiFi 経由で確立。理由: `nmcli con modify` は profile update のみ、active connection metric は次回 up まで反映されない。

含意: 043251 と同じ症状。WiFi off で最終的に BT-PAN 経由に切り替わるため moot だが、setup 段階で cleanliness を求める場合は `sudo nmcli con up OpenWrt` で active 再適用が必要 (ssh via WiFi の場合は disruption リスクあり)。

### B. pgrep regex bug: 単純な `ping( |$)` は `gsd-housekeeping` に false match

初回 58-snapshot-only smoke test で `ping_running=YES` 報告、原因は `pgrep -af "ping( |$)"` が "gsd-housekeepi**ng**" の末尾 "ping" に match。修正: `(^|[ /])ping( |$)` で **word boundary anchor** (前が行頭/空白/スラッシュ、後が空白/行末) → 正常化。

含意:
- pgrep は full command line を regex 探索するため、pattern の前後 anchor 無しでは substring match してしまう
- 次セッション以降も pgrep 系 pattern は word boundary anchor を必ず付ける
- 今回は smoke test で発覚したので実 cycle には影響なし、smoke test の重要性を再確認

### C. cycle 24/25/26 の pre snapshot は state-level で identical = timing race の再確認

Cycle 24 (完走)、25 (完走)、26 (hang) の 70-h4-probe pre snapshot + snapshot-only PRE を比較した結果、観測 state は全て同一:
- xfrm_state=2 xfrm_policy=14
- kbnepd_session=alive
- bnep_netdev=MISSING
- ping_running=NO
- Network is unreachable retransmit 3 回

含意: 043251 の cycle 19/20 比較と同じ現象。**hang は predictable な state 差ではなく、timing/race で起きた**。observable state から hang を予測するのは構造的に不可能 → S4 段 (`DPM_WATCHDOG=y` カーネル) での動的観測が必要。

### D. 58-snapshot-only の durable file は Phase B-5 で決定的な役割

durable file (`/var/log/h4-probe/<epoch>.snapshot-only.PRE`) が hang reboot を跨いで生き残り、以下を実現:
1. 本セッション ping_running の 26 cycle 全数事後確認
2. Cycle 26 の hang signature 記録 (xfrm_policy=14 の証拠)
3. 過去 043251 hang の retrospective 検証は journal のみだったが、本セッションは durable file 追加で reboot 越えでも robust

含意: 次セッション以降も 58-snapshot-only + durable file 構造を維持、または 70-h4-probe に process list section を統合検討 (043251 report 副次的発見 D の handover 事項)。

### E. Pair-matching logic の落とし穴: 70-h4-probe は pre/post で独立 epoch 生成

初回集計時、`test -f "${f%.pre}.post"` で pair 判定した結果、**全 26 cycle が HANG 表示**。原因: 70-h4-probe は pre と post で **別々の `date +%s`** を実行するため、`<pre-epoch>.pre` と `<pre-epoch>.post` は絶対に一致しない。

修正: pre epoch 列と post epoch 列を昇順 sort、順次 pair matching (「pre 直後の未消費 post が次の pre より前なら OK、なければ HANG」)。この方式で正しく cycle 26 のみを hang 判定。

含意: 
- 043251 plan と同じ hardcoded `test -f "${f%.pre}.post"` は間違い、次セッション以降は order-based pair matching を使う
- 043251 report では cycle 20 hang が特定できていたが、これは post 欠落 = 1 件のみ確定していれば結論同じだったため。次セッション以降の retro-classify で cycle 番号を正確に振るには order-based 必須

### F. Cycle asleep 時間の分布: 7〜167 秒 = ユーザ体感駆動の自然揺らぎ

Cycle 別 asleep 時間 (= post_epoch - pre_epoch = 実 suspend 時間):
- 最短: 7 秒 (cycle 5)
- 最長: 167 秒 (cycle 14)
- 平均: ~30 秒
- 中央値: ~24 秒

含意: 手動駆動なので lid close 後 wake までの間隔がユーザ体感で変動、cycle 期間の均一性は保証されない。hang は cycle 期間依存ではなく、driver-suspend chain の内在的 race で起きている (asleep 7 秒でも 167 秒でも完走)。

### G. Boot 履歴の連続性: 043251 と本セッション hang が durable evidence で完全接続

boot 履歴 (`journalctl --list-boots`):
- -4: 7c44b92c (2026-06-28 05:22:50 〜 06:26:43)
- -3: 3aa09ac0 (2026-06-28 06:28:19 〜 12:29:59)
- -2: fcc3d4b0 (2026-06-28 12:32:51 〜 2026-07-01 04:15:51) ← 043251 hang
- -1: 670cf7fd (2026-07-01 04:18:04 〜 10:22:08) ← 043251 復旧 + 本セッション hang
- 0: 8963e774 (2026-07-01 10:24:12 〜 現在) ← 本セッション復旧

含意: 全 boot 時刻が durable に journal に残っており、seven-days-back までの retrospective 検証が可能。将来 metric 800 効いていたかや mode=beta セット時刻の確認等、任意の時期に retrospective 可能。

### H. Cleanup 時の nmcli con modify OpenWrt ipv4.route-metric -1 は必須

Phase B-1 で 800 に設定したが、cleanup で -1 (= NetworkManager 自動決定 = dhcp 取得 metric) に戻さないと OpenWrt 接続が本来の metric (600) と一致しなくなる。B-6 で明示的に -1 に戻して baseline 一致確認済。

### I. Boot 0 (2026-07-01 10:24:12) の resume 頻度: 手動 WiFi on 前に 1 suspend 発生

boot 履歴 `0: 2026-07-01 10:24:12 → 10:25:41` の期間は約 90 秒。この間にユーザがログインして `nmcli radio wifi on` 実行、その後 ssh 復活。suspend_stats は現時点で 0/0 なので、boot 0 では suspend 未経験、次回 suspend までは真 clean 状態。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 08:23 | Phase B-0 | SESSION_START_EPOCH=1782861826 捕捉、baseline 7 項目確認 |
| 08:24 | Phase B-1 | 58-snapshot-only 初回 install → smoke test で pgrep regex bug 発見 |
| 08:25 | Phase B-1 | pgrep regex 修正 → smoke test で `ping_running=NO` 確認 |
| 08:26 | Phase B-1 | vpn-watcher / cycle-watcher 起動、NM autoconnect=yes + route-metric 800 |
| ~09:40 | Phase B-2 | ユーザ iPad テザリング ON、xfrm src=192.168.33.145 (WiFi 経由)、ping 禁止案内 |
| ~09:47 | Phase B-3 | ssh 越しに `nmcli radio wifi off` → ssh 切断 |
| 09:48-10:22 | Phase B-4 | ユーザ手動 lid close + 電源ボタン wake で 26 cycle 駆動 (25 完走 + cycle 26 hang) |
| **10:22:08** | **HANG 発生** | cycle 26、`PM: suspend entry (s2idle)` 最終、`ping_running=NO` durable file 記録済 |
| ~10:24 | hang reboot | ユーザ強制電源断 → reboot → `nmcli radio wifi on` |
| 10:26-10:28 | Phase B-5 | Claude ssh 復活、durable evidence 完全回収 (boot 履歴 + snapshot 数 + ping 集計 + source-IP retro-classify + hang signature) |
| 10:28 | Phase B-6 | cleanup (transient units stop + 58-snapshot-only rm + NM revert) |
| 10:29 | レポート作成 | 本レポート作成、次セッション handover |

実験全体所要時間: 約 2 時間 (Phase B-4 で cycle 26 hang により終了、想定より短縮)。

## 検討して除外した事項

- **60 cycle への延長**: 1 hang 出た時点で本セッション「hang 独立再現、ping 無し」の headline は確定、延長は不要 (plan 記載通り)
- **hang cycle の詳細 kernel dump 取得**: 現行 kernel は `DPM_WATCHDOG=n` のため dpm_suspend で stall する device 特定は不可能 → S4 段の自前ビルドカーネルへ

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-07-01 10:29 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで pre +26 / post +25 = 累計 206 pre / 204 post) | 本セッション 26 cycle の証拠 + 将来 retro-classify 素材 |
| `/var/log/h4-probe/*.snapshot-only.PRE/POST` | 残置 (本セッションで新規 PRE 28 = 実 cycle 26 + smoke test 2、POST 25 = 完走 cycle 25 のみ; snapshot-only は本セッション初導入なので累計 = 本セッション数) | ping_running + xfrm count durable 証拠 |
| vpn-watcher.service | **削除済** (systemctl stop) | VPN reconnect 自動化 |
| cycle-watcher.service | **削除済** (systemctl stop) | 進捗監視 |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | -1 (revert 済) | |
| WiFi radio | enabled (hang reboot 後にユーザが `nmcli radio wifi on`) | |

実機の suspend_stats: success 0, fail 0 (新 boot 開始時 = 10:24 JST)。boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (本セッション hang reboot で変化)。

dev 機 (akdx01) 側: 何も書き換えなし。

## 次セッション引継ぎ

### メモリ更新内容 (本セッション終了時)

- `s2idle-btvpn-hang-mechanism-ladder`:
  - 「過去セッションの valid 性」表に本セッション (26 BT-PAN-valid / 1 hang, `ping_running=NO` durable evidence) を反映
  - 「本セッション (2026-07-01 102907) 結果」セクションを追加、ping confound 説反証を明記
  - candidate (d) の位置づけを「維持困難」→「排除」に更新
  - candidate (b) は「弱いヒント強化、但し依然 establish されず、次は WiFi-on N 拡大」に更新
  - 次の手を「S4 (`DPM_WATCHDOG=y` 自前ビルドカーネル) or `modprobe -r wl` or WiFi-on N=60+ 拡大」に更新
- `MEMORY.md`: index の description を本セッション結論に合わせて訂正

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
echo "=== boot_id (期待: 8963e774... = 本セッション hang reboot 後) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting"
echo "=== transient units 残存していないか ==="
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

### 推奨の次の手 (優先順位順)

#### (i) **`modprobe -r wl` まで踏み込む実験** (~80-100 分)

現在の WiFi-off (`nmcli radio wifi off`) は soft rfkill のみで wl モジュールはロード状態、dpm_suspend chain に参加。この状態で 3 セッション連続 hang が出ているため、「wl が dpm_suspend chain に居ること自体」が hang の必要条件かを切り分けるには `sudo modprobe -r wl` で完全にアンロード → 30 cycle 駆動が必要。

**設計**:
- Baseline 確認 → 58-snapshot-only + vpn-watcher/cycle-watcher デプロイ (本セッションと同じ)
- `nmcli radio wifi off` → **`sudo modprobe -r wl`** (追加ステップ)
- 手動 30 cycle 駆動 (連続 ping 引き続き禁止、pgrep ping で監視)
- 結果: hang → 「wl 完全アンロードでも hang → wl 非依存」bedrock、clean → 「wl-in-chain が決定因の可能性」

#### (ii) **WiFi-on N=60 拡大** (~150-200 分)

061553 の N=30 では statistical power 不足。次は WiFi-on で 60 cycle 駆動 or hang 発生まで:
- 60/60 clean → WiFi-off 三セッション合計 5/56 との比較で Fisher p < 0.05 到達可能 → **candidate (b) bedrock 化**
- 途中 hang → WiFi-on protective 説反証

#### (iii) **S4 (DPM_WATCHDOG カーネル) 自前ビルド** (~1-2 日)

現状 kernel は `DPM_WATCHDOG=n` のため dpm_suspend の stall device 特定不可。`.config` 変更 → 自前ビルド → 実機インストール → 再現駆動で dmesg dump 取得。

機序決着の最終手段、(i)/(ii) で新情報が出なくなった時点で移行。

### 注意事項

- **pgrep pattern に必ず word boundary anchor**: 次セッション以降も pgrep 系 pattern (`(^|[ /])pattern( |$)` 等) で substring false match を防止 (本セッション B-1 で発見した bug)
- **Pair-matching は order-based で**: 70-h4-probe は pre/post 独立 epoch なので `test -f` パターンは間違い、pre 直後の未消費 post を順次消費する方式で
- **SESSION_START_EPOCH は scratchpad 保存**: hardcode 排除、次セッションでも同パターン
- **candidate (d) は今後言及不要**: 三度独立に verified hang で完全排除
- **candidate (b) は要 N 拡大**: WiFi-on/off の差は方向性のみ、統計的有意ではない
- **本 hang は ping 独立**: 「連続 ping が bulk_anchor URB 蓄積」筋書きは反証、機序探究の方向修正
- **`/var/log/h4-probe/` の累積管理**: 累計 206 pre + 204 post + 28 snapshot-only PRE + 25 snapshot-only POST ≈ 470 ファイル、logrotate or 月次手動削除を検討

## 関連レポート

- [2026-07-01_043251 セッション: 二つの壁で establish 不可 (本セッションの起点)](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md)
- [2026-06-30_061553 セッション: 30/30 BT-PAN-valid clean (WiFi-on)](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説 (本セッション hang signature と完全一致)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang (原 bedrock)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-30_030349 セッション: S3'' 30 cycle / cycle 1 のみ valid confound](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md)
- [2026-06-29_200520 セッション: S3 (bnep teardown) 32 cycle / cycle 1 のみ valid confound](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md)
- [2026-06-29_064608 セッション: driver path 25 cycle / 13 valid](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md)
- [2026-06-29_041006 セッション: S1 (btusb pre-unload) 22 cycle / 22 fully valid](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
