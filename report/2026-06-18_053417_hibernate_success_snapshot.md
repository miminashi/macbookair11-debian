# バッテリ連動ハイバネ成功の実証と現行設定スナップショット

- **実施日時**: 2026年6月18日 05:34 (JST)

## 添付ファイル

- [調査・レポート作成プラン](attachment/2026-06-18_053417_hibernate_success_snapshot/plan.md)

## 前提・目的

- **背景**: 前回レポート [2026-06-15 _BTP 無効化修正](2026-06-15_234635_fix_battery_hibernate_btp.md) で、`/sys/class/power_supply/BAT0/alarm=0`（ACPI `_BTP` トリップ点を無効化）により `systemd-suspend-then-hibernate` を**壊れたハードウェア `_BTP` 経路ではなく `custom_timer_suspend()`（RTC ポーリング推定）経路へ強制**する恒久修正を適用した。RTC 自動起床・放電率推定・5% 逆算スケジュールは実機ログで実証済みだったが、**実使用で実際に capacity ≤5% に達してハイバネが発火する瞬間だけが未観測**で、ユーザ合意のもと「自然な低残量時に確認する」という残課題が残っていた。
- **目的**: その残課題（実発火）が成立したことを実機ログで実証し、あわせて**現時点の電源管理まわりの全設定をスナップショットとして保存**する（将来の再構築・回帰判定の基準点）。
- **前提条件**: 操作対象は別ホストの実機 MacBook Air 11" (Early 2015) `macbookair2015.lan`、ssh 経由で読み取り専用の診断のみ実施（本セッションでは設定変更なし）。スリープモードは s2idle、蓋閉じ（電池）で suspend-then-hibernate に入る運用。

## 環境情報

| 項目 | 値 |
|---|---|
| 機種 | MacBook Air 11" (Early 2015), `macbookair2015.lan` |
| OS | Debian 13 (trixie) |
| kernel | `6.12.90+deb13-amd64` |
| systemd | 257 (257.9-1~deb13u1) |
| RAM | 3916004 kB（約 3.7 GiB） |
| swap | `/dev/sda3` 3.7G（`swapon` PRIO -2） |
| バッテリ | charge ベース（`charge_full=4747000µAh`、`energy_*`/`power_now` は NA）。本調査時点 `status=Charging` `capacity=55%`、AC online=1 |

## 成功の実証（実機ログ）

`journalctl -b 0`（boot 0 = 2026-06-15 22:08 起動、現在も継続 / `up 2 days`）に、**実使用での ≤5% ハイバネ発火と S4 復帰完走**が記録されている。

```
6月 17 23:09:34 systemd-logind: Suspending, then hibernating...
6月 17 23:09:35 systemd-sleep: BAT0: Found battery with capacity below threshold (3% <= 5%).
6月 17 23:09:35 systemd-sleep: Performing sleep operation 'hibernate'...
6月 17 23:09:35 kernel:       PM: hibernation: hibernation entry
   ── 23:09:36〜02:45:43 はジャーナルが完全に空（"No entries"）＝ S4 で電源断 ──
6月 18 02:45:44 kernel:       PM: hibernation: Creating image:        ← flush アーティファクト（後述）
6月 18 02:45:44 kernel:       PM: hibernation: hibernation exit
6月 18 02:45:44 systemd-sleep: System returned from sleep operation 'suspend-then-hibernate'.
```

実証できたこと:

- **電池 3%（≤5%）で `hibernate` が発火**し、S4 イメージを書き出した。これは前回までの修正（`alarm=0` → RTC ポーリング推定経路）が**実使用の自然な低残量で正しく終端まで動いた**ことを示す。
- **コールドブートではなく S4 resume 完走**: 現在の boot_id `86ba1c2d-b717-4113-b09f-8c0e238c7817` は `journalctl --list-boots` の **boot 0 と一致**。すなわちハイバネ→電源投入→復帰で boot_id が変わっていない（＝枯渇死による電源喪失ではなく、正常な S4 サスペンド／レジューム）。
- **修正適用（6/15 22:08）以降コールドブート 0 回**（枯渇死ゼロ）。

### タイムスタンプの正しい解釈（誤読防止）

wall-clock だけ見ると `hibernation entry` が 6/17 23:09、`Creating image`/`hibernation exit` が 6/18 02:45 で **約 3.5h の隔たり**があり、あたかも「イメージ作成に 3.5h かかった」ように見えるが、これは誤読である。monotonic タイムスタンプで見ると実態が分かる:

```
[10069.680036] PM: hibernation: hibernation entry
[10075.180706] PM: hibernation: Allocated 330877 pages for snapshot
[10075.180706] PM: hibernation: Allocated 1323508 kbytes in 2.56 seconds (516.99 MB/s)
[10075.414567] PM: hibernation: Creating image:
[10075.414601] PM: hibernation: Need to copy 327979 pages
[10075.699788] Restarting tasks ... done.
[10075.700545] PM: hibernation: hibernation exit
```

`hibernation entry [10069.68]` から `hibernation exit [10075.70]` まで **monotonic で約 6 秒**しかない。monotonic クロックは電源断中は停止するため、実際の流れは:

1. 6/17 23:09:35 に 3% でハイバネ開始 → **約 6 秒でイメージ作成完了**（327979 pages コピー、`Allocated 1323508 kbytes`＝約 1.26 GiB、書込 `516.99 MB/s`）→ 電源断。
2. **23:09:36〜02:45:43 はジャーナルが 1 行も無い ＝ 約 3h36m 完全に S4 電源断**（正常な S4 であり枯渇死ではない）。
3. 6/18 02:45:44 に電源ボタンで resume、kernel がイメージを復元。

→ wall-clock で `Creating image`/`hibernation exit` が 02:45:44 に並ぶのは、**電源断中に kernel ring buffer へ溜まった行が resume 時にまとめて journald へ flush された際に付与されたタイムスタンプ**であり、イメージ作成に要した時間ではない。3.5h は S4 で電源断していた時間である。

### 本番（debug オフ）での RTC ポーリング再サスペンドの実動作

6/15 のテスト時は `SYSTEMD_LOG_LEVEL=debug` 窓で `Set timerfd wake alarm for …` を直接観測したが、debug 撤去後の本番でも、**RTC ポーリングが周期起床→再サスペンドを繰り返した時刻そのものは INFO ログに残っており可視**である。3% ハイバネに至る前の電池 STH 運用では、`systemd-sleep[59664]` という 1 プロセスが内部で **3 レグ**を回している:

```
19:16:36 'suspend' → 19:32:07 返り（約15.5分）→ 再 'suspend'
                   → 19:47:39 返り（約15.5分）→ 再 'suspend'
                   → 22:08:33 返り（約2h21m）
（lid 開閉で新たな STH） 22:08:57 'suspend' → 23:09:07 返り（約60分）
23:09:34 STH → capacity 3% → 'hibernate'
```

各 `Performing sleep operation 'suspend'` → `System returned …` の対が、`custom_timer_suspend()` が張った timerfd（RTC）で s2idle から自動起床し、放電を再評価して再サスペンド／ハイバネを判断するループの 1 回転にあたる。**6/15 の debug 観測とは独立に、本番で RTC ポーリングループが実際に回り続けた証跡**であり（timerfd の設定値自体は debug レベルで不可視だが、起床・再サスペンドの時刻は INFO で残る）、いずれの自動起床でも s2idle resume hang は再発していない。

### バッテリ STH 運用のエンデュランス・エンベロープ

- STH（電池）運用は **6/17 19:16 頃に開始**（直前 06:30→19:16 は plain `suspend`＝AC 接続時の蓋閉じ）、**3% ハイバネが 23:09** ＝ **約 3h53m の電池 STH 運用で 3% に到達**した。
- 途中 **22:08:33 に `localsearch-3: Running on LOW Battery, pausing`** が記録されている（この区間で残量を示す唯一の中間痕跡）。
- ただし **19:16 の電池切替時点の正確な capacity は INFO ログに残っておらず復元不能**なため、この区間から放電率（%/h）は算出できない。後述の「学習放電率 29→3 の不一致は未解決」の根拠でもある（実効レートを実測値で裏取りできない）。

## 現行設定スナップショット

> 本セッションでは設定変更を行っていない。以下はすべて実機 (`ssh miminashi@macbookair2015.lan`) で読み取った 2026-06-18 時点の値。

### カーネル／スリープ基盤

| 項目 | 現在値 |
|---|---|
| `/proc/cmdline` | `BOOT_IMAGE=/boot/vmlinuz-6.12.90+deb13-amd64 root=UUID=147f49dc-… ro quiet no_console_suspend mem_sleep_default=s2idle` |
| `/etc/default/grub` `GRUB_CMDLINE_LINUX_DEFAULT` | `quiet no_console_suspend mem_sleep_default=s2idle` |
| `/sys/power/mem_sleep` | `[s2idle] deep` |
| `/sys/power/disk` | `[platform] shutdown reboot suspend test_resume` |
| `/sys/class/power_supply/BAT0/alarm` | `0` ← **_BTP 無効化（修正の核心）** |
| DMI System Wake-up Type | `Power Switch` ← 修正が必要だった構造的理由 |

### ハイバネ配線（swap / RESUME）

| 項目 | 現在値 |
|---|---|
| swap デバイス | `/dev/sda3`（`swapon` SIZE 3.7G, PRIO -2） |
| swap UUID | `65051de6-9fb3-4588-8f89-3b9cd714e859` |
| `/etc/initramfs-tools/conf.d/resume` | `RESUME=UUID=65051de6-9fb3-4588-8f89-3b9cd714e859`（swap UUID と一致） |
| `/sys/power/resume` / `resume_offset` | `8:3`（=sda3） / `0` |
| initramfs resume hook | `scripts/local-premount/resume`, `conf/conf.d/resume` あり |
| swap 容量 vs RAM | swap 3.7G ≈ RAM 3.7G。**今回 約 1.26 GiB のイメージを実際に格納・復元成功**（容量充足を実証） |

### 設定ファイル全文

`/etc/udev/rules.d/99-disable-battery-trip-point.rules`:
```
# MacBook Air (Early 2015): ACPI _BTP battery trip point を無効化 (alarm=0) し、
# systemd-suspend-then-hibernate を壊れたハード _BTP 経路ではなく
# custom_timer_suspend (RTC ポーリング推定) 経路へ強制する。
# 背景: DMI wakeup type=Power Switch のため check_wakeup_type()=0 となり、
# ハード経路では構造的にハイバネに到達できない。
ACTION=="add|change", SUBSYSTEM=="power_supply", KERNEL=="BAT0", ATTR{alarm}="0"
```

`/etc/systemd/sleep.conf.d/20-battery-hibernate.conf`:
```ini
[Sleep]
# 放電率未学習の初回サイクル用の上限間隔。本機の s2idle 放電は約29%/時と速いため
# 既定60minを短縮し初回オーバーシュートを抑制 (学習後は実測レートで自動スケジュール)。
SuspendEstimationSec=30min
```

`/etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf`:
```ini
[Login]
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=suspend
```

`/etc/UPower/UPower.conf`（非コメント行抜粋）:
```ini
[UPower]
UsePercentageForPolicy=true
PercentageLow=20.0
PercentageCritical=5.0
PercentageAction=2.0
AllowRiskyCriticalPowerAction=true
CriticalPowerAction=Hibernate
```

> **注記（経路の区別 / 「2% 設定なのに 3% 発火」の解消）**: 今回 3% で発火したのは **systemd-suspend-then-hibernate のスリープ中閾値**（ログ `capacity below threshold (3% <= 5%)`＝ systemd 内蔵の `BATTERY_LOW_CAPACITY_LEVEL=5`、≤5%）であり、この UPower 設定ではない。UPower の `CriticalPowerAction=Hibernate`（`PercentageAction=2.0`）は**覚醒中の最終安全網**で、サスペンド中は発火できない（[2026-06-08 レポート](2026-06-08_035056_low_battery_hibernate.md) 参照）。今回は systemd が先に 3% でハイバネしたため UPower の 2% 経路は出番がなかった。両者は閾値も発火タイミング（スリープ中 vs 覚醒中）も異なる別系統である。

### 学習済み放電率ファイル

`/var/lib/systemd/sleep/battery_discharge_percentage_rate_per_hour`（verbatim）:
```
13729338060412566372 3
```
- 形式は `<バッテリ識別子の hash> <放電率 %/h>`。修正前はこのディレクトリ自体が存在せず（推定ロジックに一度も到達していなかった傍証）、修正後に生成されるようになった。
- なお初回学習（6/15 の 2 分テスト）では `29% per hour` と推定・保存されていた。現在ファイルの値は `3`。systemd は起床ごとに再推定するが、**29→3 の低下理由は本調査では未解決**（後述 caveat）。

### クリーンアップ／履歴の確認

- `/etc/systemd/system/systemd-suspend-then-hibernate.service.d/`（前回のデバッグ用 `SYSTEMD_LOG_LEVEL=debug` drop-in）は**ディレクトリごと撤去済み**。
- cmdline 履歴: `pcie_aspm=off` / `pm_print_times=1` は S3 hang 対策として 5/23 (commit `5f65b66`) に追加されたが、**S3→s2idle 恒久切替時 (commit `85548c5` / 2026-05-31) に「s2idle の消費電力を悪化させる失敗済みパラメータ」として意図的に除去**された。現在の cmdline にこれらが無いのが正しい状態。

### ログ可視性に関する注記

6/15 のテスト時に見えていた冗長ログ（`Set timerfd wake alarm for …` / `Estimating discharge rate` / `discharged in …`）は、当時一時投入していた `SYSTEMD_LOG_LEVEL=debug` 窓でのみ出力されていた。debug 撤去後の 6/17 の実発火サイクルでは、INFO レベルの `Found battery with capacity below threshold (3% <= 5%)` と kernel の hibernation 行のみが残る。**機構は同一で、差はログレベルのみ**。

## caveat・残課題

- **3% で起床＝5% フロアを下回る軽度オーバーシュート**: 今回ハイバネが発火したのは 5% ぴったりではなく 3% であり、目標フロア（5%）を下回ってからの発火だった。0% より十分上で書込に成功した（実際 1.26 GiB を約 6 秒で書けている）が、これは前回レポートが警告した「5%→0% のマージンが薄い」リスクが**軽度に現実化した実例**である。**今回成功した事実をもって「余裕十分」とは総括しない**。前回の薄マージン懸念（古い電池の電圧サグ等）は依然有効で、最終手段として固定 `HibernateDelaySec` フロアへ切り替える余地は残る。
- **放電率 29→3 の不一致は未解決**: 学習ファイルの値が初回 29%/h から現在 3 に変化しているが、6/17 の電池切替時点の正確な capacity が INFO ログから復元できない（debug 窓外のため `Set timerfd`/再推定ログが残っていない）ため、低下の原因は断定できない。**この値はあくまで verbatim 記録**とし、「s2idle 放電が緩やかになった」と解釈してはならない（boot 0 に見られる長時間 suspend leg は AC 接続時の plain `suspend` であり、放電率の根拠にならない）。
- **s2idle resume hang は別トラックの既知リスク**: [2026-06-01 s2idle hang 調査](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) 参照。今回の S4 resume では再発しなかったが、s2idle suspend レグ自体のリスクは根治していない。

## 参照した過去レポート

- [2026-06-15 バッテリ連動ハイバネ不発の原因特定と修正（_BTP 無効化）](2026-06-15_234635_fix_battery_hibernate_btp.md) — 今回クローズした残課題の出所。
- [2026-06-08 低バッテリ時ハイバネ対応（STH 初回設定）](2026-06-08_035056_low_battery_hibernate.md) — STH / UPower の初回設定。
- [2026-06-01 s2idle resume hang 調査](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) — 別トラックの既知リスク。

## 再現方法（成功の確認手順・すべて読み取り専用）

```bash
# 1) ≤5% ハイバネ発火と S4 復帰の確認（boot 0 内）
ssh miminashi@macbookair2015.lan 'journalctl -b 0 --no-pager | \
  grep -iE "capacity below threshold|hibernation: Creating image|hibernation exit"'

# 2) コールドブートではなく resume 完走（boot_id 不変）の確認
ssh miminashi@macbookair2015.lan 'cat /proc/sys/kernel/random/boot_id; journalctl --list-boots | tail -3'

# 3) タイムスタンプ artifact の検証（entry〜exit が monotonic で数秒）
ssh miminashi@macbookair2015.lan 'journalctl -b 0 -o short-monotonic --no-pager | \
  grep -iE "PM: hibernation: (hibernation entry|Creating image|hibernation exit)|Allocated .* kbytes"'

# 4) 現行設定スナップショットの再取得
ssh miminashi@macbookair2015.lan 'cat /sys/class/power_supply/BAT0/alarm; cat /proc/cmdline; \
  cat /etc/udev/rules.d/99-disable-battery-trip-point.rules; \
  cat /etc/systemd/sleep.conf.d/20-battery-hibernate.conf; \
  cat /etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf; \
  cat /var/lib/systemd/sleep/battery_discharge_percentage_rate_per_hour'
```
