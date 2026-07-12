# S3 (deep) 再検証 — lid open wake 復活の可否判定

## Context

suspend hang 問題は Phase C-7/C-8 で真因確定 (wl 親ポート 00:1c.2 の D3hot 復帰不全) し、恒久対策 (udev rule `99-c7r3-wl-d3cold.rules` = 03:00.0 `d3cold_allowed=0` → 00:1c.2 D0 固定) + stock 6.12.95 で hang 0 の常用 soak 中。

一方、lid open で復帰する挙動は s2idle では構造的に不可能 (lid 通知が EC GPE 相乗りでマスク、gpe70 不発 — 2026-06-18 確定)。S3 (deep) なら lid wake は健全 (AC 21/21 + 7/7 実証済) だが、当時は「内在的 S3-deep hang (~0.7/週)」を理由に 6/27 に no-go となった。**その no-go 判断は真因確定前のもので、しかも「suspend 側停止」という当時の根拠は C-4 (m) で正式訂正された journal の対称性錯誤に基づく** — S3 hang も resume 側の同根 (wl war × 親ポート D3 復帰) だった可能性が高い。

よって「**udev 保護つきで S3 deep を再検証し、hang が消えていれば lid wake を復活させる**」。副次効果として待機電力も s2idle+保護 ~1.6W → S3 ~0.06–0.10W 級 (当時実測、要再計測) が見込める。

残る既知の障壁: **バッテリ時の spurious wake (gpe70 = LID0 _PRW、S3 進入 ~6 秒で必ず起床、battery のみ)**。lid wake と同一 GPE のため GPE 粒度では両立不可。→ 解決策候補 = 「AC 時のみ LID0 有効」の動的ポリシー (Phase 3 で判定)。

## 実機の現在状態 (C-9 撤収検収 2026-07-12 時点、P0 で再検収)

- カーネル: stock 6.12.95 (GRUB_DEFAULT=0)、6.12.94-dpmwd4 残置 (hang 時 decode 用)
- cmdline: `quiet no_console_suspend mem_sleep_default=s2idle panic=15`
- udev 保護: 有効 (03:00.0 d3cold_allowed=0)
- LID0: `*enabled` (/proc/acpi/wakeup)
- sleep hooks 残置: 50-kbd-backlight / 58-snapshot-only / 59-pmtrace-timefix / 60-s3-soak-log (deep 強制 2 行は削除済み) / 70-h4-probe
- s3-deep-apply.service: **unit ごと削除済み** (再 enable 不可)
- logind: バッテリ lid close = suspend-then-hibernate、AC = suspend

## 検証の設計方針

- **全フェーズ runtime `echo deep > /sys/power/mem_sleep` のみで実施** (GRUB・service・hook での永続化は採否決定まで一切しない)。強制電源断 → 再起動で自動的に s2idle へ戻る = 安全側フェイルセーフ。
- ストレスは **stock 6.12.95 で実施** (実運用構成での判定が目的)。hang が出た場合のみ dpmwd4+pm_trace を re-arm して decode (C-9 手順流用、bak-c9 方式)。
- ハーネスは C-6〜C-9 のものをそのまま流用 (70-h4-probe の PRE 台帳 = n の正、BT_PAN_VALID = PRE の xfrm 双方向 SA、POST は resume epoch 命名の罠に注意)。
- ssh は sandbox 越しに通らないため **/sandbox でサンドボックス一時無効化** して作業。

## Phase 0: 現状検収 (ssh のみ、変更なし)

```bash
ssh miminashi@macbookair2015.lan '
  uname -r; cat /sys/power/mem_sleep;
  cat /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed;
  grep LID0 /proc/acpi/wakeup;
  ls /usr/lib/systemd/system-sleep/;
  systemctl is-enabled s3-deep-apply.service 2>&1;
  cat /sys/firmware/acpi/interrupts/gpe70'
```

期待: 6.12.95 / `[s2idle] deep` / d3cold=0 / LID0 enabled / hooks 5 本 / not-found。
ズレがあればレポートに記録し、計画を修正してから進む。

## Phase 1: S3 smoke — deep が保護つきで動くか + lid wake 復活確認 (AC、~30 分)

1. runtime deep 化: `echo deep | sudo tee /sys/power/mem_sleep` → `s2idle [deep]` 確認
2. dynamic debug 有効化 (`file drivers/pci/pci-driver.c +p` 等) で per-device D-state を journal に出す
3. **cycle 1 (rtcwake)**: `sudo rtcwake -m mem -s 60` → 完走確認 → journal で:
   - `Preparing to enter system sleep state S3` / `Waking up from system sleep state S3` (真の S3 確認)
   - `PCI PM: Suspend power state:` 行で **00:1c.2 が D0 か** (udev 保護の S3 実効性 = 本検証の第一関門)
   - ※ rtcwake は systemd 経路を通らず sleep hooks 未発火 (既知の罠) — D-state 確認目的なので許容
4. **cycle 2-6 (lid wake ×5)**: ユーザが AC 接続のまま lid 閉 → ~30 秒 → **lid 開だけで復帰するか** (電源ボタン不使用)。journal の Lid opened / gpe70 増分 / drm エラー無しを毎回確認
5. 判定:
   - 00:1c.2 が S3 で D0 → 保護実効あり、Phase 2 へ
   - 00:1c.2 が D3hot に落ちる → 保護は S3 で無効。**hang リスク評価をやり直す必要がある**ため一旦停止してユーザ報告 (Phase 2 を「dpmwd4 で decode 前提の少数 cycle」に変更するか判断)
   - lid wake 不発 → その場で原因調査 (LID0 状態、gpe70 カウント)

## Phase 2: hang ストレス — 最強条件で 0/30 を狙う (AC、ユーザの手動 lid 操作が必要)

実績ある最強 stressor = **BT-PAN (iPad) + VPN (GSNet) + WiFi radio-off** の lid close cycle。deep でこれが 0/30 なら Fisher 片側 p≈1.7e-4 級 (無保護 pool 9/24≈38% 対比) で「保護により S3 hang も消滅」を主張できる。

セットアップ (C-6/C-9 手順流用):
```bash
# marker + watchers
sudo touch /var/log/h4-probe/SESSION-S3R-START.marker
sudo systemd-run --unit=cycle-watch-s3r --collect bash -c \
  'journalctl -k -f -o short-unix | grep --line-buffered -E "PM: suspend (entry|exit)" >> /var/log/h4-probe/cycle-watch-s3r.log'
sudo systemd-run --unit=vpn-watch-s3r --collect bash -c \
  'while true; do echo "$(date +%s) $(ip -o -4 addr show | grep -oE "172\.20\.10\.[0-9]+/[0-9]+" | head -1) xfrm=$(ip xfrm state | grep -c ^src)" >> /var/log/h4-probe/vpn-watch-s3r.log; sleep 20; done'
# 条件: iPad BT-PAN 接続 → nmcli radio wifi off (detached) → nmcli con up GSNet (BT-PAN 上で再確立)
# 有効性: sudo ip xfrm state | grep -c ^src == 2 (172.20.10.13 ⇄ 160.16.210.47 双方向)
```

- cycle: ユーザが lid 閉 → 10–15 秒 → **lid 開で wake** (S3 なので電源ボタン不要のはず — これ自体が lid wake の反復実証を兼ねる)
- 有効 cycle は 70-h4-probe の PRE 台帳 + BT_PAN_VALID で機械計上 (体感回数と必ずズレる、台帳が正)
- 終了条件: **有効 30 cycle clean** または **hang 1 回**
- hang 時: 5 分放置 → 長押し断 → PRE unpaired 確認 → **一級データとして記録** → dpmwd4+pm_trace re-arm (GRUB_DEFAULT=saved 一時変更 + `sync` 必須、bak 取得) して再演・decode へ移行 (C-9 手順)
- 進め方: 1 セッションで 30 回やり切る必要はない。複数セッション分割可 (marker と PRE 台帳で通算)

## Phase 3: バッテリ spurious wake の再確認と lid wake ポリシー決定 (battery、~15 分)

1. AC を抜き、`sudo rtcwake -m mem -s 60` ×3 — elapsed≈6s (spurious) か 60s (完走) か。gpe70 増分を前後比較
2. 予想: 再現する (firmware 挙動、真因対策とは無関係)。再現したら **「AC 時のみ LID0 有効」の動的ポリシー**を採否候補にする:
   - system-sleep pre フックで `ac=0 かつ LID0 *enabled → echo LID0` (凍結)、post で `ac=1 復帰時に再有効化` — /proc/acpi/wakeup はトグルなのでガード必須
   - 効果: AC lid close → lid open で復帰 / バッテリ lid close → 電源ボタン復帰 (現状と同じ、ただし sleep は保たれる)
   - バッテリ lid close は logind 設定により suspend-then-hibernate のまま (低残量ハイバネ機構とも干渉しない)
3. 万一 spurious が再現しなければ (カーネル更新等で状況変化)、LID0 常時有効のまま採用可 — battery lid wake も復活

## Phase 4: 待機電力の再計測 (battery、一晩 or 数時間、任意だが推奨)

udev 保護 (00:1c.2 D0) が S3 待機電力に与える影響は未知 (当時の 0.06–0.10W は保護なし)。
`/usr/local/sbin/s3-soak-measure.sh` を流用 (要: 実機に残存しているか P0 で確認、無ければレポート記載から再作成):
```bash
# LID0 を一時凍結 (spurious 回避) → AC 抜く → 8h セグメント計測
sudo systemd-run --collect --unit=s3r-night /usr/local/sbin/s3-soak-measure.sh 28800 1800 s3r
# 翌朝: sudo grep RESULT /var/log/s3-soak-measure.log → charge_now 差分で W 算出
```
判定目安: ~0.1W 級なら圧勝 (現行 s2idle+保護 1.6W の 1/16)。仮に保護のせいで数百 mW 増えても s2idle 比で優位は揺るがない見込み。

## Phase 5: 採否判定・恒久化・レポート

**採用条件**: Phase 1 で保護実効 + lid wake 動作、Phase 2 で 0/30 clean。

採用時の恒久化 (すべて可逆に):
1. **deep 化**: 起動時 oneshot を新規作成 (旧 s3-deep-apply の設計流用、ただし今回は LID0 凍結はしない)。GRUB `mem_sleep_default=deep` への変更は 1–2 週間の常用 soak 通過後に判断 (6/20 と同じ二段構え)
2. **LID0 ポリシー**: Phase 3 の結果に従い、動的フック (AC 連動) or 常時有効
3. 常用 soak 継続 (60-s3-soak-log は type/gpe70/lid を記録済みなのでそのまま監視に使える)。ウォッチリスト: hang 再発 / spurious wake / 待機電力 / hibernate 遷移の挙動

**不採用時**: `echo s2idle | sudo tee /sys/power/mem_sleep` で即時復帰 (再起動でも戻る)。hang が出た場合はその decode 結果自体が C-7 (iv) 機序解明の一級データになるのでレポート化。

レポート: `report/yyyy-mm-dd_hhmmss_s3_deep_retrial_*.md` (CLAUDE.md ルール準拠、タイムスタンプは `TZ=Asia/Tokyo date`、本プランを attachment に添付)。フェーズ分割実施の場合はフェーズごとにレポート。メモリ (`s3-revival-evaluation.md` 等) も更新。

## 触ってはいけないもの

- udev rule `99-c7r3-wl-d3cold.rules` (恒久対策、本検証でも保護は付けたまま)
- GRUB (Phase 2 で hang → dpmwd4 re-arm する場合のみ、bak 取得 + `sync` の上で一時変更・撤収時復元)
- `~/.ssh/config` 等ユーザ管理ファイル
- 60-s3-soak-log / 70-h4-probe 等の残置フック (流用するが改変しない。Phase 5 で動的 LID0 フックを**新規ファイルとして**追加する場合のみ例外)

## 主要参照レポート

- S3 断念の経緯: `report/2026-06-18_142303_why_not_s3_deep_sleep.md`
- S3 復活評価 (lid wake 21/21+7/7、gpe70 spurious): `report/2026-06-18_233837_s3_revival_evaluation.md`
- S3 待機電力計測: `report/2026-06-19_094329_s3_battery_standby_power.md`
- S3 deep 永続化の設計 (可逆 oneshot): `report/2026-06-20_045414_s3_deep_persist_soak_start.md`
- S3 hang 4 件と no-go: `report/2026-06-27_072510_bluetooth_vpn_lid_close_hang.md`
- 真因確定 + udev rule: `report/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md`
- dpmwd4 re-arm/decode 手順: `report/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md`
- 調査総括: `report/2026-07-13_005126_suspend_hang_investigation_summary.md`
