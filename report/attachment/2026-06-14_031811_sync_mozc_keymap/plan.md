# macbookair2015 の日本語入力ショートカットをローカル(開発機)と一致させる

## Context

ユーザは、運用対象機 **macbookair2015.lan** (= リポジトリ名の "macbookair11") の
日本語入力中のショートカットキー割当を、**いま Claude が動いているこの開発機(ローカル)**と
一致させたい。

両機とも IME は **ibus-mozc 2.29.5160.102** (完全同一バージョン) を使用しており、
日本語入力中のショートカット割当は mozc の設定ファイル
`~/.config/mozc/config1.db` (plaintext protobuf) に格納されている。

### 調査で判明した事実 (重要)

ローカルとリモートの `config1.db` を protobuf としてパースし、フィールド単位で
厳密比較した結果、**メタデータ (field 1: タイムスタンプ) を除く差分は次の 2 フィールドだけ**で、
他の全設定 (記号入力・文字形・各種フラグ等 47 フィールド) はバイト単位で一致していた。

| field | 意味 | ローカル(開発機) | リモート(macbookair2015) |
|---|---|---|---|
| 41 | `session_keymap` (キーマップ種別) | `0` (NONE) | `1` (CUSTOM) |
| 42 | `custom_keymap_table` (キーマップ本体) | len=5095 bytes | len=4875 bytes (内容も別) |

→ **キーマップ以外の設定は既に同一**なので、ローカルの `config1.db` を丸ごとリモートへ
コピーすることは「キーマップ(field 41/42)だけを移植する」ことと等価で、副作用がない。

注: `session_keymap=NONE` が mozc 内部で既定キーマップに解決されるのか格納テーブルを使うのかは
本環境からは断定できないが、field 41 と 42 の両方をコピーすればリモートはローカルと
**バイト同一**になり、いずれにせよ挙動が一致する。よって NONE の意味解決は不要。

### 矛盾チェック: なぜ remote を NONE(0) にするのか

「キーマップを同期するのに session_keymap を NONE にするのは矛盾では?」と見えるが、矛盾はない:

- 目的は**ローカルと一致させること**であり、ローカルは `session_keymap=NONE`。一致させるには
  remote も NONE にする必要がある (NONE は「キーマップ無効」ではなく、mozc がその種別を
  解決して使う内部既定値)。
- 仮に field 42 (テーブル) だけコピーし remote を `CUSTOM(1)` のまま残すと、remote は明示的に
  そのテーブルを使う一方、ローカルは NONE 解決で動くため、NONE が既定キーマップに解決される
  場合に**両者が食い違う**。したがって field 41 と 42 の**両方**をコピー (=丸ごとコピー) する
  ことが、確実に一致させる唯一の方法。これがフィールド単位の surgical 編集ではなく
  whole-file コピーを採る理由でもある。

## 変更対象

- リモート機 `macbookair2015.lan` の `~/.config/mozc/config1.db` のみ
  (`history.db` / `segment.db` 等の機種固有・暗号化ファイルは触らない)

## 実装手順

ssh はサンドボックス無効状態で疎通済み (`ssh miminashi@macbookair2015.lan`)。
**順序が重要**: バックアップ → コピー → 即時 `pkill` (稼働中サーバが旧設定を書き戻す
レースを避けるため)。

1. **リモートの現行設定をバックアップ** (タイムスタンプ付き)
   ```bash
   ssh miminashi@macbookair2015.lan \
     'cp -a ~/.config/mozc/config1.db ~/.config/mozc/config1.db.bak.$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)'
   ```

2. **ローカルの config1.db をリモートへ転送** (パイプで内容を流し込む)
   ```bash
   cat ~/.config/mozc/config1.db | \
     ssh miminashi@macbookair2015.lan 'cat > ~/.config/mozc/config1.db'
   ```
   (`scp` でも可。所有者・パーミッションは `miminashi` のまま維持される)

3. **mozc サーバを再起動して新設定を反映** (コピー直後に即実行)
   ```bash
   ssh miminashi@macbookair2015.lan 'pkill -x mozc_server; pkill -f ibus-engine-mozc'
   ```
   - mozc_server は config1.db を起動時のみ読むため、再起動しないと反映されない
   - `ibus-engine-mozc` が次の IME 利用時に mozc_server を遅延再起動し、新 config を読む
   - これでログアウト不要で反映される。万一反映されない場合の最終手段はリモートの
     デスクトップセッションでログアウト/ログイン

## 検証

1. **設定がバイト一致したことを確認** (apply 後にリモートの config1.db を再取得しパース)
   ```bash
   ssh miminashi@macbookair2015.lan 'cat ~/.config/mozc/config1.db' > /tmp/remote_after.db
   # python で field 41==0 かつ field 42 == ローカルの field 42 バイト列 を assert
   ```
   - `field 41 (session_keymap) == 0` であること
   - `field 42 (custom_keymap_table)` がローカルのものと完全一致すること

2. **実打鍵の最終確認はユーザに依頼**: リモート機の GUI 上で実際にアプリへ日本語入力し、
   変換中のショートカット (Space で変換、Ctrl+; 等の割当) が開発機と同じ挙動になるか
   確認してもらう。Claude 側からは生きた打鍵確認はできないため、これは明示的にユーザ確認とする。

## ロールバック

不具合時はバックアップから復帰:
```bash
ssh miminashi@macbookair2015.lan \
  'cp -a ~/.config/mozc/config1.db.bak.<TS> ~/.config/mozc/config1.db && pkill -x mozc_server; pkill -f ibus-engine-mozc'
```

## (任意) レポート

本作業は実験ではなく単純な設定同期のため、レポートは必須ではない。記録を残したい場合のみ
`report/` に作成する (CLAUDE.md のレポート規約に従い、JST タイムスタンプは
`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得)。
