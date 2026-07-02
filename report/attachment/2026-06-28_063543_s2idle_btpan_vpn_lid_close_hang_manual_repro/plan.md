# s2idle ハング手動再現セッション — 監視プロトコル

## Context（なぜこれをやるか）

[2026-06-28_021019 レポート](../../../projects/macbookair11-debian/report/2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)で、真の s2idle 下では **AC・自動 suspend ループ**で BT テザリングありでも 10/10 ハング 0 だった。だが同レポートが「最も切り分けたい未検証セル」と明記した条件＝**ユーザの実条件（battery + lid close→STH + VPN + BT-PAN, s2idle）**は手つかず。

今回はそれを**ユーザの手動操作で再現試行**する。Claude の役割は限定的:

- ユーザが「**状況を確認してください**」と言ったら、ターゲット実機の状態を確認して報告する
- ユーザが「**終わります**」と言ったら実験終了 → レポートを書く
- **suspend を Claude が driver で叩かない**（前回と違い 100% 手動）。BT-PAN/VPN の up はユーザが GUI で行う想定（依頼されれば ssh で代行可）

## ベースライン（セッション開始時スナップショット, 2026-06-28 04:18 JST 取得）

| 項目 | 値 |
|---|---|
| boot_id | `1bc7fb70-bf66-4140-ad0c-516672168eb2` |
| boot since | `2026-06-28 01:26:15`（= 6/27 #4 deep ハング後の強制電源断起点） |
| mem_sleep | `[s2idle] deep`（s2idle 選択） |
| LID0 wakeup | `*enabled`（lid wake 有効） |
| s3-deep-apply.service | disabled / inactive |
| 電源 | AC online=1 / BAT0=87% |
| s3-soak.log 最終 | `02:09:08 WAKE ... ss_ok=28 drm_err=0`（= 直前 ss_ok カウンタ=28） |
| 60-s3-soak-log フック | deep 強制 2 行は `# DISABLED-rollback-2026-06-28:` でコメント済（s2idle が維持される） |

**lid 挙動（確定）**: battery 蓋閉じ = `suspend-then-hibernate`（drop-in `10-suspend-then-hibernate.conf`, `SuspendEstimationSec=30min` → 30分後 hibernate to `/dev/sda3`）。AC 蓋閉じ = 素の `suspend`。

## ハング検出のセマンティクス（最重要・前回と違う点）

1. **driver ログ（susp-test.log）は今回**書かれない**（手動なので PRE/POST が無い）。** 主検出器は **`/var/log/s3-soak.log` の「SLEEP 行あり → 対応 WAKE 無し → 次行が BOOT」**（system-sleep フック `60-s3-soak-log` は lid close 由来の suspend でも自動発火する）。
2. **ssh 到達不可 ≠ ハング。** 正常に suspend 中の機体も ssh 不通になる。だから「ssh がタイムアウトした」だけではハングと判定しない／**suspend 窓に向けて status-check をリトライループしない**。判別はユーザが起こした後の挙動:
   - 到達可 + s3-soak.log に新しい WAKE → **正常復帰**
   - ユーザが蓋を開けた／キーを押しても**黒画面のまま** → ハング → ユーザが**物理電源ボタン長押しで強制電源断**→再起動 → **そこで確定検出**（boot_id 変化 + uptime リセット + s3-soak.log が SLEEP→BOOT で WAKE 欠落）
3. 到達不可のときは「**suspend 中かハングか不明。起こす操作をしてから再確認**」と報告し、推測でハング宣言しない。

## 「状況を確認してください」で実行する確認（再利用する 1 コマンド）

ssh で read-only に以下を取得（到達不可なら "asleep-or-hung" を報告）:

```bash
ssh -o ConnectTimeout=8 miminashi@macbookair2015.lan '
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)   (baseline 1bc7fb70-...)"
echo "uptime=$(uptime -p)  since=$(uptime -s)"
echo "ac=$(cat /sys/class/power_supply/ADP1/online) cap=$(cat /sys/class/power_supply/BAT0/capacity)%"
echo "mem_sleep=$(cat /sys/power/mem_sleep)  lid=$(grep -o "LID0.*" /proc/acpi/wakeup)"
echo "--- s3-soak.log tail ---"; sudo tail -n 6 /var/log/s3-soak.log
echo "--- BT/VPN active ---"; nmcli -t -f NAME,TYPE,DEVICE con show --active | grep -Ei "bluetooth|vpn"
echo "--- suspend entry/exit (b0) ---"; sudo journalctl -b 0 -g "PM: suspend (entry|exit)" -o cat | sort | uniq -c
'
```

判定:
- **boot_id がベースラインと同じ + uptime 連続** → セッション開始以降ハング 0（高速確認）。
- **boot_id 変化 / uptime リセット** → 再起動が起きた → s3-soak.log を遡って **SLEEP→(WAKE 無し)→BOOT** を探し、ハングか否か・条件（type/ac/cap、直前の BT-PAN/VPN）を確定。
- s3-soak.log の **SLEEP と WAKE がペアで揃い drm_err=0** → 正常。**SLEEP のみで WAKE 欠落の最終行** → その suspend で停止中（到達不可時）またはハング（再起動済時）。
- battery STH では **1 suspend で SLEEP/WAKE が 2 ペア記録され得る**（30分後の hibernate(S4)→resume を含む）。2 ペア目を異常と誤読しない。

## 終了時（ユーザが「終わります」）

CLAUDE.md のレポートルールに従い、`report/2026-06-28_021019` の**続編**としてレポートを作成:

1. タイムスタンプ: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`（推測しない）。ファイル名 `report/yyyy-mm-dd_hhmmss_<英語名>.md`。
2. 記載: 前提・目的（手動再現、未検証セル battery/STH+VPN+BT-PAN+s2idle）、環境情報、実験中に確認した状況（各「状況確認」の結果）、ハングの有無と条件、再現手順、元レポートへのリンク。
3. 添付 `report/attachment/<名>/` に実験窓の `s3-soak.log` 抜粋を格納しリンク。
4. レポート確定（durable 化）後に最終確認。

## やらないこと

- Claude から `systemctl suspend` / `systemd-run` / rtcwake で suspend を**注入しない**（手動セッション）。
- mem_sleep / LID0 / フックを**変更しない**（s2idle ロールバック状態を維持。観測専念）。
- ssh タイムアウト 1 回でハング宣言しない／suspend 窓にリトライループしない。
