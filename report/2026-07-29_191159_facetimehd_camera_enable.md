# 内蔵カメラをブラウザから使えるようにした — ドライバ導入と S3 設定の仕上げ

- **実施日時**: 2026年7月29日 18:20〜19:12 (JST)
- **執筆者**: Claude Opus 5 (Claude Code)

## 概要

「ブラウザからカメラが使えない」という報告を受けて調査したところ、原因はブラウザ側の設定や権限ではなく、そもそも OS にカメラのドライバが入っていないことだった。この機種の内蔵カメラは一般的な USB カメラと違って PCIe 接続の特殊なデバイスで、Linux 標準のドライバでは動かず、Debian の公式パッケージにも対応ドライバが存在しない。有志がリバースエンジニアリングで開発したドライバと、Apple の配布物から抽出したファームウェアを自分で組み込む必要がある。ブラウザで「カメラが一覧に出ない・許可も聞かれない」という症状は、OS から見えるカメラがゼロ台だったことでそのまま説明がつく。

導入の前に、先送りになっていた宿題をひとつ片付けた。7月13日から続けていた S3 スリープの試験運用 (soak) である。16 日間・スリープ 70 回で、ハングも失敗も一度もなかったことを確認し、起動設定 (GRUB) レベルで S3 を正式採用した。カメラのドライバはスリープ調査で「シロと確定していない」ポートにぶら下がっているため、新しい要素を持ち込む前に S3 の判断を確定させておく、という順序である。

この確定作業の検収中に、思わぬ発見があった。リモートから (= 蓋を開けたまま) スリープさせると、電源接続でも約 6 秒で勝手に目が覚めてしまうのである。切り分けの結果、これは今回の変更による退行ではなく「蓋を開けたまま S3 に入ると、蓋センサーの信号がすぐに火を吹く」というこの機体の持病と判明した。過去に「バッテリー時特有」とされていた 6 秒復帰現象は、実はバッテリーではなく「蓋が開いていること」が原因だった可能性が高い。普段の使い方 (蓋を閉じてスリープ) には影響しない。

カメラ本体の導入は素直に進んだ。ファームウェアの抽出、ドライバのビルドとインストール、カーネル更新に自動追従する仕組み (DKMS) への登録まで一通り成功し、カメラは 720p/30fps で映像を出せるようになった。スリープとの相性問題を避けるため、眠る直前にドライバを外して目覚めたら戻すフックも仕掛けた。これでスリープ中の状態は導入前と全く同じに保たれ、長期間続けているスリープ調査の統計を汚さない。

最後に実機で目視確認を行い、カメラアプリ (gnome-snapshot) と Firefox のブラウザ上 (WebRTC テストページ) の両方で映像が表示されることを確認した。当初の報告症状は解消である。スリープをまたいでも再起動をまたいでもカメラは自動で復活する。

## 添付ファイル

- [実装プラン](attachment/2026-07-29_191159_facetimehd_camera_enable/plan.md)
- [導入前ベースライン (PM 状態・lspci・dmesg)](attachment/2026-07-29_191159_facetimehd_camera_enable/b0_pre_install_baseline.txt)

## 前提・目的

- 背景: ユーザから「ブラウザからカメラが使えなかった」との報告 (https サイト、デバイス一覧に出ない・許可も聞かれない、導入以来一度も使えたことがない)
- 目的:
  1. 原因を特定してブラウザからカメラを使えるようにする
  2. (先行タスク) S3 soak 通過を受けた GRUB `mem_sleep_default=deep` 恒久化 — カメラ導入で suspend 系に新変数が入る前に確定させる (ユーザ判断による順序)
- 前提条件: S3 soak が通過していること (7/13 開始、判定基準 = hang 再発なし・wl-unload FAILED なし・battery spurious なし)

## 環境情報

| 項目 | 値 |
|---|---|
| 機体 | MacBook Air 11" Early 2015 (MacBookAir7,1, board Mac-9F18E312C5C2BF0B) |
| OS | Debian 13 (trixie)、kernel 6.12.95+deb13-amd64 |
| カメラ | `02:00.0` Broadcom 720p FaceTime HD Camera `[14e4:1570]`、親ポート `00:1c.1`、ACPI `\_SB_.PCI0.RP02.CMRA` |
| ブラウザ | firefox-esr 140.12.0esr (deb 版) |
| デスクトップ | GNOME (Wayland)、pipewire 1.4.2 |
| Secure Boot | 無効 (module 署名は DKMS の MOK で実施されるが強制なし) |
| ディスク | / 92G 中 17G 使用 |
| 導入ドライバ | facetimehd 0.7.0.1 (patjak/facetimehd master, DKMS) + firmware 1.43.0 (El Capitan 10.11.5 由来) |

## 原因の診断 (カメラが使えなかった理由)

| 確認項目 | 結果 |
|---|---|
| `lspci -nnk` `02:00.0` | `Kernel driver in use` 行なし = ドライバ未バインド |
| `/dev/video*` | 存在しない |
| `facetimehd` モジュール / `/lib/firmware/facetimehd/` | 不在 |
| Debian リポジトリ (contrib/non-free 込み) | `facetimehd-dkms` / `facetimehd-firmware` とも存在しない (`apt-cache search facetime` 0 件) |

Broadcom 1570 は mainline カーネルに in-tree ドライバが無い PCIe 接続 ISP。デバイスがゼロのため Firefox は `getUserMedia` を許可ダイアログ以前に `NotFoundError` で失敗させる — 報告症状と完全に一致。テストページは https だったため secure context 側の別原因はない。

## Phase A: S3 の GRUB 恒久化

### soak 通過判定 (7/13 17:41 boot 〜 7/29)

- boot 1 本のみ 16 日間 = hang による強制電源断ゼロ
- `s3-soak.log`: `ss_ok=70 ss_fail=0`
- `wl-unload.log`: FAILED 0 件
- 短時間 wake (asleep_s<60) は 16 日で 5 件 (7〜39s)、連発パターンなし。うち 1 件 (7/18 00:59 AC asleep_s=7) は後述の「蓋開き spurious」と同署名
- → **通過** と判定

### 実施内容

1. バックアップ: `/etc/default/grub.bak-grub-deep-20260729`
2. `GRUB_CMDLINE_LINUX_DEFAULT` の `mem_sleep_default=s2idle` → `deep`、`update-grub && sync`
3. 再起動検収: `/proc/cmdline` に `mem_sleep_default=deep`、`/sys/power/mem_sleep` = `s2idle [deep]`、`s3-deep-select.service` success (実質 no-op 化、フェイルセーフとして enabled 残置)
4. **フェイルセーフ手順の差し替え**: 旧手順「service disable + 再起動で s2idle」は GRUB deep 化で不成立になるため、`/usr/local/sbin/s3-deep-select.sh` のコメントと unit の Description を更新。新ロールバック = **`/etc/default/grub` を `.bak-grub-deep-*` から復元 → `update-grub && sync` → 再起動**
5. クリーンアップ: 旧 `s3-deep-apply.service` (enable 禁止の LID0 無条件凍結仕様、disabled 残置だったもの) を unit・スクリプトごと削除

### 副発見: 「蓋開き S3 の ~6s spurious wake」— battery 特有説の訂正候補

再起動検収の e2e (リモート suspend = **蓋開きのまま**) で、AC にもかかわらず ~6s で gpe70 により復帰する現象が再現的に発生した。切り分け 6 サイクル:

| cycle | 条件 | 結果 |
|---|---|---|
| 1 | AC + 蓋開 + LID0 有効 + RTC alarm 60s | **6s wake** (gpe70+1、alarm 未発火のまま armed) |
| 2 | 同上 alarm 90s | **6s wake** (同上) |
| 3 | 同上 alarm なし | **5s wake** → alarm 起因説棄却 |
| 4 | **LID0 凍結** + alarm 90s | **91s 完走**、gpe70 増えず → spurious = LID0 (gpe70) 由来で確定 |
| 5 | LID0 再有効 + alarm 120s | **7s wake** → 凍結トグルでは直らない |
| 6 | 物理 lid close/open 実施後 + alarm 120s | **6s wake** → 「EC 未整定」説も棄却 |

解釈: **「S3 + 蓋開き + LID0 有効 → ~6s gpe70 spurious wake」はこの機体の持病で、AC/battery を問わない**。過去の「battery 特有 6s spurious」(report 2026-07-13_055510) は、リモート (=蓋開き) テストが battery 側でだけ行われ、AC の clean 実績 (lid wake 38/38 等) がすべて蓋閉じだったことによる**条件の交絡**だった可能性が高い。16 日 soak が正常だったのは実運用が蓋閉じ suspend だから。**GRUB deep 化による退行ではない** (同一 boot 内で LID0 凍結時のみ完走することから cmdline 非依存)。

- 実運用への影響: なし (蓋閉じ suspend では発生しない。蓋開きのアイドル自動 suspend では発生しうるが、soak 16 日で 1 件のみ)
- 46-lid0-ac-policy (battery 時のみ LID0 凍結) の設計前提「AC は clean」は「蓋閉じなら clean」に読み替えが必要。現行動作のままで実害はない
- 今後リモートで S3 e2e を行う際は **LID0 凍結 + RTC alarm** を標準手順とする

## Phase B: facetimehd 導入

### B-0 ベースライン

導入前の sleep 中 PM 状態を採取 ([添付](attachment/2026-07-29_191159_facetimehd_camera_enable/b0_pre_install_baseline.txt))。`02:00.0` / `00:1c.1` とも素の pci 経路で suspend 0us / noirq ~0.3ms (port ~11.3ms)、runtime D0・`d3cold_allowed=1`。

### B-1 ファームウェア

- `patjak/facetimehd-firmware` を clone、`make` が Apple CDN (`OSXUpd10.11.5.dmg` の byte-range 部分取得 ~2.7MB) から抽出 → **スクリプト内蔵ハッシュ照合 pass** (「Found matching hash from OS X, El Capitan 10.11.5」、firmware version 1.43.0)
- `firmware.bin` = 1,425,412 bytes (gzip 解凍後)。プラン記載の期待値 603,715 bytes は誤り (解凍前の別版の値) — 実ゲートはスクリプトの sha256 照合で、これは通っている
- `sudo make install` → `/usr/lib/firmware/facetimehd/firmware.bin`

### B-2 ドライバ (DKMS)

- `patjak/facetimehd` master (0.7.0.1) を `/usr/src/facetimehd-0.7.0.1` に配置、`dkms add/build/install` — kernel 6.12.95 で警告なくビルド成功 (MODULES_CONF deprecation 警告のみ。`blacklist bdc_pci` は本機で bdc_pci 未ロードのため実質無関係)
- `modprobe facetimehd` → **`Full memory verification succeeded! (0)`**、firmware 1392kb ロード、ISP 起床、`/dev/video0` 生成。懸念していた既知失敗 (issue #229 の `Full memory verification failed`) は発生せず
- 自動ロード: PCI modalias 経由の udev coldplug で再起動後に自動ロード確認済み → `/etc/modules-load.d/` への追加は不要だった
- 他カーネル: dkms status では 6.12.95 のみ installed (autoinstall=yes なので今後のカーネル更新には自動追従)。6.12.94-dpmwd4 向けは未ビルド (次に dpmwd4 で boot した場合は `dkms autoinstall` が走る。失敗しても本番カーネルに影響なし)

### B-3 suspend 中立化フック

`/usr/lib/systemd/system-sleep/47-facetimehd` を新設 (45-wl-unload と同型: pre で `modprobe -r facetimehd` (timeout 10s)、post で reload (timeout 15s)、フラグ `/run/facetimehd-unloaded`、ログ `/var/log/facetimehd-sleep.log`、`rm` 一発で可逆)。

目的: (1) sleep 中の `02:00.0` / `00:1c.1` の PM 状態を導入前と同一に保つ (00:1c.1 は hang 調査で共犯可能性未排除)、(2) facetimehd の resume 後不安定 (上流既知) の回避。

**既知の穴**: カメラ使用中 (`/dev/video0` busy) は unload が失敗し、FAILED をログに残して suspend を続行する = ドライバを載せたまま S3 に入る未検証構成。→ soak ウォッチリストに `facetimehd-sleep.log` の FAILED 行を追加。

### B-4 検証結果 (全 green)

| # | 項目 | 結果 |
|---|---|---|
| 1 | `v4l2-ctl --list-devices` / formats | Apple Facetime HD (PCI:0000:02:00.0)、YUYV/YVYU 1280x720@30fps |
| 2 | 権限 | udev uaccess が PCI カメラでも機能、ACL `user:miminashi:rw-` 付与を実測 |
| 3 | 実ストリーム | 30 フレーム取得 (sudo)、10 フレーム (非 root、ssh セッションでも ACL で可) |
| 4 | gnome-snapshot | 映像表示 OK (ユーザ目視) |
| 5 | Firefox WebRTC テストページ | デバイス列挙・許可ダイアログ・映像表示すべて OK (ユーザ目視) — **報告症状の解消確認** |
| 6 | suspend/resume 後 | LID0 凍結+alarm 90s で 91s 完走、47/45 フック対で発火、resume 後 `/dev/video0` 再生成・5 フレーム取得 |
| 7 | PM 中立性 | sleep cycle の `02:00.0`/`00:1c.1` callback がベースラインと同形 (素の pci 経路、suspend 0us / noirq 317us / port 11450us ≈ 導入前 262〜356us / 11348us) |
| 8 | 再起動後 | 自動ロード、boot 時 `Full memory verification succeeded`、ストリーム OK、`mem_sleep` = deep 維持 |

## 再現方法

```bash
# --- Phase A: GRUB deep 化 ---
ssh miminashi@macbookair2015.lan
sudo cp -a /etc/default/grub /etc/default/grub.bak-grub-deep-$(TZ=Asia/Tokyo date +%Y%m%d)
sudo sed -i 's/mem_sleep_default=s2idle/mem_sleep_default=deep/' /etc/default/grub
sudo update-grub && sudo sync   # sync 必須 (GRUB はジャーナル未反映ブロックを読む)
sudo systemctl reboot
# 検収: cat /proc/cmdline; cat /sys/power/mem_sleep

# --- Phase B: facetimehd ---
mkdir -p ~/src && cd ~/src
git clone --depth 1 https://github.com/patjak/facetimehd-firmware.git
cd facetimehd-firmware && make          # 「Found matching hash」を確認してから
sudo make install                        # /usr/lib/firmware/facetimehd/firmware.bin
cd ~/src && git clone --depth 1 https://github.com/patjak/facetimehd.git
sudo cp -a facetimehd /usr/src/facetimehd-0.7.0.1
sudo /usr/sbin/dkms add -m facetimehd -v 0.7.0.1
sudo /usr/sbin/dkms build -m facetimehd -v 0.7.0.1
sudo /usr/sbin/dkms install -m facetimehd -v 0.7.0.1
sudo modprobe facetimehd
sudo dmesg | grep -E 'Full memory verification|Loaded firmware'   # succeeded を確認
# フック: /usr/lib/systemd/system-sleep/47-facetimehd (本文参照、45-wl-unload と同型)
# 検証: sudo apt-get install -y v4l-utils
#       v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=30

# --- リモート S3 e2e の標準手順 (蓋開き spurious 回避) ---
echo LID0 | sudo tee /proc/acpi/wakeup          # 凍結 (状態ガード付きで)
echo $(( $(cat /sys/class/rtc/rtc0/since_epoch) + 90 )) | sudo tee /sys/class/rtc/rtc0/wakealarm
sudo systemctl suspend
# 復帰後: LID0 再有効化 + wakealarm クリア (echo 0)
```

### ロールバック

```bash
# カメラ
sudo /usr/sbin/dkms remove facetimehd/0.7.0.1 --all && sudo rm -rf /usr/src/facetimehd-0.7.0.1
sudo rm -rf /usr/lib/firmware/facetimehd
sudo rm -f /usr/lib/systemd/system-sleep/47-facetimehd
sudo depmod -a
# S3 → s2idle
sudo cp /etc/default/grub.bak-grub-deep-20260729 /etc/default/grub
sudo update-grub && sudo sync && sudo systemctl reboot   # (+ 必要なら s3-deep-select.service も disable)
```

## 参照した過去レポート

- [S3 再挑戦 — lid wake 復活と wl unload (Phase 5 恒久化)](2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload.md) — soak 開始と GRUB deep 化の積み残し、battery spurious 6s の記録 (本レポートで解釈を訂正候補化)
- [suspend hang 調査総括](2026-07-13_005126_suspend_hang_investigation_summary.md) — 00:1c.1 (カメラ親) の共犯未排除の経緯
- [Phase C-7 Rung 2 — 非 TB ルートポート 3 本で hang 消滅](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md) — 02:00.0 への d3cold_allowed 書込みで 00:1c.1 を D0 固定した実績 (今回のフック設計の背景)

## 今後・残リスク

1. **soak 継続** (S3 + カメラ構成)。ウォッチリスト既存項目に加え: `facetimehd-sleep.log` の FAILED 行 (カメラ使用中 suspend = ドライバ載せたまま S3 の未検証構成)、カメラ起因の新規 hang (発生時は一級データ)
2. **蓋開き spurious の解釈訂正**は本レポートの 6 サイクルが根拠。7/13 の battery 3/3 データとの完全統合 (battery + 蓋閉じで clean になるか) は未検証 — 必要になったら battery + 蓋閉じ + LID0 有効の対照を 1 本取る
3. facetimehd は upstream 追従が必要な out-of-tree ドライバ。カーネル大幅更新 (6.13+) で DKMS ビルドが割れたら `~/src/facetimehd` を `git pull` して再 add/build/install
4. 稼働中 (非 sleep) の消費電力がわずかに増える可能性 (ISP 常時給電)。体感悪化があれば `modprobe -r facetimehd` で切り分け可
