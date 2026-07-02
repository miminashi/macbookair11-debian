# Bluetoothテザリング中のlid closeで計3回ハング — 原因切り分けと対策

> 初版は「BTテザリング+VPN で 2 回」として起票。調査で VPN は不要条件と判明、一時は「真因 = active BT-PAN」と結論したが、**追記4 でそれも反証**（btusb 除去でもハング #4）。**最新結論: 根因は BT 非依存の内在的 S3-deep hang（史実 ~0.7/週）、BT-PAN は増悪 stressor**。計 4 回ハング。**最新の確定見解は追記4 を参照**。

- **実施日時**: 2026年6月27日 07:25 (JST)
- **位置づけ**: S3(deep) soak（[2026-06-20 開始](2026-06-20_045414_s3_deep_persist_soak_start.md)）の**中間チェックイン（6/27 目安）を兼ねる事故調査**。soak の go/no-go に関わる suspend 中ハングが **active BT テザリング条件下で計 3 回顕在化**した事案を分析し、対策（フック B-2）を実装・検証した。

## 本レポートの読み方（重要・先に必読）

本レポートは**時系列で理解が更新された**記録。**本文〜追記3 も逐次更新され、最新の確定見解は追記4**。本文/初期追記は**経緯（どう誤読し、どう訂正したか）の記録**として読むこと:

> **🔴 最重要（追記4・最新結論）**: バッテリ STH で **btusb を完全除去してもハング（#4）**。よって **「真因 = active BT-PAN」は反証された**。**根因は BT 非依存の内在的 S3-deep hang（史実 ~0.7/週）**。BT-PAN は増悪 stressor の一つにすぎない。**S3 deep の go/no-go は no-go 寄り** = ユーザの価値判断（s2idle 退避 vs 継続）待ち。フック B-2 は #1/#2 級の BT stressor 緩和として残す（信頼性の解決策ではない）。

| 本文（初版）の主張 | 中間訂正（追記1〜3） | 最新（追記4） |
|---|---|---|
| ハング **2 回** | 計 **3 回**（追記1） | **計 4 回**（#4=battery STH, 追記4） |
| **BT+VPN の複合相関**（仮説C） | VPN 不要・真因は **active BT-PAN が経路に存在**（追記1・2） | **反証**: btusb 除去でもハング → **BT は stressor、根因は BT 非依存の内在 S3-deep hang** |
| 「radio off」で緩和 | radio off 不十分・**module unload** 必要（追記2） | module unload も**根治せず**（内在 hang は teardown で直らない） |
| 対策 **B-1** 実装済 | **B-2（module unload）に置換**・稼働中（追記2・3） | B-2 は残すが **S3 信頼性の解決策ではない** |

## 添付ファイル

- [調査プラン](attachment/2026-06-27_072510_bluetooth_vpn_lid_close_hang/plan.md)

## 前提・目的

- **事象（ユーザ報告）**: 2026-06-27 に MacBook Air が **2 回ハング**。いずれも **Bluetooth テザリング + VPN を使用中に lid close** したとき。復帰には**電源ボタン長押しの強制電源断**が必要だった。
- **目的**: durable ログ（`/var/log/s3-soak.log` + 永続 journald）で 2 回のハングを**事実分類**し、ユーザの挙げた「BT テザリング+VPN」という共通条件が**真の相関要因か偶発か**を切り分ける。根因に応じた可逆な対策を提示する。
- **前提（現行スリープ構成）**: 6/20 から S3(deep) 永続化（可逆）+ 2週間 passive soak が稼働中。`s3-deep-apply.service` enabled（起動毎に `mem_sleep=deep` 選択 + `LID0` wake 無効化）。battery 時の lid close は logind `HandleLidSwitch=suspend-then-hibernate`（STH, `SuspendEstimationSec=30min`）。LID0 wake 無効のため復帰は電源ボタン。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `/sys/power/mem_sleep` = `s2idle [deep]`（deep を runtime 選択）、`LID0  S4  *disabled`、`s3-deep-apply.service` enabled。swap=`/dev/sda3`（≈3.73 GiB, hibernate 用）。
- **Bluetooth**: `btusb`（**USB 接続**）, `hci0`。デバイス `BCM2046B1` (0a5c:4500) + `Apple Bluetooth USB Host Controller` (05ac:828f)。BT テザリング相手の BT デバイス = `CC:60:23:AF:2C:60`。
- **WiFi**: `wl`（broadcom-sta DKMS, BCM4360）, `wlp3s0`。**BT と WiFi は同一コンボチップ系だが rfkill スイッチは別**（`rfkill0`=hci0 / `rfkill1`=phy0）。※初版 B-1 は wl も被疑として WiFi off したが、追記で **wl は主因でない**と判明（対策 B-2 は WiFi に触れない）。
- **VPN**: NetworkManager 接続 `GSNet`（type=vpn）= **strongSwan 6.0.1 IPsec/IKEv2**（`charon-nm`, `nm-xfrm-*`, ゲートウェイ側 `192.168.83.1`）。
- **テザリング**: BNEP PAN（`bnep0` → `enx98e0d98d205e`）。割当 IP `172.20.10.6`（iPhone テザリング既定サブネット）。
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。

## 調査結果

### 1. 2 回のハングを事実確定（true hang）　※調査時点で判明した 2 件。**#3 は検証中に発生（追記1）＝計 3 件**

`/var/log/s3-soak.log` で「**SLEEP 行あり → 対応 WAKE 無し → 次行が BOOT**」のシーケンスを 2 件検出。`journalctl --list-boots` でも該当 boot が**異常終了**（強制電源断）している。

| # | ハングした boot | SLEEP(入眠) | type / ac / cap | 次の BOOT(復帰) | 復帰までの空白 |
|---|---|---|---|---|---|
| 1 | `840c7e57` | 2026-06-26 22:31:56 | STH / **ac=0** / 84% | 2026-06-27 01:03:14 | ~2.5h |
| 2 | `43beb408` | 2026-06-27 04:04:37 | STH / **ac=0** / 53% | 2026-06-27 06:59:25 | ~2.9h |

- 両件とも `gpe70=0`（spurious wake 源 LID0 は凍結維持）・`drm_err` は WAKE 行が無いので記録なし。
- 両件とも **battery 時の STH 経路**（lid close → logind STH → S3 deep）。

### 2. ハングの停止位置 — system-sleep フック完走後の S3 遷移中（journald 不可視）

両ハング boot の journald **最終行**は、どちらも `kbd-backlight-sleep[...]: pre/suspend-then-hibernate: saved=0 set->0`（= `50-kbd-backlight` フック）。soak ログには SLEEP 行が記録済み（= `60-s3-soak-log` フックも完走）。

→ **ハングは system-sleep pre フック 2 本が走り終えた後、実カーネル suspend 遷移（S3 deep）中**で発生。journald は suspend 突入後 disk に flush されないため停止位置はこれ以上特定不能（[2026-05-31 レポート](2026-05-31_132125_s3_hang_switch_to_s2idle.md)の「可視性ゼロ」像と一致）。`pm_print_times` の device 行も同理由で残らない。

### 3. BT/VPN 相関 — 対照群が完全に分離（最重要）　⚠️初版解釈（追記1で更新: **VPN は不要条件・真因は BT device**）

各 suspend の直前に **BT-PAN(BNEP) と strongSwan IPsec(charon-nm) が active だったか**を journald で照合し、soak 全期間と突き合わせた:

| 条件 | 該当 suspend | ハング |
|---|---|---|
| **BT/VPN 無し**（boot `dd9c9218`, 6/20–6/25 の 5日間。長時間 battery STH 含む ~13 サイクル） | 多数 | **0** |
| **BT/VPN 有り**（6/26 22:18〜 のモバイルセッション。全て battery STH） | 3 | **2 (67%)** |

- クリーン週（boot `dd9c9218`）は `charon`/`bnep`/`strongswan` の出現が **0 件**（= BT テザリングも VPN も一切未使用）。長時間 battery STH（asleep_s 最大 ~128310s ≈ 35h）も**全て正常復帰**。→ **battery / STH / S3 deep そのものは hang の十分条件ではない**。
- ハング #1（boot `840c7e57`）: BT/VPN セッション開始 **22:18:09**（`bnep0 connected`）/ **22:18:15**（`vpn "GSNet": starting strongswan`）→ **13 分後の 22:31:56 suspend でハング**。同 boot 内のそれ以前の suspend（20:04/04:25/08:18×2/08:38）は**全て BT/VPN 開始前**で正常。
- ハング #2（boot `43beb408`）: BT/VPN 稼働中。`01:16 suspend → 03:06 正常復帰`（asleep_s=6642, drm_err=0）の後、BT/VPN 再接続（03:07）→ **04:04 suspend でハング**。

**結論（相関）**: BT テザリング(BNEP) + strongSwan IPsec VPN セッション中の battery STH は **3 回中 2 回（67%）ハング**、BT/VPN 無しでは **0%**。極めて強い相関。ただし **1 回（01:16）は BT/VPN 稼働中でも正常復帰**したため、「BT/VPN ＝必ずハング」ではなく**確率的増悪**である。

### 4. 入眠直前の挙動（両ハング boot 共通シグネチャ）

```
charon-nm[...]: error writing to socket: Network is unreachable
charon-nm[...]: 172.20.10.6 / 192.168.83.1 disappeared from enx98e0d98d205e / nm-xfrm-...
NetworkManager: device (CC:60:23:AF:2C:60): disconnected -> unmanaged (reason 'unmanaged-sleeping')
systemd: Reached target sleep.target
systemd: Starting systemd-suspend-then-hibernate.service
kbd-backlight-sleep: pre/suspend-then-hibernate: saved=0 set->0   ← journald 最終行（ここから先は不可視）
```

- **NetworkManager は suspend 前に既に BT/VPN を soft teardown している**（`unmanaged-sleeping`、XFRM アドレス除去）。**それでもハングした** → ソフトな論理切断だけでは不足で、**btusb/bnep デバイスや無線が電源 ON のまま S3 遷移に入る**ことが疑わしい。
- 参考: ハング窓と同セッションで `wl` ドライバが `ERROR @wl_set_key_mgmt : invalid cipher group (1027076)` を連発（resume 直後の WiFi 再アソシ時）。**同一コンボチップの WiFi 側も同時に不安定**。

### 5. 根因の位置づけ（仮説 C: S3 遷移の脆弱性 × BT/VPN teardown の増悪）　⚠️初版解釈（追記1で更新: **VPN/wl/XFRM は不要・真因は active BT-PAN が経路に存在**）

- 歴史的な S3 resume hang（週 0.7–0.8 件）は **BT/VPN 導入前（自宅 WiFi 運用）から存在**する。今回の 2 件は新種のバグではなく、**S3 deep 遷移の元来の脆弱性が、btusb(BT-PAN) + IPsec(XFRM) + wl の suspend/resume 経路の増分により増悪**した像（プラン仮説 C）。
- よって対策が成功しても「**スパイクの消失**」が期待値であり、**BT/VPN 非依存のベースライン S3 hang は別問題**として残る（soak の go/no-go はこの点を別途評価）。

## 対策（B-1 広い案 — ⚠️初版。**追記2で B-2 に置換済**）

> **⚠️ 重要（矛盾回避）**: 本節は初版の対策 B-1（radio off / WiFi off）の記録。**radio off は #3 で不十分と判明し、追記2 で B-2（BT module unload / WiFi off 廃止）へ置換した。現在 `/usr/lib/systemd/system-sleep/55-net-teardown` で稼働しているのは B-2**。本節の pre/post 手順（`bluetoothctl power off` / `nmcli radio wifi off` 等）は**現行フックの動作ではない**。経緯として保持する。

> 方針: soak 既定の「true hang → s2idle 自動退避」は**発火させない**（s2idle も [2026-06-01](../) にハング実績、BT/VPN が真因要素なら sleep mode は red herring）。まず BT/VPN 相関を**安価かつ可逆に**潰す。

### 即時の行動的 stopgap（システム変更なし・本日から有効）
診断確定までは **lid close 前に手動で VPN/BT を切断**（GNOME で OFF / `nmcli con down GSNet`）するか、**BT テザリング+VPN 使用中は lid close しない**。これで強制電源断によるデータ損失リスクを回避。（※「AC につなげば安全」は誤り。AC でも suspend には入り得る。）

### 対策 B-1（実装済・診断兼治療・可逆）: suspend 前に全無線を電源断する system-sleep フック
既存フック枠（`50-kbd-backlight` / `60-s3-soak-log`）に倣い **`/usr/lib/systemd/system-sleep/55-net-teardown`** を**設置済**（実行順 50<55<60）。NM の soft teardown では不足だった**無線の電源断**を pre フックの**プロセス文脈**で確実に行う。**ユーザ選択により「広い案（BT+VPN+WiFi 全無線）」を採用**。

- **pre**: ① active な NM VPN を `nmcli connection down`（charon/XFRM を綺麗に畳む）→ ② `bluetoothctl power off`（BT-PAN/bnep 切断 + btusb アイドル化）→ ③ `nmcli radio wifi off`（wl/wlp3s0 down）。各ステップ `timeout 10` + guard で suspend を阻害しない。`/var/log/net-teardown.log` に記録。
- **post**: `nmcli radio wifi on` + `bluetoothctl power on`（WiFi/BT 復帰。**VPN はユーザが GUI で手動再接続**）。
- **可逆**: `sudo rm /usr/lib/systemd/system-sleep/55-net-teardown` で原状復帰。
- **設計上の修正点（本調査で判明）**: **`rfkill` CLI 未インストール**のため `bluetoothctl` / `nmcli radio` で実装。BT と WiFi は別 rfkill（`rfkill0`=hci0 / `rfkill1`=phy0）で、`wl` も同 suspend 窓で異常 → 広い案で両方畳む。
- **済んだ検証（ロックアウト回避のため WiFi 非干渉の範囲のみ）**: ローカル/実機 `sh -n` 構文 OK。`bluetoothctl power off→on` 往復で `Powered: no→yes` を確認。VPN-down ループは現在 VPN 無しで no-op を確認。**実機は WiFi のみで接続（ssh 経路も同 WiFi）のため `nmcli radio wifi off` のライブ実行は不可**（ssh 自切断）。
- **未実施（user-gated）**: BT+VPN を up した状態での実 suspend 検証。各ハングは電源ボタン強制復帰が必要なため**ユーザ立ち会いが前提**。
- **再発時の解釈注意**: BT/VPN/WiFi 全部畳んでも再発するなら、残る被疑は btusb/bnep の**デバイス(USB)suspend 自体**（→ `modprobe -r btusb` 等の escalation）か、**BT/VPN 非依存のベースライン S3 hang**。

### 対策 A-1（仮説 A 寄り＝純 S3 firmware hang が確定し B-1 無効の場合のみ・可逆 stopgap）
`s3-deep-apply.service` を disable + `mem_sleep=s2idle`（6-20 レポートのロールバック手順）。ただし s2idle 史実ハングのため恒久解にしない。

## 再現方法（実機手順 / すべて read-only）

```bash
# 1) true hang の検出（SLEEP→WAKE無し→BOOT のシーケンス）
ssh miminashi@macbookair2015.lan 'sudo cat /var/log/s3-soak.log'
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail -10'

# 2) ハングした boot の停止位置（最終行 = フック）と BT/VPN 状態
for B in 840c7e57-68be-495f-997b-1ccd7a7e62dc 43beb408-4b43-4fee-b669-99bfdcc2bb0f; do
  ssh miminashi@macbookair2015.lan "sudo journalctl -b $B -o short-iso | tail -12"
done

# 3) BT/VPN セッションと各 suspend の整列（相関の確認）
for OFF in -2 -1; do
  ssh miminashi@macbookair2015.lan "sudo journalctl -b $OFF -o short-iso | \
    grep -iE 'bnep0 connected|starting strongswan|Reached target sleep.target|disappeared from'"
done
# 対照: クリーン週 boot -6 に charon/bnep が出ないこと（→ 0 件）
ssh miminashi@macbookair2015.lan "sudo journalctl -b -6 | grep -icE 'charon|bnep0 connected|strongswan'"
```

## 検証（対策投入後 — ⚠️初版の計画。**実検証は追記2・3 で実施済**）

> **⚠️** 本節は B-1 時点の検証計画。実際の検証（btusb 除去 5/5・load-bearing・E2E）は**追記2・3 に結果として記載済**。以下は当初想定。

- **最速**: BT テザリング+VPN を up した状態で `systemctl suspend` を数サイクル（フック発火のため rtcwake 単体不可）。**各ハングは電源ボタン強制復帰が必要なため user-gated**。
- **安全側**: 通常運用 passive soak で、**意図的に BT+VPN+lid close** を繰り返し `s3-soak.log` で true hang 0 件を確認。
- 期待: 仮説 C が正なら BT/VPN 時の**ハング・スパイクが消失**。ベースライン S3 hang の有無は別途継続観測。

## 結論と次の一手（⚠️初版の結論。**追記1〜3で更新済**）

> **⚠️ 本節は初版（2 ハング・BT/VPN 相関・仮説C・B-1）時点の結論。確定結論は追記2・3 を参照**（計3回・VPN不要・真因=active BT-PAN が suspend 経路に存在・対策=B-2）。

- 本日の 2 回のハングは **battery STH(S3 deep) 入眠時の true hang** で、**BT テザリング(BNEP) + strongSwan IPsec VPN セッションに強く相関**（BT/VPN 時 67% vs 無し 0%）。**確率的増悪（仮説 C）**であり、S3 遷移の元来の脆弱性が btusb/bnep/XFRM/wl の suspend 経路で悪化したもの。
- **次の一手**: 対策 B-1（**広い案＝BT+VPN+WiFi 全無線を suspend 前に電源断**）を `55-net-teardown` として**設置済**（`bluetoothctl`/`nmcli radio` 実装）。残るは **user-gated な実 suspend 検証**（BT+VPN を up → `systemctl suspend` を数サイクル、各ハングは電源ボタン強制復帰）。
- soak への含意: **S3 deep go/no-go は「BT/VPN 時のスパイク」と「ベースライン hang」を分離して評価**する。今回の 2 件を以て即 s2idle 退避はしない。

## 追記 (2026-06-27 17:35 JST) — 検証で3件目のハング、容疑が BT デバイスへ収束

広い案フック設置後、ユーザが検証を実施したところ **4サイクル目でハング（3件目）**。これにより解釈が更新された。

- **検証の実態**: AC 給電・plain `systemctl suspend`（+rtcwake）を**高速サイクル**（8分で4回, 各 asleep ~25–35s / awake ~80s）。**VPN は非アクティブ**（`net-teardown.log` の `vpn_down=[]`）。BT-PAN は各 resume 後に再接続（`bnep0` rename）。
- **フックは正常動作**: ハングした suspend 直前に `bluetoothd ... power_down`（BT off）+ `NetworkManager audit op=radio-control wireless-enabled:off`（WiFi off）を記録。**全無線を電源断した状態でハング**。kernel 最終行 = `PM: suspend entry (deep)`。
- **2つの誤読を訂正（重要）**:
  1. **`PM: suspend entry (deep)` 最終行は firmware 署名ではない** — journald が suspend で停止する前の最後の1行にすぎず、**btusb 等の device-suspend hang と firmware hang を区別できない**（[2026-05-31 レポート](2026-05-31_132125_s3_hang_switch_to_s2idle.md)の知見）。よって「ベースライン firmware hang」とは結論できない。
  2. **radio off ≠ device 除去** — `bluetoothctl power off` / `nmcli radio wifi off` は電源を落とすが、**btusb/bnep/wl は dpm_suspend 経路に残ったまま**。「無線を切ってもハングした」は **BT デバイスの容疑を晴らさない**。
- **全ハングの共通項は BT（テザリング）で、VPN ではない**:

  | ハング | BT-PAN | VPN | 電源 |
  |---|---|---|---|
  | #1 (22:31) | ✓ (bnep 22:18) | ✓ | battery STH |
  | #2 (04:04) | ✓ (bnep 03:07) | ✓ | battery STH |
  | #3 (17:26) | ✓ (bnep 17:25再接続) | **✗** | AC plain suspend |
  | クリーン週(~13サイクル) | ✗ (charon/bnep=0) | ✗ | AC/battery → **0件** |

  → **正直な集計（この時点）: BT 稼働 suspend ≈ 3 hang / 7、BT 無し ≈ 0 / 13**（※追記2 の決定テスト 5 サイクル追加で **BT 無し 0 / 18** に更新）。**確率的・BT 相関・VPN は不要条件**。3件目は VPN を「必要条件」から外しただけで、**BT/btusb への容疑をむしろ強めた**。
- **高速サイクルの交絡に留意**: `renamed from bnep0 (while UP)` = BT-PAN 再構成途中の netdev churn。実ハング条件ともクリーン週とも違う cadence なので、決定テストは normal cadence で行う。

## 追記2 (2026-06-27 18:00 JST) — 決定テスト結果: BT 除去で 5/5 clean、フックを B-2 へ

`systemd-run` でデタッチ実行（`/usr/local/sbin/btusb-test.sh`, `/var/log/btusb-suspend-test.log`）:

1. `systemctl stop bluetooth` + `modprobe -r bnep btusb` → kernel `usbcore: deregistering interface driver btusb`、`/sys/class/bluetooth/` 空（**hci0=BT USB コントローラが suspend 経路から消失**）。
2. **AC・normal cadence（awake ~120s）で `systemctl suspend` を 5 サイクル → 5/5 clean**（soak ログに `SLEEP→WAKE` ペア・`asleep_s` 31–33・`drm_err=0`、異常終了 boot なし）。
3. テスト後 `modprobe btusb` + `systemctl start bluetooth` で BT 復帰。

> 補足: 起動ログの「remaining=1」は **bnep**（純ソフトの PAN netdev 層でハードを持たず suspend 経路に無関係）であり、**btusb は確実に除去**されていた（`deregistering` + `hci=` 空が裏付け）。

**集計（最終）**: active BT-PAN あり = **3 hang / 7**、BT 無し or PAN 非アクティブ（クリーン週 13 + 本テスト 5）= **0 / 18**。
→ **真因は「active BT-PAN（btusb/hci0）が dpm_suspend 経路に存在すること」**。`radio off` だけの B-1 は不十分（#3 が証明）、**device を経路から外す（module unload）と消失**。
※ 残る交絡: 本テストは btusb 除去と同時に cadence も normal 化（高速→通常）。ただし全ハング(3/3)に active BT が共通し BT 非依存は 0/18 のため、**BT が支配要因**と判断（cadence は二次的）。

### 対策を B-2 に更新（実装済 / happy path・**load-bearing path 検証済** / 実 suspend E2E も実施＝後述・限界あり）
`55-net-teardown` を **radio off 方式（B-1）から module unload 方式（B-2）へ書き換え設置済**:
- **pre**: ① active NM の VPN+Bluetooth 接続を `nmcli connection down` → ② NM の bt デバイスを `nmcli device disconnect` → ③ `systemctl stop bluetooth` + `modprobe -r bnep btusb`（成功時 `/run/net-teardown.bt-removed` を立てる。失敗時のみ `bluetoothctl power off` で緩和）。**WiFi off は廃止**（クリーン週で WiFi 稼働中 0 件＝不要と判明、resume 遅延も削減）。
- **post**: フラグがあれば `modprobe btusb` + `systemctl start bluetooth` で BT 復帰（VPN はユーザ手動再接続、WiFi は NM 自動復帰）。
- **検証(happy path・往復・実 suspend せず安全に)**: `sh -n` OK、pre→post 往復で `hci0`/`btusb` が `除去→復帰`、`Powered: yes` を確認（次の load-bearing・E2E と合わせて検証は3段階）。
- **load-bearing path 検証済（advisor 指摘点を解消）**: 当初の 5/5 テスト・往復テストは **BT アイドル時**にしか `modprobe -r` しておらず、実テザリング中は bnep/hci0 が refcount を持ち NM が `enx…` を保持 → `modprobe -r` が **EBUSY** で fallback（=B-1=#3 で hang）に落ちる懸念があった。対策として pre に **NM の bluetooth 接続 down + bt device disconnect** を追加。**実テザリング稼働中（bt device=connected, `hci0:12` PAN, `enx98…` netdev, bnep refcount=3）に pre ロジックのみ実行 → `bt=removed`（modprobe -r 成功, EBUSY フォールバックせず）, hci0 消失を確認**（suspend せず・ハングリスク0）。post で hci0/btusb/`Powered: yes` 復帰も確認。
- **実 suspend 検証（E2E, 実施済 18:25）**: 実 BT テザリング up 状態で `rtcwake -m no -s 30; systemctl suspend` を 4 サイクル（detached, AC）。**4/4 クリーン復帰・ハング 0・boot 健全**、各 net-teardown `bt=removed→reloaded`、soak WAKE ペア・drm_err=0。
  - **限界（正直な評価）**: 実テザリングが suspend 時に生きていたのは **サイクル1のみ**（`bt_connected=1`）。btusb reload 後の自動再接続が電話側都合で復帰せず、サイクル2–4 は BT アイドル化。よって**真の故障条件のフル E2E は 1 サイクル（クリーン）**＋ BT アイドル 3 サイクル（クリーン）。
  - **機構の実証は強固**: 「実テザリング稼働中→`bt=removed`」は 2 回確認（手動 load-bearing + E2E#1）。「BT を経路から除去→クリーン suspend」は通算 **9/9**（btusb テスト 5 + E2E 4）。
  - **残提案**: より高い統計的確信が要れば、通常運用で実テザリング+lid close を数回繰り返し `net-teardown.log`/`s3-soak.log` で再発 0 を蓄積（hook が常時稼働）。
- **運用上の注意**: 本機の BT は**テザリング専用**（内蔵キーボードは applespi）なので毎 suspend の btusb unload/reload は安全。BT 入力機器を使う構成では条件分岐化が必要。
- **go/no-go の留保**: 5 clean cycle は ~0.7/週の baseline S3 hang を否定できる量ではない。S3 deep の最終判定は**継続 soak** で行い、この 5 件に依拠しない。

## 追記3 (2026-06-27 18:30 JST) — 検証で判明した補足事実

E2E 検証中に判明し、上記までに未記載だった事実:

- **フックの step-1（`nmcli connection down`）は BT-PAN を取りこぼすことがある**: E2E サイクル1 で、suspend 時にテザリングが生きていた（`bt_connected=1, pan_netdev=1`）にもかかわらず、net-teardown ログは `conn_down=[]`（空）で `bt=removed`。つまり **BT を実際に suspend 経路から外しているのは step-2・3（`nmcli device disconnect` + `systemctl stop bluetooth` + `modprobe -r bnep btusb`）＝これが load-bearing**。step-1 は best-effort（主に VPN/charon を畳む役割）であり、BT-PAN の解放を step-1 に依存していない点が、むしろ本フックの頑健性の理由（手動 load-bearing テストでは `conn_down` 非空だったので、active 接続の見え方は状況依存）。
- **対策検証はすべて AC plain suspend で実施。元の故障経路（battery STH = lid-close）では未再検証**: フックは電源状態非依存（pre で BT を除去するため STH/通常 suspend を問わない設計）だが、厳密には **battery STH での実ハング再現・対策確認は残課題**。元の #1/#2 は battery STH、検証（btusb テスト・E2E）は AC plain suspend だった。
- **表題・前提・結論セクションは初版の「2回ハング」のまま**: 実際は計 3 回（#3 は検証中に発生）。追記1–2 で訂正済みだが、冒頭サマリは初版時点の記述。

## 追記4 (2026-06-27 19:10 JST) — 【結論訂正】バッテリ STH で #4 ハング: BT 除去でも再発、真因は BT 非依存の内在 S3-deep hang

ユーザがバッテリ駆動 + BT テザリングで lid-close 復帰を 4–5 回（**高速サイクル**）試行 → **再びハング（#4, 強制電源断）**。journald が決定的:

- ハングした suspend（`19:04:59`, type=suspend-then-hibernate, **ac=0**, 直前 awake ~63s）の直前ログ: `bluetooth.service Stopped` + **`usbcore: deregistering interface driver btusb`**（= フック B-2 が btusb を確実に除去）→ `Performing sleep operation 'suspend'` → **`PM: suspend entry (deep)` で停止**。net-teardown も `bt=removed`。btusb はテスト中 12 回 deregister/register を交互（毎サイクル除去→復帰）。
- → **btusb を suspend 経路から完全に除去しても、S3 deep 入口でハングした**。

**これは追記2 の「真因 = active BT-PAN が経路に存在」を反証する**:
- **BT-PAN は増悪要因（stressor）の一つであって根因ではない**。#1/#2/#3 は説明できるが、#4（btusb 除去）は説明できない。
- **根因 = BT 非依存の内在的な S3-deep hang**（[2026-05-31](2026-05-31_132125_s3_hang_switch_to_s2idle.md) で s2idle へ退避する原因になった史実 ~0.7–0.8 件/週の firmware/device suspend hang）。「5 clean cycle では否定できない」と留保していた baseline がここで再確認された。

**cadence は過剰解釈しない**: #3/#4 は高速サイクル（awake ~60–120s）、#1/#2 は normal cadence + active BT。一見「高速サイクルが別トリガー」に見えるが、**btusb 除去条件では rapid と battery が交絡**（唯一の battery+btusb 除去ランが #4=rapid でハング）。**normal-use セル（battery + lid STH + normal cadence + hook 有効）のクリーンデータは 0 件**。よって「高速は test artifact だから normal use は安全」とは**言えない**。「normal use が許容範囲」の唯一の根拠は**クリーン週（テザリング無し・normal cadence・battery STH 含む ~13 サイクル・0 ハング）**。

**全ハング集計（最終・訂正版）**:

| ハング | 電源 | cadence | btusb | 説明 |
|---|---|---|---|---|
| #1 22:31 | battery STH | normal(~14分) | 有・active BT | BT stressor |
| #2 04:04 | battery STH | normal(~58分) | 有・active BT | BT stressor |
| #3 17:26 | AC plain | rapid(~2分) | 有 | rapid/stressor |
| #4 19:04 | battery STH | rapid(~63s) | **除去済** | **BT 非依存 = 内在 hang** |
| クリーン週 | AC/battery | normal | 有(PAN非active) | 0/~13 |
| btusb/E2E テスト | AC | normal | 除去 | 0/9（**全て AC**） |

**判断（go/no-go）**: 本件は S3 deep の go/no-go が **no-go 寄り**に答えた事案。teardown 調整では内在 firmware/device hang は直らない（史実: カーネルパラメータ 3 回の試行も全失敗）。**フック B-2 は #1/#2 級の BT stressor を消す効果はあるので残す**が、S3 信頼性の解決策ではない。次は**ユーザの価値判断**（s2idle 退避 vs S3 deep 継続）。

## 追記5 (2026-06-27 19:20 JST) — s2idle へロールバック実施（ユーザ決定）

#4 を受け、ユーザ判断で **s2idle へロールバック**（痛み優先。soak 既定ルール「true hang→退避」に沿う）。実施:

```bash
sudo systemctl disable --now s3-deep-apply.service   # oneshot 無効化（deep 再選択を止める）
echo s2idle | sudo tee /sys/power/mem_sleep           # runtime を s2idle に
echo LID0 | sudo tee /proc/acpi/wakeup                # LID0 wake 凍結を解除（*disabled→*enabled）
```

確認: `mem_sleep=[s2idle] deep`（s2idle 選択）/ service `disabled+inactive` / `LID0 *enabled` / GRUB cmdline `mem_sleep_default=s2idle`（**再起動しても s2idle 維持＝恒久**）。

- **トレードオフ（受容済）**: 待機電力が S3 の ~0.06–0.10W → **s2idle ~0.70W**（夜間ドレイン増）。S3 deep の主目的（待機電力低減）は**今回は断念**。
- **注意**: s2idle も史実で 1 回ハング（[2026-06-01](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)）＝「マシ」であって無欠ではない。再発時は `s3-soak.log` で検出される（soak ログ計測フック `60-s3-soak-log` は残置、監視継続）。
- **残置物**: フック `55-net-teardown`（B-2）は当面**残置**（BT stressor 緩和の保険。ただし根因でないため、毎 resume の BT/VPN 手動再接続が煩わしければ `sudo rm` で除去可）。S3 復帰（再 enable）も `systemctl enable --now s3-deep-apply.service` で可能（可逆）。
- **S3 deep の最終評価**: 内在 S3-deep hang が teardown で直らないことが判明したため、**S3 deep 本採用（GRUB deep 化）は見送り**。将来やるなら別アプローチ（firmware/カーネル側の根本対処）が必要。

## 関連レポート

- [2026-06-20 S3(deep) 永続化+soak 開始](2026-06-20_045414_s3_deep_persist_soak_start.md) — soak ログ形式・true hang 判定・STH 2ペア記録・ロールバック手順の出典（本件は中間チェックインを兼ねる）
- [2026-05-31 S3 hang により s2idle へ切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md) — hang 史・「停止位置はログから特定不能」の根拠
- [2026-06-19 battery 駆動 S3 待機電力測定](2026-06-19_094329_s3_battery_standby_power.md) — soak の親（主目的 go の決着）
