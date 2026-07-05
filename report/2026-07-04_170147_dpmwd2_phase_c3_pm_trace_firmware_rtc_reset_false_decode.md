# Phase C-3 — hang 三度目の再現 (完全沈黙)、pm_trace の RTC チャネルは Mac firmware の日付リセットにより boot を越えられないことを発見・確定 (偽 decode の罠込み)

- **実施日時**: 2026年7月4日 08:57 〜 17:01 JST (hang 発生: 実時刻 ~16:35 前後、有効 cycle 3 回目)
- **位置づけ**: [2026-07-04_022842](2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md) の引継ぎ (事前定義の次段 = pm_trace 再演)。**pm_trace の e2e 検証中に想定外の挙動を検出し、hang 再現・回収を経て、その正体 (firmware による RTC 日付検証・リセット) を制御実験で確定させた**。

## 概要

### 何をしたか

dpmwd2 (`CONFIG_PM_TRACE_RTC=y` ビルド済) の `/sys/power/pm_trace` を runtime 有効化し、022842 と同一の hang-arm 条件 (wl loaded + radio off + BT-PAN + VPN + 手動 lid close) で再演。hang 再現後、強制電源断→初回 boot の RTC hash decode で停止点を特定する計画だった。

### 結果 (主要成果)

1. **hang 再現: 有効 cycle 3 回目 (1/3、全 cycle BT_PAN_VALID)**。dpmwd2 watchdog (main+late/noirq) + hung_task_panic とも**三度目の完全沈黙** (pstore 両所在空、~5 分以上待機) — 022842 の「停止段 ∈ {syscore 相当領域, s2idle-enter}」を n=2 で補強。
2. **【本セッションの最大の発見】pm_trace の RTC チャネルは本機では構造的に使用不能**。MacBook の firmware (EFI/SMC) は **boot 時に RTC の日付を検証し、不正な日付 (pm_trace が書く year 2056 等の hash encode) を初期値 `2016-01-01 00:00:00` にリセットする**。したがって hang→強制電源断→boot で読める値は常に firmware 初期値であり、カーネルが suspend 中に書いた hash は失われる。
3. **偽 decode の罠を検出・解体**: firmware 初期値 2016-01-01 00:00 は decode すると n=16 = `Magic 0:1:0` となり、kernel の照合機能が **1/997 の hash 偶然衝突**で `hash matches drivers/base/power/main.c:1728` (device_suspend 末尾) を報告する。これは「dpm main 段末尾で停止」という**もっともらしい嘘**であり、成功 cycle 後の reboot でも hang 後でも同一値が出ることから偽物と見抜いた (決定打は秒フィールド: 3 回の独立イベントで `00:00:13` が完全一致 = 決定論的リセット + 固定 boot 遅延)。
4. **encode/decode/hash 実装自体は健全**: 実スリープしない `pm_test=devices` / `platform` cycle では OS の書き込みが RTC に残り、期待どおり `main.c:1001` (device_resume 末尾) + 最終 resume device に decode されることを UTC 手計算で検証済み (自作 sdbm hash 計算もカーネル出力と一致)。**壊すのは firmware であって pm_trace ではない**。
5. **救済路の成立可能性を probe で確認**: firmware の検証は少なくとも年粒度で、**year 2026 なら月日・時刻が任意でも素通しされる** (2026-12-28 23:57 を設定→reboot→生存)。→ dpmwd3 で「firmware-safe encoding (年を現行に固定し、hash を月日時分 12×28×24×20 = 161,280 通り ≥ user×file = 15,952 に詰める)」が設計可能。
6. 副次: カーネルソース精読 (src = dpmwd2 実体 b90248d63) により **s2idle 経路は `syscore_suspend()` を通らない** (suspend.c:432-435 で s2idle_loop へ直行) ことを確認。022842 の残存候補「syscore」の s2idle における実体は **{acpi_s2idle_prepare_late (platform prepare_noirq), s2idle_loop 内部 (s2idle_enter / tick_freeze / cpuidle), wake 側 s2idle 領域}** と精緻化される。

### 統計への影響

| プール | 更新前 | 更新後 |
|---|---|---|
| hang-arm (wl-loaded + radio-off + BT-PAN + VPN) | 7/110 ≈ 6.4% | **8/113 ≈ 7.1%** (+ 本セッション 1/3) |
| clean-arm (radio-on / wl-unloaded) | 0/112 | 0/112 (不変) |

注: 本セッションは pm_trace=1 (suspend 中に RTC への CMOS 書き込みが数百回入る) という摂動下での cycle。hang が 3 cycle 目で出たこと自体は p≈6-7% の幾何分布として異常ではないが、プール解釈時は摂動 tag 付きとして扱う。

## 添付ファイル

- [実装プラン](attachment/2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode/plan.md)
- [hang cycle PRE スナップショット (1783144069.pre)](attachment/2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode/hang-cycle-1783144069.pre.txt)
- [6 ブート分の Magic number 証跡](attachment/2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode/magic-number-6boots-evidence.txt)

## 前提・目的

- **背景**: 022842 で停止段が {syscore, s2idle-enter} に絞られ、dpmwd2 の watchdog では届かない領域と確定。事前定義の次段 = pm_trace 再演 (RTC hash 照合) を実施する。
- **目的**: hang 再演時に RTC に残る「最後に通過した TRACE 点」の hash から、suspend 進行の最終到達点を正の証拠で特定する。
- **役割分担**: セットアップ・回収・解釈 = Claude (ssh)、テザリング・lid cycle・wake キー押下・強制電源断・WiFi 復旧 = ユーザ。

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd2** (DPM_WATCHDOG=y 60s + late/noirq 拡張 b90248d63、**PM_TRACE_RTC=y**、cmdline `panic=15`)
- スリープ: `[s2idle] deep`、`intel_pch_thermal.delay_cnt=300`
- hooks: 50-kbd-backlight / 58-snapshot-only / **59-pmtrace-timefix (本セッションで新規配置)** / 60-s3-soak-log / 70-h4-probe
- BT/テザリング: iPad BT-PAN `172.20.10.13/28`、VPN: GSNet (strongSwan IKEv2)
- WiFi: `wl` loaded のまま `nmcli radio wifi off` (tight reading (b'') 維持)、電源: AC
- 参照ソース: `src/linux-6.12.y` = **dpmwd2 の実体そのもの** (git HEAD = b90248d63、行番号が実機カーネルと一致)

## 実験タイムライン (2026-07-04 JST、hang ブート内の時刻は clock skew あり概算)

| 時刻 | 内容 |
|---|---|
| 08:57-09:00 | Phase 0 ゲート全通過 (`/sys/power/pm_trace` 実在=0 確認)。smoke 1 cycle |
| 09:00 | 59-pmtrace-timefix 配置、pm_trace=1 有効化 (カーネル警告出力確認) |
| 13:35 | 検証 cycle 1 (ユーザ lid cycle、radio-on): 時計破壊→timefix→timesyncd 復旧の e2e 確認 |
| 14:11 | 検証 cycle 2 + wake 20 秒後自動 reboot (#1) → **decode `0:1:0 → main.c:1728` — 予測 (1001) と不一致、調査開始** |
| 14:24 | `pm_test=devices` 較正 cycle (実スリープなし) → RTC = **`main.c:1001` hash (期待どおり)** を UTC 手計算で確認 |
| 14:27 | reboot (#2) → RTC は timesyncd により実時刻復旧済みで **リセットされず素通し (対照実験)** |
| 14:28-14:35 | Phase 2: hang-arm 条件投入 (sysctl/NM/watchers/pm_trace=1/radio off) |
| ~16:2x-3x | ユーザ: BT-PAN 有効 cycle 1, 2 (clean) → **cycle 3 で hang** (journal は `PM: suspend entry (s2idle)` で途絶、entry 4 / exit 3) |
| ~16:40 | ユーザ: 5 分以上待機 → 自動再起動なし → 強制電源断 → boot → WiFi 復旧 |
| 16:46-16:50 | 回収: pstore 空 (三度目の沈黙)、**boot RTC = `2016-01-01 00:00:13` → 偽 decode 0:1:0**。`pm_test=platform` 較正 → OS write 残存確認 |
| 16:52 | **制御実験**: RTC=2056 ガベージのまま reboot → `2016-01-01 00:00:13` + 0:1:0 が再現 (firmware リセット確定、n=3) |
| 16:57 | **probe A**: RTC=2026-12-28 23:57 設定 → reboot → **生存** (year 2026 は素通し = dpmwd3 救済路成立) |
| 17:01 | 撤収: pm_trace=0、時刻/RTC 復旧 (`hwclock --systohc`)、NM 平常化 |

## 証拠と検証

### firmware RTC リセットの確定 (6 ブート対照表)

| boot | 直前の RTC 内容 | boot 時読み取り | 判定 |
|---|---|---|---|
| 02:22 (022842 hang 後、pm_trace 未使用) | 実時刻 | `2026-07-03 17:22:10` (実時刻、素通し) | 対照 |
| 14:11 reboot#1 (成功 cycle 直後、hash 残存) | hash (year 異常) | **`2016-01-01 00:00:13` → 0:1:0** | リセット |
| 14:27 reboot#2 (timesyncd が実時刻復旧済み) | 実時刻 | `2026-07-04 05:27:28` (素通し) | 対照 |
| 14:47 **hang 後 cold boot** | hash (suspend 中の書込み) | **`2016-01-01 00:00:13` → 0:1:0** | リセット |
| 16:52 制御実験 (2056 ガベージを意図的に残して reboot) | `2056-11-19 00:44` | **`2016-01-01 00:00:13` → 0:1:0** | リセット (制御) |
| 16:57 probe A (`2026-12-28 23:57` を設定) | 同左 | `2026-12-28 14:57:20 UTC` (**生存**) | 素通し (年内なら任意) |

- **秒フィールドの論証**: リセット 3 回とも読み取り値が `00:00:13` で完全一致。カーネル書き込みの残存なら hang 突入→電源断→boot の 5 分超で分フィールドが進むはず。13 秒 = 「firmware が boot 開始時にリセット → kernel の読み取りまでの固定遅延」であり、決定論的リセットの証拠。
- **偽 decode の機構**: 2016-01-01 00:00 は `read_magic_time` で n=16 → (user=0, file_hash=1, dev=0)。`.tracedata` 全 18 site 中 main.c:1728 (device_suspend 末尾 `TRACE_SUSPEND(error)`) だけが hash_string(1728, "drivers/base/power/main.c", 997) = 1 に衝突し `hash matches` が出る (sdbm を手元実装で全 site 計算し確認)。dev=0 に一致する device は無し (dev match 空欄) — これも偽物のサイン。
- **健全性の対照**: `pm_test=devices`/`platform` (実スリープなし、reboot なし) 後の RTC は `2056-11-19 00:42` = n=11815056 → (0, 661, 740)。661 = hash(main.c:1001) = device_resume 末尾 = **教科書どおりの「成功 cycle の最終書き込み」**。encode/decode/照合の全経路はカーネル内では正しく動く。

### hang の確定 (durable evidence)

- h4-probe: unpaired PRE = 1783144069 が hang cycle。同 PRE で `ip xfrm state src 172.20.10.13 dst 160.16.210.47` (lastused 突入 21 秒前) = **BT_PAN_VALID**、`wl_loaded=YES ping_running=NO`
- 有効 cycle 1 (1783143949)・2 (1783144014) も PRE で BT_PAN_VALID + wl loaded 確認済み (clean)
- hang ブート journal: `PM: suspend entry` 4 / `exit` 3 で不均衡、最終行 `PM: suspend entry (s2idle)` (既知 signature)
- pstore 両所在空 (セッション開始時に空を確認済み → 空 = panic 未発火と一意に解釈可)。watchdog の実戦発火能力は [012628](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md) で検証済み

### s2idle と syscore の関係 (ソース精読、解釈マトリクスの精緻化)

`kernel/power/suspend.c` (dpmwd2 実体): `suspend_enter()` は s2idle の場合 432-435 行で `s2idle_loop()` に直行し、`syscore_suspend()` (446 行) は**非 s2idle 経路でのみ実行**される。よって 022842 の「停止段 ∈ {syscore, s2idle-enter}」の s2idle における実体は:

> **停止段 ∈ {platform_suspend_prepare_noirq (= acpi_s2idle_prepare_late), s2idle_loop 内部 (s2idle_enter → tick_freeze/timekeeping・cpuidle enter)、wake 側 s2idle 領域 (dpm_resume_noirq 開始前)}**

また `TRACE_*` は `drivers/base/power/main.c` の per-device callback 18 箇所にしかなく、上記領域には trace 点が 1 つも無い (ftrace の `trace_suspend_resume` のみ = 強制電源断で揮発)。**仮に firmware リセットが無かったとしても、素の pm_trace はこの領域内部を指せない** (最深で「noirq 最終 device の末尾」= 予測値 0:610:799 まで)。

## 結論

1. **Phase C-3 の主目的 (RTC hash による停止点特定) は本機では構造的に不能** — Apple firmware が boot 時に RTC 日付を検証し、pm_trace の hash encode (不正な日付になる) をリセットするため。これは pm_trace の設計 (RTC は電源断を跨ぐ唯一の記憶という前提) が Apple ハードウェアで成立しないことを意味する。
2. **hang は 3 セッション連続で全監視機構 (DPM watchdog main/late/noirq + hung_task_panic) に対して沈黙** — 停止域は s2idle 深部 {acpi_s2idle_prepare_late, s2idle_loop, wake 側} で不変・補強。
3. **`Magic 0:1:0 → main.c:1728` を「dpm main 段末尾で停止」と読む誤解釈を未然に回収した**。成功 cycle 後の reboot で同一値が出たことが疑いの発端。**今後 RTC 由来の証拠を扱う際は必ず「成功 cycle 後の対照」を取ること** (教訓)。

## 次セッション引継ぎ (Phase C-4 候補)

1. **dpmwd3: firmware-safe pm_trace (推奨)** — 2 点の改造で C-3 の目的を達成可能:
   - `set_magic_time()` の encode を「年 = 現行 (2026) 固定、hash を月×日×時×分バケット (12×28×24×20 = 161,280 通り) に格納」へ変更。probe A で year 2026 なら素通しを確認済み。容量は user(16)×file(997) = 15,952 に十分 (dev は落とすか残余 ×10 に圧縮)
   - **s2idle 領域への TRACE 点追加**: `platform_suspend_prepare_noirq` 前後、`s2idle_loop` 突入、`s2idle_enter` 前後、`acpi_s2idle_wake` — 素の pm_trace では見えない残存候補領域を直接カバーする (mc146818_set_time は irq-off 文脈でも呼べる)
   - decode 側 (`read_magic_time`) も対応変更。ビルド・デプロイ手順は 182811/021628 と同一
2. 代替: `pm_test=platform` 二分 (s2idle では platform レベルまでしか無いため {≤prepare_noirq} vs {s2idle_loop 以深} の 1 bit のみ、p≈7% 下で統計コスト大)
3. 検討済み・保留: pstore console バックエンドによる breadcrumb (EFI NVRAM の書き込み耐久・容量制約が Mac で未知、リスクあり)

## 残置物 (実機の現状、17:01 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd2 稼働 (saved default)。dpmwd1 / stock 残置 |
| pm_trace / pm_debug_messages / pm_test | 0 / 0 / none (全て inert) |
| RTC / 時刻 | NTP 同期済み + `hwclock --systohc` で復旧済み |
| NM autoconnect / route-metric | 平常化済み (BT-PAN/GSNet=no, OpenWrt=yes/-1) |
| kernel.hung_task_panic | 0 |
| sleep hooks | 従来 4 本 + **59-pmtrace-timefix 新規残置** (pm_trace=1 ガード付きで平常時は完全 no-op、撤去は rm のみ) |
| pstore | 両所在空。pstore-guard enabled (no-op) |
| /var/log/h4-probe | 本セッション分追加 (削除しないこと)。hang PRE = 1783144069 |

## 再現方法

### firmware RTC リセットの再現 (本セッションの核心的発見)

```bash
# 不正な日付を RTC に書いて reboot → 2016-01-01 にリセットされることを確認
ssh miminashi@macbookair2015.lan 'sudo hwclock --set --date "2056-11-19 00:42:00" --utc && sudo systemctl reboot'
# boot 後:
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -k | grep -E "RTC time|Magic number|hash matches"'
#  → PM: RTC time: 00:00:13, date: 2016-01-01 / Magic number: 0:1:0 / hash matches ...main.c:1728
# 対照: 年内の日付は生存する
ssh miminashi@macbookair2015.lan 'sudo hwclock --set --date "2026-12-28 23:57:00" --utc && sudo systemctl reboot'
#  → PM: RTC time: (設定値+boot 遅延) が読める
# 後始末 (時刻復旧):
ssh miminashi@macbookair2015.lan 'sudo systemctl restart systemd-timesyncd && sleep 10 && sudo hwclock --systohc'
```

### pm_trace の健全性確認 (実スリープなしの較正 cycle)

```bash
ssh miminashi@macbookair2015.lan '
echo 1 | sudo tee /sys/power/pm_trace; echo devices | sudo tee /sys/power/pm_test
sudo systemctl start systemd-suspend.service --wait
echo none | sudo tee /sys/power/pm_test; sudo hwclock -r'
# hwclock の UTC 値を read_magic_time のロジックで decode → (0, 661, dev) = main.c:1001 になる
```

### hang-arm セッション (022842 と同一、資材は scratchpad phase-bc-materials/)

022842 の「再現方法」参照。C-3 差分は `pm_trace=1` / `pm_debug_messages=1` と、resume 後の時刻復旧待ち (59-pmtrace-timefix + timesyncd) のみ。

## 関連レポート

- [2026-07-04_022842 Phase C-2 第 2 回 hang 再現・停止段 {syscore, s2idle-enter} 確定 (引継ぎ元)](2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md)
- [2026-07-04_012628 intel_pch_thermal 偽陽性 (watchdog 実戦発火能力の検証 = 沈黙判定の根拠)](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md)
- [2026-07-03_021628 dpmwd2 デプロイ (PM_TRACE_RTC=y ビルド検収の一次証拠)](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md)
- [2026-07-03_002608 dpmwd1 解釈マトリクスの定義元](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md)
- [2026-07-02_103415 (b'') tight reading bedrock (hang-arm 条件の統計的根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
