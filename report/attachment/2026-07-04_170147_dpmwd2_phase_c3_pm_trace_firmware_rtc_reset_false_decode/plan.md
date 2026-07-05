# Phase C-3: pm_trace=1 再演 — RTC hash による hang 直前到達点の特定

## Context

[2026-07-04_022842](../projects/macbookair11-debian/report/2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md) で dpmwd2 (DPM watchdog late/noirq 拡張 + hung_task_panic) が hang に対して完全沈黙し、停止段 ∈ {syscore, s2idle-enter} が確定した。事前定義された次段の分岐に従い、**推奨案の pm_trace 再演** を実施する。dpmwd2 は `CONFIG_PM_TRACE_RTC=y` でビルド済み (021628 で deb config 検収済)・runtime `/sys/power/pm_trace=0` で inert 稼働中のため、**リビルド不要・runtime 有効化のみ**で投入できる。

- 目的: hang-arm 条件 (wl loaded + radio off + BT-PAN + VPN + 手動 lid close) で hang を再演し、強制電源断後の再起動時に RTC に残った hash (`Magic number:` / `hash matches`) から「最後に通過した TRACE 点」を特定する
- 役割分担: セットアップ・回収・解釈 = Claude (ssh)、iPad テザリング・lid cycle・wake キー押下・強制電源断 = ユーザ

## 計画時の新知見 (カーネルソース精読、src/linux-6.12.y = 6.12.94)

プラン作成時に pm_trace の実装を精読した結果、**期待値の較正**が必要:

1. **TRACE_* は per-device callback にしか無い**: `TRACE_DEVICE`/`TRACE_SUSPEND` の設置は `drivers/base/power/main.c` の device_suspend (main:1613/1614, 末尾 1728) / device_suspend_late (1403/1404, 末尾 1461) / device_suspend_noirq (1228/1229, 末尾 1292) と resume 側 (626/627, 791/792, 928/929) のみ。`kernel/power/suspend.c` (s2idle_loop / s2idle_enter) と `drivers/base/syscore.c` には **TRACE 点が 1 つも無い**。→ pm_trace が指せる最深点は「最後に触った noirq device」まで。syscore/s2idle 領域**内部**の device 粒度特定は構造的に不可能。
2. **s2idle 経路では syscore_suspend() は呼ばれない** (suspend.c:432-435 で `s2idle_loop()` へ直行、syscore_suspend は非 s2idle 経路 :446 のみ)。→ 022842 の残存候補「syscore」は s2idle では実体が異なり、正しい残存領域は **{platform_suspend_prepare_noirq (= acpi_s2idle_prepare_late), s2idle_loop 内部 (s2idle_enter / tick_freeze / cpuidle enter), wake 側 s2idle 領域}**。レポートでこの精緻化を明記する。
3. **それでも pm_trace の価値は残る**: (a) 「全 device callback 完走」を watchdog 沈黙という消極的証拠でなく**正の証拠**で確認、(b) file hash (main.c の suspend 側 vs resume 側の行) で **α (突入側 hang) / β (実は wake して復帰側 hang)** を判別、(c) hash が noirq 途中の device を指せば watchdog 沈黙との矛盾 = 大発見。毎 hang からゼロ追加試行で情報が取れる (pm_test 分離は p≈6% 下で腕ごとに ~30 cycle 必要なので C-4 に温存)。
4. **強制電源断でも hash は残る** (RTC 不揮発)。次ブートの `core_initcall(early_resume_init)` が読み、`late_initcall` が dmesg に `Magic number: user:file:dev` と `hash matches` を出す。照合は同一カーネル・同ブートの dpm_list に依存 (bnep/enx のような動的 device は照合不能だが file hash は device 非依存で常に有効)。

## 副作用と対策 (pm_trace 固有、今回の新規オペレーション)

| 副作用 | 対策 |
|---|---|
| suspend/resume のたびに RTC 時刻フィールドが hash で破壊される | resume 後に systemd-timesyncd で再同期 (下記 timefix)。セッション終了時に時刻同期確認後 `hwclock --systohc` で RTC 復旧 |
| **RTC alarm が使えなくなる** (alarm は時刻レジスタとの一致で発火、時刻が壊れるため) | rtcwake を使う smoke は **pm_trace 有効化の前に**実施。以後の wake は全て手動 (ユーザのキー押下) |
| resume 直後は時計が滅茶苦茶 → strongSwan の証明書検証が失敗し GSNet 再接続不能 → BT_PAN_VALID が崩れる | 一時 sleep hook `59-pmtrace-timefix` (post 時 & pm_trace=1 の時のみ `systemctl restart systemd-timesyncd`) を配置。timesyncd が BT-PAN 経由で大オフセットを step 修正 → vpn-watcher (3 秒間隔リトライ) が時刻復旧後に GSNet 接続成功する順序で自然に収束 |
| hang→再起動後のブートは時刻が壊れたまま開始 (journal タイムスタンプ異常) | 解析は epoch でなく boot 相対で行う。ssh 復旧後 (radio on) に timesyncd が修正 |

timesyncd の存在 (`systemctl is-enabled systemd-timesyncd`) はゲートで確認。無効なら timefix は transient watcher (vpn-watcher と同型) で代替。

## 実施手順

### Phase 0: 資材と経路

1. sandbox 経路確保: `/sandbox` 一時無効化をユーザに依頼 (または allowedDomains)。
2. 資材コピー: `/tmp/claude-1001/-home-miminashi-projects-macbookair11-debian/eae2c456-25da-472a-b290-5023f8b4a94b/scratchpad/phase-bc-materials/` (現存確認済、5 ファイル) → 今セッション scratchpad へ。新規に `59-pmtrace-timefix` フックを書き足す。
3. 実機ゲート (022842 と同じ + C-3 追加分):
   - `uname -r` = 6.12.94-dpmwd2、cmdline に panic=15、`[s2idle]`
   - **`/sys/power/pm_trace` が存在し 0** (PM_TRACE ビルドの実機確認)
   - `wl_loaded=YES`、`intel_pch_thermal.delay_cnt=300`
   - pstore 両所在: 残ダンプがあれば `~/pstore-recovered/` へ退避→削除 (空 = 沈黙判定の一意性確保)
   - hooks 4 本残置確認、`systemctl is-enabled systemd-timesyncd`

### Phase 1: pm_trace e2e 検証 (1 回だけ、022842 の pstore e2e 検証と同格)

1. 通常 smoke (rtcwake 使用、pm_trace=0 のまま) → `wl_loaded=YES ping_running=NO` 確認
2. `59-pmtrace-timefix` 配置 → `echo 1 | sudo tee /sys/power/pm_trace` → `sudo /sys/power/pm_debug_messages` も 1 に (成功 cycle の per-device 順序 = hash 解釈用ベースラインを journal に残す)
3. 手動 suspend 1 cycle (wake = ユーザのキー押下) → resume 後: 時計が壊れる→timesyncd が復旧することを確認。journal から **noirq 最終 device 名** を抽出 (ベースライン)
4. `sudo reboot` → 次ブートの `dmesg | grep -E "Magic number|hash matches"` で decode 動作を実証。`/sys/power/pm_trace_dev_match` も採取
5. 再起動で pm_trace=0 に戻るので **再度 1 を書く** (以後、再起動のたびに再有効化 — hang 後手順に組込み)

### Phase 2: セッション開始 (session-commands.md「1.」+ C-3 差分)

- `hung_task_panic=1`、NM autoconnect 設定 (BT-PAN/GSNet=yes, OpenWrt=no/800)、vpn-watcher / cycle-watcher transient units、最後に `radio off` (rmmod は絶対にしない)
- C-3 差分: `pm_trace=1`・`pm_debug_messages=1` を確認してから cycle 開始
- ユーザ: iPad テザリング → 手動 lid cycle 反復 (再現期待値 p≈6.4%、中央値 ~10 cycle)。**各 resume 後に GSNet が activated に戻ってから次の lid close** (vpn-watcher 任せでよいが、時刻復旧分だけ従来より数秒〜数十秒余計にかかる)

### Phase 3: hang 後 (順序厳守、session-commands.md「2.」+ C-3 差分)

1. ユーザ: 5 分以上待機 (自動再起動なしを確認) → 強制電源断 → 起動 → `nmcli radio wifi on` + `con up OpenWrt` で ssh 復旧
2. Claude: **pstore 判別を先に** (012628 ルール: ダンプありなら panic デバイスで対象 hang/偽陽性を判別。沈黙なら従来どおり)
3. **本命: `sudo dmesg | grep -E "Magic number|hash matches"` と `/sys/power/pm_trace_dev_match` を採取** (このブートの dmesg から。journal 保全も)
4. h4-probe unpaired PRE で hang cycle 確定、PRE の xfrm state で BT_PAN_VALID ゲート
5. 継続する場合: pstore 掃除 → sysctl 再設定 → transient units 再作成 → **pm_trace=1 再有効化** → radio off

### Phase 4: 解釈 (事前定義マトリクス — 結果を見る前に確定)

| 観測 (hang 後の Magic number) | 解釈 | 次段 |
|---|---|---|
| file hash = device_suspend_noirq 末尾 (main.c:1292 相当) & dev hash = ベースライン noirq 最終 device | **全 device callback 完走の正の証拠** → 停止域 = {acpi_s2idle_prepare_late, s2idle_loop 内部, wake 側 s2idle 領域} に精緻化 | C-4: pm_test=platform 分離 or ACPI/idle 層計装 |
| dev hash = noirq **途中**の device | watchdog 沈黙と矛盾 → その device の callback 内で watchdog が panic できない文脈 (NMI/irq off 等) の疑い | 当該 device 深掘り |
| file hash = resume 側 (main.c:626/791/928 系) | 実は wake して **β (復帰側) hang** → 解釈の大転換 | wake 経路の再設計 |
| Magic number 出ず / decode 不能 | pm_trace 書込み未達 (enable 漏れ / dpm 到達前) | ゲート再確認、hung_task 系再検討 |

### Phase 5: 撤収 (session-commands.md「3.」+ C-3 差分)

- `pm_trace=0`、`pm_debug_messages=0`、時刻同期確認後 `sudo hwclock --systohc` (**RTC 恒久復旧、忘れると次ブートも時刻異常**)
- `59-pmtrace-timefix` は pm_trace=1 ガード付きで inert なので残置可 (判断はその場で、レポートに明記)
- NM 平常化、hung_task_panic=0、transient units stop。58-snapshot-only / pstore-guard / h4-probe ログは従来どおり残置

## 成果物

1. レポート `report/2026-07-04_HHMMSS_dpmwd2_phase_c3_pm_trace_*.md` (タイムスタンプは `TZ=Asia/Tokyo date` で取得)。内容: pm_trace e2e 検証、hang 再現の有無と Magic number 解釈、**「s2idle では syscore_suspend は呼ばれない」精緻化 (ソース根拠つき)**、統計更新 (hang-arm pool に本セッション分を追加、pm_trace 摂動の注記)、次セッション引継ぎ。プランファイル添付 (attachment 規約)
2. メモリ `s2idle-btvpn-hang-mechanism-ladder.md` に (l) 項を追記

## 検証方法

- pm_trace e2e: Phase 1 の意図的 reboot で `Magic number:` 行が decode され、直前 resume の最終 device と整合することを確認 (これが通らない限り hang-arm cycle に入らない)
- 時刻復旧: Phase 1 の手動 cycle で resume 後 60 秒以内に `timedatectl` が synchronized=yes へ戻り、GSNet が再接続されること
- hang 判定: 従来どおり journal 途絶 signature + h4-probe unpaired PRE + pstore (012628 判別ルール)

## リスク・注意

- 初回 cycle で hang した 022842 と逆に、長時間再現しない可能性 (021628 は 0/29)。その場合も cycle 数は clean 側でなく **hang-arm pool に計上** (条件は hang-arm そのもの)
- pm_trace の RTC 書込みが suspend タイミングを微妙に変える摂動はゼロではない (レポートに注記、pool には tag つきで計上)
- cycle-watcher はセットアップ smoke を cycle 1 に計上する既知のズレ (021628 の罠) — 体感カウントと突合時に注意
