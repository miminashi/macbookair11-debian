# hang 問題まとめレポート執筆プラン

## Context

MacBook Air 11" (Early 2015) + Debian 13 の suspend hang 問題は、2026-05-10 の発覚から 2026-07-12 の Phase C-9 まで約 2 ヶ月・約 27 本のレポートにわたって調査され、真因確定 (wl の親 PCIe root port 00:1c.2 の sleep 中 D3hot 遷移) と恒久対策 (udev rule で 00:1c.2 を D0 固定 + stock カーネル復帰) に到達した。個別レポートは各セッションの断片であり、全体を通読できる総括が存在しない。ユーザの依頼は「hang 問題のまとめレポート」の執筆。

## 成果物

`report/2026-07-1x_hhmmss_suspend_hang_investigation_summary.md` (タイムスタンプは執筆時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得)

- タイトル案: 「スリープ復帰ハング問題の調査総括 — 発覚から真因確定・恒久対策まで」
- 新規の実験は行わない。既存レポート群 + メモリの知見の**統合・再構成**が本体
- 現在の実機構成 (カーネル版、udev rule、soak 状況) のみ ssh で軽く実測して「現在の構成」節に反映する (サンドボックスの都合で ssh 不可なら最終レポート記載値を使用し、その旨明記)

## レポート構成

1. **概要** (5〜8 段落、平易な日本語の通読可能な文章)
   - 症状 → 長期化した理由 (再現率数%・ログ皆無の「静かな死」) → 切り分けの流れ → 真因 → 対策 → 現状、を物語として
2. **前提・目的** — 本レポートは総括であること、対象読者 (将来の自分/類似機体の調査者)
3. **環境情報** — MacBook Air 7,1 / Debian 13 / BCM4360 (broadcom-sta wl) / TB2 (Falcon Ridge) / 現在: stock 6.12.95 + udev rule
4. **問題の症状** — lid open 復帰失敗、画面真っ暗・電源ボタン長押しのみ、再現率 ~数%〜数十回に 1 回、ログ無し
5. **調査の経緯 (フェーズ別)** — 各フェーズ見出し + 数段落 + 該当レポートへの相対リンク
   - フェーズ 1: S3 hang 発覚と対症療法 → s2idle 恒久切替 (5/10〜6/03)。s2idle でも再発
   - フェーズ 1.5 (背景): S3 復活評価・待機電力・soak → 6/27 の 4 ハングで no-go、s2idle 復帰。ロールバック不完全 (deep 化け) の教訓も含む
   - フェーズ 2: BT-PAN×VPN×lid close の factorial 切り分け → 「wl loaded かつ radio-off」必要条件の統計的確立 (Fisher p≈0.024, bedrock)
   - フェーズ 3: dpmwd1〜4 計測カーネル。watchdog 全沈黙 → pm_trace firmware-safe encoding → 停止点は **resume 側** noirq/main と特定、署名 A (TB bridge) / 署名 B (i915) の実名化
   - フェーズ 4: 名指し介入の梯子。C-6 pcie_port_pm=off (0/30) → C-7 Rung1〜3 で 00:1c.2 一本釣り (0/37, p≈7.5e-5) → C-8 機序解明 (wl の 4360 PCIe2 war) + stock 復帰 → C-9 バスエラー物証 (AER CorrErr/MAbort)
6. **真因と機序** — 必要条件の連鎖 (wl loaded + radio off + 手動 lid close + 親 D3hot)、war の resume 短縮経路、i915 は被害者、C-9 の AER 物証
7. **恒久対策と現在の構成** — udev rule 全文、pcie_port_pm=off 撤去、stock 6.12.95、待機電力トレードオフ (0.7W→1.6W)、モバイル時はハイバネ/シャットダウン推奨
8. **統計サマリ** — 主要 arm の hang 率テーブル (hang pool 5/56→9/24、clean 0/112、介入後 0/30・0/37 等、Fisher p 値)
9. **教訓 (方法論)** — 方法論監査 (07-02_092013) + 各レポートの「罠」から抜粋: confound 検証 (VPN autoconnect)、RTC 由来証拠は成功対照必須、ロールバック検証、体感 n と台帳 n のズレ、pstore/watchdog 偽陽性判別など
10. **未解明事項・残タスク** — バスレベル最終瞬間の詳細、BAR0+0x1408 実名、無人 wake 源、C-8 クリーンアップ、soak 継続
11. **参照レポート一覧** — 時系列の全 hang 関連レポート (約 27 本) をファイル名リンク + 一行要約で列挙
12. **添付ファイル** — 本プランファイル (`report/attachment/<レポート名>/plan.md` にコピー)

## 執筆手順

1. `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得、ファイル名確定
2. (可能なら) ssh で現在構成を確認: `uname -r`、udev rule 存在、`cat /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed`。ssh 不可なら省略しレポート記載値を使用
3. 主要転換点レポート数本 (05-10 発覚、07-02 bedrock、07-05 C-4、07-06 C-5/C-6、07-10 C-7 Rung3、07-12 C-8/C-9) の概要を Read で確認し、要約の正確性を担保
4. レポート本文執筆 (Write)
5. プランファイルを `report/attachment/` にコピー、リンク記載
6. CLAUDE.md のルール通り書き漏らし確認 → 矛盾点検の通読
7. コミットはユーザ指示があれば実施 (勝手に push しない)

## 検証

- レポート内リンク (参照レポート・添付) が実在ファイルを指すことを `ls` で確認
- 日時表記が JST・分まで入っていることを確認
- 概要が 8 段落以内・平易な日本語であることを通読確認
