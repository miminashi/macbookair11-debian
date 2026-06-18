# バッテリ枯渇時にハイバネーションさせる対応レポート

- **実施日時**: 2026年6月8日 03:50 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-08_035056_low_battery_hibernate/plan.md)

## 前提・目的

- **背景**: 2026-06-07 23:37 頃、バッテリ低下中の MacBook Air が「ハイバネーションせずにシャットダウンしてしまった」とユーザから報告。
- **目的**: 原因を特定し、可能ならバッテリ低下時にハイバネーションするよう恒久設定する。
- **前提条件**:
  - 操作対象は別ホストの実機 MacBook Air 11" (Early 2015) `macbookair2015.lan`、ssh 経由で診断・修正。
  - 本機は 2026-05-31 にスリープモードを ACPI S3 → **s2idle へ恒久切替**済み（参照: [s2idle 切替レポート](2026-05-31_132125_s3_hang_switch_to_s2idle.md)）。蓋閉じで s2idle サスペンドに入る運用。
  - s2idle resume hang の長い調査履歴があり、ハイバネ(S4)経路は本機で**一度も検証されていなかった**（参照: [s2idle hang 切り分けレポート](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)）。

## 環境情報

- 機種: MacBook Air 11" (Early 2015), `macbookair2015.lan`
- OS: Debian 13 (trixie), kernel `6.12.90+deb13-amd64`
- systemd: 257 (257.9-1~deb13u1) / UPower 1.90.9
- RAM 3.7GiB / Swap 3.7GiB（`/dev/sda3` partition, UUID `65051de6-9fb3-4588-8f89-3b9cd714e859`）
- ストレージ: `/dev/sda`（sda1 EFI 976M / sda2 ext4 root 93.1G / sda3 swap 3.7G）
- ハイバネ配線: `RESUME=UUID=65051de6…`（swap UUID と一致）、initramfs に resume hook あり、`/sys/power/disk` = `[platform] …`
- バッテリ: capacity 92.7%（健康度良好）、energy-full 35.9Wh、`/sys/class/power_supply/BAT0/alarm` 存在（ACPI `_BTP` 利用可）

## 原因（ログ解析で確定）

枯渇直前のブート（boot -1, `db743a1d…`）の最終ログ:

```
6月 07 23:37:38 systemd-logind[805]: Lid closed.
6月 07 23:37:38 systemd-logind[805]: Suspending...
6月 07 23:37:39 systemd[1]: Starting systemd-suspend.service - System Suspend...
6月 07 23:37:39 systemd-sleep[378612]: Performing sleep operation 'suspend'...
6月 07 23:37:39 kernel: PM: suspend entry (s2idle)        ← boot -1 の最終行
```

次の起動は 3 時間 40 分後（06-08 03:17 コールドブート）。

→ **蓋を閉じて s2idle サスペンドに入り、残りバッテリが s2idle 中に放電し尽くして電源断（ハード電源喪失）した。** 正規シャットダウンですらない。

なぜハイバネしなかったか — **「低バッテリ→ハイバネ」が二重に塞がれていた**:

1. **UPower の `CriticalPowerAction` はサスペンド中は発火できない**（システムが停止しており閾値監視も動かない）。実際の枯渇はサスペンド中に発生した。
2. 仮に覚醒中に閾値到達しても失敗する設定だった: `CriticalPowerAction=HybridSleep` かつ `AllowRiskyCriticalPowerAction=false` のため、UPower は「risky」として拒否し **PowerOff（シャットダウン）にフォールバック**する。

## 対応内容

ゲート（ハイバネ実機検証）→ 設定適用、の順で実施。

### Step 0: ハイバネ resume の実機検証（ゲート）— **合格**

設定を入れる前に、本機でハイバネが完走するか物理操作込みで確認した（復帰は電源ボタン押下）。

- **0a) awake からの素のハイバネ**: `sudo systemctl hibernate` → 電源断 → 電源投入で **boot_id 不変のまま resume 完走**。
  - `PM: hibernation: Creating image:` / `Reached target hibernate.target` / `PM: hibernation: hibernation exit` / `Restarting tasks ... done.`、`journalctl --list-boots` に新ブートなし。
- **0b) suspend-then-hibernate フルチェーン**: 一時的に `HibernateDelaySec=20s` と `HibernateOnACPower=yes` を設定し（テストは AC 接続中に実施したため、AC でもハイバネに落ちるよう後者を明示）、`sudo systemctl suspend-then-hibernate` → s2idle→RTC 起床→ハイバネ→電源断→電源投入で復帰。boot_id 不変。
  ```
  03:47:41 PM: suspend exit / System returned from 'suspend-then-hibernate'   ← s2idle から RTC 起床
  03:47:41 Performing sleep operation 'hibernate'...
  03:48:32 PM: hibernation: Creating image: / hibernation exit / Restarting tasks ... done.
  ```
- → 本機でハイバネの書き込み・電源断・復帰、および s2idle からの連結ハイバネが**すべて正常動作**することを実証。テスト用一時設定 `99-sth-test.conf` は撤去済み。

### Step 1: UPower の critical action 修正（覚醒中の低バッテリ対策）

`/etc/UPower/UPower.conf`（変更前をバックアップ: `UPower.conf.bak.20260608_034937`）:

| キー | 変更前 | 変更後 |
|---|---|---|
| `CriticalPowerAction` | `HybridSleep` | `Hibernate` |
| `AllowRiskyCriticalPowerAction` | `false` | `true` |

`PercentageAction=2.0` は据え置き。`systemctl restart upower` で反映。
→ **覚醒中**にバッテリが 2% に達したら自動ハイバネ（従来はシャットダウンしていた）。

### Step 2: suspend-then-hibernate 化（サスペンド中放電＝今回の実故障への直接対策）

`/etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf`（新規）:

```ini
[Login]
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=suspend
```

- バッテリ駆動の蓋閉じ → s2idle に入り、systemd 257 のバッテリ連動（ACPI `_BTP` を wake 源に、systemd 内部しきい値の 5% 未満で自動起床）で、**バッテリが尽きる前にハイバネへ移行**する。
- `HandleLidSwitchExternalPower=suspend` は**明示が必須**（未設定だと `HandleLidSwitch` にフォールバックし AC 時の蓋閉じも STH 化してしまう）。AC 時は素の suspend を維持。
- **`sleep.conf` は変更不要**: `HibernateDelaySec` 未設定＝バッテリ連動モード。`HibernateOnACPower` は man 上「`HibernateDelaySec` 設定時のみ有効」のため未設定では no-op。本機は `_BTP` 利用可を確認済み。
- `systemctl restart systemd-logind` で反映。

## 適用後の最終状態（検証）

```
UPower:  PercentageAction=2.0 / AllowRiskyCriticalPowerAction=true / CriticalPowerAction=Hibernate   (active)
logind:  HandleLidSwitch=suspend-then-hibernate / HandleLidSwitchExternalPower=suspend               (active)
sleep:   HibernateDelaySec 未設定（バッテリ連動）/ sleep.conf.d は空（テスト設定撤去済み）
_BTP:    /sys/class/power_supply/BAT0/alarm = 300000（利用可）
```

これにより、低バッテリ時のハイバネ経路が 2 層で確保された:

- **覚醒中** にバッテリ 2% 到達 → UPower が Hibernate。
- **s2idle サスペンド中**（蓋閉じ・バッテリ駆動）にバッテリ低下（_BTP <5%）→ 自動起床して Hibernate。今回の枯渇死を直接防ぐ。

## 残課題・留意

- Step 2 は s2idle（suspend レグ）をそのまま使うため、既知の **s2idle resume hang の可能性は残る**（別トラックの調査対象）。本対応は「枯渇死を防ぐ」目的であり、s2idle hang 自体の解決ではない。
- バッテリ連動（_BTP <5%）の実発火は実放電を要するため、本レポート時点では未観測（機構は Step 0b で実証済み）。次回バッテリ駆動で長時間蓋閉じした際に `journalctl | grep -i hibernation` で確認するとよい。

## 検証の限界・チューニング余地

報告の結論（ハイバネ機構は健全、設定で2層の枯渇死防止を確保）は変わらないが、以下は検証上の限界・調整余地として明記する。

1. **ハイバネ検証（Step 0a/0b）は AC 接続・充電状態で実施した**
   テスト時のバッテリは 47%→54%（充電中）。すなわちハイバネの**機構**は実証できたが、実際の**低バッテリ・低電圧の電気的条件下**では未検証。低残量時に挙動が変わる可能性は低いものの、厳密には別条件である。

2. **`PercentageAction=2.0`（覚醒時ハイバネのトリガ閾値）が非常に低い**
   覚醒中の UPower→Hibernate は残り **2%** でしか発火しない。本機のバッテリは約11年もの（capacity 表示は 92.7% だが燃料計の精度は不明）で、2% からハイバネ書き込みを完了する余裕が乏しい恐れがある。**5% 程度への引き上げ**で安全マージンを確保する調整余地がある（本対応では既定値を据え置いた）。

3. **枯渇直前のバッテリ推移は実測できていない（強い推論）**
   原因セクションの「残バッテリが放電し尽くして」は強い推論であり、正確な % や放電率はログに残っていない。唯一の具体的アンカーは **2026-06-07 23:10:26 の `localsearch-3: Running on LOW Battery, pausing`**（UPower の PercentageLow=20% 以下を示す）で、蓋閉じ（23:37:38）の**約27分前には既に残量20%以下**だったことが分かる。なお LOW Battery 警告は 6/4・6/6 にも出ており、常用で繰り返し低残量に達していた。

   （補足・軽微: fstab のコメントは「swap was on /dev/sdb3」だが実際の swap は `/dev/sda3`＝UUID 指定のため無害な表記ずれ。コールドブート時の `PM: Image not found (code -22)` はその時点でイメージが無いだけの正常メッセージ。）

## 今後の提案（未実施・次回検討）

### 覚醒時ハイバネ閾値（`PercentageAction`）の引き上げ

「検証の限界・チューニング余地」項目2 の具体策。現状は `PercentageAction=2.0`（残2%でハイバネ実行）だが、約11年もののバッテリでは**残量計の誤差・低残量域の電圧サグ**により、2% を指す前に電源喪失する恐れがある。**実行レベルを引き上げ**て書き込み完了の確実性を上げる（その代わり数%の使用可能残量を捨てるトレードオフ）。

UPower のしきい値は本来 `Action < Critical < Low` の順（警告→警告→実行）を保つべき。現状は `Low=20 / Critical=5 / Action=2`。引き上げる場合の案:

- **案A（穏当）**: `PercentageAction=4.0`（`Critical=5` の下に保ち、のりしろを少し増やす）
- **案B（安全寄り）**: `PercentageAction=5.0` かつ `PercentageCritical=10.0`（実行を 5% に上げ、警告段階を上にずらして順序維持）。`Low=20` 据え置き。

適用例（案B）:

```bash
ssh miminashi@macbookair2015.lan 'sudo sed -i -E \
  "s/^PercentageAction=.*/PercentageAction=5.0/; s/^PercentageCritical=.*/PercentageCritical=10.0/" \
  /etc/UPower/UPower.conf && sudo systemctl restart upower'
```

**影響範囲の注意**: この調整が効くのは**覚醒中にバッテリを使い切る経路のみ**。今回の実故障（蓋閉じ・サスペンド中の枯渇）に効く suspend-then-hibernate 側の起床閾値は **systemd 内部の「5% 未満」固定**で、`PercentageAction` では変更できない。本提案は「覚醒したまま放置して使い切る」ケースの保険強化という位置づけ。

## 再現方法（検証手順）

```bash
# 原因確認（枯渇直前ブートの末尾）
ssh miminashi@macbookair2015.lan 'journalctl -b -1 | tail -60'
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail'

# ハイバネ resume 検証（物理操作: 電源断後に電源ボタンで起動）
ssh miminashi@macbookair2015.lan 'sudo systemctl hibernate'
ssh miminashi@macbookair2015.lan 'journalctl -b 0 | grep -iE "hibernation: (Creating|Image)|hibernation exit"'

# STH フルチェーン検証（一時的に短い遅延を設定）
ssh miminashi@macbookair2015.lan 'sudo tee /etc/systemd/sleep.conf.d/99-sth-test.conf <<EOF
[Sleep]
HibernateDelaySec=20s
HibernateOnACPower=yes
EOF'
ssh miminashi@macbookair2015.lan 'sudo systemctl suspend-then-hibernate'   # 後で 99-sth-test.conf を削除

# 設定適用
ssh miminashi@macbookair2015.lan 'sudo sed -i -E "s/^CriticalPowerAction=.*/CriticalPowerAction=Hibernate/; s/^AllowRiskyCriticalPowerAction=.*/AllowRiskyCriticalPowerAction=true/" /etc/UPower/UPower.conf'
ssh miminashi@macbookair2015.lan 'sudo systemctl restart upower'
ssh miminashi@macbookair2015.lan 'sudo tee /etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf <<EOF
[Login]
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=suspend
EOF'
ssh miminashi@macbookair2015.lan 'sudo systemctl restart systemd-logind'

# 実効確認
ssh miminashi@macbookair2015.lan 'systemd-analyze cat-config systemd/logind.conf | grep -iE "HandleLidSwitch"'
ssh miminashi@macbookair2015.lan 'grep -E "^(CriticalPowerAction|AllowRiskyCriticalPowerAction)=" /etc/UPower/UPower.conf'
```

## ロールバック

```bash
# UPower
ssh miminashi@macbookair2015.lan 'sudo cp -a /etc/UPower/UPower.conf.bak.20260608_034937 /etc/UPower/UPower.conf && sudo systemctl restart upower'
# STH
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/logind.conf.d/10-suspend-then-hibernate.conf && sudo systemctl restart systemd-logind'
```
