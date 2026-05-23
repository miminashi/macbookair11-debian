# MacBook Air S3 hang 再発 (1 日 2 回) と `pcie_aspm=off` 追加 + `pm_print_times` 永続化

- **実施日時**: 2026年5月23日 14:45 〜 14:50 JST
- **対象ホスト**: `macbookair2015.lan` (MacBookAir7,1)

## 添付ファイル

- [実装プラン](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/plan.md)
- [hang boot `9d3a4572` 末尾ログ (5/23 12:35 停止)](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/hang_boot_9d3a4572_tail.txt)
- [hang boot `260710ee` 末尾ログ (5/23 13:16 停止)](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/hang_boot_260710ee_tail.txt)
- [対策実装後の全 boot 集計](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/post_install_boot_summary.txt)
- [動作確認時の PM device timing ログ抜粋](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/post_install_pm_log_sample.txt)

## 前提・目的

### 背景

[2026-05-22 のレポート](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) で
`applespi` ブラックリスト + `no_console_suspend` を適用した直後 (約 35 時間)、
**本日 2026-05-23 に lid open 復帰失敗 (S3 hang) が 2 件発生** したため、前回プランで
予告していた **Phase B 候補 3 (`pcie_aspm=off`)** を適用する。あわせて、次回 hang
時に原因 device を特定できるよう **`pm_print_times=1` を永続化** する。

参照する過去レポート:

- [2026-05-10: lid open 復帰失敗 (S3 hang) 切り分けと暫定対策](2026-05-10_055032_lid_open_resume_hang.md)
- [2026-05-22: S3 hang 再発と applespi ブラックリスト適用](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md)

### 目的

1. 本日 2 件の hang シグネチャを確定し記録する。
2. `pcie_aspm=off` を grub に追加して観測を再開する。
3. `pm_print_times=1` を起動時から有効化し、次回 hang 時の原因 device を特定可能にする。
4. 失敗した前回観測期間を区切り、新しい観測期間を設定する。

### 前提条件

- ssh `miminashi@macbookair2015.lan` 経由で操作可能 (NOPASSWD sudo 設定済み)。
- S3 deep 維持がゴール (s2idle は lid open で wake せず・KB バックライト点灯のため常用不可、と確定済み)。
- 前回プラン Phase B 候補 3 の手順は既に文書化済み (本対応はその実行)。

## 環境情報

- ハードウェア: Apple MacBookAir7,1 (Broadwell-U, 11" Early 2015)
  - GPU: Intel HD Graphics 6000、内蔵 eDP-1 (PSR 非対応)
  - Trackpad/Keyboard: USB (`bcm5974`)、`applespi` は本機未使用で blacklist 済
- OS: Debian 13 (trixie)、kernel `6.12.88+deb13-amd64`
- 実装直前のカーネルパラメータ:
  - `quiet i915.enable_dc=0 no_console_suspend` (5/22 適用済み)
- `/sys/power/mem_sleep` = `s2idle [deep]`
- `/sys/power/pm_print_times` = `0` (デフォルト、本対応で永続的に `1` に変更)
- pstore backend: `efi-pstore` 有効・マウント済み (`/sys/fs/pstore type pstore`)
  ※ 強制電源断時には EFI runtime services を呼べないため、本症状 (静かなフリーズ)
  の debug には期待しにくいことを確認済。

## 再発の確定 (実装前のログ確認)

### hang 1 件目: boot `9d3a4572` 末尾

```
5月 23 12:35:02 macbookair2015 kernel: PM: suspend entry (deep)
(以降、完全停止 → 強制電源オフ)
```

完全な末尾ログは
[hang_boot_9d3a4572_tail.txt](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/hang_boot_9d3a4572_tail.txt)
を参照。

### hang 2 件目: boot `260710ee` 末尾

```
5月 23 13:16:26 macbookair2015 kernel: PM: suspend entry (deep)
(以降、完全停止 → 強制電源オフ)
```

完全な末尾ログは
[hang_boot_260710ee_tail.txt](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/hang_boot_260710ee_tail.txt)
を参照。

### 観察と統計的解釈

| 観察 | 内容 |
|---|---|
| ハング位置 | 両者とも `PM: suspend entry (deep)` 直後で停止 |
| `no_console_suspend` 追加情報 | **無し** (期待外れ) |
| 5/22 〜 5/23 の dpkg/apt 更新 | 無し (頻度悪化は外部要因では説明不可) |
| カーネルバージョン変化 | なし (`6.12.88+deb13-amd64` 据え置き) |
| `applespi` blacklist 状態 | 維持 (`lsmod | grep applespi` → 空) |

`no_console_suspend` で追加情報が得られなかった原理:

> console 出力は kernel ring buffer を経由し、resume 時にまとめて journal に flush
> される。**強制電源断ではこの flush が起きないため ring buffer ごと消失** する。
> したがって `no_console_suspend` 単独では「ハング直前のメッセージを永続化」できない。

頻度:

- baseline: 0.7〜0.8 件/週 ([前回までの 6 件/7.5 週間](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md#%E7%B5%B1%E8%A8%88%E7%9A%84%E8%A7%A3%E9%87%88))
- 5/22 02:23 〜 5/23 13:16 (35h): 2 件 ≒ 9.6 件/週 (≒ 12 倍)
- suspend cycle 単位だと boot `9d3a4572` 5 cycle 中 1 hang、boot `260710ee` 2 cycle
  中 1 hang、**合計 6 cycle 中 2 hang ≒ 33%**

サンプル数は少ない (6 cycle) ため、Poisson 偶然 (確率 ≈ 1.2%) の可能性も完全には
否定できない。ただし「対策直後に頻度が悪化したように見える」点は本レポートで明示する。

なお `applespi` blacklist の効果について: 前回観測された「`PM: suspend entry`
未到達の早期 hang」(5/19 の `77cd5397`、サンプル 1 件) は今回再発していないが、
**サンプル 1 件で効果を統計的に評価することはできない**。

## 採用方針

`pcie_aspm=off` (実対策) と `pm_print_times=1` 永続化 (診断強化) を**同一 reboot で
適用**する。

### attribution の取り扱い

- `pcie_aspm=off` と `pm_print_times=1` を同時に入れるため、「どちらが効いたか」は
  厳密には区別できない。
- ただし `pm_print_times=1` は kernel log に device suspend timing を追加出力する
  だけで suspend 経路を変えない (kernel doc 上も debug 用と位置付け) ため、効果の
  attribution は実質的に `pcie_aspm=off` に帰せられる。
- `applespi` blacklist と `no_console_suspend` は **rollback しない**:
  - 前者: 早期 hang のサンプル 1 件のみで効果評価できず、rollback して debug 母数を
    減らす意義が薄い
  - 後者: 副作用なし

### 採用しなかった選択肢

- **`applespi` blacklist の rollback**: 上記理由により見送り。
- **新たな pstore 設定の追加**: `efi-pstore` は既に有効・マウント済み。強制電源断時に
  EFI runtime services を呼べないため、追加設定をしても今回の症状 (静かなフリーズ)
  では効果が薄い。
- **`acpi_osi=` 系 (Apple firmware SMI 経路変更)**: Phase B 候補 4 として温存。
  `pcie_aspm=off` で改善しなかった場合の次手とする。

## 再現方法 (実装手順)

すべて `ssh miminashi@macbookair2015.lan` 経由で実施。詳細は
[プランファイル](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/plan.md)
の Step 0 〜 Step 7 に記載。要点を再掲:

### 1. hang 末尾ログを開発側に保存

```bash
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -2 _TRANSPORT=kernel --no-pager | tail -80' \
  > report/attachment/<NAME>/hang_boot_9d3a4572_tail.txt
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 _TRANSPORT=kernel --no-pager | tail -80' \
  > report/attachment/<NAME>/hang_boot_260710ee_tail.txt
```

### 2. `/etc/default/grub` バックアップ

```bash
sudo cp -av /etc/default/grub /etc/default/grub.bak.20260523_144603
```

### 3. `pcie_aspm=off` を grub に追加

```bash
sudo sed -i 's|GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend"|GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off"|' /etc/default/grub
sudo update-grub
```

### 4. `pm_print_times=1` を永続化 (systemd-tmpfiles)

```bash
sudo tee /etc/tmpfiles.d/pm_print_times.conf > /dev/null << "EOF"
# Persist /sys/power/pm_print_times = 1 across boots.
# S3 hang 時に最後の device suspend 完了行を kernel log に残すため。
# 詳細: https://www.kernel.org/doc/html/latest/admin-guide/pm/sleep-states.html
w /sys/power/pm_print_times - - - - 1
EOF
sudo systemd-tmpfiles --create /etc/tmpfiles.d/pm_print_times.conf
```

### 5. 再起動

```bash
sudo systemctl reboot
```

### 6. 反映確認

下記の「結果」セクションを参照。

## 結果

### 実装直後の反映確認

reboot 後の boot `857b9e52` で以下を確認:

```
=== /proc/cmdline ===
BOOT_IMAGE=/boot/vmlinuz-6.12.88+deb13-amd64 root=UUID=147f49dc-e854-47df-a721-b304a1c0c7bd
ro quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off

=== /sys/power/pm_print_times ===
1

=== applespi loaded? ===
(applespi not loaded - OK)

=== /sys/module/i915/parameters/enable_dc ===
0

=== /etc/tmpfiles.d/pm_print_times.conf ===
-rw-r--r-- 1 root root 258  5月 23 14:46 /etc/tmpfiles.d/pm_print_times.conf
```

| チェック項目 | 期待値 | 実測値 | 判定 |
|---|---|---|---|
| `/proc/cmdline` に `pcie_aspm=off` | あり | あり | ✅ |
| `/proc/cmdline` に `i915.enable_dc=0` `no_console_suspend` | 保持 | 保持 | ✅ |
| `/sys/power/pm_print_times` | `1` | `1` | ✅ |
| `lsmod \| grep applespi` | 空 | 空 | ✅ |
| `/etc/tmpfiles.d/pm_print_times.conf` | 存在 | 存在 | ✅ |
| `/sys/module/i915/parameters/enable_dc` | `0` | `0` | ✅ |

### ASPM が実際に無効化されているか (PCI レベル)

`/proc/cmdline` の文字列だけでは「カーネルが parameter を受理したか」しか分からないため、
ASPM が実際に PCI レベルで disable されているか確認:

```
=== dmesg ASPM messages ===
[    0.038196] Kernel command line: ... pcie_aspm=off
[    0.038330] PCIe ASPM is disabled
```

dmesg に **`PCIe ASPM is disabled`** が出ているため、カーネルの ASPM 制御は無効化された。
ただし `pcie_aspm=off` の標準挙動として、これは **「カーネルが ASPM の制御を諦める」**
ことを意味し、**firmware で設定された link 単位の ASPM 設定はそのまま** になる:

| PCI link | LnkCtl: ASPM 状態 |
|---|---|
| `00:1c.0` (Root Port #1) | Disabled |
| `00:1c.1` (Root Port #2) | L1 Enabled (firmware 由来) |
| `00:1c.2` (Root Port #3) | L0s L1 Enabled (firmware 由来) |
| `00:1c.4` (Root Port #5) | Disabled |
| `00:1c.5` (Root Port #6) | L1 Enabled (firmware 由来) |
| `02:00.0` (FaceTime HD Camera) | L1 Enabled (firmware 由来) |
| `03:00.0` (BCM4360 Wi-Fi) | L0s L1 Enabled (firmware 由来) |
| `04:00.0` (Samsung SSD) | L1 Enabled (firmware 由来) |
| `05:00.0`〜`07:00.0` (Thunderbolt) | Disabled |

意図: **S3 hang 対策として重要なのは「suspend/resume 時にカーネルが link state を
変更しなくなる」点**。link 単位の ASPM enabled が一部残るのは仕様通り。

もし `pcie_aspm=off` で hang が改善しない場合の次手として、**`pcie_aspm.policy=performance`**
を追記すれば、カーネルが各 link の ASPM 制御を取り戻したうえで全 link を Disabled に
強制する経路も用意できる。

### lid close → open 1 cycle の動作確認

reboot 直後 (boot `857b9e52`) で 14:48:55 に suspend、14:49:02 に resume (合計 7 秒) が
**graceful** に完了:

```
5月 23 14:48:55 systemd[1]: Reached target sleep.target - Sleep.
5月 23 14:48:55 systemd-sleep[2812]: Performing sleep operation 'suspend'...
5月 23 14:48:55 kernel: PM: suspend entry (deep)
5月 23 14:49:02 kernel: PM: suspend exit
```

`pm_print_times=1` が正しく機能していることも確認。**640 行** の device-level PM
タイミングログが journal に永続化された。代表例:

```
... PM: calling pci_pm_suspend @ 2812, parent: pci0000:00
... PM: pci_pm_resume returned 0 after 444059 usecs   ← i915 0000:00:02.0
... PM: calling input_dev_suspend @ 2812, parent: card0
... PM: input_dev_resume returned 0 after 0 usecs
... PM: calling platform_pm_resume @ 2812, parent: platform   ← applesmc.768
... PM: platform_pm_resume returned 0 after 259 usecs
```

i915 PCI resume が 444 ms と他 device より突出しているのは元から既知の挙動。
詳細は [post_install_pm_log_sample.txt](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/post_install_pm_log_sample.txt)
を参照。

### v2 検出スクリプトの動作確認

[post_install_boot_summary.txt](attachment/2026-05-23_144518_s3_hang_pcie_aspm_off/post_install_boot_summary.txt)
に reboot 後の全 boot 集計を保存。重要部分の抜粋:

| boot | off | suspend | resume | diff | grace | hang |
|---|---:|---:|---:|---:|---|---|
| `9d3a4572` | -3 | 5 | 4 | 1 | UNGRACEFUL | **[S3-HANG] (本日 1 件目)** |
| `260710ee` | -2 | 1 | 1 | 0 | UNGRACEFUL | **[S3-HANG] (本日 2 件目)** |
| `3ad4dc09` | -1 | 1 | 1 | 0 | graceful | — |
| `857b9e52` | 0 | 1 | 1 | 0 | current | — (1 cycle 成功) |

### 永続化設定 (実装完了時点)

実機 `macbookair2015.lan` の状態:

- `/etc/default/grub`:
  ```
  GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off"
  ```
- `/etc/modprobe.d/disable-applespi.conf`: 維持 (5/22 適用済み)
- `/etc/tmpfiles.d/pm_print_times.conf` (新規):
  ```
  w /sys/power/pm_print_times - - - - 1
  ```
- `/usr/local/sbin/check-suspend-resume.sh`: v2 (5/22 適用済み、変更なし)
- `/etc/default/grub.bak.20260523_144603`: 今回作業前のバックアップ
- カーネルパラメータ実効値:
  - `i915.enable_dc=0` ・ `no_console_suspend` ・ `pcie_aspm=off` すべて有効
- `/sys/power/pm_print_times` = `1`

## 今後のフォロー (継続観測)

### 観測期間

直近 35h で 2 件発生したケースもあるため短期側を強めに見る。
頻度 ~0.7-0.8 件/週を仮定したベースラインとの比較:

| 観測期間 (基準: 2026-05-23) | 期待 hang 件数 | 0 件で済む確率 (Poisson) |
|---|---:|---:|
| 1 週間 (〜 05-30) | 0.8 | ≈ 45% |
| 2 週間 (〜 06-06) | 1.6 | ≈ 20% |
| 4 週間 (〜 06-20) | 3.2 | ≈ 4% |
| 6 週間 (〜 07-04) | 4.8 | ≈ 0.8% |

判定窓:

- 4 週間 (〜 2026-06-20) で 0 件なら **効果ありと暫定判断**
- 6 週間 (〜 2026-07-04) で 0 件なら **恒久採用**
- **1 週間以内に再発したら次の手** (`acpi_osi=` 系) に進む

### 観測コマンド

```bash
ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh | tail -15'
```

### 再発時の調査手順

`pm_print_times=1` で device-level timing が journal に保存されるようになったため、
hang 直前にどの device の suspend で止まったかを直接見られる:

```bash
ssh miminashi@macbookair2015.lan '
  prev=$(sudo journalctl --list-boots --no-pager | awk "\$1 ~ /^-?[0-9]+\$/" | tail -2 | head -1 | awk "{print \$1}")
  sudo journalctl -b "$prev" --no-pager | grep -E "PM: calling|PM: .* returned" | tail -50
'
```

末尾の `PM: calling <fn>` で対応する `returned` が無い device が**ハング原因 device の
最有力候補**。

(注意: `_TRANSPORT=kernel` フィルタを付けるのは避ける。動作確認時に
`journalctl -b _TRANSPORT=kernel -g "..." --no-pager` がうまく一致しなかった
事象があったため、`grep` で pipe して絞り込む方が確実。)

### 再発時の次の一手 (Phase B 候補 4: `acpi_osi=`)

`pcie_aspm=off` でも hang が再発した場合の手順:

1. 再発 boot の末尾 PM device timing を確認 (上記コマンド)
2. 特定された device があれば、そのドライバ個別の workaround を優先検討
3. 一般的な次手として、grub の `GRUB_CMDLINE_LINUX_DEFAULT` に `acpi_osi=` または
   `acpi_osi="!Windows 2009"` を追記して Apple firmware の SMI 経路を変える

## ロールバック手順

`pcie_aspm=off` と `pm_print_times=1` を元に戻す場合:

```bash
ssh miminashi@macbookair2015.lan '
  sudo cp -av /etc/default/grub.bak.20260523_144603 /etc/default/grub
  sudo update-grub
  sudo rm /etc/tmpfiles.d/pm_print_times.conf
  sudo systemctl reboot
'
```

`applespi` blacklist と `no_console_suspend` の rollback はこれと独立。
[2026-05-22 レポートのロールバック手順](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md#%E3%83%AD%E3%83%BC%E3%83%AB%E3%83%90%E3%83%83%E3%82%AF%E6%89%8B%E9%A0%86)
を参照。
