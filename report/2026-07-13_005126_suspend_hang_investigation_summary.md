# スリープ復帰ハング問題の調査総括 — 発覚から真因確定・恒久対策まで

- **作成日時**: 2026年7月13日 00:51 JST
- **対象ホスト**: `macbookair2015.lan` (MacBook Air 11" Early 2015 / MacBookAir7,1, Debian 13)
- **性格**: 本レポートは 2026-05-10 〜 2026-07-12 の約 2 ヶ月・43 本のレポートにわたる suspend hang 調査の**総括**であり、新規の実機実験は行っていない。個別の事実・証跡はすべて各レポート (末尾の「参照レポート一覧」) にあり、本レポートは全体を通読できる形に再構成したものである。

## 概要

2026 年 5 月 10 日、この MacBook Air で「蓋を閉じてスリープさせると、ごくまれに二度と起きてこない」という故障が確認された。画面は真っ暗のまま、電源ボタンにも反応せず、電源ボタン長押しの強制電源断でしか脱出できない。頻度は十数回〜数十回に 1 回 (週 1 回弱)、起きたときのログは一切残らない。実害は強制電源断による作業状態の喪失である。

調査が 2 ヶ月に及んだ最大の理由は、この故障が「静かな死」だったことにある。再現率が数 % しかないうえ、カーネルの監視機構 (watchdog、hung task 検知、NMI) がすべて沈黙し、ジャーナルにも痕跡を残さない。最初の 1 ヶ月は起動オプションの変更やスリープ方式の切り替え (S3 → s2idle) といった対症療法を試したが、いずれも効かなかった。6 月中旬には待機電力の利点から S3 復活も試みたが、試験中に 4 回ハングして見送りとなった。

転機は 6 月末で、「Bluetooth テザリング + VPN を使った状態で蓋を閉じる」という再現条件が見つかった。ここから約 2 週間・13 セッションの切り分けキャンペーンで条件を要素分解し、7 月 2 日に「WiFi ドライバ (wl = broadcom-sta) がロードされていて、かつ電波オフであること」がハングの必要条件だと Fisher 検定 (p ≈ 0.024) で統計的に確立した。逆に「WiFi 電波を常時オンにしておく」だけでハングは一度も起きないことも 52 回の試験で裏付けられ、この時点で実用的な回避策は手に入った。

続く 1 週間で、カーネル内部のどこで止まっているかを特定するための計測カーネル (dpmwd1〜4) を段階的に自前ビルドした。DPM watchdog の拡張、Mac ファームウェアの RTC リセットを素通りする改造版 pm_trace、s2idle 経路への記録点追加を積み重ねた結果、驚くべきことに機械は**スリープにも wake にも成功しており、止まっていたのはその後の resume 処理の途中**だと判明した (7 月 5 日)。翌日には停止点の実名が「Thunderbolt 2 ブリッジの noirq 復帰 (署名 A)」と「内蔵 GPU i915 の main 復帰 (署名 B)」の 2 箇所に特定された。

実名が付いたことで調査は名指し介入の段階に入った。まず `pcie_port_pm=off` (全 PCIe ポートの省電力禁止) でハングが完全に消えること (0/30、p ≈ 1.7×10⁻⁴) を確認し、そこから 3 段の絞り込み (Rung 1〜3) で範囲を狭めていき、7 月 10 日に**真犯人 = WiFi チップの親にあたる PCIe ルートポート 00:1c.2 が sleep 中に省電力状態 D3hot へ落ちること**と確定した (00:1c.2 単独を D0 固定するだけで 0/37、p ≈ 7.5×10⁻⁵)。恒久対策は udev rule 1 行 — wl デバイスに `d3cold_allowed=0` を書いて親ポートだけを D0 固定する — で、カーネルに依存しない。

機序も大部分が解明された。wl ドライバは復帰のたびに BCM4360 専用の PCIe workaround (PLL 再プログラム + config space 退避/復元) を実行して自分のリンクを一度揺らす仕様であり、電波オフ時はさらに本初期化を省略した「短縮経路」(resume 54ms → 22ms) を通る。この汚い復帰が、無保護の親ポートの D3hot 復帰過渡と重なったときにまれにバスレベルの静かな死に至る。保護を外した最終実験 (7 月 12 日) では、電波オフの復帰だけが PCIe バスにエラーの痕跡 (訂正可能エラー、書き込み失敗 TLP、親ポートの Master Abort) を毎回撒いているという物的証拠も得られた。長らく容疑者だった i915 は「最長の復帰処理中に事故に巻き込まれて最後の記録を残した」だけの被害者だった。

現在の構成は stock カーネル 6.12.95 + udev rule で、ハングの全条件 (BT テザリング + VPN + 電波オフ + 蓋閉じ) を解禁したまま常用 soak を継続中、ハングはゼロである。計測カーネルは退役し、セキュリティ更新も再開された。トレードオフとして suspend 中の待機電力が約 0.7 W から約 1.6 W (毎時 4% 減) に増えており、持ち運び時はハイバネートかシャットダウンを推奨する。未解明として残るのは「汚い復帰がバス上で致命傷になる最後の瞬間」そのものだけで、これはソフトウェアで観測できる限界を越えており、専用測定器の領域である。

## 前提・目的

- **目的**: 43 本に分かれた調査レポートを、将来の自分・類似機体 (Mac + Linux + broadcom-sta) の調査者が通読できる 1 本に総括する
- **方法**: 既存レポートの読解と再構成のみ。数値・結論は原本レポートを spot-check して引用
- **現在構成の記載について**: 執筆時はサンドボックス制約で実機に ssh 接続できなかったため、「現在の構成」は最終レポート ([C-9](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md)、2026-07-12 22:55 JST 時点) および[ハウスキーピング](2026-07-12_230643_housekeeping_old_kernels_cleanup.md)の検収記載値に基づく

## 環境情報

- **実機**: Apple MacBookAir7,1 (11" Early 2015, Broadwell-U)
  - GPU: Intel HD Graphics 6000 (`0000:00:02.0`, i915)
  - WiFi: **Broadcom BCM4360** (`0000:03:00.0`)、ドライバ = `broadcom-sta-dkms` (`wl`) 6.30.223.271-26
  - SSD: APPLE SSD SM0128G (AHCI `0000:04:00.0`)
  - Thunderbolt 2: Intel Falcon Ridge (`00:1c.4` → `05:00.0` → `06:00.0` → downstream `06:03.0`/`06:05.0`/`06:06.0`)
- **PCIe ルートポート構成** (本件の主役):
  - `00:1c.1` → `02:00.0` FaceTime カメラ
  - **`00:1c.2` → `03:00.0` BCM4360 (wl) — 真犯人**
  - `00:1c.4` → Thunderbolt チェーン
  - `00:1c.5` → `04:00.0` SSD
- **OS**: Debian 13 (trixie)。カーネルは発覚時 6.12.85+deb13 → 調査中 6.12.94 stock / 6.12.94-dpmwd1〜4 (自前計測カーネル) → **現在 6.12.95+deb13-amd64 (stock)**
- **スリープ**: 発覚時 S3 (deep) → 2026-05-31 以降 s2idle (`mem_sleep_default=s2idle`)
- **再現条件で使う周辺**: iPad の Bluetooth PAN テザリング (172.20.10.0/28)、strongSwan IKEv2 VPN (GSNet)

## 問題の症状

- lid close でスリープ → lid open しても復帰しない。画面消灯のまま、キーボード・電源ボタン短押しに無反応 (電源短押しでキーボードバックライトのみ点灯する「部分応答」が後の調査で判明)
- 脱出手段は電源ボタン長押しの強制電源断のみ。**実害 = 保存していない作業状態の喪失** (バッテリ残量はある状態で起きる)
- 再現はランダムで、発覚時の頻度は十数回〜数十回に 1 回 (~0.7 回/週)
- ジャーナル上は `PM: suspend entry` の後に exit が欠落するだけで、エラーは一切記録されない。カーネルの watchdog / hung task 検知 / NMI hardlockup / softlockup の全監視が沈黙する「静かな死」

## 調査の経緯

### フェーズ 1: S3 hang として発覚、対症療法の失敗と s2idle への切り替え (5/10 〜 6/03)

[発覚レポート](2026-05-10_055032_lid_open_resume_hang.md) (5/10) の時点では、S3 (deep) 経路特有の故障と考えられており、ゴールも「S3 deep を維持したまま修正する」だった。以後 1 ヶ月、[applespi の blacklist](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) (5/22)、[`pcie_aspm=off`](2026-05-23_144518_s3_hang_pcie_aspm_off.md) (5/23) と回避策を 1 つずつ足しては数週間様子を見る手探りが続いたが、いずれも再発した。なおこの時期に `i915.enable_dc=0` も試して効果がなかったことが、後のフェーズ 4 で「i915 は被害者」という判断を早める材料になる。

5/31 に[スリープ方式そのものを s2idle へ恒久切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md)したが、[翌日に s2idle でも hang が再発](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) (6/01) し、「スリープ方式が原因」という見立ては崩れた。[電源ボタン短押しで健全な s2idle を起こせることの前提検証](2026-06-03_123439_pwrbtn_wake_premise_verification.md) (6/03) を挟み、調査は仕切り直しとなる。

### フェーズ 1.5 (背景): S3 復活の挑戦と挫折、そして「本物の s2idle」へ (6/18 〜 6/28)

s2idle の待機電力 (~0.70 W) に対し S3 deep は ~0.06〜0.10 W と桁で優位なため、6 月中旬に S3 復活が検討された。[lid wake の構造的制約の精査](2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe.md)、[S3 を捨てた経緯の整理](2026-06-18_142303_why_not_s3_deep_sleep.md)、[復活可否の切り分け](2026-06-18_233837_s3_revival_evaluation.md) (battery 時の spurious wake 源 = gpe70 の特定)、[待機電力の実測](2026-06-19_094329_s3_battery_standby_power.md)を経て、[可逆な形での S3 永続化 + 2 週間 soak](2026-06-20_045414_s3_deep_persist_soak_start.md) が 6/20 に始まった。

しかし soak 中の 6/27 に[計 4 回のハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)が発生し S3 復活は no-go、s2idle へロールバックした。このとき一時「Bluetooth テザリングが真因」と結論しかけたが、Bluetooth ドライバを完全に外してもハングした 1 例が自ら反証となった。さらに[ロールバック自体に不備があり「s2idle に戻したはずが残存フックで毎回 deep で寝ていた」ことが後日発覚](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) (6/28)。これを修正して初めて「本物の s2idle」での検証が始まった。

### フェーズ 2: 再現条件の確立 — 「wl ロード + 電波オフ」が必要条件 (6/28 〜 7/02)

[手動の factorial 切り分け](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) (6/28) で「BT-PAN × VPN 併用の lid close」が 3/3 でハングする一方、単独要素はすべてクリーンという相互作用が確定し、以後この条件が再現の基準になった。[カーネルソースの机上解析](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)で仮説群 (H1〜H7) を立て、[自動 suspend では再現しないこと](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)、[テザリング相手に依存せず手動 lid close 経路が必要なこと](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)を順に切り分けた。

以後の消去戦は一直線ではなかった。[btusb 事前 unload で 22/22 clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)、[heavy traffic 経路 25 cycle clean](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md)、[bnep 明示 teardown で 32/32 clean](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) と成果が積み上がったかに見えたが、[VPN の autoconnect が不安定で「30 回中 29 回は VPN が張られていなかった」ことが判明し、clean 結果が丸ごと無効化される事件](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md)が起きた (6/30)。これを機に「suspend 突入時点で BT-PAN アドレスと VPN の ESP SA が双方向に生きていること」を cycle ごとに機械検証する有効性ゲート (BT_PAN_VALID) が導入され、[検証付きの 30/30 clean](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) が初めて成立した。

7/01、[WiFi 電波オフの条件で hang が独立再現](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md)し、[ping などのトラフィック要因も排除](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md)、[wl を完全に unload すると 30/30 clean](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) という決定的なヒントが得られた。並行して [2 ヶ月間の方法論監査](2026-07-02_092013_hang_investigation_methodology_audit.md)を実施し (後述の「教訓」参照)、その指摘 (clean 側もプールして統計を対称に扱う) を受けて 30 cycle を追加、[wl unload 合算 0/60 vs hang 側 5/56 の Fisher 片側検定 p ≈ 0.024](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) で **「wl がロードされていて、かつ電波オフ」がハングの必要条件**であることが統計的に確立した (7/02、以後 "bedrock" と呼ぶ基準)。全 7 セッションの hang/clean がこの単一変数で完全に分離した:

| 条件 | 結果 (プール) |
|---|---|
| wl loaded + radio **off** | **5/56 hang (~9%)** |
| wl loaded + radio **on** | 0/52 clean |
| wl **unloaded** | 0/60 clean |

この時点で実用回避策「**WiFi 電波を常時オンにしておく**」が確立した。

### フェーズ 3: 計測カーネル dpmwd1〜4 — 停止点は resume 側、実名は TB ブリッジと i915 (7/02 〜 7/06)

停止箇所の特定には市販の手段がなく、[DPM_WATCHDOG=y の自前カーネル 6.12.94-dpmwd1 をビルド・デプロイ](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)するところから始めた (7/02、pstore による panic ダンプ回収も end-to-end 検証)。ところが [hang を再現させても watchdog は ~18 分沈黙し pstore は空](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) (7/03)。監視範囲を広げた [dpmwd2 (late/noirq 拡張 + PM_TRACE_RTC)](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) でも、[初の実戦 panic は intel_pch_thermal の正規冷却ループと watchdog 60 秒の衝突という偽陽性](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md)で、[本物の hang では全監視が完全沈黙](2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md)だった (7/04)。

電源断を越えて停止位置を残せる唯一の仕組み pm_trace (RTC に記録) には、[Mac ファームウェアが boot 時に不正な RTC 日付を検証リセットしてしまい記録が消えるという構造的な壁](2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md)があった (7/04)。しかもリセット後の値が偶然正規の記録に見える「偽 decode」の罠まであった。これを [firmware の検証を素通りする encoding に改造し、s2idle 経路に記録点 12 箇所を追加した dpmwd3](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md) で突破し、hang 4 回・4 回とも停止点の取得に成功 (7/05)。結果は従来の見立てを覆した: **機械はスリープにも wake にも成功しており、止まっていたのは resume 処理 (noirq〜early 段) の途中**だった。「suspend の途中で止まる」というそれまでの推定は、ジャーナルでは suspend 側と resume 側の停止が区別できないことによる対称性の錯誤だった。

続く [dpmwd4 (記録点の順序入替でデバイス実名を取得)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md) で停止点は 2 つの署名に二極化した (7/06): **署名 A = Thunderbolt 2 downstream ブリッジ (06:03.0/06:06.0) の noirq resume 入口**、**署名 B = i915 (00:02.0) の main resume 入口**。全監視の沈黙と合わせ、「callback が長時間走っているのではなく、タイマや NMI の土台ごと止まる静かな停止」という像が実名付きで固まった。

### フェーズ 4: 名指し介入の梯子 — 真犯人 00:1c.2 の確定と恒久対策 (7/06 〜 7/12)

- **C-6** (7/06): [`pcie_port_pm=off` (全 PCIe ポートの D3 禁止) で hang 0/30](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)。同摂動ベースライン 8/19 ≈ 42% に対し p ≈ 1.7×10⁻⁴。**署名 A だけでなく署名 B も同時に消えた** = PCIe ポートの D3 遷移が両署名の共通上流にあり、i915 は被害者の可能性が高い。ただし広域介入のため真犯人ポートは未特定。この構成で常用 soak を開始したが、[suspend 中の放電が 2.8〜3.4 W (従来の 4〜5 倍) に達し鞄内発熱として顕在化](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) (7/07)、絞り込みの優先度が上がった。
- **C-7 Rung 1** (7/08): [Thunderbolt サブツリーのみの保護では不十分で hang 再発 (署名 B)](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md)。「TB 単独犯」説は棄却。同時に「00:1c.2 の子は wl」という必要条件との物理接点が浮上。
- **C-7 Rung 2** (7/09): [非 TB ルートポート 3 本 (カメラ親 00:1c.1 / wl 親 00:1c.2 / SSD 親 00:1c.5) を D0 固定して hang 0/30](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md)。真犯人はこの 3 本のいずれかに確定。
- **C-7 Rung 3** (7/10): [一本釣り成功 — wl (03:00.0) に `d3cold_allowed=0` を書いて親 00:1c.2 単独を D0 固定 → hang 0/37 (p ≈ 7.5×10⁻⁵)](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md)。無保護のまま 37 回生き延びた 00:1c.1/00:1c.5 は容疑から外れ、**真犯人 = 00:1c.2 の sleep 中 D3hot 遷移**と確定。待機電力 ≈1.6 W (広域介入の半分) のトレードオフでユーザ判断により **udev rule を恒久対策として採用**、`pcie_port_pm=off` は撤去。
- **C-8** (7/12): [機序の解明と stock カーネル復帰](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md)。broadcom-sta の Debian ソース + バイナリ blob の逆アセンブルで、**wl が resume のたびに BCM4360 専用 PCIe workaround (`wlc_bmac_4360_pcie2_war` = PMU PLL 再プログラム + PCIe config space 退避/復元) を実行し自リンクを揺らす**仕様を特定。実測で radio off 時は resume callback が 54ms → 22ms の「短縮経路」(workaround は走るが本初期化を中断) になることを分離した。恒久対策がカーネル非依存になったため stock カーネルへ復帰し (hang 全条件 0/30 で検収)、セキュリティ更新を再開して 6.12.95 へ。計測カーネル系は退役。
- **C-9** (7/12): [保護を一時解除した最終トレース](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md)。hang 3 回再現・全 decode 成功で署名 A の実名に 06:05.0 (TB downstream) が加わり「TB サブツリーの noirq 復帰域」と確定 (3 例目)。新設の bus-watch (resume 毎の lspci snapshot) が**物証を初取得: radio-off cycle の 6/11 で wl に訂正可能エラー、1 回は非致命の uncorrectable、AER HeaderLog に wl BAR0+0x1408 への書き込み失敗 TLP、親 00:1c.2 に Master Abort とリンク断/再確立のラッチ — radio-on では残渣ゼロ**。実験後は stock + 保護へ完全復帰。

## 真因と機序

確定した因果の連鎖は次のとおり。

1. **必要条件 (bedrock、統計的に確立)**: wl (broadcom-sta) がロードされていて、かつ WiFi 電波がオフであること。実際の再現には加えて BT-PAN テザリング + VPN + 手動 lid close が揃う (相互作用でタイミング条件が濃縮されると解釈)
2. **物理的な引き金 (介入で確定)**: wl の親 PCIe ルートポート **00:1c.2 が sleep 中に D3hot へ遷移する**こと。この 1 点を止める (D0 固定) だけで、他を一切変えずにハングが消える
3. **機序 (ソース解析 + 実測 + 物証)**: wl は resume のたびに 4360 PCIe2 war で自リンクを激しく擾乱する。radio off 時は本初期化を中断する短縮経路 (22ms) になり、この「汚い復帰」が親ポートの D3hot 復帰過渡と時間的に重なる。バスには radio-off 復帰のたびにエラー残渣 (CorrErr、書き込み失敗 TLP、親の MAbort) が実際に残っており、これがまれに致命傷になる
4. **停止の様相**: 機械は wake まで成功し、resume の途中 (署名 A = TB サブツリー noirq 域、署名 B = i915 main 入口) で、タイマ・NMI 基盤ごと止まる「静かな死」に至る。watchdog も hung task 検知も届かない
5. **i915 (署名 B) は被害者**: i915 の resume callback は全デバイス最長の ~440ms で、その窓の内側で wl の war が並走する。i915 に触れない介入 3 連続でハングが消えたことと、pm_trace の「最後に記録を書いたのが i915 だった」という async resume の解釈で一貫

なぜこの組み合わせが Mac 固有のレア故障になるかも説明が付く: BCM4360 + broadcom-sta (毎 resume war) + Falcon Ridge TB2 + この firmware という構成が揃った上で、radio off という比較的珍しい運用があって初めてタイミング条件が成立する。

## 恒久対策と現在の構成

**恒久対策** (2026-07-10 採用、カーネル非依存):

```
# /etc/udev/rules.d/99-c7r3-wl-d3cold.rules
ACTION=="add", SUBSYSTEM=="pci", KERNEL=="0000:03:00.0", ATTR{d3cold_allowed}="0"
```

wl デバイス (03:00.0) の `d3cold_allowed` を 0 にすると、カーネルの PCIe PM 実装により親ルートポート 00:1c.2 だけが sleep 中も D0 に固定される。ライブ trigger と再起動 e2e の両方で自動適用を検証済み。撤去はこのファイルを rm して再起動するだけ。

**現在の構成** (2026-07-12 22:55 JST の C-9 撤収検収時点):

| 項目 | 値 |
|---|---|
| カーネル | 6.12.95+deb13-amd64 (stock、GRUB default)。フォールバックに 6.12.94 stock、再演用に 6.12.94-dpmwd4 を残置 (dpmwd1〜3 は [purge 済み](2026-07-12_230643_housekeeping_old_kernels_cleanup.md)) |
| cmdline | `quiet no_console_suspend mem_sleep_default=s2idle panic=15` (`pcie_port_pm=off` なし) |
| スリープ | s2idle。恒久対策で 00:1c.2 のみ D0 で sleep (検収済み) |
| 運用 | BT+VPN+radio-off を含む全条件解禁で常用 soak 継続中、hang 0 |
| セキュリティ更新 | 再開済み (dkms が wl を新カーネルへ自動ビルド、検収済み) |

**トレードオフと運用上の注意**:

- suspend 中の待機電力は約 **1.6 W (毎時 ~4% 減)**。従来ベースライン 0.70 W の 2.3 倍だが、広域介入 `pcie_port_pm=off` の 2.8〜3.4 W の半分。**持ち運び (鞄に入れる) 時はハイバネートかシャットダウンを推奨**
- 本機の s2idle からの wake は電源ボタン短押しのみ (lid open・キー押下では起きない)
- 万一 hang が再発した場合は 0/37 + soak の反例 = 一級データ。5 分放置 → 電源長押し → 状況を記録して報告

## 統計サマリ

陰性証拠 (「N 回連続 clean」) の解釈には有効性ゲート (BT_PAN_VALID = suspend 突入時に BT-PAN アドレス + VPN ESP SA 双方向生存を機械確認) と arm (摂動条件) の分離が必須である。主要な arm の集計:

| arm | 条件 | 結果 | 備考 |
|---|---|---|---|
| hang 側 (非摂動 s2idle) | wl loaded + radio off + BT+VPN | 5/56 (~9%) | 063543/043251/102907 プール |
| clean 側 | wl loaded + radio **on** + BT+VPN | 0/52 | 実用回避策の根拠 |
| clean 側 | wl **unloaded** + BT+VPN | 0/60 | vs 5/56 で Fisher 片側 **p ≈ 0.024** (bedrock) |
| 非摂動プール最終 | 同 hang 条件 | 8/113 (~7.1%) | C-3 時点まで |
| 計測摂動 arm | dpmwd + pm_trace=1 + 同 hang 条件 | 8/19 → 9/24 (~38〜42%) | 摂動で発生率が濃縮、非摂動と合算しない |
| C-6 介入 | + `pcie_port_pm=off` | **0/30** | vs 8/19、**p ≈ 1.7×10⁻⁴** |
| C-7 Rung 2 介入 | 非 TB root port 3 本 D0 | **0/30** | vs 9/24、p ≈ 1.7×10⁻⁴ |
| C-7 Rung 3 介入 | **00:1c.2 単独 D0** | **0/37** | vs 9/24、**p ≈ 7.5×10⁻⁵** = 真犯人確定 |
| C-8 stock 検収 | stock 6.12.94 + udev rule | 0/30 | 恒久構成の検収 |
| C-9 無保護 | dpmwd4 + 保護解除 (+dynamic debug 摂動) | 3/13 (~23%) | 物証採取用、全 decode 成功 |

## 教訓 (方法論)

2 ヶ月の調査から得られた、次の長期切り分けに持ち越すべき教訓。多くは[方法論監査](2026-07-02_092013_hang_investigation_methodology_audit.md)の指摘と各セッションの「罠」に由来する。

1. **陰性証拠は発生率とセットでしか意味を持たない**。再現率数 % の故障では「対策後 30 回 clean」は偶然でも 2〜3 割起きる。hang 側・clean 側を対称にプールし Fisher 検定で有意水準を越えるまで「確定」と言わない (bedrock 方式)
2. **試験の有効性を cycle ごとに機械検証する**。「VPN が張られているつもりで 30 回中 29 回張られていなかった」confound で確定級の結論が全面撤回された。以後の BT_PAN_VALID ゲート (ESP SA 双方向の機械確認) が調査全体の信頼性を支えた
3. **ロールバックは検証するまで完了ではない**。「s2idle に戻したはず」が残存フックで毎回 deep 化けしていた事件。構成変更後は実効値 (この場合は journal の `PM: suspend entry (s2idle)`) を必ず実測する
4. **ジャーナルは suspend 側と resume 側の停止を区別できない**。exit 欠落だけでは「suspend 中に止まった」とは言えない (実際は resume 側だった)。対称性の錯誤に 3 週間気づけなかった
5. **RTC 由来の証拠は成功 cycle の対照を必ず取る**。Mac firmware の RTC リセット値が偶然正規の pm_trace 記録に decode できてしまう偽物を、「成功 cycle 後の再起動でも同じ値が出る」ことで見抜いた
6. **watchdog panic は偽陽性判別をルーチン化する**。intel_pch_thermal の正規冷却ループ (最大 60 秒) が watchdog 60 秒と正確に衝突した実例。再起動検知時は pstore の panic 対象デバイスで本物か判別する
7. **観測系そのものが摂動になる**。pm_trace arm では発生率が ~7% から ~40% へ濃縮された。摂動 tag ごとに統計を分離し、非摂動プールと合算しない
8. **体感の回数は当てにならない**。ユーザ体感 32 回に対し機械台帳 37 回など、n は必ず durable な台帳 (PRE/POST marker ファイル) から取る
9. **計測手段への投資は早いほうがよかった**。「DPM_WATCHDOG カーネルが唯一の機序決着手段」と早期に分かっていながら着手が 7 月にずれ込み、5〜6 月は決着し得ない観測 (スナップショットとログ) を続けた。一方で、着手後は dpmwd1→4 の 4 世代を 4 日で回して決着させた
10. **自己修正が機能する構造を保つ**。confound の発見も誤結論の撤回もすべて自前の再検証によるもの。advisor 役 (別視点のレビュー) の指摘が bedrock 化・監査の両方で効いた

## 未解明事項・残タスク

- **バスレベルの最後の瞬間**: 「汚い復帰」が親ポート D3hot 復帰過渡とどう相互作用して全システム停止 (タイマ/NMI ごと) に至るかの最終メカニズム。ソフトウェアで取れる証拠は C-9 で出尽くしており、PCIe アナライザ等の専用測定器の領域。実用上の必要性はない (対策確立済み)
- **wl BAR0+0x1408 の実名**: 書き込み失敗 TLP の宛先レジスタの意味 (blob 内シンボルとの突合、優先度低)
- **無人 wake の源**: C-9 hang #2 で観測された「誰も触っていないのに wake が始まる」現象の起源 (wakeup 有効デバイスは LID0 と内蔵キーボードのみ)。無保護実験時の運用注意 (lid close 放置禁止) として対処済み
- **保護あり構成での bus-watch 比較**: 恒久対策下で radio-off 残渣がどう変わるかの安価な追加観測 (`c9-bus-snap.sh` 残置済み)
- **C-8/C-9 残置物のクリーンアップ**: 調査用フック・スクリプト類の棚卸し (dpmwd4 は再演用に意図的に残置)
- **soak の継続**: stock + udev rule での常用がそのまま非摂動検証を兼ねる。ウォッチリスト = hang 再発 / 原因不明の再起動 / 待機電力の体感悪化

## 参照レポート一覧 (時系列)

### フェーズ 1: 発覚と対症療法 (S3 → s2idle)

| レポート | 一行要約 |
|---|---|
| [2026-05-10 lid open 復帰失敗の切り分け](2026-05-10_055032_lid_open_resume_hang.md) | 問題発覚。S3 hang としてシグネチャ化と暫定対策開始 |
| [2026-05-22 applespi blacklist](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) | 再発、候補 2 の適用 (効果なし) |
| [2026-05-23 pcie_aspm=off](2026-05-23_144518_s3_hang_pcie_aspm_off.md) | 再発、ASPM 無効化 + pm_print_times 恒久化 |
| [2026-05-31 s2idle へ切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md) | スリープ方式の恒久切替 |
| [2026-06-01 s2idle でも hang](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) | 「S3 特有」説の崩壊、RTC ストレスで切り分け |
| [2026-06-03 電源ボタン wake 前提検証](2026-06-03_123439_pwrbtn_wake_premise_verification.md) | 検証手段の健全性確認 |

### フェーズ 1.5: S3 復活の挑戦と挫折 (背景)

| レポート | 一行要約 |
|---|---|
| [2026-06-18 KB バックライトと lid wake](2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe.md) | s2idle の lid wake は構造的に不可能と確定 |
| [2026-06-18 なぜ S3 deep を使わないか](2026-06-18_142303_why_not_s3_deep_sleep.md) | 経緯の整理 (通読版) |
| [2026-06-18 S3 復活評価](2026-06-18_233837_s3_revival_evaluation.md) | battery spurious wake 源 = gpe70 特定 |
| [2026-06-19 S3 待機電力](2026-06-19_094329_s3_battery_standby_power.md) | ~0.1 W (s2idle の 1/7) で go 判断 |
| [2026-06-20 S3 永続化 + soak 開始](2026-06-20_045414_s3_deep_persist_soak_start.md) | 可逆な永続化と 2 週間試験 |
| [2026-06-27 BT テザリング中の lid close hang](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) | soak 中に 4 ハング、S3 復活 no-go。再現条件の原型 |
| [2026-06-28 s2idle ロールバック不完全の発見](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) | 「毎回 deep で寝ていた」の修正、真の s2idle 初実証 |

### フェーズ 2: 再現条件の確立

| レポート | 一行要約 |
|---|---|
| [2026-06-28 BT-PAN×VPN×lid close 手動再現](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) | 3/3 hang、相互作用の確定 (以後の署名基準) |
| [2026-06-28 カーネルソース机上解析](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) | 仮説群 H1〜H7 の設定 |
| [2026-06-28 自動 suspend では再現せず](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) | lid close 経路の固有性 |
| [2026-06-28 peer 非依存・lid 経路必要](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md) | 2×2 切り分け |
| [2026-06-29 btusb unload clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) | 22/22 clean (radio-on 系 clean の一角) |
| [2026-06-29 driver path 25 cycle](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) | traffic 要因の erosion |
| [2026-06-29 bnep teardown 30 cycle clean](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) | 後に confound で無効化される clean |
| [2026-06-30 VPN autoconnect confound 発覚](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) | 200520 の全面撤回、有効性ゲート導入の契機 |
| [2026-06-30 検証付き 30/30 clean](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) | BT_PAN_VALID 初の成立 (radio-on clean) |
| [2026-07-01 WiFi off で hang 再現](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) | radio-off 条件の独立再現 |
| [2026-07-01 ping confound 排除](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) | トラフィック要因の消去 |
| [2026-07-01 wl unload 30/30 clean](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) | 「wl が鎖の中にいる」ヒント |
| [2026-07-02 方法論監査](2026-07-02_092013_hang_investigation_methodology_audit.md) | 2 ヶ月 29 本の棚卸し、構造的バイアスの指摘 |
| [2026-07-02 bedrock 化](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) | 0/60 プールで p ≈ 0.024、必要条件の統計的確立 |

### フェーズ 3: 計測カーネルによる停止点特定

| レポート | 一行要約 |
|---|---|
| [2026-07-02 dpmwd1 ビルド・デプロイ](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md) | DPM_WATCHDOG=y + pstore e2e 検証 |
| [2026-07-03 dpmwd1 で hang 再現も panic 沈黙](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) | 停止段の絞り込み第 1 弾 |
| [2026-07-03 dpmwd2 デプロイ](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) | late/noirq watchdog 拡張、29 cycle clean |
| [2026-07-04 実戦 panic は偽陽性](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md) | intel_pch_thermal との衝突、偽陽性判別の確立 |
| [2026-07-04 全監視沈黙の hang](2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md) | 停止段 ∈ {syscore, s2idle-enter} (後に訂正) |
| [2026-07-04 pm_trace の RTC リセット罠](2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md) | Mac firmware の壁と偽 decode の発見 |
| [2026-07-05 停止は resume 側 (C-4)](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md) | firmware-safe pm_trace で 4/4 decode、対称性錯誤の訂正 |
| [2026-07-06 停止デバイス実名化 (C-5)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md) | 署名 A (TB ブリッジ) / 署名 B (i915) の二極化 |

### フェーズ 4: 名指し介入 → 真因確定 → 恒久化

| レポート | 一行要約 |
|---|---|
| [2026-07-06 pcie_port_pm=off で hang 消滅 (C-6)](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md) | 0/30 (p ≈ 1.7×10⁻⁴)、両署名の共通上流 = PCIe D3 |
| [2026-07-07 待機電力 4〜5 倍の代償](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) | 広域介入のコスト定量化、絞り込みへ |
| [2026-07-08 TB のみ保護は不十分 (Rung 1)](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md) | 署名 B 再発、wl 親ポートへの接点浮上 |
| [2026-07-09 非 TB 3 本で消滅 (Rung 2)](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md) | 真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5} |
| [2026-07-10 真犯人 00:1c.2 確定 + udev 恒久対策 (Rung 3)](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md) | 0/37 (p ≈ 7.5×10⁻⁵)、一本釣り成功 |
| [2026-07-12 機序解明 + stock 復帰 (C-8)](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md) | 4360 PCIe2 war の特定、計測カーネル退役 |
| [2026-07-12 無保護トレースと物証 (C-9)](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md) | 停止点実名 + バスエラー残渣、hang 調査の最終レポート |
| [2026-07-12 旧カーネル整理](2026-07-12_230643_housekeeping_old_kernels_cleanup.md) | dpmwd1〜3 purge、現行構成の確定 |

## 添付ファイル

- [執筆プラン](attachment/2026-07-13_005126_suspend_hang_investigation_summary/plan.md)
