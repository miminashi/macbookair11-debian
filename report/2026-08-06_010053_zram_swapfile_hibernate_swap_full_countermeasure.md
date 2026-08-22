# zram と swapfile の増設で「swap 満杯によるハイバネート失敗」を防ぐ対策を実施した

- **実施日時**: 2026年8月6日 01:00 (JST)
- **作業時間帯**: 2026年8月6日 00:17〜01:00 (JST)

## 概要

前夜 (8月5日) に起きた「バッテリ 3% での低バッテリハイバネートが swap 満杯で書き込み失敗し、電池切れでセッションを失った」事象への対策を実施した。原因調査の結論は「7 日間の連続稼働で swap 3.7GiB が通常のメモリ退避に使い切られ、ハイバネートイメージを置く場所が残っていなかった」というものだったので、対策の骨子は「実行時のメモリ退避を別の受け皿に逃がし、既存の swap パーティション (sda3) をハイバネート専用の空き領域として温存する」こととした。

具体的には swap を 3 層に階層化した。第 1 層は zram (RAM 内圧縮 swap、3.7GiB、優先度 100)、第 2 層は root 上に新設した 8GiB の swapfile (優先度 50)、第 3 層が従来の sda3 (優先度 -2、変更なし) である。カーネルは優先度の高い swap から使うため、日常のメモリ退避は zram → swapfile の順に吸収され、sda3 は zram と swapfile の計 11.7GiB を使い切らない限り書き込まれない。これで「いざという時に sda3 が埋まっていてイメージが書けない」という前回の失敗経路が構造的に塞がれる。

設計にあたっての制約が 2 つあった。まずディスク末尾の未割当 15.5GiB は SSD 寿命のための over-provisioning 領域なので触らない (当初検討した sda3 の後方拡張は却下)。また root (ext4) のオンライン縮小は不可能でリモート作業に向かないため、パーティション変更を伴わない swapfile 方式を採用した。なお現代のカーネルでは swapfile の I/O はファイルシステム層をバイパスするため、性能はパーティション swap と同等である。

懸念だった「swap が複数あると systemd がハイバネート先に優先度上位の swapfile を選んでしまわないか」は、systemd v257 のソースを裏取りして否定した。`/sys/power/resume` が設定済み (本機は initramfs が毎 boot sda3 を設定) の場合、systemd は devno が一致する swap だけを候補にし、優先度比較は行わない。zram もパス名判定で候補から除外される。つまりハイバネート先は sda3 に固定されたままで、resume 経路も一切変更していない。

検証は再起動 e2e とハイバネート往復 e2e の両方を実施し、全項目 green だった。特にハイバネート e2e は、メモリ負荷をかけて zram に 661MB の実データを退避させた状態 (このとき swapfile と sda3 の使用は 0 で、優先度設計どおりの動作も同時に実証) で実行し、RTC alarm による自動復帰後にテスト用プロセスが生存し「Hibernation image restored successfully」がログに残ることを確認した。変更はすべて可逆で、ロールバック手順を本文に記載した。

## 前提・目的

- 背景: [2026-08-05 の調査レポート](2026-08-05_233935_hibernate_write_failed_swap_full_battery_died.md) で、低バッテリハイバネート失敗の根本原因が swap 満杯 (`PM: Cannot get swap writer` + ENOSPC) と特定された
- 目的: ユーザ要望「zram によるメモリ圧縮と swap の拡張の併用」を、ハイバネート経路を壊さずに実装する
- 制約: ディスク末尾の未割当 15.5GiB は SSD 寿命用の OP 領域として不可侵。root のオフライン縮小 (live USB 作業) は行わない
- 方式・サイズ (swapfile 8GiB)・ハイバネート e2e 実施は 2026-08-06 にユーザが選択済み

## 環境情報

- 機体: MacBook Air 11" (Early 2015), RAM 3.7GiB
- OS: Debian 13 (trixie), カーネル 6.12.95+deb13-amd64 (stock), systemd 257.9-1~deb13u1
- ディスク: APPLE SSD SM0128 113G = sda1 EFI 976M / sda2 root ext4 93.1G / sda3 swap 3.7G / 未割当 15.5G (OP)
- resume 設定: initramfs `RESUME=UUID=65051de6-9f...` → `/sys/power/resume` = 8:3 (sda3)。今回変更なし
- スリープ構成: GRUB `mem_sleep_default=deep` (S3)、バッテリ lid close = suspend-then-hibernate、低バッテリ 5% 以下で直行ハイバネート、sleep フック群 (45-wl-unload 等) — 今回いずれも変更なし

## 実施内容

### 3 層 swap 構成 (今回の変更点)

| 層 | デバイス | サイズ | priority | 役割 | 実現方法 |
|---|---|---|---|---|---|
| 1 | /dev/zram0 (zstd) | 3.7GiB | 100 | 実行時退避の第一受け皿 (圧縮 RAM 内) | `systemd-zram-generator` 1.2.1-2 新規導入 + `/etc/systemd/zram-generator.conf` |
| 2 | /swapfile (ext4) | 8GiB | 50 | zram 溢れ時のオーバーフロー | `fallocate` で作成 (76 extents)、fstab に `sw,pri=50` で追記 |
| 3 | /dev/sda3 | 3.7GiB | -2 | ハイバネートイメージ専用に温存 | 変更なし |

追加で `/etc/sysctl.d/99-zram.conf` に `vm.swappiness=100` (zram 前提で退避を積極化) と `vm.page-cluster=0` (zram のスワップイン readahead 無効化) を設定した。

### systemd のハイバネート先選定の裏取り (ソース確認)

systemd v257 `src/shared/hibernate-util.c` の `find_suitable_hibernation_device_full()` を確認した:

- `/sys/power/resume` が非 0 の場合、devno が一致する swap エントリだけを候補にし、それ以外は全てスキップする (priority 比較は resume 未設定時専用の分岐)
- `/dev/zram*` はパス名判定で候補リスト追加前に除外される
- resume 設定済みの場合、`sleep.c` 側で `write_resume_config()` は呼ばれず `/sys/power/resume` は書き換えられない

したがって本構成 (swapfile prio 50 > sda3 prio -2) でも、ハイバネート先が swapfile に奪われることはなく、sda3 固定が保たれる。`resume=` カーネル引数の明示などの追加設定は不要と判断した。

### 導入時のつまずき (記録)

`systemd-zram-generator` はパッケージインストール時に同梱デフォルト設定 (`/usr/lib/systemd/zram-generator.conf`: zram-size=min(ram/2,4G)・lz4) で zram0 を即座に作成する。その後に `/etc/systemd/zram-generator.conf` を置いても稼働中デバイスには反映されないため、`systemd-zram-setup@zram0.service` の stop → daemon-reload → start で作り直した。この際 `dev-zram0.swap` ユニットの再起動を短時間に繰り返して start-limit-hit に当たったが、`systemctl reset-failed` 後の起動で正常化した。恒久状態には影響なし (再起動 e2e で boot 時から正しい設定で起動することを確認済み)。

## 検証結果 (全て green)

### 再起動 e2e

- boot 後に 3 層 (zram0 prio 100 / swapfile prio 50 / sda3 prio -2) が自動復元
- zram0 は zstd / disksize 3.7G で起動 (設定反映確認)
- `/sys/power/resume` = 8:3 維持、sysctl 適用済み、failed unit なし

### 優先度階層の実証

メモリ負荷 (計 3.4GB 確保) をかけたところ、退避 661MB が**全て zram0 に入り、swapfile と sda3 の使用は 0** だった。設計どおり sda3 が最後まで温存されることを実測で確認した。zstd の圧縮も機能 (テストデータはほぼゼロページのため圧縮率は参考値)。

### ハイバネート往復 e2e (zram に実データがある状態)

1. 上記のメモリ負荷プロセス 2 つ (計 3.4GB) を生かしたまま、RTC wakealarm を 3 分後にセットして `systemctl hibernate` 実行 (00:56:10)
2. イメージ作成 333121 pages (約 1.3GB) → sda3 へ書き込み → 電源断
3. RTC alarm (00:59:07 JST = RTC/UTC 15:59:07) で自動起動 → イメージ復元 → `PM: hibernation: Hibernation image restored successfully` (00:59:29)
4. 復帰後の確認: テスト用プロセス 2 つとも生存 (メモリ状態復元の実証)、zram 内の退避データ健全、`/sys/power/resume` = 8:3 維持、wl-unload フック pre/post とも正常発火

前回失敗時と同じ「swap に実データが載った状態でのハイバネート」が、今回は成功した (前回との差分 = 実行時退避が zram に隔離され sda3 が空)。

副観測: ハイバネート処理中の `Preallocating image memory` (イメージ用メモリ確保) に伴い、カーネルが追加のページ退避を行った先も zram だった (復帰後の zram 使用が 661MB → 2.9GB に増加、sda3 は復帰後 0 のまま)。イメージ縮小のためのメモリ解放も sda3 を消費しない = 設計どおり sda3 の空きがイメージ書き込みにフルに使える。

## 運用上の注意

- 実行時 swap が zram + swapfile の計 11.7GiB を超えると sda3 が使われ始め、同種の失敗が再発しうる。従来実績 (7 日連続稼働で 3.7GiB) の 3 倍の容量なので実用上は到達しにくいが、`free -h` で swap 使用が 4GiB (zram 容量) を大きく超えていたら swapfile まで溢れているサインなので、再起動または AC 運用を推奨
- zram の実 RAM 消費は `zramctl` の TOTAL 列で観測できる。メモリ逼迫が疑われる場合は `zram-size = ram / 2` への縮小を検討 (conf 1 行 + 再起動)
- root の空きは 71G → 63G に減少 (swapfile 8GiB 分)。OP 領域 15.5GiB は不可侵のまま

## ロールバック手順 (全て可逆)

```bash
# zram 撤去
sudo swapoff /dev/zram0
sudo rm /etc/systemd/zram-generator.conf
sudo systemctl daemon-reload
sudo apt-get purge systemd-zram-generator

# swapfile 撤去
sudo swapoff /swapfile
sudo rm /swapfile
# + /etc/fstab から「/swapfile none swap sw,pri=50 0 0」の行を削除

# sysctl 撤去
sudo rm /etc/sysctl.d/99-zram.conf
sudo sysctl --system
```

sda3・initramfs RESUME・GRUB・sleep フックは一切変更していないため巻き戻し不要。

## 再現方法 (実施手順)

すべて開発機から ssh 経由で実施。

1. zram 導入:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo apt-get install -y systemd-zram-generator'
   # /etc/systemd/zram-generator.conf を作成:
   #   [zram0]
   #   zram-size = ram
   #   compression-algorithm = zstd
   #   swap-priority = 100
   # 反映 (インストール直後はデフォルト設定でデバイスが作られているため作り直し):
   ssh miminashi@macbookair2015.lan 'sudo systemctl stop systemd-zram-setup@zram0.service; sudo systemctl daemon-reload; sudo systemctl restart systemd-zram-setup@zram0.service && sudo systemctl start dev-zram0.swap'
   ```
2. swapfile 作成:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon -p 50 /swapfile'
   ssh miminashi@macbookair2015.lan 'echo "/swapfile none swap sw,pri=50 0 0" | sudo tee -a /etc/fstab'
   ```
3. sysctl (`/etc/sysctl.d/99-zram.conf` に swappiness=100 / page-cluster=0) → `sudo sysctl --system`
4. 再起動して 3 層構成・`/sys/power/resume`=8:3 を確認
5. ハイバネート e2e (RTC 自動復帰):
   ```bash
   # メモリ負荷で zram に退避を作った上で
   ssh miminashi@macbookair2015.lan 'echo 0 | sudo tee /sys/class/rtc/rtc0/wakealarm; date -d "+3 min" +%s | sudo tee /sys/class/rtc/rtc0/wakealarm; sudo systemctl hibernate'
   # 復帰後: journalctl で "Hibernation image restored successfully"、プロセス生存、/proc/swaps を確認
   ```

## 添付ファイル

- [実装プラン](attachment/2026-08-06_010053_zram_swapfile_hibernate_swap_full_countermeasure/plan.md)

## 関連レポート

- [2026-08-05 swap 満杯によるハイバネート失敗の調査](2026-08-05_233935_hibernate_write_failed_swap_full_battery_died.md) — 本対策の起点。同レポート「対策の選択肢」の 3 (swap 拡張) を swapfile 方式で、追加で zram 階層化を実施した形
- [2026-06-18 実使用 3% でのハイバネート成功実証](2026-06-18_053417_hibernate_success_snapshot.md) — swap に空きがあれば低バッテリハイバネートが完走することの実証。今回の対策は「その前提 (sda3 の空き) を常時保つ」ためのもの
- [2026-06-15 バッテリ連動ハイバネートの修理](2026-06-15_234635_fix_battery_hibernate_btp.md) — 低バッテリ直行ハイバネート (閾値 5%) の整備
