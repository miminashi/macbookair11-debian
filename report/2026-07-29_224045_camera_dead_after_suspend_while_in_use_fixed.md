# カメラ使用中にスリープすると復帰後カメラが死ぬ問題 — 原因特定とドライバ修正

- **実施日時**: 2026年7月29日 20:30〜22:45 (JST)
- **執筆者**: Claude Fable 5 (Claude Code)

## 概要

同日夕方に導入したばかりの内蔵カメラについて、「カメラを使ったままスリープすると、復帰後にカメラが使えなくなる。カメラアプリはフリーズし、ブラウザは映像部分が真っ黒になる」という報告を受けて調査した。導入時のレポートで「カメラ使用中のスリープは未検証の構成」と注記していた、まさにその穴が踏まれた形である。

調べてみると、症状は「カメラが復帰しない」どころではなかった。このカメラのドライバは、スリープに入るときデバイスを丸ごと削除し、復帰時に一から作り直すという乱暴な作りになっている。カメラが誰にも使われていなければ、眠る前にドライバを外す保護フックが働いてこの経路を踏まずに済むのだが、カメラ使用中はドライバを外せないため、この乱暴な削除・再作成がアプリの目の前で起きる。アプリは消えた古いカメラデバイスを掴んだまま取り残され (これがフリーズと真っ黒の正体)、さらにアプリが古いデバイスを手放す瞬間、ドライバが既に破棄済みの内部データに触れてカーネルクラッシュ (Oops) を起こしていた。実際、報告のあった夜には Firefox 起因で 1 回、その後の再起動時のシャットダウン処理中に pipewire 起因でもう 1 回、計 2 回の Oops がログに残っており、2 回目はシャットダウンを約 5 分も引きずらせていた。ドライバの開発元も「デバイスを開いたままのスリープは未サポート」と公言している既知の弱点である。

対策として、ドライバに小さな修正パッチを当てた。方針は「デバイスを開いたまま眠っても、少なくとも壊れない」ようにすること。具体的には、削除処理の冒頭で「このデバイスはもう死んでいる」という印を立て、古いデバイスを掴んでいたアプリの後始末が走ってもハードウェアや破棄済みデータには一切触れないようにした。あわせて、映像待ちでブロックしたままのアプリを起こしてエラーを返す処理と、コントロール構造の解放を最後の利用者が手を離すまで遅らせる修正も入れた。

修正後の実機検証では、カメラを掴みっぱなしのプロセスを用意してスリープ・復帰させる再現試験を行い、従来カーネルクラッシュしていた「古いデバイスの手放し」が何事もなく完了することを確認した。掴んでいたプロセスはエラーを受け取って自力で終了し、カメラは新しいデバイス番号で復活、通常のフレーム取得も問題ない。カメラ未使用時の従来動作 (フックによるドライバ外し) にも退行はなかった。

運用上の注意はひとつだけ残る。カメラ使用中にスリープした場合、復帰後のカメラは新しいデバイス番号で生まれ変わるため、使っていたアプリ側では一度カメラを閉じて開き直す (アプリを立ち上げ直す) 必要がある。クラッシュもフリーズもしなくなったが、「何事もなかったかのように映像が続く」ところまでは求めていない。そこまでやるには実験的ドライバの大改造が必要で、リスクに見合わないと判断した。

## 添付ファイル

- [実装プラン](attachment/2026-07-29_224045_camera_dead_after_suspend_while_in_use_fixed/plan.md)
- [ドライバ修正パッチ](attachment/2026-07-29_224045_camera_dead_after_suspend_while_in_use_fixed/0001-survive-remove-with-open-fds.patch) (リポジトリ管理版: `patches/facetimehd/0001-survive-remove-with-open-fds.patch`)
- [カーネル Oops ログ 2 件](attachment/2026-07-29_224045_camera_dead_after_suspend_while_in_use_fixed/oops_logs.txt)

## 前提・目的

- 背景: report [2026-07-29_191159](2026-07-29_191159_facetimehd_camera_enable.md) で facetimehd (DKMS 0.7.0.1) を導入。suspend 中立化フック 47-facetimehd の「既知の穴」として「カメラ使用中は unload 失敗 → ドライバ載せたまま S3 = 未検証構成」を注記し soak ウォッチ対象としていた
- 報告症状: カメラ on のまま suspend → 復帰後、GNOME Camera (gnome-snapshot) はフリーズ、ブラウザはカメラ映像箇所が真っ黒
- 目的: 原因の特定と恒久対策 (ユーザ判断: ドライバ安全化 patch を採用、本格 PM 実装はしない)

## 環境情報

| 項目 | 値 |
|---|---|
| 機体 | MacBook Air 11" Early 2015 (MacBookAir7,1) |
| OS | Debian 13 (trixie)、kernel 6.12.95+deb13-amd64 |
| カメラ | Broadcom 1570 `02:00.0`、facetimehd 0.7.0.1 (DKMS) + firmware 1.43.0 |
| sleep | S3 (deep)、GRUB `mem_sleep_default=deep` (7/29 恒久化) |
| フック | 45-wl-unload / 46-lid0-ac-policy / 47-facetimehd |
| デスクトップ | GNOME (Wayland)、pipewire 1.4.2、firefox-esr 140.12 |

## 原因分析

### 因果連鎖 (実機ログ + ソースで確定)

1. **カメラ使用中は保護フックが無力化**: `/var/log/facetimehd-sleep.log` に `modprobe -r facetimehd FAILED rc=1` が 3 件 (7/29 19:59 / 20:00 / 20:27)。カメラ使用中 (`/dev/video0` open) はモジュール参照が残るため unload できず、**ドライバを載せたまま S3 に入った** (導入時に注記した未検証構成)
2. **ドライバの suspend 実装が「remove/probe」**: `fthd_pci_suspend = fthd_pci_remove` (デバイス完全削除)、`fthd_pci_resume = fthd_pci_probe` (再プローブ) — fthd_drv.c:526-535。resume ログで全初期化 (firmware 再ロード・Full memory verification・~515ms) を毎回実行していることを確認。**suspend のたびに `/dev/video0` が unregister され、resume で新番号 (`/dev/video1` → 2 → 3) で再作成される**
3. **アプリは消えたノードに取り残される**: pipewire は `'/dev/video0' VIDIOC_STREAMOFF: そのようなデバイスはありません`、gnome-snapshot は GStreamer Bus Error → **報告症状 (フリーズ・真っ黒) の直接原因**。v4l2 コアは unregister 済みデバイスへの ioctl/read を ENODEV で弾くが、映像待ちでブロック中のスレッドは起こされず宙吊りになる (フリーズの機序)
4. **stale fd の close でカーネル Oops**: `fthd_pci_remove` は open 中の fd への配慮なしに `isp_uninit` (ISP メモリプールの resource 木を破棄)・`iounmap`・`fthd_buffer_exit` (iommu root を kfree) まで実行する (fthd_drv.c:321-360)。その後アプリが古い fd を close すると v4l2 release 経路だけは素通しでドライバに届き、`__vb2_queue_cancel → fthd_stop_streaming → fthd_isp_cmd → isp_mem_create` が破棄済みの resource 木に触れて **NULL deref**:
   - **Oops #1**: 7/29 20:31:32、Comm=`VideoCapture` (Firefox のカメラスレッドの close)
   - **Oops #2**: 7/29 22:26:40、Comm=`pipewire` (再起動時の exit_group → fput)。pipewire が SIGKILL でも死ねなくなり、stop job タイムアウトの連鎖で**シャットダウンが約 5 分停滞**
5. さらに release 経路では `fthd_buffer_cleanup` も (a) iounmap 済み `s2_io` へのレジスタ書き込み、(b) kfree 済み root への `release_resource` を行う設計で、Oops #1 で倒れなくてもここで倒れる二段構えだった
6. 上流 (patjak/facetimehd wiki) も「suspend/resume with the device opened is still not supported」と公言する既知の未サポート領域

### 補足観測

- Oops 後は該当 fd が close 不能になり module 参照カウントが下がらず (`lsmod` で 3 残留)、unload 不能 → 再起動でしか回復できない状態だった
- pipewire が削除済み `/dev/video0`・`/dev/video1` の fd を保持し続けていることを `/proc/1551/fd` で実測 (再起動前)

## 対策: ドライバ安全化 patch

`/usr/src/facetimehd-0.7.0.1/` に [0001-survive-remove-with-open-fds.patch](attachment/2026-07-29_224045_camera_dead_after_suspend_while_in_use_fixed/0001-survive-remove-with-open-fds.patch) を適用し DKMS 再ビルド。patch はリポジトリ `patches/facetimehd/` で管理。方針は最小限の hot-unplug 安全化 (本格 PM 化はしない):

1. `struct fthd_private` に `bool removed` を追加 (fthd_drv.h)
2. `fthd_pci_remove()` 冒頭で `removed = true` を立て、`vb2_queue_error()` で映像待ちブロック中のリーダーを起こしてエラーを返す (フリーズ防止)
3. `fthd_stop_streaming()`: `removed` なら HW コマンドを一切呼ばず、キュー済みバッファを `VB2_BUF_STATE_ERROR` で返却して終了 (Oops #1 経路の遮断)
4. `fthd_buffer_cleanup()`: `removed` なら iounmap 済みレジスタ書き込みと破棄済み resource 木への `release_resource` をスキップ (二段目の遮断。小オブジェクトはリークさせる — `dev_priv` 自体が remove で解放されない既存設計と同水準の有界リーク)
5. `v4l2_ctrl_handler_free` を unregister 時から `video_device` の release コールバック (最終 close 後) に移動 (ctrl イベント購読解除経路の UAF 予防)

成立根拠: `fthd_pci_remove` は `dev_priv` を kfree しない (kfree は probe 失敗経路のみ) ため、stale fd の release 時もフラグは有効に読める。ioctl/read/poll/mmap/新規 open は v4l2 コアの `video_is_registered` チェックで既に遮断されており、ドライバ側で塞ぐべきは release 経路のみ。

あわせて 47-facetimehd フックのコメントと FAILED ログ文言を「patch 済み: resume 後 /dev/videoN 再作成・アプリ再オープンで復旧」に更新した (動作は不変)。

## 検証結果 (全 green)

再起動でクリーン状態にした後、リモート S3 e2e 標準手順 (LID0 凍結 + RTC wakealarm 90s) で実施:

| # | シナリオ | 結果 |
|---|---|---|
| 1 | 正常系回帰: カメラ未使用 suspend | 47 フック unload/reload 発火、Oops 0、resume 後 `/dev/video0` で 5 フレーム取得 OK |
| 2 | 再現系: `v4l2-ctl --stream-mmap` でカメラを掴んだまま suspend | FAILED ログ (期待どおり)、**resume 後 Oops 0** |
| 3 | stale fd の close (従来 Oops した操作) | ストリーマは resume 後 `VIDIOC_DQBUF: No such device` を受けて自力終了 = 旧 fd close 済み、**Oops 0**、refcount 0 まで低下 |
| 4 | 再作成ノード | `/dev/video1` 生成、5 フレーム取得 OK |
| 5 | モジュール入れ直し | `modprobe -r && modprobe` で `/dev/video0` に復帰、5 フレーム取得 OK |
| 6 | ビルド | kernel 6.12.95 で警告なし、MOK 署名済み |

GUI 実使用系 (GNOME Camera / Firefox でカメラ表示中に lid close) はユーザの通常利用の中で確認する (期待動作: 復帰後アプリのカメラを開き直せば復活。フリーズ・真っ黒・Oops は発生しない)。

## 再現方法

```bash
# --- 症状の再現 (patch 前) ---
# カメラを開いたまま suspend するだけ。復帰後 /dev/video0 が消え新番号になり、
# 掴んでいたアプリの fd close で isp_mem_create の NULL deref Oops
# (詳細ログ: 添付 oops_logs.txt)

# --- patch 適用 ---
ssh miminashi@macbookair2015.lan
sudo tar -C /usr/src -czf /root/facetimehd-0.7.0.1-pristine-20260729.tar.gz facetimehd-0.7.0.1
cd /usr/src/facetimehd-0.7.0.1
sudo patch -p1 < 0001-survive-remove-with-open-fds.patch
sudo /usr/sbin/dkms build -m facetimehd -v 0.7.0.1 --force
sudo /usr/sbin/dkms install -m facetimehd -v 0.7.0.1 --force
sudo systemctl reboot   # 旧モジュールが稼働中のため

# --- 再現系の検証 ---
setsid nohup v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=100000 \
  > /tmp/streamer.log 2>&1 < /dev/null &
echo LID0 | sudo tee /proc/acpi/wakeup    # 蓋開き spurious 回避 (状態確認の上)
echo $(( $(cat /sys/class/rtc/rtc0/since_epoch) + 90 )) | sudo tee /sys/class/rtc/rtc0/wakealarm
sudo systemctl suspend
# 復帰後:
tail /var/log/facetimehd-sleep.log        # FAILED 行 (期待どおり)
sudo dmesg | grep -cE "BUG:|Oops"         # → 0 が成功判定
pgrep v4l2-ctl || cat /tmp/streamer.log   # DQBUF: No such device で自力終了 = fd close 済み
ls /dev/video*                            # 新番号で再作成
# 後片付け: LID0 再有効化 + wakealarm クリア (echo 0)
```

## ロールバック

```bash
sudo tar -C /usr/src -xzf /root/facetimehd-0.7.0.1-pristine-20260729.tar.gz
sudo /usr/sbin/dkms build -m facetimehd -v 0.7.0.1 --force
sudo /usr/sbin/dkms install -m facetimehd -v 0.7.0.1 --force
sudo systemctl reboot
```

## 参照した過去レポート

- [内蔵カメラをブラウザから使えるようにした](2026-07-29_191159_facetimehd_camera_enable.md) — facetimehd 導入と 47-facetimehd フック新設、「既知の穴」の注記元
- [S3 再挑戦 — Phase 5 恒久化](2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload.md) — リモート S3 e2e 標準手順 (LID0 凍結 + RTC alarm) の出典

## 今後・残リスク

1. **運用**: カメラ使用中に suspend した場合、復帰後はアプリでカメラを開き直す (デバイス番号は変わるが pipewire/アプリは新ノードを列挙し直せる)。クラッシュ・フリーズはしない
2. **soak ウォッチ更新**: `facetimehd-sleep.log` の FAILED 行は「未検証構成の警報」から「patch 済み経路の通過記録」に意味が変わった。引き続き Oops/hang の再発だけを警報として扱う
3. patch は out-of-tree ローカル修正。カーネル更新時は DKMS が patch 済みソースから自動再ビルドするため追従不要だが、**facetimehd を上流から更新する際は patch の再適用が必要** (`patches/facetimehd/` に管理)。上流へ還元する価値はあるが、上流は本格 PM 実装を志向する可能性があり本 patch は最小主義のため、そのまま PR にはしていない
4. 小さな残穴: suspend をまたいだ古い `dev_priv` とバッファオブジェクトはリークする (1 cycle あたり数 KB オーダー、既存設計と同水準)。実害が出る規模ではない
5. カメラ使用中 suspend では 02:00.0 / 00:1c.1 の sleep 中 PM 状態が「ドライバあり」になる (中立化が効かない)。hang 統計上は従来どおり FAILED 行で識別可能
