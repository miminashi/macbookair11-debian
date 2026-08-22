# バッテリ切れ直前のハイバネートが swap 満杯で失敗し、電池切れでセッションを失った

- **実施日時**: 2026年8月5日 23:39 (JST)
- **事象発生日時**: 2026年8月5日 18:20〜23:30 (JST)

## 概要

8月5日の夜、蓋を開けても作業状態が戻らず「ハイバネーションからの復帰に失敗したかもしれない」という状況になった。実機のジャーナルとスリープフックのログを調べた結果、実体は「復帰の失敗」ではなく、**そもそもハイバネーションのイメージ書き込みが失敗しており、成立していなかった**ことが分かった。

流れはこうである。18時20分、バッテリ残量 3% の状態で蓋を閉じたところ、systemd が低バッテリ (3% ≤ 閾値 5%) を検知し、suspend を飛ばして直行ハイバネートを実行した。この発火自体は 6月に整備した低バッテリ連動の設計どおりである。メモリのスナップショット作成までは成功したが、swap への書き込み段階で「PM: Cannot get swap writer」(ENOSPC = 空き無し) というエラーで失敗した。

失敗を受けて systemd は S3 suspend にフォールバックし、残量 3% のままスリープに入った。その後ジャーナルは途絶しており、suspend 中にバッテリが枯渇して電源断となった。23時30分に AC を繋いで電源を入れた時にはイメージが存在しない (書けていないので当然) ため、フレッシュブートとなり、作業状態が失われた。

書き込み失敗の根本原因は **swap の満杯**である。エラーメッセージが「Not enough free swap」(空きが image より少ない) ではなく「Cannot get swap writer」+ ENOSPC であることから、swap の空きスロットが文字どおりゼロだったことが確定する。前回起動は 7月29日から約 7 日間の連続稼働で、RAM 3.7GiB のこの機体では swap 3.7GiB が通常のメモリ退避で使い切られており、ハイバネートイメージを置く場所が残っていなかった。

システム自体に異常はない。panic の痕跡はなく (pstore 空)、S3 の保護フック (wl unload 等) も正常に動作しており、再起動後の現在は swap 使用 0B・バッテリ充電中で健全である。教訓は「長期連続稼働で swap が埋まっていると、いざという時の低バッテリハイバネートが物理的に不可能になる」という点で、対策の選択肢を本文末尾にまとめた。

## 前提・目的

- 背景: 本機は 7/29 に S3 (deep) の soak を通過して GRUB deep 恒久化 (S3 本採用) 済みで、バッテリ時の lid close は suspend-then-hibernate、バッテリ 5% 以下では直行ハイバネートという構成で常用中 ([2026-07-29 カメラ有効化レポート](2026-07-29_191159_facetimehd_camera_enable.md) に同日の GRUB deep 恒久化を記載)
- 目的: ユーザ報告「ハイバネーションからの復帰に失敗したかもしれない」の事実関係と原因を特定する
- 前提条件: 実機への変更は行わない読み取り専用調査 (プランモードで実施)

## 環境情報

- 機体: MacBook Air 11" (Early 2015), RAM 3.7GiB
- OS: Debian 13 (trixie), カーネル 6.12.95+deb13-amd64 (stock)
- swap: /dev/sda3, 3906556kB (約 3.7GiB), initramfs に `RESUME=UUID=65051de6-9fb3-4588-8f89-3b9cd714e859` 設定済み
- スリープ構成: GRUB `mem_sleep_default=deep` (S3 本採用)、バッテリ lid close = suspend-then-hibernate、45-wl-unload / 46-lid0-ac-policy / 47-facetimehd フック稼働
- 前回 boot: 2026-07-29 22:34 起動 〜 2026-08-05 18:21 (約 7 日間連続稼働)

## 事象の時系列 (2026-08-05, JST)

| 時刻 | 事象 |
|---|---|
| 18:06:17 | バッテリ 9% で lid close → 通常 suspend (S3) |
| 18:09:31 | lid open で正常復帰 (cap 11%)。この時点まで S3 は健全 |
| 18:20:50 | バッテリ **3%** (charge_now 111mAh) で lid close → suspend-then-hibernate 開始 |
| 18:20:52 | systemd-sleep が低バッテリ判定: `BAT0: Found battery with capacity below threshold (3% <= 5%)` → suspend を飛ばして `Performing sleep operation 'hibernate'` |
| 18:20:59 | freeze・スナップショット・デバイス thaw まで成功後、`PM: hibernation: Writing hibernation image.` → **`PM: Cannot get swap writer`** で失敗。systemd-sleep: `Failed to put system to sleep. System resumed again: No space left on device` |
| 18:20:59 | `Couldn't hibernate, will try to suspend again.` → フックが再度発火 (wl unload 正常) |
| 18:21:00 | `Performing sleep operation 'suspend'` (S3) を最後にジャーナル途絶 |
| 18:21〜23:30 | suspend 中にバッテリ枯渇 → 電源断 (WAKE 記録なし、s3-soak.log にも WAKE 行なし) |
| 23:30:43 | AC 接続 + 電源投入。新しい boot ID でフレッシュブート。`PM: Image not found (code -22)` (イメージは書けていないので当然)。pstore 空 = panic ではない |

## 原因分析

### 直接原因: swap 満杯によるイメージ書き込み失敗

カーネルのハイバネート書き込み経路では、swap の空き総量不足は `swsusp_write()` 内の `enough_swap()` チェックで「Not enough free swap」となるが、今回のエラーは `get_swap_writer()` 段の「Cannot get swap writer」+ ENOSPC である。この組み合わせは `get_swap_writer()` → `alloc_swapdev_block()` が**最初の swap map ページの 1 スロットすら確保できなかった**場合に対応し、swap の空きが実質ゼロだったことを意味する (kernel/power/swap.c)。

swap 構成・resume 設定自体は正常である (今回 boot でも同一 UUID で swap 有効化済み、使用 0B)。つまり「設定の壊れ」ではなく「7 日間の連続稼働で 4GB RAM 機の swap 3.7GiB が通常のページ退避で埋まっていた」という状態の問題である。

なお、実機に sysstat 等は未導入のため事象当時の swap 使用率の直接記録はなく、「swap 満杯」はカーネルのエラー経路 (どの分岐がこのメッセージと ENOSPC を出すか) からの特定である。ただしこの経路は空きスロットゼロ以外では通らないため、結論の確度は高い。今後同種の切り分けを直接証拠で行いたい場合は、対策 2 の swap 監視がそのままログ代わりになる。

### なぜ「復帰失敗」に見えたか

低バッテリハイバネートの発火 (閾値 5%) は設計どおり機能したが、書き込みが失敗して S3 フォールバックに落ち、残量 3% では S3 (実測 約0.09W) でも持たずに電源断となった。ユーザ視点では「ハイバネートしたはずが起きたら消えていた」= 復帰失敗に見えるが、実体は「ハイバネート不成立 + suspend 中の電池切れ」である。6/18 に実証した「実使用 3% でハイバネート発火 → S4 resume 完走」の成功例との差分は、当時は swap に空きがあったことに尽きる。

### 無関係と判定した事項

- 18:20:51 の kernel WARNING (`__cfg80211_connect_result` net/wireless/sme.c:848): 45-wl-unload フックによる wl/cfg80211 unload と WiFi 切断イベントの競合で出た無害な警告。18:06 の lid close 時にも同種のトレースあり。ハイバネート失敗より前の事象であり本件と無関係
- S3 hang (歴代調査対象): 今回は hang ではない。suspend 突入は正常で、pstore も空
- facetimehd: S2 DRAM 検証まで正常にログされており問題なし

## 対策の選択肢 (提案のみ、未実施)

1. **運用 (即効・変更なし)**: バッテリ残量が少ない時は早めに AC に繋ぐ。数日以上の連続稼働後は再起動して swap を解放しておく (swap 使用量は `free -h` で確認可能)
2. **swap 使用率の監視・警報**: swap 使用率が高い状態では低バッテリハイバネートが機能しない旨を警告する仕組み (例: cron / 既存フック群に閾値チェックを追加)。実装は軽量で可逆
3. **swap 拡張**: パーティション再構成が必要で影響が大きい。RAM 3.7GiB + 使用中 swap を同居させるには現行 3.7GiB では余裕がない、という構造問題への根本対処だが、コストに見合うかは要検討
4. **低バッテリ閾値 (5%) の引き上げについて**: 発火自体は正常に機能しており、閾値を上げても swap が満杯なら同じ失敗をする。単独では対策にならない点に注意

## 再現方法 (調査手順)

すべて開発機から ssh 経由・読み取り専用で実施。

1. boot 履歴と現在の稼働状況:
   ```bash
   ssh miminashi@macbookair2015.lan 'uptime; last -x -n 15; journalctl --list-boots | tail -5'
   ```
2. 前回 boot 末尾のハイバネート失敗ログ:
   ```bash
   ssh miminashi@macbookair2015.lan 'journalctl -b -1 -n 60 --no-pager'
   ssh miminashi@macbookair2015.lan 'journalctl -b -1 --no-pager --since "2026-08-05 17:00" | grep -E "systemd-sleep|Performing sleep|Lid|BAT0"'
   ```
3. 今回 boot の resume 試行と pstore:
   ```bash
   ssh miminashi@macbookair2015.lan 'journalctl -b 0 --no-pager | grep -iE "hibernat|Image"; sudo ls -la /sys/fs/pstore/ /var/lib/systemd/pstore/'
   ```
4. swap / resume 設定とフックログ:
   ```bash
   ssh miminashi@macbookair2015.lan 'cat /proc/cmdline; free -h; grep -r RESUME /etc/initramfs-tools/conf.d/'
   ssh miminashi@macbookair2015.lan 'tail -30 /var/log/s3-soak.log; tail -20 /var/log/wl-unload.log'
   ```

## 添付ファイル

- [実装プラン](attachment/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died/plan.md)
- [前回 boot 最終時間帯のジャーナル (18:05〜途絶まで)](attachment/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died/journal_boot-1_final_hour.log)
- [今回 boot 冒頭のジャーナル (Image not found 含む)](attachment/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died/journal_boot0_head.log)
- [s3-soak.log 末尾 (バッテリ残量と SLEEP/WAKE 台帳)](attachment/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died/s3-soak_tail.log)
- [wl-unload.log 末尾 (保護フックの動作記録)](attachment/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died/wl-unload_tail.log)

## 関連レポート

- [2026-07-29 soak 通過・GRUB deep 恒久化 + カメラ有効化](2026-07-29_191159_facetimehd_camera_enable.md) — S3 本採用と現行スリープ構成の経緯
- [2026-06-15 バッテリ連動ハイバネートの修理 (_BTP 経路問題)](2026-06-15_234635_fix_battery_hibernate_btp.md) — 低バッテリ直行ハイバネート (閾値 5%) の整備
- [2026-06-18 実使用 3% でのハイバネート成功実証](2026-06-18_053417_hibernate_success_snapshot.md) — 当時は swap に空きがあり S4 resume 完走。今回との差分は swap の空きの有無
- [2026-06-08 バッテリ枯渇シャットダウンの初回調査](2026-06-08_035056_low_battery_hibernate.md)
