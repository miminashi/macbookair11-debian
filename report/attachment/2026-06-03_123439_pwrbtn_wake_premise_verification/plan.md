# 案2 の前提検証 — 電源ボタンが健全 s2idle を起こせるかの物理確認

## Context（なぜこれをやるか）

[2026-06-01 レポート](/home/miminashi/projects/macbookair11-debian/report/2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) の「次アクション 1」。

MacBook Air 11" (Early 2015) / Debian 13 の s2idle resume hang は、案1（RTC ストレステスト）で **RTC 68/68 clean vs lid 1/5 hang** まで切り分けたが、残存被疑は **(c) LID0 wake の間欠取りこぼし** と **(b′) lid 開閉/ディスプレイ復帰経路固有の resume hang** の2つで、RTC テストでは原理的に分離できない。

本筋の切り分けは **案2 = 次に lid hang した時に「強制電源長押しの前に電源ボタン短押し」を試す**（復帰すれば (c) 確定＝カーネル生存・wake のみ未配送、無反応なら (b′)）。だが案2 が意味を持つのは **電源ボタンが健全な s2idle を起こせる wake 源である場合に限る**。現状 `/proc/acpi/wakeup` で enabled は LID0 のみのため、**まず健全サイクルで電源ボタン短押しが復帰させるかを物理押下で確認**する（ssh 不可）。本プランはこの前提検証だけを行う（lid hang を誘発する案2 本体は別フェーズ）。

期待される成果: 「健全 s2idle で電源ボタン短押し → 復帰する」を確証できれば、案2 が実行可能になり、(c) vs (b′) の決着手段が手に入る。

## 実機の現状（read-only 調査済み・2026-06-03）

- `mem_sleep` = `[s2idle]`、cmdline に `mem_sleep_default=s2idle`。AC online=1、BAT0 Full 93%、lid open。
- `/proc/acpi/wakeup`: enabled は **LID0 のみ**（PWRB/PNP0C0C 項目はそもそもリストに無い）。
- **ただし sysfs では電源ボタン `/sys/bus/acpi/devices/PNP0C0C:00/power/wakeup = enabled`**（Sleep Button PNP0C0E・LNXPWRBN も enabled）。s2idle の wake は IRQ 駆動で **sysfs の `power/wakeup` が効く**（`/proc/acpi/wakeup` は ACPI deep 用）→ 電源ボタンで起きる見込みは高いが、wake 配送こそが論点なので物理確認が要る。
- **要注意（confound）**: sysfs で他にも armed のまま: `usb 1-5` / `thunderbolt 0-0,domain0` / `pci 0000:07:00.0` / `pnp 00:02` / `alarmtimer`。これらが s2idle で spurious wake を起こすと「早期復帰＝電源ボタン」と誤断定し得る。過去に ~84s spurious wakeup 問題あり（udev で /proc/acpi/wakeup を抑止したが、s2idle IRQ wake には効いていない可能性）。→ コントロール試行で実測対処する（下記）。
  - 補強材料: 案1 第2バッチ（6×1800s）で「全 1800s 完走・早期 wake なし」を観測済み＝現構成で spurious wake は実質出ていない。コントロールは安価な再確認。
- `logind.conf` は全デフォルト（`HandlePowerKey=poweroff` が効く）。GNOME 稼働中（gnome-shell）。
- `check-suspend-resume.sh`（残置）current boot `db743a1d` = 77/77 graceful、新規 hang なし。

## 設計の骨子

1. **RTC を安全網に**: `rtcwake -m mem -s 180` で s2idle 進入。電源ボタンが何もしなくても **180s 後に必ず RTC で復帰**するので machine を取りこぼさない（強制電源断は不要）。
2. **ssh セッションは s2idle 中に切れる** → 計測はデタッチ常駐ユニットが **ディスクログに ENTER/EXIT+elapsed を sync 付きで記録**。復帰後に ssh で読むだけ。
3. **lid は OPEN 固定**で suspend（LID0 を wake 源から外し、電源ボタンを能動 wake 源として切り出す。USB/TB/PCI/PNP は armed だが受動的＝静かなテスト中はイベントが起きないので実質発火しない。それでも念のため Trial0 で排除確認する）。
4. **判定は elapsed**: 電源ボタンで起きれば elapsed ≈ 押下オフセット（≪180s）、起きなければ elapsed ≈ 180s（RTC）。
5. **誤断定対策（必須）**:
   - **Trial 0 = 無押下コントロール**: `-s 180` で何も押さず、丸 180s 寝るか確認。早期復帰すれば spurious wake が live → bare「早期復帰」は無意味。その場合は他 sysfs wake 源を一時 disable して再コントロール。
   - **押下オフセットを試行ごとに変える**（20s / 40s / 30s）。resume が毎回押下に追従すれば電源ボタンと確定。逆に毎回 ~固定秒（例 ~84s）なら spurious。

## 手順（実機・ユーザ物理同席が必須）

> 実行はプランモードを抜けてから。各 trial は「triggerは ssh、押下はユーザ、結果読取は ssh」の3手。ユーザが実機の前にいて、合図で**短押し1回**できる状態で行う。

### 0. プリフライト（read-only）
```bash
ssh miminashi@macbookair2015.lan '
 cat /sys/power/mem_sleep; cat /sys/class/power_supply/ADP1/online;
 cat /proc/acpi/button/lid/*/state; cat /proc/sys/kernel/random/boot_id;
 systemctl is-active "pwrbtn-wake-*" 2>/dev/null || echo no-unit-running'
```
→ `[s2idle]` / online=1 / lid open を確認、boot_id を記録。

### 1. 安全策（logind 一時無害化・任意だが既定で適用）
電源ボタン押下が wake 後に userspace へ再配送された場合の poweroff を防ぐ。GNOME が logind を上書きする可能性があり完全ではないが安価・可逆。
```bash
ssh miminashi@macbookair2015.lan 'sudo install -d /etc/systemd/logind.conf.d &&
 printf "[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=ignore\n" |
   sudo tee /etc/systemd/logind.conf.d/99-pwrbtn-test.conf &&
 sudo systemctl kill -s HUP systemd-logind'
```
（注: poweroff してしまっても boot_id 変化＝「電源ボタンは wake 源である」証拠にはなる。下記判定表参照）

### 2. テストスクリプト配備（残置可・rtcwake-stress.sh と同パターン）
`/usr/local/sbin/pwrbtn-wake-test.sh`:
```bash
#!/bin/bash
LOG=/var/log/pwrbtn-wake-test.log
SECS=${1:-180}; LABEL=${2:-trial}
echo "$(TZ=Asia/Tokyo date -Is) ENTER label=$LABEL secs=$SECS boot=$(cat /proc/sys/kernel/random/boot_id)" >> "$LOG"; sync
T0=$(date +%s); /usr/sbin/rtcwake -m mem -s "$SECS" >> "$LOG" 2>&1; rc=$?; T1=$(date +%s)
echo "$(TZ=Asia/Tokyo date -Is) EXIT label=$LABEL rc=$rc elapsed=$((T1-T0))s" >> "$LOG"; sync
```

### 3. Trial 0 — 無押下コントロール
```bash
ssh miminashi@macbookair2015.lan 'sudo systemd-run --collect --unit=pwrbtn-wake-ctl \
  /usr/local/sbin/pwrbtn-wake-test.sh 180 control'
# ★何も押さない。~190s 待ってから:
ssh miminashi@macbookair2015.lan 'tail -n 4 /var/log/pwrbtn-wake-test.log; cat /proc/sys/kernel/random/boot_id'
```
- elapsed ≈ 180s → spurious wake 無し、判別器は健全。**Trial 1 へ**。
- elapsed ≪ 180s（早期復帰）→ spurious wake live。**他 sysfs wake 源を一時 disable**して再コントロール:
  ```bash
  ssh miminashi@macbookair2015.lan 'for n in /sys/bus/usb/devices/1-5 /sys/bus/thunderbolt/devices/0-0 \
     /sys/bus/pci/devices/0000:07:00.0 /sys/bus/pnp/devices/00:02; do
     echo disabled | sudo tee $n/power/wakeup; done'
  ```
  （検証後に `echo enabled` で戻す）

### 4. Trial 1–3 — 電源ボタン短押し（オフセット可変）
各 trial で（`N` は 1/2/3 に置換し、ユニット名・label を一意にする）:
```bash
ssh miminashi@macbookair2015.lan 'sudo systemd-run --collect --unit=pwrbtn-wake-1 \
  /usr/local/sbin/pwrbtn-wake-test.sh 180 press1'   # Trial2→pwrbtn-wake-2/press2, Trial3→-3/press3
```
- **合図**: ユーザは画面が消えて s2idle に入ったのを確認し、**Trial1=約20s後 / Trial2=約40s後 / Trial3=約30s後** に **電源ボタンを短く1回**押す（長押し厳禁＝firmware 強制断で無意味）。
- 早期に起きなければ **180s の RTC 復帰を待つ**（強制電源断はしない＝boot_id を汚さない）。
- 各 trial 後:
  ```bash
  ssh miminashi@macbookair2015.lan 'tail -n 4 /var/log/pwrbtn-wake-test.log;
    cat /proc/sys/kernel/random/boot_id; sudo /usr/local/sbin/check-suspend-resume.sh | tail -2'
  ```
  boot_id 不変・graceful を確認。

### 5. 後始末
```bash
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/logind.conf.d/99-pwrbtn-test.conf &&
  sudo systemctl kill -s HUP systemd-logind'
# Trial0 で他 wake 源を disable した場合は enabled に戻す
```

## 判定表

| Trial1–3 の resume | boot_id | 結論 |
|---|---|---|
| 早期・**押下オフセットに追従**（20/40/30s に対応） | 不変 | **電源ボタンが健全 s2idle を起こす → 案2 成立 ✓** |
| machine が **poweroff/再起動** | 変化 | 押下が userspace に届いた＝**電源ボタンは wake 源である**（案2 成立。本番は `HandlePowerKey=ignore` 必須）。※今回 ignore を適用するので発生時は GNOME か firmware 経路 |
| 早期だが **押下と無関係に ~固定秒** | 不変 | spurious wake（電源ボタンではない）→ Trial0 の対処後に再試 |
| **180s（RTC）まで起きない** | 不変 | **電源ボタンでは起きない → 案2 不成立**。別 wake 源（USB/キー wake 一時有効化など）が必要。※押下が 170s 等と遅すぎて 180s に見えた疑いがあれば、押下タイミングを早めて再試 |

3 trial は intermittency 監視のため（押下 wake 配送が間欠的に取りこぼれないかも見る）。健全ケースなので結果は一貫するはず。Trial1 が「早期・押下追従・boot_id 不変」で明快に成功し 3 trial とも一貫すれば前提検証は成立。

## 検証（この前提検証自体の妥当性確認）

- Trial 0 が丸 180s 寝る ＝ 判別器（早期 wake = 押下）の前提が成立していることの確認。
- elapsed が3 trial で押下オフセットに追従 ＝ 偶然/spurious の排除。
- 全 trial で boot_id 不変・`check-suspend-resume.sh` graceful ＝ 固着も強制断も無く健全。

## 結果反映

完了後、[2026-06-01 レポート](/home/miminashi/projects/macbookair11-debian/report/2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) の次アクション 1 に対する結果として **新規レポート**を `report/` に作成（CLAUDE.md のルール準拠・本プランを attachment に添付）。メモ `s2idle-observation-phase` の「次フェーズ」記述を案2 成立/不成立で更新。

## 次アクション（結果別）

- **案2 成立** → 別フェーズで案2 本体（次の lid hang 時に電源ボタン短押し）を待ち受け。復帰=(c)確定 / 無反応=(b′)。
- **案2 不成立** → レポートの「次アクション 2」（lid を物理的に閉じたまま RTC wake させる代替試験）へ。
