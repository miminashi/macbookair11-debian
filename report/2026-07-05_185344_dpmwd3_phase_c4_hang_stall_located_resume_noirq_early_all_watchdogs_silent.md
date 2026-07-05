# ハング停止点の特定 — 停止は suspend 側ではなく resume 側だった (Phase C-4 / dpmwd3)

**サマリ**: firmware-safe に改造した pm_trace (dpmwd3) で hang を 4 回再現し、全回で停止点の取得に成功。停止域は従来推定の「suspend 側 s2idle 深部」ではなく **wake 成功後の dpm resume noirq/early 段のデバイス境界**と確定した (DPM watchdog / hung_task / NMI hardlockup / softlockup の 4 監視は、判定に足る待機を行った hang #2〜#4 で全て沈黙)。

- **実施日時**: 2026年7月4日 17:30 〜 7月5日 18:55 JST (ビルド・デプロイ: 7/4 夕、hang-arm 再演: 7/5 午前〜夕)
- **位置づけ**: [2026-07-04_170147](2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md) の引継ぎ第 1 候補 (dpmwd3) を実施。**pm_trace を Mac firmware 耐性のある encoding に改造し、s2idle 領域に TRACE 点を追加した自前カーネルで、3 セッション沈黙だった hang の停止点を初めて正の証拠で取得した**。

## 概要

本機で追跡している「BT テザリング + VPN 使用中に lid を閉じるとスリープから戻らなくなる」ハングは、これまで計 8 回再現しながら停止位置が分からず、特に直近 3 セッションでは監視機構を仕込んだカーネル (dpmwd1/dpmwd2) 上で再現させても一切痕跡を残さなかった。前回 (C-3) は、電源断を跨いで停止位置を記録できる唯一の仕組みである pm_trace が、Mac のファームウェアが起動時に RTC の日付を検証してリセットしてしまうために使えない、という壁に突き当たって終わっていた。

今回はこの壁を越えるため、ファームウェアの検証を素通りする形式で停止位置を RTC に記録するように pm_trace を改造したカーネル (dpmwd3) をビルド・デプロイし、従来記録ポイントが存在しなかった s2idle 経路にも記録点を追加した。改造の動作は、実スリープを伴わない較正、再起動を越えた読み出し、そして「スリープ中に強制電源断する」という本番同様の予行の 3 段階で事前に実証してから本番に臨んだ。

その結果、ハングを 4 回再現し、4 回とも停止位置の取得に成功した。判明した事実は従来の見立てを覆すものだった。**機械はスリープに正常に入っており、lid を開けたときの wake も成功している。止まっていたのはその後、デバイスを順に起こしていく resume 処理 (noirq〜early 段) の途中**だった。これまで「suspend の途中で止まる」と考えてきたのは、ログ上は suspend 側の停止と resume 側の停止が区別できないことによる誤りだったと確定した。

停止位置が分かったことで、新しい謎も明確になった。停止箇所は DPM watchdog の監視範囲内なのに panic せず、今回追加で仕掛けた NMI ベースの検知にも掛からない。CPU が暴走しているわけでも、タスクが長時間ブロックされているわけでもない「静かな停止」である。また 30 分放置しても復帰しないことを確認し、「時間をかければ resume が完走する」可能性は否定された。

残る特定対象は「どのデバイスの境界で止まるか」の実名だけであり、次の小改造 (dpmwd4) で取得できる見込みである。実用上の回避策は引き続き「WiFi radio を常時 on にしておく」ことで変わらない。

## 添付ファイル

- [実装プラン](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/plan.md)
- [dpmwd3 パッチ (7c86c3994)](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/dpmwd3-firmware-safe-pmtrace-s2idle-tracepoints.patch)
- [decode チートシート (全 24 site の hash/RTC 予測値)](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/decode-cheatsheet.txt)
- [decode ヘルパ decode.py (hour 汚染の -1h 補正付き)](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/decode.py)
- [hash 計算・衝突チェックスクリプト](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/hashcalc.py)
- [直近 8 ブートの decode 証跡 (journal 抜粋)](attachment/2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent/c4-decode-evidence.txt)

## 前提・目的

- **背景**: 170147 で pm_trace の RTC チャネルが Mac firmware の日付リセットで使用不能と確定、同時に year 2026 なら素通しされる救済路を発見。停止域は「s2idle 深部 (watchdog の届かない領域)」と推定されていた。
- **目的**: firmware-safe encoding + s2idle 領域 TRACE 点の dpmwd3 を作り、hang 再演時に「最後に通過した TRACE 点」を正の証拠として取得、停止点を特定する。
- **役割分担**: ビルド・デプロイ・arm・回収・解釈 = Claude (ssh)、テザリング・lid cycle・強制電源断・WiFi 復旧 = ユーザ。

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd3** (= dpmwd2 の DPM watchdog late/noirq 拡張 + 本パッチ、`CONFIG_PM_TRACE_RTC=y`、cmdline `panic=15`)
- ビルド機: 開発機 (12 コア)、`src/linux-6.12.y` ブランチ HEAD `7c86c3994` (81 commits = Debian 79 + dpmwd2 + dpmwd3)、`make -j12 LOCALVERSION= bindeb-pkg` ~35 分
- スリープ: `[s2idle]`、`intel_pch_thermal.delay_cnt=300`、hooks: 50/58/59/60/70 (170147 と同一)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28`、VPN: GSNet (strongSwan IKEv2)、WiFi: `wl` loaded + `nmcli radio wifi off`
- **LPS0 デバイス (PNP0D80) は本機に不在**であることを確認 — `acpi_s2idle_prepare_late` の DSM 群は本機では実行されず、prepare_late 入口 TRACE (site 8) のみ発火

## dpmwd3 の設計と検証ゲート (詳細)

### 実施項目

1. **Phase 0 probe**: RTC year **2027 も firmware を素通し**することを実証 (`hwclock` 設定→reboot→生存)。実時刻 (2026) と衝突しない「hash 存在の署名」として採用可能に。
2. **dpmwd3 ビルド・デプロイ**: dpmwd2 (b90248d63) の上に 1 commit (`7c86c3994`) を追加。
   - **(A) firmware-safe encoding** (`drivers/base/power/trace.c`): year=2027 固定 (署名兼用)、hash を mon×mday×hour (8,064 slot) のみに格納、**min/sec=0 で書き込み → RTC tick 猶予が stock の 3 分から 60 分に拡大** (min:sec は「最終 TRACE からの経過時間」の副次情報になる)、FILEHASH 997→397、dev チャネル廃止、decode 側に year 署名検証 (不一致なら「no trace data」)。
   - **(B) s2idle 領域 TRACE 点 12 箇所追加**: `suspend.c` (prepare_noirq 前後 / s2idle_loop 突入・脱出 / s2idle_enter 前後 / Platform_wake)、`acpi/x86/s2idle.c` (prepare_late 入口ほか)、`acpi/sleep.c` (acpi_s2idle_wake 入口)。全 24 site の sdbm hash 衝突をビルド前に全計算し衝突ゼロを確認 (1 件を空行挿入で回避)。
3. **検証ゲート全通過**: (a) 起動 10 項目 / (t1) encode 較正=手計算予測と完全一致 / (t2) **hash が reboot を生存しカーネルが自力 decode** (C-3 で構造的に死んでいた経路の復活) / (t3) **合成 hang** (キーボード・電源ボタンの wake を runtime 無効化 → スリープ中に強制電源断) で `Magic 3:332 → suspend.c:152` = 「s2idle_enter 直前で就寝中」の署名を正確に取得。
4. **Phase C-4 hang-arm 再演** (wl loaded + radio off + BT-PAN + VPN + lid close): **4 回 hang 再現、4 回とも停止点 decode に成功**。

## hang 再現結果 (停止点の詳細)

| hang | 有効cycle | 停止点 (RTC decode) | 意味 | 経過 (最終TRACE→boot読取) |
|---|---|---|---|---|
| #1 | 1/1 | `main.c:836` (Magic 0:389) | **device_resume_early 末尾** | 1分11秒 |
| #2 | 3/3 | `main.c:627` (Magic 0:167) | **device_resume_noirq 開始** | 20分21秒 |
| #3 | 2/2 | `main.c:700` (Magic 0:30) | **device_resume_noirq 末尾** | **15秒 (=電源断直前まで書込み継続)** |
| #4 | 3/3 | `main.c:700` (Magic 0:51 → **-1h 補正** 0:30) | 同上 | **1時間1分58秒 (30分放置+α)** |

1. **hang は suspend 側ではなく resume 側**。suspend は完走して s2idle で正常就寝し、lid open/キーで **wake 自体は成功**、resume が noirq を経て early 段まで進む途中の**デバイス境界で停止**する。002608→022842→170147 で積み上げた「停止段 ∈ {syscore 相当, s2idle-enter}」は、**journal 上 suspend 側停止と resume 側停止が区別不能** (console 未復旧のため journal は `suspend entry` で途絶) だったことによる誤絞り込みと判明。pm_trace だけがこれを見分けた。
2. **全監視機構が resume 側停止に対して沈黙することを確認**: DPM watchdog 60s (dpmwd2/3 は resume_noirq/early の callback を計装済み・012628 で実戦発火能力検証済み) / hung_task_panic 120s / **NMI hardlockup (panic=1、hang #3-#4 で arm)** / softlockup — いずれも panic せず (pstore 全 4 回空)。**「callback 単位では 60 秒未満で完了し、D 状態にも長期滞留せず、CPU スピンでもない」停止**という強い制約が付いた。**注: hang #1 は電源断までの待機が ~40 秒と短く、watchdog (60s) 以降の判定窓に達していないため沈黙判定から除外する** (沈黙確認は #2 = 5 分 / #3 = 数分 / #4 = 30 分超に基づく)。
3. **crawl 仮説 (デバイス毎タイムアウトの直列進行でいずれ完走) を棄却**: hang #4 で 30 分放置しても復帰せず (画面黒・短押し無反応・本体ほんのり温)、最終 TRACE 後 62 分間書き込みゼロ。ただし hang #3 では電源断直前まで TRACE 書き込みが継続しており、**イベント間で停止の様相に差がある** (#3 は電源ボタン押下に伴う wake/resume 活動の可能性)。
4. **残る未知は「どのデバイスの境界か」のみ** (本 encode は容量制約で dev チャネルを廃止したため)。次段 dpmwd4 で取得可能 (次セッション引継ぎ参照)。

## 統計への影響 (摂動 tag 付き)

- **本セッション: hang 4/9 有効 cycle ≈ 44%** — 歴史的 hang-arm pool (8/113 ≈ 7.1%) から大幅に乖離。**dpmwd3 + pm_trace=1 (s2idle ループ内で rtc_lock irqsave の CMOS 書き込みが cycle 毎に発生) の摂動下の数字であり、既存 pool へは合算せず別 arm として記録する**。乖離の解釈候補: (i) pm_trace の RTC 書き込みが race 窓を拡大 (計測が現象を増悪)、(ii) 「arm 条件確立直後の初回 lid close」の hang 濃縮 (022842 の cycle 1 hang と合わせ既に 3 例目)、(iii) 偶然。
- 停止点の観測値は摂動下の系のものだが、症状 (黒画面・無反応・全沈黙)・条件 (BT_PAN_VALID) は歴史的 hang と同一で、機序同一性は高い蓋然性 (断定はしない)。

## 実験タイムライン (JST)

| 日時 | 内容 |
|---|---|
| 7/4 17:32 | Phase 0: RTC=2027-03-15 設定→reboot→**素通し確認** (probe B)。時刻復旧 |
| 7/4 17:40-18:14 | パッチ作成 (4 ファイル)・hash 衝突解消・commit 7c86c3994・ビルド (~34 分) |
| 7/4 18:15-18:18 | deb scp・dpkg -i (dkms wl 自動ビルド)・grub-reboot ワンショット→dpmwd3 起動 |
| 7/4 18:17-18:28 | ゲート (a) 10/10・(t1) encode 較正一致・saved default を dpmwd3 に変更・(t2) boot 越え decode 成功 |
| 7/4 18:38〜7/5 09:19 | (t4 相当) pm_trace=1 のまま一晩実 s2idle → 正常 resume (**新 TRACE 点がスリープを壊さないことの実証**) |
| 7/5 09:23-09:31 | (t3) 合成 hang: kbd/電源ボタン wake を runtime 無効化→suspend→強制電源断→**decode `3:332 → suspend.c:152` 一致** (途中、電源ボタン wake が ACPI 固定イベント経由と判明し ff_pwr_btn も無効化して再試行) |
| 7/5 09:32-09:41 | Phase 3 arm (sysctl/NM/watchers/smoke/pm_trace=1)→BT-PAN→radio off→**hang #1 (初回 lid close)** |
| 7/5 09:45-09:55 | 回収 (decode #1)・再 arm→cycle×2 clean→**hang #2 (5 分待機→沈黙確認)** |
| 7/5 10:30-10:48 | 回収 (decode #2)・**NMI hardlockup_panic=1/softlockup_panic=1 を runtime arm**・再 arm→cycle clean→**hang #3 (数分待機→沈黙)** |
| 7/5 17:20-17:44 | 回収 (decode #3)・`pm_print_times=1` 追加・再 arm→cycle×2 clean→**hang #4** |
| 7/5 17:45-18:20 | **30 分放置→復帰せず**→強制電源断→回収 (decode #4、-1h 補正) |
| 7/5 18:50-18:55 | 証跡恒久化・テアダウン (全ノブ平常化・NM/RTC 復旧)・本レポート |

## 証拠と検証

### 停止点 decode の信頼性

- **encode/decode/boot 越えの全経路をゲート t1-t3 で事前実弾検証済み** (t3 は「スリープ中に強制電源断→cold boot→期待 site (suspend.c:152) を正確に decode」という hang 本番と同一経路)。
- **年署名の有効性は初回起動時に自然実証**: 実時刻 RTC (2026) の boot は `no trace data (RTC year 2026, expected 2027)` と正しく棄却された (C-3 の偽 decode の罠を構造的に排除)。
- hang #4 の `0:51` は既知 site 不一致 → 放置 60 分超による hour 桁繰り上がり (+336/16=+21) を decode.py の -1h 補正で解読、`0:30 = main.c:700`。真の経過 1:01:58 は放置時間 (30 分タイマー+検知までの時間+電源投入遅延) と整合。
- 各 hang の BT_PAN_VALID: **4 hang すべての PRE スナップショットで `wl_loaded=YES` + xfrm SA (`172.20.10.13 → 160.16.210.47`) を確認** (PRE epoch: #1=1783212084 / #2=1783212892 / #3=1783216095 / #4=1783241071)、加えて suspend entry 直前まで charon が BT-PAN 上で retransmit していた journal 証跡も一致 (NM teardown が hook より先行して bnep/enx を消すのは 063543 既知の正常挙動)。
- **罠 (セッション中に 1 回踏んだ)**: hang cycle の PRE を「`ls -t` の最新ファイル」で掴むと、復旧 boot 内で起きた別の短い suspend の PRE (今回 1783218741、POST とペア済み) を誤って hang に帰属しうる。**hang の PRE は「POST とペアになっていない unpaired PRE」で同定するのが正** (boot 境界 journal との突合で全 4 hang の帰属を検証済み — 各 hang boot の journal 最終時刻と unpaired PRE epoch が 1 秒以内で一致)。

### 監視機構の沈黙 (resume 側停止に対して)

- dpmwd2/3 の DPM watchdog は `device_resume_noirq`/`device_resume_early` の callback を 60 秒で計装済み (b90248d63)。停止点が正にその領域なのに 4 回とも panic せず。
- NMI hardlockup detector (PERF) は `nmi_watchdog=1` が歴代セッションでも常時有効だったが **`hardlockup_panic=0` のため「検知しても console (suspend 中で不可視) 出力のみ」だった**ことが判明。hang #3-#4 では panic=1 で arm したが発火せず → **irq-off CPU スピンではない**。
- hung_task (120s、D 状態) も沈黙 → **長期 D 状態滞留でもない** (TASK_IDLE 待ちは検知対象外である点に注意)。
- 総合すると停止の形態は「callback 間 (dpm 機構部) での停止」「TASK_IDLE 等の検知対象外の待ち」「callback 単位 60 秒未満での進行停止の複合」のいずれかに絞られる。

## 結論

1. **Phase C-4 の主目的 (停止点の正の証拠取得) を達成**。3 セッション・のべ 8 hang で完全沈黙だった停止点は、**wake 成功後の dpm resume noirq/early 段のデバイス境界** (main.c:627/700/836) にあった。
2. 022842/170147 の「停止段 ∈ {syscore, s2idle-enter}」は **journal の対称性錯誤による誤絞り込み**として正式に訂正する (suspend 側停止と resume 側停止は journal 上識別不能)。
3. H4 (btusb URB drain = suspend 側機序) は今回の停止点と直接整合しない位置にあり、さらに後退。「wake 喪失」仮説 (lid 通知が届かない) も**棄却** (wake は成功している)。
4. 残る特定対象は**停止境界のデバイス実名**。全監視機構をすり抜ける停止形態の機序解明もこれに依存する。

## 次セッション引継ぎ (Phase C-5 候補)

1. **dpmwd4: デバイス実名の取得 (推奨、改造 ~30 分 + ビルド ~35 分)** — `main.c` の resume 側 6 箇所で `TRACE_DEVICE` と `TRACE_RESUME` の**呼び出し順を入替え** (現在: DEVICE→RESUME で RTC には site が残る → 入替後: RESUME→DEVICE で **「これから callback を実行するデバイスの hash」が RTC に残る**)。encode は user=15 をデバイス書き込みの marker に予約し、`val = 15 + 16×(dev_hash % 397)` 等で site と判別。decode 側で dpm_list を hash 照合 (旧 show_dev_hash の要領)。
2. 代替/併用: resume 側だけ `dev_dbg` 相当の breadcrumb を pstore console に書く (EFI 変数の書込み耐久が未知のためリスクあり、170147 で保留済み)。
3. **実用対策は不変**: 常時 WiFi radio-on 運用 (0/52 clean) が引き続き唯一の確実な回避策。
4. 検証すべき論点: (i) pm_trace 摂動が hang 率を上げているか (dpmwd4 で pm_trace=0/1 の率比較が安価にできる)、(ii) 「arm 直後の初回 lid close 濃縮」(022842 と今回 #1、n=3)、(iii) hang #3 の「電源断直前まで TRACE 継続」の再現性 (電源ボタン押下による wake/resume 活動説の検証)。

## 残置物 (実機の現状、7/5 18:55 JST)

| 項目 | 状態 |
|---|---|
| kernel | **6.12.94-dpmwd3 稼働 (saved default)**。dpmwd1/dpmwd2/stock 残置 (多段ロールバック可) |
| pm_trace / pm_print_times / pm_test | 0 / 0 / none (全て inert) |
| hardlockup_panic / softlockup_panic / hung_task_panic | 0 / 0 / 0 (平常) |
| NM / radio | autoconnect・route-metric 平常化済み、radio on |
| RTC / 時刻 | NTP 同期 + `hwclock --systohc` 済み |
| sleep hooks | 5 本とも残置 (58/59/70 は実験用、平常時 no-op) |
| pstore | 両所在空。pstore-guard enabled |
| /var/log/h4-probe | 本セッション分追加 (hang PRE = unpaired: 1783212084 / 1783212892 / 1783216095 / 1783241071)。削除しないこと |
| 開発機 | `src/linux-6.12.y` HEAD=7c86c3994 (dpmwd3)、deb 成果物 `src/*.deb` |

## 再現方法

### dpmwd3 のビルド・デプロイ

182811/021628 と同一手順。差分は commit 7c86c3994 (添付パッチ) と `CONFIG_LOCALVERSION="-dpmwd3"` のみ。LOCALVERSION 変更後は `rm include/config/auto.conf && make olddefconfig`、ビルドは `make -j12 LOCALVERSION= bindeb-pkg`。

### 停止点 decode (hang 後)

```bash
# hang → (放置判定) → 強制電源断 → 電源投入 → WiFi 復旧後:
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -k | grep -E "RTC time|Magic number|no trace data|trace data valid|hash matches"'
# 「Magic u:f」が出たら添付 decode-cheatsheet.txt で site を引く。
# 不一致なら放置 60 分超の hour 汚染 → 添付 decode.py が -1h 補正候補を提示:
python3 decode.py "YYYY-MM-DD HH:MM:SS"   # journal の RTC time/date 行の値 (UTC)
```

### 合成 hang (計測系の実弾検証、ゲート t3)

```bash
ssh miminashi@macbookair2015.lan '
echo disabled | sudo tee /sys/bus/usb/devices/1-5/power/wakeup           # 内蔵キーボード
echo disable  | sudo tee /sys/firmware/acpi/interrupts/ff_pwr_btn        # 電源ボタン固定イベント
echo disabled | sudo tee /sys/bus/acpi/devices/LNXPWRBN:00/power/wakeup
echo 1 | sudo tee /sys/power/pm_trace
sudo systemd-run --unit=t3-suspend --collect --on-active=8 systemctl suspend'
# → 30 秒待って電源ボタン 10 秒長押し (SMC ハード断、wake しない) → 電源投入
# → boot decode が「Magic 3:332 → suspend.c:152」になれば計測系正常 (全設定は boot で自動復帰)
```

### hang-arm セッション

022842 の「再現方法」と同一 + `pm_trace=1`。radio off 後は LAN ssh 不能になるため、WiFi 復旧は実機コンソールで `nmcli radio wifi on && nmcli con up OpenWrt` (autoconnect off のため `con up` 必須)。

## 関連レポート

- [2026-07-04_170147 Phase C-3 firmware RTC リセット発見・dpmwd3 設計の引継ぎ元](2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md)
- [2026-07-04_022842 Phase C-2 「停止段 {syscore, s2idle-enter}」(本レポートで訂正)](2026-07-04_022842_dpmwd2_phase_c2_run2_hang_reproduced_silent_stage_syscore_s2idle.md)
- [2026-07-04_012628 DPM watchdog 実戦発火能力の検証 (沈黙判定の根拠)](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md)
- [2026-07-03_002608 dpmwd1 解釈マトリクス (本レポートで一部訂正)](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md)
- [2026-07-02_182811 カーネルビルド・デプロイ手順の一次ソース](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-07-02_103415 (b'') tight reading bedrock (hang-arm 条件の統計的根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
