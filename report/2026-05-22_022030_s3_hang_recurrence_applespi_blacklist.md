# MacBook Air lid open 復帰失敗 (S3 hang) 再発と Phase B 候補 2 (applespi blacklist) 適用

- **実施日時**: 2026年5月22日 02:18 〜 02:22 JST
- **対象ホスト**: `macbookair2015.lan` (MacBookAir7,1)

## 添付ファイル

- [実装プラン](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/plan.md)
- [再発 boot (77cd5397) 末尾ログ](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/hang_boot_77cd5397_tail.txt)
- [対策実装後の全 boot 集計](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/post_install_boot_summary.txt)

## 前提・目的

### 背景

[2026-05-10 のレポート](2026-05-10_055032_lid_open_resume_hang.md) で `i915.enable_dc=0`
を暫定対策として導入し、4〜6 週間の継続観測フェーズに入っていた。導入から 12 日後の
2026-05-19 09:15:58 にスリープ復帰失敗が再発したため、前回プランで予告していた次の手
(Phase B 候補 2: `applespi` ブラックリスト) を適用する。

### 目的

1. 再発を `journalctl -b -1` 末尾ログから確定させ、ハングシグネチャを記録する。
2. `applespi` ブラックリストを適用し、`no_console_suspend` を追加して次回 hang 時の
   debug 情報を確保する。
3. 既存検出スクリプト `check-suspend-resume.sh` が今回再発を捕捉できなかった原因に
   対処し、早期ハング (`PM: suspend entry` が出る前で停止) も検出できるよう更新する。

### 前提条件

- ssh `miminashi@macbookair2015.lan` 経由で操作可能 (NOPASSWD sudo 設定済み)。
- S3 deep 維持がゴール (s2idle は lid open で wake せず・KB バックライト点灯の理由で
  常用不可、と前回確定済み)。
- 前回プランで `applespi` ブラックリスト適用手順は既に文書化済み (本対応はその実行)。

## 環境情報

- ハードウェア: Apple MacBookAir7,1 (Broadwell-U, 11" Early 2015)
  - GPU: Intel HD Graphics 6000、内蔵 eDP-1 (PSR 非対応)
  - Trackpad/Keyboard: USB (`bcm5974` driver) — `applespi` は本機未使用だが auto-load
- OS: Debian 13 (trixie)、kernel `6.12.88+deb13-amd64`
- 実装直前のカーネルパラメータ:
  - `quiet i915.enable_dc=0` (前回適用済み)
- `/sys/power/mem_sleep` = `s2idle [deep]`
- `applespi` モジュール状態 (実装前): loaded, use_count=0

## 再発の確定 (実装前のログ確認)

直前 boot `77cd5397` の `journalctl -b -1` 末尾は以下で停止:

```
5月 19 09:15:57 macbookair2015 gnome-shell[1711]: Cursor update failed: drmModeAtomicCommit: 無効な引数です
5月 19 09:15:58 macbookair2015 systemd[1]: Reached target sleep.target - Sleep.
5月 19 09:15:58 macbookair2015 systemd[1]: Starting systemd-suspend.service - System Suspend...
5月 19 09:15:58 macbookair2015 systemd[1]: session-2.scope: Unit now frozen-by-parent.
5月 19 09:15:58 macbookair2015 systemd[1]: user@1000.service: Unit now frozen-by-parent.
5月 19 09:15:58 macbookair2015 systemd[1]: user-1000.slice: Unit now frozen-by-parent.
5月 19 09:15:58 macbookair2015 systemd[1]: user.slice: Unit now frozen.
5月 19 09:15:58 macbookair2015 systemd-sleep[221678]: Successfully froze unit 'user.slice'.
5月 19 09:15:58 macbookair2015 systemd-sleep[221678]: Performing sleep operation 'suspend'...
(以降、完全停止 → 強制電源オフ → 5/22 01:33:48 に手動起動)
```

完全な末尾ログは
[hang_boot_77cd5397_tail.txt](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/hang_boot_77cd5397_tail.txt)
を参照。

### 今回のハングシグネチャの重要な変化

前回観測した 4 件はいずれも `PM: suspend entry (deep)` で停止していたが、今回は
それより**一段早い段階**で停止している:

- 前回パターン: `Performing sleep operation 'suspend'...` → `PM: suspend entry (deep)` → 停止
- 今回パターン: `Performing sleep operation 'suspend'...` → **停止** (`PM: suspend entry`
  まで到達せず)

これは「カーネルが actual `pm_suspend()` に入ろうとした **device suspend phase**」で
停止していることを示唆する。`applespi.suspend` 等のドライバ suspend フックは
`PM: suspend entry` ログ発行より前 (デバイス freeze 直前) に実行されるため、未使用
ドライバの suspend フックが固まる仮説 (= `applespi` ブラックリスト) と整合する。

### 検出スクリプトの不備が露呈

既存 v1 スクリプトは `PM: suspend entry` ログのカウント差分で hang を検出する設計
だったため、今回のように `PM: suspend entry` 自体が出力されないと **検出不能** だった
(再発 boot も `suspend=10/resume=10 diff=0` で正常 boot と区別が付かなかった)。
本対応で v2 へ更新する。

### 統計的解釈

`i915.enable_dc=0` 導入後 12 日間で hang 1 件 ≈ 週 0.58 件。元の頻度 (週 0.7 件) と
統計的に区別不能であり、`i915.enable_dc=0` 単独では本件を解決できないと判断する。

なお v2 スクリプトで過去 boot を遡って再判定したところ、**前回 v1 で見落としていた
hang が 1 件追加発見** された (`17ecb545`、4/26 18:28、末尾が `PM: suspend entry (deep)`
で suspend cycle 数の偶然から v1 では diff=0 と判定)。これにより 4/1 〜 5/22 (約 7.5 週間)
の hang 件数は **6 件** ≈ 週 0.8 件 となり、前回の頻度推定値 0.7 件/週とほぼ一致する。

## 再現方法 (実装手順)

実機で実行したコマンドは [プランファイル](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/plan.md)
の Step 1 〜 Step 6 に記載。要点のみ再掲:

### 1. `/etc/default/grub` バックアップ

```bash
sudo cp -av /etc/default/grub /etc/default/grub.bak.20260522_021812
```

### 2. `applespi` ブラックリスト設定 + initramfs 更新

```bash
sudo tee /etc/modprobe.d/disable-applespi.conf > /dev/null << "EOF"
# MBA 7,1 では applespi が bind するデバイスは存在しない (USB トラックパッド/キーボード)。
# 未使用ドライバが suspend hook 経由で不安定要因になる懸念があり、
# i915.enable_dc=0 だけでは S3 hang が再発したため (2026-05-19 再現確認) blacklist する。
blacklist applespi
EOF
sudo update-initramfs -u
```

### 3. `no_console_suspend` をカーネルパラメータに追加

```bash
sudo sed -i 's|GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"|GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend"|' /etc/default/grub
sudo update-grub
```

### 4. 検出スクリプトを v2 に更新

判定方針を「`PM: suspend entry` カウント差分」から「各 boot 末尾 200 行の graceful
shutdown マーカー有無 + 最後の 1 行が hang シグネチャか」に変更。スクリプト本体は
プランファイル Step 4 を参照。

### 5. 再起動

```bash
sudo systemctl reboot
```

### 6. 反映確認

下記の `結果` セクション「実装直後の反映確認」を参照。

## 結果

### 実装直後の反映確認

reboot 後の boot `9d3a4572` で以下を確認:

```
=== /proc/cmdline ===
BOOT_IMAGE=/boot/vmlinuz-6.12.88+deb13-amd64 root=UUID=147f49dc-e854-47df-a721-b304a1c0c7bd
ro quiet i915.enable_dc=0 no_console_suspend

=== applespi loaded? ===
(applespi not loaded — OK)

=== modprobe.d ===
broadcom-sta-dkms.conf  broadcom-sta.conf  disable-applespi.conf
dkms.conf  intel-microcode-blacklist.conf

=== i915 enable_dc ===
0
```

| チェック項目 | 期待値 | 実測値 | 判定 |
|---|---|---|---|
| `/proc/cmdline` に `i915.enable_dc=0` | あり | あり | ✅ |
| `/proc/cmdline` に `no_console_suspend` | あり | あり | ✅ |
| `lsmod \| grep applespi` | 空 | 空 | ✅ |
| `/etc/modprobe.d/disable-applespi.conf` | 存在 | 存在 | ✅ |
| `/sys/module/i915/parameters/enable_dc` | `0` | `0` | ✅ |

### v2 検出スクリプトの動作確認

[post_install_boot_summary.txt](attachment/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist/post_install_boot_summary.txt)
に reboot 後 (今回の対策反映後) の全 boot 集計を保存。重要部分の抜粋:

| boot | suspend | resume | diff | grace | hang |
|---|---:|---:|---:|---|---|
| `edea8161` | 18 | 17 | 1 | UNGRACEFUL | [S3-HANG] |
| `17ecb545` | 1 | 1 | 0 | UNGRACEFUL | **[S3-HANG] (v2 新規検出)** |
| `b4415a38` | 13 | 12 | 1 | UNGRACEFUL | [S3-HANG] |
| `8ffbacdb` | 5 | 4 | 1 | UNGRACEFUL | [S3-HANG] |
| `139bb7e4` | 10 | 9 | 1 | UNGRACEFUL | [S3-HANG] |
| `77cd5397` | 10 | 10 | 0 | UNGRACEFUL | **[S3-HANG] (今回再発)** |
| `9d3a4572` | 1 | 1 | 0 | current | — |

v2 は `diff` が 0 でも末尾ログの停止位置で hang を正しく分類できることが確認できた。

### 永続化設定 (実装完了時点)

実機 `macbookair2015.lan` の状態:

- `/etc/default/grub`:
  ```
  GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend"
  ```
- `/etc/modprobe.d/disable-applespi.conf`:
  ```
  blacklist applespi
  ```
- `/usr/local/sbin/check-suspend-resume.sh`: v2 (末尾ログ判定方式)
- `/etc/default/grub.bak.20260522_021812`: 今回作業前のバックアップ
- カーネルパラメータ実効値: `i915.enable_dc=0` ・ `no_console_suspend` ともに有効

## 今後のフォロー (継続観測)

### 観測期間

前回と同じく頻度 ~0.7 件/週を仮定:

| 観測期間 (基準: 2026-05-22) | 期待 hang 件数 | 0 件で済む確率 (Poisson) |
|---|---:|---:|
| 2 週間 (〜 06-05) | 1.4 | ≈ 25% |
| 4 週間 (〜 06-19) | 2.8 | ≈ 6% |
| 6 週間 (〜 07-03) | 4.2 | ≈ 1.5% |

判定窓: 4 週間 (〜 2026-06-19) で 0 件なら効果ありと暫定判断、6 週間 (〜 2026-07-03)
で 0 件なら恒久採用。

### 観測コマンド

```bash
ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh | tail -15'
```

v2 スクリプトは boot 末尾の graceful shutdown マーカーで判定するため、`diff=0` でも
末尾ログ判定で hang が見つかれば `UNGRACEFUL [S3-HANG]` と分類される。今回のような
早期 hang も逃さない。

### 再発時の次の一手

`applespi` 無効化でも hang が再発した場合の手順:

1. **`no_console_suspend` のおかげで増えているはずのカーネルログを確認**:
   ```bash
   prev=$(sudo journalctl --list-boots --no-pager | awk '$1 ~ /^-?[0-9]+$/' | tail -2 | head -1 | awk '{print $1}')
   sudo journalctl -b "$prev" _TRANSPORT=kernel --no-pager | tail -50
   ```
   ハング直前にどのドライバ/サブシステムまで suspend が進んでいたかを観察し、
   原因デバイスの特定を試みる (前回までは `Performing sleep operation 'suspend'`
   または `PM: suspend entry (deep)` 以降は完全に消えていたが、今回は console 出力
   が残ることでより詳細なフェーズが見える期待がある)。

2. **`pcie_aspm=off` を追加** (Phase B 候補 3): grub の `GRUB_CMDLINE_LINUX_DEFAULT`
   末尾に `pcie_aspm=off` を追記 → `update-grub` → reboot。副作用として待機電力増。

3. それでも改善しなければ、`acpi_osi=` (Apple firmware の SMI 経路を変えるトリック)
   等を検討。

## ロールバック手順

`applespi` blacklist と `no_console_suspend` を元に戻す場合:

```bash
ssh miminashi@macbookair2015.lan '
  sudo rm /etc/modprobe.d/disable-applespi.conf
  sudo update-initramfs -u
  sudo cp -av /etc/default/grub.bak.20260522_021812 /etc/default/grub
  sudo update-grub
  sudo systemctl reboot
'
```

検出スクリプト v1 への戻しは原則不要 (v2 は v1 の出力フィールドを完全に内包する
スーパーセット)。
