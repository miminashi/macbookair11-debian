# 案2 の前提検証 — 電源ボタン短押しは健全 s2idle を起こせる（成立）

- **実施日時**: 2026年06月03日 12:34 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-03_123439_pwrbtn_wake_premise_verification/plan.md)

## 前提・目的

[2026-06-01 レポート（案1: RTC ストレステスト）](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) の「次アクション 1」を実施。

MacBook Air 11" (Early 2015) / Debian 13 の s2idle resume hang は、案1 で **RTC 68/68 clean vs lid 1/5 hang** まで切り分けたが、残存被疑は次の2つで RTC テストでは原理的に分離できない:

- **(c) LID0 wake の間欠取りこぼし**（カーネルは s2idle freeze で生存しているが蓋開け割り込みが時々配送されず起きない）
- **(b′) lid 開閉/ディスプレイ復帰経路に固有の resume hang**

本筋の切り分けは **案2 = 次に lid hang した時に「強制電源長押しの前に電源ボタン短押し」を試す**（復帰すれば (c) 確定＝カーネル生存・wake のみ未配送、無反応なら (b′)）。だが案2 が意味を持つのは **電源ボタンが健全な s2idle を起こせる wake 源である場合に限る**。現状 `/proc/acpi/wakeup` で enabled は LID0 のみのため、**まず健全サイクルで電源ボタン短押しが復帰させるかを物理押下で確認**する（ssh では押下不可）のが本レポートの目的。

- **前提条件**: 操作対象は ssh 接続先の実機 `macbookair2015.lan`。スリープ投入・ログ取得は ssh、電源ボタン短押しはユーザの物理操作。
- **目的**: 「健全 s2idle で電源ボタン短押し → 復帰する」を確証し、案2 の実行可否を確定する。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル: `6.12.90+deb13-amd64`
- スリープ: `/sys/power/mem_sleep` = `[s2idle] deep`（cmdline `mem_sleep_default=s2idle`）
- wake 源（検証時点）:
  - `/proc/acpi/wakeup`: enabled は **LID0 のみ**（PWRB 項目はリストに無い）
  - **sysfs では電源ボタン `/sys/bus/acpi/devices/PNP0C0C:00/power/wakeup = enabled`**（Sleep Button PNP0C0E・LNXPWRBN も enabled）。s2idle の wake は IRQ 駆動で sysfs の `power/wakeup` が効く（`/proc/acpi/wakeup` は ACPI deep 用）
  - 他に sysfs で armed: `usb 1-5` / `thunderbolt` / `pci 0000:07:00.0` / `pnp 00:02` / `alarmtimer`（confound 候補）
- 電源: AC online=1、BAT0 Full 93%、lid open（全 trial で lid OPEN 固定）
- boot: 検証開始時 `db743a1d`（2026-05-31 21:41 起動、検証終了まで再起動なし）
- 検出スクリプト: `/usr/local/sbin/check-suspend-resume.sh`（残置）

## 設計（要点）

- **RTC を安全網に**: `rtcwake -m mem -s 180` で s2idle 進入。電源ボタンが何もしなくても 180s 後に必ず RTC 復帰するので強制電源断不要。
- **計測**: ssh は s2idle 中に切れるため、デタッチ常駐ユニット（`systemd-run`）が ENTER/EXIT+elapsed を sync 付きでディスクログに記録。復帰後に ssh で読む。
- **判定は elapsed**: 電源ボタンで起きれば elapsed ≈ 押下オフセット（≪180s）、起きなければ ≈ 181s（RTC）。
- **誤断定対策**: ① **無押下コントロール**で spurious wake が無いことを実測（早期復帰が出れば「電源ボタンが起こした」と読める前提を担保）、② **押下オフセットを試行ごとに変え**、resume が押下に追従することを確認（偶然/spurious 排除）。
- **安全策**: 検証中だけ `logind` を `HandlePowerKey=ignore` 化（押下が wake 後に userspace 再配送されても poweroff しないように）。検証後に撤去。

## 再現方法（実機での手順）

```bash
# 0. プリフライト (read-only): [s2idle] / AC online=1 / lid open / boot_id 記録
ssh miminashi@macbookair2015.lan 'cat /sys/power/mem_sleep; cat /sys/class/power_supply/ADP1/online; cat /proc/acpi/button/lid/*/state; cat /proc/sys/kernel/random/boot_id'

# 1. 安全策: logind 一時無害化
ssh miminashi@macbookair2015.lan 'sudo install -d /etc/systemd/logind.conf.d &&
 printf "[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=ignore\n" | sudo tee /etc/systemd/logind.conf.d/99-pwrbtn-test.conf &&
 sudo systemctl kill -s HUP systemd-logind'

# 2. テストスクリプト配備 /usr/local/sbin/pwrbtn-wake-test.sh
#    ENTER → rtcwake -m mem -s $SECS → EXIT(elapsed) を sync 付きでログ
#!/bin/bash
LOG=/var/log/pwrbtn-wake-test.log
SECS=${1:-180}; LABEL=${2:-trial}
echo "$(TZ=Asia/Tokyo date -Is) ENTER label=$LABEL secs=$SECS boot=$(cat /proc/sys/kernel/random/boot_id)" >> "$LOG"; sync
T0=$(date +%s); /usr/sbin/rtcwake -m mem -s "$SECS" >> "$LOG" 2>&1; rc=$?; T1=$(date +%s)
echo "$(TZ=Asia/Tokyo date -Is) EXIT label=$LABEL rc=$rc elapsed=$((T1-T0))s" >> "$LOG"; sync

# 3. Trial 0 無押下コントロール (何も押さない)
ssh miminashi@macbookair2015.lan 'sudo systemd-run --collect --unit=pwrbtn-wake-ctl /usr/local/sbin/pwrbtn-wake-test.sh 180 control'

# 4. Trial 1-3 押下 (画面が消えてから各オフセット後に電源ボタン短押し1回、長押し厳禁)
ssh miminashi@macbookair2015.lan 'sudo systemd-run --collect --unit=pwrbtn-wake-1 /usr/local/sbin/pwrbtn-wake-test.sh 180 press1'  # ~20s後押下
# Trial2 → unit pwrbtn-wake-2 / label press2 / ~40s後押下
# Trial3 → unit pwrbtn-wake-3 / label press3 / ~30s後押下

# 結果取得 + cross-check
ssh miminashi@macbookair2015.lan 'cat /var/log/pwrbtn-wake-test.log; cat /proc/sys/kernel/random/boot_id; sudo /usr/local/sbin/check-suspend-resume.sh | tail -2'

# 5. 後始末: logind drop-in 撤去
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/logind.conf.d/99-pwrbtn-test.conf && sudo systemctl kill -s HUP systemd-logind'
```

## 結果

`/var/log/pwrbtn-wake-test.log` 実測（boot `db743a1d` 連続・全 trial lid OPEN）:

| Trial | ENTER (JST) | EXIT (JST) | 押下オフセット | **elapsed** | rc | 判定 |
|---|---|---|---|---|---|---|
| control（無押下） | 11:41:06 | 11:44:07 | — | **181s** | 0 | RTC 復帰（spurious wake 無し） |
| press1 | 12:12:46 | 12:13:11 | ~20s | **25s** | 0 | ✓ 電源ボタンで復帰 |
| press2（押し逃し・無効） | 12:13:31 | 12:16:32 | —（押し忘れ） | **181s** | 0 | RTC 復帰（無押下=RTC を再確認） |
| press2b（再試） | 12:30:54 | 12:31:56 | ~40s | **62s** | 0 | ✓ 電源ボタンで復帰 |
| press3 | 12:33:05 | 12:33:39 | ~30s | **34s** | 0 | ✓ 電源ボタンで復帰 |

- **無押下 2 回（control / press2 押し逃し）= 共に 181s（RTC）**、**有効押下 3 回 = 25s / 34s / 62s（≪181s）**。明快な二分。
- **elapsed が押下オフセットに単調追従**（押下 20s→25s、30s→34s、40s→62s。オフセットはユーザの手動カウントのため線形ではないが、待ち時間が長いほど elapsed も長い＝25 < 34 < 62 ⇔ 20 < 30 < 40）。早期復帰が偶然・spurious ではなく**押下に因果**することを示す。
- 全 trial で **boot_id `db743a1d` 不変**、検出スクリプト cross-check は current boot **82/82 diff=0 graceful**（再起動・hang・強制電源断ゼロ）。

## 結論

**前提検証 成立: 電源ボタン短押しは健全な s2idle を確実に起こす wake 源である（有効押下 3/3、間欠取りこぼし観測されず）。** `/proc/acpi/wakeup` に PWRB が載っていなくても、sysfs `PNP0C0C:00/power/wakeup=enabled` の電源ボタンは s2idle を IRQ 経由で起こせることを実証した。

→ **案2 が実行可能になった。** 次に lid hang が発生した際、**強制電源長押しの前に電源ボタン短押し**を試すことで:

- **復帰すれば (c) 確定**（カーネルは s2idle freeze で生存・LID0 wake のみ未配送）
- **無反応なら (b′)**（wake 源を変えても固着＝lid/display 固有の resume hang）

として残存被疑 (c) vs (b′) を決着できる。本検証により「電源ボタン未検証のまま無反応→(b′) と推論する」リスクは解消された。

### 限界・注意

- 本検証は **健全 s2idle** での電源ボタン wake 成立を示すのみ。hang 時にカーネルが本当に生存しているか（=(c)）の確証は、実際の lid hang 時に電源ボタン短押しが復帰させるか（案2 本体）で得る。
- 健全ケースで 3/3 成功＝間欠取りこぼしは観測されなかったが、これは「電源ボタン wake は常に確実」を保証するものではない（サンプル 3）。案2 本番で無反応だった場合、(b′) と「電源ボタン wake の取りこぼし」を更に切り分ける余地は残る。

## テスト資材（残置）

- 実機スクリプト: `/usr/local/sbin/pwrbtn-wake-test.sh`（第1引数=RTC 秒, 第2=label）
- ログ: `/var/log/pwrbtn-wake-test.log`
- logind 無害化 drop-in `99-pwrbtn-test.conf` は **撤去済み**（`HandlePowerKey` はデフォルト `poweroff` に復帰）。sysfs wake 源は未変更。

## 次アクション

1. **案2 本体（別フェーズ）**: 次に lid hang した時、強制電源長押しの前に電源ボタン短押し → 復帰=(c)確定 / 無反応=(b′)。ユーザへ運用手順として周知。
2. **代替（よりクリーン）**: lid を物理的に閉じたまま RTC で起こす試験（lid-closed 物理状態を保持し wake 源だけ差替え）でも (c)/(b′) を分離可能（前回レポート次アクション 2）。
3. **(b′) を device レベルで詰めるなら** `pm_debug_messages=1` 有効化で suspend/resume timing を journal に残す。
