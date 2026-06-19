# S3 復活検証の続き — battery 長時間 S3 の実待機電力測定（go/no-go の主指標）

## Context（なぜ続きとしてこれをやるのか）

[2026-06-18_233837 S3 復活検証レポート](../../projects/macbookair11-debian/report/2026-06-18_233837_s3_revival_evaluation.md)
は、S3(deep) の firmware/lid wake が AC では健全（A=21/21, B=7/7）で、battery では
**gpe70(LID0 _PRW) 起因の ~6s spurious wake** が最大の障壁、ただし **LID0 wake 無効化で
battery でも S3 が完走する脱出路**（C-3, n=1, 123s）を確認した。しかし取り組み全体の
**go/no-go を握る主指標＝実待機電力は「データ皆無」**（finding #5 / 未解決 #1）のまま閉じた。

主指標が測れなかった直接原因は、残置スクリプト `/usr/local/sbin/s3-power-measure.sh` が
**LID0 を無効化せずに** `rtcwake -m mem -s 2400` を battery で回したため、**6 秒で spurious
wake**（22:52 ログ: BEFORE t=…739 → AFTER t=…745, Δq=+3000µAh ＝ gauge ノイズ）したこと。
S3 の微小消費（~0.1–0.2 W 想定）が短窓のゲージ再推定ノイズ（観測帯 +3000〜−59000 µAh）に
完全に埋もれた。

**この続きの狙い**: LID0 wake を無効化して battery で S3 を長時間維持し、実待機電力を
SNR が立つ窓長で測定して **s2idle 実測 0.70 W と数値比較**する。これで未解決 #1（主指標）
を決し、loop の副産物として #2（hold の数時間持続性 / spurious 回数）も同時に解く。
結論は「S3 復活可（永続化検討へ）」も「棄却（s2idle 据え置き）」も等しくあり得る。

**スコープ規律**: #1 +（loop の副産物としての）#2 のみ。#3（gpe70 spurious の機序＝研究の沼）
と #4（90% から一晩では低バッテリ閾値に届かず、長時間 run が勝手に検証する）は本件で追わない。

## 設計の肝（advisor レビュー反映・5 点）

1. **窓長は SNR で決まる。** 一番うれしい結果（低 W）が一番測りにくい。0.15 W だと
   1h ≈ 20000 µAh でノイズ帯に埋もれる。**S3 が低性能なほど長く回さないと証明できない**。
   一晩（8–12h）で初めて低 W が credible。capacity の整数 % 低下が charge_now への独立クロスチェック。
   → ユーザ合意: **まず 1h プレ計測 → その後一晩計測**。
2. **endpoints-only・median。** `W = Δcharge(start→end) × V_mean / 総 wall-clock`。
   **per-segment Δ を足し合わせない**（resume ごとの gauge 再推定＝−59000 の正体を、wake 毎に注入してしまう）。
   BEFORE/AFTER は各々「settle 後に ~5 回読んだ median」、両方とも **battery 上**で取る。
3. **re-suspend loop が #2 をタダで解き、かつ overnight の安全設計そのもの。** 単発長 rtcwake は、
   LID0 無効 hold が夜中に破れたら（実証 n=1・123s だけ）~6W 覚醒のまま放電→破滅。
   毎周 RTC 再武装・wall-clock cap・自己終了・**各 wake を sync ログ**（高デューティで ssh 到達性は
   使えない＝教訓、on-disk sync ログだけが ground truth）。RTC 再武装間隔 ~20–30 分。
4. **無人放置前に safety net を pre-flight 確認。** 低バッテリ連動ハイバネ（RTC ポーリング経路）が
   armed か AC を抜く前に確認。ただしこれは覚醒時のみチェックする backup（Phase 0 で詳述）。
   無人放置の primary safety は loop の wall-clock cap + 自己終了。
5. **AFTER は必ず battery 上・AC 再接続の前に読む**（充電すると charge_now が跳ねる）。
   loop が AC 再接続を跨がないこと。

## 実機・前提

- 操作対象は ssh 接続先 `macbookair2015.lan`（全コマンド ssh 越し）。現状＝既知良状態
  （`mem_sleep`=`[s2idle] deep`、LID0=enabled、boot_id=`86ba1c2d…` 不変、cap 90%）。
- **物理立ち会い必須**（AC 抜き差しはユーザ操作）。
- **lid は開いたまま測定する**（LID0 wake 無効化済みなので開いても wake しない）。理由: logind は
  report B で default に復元済みで、**閉じた lid のまま各セグメントが brief wake すると logind が
  独自に suspend-then-hibernate を発火**させ、測定を汚染し夜間にハイバネ落ちしうる。lid を閉じる
  運用にしたい場合のみ、測定中だけ logind drop-in（`HandleLidSwitch=ignore`）で無害化し Phase 4 で撤去する。
- **battery での S3 resume 健全性は未確立**（親レポートの clean データ A=21/21・B=7/7 は**全て AC**。
  battery resume 成功は C-3/C-4 の **n=1 が 2 例のみ**）。無人 overnight は未検証の
  battery-firmware-resume リスクを一部負う（overnight 自体が部分的にその検証になる）。
  床は loop の wall-clock cap + 自己終了（後述）が primary、低バッテリ連動ハイバネ（RTC ポーリング）が backup。
- 可逆性: deep 切替は runtime（cmdline は `mem_sleep_default=s2idle` のまま＝再起動で安全側）。
  LID0 無効化は `/proc/acpi/wakeup` トグル（boot 限り、再起動で復帰）。
- BAT0: `charge_full`=4747000 / `charge_full_design`=5100000 µAh、`voltage_now`~8.5V、`energy_now` 非対応
  （µAh×V で µWh 換算する）。

## 再利用 / 新規資材

- 再利用: `systemd-run --collect --unit=…` のデタッチ常駐（ssh 切断後も継続）。
- **新規スクリプト `/usr/local/sbin/s3-soak-measure.sh`**（承認後に作成。残置 `s3-power-measure.sh`
  は LID0 無効化も loop も無いため置き換える）。仕様:
  - 引数: `TOTAL_CAP`(総 wall-clock 秒) `SEG`(RTC 再武装間隔秒, 既定 1500=25min) `LABEL`
  - `LOG=/var/log/s3-soak-measure.log`。全行 `sync` 付き追記。
  - 起動時: deep 確認・LID0 が disabled であること確認（未 disabled なら **abort**＝安全弁）。
  - **BEFORE**: 60s settle 後に `charge_now` を ~5 回（各 10–15s 間隔で gauge 再推定を跨ぐよう分散）読み
    median、`voltage_now`/`capacity`/epoch を記録（battery 上）。
  - **loop**: `start_epoch` 記録。`while (now-start) < TOTAL_CAP`: `rtcwake -m mem -s SEG` →
    resume 直後に 1 行ログ（`woke_at`, `seg_elapsed`, `charge_now` スナップショット, `capacity`,
    `gpe70` カウント, `suspend_stats` success/fail）。`seg_elapsed << SEG` なら **spurious wake** として
    カウントし即 re-suspend（覚醒滞留を最小化）。各周 `sync`。
  - **AFTER**: loop 終了後、battery 上で（AC 再接続前に）60s settle → `charge_now` ~5 回 median 等を記録。
  - **算出**: `Δq=q_before−q_after`(µAh)、`V_mean=(v_before+v_after)/2`、`Δt=after_epoch−before_epoch`(h)、
    `W = Δq×V_mean / Δt` を最終行に出力。**per-segment Δ は診断（hold/ spurious 回数）専用で W には使わない**。
  - 自己終了（wall-clock cap 到達でループ脱出）。loop は AC 再接続を跨がない。

## 手順（フェーズ）

### Phase 0 — pre-flight（read-only + safety net 確認）
- AC online / lid / `mem_sleep` / boot_id / `suspend_stats`（success/fail）/ cap・charge_now を記録。
- **safety net 確認**: バッテリ連動ハイバネ（RTC ポーリング経路, `low-battery-hibernate` 系）の
  timer/設定が armed か確認（無効なら overnight 前にユーザへ報告し判断を仰ぐ）。
  - **注意（床の限界）**: このハイバネは **RTC ポーリング＝覚醒時のみチェック**で、S3 で寝ている間は
    判定が走らない。よって**即座の床ではなく、覚醒した時だけ効く backup**。loop が死んでも最後の
    rtcwake の RTC alarm で SEG 後に覚醒し、その時に低バッテリならハイバネに落ちる。
    **primary safety は loop の wall-clock cap + 自己終了**であり、低バッテリ連動ハイバネはその後ろの保険。

### Phase 1 — 1h プレ計測（loop と hold の妥当性検証 + 粗い W）
1. **lid は開いたまま**にする（必要なら logind drop-in `HandleLidSwitch=ignore` を仕込み Phase 4 で撤去）。
2. `echo deep | sudo tee /sys/power/mem_sleep` → `[deep] s2idle` 確認。
3. `echo LID0 | sudo tee /proc/acpi/wakeup` → `LID0 … disabled` 確認（gpe70 凍結の前提）。
4. **ユーザに AC を抜いてもらう**（`ADP1/online`=0 を確認）。
5. `sudo systemd-run --collect --unit=s3-soak-pre /usr/local/sbin/s3-soak-measure.sh 3600 1200 pre`
   （1h, SEG=20min → 3 セグメント。hold サンプルを数回取りつつ粗い W）。
6. 完了後（battery 上のまま）ログを読む。判定:
   - **各セグメントが SEG≈20min 完走（spurious 0〜僅少）** → hold は数時間持続の見込み、overnight へ。
   - **早期 wake が頻発 or 覚醒滞留** → overnight 前に原因（gpe70 以外の wake 源）を切り分け。
   - 粗い W が出れば overnight の期待値の当たりを付ける（1h は decisive ではない＝ノイズ帯近傍前提）。
7. ユーザに結果を提示。**pre と overnight は各 run が自前の BEFORE/AFTER を battery 上で取る独立測定**なので、
   pre のあと AC 再接続・充電して構わない（次 run は再度 AC を抜いてから自分の BEFORE を取り直す）。
   日中 pre → 夜に Phase 2 を別 run、が自然。連続で行ってもよい。

### Phase 2 — 一晩計測（主指標・decisive）
1. lid 開・deep・LID0 disabled・battery を確立（Phase 1 から連続なら維持、別 run なら再設定し AC を抜く）。
2. `sudo systemd-run --collect --unit=s3-soak-night /usr/local/sbin/s3-soak-measure.sh 36000 1800 night`
   （10h cap, SEG=30min。実際の就寝時間に合わせ TOTAL_CAP は調整）。
3. **翌朝**: loop は自己終了済み。`/var/log/s3-soak-measure.log` の AFTER と W 算出行を確認
   （**AC 再接続前に**読む）。capacity の整数 % 低下を独立クロスチェックに使う。
4. 読み終えたらユーザに AC 再接続してもらう。

### Phase 3 — 分析と判定（decision matrix）
- `W_S3 = Δq×V_mean/Δt` を s2idle 実測 0.70 W と比較。capacity %低下とも突き合わせ整合確認。

| 結果 | 判定 |
|---|---|
| `W_S3` が 0.70 W より**有意に低い**（見込み 0.1–0.2 W 台）かつ hold が一晩持続（spurious 僅少） | **主目的成立**。永続化（`mem_sleep_default=deep`）と soak の検討へ（別タスク・本件外） |
| `W_S3` が **~0.5 W 付近で曖昧** | **同一条件で s2idle を翌晩に再ベースライン測定**（ユーザ合意の条件付き追加）→ 直接 A/B で再判定 |
| `W_S3` が s2idle と**大差なし** | **S3 棄却**（主目的不成立、hang リスクに見合わない）。s2idle 据え置き |
| 一晩で hold が破れ覚醒放電（または S4 ハイバネ落ち多発） | hold 持続性が NG。spurious 源の追加切り分けが必要（go 不可） |

### Phase 4 — 復元（既知良状態へ）
```bash
ssh ... 'echo s2idle|sudo tee /sys/power/mem_sleep; \
  grep -q "LID0.*disabled" /proc/acpi/wakeup && echo LID0|sudo tee /proc/acpi/wakeup; \
  sudo rm -f /etc/systemd/logind.conf.d/99-*.conf; sudo systemctl kill -s HUP systemd-logind; \
  echo 0|sudo tee /sys/class/rtc/rtc0/wakealarm'
```
- logind drop-in を Phase 1 で仕込んだ場合のみ上の rm/HUP が効く（仕込まなければ no-op）。
- 永続設定（cmdline / GPE mask）は本件で**変更しない**。deep/LID0/logind は runtime/drop-in のみ。

## Verification（検証の妥当性チェック）

- **W の算出は endpoints-only**（per-segment Δ を足さない）。BEFORE/AFTER とも battery 上・median・settle 後。
- **hold 持続性**: per-segment ログで「各セグメントが SEG 完走したか」「spurious wake 何回・どの GPE」を確認。
- **boot_id 不変** と `suspend_stats` fail=0 で、測定中に真の hang/強制 off が無かったことを cross-check。
- **独立クロスチェック**: charge_now（ノイジー）に対し capacity 整数 % 低下が同じ消費を指すか整合確認。
- AFTER を AC 再接続前に取得していること（充電跳ねの混入防止）。

## 成果物（CLAUDE.md レポートルール）

実施後 `report/yyyy-mm-dd_hhmmss_s3_battery_standby_power.md` を作成（タイムスタンプは
`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。前提・目的・環境情報・再現方法・結果（W_S3 と s2idle 比較・
hold 持続性・spurious 回数）・decision を記載。本プランファイルを
`report/attachment/<レポート名>/plan.md` に添付しリンク。
親レポート（2026-06-18_233837）と関連（2026-06-01 / 2026-06-18 各種）へのリンクも張る。
`s3-soak-measure.log` は `report/attachment/<レポート名>/` に退避して添付する。
