# バッテリ連動ハイバネ不発の原因特定と修正レポート（ACPI _BTP 無効化で RTC ポーリング経路へ強制）

- **実施日時**: 2026年6月15日 23:46 (JST)

## 添付ファイル

- [調査・対策プラン](attachment/2026-06-15_234635_fix_battery_hibernate_btp/plan.md)

## 前提・目的

- **背景**: ユーザから「ハイバネーションに失敗している気がする」と報告。過去レポート（[2026-06-08 低バッテリ時ハイバネ対応](2026-06-08_035056_low_battery_hibernate.md)）で suspend-then-hibernate（STH）を設定済みだったが、その後も枯渇死していた疑い。
- **ユーザの最終ゴール**: **「蓋を閉じたら s2idle で sleep し、蓋を閉じたままバッテリが尽きそうになったら（バッテリ駆動の判断で）自動的にハイバネする」** という STH のバッテリ連動動作を成立させること。一時的な実用性低下は許容。
- **目的**: バッテリ連動の自動ハイバネが発火しない原因を特定し、本機で成立させる。
- **前提条件**: 操作対象は別ホストの実機 MacBook Air 11" (Early 2015) `macbookair2015.lan`、ssh 経由で診断・修正。スリープモードは s2idle、蓋閉じ（電池）で STH に入る運用。ハイバネ（S4）の**実行**自体は前回 Step 0a/0b で本実機実証済み。

## 環境情報

- 機種: MacBook Air 11" (Early 2015), `macbookair2015.lan`
- OS: Debian 13 (trixie), kernel `6.12.90+deb13-amd64`
- systemd: 257 (257.9-1~deb13u1)
- スリープ: `mem_sleep = [s2idle] deep`（s2idle 運用）、`/sys/power/disk = [platform]`
- スワップ/ハイバネ配線: swap `/dev/sda3` UUID `65051de6…` = RESUME 一致、initramfs resume hook あり
- バッテリ: charge ベース（`charge_now/charge_full=4747000µAh` あり、`energy_*`/`power_now` は NA）、capacity 表示 92〜93%
- **DMI System Information Wake-up Type: `Power Switch`**（後述の原因の核心）

## 調査と原因（確証）

### 症状

`journalctl` 解析より、boot 0 起動時に `PM: Image not found (-22)` ＝ **ハイバネイメージが一度も書かれていない**。最終サイクル（2026-06-15 01:59:23 s2idle 突入）は **コールドブート（残≒0%）まで放電＝必ず低残量域を横切った**のに、ハイバネが実行されていなかった。前回設定した STH が機能しておらず、s2idle のまま放電死していた。

### 根本原因（systemd 257 の逐語ソース `src/sleep/sleep.c` `execute_s2h()` で確定）

`HibernateDelaySec` 未設定時、systemd は次のように経路を選ぶ（要点を簡略化。完全な逐語版は systemd v257 `src/sleep/sleep.c`）:

```c
// HibernateDelaySec 未設定時:
r = check_wakeup_type();                   // 本機=Power Switch → 0 (エラー時以外、経路選択には使われない)
if (r >= 0)
    r = battery_trip_point_alarm_exists();  // ← r はこちらで上書き。alarm 存在(300000>0)なら true
if (r > 0) {                                // ＝ _BTP alarm が存在する → ハード経路
    log_debug("Attempting to suspend...");
    execute(SLEEP_SUSPEND);                 // 素の suspend。RTC は張らず _BTP ハード割込待ち
    r = check_wakeup_type();
    if (r == 0) return 0;                   // 本機は APM Timer 型でないため常にここで return(ハイバネせず)
} else {
    custom_timer_suspend();                 // RTC ポーリング推定（本来こちらに来るべき）
}
```

経路選択は `battery_trip_point_alarm_exists()`（`/sys/class/power_supply/BAT0/alarm` の存在）で決まる。本機は alarm が存在する（値 300000）ため **`r>0` → ハードウェア `_BTP` 経路**を選ぶ。

ところが本機の **DMI Wake-up Type は `Power Switch`（byte=6）** であり、`check_wakeup_type()` は**常に 0** を返す。`check_wakeup_type()` が読むのは「このサイクルの起床要因」ではなく **SMBIOS Type-1 の機種固定値**なので、起床要因に関わらず永久に 0。したがって:

- **ハード `_BTP` 経路はこの機種では構造上ハイバネに到達できない**: ① 何にも起こされず s2idle に居座って放電死、または ② 仮に起床しても直後の `check_wakeup_type()==0` ゲートで `return 0`（ハイバネせず）。

これが systemd と Apple firmware の不整合: **systemd は「alarm が存在する＝ハード _BTP で起こされる」と仮定するが、`Power Switch` 機種では post-wake の APM-Timer ゲートを満たせず、結果としてハイバネに決して至らない。**

`battery_trip_point_alarm_exists()` の定義（`src/sleep/battery-capacity.c`）も逐語確認:

```c
r = safe_atoi(alarm_attr, &has_alarm);
if (has_alarm <= 0)
        return false;      // alarm の値が 0 なら false
...
return has_battery;
```

→ **`alarm` に `0` を書けば `battery_trip_point_alarm_exists()` が false を返し、`else` 側の `custom_timer_suspend()`（RTC ポーリング推定）経路に落ちる。**

### デバッグログによる裏付け

`SYSTEMD_LOG_LEVEL=debug` を一時投入して STH を電池で発火させたところ、修正前は `Attempting to suspend...` のみで**推定・RTC アラーム・ハイバネスケジューリングのログが皆無**＝ハード経路で素の suspend のまま放置、を直接観測した。

## 対応内容（適用済み・恒久）

### 1. ACPI `_BTP` トリップ点を無効化（`alarm=0`）→ RTC ポーリング経路へ強制

udev rule `/etc/udev/rules.d/99-disable-battery-trip-point.rules`:

```
ACTION=="add|change", SUBSYSTEM=="power_supply", KERNEL=="BAT0", ATTR{alarm}="0"
```

- `add`（起動）・`change`（AC 抜き差し・状態変化）の両方で `alarm=0` を再適用。手動で 300000 へ再アームしても change/add 発火で 0 に戻ることを検証済み。

### 2. `SuspendEstimationSec=30min`（初回サイクルの上限）

`/etc/systemd/sleep.conf.d/20-battery-hibernate.conf`:

```ini
[Sleep]
SuspendEstimationSec=30min
```

- 放電率未学習の初回サイクルの上限間隔。本機の s2idle 放電は**約 29%/時と速い**ため、既定 60min を短縮して初回オーバーシュートを抑制。学習後は実測レートで自動スケジュールされる（学習値は `/var/lib/systemd/sleep/battery_discharge_percentage_rate_per_hour` に永続保存される）。

### 3. logind は変更不要

`HandleLidSwitch=suspend-then-hibernate` / `HandleLidSwitchExternalPower=suspend` は前回設定のまま維持。

## 検証結果

`alarm=0` 投入後、テスト用に `SuspendEstimationSec=2min` を設定して STH を電池で発火させ、経路切替と RTC ポーリングの動作を実機ログで実証した:

```
Found battery with capacity above threshold (93% > 5%).
Set timerfd wake alarm for 2min                  ← RTC ポーリング経路へ切替成立
Performing sleep operation 'suspend'...            → s2idle
（2分後）System returned ...                        ← timerfd(RTC) で s2idle から自動起床（hang なし）
BAT0: 1% was discharged in 2min. Estimating discharge rate...
Estimated discharge rate 29% per hour successfully saved   ← 放電率を学習・永続保存
Set timerfd wake alarm for 2h 40min 20s            ← 学習値(29%/時)からマージンを取って次回起床を予約(この回は約15%地点で起床する計算。後述の段階収束)
```

実証できたこと:

- `alarm=0` で **`custom_timer_suspend()`（RTC ポーリング推定）経路へ切替成立**（壊れたハード `_BTP` 経路を回避）。
- **timerfd（RTC）で s2idle から自動起床が機能**（resume hang も発生せず）。
- **放電率推定が機能**（実測 29%/時）。
- **5% 到達を逆算したスケジューリングが機能**。

補足の重要事実:

- **スケジューリングは一発で 5% を狙わず、マージンを取りつつ段階収束する**。92%・29%/時の状態で systemd がセットした次回起床は「2h40m 後」＝逆算すると**約 15% 地点での起床**であり、いきなり 5% ではない。各起床で放電率を再測定しながら 5% へ収束する設計のため、単発オーバーシュートのリスクは低い（安全マージン上の利点）。
- **修正前は `/var/lib/systemd/sleep/` が存在しなかった**＝放電率の学習サイクルを**一度も完了できていなかった**。これはハード `_BTP` 経路で素通りし続けていたこと（推定ロジックに到達していなかったこと）の傍証。修正後は学習値（`… 29`）が保存されるようになった。

ハイバネ発火条件は `battery_is_discharging_and_low()`（`src/shared/battery-util.c`、`BATTERY_LOW_CAPACITY_LEVEL = 5`）＝ **AC 非接続かつ capacity ≤ 5%**。すなわち「s2idle で sleep → RTC ポーリングで放電を監視 → 5% でハイバネ」というゴールの全機構が揃った。なお S4 実行→復帰（boot_id 不変）自体は前回 Step 0b（`HibernateDelaySec=20s` も同じ `custom_timer_suspend()` 経路）で本実機実証済み。

## 残課題・最終確認（ユーザ合意により実使用で確認）

- **実際に ≤5% まで放電してハイバネが発火する瞬間**のみ未観測（機構は上記で実証済み）。ユーザ合意のもと、**実使用での自然な低残量時に確認**する方針とした。確認時は以下のログを参照:

```bash
ssh miminashi@macbookair2015.lan 'journalctl -b -1 --no-pager | grep -iE "capacity below threshold|PM: hibernation: Creating image|hibernation exit"'
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail'   # 復帰で boot_id 不変＝成功
```

- 期待ログ: `Found battery with capacity below threshold (5% <= 5%)`（INFO）→ `PM: hibernation: Creating image`（kernel）→ 電源ボタンで boot_id 不変 resume。
- **留意（マージン）**: s2idle 放電が 29%/時と速く、ハイバネ閾値 5% はコンパイル時定数（変更不可）。5% から書込完了までの余裕は約 10 分程度の想定。古い電池の電圧サグで足りない懸念が残る場合は、最終手段として固定 `HibernateDelaySec` タイマー（プラン Step 3 floor、バッテリ連動ではないが確実）への切替余地がある。
  - 放電率 29%/時の含意として、**満充電でも s2idle のみで約 3.4 時間で枯渇**する計算になる。これは過去に観測された「満充電から数時間で死ぬ」挙動と整合し、s2idle の電力消費が本機では大きいことを示す（修正後はその枯渇前に 5% でハイバネへ移行する）。
- s2idle resume hang は別トラックの既知リスク（[s2idle hang 調査](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)）。今回の RTC 自動起床テストでは再発しなかったが、根治ではない。

## 再現方法（診断・修正手順）

```bash
# 1) 経路選択の確定: DMI wakeup type と alarm 値
ssh miminashi@macbookair2015.lan 'sudo dmidecode -t system | grep -i wake-up'           # Power Switch を確認
ssh miminashi@macbookair2015.lan 'cat /sys/class/power_supply/BAT0/alarm'                 # 300000(存在)→ハード経路選択

# 2) デバッグログで挙動観測（一時）
ssh miminashi@macbookair2015.lan 'sudo mkdir -p /etc/systemd/system/systemd-suspend-then-hibernate.service.d && \
  printf "[Service]\nEnvironment=SYSTEMD_LOG_LEVEL=debug\n" | sudo tee /etc/systemd/system/systemd-suspend-then-hibernate.service.d/99-debug.conf && \
  sudo systemctl daemon-reload'
# → 電池で蓋閉じ→数分→蓋開け、の後:
ssh miminashi@macbookair2015.lan 'journalctl -u systemd-suspend-then-hibernate.service -b | grep -iE "Attempting to suspend|Set timerfd|estimate|discharge"'

# 3) 修正適用: _BTP 無効化(alarm=0) を udev で永続化
ssh miminashi@macbookair2015.lan 'printf "ACTION==\"add|change\", SUBSYSTEM==\"power_supply\", KERNEL==\"BAT0\", ATTR{alarm}=\"0\"\n" | \
  sudo tee /etc/udev/rules.d/99-disable-battery-trip-point.rules && \
  sudo udevadm control --reload-rules && \
  sudo udevadm trigger --subsystem-match=power_supply --action=change'
ssh miminashi@macbookair2015.lan 'cat /sys/class/power_supply/BAT0/alarm'                 # 0 を確認

# 4) SuspendEstimationSec=30min
ssh miminashi@macbookair2015.lan 'printf "[Sleep]\nSuspendEstimationSec=30min\n" | \
  sudo tee /etc/systemd/sleep.conf.d/20-battery-hibernate.conf'

# 5) クリーンアップ(debug 撤去)
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/system/systemd-suspend-then-hibernate.service.d/99-debug.conf && sudo systemctl daemon-reload'
```

## ロールバック

```bash
# _BTP 無効化を解除（systemd は再びハード経路を選ぶ＝枯渇死に戻るので注意）
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/udev/rules.d/99-disable-battery-trip-point.rules && \
  sudo udevadm control --reload-rules && \
  echo 300000 | sudo tee /sys/class/power_supply/BAT0/alarm'
# SuspendEstimationSec を既定へ
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/sleep.conf.d/20-battery-hibernate.conf'
```
