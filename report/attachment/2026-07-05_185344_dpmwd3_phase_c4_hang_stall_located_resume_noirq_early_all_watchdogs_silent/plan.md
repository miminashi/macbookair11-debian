# Phase C-4: dpmwd3 (firmware-safe pm_trace + s2idle TRACE 点) ビルド・デプロイ・hang-arm 再演

## Context

C-3 (report 2026-07-04_170147) で、s2idle hang の停止点特定に使う予定だった pm_trace の RTC チャネルが、Mac firmware の boot 時 RTC 日付検証 (不正日付 → 2016-01-01 リセット) により構造的に使用不能と確定した。一方で **year 2026 なら任意の月日時分が素通しされる**ことを probe で実証済み。さらにソース精読で **s2idle 経路には TRACE 点が 1 つも無い** (最深 = noirq 末尾) ことも確定している。

本セッション = レポートの引継ぎ第 1 候補 **dpmwd3**:
- (A) `set_magic_time`/`read_magic_time` を firmware-safe encoding に変更
- (B) s2idle 残存候補領域 {acpi_s2idle_prepare_late, s2idle_loop/s2idle_enter, wake 側} に TRACE 点を追加
- ビルド・デプロイ後、hang-arm 再演で「最後に通過した TRACE 点」を RTC から回収し停止点を特定する

停止域の現状: {acpi_s2idle_prepare_late, s2idle_loop 内部, wake 側 s2idle 領域} (022842 + 170147、watchdog/hung_task とも 3 連続完全沈黙)。統計 pool: hang-arm 8/113 ≈ 7.1%。

## 設計 (パッチ、C-3 からの改良 2 点込み)

### 設計上の重要判断 (C-3 レポートに無い追加考慮)

1. **RTC tick 問題**: RTC は hash 書き込み後も進み続ける (電源断中も)。stock encode は min に hash 上位桁を格納するため **3 分でデコード破壊**。hang 検知 → 強制電源断 → boot の実運用に 3 分は危険なので、**min/sec を hash から外す** → tick 猶予 60 分に拡大。min:sec は「最終 TRACE から boot までの経過時間」の副次情報になる。
2. **実時刻との判別 (C-3 の罠の再来防止)**: year を実年 2026 固定にすると「実時刻が残った RTC」と「hash」が判別不能。**Phase 0 で year 2027 の firmware 素通しを probe** し、通れば `PM_TRACE_YEAR=127` (2027) を署名に使う (実時刻は 2026 なので year=2027 ⇔ hash 存在、が一意)。2027 が reset される場合のみ 2026 固定 + プロトコル判別 (成功 cycle 対照必須) にフォールバック。

### (A) encode/decode 変更 — `drivers/base/power/trace.c`

- 容量設計: mon(12) × mday(28) × hour(24) = **8,064**。dev チャネルは廃止 (device callback は dpmwd2 watchdog が既にカバー済み・停止域はその先)、**FILEHASH 997 → 397** に縮小。n_max = 15 + 16×396 = **6,351 ≤ 8,064** ✓
- `set_magic_time()` (trace.c:86-116): `n = user + USERHASH*file` (dev 引数は無視 or 削除)。
  `tm_year = PM_TRACE_YEAR` (固定) / `tm_mon = n%12` / `tm_mday = (n/12)%28+1` / `tm_hour = (n/336)%24` / `tm_min = 0` / `tm_sec = 0`。n ≥ 8064 なら -1。
- `read_magic_time()` (trace.c:118-137): **`tm_year != PM_TRACE_YEAR` なら「no trace data (firmware reset or real time)」を pr_info して invalid フラグ** (static bool)。valid 時は `val = mon + (mday-1)*12 + hour*336`、min:sec を経過時間として pr_info。
- `late_resume_init()` (trace.c:286-304): invalid フラグ時は decode スキップ。valid 時 `user = val%16, file = val/16` (FILEHASH=397 で `show_file_hash` 照合)。`show_dev_hash` 呼び出しは削除。
- `generate_pm_trace()` (trace.c:167-180): `file_hash_value = hash_string(lineno, file, 397)`。

### (B) s2idle 領域への TRACE 点追加 (計 ~11 点、user コード 0-15 でサブステップ判別)

対象 3 ファイルに `#include <linux/pm-trace.h>` を追加 (現状 3 つとも include 無し、確認済み):

`kernel/power/suspend.c` (`suspend_enter()` 403-482 / `s2idle_loop()` 126-154):
1. `platform_suspend_prepare_noirq(state)` (425 行) 直前: `TRACE_SUSPEND(0)`
2. 同・成功直後 (s2idle 分岐 432 行の直前): `TRACE_SUSPEND(1)`
3. `s2idle_loop()` 冒頭 (128 行): `TRACE_SUSPEND(2)`
4. loop 内 `s2idle_enter()` (150 行) 呼び出し直前: `TRACE_SUSPEND(3)` — **s2idle_lock の外に置く** (rtc_lock ネスト回避)
5. `s2idle_enter()` 復帰直後: `TRACE_RESUME(4)`
6. `s2idle_loop()` 末尾 (153 行): `TRACE_RESUME(5)`
7. `Platform_wake:` の `platform_resume_noirq(state)` (470 行) 直前: `TRACE_RESUME(6)`

`drivers/acpi/x86/s2idle.c` (LPS0、本機で実際に効く側):
8. `acpi_s2idle_prepare_late()` (545 行) 冒頭: `TRACE_SUSPEND(0)`
9. 同・screen-off DSM 後 / LPS0 entry DSM 前: `TRACE_SUSPEND(1)`
10. 同・末尾: `TRACE_SUSPEND(2)`
11. `acpi_s2idle_restore_early()` (604 行) 冒頭: `TRACE_RESUME(3)`

`drivers/acpi/sleep.c`:
12. `acpi_s2idle_wake()` (758 行) 冒頭: `TRACE_RESUME(7)` (wake 判定ループ到達の証拠)

- `mc146818_set_time` は `spin_lock_irqsave` のみで irq-off 文脈から呼べる (noirq callback での発火実績あり、rtc-mc146818-lib.c:280-307 確認済み)
- **hash 衝突ゲート**: ビルド後、全 TRACE site (main.c 18 + 新規 ~12) の `sdbm(lineno, file) % 397` を手元スクリプトで全計算し、衝突表 + decode 予測チートシートを作る。s2idle 域サイト同士が衝突したら該当行に空行を足して番号をずらして再ビルド。

## 実施フェーズ

### Phase 0: 事前 probe (実機、~10 分、reboot 2 回)

C-3 の再現方法セクションと同じ hwclock probe で **year 2027 の素通し**を確認:
```bash
ssh ... 'sudo hwclock --set --date "2027-03-15 07:00:00" --utc && sudo systemctl reboot'
# boot 後 journal の "RTC time" が設定値+boot 遅延なら素通し → PM_TRACE_YEAR=127
# リセットされたら 2026 (=126) にフォールバック。後始末: timesyncd restart + hwclock --systohc
```
※ ssh を使うため **サンドボックス切替 (/sandbox) をユーザに依頼**してから開始。

### Phase 1: パッチ作成 + ビルド (開発機 `src/linux-6.12.y`、~40 分)

1. `git checkout -b dpmwd/6.12.94-wd3 b90248d63` 相当 (現ブランチ HEAD=b90248d63 にコミット追加でも可)。パッチ (A)(B) を 1 commit「PM: sleep: firmware-safe pm_trace encoding + s2idle trace points」として積む (81 commits 目)
2. `.config` は残存する dpmwd2 のものをベースに `CONFIG_LOCALVERSION="-dpmwd3"` のみ変更 → **`rm include/config/auto.conf && make olddefconfig`** (LOCALVERSION 反映の既知の罠、182811)
3. `make -j12 LOCALVERSION= bindeb-pkg` (**env LOCALVERSION= 必須**、`+` 付与回避。~35 分)
4. 検収: deb 内 config に `DPM_WATCHDOG=y/60`, `PM_TRACE_RTC=y`。hash 衝突チェック (前述) → decode チートシート作成 (scratchpad + 後でレポート添付)

### Phase 2: デプロイ + 検証ゲート (実機、182811/021628 と同一手順 + 新ゲート)

1. deb 2 個 scp (md5 照合) → `dpkg -i` headers → image (dkms が wl 自動再ビルド、initramfs、update-grub)
2. `grub-reboot` ワンショットで dpmwd3 初回起動 (saved default は dpmwd2 のまま = フェイルセーフ) → **grubenv 変更後は必ず `sync`**
3. **ゲート (a)**: uname=6.12.94-dpmwd3 / config 全項目 / cmdline panic=15 / wl loaded + WiFi / pstore 空 / pstore-guard / s2idle / `intel_pch_thermal.delay_cnt=300`
4. **ゲート (t1) encode 較正** (実スリープなし): `pm_trace=1` + `pm_test=devices` cycle → hwclock 読み → year=PM_TRACE_YEAR かつ decode = main.c:1001 相当サイト (新 hash で手計算照合)
5. **ゲート (t2) boot 越え e2e** (C-3 で死んだ経路の再検証): hash を残したまま reboot → journal に `Magic number` + 正しい `hash matches` が出ること (**firmware リセットされないこと**)
6. **ゲート (t3) 新 TRACE 点の発火確認**: `pm_test=platform` cycle (429 行で折り返し = 最終書き込みが新設サイト #2 になる) → decode がサイト #2 を指すこと
7. **ゲート (t4) 成功 cycle 対照** (C-3 の教訓): radio-on の実 s2idle 1 cycle (a2 相当) → resume 後 reboot → decode が resume 末尾サイトを指すこと
8. 全ゲート通過後: `grub-set-default` を **dpmwd3 に変更 + sync** (hang 後の強制電源断 boot が dpmwd3 で立ち上がらないと decode 側が旧ロジックになるため、hang-arm 前に必須)

### Phase 3: Phase C-4 hang-arm 再演 (ユーザ協働、022842/170147 と同一プロトコル)

- 資材: 前セッション scratchpad (`/tmp/claude-1001/.../eae2c456-*/scratchpad/phase-bc-materials/`、5 ファイル) を現セッション scratchpad にコピー (消えていれば report/attachment から復元)。59-pmtrace-timefix は実機に残置済み
- Phase 0 ゲート → sysctl hung_task_panic=1 / NM autoconnect 設定 / vpn-watcher・cycle-watcher / pm_trace=1 / smoke 1 cycle → iPad BT-PAN + GSNet → detached radio off → **ユーザ: 手動 lid cycle 反復**
- **hang 時の手順 (C-3 からの変更点)**: lid open 無反応確認 → 5 分待機 (watchdog 沈黙確認、tick 猶予 60 分なので余裕あり) → 強制電源断 → boot (dpmwd3) → **journal の `Magic number` decode + `hwclock -r` 生値を即時回収** (timesyncd が RTC を上書きする前に) → チートシートで停止点判定
- 統計: cycle は hang-arm pool に摂動 tag (pm_trace=1) 付きで計上。cycle-watcher のセットアップ smoke 1 ズレ既知罠に注意

### Phase 4: 撤収 + レポート

- pm_trace=0 / 時刻・RTC 復旧 (`hwclock --systohc`) / NM 平常化 / sysctl 復元 / transient units 停止
- レポート作成 (report/ 規約どおり、`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得)。本プランファイルを attachment にコピー。decode チートシート・hash 衝突表・hang cycle 証跡を添付
- メモリ (s2idle-btvpn-hang-mechanism-ladder) に (m) エントリ追記

## 検証方法 (要約)

パッチの正しさはゲート t1-t4 が end-to-end で担保する: encode 手計算照合 (t1) → firmware 素通し (t2) → 新 TRACE 点発火 (t3) → 成功 cycle 対照 (t4)。本番 (hang) では「最後に書かれたサイト」の一意 decode が成果物。

## リスク・ロールバック

| リスク | 対処 |
|---|---|
| year 2027 も firmware にリセットされる | Phase 0 で事前判明 → 2026 固定 + 成功 cycle 対照プロトコルで判別 |
| dpmwd3 起動不能 | grub-reboot ワンショット → 次回自動で dpmwd2 に復帰。stock/dpmwd1/dpmwd2 全残置 |
| hash 衝突で decode 曖昧 | ビルド時全サイト衝突チェック + show_file_hash は全一致を列挙するので曖昧でも可視 |
| TRACE 点追加による挙動摂動 (RTC CMOS write が cycle 毎に十数回) | pm_trace=0 時は完全 no-op (マクロ内ガード)。有効時は摂動 tag で統計管理 (C-3 と同じ) |
| hang 放置 60 分超で hour 桁繰り上がり | decode 出力に生 mon/mday/hour/min を併記し手動補正可能にする。ユーザに 50 分以内の電源断を依頼 |

## 主要参照

- 引継ぎ元: `report/2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md` (次セッション引継ぎ §1)
- ビルド・デプロイ手順の前例: `report/2026-07-02_182811_*.md` / `report/2026-07-03_021628_*.md`
- hang-arm プロトコル: `report/2026-07-04_022842_*.md` 再現方法
- 改造対象: `src/linux-6.12.y` — `drivers/base/power/trace.c` (86-137, 167-180, 286-304)、`kernel/power/suspend.c` (126-154, 403-482)、`drivers/acpi/x86/s2idle.c` (545-589, 604-642)、`drivers/acpi/sleep.c` (758-819)
