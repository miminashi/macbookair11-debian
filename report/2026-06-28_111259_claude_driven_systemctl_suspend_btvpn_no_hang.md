# Claude 自動駆動 systemctl suspend では「BT-PAN × VPN」s2idle ハングが再現せず — lid-close 固有トリガー疑い

- **実施日時**: 2026年6月28日 11:12 (JST)
- **位置づけ**: [2026-06-28_063543 レポート](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)（真の s2idle・AC で「BT-PAN × VPN」併用 lid close ハングを手動 3/3 再現）の続編。同レポートで未解決の「**ハングのトリガーが lid-close 固有か、`systemctl suspend` 経路でも出る汎用 device-suspend の問題か**」を切り分けるため、Claude が ssh 越しに driver で自動駆動して再現を試みた。

## 結論（先に要約）

1. **`systemctl suspend` 経路では 15/15 完走・ハング 0**。前回手動（lid close）で 0/1/6 サイクル目でハングしたのと**直接対照**で、systemctl suspend 駆動の自動 N=15 ループは 1 度もハングしなかった。
2. 各サイクルで「BT-PAN × VPN」**条件は完全に成立**していたことを per-cycle で立証: 全 15 ITER で `panup=ok / pan_ip=172.20.10.13 / vpnup=ok / xfrm_src=172.20.10.13`、IKE_SA 14/15 件が `between 172.20.10.13 ... 160.16.210.47`（残 1 件は IKE delete が記録される前に次サイクル投入のタイミング差で、条件喪失ではない）。
3. 独立記録の突合も全件クリーン: PM `suspend entry`=16 / `exit`=16（**全 entry に対応する exit あり＝ハング 0**。16 の内訳は BTVPN 15 + 本ラン前のセッション初期に発生したオフトピックの 1 suspend、詳細は下記「裏付け」節）、`suspend_stats success=16 fail=0`（全 `failed_*` カウンタ 0、`last_failed_dev` 空）、`s3-soak.log` 15 SLEEP=15 WAKE すべて `drm_err=0 / gpe70=0 / asleep_s=26–31s`。
4. つまり「BT-PAN × VPN」が必要条件であることは前回確定済みだが、**それだけでは十分でなく、lid-close 経路（logind / LID GPE / HandleLidSwitch 系）の何かを併せて踏まないとハングは出ない**、という追加の必要条件が浮上した。
5. 本実験は 15 サイクルの小標本で「`systemctl suspend` では絶対に出ない」とは言えないが、手動 lid close が「3/3＋数回以内」で出すのに対し**強い相対的陰性シグナル**で、トリガーが lid-close 経路に局在することを示唆する。

## 添付ファイル

- [監視・実行プラン](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/plan.md)
- [v3 driver (susp-btvpn-driver.sh)](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/susp-btvpn-driver.sh)
- [Claude 駆動ランの susp-test.log 抜粋 (DRYRUN + BTVPN 15 cycles)](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/susp-test-claude-run.log)
- [同窓の s3-soak.log 抜粋 (15 SLEEP/WAKE ペア)](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/s3-soak-claude-run-window.log)
- [IKE_SA delete 行 (BT-PAN 経由＝172.20.10.13 を確定)](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/ike-sa-deletes.log)

## 前提・目的

- 親レポート 063543 で「真の s2idle・AC・BT-PAN × VPN」併用の**手動 lid close** で 3/3 ハングが再現し、同レポートが論理 down 反復案を「**既に NM がやっている**」と棄却し、検証すべき hypothesis として (a) `btusb` module unload、(b) 残留 xfrm device 確認、(c) **lid-close 固有性**を挙げていた。
- 本実験の目的: (c) の切り分け。lid-close を介さず `systemctl suspend` で同条件 (BT-PAN を実トランスポートにした VPN active) を作って自動ループしたとき、ハングが出るかを観測する。
- もし出れば「lid 固有ではなく device-suspend 段の汎用問題」、出なければ「lid-close 経路のどこかが必要条件として残る」と切り分けられる。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `mem_sleep=[s2idle] deep`（s2idle 選択・全 16 cycle で `PM: suspend entry (s2idle)` 確認）、`LID0 *enabled`、`s3-deep-apply.service` disabled。
- system-sleep フック: `50-kbd-backlight`、`60-s3-soak-log`（deep 強制は 6/28 にコメント無効化済＝s2idle が維持される）。
- 電源: 全サイクル **AC 給電**（`ADP1/online=1`）、バッテリ 87%（cap/charge_now 全期間で不変）。
- **Bluetooth/テザリング**: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)。**今回は iPad(`iMiminashiPadPro`, peer `34:42:62:16:03:F6`) を代替ホットスポットとして使用**（前回手動は iPhone(`iMiminashiSE`, `CC:60:23:AF:2C:60`)）。NM 接続 `iMiminashiPadPro ネットワーク`(type=bluetooth, UUID `fd2a3edb-9800-4d5c-a775-d8055e7e623e`)。PAN = `enx98e0d98d205e`（iface 名はローカル hci0 MAC 由来で iPhone と同一）、IP `172.20.10.13/28`、GW `172.20.10.1`。
- **VPN**: NM 接続 `GSNet`(type=vpn, EAP, `user=macbookair2015`, GW `160.16.210.47`)。本実験のため `password-flags` を 1→0 に変更して headless con up 可能に。**変更手順の落とし穴**: GNOME の VPN 接続詳細にある「他のユーザーも利用できるようにする」をチェックしても **flag は変わらない**（これは接続自体の利用権限で、シークレットの保管場所とは独立）。flag=0 にするには **パスワード入力欄の右端アイコンから「全ユーザー用に保存」** を選ぶ必要がある。最初に前者で試して headless con up が依然失敗（`nm-strongswan-auth-dialog: cannot open display` / `有効なシークレットはありません`）したことで判明。
- **WiFi**: `wl`/`wlp3s0`、`OpenWrt`（`192.168.33.145`）。driver 開始時に **`nmcli dev disconnect wlp3s0`**（非永続＝再起動で復活）で切断、`PHASE DONE` で `dev connect` で復旧。**この方式選択の経緯**: 最初は setup 段階で `nmcli radio wifi off` を ssh で叩いて wifi を落とそうとしたが、ssh 制御経路自体が wifi だったため**コマンド完了前に ssh が切れて実機が LAN 外で残り、ユーザ介入で復旧した**。`radio off` は**再起動でも off が維持される永続設定**で blind 運用との相性が最悪。これを受けて driver は (1) 設定中は wifi を保つために**「wifi 切断は driver 起動直後に driver 自身がやる」**設計に変更、(2) 切断手段を**非永続な `dev disconnect`** に変更（強制電源断 → 再起動で自動再接続を担保）した。
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。本セッションは `/sandbox` 無効でサンドボックス外から ssh。Claude による全工程（driver 起動・状態確認・ログ突合）を実施。

## アプローチ（driver = `susp-btvpn-driver.sh` v3）

`2026-06-28_021019` の `susp-test-driver.sh` v2（`pan_up()`＋`rtcwake -m no -s N`＋`systemctl suspend`＋PRE/POST sync 永続化）を拡張:

- **Phase 開始**: `nmcli dev disconnect wlp3s0`（VPN が WiFi に逃げないよう強制。**ssh 制御経路もここで切れるため blind 運用**に入る。再起動 or PHASE DONE まで実機は LAN 外）。
- **`pan_up()` / `vpn_up()` を毎サイクル**: `nmcli con up <PAN_CON>` → iface に IPv4 が付くまで最大 25s 待ち → `nmcli con up GSNet` → 最大 25s 内に (a) GSNet が active かつ (b) `ip xfrm state` の ESP SA `src` が PAN iface の IP (`172.20.10.13`) と一致＝**BT-PAN 経由を SA レベルで検証**してから `vpnup=ok` を記録。
- **PRE 行に `vpnup=` と `xfrm_src=`** を追記。`panup`/`vpnup`/`pan_ip`/`xfrm_src` を毎サイクル sync で persist し、後から「条件成立サイクルが実在したか」を保証する。
- **active 通信**: BT-PAN gw への持続 ping を `systemd-run --unit=bt-vpn-ping --collect` で起動。`PHASE DONE` で stop。
- **dry-run モード (N=0)**: suspend を打たず精密チェックのみ → wifi 復帰 → exit。本番投入前の機構検証に使用。
- **正常完走時**: `bt-vpn-ping` を stop し `nmcli dev connect wlp3s0` で wifi を戻して終了。

> driver 構造上、**ハングすれば 1 回で停止し、その後のサイクルは進まない**（PRE が無い iteration は出ない）。1 回ハングできれば確定再現で十分だった、という設計。

## 実行サマリ

| 段 | ユニット | 結果 | 時刻 (JST) |
|---|---|---|---|
| 機構検証 | `susp-btvpn-dry.service` (N=0) | DRYRUN PRECHECK `panup=ok pan_ip=172.20.10.13 vpnup=ok xfrm_src=172.20.10.13 gw_dev=nm-xfrm-8442968` → wifi 復帰 → exit | 07:33:57–07:34:07 |
| 本番 | `susp-btvpn.service` (N=15) | 15/15 完走・**ハング 0**、PHASE DONE で wifi 復帰 | 07:35:41–07:47:40 |

### per-cycle 観測（全 15 ITER 同一パターン）

```
ITER i/15 phase=BTVPN bt=on PRE panup=ok pan_ip=172.20.10.13 vpnup=ok xfrm_src=172.20.10.13 mem_sleep="[s2idle] deep" lid=platform:PNP0C0D:00 ac=1
ITER i/15 phase=BTVPN bt=on POST                                                              mem_sleep="[s2idle] deep" lid=platform:PNP0C0D:00 ac=1
```

> 注: `lid=platform:PNP0C0D:00` は driver の `state()` が `/proc/acpi/wakeup` の `LID0` 行末（プラットフォームバインディング名）を `awk '{print $NF}'` で取得したもの。「`*enabled`／`*disabled`」（凍結状態）を取りたければ別途 `awk '{print $(NF-1)}'` 等が必要。一方 s3-soak.log の `lid=*enabled` は同じ行の別フィールド（`*enabled`/`*disabled` 部分）を取得しているため両者は別の意味を持つ。本実験中、`/proc/acpi/wakeup` の LID0 が常に `*enabled` だったことは s3-soak.log の `lid=*enabled` が全 15 WAKE で記録されたことで担保されている。

全 15 サイクルで条件が**毎回成立**したことを sync 永続化で立証（[susp-test.log 抜粋](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/susp-test-claude-run.log)）。

### 独立記録による完走の裏付け

- **PM 件数（boot 0 全期間）**: `PM: suspend entry (s2idle)` = 16 / `PM: suspend exit` = 16（**全 suspend に exit 対応＝ハングなし**）。内訳 = DRYRUN は N=0 で suspend 0 + BTVPN 15 + α 1（α は本ラン前の単発 VPN 検証セッション中に発生したオフトピックの 1 suspend と推定。本実験全体の入眠は全て s2idle）。
- **`/sys/power/suspend_stats`**: `success=16 / fail=0`、全 `failed_*` カウンタ 0、`last_failed_dev` 空、`last_failed_errno=0`。
- **s3-soak.log（15 SLEEP/WAKE 完全ペア・[s3-soak-claude-run-window.log](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/s3-soak-claude-run-window.log)）**: 全件 `drm_err=0`、`gpe70=0`（LID0 spurious wake もなし）、`asleep_s=26–31s`（rtcwake 30s と整合）、`lid=*enabled` 維持。
- **IKE_SA over BT-PAN（[ike-sa-deletes.log](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/ike-sa-deletes.log)）**: 14 件すべて `between 172.20.10.13[macbookair2015] ... 160.16.210.47[160.16.210.47]`＝**毎 suspend で VPN が BT-PAN 経由でアクティブだったことを strongSwan 側からも確定**。残 1 cycle は IKE delete 行が次サイクルとの境で記録されなかっただけで、PRE 行の `xfrm_src=172.20.10.13` で条件成立は担保。

## 検討して除外した事項・観測上の限界

- **条件未成立の空回り疑い → 棄却**: 全 ITER PRE で `panup=ok` かつ `vpnup=ok` かつ `xfrm_src=172.20.10.13` を sync で永続化済。「BT-PAN が落ちて空サイクル化していた」可能性は事前に潰した（plan で立てた懸念）。
- **WiFi に逃げていた疑い → 棄却**: driver が `dev disconnect wlp3s0`、ESP SA の local src が `172.20.10.13` で BT-PAN 経路を SA レベルで確認、IKE delete も全件 BT-PAN 端点。
- **wake-up 起源の差 → 違いはあるが要因の特定には不十分**: 自動は `rtcwake -m no` で RTC 起床、手動は lid open で起床。前回手動の「停止位置は entry か exit か判別不能」の不確定性のため、resume 経路の差が効いている可能性は残る。
- **小標本性**: 15 cycle は前回手動 #3 boot の「6 正常 → 7 回目でハング」より少しだけ多い程度。**「systemctl suspend では絶対出ない」とは言えない**。ただし、手動は 3 boot 通算でハングまでの累積試行回数 #1=1, #2=2, #3=7（**合計 10 cycle 中 3 hang ＝ ~30%**）、自動は 15 cycle で 0/15＝0%、二項分布で見ると差は強い（手動 hit 率がせめて 10% でも 15 連続 miss は ~20.6%、20% 仮定なら ~3.5%、30% 仮定なら ~0.5%）。
- **代替 peer (iPhone → iPad) の影響**: 親レポートのハング 3 件は iPhone(`172.20.10.6`)、本実験は iPad(`172.20.10.13`)。同じ Apple Personal Hotspot で同サブネット規格、同 NM bluetooth type、ローカル iface 名も同一だが、**peer 側の挙動差（BT 帯域、応答性、PAN コネクションの保持挙動）でハング再現性が変わる可能性は残る**。これは次の一手で iPhone を戻して同 driver で 1 ラン回せば直接切り分けられる。
- **`nm-xfrm-N` 仮想 netdev の存在を SA 経路で観測**: DRYRUN で `gw_dev=nm-xfrm-8442968`（本番ランで毎 cycle 同様の `nm-xfrm-N` が生成）を観測。**nm-strongswan が VPN active 時に xfrm 仮想 netdev を作る**直接証拠で、親レポート 063543 が hypothesis (b)「残留 xfrm device の確認」で挙げていた前提（そもそも xfrm device が存在するか）を本実験のログで裏付けた。**ただし本実験は毎 cycle `vpn_up()` で張り直す（NM 経由で down→up）ため、suspend 突入時点で当該 netdev が残留していたかは観測していない**。残留検証は別途必要（hypothesis (b) 自体は未検証）。
- **ハング → 再起動 → wifi 自動復活経路の未実証**: driver の `dev disconnect`（非永続）設計は理屈上「強制電源断 → 再起動で wifi が auto-connect されて LAN 復帰」を担保するはずだが、**今回は完走したのでこの経路を実証していない**。次にハングを引き当てたとき初めて検証される。設計の前提として書いたが、未検証の留意点として明示。

## 何が次の必要条件か（仮説）

`systemctl suspend` と lid-close で **device-suspend 段の callback 列は同じ**はずだが、その**前段の差**がトリガーを支配している、と読むのが素直:

1. **logind / `HandleLidSwitch*` 経路**: lid-close 時に logind が `suspend.target` を呼ぶ前に行う一連の処理（systemd-inhibit の評価、user session への通知、idle hint 等）。`systemctl suspend` は `loginctl suspend` 経由でも `systemctl start suspend.target` 直叩きでも、この前段が短い。
2. **LID GPE と suspend の相互作用**: 蓋を閉じた瞬間に LID0 GPE 経由のイベントが入り、それと並行して suspend が走ることで競合状態が生じる可能性。`systemctl suspend` ではこの GPE は走らない。
3. **`rtcwake -m no` 自体**: アラームを set してから suspend するため、`/sys/class/rtc/rtc0/wakealarm` が立つ状態。前回手動はアラーム無し。
4. **VPN/BT のタイミング**: lid-close は人間操作で「VPN/BT を上げてから秒〜分単位の間が空く」運用。自動は `vpn_up` 完了後ほぼ即座（~5s 以内）に suspend。**短い間隔の方が起こしやすい可能性は普通の直感に反する**ので最有力ではないが、ESP の rekey タイミング等で逆転もありうる。
5. **iPhone vs iPad の peer 差**。

## 再現方法

driver は `/usr/local/bin/susp-btvpn-driver.sh`（[添付](attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/susp-btvpn-driver.sh)）。前提として `GSNet` の `password-flags=0`（GNOME で「全ユーザー用に保存」）。

1. **前提状態**:
   ```bash
   ssh miminashi@macbookair2015.lan 'cat /sys/power/mem_sleep; grep LID0 /proc/acpi/wakeup; systemctl is-enabled s3-deep-apply.service'
   # 期待: [s2idle] / LID0 *enabled / disabled
   ```
2. **iPad 側で Personal Hotspot ON**（BT で `iMiminashiPadPro` がペアリング済前提）。
3. **PAN を up して iface / IP を確定**:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo nmcli con up "iMiminashiPadPro ネットワーク"; ip -4 -br addr show enx98e0d98d205e'
   ```
4. **dry-run で機構検証**:
   ```bash
   sudo systemd-run --unit=susp-btvpn-dry --collect \
     /usr/local/bin/susp-btvpn-driver.sh DRY 0 on 30 15 \
       "iMiminashiPadPro ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
   ```
   完了後 `susp-test.log` の `DRYRUN PRECHECK` 行で `panup=ok / vpnup=ok / xfrm_src=<PAN IP>` を確認。
5. **本番**:
   ```bash
   sudo systemd-run --unit=susp-btvpn --collect \
     /usr/local/bin/susp-btvpn-driver.sh BTVPN 15 on 30 15 \
       "iMiminashiPadPro ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
   ```
   起動直後 `nmcli dev disconnect wlp3s0` で**実機は LAN 外（blind 運用）**になる。完走 or ハングまで放置。
6. **判定**: 完走 = `susp-test.log` に `PHASE DONE phase=BTVPN`＋wifi 復帰＋15 ITER の PRE/POST 完備。ハング = `PHASE DONE` 欠落＋PRE あり/POST 無しの最終 iteration＋`s3-soak.log` SLEEP→(WAKE 無し)→BOOT＋boot_id 変化。

## 留意・次の一手

- **次にやるなら最有力**: 同条件のまま **ユーザが実 lid close を反復**（前回 063543 のプロトコル）して、**peer を iPad に変えた状態**で 3/3 が再現するかを見る。これで「peer 差で消えたのか」「自動経路が必要条件を満たさなかったのか」が分離できる。
- 続けて、駄目押しで **`susp-btvpn-driver.sh` を iPhone に対して回す**（NM 接続名と PAN IP を `iMiminashiSE ネットワーク` / `172.20.10.6` に差し替え）。iPhone でも 15 cycle クリーンなら、トリガーは確かに lid-close 経路に局在。
- もし peer 差で消えていた場合は親レポートの結論「BT-PAN × VPN の相互作用条件」を**「BT-PAN × VPN × iPhone(または特定 peer 挙動)」**に縮める必要が出る。
- 親レポートの hypothesis (a) `btusb` module unload は、自動経路で出ないことが分かった以上**現在の優先度は下がる**。先に lid-close 固有性を確証してから戻す方が筋。
- 残置物（撤去任意）: `/usr/local/bin/susp-btvpn-driver.sh`、`/var/log/susp-test.log`（追記）、`susp-btvpn.service`/`susp-btvpn-dry.service` は `--collect` で自動回収済。`GSNet` の `password-flags=0` は本実験のためのユーザ変更で**実機に残っている**ため、セキュリティ要件で戻したい場合は GNOME 側でパスワード欄を「このユーザー用にのみ保存」に戻すこと。
- 後始末ログ確認: PHASE DONE 後に `nmcli dev connect wlp3s0` で wifi 復帰済、`bt-vpn-ping` も stop 済（driver 内）、現状 `susp-btvpn` unit は inactive、boot_id 不変。

## 関連レポート

- [2026-06-28_063543 手動 factorial 切り分け（直接の親）](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — BT-PAN × VPN × lid-close で手動 3/3 ハング、本件の自動再現を要請
- [2026-06-28_021019 driver 方式・VPN 無し BT-PAN 10/10 クリーン](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) — 本 driver の親 (`susp-test-driver.sh` v2)
- [2026-06-27_072510 deep モード計4ハング・s2idle ロールバック決定](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) — deep 側で「内在 hang」と結論した文脈
