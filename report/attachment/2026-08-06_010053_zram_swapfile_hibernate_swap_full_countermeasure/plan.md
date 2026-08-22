# zram 導入 + swapfile 増設による低バッテリハイバネート保全プラン

## Context

2026-08-05 の夜、バッテリ 3% での低バッテリ直行ハイバネートが **swap 満杯** (7 日連続稼働で sda3 3.7GiB が通常のページ退避で使い切られていた) により `PM: Cannot get swap writer` (ENOSPC) で失敗し、S3 フォールバック中にバッテリが枯渇してセッションを失った ([調査レポート](../projects/macbookair11-debian/report/2026-08-05_233935_hibernate_write_failed_swap_full_battery_died.md))。

対策としてユーザの要望は「**zram によるメモリ圧縮と swap の拡張の併用**」。設計上の制約・決定事項:

- ディスク末尾の未割当 15.5GiB は **SSD 寿命のための OP (over-provisioning) 領域なので触らない** (当初案の sda3 後方拡張は却下)
- root (ext4) のオンライン縮小は不可能でリモート作業に適さないため、**swapfile 8GiB 方式** をユーザが選択
- 設定完了後に **ハイバネート e2e テスト (RTC wakealarm 自動復帰) まで実施** することをユーザが選択

## 実機の現状 (2026-08-06 調査済み)

- MacBook Air 11" Early 2015, RAM 3.7GiB, Debian 13 (trixie), kernel 6.12.95+deb13-amd64 (stock), systemd 257.9-1~deb13u1
- ディスク: sda 113G = sda1 EFI 976M / sda2 root ext4 93.1G (使用 17G, 空き 71G) / sda3 swap 3.7G / 未割当 15.5G (OP、不可侵)
- swap: sda3 のみ (UUID=65051de6-...)、fstab は UUID 指定、initramfs `RESUME=UUID=65051de6-...`
- `/sys/power/resume` = `8:3` (sda3)、`/sys/power/resume_offset` = 0 → ハイバネート先は sda3 に固定されている
- zram モジュール (`zram.ko.xz`) と zstd (`crypto/zstd.ko.xz`) は stock カーネルに同梱。zram 系パッケージは未導入 (trixie に `systemd-zram-generator` 1.2.1-2 あり)
- `vm.swappiness` = 60 (デフォルト)、fstrim.timer enabled
- sleep 構成: GRUB `mem_sleep_default=deep` (S3 本採用)、バッテリ lid close = suspend-then-hibernate、低バッテリ 5% 以下で直行ハイバネート、sleep フック群 (45-wl-unload 等) 稼働中 — **今回いずれも変更しない**

## 設計

3 層の swap を優先度で階層化し、sda3 を「実行時にはほぼ使われないハイバネート専用領域」として温存する:

| 層 | デバイス | サイズ | priority | 役割 |
|---|---|---|---|---|
| 1 | /dev/zram0 (zstd) | zram-size = ram (3.7G) | 100 | 実行時 swap の第一受け皿 (圧縮 RAM 内) |
| 2 | /swapfile (ext4, root) | 8GiB | 50 | zram 溢れ時のオーバーフロー |
| 3 | /dev/sda3 | 3.7G (不変) | -2 (デフォルト) | ハイバネートイメージ専用に温存 |

- カーネルは priority の高い順に swap を消費するため、sda3 は zram (3.7G 分) + swapfile (8G) を使い切るまで書き込まれない → 「swap 満杯でイメージが書けない」の構造的防止
- ハイバネート書き込み先は `/sys/power/resume`=8:3 (initramfs が毎 boot 設定) のまま不変。resume 経路 (initramfs RESUME=UUID) も不変
- **裏取り済み (systemd v257 ソース、src/shared/hibernate-util.c `find_suitable_hibernation_device_full()`)**: `/sys/power/resume` が非 0 の場合、systemd は devno 一致する swap (= sda3) だけを候補にし、priority 比較は一切行わない (priority 選定は resume 未設定時専用)。また `/dev/zram*` はパス名判定で候補から除外される。したがって swapfile (prio 50) や zram0 (prio 100) がハイバネート先を横取りする経路は存在せず、`/sys/power/resume` の書き換えも発生しない (sleep.c で resume_set=true のため write_resume_config は呼ばれない)。追加設定 (resume= カーネル引数の明示等) は不要
- sysctl 調整 (可逆): `vm.swappiness=100` (zram 前提で退避を積極化)、`vm.page-cluster=0` (zram のスワップイン readahead を無効化しレイテンシ改善)
- swapfile はハイバネート書き込み先にしない (resume_offset 運用は採らない) ため、断片化・COW 等の懸念なし。ext4 + swapon は FS 層をバイパスして直接ブロック I/O するため性能はパーティション同等

## 実装手順 (実機の状態変更 = 本体が直接 ssh で実行、サブエージェントに委譲しない)

### Step 0: 前提確認

```bash
ssh miminashi@macbookair2015.lan 'cat /sys/class/power_supply/BAT0/capacity /sys/class/power_supply/ADP1/online; free -h; df -h /'
```
- AC 接続 (ADP1 online=1) を確認。バッテリのみなら AC 接続を依頼してから進める
- swap 使用がほぼゼロであること (現在 512Ki) を確認

### Step 1: zram 導入 (systemd-zram-generator)

```bash
ssh miminashi@macbookair2015.lan 'sudo apt-get install -y systemd-zram-generator'
```

`/etc/systemd/zram-generator.conf` を作成 (tee 経由):

```ini
# zram swap: 実行時 swap の第一受け皿 (2026-08-06 導入)
# 目的: sda3 をハイバネート専用に温存する (report/2026-08-05_233935)
[zram0]
zram-size = ram
compression-algorithm = zstd
swap-priority = 100
```

```bash
sudo systemctl daemon-reload
sudo systemctl start systemd-zram-setup@zram0.service
```

検証: `cat /proc/swaps` に zram0 (prio 100)、`zramctl` で zstd / disksize 3.7G。

### Step 2: swapfile 8GiB 作成

```bash
sudo fallocate -l 8G /swapfile      # 失敗時 fallback: dd if=/dev/zero of=/swapfile bs=1M count=8192 status=progress
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon -p 50 /swapfile
```

fstab に追記 (既存 sda3 行は不変):

```
/swapfile none swap sw,pri=50 0 0
```

検証: `cat /proc/swaps` で 3 層 (zram0=100 / swapfile=50 / sda3=-2)、`df -h /` (空き 71G→63G)、`filefrag /swapfile` で extent 数確認 (参考情報)。

### Step 3: sysctl 調整

`/etc/sysctl.d/99-zram.conf`:

```ini
# zram 前提のチューニング (2026-08-06, report/2026-08-05_233935 対策)
vm.swappiness = 100
vm.page-cluster = 0
```

`sudo sysctl --system` で適用、`sysctl vm.swappiness vm.page-cluster` で確認。

### Step 4: 再起動 e2e

```bash
ssh miminashi@macbookair2015.lan 'sudo reboot'
```

再接続後に確認:
- `/proc/swaps` が 3 層構成で復元されている (zram generator の boot 時自動起動、fstab の swapfile)
- `/sys/power/resume` = 8:3 のまま (initramfs が設定)
- `sysctl vm.swappiness` = 100
- 既存フックログ (wl-unload.log 等) に異常なし

### Step 5: ハイバネート e2e テスト (RTC wakealarm 自動復帰)

前提: AC 接続確認済み。マルチ swap 構成で systemd がイメージを sda3 に書くことの実証を兼ねる。

1. (推奨) 実データを swap に載せた状態を作る: 一時的にメモリを消費させ zram に数百 MB 退避させる (例: `stress-ng --vm` が無ければ python で確保 → 解放はテスト後)。過剰な負荷はかけない
2. RTC alarm セット + ハイバネート:
   ```bash
   ssh miminashi@macbookair2015.lan 'echo 0 | sudo tee /sys/class/rtc/rtc0/wakealarm; date -d "+3 min" +%s | sudo tee /sys/class/rtc/rtc0/wakealarm; cat /proc/driver/rtc'
   ssh miminashi@macbookair2015.lan 'sudo systemctl hibernate'
   ```
3. 約 3〜4 分待って再接続し確認:
   - `journalctl -b -1 | grep -E "hibernat|Writing|swap"` : `Writing hibernation image` 成功、エラーなし
   - `journalctl -b 0 | grep -iE "hibernat|image"` : `PM: Image loading` → resume 完走 (フレッシュブートでなく hibernate 復帰であること = boot ID とプロセス生存で確認)
   - 復帰後の `/proc/swaps` 健全、`/sys/power/resume` = 8:3
4. **失敗時 fallback**: RTC 復帰しない場合はユーザに電源ボタン押下を依頼 (事前にその旨を伝えてから hibernate を実行する)

### Step 6: レポート作成 + メモリ更新

- `report/` に新規レポート (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)。概要 (平易な日本語の段落)、前提・目的、環境情報、設計、再現方法、e2e 結果、ロールバック手順を記載
- 本プランを `report/attachment/<レポート名>/plan.md` にコピーし「添付ファイル」セクションからリンク
- 元レポート (2026-08-05_233935) の「対策の選択肢」に対する実施結果として関連レポートにリンク
- メモリ更新: `low-battery-hibernate.md` に対策実施 (zram+swapfile 3 層化、sda3 ハイバネート専用温存) を追記、MEMORY.md の該当行を更新

## ロールバック手順 (全て可逆)

- zram: `sudo swapoff /dev/zram0; sudo rm /etc/systemd/zram-generator.conf; sudo systemctl daemon-reload; sudo apt-get purge systemd-zram-generator`
- swapfile: `sudo swapoff /swapfile; sudo rm /swapfile` + fstab の追記行を削除
- sysctl: `sudo rm /etc/sysctl.d/99-zram.conf; sudo sysctl --system`
- sda3・initramfs RESUME・GRUB・sleep フックは一切変更しないため巻き戻し不要

## リスクと対応

| リスク | 対応 |
|---|---|
| systemd が hibernate 先に priority 上位の swapfile を選び resume 先を書き換える | **ソース裏取りで否定済み** (/sys/power/resume 設定済みなら sda3 固定、zram はパス名で除外)。Step 5 の e2e で実証も行う |
| 実行時 swap が zram+swapfile 計 11.7G を超えると sda3 が使われ始め、同種の失敗が再発しうる | 従来実績 (7 日で 3.7G) の 3 倍の容量で実用上到達困難。レポートに「swap 使用が swapfile まで溢れたら要注意」と運用注意を記載 |
| zram の実 RAM 消費によるメモリ逼迫 (3.7G 機) | zram-size=ram は「非圧縮換算の上限」で実消費は圧縮後 (~1/3 目安)。導入後に `zramctl` で mem_used を観測。問題あれば zram-size = ram/2 へ縮小 (conf 1 行) |
| ハイバネートイメージ (最大 RAM 3.7G 相当、カーネル側 LZO 圧縮) が sda3 3.7G に収まるか | sda3 が空なら 6/18 の実使用 3% ハイバネート成功実証と同条件。image_size デフォルト (2/5 RAM 目標) のまま |
| fallocate 起因の swapfile ホール | swapon がホールを拒否するため即検出。fallback は dd |
| e2e で RTC 復帰失敗 | 事前告知の上で実施し、失敗時はユーザに電源ボタンを依頼 |

## 検証まとめ (Definition of Done)

1. 再起動後に zram0 (100) / swapfile (50) / sda3 (-2) の 3 層が自動復元される
2. `/sys/power/resume` = 8:3 が維持される
3. ハイバネート往復 e2e が成功し、イメージが sda3 に書かれ resume 完走する
4. レポートとメモリが更新されている
