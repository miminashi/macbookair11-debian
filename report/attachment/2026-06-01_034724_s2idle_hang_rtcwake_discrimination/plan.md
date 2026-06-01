# s2idle でも resume hang 再発 — RTC ストレステストで原因切り分け (案1)

## Context（なぜこの作業をするか）

2026-05-31 に MacBook Air 11" (Early 2015) のスリープ復帰失敗 (S3 hang) 対策として、スリープモードを ACPI S3 deep → **s2idle へ恒久切替**した（`mem_sleep_default=s2idle` + udev で wake 源を LID0 のみに抑止）。その狙いは「hang が紐づく ACPI S3 deep の firmware 遷移そのものを使わない」ことだった。

今回ユーザから「スリープ復帰失敗」の報告があり調査した結果、**s2idle 切替後 初日（同 2026-05-31 21:25）に hang が再発**していたことが判明した。

- 検出スクリプトで boot `ec20c308`（off=-1）が `suspend=7 resume=6 diff=1 UNGRACEFUL`。
- 当該 boot の cmdline は `mem_sleep_default=s2idle`（s2idle で稼働中の hang と確定）。
- boot -1 の trigger→outcome:

  | # | トリガ | entry | exit | 結果 |
  |---|--------|-------|------|------|
  | 1 | rtcwake -s 90 | 13:14:14 | 13:15:03 | ✓ |
  | 2 | rtcwake -s 180 | 13:17:19 | 13:20:20 | ✓ |
  | 3 | Lid closed | 13:46:20 | 19:26:28 (5h40m) | ✓ |
  | 4 | Lid closed | 19:29:05 | 20:24:31 | ✓ |
  | 5 | Lid closed | 20:38:02 | 21:11:14 | ✓ |
  | 6 | Lid closed | 21:20:30 | 21:21:20 | ✓ |
  | 7 | **Lid closed** | **21:25:17** | **なし** | **HANG** |

  → RTC 2/2 成功・lid 4/5 成功・lid #7 のみ hang。次 boot は 21:41（約16分後＝強制電源）。16分で 0.7W のバッテリーは枯渇せず、長時間スリープ #3 も復帰済み → **バッテリー枯渇ではなく真の hang**。

**結論となる転換点**: s2idle 下でも hang が出た以上、**「ACPI S3 deep firmware が原因」説は棄却**。ただしログ上はどの hang も最終行が `PM: suspend entry` で区別不能、かつ pstore 不在で device 単位ログも取れないため、断定できる被疑は3候補:

- **(a) suspend-path hang**（寝る途中で固まる）
- **(b) resume-path hang**（起きる途中で固まる）
- **(c) LID0 wake を間欠的に取りこぼす**（カーネルは s2idle freeze で生存するが、蓋開け割り込み(LID0 notify)が時々配送されず起きない。今回 wake 源を LID0 のみに絞った構成で新たに浮上した候補）

  ※ (c) は「常に届かない」ではない。boot -1 で lid は 4/5 成功しており、**間欠故障**でなければデータと矛盾する。3候補いずれも「間欠的」である点に注意（lid 4/5・#7 のみ失敗）。

なお、観測された hang はいずれも userspace freeze 完了後（`Successfully froze unit 'user.slice'` → `Performing sleep operation 'suspend'` → `PM: suspend entry (s2idle)`）の **カーネル段**で停止している。systemd 抜きの `rtcwake -m mem` でも、この `/sys/power/state ← mem` 以降のカーネル suspend/resume 経路は lid 経路と同一なので、当該 hang の再現手段として妥当（rtcwake がバイパスするのは freeze/hook の userspace 段だけで、そこは今回すでに通過済み）。

**confound（要明記）**: s2idle 切替時に `i915.enable_dc=0` と `pcie_aspm=off` も同時に外した。boot -1 は S3 時代と3変数違う → 今回の hang が S3 時代の hang と同根とは断定しない（S3-firmware 棄却は変数に依らず成立）。

## 目的（このプランのゴール）

ユーザ選択により **案1: 能動 rtcwake ストレステスト** で (c) と (a)/(b) を切り分ける。RTC 起床は **LID0 を一切使わずカーネル内蔵 RTC アラームで起きる**ため、wake 配送経路を切り離せる:

- **RTC では一度も hang しない**（lid では hang する）→ 失敗は wake 配送固有 → **(c) LID0 取りこぼし**を支持。
- **RTC でも hang する** → wake 源に依らずコード経路の固着 → **(a)/(b) コード hang**（少なくとも (c) は除外）。

注意点:
- 本テストは **(c) vs (a)/(b) の切り分けのみ**。(a) と (b) の分離はしない。
- 故障は間欠的（lid 4/5 成功）。RTC も間欠的に hang する可能性があるため「N 回 hang 0」は (c) を**確率的に支持するだけで確定ではない**。N を十分大きく取る。
- 「RTC clean」は (c) の**必要条件であって十分条件ではない**。(c) を積極確定するには、後段で次に lid hang した時に電源ボタン短押しで復帰するか（案2）を見るのが本筋。案1 はまず「RTC でも固まるか？」を能動的に確かめ、(a)/(b) を**反証/支持**する位置づけ。

## 前提・環境

- 操作対象: `ssh miminashi@macbookair2015.lan`（Debian 13 / kernel `6.12.90+deb13-amd64`）
- 現状: AC 接続済み（ADP1 online, 83% Charging）、`/sys/power/mem_sleep` = `[s2idle] deep`、enabled wakeup = LID0 のみ。`/usr/sbin/rtcwake` 存在。
- 現 boot(0) は 8 cycle 全て graceful で健全。
- **物理前提**: テスト中に hang したら ssh 越しには直せない。**ユーザが実機の電源長押しで復帰**させる必要がある。テストは AC 接続・蓋を開けたまま・実機の前にいられる時間帯に実施する。

## 作業内容

### 1. 調査結果のレポート作成（方針に依らず実施）

CLAUDE.md のレポートルールに従い `report/` 直下に作成:

- ファイル名: `report/<TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S>_s2idle_hang_rtcwake_discrimination.md`（**タイムスタンプは `TZ=Asia/Tokyo date` で取得、推測禁止**、日時は JST）
- 内容: 上記 Context の調査結果（s2idle 下 hang 再発の確定根拠、trigger→outcome 表、S3-firmware 棄却、3候補、3変数 confound）＋ 案1 の方針と手順。
- 過去レポートへのリンク: `2026-05-31_132125_s3_hang_switch_to_s2idle.md`。
- プランモード作業のため `## 添付ファイル` に本プランをコピーして添付:
  - `mkdir -p report/attachment/<レポート名>/`
  - `cp /home/miminashi/.claude/plans/ethereal-swimming-planet.md report/attachment/<レポート名>/plan.md`

### 2. メモリ更新

`memory/s2idle-observation-phase.md` を「s2idle でも hang 確認（2026-05-31）、contingency 通り device-resume 仮説へ pivot。現在は RTC ストレステストで (c)wake-not-delivered と (a)/(b)code-hang を切り分けるフェーズ」に更新。MEMORY.md の1行ポインタも追従。

### 3. rtcwake ストレステストの配備と実行

**ssh セッションは s2idle 中に切れる**（NetworkManager ASLEEP）ため、ループは**実機側にデタッチで常駐**させ、結果を**ディスクの logfile に各サイクル前後で sync 付き追記**する。こうすると hang→強制再起動を跨いでも「どのサイクルで ENTER 止まりか」が残り、pstore 不在でも**粗い hang 検出だけは電源断を越えて取れる**。

スクリプト `/usr/local/sbin/rtcwake-stress.sh`（配備）:

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

実行（デタッチ常駐）:

```bash
# プリフライト: AC online=1, mem_sleep=[s2idle], 蓋 open を確認
# 第1バッチ: 短時間サイクルで件数を稼ぐ
ssh ... 'sudo systemd-run --unit=rtcwake-stress /usr/local/sbin/rtcwake-stress.sh 60 90'
# 進捗確認（ssh は s2idle 中は切れるので、終了後 or 覚醒中に logfile を見る。ライブ追従は前提にしない）
ssh ... 'tail -n 20 /var/log/rtcwake-stress.log; systemctl is-active rtcwake-stress; systemctl is-failed rtcwake-stress'
```

- **第1バッチ**: `60` cycle × `-s 90`（短時間サイクルで件数を稼ぐ、約 1.7h）。注: #7 の意図スリープ長は不明（蓋を開けた時点で hang）なので「短時間が危険」とは断定せず、件数確保が目的。
- 第1バッチが全 graceful なら **第2バッチ**: `6` cycle × `-s 1800`（長時間スリープ相当、#3 の 5h40m ケースをカバー、約 3h+）。
- サイクル数・秒数は引数で可変。
- **`--collect` は使わない**（完走後もユニットを残し `systemctl status` で結果を見られるようにする）。次回テスト前に `systemctl reset-failed rtcwake-stress` で掃除する。
- 早期 wake（90s 未満で起きる）は hang ではない（`EXIT rc=0` が記録される）。本テストは hang（ENTER 止まり）だけを検出するので早期 wake は無害。

### 4. 結果の解釈

- **全サイクル EXIT 記録あり（hang 0）** → RTC 起床は clean。lid #7 と対比して **(c) LID0 wake 配送問題**を支持（確率的）。次フェーズで wake 源復活（電源ボタン等）の検討へ。
- **どこかで ENTER 止まり（machine 固着）** → ユーザが電源長押しで復帰 → 再起動後に logfile の最終 ENTER 行 + `check-suspend-resume.sh` で hang サイクルを確定 → **(a)/(b) コード hang**（(c) 除外）。RTC でも固まるなら wake 配送は無実。
- いずれもレポートに追記して観測フェーズを継続。

## 検証（テスト方法）

- 配備直後に `rtcwake-stress.sh 1 60` の1サイクルだけ試走し、logfile に `ENTER`/`EXIT rc=0` が両方記録され ssh で復帰することを確認（スクリプトと sync ログの健全性チェック）。
- 既存 `/usr/local/sbin/check-suspend-resume.sh` をテスト前後に実行し、boot 単位 suspend/resume カウントとデタッチログが整合することをクロスチェック。
- テスト完走の判定は **logfile の `DONE` 行**を正とする。ユニットは残置するので `systemctl status rtcwake-stress`（Active/Result）も併用できる。`--collect` を使わない前提のため is-active 表記には依存しない。

## クリーンアップ / 注意

- テスト用ユニット `rtcwake-stress` は完走後も残す（`systemctl status` で結果確認のため）。次回テスト前に `systemctl reset-failed rtcwake-stress` で掃除。`/usr/local/sbin/rtcwake-stress.sh` と `/var/log/rtcwake-stress.log` は次セッションの参照用に残置（恒久構成は変更しない）。
- 恒久設定（grub cmdline / udev wake 抑止 / mem_sleep）は**本プランでは変更しない**。テストは現行構成のまま実施する。
