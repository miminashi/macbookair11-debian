# カメラ使用中 suspend でカメラが死ぬ問題 — 原因確定と恒久対策 (ドライバ安全化 patch)

## Context

7/29 に導入した facetimehd カメラ (report 2026-07-29_191159) について、「カメラ on のまま suspend すると復帰後にカメラが復帰しない (GNOME Camera フリーズ / ブラウザ真っ黒)」との報告。調査の結果、導入時に「既知の穴」として明記していた**カメラ使用中 suspend = 未検証構成**がまさに踏まれ、単なる機能不全ではなく **kernel Oops (NULL deref)** まで発生していることを確認した。

## 原因 (調査で確定済み — 実機ログ + ソース裏取り済み)

因果連鎖:

1. カメラ使用中は `/usr/lib/systemd/system-sleep/47-facetimehd` の `modprobe -r` が失敗
   (`/var/log/facetimehd-sleep.log` に FAILED 3 件: 7/29 19:59 / 20:00 / 20:27) →
   **ドライバを載せたまま S3 へ** (設計時に明記した未検証構成)
2. facetimehd の PM 実装が乱暴: `fthd_pci_suspend = fthd_pci_remove` (デバイス完全削除)、
   `fthd_pci_resume = fthd_pci_probe` (再プローブ) — `/usr/src/facetimehd-0.7.0.1/fthd_drv.c:526-535`
   → **suspend のたびに /dev/video0 を破棄、resume で新番号 (/dev/video1→2→3) で再作成**
3. アプリ (pipewire / Firefox) は消えた旧ノードの fd を握ったまま
   → pipewire `VIDIOC_STREAMOFF: そのようなデバイスはありません`、GNOME Camera フリーズ、ブラウザ真っ黒
4. **use-after-teardown で kernel Oops**: `fthd_pci_remove` は open 中 fd への配慮なしに
   `isp_uninit` (ISPメモリプール破棄) + `iounmap` まで実行 (fthd_drv.c:321-360)。
   その後アプリが stale fd を close すると `v4l2_release → vb2_fop_release →
   __vb2_queue_cancel → fthd_stop_streaming → fthd_isp_cmd → isp_mem_create` が
   破棄済み状態に触れて **NULL deref** (実測: 7/29 20:31:32、Comm=VideoCapture (Firefox)、
   `RIP: isp_mem_create+0x75`)
5. 上流の公式見解: 「suspend/resume with the device opened is still not supported」
   (patjak/facetimehd wiki) — 既知の未サポート領域

**現在の実機の残留状態**:
- カーネル tainted (W + Oops 1 回)
- pipewire (PID 1551) が削除済み `/dev/video0`・`/dev/video1` の fd を保持
  → close する瞬間 (pipewire 再起動/ログアウト/シャットダウン) に再 Oops を踏む地雷
- 現行 `/dev/video3` 自体は動作する (3 フレーム取得を実測)

**ユーザ決定**: 恒久対策 = ドライバ安全化 patch / 再起動 = 作業の最後にまとめて実施

## 実装ステップ

### Step 1: 安全化 patch の作成

対象: 実機の `/usr/src/facetimehd-0.7.0.1/` (DKMS ソース)。patch ファイルは開発機リポジトリ
`patches/facetimehd/0001-survive-remove-with-open-fds.patch` としてコミットして管理
(適用は実機側。src/ ではなく patches/ なので .gitignore 対象外)。

内容 (最小限の hot-unplug 安全化。本格 PM 化はしない):

1. `fthd_common.h` の `struct fthd_private` に `bool removed;` を追加
2. `fthd_drv.c` の `fthd_pci_remove()` 冒頭 (drvdata NULL チェック直後) で
   `dev_priv->removed = true;` を設定
3. `fthd_v4l2.c` の `fthd_stop_streaming()` に早期脱出を追加:
   `removed` なら HW コマンド (`fthd_stop_channel` 等) を一切呼ばず、
   キュー済み vb2 バッファを `VB2_BUF_STATE_ERROR` で返却して return
   (vb2 はバッファ全返却を要求するため、既存の buffer 返却部だけ流用)
4. ctrl handler の解放タイミング修正 (`fthd_v4l2.c:781-790`):
   `fthd_v4l2_unregister()` で `v4l2_ctrl_handler_free` を open 中 fd が残った状態で
   呼ぶと release 時の event unsubscribe 経路で UAF になりうるため、
   `vdev->release` カスタムコールバック (`fthd_vdev_release`: `v4l2_ctrl_handler_free`
   → `video_device_release`) に移し、最後の close 後に解放されるようにする
   (`fthd_v4l2.c:751` の `vdev->release = video_device_release` を差し替え)

備考: `fthd_pci_remove` は現状 `dev_priv` を kfree しない (kfree は probe 失敗経路
fthd_drv.c:521 のみ) ため、stale fd の release 時も `dev_priv` 本体は生存しており
フラグ方式が成立する。cycle ごとの小さなメモリリークは既存挙動のまま許容
(ioctl/poll/mmap/新規 open は v4l2 コアの `video_is_registered` チェックで既に ENODEV
になるため、driver 側で塞ぐべきは release 経路のみ)。

### Step 2: DKMS 再ビルド・適用 (実機)

```bash
# patch 適用 (scp で転送 or ヒアドキュメント)
cd /usr/src/facetimehd-0.7.0.1 && sudo patch -p1 < 0001-....patch
sudo /usr/sbin/dkms build -m facetimehd -v 0.7.0.1 --force
sudo /usr/sbin/dkms install -m facetimehd -v 0.7.0.1 --force
```

- 適用前に `/usr/src/facetimehd-0.7.0.1` を `tar` でバックアップ (ロールバック用、
  実機 `/root/` か `~/` 配下)
- 47-facetimehd フックは変更しない (unload 成功時の中立化は引き続き第一防衛線。
  FAILED 時の挙動が「Oops」から「安全に生き残る」に変わるだけ)
- フックの FAILED ログ文言の「未検証構成」を「patch 済み・open中suspendは
  ノード再作成」等に更新する程度の文言修正は任意

### Step 3: 再起動 + 検証 (実機)

再起動 (Step 1-2 完了後。地雷 fd と tainted 状態のクリアを兼ねる。
シャットダウン中に旧カーネルモジュールで最後の Oops が出る可能性はあるが実害なし):

検証シナリオ (リモート S3 e2e 標準手順 = LID0 凍結 + RTC wakealarm を使用):

1. **正常系回帰**: カメラ未使用で suspend → 47 フック unload/reload、resume 後
   `/dev/video0` でフレーム取得 OK (従来動作の非退行)
2. **本題の再現系**: `v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=100000` を
   background で流してカメラ busy 状態を作る → suspend →
   - FAILED がログに残る (期待どおり)
   - resume 後 dmesg に **Oops/BUG が出ないこと** (最重要判定)
   - 新ノード `/dev/video1` が生成され、フレーム取得できること
   - background の v4l2-ctl を止めて stale fd を close → **Oops が出ないこと** (第 2 判定)
   - lsmod の refcount が 0 に戻り `modprobe -r facetimehd && modprobe facetimehd` で
     `/dev/video0` に戻せること
3. (可能なら) GUI 実使用系: GNOME Camera / Firefox でカメラ表示中に suspend →
   resume 後アプリを開き直してカメラ復活することをユーザ目視確認 (依頼ベース、任意)

### Step 4: レポート作成 (開発機リポジトリ)

- `report/` に新規レポート (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)。
  ファイル名案: `camera_dead_after_suspend_while_in_use_fixed.md` 系の英語名
- 内容: 概要 (平易な日本語・段落形式) / 前提・目的 / 環境情報 / 原因分析 (上記の因果連鎖、
  ログ・Oops スタック・ソース行の証拠) / patch 内容 / 検証結果 / 再現方法 / ロールバック /
  参照レポート (2026-07-29_191159) / 残リスク
- 添付: `report/attachment/<レポート名>/` にプランファイル (本ファイル) を cp、
  patch ファイル、Oops ログ抜粋
- レポート後の書き漏らし再確認 + 矛盾点検 (プロジェクトルール)
- メモリ更新: S3 系メモリの facetimehd ウォッチ項目に「FAILED は patch 済みで
  Oops しない・ノード番号が変わる」旨を反映

## ロールバック

```bash
# patch 撤回
sudo tar -C / -xf <バックアップ>.tar   # /usr/src/facetimehd-0.7.0.1 復元
sudo /usr/sbin/dkms build -m facetimehd -v 0.7.0.1 --force && sudo /usr/sbin/dkms install -m facetimehd -v 0.7.0.1 --force
sudo systemctl reboot
```

## 検証 (成功判定)

- 再現系 (カメラ busy suspend → resume → stale fd close) を通しで実行して
  dmesg に BUG/Oops が 1 件も出ない
- 正常系 (カメラ未使用 suspend) の 47 フック動作・PM 中立性が非退行
- 再起動後にカーネル untainted で上記が再現する
