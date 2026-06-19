# ハングを回避しつつ S3 (deep) sleep を復活できるか — 切り分け実験 (firmware OK / lid wake OK / battery spurious wake=gpe70 特定)

- **実施日時**: 2026年06月18日 21:39〜23:38 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-18_233837_s3_revival_evaluation/plan.md)

## 前提・目的

MacBook Air 11" (Early 2015) / Debian 13 は、2026-05-31 に「復帰 hang」を理由に
ACPI S3 (deep) → s2idle へ恒久切替した（[2026-05-31 レポート](2026-05-31_132125_s3_hang_switch_to_s2idle.md)）。
だがその放棄判断は、**当時存在しなかった切り分け方法論（RTC ストレステスト + ssh 到達性
+ 電源ボタン復帰判定）を S3 に一度も適用しないまま**下されていた。s2idle 側ではこの方法論で
「真の resume hang」と「wake 配送失敗」を分離できており（[2026-06-01](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md) /
[2026-06-03](2026-06-03_123439_pwrbtn_wake_premise_verification.md)）、総合レポート §8 自身が
「S3 時代の hang の一部は真の hang でなく wake 配送失敗だった可能性」を認めている
（[2026-06-18 通読版](2026-06-18_142303_why_not_s3_deep_sleep.md)）。

- **背景**: ユーザの主目的は**待機電力の低減**（s2idle 実測 0.70 W。S3 は RAM セルフ
  リフレッシュのみで桁違いに低い見込み）。lid wake 復活は副次。
- **目的（falsifiable）**: S3 を実機で一度も判定されなかった失敗モードについて判定する。
  結論は「復活可」も「棄却」も等しくあり得る、という前提で進めた。
- **失敗モードの 3 分法**: (1) 真の firmware hang（RTC でも戻らない）/ (2) suspend/resume
  コード hang / (3) i915/display resume 失敗（システム生存・画面だけ黒）。**ssh 到達性**を
  decisive discriminator とする。
- **前提条件**: 操作対象は ssh 接続先の実機 `macbookair2015.lan`。診断・設定は ssh 越し、
  lid 開閉・電源ボタン押下・AC 抜き差しはユーザの物理操作。物理立ち会い必須。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.90+deb13-amd64`
- スリープ: `/sys/power/mem_sleep` = `[s2idle] deep`（cmdline `mem_sleep_default=s2idle`、deep は runtime で選択可）
- 電源デバイス: AC=`ADP1`、電池=`BAT0`（`charge_*`/`voltage_now` 系。`energy_now` 非対応）
- swap/hibernate 配線・低バッテリ連動ハイバネは [2026-06-18 スナップショット](2026-06-18_053417_hibernate_success_snapshot.md) のまま据え置き
- 検証中、実機は **一度も再起動していない**（`boot_id` = `86ba1c2d…` 不変）。`suspend_stats`
  はこの boot で **success 21 → 58、fail=0**（全サスペンドで失敗ゼロ）
- 再利用した実機残置スクリプト: `/usr/local/sbin/rtcwake-stress.sh`,
  `/usr/local/sbin/pwrbtn-wake-test.sh`, `/usr/local/sbin/check-suspend-resume.sh`

## 結果サマリ

| 検証 | 条件 | 結果 |
|---|---|---|
| **A. firmware 隔離（RTC stress）** | deep, **AC**, lid open, RTC wake | smoke 1 + batch 20 = **21/21 clean**, fail=0, dmesg i915 含め全 `returned 0` |
| **B. lid 閉→開 wake（歴史的失敗モード）** | deep, **AC** | **7/7 復帰・画面正常**, i915 エラーなし, gpe70 で配送 |
| **C-1. battery で S3 維持** | deep, **battery**, LID0 wake 有効 | **約6秒で spurious wake**（決定論的・再現性あり） |
| **C-2. spurious wake 源の特定** | GPE mask 切り分け | **gpe70（LID0 _PRW wake GPE）と確定**。gpe4E(EC)/gpe4D/gpe52/PCI(TB)/USB(kbd) は除外 |
| **C-3. 緩和策の検証** | LID0 wake 無効化, battery | **S3 が 123s 完走**（gpe70 凍結）。n=1 |
| **C-4. 電源ボタン S3 wake** | deep, LID0 無効, battery | **成立**（elapsed 60s ≪ RTC 90s）。n=1 |
| **C-5. 実待機電力** | — | **未測定**（gauge ノイズ。下記） |

### 主目的（待機電力低減）の判定: **保留（go/no-go 未確定）**

有望（firmware・lid wake はいずれも健全、battery で寝続ける構成も存在）だが、採用前に
未解決の load-bearing が残る（後述「未解決の論点」）。**最大の問題は、肝心の待機電力を
一度も測れていないこと**。

## 主要な発見

### 1. S3 firmware suspend/resume は現行ベースラインで健全（境界つき）

`echo deep` の runtime 切替（cmdline は s2idle のまま＝再起動で安全側へ）で、RTC 起床の
S3 を 21 サイクル（90s×20 + smoke）連続実行し **全 clean**。さらに歴史的失敗モードである
**lid 閉→開**を 7 回踏んで **全て画面正常で復帰**、i915/drm エラーなし。journal は
`Preparing to enter system sleep state S3` → `Waking up from system sleep state S3` を毎回
記録し、**真の ACPI S3**（s2idle ではない）であることを確認。

**resume レイテンシ（実測）**: resume の最遅デバイスは **PCIe ルートポート `0000:00:1c.5`（RP06）の
`pci_pm_resume_noirq` で約 1.09 秒**（配下は AHCI `04:00.0` = SSD `sda`）。次いで **i915 `0000:00:02.0`
の `pci_pm_resume` が約 0.44 秒**（複数サイクルで一貫）。いずれも `returned 0`（正常）だが、S3 復帰の
体感レイテンシはこの 2 デバイスが律速。

> **境界**: clean データは**全て AC 給電**。lid サンプル 7 は、歴史的 hang 率（週0.7〜0.8件＝
> 推定数%/サスペンド）を統計的に排除できる数ではない（5%故障率なら7連続成功は確率0.70で生起）。
> 「firmware/lid resume は AC では健全」までが正確で、「S3 は安全」とは言えない。

### 2. S3 lid wake は display 込みで動作する（gpe70 経由）

s2idle では lid wake は構造的に不可能（lid 通知が EC GPE 相乗りで s2idle 中マスク、宣言 wake
GPE gpe70 は発火せず＝[2026-06-18 probe](2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe.md)）
だった。**S3 では lid 閉→開で gpe70 が発火し復帰**（7回の lid wake で gpe70 が +7 増加）。
s2idle で死んでいた gpe70（firmware _PRW 経路）が、S3 では wake 源として機能する。

### 3. 【新発見・最大の障壁】battery 駆動時、S3 は約6秒で spurious wake する

AC 給電では S3 が ≥90s 保つのに対し、**AC を抜くと S3 進入から約6秒で必ず起床**（複数回再現）。
真の S3 進入後の wake（abort ではない）。GPE mask による切り分けで源を特定:

- `gpe4E`（EC GPE, ~145回/秒）を **mask しても 6s で起床** → **EC は源ではない**
- `gpe4D` + `gpe52` を **mask しても 6s で起床**、増えたのは **gpe70 のみ** → 源は gpe70
- **LID0 を `/proc/acpi/wakeup` で無効化 → S3 が 123s 完走・gpe70 凍結** → **源 = gpe70（LID0 _PRW）と確定**
- PCI（Thunderbolt `07:00.0`）/ USB（内蔵キーボード `1-5`）の sysfs wake も無効化済みで無関係

すなわち **spurious wake と lid wake は gpe70 を共有**する。GPE 粒度では「spurious を殺すと
lid wake も死ぬ」トレードオフ。ただし **gpe70 が battery で lid 静止のまま自走する機序は未特定**
（phantom lid notify か GPE 0x70 共有かは不明。lid チャタリング等と断定はしない）。

> **証拠の性質（要・明記）**: 「AC では ≥90s 保つ」は時刻の異なる検証 A（AC・LID0 有効）と
> battery 検証の **cross-time 比較**であり、**同一セッションでの controlled A/B（AC で再現対照）は
> 未実施**。battery 固有性は強く示唆されるが直接対照では確定していない。また **battery hold（123s）と
> 電源ボタン S3 wake はいずれも n=1**（s2idle 時代の電源ボタン wake は 3/3 取得していたのに対し、
> S3 では今回 1 回のみ）。再現性は follow-up で要確認。

### 4. 主目的への脱出路の構成要素を確認（lid wake を犠牲・各 n=1）

主目的は待機電力なので「lid wake を捨てて低待機電力を取る」路線が成立し得る。その**構成要素が
それぞれ動くこと**を各 1 回ずつ確認した（路線そのものの成立＝低電力達成の確認ではない）:

- **LID0 wake 無効化** → battery でも S3 が寝続ける（C-3, n=1, 123s）
- **電源ボタンは S3 を起こす**（C-4, elapsed 60s ≪ RTC 90s, n=1）。これは **deep での電源ボタン
  wake を実機で初めて確認**したもの（2026-06-03 は s2idle の IRQ 駆動経路での実証であり、
  deep の `/proc/acpi/wakeup` 管轄では PWRB が載らず未確認だった）

→ **「LID0 wake off + 電源ボタン wake」は battery で S3 を寝続けさせ手動復帰できる構成**（lid wake は失う）。
ただし**この構成で実際に s2idle より低い待機電力が得られるかは未測定**（finding 5 / 未解決 #1）。
脱出路が「成立」と言えるのは電力測定をパスして初めてであり、現時点は**構成要素の動作確認（各 n=1）まで**。

### 5. 実待機電力は測定不能だった（gauge ノイズ）

`charge_now` は安静時/レジューム時に大きく再推定で跳ね（観測値 +3000 / -4000 / +4000 /
**-59000** µAh と符号すら不定）、S3 の微小消費（~0.1–0.2 W 想定）は短時間測定では完全に
埋もれる。s2idle 0.70 W が 12 時間測定だったのと同様、**S3 の正確な測定には数時間〜一晩の
連続 S3 が必要**（LID0 無効化で初めて可能になった）。**primary metric のデータはゼロ。**

**参考: 覚醒アイドルの battery 消費 ≈ 5.9〜7.5 W**（`current_now` 890mA@8.44V＝AC 抜き直後 →
のち 703mA）。これは「**6秒で spurious wake する S3 は実運用で破滅的**」であることを定量づける —
大半の時間を ~6W の覚醒状態で過ごせば、s2idle の 0.70 W すら大きく上回る。よって C-1 の battery
spurious wake は、解決しない限り S3 を待機電力目的に使えなくする致命的問題である（緩和策 C-3 が要る理由）。

## 補足観測（参考・結論には未反映）

調査中に観測したが上の結論には直接効かない事実。今後の手掛かりとして残す。

- **S3 resume 時に SSD の quirk メッセージ**: `ata1.00: LPM support broken, forcing max_power` /
  `ata1.00: unexpected _GTF length (8)` が S3 resume 経路で毎回出る。エラーではない既知系の警告。
- **`gpe4E`（EC GPE）≈ SCI 総数**: 累積 約 6.7M で SCI 総数とほぼ一致 → **SCI のほぼ全数が EC GPE**
  由来（覚醒中 ~145回/秒）。なお C-2 でこれを mask しても spurious wake は止まらず、源ではないと確定。
- **セッション中の battery 消費**: 91% → 82%（約9%）。大半は覚醒駆動（~6W）＋多数の S3 サイクル実験による。
- **PM device timing が journal に出ていた**: 本検証では `pm_print_times` 相当の per-device `PM: calling …/
  returned 0` が S3 経路で記録されており、上記 resume レイテンシ（RP06 / i915）の特定に使えた。

## 再現方法（実機手順）

```bash
# --- 共通: deep へ runtime 切替（cmdline は s2idle のまま＝再起動で復帰） ---
ssh miminashi@macbookair2015.lan 'echo deep | sudo tee /sys/power/mem_sleep'

# A. firmware 隔離（RTC stress, AC 給電・lid open）
ssh ... 'sudo systemd-run --collect --unit=s3-rtcwake-stress /usr/local/sbin/rtcwake-stress.sh 60 90 10'
#   注意: 高速巡回(睡眠90s+起床~10s=デューティ~10%)は ssh 到達性で監視不能。
#         オンディスクログ /var/log/rtcwake-stress.log が唯一の ground truth。

# B. lid 閉→開（logind を一時 suspend 化、RTC フォールバック）
ssh ... 'printf "[Login]\nHandleLidSwitch=suspend\nHandlePowerKey=ignore\n" | sudo tee /etc/systemd/logind.conf.d/99-test.conf; sudo systemctl kill -s HUP systemd-logind'
ssh ... 'sudo rtcwake -m no -s 240'   # RTC 安全網を仕込む（寝ない）
#   → ユーザが lid 閉→~30s→開。journal の Lid closed/opened と PM suspend entry/exit で判定

# C. battery spurious wake の切り分け（AC を抜く）
ssh ... 'echo mask | sudo tee /sys/firmware/acpi/interrupts/gpe4E'   # 可逆: unmask
ssh ... 'echo deep|sudo tee /sys/power/mem_sleep; sudo rtcwake -m mem -s 60'  # elapsed で hold/wake 判定
ssh ... 'echo LID0 | sudo tee /proc/acpi/wakeup'   # LID0 wake トグル → battery S3 が 123s 完走
#   GPE 増分は /sys/firmware/acpi/interrupts/gpe70 等を前後比較

# C-4. 電源ボタン S3 wake（LID0 無効・battery）
ssh ... 'sudo systemd-run --collect --unit=s3-pwrbtn /usr/local/sbin/pwrbtn-wake-test.sh 90 s3pwrbtn'
#   → ユーザが画面消灯後に電源ボタン短押し。elapsed≪90 なら成立
```

復元（既知良状態）:
```bash
ssh ... 'echo s2idle|sudo tee /sys/power/mem_sleep; \
  grep -q "LID0.*disabled" /proc/acpi/wakeup && echo LID0|sudo tee /proc/acpi/wakeup; \
  for g in gpe4E gpe4D gpe52; do echo unmask|sudo tee /sys/firmware/acpi/interrupts/$g; done; \
  sudo rm -f /etc/systemd/logind.conf.d/99-*.conf; sudo systemctl kill -s HUP systemd-logind; \
  echo 0|sudo tee /sys/class/rtc/rtc0/wakealarm'
```

## 未解決の論点（採用前に要決着・優先順）

1. **実待機電力（primary metric・データ皆無）**: LID0 wake 無効の battery S3 を**数時間〜
   一晩**連続させ、capacity/charge の大きな差分から W を算出し s2idle 0.70 W と比較する。
   **これが取り組み全体の go/no-go**。これ無しに復活可否は決まらない。
2. **battery hold の持続性（n=1, 123s のみ）**: 数時間スケールで gpe70 以外の低頻度 wake 源が
   出ないか未確認。上記 #1 の長時間測定が同時に検証になる。
3. **gpe70 spurious 発火の機序**: 未特定。機序が分かれば lid wake を温存したまま spurious だけ
   止める道（DSDT/quirk 等）があり得る。判明すれば「lid wake を犠牲」前提が外れる。
4. **低バッテリ連動ハイバネとの干渉**: S3 は完全停止のため心配されたが、**RTC wake は S3 で
   現に機能**（21/21＋全 rtcwake）しており、STH の時限ハイバネは RTC で起こせる以上たぶん
   機能する。**確定 blocker ではなく「要検証」**。

## 教訓（方法論）

- **高速 RTC 巡回では ssh 到達性は hang の discriminator にならない**。睡眠90s+起床~10s の
  デューティ約10%で、健全でも起床窓を取りこぼし続ける。本検証の序盤、これを誤って
  「真の firmware hang」と早合点したが、sync 済みオンディスクログ（21サイクル全 EXIT・
  boot_id 不変）で誤報と判明した。**高速巡回ではオンディスクログが唯一の真実**。ssh 到達性が
  正しく効くのは単発・長時間・立ち会いの安定状態（Ladder B/C）のみ。

## テスト資材（残置）

- 実機: `/usr/local/sbin/s3-power-measure.sh`（新規）、`/var/log/rtcwake-stress.s3-batch1-20cyc.*.log`
  （20サイクル clean の証拠）、`/var/log/pwrbtn-wake-test.log`、`/var/log/s3-power-measure*.log`
- 実機の永続設定は**未変更**（cmdline は `mem_sleep_default=s2idle` のまま）。実験中の deep/
  LID0/GPE/logind 変更はすべて runtime/drop-in で行い、検証後に既知良状態へ復元済み。
