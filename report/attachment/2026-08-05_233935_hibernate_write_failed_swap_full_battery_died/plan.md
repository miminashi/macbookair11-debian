# ハイバネーション復帰失敗の調査レポート作成プラン

## Context

2026-08-05、ユーザから「ハイバネーションからの復帰に失敗したかもしれない」との報告。実機 (macbookair2015.lan) のジャーナル・フックログを読み取り専用で調査した結果、**原因は完全に特定済み**。本プランは調査結果をレポート化するもの (実機への変更は行わない)。

## 調査で確定した事実 (レポートに記載する内容)

### 事象の時系列 (2026-08-05, JST)

1. **18:06** バッテリ 9% で lid close → 通常 suspend (S3)、18:09 に lid open で正常復帰 (cap 11%)
2. **18:20:50** バッテリ **3%** で lid close → suspend-then-hibernate 開始
3. **18:20:52** systemd-sleep が低バッテリ判定 (`BAT0: 3% <= 5%`) → suspend を飛ばして**直行ハイバネート**を試行
4. **18:20:59** スナップショット作成は成功したが、イメージ書き込みで **`PM: Cannot get swap writer` → ENOSPC (No space left on device) で失敗**
5. systemd-sleep が「Couldn't hibernate, will try to suspend again」で **S3 suspend にフォールバック** (18:21:00、wl unload 保護フックは正常動作)
6. その後ジャーナル途絶 = **suspend 中にバッテリ枯渇 (3%/107mAh) → 電源断** → メモリ内容・セッション喪失
7. **23:30** AC 接続 + 電源投入でフレッシュブート (`PM: Image not found` = イメージ無し、当然)。pstore 空 = panic ではない

### 根本原因

- **swap 満杯**。カーネルの `get_swap_writer` → `alloc_swapdev_block` が ENOSPC = swap に空きスロットがゼロ (「Not enough free swap」ではなく「Cannot get swap writer」であることが決定的)
- 前回 boot は 7/29 22:34 から **約 7 日間連続稼働**、RAM 3.7GiB の機体で swap 3.7GiB (/dev/sda3) が使い切られていた
- resume= 設定 (initramfs RESUME=UUID=65051de6...) や swap 自体の構成は正常。**今 boot では swap 使用 0B で健全**

### 補足事実

- 前回 boot 中、STH のハイバネート段まで到達したのはこの 1 回のみ (それ以前の STH は全て suspend 段で復帰)
- 18:20:51 の cfg80211 WARNING (`__cfg80211_connect_result` sme.c:848) は wl unload フックと切断イベントの競合による無害な警告で、本件とは無関係
- 「復帰失敗」の実体 = **ハイバネーションは書き込み段階で失敗しており、そもそも成立していなかった**。S3 落ちしたまま電池切れ

## 実施内容 (レポート作成のみ、実機変更なし)

1. `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得
2. `report/<ts>_hibernate_write_failed_swap_full_battery_died.md` を作成
   - CLAUDE.md のレポート規約に従う: 平易な日本語タイトル、通読できる概要 (5 段落目安)、前提・目的、環境情報、時系列、原因分析、再現方法 (調査コマンド)、関連レポートへのリンク
   - 対策の選択肢を「提案」として記載 (実施はしない):
     - (a) 運用: バッテリ低下時は早めに AC 接続 / 長期稼働時は再起動で swap を解放
     - (b) swap 拡張 (要 repartition、4GB RAM 機で image + 使用中 swap の同居余裕を作る)
     - (c) swap 使用率の監視・警報 (swap 高使用時はハイバネート不能になる旨)
     - (d) systemd-sleep の閾値 5% はハイバネート実行自体には機能した (発火は正常)。閾値引き上げは swap 満杯там根本解決にならない点を明記
3. 添付: `report/attachment/<レポート名>/` に本プランをコピー、主要ログ抜粋 (journal 抜粋、s3-soak.log 末尾、wl-unload.log 末尾) を保存
4. 書き漏らし・矛盾の最終点検 (CLAUDE.md 規約)

## 検証方法

- レポート内の全タイムスタンプ・ログ引用が実機ジャーナルと一致することを確認済み (本調査で取得済みの生ログを添付に残す)
- 実機の現状健全性は確認済み: swap 0B 使用、バッテリ 30% 充電中、pstore 空
