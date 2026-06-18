# バッテリ枯渇時にハイバネーションさせる

## Context（背景・なぜ）

2026-06-07 23:37、バッテリ低下中に「シャットダウンしてしまった」件の調査。
ログ解析で **真の原因が判明** した:

- 23:37:38 `systemd-logind: Lid closed` → `Suspending...` → 23:37:39 `PM: suspend entry (s2idle)` が boot -1 の最終行。
- 次の起動は 3 時間 40 分後の 06-08 03:17（コールドブート）。
- **= 蓋を閉じて s2idle サスペンドに入り、残りバッテリが s2idle 中に放電し尽くして電源断（ハード電源喪失）した。** 正規シャットダウンですらない。

なぜハイバネーションしなかったか:
1. **UPower の `CriticalPowerAction` はサスペンド中は発火できない**（システムが止まっているので閾値監視も動かない）。実際の枯渇はサスペンド中に起きた。
2. 仮に起きていても現状設定では失敗する: `CriticalPowerAction=HybridSleep` かつ `AllowRiskyCriticalPowerAction=false` のため、UPower は「risky」として拒否し **PowerOff にフォールバック** する（= シャットダウン）。

つまり「低バッテリ→ハイバネ」は **二重に塞がれていた**。本タスクで両層を開ける。

## 調査で確定した事実（実機 macbookair2015.lan）

| 項目 | 値 | 評価 |
|---|---|---|
| RAM / Swap | 3.7Gi / 3.7Gi (`/dev/sda3`, UUID `65051de6…`) | image は収まる（使用 ~1.1Gi） |
| `/sys/power/disk` | `[platform] shutdown reboot suspend test_resume` | ハイバネ機能あり |
| `RESUME=` (initramfs conf.d) | `UUID=65051de6…` ＝ swap UUID 一致 | resume 配線 OK |
| initramfs resume hook | `scripts/local-premount/resume` 等 存在 | resume 配線 OK |
| systemd | 257 | suspend-then-hibernate のバッテリ連動対応 |
| RTC wakeup | `enabled`（`90-s2idle-wakeup-suppress.rules` は XHC1/RP01-06 のみ抑止、RTC は対象外） | STH の RTC wake 源 健全 |
| RTC wake 実績 | 過去テスト 68/68 clean（メモリ記載） | suspend→RTC-wake レグは実証済み |
| **ハイバネ成功履歴** | **なし（一度も実行されていない）** | **= resume は未検証。最大のリスク** |
| バッテリ健康度 | capacity 92.7%, energy-full 35.9Wh | 良好 |

## 既知のリスク（重要）

この機体は **s2idle resume hang の長い履歴** がある（report 各種）。ハイバネ resume は
s2idle とは別のコード経路（コールドブート→カーネルが image を復元）で、デバイス再初期化が
フルブート相当のため一般に s2idle resume より堅牢だが、**この機体で resume が完走するかは未検証**。
→ 設定を入れる前に **手動ハイバネ→電源投入→復帰** を必ず実機で確認する（物理操作が必要）。

## アプローチ（ゲート付き 3 段階）

### Step 0（ゲート・最優先）: ハイバネ resume の手動検証 — *物理操作が必要*

設定を一切入れる前に、ハイバネが「書き込み→電源断→次回コールドブートで復帰」まで
完走するか実機で確認する。ユーザの立会いが必須（復帰は電源ボタンを押す必要がある）。

```bash
# (a) awake からの素のハイバネ
ssh … 'sudo systemctl hibernate'
# → 機体の電源が落ちる。ユーザが電源ボタンで投入 → デスクトップが復元されれば OK
# 復帰後に確認:
ssh … 'journalctl -b 0 | grep -iE "hibernation: (writing|Image|Restoring)|PM: hibernation exit"; \
        journalctl --list-boots | tail -3'

# (b) STH のフルチェーン（suspend→RTC wake→hibernate）も検証
ssh … 'sudo systemctl suspend-then-hibernate'   # ※実施時は短い HibernateDelaySec を一時設定
```

**判定:**
- 復帰成功 → Step 1・2 へ進む。
- resume hang（黒画面/無反応） → **自動ハイバネは入れない**。ハード電源断と大差ない（むしろ
  起動不能で悪化）ため、別途検討（resume hang の原因切り分けが先）。ユーザに報告して停止。

### Step 1: UPower の critical action 修正（覚醒中の低バッテリ対策）

`/etc/UPower/UPower.conf` を編集（バックアップを取る）:

```ini
[UPower]
CriticalPowerAction=Hibernate
AllowRiskyCriticalPowerAction=true
```

- `CriticalPowerAction`: `HybridSleep` から変更。critical 時に RAM 給電を残す HybridSleep は不適。
- `AllowRiskyCriticalPowerAction`: `false`→`true`。これが無いと Hibernate/HybridSleep は
  拒否され PowerOff にフォールバックする（今回の塞がり要因の一方）。
- UPower.conf は GKeyFile 形式のためインラインコメント不可（コメントは行頭 `#`）。

その他の閾値（`PercentageAction=2.0` 等）は据え置き。`sudo systemctl restart upower` で反映。
→ **覚醒中** にバッテリが 2% に達したら自動ハイバネ。

### Step 2: suspend-then-hibernate 化（今回の実際の失敗＝サスペンド中放電 への直接対策）

蓋閉じで s2idle に入った後、**バッテリ低下時に RTC で自動起床してハイバネ** させる。
これが今回の枯渇死を直接防ぐ層。**方針＝バッテリ連動（自動）を採用**。

**重要（man 精読で確定）: バッテリ連動モードでは `sleep.conf` の変更は不要。**
systemd 257 のデフォルト挙動で「battery あり＋`HibernateDelaySec` 未設定」なら ACPI `_BTP`
低バッテリアラーム（<5%）で自動起床→ハイバネする。本機は `/sys/class/power_supply/BAT0/alarm`
が存在し `_BTP` 利用可を確認済み。`AllowSuspendThenHibernate` もデフォルトで有効。
→ 触るのは logind だけ。

1. logind drop-in `/etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf`:
   ```ini
   [Login]
   HandleLidSwitch=suspend-then-hibernate
   HandleLidSwitchExternalPower=suspend
   ```
   - `HandleLidSwitchExternalPower` は **明示が必須**: man に「completely ignored by default —
     an explicit value must be set」とあり、未設定だと `HandleLidSwitch` にフォールバックして
     **AC 時の蓋閉じも STH になってしまう**。AC 時は素の suspend に保つため明示する。

2. 反映: `sudo systemctl restart systemd-logind`（または再ログイン）。

**`sleep.conf` は変更しない理由（修正前プランの矛盾を是正）:**
- `HibernateOnACPower=` は man に「Only used … **when HibernateDelaySec= is set**」と明記。
  `HibernateDelaySec` 未設定（=バッテリ連動）では **完全に無視される no-op** なので入れない。
- `HibernateDelaySec` を設定すると逆に `_BTP` 経路が無効化され固定遅延の周期ポーリングになる。
  バッテリ連動を選んだので未設定のままにする。
- AC 接続中はそもそも放電しない→`_BTP` が発火しない→サスペンド維持。`HibernateOnACPower` に
  頼らずとも AC 時にハイバネしない挙動は満たされる。

## 変更ファイル一覧

| ファイル | 変更 |
|---|---|
| `/etc/UPower/UPower.conf` | `CriticalPowerAction`, `AllowRiskyCriticalPowerAction` |
| `/etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf` | 新規（`HandleLidSwitch`, `HandleLidSwitchExternalPower`） |

（`sleep.conf` は変更不要 — Step 2 参照。バッテリ連動 STH は systemd 257 のデフォルトで機能）

いずれも実機上の設定ファイル。リポジトリのコードは変更しない（report のみ作成）。

## 検証（Verification）

1. **Step 0 ゲート**（上記）: 手動 hibernate / suspend-then-hibernate で resume 完走を実機確認。
2. Step 1 反映後: 設定の反映を確認（`upower --dump` / UPower.conf 再読込）。閾値到達時の動作は
   バッテリ偽装ではなく実放電で 2% 到達時に 1 度観測する（or 受容）。
3. Step 2 反映後: 蓋を閉じ、バッテリ駆動で放置 → 後で `journalctl --list-boots` と
   `journalctl | grep -i "hibernation"` で「s2idle 後に RTC 起床→ハイバネ→復帰」が記録されるか確認。
4. 最終: バッテリを意図的に低くして蓋閉じ → 枯渇死せずハイバネに落ちることを確認（1 サイクル）。
5. レポート作成（`report/yyyy-mm-dd_hhmmss_low_battery_hibernate.md`、JST、前提/環境/再現手順/本プラン添付）。

## ロールバック

- UPower: バックアップから復元 or `CriticalPowerAction=PowerOff` に戻す。
- STH: logind drop-in を削除 → `HandleLidSwitch=suspend`（デフォルト）に戻る。
- いずれも再起動不要（各 daemon の restart で戻る）。

## 留意

- Step 2 は s2idle（suspend レグ）をそのまま使うため、既知の **s2idle resume hang の可能性は残る**。
  STH は「枯渇死を防ぐ」目的であり、s2idle hang 問題自体の解決ではない（別トラック）。
- s2idle hang 調査用の RTC ストレステスト資材（`/usr/local/sbin/rtcwake-stress.sh` 等）には触れない。
