# MacBook Air 11" のカメラをブラウザから使えるようにする (facetimehd 導入) + S3 の GRUB 恒久化

## Context

ユーザから「ブラウザからカメラが使えなかった」と報告があった。実機 (`macbookair2015.lan`, MacBookAir7,1, Debian 13) を調査した結果、**ブラウザ側の問題ではなく OS にカメラドライバが存在しない**ことが確定した。

確認済みの事実:

| 項目 | 実測値 |
|---|---|
| カメラデバイス | `02:00.0 Multimedia controller [0480]: Broadcom 720p FaceTime HD Camera [14e4:1570]` (ACPI: `\_SB_.PCI0.RP02.CMRA`) |
| バインドされたドライバ | **なし** (`lspci -nnk` に `Kernel driver in use` 行が出ない) |
| `/dev/video*` | **存在しない** |
| `facetimehd` モジュール / `/lib/firmware/facetimehd/` | いずれも**不在** |
| Debian trixie のパッケージ | `facetimehd-dkms` / `facetimehd-firmware` とも **リポジトリに存在しない** (`apt-cache policy` が空、`apt-cache search facetime` も 0 件。sources.list には contrib/non-free 含む) |
| カーネル | `6.12.95+deb13-amd64` (ヘッダ導入済み。`6.12.94-dpmwd4` のヘッダも残存) |
| ブラウザ | `firefox-esr 140.12.0esr` (deb 版。snap/flatpak ではないのでサンドボックス起因ではない) |
| ビルド環境 | build-essential / dkms / git / curl / xz-utils / cpio すべて導入済み。Secure Boot 無効 (EFI 変数なし) |

Broadcom 1570 は **mainline に in-tree ドライバが無い** PCIe 接続の ISP で、動かすには上流のリバースエンジニアリング実装 `patjak/facetimehd` (DKMS) と、Apple 配布バイナリから抽出した firmware が要る。ユーザ症状「デバイスが一覧に出ない」「許可を求められない」は、デバイスがゼロなので Firefox が `getUserMedia` を `NotFoundError` で即失敗させ許可ダイアログに至らない挙動と完全に整合する (テストページは https だったことを確認済み = secure context 側の別原因はない)。

着手順序はユーザ判断により **Phase A (S3 の GRUB deep 化) を先に確定させ、その後 Phase B (カメラ導入)** とする。カメラ `02:00.0` の親ルートポート `00:1c.1` は suspend hang 調査で「単独犯ではない」までしか確定しておらず共犯可能性が未排除のため、S3 恒久化の判断に新規要素を混ぜない。

参照レポート (`report/` 起点): [`2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload.md`](2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload.md) — Phase 5 恒久化。soak 通過後の GRUB deep 化が積み残し課題として明記されている / [`2026-07-13_005126_suspend_hang_investigation_summary.md`](2026-07-13_005126_suspend_hang_investigation_summary.md) — 調査総括

---

## Phase A: S3 の GRUB 恒久化 (soak 通過を受けた積み残しの消化)

> **Phase A は runtime 中立**: 現在すでに `s3-deep-select.service` により runtime が `s2idle [deep]` になっており、Phase A が変えるのは boot 既定値だけで sleep の挙動は変わらない。したがって A-2 の再起動検収が通れば**同セッションで Phase B に進む**。改めて soak 期間は置かない。

### A-0. soak 通過の最終確認 (read-only)

7/29 時点で以下を確認済み。実行直前に再確認する。

- boot は 7/13 17:41 以降 **1 本のみ** (16 日) = hang による強制電源断ゼロ
- `s3-soak.log`: `ss_ok=70 ss_fail=0`、`asleep_s` に battery spurious wake (~6s) なし
- `wl-unload.log`: FAILED **0 件**
- `lid0-ac-policy.log`: AC 運用のため全て no-op で正常

### A-1. GRUB 変更

```bash
sudo cp -a /etc/default/grub /etc/default/grub.bak-grub-deep-$(TZ=Asia/Tokyo date +%Y%m%d)
# mem_sleep_default=s2idle → deep
sudo sed -i 's/mem_sleep_default=s2idle/mem_sleep_default=deep/' /etc/default/grub
grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub
sudo update-grub && sudo sync    # sync 必須 (既知の罠: GRUB がジャーナル未反映ブロックを読む)
```

### A-2. 再起動と検収

- 再起動後 `cat /proc/cmdline` に `mem_sleep_default=deep`、`cat /sys/power/mem_sleep` が `s2idle [deep]`
- `systemctl status s3-deep-select.service` が success (deep が既定になったので実質 no-op、フェイルセーフとして enabled のまま残す)
- lid close → lid open (AC) で 1 回 suspend/resume を通し、`s3-soak.log` に `ss_fail=0` のまま WAKE が記録されること

### A-3. フェイルセーフ手順の更新 (必須)

Phase 5 で文書化されたロールバック手順「`systemctl disable s3-deep-select` + 再起動 → s2idle」は、GRUB が `deep` を既定にした時点で**成立しなくなる** (unit を止めても deep のまま)。

- 新しいロールバック = `/etc/default/grub` を `.bak-grub-deep-*` から復元 → `sudo update-grub && sudo sync` → 再起動
- `s3-deep-select.service` の `Description` / `/usr/local/sbin/s3-deep-select.sh` のコメントを更新し、古い手順が実機上に残って現実と矛盾しないようにする
- この差し替えをレポートにも明記する

### A-4. クリーンアップ (任意・同時実施)

- 旧 `s3-deep-apply.service` (disabled 残置、LID0 無条件凍結の旧仕様で enable 禁止) を unit ごと削除

---

## Phase B: カメラ (facetimehd) 導入

作業ディレクトリは実機の `~/src/` とする (ビルドは実機上で行う。開発機リポジトリの `src/` はソース読解が必要になった場合のみ使う)。

### B-0. 導入前ベースライン採取 (read-only、B-4-7 の比較対照)

ドライバを入れる前に、sleep 1 回分の `02:00.0` / `00:1c.1` の PM 状態を採取して保存する:

- runtime 値 (採取済み): `02:00.0` = D0、`d3cold_allowed=1`
- sleep 中の状態: 既存 `58-snapshot-only` フックの直近スナップショットから `02:00.0` / `00:1c.1` の行を抜き出して控える (無ければ Phase A の検収 suspend で 1 回分取る)
- `lspci -nnk`、`dmesg | grep 02:00.0` の現状も控える

### B-1. ファームウェア抽出

```bash
mkdir -p ~/src && cd ~/src
git clone https://github.com/patjak/facetimehd-firmware.git
cd facetimehd-firmware
make        # updates.cdn-apple.com から OSXUpd10.11.5.dmg の byte-range 204909802-207733123 (約 2.7MB) だけ取得
            # → xzcat|cpio で AppleCameraInterface を抽出 → extract-firmware.sh -x で firmware.bin 生成
```

**ゲート (重要)**: Makefile のダウンロード行は `&> /dev/null || true` で失敗を握り潰すため、CDN が死んでいても「`mv: cannot stat 'AppleCameraInterface'`」という紛らわしいエラーになるだけ。install の前に必ず明示確認する。

```bash
ls -l firmware.bin        # 期待値 603,715 バイト
sha256sum firmware.bin    # extract-firmware.sh 内蔵の既知ハッシュと照合 (スクリプト自身が検証するが結果を目視)
sudo make install         # → /usr/lib/firmware/facetimehd/firmware.bin
```

ダウンロードが失敗した場合の代替: `extract-firmware.sh` は Boot Camp 5.1.5722 ドライバ (`support.apple.com/downloads/DL1831/`) からの抽出経路も持つので、そちらを手動取得して `-x` に渡す。

### B-2. ドライバ (DKMS)

```bash
cd ~/src && git clone https://github.com/patjak/facetimehd.git
cat facetimehd/dkms.conf          # PACKAGE_NAME / PACKAGE_VERSION を実読 (パスを推測しない)
sudo cp -a facetimehd /usr/src/facetimehd-<ver>
sudo dkms add    -m facetimehd -v <ver>
sudo dkms build  -m facetimehd -v <ver>
sudo dkms install -m facetimehd -v <ver>
sudo dkms status                   # 6.12.95+deb13-amd64 で installed。6.12.94-dpmwd4 も autoinstall 対象
sudo modprobe facetimehd
```

- 上流は 2026-06 まで活発にメンテされ、6.13 / 7.0 向け追従コミットがあるので 6.12 は射程内。`dkms` は `/usr/sbin/dkms` なので `sudo` 経由で叩く
- `dpmwd4` 側のビルドが失敗しても本番カーネルには影響しない (ログに残して続行)
- `dmesg` を確認し、firmware ロード成功と、既知の失敗パターン **`Full memory verification failed!`** (MBA7,2 の [issue #229](https://github.com/patjak/facetimehd/issues/229)) が出ていないことを見る
- 自動ロードは PCI modalias 経由の udev autoload を再起動で実測確認する。効かない場合のみ `/etc/modules-load.d/facetimehd.conf` を置く

### B-3. suspend 中立化フック (新設)

`/usr/lib/systemd/system-sleep/47-facetimehd` を、既存の `45-wl-unload` と同じ作り (pre で unload / post で reload、`/run/facetimehd-unloaded` フラグ、`/var/log/facetimehd-sleep.log`、timeout 付き、`exit 0`) で新設する。

意図は 2 つ:

1. **soak 中立性** — sleep 中の `02:00.0` / `00:1c.1` の PM 状態を導入前と同一に保ち、hang 調査の統計に新変数を持ち込まない
2. facetimehd は resume 後の復帰が不安定という上流既知の性質があり、unload/reload が定番の回避策

**既知の穴 (要ウォッチ)**: カメラ使用中は `/dev/video0` が busy で `modprobe -r` が失敗し、`45-wl-unload` と同じくログに FAILED を残して suspend を続行する = ドライバを載せたまま S3 に入る未検証構成になる。この行を soak ウォッチリストに追加する。

### B-4. 検証 (この順に、段階を飛ばさない)

1. `sudo apt-get install v4l-utils` → `v4l2-ctl --list-devices` / `v4l2-ctl --all`
2. **権限確認**: `getfacl /dev/video0` / `id -nG miminashi`。調査済みの前提は良好 (`/usr/lib/udev/rules.d/70-uaccess.rules:34` が `SUBSYSTEM=="video4linux", TAG+="uaccess"` を USB 限定なしで付与、ユーザは `video` グループ所属済み) だが、PCI カメラで実際に ACL が付くかは実測する。付かない場合はデバイスのモード/グループを見て udev rule で補う
3. **実ストリーム**: `sudo v4l2-ctl --stream-mmap --stream-count=30` でフレームが取れること (デバイスノードの存在だけでは合格にしない — ISP 初期化失敗は「ノードはあるが映らない」形で出る)。**ssh セッションは seat セッションではないため uaccess の ACL が効かない**ので、ここは `sudo` で実行し、非 root での可否は次の段階 (グラフィカルセッション) で判定する
4. `gnome-snapshot` で実映像を目視 (グラフィカルセッションでの非 root 動作確認を兼ねる)
5. **ブラウザ**: Firefox で https://webrtc.github.io/samples/src/content/devices/input-output/ を開き、デバイス列挙・許可ダイアログ・映像表示の 3 点を確認 (ユーザ報告の症状そのものが解消したことの確認)
6. **suspend/resume 後**: 蓋閉じ → AC で lid open 復帰後に 3〜5 が再度通ること。`facetimehd-sleep.log` と `wl-unload.log` が対で正常なこと、`s3-soak.log` の `ss_fail` が 0 のまま
7. **B-3 の中立性を実測**: 導入後の sleep 1 回で `0000:02:00.0` と `0000:00:1c.1` の `power_state` / `d3cold_allowed` を採取し、導入前の値 (現状 `02:00.0` = D0 / `d3cold_allowed=1`) と一致することを確認する。上流の最新コミットが ACPI (`\_SB_.PCI0.RP02.CMRA`) 経由でセンサ電源を入れるようになっているため、unload が対称でなければ中立にならない
8. **再起動後**: 自動ロードされ `/dev/video0` が出ること

### ロールバック

```bash
sudo dkms remove facetimehd/<ver> --all && sudo rm -rf /usr/src/facetimehd-<ver>
sudo rm -rf /usr/lib/firmware/facetimehd
sudo rm -f /usr/lib/systemd/system-sleep/47-facetimehd
sudo depmod -a && sudo update-initramfs -u
```

---

## レポート作成

`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で採番し `report/<ts>_facetimehd_camera_enable.md` を作成する。平易な段落の「概要」、前提・目的、環境情報、再現方法 (上記コマンド)、検証結果 (各段階の実測)、Phase A の恒久化記録、残リスクを含める。`report/attachment/<ts>_facetimehd_camera_enable/plan.md` に本プランをコピーしてリンクする。

## 残リスク (プラン時点で未確定)

- Apple CDN の URL 生存 (2019 年の配布 URL。死んでいれば Boot Camp 経路へ切替)
- `6.12.95+deb13-amd64` での DKMS ビルド可否 (上流の追従状況からは通る見込み)
- ISP 初期化失敗 (`Full memory verification failed`) の可能性。出た場合は上流 issue の追試まで行い、深追いはユーザ判断を仰ぐ
- 稼働中の消費電力がわずかに増える可能性 (sleep 中は unload するので待機電力への影響はない見込み)
