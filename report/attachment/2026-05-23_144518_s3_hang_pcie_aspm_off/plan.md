# MacBook Air S3 hang 再発 (2026-05-23 1 日 2 回) と pcie_aspm=off 追加 + pm_print_times 永続化

## Context

### なぜこの対応をするか

`macbookair2015.lan` (MacBookAir7,1) の S3 hang 対策として 2026-05-22 に
`applespi` ブラックリスト + `no_console_suspend` を適用した
([前回レポート](../projects/macbookair11-debian/report/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md))。
その直後 (2026-05-22 02:23 以降の 35 時間) で **本日 2 件の lid open 復帰失敗**
が発生した。

### 観測事実

- boot `9d3a4572` 末尾 (5/23 12:35:02): `PM: suspend entry (deep)` で停止 → 強制電源断
- boot `260710ee` 末尾 (5/23 13:16:26): `PM: suspend entry (deep)` で停止 → 強制電源断
- 両者とも `_TRANSPORT=kernel` ログには `PM: suspend entry (deep)` 直後で停止し、`no_console_suspend` を入れたにも関わらず追加情報なし
  - 原理的に: console 出力は ring buffer 経由で resume 時に flush されるため、強制電源断で消失する。`no_console_suspend` 単独では「ハング直前のメッセージを永続化」できない
- 5/22 02:23 以降 dpkg/apt の更新は無し (頻度悪化は外部要因では説明できない)
- カーネル `6.12.88+deb13-amd64` は変更なし
- `efi-pstore` は既に有効・マウント済み (`pstore on /sys/fs/pstore type pstore`) だが、強制電源断時に EFI runtime services が呼べないため hang のログ保存には期待しにくい

### 統計的解釈

- baseline: 0.7〜0.8 件/週
- 5/22 02:23 〜 5/23 13:16 (35h): 2 件 ≒ 9.6 件/週
- suspend cycle 単位では 6 cycle 中 2 hang ≒ 33%。過去の 5〜10% 失敗率を大きく超える
- ただしサンプルが少ない (6 cycle) ため Poisson 偶然 (≈ 1.2%) も否定はできない
- `applespi` blacklist で「`PM: suspend entry` 未到達の早期 hang」(5/19 の 77cd5397) のパターンは観測されていないが、サンプル 1 件で効果評価はできない

### 意図する成果

- 前回プランの Phase B 候補 3 (`pcie_aspm=off`) を実機に適用し、観測を再開する
- 次回 hang 時に原因 device を特定できるよう `pm_print_times=1` を永続化する
- 失敗となった前回観測期間を区切り、新しい観測期間を設定する

## 採用方針

`pcie_aspm=off` (実対策) と `pm_print_times=1` 永続化 (診断強化) を同一 reboot で適用する。

### attribution についての明示

- `pcie_aspm=off` と `pm_print_times=1` を同時に入れるため、「どちらが効いたか」は区別できない
- ただし `pm_print_times=1` は kernel log の冗長性を増すのみで suspend 経路を変更しない (Phase 開始からの慣例的な safe 設定) ため、効果の attribution は実質的に `pcie_aspm=off` に帰せられる
- `applespi` blacklist と `no_console_suspend` は **rollback しない** (前者は早期 hang のサンプル 1 を残しているため確証が無い、後者は副作用なし)

### 採用しなかった選択肢

- **`applespi` blacklist の rollback**: サンプル数不足 (1 件) で効果の有無を判定不能。元に戻すと debug 母数を減らすだけで意義が薄い
- **新たな pstore 設定の追加**: `efi-pstore` は既に有効・マウント済み。強制電源断時に EFI runtime services が呼べないため、追加設定をしても今回の症状 (静かなフリーズ) では効果が薄い
- **`acpi_osi=` 系 (Apple firmware SMI 経路変更)**: Phase B 候補 4 として温存。`pcie_aspm=off` で改善しなかった場合の次手

## 実装手順

すべて `ssh miminashi@macbookair2015.lan` 経由で実施。

### Step 0. 事前確認・現状記録

```bash
ssh miminashi@macbookair2015.lan '
  cat /proc/cmdline
  cat /sys/power/pm_print_times
  ls /etc/default/grub.bak.* 2>&1
  sudo /usr/local/sbin/check-suspend-resume.sh | tail -10
'
```

### Step 1. hang 末尾ログを開発側に保存 (レポート添付用)

開発側で:

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_s3_hang_pcie_aspm_off"
ATTACH_DIR="report/attachment/${REPORT_NAME}"
mkdir -p "$ATTACH_DIR"

ssh miminashi@macbookair2015.lan 'sudo journalctl -b -2 _TRANSPORT=kernel --no-pager | tail -50' \
  > "$ATTACH_DIR/hang_boot_9d3a4572_tail.txt"
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 _TRANSPORT=kernel --no-pager | tail -50' \
  > "$ATTACH_DIR/hang_boot_260710ee_tail.txt"
```

### Step 2. `/etc/default/grub` バックアップ

```bash
ssh miminashi@macbookair2015.lan '
  BAK=/etc/default/grub.bak.$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)
  sudo cp -av /etc/default/grub "$BAK"
  echo "backup: $BAK"
'
```

### Step 3. `pcie_aspm=off` を grub に追加

現状の `GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 no_console_suspend"` 末尾に `pcie_aspm=off` を追記:

```bash
ssh miminashi@macbookair2015.lan '
  sudo sed -i "s|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet i915.enable_dc=0 no_console_suspend\"|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet i915.enable_dc=0 no_console_suspend pcie_aspm=off\"|" /etc/default/grub
  grep "^GRUB_CMDLINE_LINUX_DEFAULT" /etc/default/grub
  sudo update-grub
'
```

### Step 4. `pm_print_times=1` を永続化 (systemd-tmpfiles)

```bash
ssh miminashi@macbookair2015.lan '
  sudo tee /etc/tmpfiles.d/pm_print_times.conf > /dev/null << "EOF"
# Persist /sys/power/pm_print_times = 1 across boots.
# S3 hang 時に最後の device suspend 完了行を kernel log に残すため。
# 詳細: https://www.kernel.org/doc/html/latest/admin-guide/pm/sleep-states.html
w /sys/power/pm_print_times - - - - 1
EOF
  sudo systemd-tmpfiles --create /etc/tmpfiles.d/pm_print_times.conf
  cat /sys/power/pm_print_times
'
```

期待値: `1` が返る。

### Step 5. reboot

```bash
ssh miminashi@macbookair2015.lan 'sudo systemctl reboot'
```

### Step 6. 反映確認

reboot 後 ssh 復帰したら:

```bash
ssh miminashi@macbookair2015.lan '
  echo "=== /proc/cmdline ==="
  cat /proc/cmdline
  echo "=== /sys/power/pm_print_times ==="
  cat /sys/power/pm_print_times
  echo "=== applespi loaded? ==="
  lsmod | grep -E "applespi" || echo "(applespi not loaded - OK)"
  echo "=== check-suspend-resume.sh ==="
  sudo /usr/local/sbin/check-suspend-resume.sh | tail -10
'
```

期待値:
- `/proc/cmdline` に `pcie_aspm=off` を含む (既存の `i915.enable_dc=0`, `no_console_suspend` も維持)
- `/sys/power/pm_print_times` → `1`
- applespi は非ロードのまま

### Step 7. 動作確認 (lid close → open 1 cycle)

ユーザに以下を依頼:

1. 蓋を閉じる
2. 30 秒以上待つ
3. 蓋を開ける
4. ssh で生存確認

成功したら kernel log に device-level の suspend timing が出ているはず:

```bash
ssh miminashi@macbookair2015.lan '
  sudo journalctl -b _TRANSPORT=kernel --no-pager | grep -E "calling|PM:" | tail -40
'
```

### Step 8. レポート作成

`report/${REPORT_NAME}.md` を作成。Step 1 で作成した `$ATTACH_DIR` に `plan.md` (本ファイルのコピー) と末尾ログを格納。レポートは CLAUDE.md のレポート作成ルールに準拠。

## 重要ファイル

- 実機 `/etc/default/grub` ・・・ `pcie_aspm=off` 追記対象
- 実機 `/etc/tmpfiles.d/pm_print_times.conf` ・・・ 新規作成 (`pm_print_times=1` 永続化)
- 実機 `/usr/local/sbin/check-suspend-resume.sh` ・・・ v2 (変更なし、観測継続)
- 開発側 `report/${REPORT_NAME}.md` ・・・ 新規作成
- 開発側 `report/attachment/${REPORT_NAME}/plan.md` ・・・ 本プランファイルのコピー

## 検証 (Verification)

### 設定の反映確認 (Step 6 で実施)

| チェック項目 | 期待値 |
|---|---|
| `/proc/cmdline` に `pcie_aspm=off` | あり |
| `/proc/cmdline` に `i915.enable_dc=0` `no_console_suspend` | 保持 |
| `/sys/power/pm_print_times` | `1` |
| `lsmod \| grep applespi` | 空 |
| `/etc/tmpfiles.d/pm_print_times.conf` | 存在 |

### lid close→open 1 cycle の動作確認 (Step 7 で実施)

- ssh 復帰すること
- `journalctl -b _TRANSPORT=kernel | grep "calling"` に device suspend timing が大量に出ていること (= pm_print_times=1 が働いている)
- `check-suspend-resume.sh` で当該 boot が `graceful` 判定 / `suspend == resume`

### 継続観測 (次回レポートに記載)

新観測期間を 2026-05-23 起点で設定:

| 観測期間 (基準: 2026-05-23) | 期待 hang 件数 (0.8/週) | 0 件で済む確率 |
|---|---:|---:|
| 1 週間 (〜 05-30) | 0.8 | ≈ 45% |
| 2 週間 (〜 06-06) | 1.6 | ≈ 20% |
| 4 週間 (〜 06-20) | 3.2 | ≈ 4% |

判定窓: 4 週間で 0 件なら効果ありと暫定判断、6 週間で 0 件なら恒久採用。
ただし今回は直近 35h で 2 件発生したケースもあるため、**1 週間以内に再発したら早期に次の手 (`acpi_osi=` 系) へ進む**。

### 観測コマンド

```bash
ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh | tail -15'
```

hang 再発時の pm_print_times=1 ログ確認:

```bash
ssh miminashi@macbookair2015.lan '
  prev=$(sudo journalctl --list-boots --no-pager | awk "\$1 ~ /^-?[0-9]+\$/" | tail -2 | head -1 | awk "{print \$1}")
  sudo journalctl -b "$prev" _TRANSPORT=kernel --no-pager | grep -E "calling|PM:" | tail -50
'
```

## ロールバック手順

`pcie_aspm=off` と `pm_print_times=1` を元に戻す場合:

```bash
ssh miminashi@macbookair2015.lan '
  # Step 2 で作成したバックアップから復元 (作業時の正確なファイル名は実機で確認)
  sudo cp -av /etc/default/grub.bak.YYYYMMDD_HHMMSS /etc/default/grub
  sudo update-grub
  sudo rm /etc/tmpfiles.d/pm_print_times.conf
  sudo systemctl reboot
'
```
