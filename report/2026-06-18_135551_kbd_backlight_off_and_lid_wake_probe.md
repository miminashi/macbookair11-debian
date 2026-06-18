# スリープ改善: キーボードバックライト消灯フック導入 + s2idle lid wake 復活可否の精査

- **実施日時**: 2026年6月18日 13:55 (JST)
- **作業時間帯**: 同日 07:00〜13:55 (JST) ほか

## 添付ファイル

- [実装プラン](attachment/2026-06-18_135551_kbd_backlight_off_and_lid_wake_probe/plan.md)

## 前提・目的

ハイバネ調査で得たスリープ機構の知見（特に **s2idle の wake は IRQ/GPE 経路で決まり、`/proc/acpi/wakeup` は ACPI deep(S3) 用の表示**という理解）を活かし、実使用で残る 2 つの不満を改善する。

1. **スリープ中もキーボードバックライトが点灯したまま**（蓋を閉じても／開けたままでも発生）
2. **lid open で s2idle から復帰できない**（「復活させたい」→ 復活可能かを精査する）

### ユーザー要件（確定）
- **s2idle 復帰**: lid open で起きてほしい。たまの取りこぼし時に電源ボタン押下は許容（100% 信頼性は不要）。
- **S4(ハイバネ)復帰**: 毎回電源ボタンで問題なし（lid 復帰は求めない、受容済み）。

→ S4 lid 復帰は受容済みのため対象外。焦点は「s2idle で lid open が概ね起こせるか」。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) — 操作対象は ssh 接続先実機 `macbookair2015.lan`
- OS: Debian 13 (trixie)
- カーネル: `6.12.90+deb13-amd64`
- スリープモード: `/sys/power/mem_sleep = [s2idle] deep`（s2idle 恒久運用）
- 蓋閉じ動作: `HandleLidSwitch=suspend-then-hibernate`（電池駆動）/ `HandleLidSwitchExternalPower=suspend`（AC）
- 既存 wakeup 抑止: udev で XHC1(USB)/RP01-06(PCIe) を `power/wakeup=disabled`、`/proc/acpi/wakeup` の enabled は `LID0` のみ
- 電源/電池: 作業時 AC 接続・バッテリ 92%
- キーボードバックライト LED: `/sys/class/leds/smc::kbd_backlight`（applesmc, `max_brightness=255`, `trigger=[none]`）

## 参照した過去レポート

- [S3→s2idle 恒久切替 + spurious wakeup 抑止](2026-05-31_132125_s3_hang_switch_to_s2idle.md)
- [電源ボタン短押しは健全 s2idle を起こす(3/3)](2026-06-03_123439_pwrbtn_wake_premise_verification.md)
- [s2idle resume hang の RTC ストレス切り分け(lid 1/5 hang)](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)
- [ハイバネ成功スナップショット](2026-06-18_053417_hibernate_success_snapshot.md)

---

## Deliverable 1: キーボードバックライト消灯フック（完了・検証済み）

### 実装
`/usr/lib/systemd/system-sleep/50-kbd-backlight`（755）を新規配備。systemd-sleep が pre/post で実行し、suspend / hibernate / suspend-then-hibernate 全経路を 1 本でカバーする。

```sh
#!/bin/sh
# スリープ中にキーボードバックライト(applesmc)を消灯し、復帰時に元の輝度へ戻す。
# s2idle は software freeze で LED が通電し続けるため、明示的に 0 にする。
# 注: systemd 経由(logind 蓋閉じ / systemctl suspend / STH)でのみ呼ばれる。
#     rtcwake -m mem は /sys/power/state 直書きで systemd を経由しないため呼ばれない。
LED=/sys/class/leds/smc::kbd_backlight
SAVE=/run/kbd_backlight.brightness
[ -e "$LED/brightness" ] || exit 0
case "$1" in
  pre)
    cur=$(cat "$LED/brightness" 2>/dev/null)
    echo "$cur" > "$SAVE" 2>/dev/null
    echo 0 > "$LED/brightness" 2>/dev/null
    logger -t kbd-backlight-sleep "pre/$2: saved=$cur set->0"
    ;;
  post)
    if [ -f "$SAVE" ]; then
      val=$(cat "$SAVE" 2>/dev/null)
      echo "$val" > "$LED/brightness" 2>/dev/null
      rm -f "$SAVE"
      logger -t kbd-backlight-sleep "post/$2: restored=$val"
    fi
    ;;
esac
exit 0
```

### 検証結果（成功）
- **フック単体**: `pre suspend` で 128→退避→0、`post suspend` で 128 復元・退避ファイル削除を確認。
- **systemd 実経路**: `systemctl suspend`（RTC 安全網 `rtcwake -m no -s N` 併用）で s2idle に入れ、journal に発火を確認:
  ```
  07:19:29 kbd-backlight-sleep: pre/suspend: saved=128 set->0
  07:19:29 PM: suspend entry (s2idle)
  07:21:30 PM: suspend exit
  07:21:30 kbd-backlight-sleep: post/suspend: restored=128
  ```
- **物理確認**: 輝度128(明)から120秒 s2idle に入れ、**スリープ中にバックライトが消灯**することをユーザー目視で確認。復帰後は元の輝度に復元。

### 重要な学び（検証の落とし穴）
**`rtcwake -m mem` は `/sys/power/state` に直接書き込むため systemd を経由せず、system-sleep フックが呼ばれない。** 初回の rtcwake 検証ではフックが走らず「点いたまま」となり空振りした。実運用（蓋閉じ→logind→systemd-suspend、`systemctl suspend`、STH）は systemd 経路なのでフックは確実に走る。フック検証は必ず `systemctl suspend` で行うこと。

---

## Deliverable 2: s2idle lid wake 復活可否の精査（結論: クリーンには不可能 = ファーム/HW 制約）

### 精査の経緯と訂正
当初、lid の `wakeup_active_count = 11` を「lid で 11 回 wake した実績＝機構的に動く」と読んだが、**これは誤り**。制御実験で「RTC が起こしたサイクルでも `active_count` が +1 した」ことを観測し、**この counter は『lid open が wake を起こした時』だけでなく『復帰後に蓋開けを検知した時』にも増える**と判明。よって counter は lid-as-wake-cause の証拠にならない（過去の 11 回も復帰後検知の可能性）。

### 制御実験（rtcwake 安全網 + 物理蓋開け, 0/3）
logind を一時無害化（`99-lidtest.conf` に `HandleLidSwitch=ignore` → 蓋閉じで STH が走らないように）し、蓋を閉じた状態で `rtcwake -m mem -s 90〜120` で s2idle に入れ、15〜20秒後にユーザーが蓋を開けて復帰するか測定:

| 試行 | RTC秒 | elapsed | 結果 |
|---|---|---|---|
| 1 | 120 | 121s | RTC 復帰（蓋開けで起きず） |
| 2 | 90 | 91s | RTC 復帰（蓋開けで起きず） |
| 3 | 90 | 91s | RTC 復帰（蓋開けで起きず） |

**0/3。蓋開けで s2idle から復帰できない**（ユーザー目視でも「蓋を開けても画面は暗いまま、約2分後 RTC で勝手に復帰」を確認）。journal でも「Lid opened」は RTC 復帰時刻に初めてログされ、s2idle 中は lid open が届いていない。

### 根本原因（GPE/_PRW 解析で機構を特定）
1. **lid の runtime 通知は EC 経由**: 覚醒中に蓋を 3 往復トグルしたところ、反応した GPE は **gpe4E（EC GPE）のみ**で、専用 lid GPE は一切動かなかった。lid open/close は EC の `_Qxx`（→ `Notify(LID0)`）で配送される。
2. **EC GPE は s2idle 中マスクされる**: s2idle 進入時、カーネルは wake-GPE 以外（runtime GPE）を無効化する。gpe4E はアイドルでも常時発火する runtime GPE（**実測 約145回/秒**、累積平均27回/秒、SCI 総数のほぼ全数を占める）であり wake-GPE ではない → **s2idle 中は無効化され、lid 通知が届かない**。
3. **宣言された wake GPE は配線されていない**: DSDT の lid デバイス(`LID0` / `_HID PNP0C0D`)の `_PRW` を解析すると wake GPE = **0x70 (gpe70)** を宣言。しかし `gpe70` のカウントは **3 回の s2idle 蓋開け試行を経ても 0 のまま**。つまり宣言上の lid wake GPE は実機で一度も発火せず、lid open のハード wake 信号として機能していない。

### 結論（「復活可能か」への答え）
**s2idle lid wake はこの機体ではクリーンに復活できない（ファーム/HW 制約、カーネル修正で直せるバグではない）。**
- lid 通知は常時発火する EC runtime GPE に相乗りしており、これを wake 武装すればアイドルでも約145回/秒の EC イベントで即・常時 spurious wake となり実用不可（過去に XHC1/RP を抑止した理由と同根）。
- 宣言上の専用 wake GPE(gpe70)は実機で発火せず使えない。
- **電源ボタン短押しが s2idle を確実に起こす**（[2026-06-03 レポート](2026-06-03_123439_pwrbtn_wake_premise_verification.md)で 3/3 実証）ため、これが信頼できる復帰手段。ユーザーは取りこぼし時の電源ボタン使用を受容済みのため、運用上の実害は吸収される。

これは過去レポートで「(c) LID0 notify 取りこぼし（未決着）」とされていた現象の機構的な決着でもある。

## 再現方法

### Deliverable 1（バックライトフックの検証）
```bash
# フック配置 (上記スクリプトを 755 で配置)
ssh miminashi@macbookair2015.lan 'sudo mkdir -p /usr/lib/systemd/system-sleep && sudo tee /usr/lib/systemd/system-sleep/50-kbd-backlight >/dev/null <<EOF
...(本文スクリプト)...
EOF
sudo chmod 755 /usr/lib/systemd/system-sleep/50-kbd-backlight'

# 検証: 必ず systemctl suspend 経路で (rtcwake -m mem 単独は systemd を経由せず不可)
ssh miminashi@macbookair2015.lan '
  sudo sh -c "echo 128 > /sys/class/leds/smc::kbd_backlight/brightness"
  sudo rtcwake -m no -s 120   # RTC 安全網のみセット
  sudo systemctl suspend       # systemd 経由 → フック発火'
# 復帰後: journalctl -b -t kbd-backlight-sleep でログ確認、目視でスリープ中の消灯確認
```

### Deliverable 2（lid wake 精査）
```bash
# logind 一時無害化 (蓋閉じで STH を走らせない)
ssh miminashi@macbookair2015.lan 'sudo tee /etc/systemd/logind.conf.d/99-lidtest.conf >/dev/null <<EOF
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
EOF
sudo systemctl kill -s HUP systemd-logind'

# 蓋を閉じた状態で s2idle 投入 → 15-20秒後に物理的に蓋を開け、elapsed を測定
ssh miminashi@macbookair2015.lan 'b=$(date +%s); sudo rtcwake -m mem -s 90; a=$(date +%s); echo "elapsed=$((a-b))"'
# elapsed≈90 → RTC 復帰=lid wake 失敗 / 大幅に短い → lid wake 成功

# GPE 経路特定 (覚醒中に蓋トグル → 差分)
ssh miminashi@macbookair2015.lan 'for f in /sys/firmware/acpi/interrupts/gpe* /sys/firmware/acpi/interrupts/sci; do printf "%s %s\n" "$(basename $f)" "$(awk "{print \$1}" $f)"; done > /tmp/before.txt'
#   ↑ 蓋を 3 往復トグル ↑
ssh miminashi@macbookair2015.lan '...同様に after.txt → join で差分'

# lid の _PRW wake GPE は DSDT から (iasl が無ければ /sys/firmware/acpi/tables/DSDT をバイナリ解析)
#   → LID0 (_HID PNP0C0D) の _PRW = Package{0x70,...} = gpe70、ただし発火カウントは常に 0

# 後始末 (必須)
ssh miminashi@macbookair2015.lan 'sudo rm -f /etc/systemd/logind.conf.d/99-lidtest.conf && sudo systemctl kill -s HUP systemd-logind'
```

## 最終状態

- **追加**: `/usr/lib/systemd/system-sleep/50-kbd-backlight`（755）— スリープ時バックライト消灯（残置）
- **一時設定**: `99-lidtest.conf` は撤去済み、現行 logind 設定（`10-suspend-then-hibernate.conf`）に復帰
- **lid wake**: 設定変更なし（復活不可と判明。電源ボタンが信頼できる s2idle 復帰手段）

## 残課題・備考

- s2idle lid wake の復活は不可（ファーム/HW 制約）。深掘り余地は EC GPE のカーネルレベル選択的 wake などしか無く、spurious wake と引き換えで実用性なし。要件（取りこぼし許容＋電源ボタン fallback）下では現状維持が妥当。
- s2idle resume hang（別トラック、[2026-06-01](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)）は本作業では再発観測なし（今回の全 suspend サイクルは clean に復帰）。
