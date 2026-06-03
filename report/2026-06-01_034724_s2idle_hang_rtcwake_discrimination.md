# s2idle 切替後も resume hang 再発 — RTC ストレステストで原因切り分け (案1)

- **実施日時**: 2026年06月01日 03:47 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-01_034724_s2idle_hang_rtcwake_discrimination/plan.md)

## 前提・目的

MacBook Air 11" (Early 2015) / Debian 13 で、スリープ復帰失敗 (S3 hang) 対策として [2026-05-31 に スリープモードを ACPI S3 deep → s2idle へ恒久切替](2026-05-31_132125_s3_hang_switch_to_s2idle.md) した（`mem_sleep_default=s2idle` + udev で wake 源を LID0 のみに抑止）。その狙いは「hang が紐づく ACPI S3 deep の firmware 遷移そのものを使わない」ことだった。

- **背景**: 今回ユーザから「スリープ復帰失敗」の報告があり状況確認を実施。調査の結果、**s2idle 切替後 初日（同 2026-05-31 21:25）に hang が再発**していたことが判明した。
- **目的**:
  1. 今回の hang を確定し、原因仮説を再評価する（S3-firmware 説の検証）。
  2. ユーザ選択により **案1: 能動 rtcwake ストレステスト**で、残る被疑のうち「LID0 wake 取りこぼし」と「カーネルコード経路の hang」を切り分ける。
- **前提条件**: 操作対象は ssh 接続先の実機 `macbookair2015.lan`。すべての診断・修正は ssh 越しに実施。

## 環境情報

- 機種: MacBook Air 11" (Early 2015)
- OS: Debian 13 (trixie)
- カーネル: `6.12.90+deb13-amd64`
- スリープ: `/sys/power/mem_sleep` = `[s2idle] deep`（cmdline `quiet no_console_suspend mem_sleep_default=s2idle`）
- wake 源: `/proc/acpi/wakeup` で enabled は **LID0 のみ**（udev `90-s2idle-wakeup-suppress.rules` で XHC1/RP01-06 を抑止）
- バッテリー: `BAT0`（s2idle スリープ電力実測 ≈ 0.70 W）。調査時点 AC 接続・83% Charging
- 検出スクリプト: `/usr/local/sbin/check-suspend-resume.sh`（`PM: suspend entry`/`exit` を boot 単位で数え `diff>0` を `UNGRACEFUL [S3-HANG]` 判定）

## 今回の hang の確定根拠

検出スクリプトで boot `ec20c308`（off=-1）が `suspend=7 resume=6 diff=1 UNGRACEFUL`。当該 boot の cmdline は `mem_sleep_default=s2idle` で、**s2idle で稼働中の hang** と確定した（`journalctl --list-boots` でも boot -1 = 2026-05-31 13:13:23〜21:25:17 JST）。

boot -1 の suspend/resume を時刻・トリガ別に並べた trigger→outcome:

| # | トリガ | entry | exit | 結果 |
|---|--------|-------|------|------|
| 1 | `rtcwake -m mem -s 90` | 13:14:14 | 13:15:03 | ✓ |
| 2 | `rtcwake -m mem -s 180` | 13:17:19 | 13:20:20 | ✓ |
| 3 | Lid closed | 13:46:20 | 19:26:28 (5h40m) | ✓ |
| 4 | Lid closed | 19:29:05 | 20:24:31 | ✓ |
| 5 | Lid closed | 20:38:02 | 21:11:14 | ✓ |
| 6 | Lid closed | 21:20:30 | 21:21:20 | ✓ |
| 7 | **Lid closed** | **21:25:17** | **なし** | **HANG** |

- RTC 2/2 成功・lid 4/5 成功・**lid #7 のみ hang**。
- #7 は 21:25:15 の `systemd-logind: Lid closed → Suspending...` で s2idle 進入後、復帰せず。次 boot は 21:41:02（約16分後＝強制電源）。
- **バッテリー枯渇ではなく真の hang**: 16分で 0.70 W のバッテリーは枯渇しないうえ、長時間スリープ #3（5h40m）は復帰済み。前回レポートでバッテリー残量低下を懸念していたが、本件はそれが原因ではない。

## 原因仮説の転換点

**s2idle 下でも hang が出た以上、「ACPI S3 deep firmware が原因」説は棄却**される（hang は S3 firmware 遷移を一切伴わずに発生した）。これは前回レポートの contingency（「s2idle でも resume hang が出る場合は device-resume 起因の別仮説へ切り替える」）の発火に相当する。

ただしログ上は **どの hang も最終行が `PM: suspend entry`** で区別不能、かつ **pstore 不在**（`/sys/fs/pstore` 空・ERST なし）で電源断を跨いだ device 単位ログも取れない。したがって断定できる被疑は次の3候補に絞られる:

- **(a) suspend-path hang**（寝る途中、device の suspend コールバックで固まる）
- **(b) resume-path hang**（起きる途中、device の resume コールバックで固まる）
- **(c) LID0 wake を間欠的に取りこぼす**（カーネルは s2idle freeze ループで生存しているが、蓋開け割り込み LID0 notify が時々配送されず起きない。wake 源を LID0 のみに絞った今回の構成で新たに浮上した候補）

**3候補いずれも間欠故障**である点に注意（lid 4/5 成功・#7 のみ失敗）。特に (c) は「常に届かない」ではなく「間欠的に取りこぼす」でないとデータと矛盾する。

**hang はカーネル段で停止**: 観測された hang はいずれも userspace freeze 完了後（`Successfully froze unit 'user.slice'` → `Performing sleep operation 'suspend'` → `PM: suspend entry (s2idle)`）で止まっている。systemd を経由しない `rtcwake -m mem` でも、この `/sys/power/state ← mem` 以降のカーネル suspend/resume 経路は lid 経路と同一なので、当該 hang の再現手段として妥当（rtcwake がバイパスするのは freeze/hook の userspace 段だけで、そこは今回すでに通過済み）。

**confound（要明記）**: s2idle 切替時に `i915.enable_dc=0` と `pcie_aspm=off` も同時に外している。boot -1 は S3 時代と **3変数**違う → 今回の hang が S3 時代の hang と同根とは断定しない（S3-firmware 棄却自体は変数に依らず成立）。

## 切り分け方針（案1: 能動 rtcwake ストレステスト）

RTC 起床は **LID0 を一切使わずカーネル内蔵 RTC アラームで起きる**ため、wake 配送経路を切り離せる。多数の s2idle cycle を能動的に踏ませ、RTC トリガで hang が出るかを見る:

- **RTC で一度も hang しない**（lid では hang する）→ 失敗は wake 配送に固有 → **(c) LID0 取りこぼし**を支持。
- **RTC でも hang する** → wake 源に依らずコード経路の固着 → **(a)/(b) コード hang**（少なくとも (c) は除外）。

注意点（過大解釈を避ける）:

- 本テストは **(c) vs (a)/(b) の切り分けのみ**。(a) と (b) の分離はしない。
- 故障は間欠的なため「N 回 hang 0」は (c) を**確率的に支持するだけで確定ではない**。N を十分大きく取る。
- 「RTC clean」は (c) の**必要条件であって十分条件ではない**。(c) の積極確定は、後段で次に lid hang した時に電源ボタン短押しで復帰するか（案2）を見るのが本筋。

## 再現方法（実機での手順）

### A. 今回の hang の確認

```bash
ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh'   # ec20c308 が UNGRACEFUL
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail -10'             # boot -1 の時刻
# boot -1 の trigger→outcome
ssh miminashi@macbookair2015.lan \
  'journalctl -b -1 -o short-iso | grep -E "PM: suspend (entry|exit)|Lid closed|Suspending|rtcwake"'
```

### B. RTC ストレステスト（案1）

実機に配備するループスクリプト `/usr/local/sbin/rtcwake-stress.sh`（各サイクル前後で sync 付きでディスクログに追記し、hang→強制再起動を跨いでも「どのサイクルで ENTER 止まりか」を残す）:

```bash
#!/bin/bash
LOG=/var/log/rtcwake-stress.log
N=${1:-60}; SECS=${2:-90}
echo "$(TZ=Asia/Tokyo date -Is) START N=$N s=$SECS boot=$(cat /proc/sys/kernel/random/boot_id)" >> "$LOG"; sync
for i in $(seq 1 "$N"); do
  echo "$(TZ=Asia/Tokyo date -Is) cycle $i/$N ENTER" >> "$LOG"; sync
  /usr/sbin/rtcwake -m mem -s "$SECS" >> "$LOG" 2>&1
  echo "$(TZ=Asia/Tokyo date -Is) cycle $i/$N EXIT rc=$? " >> "$LOG"; sync
  sleep 10
done
echo "$(TZ=Asia/Tokyo date -Is) DONE $N cycles" >> "$LOG"; sync
```

実行（デタッチ常駐 / プリフライト: AC online=1・`[s2idle]`・蓋 open）:

```bash
# 第1バッチ: 60 cycle x -s 90 (件数確保, 約 1.7h)
ssh miminashi@macbookair2015.lan \
  'sudo systemd-run --unit=rtcwake-stress /usr/local/sbin/rtcwake-stress.sh 60 90'
# 結果確認 (DONE 行を正とする)
ssh miminashi@macbookair2015.lan 'tail -n 20 /var/log/rtcwake-stress.log; systemctl status rtcwake-stress --no-pager'
# 全 graceful なら第2バッチ: 6 cycle x -s 1800 (長時間スリープ相当)
```

判定:

- **全サイクル EXIT 記録あり（hang 0）** → RTC clean → lid #7 と対比し **(c) LID0 取りこぼし**を支持（確率的）。次フェーズで wake 源復活（電源ボタン等）の検討へ。
- **どこかで ENTER 止まり（machine 固着）** → ユーザが電源長押しで復帰 → 再起動後に logfile の最終 ENTER 行 + `check-suspend-resume.sh` で hang サイクルを確定 → **(a)/(b) コード hang**（(c) 除外）。

## 結果

### 第1バッチ（60 cycle × `rtcwake -m mem -s 90`）

2026-06-01 03:52:01 〜 05:33:01 JST（1h41m）に実行（boot `db743a1d`、AC 接続・バッテリー90%、systemd-run ユニット `rtcwake-stress`）。

| 指標 | 値 |
|---|---|
| ENTER（s2idle 進入） | 60 |
| EXIT（復帰） | 60 |
| EXIT rc≠0 | 0 |
| rtcwake 復帰行 | 60 |
| **hang（ENTER 止まり）** | **0** |

- 検出スクリプト cross-check: current boot `db743a1d` = `suspend=69 resume=69 diff=0 graceful`（バッチ前 8 + バッチ 60 + 検証 1 = 69 で整合、hang ゼロ）。
- 同一 `boot_id` 維持・uptime 連続 → **再起動なし・固着なし**。

**→ RTC 起床の s2idle は 60/60 全て正常復帰（hang 0）。** boot -1 の RTC 2/2 成功と合わせ **RTC 通算 62/62 clean**。一方 lid は **1/5 hang**（#7）。

### 解釈（第1バッチ時点）

RTC（LID0 を使わない）で 62/62 clean、lid で 1/5 hang という非対称は、**(c) LID0 wake の間欠取りこぼし**を支持する。すなわち今回の故障は「カーネルが s2idle freeze で生存しているのに、蓋開け割り込み(LID0 notify)が配送されず起きない」可能性が高い。

ただし方針どおりこれは **(c) の必要条件であって十分条件ではない**:

- lid サンプルは 5 回と少ない（hang 率の点推定 20%、信頼区間は広い）。
- 第1バッチは短時間サイクル（90s）中心。長時間 s2idle で挙動が変わらないかは第2バッチ（`-s 1800`）で確認する。
- (c) の積極確定は、次に lid hang した時に**電源ボタン短押しで復帰するか**（案2）を見るのが本筋。RTC clean はそれを「電源ボタンを試す価値がある」方向に裏付けるもの。

### 第2バッチ（6 cycle × `rtcwake -m mem -s 1800`）

2026-06-01 07:58:25 〜 11:04:31 JST に実行（同 boot `db743a1d`、AC 接続・バッテリー94%、サイクル間覚醒窓を 60s に拡大）。

| 指標 | 値 |
|---|---|
| ENTER | 6 |
| EXIT | 6 |
| EXIT rc≠0 | 0 |
| 各サイクル実睡眠 | 全 1800s 完走（早期 wake なし） |
| **hang（ENTER 止まり）** | **0** |

- 各サイクルがきっちり 30 分スリープ→復帰（例: 07:58:25 ENTER → 08:28:26 EXIT）。**夜間運用に近い長時間 s2idle でも RTC 起床で確実に復帰**。
- 検出スクリプト cross-check: current boot = `suspend=75 resume=75 diff=0 graceful`（69 + 6 = 75 で整合）。同一 boot_id・再起動なし。

### 総合結論

| トリガ | s2idle cycle 数 | hang | 備考 |
|---|---|---|---|
| **RTC**（LID0 不使用） | **68** | **0** | boot-1: 2、第1バッチ: 60(×90s)、第2バッチ: 6(×1800s) |
| **Lid**（LID0 wake） | 5 | 1 | boot-1 の #3〜#7、#7 のみ hang |

- **RTC 68/68 clean（短時間・長時間とも）vs lid 1/5 hang** という非対称が出た。s2idle の **wake 源に依らない** suspend/resume コード経路は、短時間・長時間いずれでも RTC 起床で完全に動作する。

**ただし RTC テストは 2 つの条件を同時に変えている（重要な限界）**: 68 サイクルはすべて **lid OPEN** のまま suspend し、wake も RTC。一方 実故障はすべて **lid CLOSE → OPEN** の遷移を伴う。つまり本テストは「wake 源（LID0 vs RTC）」だけを分離できておらず、**lid 開閉に伴う物理遷移／ディスプレイ復帰 (HPD) 経路を一度も再現していない**。resume 後のカーネル復帰シーケンスは wake 源に依らず同一なので、RTC が 68 回同経路を通った事実が否定できるのは **wake 源非依存の suspend/resume hang のみ**であり、lid 遷移ブランチは否定できない。

→ したがって残存する真の被疑は次の 2 つで、**どちらも今回のデータ（RTC clean・lid 1/5 hang）を等しく説明する**:

- **(c) LID0 wake の間欠取りこぼし**: カーネルは s2idle freeze で生存しているのに、蓋開け割り込み LID0 notify が時々配送されず起きない。
- **(b′) lid 開閉／ディスプレイ復帰経路に固有の resume hang**: lid-closed→open / GPU(i915) resume の枝で固まる。**`i915.enable_dc=0` を s2idle 切替時に外した**ぶん、ディスプレイ復帰起因の hang はむしろ有力になっている（§confound）。display/GPU resume は典型的な hang 箇所。

**よって「(a)/(b) は後退」と断定はしない**。RTC で否定できたのは wake 源非依存の hang だけで、lid/display 固有の (b′) は健在。lid サンプルが 5 回（hang 率点推定 20%、信頼区間広）と少ない点も留意。

残存被疑は **(c) vs (b′)**。これは RTC テストでは原理的に切り分けられない（上記の限界）。切り分けには次のいずれかが要る。

### 補足観測（調査中に確認した未整理の事実）

以下は本調査の journal 確認中に観測したが上の結論には未反映の事実。今後の切り分けの手掛かりになり得る。

- **hang した #7 suspend の直前に DRM(ディスプレイ)エラーが記録されていた — が、照合の結果 red herring と判明**: hang した #7 の直前に `gnome-shell[2197]: Cursor update failed: drmModeAtomicCommit: 無効な引数です`（display/i915 エラー）があり、当初は (b′) の補強かと見えた。しかし 2026-06-03 に boot -1 の全 suspend を照合したところ、**この行は lid-close 5 回（#3〜#7）すべての直前に出ており、うち #3〜#6 は正常復帰している**:

    | suspend | Lid closed | DRM エラー | 結果 |
    |---|---|---|---|
    | #3 | 13:46:18 | 13:46:19 あり | ✓ 復帰 |
    | #4 | 19:29:03 | 19:29:04 あり | ✓ 復帰 |
    | #5 | 20:38:00 | 20:38:01 あり | ✓ 復帰 |
    | #6 | 21:20:28 | 21:20:29 あり | ✓ 復帰 |
    | #7 | 21:25:15 | 21:25:16 あり | ✗ **HANG** |

    → **hang との相関なし**。これは lid-close 時のディスプレイ teardown で毎回出る定常メッセージ（RTC suspend #1/#2 は lid-close が無いため出ない）であり、**hang の手掛かりにはならない（red herring 確定）**。なお、これは (b′) 仮説そのものを否定するものではない（このログ行が (b′) の証拠にならない、というだけ）。
- **s2idle の成功 resume でも `pm_print_times` の device-level timing が journal に出ていなかった**: `pm_print_times=1`（維持）にもかかわらず、boot -1 の成功 resume で device の `call ... returned` 行を grep しても 0 件だった（`pm_debug_messages=0`）。つまり s2idle 経路では device 単位の suspend/resume timing が既定では記録されておらず、pstore 不在と併せて **device 単位の可視性は s2idle でも乏しい**。(b′) を device レベルで詰めるなら `pm_debug_messages=1` の有効化などが別途必要。

### 次アクション

0. **（済 / 安価）DRM エラーの裏取り → red herring 確定**（2026-06-03 照合済み、上記補足観測を参照）。今後の (b′) 切り分け用に `pm_debug_messages=1` を有効化しておくと、device 単位の suspend/resume timing を journal に残せる（未実施）。
1. **案2 の前提検証（必須・先行）**: 案2（lid hang 時に電源ボタン短押しで復帰するか）が意味を持つのは、**電源ボタンが健全な s2idle を起こせる wake 源である**場合に限る。現状 `/proc/acpi/wakeup` で enabled は **LID0 のみ**（XHC1/RP01-06 は意図的に抑止）なので、まず**健全なスリープサイクルで電源ボタン短押しが復帰させるか**を物理押下で確認する（ssh では不可）。
   - 健全時に電源ボタンで起きる → 案2 が成立。次に lid hang した時、**強制電源長押しの前に電源ボタン短押し** → **復帰すれば (c) 確定**（カーネル生存・wake のみ未配送）、**無反応なら (b′)**（wake 源を変えても固着）。
   - 健全時に電源ボタンで**起きない** → 案2 は不成立。別の第2 wake 源（例: 一時的に USB/キー wake を有効化）を用意する必要がある。
2. **（代替・よりクリーンな切り分け）lid を物理的に閉じたまま RTC で起こす試験**: lid CLOSE 状態を保ったまま RTC wake させれば、「lid-closed の物理状態」を保持しつつ wake 源だけを LID0→RTC に差し替えられる。これで (c) と (b′) をより直接的に分離できる（lid 閉でも RTC で復帰するなら、固着は lid-open notify 配送に固有 = (c) 寄り）。実機の前での操作が必要。
3. **(c) が確定した場合の対策方向**: lid wake 取りこぼし対策（LID0 GPE の扱い、別 wake 源の併用復活、`button.lid_init_state` 等）。spurious wakeup 抑止（84s 問題）とのトレードオフを再評価。
4. **(b′) が確定した場合の対策方向**: ディスプレイ/GPU resume 経路の対策。まず `i915.enable_dc=0` を s2idle 構成に戻して再発するか（外したことが効いたか）を切り分ける。

### テスト資材（残置）

- 実機スクリプト: `/usr/local/sbin/rtcwake-stress.sh`（第3引数 = サイクル間覚醒秒, default 10）
- ログ: `/var/log/rtcwake-stress.log`（第2バッチ）, `/var/log/rtcwake-stress.batch1.log`（第1バッチ退避）
- systemd-run ユニット: `rtcwake-stress`（恒久構成は未変更）
