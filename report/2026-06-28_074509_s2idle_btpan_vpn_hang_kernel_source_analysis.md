# s2idle「BT-PAN × VPN」lid-close ハング — 関連カーネルソースの取得と怪しい箇所の特定

- **実施日時**: 2026年6月28日 07:45 (JST)
- **位置づけ**: [2026-06-28_063543 レポート](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)で factorial に確定した「真の s2idle・AC でも **BT-PAN テザリングをトランスポートにした VPN(strongSwan/charon/XFRM) 併用 lid close でのみ 3/3 ハング**」について、関連カーネルソースを取得し、**コードレベルで怪しい箇所（仮説）をランク付けで特定**した調査。修正の実装は本レポートの範囲外（次フェーズ）。

## 添付ファイル

- [調査プラン](attachment/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis/plan.md)
- [実機 .config 抜粋](attachment/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis/config-excerpts.txt)
- [F1 fix 考古学（手元窓 + mainline）](attachment/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis/f1-fix-archaeology.txt)

## 結論（先に要約）

1. **ハングは freezer 段そのものではなく、その前後で走る同期コールバック段（最有力は freeze 後の `dpm_suspend` device callback）で起きている**とコードから推定できる。理由: freezer 段で固まるなら `try_to_freeze_tasks` が **20秒で "Freezing … failed" をログして suspend を中断**する（`kernel/power/process.c:26,88-93,111`）。観測は永久・無ログ・要強制電源断なので **freezer 段は除外**。`CONFIG_DPM_WATCHDOG` 無効（`drivers/base/power/main.c:552-555` が no-op）＋ `suspend_console()` が `dpm_suspend_start()` の前（`kernel/power/suspend.c:505 < 507`）のため、**`dpm_suspend` 段の device callback** が無限ブロックすれば **無ログ・`PM: suspend exit` 欠落・永久ハング**になり観測 signature と一致（＝H4 が最有力）。**ただし freezer の前に走る `PM_SUSPEND_PREPARE` notifier（`hci_suspend_dev`）も同じハング窓内の同期経路で、freezer 論証では排除されない**（追補参照。pre-freeze 経路は完全には除外できない）。

2. **観測 signature（無音・永久・device-suspend 段）に最も合致する単一コード地点は H4** = `btusb_suspend()` の **timeout 無し URB drain**。`drivers/bluetooth/btusb.c:4293 btusb_stop_traffic()` → `:1977-1981` で intr/**bulk**/isoc/diag/ctrl の 5 anchor を `usb_kill_anchored_urbs()` で kill → 各 URB で `drivers/usb/core/urb.c:713 wait_event(usb_kill_urb_queue, use_count==0)`（**uninterruptible・timeout 無しの無限待ち**）。BT-PAN/ESP のデータは ACL→**bulk endpoint** に載るため `bulk_anchor` の drain が具体的停止点。HCD が URB を giveback しない（コントローラ wedge）と永久に返らない。

3. **ただし H4 単独では「VPN 併用特異性」を説明できない**。この no-timeout drain は BT-PAN 単独（25/25 クリーン）でも同じく通る共通経路で、VPN 専用コードパスではない。VPN-over-bnep は ESP/暗号化パケットを suspend 直前まで bulk endpoint に流し続けるため **drain 実行時の in-flight bulk URB を増やし、race ウィンドウを量的に広げる**寄与に留まる。「URB が返らなくなる」根本トリガ（コントローラ/HCD の wedge、もしくは btusb 外の suspend 順序問題＝xfrm/bnep teardown との相互作用）は別レーンにあり、本調査では単一行に確定できなかった（＝**怪しい「領域」は特定、単一「真因行」は未確定**）。

4. **race（連続成功 0/1/6 のばらつき）の供給源は H2 の非同期実体**: `bnep_session` は **non-freezable kthread**（`net/bluetooth/bnep/core.c`、`set_freezable`/`try_to_freeze` 不使用＝PF_NOFREEZE 継承）、xfrm state GC は **system_wq**（非 freezable, `net/xfrm/xfrm_state.c:52,744`）。いずれも freezer を素通りして dpm_suspend 段まで in-flight になりうる。これが「freeze 開始時に teardown がまだ走っている」状況を生む。

5. **H1（xfrm の dev ref leak → `netdev_wait_allrefs` で永久ループ）は機序前提も非対称性も実在するが、ハング因果としては確度・低**。`netdev_wait_allrefs` は **kbnepd kthread 文脈**で走り suspend タスクに橋渡しされず、固まれば `net/core/dev.c:10850` の `pr_emerg("unregister_netdevice: waiting for … to become free")` を 10秒毎に出すはず（観測の完全沈黙と不整合）。ただし bnep 固有の脆さとして残る。**判別子（重要・後述）**: ハング boot の dmesg は強制電源断で揮発するため使えないが、この `pr_emerg` は **kbnepd が CPU 稼働中に出す**＝「bnep ref leak が起きたが結局正常に suspend/resume できた boot」の journald に残る。よって**既に取得済みの正常 boot（特に対照クリーンセル）のログを grep**すれば再現不要で H1 を支持/否定できる。

6. **H3（rtnl デッドロック）は否定**: PM コアは rtnl を一切取らない（`drivers/base/power/`・`kernel/power/` で `rtnl_lock` grep 0 件）。**H5（resume 側ハング）は確度・低**: `btusb_resume` は非ブロッキング（`usb_submit_urb`）、`hci_resume_sync` は timeout 付き、bnep 再接続はユーザ空間責務。suspend 側で固まれば resume には到達しない。

## 前提・目的

- **対象事象**: 真の s2idle・AC・素 suspend で、BT-PAN(bnep over btusb) をトランスポートにした VPN(strongSwan/charon-nm/XFRM) を併用して lid close すると数回以内に true hang（強制電源断必須）。単独要素はクリーン（BT-PAN 単独 25/25・VPN-over-WiFi 11/11・無線なし 9/9）、**併用のみ 3/3**。詳細は[親レポート](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)。
- **停止位置（親レポート）**: `systemd-suspend.service` 起動・system-sleep pre フック完走後、`/sys/power/state` 書込み後の**カーネル suspend 遷移中**で停止。`PM: suspend exit` 欠落・ログ皆無。入眠直前に charon-nm が「bypass policy を `nm-xfrm-N` へ付替」「IKE_SA 削除（端点 `172.20.10.6`=BT-PAN IP）」「`enx98e0d98d205e`(bnep) deactivate/delete」を**完了済**＝論理 teardown は suspend 前に終わっている。それでもハング。
- **目的**: 上記ハングに関連するカーネルソースを取得し、コードを精読して「怪しい箇所」を仮説としてランク付けで特定する。

## 環境情報

- 機種: MacBook Air 11"(Early 2015) / OS: Debian 13 (trixie)
- カーネル: **`6.12.94+deb13-amd64`**（`/proc/version`: `Debian 6.12.94-1 (2026-06-20)`, gcc-14.2.0, binutils 2.44, PREEMPT_DYNAMIC）
- 実機 .config 要点（[添付](attachment/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis/config-excerpts.txt)）: **`CONFIG_DPM_WATCHDOG` 無効**、`BT_HCIBTUSB_AUTOSUSPEND=y`（`enable_autosuspend=Y`, `usbcore.autosuspend=2`）、`XFRM_OFFLOAD=y`/`INET_ESP_OFFLOAD=m`、`XFRM_INTERFACE=m`/`INET_ESP=m`/`BT_BNEP=m`、`PROVE_LOCKING`/`LOCKDEP`/`REF_TRACKER`/`DEBUG_NET` いずれも無効。
- 取得ソース:
  - **method A (upstream stable)**: `git.kernel.org` の `linux-6.12.y` を shallow-since クローン → `src/linux-6.12.y`（branch tip = **`v6.12.94`**, `git describe`=v6.12.94 で版一致確認）。
  - **method B (Debian)**: snapshot.debian.org から `linux_6.12.94-1.debian.tar.xz`（sha1 `0e32c6f…` 一致）取得・展開 → `src/debian-6.12.94-1`。**patch series 115 件に bluetooth/btusb/bnep/xfrm/PM/suspend を触る Debian 固有パッチは無し**を確認＝当該サブシステムは **v6.12.94 upstream = 実機版**。A を正本に読解した。
  - clone 物は `.gitignore`（`/src/`）で除外（コミットしない）。

## 調査結果（怪しい箇所＝ランク付き仮説）

VPN-over-WiFi がクリーン・BT-alone もクリーンで、**併用時のみ**出る。交差点は「**btusb-backed netdev(bnep) に紐づいた xfrm の state/dst/policy が freeze 窓を越えること**」。以下、各仮説を「`path:行` のコード引用 + 観測整合」で評価した。

### H4（機序として最有力・確度 中〜高）: `btusb_suspend` の timeout 無し URB drain で device-suspend 永久ブロック

- `drivers/bluetooth/btusb.c:4293 btusb_stop_traffic(data)` → `:1977-1981`:
  ```
  usb_kill_anchored_urbs(&data->intr_anchor);
  usb_kill_anchored_urbs(&data->bulk_anchor);   // ← BT-PAN/ESP データ(ACL)はここ
  usb_kill_anchored_urbs(&data->isoc_anchor);
  usb_kill_anchored_urbs(&data->diag_anchor);
  usb_kill_anchored_urbs(&data->ctrl_anchor);
  ```
  続いて `:4294 usb_kill_anchored_urbs(&data->tx_anchor)`。実体は `drivers/usb/core/urb.c:713`:
  ```
  wait_event(usb_kill_urb_queue, atomic_read(&urb->use_count) == 0);  // timeout 無し・uninterruptible
  ```
  timeout 付きの `usb_wait_anchor_empty_timeout()` は存在するが btusb suspend では**使っていない**。drain をすり抜けた URB は後続 `usb_hcd_flush_endpoint()`（`drivers/usb/core/hcd.c:1798` の `usb_kill_urb` ループ）でも timeout 無しで待つ。
- これらは `/sys/power/state` 書込み後の **`usb_suspend()`（device `->suspend`, `drivers/usb/core/driver.c:1581`）** で走る。`CONFIG_DPM_WATCHDOG` 無効 + `suspend_console()` 済 → 固まれば**無ログ・`PM: suspend exit` 欠落・永久ハング**＝観測 signature に**機序として一致**。
- runtime autosuspend の競合（ウィンドウ拡大要因）: active BT-PAN 中は `btusb_suspend:4272-4273`（`PMSG_IS_AUTO && hci_conn_count>0` で `-EBUSY`）で autosuspend が抑止されるが、NM が suspend 直前に BT-PAN を落とすと `hci_conn_count→0` で **autosuspend ゲートが開く**（`usbcore.autosuspend=2`）→ 同じ no-timeout drain に収束。独立した第2ハングではなく終端待ちの共有。
- **確度を「高」にしきれない理由**: この無限待ちは BT-PAN 単独でも通る共通経路で、25/25 クリーンが示すとおり通常は giveback 完了で抜ける。永久化には「URB が返らない＝コントローラ/HCD wedge」という**別の前提条件**が要る。H4 は「wedge を無音永久ハングに変換する装置」であって root trigger ではない。

### H2（race 供給源として妥当・確度 中）: 非 freezable な非同期 teardown が freeze 窓を越えて in-flight

- `bnep_session` は `kthread_run`（`net/bluetooth/bnep/core.c:653`）で起動、**PF_NOFREEZE を継承**（`kernel/kthread.c` の kthreadd 既定）、`net/bluetooth/` 全体で `set_freezable`/`try_to_freeze` は **0 件**。アイドルは `core.c:539 wait_woken(..., MAX_SCHEDULE_TIMEOUT)` で `try_to_freeze` 無し。停止は `bnep_del_connection`（`core.c:673`）の `atomic_inc(&s->terminate)`+wake → ループが `core.c:547 unregister_netdev(dev)` を完走したときのみ。
  - 裏付け（コード×観測の交差）: もし freezer 計上されるなら、アイドル BT-PAN セッションが在るだけで毎回 20秒 "Freezing … failed" が**決定論的**に出るはず。BT-PAN 単独 25/25 が正常 suspend している事実は **non-freezable** とのみ整合（grep より強い証拠）。
- xfrm state GC は `net/xfrm/xfrm_state.c:52 DECLARE_WORK(xfrm_state_gc_work)` を `:744 schedule_work`（**system_wq=非 freezable**）でキュー → `synchronize_rcu` 後に SA を解体し dev_put が deferred。
- これらが「freeze 開始時に in-flight」かどうかで bnep unregister / dst 解放が device-suspend と時間的に重なるか決まり、**0/1/6 のばらつき（race）を説明できる**。「衝突＝ハング」の最終ホップ自体は bnep/xfrm/PM コアのコード内だけでは描けず、停止点は H4（btusb の drain）に落ちる像。

### H1（非対称性は綺麗に説明・だがハング因果は確度 低）: 削除済み bnep への xfrm dst ref leak → `netdev_wait_allrefs`

- 前提は実在: xfrm の software bundle(xdst) は下回り netdev(bnep) を **`net/ipv4/xfrm4_policy.c:74 netdev_hold(dev, &xdst->u.dst.dev_tracker, GFP_ATOMIC)`** で握る（v6 は `xfrm6_policy.c`）。解放は bundle 破棄時の `dst_destroy`→`netdev_put`（`net/core/dst.c`）のみで、**software bundle を NETDEV イベントで walk して落とす経路は無い**（`xfrm_dev_event`（`net/xfrm/xfrm_device.c:528-546`）は HW-offload state/policy を flush するだけ。なお offload ref leak 自体の既知 fix `xfrm_dev_unregister()` は `xfrm_device.c:520` に**既込み**＝実機は対象外）。よって bnep 削除時に software bundle の dev ref は同期解放されず **RCU/socket 再評価任せ**。
- **非対称性（H1 の最強点）**: wlp3s0 は**永続 netdev で VPN teardown でも unregister されない**→`netdev_wait_allrefs` を一切起動しない。bnep は接続毎の **ephemeral netdev で必ず unregister される**（`core.c:547`）。よって「削除済み netdev への ref 残留で wait が固まる」現象は**構造上 bnep だけが踏みうる**＝VPN-over-WiFi クリーン／VPN-over-BT ハングの非対称を綺麗に説明する。
- **だがハング因果は弱い**: `netdev_wait_allrefs`（`net/core/dev.c:10792-10845`、`while(true)` で ref が 1 に落ちるまで無限ループ）は **kbnepd kthread 文脈**で走り、`bnep_session_sem` を握る他者は全て userspace ioctl 由来（dpm 前に frozen）で**suspend タスクに橋渡しされない**。さらに固まれば `net/core/dev.c:10850` の `pr_emerg("unregister_netdevice: waiting for %s to become free")` を **10秒毎に出すはず**で、観測の完全沈黙と不整合。
- → H1 は「VPN/BT 非対称性」と「bnep の ref 脆さ」を説明する価値はあるが、**観測された無音 device-suspend ハングの直接因果としては確度・低**。**判別子（詳細は「留意・次の一手」）= 既収集の正常 boot の journald にこの `unregister_netdevice: waiting…` 行が出るか**（ハング boot の dmesg は強制電源断で揮発するため不可。この `pr_emerg` は kbnepd が CPU 稼働中に出すので正常 boot のログに残る）。

### H3（否定）: rtnl デッドロック
- PM コアは rtnl を取らない（`drivers/base/power/`・`kernel/power/` で `rtnl_lock` grep 0 件）。`unregister_netdev` の rtnl は kbnepd 文脈で、suspend タスクは待たない。`device_pm_remove` は `complete_all`（`drivers/base/power/main.c:157`）を `list_del` 前に呼ぶため「解体された子の永久待ち」も構造的にガード済。suspend 窓内で rtnl を取る in-path PM notifier も無し（net 系 PM notifier は bluetooth のみ、かつ `hci_req_sync_lock`=mutex で rtnl ではない）。→ 具体経路を構成できず**否定**。

### H5（確度 低）: resume 側ハング
- `btusb_resume`（`btusb.c:4351`）は `usb_submit_urb`（非ブロッキング）で再 submit するのみ、BCM 機は `data->resume` が NULL。`hci_resume_sync` のコマンドは timeout 付き。bnep 再接続はユーザ空間（NM）責務でカーネル resume は bnep を待たない。suspend 側で固まれば resume に到達しないため、ユーザ体感「蓋開けでハング」は H5 を支持しない（親レポートの「入眠/復帰どちらか判別不能」と整合）。脆さとしては `reset_resume=1`（`btusb.c:4307-4315`）に対し `btusb_driver` に `.reset_resume` が無く resume 時に再 probe(firmware 再ロード)対象になりうる点があるが、bounded で全体ハングではない。

### 追補: 精読で判明した重要事実（初版本文に未反映だったもの）

- **【もう一つの BT 特異性】ネットワーク系で PM suspend notifier を登録するのは Bluetooth だけ**。`grep -rln register_pm_notifier net/` → `net/bluetooth/hci_core.c` のみ（`hci_core.c:2809`）。xfrm/wl/その他 net サブシステムは suspend notifier チェーンに**入っていない**。つまり「bnep が ephemeral netdev で必ず unregister される（H1）」とは別に、**BT だけが suspend 経路の早い段で同期コールバックを持つ**という構造的非対称が存在し、「なぜ BT 特異か」をもう一段補強する。

- **【in-window のもう一つの候補】`hci_suspend_dev` が suspend タスク内で同期実行され、ハング窓に入る**。`hci_suspend_notifier`（`hci_core.c:2441 PM_SUSPEND_PREPARE`）→ `hci_suspend_dev`（`:2852`）は `kernel/power/suspend.c:367 pm_notifier_call_chain_robust(PM_SUSPEND_PREPARE)` で呼ばれ、これは **freeze（`:372`）より前・かつ `/sys/power/state` 書込み後**（＝最後の on-disk ログ行より後＝ハング窓内）。`:2870 hci_req_sync_lock`（= **req_lock mutex**）を取り `hci_suspend_sync`（HCI コマンドは timeout 付き）を実行。通常は永久ブロック源でないが、**req_lock が別の停滞オペで保持されていれば恒久ブロックしうる**（確度 中〜低）。初版は hci を resume 側中心に扱ったが、**suspend 側のこの in-window 同期経路は独立した候補**として残すべき。

- **【ハング窓の正確な順序と「沈黙」の解釈限界】** suspend 経路は `pm_suspend()` が **`suspend.c:624 pr_info("suspend entry (%s)")` を最初に出し**、その後 `enter_state` → `suspend_prepare`（PM_SUSPEND_PREPARE notifier=`hci_suspend_dev` → `freeze_processes`）→ `suspend_devices_and_enter`（`suspend_console()` `:505` → `dpm_suspend` `:507`, ここに btusb drain=H4）→ 復帰後 `:627 pr_info("suspend exit")`。**重要**: `PM: suspend entry` は **freeze/console suspend より前**に出る（journald は当該時点で生存）。よって親レポートの「ハング boot に `PM: suspend entry` が on-disk で残らない」は **journald のフラッシュ間隔次第**で、ハングが pre-freeze（hci_suspend_dev）か post-freeze（btusb drain）かを**綺麗には判別しない**（沈黙＝post-freeze 確定、ではない）。H4 を最有力としつつ、pre-freeze の hci 経路を完全には排除できない。

- **【H1 の lazy-teardown の具体機序（初版は要約のみ）】** software xfrm bundle が落ちるのは、保持元 socket の `dst_check`→`stale_bundle`→`xfrm_bundle_ok` の `dst->dev && !netif_running(dst->dev)`（`net/xfrm/xfrm_policy.c:3987-3988`）が false を返し再 route された後、`dst_release`→`call_rcu_hurry(dst_destroy_rcu)`（`net/core/dst.c:178`）で `netdev_put` が走る、という二段の遅延。NETDEV イベントで software bundle を walk して落とす経路は無い。

- **【検討して除外（explicit negatives）】** `BT_HCIBTUSB_POLL_SYNC` は無関係（`btusb_intr_complete` が `urb->status==-ENOENT`＝kill 中なら再 submit せず return、`btusb.c:1423-1426`）。BCM 機は `btusb_suspend` の `data->suspend` が NULL（MTK 専用フック）。これらは「読んで除外した」事実。

### F1: fix 考古学（[添付](attachment/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis/f1-fix-archaeology.txt)）

- `linux-6.12.y` の branch tip が**ちょうど v6.12.94**（= 6.12.94 が 6.12.y 系の現最新, `v6.12.94..HEAD`=0）。安定ツリーに「6.12.94 以降の fix」はまだ無い。
- 手元窓(≈6.12.85→94, **既に実機に入っている**)に当該領域の fix が集中: `4236c30b4 xfrm: hold dev ref until after transport_finish NF_HOOK`（dev ref）, `b21805258 Bluetooth: bnep: Fix UAF read of dev->name`（bnep_session が netdev を並行 free する race）, `107c826e4 L2CAP: chan ref leak` 等＝**当該領域が継続的に fragile**。
- **mainline で 6.12.94 より後の候補**（GitHub API, ipsec 2026-06-22 pull）: `xfrm: Fix dev use-after-free in xfrm async resumption`（**original-device refcount leak**）, `xfrm: Fix xfrm state cache insertion race`。いずれも input/RX 経路で本件 suspend hang とは経路が異なるが、**xfrm の dev ref 管理が直近も継続して脆い**ことを示す。stable backport 状況を後続で照合する価値あり。
- **btusb mainline 2026-06 の fix は全て probe/disconnect 経路**で、suspend の URB drain を直すものは無い → **no-timeout drain は設計どおり**（H4 が「バグ＋fix」ではなく外部トリガ必須であることの裏付け）。

### 精読した／未精読のファイル（カバレッジの明示）

- **精読**: `drivers/bluetooth/btusb.c`, `drivers/usb/core/{urb.c,driver.c,hcd.c}`, `net/bluetooth/{hci_core.c,hci_sync.c,bnep/core.c,bnep/netdev.c}`, `net/xfrm/{xfrm_device.c,xfrm_policy.c,xfrm_state.c}`, `net/ipv4/xfrm4_policy.c`, `net/core/{dev.c,dst.c}`, `kernel/power/{process.c,suspend.c}`, `drivers/base/power/main.c`。
- **未精読（限界）**: **`net/xfrm/xfrm_interface_core.c`**。`nm-xfrm-N` は journal 上 最も証拠中心的なオブジェクト（charon が入眠直前に bypass policy を**そこへ**移す）だが、仮想 netdev は PM の `->suspend` callback を持たず、PM コアは rtnl を取らない（H3 で確認）ため **dpm hang の直接原因である可能性は低い**と判断し優先度を下げた。F2（live capture）で `nm-xfrm-N` の残留が確認されたら、このファイルを精読対象に格上げすべき。

## 再現方法（本調査の手順）

ハング再現操作は親レポート参照。本調査はソース解析で実機 suspend は注入していない。

1. **実機情報の read-only 取得**（別セッションの実験を妨げないよう先取り）:
   ```bash
   ssh miminashi@macbookair2015.lan 'uname -r; cat /proc/version; lsmod | grep -Ei "btusb|bnep|bluetooth|usbcore"; \
     grep -E "DPM_WATCHDOG|BT_HCIBTUSB_AUTOSUSPEND|XFRM_OFFLOAD|PROVE_LOCKING|REF_TRACKER" /boot/config-$(uname -r); \
     ip -br link; sudo ip xfrm policy; sudo ip xfrm state'
   ```
2. **method A**: `git clone --shallow-since="2026-05-15" --branch linux-6.12.y https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git src/linux-6.12.y`（tip=v6.12.94 を確認）。
3. **method B**: `curl https://snapshot.debian.org/.../linux_6.12.94-1.debian.tar.xz` → 展開 → `debian/patches/series` を `grep -Ei "bluetooth|btusb|bnep|xfrm|power|suspend"`（該当固有パッチ無しを確認）。
4. **F1**: 手元窓 `git log --grep='suspend|freeze|refcount|race|netdev_wait|unregister|dst|use-after-free' -- <path>`、mainline は GitHub API `repos/torvalds/linux/commits?path=<path>`（cgit は anti-bot で不可）。
5. **精読**: `src/linux-6.12.y`（HEAD=v6.12.94）で H1〜H5 の該当関数を読み、本文の `path:行` を確認。

## 留意・次の一手

- **本調査の到達点と限界**: 怪しい「領域」は特定し、観測 signature に最も合う単一コード地点（H4 = btusb の no-timeout URB drain）まで絞れた。だが **VPN 併用特異性の root trigger（何が URB を返らなくするか／btusb 外の suspend 順序相互作用か）は単一行に確定できていない**。「無音・device-suspend 段・永久」という観測がそれ以上の内部可視性を与えないため（親レポートの「停止位置はログから特定不能」と同根）。
- **決定的判別子（最優先・再現不要・read-only で可能）**: **既に取得済みの journald**（全 boot、特に BT-PAN+VPN を張って teardown した対照クリーンセルの boot）を **`unregister_netdevice: waiting for … to become free`**（`net/core/dev.c:10850`）で grep。
  - 注意: **ハング boot 自身の dmesg は使えない**（強制電源断で printk リングバッファが揮発。pstore/ramoops が設定されていれば別だが Debian stock では通常未設定＝要確認）。この `pr_emerg` は kbnepd kthread が **CPU 稼働中**に 10秒毎に出すので、「bnep ref leak は起きたが結局正常に suspend/resume できた boot」のログに残る。それを拾う。
  - **出る** → H1（xfrm dst ref leak → netdev_wait_allrefs）を強く支持。
  - **BT-PAN+VPN を多数回張った正常 boot で一貫して出ない** → H1 を否定し、**H4（btusb drain での device-suspend 永久ブロック）を支持**。
    ```bash
    ssh miminashi@macbookair2015.lan 'sudo journalctl --no-pager | grep -i "unregister_netdevice: waiting"; \
      cat /sys/module/ramoops/parameters/* 2>/dev/null; ls /sys/fs/pstore 2>/dev/null'
    ```
- **F2（条件下 live capture, 後続セッション）**: BT-PAN+VPN を張った状態で手動 suspend 直前に `ip -o link show type xfrm; ip xfrm policy; ip xfrm state; cat /proc/net/dev | grep -E "enx|nm-xfrm|bnep"` を read-only 取得 → `nm-xfrm-N`/bnep/残留 dst が suspend 窓に残るか（H1/仮説b の確度更新）。
- **検証用の修正仮説（fix ではなく切り分け、別フェーズ）**:
  - (a) 親レポート B-2 = **suspend 前に `modprobe -r btusb`**（btusb を device-suspend 経路から除去）。H4 が真なら drain 経路自体が消えてクリーンになるはず（直接の H4 検証）。**この test は deep モードと s2idle を切り分ける意味でも決定的**: deep #4 は **btusb 完全除去でもハングした**（同じ `PM: suspend exit` 欠落 signature）。つまり deep #4 と本件 s2idle は **signature が同じでも機序が別**である可能性が高く（H4 は s2idle の機序であって deep #4 の機序ではない）、s2idle+BT-PAN+VPN で btusb 除去がクリーンなら両者を分離でき、ハングするなら H4 を s2idle でも棄却できる。
  - (b) post-6.12.94 の xfrm dev-ref/state-race fix を backport して本条件で再試行（H1/H2 領域の検証）。
- **DPM_WATCHDOG の観測支援**: 切り分け目的に限り、テスト用に `CONFIG_DPM_WATCHDOG` 有効カーネルがあれば「どの device の `->suspend` で固まったか」をウォッチドッグが吐く（恒久採用ではなく診断用）。

## 関連レポート

- [2026-06-28_063543 s2idle「BT-PAN×VPN」併用 lid close で 3/3 ハング再現（手動 factorial）](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — 本調査の対象事象・親
- [2026-06-28_021019 s2idle ロールバック不完全の発見 + AC 自動ループ BT-PAN 10/10 クリーン](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 BT テザリング lid close で計4ハング・s2idle ロールバック決定](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
- [2026-05-31 S3 hang により s2idle へ切替（停止位置はログから特定不能）](2026-05-31_132125_s3_hang_switch_to_s2idle.md)
