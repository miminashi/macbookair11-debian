# S3'' rerun: VPN watcher + 30/30 BT-PAN-valid cycle clean — プロジェクト初の verified N=30、063543 hang は同条件で再現せず condition が narrower

- **実施日時**: 2026 年 6 月 30 日 04:28 〜 06:15 (JST)
- **位置づけ**: [2026-06-30_030349 S3'' (traffic-only off) 30 cycle / cycle 1 のみ valid confound 発覚レポート](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) の引継ぎ (ii) 「VPN watcher loop + 30 valid cycle rerun」を実施。**結果として 30/30 BT-PAN-valid clean を達成、本プロジェクト初の verified N=30 valid trial set**。但し 063543 (3/3 hang) との対比で 4 候補解釈 (peer/WiFi/hook/baseline) は **discriminated されない** ことが advisor 諮問で確定。次の手 = one-variable-back (WiFi-off で repro)。

## 結論 (先に要約)

1. **30/30 BT-PAN-valid cycle clean** (boot_id `fcc3d4b0...` 不変、suspend_stats success 187→220 +33、fail=0)。**真の N=30 hang 0** = 本プロジェクト初の confound 無し valid trial set。
2. **方法論勝利**: source-IP gate (= 70-h4-probe pre snapshot の `ip xfrm state` 行から local-src を抽出して「BT-PAN (172.20.10.13) / WiFi (192.168.33.145) / inactive」に三分類) と vpn-watcher loop の組合せが機能。33 cycle 中 30 が BT-PAN-valid、3 が VPN inactive (BT-PAN 落ち期間)、**WiFi-known-clean (= VPN over WiFi) 混入はゼロ**。retro-classify で xfrm state count だけでなく source IP を確認する手順を採用し、advisor 指摘 (state count gate は不十分) を解消。
3. **0/30 の strength を定量化**: (1−p)^30 = 4.2% (p=0.10), 0.12% (p=0.20), ~2e-5 (p=0.30)。063543 cell は 3 hang / ~10 cycle ≒ 30%、ユーザ実体験 (「外出時毎度数回でハング」) と整合 → 同条件で 0/30 は very unlikely → **moderate evidence で本セッションの condition は 063543 full setup より narrower**。
4. **4 候補解釈は discriminated されない**: (a)iPhone→iPad peer 差、(b)WiFi off→on の active NIC 差、(c)70/58 hook の suspend-time 処理が race を変えた、(d)063543 baseline が想定より低い — のいずれも 0/30 を predict するため、本実験では区別不能。とくに **「WiFi 介在は hang 要因ではない」は backwards** (WiFi が protective である可能性も同じ確率で残る、本実験では distinguishable でない)。
5. **063543 は依然 valid bedrock**: candidate (d) は corrosive (= 唯一の hang 観測を攻撃する) だが、063543 は per-cell active verification あり + ユーザの実体験 corroborate → **rate が ~10% より低い可能性は残るが hang は real**、bedrock として維持。
6. **次セッション設計のトレード**: 真の 063543 condition = WiFi-off + iPhone + 70/58 hooks 無し。但し hook 無しでは source-IP gate (= valid 判定機構) が使えない → どれを犠牲にするか要設計。one-variable-back の優先候補は **WiFi-off で iPhone+hook 維持** (= peer は iPad のままで OK)。
7. **副次的成果**: vpn-watcher が機能 (T_reconnect ≒ 12 秒、wake 後 20 秒待ちで gate 達成)。途中 BT-PAN が iPad 側 hotspot timeout で 1 回落ち → bluetoothd 内部状態の壊れ (`Operation already in progress 114`) を `systemctl restart bluetooth.service` + iPad ペアリング再構成で復旧。本セッションの運用知見として残る。

## 添付ファイル

- [実装プラン (本セッションで実施したもの、矛盾修正後の最終版)](attachment/2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower/plan.md)
- [Phase 4 retro-classify 表 (全 33 cycle の xfrm source IP 分類)](attachment/2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower/retro-classify.md)
- [Phase 4 全 cycle ログ (58-snapshot-only / vpn-watcher / cycle-watcher journal 抜粋)](attachment/2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower/cycle-logs.txt)

## 通読版: 経緯と本セッションの位置づけ

(本レポート単体で全体像が掴めるよう散文でまとめる。細かい数値・コマンド・cycle ごとの分類は後続のセクションと添付ファイル参照。)

### 何のためにやっているか

MacBook Air 11" (Early 2015) を日常 PC として常用しているユーザに、外出先で Bluetooth テザリング + VPN を使った状態で蓋を閉じてスリープに入ると、数回に一度ハングして強制電源断が必要になるという実害がある。バッテリは十分残っているのに作業状態を喪失するので大きなストレス。本プロジェクトの目的はこのハングを恒久的に消すこと。

### 直前までに分かっていたこと

過去 1 週間、何度か「N 回連続ハングなし」という結果を取ってきた。しかし直前のセッション (030349) で深刻な事実が判明している。**resume 後に VPN が再接続されず、2 cycle 目以降はずっと「VPN なし」の状態で suspend していた**。「VPN なし」では元々ハングが出ないことが過去レポートで確認済なので、つまり「30 回試したが、実質的に有効な試行は 1 回しかなかった」ことになる。

本セッション開始時に過去 2 セッションの状態を遡及的に検証したところ:
- **041006 (btusb を suspend 前に外す実験) は 22 回すべて有効** だった
- **064608 (driver path 25 cycle) は半分くらいに「VPN なし」が混入** していた (cycle 1 + cycle 13-25 ≒ 14 cycle が有効)

つまり「全部が confound」というわけではなく、特定の実験 (S3 系) だけが confound に陥っていた。

### 本セッションの設計

confound に陥った S3 系の rerun を、各 cycle で VPN を確実に再接続させる仕組みを入れて再実施する。具体的には:

- 実機側に常駐するスクリプト (vpn-watcher) を起動し、「BT-PAN が up なのに VPN が inactive なら `nmcli con up GSNet` を発火」を 3 秒間隔で監視する
- 各 cycle のスナップショットで xfrm の本数を記録、本数 ≥ 1 を「有効な試行」の判定条件とする
- 30 回の有効試行が集まるまでユーザに lid close を依頼する

なお、200520 で投入した bnep teardown スクリプト (S3 hook) は意図的に入れない。これは 030349 と同じ条件で、純粋に「素 traffic + bnep/VPN active で suspend に進入する」状態を再現するため。S3 hook 自体の効果測定は本セッション結果次第で別途設計する。

判定枠は事前に 2 つ用意した:
- **30 回連続ハングなし** → 元ハング (063543 の 3/3) と一致しない → 環境差分のどれが効いたかを別途検討
- **1 回以上ハング** → 元ハングを真に再現できた → 機序仮説のラダーを次段に進める

### 実際の流れ

smoke test 2 cycle で vpn-watcher の動作を確認 (wake から VPN 再接続まで約 12 秒)、これを踏まえて「wake 後 20 秒待ってから次の lid close」というガイドで本駆動を開始した。

最初の 18 cycle はトラブルなく順調に valid を集めた。ところが 18 cycle あたりで **iPad 側の Personal Hotspot が timeout で勝手に OFF** になり、3 cycle 分が invalid (VPN なし状態) として記録された。続けて bluetoothd の内部状態が壊れて (`Operation already in progress (114)` で接続試行が詰まる)、`systemctl restart bluetooth.service` だけでは復旧せず、最終的にユーザが iPad 側で**ペアリングを削除して再構成**することで復旧した。

復旧直後にも小さなトラブルがあった。BT-PAN が up した直後の route cache が WiFi 経由のままだったため、VPN が一瞬 **WiFi 経由で確立されてしまう** という副作用が発生 (これは後の advisor 諮問で重要な意味を持つ)。`nmcli con down GSNet` で VPN を一度落として再度 up することで、BT-PAN 経由に強制し直した。

復旧後の 12 cycle は再び安定して valid を集め、通算 33 cycle で 30 valid に到達。**ハングは一度も発生しなかった**。boot_id は起動以来不変、suspend_stats success は 187 → 220 (+33)、fail は 0。

### advisor から指摘された重大な見落とし

集計の段階で「30/30 ハングなし」と書こうとしたところで advisor 諮問したところ、重大な指摘を受けた:

> 「有効性の判定は xfrm state の **本数** しか見ていない。VPN tunnel の outer source IP が BT-PAN (172.20.10.13) か WiFi (192.168.33.145) かは確認していない。本セッション中に WiFi 経由で VPN が確立された瞬間が確かにあった (BT-PAN 復旧直後)。その瞬間に suspend に入っていれば xfrm state=2 で『有効』とカウントされてしまうが、実体は『VPN over WiFi』であり、063543 でハングが出ないと確認済のクリーン対照セルと同じ条件でしかない。」

幸い 70-h4-probe (= 永続的に動いている観測 hook) が xfrm state の生データを含むスナップショットを残していたので、過去レポートでも実施した遡及検証 (retro-classify) と同じ手順で 33 cycle 全件を分類した。結果:

- **30 cycle が BT-PAN 経由** (= 真の有効試行)
- **3 cycle が VPN 無し** (= BT-PAN 落ちの期間)
- **0 cycle が WiFi 経由** (= advisor の懸念は杞憂だった)

WiFi 経由で VPN が確立されていた瞬間は確かに存在したが、その時間帯にはたまたま suspend に入っていなかった (= スナップショットが発火していない)。VPN を down/up で BT-PAN 経由に強制した後に cycle 駆動を再開したため、その後は全 cycle が BT-PAN 経由で確定。

これで「真の 30/30 BT-PAN 経由 valid clean」が成立し、**本プロジェクト初の confound 無しの N=30 有効試行セット** が得られた。

### 0 hang / 30 valid をどう解釈するか

advisor から最終的な解釈の framing を受けた。要点 3 つ:

**(1) 4 つの候補仮説のどれも 0/30 では区別できない。** 本セッションは 063543 と次の 4 点で条件が違うが、どの候補仮説も「ハング無し」を予測するため、本実験の結果ではどれが効いたか決められない:

- (a) BT-PAN の相手が iPhone → iPad に変わった
- (b) WiFi が off → on になった (BT-PAN 750 < WiFi 800 で routing は BT-PAN だが WiFi NIC は active)
- (c) hook が 50/60 のみ → 50/60/70 + 58 になった (本セッションの観測装置自体が条件差分)
- (d) 063543 のハング率自体が想定より低い (3 hang は外れ値だった)

特に「WiFi が active でもハング無しだから WiFi は無関係」と書くのは **逆向きで危険**。WiFi が **ハングを抑制する向きに働いている** 可能性も、同じく排除できない。

**(2) 0/30 という結果の強さは定量化できる。** 同じ条件で本当にハング率が p% なら 30 回連続でハング無しの確率は (1-p)^30 で:

- p = 10% なら 4.2% → 中程度の証拠
- p = 20% なら 0.12% → 強い証拠
- p = 30% なら ~2e-5 → 非常に強い証拠

063543 の対象セルは 3 hang / ~10 cycle ≒ **30%** であり、ユーザの実体験 (「外出時毎度数回でハング」) もこのオーダーに整合する。**本セッションの条件はおそらく 063543 のフル条件より何かしらの意味で狭くなっていて、その狭くなった差分がハングを消した** というのが妥当な解釈。

**(3) 候補 (d) (baseline 低い説) は危険な解釈なので採用しすぎないこと。** これを採用すると、唯一のハング観測である 063543 を「外れ値」として否定することになる。しかし 063543 は各セルで条件成立 (BT-PAN 経由 VPN active) を実際の journal で直接確認しており、ユーザの実体験とも整合している。「ハング率が想定より低い可能性」までは認めるが、「3 hang は real」を覆すには証拠不足。**063543 は依然 bedrock として維持**、候補リストには (d) を残すが明示的に downweight する。

**candidate (c) の sharpen**: 70-h4-probe + 58-snapshot-only は suspend entry で実際に work をしている (各 58KB のディスク書込み、`pm_debug_messages=1`、0.5 秒の sleep、nmcli/ip/pgrep など複数のコマンド実行)。063543 ではこれらの hook は存在しなかった (50-kbd-backlight と 60-s3-soak-log だけだった)。**観測装置自体が条件差分** であり、中立な観察者ではない。「真の 063543 condition を再現するには 70/58 を外すしかない、しかし外すと有効性判定 (source IP retro-classify) もできなくなる」というトレードが残る。

### 次セッションの方向性

候補を 1 つずつ潰していく **one-variable-back** が正しい次の手。優先順位は (b) WiFi-off:

- WiFi だけ off にして、他は本セッションと同じ条件で 30 valid cycle を集める
- 1 回でもハングが出れば「WiFi-on が protective」が決まる
- 0/30 なら更に variable を 1 つ戻す (= peer を iPhone に or hook を最小化)

候補 (c) を試すときには「hook を外すと有効性判定機構も外れる」というトレードをどう扱うかが設計課題。例えば 70-h4-probe を「xfrm state だけ capture して他は省略する minimal mode」に書き直すことで、観測装置の影響を最小化しつつ source-IP gate は維持する設計も考えられる。

詳細は本レポート末尾「次セッション引継ぎ」節参照。

## 前提・目的

- **背景**: [030349](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) の引継ぎ (ii) を実行する。VPN watcher loop で各 cycle に VPN 強制再接続し、xfrm_state>0 を valid gate として 30 valid cycle を集める bare condition rerun。S3 hook (57-bnep-down) は投入しない (030349 と同条件、bnep/VPN active 状態で suspend に進入する)
- **本セッションのみで意味のある追加目的**: 「『N/N clean』系結果に潜む confound を完全に潰す方法論を確立する」 — source-IP gate を採用し、xfrm count だけでなく VPN tunnel の outer source IP まで遡及検証可能な setup を作る
- **役割分担**: hook/watcher デプロイ・状態確認・retro-classify は Claude が ssh で実施。NM GUI 操作 (BT-PAN/GSNet up) と物理 lid close/wake はユーザ手動。BT-PAN 復旧 (iPad ペアリング再構成) もユーザ手動

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、LID0 `*enabled`
- system-sleep フック (本セッション実施中): `50-kbd-backlight`、`58-snapshot-only` (本セッションで新規投入、Phase 6 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後は 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer は iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.0/24`)。実験中は route-metric -1 → 800 に下げて BT-PAN 経路を優先、終了後 auto に revert
- baseline (実験開始時): boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変、030349 終了時から不変)、suspend_stats success=187 fail=0、h4-probe mode=beta、snapshot count=126 pre、NM autoconnect 両方 no、route-metric -1
- 比較対照 063543 との condition 差 (本セッション計画段階で advisor 諮問で明示): peer = iPhone→**iPad**、WiFi = off→**on (metric 800)**、hook = 50/60 のみ→**50/60/70 + 58 (本セッションで投入)**、駆動 = 手動 lid close + 電源ボタン wake (同じ)

## 実施内容と結果

### Phase 0: 開始時の前提確認 (04:28-04:29 JST)

実機 ssh で baseline 7 項目を確認、全て期待値と一致 (Plan 立案フェーズの Explore agent 調査から変化なし、boot_id 不変、suspend_stats 187/0、hooks 3 個、autoconnect 両方 no、transient units 全 inactive)。

### Phase 1: 一時設定 (04:29-04:30 JST)

```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
```

ユーザ操作: iPad テザリング ON → NM GUI で BT-PAN up → GSNet up。

確認: xfrm state count=2、src 172.20.10.13 dst 160.16.210.47 (= VPN over BT-PAN)、route to 10.0.0.1 が `dev nm-xfrm-9871244 src 192.168.83.1` (VPN tunnel 経由)、BT-PAN metric 750 < WiFi metric 800 ✓

### Phase 2: 58-snapshot-only hook + vpn-watcher + cycle-watcher デプロイ (04:30 JST)

#### 58-snapshot-only hook
030349 と同じスクリプト (bnep delta / kbnepd 存在 / netdev 存在 / xfrm state+policy count を logger で記録)、`/usr/lib/systemd/system-sleep/58-snapshot-only` に install。手動 smoke test (`sudo /usr/lib/.../58-snapshot-only pre suspend`) で 4 行正常出力 + xfrm state=2 policy=29 確認。

#### vpn-watcher

```bash
sudo systemd-run --unit=vpn-watcher --collect bash -c '
while true; do
  if ip -br link show enx98e0d98d205e 2>/dev/null | grep -q "UP"; then
    if ! nmcli -t -f NAME con show --active | grep -qx "GSNet"; then
      logger -t vpn-watcher "BT-PAN up but GSNet inactive, re-activating"
      nmcli con up GSNet 2>&1 | logger -t vpn-watcher
      sleep 5
    fi
  fi
  sleep 3
done
'
```

#### cycle-watcher

```bash
sudo systemd-run --unit=cycle-watcher --collect bash -c '
prev=$(cat /sys/power/suspend_stats/success)
while true; do
  curr=$(cat /sys/power/suspend_stats/success)
  if [ "$curr" != "$prev" ]; then
    logger -t cycle-watcher "suspend_stats success: $prev -> $curr (delta=$((curr-prev)))"
    prev=$curr
  fi
  sleep 5
done
'
```

両 unit active 確認。

### Phase 3: smoke test (cycle 1-2) + T_reconnect 測定 (04:30-04:34 JST)

| cycle | lid close 報告 | PM entry (kernel) | snapshot 時刻 | xfrm_state | xfrm_policy | wake 時刻 | IKE_SA established | T_reconnect |
|---|---|---|---|---|---|---|---|---|
| 1 | 04:30:08 | 04:29:59 | 04:29:59 | **2** | 14 | 04:30:30 | 04:30:42 | **12 秒** |
| 2 | 04:32:32 | 04:32:29 | 04:32:29 | **2** | 14 | 04:32:59 | 04:33:11 | **12 秒** |

両 cycle で:
- vpn-watcher 1 回目試行で `Could not find source connection` (BT-PAN がまだ完全 up していない)
- vpn-watcher 2 回目試行で成功
- 約 12 秒で IKE_SA[N] established
- 次 cycle snapshot で xfrm_state=2 (= valid 確定)

Phase 4 の各 cycle ガイドを「**wake 後 20 秒待ってから次 lid close**」と決定。

### Phase 4: 30 valid cycle 駆動 (05:17-06:07 JST、復旧含めて約 50 分)

#### Phase 4 全 33 cycle の概要

| 期間 | cycle 数 | 状況 | xfrm_state 集計 | 判定 |
|---|---|---|---|---|
| 04:29-04:32 (Phase 3 smoke) | 2 | 正常駆動 | state=2 ×2 | valid ×2 |
| 05:17-05:32 (本駆動 cycle 3-18) | 16 | 正常駆動 | state=2 ×16 | valid ×16 |
| 05:33-05:35 (cycle 19-21) | 3 | **BT-PAN 落ち** | state=0 ×3 | invalid ×3 |
| 05:35-05:54 (復旧作業) | 0 | bluetoothd restart + iPad ペアリング再構成 + VPN BT-PAN 経由再確立 | — | — |
| 05:57-06:07 (本駆動 cycle 22-33) | 12 | 正常駆動 | state=2 ×12 | valid ×12 |
| **合計** | **33** | | **state=2 ×30, state=0 ×3** | **valid 30 / invalid 3** |

#### BT-PAN 落ち (cycle 19-21) と復旧の詳細

cycle 18 終了 (05:32:32) 直後、ユーザから「VPN が自動復帰しなくなった」報告。確認すると:
- `nmcli con show --active`: OpenWrt のみ (BT-PAN/GSNet 両方 inactive)
- `bluetoothctl info 34:42:62:16:03:F6`: Paired/Bonded yes, **Connected: no**
- `bluetoothd` log: `connect to 34:42:62:16:03:F6: Operation already in progress (114)` を 14 回連続
- `bnep netdev`: 存在しない

原因: iPad 側 Personal Hotspot の timeout (一定時間使われないと自動 OFF になる) で BT-PAN が切れ、その後 NM の autoconnect=yes が連続再接続を試みた結果、bluetoothd 内部の接続試行 queue が race して詰まった (= `Operation already in progress`)。

復旧手順 (Claude + ユーザ):
1. `sudo nmcli con down "iMiminashiPadPro ネットワーク"` → 試行停止
2. `sudo bluetoothctl disconnect 34:42:62:16:03:F6` → queue クリア (Disconnection successful + Network: disconnect ×5)
3. ユーザに iPad Personal Hotspot OFF → 30 秒待ち → ON 依頼
4. ユーザに NM GUI で BT-PAN up 依頼 → **依然 NAP connect failed: Input/output error**
5. `sudo systemctl restart bluetooth.service` → bluetoothd PID 317551 → 893660 (= 完全再起動)
6. ユーザに NM GUI で BT-PAN up 依頼 → 依然失敗
7. **ユーザに iPad のペアリングを Settings から削除 → 再ペアリング依頼** → これで復旧 (BT-PAN active、bnep netdev 復活)

#### 復旧後の WiFi 経由 VPN 問題

復旧直後の確認で **xfrm src=192.168.33.145** (= WiFi IP) を観測 = VPN が WiFi 経由で確立されてしまった。原因推定: BT-PAN 復旧時に route cache が WiFi 経由のまま残っていて、charon-nm が VPN initiate するときの source 選択が WiFi になった。

対処:
1. `sudo nmcli con down GSNet`
2. 15 秒待ち
3. vpn-watcher が自動再 up を試みるが **「有効なシークレットはありません」** で失敗 (gnome-keyring の secrets cache が NM 側で expire?)
4. ユーザに NM GUI から GSNet を手動 up 依頼 → 成功 (secrets が再 cache、xfrm src=172.20.10.13 = BT-PAN 経由に戻る)

復旧後 (05:57:58〜) は vpn-watcher が安定動作、12 cycle 全 valid。

#### Phase 4 hang 0、boot_id 不変

各 cycle で PM entry/exit ペア完備 (cycle-watcher が suspend_stats delta=1 を 33 回 logger)、device-suspend 所要 480-490 msec の範囲で安定。一度も hang なし。

### Phase 5: 集計 + retro-classify (06:07-06:14 JST)

#### advisor 諮問で発覚した state count gate の限界

Phase 5 初動で「0 hang / 30 valid」と判定する直前に advisor 諮問。指摘 (上記「通読版」参照): **state count gate は WiFi 経由 VPN を valid と誤判定するリスクがある、source IP まで遡及検証すべき**。

#### 70-h4-probe .pre snapshot から source IP retro-classify

```bash
ssh miminashi@macbookair2015.lan '
EPOCH_START=$(date -d "2026-06-30 04:28 JST" +%s)
EPOCH_END=$(date -d "2026-06-30 06:08 JST" +%s)
for f in /var/log/h4-probe/*.pre; do
  TS=$(basename "$f" .pre)
  if [ "$TS" -ge "$EPOCH_START" ] && [ "$TS" -le "$EPOCH_END" ]; then
    LOCAL_SRC=$(sudo sed -n "/^=== ip xfrm state ===$/,/^=== ip xfrm policy ===$/{/^=== /d; p}" "$f" | grep "^src " | awk "{print \$2}" | grep -v "^160\.16\.210\.47" | head -1)
    if [ -z "$LOCAL_SRC" ]; then echo "VPN_INACTIVE"
    elif echo "$LOCAL_SRC" | grep -q "^172\.20\.10"; then echo "BT_PAN_VALID"
    elif echo "$LOCAL_SRC" | grep -q "^192\.168\.33"; then echo "WIFI_KNOWN_CLEAN"
    else echo "OTHER"
    fi
  fi
done | sort | uniq -c
'
```

結果:
```
30 BT_PAN_VALID
 3 VPN_INACTIVE
 0 WIFI_KNOWN_CLEAN
```

→ **真の 30/30 BT-PAN-valid clean** 確定。WiFi 経由になっていた瞬間 (05:51-54) は確かに存在したが、その時間帯には suspend に入っていなかった (= snapshot が発火しなかった)。GSNet down/up で BT-PAN 経由に強制した後の 05:57:58 以降が cycle 駆動再開のタイミング。

#### advisor 確定 framing (Phase 7 解釈の基礎)

(上記「通読版: 0 hang / 30 valid をどう解釈するか」参照)

### Phase 6: クリーンアップ (06:14-06:15 JST)

```bash
sudo systemctl stop vpn-watcher.service cycle-watcher.service
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
```

期待 final 状態 (= 本セッション開始時と設定面同一):

| 項目 | 期待 | 実測 |
|---|---|---|
| hooks | 50/60/70 の 3 個 | ✓ |
| transient units (vpn-watcher / cycle-watcher) | 全 inactive | ✓ |
| NM autoconnect (BT-PAN / GSNet) | 両方 no | ✓ |
| OpenWrt route-metric | -1 | ✓ |
| boot_id | `fcc3d4b0...` 不変 | ✓ |
| suspend_stats | 220/0 (= 187+33) | ✓ |
| snapshot count | 159 pre (= 126+33) | ✓ |

完全に巻き戻し成功。dev 機 (akdx01) 側: 何も書き換えなし。

## 機序評価 (advisor 確定 framing)

### 0/30 で何が分かるか / 何が分からないか

**分かる**: 「本実験の condition (= iPad + WiFi-on + metric 800 + 70/58 hook + vpn-watcher + 手動 lid close + 素 traffic) で 30 連続 clean = hang は出ない」。

**分からない**: 「063543 condition (= iPhone + WiFi-off + hook 無し + 手動 lid close + 素 traffic) との差分のどれが hang を消したか」。本実験は 4 candidate を **どれも discriminate しない** (全候補が clean を predict するため)。

**特に backwards にならないこと**: 「WiFi 介在は hang 要因ではない」 → 本実験で WiFi-on で 0/30 だが、これは WiFi-off だと 0/30 になる可能性 と WiFi-off だと hang 出る可能性 のどちらとも整合する。WiFi が **protective** (= 何らかの mechanism で suspend race を変えて hang を消す) の可能性は同じ確率で残る。

### 0/30 の strength を定量化

5% baseline 仮定 (Plan で挙げた値): (1−0.05)^30 = **21%** → 中立に近い、強い証拠ではない。

10% baseline (memory の数値): (1−0.10)^30 = **4.2%** → moderate evidence。

20% baseline: (1−0.20)^30 = **0.12%** → strong evidence。

30% baseline (063543 cell の実観測 3/10): (1−0.30)^30 = **~2e-5** → very strong evidence。

063543 cell の hang/cycle 比 (3 hang / ~10 cycle 推定 ≒ 30%) と、ユーザの実体験「外出時毎度数回でハング」(= ~20-30% 推定) を踏まえると、**baseline は 10-30% の range が妥当**。同 condition での 0/30 はこの range で all moderate-to-strong evidence で unlikely → **condition は genuinely narrower than 063543 full setup**。

### candidate (d) (baseline 低い説) を corrosive として downweight

(d) を採用すると「063543 の 3 hang は外れ値、真の baseline は near-zero」になり、唯一の hang 観測 (= プロジェクトの bedrock) を攻撃する。063543 は per-cell active verification (= 各 cell で `xfrm src=172.20.10.6` を suspend 直前の journal で確認) あり + ユーザの実体験 corroborate あり → (d) は完全否定しないが explicitly downweighted。

正しい言い方: 「真の baseline は memory の ~10% より低い可能性があるが、063543 の 3 hang は real な観測であり、機序検討の bedrock として依然信頼可能」。

### candidate (c) (hook 影響) を sharpen

70-h4-probe + 58-snapshot-only は **suspend entry で real work を実行**:
- 70-h4-probe: pre/post で各 58KB のスナップショット書込み + `sync` (= disk I/O)、pm_debug_messages=1 echo、ip/lsmod/nmcli/cat 等のコマンド多数 (= CPU 負荷 + syscall)
- 58-snapshot-only: bnep statistics 読込み 0.5s sleep + pgrep/ip コマンド + logger
- 合算で **suspend entry に 100-500ms 程度の追加処理時間 + I/O race の機会**

063543 では `50-kbd-backlight` (LED 制御のみ) + `60-s3-soak-log` (echo + sync 程度) のみ = ほぼ no-op に近い。よって 70/58 が suspend race を変えた可能性は **plausible**。

これは「真の 063543 condition を repro したければ 70/58 hook を外す必要がある」が、外すと source-IP gate も使えなくなる、というトレードを生む。

### candidate (a) (peer 差) と (b) (WiFi 差) について

(a) iPhone (`iMiminashiSE`) → iPad (`iMiminashiPadPro`): 両方 Apple モバイル機器で BT-PAN プロトコル的には同等のはず。但し iOS バージョン差・hotspot 実装差・hci timing 差が device-suspend 段の race を変える可能性は否定できない。本実験では distinguishable でない。

(b) WiFi off → on (metric 800): WiFi NIC (`wl`/broadcom-sta DKMS) が active = suspend 時に device-suspend chain を通る。これが BT-PAN/btusb 側の race を「速める」か「遅らせる」かは未知。WiFi-off で N=30 を集めれば distinguishable。

## 観測上の副次的発見 (運用知見・methodology)

### A. iPad Personal Hotspot は使われないと自動 OFF (timeout)

連続 lid-close cycle 駆動で iPad 側 Personal Hotspot は一度切れる (cycle 18-19 の間、~16 分間隔)。これは iPad の省電力動作で「クライアント接続が無い時間が一定以上続くと自動 OFF」される仕様の可能性。本セッションでは復旧手順を踏んだが、次セッションでは:

- (i) cycle 駆動中に背景 traffic を流して hotspot を keep-alive する (= traffic-gen を再投入、ただし軽量に)
- (ii) iPad 側で Personal Hotspot を常時 ON 維持するアクセサリー設定 (Auto-Lock を Never に等)
- (iii) Personal Hotspot 切れ検出時の自動復旧スクリプト (BT-PAN watcher、vpn-watcher と同型)

を入れることで連続駆動の中断を防げる。

### B. bluetoothd `Operation already in progress (114)` の解消手順

NM autoconnect=yes 設定下で BT peer が disconnect すると、NM が連続再接続を試みる → bluetoothd 内部の queue が race して詰まり、以後の手動接続も全部 fail する状態に陥る。解消手順:

1. `sudo nmcli con down "<BT-PAN connection name>"` (= autoconnect 試行を止める)
2. `sudo bluetoothctl disconnect <peer MAC>` (= queue クリア、log に Disconnection successful + Network: disconnect ×N が出る)
3. (それでも復活しないなら) `sudo systemctl restart bluetooth.service`
4. (それでも復活しないなら) **iPad/iPhone 側のペアリングを Settings から削除 → 再ペアリング**

本セッションは 4 まで必要だった (ペアリング再構成で復旧)。

### C. resume 後の VPN tunnel source が WiFi になる route cache race

BT-PAN 復旧直後 (= bnep netdev は up だが route cache がまだ WiFi 経由) で NM が GSNet を auto-activate すると、charon-nm の initiate 時の source 選択が WiFi になり、VPN tunnel が WiFi 経由 (`xfrm src 192.168.33.145`) で確立されてしまう。これは:

- `nmcli con down GSNet` → vpn-watcher 経由で再 up
- もしくは `sudo nmcli con up GSNet` を default route が BT-PAN 優先になってから手動実行

で BT-PAN 経由に切り替えられる。

含意 (= source-IP gate の必要性): xfrm state count = 2 だけでは「VPN active」しか分からない。本セッションのように WiFi/BT-PAN の race がある環境では、**state count gate + source-IP gate の二段構え** が必要。本セッションは結果的に WiFi-routed cycle がゼロだったが、設計上はこのリスクは常に存在する。

### D. NM の VPN secrets cache の脆さ

GSNet を頻繁に up/down 繰り返した結果、vpn-watcher 経由の `nmcli con up GSNet` が **「有効なシークレットはありません」** で失敗する事象が 1 回発生 (05:54)。原因推定: gnome-keyring と NM の secrets cache の同期失敗、もしくは agent (= GUI ログインユーザの D-Bus 接続) が transient unit (= ssh 経由 root 起動) からは見えない権限問題。

復旧: ユーザが NM GUI から手動で GSNet を up することで secrets が再 cache される。

含意: vpn-watcher は user-session の agent が稼働している前提で動く。長時間 cycle 駆動セッションでは、5-10 cycle ごとに `nmcli con show GSNet` で secrets エラーが出ていないか確認する手順を加えると安全。

### E. 70-h4-probe の multi-purpose snapshot 設計が再び救った

070 の `=== ip xfrm state ===` セクションは 041006 セッション当時、H4 / xfrm 切り分け用の多目的 snapshot として設計されていた。本セッションでは **source IP retro-classify** という設計時に想定していなかった用途で活用され、advisor 指摘 (state count gate の限界) を 5 分で解消できた。

教訓: snapshot 系 hook は「将来の retroactive analysis に有用な情報も含めて広めに capture する」が正解 (200520 confound 発見、本セッション WiFi 混入チェック、いずれも 70-h4-probe のおかげ)。今後の hook 設計もこの方針を維持。

### F. T_reconnect 12 秒の内訳

wake から VPN 再確立までの 12 秒の実観察タイムライン (cycle 1, wake=04:30:30 基準):
- 0 秒 (04:30:30): wake (PM: suspend exit)、この間 kernel resume + WiFi/BT NIC re-init + NM が BT-PAN auto-up が並行進行
- 3 秒 (04:30:33): vpn-watcher 1 回目 poll (BT-PAN UP 検出 + GSNet inactive → `nmcli con up GSNet` 発火) → 即時 `Could not find source connection` で fail (= NM 内部で BT-PAN device.address ↔ connection の binding がまだ完了していない)
- 11 秒 (04:30:41): vpn-watcher 2 回目 poll (= 1 回目失敗後 5 秒待ち + 次 poll 3 秒間隔の合算) → `nmcli con up GSNet` 成功
- 12 秒 (04:30:42): charon-nm が IKE_SA_INIT → AUTH (EAP-MSCHAPV2) → IKE_SA established (= 1 秒で完走)

「wake 後 20 秒待ち」ガイドはこの 12 秒に余裕を 8 秒持たせた値。実測で 1 回目失敗→2 回目成功のパターンが cycle 1, 2 で 100% 再現したので、watcher の sleep を 1 秒に短縮して 1 回目を間に合わせる改良も可能だが、本セッションでは 20 秒待ちで十分なため見送り。

### G. policy=14 の意味

cycle 1 で 030349 と同じく xfrm policy=14 (本来の 29 の半分) を観測。これは IKE_SA delete が進行中で、xfrm policy の片方向だけが残っている過渡状態 (= NM teardown の途中)。これも 030349 で観察された xfrm residue の direct observation と同質で、074509 の H1 機序 (xfrm dev ref leak) を弱く支持する material として継続観察。但し `unregister_netdevice: waiting` は依然 0 件 = H1 確定にはならない。

### H. cycle 1 の VPN teardown は本セッションでは clean に完了した (030349 との重要な差分)

030349 の cycle 1 では IKE_SA delete request が `error writing to socket: Network is unreachable` で 3 回 retransmit fail し、IKE_SA delete が完了しないまま suspend に入った (= 030349 副次的発見 B)。

本セッション cycle 1 (04:30:34) では:
```
04:30:34 charon-nm: 06[IKE] sending DELETE for IKE_SA GSNet[1]
04:30:34 charon-nm: 12[IKE] IKE_SA deleted
04:30:34 charon-nm: 11[KNL] interface nm-xfrm-9871244 deleted
```
**Network is unreachable retransmit 0 件、delete clean 完了**。注: タイムスタンプ 04:30:34 は wake (04:30:30) の 4 秒後 = **suspend に入る前ではなく、resume 後の post-wake teardown**。つまり cycle 1 の VPN teardown は:
- 030349: cycle 1 suspend entry 時に NM が teardown → bnep 消失後の delete 試行 → network unreachable で fail
- 本セッション: cycle 1 suspend entry 時に snapshot を取り (= xfrm state=2 policy=14 = teardown 進行中)、その後 suspend → resume → resume 後の charon-nm が新しい IKE_SA[2] を up する前に古い [1] を delete (= bnep が復活した状態で delete 試行 → clean 完了)

差の原因は teardown のタイミングと bnep netdev の生死順序。autoconnect=yes + vpn-watcher が NM teardown sequence を直接変えたわけではないが、結果として「post-wake で再確立する前に古い SA を綺麗に片付ける」サイクルが成立した。030349 との因果関係は **observed difference であって、設計の直接的帰結ではない** (= 副次的観察)。

含意: 030349 で観察された「kernel suspend に xfrm residue が持ち越し」(state=2 / policy=14) は本セッションでも cycle 1 (04:29:59 snapshot) で観察された (= policy=14)。**suspend entry 時点での xfrm 構造の片寄せは両セッションで共通**で、074509 の H1 機序 (xfrm dev ref leak) を弱く支持する観察として材料は継続的に蓄積。一方 post-wake での delete clean 完了は機序判定とは独立 (= hang が起きるのは suspend entry の dpm_suspend 段なので、その後の post-wake teardown 動作は機序ラダーに直接影響しない)。

### I. 手動 smoke test と systemd-suspend cycle 1 の hook 動作差 (030349 副次的発見 F の本セッション再現)

本セッションでも 030349 と同じパターンを観測:

| 実行 context | 時刻 | bnep_session kthread | bnep netdev | xfrm policy |
|---|---|---|---|---|
| 手動 (`pre suspend` 引数) | 04:29:00 | **alive** | **present** | 29 |
| cycle 1 (systemd-suspend.service) | 04:29:59 | **NOT FOUND** | **MISSING** | 14 |

手動実行は systemd-suspend.service の context ではないので NM teardown は走らず、bnep_session/netdev が alive のままで snapshot される (= S3'' 設計が当初想定した「bnep up のまま」状態)。cycle 1 で systemd-suspend が走った時点では既に NM が teardown を完了している。

**この差は再現性のある reproducible finding**: 030349 と本セッションで 2 回独立に観察された。「system-sleep/pre フックは NM teardown 完了後に走る、bnep を up のまま suspend させる手法は構造的に不可能」が確定。S3''' (= bnep を up のまま suspend) を将来試みる場合は systemd-sleep service 自体に手を入れる必要があり、ROI 低。

### J. vpn-watcher と NM autoconnect は協調動作する (autoconnect=yes だけでは不十分)

本セッションで autoconnect=yes 設定にしたが、resume 後に NM autoconnect だけでは GSNet が確実に再接続されない (= 030349 で確認した既知の問題)。vpn-watcher は autoconnect の補助として機能し、両者協調で valid 状態を維持:

- BT-PAN は autoconnect=yes で resume 後すぐ activate される (NM 側の標準動作)
- GSNet は autoconnect=yes だが NM の依存解決が strongSwan/charon-nm では機能せず、 BT-PAN active だけでは auto-up されない
- vpn-watcher が 3 秒 poll で `bnep0 UP かつ GSNet inactive` を検出 → `nmcli con up GSNet` を発火
- 1 回目試行は `Could not find source connection` で fail (推定: BT-PAN device.address ↔ NM connection の binding が NM 内部でまだ完了していない)
- 2 回目試行 (= 3 秒後の次 poll cycle、もしくは 5 秒待ち後) で成功

含意: 「vpn-watcher を入れたから autoconnect=no で良い」ではなく、両者を併用するのが現実的な運用パターン。autoconnect=no にすると watcher が `nmcli con up` を初回から打つことになるが、それでも BT-PAN binding 完了待ちは同じく必要なので、結果はほぼ同じ。

### K. iPad ペアリング再構成は iPad+macbook 双方のリセットが必要 (bluetoothd restart だけでは不十分)

本セッションの BT-PAN 復旧手順で、`systemctl restart bluetooth.service` だけでは復旧せず、ユーザに iPad のペアリングを Settings から削除 → 再ペアリングしてもらって初めて復旧した。これは:

- bluetoothd restart は macbook 側の Bluetooth スタックの内部状態 (queue, sessions, profile registrations) をリセット
- 但し iPad 側の bonding state (= pairing key, link key cache) は macbook 側 restart で同期されない
- iPad 側で device を delete することで iPad の bonding state をリセット
- macbook 側でも自動的に iPad の bonding state がリセットされる (`bluetoothctl info <MAC>` で Bonded: no になる)
- 双方で fresh pair すると、新しい bonding key で接続が成立する

NM connection の UUID (`a6300eea-6e89-45f0-b494-8d60cc8515e1`) はペアリング再構成後も維持された (= connection 設定 = device.address+name 等は変わらず)、本セッションは connection 名 `iMiminashiPadPro ネットワーク` で connection 自体は再利用された。

含意: 次セッション以降の運用で BT-PAN が同様に詰まった場合、まず bluetoothd restart を試し、ダメなら iPad ペアリング再構成、の順で復旧する。NM connection を delete する必要は通常無い。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 04:28-04:29 | Phase 0 | baseline 確認 (suspend_stats 187/0, boot_id fcc3d4b0..., hooks 3 個, autoconnect no) |
| 04:29-04:30 | Phase 1 | NM autoconnect=yes + route-metric=800 + ユーザ操作 (iPad テザリング ON, BT-PAN/GSNet up), xfrm src=172.20.10.13 確認 |
| 04:30-04:30 | Phase 2 | 58-snapshot-only hook 投入 + 手動 smoke test (state=2 policy=29) + vpn-watcher/cycle-watcher 起動 |
| 04:30-04:34 | Phase 3 | smoke test cycle 1-2 (T_reconnect 12 秒、wake 後 20 秒待ちガイド決定) |
| 05:17-05:32 | Phase 4 part 1 | 本駆動 cycle 3-18 = 16 cycle 全 valid (xfrm src=172.20.10.13 維持) |
| 05:33-05:35 | Phase 4 BT-PAN 落ち | cycle 19-21 (= invalid, xfrm state=0, BT-PAN disconnect, bluetoothd queue 詰まり) |
| 05:35-05:54 | Phase 4 復旧 | nmcli con down + bluetoothctl disconnect + bluetooth.service restart + iPad ペアリング再構成 + VPN WiFi 経由化 → BT-PAN 経由再強制 + secrets エラー対応 |
| 05:57-06:07 | Phase 4 part 2 | 本駆動 cycle 22-33 = 12 cycle 全 valid (xfrm src=172.20.10.13 維持) |
| 06:07-06:08 | 集計 | suspend_stats 220/0, 通算 33 cycle, valid 30 (= xfrm state=2), invalid 3 (= state=0) |
| 06:08-06:14 | advisor 諮問 + retro-classify | state count gate の限界判明 → 70-h4-probe pre snapshot から source IP 三分類 → **30 BT_PAN_VALID + 3 VPN_INACTIVE + 0 WIFI_KNOWN_CLEAN** 確定 |
| 06:14-06:15 | Phase 6 cleanup | hooks 3 個に戻し + transient units stop + NM autoconnect=no + route-metric=-1, 全項目 baseline 復帰 |
| 06:15-06:30 | Phase 7 | advisor 再諮問 (機序解釈最終 framing) + 本レポート作成 + メモリ更新 |

実験全体所要時間: 約 2 時間。Phase 4 cycle 駆動は実駆動 ~30 分 (BT-PAN 落ち復旧除く)、復旧 ~20 分、駆動再開 ~10 分。

## 検討して除外した事項

- **WiFi-off で本セッションを実施**: 設計検討段階で「063543 と同条件に近づけるべきだが、WiFi-off だと ssh が切れて observation 不能」のトレードで WiFi-on (metric 800) を選択。次セッションで WiFi-off の対照を取ることで初めて (b) candidate を discriminate できる
- **70/58 hook を最小化**: 同じく 063543 の hook 無し condition との差分を消すため hook を外す案 — 但し source-IP gate (= valid 判定) が使えなくなるトレードあり。本セッションは「valid を保証する設計」を優先
- **iPhone (`iMiminashiSE`) で repro**: peer 差 candidate (a) を変える案 — iPad と iPhone の両方を切り替えながら駆動するのは現実的でないため、本セッションは iPad で統一
- **traffic-gen 再投入**: 063543 は素 traffic で出た事象 + 064608 で「heavy traffic 中の driver path は構造的に維持不能」と判明 → 本セッションも素 traffic で実施し、traffic 量を hang factor から除外

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-06-30 06:15 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット (xfrm state capture が retro-classify を救った、設計の正しさが本セッションでも実証) |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 (前セッションから) | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで +33 ペア = 66 ファイル、累計 159 pre) | 本セッション 33 cycle の証拠 + 将来 retro-classify 素材 |
| vpn-watcher.service | **削除済** (transient unit、stop で消える) | VPN reconnect 自動化 |
| cycle-watcher.service | **削除済** (同上) | 進捗監視 |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | revert 済 (-1 = auto) | |

実機の suspend_stats: success 220, fail 0 (start 187 → +33)。boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動時刻 2026-06-28 12:32:55 JST、本セッション終了時 uptime ~1 日 18 時間、起動以来不変)。

dev 機 (akdx01) 側: 何も書き換えなし。`src/linux-6.12.y`, `src/debian-6.12.94-1` は前セッションから残置。

## 次セッション引継ぎ

### メモリ更新済 (本セッション終了時)

- `s2idle-btvpn-hang-mechanism-ladder`: 全面改訂。「N/N clean」系結果の取り扱いの methodology 確立 (= source-IP gate 必須)、本セッション 30/30 BT_PAN_valid clean の含意、4 candidate が discriminate されない事実、063543 を bedrock として維持する判断、次セッション設計指針 (= WiFi-off で one-variable-back) を反映
- `MEMORY.md`: index の description を本セッション結果に合わせて訂正

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
echo "=== boot_id (期待: fcc3d4b0... 不変 or 再起動) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats (期待: success=220 fail=0) ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting" || echo "0"
echo "=== transient units 残存していないか ==="
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

### 推奨の次の手 (優先順位順)

#### (i) **WiFi-off で 30 valid cycle (one-variable-back)** (最優先、~80-100 分)

本セッション「(b) WiFi off→on の active NIC 差」を discriminate する設計:
- WiFi off (= `sudo nmcli con down OpenWrt` または `nmcli radio wifi off`)
- iPad + 70/58 hook + vpn-watcher は本セッションと同じ維持
- ssh が切れる対策: 実機側に **すべての操作を transient unit で常駐** (= 本セッション同様)、Claude は ssh 復活を待って状態確認
- 30 valid cycle 駆動
- 結果:
  - **1+ hang / 30 valid** → 「WiFi-on が protective」確定 = candidate (b) 採用、次は why WiFi-on protective の機序解明 (= WiFi NIC が device-suspend chain の何かを変える、specific には wl ドライバの suspend ordering or IRQ scheduling など)
  - **0/30 BT_PAN_valid** → WiFi-off も 0/30 → 次の variable へ (= iPhone peer or hook 最小化)

ssh 切れ対策の具体:
```bash
# 実機側で先に transient driver を仕込む (= ssh 切れても駆動継続)
sudo systemd-run --unit=cycle-helper --collect bash -c '
# ユーザ手動 cycle 待ちなら不要、driver mode (rtcwake + systemctl suspend) なら 064608 v3 手順
# 本セッション同様の手動 lid close mode のままで OK、ssh は復活を待つ
'
```

#### (ii) 64608 / 041006 を source-IP retro-classify でも検証 (~10 分、cycle 駆動不要)

本セッション開始時に Explore agent で xfrm state count ベースで retro-classify したが、advisor 指摘を踏まえて **source IP まで遡及検証** する。041006 (22/22 valid claim) と 064608 (~14 valid claim) は本セッションと同じ環境 (= iPad + WiFi-on metric 800 + autoconnect yes) で実施されていたので、WiFi 経由 cycle が混入していた可能性は本セッションと同様にあり得る。

```bash
# 041006 期間: 2026-06-29 03:25 〜 03:56 JST
# 064608 期間: 2026-06-29 05:43 〜 06:43 JST
# 本セッション Phase 5 と同じスクリプトで EPOCH を変えて実行
```

#### (iii) 70/58 hook を最小化した condition で valid cycle (~80 分、advanced)

candidate (c) (hook 影響) を discriminate する設計。但し hook を外すと source-IP gate も使えなくなるトレードあり。代替案: 70-h4-probe の write を no-op に近づける minimal mode を作る (= xfrm state は capture するが他は skip、 50 行 → 5 行程度に slim down) → これで source-IP gate を維持しつつ instrumentation 影響を最小化。

### 注意事項

- **「N/N clean」系結果を機序判定に使う前に retro-classify で source IP を確認すること** (state count だけでは不十分、本セッション methodology 教訓)
- **063543 の 3/3 hang は依然 valid bedrock**: per-cell active verification あり + ユーザ実体験 corroborate あり。本セッション 0/30 で「baseline 低い」候補 (d) は corrosive なので explicitly downweighted、bedrock 維持
- **70-h4-probe の xfrm state capture は維持すべき**: retro-classify の価値が本セッションでも再証明された。今後の hook も「将来の再分析に有用な multi-purpose snapshot」を意識
- **iPad Personal Hotspot timeout 対策**: 連続 lid-close 駆動中の自動 OFF を防ぐため、cycle 駆動の合間に軽量 ping を流す or iPad 側設定で常時 ON 維持。次セッションでも復旧手順を踏むコストを避けるため事前対策推奨
- **VPN secrets cache の脆さ**: 5-10 cycle ごとに secrets エラー有無を確認 (vpn-watcher の journal に「有効なシークレットはありません」が出ていないか)、出たら GUI から手動 up で復旧

## 関連レポート

- [2026-06-30_030349 セッション: S3'' 30 cycle / cycle 1 のみ valid confound](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) — 本セッションの起点、引継ぎ (ii) を実行
- [2026-06-29_200520 セッション: S3 (bnep teardown) 32 cycle / cycle 1 のみ valid confound](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) — 同 confound、本セッション開始時に再確認
- [2026-06-29_064608 セッション: driver path 25 cycle / ~14 valid (要 source-IP retro-classify)](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) — 次セッションで再 retro-classify 候補
- [2026-06-29_041006 セッション: S1 (btusb pre-unload) 22 cycle / 22 fully valid (xfrm count ベース) — 要 source-IP retro-classify](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) — 同上
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — **bedrock として維持** (本セッション 0/30 は同 condition での「不一致」だが downgrade されない、per-cell active verification ありかつ実体験 corroborate)
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
