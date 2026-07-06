# MacBook Air 11" (2015) Debian パッチプロジェクト

MacBook Air 11-inch (Early 2015) で Debian 13 (trixie) を安定動作させるための、
ハードウェア互換性パッチ・ワークアラウンドの記録プロジェクト。

## 対象環境

- ハードウェア: MacBook Air 11-inch, Early 2015 (Broadwell-U)
  - SSD: APPLE SSD SM0128G (128GB, SATA)
  - Wi-Fi: Broadcom BCM4360 802.11ac (PCI 03:00.0)
- OS: Debian 13 (trixie)
- カーネル: 自前ビルド `6.12.94-dpmwd4` 系で運用中 (suspend hang 調査用に
  DPM watchdog + 拡張 pm_trace を組み込み。stock カーネルも残置しロールバック可)
- 主な利用ドライバ: broadcom-sta-dkms (`wl`)

## 目的

MacBook Air 11" で Debian 13 を安定運用するために必要な
ハードウェア互換性パッチ・ワークアラウンドを実装し、
その手順と検証結果をレポートとして蓄積する。

## 適用済みパッチ・ワークアラウンドの概要

- **ストレージ系**: 出荷時 SSD のハードウェア故障 (不良セクタ・SMART 無応答) を診断し、
  同型品への交換と交換後の健全性検査を実施。
- **Wi-Fi 系**: BCM4360 + `wl` ドライバが WPA-PSK-SHA256 非対応のため、
  AP 側 (OpenWrt) の WPA2+WPA3 トランジション設定下で接続不可となる問題に対処。
  暫定的に wpa_supplicant + systemd-networkd へ置き換えたのち、
  最終的に NetworkManager 1.52.1 のソースへ PMF=disable バグ修正パッチを適用し、
  GNOME GUI からの操作を復旧。
- **Wi-Fi 系 (DKMS 追従)**: その後 Debian カーネル更新 (`6.12.85+deb13-amd64`) で
  `broadcom-sta-dkms` が新カーネル向けに再ビルドされず `wl.ko` が消失し Wi-Fi が再喪失。
  根本原因は `linux-headers-amd64` メタパッケージ未投入で、
  メタを投入して DKMS が今後のカーネル更新に自動追従するよう恒久対策を実施。
- **電源管理系 (suspend/resume hang 調査 → `pcie_port_pm=off` で hang 消滅、soak 中)**:
  スリープからの復帰に時々失敗する (カーネルがハングし強制電源断が必要、週 ~0.7 件)
  問題を約 2 ヶ月かけて切り分けた。経緯の骨子:
  - ACPI S3 (deep) で hang が再発し続け、cold power-off でログが消えるためフィードバックが
    得られないことから **s2idle へ切替** (2026-05-31)。切替後も hang が再発し、
    「S3 deep firmware が原因」説は棄却。
  - 待機電力メリット (実測 ~0.1W、s2idle 0.70W の ~1/7) を狙って S3 (deep) の復活を検証
    したが、soak 中に BT テザリング絡みで hang が多発し **no-go、s2idle へロールバック**
    (2026-06-27〜28)。
  - 真の s2idle でも「BT-PAN テザリング × VPN × lid close」で hang を再現。factorial
    切り分けと統計検定 (clean 側 0/60、Fisher 片側 p≈0.024) で **「wl (Broadcom Wi-Fi
    ドライバ) がロードされ、かつ WiFi radio-off」が hang の必要条件**と確定
    (実用回避策 = WiFi radio 常時 on)。
  - DPM watchdog + 拡張 pm_trace 入りの自前カーネル (dpmwd1〜4) を 4 世代ビルドして
    停止点を追跡し、**停止は suspend 側でなく wake 成功後の resume noirq/early 段**、
    停止デバイスは **Thunderbolt 2 ブリッジ (pcieport) と i915 の 2 署名**と実名特定。
  - 名指し介入第 1 弾 **`pcie_port_pm=off` で hang 0/30** (同条件ベースライン 8/19≈42%
    に対し Fisher 片側 p≈1.7e-4) となり hang 消滅を確認。真犯人ポートの絞り込みと機序
    (BT+VPN+radio-off と PCIe D3 復帰の接点) は未解明のため「解決済み」ではなく、
    **ワークアラウンドとして実機に残置し `pcie_port_pm=off` + dpmwd4 構成で常用 soak 中**
    (2026-07-06 開始)。
- **電源管理系 (低バッテリ時ハイバネ)**: スリープ中のバッテリ枯渇でハイバネせず
  ハード電源喪失する問題を修正。本機は DMI Wake-up Type=Power Switch のため systemd の
  ハードウェア `_BTP` 経路が構造的にハイバネ不能と特定し、`BAT0/alarm=0` で RTC
  ポーリング経路へ強制する恒久修正を適用。実使用の電池 3% でハイバネが発火し
  S4 resume を完走することを実証済み。
- **その他**: スリープ中のキーボードバックライト消灯フック導入、mozc 日本語入力
  キーマップの開発機への同期。

## レポート一覧

`report/` 配下に時系列で蓄積。新しいものから記載する。

| 日時 (JST) | タイトル | 概要 |
|---|---|---|
| 2026-07-06 02:05 | [PCIe ポートの電源管理を切ったらハングが消えた — 名指し介入第 1 弾 (Phase C-6)](report/2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md) | 停止点実名への名指し介入第 1 弾として `pcie_port_pm=off` を適用し、高再現 arm (ベースライン hang 率 8/19 ≈ 42%) で 30 有効 cycle を駆動して **hang 0/30** (Fisher 片側 p≈1.7×10⁻⁴)。TB 狙いの介入で署名 B (i915) も同時に消え、PCIe ポートの D3 遷移が両署名の共通上流と強く示唆。パラメータは実機に残置し常用 soak へ |
| 2026-07-06 00:26 | [ハング停止点のデバイス実名を取得 — Thunderbolt ブリッジと GPU の 2 署名に二極化 (Phase C-5 / dpmwd4)](report/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md) | resume 側 pm_trace をデバイスマーカー書込みに置換した dpmwd4 で hang 4 回再現 (4/10 cycle) し、4 回とも停止デバイスの実名取得に成功。(A) Thunderbolt 2 ブリッジ downstream ポート (06:03.0/06:06.0) の noirq resume 入口 ×2 と (B) i915 (0000:00:02.0) の main resume 入口 ×2 の 2 署名に二極化。4/4 とも entry marker で callback 完了例なし、全監視も沈黙 |
| 2026-07-05 18:53 | [ハング停止点の特定 — 停止は suspend 側ではなく resume 側だった (Phase C-4 / dpmwd3)](report/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md) | firmware-safe encoding + s2idle 領域 TRACE 点を追加した dpmwd3 で hang 4 回再現・全回停止点 decode に成功。停止域は従来推定の suspend 側でなく **wake 成功後の dpm resume noirq/early 段のデバイス境界**と確定 (従来の suspend 側解釈を正式訂正)。DPM watchdog/hung_task/NMI hardlockup/softlockup の 4 監視が全沈黙する「静かな停止」で、30 分放置でも復帰せず |
| 2026-07-04 17:01 | [Phase C-3 — pm_trace の RTC チャネルは Mac firmware の日付リセットで boot を越えられないと確定 (偽 decode の罠込み)](report/2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md) | dpmwd 系列で 3 回目の hang 再現 (全監視また完全沈黙)。Mac firmware が boot 時に RTC 不正日付を 2016-01-01 へリセットするため素の pm_trace は構造的に使用不能と確定し、hash 偶然衝突 (1/997) が生む「もっともらしい偽 decode」の罠も解体。year が実年なら素通しされる救済路を発見し firmware-safe encoding (dpmwd3) の設計へ |
| 2026-07-04 02:28 | [Phase C-2 第 2 回 — dpmwd2 で hang 再現、拡張 watchdog も完全沈黙](report/2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md) | 同一 hang-arm 条件の再演で最初の lid close で hang 再現。late/noirq 拡張 watchdog も hung_task_panic も ~10 分完全沈黙 (pstore 空) で、停止段を {syscore, s2idle-enter} に絞り込み (当時の suspend 側解釈、後に C-4 で resume 側と訂正) |
| 2026-07-04 01:26 | [dpmwd2 初の実戦 panic 捕獲 — intel_pch_thermal 冷却ループと watchdog 60s の衝突 (偽陽性) の解明と緩和](report/2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md) | 普段使い中に DPM watchdog が初の実戦 panic を発火し pstore ダンプ捕獲に成功 (panic 自己申告能力の実戦検証完了)。中身は `intel_pch_thermal` の正規冷却待ちループ (最大 ~60s) と watchdog timeout 60s の衝突による偽陽性で、`delay_cnt` 600→300 で緩和 (可逆)。調査対象 hang の統計には不計上 |
| 2026-07-03 02:16 | [dpmwd2 (watchdog late/noirq 拡張カーネル) のデプロイと Phase C-2 第 1 回 — 29 cycle clean](report/2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) | watchdog を late/noirq 段へ拡張した `6.12.94-dpmwd2` をビルド・デプロイし同一 hang-arm 条件で再演したが hang 未再現 (0/29、全 cycle BT_PAN_VALID、生起確率的には通常変動内)。以降 dpmwd2 を常用カーネルとし、日常 hang も panic→pstore で自己申告する体制に |
| 2026-07-03 00:26 | [DPM_WATCHDOG カーネル上で hang 再現 — 18 分間の panic 沈黙で停止段を絞り込み](report/2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) | dpmwd1 で hang 再現 (1/24) も ~18 分間 watchdog/hung_task とも panic 発火せず pstore 空。この「沈黙」が判別情報となり停止段は main phase より後と絞り込み (当時の suspend 側解釈、後に C-4 で resume 側と訂正)。H4 (btusb URB drain) は強く disfavor、H2 (bnep kthread) も disfavor に転落 |
| 2026-07-02 18:28 | [DPM_WATCHDOG=y 自前カーネル (6.12.94-dpmwd1) のビルド・実機デプロイと pstore e2e 検証の完了](report/2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md) | 機序決着の唯一の出口とされた自前カーネルに着手。`CONFIG_DPM_WATCHDOG=y` の `6.12.94-dpmwd1` を開発機でビルドし実機にデプロイ、sysrq crash による pstore 回収 (dmesg 172KB) を end-to-end 検証し panic→自動復帰ループを確立。grubenv の sync 漏れという落とし穴も解決 |
| 2026-07-02 10:34 | [wl を完全に外した状態で 30 サイクル追加通過 — 合算 0/60 で「wl loaded かつ radio-off が必要条件」を統計的に裏付け](report/2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) | wl-unload arm で 30 cycle を追加し 30/30 clean、前セッションと合算 0/60 で Fisher 片側 p≈0.024 に到達。**「wl がロードされ、かつ WiFi radio-off」が hang の必要条件**が統計的に確立 (bedrock 化)。実用回避策 = WiFi radio 常時 on。次は DPM_WATCHDOG カーネルへ |
| 2026-07-02 09:20 | [ハングアップ調査 2 ヶ月間の方法論監査 — アプローチの問題点と見落としの棚卸し](report/2026-07-02_092013_hang_investigation_methodology_audit.md) | 5/10〜7/01 のレポート 29 本を読解ベースで監査 (新規実機実験なし)。「N 回連続クリーン」への過度依存・検証基準の後追い改訂・多変数同時変更などを指摘し、DPM_WATCHDOG カーネル未着手を最大の見落としとして以後の優先順位を再提示 |
| 2026-07-01 13:02 | [wl 完全 unload で 30/30 clean — 「wl-loaded かつ radio-off」単一変数分離の浮上](report/2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) | `rmmod wl` で wl を完全アンロードした状態で 30/30 clean (単独では決定力不足)。全セッション横断で hang/clean が「wl-loaded-AND-radio-off」の単一変数で綺麗に分離される読みが浮上し、N 拡大による統計的確立へ |
| 2026-07-01 10:29 | [Ping 無し条件下で WiFi-off + BT-PAN + VPN hang を独立再現 — ping confound 説を排除](report/2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) | 連続 ping を明示禁止した非対称設計で cycle 26 に hang 再現。「連続 ping が race 窓を広げた」説を反証し、同署名 hang の verified 3 例目 (063543/043251 に続く) に。「hang はたまたま」説は維持困難に |
| 2026-07-01 04:32 | [WiFi-off で BT-PAN + VPN 蓋閉じハングを独立再現 — 063543 と同シグネチャ](report/2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md) | WiFi-off 条件の 20 有効 cycle 中 cycle 20 で hang を独立再現 (xfrm 半分 teardown + suspend exit 欠落の同一署名)。「ベースラインほぼ 0」説が弱まる一方、「WiFi-on が protective」説は N=1 と ping confound のため未確定のまま |
| 2026-06-30 06:15 | [VPN watcher 付き再駆動で 30/30 有効 cycle clean — プロジェクト初の confound 無し N=30](report/2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) | VPN watcher loop + source-IP gate で 30/30 BT-PAN-valid cycle clean を達成、プロジェクト初の confound 無し verified N=30。063543 (~30% hang) の再現条件は本条件より narrower と判定し、one-variable-back (WiFi-off) の検証へ |
| 2026-06-30 03:03 | [VPN autoconnect 不安定の発覚 — 直前 2 セッションの clean 結果が confound で無効に](report/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md) | 表面上 0/30 clean だったが retro-classify で cycle 2 以降が VPN inactive のまま suspend していたと判明 (有効 N=1)。resume 後に VPN が autoconnect 復帰しないのが原因で、前セッション 200520 の 32/32 clean も同 confound で無効化。以後 valid-cycle 検証を必須とする設計に転換 |
| 2026-06-29 20:05 | [bnep 明示 teardown pre フックで手動 lid close 32/32 clean](report/2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) | suspend 直前に bnep を明示 teardown するフックを入れ手動 lid close 32/32 clean を観測 (後続 030349 で VPN autoconnect confound により結論無効化) |
| 2026-06-29 06:46 | [heavy traffic 中 driver path で 25 cycle 完走 — ただし真に traffic 中は 2/25 のみ](report/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) | ゼロビルドの free test (heavy traffic 中の driver path で hang するか) へ転回し 25 cycle 完走・hang 0。ただし iperf3 の idle 死や BT-PAN rename 等の連鎖で真に heavy traffic 中だったのは 2/25 のみで判別力は弱く、「lid close 必要条件」は覆らず |
| 2026-06-29 04:10 | [切り分けセッション 1: suspend 前 btusb 物理除去 (S1) で 22/22 クリーン](report/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) | suspend 前に `btusb` を物理除去する S1 で 22/22 全クリーン (中等度の陽性証拠)。btusb_suspend が critical path 上にある H4 寄りの方向性を支持するも、S1 は BT-PAN teardown も同時に起こすため真因の最終識別は不可 |
| 2026-06-28 14:12 | [peer 非依存・手動 lid-close 経路が必要条件であることを 2×2 で確定](report/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md) | iPad 手動 (hang 1/22) と driver 自動 (iPhone/iPad 合計 0/45) で 2×2 を完成。トリガーは「BT-PAN × VPN × 手動 lid-close 経路」の AND で peer (iPhone/iPad) 非依存と確定、hang 署名は iPhone 手動と完全同一 |
| 2026-06-28 11:12 | [Claude 自動駆動の systemctl suspend では BT-PAN × VPN ハングが再現せず](report/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) | 「BT-PAN × VPN」条件成立を per-cycle で立証した上で `systemctl suspend` を自動駆動し 15/15 完走・hang 0。同条件は必要だが十分でなく、lid-close 経路 (logind / LID GPE 等) の要素が追加の必要条件として浮上 |
| 2026-06-28 07:45 | [BT-PAN × VPN lid-close ハング — 関連カーネルソースの取得と怪しい箇所の特定](report/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) | 実機導入版 v6.12.94 のソースを精読し、停止を freeze 後の `dpm_suspend` device callback 段と推定。最有力 H4 = `btusb_suspend` の timeout 無し URB drain、race 供給源 H2 = non-freezable な bnep kthread を特定 (停止段推定は後に C-4 で resume 側と訂正、H4/H2 も dpmwd 系列で disfavor へ) |
| 2026-06-28 06:35 | [s2idle でも「BT-PAN テザリング × VPN」併用 lid close でハング再現 — 手動 factorial 切り分け](report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) | 真の s2idle・AC でも BT-PAN × VPN 併用の lid close で 3/3 true hang。BT-PAN 単独・VPN 単独・無線なしの単独要素は全てクリーンで、トリガーは相互作用に局在と確定 (ユーザの実使用実感と一致)。以後の切り分けの基準セッション (063543) となる |
| 2026-06-28 02:10 | [s2idle + BT テザリングでの suspend ハング再現実験 — 「s2idle ロールバック不完全」の発見](report/2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md) | soak 用フックに残った強制 deep 化コードにより、ロールバック後も実態は毎 suspend が deep だったことを発見・修正し、真の s2idle を初実証。真の s2idle では BT-PAN active でも 10/10 完走・hang 0 (deep との明確な対照) |
| 2026-06-27 07:25 | [Bluetooth テザリング中の lid close で計 4 回ハング — S3 deep は no-go、s2idle へロールバック](report/2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) | S3 deep soak 中に BT テザリング絡みで計 4 回のハングが顕在化した事故調査。当初「真因 = active BT-PAN」としたが btusb 完全除去でも 4 件目が発生して反証され、根因は BT 非依存の内在的 S3-deep hang (史実 ~0.7/週)・BT-PAN は増悪 stressor と結論。S3 deep 本採用は no-go とし s2idle へロールバック |
| 2026-06-20 04:54 | [S3 (deep) 永続化 (可逆方式) と 2 週間 passive soak の開始](report/2026-06-20_045414_s3_deep_persist_soak_start.md) | 待機電力 go を受け、deep を毎スリープ既定にする設定を oneshot service で可逆に永続化し 2 週間の passive soak を開始。残る go/no-go 判定材料は歴史的 S3 resume hang の再武装リスク (後に 6/27 の事故で no-go 決着) |
| 2026-06-19 09:43 | [battery 駆動 S3 (deep) の実待機電力測定 — 一晩計測で ~0.1W](report/2026-06-19_094329_s3_battery_standby_power.md) | LID0 wake 無効化 + battery で S3 を一晩維持し、実待機電力 ~0.1W (s2idle 実測 0.70W の ~1/7) を記録。主目的の待機電力低減は go と判定し、永続化 + soak へ |
| 2026-06-18 23:38 | [ハングを回避しつつ S3 (deep) sleep を復活できるか — 切り分け実験](report/2026-06-18_233837_s3_revival_evaluation.md) | 放棄されていた S3 を RTC ストレス + ssh 到達性で再評価。firmware 隔離は AC・lid open で 21/21 clean と健全、battery での ~6s spurious wake 源 = gpe70 (LID0 _PRW) と特定し、S3 復活の可能性が残る方向の結果 |
| 2026-06-18 14:23 | [なぜ ACPI S3 (deep sleep) を使っていないのか — 経緯と根拠の通読版](report/2026-06-18_142303_why_not_s3_deep_sleep.md) | 既存レポート群を統合した解説 (新規操作なし)。s2idle 運用の根拠を「hang が週 ~0.7 件で再発」「ログ痕跡が残らず原因特定手段が原理的に無い」「唯一の対処が故障経路 (S3 firmware 遷移) を使わないこと」の 3 点に集約 |
| 2026-06-18 13:55 | [キーボードバックライト消灯フック導入 + s2idle lid wake 復活可否の精査](report/2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe.md) | スリープ中のキーボードバックライト消灯フックを実装・検証。s2idle の lid wake はクリーンには不可能 (firmware/HW 制約) と機構的に決着し、過去の残存被疑 (c) LID0 notify 取りこぼしをクローズ |
| 2026-06-18 05:34 | [バッテリ連動ハイバネ成功の実証と現行設定スナップショット](report/2026-06-18_053417_hibernate_success_snapshot.md) | 実使用で電池残 3% (≤5% 閾値) でハイバネが発火し、boot_id 不変のまま S4 resume を完走したことを実機ログで実証。あわせて現行の電源管理設定を回帰判定の基準点としてスナップショット保存 |
| 2026-06-15 23:46 | [バッテリ連動ハイバネ不発の原因特定と修正 — ACPI _BTP 無効化で RTC ポーリング経路へ強制](report/2026-06-15_234635_fix_battery_hibernate_btp.md) | STH 設定後も枯渇死する根本原因 = 本機の DMI Wake-up Type が Power Switch のため、systemd 257 が壊れたハードウェア `_BTP` 経路を選びハイバネせず return していたことを逐語ソースで確定。`BAT0/alarm=0` で RTC ポーリング経路へ強制する恒久修正を適用 |
| 2026-06-14 03:18 | [mozc 日本語入力キーマップを開発機に同期](report/2026-06-14_031811_sync_mozc_keymap.md) | 設定は `~/.config/mozc/config1.db` の field 41 (session_keymap) / 42 (custom_keymap_table) に格納と特定し、運用機のキーマップを開発機に同期。学習履歴・暗号化系は機体固有のため対象外 |
| 2026-06-08 03:50 | [バッテリ枯渇時にハイバネーションさせる対応](report/2026-06-08_035056_low_battery_hibernate.md) | 低バッテリ時にハイバネせずシャットダウンした事象を調査し、s2idle サスペンド中の放電し尽くしによるハード電源喪失 (正規シャットダウンですらない) と確定。「低バッテリ → ハイバネ」が二重に塞がれていたことを特定し、suspend-then-hibernate による恒久対策へ |
| 2026-06-03 12:34 | [電源ボタン短押しは健全 s2idle を起こせる — 切り分け案 2 の前提検証](report/2026-06-03_123439_pwrbtn_wake_premise_verification.md) | hang 切り分け「案 2 (lid hang 時に電源ボタン短押しで復帰可否を見る)」の前提として、電源ボタン短押しが有効な wake 源であることを物理検証し前提成立を確認 |
| 2026-06-01 03:47 | [s2idle 切替後も resume hang 再発 — RTC ストレステストで原因切り分け](report/2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) | s2idle 切替 (5/31) 後 初日 21:25 に lid trigger で hang 再発。バッテリー枯渇ではなく真の hang と確定し、**ACPI S3 deep firmware 原因説を棄却**。`rtcwake -m mem` で s2idle を **68 サイクル (90s×60 + 1800s×6 + 既存2) 回して hang 0** (対して lid 1/5 hang)、wake 源非依存の suspend/resume hang を否定。ただし RTC は全て lid open での試験で lid 開閉/display 復帰経路を未再現のため、残存被疑は **(c) LID0 wake 間欠取りこぼし** vs **(b′) lid/display 固有 resume hang** (`i915.enable_dc=0` 除去で有力) の 2 つに絞られた。次は電源ボタン wake 検証 / lid 閉 RTC 試験で切り分け |
| 2026-05-31 13:21 | [S3 hang 対策: スリープモードを s2idle へ恒久切替 + spurious wakeup 抑止](report/2026-05-31_132125_s3_hang_switch_to_s2idle.md) | `pcie_aspm=off` 適用から ~7 日で再発 (5/30 18:44、`PM: suspend entry (deep)` で停止)。cold off で ring buffer 消失 + pstore/ERST 不在のため診断ループはフィードバック皆無と判明し、ACPI S3 deep を使わない **s2idle へ恒久切替** (`mem_sleep_default=s2idle`、失敗済み `pcie_aspm=off`/`i915.enable_dc=0` は除去)。s2idle の spurious wake (~84s) を `udev` で XHC1/RP01-06 wakeup 無効化し lid-only に固定。スリープ電力 0.70W (12h で 22%) を実測。resume 信頼性の長期観測へ |
| 2026-05-23 14:45 | [S3 hang 再発 (1 日 2 回) と `pcie_aspm=off` 追加 + `pm_print_times` 永続化](report/2026-05-23_144518_s3_hang_pcie_aspm_off.md) | `applespi` blacklist 適用直後の 35h で hang 2 件 (両方とも `PM: suspend entry (deep)` 直後で停止、`no_console_suspend` で追加情報得られず)。前回プラン Phase B 候補 3 (`pcie_aspm=off`) を適用し、診断強化として `pm_print_times=1` を tmpfiles.d で永続化。次回 hang 時には device-level suspend timing から原因 device を直接特定可能に |
| 2026-05-22 02:20 | [lid open 復帰失敗 (S3 hang) 再発と Phase B 候補 2 (applespi blacklist) 適用](report/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) | `i915.enable_dc=0` 導入から 12 日後の 5/19 に S3 hang 再発を確認 (停止位置は前回より早く device suspend phase)。前回プラン通り `applespi` ブラックリスト + `no_console_suspend` 追加 + 検出スクリプト v2 (末尾ログ判定方式) へ更新。v2 で過去 1 件の見落とし hang も追加発見、頻度は 4/1 〜 5/22 で 6 件 ≒ 週 0.8 件に更新 |
| 2026-05-17 10:53 | [Debian アップデート後デグレチェック (6.12.86→6.12.88 2 段昇格)](report/2026-05-17_105358_post_update_regression_check.md) | 5/17 の 2 段カーネル昇格を含むアップデート後、NM `+broadcomfix1` hold / DKMS 全カーネル installed / `i915.enable_dc=0` / SSD SMART いずれもデグレなしを確認。5/5 で入れた DKMS 自動追従恒久対策 (`linux-headers-amd64` メタ) の初実戦テスト合格 |
| 2026-05-10 05:50 | [lid open 復帰失敗 (S3 hang) 切り分けと暫定対策](report/2026-05-10_055032_lid_open_resume_hang.md) | journal 集計で 16 boot 中 4 件の S3 ハング (`PM: suspend entry (deep)` 直後で固まる) を確認。蓋開閉対照実験 (S3 30 cycle / s2idle 10 cycle / S3+`i915.enable_dc=0` 30 cycle) では fix の経験的 validation は得られず (A-1 でも 0 件)、理論ベースの暫定設定として `i915.enable_dc=0` を残し 4-6 週間の継続観測へ |
| 2026-05-05 00:09 | [カーネル更新で消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)](report/2026-05-05_000905_kernel_dkms_recovery.md) | Debian アップデートで `6.12.85+deb13-amd64` が入り `wl.ko` が消失。`linux-headers-amd64` メタを投入し DKMS 再ビルドで復旧、今後のカーネル追従を恒久化 |
| 2026-04-01 18:20 | [NetworkManager WPA-PSK-SHA256 パッチ適用](report/2026-04-01_182006_networkmanager_patch.md) | NM 1.52.1 のソースに PMF=disable バグ修正パッチを適用し、GNOME GUI からの Wi-Fi 操作を復旧 |
| 2026-04-01 08:01 | [Wi-Fi 接続問題 調査・修正](report/2026-04-01_080116_wifi_fix.md) | BCM4360 + `wl` ドライバが WPA-PSK-SHA256 非対応で接続不可。wpa_supplicant + systemd-networkd へ置き換えるワークアラウンド |
| 2026-03-30 18:54 | [SSD 健全性レポート (交換後)](report/2026-03-30_185423_sda_health_check.md) | 交換後 SSD (S2PBNYAGB28065) の SMART・dd・I/O カウンタ検査 → PASSED |
| 2026-03-30 14:31 | [SSD ディスク調査レポート](report/2026-03-30_143128_sda_investigation.md) | 旧 SSD (S29BNYDG874781) の不良セクタ・I/O タイムアウト・SMART 無応答を診断、ハードウェア故障と判定 |

その他の関連ファイル:

- `ssd_diagnosis_192.168.1.238.txt` — 初期 SSD 故障調査の生ログ (Samsung S4LN058A01[SSUBX] コントローラ故障)

## ディレクトリ構成

```
.
├── CLAUDE.md                      # レポート作成ルール (Claude Code 用)
├── README.md                      # このファイル
├── report/                        # 検証・修正レポート (Markdown)
│   ├── YYYY-MM-DD_HHMMSS_*.md
│   └── attachment/                # 各レポートに紐づくプランファイル等
│       └── <レポートファイル名>/
├── src/                           # 調査用に clone した OSS ソース (.gitignore で除外、コミットしない)
├── .ssh/                          # GitHub deploy key 運用 (鍵本体は .gitignore で除外)
│   ├── README.md
│   ├── git.sh                     # GIT_SSH_COMMAND 経由の git ラッパー
│   └── known_hosts
└── ssd_diagnosis_192.168.1.238.txt
```

## レポート作成ルール

レポートのファイル名規約・添付ファイル運用などは
[CLAUDE.md](CLAUDE.md) を参照。
