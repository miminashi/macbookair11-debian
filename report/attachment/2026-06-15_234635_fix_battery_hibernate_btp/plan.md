# バッテリ連動 suspend-then-hibernate を成立させる調査・対策プラン

## Context（背景・目的）

ユーザの最終ゴールは **「蓋を閉じたら s2idle で sleep し、蓋を閉じたままバッテリが尽きそうになったら（バッテリ駆動の判断で）ハイバネする」**＝ systemd の suspend-then-hibernate（STH）バッテリ連動動作そのものを成立させること。

調査の結果、この機構が **本機では発火しておらず**、前回 2026-06-08 で設定した STH は実際には「s2idle のまま放電死」していたことが判明した（イメージ未書込）。本プランは「設定一発」ではなく、**なぜバッテリ連動の自動ハイバネが発火しないかを実機実験で切り分け、成立させる**ための調査ラダーである。ユーザは一時的な実用性低下を許容している。

参照: [低バッテリ時ハイバネ対応レポート](../../projects/macbookair11-debian/report/2026-06-08_035056_low_battery_hibernate.md)（Step 0a/0b でハイバネ**実行**自体は本実機実証済み）。

## 診断（今回の調査で確定した事実）

実機 `macbookair2015.lan`（Debian 13 / kernel 6.12.90 / systemd 257）の `journalctl` 解析より:

1. **STH 自動ハイバネが一度も発火していない**。boot 0 起動時 `PM: Image not found (-22)` ＝ ハイバネイメージは一度も書かれていない。
2. **核心の証拠（曖昧さのない確証）**: `_BTP` トリップ点は `alarm=300000 / charge_full=4747000` ＝ **約 6.3%** に設定されている。最終サイクル（2026-06-15 01:59:23 に s2idle 突入）は **コールドブート（残≒0%）まで放電した＝必ず 6.3% トリップを横切った**にもかかわらず、`Image not found` ＝ ハイバネが実行されていない。**＝ `_BTP` トリップ起床→ハイバネのエスカレーションが確実に失敗している**。
   - 補足（弱い傍証）: 直前 2026-06-14 23:00 に `LOW Battery`（残 <20%）が出た後、23:11 蓋閉じ→ s2idle に 2h48m 居座り（復帰は RTC ではなく **ユーザの蓋開け**）。ただしこの時間帯の残量は 6.3% トリップより上だった可能性が高く、**発火しなかったこと自体はバグの確証にはならない**（トリップ未到達なら正常挙動）。確証はあくまで上記の最終サイクル（0% まで放電＝トリップ確実横断）。
3. **systemd 257 STH のバッテリ連動仕様**（man `systemd-sleep.conf` で確認）:
   - `HibernateDelaySec` 未設定時、バッテリ**搭載**機は放電率推定ベースで動く（「2h デフォルト」は**非搭載機向け**であり本機には適用されない）。
   - ACPI `_BTP`（battery trip point, `/sys/class/power_supply/BAT0/alarm` で露出, 本機は `300000` で利用可）が使えればそれを wake 源にする。`_BTP` が無い場合のみ `SuspendEstimationSec`（既定60min）で**定期的に RTC 起床**して放電率を測る（last resort）。
4. **学習状態が空**: `/var/lib/systemd/sleep/` が存在しない（放電率の学習値を一度も保存できていない）。バッテリは charge ベース（`charge_now/charge_full` あり、`energy_*`/`power_now` は NA）。
   - 注: `current_now=0` は Full/AC で読んだため不確定。推定は `charge_now` の差分で行うため、この値単独を根拠にしない。

→ **結論**: ハイバネ実行は健全だが、「s2idle 中にバッテリ低下を検知してハイバネへエスカレートする」トリガ機構が本機で機能していない。なぜ機能しないか（`_BTP` 起床が s2idle を起こせない / 放電率推定が破綻 / アラーム未武装 のいずれか）は**未確定**であり、推測ではなく**実機のデバッグログで観測**して切り分ける。

## 前提・制約

- 操作は全て ssh 経由（`ssh miminashi@macbookair2015.lan '...'`）。sudo は NOPASSWD。
- **物理操作が必要**: AC を抜く（バッテリ駆動化）、蓋を閉じる／開ける、復帰時の電源ボタン押下はユーザが実機で行う。ssh 側からはコマンド投入・ログ採取・電源状態確認を担う。
- ハイバネ実行・配線は実証済み（0b）。本プランで触るのは**トリガ機構の設定のみ**。
- 各段は **検証ゲート**（短い試験値で実発火を確認 → 本番値）を必ず通す。前回の失敗は「機構は実証済み・実発火は未観測」のまま本番投入したことなので、同じ轍を踏まない。

## 調査ラダー（上の段から試し、達成できなければ下の段へ。最下段は必ず枯渇死を止める floor）

### Step 1（最優先・低コスト・決定的）: 1サイクル分のデバッグログ採取

discharge を待たずに「systemd が何を計算し、どの wake 源をどう武装したか」を直接観測する。

1. STH サービスにデバッグログ drop-in を一時投入:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo mkdir -p /etc/systemd/system/systemd-suspend-then-hibernate.service.d && \
     sudo tee /etc/systemd/system/systemd-suspend-then-hibernate.service.d/99-debug.conf <<EOF
   [Service]
   Environment=SYSTEMD_LOG_LEVEL=debug
   EOF
   sudo systemctl daemon-reload'
   ```
2. ユーザ操作: **AC を抜く** → 蓋を閉じて s2idle 突入 → 数分待つ → 蓋を開けて復帰（フル放電は不要）。
3. ログ採取・解析:
   ```bash
   ssh miminashi@macbookair2015.lan 'journalctl -u systemd-suspend-then-hibernate.service -b --no-pager | \
     grep -iE "battery|discharg|estimat|trip|_BTP|alarm|rtc|wakeup|interval|hibernat|capacity"'
   ```
4. 判定（このログで分岐が決まる）:
   - systemd が**正常な放電率と妥当な wake 間隔／trip を算定し武装**している → Step 2A へ（実放電で発火確認）。
   - `_BTP`（`/sys/.../alarm` 書込）を武装したが s2idle で起床しない疑い、または**放電率算定が破綻**（rate=0／NaN／武装せず） → Step 2B へ。
5. 後始末: 調査完了後に `99-debug.conf` は撤去。

### Step 2A: ネイティブ・バッテリ連動が「使えそう」な場合 → 実発火を確認

Step 1 のログで「systemd が `_BTP` トリップを武装している（RTC ポーリングではなく `_BTP` 経路）」と分かった場合、**トリップ横断時に実際に起床→ハイバネするか**を確認する。本番のトリップは ~6.3% と低く検証に時間がかかるため、**トリップ点を一時的に高く設定して短時間で試す**:

- トリップ点を引き上げて即試験（例 50% 相当）:
  ```bash
  # charge_full≒4747000 の 50% ≒ 2373000 をトリップに設定（systemd が STH 開始時に上書きする可能性あり→Step1ログで確認）
  ssh miminashi@macbookair2015.lan 'echo 2373000 | sudo tee /sys/class/power_supply/BAT0/alarm'
  ```
- ユーザ操作: AC を抜き、現在残量がトリップ（上の例なら 50%）より少し上の状態で蓋を閉じて s2idle → 放電がトリップを横切る → **`_BTP` 起床 → ハイバネ → 電源断**。電源ボタンで復帰。
- 確認: `journalctl -b -1 | grep -iE "PM: suspend exit|hibernation: Creating image|hibernation exit"` と `journalctl --list-boots`（boot_id 不変なら成功）。
- **`_BTP` 起床→ハイバネを実機で観測できたら採用**。これが最もユーザのゴールに近い。本番はトリップ点を適切な低残量（例 10–15%＝余裕を持たせた値、6.3% は書込完了に厳しい恐れ）に設定。トリップ点の永続化方法（udev rule か起動時 oneshot）も併せて決める。
- もし Step 1 で「`_BTP` ではなく RTC ポーリング経路」だった場合は、本段ではなく Step 2B（`SuspendEstimationSec` 調整）で扱う。

### Step 2B: ネイティブが破綻している場合 → RTC ポーリングを強制 or 自前ポーラ

`_BTP` 経路が本機の s2idle を起こせない／放電率推定が破綻している場合:

- まず `SuspendEstimationSec` を短く設定（例 5–10min）して、systemd が RTC で定期起床→残量チェック→低ければハイバネ、に入れるか確認する。
  - 注意: man 上 RTC ポーリングは「`_BTP` が使えない時の last resort」。`_BTP` が露出している本機では systemd が `_BTP` を優先し、`SuspendEstimationSec` が効かない可能性がある。Step 1 のログで「どちらの経路か」を見て判断する。
- それでも RTC ポーリング経路に入れない場合は、**自前の軽量ポーラ**（s2idle で `/sys/class/rtc/rtc0/wakealarm` に N 分後を設定 → 起床 → 残量 < 閾値ならハイバネ、でなければ再武装して再 s2idle）を検討。STH の RTC フォールバックを最小実装で再現するもの。設計の是非はログ結果を見てから判断。
- いずれも**検証ゲート**: 短い試験値（例 `SuspendEstimationSec=2min`）で「s2idle→ RTC 起床→（低残量なら）ハイバネ」を実機で観測してから本番値。

### Step 3（FLOOR・必ず到達できる安全網）: 明示 `HibernateDelaySec` タイマー

ネイティブのバッテリ連動が本機ハードで成立しないと判明した場合の確実な着地点。**バッテリ連動ではない**が、s2idle に居座り続けず必ず一定時間でハイバネするため**枯渇死は止まる**。0b で本実機実証済みの経路。

```bash
ssh miminashi@macbookair2015.lan 'sudo tee /etc/systemd/sleep.conf.d/20-hibernate-delay.conf <<EOF
[Sleep]
HibernateDelaySec=20min
EOF'
```
- 検証ゲート: まず `HibernateDelaySec=60s` で試験 → 「蓋閉じ(電池)→ s2idle → 60秒後 RTC 起床 → `PM: hibernation: Creating image` → 電源断 → 電源ボタンで boot_id 不変 resume」を実機確認 → その後 20min 等の本番値へ。
- 値は短いほど放電死に強いが書込頻度が上がる。20min を初期値とし運用で調整。

## 検証（共通の成功条件）

どの段でも「実発火」を以下で確認してから本番値にする:

```bash
# サイクル後
ssh miminashi@macbookair2015.lan 'journalctl -b -1 --no-pager | grep -iE "PM: suspend (entry|exit)|hibernation: Creating image|hibernation exit|Restarting tasks"'
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail'   # 復帰サイクルで boot_id が変わっていない＝ resume 成功
ssh miminashi@macbookair2015.lan 'cat /sys/class/power_supply/BAT0/{capacity,status}'
```

成功条件: `PM: hibernation: Creating image` が出てイメージが書かれ、電源断後に電源ボタンで **boot_id 不変のまま resume** 完走すること。

## 触るファイル（実機 `macbookair2015.lan`）

- `/etc/systemd/system/systemd-suspend-then-hibernate.service.d/99-debug.conf`（Step1, 一時・後で撤去）
- `/etc/systemd/sleep.conf.d/20-hibernate-delay.conf`（Step 3 floor、または試験用の短い `HibernateDelaySec`）
- `/sys/class/power_supply/BAT0/alarm`（Step 2A の `_BTP` トリップ点。試験で一時変更、本番は永続化方法を別途決定）
- `/etc/systemd/sleep.conf.d/` に `SuspendEstimationSec` の drop-in（Step 2B のみ）
- logind 側 `HandleLidSwitch=suspend-then-hibernate` は現状維持（変更しない）

## 後始末・記録

- 調査完了後、`99-debug.conf` とログレベル変更を撤去。
- CLAUDE.md のルールに従い `report/` に調査レポートを作成（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`、本プランを `report/attachment/<name>/plan.md` に添付、過去レポートへのリンク・環境情報・再現手順を記載）。
- メモリ `low-battery-hibernate.md` / `s2idle-observation-phase.md` を結果で更新（バッテリ連動 STH が本機で発火しなかった事実と、最終的に採用した段）。
