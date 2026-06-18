# レポート作成プラン: バッテリ連動ハイバネ成功の実証と現行設定スナップショット

## Context（なぜこのレポートを作るか）

前回レポート [2026-06-15 _BTP 無効化修正](report/2026-06-15_234635_fix_battery_hibernate_btp.md) で、`alarm=0`（ACPI `_BTP` 無効化）により systemd-suspend-then-hibernate を RTC ポーリング推定経路へ強制する恒久修正を適用した。ただし**実使用での ≤5% ハイバネ実発火だけが未観測**で、ユーザ合意のもと「自然な低残量時に確認」という残課題が残っていた。

今回、その残課題が **実機で完全クローズ** した（6/17 23:09 に電池 3% でハイバネ発火 → イメージ作成 → boot_id 不変で resume 完走）。本レポートは **成功の実証と、現時点の電源管理まわり全設定のスナップショット保存**を主眼とする（将来の再構築・回帰時の基準点）。

## 実機調査で確定した事実（すべて ssh 実機で確認済み）

### 成功の決定的証拠（boot 0 = 2026-06-15 22:08 起動、現在も継続 / up 2日）

wall-clock ログ（INFO + kernel）:
```
6月 17 23:09:34 systemd-logind: Suspending, then hibernating...
6月 17 23:09:35 systemd-sleep: BAT0: Found battery with capacity below threshold (3% <= 5%).
6月 17 23:09:35 systemd-sleep: Performing sleep operation 'hibernate'...
6月 17 23:09:35 kernel: PM: hibernation: hibernation entry
   ── 23:09:36〜02:45:43 はジャーナル完全に空（"No entries"）＝ S4 で電源断 ──
6月 18 02:45:44 kernel: PM: hibernation: Creating image:        ← flush アーティファクト（後述）
6月 18 02:45:44 kernel: PM: hibernation: hibernation exit
6月 18 02:45:44 systemd-sleep: System returned from sleep operation 'suspend-then-hibernate'.
```

**タイムスタンプの正しい解釈（誤読防止・本文に必ず明記）**: monotonic で見ると `hibernation entry [10069.68]` → `Creating image [10075.41]` → `hibernation exit [10075.70]` は**約 6 秒**しかない（monotonic クロックは電源断中は停止）。実際の流れは:
1. 6/17 23:09:35 に 3% でハイバネ開始、**約 6 秒でイメージ作成完了**（327979 pages / 約 1.26GiB、`516.99 MB/s`）→ 電源断。
2. **23:09:36〜02:45:43 はジャーナルが 1 行も無い ＝ 約 3h36m 完全に S4 電源断**（枯渇死ではなく正常な S4）。
3. 6/18 02:45:44 に電源ボタンで resume、kernel がイメージを復元。

→ wall-clock で `Creating image`/`hibernation exit` が 02:45:44 に並ぶのは、**電源断中に ring buffer へ溜まった kernel 行が resume 時にまとめて journald へ flush された際の付与タイムスタンプ**であり、「イメージ作成に 3.5h かかった」わけではない。3.5h は S4 で電源断していた時間。

- 現在の boot_id `86ba1c2d-b717-4113-b09f-8c0e238c7817` = `journalctl --list-boots` の boot 0 と一致 → **コールドブートではなく S4 resume 完走**。
- 修正適用（6/15 22:08）以降コールドブート 0 回（枯渇死ゼロ）。
- ハイバネイメージ実測: 327979 pages コピー、`Allocated 1323508 kbytes`（約 1.26GiB）。swap 3.7G に余裕で格納（後述スナップショット）。

### 正直な caveat（advisor 指摘・必ず本文に明記）
- **3% で起床＝5% フロアを下回る軽度オーバーシュート**。前回レポートが警告した「5%→0% のマージン薄」リスクが（軽度に）現実化した実例。0% より十分上で書込成功したが、**前回の薄マージン懸念は依然有効**。「余裕十分」とは総括しない。
- **学習放電率ファイルの値 `3` は verbatim 記録に留める**。初回（6/15 2分テスト）は 29%/時、現在ファイルは `3`。systemd は cycle ごとに再推定するが、**29→3 の低下理由は未解決**（電池切替時の正確な容量が INFO ログから復元不能なため断定不可）。長時間 suspend leg が生存した事実を「放電が緩やか」の根拠にしてはならない（それらは AC 接続時の plain `suspend` であり因果が成立しない）。

## 現行設定スナップショット（本文に全文転記）

| 項目 | 現在値 |
|---|---|
| 機種 / OS | MacBook Air 11" (Early 2015) / Debian 13 (trixie) |
| kernel | `6.12.90+deb13-amd64` |
| systemd | 257 (257.9-1~deb13u1) |
| `/proc/cmdline` | `… ro quiet no_console_suspend mem_sleep_default=s2idle` |
| `GRUB_CMDLINE_LINUX_DEFAULT` | `quiet no_console_suspend mem_sleep_default=s2idle` |
| `/sys/power/mem_sleep` | `[s2idle] deep` |
| `/sys/power/disk` | `[platform] …` |
| `/sys/class/power_supply/BAT0/alarm` | `0`（_BTP 無効・修正の核心） |
| DMI Wake-up Type | `Power Switch`（修正が必要だった構造的理由） |
| swap / RESUME | `/dev/sda3` UUID `65051de6…`（swap 3.7G ≈ RAM 3.7G、今回 1.26GiB イメージを実際に格納成功）、`/sys/power/resume=8:3`、`resume_offset=0`、initramfs resume hook あり |
| 学習放電率ファイル | `/var/lib/systemd/sleep/battery_discharge_percentage_rate_per_hour` = `13729338060412566372 3`（hash + rate%/h、verbatim） |

設定ファイル全文（本文にコードブロックで転記）:
- `/etc/udev/rules.d/99-disable-battery-trip-point.rules`（`ATTR{alarm}="0"`）
- `/etc/systemd/sleep.conf.d/20-battery-hibernate.conf`（`SuspendEstimationSec=30min`）
- `/etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf`（`HandleLidSwitch=suspend-then-hibernate` / `HandleLidSwitchExternalPower=suspend`）
- `/etc/UPower/UPower.conf` 抜粋（`CriticalPowerAction=Hibernate`, `AllowRiskyCriticalPowerAction=true`）

クリーンアップ確認:
- `systemd-suspend-then-hibernate.service.d/` のデバッグ drop-in は撤去済み（ディレクトリ不在）。
- cmdline 履歴: `pcie_aspm=off`/`pm_print_times` は 5/23 (5f65b66) で S3 hang 対策に追加 → S3→s2idle 恒久切替 (85548c5 / 2026-05-31) で「s2idle 消費電力を悪化させる失敗パラメータ」として意図的に除去。現状が正。

### ログ可視性の注記
6/15 の `Set timerfd`/`Estimating discharge rate` の冗長ログは当時の `SYSTEMD_LOG_LEVEL=debug` 窓でのみ出力。debug 撤去後の 6/17 は INFO レベルの `capacity below threshold (3%)` と kernel hibernation 行のみ残る（機構は同一、ログレベルの差）。

## レポート構成（出力するファイル）

- ファイル名: `report/yyyy-mm-dd_hhmmss_hibernate_success_snapshot.md`
  - タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得（推測しない）
- セクション: タイトル / 実施日時(JST) / 添付ファイル / 前提・目的 / 環境情報 / **成功の実証**（ログ＋boot_id 不変）/ **現行設定スナップショット**（上表＋全文転記）/ **caveat・残課題**（3% オーバーシュート、放電率 29→3 未解決、s2idle resume hang は別トラック既知リスク）/ 過去レポートへのリンク / 再現・確認方法（成功確認 grep）
- 過去レポートリンク: 2026-06-15（修正）, 2026-06-08（初回 STH）, s2idle hang 調査
- **添付（CLAUDE.md 必須ルール）**: `report/attachment/<reportname>/plan.md` に本プランファイルをコピーし、本文「## 添付ファイル」からリンク

## 検証（レポート作成後）
- `report/` 直下への Write で Discord 通知 hook が発火することを確認
- 添付プランファイルへの相対リンクが正しいことを確認
