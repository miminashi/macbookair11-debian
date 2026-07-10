# 外出中発熱の状況確認レポート作成プラン

## Context

ユーザが MacBook Air を持って外出したところ、鞄の中で「使い捨てカイロ程度」の発熱があった (hang はなし)。ssh 読み取り専用調査の結果、原因は **pcie_port_pm=off 常用 soak の既知の代償 = s2idle 待機電力の悪化** と確定した。故障・新規異常ではないが、C-6 常用 soak のウォッチリスト (iii)「待機電力悪化」が実地で定量化された一級データであり、C-7 の残課題 (iii)「恒久対策評価 (待機電力計測)」が事実上完了したため、レポートに記録する。

## 調査で確定した事実 (レポートに記載する内容)

1. **hang / panic / 再起動なし**: uptime 1d21h (7/6 01:24 JST boot 継続)、pstore 空、suspend_stats fail=0、SLEEP/WAKE ペア欠落なし → ウォッチリスト (i)(ii) クリーン
2. **外出中の suspend は正常** (journal -b 0 + /var/log/s3-soak.log):
   - 7/7 19:19:26 SLEEP (cap 90%, charge_now 4,584,000 µAh, AC 抜き直後) → 21:03:41 WAKE (cap 78%, 3,947,000 µAh)、asleep 6,255 s、途中 wake なし
   - 7/7 21:56:29 SLEEP (suspend-then-hibernate, cap 50%, 2,518,000 µAh) → 22:45:36 WAKE (cap 43%, 2,147,000 µAh)、asleep 2,947 s
3. **suspend 中放電の定量化** (発熱の正体):
   - 区間 1: 637 mAh / 1.74 h ≈ 2.8 W (公称 7.6 V 換算)
   - 区間 2: 371 mAh / 0.82 h ≈ 3.4 W
   - 従来 s2idle 実測 ~0.70 W の **約 4〜5 倍**。pcie_port_pm=off で TB downstream 4 ポート含む PCIe ポート群が D0 常駐 (調査時点で 06:03.0 / 06:06.0 が D0/active を実確認) のため PCH が深い PC state に入れないことと整合
   - 発熱の体感には、鞄投入直前 21:03〜21:56 のバッテリ駆動使用 (cap 78%→50%) の余熱も上乗せ
4. 環境: kernel 6.12.94-dpmwd4、cmdline に pcie_port_pm=off、pm_trace=0 (inert)、mem_sleep=[s2idle]

## 作業内容

1. `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得
2. レポート作成: `report/<ts>_s2idle_standby_power_increase_on_pcie_port_pm_off.md`
   - タイトル案: 「pcie_port_pm=off 常用中の外出で判明した s2idle 待機電力の悪化 (約 4〜5 倍)」
   - CLAUDE.md ルール準拠: 概要 (通読できる段落文・5 段落目安)、日時 (JST・分まで)、前提・目的、環境情報、再現方法 (soak ログ差分から待機電力を算出する手順)、参照レポートリンク (2026-07-06_020526 C-6 ほか)
   - 「常用 soak ウォッチリスト消化状況」: (i) 再起動なし (ii) hang なし (iii) 待機電力悪化 = 本件で定量化、を明記
   - 「今後の選択肢」: C-7 (i) 絞り込み (pcie_port_pm=off を外し TB のみ d3cold_allowed=0 等) の優先度が上がった旨を記録 (実施はしない、記録のみ)
3. プランファイル添付 (必須ルール): `mkdir -p report/attachment/<レポート名>/ && cp` 本プラン → `## 添付ファイル` セクションからリンク
4. メモリ更新: `s2idle-btvpn-hang-mechanism-ladder.md` に (p) 追記 — soak 経過 (hang 0 継続) + 待機電力 2.8〜3.4 W 実測 (ベースライン 0.70 W の 4〜5 倍) + C-7 (iii) 実地完了、`MEMORY.md` の該当行 hook を更新
5. レポート事後セルフレビュー 2 段階 (書き漏らし確認 → 矛盾通読点検)

## 実機への変更

なし (読み取り専用調査のみで完結。pcie_port_pm=off は soak 継続のため残置)

## 検証方法

- レポートが CLAUDE.md の全ルール (ファイル名形式、概要の体裁、添付、JST 表記) を満たすことを確認
- 計算の再現: `sudo tail /var/log/s3-soak.log` の charge_now 差分 ÷ asleep_s × 7.6 V が本文の W 値と一致すること
