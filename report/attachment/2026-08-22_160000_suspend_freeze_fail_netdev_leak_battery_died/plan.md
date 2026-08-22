# 2026-08-21 ハイバネート失敗 (バッテリ枯渇死) の調査結果とレポート作成プラン

## Context

8/21 夜、MacBook Air が再びハイバネートに失敗し強制電源断状態で発見された。調査の結果、
**8/6 の swap 満杯とは別の新しい障害モード**であることが確定した。swap・ハイバネート機構自体は健全で、
suspend の前段 (プロセス freeze) が構造的に失敗し続け、lid closed のまま約 5 時間再試行ループして
バッテリが枯渇した。

## 確定した事象チェーン (証拠は journalctl -b -1 / /var/log/wl-unload.log)

1. **8/21 17:30:37** lid close (バッテリ駆動) → logind が suspend-then-hibernate 開始
2. NM sleep teardown で wlp3s0 (wl) の切断と VPN GSNet (charon-nm, nm-xfrm-1102441) の teardown が並走
3. その最中に **cfg80211 WARN @ net/wireless/sme.c:848** (`__cfg80211_connect_result` の
   `WARN_ON(bss_not_found)`、v6.12 ソースで確認済)。この WARN 自体は **8/6 以降ほぼ毎回の
   suspend teardown で発生していた既往症** (8/06 ×3, 8/08 ×2, 8/11 ×2, …) で、通常は実害なし
4. 今回だけ **netdev refcount 破壊**に至った:
   - `unregister_netdevice: waiting for wlp3s0 to become free. Usage count = 10` (リーク)
   - `unregister_netdevice: waiting for nm-xfrm-1102441 to become free. Usage count = -8` (**アンダーフロー**)
   - 両 netdev の unregister が永久に完了しない状態 (回復不能、要再起動)
5. pre hook `45-wl-unload` の `modprobe -r wl` (PID 639913) が netdev_wait_allrefs で
   **D state 永久ブロック** (timeout 10 の SIGTERM/SIGKILL も無効)
6. suspend 実行段で **freeze 失敗**: `Freezing user space processes failed after 20.007 seconds
   (2 tasks refusing to freeze)` — charon-nm が `netdev_run_todo` 内 D state (+ 上記 modprobe)
7. logind は lid closed のため**約 6.7 分周期で無限再試行** (17:30〜22:40 で約 46 回、
   wl-unload.log に FAILED 49 件)。全て同じ freeze 失敗で status=1
8. **22:40:58 journal 途絶 = バッテリ枯渇死** (今回 boot に `EXT4-fs (sda2): orphan cleanup` =
   不正終了痕跡、pstore 空 = panic ではない)。ハイバネート画像の書き込みには一度も到達していない

## 性質の整理

- 旧仮説 H1 (xfrm→netdev ref leak→netdev_wait_allrefs) の signature が**初めて実地で発現**。
  ただし対象は「resume hang (C-7 で解決済)」とは別の、**suspend 前段 teardown の障害**
- 必要条件は「WiFi 接続中 + VPN (xfrm) 稼働中の sleep teardown」。radio-off や BT-PAN は無関係
- WARN は高頻度・リーク発現は低頻度 (16 日で 1 回) の確率的 race
- 一度発現すると suspend は二度と成功できないのに lid closed で再試行し続ける構造が
  「バッテリ枯渇死」に直結した (フェイルセーフ不在)

## プラン

### 1. レポート作成 (必須)

- `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得
- `report/<ts>_suspend_freeze_fail_netdev_leak_battery_died.md` (英語ファイル名は実際の ts で)
- 構成: 概要 (平易な段落 5 前後) / 前提・目的 / 環境情報 / 事象タイムライン /
  証拠と解析 (WARN・refcount・freeze 失敗・再試行ループ) / 8/6 障害との違い /
  対策の選択肢と次アクション / 再現・確認方法 (journalctl コマンド)
- 添付: `report/attachment/<レポート名>/` に journal 抜粋 (WARN トレース、freeze 失敗、
  再試行ループ、wl-unload.log 抜粋) + 本プランファイル (plan.md)
- 書き漏らし・矛盾の再点検 (CLAUDE.md ルール)

### 2. フェイルセーフ導入 (ユーザ承認済み・実施する)

「リーク発現後の suspend 永久失敗 → 枯渇死」を断つ、小さく可逆な対策:

- system-sleep post hook (例 `48-netdev-leak-guard`) を新設:
  post 段で `dmesg | grep "unregister_netdevice: waiting"` を検査し、署名検出時は
  wall 通知 + ログ記録の上で `systemctl poweroff` (クリーンシャットダウン)
  - リーク発現後は再起動以外に回復手段がないため、poweroff が正当
  - 誤爆リスク低 (署名は正常時に出ない)。rm で従来動作に戻る可逆設計
- 実機での検証: hook の dry-run (署名なし時 no-op を確認)。リーク自体の再現は不可能なので
  署名検出ロジックは擬似入力でテスト

### 3. 対策の続き (レポートに次アクションとして記載のみ)

- VPN 先行切断 (teardown 順序制御) の設計検討 — race 窓の縮小
- cfg80211 WARN error path / broadcom-sta の refcount バグのコードレベル調査 (opus 委譲候補)

### 4. メモリ更新

- `low-battery-hibernate.md` に本障害 (新モード: freeze 失敗系) を追記
- `s2idle-btvpn-hang-mechanism-ladder.md` に H1 signature 初発現の事実を追記

## 検証方法

- レポート: リンク切れ・添付パス・JST 表記・概要の通読性を確認
- hook (導入時): 署名なし環境で no-op、擬似署名でロジック発火をテスト後、実機配置
