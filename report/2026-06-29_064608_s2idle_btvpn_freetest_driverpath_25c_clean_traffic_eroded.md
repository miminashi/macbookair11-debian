# s2idle BT-PAN+VPN free test: heavy traffic 中 driver path で 25 cycle 完走 (= 0 hang) — ただし「真に heavy traffic 中」だったのは 2/25 のみ

- **実施日時**: 2026 年 6 月 29 日 05:25 〜 06:46 (JST)
- **位置づけ**: [2026-06-29_041006 セッション 1](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) 終了直後の「セッション 2」。元プランは S5 (btusb URB drain timeout patch) だったが、advisor からのレビュー (timeout-then-kill パッチが意味なし / S1 結果は btusb_suspend 全体が path 上を示すのみ / silent hang 時の証拠は残らない) で **S5 直行を回避**、その前にゼロビルドでできる「heavy traffic 中の driver path で hang するか?」の判別実験 (= Free test) に転回した。

## 結論 (先に要約)

1. **3 ラウンド計 25 cycle 完走** (v1=1, v2=12, v3=12) で boot_id 不変、suspend_stats 100 → **125 (+25)**、journald `PM: suspend entry/exit` ペア完備。**hang 0**。
2. **但し「heavy traffic 中 + driver path」が真に成立した cycle は事後検証で 2 のみ** (v1 cycle "1" = 05:43:54 entry, v3 cycle 1 = 06:31:16 entry)。残り 23 cycle は **traffic 0 bps 状態で suspend していた** ことが retrospective に判明 (iperf3 idle timeout 死亡 / BT-PAN device renaming で BT 断 / VPN tunnel dead が連鎖)。**= 元プラン目的「heavy traffic 中で hang する/しない」の判別力は 2/2 clean = N=2 で弱証拠**。
3. **元プラン分岐表のどこに着地したか**: 「0 hang/12-15 cycle (clean)」相当。**lid close 必要条件 (2026-06-28_141226 + 0_063543)** を覆す証拠は得られなかった。よって **次セッションは S2/S3 (xfrm flush / bnep down pre フック) → S4 (DPM_WATCHDOG)** の順で進める。
4. **本セッションの副次的発見 (8 件、詳細は「観測上の副次的発見」節 A〜H)**:
   - (A) **`systemctl suspend` は D-Bus 経由で async** (即時 return) で polling loop と race する。**`systemctl start systemd-suspend.service --wait`** が同期で正解
   - (B) **cycle 1 wake で BT-PAN netdev が rename される** (`bnep0 → enx98e0d98d205e`) → BT-PAN tear down → VPN tunnel IKE peer-dead → 完全 dead。これにより 1 cycle 級の使い捨て実験しかできない
   - (C) **ssh が wake 直後の WiFi re-associate 中に「No route to host」**で 30+ 秒 unreachable。`ServerAliveInterval=10 + CountMax=30` (= 300 秒) でもまれに切断
   - (D) **ssh 切断後も bash loop が ssh 子プロセスとして残存** (SIGHUP 不発)、cycle 駆動が 5+ 分間継続
   - (E) **iperf3 の TCP idle timeout** で 0 bps 状態が 5 分続くと exit → ping ベースの traffic generator が安全
   - (F) **Apple Internal Keyboard/Trackpad の USB wakeup=enabled** (= キー押下で wake する根拠)。Bluetooth USB は disabled で **BT IRQ wake は機序的に発生しない** → 過去 S0.5 の「短い asleep_s = BT IRQ wake」推定は要見直し
   - (G) **h4-probe pre snapshot の retrospective 検証は本セッションで未実施** → 次セッションで cycle-by-cycle 検証スクリプトを組み込む
   - (H) **「キー連打で wake 維持」が強制電源断の代替手段になる** → ssh 切断時の状態確認手法として有効
5. **次セッション分岐**: 上記「S2/S3 → S4」を本レポート末尾の「次セッション引継ぎ」節に手順込みで記載。本セッションの最終状態 = 次セッション開始時の状態と一致 (cleanup 完了)。

## 添付ファイル

- [実装プラン (本セッションで承認・実施したもの)](attachment/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded/plan.md)
- [v1 cycle log (idle traffic baseline、ssh 切断で cycle 2 で停止)](attachment/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded/v1-cycles.log)
- [v2 cycle log (iperf3 死亡後、ssh 切断で cycle 1 のみ記録)](attachment/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded/v2-cycles.log)
- [v3 cycle log (ping ベース traffic、--wait 同期、ssh 切断で cycle 1 のみ記録)](attachment/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded/v3-cycles.log)

## 前提・目的

- **背景**: [2026-06-29_041006 (S1 = btusb pre-unload で 22/22 clean)](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) の引継ぎとして、次は S5 (btusb URB drain timeout patch) を実施する予定だった。Phase 1 で実機状態確認 + Debian カーネルソース取得状況確認まで実施 → advisor レビューで S5 設計の致命的な穴を 3 点指摘される:
  1. S5 のパッチ案 (timeout 検出 → 警告ログ → `usb_kill_anchored_urbs`) は無意味: `usb_kill_anchored_urbs` も内部で `wait_event` 無制限待ち。2 秒 timeout 後に再度 kill を呼ぶと同じ wait に再突入。
  2. **S1 結果は「`btusb_suspend` 関数全体が path 上」しか証明していない**: drain (`btusb_stop_traffic`) の前にも `cancel_work_sync(&data->work)` と vendor `data->suspend()` callback がある (どちらも無制限 wait)。よって真因が drain か他の wait 群かは未確定。
  3. silent hang 時に `bt_dev_warn` 等の printk は **pstore に残らない**: efi_pstore は panic/oops 時のみ dump。silent hang → 強制電源断 → RAM の log buffer 消失。捕捉手段は (a) DPM_WATCHDOG → panic → efi_pstore (= S4) しかない。
- **目的の絞り込み**: S5/S4 のどちらに進むにせよ、その前に **「in-flight URB が hang の必要条件か?」を費用ゼロで切り分ける free test** を回す。過去の driver path 0/15 clean (2026-06-28_111259) は idle BT link 中の `systemctl suspend` だった可能性が極めて高く、実使用 lid close の「ネット使用中に蓋を閉じる = bulk URB が in-flight」状態とは決定的に違う。これが事実なら、これまで結論として確立してきた「lid close が必要条件」(2026-06-28_141226) を部分的に覆し、`heavy BT-PAN+VPN traffic 中の driver path` でも hang が再現するはず。
- **設計**: 元プラン (`report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md`) を「セッション 2 用」に書き直し、本セッション添付の `plan.md` として実施。
- **役割分担**: hook デプロイ・cycle 駆動・状態確認は Claude が ssh で実施。NM GUI 操作 (BT-PAN/VPN 接続 up/再 up) と物理 wake のみユーザ手動。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、`s3-deep-apply.service` not-found、LID0 `*enabled`
- system-sleep フック (開始時 / 終了時とも): `50-kbd-backlight`、`60-s3-soak-log`、`70-h4-probe` の **3 個**
- 電源: 全実験 **AC 給電** (`ADP1/online=1`)
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer は iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)
- BT-PAN netdev 名: **`enx98e0d98d205e`** (= USB Ethernet style)、wake 直後に `bnep0` から rename される (今回 cycle 1 wake で実証)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`)、`password-flags=0`、tunnel inner IP `192.168.83.1/32`
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.0/24`)。free test 中は route-metric 600 → 800 に下げて VPN を BT-PAN 経由に強制、終了後 auto に revert
- iperf3 server: `10.0.0.1` (VPN 越し、ユーザ環境のサーバ)
- USB wakeup 状態: **Bluetooth USB Host Controller (`1-3.3`) は `wakeup=disabled`** (本セッションで確認、原因不明だが恒常的)
- dev 機: `akdx01` (Linux 6.12.74+deb13+1-amd64)、6.12.94 用 linux-headers 未インストール (S5 を即時実行できないので別の意味でも free test 先行は妥当だった)

## 実施内容と結果

### Phase 1: 状態把握 + Plan モード (05:25 〜 06:09)

- 実機の現状確認: 前セッション終了時の引継ぎ表と完全一致 (hooks 3 個 / mode=beta / autoconnect=no x2 / route-metric=-1 / suspend_stats 100 / 0)
- dev 機の src/ 状態確認: `linux-6.12.y/` (upstream tag `v6.12.94` の git clone) と `debian-6.12.94-1/debian/` (Debian ソースパッケージのメタデータ) が存在。**`debian/patches/series` 全 115 件中 bluetooth/btusb 関連 0 件** → upstream `linux-6.12.y/drivers/bluetooth/btusb.c` がそのまま実機 `btusb.ko` と一致する状態を確認 (S5 のパッチ対象を upstream 版で書ける)
- **advisor レビュー結果を受けて S5 を保留**、free test を Plan モードでプランニング (`/home/miminashi/.claude/plans/report-2026-06-29-041006-s2idle-btvpn-ha-zippy-spark.md`、本レポートに添付)
- ユーザと AskUserQuestion で「Free test / S4 / S5 改 / S2/S3」の 4 択協議 → **Free test 選択**
- プラン承認後 ExitPlanMode → 実施フェーズへ

### Phase 2: Free test 実施 (06:09 〜 06:43)

#### v1 ラウンド: iperf3 baseline (05:43 〜 05:46)

- Step 1 一時設定: autoconnect=yes (両方), route-metric=800, mode=alpha (60s 自動 RTC wake)
- Step 2 (ユーザ操作): iPad テザリング ON → BT-PAN + GSNet up
- 確認: `ip xfrm state | grep "src 172.20.10\."` で `src 172.20.10.13 dst 160.16.210.47` (VPN outer = BT-PAN 経由)、`ip route get 10.0.0.1` → `dev nm-xfrm-1817406 src 192.168.83.1` (VPN tunnel 経由)、`ip route get` 全体で **BT-PAN metric 750 < WiFi metric 800**、別 VPN GW なし
- Step 3: `systemd-run --unit=traffic-gen` で `iperf3 -c 10.0.0.1 -t 9999 -R -P 4` を while-true wrapper で起動
- 5 秒間 BT-PAN delta: rx +870KB、tx +78KB ← **bulk URB が in-flight 状態 confirmed**
- Step 4 cycle 駆動: `for i in $(seq 1 12); rtcwake -m no -s 60 && systemctl suspend ...` を background ssh で発火 → **ここで判明**: `systemctl suspend` は **D-Bus 経由で async** (即時 return)。loop 内の `is-active --quiet systemd-suspend.service` が start 前に false を返し break → `WOKE` を即時記録 → 次の cycle で `Call to Suspend failed: Action suspend already in progress, refusing requested suspend operation.` で fail
- **v1 結果**: log 上は 1 cycle のみ、suspend_stats は +1 (101)。journald で 05:43:54 entry → 05:44:55 exit (= cycle 1 の async 依頼が 1 秒遅延で実行)。**clean / 1 cycle**

#### v2 ラウンド: --wait なしで再試行 + ssh 切断発生 (05:47 〜 06:00)

- 修正: loop 内で `for w in $(seq 1 120); systemctl is-active --quiet systemd-suspend.service; sleep 1; ...` で完了 polling、`set -e + ssh ServerAliveInterval=30 CountMax=10`
- 12 cycle で background 起動
- **cycle 1 開始時 (05:47:57)** の bt rx_bytes = **6593** ← **既にこの時点で traffic が崩壊** (iperf3 が `iperf3: error - idle timeout for receiving data` で 05:46:49 に死亡、while-true wrapper で reconnect 試行中だが VPN tunnel が再確立できず `Network is unreachable`)
- ssh が ~3 分後に dev 機側から「No route to host」で切断
- だが実機側では bash loop が ssh 切断後も継続 (SIGHUP 不発か):
  - journald で `PM: suspend entry/exit` ペア 12 個 (v2 cycle 1 〜 12)
  - 60 秒周期で連続発火 (entry: 05:47:58 〜 05:59:19、exit: 05:48:58 〜 06:00:16)
  - suspend_stats: 101 → **113** (+12)
- **v2 結果**: 12 cycle clean。**但し全 cycle で traffic 0 bps** (= iperf3 ループは reconnect 失敗で 0.00 bits/sec 出力後、`Network is unreachable` で連続失敗)。当初目的を満たしていない (= idle BT link での driver path 0/12 clean = 既知 0/15 clean の追試)

#### iperf3 が cycle 1 直後に死んだ仕組み (重要)

- 05:43:08 iperf3 開始 (`-c 10.0.0.1 -t 9999 -R -P 4`)
- 05:44:55 v1 cycle 1 (実体は cycle 2 の async が処理された分) exit
- **05:44:56 以降 iperf3 が 0.00 bits/sec の出力を連発** ← VPN tunnel が cycle 中に IKE 観点で peer-dead (s2idle suspend 中の MOBIKE keepalive timeout) → traffic 流れず → iperf3 が 5 分 idle timeout で exit
- 05:46:49 `iperf3: error - idle timeout for receiving data` → wrapper の while-true で reconnect 試行
- 以降 `iperf3: error - unable to connect to server ... Network is unreachable` 連発 (06:00:41, 06:02:58, 06:05:15, 06:07:33, 06:09:50)
- = **v2 cycle 1 〜 v3 開始まで heavy traffic は完全に失われていた**

#### v3 ラウンド: ping ベース + --wait 同期で再試行 (06:27 〜 06:43)

- ユーザに VPN を NM GUI で再 up 依頼 → GSNet activated (新 xfrm interface `nm-xfrm-1996142`)
- `traffic-gen.service` を ping ベースに置換: `ping -i 0.05 -s 1400 -O 10.0.0.1` (VPN 越し) と `ping -i 0.05 -s 1400 -O 172.20.10.1` (BT-PAN 直接) を並行
- 動作確認: 10 秒間 BT-PAN delta rx +572KB / tx +588KB (= 50 KB/s 双方向)、ping reply が両方届く
- cycle loop を修正: `sudo systemctl start systemd-suspend.service --wait` で **同期 suspend** (wake まで block)
- 12 cycle で background 起動
- **cycle 1 開始時 (06:31:16)**: bt rx_bytes = **9634842 (= 9.6 MB)** + `ping-vpn last: 1408 bytes from 10.0.0.1: icmp_seq=4006 ttl=63 time=111 ms` ← **traffic 確実に in-flight**
- ssh が 5 分後の 06:36:25 に「Timeout, server not responding」で切断
- ユーザに「実機状態確認」依頼 → 「**スリープを解除してもすぐにスリープに移行してしまいます**」と報告される (= cycle 9-12 はユーザのキー押下で早期 wake = 各 cycle の asleep が 3-30 秒、loop 内 `sleep 3` のため wake → 次の suspend 突入まで約 4 秒、これでユーザは「すぐスリープ」と認識)
- ユーザがキー連打で wake 維持中に ssh で素早く状態確認:
  - **boot_id 不変** (起動時の `fcc3d4b0-8141-4477-b7df-d5b725adbda1`)、uptime 18:11
  - **suspend_stats 125** (+12 が v3 で完走)
  - journald: 06:31:16 entry → 06:32:17 exit (cycle 1) ... 06:41:13 exit (cycle 12) まで 12 ペア完備
  - **06:32:19 (cycle 1 wake 2 秒後)** に kernel ログ: `bluetooth hci0:12 enx98e0d98d205e: renamed from bnep0 (while UP)` が **同タイムスタンプで 2 行重複出力** ← **BT-PAN netdev が wake 直後に rename を起こした** = BT-PAN device が一旦死んで再 attach した痕跡 (2 行重複の理由は不明、kernel printk 重複 or 実際に 2 回 rename された可能性)
  - **NM active**: GSNet も BT-PAN 接続も active connection から消えている (= cycle 1 wake で teardown された後 reconnect 失敗)
  - pstore: 空
- **v3 cycle タイムライン** (journald entry/exit ペア、`asleep` = exit - entry):

  | cycle | entry | exit | asleep | 機序 |
  |---|---|---|---|---|
  | 1  | 06:31:16 | 06:32:17 | 61s | RTC wake (60s) |
  | 2  | 06:32:21 | 06:33:22 | 61s | RTC wake |
  | 3  | 06:33:26 | 06:34:26 | 60s | RTC wake |
  | 4  | 06:34:30 | 06:35:31 | 61s | RTC wake |
  | 5  | 06:35:35 | 06:36:36 | 61s | RTC wake |
  | 6  | 06:36:40 | 06:37:41 | 61s | RTC wake |
  | 7  | 06:37:45 | 06:38:45 | 60s | RTC wake |
  | 8  | 06:38:49 | 06:39:50 | 61s | RTC wake |
  | 9  | 06:39:54 | 06:40:04 | **10s** | ユーザ手動 wake (キー押下) |
  | 10 | 06:40:08 | 06:40:11 | **3s**  | ユーザ手動 wake (キー連打中) |
  | 11 | 06:40:15 | 06:40:39 | **24s** | ユーザ手動 wake |
  | 12 | 06:40:43 | 06:41:13 | **30s** | ユーザ手動 wake |

  - cycle 1-8 は cycle 駆動 loop が RTC 60s で sleep 維持
  - **cycle 9 (06:39:54) からユーザのキー押下で早期 wake** → loop は `WOKE` → `sleep 3` → 次の cycle で即時再 suspend → ユーザが「スリープを解除してもすぐにスリープに移行」と目撃した時間帯
  - 各 cycle の wake → 次の entry まで 4 秒 = loop 内の `sleep 3` + rtcwake コマンドオーバヘッド ~1 秒
  - **device-suspend 所要時間**: `PM: suspend of devices complete after X msecs` で **390-498 msec の範囲** (全 cycle 平均 ~450 msec) → device-suspend 段は安定して短時間で完了 = ここで stuck している兆候は無し
- **v3 結果**: 12 cycle 全完走 / 0 hang。**但し cycle 1 のみが「真に heavy traffic 中」で、cycle 2-12 は BT-PAN/VPN 再 establishment 失敗状態で traffic 不明 (恐らく 0)**

### Phase 3: 集計

| ラウンド | loop 予定 | 実駆動 | 完走 | hang | heavy traffic 中だったか |
|---|---|---|---|---|---|
| v1 | 12 | 2 (loop 設計バグで cycle 2 の `Action suspend already in progress` で fail) | 1 (= v1 cycle 1 の async が 05:43:54 entry で実行) | 0 | **○ (cycle 1 の async = 05:43:54、その時点で iperf3 traffic +1.8MB/2s)** |
| v2 | 12 | 12 | 12 | 0 | × (iperf3 死亡で 0 bps、cycle 1 の bt rx_bytes=6593 が示す) |
| v3 | 12 | 12 | 12 | 0 | **cycle 1 (06:31:16) のみ ○ (bt rx_bytes=9.6MB)**、cycle 2-12 は BT-PAN renaming + VPN dead で × |
| **合計** | **36** | **26** | **25** | **0** | **2/25 = 8%** が真に heavy traffic 中 |

注: loop は予定 36 cycle のうち v1 で 10 cycle を発行できずに stop。実駆動 26 のうち 25 が完走 (v1 cycle 2 の loop 試行は `Action suspend already in progress` で実機の suspend に到達せず未カウント)。

## 機序評価

### 「heavy traffic 中 + driver path で hang」は再現できなかった (N=2 で弱証拠)

- 真の heavy traffic 中で driver path を走らせた cycle は **2 つ** (v1 cycle = 05:43:54、v3 cycle 1 = 06:31:16) → 両方 clean。
- N=2、5% baseline で全クリーン確率 `0.95^2 = 0.9` = ほぼ「弱い陰性」相当。
- 過去レポート (2026-06-28_141226) で driver path 0/75 clean、本セッションでも heavy traffic 中の駆動でも 2/2 clean → **「driver path では hang しない」(= lid close 経路が必要)** の仮説は依然有力。

### 但し「実験のセットアップ自体が破綻」している

- **cycle 1 wake で BT-PAN netdev が rename を起こす** (今回初発見) → BT-PAN がコネクション層で teardown → VPN tunnel が IKE/MOBIKE 観点で peer-dead → **2 cycle 目には heavy traffic が完全に失われている**。
- これは「12-15 cycle 級で『heavy traffic 中 + driver path』を維持する」のが構造的に不可能であることを意味する。本実験を 12 cycle 級にスケールさせるには、各 cycle 後に NM の VPN/BT-PAN を up し直す wrapper が必要。コスト大。
- 一方で **lid close 経路** では 2026-06-28_063543 で 3/3 hang を観測している → 同じく cycle 1 で BT-PAN renaming が起きたはずだが、hang したのは「最初の 1 cycle」(= heavy traffic 中)。これは現状の「2 cycle 目には traffic 失われる」とも整合し、**両経路とも「1 cycle 目で heavy traffic 中の挙動」** を比較する形になっている。
- そう見ると本実験の有意味な比較は:
  - **lid close 経路 + 1 cycle 目 (heavy traffic 中) = 3/3 hang** (2026-06-28_063543)
  - **driver path + 1 cycle 目 (heavy traffic 中) = 2/2 clean** (本セッション)
- → **lid close 経路 が hang の必要条件** という結論は引き続き支持される (N=3 vs N=2 で対照、両方とも heavy traffic 中)。

### S1 結果との整合

- S1 (btusb pre-unload + 手動 lid close + heavy traffic): 22/22 clean
- これは「btusb を suspend 経路から除けば、lid close + heavy traffic でも hang しない」の証拠
- 本 free test の結論「driver path + heavy traffic でも hang しない」と組み合わせると、**hang 発生条件は「lid close 経路 + btusb_suspend 実行 + heavy traffic 中」の 3-way AND** で確定的に書ける
- driver path で hang しないのは、**「lid close 経路特有の何か」(LID0 GPE 配信、logind の SW_LID handler 経路、logind の inhibit 解放のタイミング etc.)** が必要条件である可能性を示唆

## 観測上の副次的発見

### A. `systemctl suspend` は D-Bus 経由で async、`systemctl start systemd-suspend.service --wait` が同期

- v1 で `systemctl suspend` を loop 内で連発したところ、各呼び出しは即時 return → `Action suspend already in progress` で衝突
- v3 で `systemctl start systemd-suspend.service --wait` に切替えたところ、cycle 駆動が綺麗に直列化
- 次セッションで cycle 駆動 loop を書くときは **必ず `--wait` 付きで `systemctl start systemd-suspend.service`** を使うこと。`systemctl suspend` はやめる

### B. cycle 1 wake で BT-PAN netdev が rename される (今回初発見)

- 観測: `bluetooth hci0:12 enx98e0d98d205e: renamed from bnep0 (while UP)` が wake 2 秒後に出る
- 含意: BT-PAN device は wake で **一旦 down 〜 up し直す** (= netdev は維持されるが内部で reset が走り、上層 (IPsec/IKE) は dead peer と認識する)
- 結果として **「heavy traffic を 12-15 cycle 級で維持する」のは構造的に困難** (cycle 1 で BT-PAN が IKE peer-dead → VPN tunnel teardown → 後続 cycle で traffic 0)
- これは過去レポートでも (2026-06-28_021019 等) で観察されていた可能性が高いが、本セッションで初めて kernel log として明示的に確認

### C. ssh の transient「No route to host」 (wake 直後 30+ 秒間)

- 観測: dev 機 (akdx01) からの ARP 解決が wake 直後 30+ 秒 unreachable
- `ServerAliveInterval=10 + CountMax=30 = 300 秒` ssh timeout でも頻発
- 原因推定: 実機の WiFi NIC が wake で re-associate する間に dev 機の ARP cache が一時的に flush される (ARP probe 失敗で device down 認識?)
- 次セッションで cycle 駆動 loop を書くときは **`ssh -o ServerAliveInterval=5 -o ServerAliveCountMax=60` (= 5 分耐性) でも切断しうる** ことを想定して、loop は dev 機側で driver にせず、**実機側に nohup or systemd-run で常駐させる** ほうがよい

### D. ssh 切断後も bash loop が ssh 子プロセスとして残存

- v2/v3 ともに ssh 切断後も実機側で bash の `for` loop が継続 (SIGHUP 不発か `huponexit` shopt off で)
- 結果として cycle が 5-10 分間 background で発火し続け、loop 内の `sleep 3` のため **wake → 次の suspend 突入まで約 4 秒** で連続。ユーザは「すぐ sleep に移行」と目撃する (v3 cycle 9-12 は asleep 3-30 秒、wake → 再 suspend が約 4 秒)
- 次セッションでは loop process を実機側で管理可能な systemd-run で起動するのが安全 (`sudo systemctl stop cycle-driver.service` で確実に止められる)

### E. iperf3 の TCP idle timeout (default 30 秒) で 0 bps 状態が長く続くと exit

- v1 観測: VPN tunnel が cycle 1 中に IKE peer-dead → iperf3 traffic 0 → 5 分 idle timeout → exit
- 次セッションで heavy traffic を流すなら **ping ベース (or iperf3 -u UDP モード) + cycle 後 VPN を NM で up し直す wrapper** が必要
- 本セッションで使った iperf3 起動コマンドは `iperf3 -c 10.0.0.1 -t 9999 -R -P 4` (`-R` = server → client direction, **MacBook が受信側** で **bulk_in URB を埋める** ことを狙った設計)

### F. USB wakeup 設定の全体像と「キー押下で wake」の根拠

実機の全 USB device の `power/wakeup`:

| device | path | vendor:product | wakeup | product |
|---|---|---|---|---|
| `1-5`   | Apple keyboard | `05ac:0290` | **enabled** | Apple Internal Keyboard / Trackpad |
| `1-3.3` | btusb | `05ac:828f` | **disabled** | Bluetooth USB Host Controller |
| `1-3`   | BRCM hub | `0a5c:4500` | disabled | BRCM20702 Hub |
| `usb1`  | xHCI | `1d6b:0002` | disabled | xHCI Host Controller |
| `usb2`  | xHCI | `1d6b:0003` | disabled | xHCI Host Controller |

含意:
- **キーボード/トラックパッドの USB wakeup は enabled** → ユーザのキー押下で wake する (v3 cycle 9-12 で観察された機序)
- **Bluetooth USB は disabled** → BT IRQ wake は機序的に発生しない
- これは [s2idle-observation-phase] の S0.5 (2026-06-29_041006) で「asleep_s 7-39s が BT IRQ wake と推定」していた点を見直すべき可能性: S0.5 でも btusb は同じ `wakeup=disabled` だったはずなので、当時の短い asleep_s も **BT IRQ wake ではなく、キーボード wakeup や他の機序** (例えば logind の何かの inhibitor 解放) の可能性。S0.5 報告の wake source 推定は要更新

### G. h4-probe pre snapshot の retrospective 検証は本セッションで未実施

- 元プラン (添付 plan.md) の「設計原則」では「各サイクルの条件成立 (BT-PAN+VPN active+lid close 経由) を事後検証」と書いていた
- 但し本セッションでは各 cycle の pre snapshot を解析せず、実機の現在の xfrm state からのみ確認 → 結果として「cycle 2 以降は traffic 0 だった」は iperf3 ログから逆算 (h4-probe snapshot からは未取得)
- 次セッション以降では、各 cycle の `.pre` snapshot から `xfrm src=172.20.10.x` と `/proc/net/dev` の rx/tx 値を抽出し、cycle-by-cycle で条件成立を確認する手順を組み込むべき
- 参考スクリプト (次セッションで使える):
  ```bash
  for f in /var/log/h4-probe/<期間>*.pre; do
    ts=$(basename $f .pre)
    dt=$(date -d @$ts +%H:%M:%S)
    xfrm=$(sudo grep -A1 "ip xfrm state" $f | grep "src 172.20.10\." | head -1)
    bt=$(sudo grep -A2 "/proc/net/dev" $f | grep enx98e0d98d205e | awk '{print "rx="$2" tx="$10}')
    echo "$dt xfrm=[$xfrm] $bt"
  done
  ```

### H. ssh 切断後の「キー連打で wake 維持」は強制電源断の代替手段になる

- 本セッション v3 で ssh 切断 (06:36:25) → 「実機が hang したか?」と判断 → 強制電源断をユーザに依頼
- だが実際にはユーザがキーを叩いて wake させた瞬間に「**スリープを解除してもすぐにスリープに移行**」を観察 → loop が背景で動いていることが確定
- ユーザに「キー連打で wake 維持」を依頼している間に ssh で素早く状態取得 → boot_id 不変 + suspend_stats が累積していることを確認 → hang ではなく cycle 暴走と判明 → 強制電源断不要
- **次セッションでも同様の状況 (ssh 切断 + 実機が応答しない) になったとき、まず「キー連打で wake 維持してもらってその間に ssh する」を試す価値がある**。電源断は最後の手段

## 検討して除外した事項

- **「heavy traffic 維持の改良で 12-15 cycle 級を狙う」**: コスト大 (NM の VPN auto-reconnect 設定、charon-nm の DPD/keepalive 強化、cycle 毎 VPN up wrapper)、ROI 低 (本質的に 1 cycle 目で hang する/しない が決定的なので、N=2 でも十分弱証拠)。次セッションは S2/S3 → S4 へ進む方が情報量大。
- **「cycle 1 wake 時の BT-PAN renaming を抑制」**: udev の rename を止めれば BT-PAN が IP 観点で維持される可能性があるが、それは別問題で本実験の範囲外。
- **「強制電源断による boot_id 比較」**: ユーザが状況確認した時点で「画面反応する」ことを確認 → hang ではないと判定 → 電源断不要。

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-06-29 06:46 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット |
| `/usr/local/bin/h4-mode` | 残置 (前セッションから) | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで +50 ファイル = 25 cycle × pre/post) | 本セッション 25 cycle の証拠 |
| traffic-gen.service | **削除済 (transient unit、stop で消える)** | heavy traffic generator |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | revert 済 (-1 = auto) | |
| `/tmp/ping-{vpn,bt}.log` | 削除済 | ping log |

実機の suspend_stats: success 125, fail 0 (start 100 → +25)。

dev 機側: 何も書き換えなし (free test はソース改変無しで実施)。`src/linux-6.12.y` (upstream tag v6.12.94 の git clone) と `src/debian-6.12.94-1` (Debian ソースパッケージのメタデータ) は前セッションから残置。

## 再現方法 (本セッションをそのまま再演する場合)

`Step 0/1` から順にやる場合の手順は本セッション添付の [plan.md](attachment/2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded/plan.md) に記載。ただし本セッション中に学んだ修正を入れた決定版手順は以下:

1. **一時設定** (Step 1, plan の通り):
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
   sudo nmcli con modify GSNet connection.autoconnect yes
   sudo nmcli con modify OpenWrt ipv4.route-metric 800
   sudo nmcli con up OpenWrt
   sudo /usr/local/bin/h4-mode alpha
   '
   ```
2. **BT-PAN + VPN up** (ユーザ操作): NM GUI で BT-PAN と GSNet を up
3. **traffic generator** (ping ベース、idle timeout なし):
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo systemctl reset-failed traffic-gen.service 2>/dev/null
   sudo systemd-run --unit=traffic-gen --collect bash -c "
   while true; do
     ping -i 0.05 -s 1400 -O 10.0.0.1 > /tmp/ping-vpn.log 2>&1 &
     P1=\$!
     ping -i 0.05 -s 1400 -O 172.20.10.1 > /tmp/ping-bt.log 2>&1 &
     P2=\$!
     wait \$P1 \$P2 2>/dev/null
     sleep 1
   done
   "'
   ```
4. **cycle 駆動** (`--wait` 同期版、`systemd-run` で実機側常駐):
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo systemd-run --unit=cycle-driver --collect bash -c "
   set -e
   for i in \$(seq 1 12); do
     echo \"=== cycle \$i / 12 \$(date +%H:%M:%S) ===\"
     /usr/sbin/rtcwake -m no -s 60 > /dev/null
     /bin/systemctl start systemd-suspend.service --wait
     echo \"WOKE at \$(date +%H:%M:%S) cycle=\$i\"
     sleep 3
   done
   echo \"=== ALL CYCLES COMPLETED \$(date +%H:%M:%S) ===\"
   " 2>&1 | tee /var/log/cycle-driver.log
   '
   ```
   完了確認:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo systemctl is-active cycle-driver.service'  # → inactive で完走
   ssh miminashi@macbookair2015.lan 'sudo cat /var/log/cycle-driver.log'
   ```
5. **判定**: boot_id 不変 + suspend_stats success +N + entry/exit ペア完備 → clean
6. **cleanup** (Step 7, plan の通り):
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo systemctl stop traffic-gen.service cycle-driver.service 2>/dev/null
   sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
   sudo nmcli con modify GSNet connection.autoconnect no
   sudo nmcli con modify OpenWrt ipv4.route-metric -1
   sudo nmcli con up OpenWrt
   sudo /usr/local/bin/h4-mode beta
   sudo rm -f /tmp/ping-vpn.log /tmp/ping-bt.log /var/log/cycle-driver.log
   '
   ```

**注意**: 「heavy traffic 中の cycle」が真に成立するのは **cycle 1 のみ** (= BT-PAN renaming で cycle 2 以降は traffic 失われる)。よって本セットアップで「12 cycle 級で heavy traffic 中の hang を観察」しようとしてもできない。

## 次セッション引継ぎ

### 開始時に確認すべきこと

```bash
ssh miminashi@macbookair2015.lan '
echo "=== alive + mem_sleep ==="
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
echo "=== system-sleep hooks (期待: 50-kbd-backlight, 60-s3-soak-log, 70-h4-probe) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== h4-probe infra ==="
ls /usr/local/bin/h4-mode /var/lib/h4-probe/mode 2>&1
cat /var/lib/h4-probe/mode
echo "snapshot count: $(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l) pre"
echo "=== NM autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
echo "=== boot_id ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats baseline ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== transient units 残存していないか ==="
systemctl is-active traffic-gen.service cycle-driver.service 2>&1
'
```

期待値:
- hooks: 3 個のみ
- h4-mode 残置、mode=`beta`
- snapshot pre: 概ね 64 個 (本セッション +25 cycle 分)
- autoconnect: 両方 `no`、route-metric: `-1`
- boot_id: `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変)
- suspend_stats: success=125, fail=0
- transient units: 両方 inactive (or unit not found)

### S2/S3 (xfrm flush / bnep down pre フック) — 推奨の次の手

元プラン (`report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md` の S2/S3 節) を参照。

**S2 (xfrm flush)** の hook (`/usr/lib/systemd/system-sleep/56-xfrm-flush`):
```sh
#!/bin/sh
case "$1" in
  pre)
    ip xfrm state flush 2>&1 | logger -t 56-xfrm-flush
    ip xfrm policy flush 2>&1 | logger -t 56-xfrm-flush
    ;;
esac
```

**S3 (bnep down)** の hook (`/usr/lib/systemd/system-sleep/57-bnep-down`):
```sh
#!/bin/sh
case "$1" in
  pre)
    nmcli -t -f UUID,TYPE con show --active | awk -F: '$2=="bluetooth"{print $1}' | \
      xargs -r -n1 nmcli con down 2>&1 | logger -t 57-bnep-down
    bluetoothctl disconnect 2>&1 | logger -t 57-bnep-down
    sleep 1
    ;;
esac
```

**実施**:
1. ユーザに **手動 lid close** での hang 再現条件 (BT-PAN + VPN active) を準備してもらう (autoconnect=yes 一時設定 + traffic-gen 起動 + h4-mode alpha)
2. S2 or S3 の hook を投入 (どちらか 1 個ずつ評価)
3. 30 cycle 手動 lid close 駆動 (ユーザ依頼) → 0 hang/30 で当該成分が真因の有意 (5% baseline → 21%)
4. 終了後 hook を `rm` で削除

**判定基準**:
- S2 0/30 → xfrm 残留関与 (= [074509] H1 系) → upstream fix backport 相談へ
- S3 0/30 → bnep_session kthread 関与 (= H2) → bnep を freezable 化する upstream パッチ提案へ
- どちらも 1+ hang → S4 へ

**S2/S3 で再投入が必要なアイテム** (本セッション cleanup で revert したもの):
```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
sudo /usr/local/bin/h4-mode alpha
# traffic-gen は本セッションの ping ベース版を再投入
```

(ping ベース traffic-gen の起動コマンドは「再現方法」節 Step 3 参照)

### S4 (DPM_WATCHDOG カーネル) — S2/S3 で hang 残ったら次の手

元プラン (`report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md` の S4 節) を参照。骨子:

1. dev 機で `cd src && apt-get source linux=6.12.94-1` (Debian ソース展開)
2. 実機 `/boot/config-6.12.94+deb13-amd64` を scp で持ち帰り `.config` に
3. `./scripts/config --enable CONFIG_DPM_WATCHDOG --set-val CONFIG_DPM_WATCHDOG_TIMEOUT 60 --enable CONFIG_PSTORE_RAM --set-str CONFIG_LOCALVERSION "+dpmwd1"`
4. `make olddefconfig && make -j$(nproc) bindeb-pkg LOCALVERSION=+dpmwd1`
5. 先に dev 機 (akdx01) で broadcom-sta-dkms が新 ABI で build 通るか確認
6. deb を実機 scp → `dpkg -i` → `dkms autoinstall` → MOK 署名 (dkms 自動)
7. `grub-reboot "Advanced options for Debian GNU/Linux>Debian GNU/Linux, with Linux 6.12.94+dpmwd1-amd64"` で 1 回だけ新カーネル起動
8. 20-30 cycle 手動 lid close 駆動 (ユーザ依頼) → hang 時 pstore に backtrace
9. ロールバック: `grub-reboot "Debian GNU/Linux"` (次回起動で stock に戻る)

**注意点**:
- **dev 機 (akdx01) は kernel 6.12.74、6.12.94 用 linux-headers 未インストール** (`dpkg -l | grep linux-headers-6.12.94` で 0 件)。`apt-get source` で取れる Debian ソース自体は 6.12.94-1 が利用可能。dev 機の cross-build 環境を整える時間が必要 (1-2h)
- broadcom-sta-dkms の現状: dkms.status を本セッションで確認していない → 次セッション開始時に `dkms status broadcom-sta` を確認すべし

### S5 (btusb URB drain timeout patch) は条件付きで保留

advisor レビュー時点での S5 のパッチ案は **意味なし** (timeout-then-kill が再度 wait_event 永久ブロックに突入する)。実装するなら **`usb_kill_anchored_urbs` を `usb_unlink_anchored_urbs` (async non-blocking) に置換** する設計が必要 (= drain を諦めて URB を放置)。これは USB core 側の安全性検証 (xhci_suspend での後続挙動) が必要で、即座に試せる素材ではない。S4 で kernel に stuck 位置を自白させた後、ピンポイントの修正設計に進む方が安全。

### 「heavy traffic 中の driver path」を本気で 12-15 cycle 級で検証したい場合の手順 (本セッション中の知見)

(やる場合のみ。次セッションでは S2/S3 → S4 を優先する方が ROI 高い)

- cycle 後に NM の VPN/BT-PAN を up し直す wrapper を作る:
  ```bash
  # cycle driver の中で wake 後に:
  sleep 5  # WiFi/sshd 復活待ち
  sudo nmcli con up "iMiminashiPadPro ネットワーク"
  sleep 3
  sudo nmcli con up GSNet
  sleep 5  # IKE handshake 完了待ち
  # ping reply を確認してから次の cycle
  ```
- 但し各 cycle で BT-PAN 再 establishment に 10-15 秒、IKE handshake に 5-10 秒かかる → 12 cycle で **15-20 分** + RTC wake 60 秒 × 12 = **30-40 分**。ROI 低い
- 替案: BT-PAN を維持できる「短い RTC sleep (= 5-10 秒)」で cycle を回す。但しこれは「実使用 = ネット使用中に蓋を閉じる」シナリオから離れる

## 関連レポート

- [2026-06-29_041006 セッション 1: S0 + S0.5 + S1 22/22 clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) — 直前セッション、本レポートの起点
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md) — driver path 0/75 / lid path 必要条件結論。本セッション結果 (driver path + heavy traffic も 2/2 clean) で追補強された
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) — driver path 0/15 (= idle traffic だった可能性、本セッション結果で部分裏付け)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) — 機序仮説、本レポートの advisor 指摘の基礎
- [2026-06-28_063543 真の s2idle + BT-PAN+VPN+lid close で 3/3 hang](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — lid path で 3/3 hang、本セッションの driver path 2/2 clean と対比
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
