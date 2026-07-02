# 計画: s2idle「BT-PAN × VPN」lid-close ハングの関連カーネルソース取得と怪しい箇所の特定

## Context（なぜこの調査をするか）

[2026-06-28_063543 レポート](../../projects/macbookair11-debian/report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
で、真の s2idle・AC でも **「BT-PAN テザリングをトランスポートにした VPN(strongSwan/charon/XFRM)」併用 lid close
でのみ 3/3 ハング**することが factorial に確定した（BT-PAN 単独 25/25・VPN-over-WiFi 11/11・無線なし 9/9 は全クリーン）。
強制電源断が必須の true hang。本計画の目的は、このハングに**関連するカーネルソースを取得し、コードレベルで怪しい箇所
（仮説）をランク付けで特定する**こと。修正の実装は本計画の範囲外（次フェーズ）。

### 確定している事実（レポート + 本セッションの read-only 確認）

- 実機: MacBook Air 11"(Early 2015) / Debian 13 / kernel **`6.12.94+deb13-amd64`**。
- モジュール構成: `CONFIG_XFRM=y`(builtin) / `XFRM_INTERFACE=m` / `INET_ESP=m` / `BT_BNEP=m`。
  VPN×BT-PAN を張った時のみ `xfrm_interface`(=`nm-xfrm-N` netdev)・`esp4/6`・`bnep` がロードされる。
- **停止位置**: 3 件とも journald 最終行が `kbd-backlight-sleep: pre/suspend`（system-sleep pre フック完走後）。
  以降は `/sys/power/state` 書込み後の**カーネル suspend 遷移中**で停止（`PM: suspend exit` 欠落）。
  → ハングはカーネル内。userspace(charon-nm/NM)は freeze 後で実行していない＝**ユーザ空間原因は除外**。
- **入眠直前の VPN 挙動**（hang-journal-excerpts.log）: charon-nm が
  `interface change for bypass policy ... to nm-xfrm-N` → `deleting IKE_SA ... 172.20.10.6 ↔ 160.16.210.47`
  → `enx98e0d98d205e`(bnep) `deactivated`/`deleted` を suspend 直前に実施。論理 teardown は **済**。
- **滞在時間非依存・連続成功数 0/1/6 とばらつく** → 決定論的デッドロックではなく **race**（freeze 開始時に
  非同期 teardown がまだ in-flight なことがある）の徴候。
- 現在のベースライン: WiFi のみ・xfrm policy/state=0・xfrm/bnep netdev 無し（条件下 capture は要セットアップ）。
- **取得済みの版情報（本セッションで read-only 先取り）**:
  - upstream stable タグ = **`v6.12.94`**（`linux-6.12.y` ブランチ上）。
  - Debian `linux` ソース版 = **`6.12.94-1`**（`/proc/version` の `Debian 6.12.94-1 (2026-06-20)`）。
    gcc-14.2.0 / binutils 2.44 / `PREEMPT_DYNAMIC` でビルド。

### 実機 `.config`（/boot/config-6.12.94+deb13-amd64）から確定した示唆 — 仮説ランクを補強

- **`# CONFIG_DPM_WATCHDOG is not set`（最重要）**: デバイス suspend コールバックが固まっても殺すウォッチドッグが
  無い → `dpm_suspend` 段で block すれば**永久ハング（強制電源断必須・ログ無し）**。観測現象と完全一致。
  「device-suspend で block」系（H1/H3/H4）が permanent hang を生み得ることの裏付け。
- **`CONFIG_BT_HCIBTUSB_AUTOSUSPEND=y` + `/sys/module/btusb/parameters/enable_autosuspend=Y` +
  `usbcore.autosuspend=2`**: btusb ランタイム autosuspend 有効。system suspend と runtime PM の競合余地（H4 の具体ノブ）。
- **`CONFIG_XFRM_OFFLOAD=y` / `INET_ESP_OFFLOAD=m`**: `net/xfrm/xfrm_device.c`（per-netdev offload・`xfrm_dev_event`）が
  実効 → H1（bnep への xfrm dst/offload 参照）に直結。`XFRM_INTERFACE=m`/`INET_ESP=m`/`XFRM_USER=m`。
- **デバッグ系ほぼ無効**: `PROVE_LOCKING`/`LOCKDEP` 無効・`REF_TRACKER`/`NET_DEV_REFCNT_TRACKER`/`DEBUG_NET` 無効・
  `DETECT_HUNG_TASK=y` だが panic 無し（freeze 中は検出 kthread も凍結で発火せず）・`SOFT/HARDLOCKUP_DETECTOR=y` だが
  noirq/CPU offline 段では無効。→ **rtnl デッドロック(H3)も netdev ref leak(H1)も「静かに固まる」**＝ログ皆無の永久
  ハングと矛盾しない（＝ログが無いこと自体は仮説を絞れない、を裏付け）。
- `CONFIG_PM_DEBUG=y`/`PM_SLEEP_DEBUG=y`/`PM_ADVANCED_DEBUG=y`・`SUSPEND_FREEZER=y`・`PREEMPT_RCU`。

## 取得するソース（method A + B 両方）

ハングはカーネル内のため**カーネルのみ**取得すれば足りる（strongSwan/NetworkManager は不要＝挙動はログに出ている）。
A で履歴（fix 探索・blame）を、B で実機導入版（Debian 固有パッチ込み）に厳密照合する。

### A: upstream stable git（履歴・blame・fix 探索の本命）
```bash
# linux-6.12.y を partial clone（履歴を残し巨大 blob は遅延取得）。--depth 1 にはしない
git clone --filter=blob:none --branch linux-6.12.y \
  https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git src/linux-6.12.y
# 実機ビルド点に合わせて読む基準を v6.12.94 に
git -C src/linux-6.12.y checkout v6.12.94    # 読む基準（fix 探索は v6.12.94..linux-6.12.y で）
```

### B: Debian ソース（実機導入版 6.12.94-1 に厳密一致）
本セッションは実機を占有しないため、**dev 機から snapshot/sources.debian.org 経由で取得**（実機での
`apt-get source` は別セッションの実験を妨げるので避ける）:
```bash
cd src && apt-get source linux=6.12.94-1   # deb-src 設定済み環境なら。不可なら下記
# 代替: snapshot.debian.org の linux 6.12.94-1 (.dsc/.orig.tar/.debian.tar) を取得して dpkg-source -x
```
> Debian パッチが btusb_suspend / PM core / xfrm を触ることは稀。まず A で読み、A で当たりが付いた
> 関数だけ B の `debian/patches/` と展開ソースで差分確認（patch があれば B を正とする）。

## 怪しい箇所（ランク付き仮説 — 「X が原因」ではなく「X が freeze をまたいで block / ref leak しうるか検証」）

VPN-over-WiFi がクリーンで BT-alone もクリーン → **btusb-backed netdev(bnep) に紐づいた xfrm の
state/dst/policy が freeze 窓を越えること**が交差点。読む対象を優先度順に:

### H1（最優先）: 削除済み bnep への xfrm dst/route 参照リーク → `netdev_wait_allrefs` で停止
- 典型的な「ほぼ恒久 hang」かつ xfrm 特異。bnep netdev unregister が deferred で走り、xfrm 由来の dst 参照が
  残ると `netdev_wait_allrefs` がループし続ける。race（0/1/6）とも整合。
- 読む: `net/core/dev.c`(`netdev_run_todo` / `netdev_wait_allrefs` / `unregister_netdevice_*`)、
  `net/xfrm/xfrm_device.c`(`xfrm_dev_event` / NETDEV_DOWN・UNREGISTER 処理)、
  `net/xfrm/xfrm_policy.c`(`xfrm_dst` / `__xfrm_dst_*` / dst gc)、`net/xfrm/xfrm_state.c`。

### H2: 非同期/deferred teardown が freeze 開始時に in-flight（race の本体）
- ログの「deleted」は**要求**であり、実 netdev 解体は deferred。RCU callback・xfrm GC・`bnep_session` kthread・
  btusb workqueue のいずれかが freeze と衝突。
- **注（永久 hang との整合）**: もし freezer 段そのもので固まるなら `try_to_freeze_tasks` の ~20s タイムアウトで
  「Freezing of tasks failed」を**ログして suspend を中断**するはず → 観測（永久・無ログ・要強制電源断）と合わない。
  従って本ハングのブロックは **freezer を越えた `dpm_suspend`/noirq 段**にあると推定される（＝H2 は「deferred work が
  device-suspend 段で衝突」の意味に限定。純 freezer ハング説は観測と矛盾するので主筋にしない）。これは H1/H3 を補強。
- 読む: `net/bluetooth/bnep/core.c`(`bnep_session` kthread / `bnep_del_connection`)、
  `kernel/power/process.c`(`freeze_processes` / `try_to_freeze_tasks` ＝中断＋ログ経路の確認)、
  RCU/workqueue が freeze 中に flush されない経路。

### H3: `rtnl_lock` 競合（deferred teardown 保持 ↔ suspend 経路）
- deferred な unregister/xfrm 処理が rtnl を保持したまま、device-suspend 側が同 lock を待ち停止。
- 読む: `drivers/base/power/main.c`(`dpm_suspend` / `dpm_suspend_noirq`)、rtnl を取る netdev/xfrm 経路。

### H4: `btusb_suspend` がコントローラ応答待ちで block
- BT-PAN peer 喪失後の HCI コマンド/URB 待ちで停止しうる。ただし VPN 非依存のはずで BT-alone がクリーンな点と
  整合しにくい → 優先度低だが resume 側とセットで確認。
- 読む: `drivers/bluetooth/btusb.c`(`btusb_suspend`/`btusb_resume`/`btusb_stop_traffic`)、
  `net/bluetooth/hci_core.c`(suspend notifier / `hci_suspend_*`)。

### H5（見落とし防止）: resume 側 hang も範囲に残す
- 自レポートが明記: ログでは entry/resume を判別不能。ユーザ体感（蓋を開けたらハング）は resume を示唆。
- 読む: btusb/bnep の resume 再初期化、`dpm_resume_*`、xfrm の resume 時整合。**suspend-entry だけに絞らない**。

## 力点（cold reading に頼らず証拠で裏付ける 2 手）

### F1: 6.12.94 以降に landed した修正の探索（A の本命価値）
```bash
cd src/linux-6.12.y
# 6.12.94 ビルド点より後に linux-6.12.y へ landed した修正だけを見る
for p in net/xfrm net/bluetooth/bnep drivers/bluetooth/btusb.c net/core/dev.c net/bluetooth/hci_core.c; do
  echo "### $p"; git log --oneline -i v6.12.94..origin/linux-6.12.y \
    --grep='suspend\|freeze\|refcount\|ref leak\|race\|deadlock\|netdev_wait\|dst\|use-after-free\|unregister' -- "$p"
done
# 参考: mainline にしかない新しい fix も拾うなら upstream master を別 remote で fetch して同様に grep
# 該当 commit があれば git show / git blame で v6.12.94 tree と突合し、本ハングに効くか評価
```
上流に一致 fix があれば、それが最速の pinpoint（Debian `debian/patches/` への backport 有無も B 側で照合）。

### F2: 条件下の残留カーネルオブジェクト live capture（仮説 b の検証 = `nm-xfrm-N` は suspend 時に残るか）
> **本セッションでは実施しない**（別セッションが実機で別実験を開始予定のため実機を占有しない）。
> 必要な実機情報（カーネル版・モジュール config・Debian ソース版）は本セッションで先取り済。F2 は実機が空いた
> 後続セッションに持ち越す。下記はその手順メモ。
> なお A+B のソース解析（読解・git log fix 探索）は実機不要なので本フェーズで完遂し、F2 で確度を後追い更新する。

suspend は注入できないが、**ユーザが BT-PAN+VPN を張った状態**で**手動 suspend 直前**に Claude が read-only スナップ:
```bash
ssh miminashi@macbookair2015.lan '
  ip -o link show type xfrm; ip -br link
  sudo ip xfrm policy; sudo ip xfrm state
  ls -l /sys/class/net/ ; cat /proc/net/dev | grep -E "enx|nm-xfrm|bnep"
  # dst/route 残留の傍証
  ip route show table all | grep -E "enx|nm-xfrm" ; ip -s link show enx98e0d98d205e 2>/dev/null'
```
→ `nm-xfrm-N` が論理 down 後も残るなら H1/仮説b を強く支持。完全消滅なら H1 を相対的に下げ H2/H3 を上げる。
（役割分担はレポート同様: 操作はユーザ、Claude は read-only 確認のみ。suspend は注入しない。）

## 成果物

`report/yyyy-mm-dd_hhmmss_s2idle_btpan_vpn_hang_kernel_source_analysis.md`（タイムスタンプは
`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得）。内容:
- 前提・目的・環境情報・参照レポートへのリンク（CLAUDE.md レポートルール準拠）。
- 取得したソース（版・ブランチ・commit）。
- **怪しい箇所**: H1〜H5 を、読んだ実コード（`file_path:line` 引用）と F1 の証拠・実機 `.config` の示唆で裏付けて
  ランク確定。**F2 は本セッション未実施のため「未検証・後続セッションで追補」と明記**（仮説 b の確度は保留）。
- 次の一手（F2 の手順を含む修正仮説の検証手順。fix 実装は別フェーズ）。
- 添付: F1 の git log 抜粋、本セッションで取得した実機 `.config` 関連抜粋を
  `report/attachment/<同名>/` に格納しリンク。本プランファイルも plan.md として添付。
  （F2 の live capture ログは未取得＝後続セッションで実施後に追補する）。

## 検証（この調査が妥当だと言える条件）

1. clone した tree の版が実機 6.12.94 系に整合（`git describe` / `Makefile` VERSION 確認）。
2. H1〜H5 各仮説について、**該当関数の実コードを引用**し「freeze 窓を越えて block/ref leak しうるか」に
   yes/no/不明で答えている（推測のみで断定しない）。
3. F1 で 6.12.94 以降の関連 fix の有無を提示（あれば commit、無ければ「該当なし」を明示）。
4. レポートが CLAUDE.md のレポート作成ルール（JST 日時・再現方法・環境情報・添付・関連レポートリンク）を満たす。

（後続セッションの追補条件）F2 で条件下の残留オブジェクトを実測し、`nm-xfrm-N` 残存の有無で H1/仮説b の確度を
更新する。これは**本セッションの完了条件ではなく**、実機が空いた後の follow-up とする。

> 注: 本調査は read-only（ソース clone は gitignore 済 `src/` への取得のみ）。実機への suspend 注入は行わず、
> ハング再現操作はユーザ手動・Claude は ssh read-only に限定する。
