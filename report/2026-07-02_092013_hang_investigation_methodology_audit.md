# ハングアップ調査 2 ヶ月間の方法論監査 — アプローチの問題点と見落としの棚卸し

- **実施日時**: 2026年7月2日 09:20 JST
- **レビュー実施**: Claude Fable 5 (`claude-fable-5`)
- **監査対象**: 2026-05-10〜2026-07-01 のハングアップ対策関連レポート **29 本** (下記「参照レポート一覧」)
- **性格**: 本レポートは **既存レポートの読解ベースの監査** であり、新規の実機実験は一切行っていない

## 添付ファイル

- [監査プラン](attachment/2026-07-02_092013_hang_investigation_methodology_audit/plan.md)

---

## 1. 概要 (通読用)

このセクションだけで全体像がつかめるよう、細かい数値や記号は省いて書く。詳細は 3 章以降にある。

### この 2 ヶ月で何が起きたか

発端は 5 月、「蓋を閉じてスリープさせると、たまに二度と起きてこなくなる」という故障だった。週に 1 回弱というまれな頻度でしか起きず、起きたときはログも残らない。最初の 1 ヶ月は、カーネルの起動オプションを 1 つずつ変えては数週間様子を見る、という手探りの対処を 3 回繰り返したが、いずれも効かなかった。そこで 5 月末、スリープの方式そのものを従来の S3 (deep) から s2idle という別方式に切り替えたところ、翌日にまたハングした。「スリープ方式が原因」という見立ては崩れ、調査は仕切り直しになった。

6 月中旬には並行して、「バッテリが切れる前に自動でハイバネートする仕組みが実は一度も動いていなかった」という別の問題をソースコードの読解で突き止めて修理し、実際に残量 3% で自動ハイバネートが発火するところまで確認できた。これはこの 2 ヶ月で最もきれいに決着した成果である。

6 月中旬〜下旬は、いったん捨てた S3 方式を「待機電力が s2idle の 10 分の 1 で済む」という利点のために復活させる挑戦をした。電力面の検証は堅実で、可逆な形で本採用前の 2 週間試験 (soak) も始めたが、その最中に 4 回ハングが起きた。一時は「Bluetooth テザリングが真因」と結論しかけたものの、Bluetooth ドライバを完全に外してもハングする例が出て自ら反証し、S3 復活は見送り (no-go)、s2idle に戻した。

ところが戻す作業に不備があり、「s2idle に戻したはずが実際は毎回 deep で寝ていた」ことが後日発覚する。これを直して初めて「本物の s2idle」での検証が始まり、6 月末から 7 月頭にかけて、「Bluetooth テザリング + VPN を使った状態で蓋を閉じるとハングする」という再現条件を突き止める集中的な切り分けキャンペーンを 13 セッション実施した。この現象自体は 3 つの独立したセッションで再現しており、実在は確かである。ただし「なぜ起きるのか」(機序) と「正確に何が揃うと起きるのか」(必要条件) は、現時点でどちらも確定していない。

### 監査して分かったこと — どこまでが確かで、どこからが未確定か

**確かなこと**: ハング現象そのものの存在と再現条件の大枠 (s2idle + Bluetooth テザリング + VPN + 手動の蓋閉じ)、ハイバネート修理の完了、S3 の待機電力優位、そして「以前の s2idle ロールバックが不完全だった」という発見。これらは複数の独立した証拠や決定的なログに支えられていて堅い。

**未確定なこと**: カーネル内部のどこで止まっているのか (候補仮説は複数あるがどれも決着していない)、WiFi ドライバの状態が本当に条件に絡むのか (最新の有力読みだが統計的には有意でない)、そしてそもそもの発生率 (セッションによって 30% と 5% で大きくぶれており、固まっていない)。

### アプローチの主な問題点

1. **「N 回連続で無事だった」に頼りすぎる構造**。この故障はまれにしか起きないため、「対策を入れたら 30 回連続クリーンだった＝効いた」という推論を多用してきた。だが発生率自体が固まっていないので、30 回クリーンは「偶然」でも 2〜3 割の確率で起きる。実際、一度「ほぼ確定」とまで書いた結論が、後から「そもそも試験条件が壊れていて、30 回のうち 29 回は VPN が張られていなかった」と判明して全面撤回になった。
2. **「試験が有効だったか」の判定基準が後追いで 7 段階も作り直された**。VPN が本当に張られていたか、どの経路を通っていたか、ping が流れていたか、ドライバがロードされていたか — 検証のたびに「前回はこれを確認していなかった」が見つかり、過去の結論が繰り返し痩せた。
3. **実際の故障条件 (バッテリ駆動・外出時の使い方) をほとんど試していない**。歴史的にハングはバッテリ駆動時に起きているのに、「無事だった」証拠のほぼすべてが AC 電源接続下で取られている。最も切り分けたい条件だと自覚しながら、13 セッションを通じて一度も検証していない。
4. **一度に複数の要素を同時に変えてしまう実験が繰り返された**。ドライバを外すとテザリングも同時に落ちる、といった形で、「効いた」としてもどの要素が効いたのか分離できない設計が何度も再演されている。

### 見落としの要点と、次に何をすべきか

最大の見落としは、**カーネルに「どのドライバで止まったか」を自白させる仕組み (DPM_WATCHDOG 付き自前カーネル) が唯一の機序決着手段だと早くから分かっていながら、最後まで着手されていない**こと。現在の観測方法 (スナップショットとログ) では、ハング直前の状態が正常時と見分けがつかないことも既に判明しており、この道具なしに機序は決着しない。次点として、(i) 発生率そのものを固める対照実験が構造的に欠けていること、(ii) バッテリ駆動・実使用条件のセルが空白のままなこと、(iii) VPN の実装を変えてみる・Android 端末で試す・USB 自動サスペンドを切ってみるといった低コストの判別手が未検討なこと、が挙げられる。

推奨する優先順位は、①発生率の確定 (ハングが出た条件そのままで試行数を積む)、②バッテリ + 実使用条件の検証、③DPM_WATCHDOG カーネル + ramoops による機序決着、④ゼロコスト系 (USB 自動サスペンド無効化、VPN 実装や接続相手の変更) の並行実施 — の順である。

なお公平のために強調すると、このプロジェクトの自己修正能力は高い。試験条件の破綻も、誤った結論も、いずれも外部からではなく **自分たちの再検証で発見・撤回されている**。限界の開示も一貫して誠実である。問題は誠実さではなく、上記のような **構造的なバイアス** (陰性証拠依存と AC 偏重) が個々のセッションの誠実さでは打ち消せない形で残り続けたことにある。

---

## 2. 前提・目的・監査の方法

### 目的

29 本のレポートを通読し、(a) これまでのアプローチに方法論上の問題がないか、(b) 見落としているポイント・打たれていない手がないか、を洗い出す。

### 監査の方法 (再現方法相当)

1. ハング関連レポート 29 本を 3 期に区分し、期ごとに 1 エージェント (計 3 並列) で全文精読。各レポートを「目的・仮説 / 方法 (N・条件) / 結論と証拠の強さ / 自認する限界 / 批判的観察」の 5 観点で分解
2. 監査レポートに引用する数値・主張は、エージェント要約を鵜呑みにせず **原本レポートを grep/Read で spot-check** して確認 (200520 の統計主張とその無効化、130206 の Fisher 検定と tight reading、063543 の 3 ハング、baseline 0.7–0.8 件/週、S3 電力、hibernate 3% 発火 — すべて原本と整合を確認済み)
3. 新規の実機実験・実機への ssh 接続は行っていない

### 対象環境 (レポート群の対象)

- MacBook Air 11" Early 2015 (`macbookair2015.lan`) / Debian 13 (trixie) / kernel 6.12.x 系
- 症状: lid close でのスリープ後、復帰不能の無音ハング (強制電源断のみ脱出可)。ログ上は `PM: suspend entry` 後に exit 欠落

### 記号についての注意

レポート群の仮説記号は **単一の連続体系ではない**。(a)-(c) は「検証すべき仮説」(063543/111259)、(a)-(d) は「0/30 の解釈候補」(061553) と、同じ字母がレポートによって別物を指す。H5 も 074509 (resume 側仮説) と 130206 (wl 単独説、撤回済み) で再利用されている。本監査では引用時に出典レポートを併記する。

---

## 3. 確立された事実 (bedrock) と未確立事項の峻別

### 堅い (複数の独立証拠 or 決定的ログあり)

| # | 事実 | 根拠 |
|---|---|---|
| B1 | **s2idle + BT-PAN + VPN + 手動 lid close で dpm_suspend 段の無音永久ハング** が実在 | 3 セッション独立再現: [063543](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) 3/10 (3 別 boot)、[043251](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) 1/20、[102907](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) 1/26。signature 6〜8 項目一致 |
| B2 | **低バッテリ自動ハイバネの修理完了**: DMI wakeup type=Power Switch でハード \_BTP 経路が構造的に不到達 → `alarm=0` で RTC ポーリング経路へ強制 | [ソースレベル確定 (06-15)](2026-06-15_234635_fix_battery_hibernate_btp.md) + [実使用 3% で発火・S4 復帰完走の実観測 (06-18)](2026-06-18_053417_hibernate_success_snapshot.md) |
| B3 | **S3 deep の待機電力は s2idle の約 7–12 分の 1** (~0.06–0.10 W vs 0.70 W) | [8h・16 セグメントの計測 (06-19)](2026-06-19_094329_s3_battery_standby_power.md)。「8h で容量 2pt 減 (0.70 W なら ~13pt)」というゲージ精度非依存の論拠 |
| B4 | **6/27 の s2idle ロールバックは不完全** (`60-s3-soak-log` フック残存で毎 suspend が deep に化けていた) → 修正後が「真の s2idle」初実証 | [PM entry/exit・suspend_stats・soak log の三点突合 (06-28 021019)](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) |
| B5 | **「N/N clean」系の複数の結論が valid 定義の欠陥で無効** (詳細は 4-2) | [030349 の retro-classify](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md): 200520 の 32 cycle 中 31 cycle が xfrm state=0 (VPN inactive) |
| B6 | **btusb 完全除去でも battery + lid close でハングした例が 1 件** → 「BT-PAN が真因 (必要条件)」は反証済み | [06-27 追記4 (#4)](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md): journald に `deregistering interface driver btusb` を残した上で `PM: suspend entry (deep)` 停止 |

### 未確立 (現時点で確定と扱ってはならない)

| # | 事項 | 状態 |
|---|---|---|
| U1 | **機序** (カーネル内のどこで止まるか) | H1 (xfrm ref leak) は判別子 4 度陰性で棄却圏、H4 (btusb URB drain) は最有力だが VPN 特異性を単独説明できず、H2 (bnep kthread) は狙い撃ち実験が confound で無効化。H6/H7 は未判別。**どれも決着していない** |
| U2 | **必要条件の精密化** — (b'')「wl が loaded かつ radio-off」説 ([130206](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md)) | 全 6 セッションを単一変数で分離する読みだが post-hoc。Fisher exact 5/56 vs 0/30 は片側 p≈0.11 で **有意未達**。keystone (061553 の radio-on clean) は実質 1 セッション |
| U3 | **base rate** (素の再現条件での発生率) | 063543 で 30% (3/10)、043251/102907 で ~5% (1/20, 1/26) と **3 倍以上乖離**。pooled 5/56 は heterogeneous で単一推定に使えないとレポート自身が明記 |
| U4 | 歴史的 baseline 0.7–0.8 件/週 | 6 件/7.5 週の小標本。hang 検出定義もスクリプト v1→v2 で途中変更されており、意思決定の prior としては柔らかい |

---

## 4. アプローチの系統的問題点 (監査の本体)

### 4-1. 陰性証拠 (N/N clean) 依存の構造

低頻度・間欠・ログ皆無という故障の性質上、「対策を入れて N 回クリーン＝効いた」という **陰性証拠にしか頼れない** 構造が 5 月から一貫している。問題は、この推論の強さが base rate p に強く依存する ((1-p)^N) のに、その p 自体が U3 の通り固まっていないこと。p=30% なら 30 連続 clean は偶然 2×10⁻⁵ で決定的だが、p=5% なら 21% で「3 回に 1 回は偶然起きる」水準になる。[130206](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) はこれを自認して「決定的でない」と書いたが、[200520](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) は 0.90^32≈3.4% を「ほぼ確定ライン」と heading に掲げ、後に全面無効化された (4-2)。また [102907](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) は「pooled 5/56 は heterogeneous なので単一 rate 推定に使わない」と自認しつつ、同じ pooled 値を Fisher 検定に投入しており、**自己批判と統計処理が両立していない**。

### 4-2. valid cycle 定義の 7 段変遷と旧結論の無効化連鎖

「そのサイクルは本当にハング条件を満たしていたか」の判定基準が、キャンペーン中に 7 段階も後追いで強化された:

| 段階 | valid 判定 | 問題の露呈 |
|---|---|---|
| 021019/063543 | IKE_SA delete 端点 IP を retrospective に確認 | 手動・事後 |
| 111259/141226/041006 | per-cycle PRE snapshot を sync 永続化 | 概ね健全だが suspend 突入時の残留は未観測 |
| **200520** | **実質検証なし** | **cycle 2–32 が VPN inactive と後日判明 → 「32/32 clean で H2/teardown timing が必要条件成分」の結論が無効化** |
| 030349 | xfrm state count>0 | count 単独では WiFi 経由 VPN の混入を検出できない |
| 061553 | + source-IP (BT-PAN/WiFi/inactive の三分類) | BT-PAN 落ち復旧中の WiFi 経由 VPN 成立を実際に検出 (gate がなければ再び誤 valid) |
| 102907 | + ping_running durable 記録 | 過去セッションの ping 有無は記録がなく事後検証不能 |
| 130206 | + wl_loaded/cfg80211/wlp3s0 durable 記録 | — |

この変遷は個々には誠実な改善だが、裏返せば **S1 (041006 の 22/22) 以降の機序ラダーの結論群が、数日間にわたり無効な valid 定義の上に積まれていた** ことを意味する。064608 に至っては valid 数が事後に 2 度 (25→約14→13) 変わった。「新しい介入を試す前に、その試験が有効だったことをどう証明するか」を先に固める発想が、030349 の事故まで欠けていた。

### 4-3. AC 偏重 — 実故障モードの検証セルが最後まで空白

歴史的なハングは **バッテリ駆動・lid close・STH 経路** で起きている ([06-27 #1/#2/#4](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) はいずれも battery)。にもかかわらず:

- S3 復活期の「健全」証拠 (RTC 21/21、lid 7/7) は **すべて AC** — [s3_revival_evaluation](2026-06-18_233837_s3_revival_evaluation.md) 自身が限界として明記
- 6/27 の「真因=BT-PAN」を導いた決定テスト (5/5 clean) も **AC・normal cadence** で、空白セル (battery STH + btusb 除去) を踏んでいなかった。#4 がまさにそのセルで反証した
- キャンペーン全 13 本も **すべて AC**。[021019](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)/[063543](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) で「最も切り分けたい実条件」と明記されながら、battery/STH × BT-PAN+VPN は **一度も検証されていない**

6/27 の battery ハングは、この非対称を放置した帰結として事実上予見可能だった。soak を待たず battery STH を能動的にストレスしていれば、S3 no-go は数日早く出せた可能性が高い。**「無事である」ことを示したい条件と、「無事である」ことを確認した条件が、2 ヶ月間ずれ続けている**。

### 4-4. 多変数同時変更の反復

同型の設計ミスが少なくとも 4 回繰り返されている:

1. [5/31 の s2idle 切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md): s2idle 化と同時に `i915.enable_dc=0`/`pcie_aspm=off` を除去 (3 変数同時、自認あり)
2. [111259](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md): peer 変更 (iPhone→iPad) と駆動経路変更 (手動→driver) が同居 (自認あり、141226 の 2×2 で解消)
3. [041006 の S1](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md): btusb unload は BT-PAN teardown を随伴 → 「btusb が原因」と「BT-PAN active が原因」を分離不能 (自認あり)
4. [130206](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md): `rmmod wl` は WiFi 機能停止と PCI suspend chain からの除去を同時に行う — S1 と同型の交絡の再演

自認はほぼ毎回あるが、**設計段階で回避されず、事後の限界注記で処理される** パターンが定着している。

### 4-5. 単発ハングへの過剰帰属と post-hoc パターン適合

キャンペーンの verified hang は全部で 5 件 (063543 の 3 + 043251 の 1 + 102907 の 1)。043251 では 1 件のハングに「WiFi-on protective」の意味を載せようとして advisor に 2 度差し戻され、6/27 では交絡を自認したまま「真因=BT-PAN」を heading に昇格させて約 1 時間後に自己反証した。最新の (b'') tight reading も、peer/hook/traffic/ping/駆動方式/N がすべて共変する 6 セッションへの **後付けの単一変数適合** であり、130206 自身が「決定的でない」と書いている通り、headline に据えるには踏み込みすぎである。確証方向に振れたドラフトを advisor 諮問や次セッションで引き戻す、というループが常態化しており、**最初の断定を弱く書く** 方が修正コストは低い。

### 4-6. 観測装置の非中立性という原理的トレードオフ

valid gate を支える hook (70-h4-probe / 58-snapshot-only) は suspend entry で数十 KB の書込 + sync を実行するため、race のタイミングを変えうる (061553 が candidate (c) として sharpen)。つまり **「素の再現条件を試すには hook を外す必要があるが、外すと試験の有効性を証明できない」** という自己言及的な袋小路に到達しており、レポート群はここから脱出する設計 (例: 観測を suspend 経路外へ移す、事後回収のみの受動記録に徹する) を出せていない。

### 4-7. 機序特定の構造的限界と S4 未着手

- journald は強制電源断で flush されないため、**入眠側 (α) か復帰側 (β) かは現行手法で原理的に判別不能** ([074509](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) が明記)。α/β 分離実験 (lid close + RTC 先行 wake) は 141226/041006 で計画されたが未実行
- [102907](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) で hang 直前 3 cycle の pre snapshot が state レベルで identical と判明 = **観測可能な state からハングは予測できない**
- したがって機序決着の唯一の出口は **S4 (DPM_WATCHDOG=y 自前カーネルで stall device をカーネル自身に吐かせる)** だが、074509 での言及以来 **全期間を通じて未着手**。snapshot 系の精緻化 (7 段の gate 強化) に投じた工数の一部を S4 に回していれば、機序はすでに決着していた可能性がある

### 4-8. 初期 (5 月期) の教訓 — ただし方法論は時系列で改善している

- **効果測定 N=0 での恒久設定積み増し**: `i915.enable_dc=0` → `applespi` blacklist → `pcie_aspm=off` の 3 連敗。いずれも反映確認 1 cycle のみで恒久適用し、判定を「4〜6 週の受動観測」に先送りした
- **弁別力の低いシグネチャを仮説根拠に使用**: 5/22 の「早期停止型シグネチャ→ device suspend phase → applespi 説」はサンプル 1 件の最終行の揺れ (flush 位置の不定) に依存し、翌日の再発で実質崩壊した
- **rtcwake 検証が本番故障モードを再現しない構造的ギャップ**: 5/31 は lid での再現テストなしに rtcwake 検証のみで恒久 deploy し、翌日 lid ハングが再発。6/01 の RTC 68/68 clean も全て lid OPEN のままで、lid 物理遷移を一度も再現していない (自認あり)

公平のために記すと、6/01 以降は対照設計 (コントロール・オフセット追従・必要/十分条件の区別) が導入され、6/28 以降は durable evidence・advisor 諮問・retro-classify が定着しており、**方法論の質は時系列で明確に向上している**。030349 の confound 発見も 6/27 の自己反証も、外部指摘ではなく内部の再検証によるものである。

---

## 5. 見落とし・未実施の手 (優先順位付き)

### 5-1. レポート内で言及済みだが未実施

| 手 | 何が判別できるか | コスト感 |
|---|---|---|
| **S4: DPM_WATCHDOG=y 自前カーネル** | dpm_suspend で stall した device の特定 = 機序の直接決着 (H2 vs H4 vs その他) | 1–2 日 (broadcom-sta DKMS の追従ビルド込み)。074509 以来の「最終手段」だが、4-7 の通り実質唯一の出口 |
| **battery/STH × BT-PAN+VPN セルの充填** | 実故障モードでの再現性。AC 偏重 (4-3) の解消 | 手動 lid 数十 cycle。ハングリスクを許容する必要あり |
| **wl-unload N=60+ 拡大** | (b'') の統計的確立 (60/60 clean で Fisher p≈0.024) | 手動 30–60 分 ×2 セッション |
| **041006 の btusb-removed arm を WiFi-off で再試行** | 「btusb 必要」vs「wl-radio-off 必要」の discriminate | 同上 |
| **S2: xfrm flush hook** | H1 系の独立検証 (cached xdst bundle 未 walk の限界は自認済み) | 小 |
| **suspend 突入時の xfrm 残留確認** (hypothesis (b), 111259) | 毎 cycle 張り直す設計のため未観測のまま | 小 (snapshot 項目追加) |
| **α/β 直接分離** (lid close 後、lid open より先に RTC で起こす) | 入眠側 (α) か復帰側 (β) かの判別。141226/041006 で計画されたまま未実行 (4-7 参照) | 小 |
| **post-6.12.94 xfrm fix の backport 再試行** | H1/H2 領域の検証。074509 が次アクション (b) として明記したまま未着手 | 中 |
| **S5: btusb URB drain timeout patch** | H4 の直接検証。現設計は欠陥指摘済み → `usb_unlink_anchored_urbs` 置換案も未着手 | 中 (カーネルビルド) |

### 5-2. レポート群に言及がない盲点 (本監査の新規指摘)

| 手 | 何が判別できるか | コスト感 |
|---|---|---|
| **無介入・素条件の base rate 確立 soak** | U3 (30% vs 5%) の解消。**介入評価の分母を先に固める**。現状は対照の base rate が宙ぶらりんのまま各介入を評価しており、4-1 の構造問題の根 | 手動 lid N=50–100 (数セッション)。hook は最小限 (4-6 とのトレードオフは残るが、gate を source-IP のみに絞れば軽量化可能) |
| **ramoops による console ログの常時退避** | 強制電源断でも直前 dmesg を不揮発領域に残す。efi_pstore (panic 時のみ dump) は 041006 で動作確認済みだが、panic を伴わない本件ハングでは無力 — `ramoops` の console_size 設定なら hang 直前行が残り、S4 と組み合わせれば stall device の回収に直結 | 小 (memmap 予約 + モジュールパラメータ、リブート 1 回) |
| **btusb autosuspend 無効化** (`usbcore.autosuspend=-1`) | 074509 が race 窓拡大要因に挙げた `BT_HCIBTUSB_AUTOSUSPEND` の寄与を **ゼロビルドで** 判別 (config 記録のみで、無効化テスト自体は未提案) | 極小 |
| **VPN 実装の切り替え** (WireGuard / OpenVPN) | 全観測が strongSwan/charon-nm (xfrm) 依存。xfrm を使わない VPN で再現すれば「xfrm 特異」を棄却、しなければ H1/xfrm 系が急浮上 | 小〜中 (peer 側設定) |
| **非 Apple peer** (Android テザリング) | 141226 の「peer 非依存」は iPhone/iPad 間のみ。Apple Personal Hotspot 実装特異性の排除 | 小 (端末があれば) |
| **`/sys/power/pm_test` による段階分離** | `pm_test=devices` 等でカーネル側の suspend 段階を人工的に区切り、hang 段の絞り込みを補助 | 小 |

---

## 6. 総合評価と推奨

### 総合評価

- **現象の存在 (B1) は堅い。しかし機序 (U1) も必要条件の精密化 (U2) も統計的には未確立** — これが 13 セッションを投じた現在地の正確な要約である
- プロジェクトの自己訂正能力 (retro-classify による自セッション無効化、真因説の 1 時間での自己反証、誤読の逐次訂正) は高く、限界開示も一貫して誠実
- 一方で、**陰性証拠依存 (4-1, 4-2) と AC 偏重 (4-3)** という 2 つの系統的バイアスは、個々のセッションの誠実さでは打ち消されず 2 ヶ月間残り続けた。前者は「試験の有効性を証明する仕組みを介入より先に固める」、後者は「無事を示したい条件で無事を確認する」という原則で防げた類のものである

### 推奨の次の一手 (優先順)

1. **base rate の確定** — 素条件 (hook 最小・AC) で N=50–100 を積み、30% vs 5% の乖離を解消する。これが決まらない限り、今後のあらゆる「N/N clean」の証拠力が計算できない
2. **battery/STH × BT-PAN+VPN セルの充填** — 実故障モードでの再現性確認。ここでハングすれば実使用への対策優先度が確定し、しなければ「AC/手動 lid 特異」という新情報になる
3. **S4 (DPM_WATCHDOG) + ramoops** — 機序決着の唯一の出口。snapshot gate の精緻化はこれ以上の限界収穫逓減が明らか (102907 で identical snapshot が実証済み) であり、投資先を移すべき
4. **ゼロコスト系の並行実施** — `usbcore.autosuspend=-1`、非 Apple peer、WireGuard 化。いずれも既存の 30 cycle プロトコルにそのまま載る

---

## 7. 参照レポート一覧

### 第 1 期: 初期 S3 ハング期 (2026-05-10〜06-03、7 本)

1. [2026-05-10 lid open resume hang 初動調査](2026-05-10_055032_lid_open_resume_hang.md)
2. [2026-05-17 アップデート後デグレ確認](2026-05-17_105358_post_update_regression_check.md)
3. [2026-05-22 再発 + applespi blacklist](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md)
4. [2026-05-23 同日 2 件再発 + pcie_aspm=off](2026-05-23_144518_s3_hang_pcie_aspm_off.md)
5. [2026-05-31 s2idle への恒久切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md)
6. [2026-06-01 s2idle ハング再発 + RTC ストレス切り分け](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)
7. [2026-06-03 電源ボタン wake 前提検証](2026-06-03_123439_pwrbtn_wake_premise_verification.md)

### 第 2 期: hibernate 修理〜S3 復活・soak 期 (2026-06-08〜06-27、9 本)

8. [2026-06-08 低バッテリハイバネ事故調査](2026-06-08_035056_low_battery_hibernate.md)
9. [2026-06-15 \_BTP 経路のソースレベル修理](2026-06-15_234635_fix_battery_hibernate_btp.md)
10. [2026-06-18 実 3% ハイバネ発火の実証スナップショット](2026-06-18_053417_hibernate_success_snapshot.md)
11. [2026-06-18 KB バックライト消灯 + lid wake 探査](2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe.md)
12. [2026-06-18 なぜ S3 deep を使っていないのか (通読版)](2026-06-18_142303_why_not_s3_deep_sleep.md)
13. [2026-06-18 S3 復活評価](2026-06-18_233837_s3_revival_evaluation.md)
14. [2026-06-19 battery S3 待機電力測定 → go](2026-06-19_094329_s3_battery_standby_power.md)
15. [2026-06-20 S3 deep 可逆永続化 + soak 開始](2026-06-20_045414_s3_deep_persist_soak_start.md)
16. [2026-06-27 BT/VPN lid close ハング事故 → no-go](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)

### 第 3 期: s2idle BT-PAN+VPN 切り分けキャンペーン (2026-06-28〜07-01、13 本)

17. [2026-06-28 ロールバック不完全発見 + 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
18. [2026-06-28 手動 factorial で 3/3 ハング (原 bedrock)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
19. [2026-06-28 カーネルソース解析 (H1–H5)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
20. [2026-06-28 driver 経路 15/15 clean](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
21. [2026-06-28 2×2 で peer 非依存・lid 経路必要](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
22. [2026-06-29 S1: btusb unload 22/22 clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)
23. [2026-06-29 driver 経路 heavy traffic free test](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md)
24. [2026-06-29 S3: bnep teardown 32/32 clean (後に無効化)](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md)
25. [2026-06-30 VPN autoconnect confound 発覚 → 200520 無効化](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md)
26. [2026-06-30 rerun N=30 valid clean](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md)
27. [2026-07-01 WiFi-off でハング独立再現](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md)
28. [2026-07-01 ping なしでハング再現 (ping confound 排除)](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md)
29. [2026-07-01 wl 完全 unload 30/30 clean + (b'') 浮上](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md)
