# battery 駆動 S3(deep) の実待機電力測定 — 一晩計測で ~0.1W（s2idle 0.70W の ~1/7）、待機電力低減は go

- **実施日時**: 2026年06月19日 00:30〜09:43 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-19_094329_s3_battery_standby_power/plan.md)
- [soak 測定ログ全文（pre 1h + night 8h）](attachment/2026-06-19_094329_s3_battery_standby_power/s3-soak-measure.log)

## 前提・目的

[2026-06-18 S3 復活検証レポート](2026-06-18_233837_s3_revival_evaluation.md) の続き。前回は
S3(deep) の firmware/lid wake が AC では健全（A=21/21・B=7/7）、battery では gpe70(LID0 _PRW)
起因の ~6s spurious wake が最大の障壁、ただし **LID0 wake 無効化で battery でも S3 が完走する
脱出路**（C-3, n=1, 123s）まで確認したが、取り組み全体の **go/no-go を握る主指標＝実待機電力は
「データ皆無」**（finding #5 / 未解決 #1）のまま閉じていた。

主指標が測れなかった直接原因は、前回の残置スクリプト `s3-power-measure.sh` が **LID0 を無効化
せずに** `rtcwake -m mem` を battery で回し **6 秒で spurious wake** していたこと。S3 の微小消費
（想定 ~0.1–0.2 W）は短窓のゲージ再推定ノイズ（観測帯 +3000〜−59000 µAh）に完全に埋もれた。

- **目的（go/no-go）**: LID0 wake を無効化して battery で S3 を長時間維持し、実待機電力を SNR が
  立つ窓長で測定して **s2idle 実測 0.70 W**（[12h 計測の既存値](2026-06-18_142303_why_not_s3_deep_sleep.md)）
  と数値比較する。「S3 が有意に低い」なら主目的成立、「大差なし」なら棄却。
- **副産物**: 未解決 #2（LID0 無効 hold が数時間持続するか / spurious 回数）を loop で同時に解く。
- **スコープ外**: #3（gpe70 spurious の機序）、永続化（cmdline `mem_sleep_default=deep` 化）と
  soak は本件では追わない（別タスク）。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.90+deb13-amd64`
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。物理操作（AC 抜き差し・lid）はユーザ。
- スリープ: `/sys/power/mem_sleep` 既定 `[s2idle] deep`（cmdline `mem_sleep_default=s2idle`、
  deep は runtime 選択。**本検証中も永続設定は未変更＝再起動で安全側に戻る**）。
- 電源: AC=`ADP1`、電池=`BAT0`（`charge_full`=4747000 µAh / `charge_full_design`=5100000 µAh、
  `voltage_now`≈8.4 V、`energy_now` 非対応のため µAh×V で µWh 換算）。
- safety net: UPower `CriticalPowerAction=Hibernate`（`PercentageAction=2.0`, `AllowRiskyCriticalPowerAction=true`）
  が armed。ただし覚醒時のみ判定する backup（S3 睡眠中はポーラ非稼働）。
- logind: battery 時 `HandleLidSwitch=suspend-then-hibernate`。→ **計測中は lid 開放必須**
  （閉じると覚醒境界で logind が STH を誤発火し測定汚染／夜間ハイバネ落ちの恐れ）。
- 検証中、実機は **一度も再起動していない**（`boot_id`=`86ba1c2d…` 不変）。
- 新規残置スクリプト: `/usr/local/sbin/s3-soak-measure.sh`（re-suspend loop。下記）。

## 結果サマリ

| 計測 | 条件 | 結果 |
|---|---|---|
| **Phase 1 (pre, 1h)** | deep, battery, LID0 disabled, SEG=20min×3 | hold **3/3 フル完走**, spurious **0**, gpe70 凍結, fail=0。W=0.19W（満充電付近でノイズ支配・非 decisive） |
| **Phase 2 (night, 8h)** | deep, battery, LID0 disabled, SEG=30min×16 | hold **16/16 フル完走**, spurious **0**, gpe70 **8h 凍結**, fail=0, boot_id 不変。**待機電力 ~0.06–0.10 W（桁）** |
| **比較対象** | s2idle, 12h | 0.70 W（既存値） |

### 主目的（待機電力低減）の判定: **go（S3 採用は待機電力の点で明確に有利）**

**battery 駆動 S3 の実待機電力は 0.1W 弱（~0.06–0.10 W の桁）**（8.025h 計測）。**s2idle 0.70 W より
おおよそ 7–12 倍低い**（容量比で ~7 倍、より低消費側の per-segment 傾き評価で ~12 倍）。

> **最も堅い論拠（ゲージ精度に依存しない）**: 8 時間で **battery が 2 ポイントしか減っていない**
> （89%→87%）。本機の capacity は設計容量(5100000µAh)基準なので 2pt ≈ 102000µAh で、直接測った
> dq=94000µAh（≈0.79 Wh）と整合。もし S3 が s2idle 並みの 0.70 W なら 8h で ≈5.6 Wh＝**約 13 ポイント**
> 減るはず（89%→~76%）。実測の減りはその ~1/7。**どう計算しても S3 は s2idle より 7 倍以上低い**ので、
> 後述の charge_now ゲージの細かい議論に関わらず go は揺るがない。

- 一晩を通して **16 セグメント全てが 30 分フル hold**、**spurious wake 0**、**gpe70 は 13 のまま
  8 時間凍結**（LID0 無効化が spurious 源を完全に殺し続けた）。未解決 #2（hold 持続性）は
  **n=1 ながら 16 連続クリーンで強く前進**。
- **fail=0 / boot_id 不変 / 全 rc=0**。battery での S3 resume 健全性は、前回 AC 限定＋battery
  n=1×2 だったのが **一晩 16 サイクル連続成功**へ格上げ。
- トレードオフは前回どおり: この低電力は **LID0 wake 無効化（lid wake の犠牲）が前提**。
  spurious wake と lid wake は gpe70 を共有するため、両立しない。

## 主要な発見

### 1. S3 待機電力は 0.1W 弱（~0.06–0.10 W の桁）。precise な単一値は出せない

endpoints-only（BEFORE/AFTER とも battery 上で settle 後に charge_now を 5 回読み median）で算出:

```
dq = 4524000 − 4430000 = 94000 µAh,  V_mean = 8.367 V,  dt = 8.025 h
W_endpoint = (0.094 Ah × 8.367 V) / 8.025 h = 0.098 W
```

**ただしこの 0.098 は precise ではなくゲージ律速**。同じログの別の取り方は低めを出す:
- **per-segment スナップショット（覚醒直後値）の傾き**: SEG#1(4567000)→SEG#15(4515000) で 52000 µAh /
  7.0 h ≈ **0.062 W**。覚醒直後どうしの比較なので「覚醒直後 vs settle 後」のバイアスが相殺され、
  むしろ素直な傾き。
- endpoint dq=94000 µAh の大半は **SEG#16 覚醒直後値(4520000) → AFTER settle 後 median(4430000) の
  90000 µAh**（わずか 85 秒）に乗っており、これは実消費でなく **覚醒直後 vs settle 後のゲージ
  再推定バイアス**（85s で 90000µAh＝32W 相当などあり得ない）。endpoint 法はこのバイアスを取り込むぶん
  過大評価側。
- → **正直な結論は「~0.06–0.10 W の桁」**。単一の有効数字 3 桁は名乗らない。

**「coulomb 計数」と「整数 capacity」は独立な二指標ではない（循環に注意）**: 本機の `capacity` は
おおむね `charge_now/charge_full_design` の丸め（4524000/5100000=88.7→89, 4430000/5100000=86.9→87 と
両端で一致）であり、charge_now と同一の coulomb 計数由来。よって「dq と 2%×capacity の一致」は
**同じ測定の言い換えで、独立な裏取りではない**。独立寄りの witness は **電圧降下（8.379→8.354 V）**
だが小さくノイジーで補助的。**go/no-go を一人で決める強い証人は、ゲージ精度に依存しない
「8h で容量低下わずか 2pt」のほう**（上記サマリ参照）。

### 2. LID0 無効 hold は 8 時間持続し、battery spurious wake はゼロ

Phase 1（1h, SEG20min×3）も Phase 2（8h, SEG30min×16）も **全セグメントが規定時間フル完走**
（seg_elapsed が常に SEG をわずかに超過＝RTC alarm まで寝ていた）。**spurious wake は通算 0**、
**gpe70 は終始 13 のまま**。前回 C-3 の n=1・123s から、**8 時間・16 サイクルへ持続性を実証**。
gpe70 以外の低頻度 wake 源も一晩で顔を出さなかった。

### 3. 1 時間プレ計測は満充電付近でノイズ支配（窓長が SNR を決める実例）

Phase 1 は W=0.19W を出したが、charge_now が満充電付近で大きく再推定で揺れた（BEFORE 4593000 →
途中 4650000 へ**上昇** → AFTER 4570000）。dq=23000µAh はノイズ帯内で **decisive ではない**。
一方 8h 窓では SNR が立った（dq=94000µAh）。なお **night 側も序盤 ~1.5h は再推定で上昇**
（BEFORE 4524000 → SEG#1–3 ≈4567–4569000）してから減少へ転じており（その後は小さな上下を
伴いつつ AFTER 4430000 まで低下）、**完全な単調ではない**。AC を満充電から抜いた直後の再推定の
名残で、序盤ベースラインは不安定。だから SEG#1 起点の per-segment 傾き（~0.06W）の方が信頼でき、
BEFORE 起点の endpoint 法はこの序盤再推定を取り込む。「低消費ほど長く回さないと証明できない」
という設計前提（SNR ドリブンの窓長）の実証。

## 補足観測（参考）

- **wifi 機なので S3 中の途中読みは不可**: S3 resume 後の wifi 再アソシエーションに数秒かかる一方、
  loop は覚醒〜再 suspend を ~1–2 秒で済ませる。セグメント間の瞬間覚醒では wifi が復帰しきる前に
  再び寝るため ssh が原理的に届かない。**ログを読めるのは loop が cap で自己終了し awake のまま
  留まる時のみ**。途中経過取得を試みたが（08:27 頃）覚醒窓を一度も掴めなかった。
- **session の battery 消費**: 開始 92% → 終了 87%。大半は実験オーバヘッド（覚醒駆動 + pre/night の
  覚醒境界）。night 8h 区間のみなら 89%→87%（2pt）= 直接測定 dq=94000µAh ≈ **0.79Wh** が S3 純消費。
- **セグメント覚醒オーバヘッドは ~3–4秒**（`seg_elapsed`≈1804s / 目標1800s）。loop 中のデューティは
  **~0.2% awake** で、loop 自体が足す覚醒電力は無視可能。覚醒電力の混入は BEFORE/AFTER の settle
  （各 ~85s）に限られる、という裏付け（W が桁として信頼できる根拠の一つ）。
- **capacity の整数量子化（±1pt）**: night は SEG#1–11（~5.5h）まで 90 のまま貼り付き、SEG#12 で
  89 へ1段。「8h で 2pt 低下」は **2±1pt** の幅を持つ。1pt＝設計容量(5100000µAh)の 1%＝51000µAh
  なので、capacity ベースの W は 1–3pt → **≈0.05–0.16W の帯**（直接測った dq=94000µAh は ~1.8pt 相当で
  観測 2pt と整合）。それでも 0.70W が要する ~13pt とは桁違いで go は不変だが、「ノイズ非依存で precise」
  ではなく「ノイズ非依存だが量子化幅つき」が正確。
- **電圧（唯一の独立寄り witness）**: night BEFORE 8.379V → AFTER 8.354V（pre 開始 8.440V より低い＝
  既に少し放電した状態でのスタート）。降下は小さくノイジーで W の主推定には使えないが、coulomb 計数と
  独立に「微減」を支持する。
- **安全弁の実証**: スクリプトの deep 未選択（exit 2）/ LID0 未無効化（exit 3）ガードは、
  本番前に s2idle 状態で実際に ABORT することを確認済み（誤って battery で 6s spurious wake を
  繰り返す前回の失敗を構造的に防止）。

## 再現方法（実機手順）

```bash
# 0) 既知良状態から: deep へ runtime 切替（cmdline は s2idle のまま）+ LID0 wake 無効化
ssh miminashi@macbookair2015.lan 'echo deep | sudo tee /sys/power/mem_sleep'
ssh ... 'echo LID0 | sudo tee /proc/acpi/wakeup'   # "LID0 ... disabled" を確認
#   lid は開けたまま（battery 時 logind=suspend-then-hibernate を誤発火させない）

# 1) ユーザが AC を抜く（ADP1/online=0 を確認）

# 2) re-suspend loop で長時間 S3 待機電力測定（systemd-run でデタッチ常駐）
#    引数: TOTAL_CAP_秒  SEG_秒  LABEL
ssh ... 'sudo systemd-run --collect --unit=s3-soak-night \
           /usr/local/sbin/s3-soak-measure.sh 28800 1800 night'   # 8h, 30min seg

# 3) cap 到達で自己終了（awake のまま）。AC 再接続前に RESULT 行を読む
ssh ... 'sudo grep RESULT /var/log/s3-soak-measure.log'
#   W = Δcharge(start→end) × V_mean / 総 wall-clock（endpoints-only, per-segment Δ は使わない）
```

スクリプト `s3-soak-measure.sh` の要点:
- 起動時に **deep 選択 / LID0 disabled を検証し、満たさなければ ABORT**（spurious wake 防止の安全弁）。
- BEFORE/AFTER は battery 上で 45s settle 後に charge_now を 5 回（間隔をあけ）読み **median**。
- `rtcwake -m mem -s SEG` を **wall-clock cap まで再武装し続ける**（自己終了）。各覚醒を
  sync 付きオンディスクログに記録（wifi 機で ssh 不通でも ground truth が残る）。
- spurious 判定 `seg_elapsed < SEG−30`、gpe70/suspend_stats を毎周記録。

復元（既知良状態へ。**実施済み**）:
```bash
ssh ... 'echo s2idle|sudo tee /sys/power/mem_sleep; \
  grep -q "LID0.*disabled" /proc/acpi/wakeup && echo LID0|sudo tee /proc/acpi/wakeup; \
  sudo rm -f /etc/systemd/logind.conf.d/99-*.conf; sudo systemctl kill -s HUP systemd-logind; \
  echo 0|sudo tee /sys/class/rtc/rtc0/wakealarm'
```

## 結論と次の一手

- **主目的（待機電力低減）は go**: battery 駆動 S3 の待機電力 **~0.06–0.10 W（桁）**、s2idle 0.70 W より
  **~7–12 倍低**（ほぼ一桁）。最も堅い論拠は「8h で容量低下わずか 2pt（0.70W なら ~13pt 減るはず）」で
  ゲージ精度に非依存。hold は 8h/16 サイクル安定、spurious 0、健全性も実証。
- **採用条件（トレードオフ）**: この低電力は **LID0 wake 無効化（lid wake を捨てる）が前提**。
  電源ボタン wake は前回 C-4 で deep でも成立（n=1）を確認済み。「lid を開けて電源ボタンで起こす」
  運用なら待機電力の大幅低減を得られる。
- **本件で確定したこと**: 前回レポート未解決 #1（実待機電力＝go/no-go）と #2（hold 持続性）を決着。
- **未着手（永続化前に要検討・別タスク）**:
  1. **永続化**（`GRUB_CMDLINE_LINUX_DEFAULT` の `mem_sleep_default=deep` 化 + LID0 無効化の
     起動時自動適用）と **1–2 週間の soak**（復帰イベントを lid/電源・ssh 通る画面黒(=モード3)・
     RTC/hibernate 救済・真の hang に分類してカウント）。
  2. **lid wake と省電力の両立**（#3 gpe70 spurious の機序解明）— 解ければ lid wake を温存したまま
     spurious だけ止められる可能性。
  3. **低バッテリ連動ハイバネとの実運用干渉**（S3 睡眠中は UPower 非稼働＝覚醒時のみ発火する backup）。

## 関連レポート

- [2026-06-18 S3 復活検証（本件の親）](2026-06-18_233837_s3_revival_evaluation.md)
- [2026-06-18 なぜ S3 を使っていないのか（通読版・s2idle 0.70W の出典）](2026-06-18_142303_why_not_s3_deep_sleep.md)
- [2026-06-01 s2idle hang の rtcwake 切り分け](2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)
- [2026-06-18 ハイバネ成功スナップショット（swap/STH 配線）](2026-06-18_053417_hibernate_success_snapshot.md)
