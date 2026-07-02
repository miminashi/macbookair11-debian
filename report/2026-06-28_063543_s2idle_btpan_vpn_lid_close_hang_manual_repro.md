# s2idle でも「BT-PANテザリング × VPN」併用 lid close でハング再現 — 手動操作による factorial 切り分け

- **実施日時**: 2026年6月28日 06:35 (JST)
- **位置づけ**: [2026-06-28_021019 レポート](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)（真の s2idle 初実証 + AC 自動ループで BT-PAN ありでも 10/10 クリーン）の**続編・追試**。前回は AC・s2idle・**VPN なし**・`systemctl suspend` 駆動だった。今回は**ユーザの手動操作（実 lid close）**で、前回未検証だった **VPN 併用**を軸に条件を factorial に振り、s2idle でハングが再現するかを切り分けた。

## 結論（先に要約）

1. **真の s2idle・AC でも、「BT-PAN テザリング × VPN」を併用して lid close すると数回以内にハングする。3 回独立に再現（3/3）。** 強制電源断（電源ボタン長押し）が必須。電源ボタン短押しでは復帰しない＝表示オフではなく**システム停止（true hang）**。
2. **単独要素ではハングしない（factorial 切り分け）**:
   - **BT-PAN 単独**（VPN なし）= **0 / 15**（＋前回 0/10）クリーン
   - **VPN 単独**（WiFi 経由, BT なし）= **0 / 11** クリーン
   - **無線なし**（WiFi のみ, BT/VPN なし）= **0 / 9** クリーン
   - **BT-PAN + VPN 併用**（VPN を BT-PAN 上で張る）= **3 ハング**
3. つまり s2idle ハングのトリガーは **「BT-PAN テザリングをトランスポートにした VPN(strongSwan/charon/XFRM)」という相互作用条件**に局在する。どちらの単独要素でも出ず、併用でのみ 3/3 で出た。
4. **この再現はユーザの実使用の実感と一致**（外出時 BT-PAN+VPN 運用で「毎度、数回スリープするとハング」）。test artifact ではなく実運用の故障そのもの。
5. **含意**: 6/27 レポートの「真因は BT 非依存の内在 S3-deep hang、BT-PAN は単なる stressor」という見立ては **s2idle には当てはまらない**。s2idle 退避でも本条件のハングは消えていなかった。

## 添付ファイル

- [監視プロトコル（プランファイル）](attachment/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro/plan.md)
- [soak ログ実験窓 (s3-soak.log の SLEEP/WAKE)](attachment/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro/s3-soak-experiment-window.log)
- [3 ハングの journal 抜粋（入眠直前〜停止位置）](attachment/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro/hang-journal-excerpts.log)

## 前提・目的

- **事象（ユーザ報告・既往）**: 外出中に BT テザリング + VPN を使っているとき、数回スリープさせると毎度ハングしていた。
- **目的**: 前回 2026-06-28_021019 の「AC・s2idle・BT-PAN（VPN なし）で 10/10 クリーン」と矛盾するこの実感を、**手動 lid close + 条件 factorial** で切り分ける。特に前回欠けていた **VPN 併用**の寄与を確定する。
- **前提（スリープ構成）**: 6/27 の決着どおり **s2idle ロールバック状態**。`mem_sleep=[s2idle]` 選択、GRUB `mem_sleep_default=s2idle`（恒久）、`s3-deep-apply.service` disabled、`LID0 *enabled`（lid wake 有効）。`60-s3-soak-log` フックの deep 強制 2 行は 6/28 にコメント無効化済（s2idle が維持される）。
- **役割分担**: ハングは強制電源断が必須のため、**操作（BT/VPN/WiFi の on/off、lid close、電源ボタン）はすべてユーザが実機の前で手動実施**。Claude は ssh 越しに read-only で状態確認・ログ突合のみ（suspend を一切注入しない手動セッション）。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: s2idle（runtime 選択・GRUB 恒久）。AC 蓋閉じ = 素の `suspend`（logind drop-in `10-suspend-then-hibernate.conf`: `HandleLidSwitchExternalPower=suspend`）。battery 蓋閉じ = `suspend-then-hibernate`（`SuspendEstimationSec=30min`, hibernate 先 `/dev/sda3`）。**本実験は全て AC 給電のため素の suspend**。
- system-sleep フック: `50-kbd-backlight`, `60-s3-soak-log`（durable な SLEEP/WAKE ログ。deep 強制は無効化済）。
- 電源: 全サイクル **AC 給電**（`ADP1/online=1`）、バッテリ 87%。
- **Bluetooth/テザリング**: `btusb`(USB)/`hci0`、NM 接続 `iMiminashiSE ネットワーク`(type=bluetooth)、peer `CC:60:23:AF:2C:60`。PAN netdev `enx98e0d98d205e`（旧 bnep0）、IP `172.20.10.6/28`（iPhone テザリング既定サブネット）。
- **VPN**: NM 接続 `GSNet`(type=vpn) = strongSwan IPsec/IKEv2（`charon-nm`, MOBIKE, GW `160.16.210.47`, 内部 `192.168.83.1`）。
- **WiFi**: `wl`(broadcom-sta DKMS)/`wlp3s0`、接続 `OpenWrt`（WiFi 時の割当 IP は `192.168.33.x` 系）。
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。本セッションはサンドボックス外から ssh。

## 調査結果

### 1. ハング 3 件の事実確定（true hang・全て s2idle・AC・素 suspend）

各ハングは **「s3-soak.log に SLEEP 行あり → 対応 WAKE 無し → 次行が BOOT」** + **boot_id 変化 + uptime リセット**で確定。停止位置は 3 件とも **`kbd-backlight-sleep: pre/suspend: saved=0 set->0`（journald 最終行）= system-sleep pre フック完走後、実 suspend 遷移中**で、`PM: suspend exit` を欠く（過去の deep ハング #1/#2/#4 と同一シグネチャ。ただし**今回は deep ではなく s2idle**）。

| # | ハング boot | SLEEP(入眠) | mode | 電源/type | 次 BOOT | VPN 端点（=トランスポート） | ハング前の連続成功 |
|---|---|---|---|---|---|---|---|
| 1 | `1bc7fb70` | 04:28:21 | s2idle | AC / suspend | 04:30:56 | `172.20.10.6`(BT-PAN) | 0（BT+VPN 投入後の初回 lid-close で一発。同 boot の 02:xx 自動実験は VPN 無しで別条件） |
| 2 | `370de629` | 05:19:45 | s2idle | AC / suspend | 05:22:50 | `172.20.10.6`(BT-PAN) | 1 回（05:19:00→14 正常）→ 2回目 |
| 3 | `7c44b92c` | 06:26:43 | s2idle | AC / suspend | 06:28:19 | `172.20.10.6`(BT-PAN) | **6 回正常 → 7回目** |

- モード判定: 各ハング boot とも、同 boot 内の他 suspend は journal 上すべて `PM: suspend entry (s2idle)`。当該ハング suspend の `PM: suspend entry` 行自体は journald flush 前に停止して残らないが、(a) mem_sleep s2idle 選択、(b) deep 強制フック無効、(c) 同 boot 全サイクル s2idle、(d) soak ログ `type=suspend ac=1` から **s2idle・素 suspend と確定**。
- VPN は 3 件とも入眠直前に `deleting IKE_SA GSNet[N] between 172.20.10.6 … 160.16.210.47`＝**VPN のローカル端点が BT-PAN の IP** で、トンネルが BT-PAN 上に載っていた。BT-PAN(`enx98e0d98d205e`)・peer(`CC:60:23:AF:2C:60`)も active。

### 2. factorial 切り分け（クリーン対照 3 セルは同一 boot `7c44b92c` で連続取得／ハングは各々別 boot）

全て **AC・s2idle・実 lid close**。各セルとも各 suspend で当該要素が**実 active だったことをログで検証**（陰性結果の妥当性担保）。クリーンな対照 3 セル（無線なし／VPN-over-WiFi／BT-PAN 単独）は同一 boot `7c44b92c` で連続取得。BT-PAN+VPN セルの 3 ハングは **#1=`1bc7fb70`・#2=`370de629`・#3=`7c44b92c` の 3 つの別 boot**にまたがる（ハングは強制電源断＝boot が変わるため、1 boot に複数ハングは原理的に乗らない）。

| WiFi | BT-PAN(実up) | VPN(経路) | サイクル | ハング | active 検証 |
|---|---|---|---|---|---|
| on | off | off | 9 | **0** | NM active=WiFi のみ、bnep/charon 痕跡ゼロ |
| on | off | **on**（WiFi 経由 `192.168.33.145`）| 11 | **0** | `deleting IKE_SA GSNet[1..10]`＝**10/11 入眠で VPN active 確認**（端点=WiFi IP）。1 サイクル(05:52:35)のみ IKE delete 無し＝当該入眠時は VPN 非アクティブの可能性 |
| off | **on** | off | 15 | **0** | enx98/bnep teardown 15 回（端点 `172.20.10.6`）、IKE_SA ゼロ |
| off | **on** | **on**（BT-PAN 経由 `172.20.10.6`）| ~10（3 boot 合算; #3 boot で 6 正常+1 hang 等）| **3** | IKE_SA over `172.20.10.6` + BT-PAN teardown を毎入眠記録 |
| off | **on** | off | 10 | **0** | （前回 2026-06-28_021019 Phase B; BT-PAN active 通信あり）|

- 裏付け: クリーン対照 3 セルを取得した区間（hang #3 発生**前**の boot `7c44b92c`）は `PM: suspend entry (s2idle)`=`exit`=35 で**件数一致**、soak ログの該当窓は SLEEP/WAKE が**全ペア・全件 drm_err=0**、その間 boot_id **不変**。※この boot `7c44b92c` 自体は末尾の BT-PAN+VPN 再試行で hang #3 を起こして終了している（対照 3 セルはその前段）。
- **VPN 単独が主因ではない**: VPN を WiFi 経由で 11 サイクル張って（10/11 入眠で active 確認）クリーン → 「VPN teardown 自体が原因」説は棄却。
- **BT-PAN 単独が主因でもない**: BT-PAN を実トランスポートにしつつ VPN なしで 15/15 クリーン（＋前回 10/10）。
- → **ハングは「BT-PAN を下回りにした VPN」併用でのみ顕在化**。XFRM/charon の suspend teardown が、トランスポートが BT-PAN(`enx98…`/btusb) のときだけ実 suspend 遷移を固める像。

### 3. 確率的だが数回以内に顕在化／実使用と一致

ハングまでの連続成功は #1=0・#2=1・#3=6 とばらつくが、いずれも数回以内に顕在化。これは**ユーザの実使用の実感（外出時 BT-PAN+VPN で毎度、数回スリープするとハング）と一致**する。制御下の再現が実運用の故障を捉えていることの強い傍証で、test artifact（高速サイクル等の人工副産物）ではない。

### 4. 検討して除外した事項・観測上の限界

- **`drmModeAtomicCommit: 無効な引数です`（gnome-shell の Cursor update failed）は red herring**。ハングした boot だけでなく**正常 suspend の直前にも毎回出る**（例: 06:23:11→正常復帰、06:24:32→正常復帰）。i915/drm 絡みでハング兆候に見えるが**ハング非特異**＝蓋閉じで表示を落とす際の良性アーティファクト。将来この行を真因として追わないこと。
- **入眠側ハングか復帰側ハングかはログから判別不能**。`PM: suspend exit` の欠落は「suspend entry の device-suspend 中で停止」と「正常に眠ったが resume できず停止」の**両方と整合**する（journald は正常 suspend でも resume まで disk flush しないため、停止位置の最終可視行は両ケースで同じになる＝[2026-05-31](2026-05-31_132125_s3_hang_switch_to_s2idle.md) の「可視性ゼロ」）。ユーザ体感「復帰させようとしたらハング」は phenomenology であり、ログ上は side を確定できていない。本レポートの「実 suspend 遷移中で停止」はこの不確定性を含む表現。
- **滞在時間依存はない**: 手動・rtcwake 不使用のため各成功サイクルの `asleep_s` は短い（3〜14s 中心、最大 206s）が、ハングは滞在時間に依らず入眠/復帰の遷移で顕在化した。

### 5. 6/27 レポートとの整合・含意

- 6/27 追記4 は「真因 = BT 非依存の内在 S3-**deep** hang、BT-PAN は stressor」とした。これは **deep モードの #4（btusb 除去でもハング）**には妥当だが、**s2idle には当てはまらない**。s2idle では BT-PAN を完全に持っていても VPN 併用がなければ出ず（25/25 クリーン）、**「BT-PAN × VPN」の相互作用が独立したトリガー**として残っている。
- つまり s2idle 退避は「deep 固有の内在 hang」は回避しても、**本条件（BT-PAN+VPN+lid close）のハングは回避できていない**。ユーザが「s2idle に戻したのに BT テザリングでハングする」と感じた現象の、少なくとも一部の実体がこれ（前回レポートは「ロールバック不完全で実体は deep」と整理したが、本実験は**真の s2idle でも本条件なら再現する**ことを別途確定した）。

## 再現方法

操作はすべて実機の前で手動。ハング時は **物理電源ボタン長押しでの強制電源断が必須**（短押しでは復帰しない）。Claude 側はすべて read-only の ssh 確認。

1. **前提状態の確認**（s2idle ロールバックが実効していること）:
   ```bash
   ssh miminashi@macbookair2015.lan 'cat /sys/power/mem_sleep; grep LID0 /proc/acpi/wakeup; systemctl is-enabled s3-deep-apply.service'
   # 期待: [s2idle] / LID0 *enabled / disabled
   ```
2. **ハング条件**（AC 給電のまま）: WiFi off、**BT テザリングを up**（`iMiminashiSE ネットワーク`）、**VPN `GSNet` を up**（VPN が BT-PAN 経由＝端点 `172.20.10.6` になることを確認）→ **lid close で数回スリープ／復帰を繰り返す**。数回以内にハング。
3. **状況確認（再利用コマンド）**: ssh 到達可なら以下、不可なら「suspend 中かハングか不明、起こしてから再確認」（**ssh 不通だけではハング判定しない**。正常 suspend 中も不通）:
   ```bash
   ssh miminashi@macbookair2015.lan '
     echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)  uptime=$(uptime -p) since=$(uptime -s)"
     echo "ac=$(cat /sys/class/power_supply/ADP1/online) cap=$(cat /sys/class/power_supply/BAT0/capacity)% mem_sleep=$(cat /sys/power/mem_sleep)"
     sudo tail -n 6 /var/log/s3-soak.log
     nmcli -t -f NAME,TYPE,DEVICE con show --active | grep -Ei "bluetooth|vpn"
     sudo journalctl -b 0 -g "PM: suspend (entry|exit)" -o cat | sort | uniq -c'
   ```
4. **ハング判定**: boot_id がベースラインから**変化** + s3-soak.log に **SLEEP→(WAKE 無し)→BOOT** + `PM: suspend exit` 欠落。条件は当該ハング boot の journal で `deleting IKE_SA GSNet … 172.20.10.6`（VPN over BT-PAN）と enx98/bnep teardown を確認。
5. **対照（陰性確認）**: 「BT-PAN のみ」「VPN over WiFi のみ」「無線なし」を各 ~10 回 → いずれもクリーン（boot_id 不変・SLEEP/WAKE 全ペア・drm_err=0）。

## 留意・次の一手

- **本実験は全て AC・s2idle・各セル ~10〜15 サイクル**。**battery/STH での BT-PAN+VPN は未検証**（電源状態の寄与は別途）。ただし実使用（外出時＝battery が主）でも同様に出ていたとの証言があり、AC 限定の現象ではない可能性が高い。
- **対策の方向性（重要な注意 — 論理 down では不足が既にログで示唆）**: **VPN の論理 down は全ハングで既に起きている**。各ハング boot を見ると `deleting IKE_SA GSNet` と bnep/xfrm teardown は **:42（`Reached target sleep.target` :43 より前）に完了**しており、ハングはその**後**の `kbd-backlight-sleep: pre/suspend` を経た**カーネル device-suspend 段階**で起きる。つまり NM は毎回 suspend 前に VPN/BT-PAN を soft teardown 済みで、**それでもハングする**。よって「suspend 前フックで `nmcli connection down GSNet` を再実行」する案は、システムが既にやっていることの反復にすぎず**有望ではない**（6/27 の「radio off では不十分・`modprobe -r btusb` が必要だった」と同型の罠）。
  - **検証すべき仮説（fix ではなく hypothesis として）**:
    - (a) 6/27 の `55-net-teardown`(B-2)＝**btusb を module unload** して BT-PAN トランスポート自体を device-suspend 経路から除去する案を**再有効化して本条件で試す**。BT-PAN を経路から消せば「BT-PAN × VPN」条件が崩れ s2idle でクリーンになる可能性（deep の BT 非依存 #4 には効かなかったが、s2idle の本条件は別物）。
    - (b) **xfrm インタフェース除去がカーネル suspend 前に完了している**か（残留 xfrm device が device-suspend を固めていないか）を確認する。
  - 運用上の即時 stopgap は「BT-PAN+VPN 使用中は lid close しない（明示的にスリープさせない／使用後に VPN・BT を切ってから蓋を閉じる）」。
- **mem_sleep の含意**: s2idle でも出る以上、待機電力目的の deep 採用是非とは独立に本条件の対策が要る。
- 残置物（撤去任意）: `/usr/local/bin/susp-test-driver.sh`、`/var/log/susp-test.log`、退避済 `60-s3-soak-log.bak`。本実験では driver 不使用（手動）。

## 関連レポート

- [2026-06-28_021019 s2idle ロールバック不完全の発見 + AC 自動ループ BT-PAN 10/10 クリーン](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) — 本件の直接の親（VPN なし条件のクリーン結果との対比が本件の出発点）
- [2026-06-27_072510 BT テザリング lid close で計4ハング・s2idle ロールバック決定](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) — deep モードでの BT/VPN 相関と「内在 S3-deep hang」結論（本件は s2idle では別トリガーが残ることを示す）
- [2026-05-31 S3 hang により s2idle へ切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md) — 「停止位置はログから特定不能」の根拠
