# スリープ周りの改善: キーボードバックライト消灯 + lid open 復帰の精査

## Context（なぜ・何を）

ハイバネ調査で得たスリープ機構の知見（特に **s2idle の wake は sysfs `power/wakeup` の IRQ 経路で決まり、`/proc/acpi/wakeup` は ACPI deep(S3) 用** という理解）を活かし、実使用で残る 2 つの不満を改善する。

1. **スリープ中もキーボードバックライトが点灯したまま**（蓋を閉じても／開けたままでも、両方で発生）
2. **lid open で復帰できない**（実現可能か精査する）

### ユーザー要件（確定）
- **s2idle 復帰**: lid open で起きてほしい。**たまの取りこぼし時に電源ボタン押下は許容**（100% 信頼性は不要）。
- **S4 復帰**: **毎回電源ボタンで問題なし**（lid 復帰は求めない）。

→ この要件により、**S4 lid 復帰の調査・対策は不要**（受容済み）。焦点は「s2idle で lid open が概ね起こせる状態か」の確認に絞る。

### 実機での精査結果（本セッションで ssh 経由・読み取り専用で確認）

操作対象は ssh 接続先の実機 `macbookair2015.lan`（CLAUDE.md 参照）。

**キーボードバックライト**:
- 制御点 = `/sys/class/leds/smc::kbd_backlight`（applesmc ドライバ, `max_brightness=255`, `trigger=[none]` でシンプルな brightness 制御）
- `/usr/lib/systemd/system-sleep/`（systemd-sleep がフックを実行するディレクトリ）は**未作成 = 既存フックなし**。クリーンに導入できる。
- s2idle は software-only freeze のため applesmc が通電を維持し、バックライトが点灯し続ける（既知の挙動）。→ system-sleep フックで pre に消灯・post に復元するのが定石。

**lid open 復帰（feasibility = 2 つの regime に分かれる）**:
- lid は wake 源として**有効化済み**。s2idle で効く判定材料（主）は **`/sys/bus/acpi/devices/PNP0C0D:00/power/wakeup = enabled`**（IRQ 経路の device_may_wakeup）。加えて `Lid Switch` input デバイス(event0) 生存、ACPI SCI = IRQ 9 稼働。`/proc/acpi/wakeup` の `LID0` enabled は主に ACPI deep(S3) 用の表示だが、ここでも矛盾なく enabled で、補強材料。
  - 注: `/sys/bus/platform/devices/PNP0C0D:00/power/wakeup = disabled` は別ノードで、権威があるのは acpi subsystem 側（enabled）。
- カーネルは lid の wake 実績を記録（`wakeup_active_count = 11`）。**＝ 機構的には lid で起こせる**。
- ただし `wakeup_active_count` は「スリープ復帰」と「起動中の蓋開閉」が混在し、信頼性の判定材料にはならない。現設定での lid wake 信頼性は**未計測**。

**→ feasibility 結論（精査の答え）**:
- **(A) s2idle（短時間スリープ）**: lid 復帰は機構的に可能で**既に有効化・機能している（実績 11 回）**。要件は「概ね起きればよい・取りこぼしは電源ボタンで許容」なので、**現設定で要件をほぼ満たしている見込み**。失敗が頻発する場合のみ間欠的な **(c) LID0 notify 取りこぼし**を追う（同一 SCI 上の電源ボタンは確実に起こせる(過去 3/3 実証)ので、汎用 resume hang ではなく lid 固有の通知欠落を示唆。根治は未確立だが取りこぼし許容なら実害は電源ボタン fallback で吸収できる）。
- **(B) hibernate / S4（長時間・低バッテリで STH がハイバネへ移行後）**: 現行 `HandleLidSwitch=suspend-then-hibernate` により、蓋閉じ(電池駆動)は s2idle → やがて S4 へ。**S4 からは一般に lid open では起こせず電源ボタン必須**（x86 のハイバネ復帰は実質コールドブートで、EC/ファーム側の wake ロジックが lid を起床源にしない）。これがユーザーの言う「lid で起きないが電源ボタンで起きるのは正常動作」の正体である可能性が高い。counter が 6/16 04:26 以降増えず直近 resume が未計上なのも、直近サイクルがハイバネ→電源ボタン復帰(=カーネル計数前のファーム復帰)だった事と整合。**ユーザーは S4 の電源ボタン復帰を受容済みのため、本トラックは対策不要**（精査結果として記録するのみ）。

過去レポート参照:
- [S3→s2idle 恒久切替 + spurious wakeup 抑止](../../projects/macbookair11-debian/report/2026-05-31_132125_s3_hang_switch_to_s2idle.md)
- [電源ボタン短押しは健全 s2idle を起こす(3/3)](../../projects/macbookair11-debian/report/2026-06-03_123439_pwrbtn_wake_premise_verification.md)
- [s2idle resume hang の RTC ストレス切り分け(lid 1/5 hang)](../../projects/macbookair11-debian/report/2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)
- [ハイバネ成功スナップショット](../../projects/macbookair11-debian/report/2026-06-18_053417_hibernate_success_snapshot.md)

---

## Deliverable 1（確実な改善）: スリープ中キーボードバックライト消灯フック

`/usr/lib/systemd/system-sleep/` に実行可能フックを 1 つ置く。pre で現在値を退避→消灯、post で復元。suspend / hibernate / suspend-then-hibernate 全経路を 1 本でカバーする。

実機での手順（ssh, 要 sudo / NOPASSWD 済み）:

1. ディレクトリ作成: `sudo mkdir -p /usr/lib/systemd/system-sleep`
2. フック `/usr/lib/systemd/system-sleep/50-kbd-backlight` を配置（内容）:
   ```sh
   #!/bin/sh
   # スリープ中にキーボードバックライト(applesmc)を消灯し、復帰時に元の輝度へ戻す。
   # s2idle は software freeze で LED が通電し続けるため、明示的に 0 にする。
   LED=/sys/class/leds/smc::kbd_backlight
   SAVE=/run/kbd_backlight.brightness
   [ -e "$LED/brightness" ] || exit 0
   case "$1" in
     pre)
       cat "$LED/brightness" > "$SAVE" 2>/dev/null
       echo 0 > "$LED/brightness" 2>/dev/null
       ;;
     post)
       if [ -f "$SAVE" ]; then
         cat "$SAVE" > "$LED/brightness" 2>/dev/null
         rm -f "$SAVE"
       fi
       ;;
   esac
   exit 0
   ```
3. 実行権付与: `sudo chmod 755 /usr/lib/systemd/system-sleep/50-kbd-backlight`

設計メモ:
- `$2`(sleep 種別)で分岐しない＝全スリープ種別で消灯（要件「両方/どちらでも」に合致）。
- 退避先は `/run`（tmpfs, 再起動でクリア）。post で復元後に削除し、欠損時(クラッシュ等)は何もしない安全側。
- LED パスのコロン (`smc::kbd_backlight`) はクォートで安全。`trigger=[none]` のため brightness 直書きで確実。

---

## Deliverable 2（精査の確認）: s2idle lid wake が要件を満たすかの軽量確認

精査の結果 **s2idle の lid wake は既に有効・機能している**ため、重い信頼性キャンペーンは不要。要件（概ね起きればよい・取りこぼしは電源ボタン許容）を満たしているかを**少数試行で確認**し、満たしていれば現状維持、まったく起きない場合のみ深掘りする。S4 は受容済みのため**対策しない**。

物理操作（蓋開閉・電源ボタン）はユーザー、suspend 投入とログ取得は ssh。

### 手順（s2idle lid open 復帰の確認, 2〜3 試行）
**方法論の落とし穴**: lid-open wake は「s2idle 中に蓋を closed→open する」必要があり、蓋が **closed の状態で suspend に入っている**必要がある。だが現行設定では蓋を閉じると `HandleLidSwitch=suspend-then-hibernate` が発火し、純粋な s2idle 投入(rtcwake)と競合する。よって確認中だけ logind を無害化する（電源ボタン検証で `HandlePowerKey=ignore` を使ったのと同型）:
1. drop-in `/etc/systemd/logind.conf.d/99-lidtest.conf` に `HandleLidSwitch=ignore` / `HandleLidSwitchExternalPower=ignore` を置き `systemctl kill -s HUP systemd-logind`（蓋を閉じても STH が走らなくなる）。
2. ユーザーが蓋を閉じる（logind が無視するので何も起きない）。
3. `rtcwake -m mem -s 120`（RTC 安全網 = 起きなくても 120s で自動復帰、強制電源断不要）で s2idle 投入。
4. 画面消灯後、ユーザーが**蓋を開ける**（lid open エッジ生成）。
5. elapsed で判定: 蓋開けから速やかに復帰すれば **lid wake 成功**（≈120s なら RTC が起こした＝lid 失敗）。これを 2〜3 回。
6. 後始末（必須）: drop-in `99-lidtest.conf` を撤去し `systemctl kill -s HUP systemd-logind` で現行設定へ復帰。

### 判定と対処
- **2〜3 回中おおむね起きる** → **要件達成。現状維持**（取りこぼしは電源ボタンで吸収、という運用で確定）。追加の設定変更は不要。
- **毎回まったく起きない**（想定外。現精査と矛盾）→ 蓋開け後に**電源ボタン短押し**で復帰するか確認: 復帰すれば **(c) lid notify 取りこぼし**（カーネル生存・通知のみ欠落）、無反応なら **(b′) resume hang**。その時点で GPE/SCI 周り（lid GPE の wake arm、`button.lid_init_state` 等）を調査するが、**根治は未確立領域**。取りこぼし許容の要件下では電源ボタン fallback で実害を吸収できるため、深追いはユーザー判断で。

---

## 検証（Verification）

**Deliverable 1（バックライト）**:
1. 配置確認: `ssh ... 'ls -l /usr/lib/systemd/system-sleep/50-kbd-backlight'`（755）。
2. バックライトを点灯（`sudo sh -c 'echo 128 > /sys/class/leds/smc::kbd_backlight/brightness'`）。
3. `rtcwake -m mem -s 60` で s2idle 投入。**スリープ中にユーザーが目視で「バックライトが消えている」ことを確認**（ssh では LED の見た目は取れないため物理確認が必要。60s は人が確認できる余裕を見た値）。
4. 自動復帰後、`cat /sys/class/leds/smc::kbd_backlight/brightness` が **128 に復元**されていることを確認。
5. `journalctl -b | grep -i system-sleep` でフック実行を確認。

**Deliverable 2（lid）**:
- 上記 2〜3 試行で s2idle lid open 復帰がおおむね成功することを確認（成功＝要件達成・現状維持）。logind drop-in の後始末（撤去）まで完了していることを確認。

## レポート作成（CLAUDE.md ルール）

実施後、`report/yyyy-mm-dd_hhmmss_<name>.md`（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）を作成し:
- 前提・目的・環境情報・再現手順・参照レポートへのリンクを記載。
- プランモード作業なので `report/attachment/<name>/plan.md` に本プランをコピーし本文からリンク（必須）。
- バックライトフックの内容、lid 精査の regime 別結論（s2idle は機能・要件達成／S4 はハード仕様で電源ボタン必須=受容）を残す。
