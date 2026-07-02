# Free Test: heavy BT-PAN+VPN traffic 中の driver path suspend で hang を起こすか

## Context

[2026-06-29_041006 セッション 1 レポート](/home/miminashi/projects/macbookair11-debian/report/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) で S1 (btusb pre-unload) 22/22 clean を観測し、**「btusb_suspend 経路を物理的に除けば hang 消失」** までは確定した。次セッションの本命は元プランでは S5 (btusb URB drain timeout patch) だが、advisor からのレビューで以下の致命的な穴が指摘された:

1. **S1 結果は「`btusb_suspend` 関数全体が path 上」しか証明していない**。`btusb_suspend` には drain (`btusb_stop_traffic`) の前に `cancel_work_sync(&data->work)` と vendor `data->suspend()` callback がある (どちらも無制限 wait)。S1 はそれらすべてを回避しただけなので、真因が drain 内か他の wait 群かは未確定。
2. **元 S5 のパッチ案 (timeout 検出 → `bt_dev_warn` → `usb_kill_anchored_urbs`) は無意味**: `usb_kill_anchored_urbs` (`urb.c:808-832`) は内部で `usb_kill_urb` を loop し、その中で `wait_event(usb_kill_urb_queue, atomic_read(&urb->use_count) == 0)` (urb.c:713) を **無制限に待つ**。2 秒 timeout 後に再度 kill を呼ぶと同じ wait に再突入し、結局同じ hang が 2 秒遅れて発生するだけ。
3. **silent hang 時に `bt_dev_warn` 等の証拠は残らない**: efi_pstore は panic/oops 時のみ dump。silent hang → 強制電源断 → RAM の printk buffer は消失する。stuck 位置を捕捉する手段は (a) DPM_WATCHDOG → panic → efi_pstore (= S4) しかない。

これらを踏まえると、**S5 / S4 のどちらに踏み込むにせよ、その前に「in-flight URB が hang の必要条件か」を費用ゼロで切り分ける free test** を回すのが最も情報量が高い。過去の driver path 0/15 clean (2026-06-28_111259) は idle BT link 中の `systemctl suspend` だった可能性が極めて高く、**実使用 (= 蓋を閉じる瞬間に実際に通信が流れている)** との決定的な違いがそこにある可能性がある。これが事実なら、これまで結論として確立してきた「**lid close が必要条件**」(2026-06-28_141226) すら部分的に覆り、もっとシンプルな再現条件が出てくる。

本プランはその free test を 1 セッションで完了し、結果で次の分岐 (S5 改 / S4 / S2/S3) を決める。

## やること

### 概要

実機 (macbookair2015.lan) で:

1. **既存準備**: 70-h4-probe + h4-mode + mode=alpha (60s RTC 自動 wake)
2. **一時設定**: autoconnect=yes (BT-PAN/GSNet 両方) + WiFi route-metric=800 (VPN を BT-PAN 経由に強制) — S1 と同じ revert 可能設定
3. **Heavy traffic 生成 (ユーザ操作)**: BT-PAN/VPN 経由で **継続的に bulk URB が in-flight になるトラフィック** を流し続ける (候補は後述)
4. **Cycle 駆動 (ssh 自動 loop)**: `rtcwake -m no -s 60 && systemctl suspend` を 12-15 cycle 回す。**手動 lid close は使わない** — driver path の純粋検証のため
5. **観測**: 各 cycle で h4-probe pre snapshot に `xfrm src=172.20.10.x` と pre snapshot の取得そのもの (= suspend に入った証拠) が出るか + `/proc/net/dev` の rx/tx delta で実トラフィックが流れていたか確認
6. **判定**: hang / clean

### 詳細手順

#### Step 0: 開始時の現状確認

```bash
ssh miminashi@macbookair2015.lan '
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
ls /usr/lib/systemd/system-sleep/
cat /var/lib/h4-probe/mode
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
'
```

期待値: hooks = `50-kbd-backlight 60-s3-soak-log 70-h4-probe` のみ、mode=`beta`、autoconnect=no x2、route-metric=-1、success=100、fail=0。

#### Step 1: 一時設定 (S1 と同様、revert 可能)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
sudo /usr/local/bin/h4-mode alpha
'
```

#### Step 2: BT-PAN + VPN active 化 (ユーザ操作)

ユーザが NM GUI で:
- iPad のテザリングを ON、`iMiminashiPadPro ネットワーク` 接続を up
- `GSNet` 接続を up
- 確認: `ip xfrm state | grep "src 172.20.10."` が出力 → BT-PAN 経由 VPN 確立済

```bash
ssh miminashi@macbookair2015.lan '
ip xfrm state | grep "src 172.20.10\."
ip route get 160.16.210.47
'
```

期待: `xfrm state` に `src 172.20.10.x` が出る、route の outgoing iface が `bnep0` (BT-PAN)。

#### Step 3: Heavy traffic を流し続ける (ユーザ操作で開始 → cycle 駆動中も維持)

**狙い**: 「`systemctl suspend` の瞬間に bulk URB が in-flight 状態」を作る。

実施候補 (どれか 1 つ以上を併用、ユーザの判断で):

- **(A) MacBook で VPN 経由の large file download**: 自宅 VPN 越しの社内サーバ等から `curl -o /dev/null https://...big-file...` をループ実行 (DL 速度より大きなファイル or `--limit-rate` 無しで連続)。**VPN endpoint (`160.16.210.47`) の先に何が触れるかは事前にユーザに確認** (社内 HTTP server / SMB / iperf3 等)
- **(B) MacBook 上で iperf3 を VPN 経由でサーバへ**: VPN endpoint の先に iperf3 server があれば `iperf3 -c <server> -t 600 -P 4` 等で連続 push/pull
- **(C) MacBook 上で大量 ICMP**: `ping -i 0.05 -s 1400 8.8.8.8` (背景タブで実行、低負荷だが連続 in-flight。VPN 越しの xfrm 経由で BT-PAN を通る)

**最低限**: (C) を ssh の別セッションで開始しておく (8.8.8.8 への ping は外向き ICMP echo / VPN 経由で BT-PAN を流れる)。可能なら (A) も併用。なお iPad の cell traffic 自体 (例: iPad 上で YouTube) は **MacBook の BT-PAN bulk URB を流れない** (iPad は consumer で MacBook はテザリング client だけ)、heavy traffic の発生源は **必ず MacBook 側** から流す必要がある。

heavy traffic の確認:
```bash
ssh miminashi@macbookair2015.lan 'cat /proc/net/dev | grep bnep0'
```
期待: rx/tx の bytes が cycle 間で増加していること (cycle 前後で delta > 0)。

#### Step 4: Cycle 駆動 (ssh 自動 loop)

ssh 別セッションで:

```bash
ssh miminashi@macbookair2015.lan '
set -e
for i in $(seq 1 12); do
  echo "=== cycle $i $(date) ==="
  cat /proc/net/dev | grep -E "bnep0|wlp3s0"
  sudo rtcwake -m no -s 60
  sudo systemctl suspend
  # systemctl suspend は wake まで block するはず
  echo "WOKE at $(date)"
  sleep 5
done
'
```

**重要**: `systemctl suspend` は内部で `pwait` し、wake してから戻る。よって `loop の中で次の cycle に進めれば = wake 成功 = clean`、**進まない (ssh が無応答になる) = hang**。

判定: ssh セッションが無応答 **120 秒以上** (rtcwake 60s + 余裕 60s) + 別 ssh で `boot_id` 確認 → hang 認定。ssh の接続維持は `ServerAliveInterval` 等の client 側設定に依存するが、過去セッション (S1 22 cycle) で 60+ 秒の suspend を ssh 越しに何度も完走している実績あり。万一 ssh が切れた場合は別 ssh で `boot_id` を確認 (不変 = wake 後ただ TCP が切れただけ、変化 = hang による強制リセット)。

#### Step 5: hang 検出時の対応

ハングしたら:
- 強制電源断 → 電源再投入で recovery
- pstore に何か残っていないか確認: `sudo ls /sys/fs/pstore/`
- 直近の h4-probe pre snapshot を保存 (rsync) — 添付ファイル化候補
- 駆動 loop を停止し、結果記録

#### Step 6: cycle 完了時の判定とフィードバック

12-15 cycle 完了後:

```bash
ssh miminashi@macbookair2015.lan '
echo "=== boot_id ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== h4-probe snapshots (本セッション分) ==="
sudo ls -la /var/log/h4-probe/ | tail -30
echo "=== journald SLEEP/WAKE pair ==="
sudo journalctl -k --since "-1 hour" | grep -E "PM: suspend entry|PM: suspend exit"
'
```

判定:
- **boot_id 不変 + suspend_stats success +N + entry/exit ペア完備 → clean**
- いずれか欠落 → hang

#### Step 7: cleanup (revert)

```bash
ssh miminashi@macbookair2015.lan '
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
sudo /usr/local/bin/h4-mode beta
'
```

70-h4-probe / h4-mode / /var/log/h4-probe/ は残置 (次セッションでも使う)。

#### Step 8: レポート作成

Step 7 完了後 (= 状態が次セッション開始時と同じに戻った状態) で、後述の「レポート作成と引継ぎの運用方針」に従ってレポートを書く。レポート書き込みで Discord 通知が走るので、書き込みは cleanup 完了後にする (revert 漏れを防ぐ)。

書き込む場所: `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_<英語名>.md`。レポート名 (英語) は free test の結果を含むものにする (例: `s2idle_btvpn_traffic_driverpath_freetest_NofN`)。

### 分岐: free test の結果に応じた次の手

| Free test 結果 | 解釈 | 次の手 (候補) |
|---|---|---|
| **1+ hang/12-15 cycle** | in-flight URB が必要条件 = drain が真因確度大幅向上。lid close は無関係 (or 単に「実使用で URB を発生させる手段」だっただけ) | **S5 改 (drain → `usb_unlink_anchored_urbs` 非同期)** を実装。同時に S4 と並走させても良い (S4 で stuck 行が `usb_kill_urb` 関連と自白するか確認) |
| **0 hang/12-15 cycle (clean)** | in-flight URB は trigger ではない。logind / lid close 経路特有の何か (cancel_work_sync、freeze 順序、xfrm 残留、bnep_session kthread、LID0 GPE と suspend race) | 候補は 2 つ: **(a) S2/S3 (xfrm flush / bnep down pre フック)** を先に挟む (安価, 30 cycle/各, hook 1 ファイル) — H1/H2 を低コストで消化 / **(b) S4 (DPM_WATCHDOG カーネル) を最優先** — kernel に stuck 行を自白させる方が情報量大きいが build/MOK/grub-reboot のコスト大。**次セッション開始時にユーザと協議して決定** |
| **限界事例 (ssh 無反応だが boot_id 不変)** | suspend 中で ssh が固まっただけ、wake で復活? → 追加調査 | journald で実体確認、cycle 数を伸ばす |

## レポート作成と引継ぎの運用方針

本プランは **1 セッション内で完結する単発の判別実験 (free test)** だが、結果分岐後の次セッション (S5 改 / S4 / S2/S3 / 追加調査) は別セッションになる。よって本セッションのレポートには次セッション引継ぎを必ず記載する。

具体的に、Step 7 (cleanup) 完了後の Step 8 でレポート (`report/YYYY-MM-DD_HHMMSS_<英語名>.md`) を作成し、以下を含めること:

1. **結論 (先に要約)**: free test 結果 (X/N cycle, hang 有無)、解釈、決まった分岐先
2. **「次セッション引継ぎ」セクション**: 上の分岐表に従い、決定した次の手 (S5 改 / S4 / S2/S3 / 追加調査) の具体的な開始手順を書く
   - **S5 改へ進む場合**: btusb.c のどの行を `usb_unlink_anchored_urbs` に置換するか、dev 機の linux-headers-6.12.94+deb13-amd64 入手手段 (apt vs snapshot vs 実機 build tree scp)、broadcom-sta MOK 鍵の流用手順、cycle 駆動の前提 (mode/autoconnect/route-metric)、ロールバック手順
   - **S4 へ進む場合**: `apt-get source linux=6.12.94-1` の dev 機実施、CONFIG_DPM_WATCHDOG 等の `scripts/config` 投入コマンド、`make bindeb-pkg` の手順、broadcom-sta-dkms との互換確認、MOK 署名、grub-reboot の指定、hang campaign 30 cycle の手順、pstore からの backtrace 抽出方法、ロールバック (`grub-reboot "Debian GNU/Linux"`)
   - **S2/S3 へ進む場合**: 元プラン (`report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md` の S2/S3 節) の hook (`56-xfrm-flush` / `57-bnep-down`) を参照、cycle 駆動の前提 (autoconnect, route-metric, mode), 30 cycle 駆動手順、判定基準 (0 hang/30 で上流提案 or 仮説確証)、ロールバック (hook ファイル `rm`)
   - **追加調査の場合**: 具体的に何を観測すべきか (例: `cancel_work_sync` を疑うなら data->work の作業内容を btusb.c で調査)
3. **「開始時に確認すべきこと」**: 引継ぎ先セッションで最初に走らせる ssh ワンライナー (hooks、mode、autoconnect、route-metric、suspend_stats、ソース展開状態) — 前セッションレポートの引継ぎ節と同形式
4. **「再投入が必要なアイテム」**: cleanup で外したものの中で次セッションで再導入したいもの (autoconnect=yes, route-metric=800, h4-mode alpha 等)
5. **「残置物」表**: マシン (dev 機/実機) 上に残した状態の一覧
6. **添付**: 本プランファイルを `report/attachment/<レポート名>/plan.md` にコピー、`scripts/` も同様に添付。レポート本文の冒頭で `## 添付ファイル` 節からリンク

引継ぎが書かれていない (= 次セッションが「最初から状況把握をやり直す」ことになる) 状態でセッションを終えない。本プランの完了 = レポート書き込み + 引継ぎ完備 + (必要なら) cleanup。

なお free test の結果で hang が出た場合は、レポートに「強制電源断によるリカバリ後の状態」「pstore に何か残っていれば抽出」「直近 hang サイクルの h4-probe pre snapshot を添付」も含めること。

### 補足: なぜ heavy traffic 中 driver path で「lid close 必要条件」が崩れる可能性があるか

過去の論証は以下:
- 2026-06-28_021019: AC で BT-PAN 単独 (VPN 無し) + lid close → 10/10 clean
- 2026-06-28_063543: AC で BT-PAN + VPN + lid close → 3/3 hang (相互作用が必要)
- 2026-06-28_111259: BT-PAN + VPN active で `systemctl suspend` (driver path) → 0/15 clean
- 2026-06-28_141226: driver path 0/75 (両機種)、lid path で再現

結論として「**lid close 経路が必要条件**」を確立してきたが、driver path のすべての cycle で **bulk URB が in-flight だったかは検証していない**。`systemctl suspend` は事前に traffic を止めて即座に呼ばれるため、suspend 突入時には bulk_anchor が empty (or 1-2 個の制御 URB のみ) だった可能性が高い。

一方で実使用の lid close は「ネット使用中に蓋を閉じる」= bulk URB が in-flight。この差が真因なら、driver path + heavy traffic で hang が再現し、「lid close 必要条件」は誤った絞り込みだったことになる。

## Critical Files

- **読む**: 
  - 既存レポート `report/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md` (S1 結果 + 引継ぎ手順)
  - `src/linux-6.12.y/drivers/bluetooth/btusb.c:1975-1982` (`btusb_stop_traffic`)、`:4280-4310` (`btusb_suspend`) — Debian カーネルは btusb に独自パッチ無し (`debian-6.12.94-1/debian/patches/series` 確認済) なので upstream `v6.12.94` タグの本ファイルが実機 `btusb.ko` と一致
  - `src/linux-6.12.y/drivers/usb/core/urb.c:798-832` (`usb_kill_anchored_urbs`), `:700-720` (`usb_kill_urb` の wait_event)
- **編集**: 無し (free test はソース改変無し)
- **既に投入済 (実機, 残置)**:
  - `/usr/lib/systemd/system-sleep/70-h4-probe`
  - `/usr/local/bin/h4-mode`
  - `/var/lib/h4-probe/mode`

## 検証

- 各 cycle で h4-probe が `.pre` / `.post` ファイルを `/var/log/h4-probe/` に出力 → cycle 数と一致するか
- suspend_stats success delta == cycle 数 (hang 無し時)
- `journalctl -k --since` で SLEEP/WAKE ペア確認
- `cat /proc/net/dev | grep bnep0` の rx/tx 差分で heavy traffic 流量を retrospective に確認

## ロールバック

- 一時設定 (autoconnect/route-metric/mode) を Step 7 で revert
- hang 発生時の強制電源断は通常 boot で復旧 (s2idle は揮発状態)

## 関連レポート

- `report/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md` (前セッション、S1 結果)
- `report/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md` (driver 経路 0/75 / lid 経路必要条件結論 — free test で再評価対象)
- `report/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md` (driver 経路 0/15 — idle traffic だった可能性)
- `report/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md` (H1/H2/H4 仮説)
- `report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md` (3/3 hang factorial)
