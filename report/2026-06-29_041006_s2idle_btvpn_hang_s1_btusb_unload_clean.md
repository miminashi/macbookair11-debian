# s2idle BT-PAN+VPN lid close hang 切り分けセッション 1: S0 観測装置 + S0.5 α/β 試行 + S1 btusb pre-unload 22/22 クリーン

- **実施日時**: 2026 年 6 月 28 日 15:25 〜 2026 年 6 月 29 日 04:10 (JST)
- **位置づけ**: [2026-06-28_074509 カーネルソース解析レポート](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) で立てた機序仮説 H1/H2/H4 のうち、**H4 (btusb_suspend → URB drain 永久ブロック)** を直接介入で検証する段階的切り分けラダー (プラン S0 → S0.5 → S1) の第 1 回セッション。次セッションで S5 (btusb URB drain timeout 試作モジュール) に進む準備が整った状態。

## 結論 (先に要約)

1. **S1 (btusb pre-unload): 22/22 全クリーン** (boot_id 不変, suspend_stats 78→100 success/fail 0)。**btusb を device-suspend 経路から物理的に除けば、本ハング条件 (BT-PAN+VPN+手動 lid close) で 22 cycle 連続 hang 0** を観測。5% baseline 仮定で全クリーン確率 0.95^22 ≒ **32%** ≒ **「btusb 経路除去で hang 消失」の中等度陽性証拠**。**H4 寄り (btusb_suspend が critical path に乗っている)** の方向性が支持された。
2. **S1 限界**: 本ハック (`bluetoothd` 停止 → モジュール unload) は btusb 除去と同時に「BT-PAN 接続を suspend 前に teardown」も実行している。**「btusb_suspend が真因」 vs 「BT-PAN active での logind 経路が真因」 の最終識別は S1 設計上できない**。次の S5 (URB drain timeout patch でフル btusb 路線を維持しつつ修正) で因果を確定させる。
3. **S0 (パッシブ観測装置): デプロイ済 + 動作確認済**。`/usr/lib/systemd/system-sleep/70-h4-probe` が pre/post で xfrm/bnep/btusb/lsmod/dmesg を `/var/log/h4-probe/$(date +%s).{pre,post}` に durable に記録 (各 ~58KB)。`pm_debug_messages=1` も pre フックで毎回有効化。**pstore は efi_pstore バックエンドが registered 済** (S4 で必須となる)。
4. **S0.5 (α/β 判別)**: 8 cycle 試行。**asleep_s が 7〜39s と短く、60s RTC alarm 前に何かが wake** (gpe70=0 = LID0 wake ではない)。**BT-PAN traffic (iPad テザリング) が btusb 経由で USB IRQ wake を起こしている可能性が高い** → BT 接続中の pure α テストは構造的に困難と判明。両モード合算で 8/8 clean = α/β 個別失敗なし (弱い対称的陰性証拠) のまま、機序ラダー S1 に進んだ。
5. **memory note 訂正**: 「lid wake は s2idle で構造的に不可能」(2026-06-18 結論) は S3 deep 評価期の状況のもので、**現状の s2idle (LID0 *enabled) では lid open で wake 動作する**。本セッション中に複数回 (S0 stuck からの recovery、α/β 試行) で実証。S0.5 設計の前提が成立。
6. **次セッションへ**: 引継ぎ手順を本レポート「次セッション引継ぎ」節に記載。実機は **観測装置のみ残した状態** (S1/S0.5 hook 削除、S0 hook + h4-mode は維持)。S5 (btusb URB drain timeout patch + module 単独ビルド + MOK 署名 + 60 cycle 検証) からスタートする。

## 添付ファイル

- [実装プラン (macbook-air-distributed-aurora.md)](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md)
- 本セッションで実装した全スクリプト (最終版、次セッションで再投入可能):
  - [`70-h4-probe`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/70-h4-probe) — S0 パッシブ観測フック (pre/post スナップショット)
  - [`65-rtcwake`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/65-rtcwake) — S0.5 safety net rtcwake (mode に応じた alpha=60s / beta=300s)
  - [`55-btusb-down`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/55-btusb-down) — S1 btusb pre-unload フック (bnep busy 時の bluetoothd 停止 fallback 込み)
  - [`90-vpn-autoup`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/90-vpn-autoup) — S1 post で h4-vpn-restore を systemd-run --no-block 起動
  - [`h4-vpn-restore`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/h4-vpn-restore) — S1 post worker (BT-PAN ready 待ち + nmcli con up GSNet retry)
  - [`h4-mode`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/h4-mode) — alpha/beta モード切替 (self-sudo elevation 込み)

## 前提・目的

- **背景**: [2026-06-28_141226 (lid path required + αβ未分離)](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md) と [2026-06-28_074509 (カーネルソース解析 H1/H2/H4 仮説)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) を承け、機序仮説の **直接的判別実験** を実施する段階。Phase 1 で macbookair2015 の状態を再確認し、Phase 2 でプラン (`macbook-air-distributed-aurora.md`) を設計、Phase 3 で実行段階に入った。
- **目的**:
  - (S0) パッシブ観測装置を実機にデプロイし、将来 hang が発生したときの「最後の pre snapshot」が証拠として残るようにする
  - (S0.5) `rtcwake` を使って **入眠側 (α)** か **復帰側 (β)** かを分離する判別実験を行う
  - (S1) btusb を device-suspend 経路から物理的に除いて hang 率を観測 (H4 の経路有無を直接検証)
- **役割分担**: Hook デプロイ・smoke test・state revert は Claude が ssh で実機操作。**ハング再現に必要な手動 lid close cycle はユーザが実機で手動実施** (Claude からは引き金を引けない)。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `mem_sleep=[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、`s3-deep-apply.service not-found` (deep ロールバック完了)、`LID0 *enabled` (lid wake 有効)
- system-sleep フック (本セッション開始時): `50-kbd-backlight`、`60-s3-soak-log` (deep 強制行コメント済 = s2idle 維持)
- 電源: 全実験 **AC 給電** (`ADP1/online=1`)、バッテリ 87%
- pstore: `efi_pstore as persistent store backend` (registered)、`/sys/fs/pstore` mount 済 (空)
- pm_debug_messages: `0` (本セッションで 70-h4-probe が pre 毎に `1` 設定)
- DPM_WATCHDOG: stock kernel で無効 (S4 で要)
- 過去 30 日 journald に `unregister_netdevice: waiting` 出現なし (H1 確度低)
- **Bluetooth/テザリング**: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer は iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)
- **VPN**: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`)、`password-flags=0`
- **WiFi**: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.x`)。S1 実験中は **route-metric を一時 600→800 に下げて VPN を BT-PAN 経由に強制**、終了後 auto に revert
- broadcom-sta-dkms 6.30.223.271-26, dkms 3.2.2

## 実施内容と結果

### S0: パッシブ観測装置 + pstore 検証 (15:25〜)

**実施**:
- `/sys/fs/pstore` 動作確認 → mount 済、efi_pstore バックエンド registered (kernel dmesg より) → **S4 の DPM_WATCHDOG panic を受け止める素地 OK**
- `/usr/lib/systemd/system-sleep/70-h4-probe` を投入 (最初 `/etc/systemd/system-sleep/` に置いたが **このバージョンの systemd-sleep は `/usr/lib/` しか scan しない** ことが判明し移動)
- 70-h4-probe は pre/post で以下を `/var/log/h4-probe/$(date +%s).{pre,post}` に出力後 `sync`:
  - `uname -a`, `mem_sleep`, `pm_debug_messages`, `suspend_stats/*`
  - `ip -o link show`, `ip addr show`, `ip xfrm state`, `ip xfrm policy`, `/proc/net/dev`
  - `nmcli active connections`, `lsmod` (btusb/btintel/bnep/bluetooth/xfrm/wl)
  - 全 USB device の `power/runtime_status` / `runtime_active_time` / product / manufacturer
  - `/proc/acpi/wakeup`, `gpe70` カウンタ, `bluetoothctl devices Connected`
  - `dmesg -T | tail -300`, `journalctl -n 200 -k`
- `pm_debug_messages` は pre フックで `1` を毎回 echo (再起動で消える可逆設定)
- mode マーカー `/var/lib/h4-probe/mode` ({alpha,beta}) と切替コマンド `/usr/local/bin/h4-mode` (self-sudo elevate, set -e で silent failure 防止)

**smoke test**: 12s rtcwake + `systemctl suspend` で pre/post pair が `/var/log/h4-probe/` に書き込まれ、`70-h4-probe[...]: phase=pre/post target=suspend mode=... file=...` が journald に残ることを確認。

**判定**: **S0 デプロイ OK**。pstore 動作 → S4 で DPM_WATCHDOG backtrace 回収可能。

### S0.5: α/β 判別子 試行 (16:30〜16:56)

**設計**: `65-rtcwake` (pre フックで mode に応じた `rtcwake -m no -s <60|300>` を仕掛ける safety net) を追加。
- mode=alpha → 60s で RTC 自動 wake (蓋を触らない = α テスト)
- mode=beta  → 300s safety net (lid open or 何か別経路で起こす = β テスト)

**初回事故 (16:05)**: 当初の `h4-mode` スクリプトが非 root 実行時に silent failure (mode file 書き込み denied だが script は exit 0 + 成功 message 表示) → mode=beta のまま suspend → wake トリガー無し → **macbookair2015 が s2idle で 24 分 stuck (16:05 SLEEP → 16:30 WAKE asleep_s=1461s)**。ユーザに lid open で復帰してもらい、**lid open で s2idle wake が動作することを実証** (memory note の「lid wake は s2idle で構造的に不可能」は古い結論)。`h4-mode` を `set -e` + 自動 sudo elevate に書き直し、`65-rtcwake` も「mode に関わらず常に safety net rtcwake を仕掛ける (alpha=60s / beta=300s)」に再設計して再発防止。

**α 駆動セッション (16:49〜16:56)**: ユーザが BT-PAN+VPN active 状態で 8 cycle (条件成立 8/8 = `xfrm src=172.20.10.13` 全 cycle、全 `PM: suspend entry (s2idle)`)。

| # | SLEEP | WAKE | asleep_s | mode | gpe70 |
|---|---|---|---|---|---|
| 1 | 16:49:46 | 16:50:25 | 39 | alpha | 0 |
| 2 | 16:50:55 | 16:51:10 | 15 | alpha | 0 |
| 3 | 16:51:39 | 16:51:57 | 18 | alpha | 0 |
| 4 | 16:52:26 | 16:52:42 | 16 | alpha | 0 |
| 5 | 16:53:56 | 16:54:10 | 14 | alpha | 0 |
| 6 | 16:54:42 | 16:54:49 | 7 | alpha | 0 |
| 7 | 16:55:17 | 16:55:39 | 22 | alpha | 0 |
| 8 | 16:56:11 | 16:56:25 | 14 | alpha | 0 |

**観察**: asleep_s が 7〜39s と短く、**60s RTC alarm 前に何かが wake**。gpe70=0 なので **LID0 wake ではない**。最有力仮説は **BT-PAN traffic (iPad テザリング) の btusb 経由 USB IRQ wake**。

**判定**: 8/8 全クリーン (両モード合算でα/β どちらの個別失敗もなし)。ただし **pure α テスト (RTC 単独 wake) は BT 通信が秒単位で wake をかけるため構造的に困難** と判明。識別力を上げるには btusb の wakeup 一時無効化が必要 (`/sys/bus/usb/.../power/wakeup`) だが、ROI が低いため次の S1 (btusb 物理除去) に進むことをユーザと合意。

### S1: btusb pre-unload (03:25〜03:56)

**Hook 設計**:
- `/usr/lib/systemd/system-sleep/55-btusb-down` (pre): `modprobe -r bnep btusb btintel`。**bnep が "in use" で失敗するため fallback で `bluetooth.service stop` → 再試行 → marker touch**。post で modprobe 復元 + marker あれば `bluetooth.service start`。
- `/usr/lib/systemd/system-sleep/90-vpn-autoup` (post): `systemd-run --no-block` で `/usr/local/sbin/h4-vpn-restore` を **transient unit として** 起動 (これ重要: 単純な `&` 起動だと systemd-suspend.service の cgroup cleanup で kill される、`setsid` でも cgroup から逃げられず)。h4-vpn-restore は BT-PAN 接続が `activated` + iface IP 取得を最大 120s 待ち、`nmcli con up GSNet` を最大 6 回 retry。
- mode は beta (300s safety) で開始したが、**btusb 除去後は BT IRQ wake も lid wake も効きづらい** (ユーザが「蓋を開けても wake しない、電源ボタン短押しで復帰」を報告) → alpha (60s 自動 RTC wake) に途中切替えて運用。

**事前準備 (テスト中限定の可逆変更)**:
- `iMiminashiPadPro ネットワーク` と `GSNet` の `connection.autoconnect: no → yes` (毎 cycle の手動再接続を回避)
- `OpenWrt` の `ipv4.route-metric: -1 → 800` (= BT-PAN 750 より低優先 → VPN が BT-PAN 経由になる)
- いずれも S1 終了時に **元値に revert 済**

**駆動 (03:25:38 〜 03:56:54)**: ユーザが手動 lid close + 自動/手動 wake で 22 cycle。各 cycle で条件成立 (`xfrm src=172.20.10.13`) を pre snapshot で事後検証 = **22/22 成立**。

| 統計 | 値 |
|---|---|
| 完了 cycle | **22 / 22** |
| ハング | **0** |
| boot_id | 不変 (`fcc3d4b0-8141-4477-b7df-d5b725adbda1`) |
| suspend_stats success/fail delta | +22 / +0 |
| 条件成立 (`xfrm src=172.20.10.13` in pre) | 22 / 22 |
| asleep_s 分布 | 9〜86s (中央値 61s)。22 cycle 中 10 cycle は ~60s RTC 自動 wake、残り 12 cycle はユーザ操作 (lid open or 電源ボタン短押し) による早期 wake |

**注意点**: 70-h4-probe (priority 70) が capture する pre snapshot で nmcli の bluetooth/GSNet は "off" 表記。理由は **55-btusb-down (priority 55) が 70-h4-probe より先に走って bluetoothd を停めるため**。条件成立の判定は **kernel 側 xfrm state** (bluetoothd 停止に影響されない) で確実に取れる。

**判定**: 22/22 clean → btusb 経路除去で hang 消失の中等度陽性証拠。5% baseline 仮定で全クリーン確率 0.95^22 ≒ 32%。プラン目標は 30 cycle (p ~21%) だが、ユーザが 20 で打切り (実際は 22 まで到達) を選択。

### 機序評価

**S1 結果 22/22 clean が示すこと**:
- btusb の `btusb_suspend` callback (および `btusb_stop_traffic` → `usb_kill_anchored_urbs` の URB drain) が hang の critical path に乗っていた可能性が高い (H4 寄り)
- ただし **本ハック (`bluetoothd` 停止 → モジュール unload) は btusb を除く副作用として「BT-PAN 接続を suspend 前に teardown する」** ことも同時に達成している
- よって最終的な因果は次の 2 つのどちらか:
  - (a) **btusb_suspend 自体が hang していた** → btusb を suspend 経路から除けば消える
  - (b) **BT-PAN active な状態で logind 経路の suspend を始めること自体が trigger** → BT-PAN が suspend 前に dead なら logind 経路でも消える
- (a) と (b) の識別は **S5 (btusb URB drain timeout patch を入れたフル btusb 路線維持の修正)** で hang が消えるかどうかが決定打になる。S5 が clean なら (a) 確定。S5 で hang 残るなら (b)、別経路探索へ。

**141226 driver path 0/75 (iPhone 30 + iPad 30 + 111259 iPad 15) + S1 lid close path 0/22 の組合せで言えること**:
- driver path (rtcwake + systemctl suspend) は btusb 残置 + BT-PAN/VPN active でも clean → **logind 経路が hang の必要条件** (driver 経路 = logind handler を通さない = hang 出ない)
- S1 (btusb 除去 + 手動 lid close = logind 経路) は clean → **btusb (≒ btusb_suspend) も必要条件**
- → hang は **「logind 経路 + btusb_suspend 呼出 + BT-PAN/VPN active」3 条件の AND** で発火する
- 仮説 H4 (btusb_suspend → URB drain block) は logind 経路で freeze 直後の dpm_suspend 段で URB drain が固まる、と説明する
- これが正しいなら、URB drain に timeout を入れた btusb は logind 経路 + BT-PAN/VPN active でも clean になるはず (= S5 で検証)

## 観測上の副次的発見 (mechanism research / 次セッション以降で有用)

本セッションのインフラ構築・smoke test 過程で得た、ハング機序の本筋とは別の **再現性のある事実**。次セッションの hook 設計・解釈で参照する。

### A. systemd-sleep は `/usr/lib/systemd/system-sleep/` しか scan しない (このバージョンで)

このマシンの `systemd 257.x` (Debian 13) の `systemd-sleep` バイナリには **`/usr/lib/systemd/system-sleep` の path のみ** が hard-coded されており、`/etc/systemd/system-sleep/` に置いた hook は **発火しない**。確認方法:
```bash
strings /lib/systemd/systemd-sleep | grep system-sleep
```
将来 hook を投入する際は `/usr/lib/systemd/system-sleep/` を必ず使うこと。本セッションでは最初 `/etc/` に置いて 1 回 silent fail した。

### B. `bnep` モジュールは `bluetoothd` が常に socket を保持している

BT-PAN 接続の有無に関わらず、`bluetoothd` が動いている間は `bnep` モジュールが "in use" 状態。よって **`modprobe -r bnep` は単独では必ず失敗** し、`bluetooth.service` を先に止める必要がある。S1 hook の fallback path はこれを受けて設計。S5 でも btusb 関連の module-only 操作を試みる際は同じ前提が効く。

### C. NM の VPN connection は parent (BT-PAN) が再 up しても確実には自動再接続しない

`connection.autoconnect=yes` 設定でも、suspend→resume サイクルで parent connection (BT-PAN) が一度切れて再 up したときに、VPN (`GSNet`) は自動で連動して up しないことを S1 で複数回観測。`nmcli con up GSNet` を別経路から打つ必要がある (本セッションでは `h4-vpn-restore` worker で対応)。

### D. systemd-suspend.service の cgroup cleanup は `setsid` 単独では逃れられない

post hook 内で `setsid <worker> &` で background 化したワーカーは、**systemd-suspend.service の完了とともに cgroup cleanup で kill される** (本セッションで実証: `h4-vpn-restore` の最初の起動はログに "starting" 1 行だけ残して消失)。`systemd-run --no-block --unit=<name>` で **transient service として起動** することで cgroup から完全に離脱できる。post hook で長時間のワーカーを spawn したい場合の常套手段。

### E. btusb 除去環境では **lid open による s2idle wake が機能しない** (本セッション新発見)

S1 hook で btusb を unload した状態で suspend に入ると、**蓋を開けても画面は真っ暗のまま反応せず、電源ボタン短押しで wake** する状況をユーザが複数 cycle 報告。stock btusb 環境では同条件で lid open が wake トリガーとして動くことと対照的。機序は未確定だが仮説:
- btusb 除去で USB host controller が異なる electrical state に入り、LID0 GPE 配信経路にも影響している可能性
- BT IRQ が wake assist として機能している可能性 (BT-PAN traffic も無くなるため)

S5 (patched btusb を load した状態) では stock 同様 lid wake が動くはず → 検証時の wake トリガー設計に影響する。S1 系の追加実験を行う場合は **mode=alpha (60s RTC 自動 wake)** を必須にすること。

### F. `gpe70` カウンタは LID0 GPE のみを反映、他の wake 源は ticks しない

`/var/log/s3-soak.log` の `gpe70=N` は LID0 _PRW = lid wake の発火回数だけを数える。**RTC alarm wake, 電源ボタン wake, USB IRQ wake (btusb 経由) では tick しない**。よって `gpe70=0 かつ asleep_s < 60s` は「lid 以外の何か (USB IRQ や電源ボタン) で起きた」を意味する。S0.5/S1 でこの含意を使って wake source を推定した:
- asleep_s ≒ 60s + gpe70=0 → RTC wake (mode=alpha)
- asleep_s ≒ 300s + gpe70=0 → RTC safety wake (mode=beta)
- asleep_s 短 (< 60s) + gpe70=0 → BT IRQ wake or 電源ボタン or 他経路
- asleep_s 任意 + gpe70=1+ → 確実に lid wake

### G. NM の route metric デフォルトは WiFi 600 < BT-PAN 750 (= WiFi 優先)

`OpenWrt` (WiFi) と `iMiminashiPadPro ネットワーク` (BT-PAN) が同時 active のとき、デフォルトでは WiFi のメトリックが低い (= 優先) ため、`GSNet` (VPN) の宛先 `160.16.210.47` への経路は **WiFi 経由 (xfrm src=192.168.33.145) になり、BT-PAN 経由にならない**。ハング条件を成立させるには:
- (a) WiFi 切断: 確実だが ssh 観測が切れる
- (b) `nmcli con modify OpenWrt ipv4.route-metric 800` で WiFi を下げる: ssh 維持可能 (本セッション S1 で採用、終了後 auto に revert)

S5 検証でも同じ前提が必要。

### H. h4-mode の silent failure → 24 分 stuck の教訓

初回の `h4-mode` スクリプトは非 root 実行時に mode file 書き込みが permission denied だったが **exit 0 で「成功」message を返していた**。これで mode=beta のまま suspend → rtcwake 仕掛けられず → 24 分 s2idle stuck (lid open で復帰)。修正: `set -e` + 自動 sudo elevation で再発防止。**hook / 制御スクリプトには必ず `set -e` を入れる**こと。

### I. `/sys/power/suspend_stats/` では本ハング条件は検出されない

本セッション全 40+ cycle で `success` カウンタは増加 (60→100) するが `fail` / `last_failed_*` は全て空 (0/null)。stock kernel の DPM_WATCHDOG 無効状態では、本ハング条件 (dpm_suspend 段の無音永久 loop) は **完了もしないし known failure としても記録されない=完全に "uncounted"**。よって `suspend_stats` ベースの監視は本問題には無力で、ハング検出は依然として:
- `boot_id` 変化 (= 強制電源断後の再起動を示唆)
- `s3-soak.log` の `SLEEP` 行 → 対応 `WAKE` 欠落
- `PM: suspend exit` ペア欠落
の 3 点セット (141226 と同じ判定方法) でしか行えない。S4 で DPM_WATCHDOG 有効カーネルを入れれば、初めて sysfs + pstore 経由の dmesg backtrace で hang を捕捉可能になる。

---

## 検討して除外した事項・観測上の限界

- **「Pure α テスト」**: BT 通信 (iPad → btusb USB IRQ) が秒単位で wake をかけるため、60s RTC を待つ前に system が起きてしまう。btusb wakeup を一時無効化すれば成立するが、ROI 低と判断して S1 へ移行。次セッション以降で必要になれば `/sys/bus/usb/<dev>/power/wakeup` を `disabled` に書き込んで再試行可能。
- **22 cycle で打切り**: プラン目標 30 cycle を 8 不足だが、5% baseline で p 値は 0.32 → 0.21 への改善幅は限定的。それより S5 (因果確定) の方が情報量が多いと判断。次セッションで S5 が clean なら S1 cycle 数の追加検証は不要、hang 残るなら S1 を 60 cycle 級まで伸ばすことを検討。
- **「(a) vs (b) の識別」**: 本 S1 の設計上できない (上述)。S5 で識別する。
- **BT IRQ wake の影響**: S0.5 の asleep_s 短さの原因と推定したが直接観測していない。次セッションで `/proc/acpi/wakeup` と `gpe70` 以外の wake source カウンタ (例: USB IRQ アクティビティ) を取れば実証可能。
- **「(α) 入眠側」 vs 「(β) 復帰側」 hang の最終識別**: S0.5 では asleep_s 短さで pure α テスト不能のため未識別。仮に S5 で hang が消えれば「H4 の URB drain は入眠側 dpm_suspend 段で固まる」が支持され、両方の側面から α 確定 (074509 ソース解析と整合) となる。

## 次セッション引継ぎ

### 開始時に確認すべきこと

```bash
ssh miminashi@macbookair2015.lan '
echo "=== alive + mem_sleep ==="
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
echo "=== system-sleep hooks (期待: 50-kbd-backlight, 60-s3-soak-log, 70-h4-probe のみ) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== h4-probe infra (期待: h4-mode, /var/lib/h4-probe/mode, /var/log/h4-probe/) ==="
ls /usr/local/bin/h4-mode /var/lib/h4-probe/mode 2>&1
ls /var/log/h4-probe/ | head -5
echo "snapshot count: $(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l) pre / $(sudo ls /var/log/h4-probe/*.post 2>/dev/null | wc -l) post"
echo "=== NM autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
echo "=== suspend_stats baseline ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
'
```

期待値:
- system-sleep hooks: `50-kbd-backlight`, `60-s3-soak-log`, `70-h4-probe` の **3 個のみ** (55-btusb-down/65-rtcwake/90-vpn-autoup は削除済)
- `/usr/local/bin/h4-mode` 残置、`/var/lib/h4-probe/mode=beta`
- `/var/log/h4-probe/` に **39 pre + 39 post = 78 ファイル** (本セッションの累積 + 過去 smoke test)
- `iMiminashiPadPro ネットワーク` と `GSNet` の autoconnect: 両方 `no`
- `OpenWrt` の route-metric: auto (-1)
- `s3-deep-apply.service`: `not-found`
- suspend_stats success: 100 前後 (本セッション終了時 100)、fail: 0

### S5 (btusb URB drain timeout patch) の実施手順

[プラン S5](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/plan.md) の手順に従い、以下の順で実施。

1. **ソース取得 (dev 機)**:
   ```bash
   cd /home/miminashi/projects/macbookair11-debian/src
   apt-get source linux=6.12.94-1   # snapshot.debian.org でも可
   ```
2. **btusb_stop_traffic の URB drain を timeout 付き wait に置換 (`src/linux-6.12.94/drivers/bluetooth/btusb.c`)**:
   - 該当箇所: `btusb_stop_traffic()` 内の各 anchor (`bulk_anchor`, `intr_anchor`, `isoc_anchor`, `diag_anchor`, `ctrl_anchor`) に対する `usb_kill_anchored_urbs()` 呼び出し
   - 置換イメージ:
     ```c
     if (!usb_wait_anchor_empty_timeout(&data->bulk_anchor, 2000)) {
         bt_dev_warn(data->hdev, "btusb: bulk_anchor URB drain timed out, force-killing");
         usb_kill_anchored_urbs(&data->bulk_anchor);
     }
     ```
   - 全 5 anchor に同様の対処。timeout 値は 2000ms 程度から調整。
3. **モジュール単独ビルド (dev 機)**: build tree を実機からスシ で取得 or `apt install linux-headers-6.12.94+deb13-amd64` で揃え、`make -C <build-tree> M=$PWD/src/linux-6.12.94/drivers/bluetooth modules`
4. **vermagic 一致確認**: `modinfo --field=vermagic btusb.ko` が実機 stock kernel の `6.12.94+deb13-amd64 SMP preempt mod_unload modversions` と完全一致
5. **MOK 署名**: `<build-tree>/scripts/sign-file sha256 /var/lib/dkms/mok.key /var/lib/dkms/mok.pub btusb.ko`
6. **実機配置**: scp で実機の `/lib/modules/6.12.94+deb13-amd64/updates/btusb.ko` に置く → `depmod -a` → `modprobe -r btusb && modprobe btusb` → `modinfo btusb | grep filename` で updates/ 配下が読まれていることを確認
7. **smoke test**: BT-PAN ペアリング・接続が変わらず動作するか確認
8. **検証セッション**: 60 cycle の手動 lid close (BT-PAN+VPN active)。autoconnect 一時 yes 設定が必要 (本セッションと同じ手順、終了後 revert)。S5 用に `65-rtcwake` の再投入も推奨 (mode=alpha=60s 自動 wake で 60 cycle 駆動を効率化)

### S5 を始める前に必要な「再投入」アイテム

S1 cleanup で削除済だが、S5 検証で再投入したいもの。**すべてアタッチの `scripts/` 配下に最終版あり**:
- **`/usr/lib/systemd/system-sleep/65-rtcwake`** (mode に応じた safety net rtcwake) → [`scripts/65-rtcwake`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/65-rtcwake)
- **autoconnect=yes 一時設定** (BT-PAN + GSNet 両方): `sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes && sudo nmcli con modify GSNet connection.autoconnect yes`
- **WiFi route-metric=800 一時設定** (VPN を BT-PAN 経由に強制): `sudo nmcli con modify OpenWrt ipv4.route-metric 800 && sudo nmcli con up OpenWrt`
- **mode=alpha** (60s 自動 wake で 60 cycle を効率的に駆動): `h4-mode alpha`

S5 では **`55-btusb-down` は不要** (btusb を置換するだけで suspend 経路に残す = 修正の効果を測定する設計のため)。

### ロールバック (S5 失敗時)

- 修正 btusb.ko を `/lib/modules/6.12.94+deb13-amd64/updates/` から削除 → `depmod -a` → `modprobe -r btusb && modprobe btusb` で stock btusb に戻る
- BT が動かなくなった場合は再起動でも回復 (updates/ が空なら kernel/drivers/bluetooth/ 配下の stock btusb が使われる)

## 残置物 (Macbook 側の現状)

クリーンアップ後 (2026-06-29 04:10 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 (元から) | キーボード LED 制御 |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 (元から) | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | **残置 (本セッションで投入)** | pre/post スナップショット採取 |
| `/usr/local/bin/h4-mode` | **残置 (本セッションで投入)** | alpha/beta モード切替。70-h4-probe が snapshot にラベルを記録する機能は維持、ただし 65-rtcwake が無いので **rtcwake 仕掛け機能は休眠** |
| `/var/lib/h4-probe/mode` | **残置** (= `beta`) | 70-h4-probe が snapshot に記録するラベル。S5 で alpha に切替えたい場合は `h4-mode alpha` |
| `/var/log/h4-probe/*.{pre,post}` | **残置 (39 pre + 39 post = 78 ファイル)** | 本セッションの全 cycle 証拠 + 過去 smoke test |
| `/var/log/h4-vpn-restore.log` | 残置 | S1 で h4-vpn-restore が出力したログ (削除可) |
| `/usr/lib/systemd/system-sleep/55-btusb-down` | **削除済** | S1 専用、S5 では不要 |
| `/usr/lib/systemd/system-sleep/90-vpn-autoup` | **削除済** | S1 専用 |
| `/usr/lib/systemd/system-sleep/65-rtcwake` | **削除済** | S0.5 専用、daily use では「5 分自動起床」が邪魔なため。S5 では再投入推奨 |
| `/usr/local/sbin/h4-vpn-restore` | **削除済** | 90-vpn-autoup の worker、S1 専用 |
| `OpenWrt` の `ipv4.route-metric` | revert 済 (auto = -1) | S1 検証中は 800 に下げていた |
| `iMiminashiPadPro ネットワーク` の autoconnect | revert 済 (no) | S1 検証中は yes だった |
| `GSNet` の autoconnect | revert 済 (no) | S1 検証中は yes だった |

実使用への影響: **毎 suspend で 70-h4-probe が ~58KB × 2 ファイル/cycle を `/var/log/h4-probe/` に書き込む**。1 日 50 cycle 仮定で 5MB/日。長期累積に注意 (定期的に古いファイルを削除するか、`logrotate` を仕掛けるなど)。

## 再現方法

### S0 (パッシブ観測装置 のみ)

すべてのスクリプトはアタッチの [`scripts/`](attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts/) 配下にある。dev 機からの投入例:

```bash
ATTACH=/home/miminashi/projects/macbookair11-debian/report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts
scp $ATTACH/70-h4-probe $ATTACH/h4-mode miminashi@macbookair2015.lan:/tmp/
ssh miminashi@macbookair2015.lan '
sudo install -m 0755 /tmp/70-h4-probe /usr/lib/systemd/system-sleep/70-h4-probe
sudo install -m 0755 /tmp/h4-mode /usr/local/bin/h4-mode
sudo mkdir -p /var/lib/h4-probe /var/log/h4-probe
echo beta | sudo tee /var/lib/h4-probe/mode
rm /tmp/70-h4-probe /tmp/h4-mode
'
# 動作確認 (12s suspend → wake で pre/post pair 確認)
ssh miminashi@macbookair2015.lan 'sudo rtcwake -m no -s 12 && sudo systemctl suspend'
sleep 18
ssh miminashi@macbookair2015.lan 'sudo journalctl -t 70-h4-probe --no-pager -n 4; sudo ls /var/log/h4-probe/'
```

### S1 (btusb pre-unload, 本セッションの再現)

S0 が動作している前提で、以下を追加デプロイ:

```bash
ATTACH=/home/miminashi/projects/macbookair11-debian/report/attachment/2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean/scripts
scp $ATTACH/55-btusb-down $ATTACH/65-rtcwake $ATTACH/90-vpn-autoup $ATTACH/h4-vpn-restore miminashi@macbookair2015.lan:/tmp/
ssh miminashi@macbookair2015.lan '
sudo install -m 0755 /tmp/55-btusb-down  /usr/lib/systemd/system-sleep/55-btusb-down
sudo install -m 0755 /tmp/65-rtcwake     /usr/lib/systemd/system-sleep/65-rtcwake
sudo install -m 0755 /tmp/90-vpn-autoup  /usr/lib/systemd/system-sleep/90-vpn-autoup
sudo install -m 0755 /tmp/h4-vpn-restore /usr/local/sbin/h4-vpn-restore
rm /tmp/55-btusb-down /tmp/65-rtcwake /tmp/90-vpn-autoup /tmp/h4-vpn-restore
# テスト中限定の可逆設定
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
'
```

次の手順:
1. BT-PAN + VPN を NM GUI で接続 (`xfrm src=172.20.10.x` 確認)
2. `h4-mode alpha` でモード設定 (60s 自動 wake)
3. **手動 lid close** で cycle 駆動 (1 cycle ~90s)。30 cycle で打切り判定
4. 終了後の revert:
   ```bash
   ssh miminashi@macbookair2015.lan '
   sudo rm /usr/lib/systemd/system-sleep/{55-btusb-down,65-rtcwake,90-vpn-autoup}
   sudo rm /usr/local/sbin/h4-vpn-restore
   sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
   sudo nmcli con modify GSNet connection.autoconnect no
   sudo nmcli con modify OpenWrt ipv4.route-metric -1
   sudo nmcli con up OpenWrt
   '
   ```

## 関連レポート

- [2026-06-28_141226 lid path required + αβ 未分離 (S0.5/S1 の動機)](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説 (S1/S5 の対象)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_111259 systemctl suspend driver で hang ゼロ (S1 結果と対照)](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_063543 真の s2idle + BT-PAN+VPN+lid close で 3/3 hang (factorial 切り分け)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-28_021019 真の s2idle 初実証 + AC・BT-PAN 単独 10/10 クリーン](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング・s2idle ロールバック決定](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
