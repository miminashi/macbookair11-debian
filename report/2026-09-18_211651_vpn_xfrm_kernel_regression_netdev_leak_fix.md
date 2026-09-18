# VPN 使用中にスリープできなくなる不具合の原因特定と修正 (カーネルのデグレと、安全装置の作り直し)

- **実施日時**: 2026年9月18日 18:28 〜 21:17 (JST)
- **障害発生**: 2026年9月18日 14:51 (1 回目)、16:13 (2 回目)

## 概要

9月18日の午後、蓋を閉じて鞄に入れた MacBook Air がスリープに入らず、熱を持った状態で見つかった。画面には `unregister_netdevice: waiting for …` と、プロセスの凍結 (freeze) 失敗が延々と並んでいた。8月21日の「スリープ不能の再試行を繰り返してバッテリが尽きた」障害と同じ系統である。直前に iPhone の USB テザリングを使っており、蓋を閉じる前にケーブルを抜いていた。同じ日の 16:13 には、テザリングと関係なく WiFi のまま同じ症状がもう一度出ている。

原因はカーネル 6.12.94 で入ったデグレと特定した。VPN (strongSwan の xfrm インタフェース) で受信パケットを復号する処理が暗号モジュールの都合で非同期に回ると、物理デバイス (WiFi や USB テザリング) の参照を取ったまま、返すときは VPN 側のデバイスに返してしまう。1 パケットごとに参照が 1 つずつずれて蓄積し、物理デバイスが消える瞬間 (USB を抜く、スリープ前に WiFi ドライバを外す) に表に出る。そうなるとデバイスの削除が永久に終わらず、再起動するまで一切スリープできない。実機で負荷をかけて意図的に再現したところ、非同期復号の回数 N に対して VPN 側の参照数がちょうど 1−N になり、理論と完全に一致した。上流には修正 (8045c0df98d4) があるが、Debian の最新 6.12.107 にもまだ入っていない。8月22日のレポートで引き金とした「WiFi の切断と VPN 撤収の競合 (cfg80211 の WARN)」は誤りだったので、ここで訂正する。

前回導入した安全装置 (リークを検知したら電源を切るフック) は今回も検知まではしていた。しかし電源断が実行されず、そこから芋づる式に問題が見つかった。スリープ処理中は logind も systemd のジョブも電源断を拒否すること。失敗した一時 unit が残って以後の再試行が全滅すること。ログバッファが一杯になると「リークは止まった」と誤判定すること。そして、無理やり再起動させてもカーネルの停止処理の中で固まって終わらないこと。16:19 に手で打った `sudo reboot` が効かなかったのも同じ理由である。これらを 1 つずつ実機で再現しながら直し、最後は softdog (ソフトウェア watchdog) による強制リセットまでつないだ。実機でリークを起こしてスリープさせる e2e 試験では、人手なしで再起動まで到達することを確認した (約 10 分)。なお、リーク状態では電源断の処理自体もカーネル内で固まるため、最後の保険が働いた場合の結末は「電源が切れる」ではなく「再起動する」になる。再起動でリークは解消し、蓋が閉じていれば通常どおりスリープするので、発熱と放電は止まる。あわせて、使用中にリークを検知したら GNOME の通知で再起動を促す見張りも追加した。

根本対策として、6.12.107 に上流の修正をバックポートした自前カーネル `6.12.107-xfrmfix1` をビルドし、実機に導入した。非同期復号を計 474 回起こした後に VPN を切る試験と、VPN を張ったままの実スリープで、リークは一度も出なかった。WiFi・カメラ・S3 の suspend/resume も従来どおり動く。今後は Debian のカーネル更新のたびに修正が入ったかを確認し、入ったら標準カーネルに戻す。入っていない版が先に来た場合は、そちらが起動の既定になってしまうので再ビルドが必要になる。

## 添付ファイル

- [実装プラン](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/plan.md)
- [発生時の画面 (14:51 の件)](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/screen_hang_1451.jpg)
- [試験 2 回目でシャットダウンが止まった画面](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/screen_shutdown_stuck.jpg)
- [journal: 14:51 の引き金と guard の電源断拒否](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/journal_boot_1451_trigger_and_guard_refusal.log)
- [journal: 16:13 の WiFi 経由の再発と、手動 reboot が効かなかった記録](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/journal_boot_1613_wifi_leak_and_manual_reboot.log)
- [journal: guard の e2e 試験 2〜4](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/journal_guard_e2e_tests.log)
- [/var/log/netdev-leak-guard.log 全文](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-guard.log)
- [VPN 撤収イベント 38 件の一覧 (ログ解析)](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/vpn_teardown_events.md)
- 導入したファイル: [48-netdev-leak-guard](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/48-netdev-leak-guard) / [netdev-leak-check](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-check) / [netdev-leak-watch](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-watch) (+ [.service](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-watch.service) / [.timer](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-watch.timer)) / [netdev-leak-guard.conf](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/netdev-leak-guard.conf) / [60-reboot-watchdog.conf](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/60-reboot-watchdog.conf) / [softdog.conf](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/softdog.conf) / [watchdog-stop-on-reboot.conf](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/watchdog-stop-on-reboot.conf)
- [再現用の負荷スクリプト fpuload.py](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/fpuload.py)
- カーネルパッチ (リポジトリ本体): [patches/linux/0001-xfrm-fix-dev-refcnt-async-resumption-6.12.patch](../patches/linux/0001-xfrm-fix-dev-refcnt-async-resumption-6.12.patch)

## 前提・目的

- 背景: 9/18 14:51 に lid close 後にスリープせず発熱した (画面写真あり)。直前に iPhone USB テザリング + VPN (GSNet) を使い、蓋を閉じる前に USB を抜いていた
- 前回: [8/22 レポート](2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died.md)で同じ署名の枯渇死を扱い、フェイルセーフ hook `48-netdev-leak-guard` を導入済み
- 目的: (1) 原因をコードレベルで特定して修正する、(2) guard が効かなかった理由を突き止め、発症しても確実に安全側 (電源断) に倒れるようにする

## 環境情報

- 機体: MacBook Air 11" (Early 2015, MacBookAir7,1)、Debian 13 (trixie)
- カーネル: 発症時 6.12.95+deb13-amd64 (stock) → 作業中に stock 6.12.107-1 に更新 → 最終的に自前の **6.12.107-xfrmfix1**
- systemd 257.9-1~deb13u1、strongSwan 6.0.1-6+deb13u6 (charon-nm)、network-manager-strongswan 1.6.2-1
- VPN: GSNet (IKEv2 EAP、サーバ 160.16.210.47)。XFRM インタフェース `nm-xfrm-<N>` で if_id 方式のフルトンネル。ESP は AES_CBC_128/HMAC_SHA2_256_128
- 暗号実装: `cbc(aes)` は `cbc-aes-aesni` (async=yes、/proc/crypto で確認)
- スリープ: S3 deep、バッテリ時 lid close は suspend-then-hibernate。sleep フック 45-wl-unload (pre で `modprobe -r wl`) ほか
- ネットワーク: WiFi (wl, broadcom-sta DKMS) / iPhone USB テザリング (ipheth, `enxce6023bad528`)
- ビルド機: 開発機 (akdx01)、`make -j12 bindeb-pkg` で 31 分

## 事象タイムライン (9/18、JST)

| 時刻 | 事象 |
|---|---|
| 14:41 | iPhone USB テザリング (enx) で接続、VPN 稼働中 |
| 14:51:21 | USB 抜去 → enx 削除。charon-nm が IKE_SA の削除を試みるが送信不能 |
| 14:51:26 | lid close → suspend-then-hibernate 開始 |
| 14:51:31 | `waiting for enxce6023bad528 … Usage count = 12` 開始 (**lid close より前、抜去の 10 秒後 = 実行時に既に破壊済**) |
| 14:51:35 | nm-xfrm-1860628 削除 → `Usage count = -10` の待機も開始 |
| 14:53:18 | freeze 失敗 (charon-nm が D state) |
| 14:54:04 | **guard が検知・発火** → 60 秒後に poweroff を予約 |
| 14:55:04 | `systemctl poweroff` → logind が **「Action suspend-then-hibernate already in progress」で拒否** |
| 〜15:33 | 約 3.7 分周期で再試行と freeze 失敗を繰り返す (鞄の中で発熱)。guard は毎回検知したが、残った失敗 unit のせいで systemd-run が全滅。15:23 以降はログバッファ飽和で「not growing」と誤判定 |
| 15:33 | ユーザが電源長押しで強制終了 |
| 15:48 | (再起動後) 再び USB 抜去。このときは発症せず (後述: 抜去までに非同期復号が起きていなかった) |
| 16:13:30 | WiFi で VPN 中に lid close → sleep teardown で `wlp3s0 … = 3` / `nm-xfrm-1147959 … = -1` (2 回目の発症) |
| 16:19 | ユーザが `sudo reboot` / `sudo halt` を実行するも**同じ logind 拒否で無効** → 電源長押し |

## 根本原因: カーネル 6.12.94 の xfrm デグレ

### 機序 (ソースで確認)

`net/xfrm/xfrm_input.c` の `xfrm_input()` (6.12.94 以降):

1. 復号の前に `dev_hold(skb->dev)` を実行する (このときの skb->dev = 物理デバイス wlp3s0 / enx)
2. `x->type->input()` が `-EINPROGRESS` を返す (= 暗号処理が cryptd に回って非同期になる) と、参照を持ったまま return する
3. 非同期の完了時に `esp_input_done` → `xfrm_input_resume` → `xfrm_input(..., -1)` で処理を再開する
4. ループを抜けると `xfrm_rcv_cb()` → `xfrmi_rcv_cb()` (xfrm_interface_core.c:378-379) が **`skb->dev = xi->dev` (nm-xfrm) に書き換える**
5. decaps 経路の `if (async) dev_put(skb->dev);` が **nm-xfrm に参照を返してしまう**

非同期復号 1 パケットにつき、物理デバイスが +1、nm-xfrm が -1 ずれる。

- 持ち込んだのは 4236c30b4 (上流 1c428b038400「xfrm: hold dev ref until after transport_finish NF_HOOK」, Cc stable) で、6.12.94 で入った。本機のインストール履歴では 6.12.94 の導入は 6/25 (dpmwd 系も 6.12.94 ベース)、stock 6.12.95 の導入は 7/12
- 修正は上流 8045c0df98d4「xfrm: Fix dev use-after-free in xfrm async resumption」(v7.2-rc1, `Fixes: 1c428b038400`)。コミットメッセージに `unregister_netdevice: waiting for vti1 to become free. Usage count = -2` という同じ署名が書かれている。Cc stable が付いておらず、6.12.110 まで未収録 (Debian 6.12.107-1 も未修正)
- 非同期になる条件: x86 の 6.12 では `kernel_fpu_begin()` がプリエンプションだけを止める。そのため、カーネル内で FPU を使っている区間に割り込んだ softirq (受信処理) では `crypto_simd_usable()` が偽になり、aesni の simd ラッパが cryptd (非同期) に回す。だから発生は確率的で、セッション中に少しずつ蓄積する

### 数値の一致

待機メッセージの値は「参照数そのもの」で、カーネルは値が 1 になるのを待つ。

| 事例 | 物理デバイス | nm-xfrm | 1 を引いた値 |
|---|---|---|---|
| 8/21 | wlp3s0 = 10 | -8 | +9 / -9 |
| 9/18 14:51 | enx = 12 | -10 | +11 / -11 |
| 9/18 16:13 | wlp3s0 = 3 | -1 | +2 / -2 |
| 再現試験 1 (stock 6.12.95、非同期 11 回) | — | **-10** | -11 |
| 再現試験 2 (stock 6.12.107、非同期 5 回) | — | **-4** | -5 |
| 再現試験 3 (stock 6.12.107、非同期 7 回) | — | **-6** | -7 |
| 再現試験 4 (stock 6.12.107、非同期 112 回) | — | **-111** | -112 |

再現試験では tracefs の kprobe で `esp4:esp_input_done` (= 非同期完了) の回数を数え、その後 VPN を切った。**nm-xfrm の値が毎回ちょうど 1 − (非同期回数) になった**ことで、機序は確定した。試験 2〜4 は Debian の最新 stock 6.12.107-1 で行っており、「6.12.107 も未修正」は changelog だけでなく実機でも直接確かめている。

### 旧説の訂正 (8/22 レポート)

[8/22 レポート](2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died.md)は、引き金を「cfg80211 WARN (sme.c:848) = NM の teardown で WiFi 切断と VPN 撤収が並走する競合」としていた。これは**誤り**である。WARN は発症しなかったイベントにも出ており、破壊は teardown よりずっと前、VPN セッション中に蓄積している (14:51 の件はスリープと無関係に USB 抜去の瞬間に表に出た)。したがって、同レポートの次アクションにある「VPN 先行切断」も効果がない。bypass-lan の設定も無関係である (strongSwan のソースで確認: bypass ポリシーは ifindex=0、ルートも dev なしの throw route)。

ログ解析で、VPN 稼働中に下位デバイスが消えたイベントが 3 boot で 38 件あった。そのうち 30 件は MOBIKE で別経路に移り、VPN を撤収していない。残る 8 件が撤収して nm-xfrm を削除し、うち 3 件が発症した ([一覧](attachment/2026-09-18_211651_vpn_xfrm_kernel_regression_netdev_leak_fix/vpn_teardown_events.md))。なお、この解析を担当したサブエージェントは「lid close からスリープ突入まで約 91 秒かかったかどうか」を判別子としたが、これは wl のアンロードがリークで固まった**結果**であり原因ではないため採らない (添付ファイル冒頭にも注記した)。発症するかどうかは「それまでに非同期復号が起きていたか」で決まるので、撤収側のイベント列では判別できない。15:48 の USB 抜去が非発症だったのも、そのセッションで非同期復号が 0 回だったためと解釈できる。journal が残っている範囲 (7/4 以降) で発症したのは、8/21 と 9/18 の計 3 件だけである。

## guard (48-netdev-leak-guard) が効かなかった理由と対策

実機でリークを意図的に起こして `systemctl suspend` する e2e 試験を繰り返し、問題を 1 つずつ潰した。

| # | 問題 (証拠) | 対策 |
|---|---|---|
| 1 | `systemctl poweroff` が logind に拒否される: `Action suspend-then-hibernate already in progress`。フックはその sleep 処理の中で動くので、必ず拒否される (手動の reboot/halt も同じ) | logind を経由せず PID1 に指示する |
| 2 | 失敗した transient unit が残り、以後の `systemd-run` が全て rc=1 | `--collect` + 事前の `reset-failed` + 多重投入チェック |
| 3 | dmesg リングバッファが飽和して件数が 374→354 に減り、「not growing」と誤判定 | 判定を「最新の署名行 (タイムスタンプ込み) が 12 秒後に更新されたか」に変更 (`netdev-leak-check` に切り出し) |
| 4 | PID1 への `start poweroff.target --job-mode=replace-irreversibly` も拒否される: `Transaction for reboot.target/start is destructive (grub-common.service has 'start' job queued…)`。Debian の grub-common.service が sleep target に紐づき、irreversible で積まれるため (試験 1) | 拒否されたら `systemctl --force` (PID1 に直接。systemd-shutdown が kill → sync → unmount してから電源断) にフォールバックする |
| 5 | `--force` 後、systemd-shutdown が開始したまま 35 分以上止まった (試験 2、画面は unregister 行のみ) | `--force` の前に `systemctl thaw user.slice` (sleep 中の cgroup 凍結を解除) を追加。ただし試験 3 でも止まったので、これが主因ではなかった |
| 6 | 試験 3: thaw → `--force` → systemd-shutdown が watchdog (softdog, 5 分) を有効化した記録まであるのに、10 分以上止まり softdog も発火しない。softdog は watchdog core の reboot notifier で**再起動の直前に停止される**ため、その後のカーネル内の停止処理 (device_shutdown。wl の unregister が固まってデバイスのロックを握ったままと推定) で固まると救えない | `options watchdog stop_on_reboot=0` で watchdog を止めないようにする。softdog は `soft_reboot_cmd` 未設定なら `emergency_restart()` を直接呼ぶので、device_shutdown を経由せずにリセットできる |

**最終構成の e2e 試験 (試験 4)**: 20:56:58 にリーク状態 (非同期 112 回、nm-xfrm = -111) で suspend → pre 段で検知 → 20:58:10 通常の投入が拒否され `--force reboot` → systemd-shutdown が watchdog 5 分で開始 → カーネル内で停止 → **softdog が強制リセット → 21:06:32 に新しい boot が起動 (人手なし)**。約 10 分で再起動まで到達した。

補足:
- 試験 1 の後に手動で行った `systemctl reboot --force` (19:39) は、約 3 分 20 秒で次の boot が起動していた。このときは停止処理で固まらなかった理由は分かっていない (デバイスのロックを握る処理の状態の違いなどが考えられる)
- **本番設定 (ACTION=poweroff) で最終的に起きるのは電源断ではなく再起動である**。guard は電源断を試みるが、リーク状態では `systemctl --force poweroff` もカーネルの停止処理 (kernel_power_off も device_shutdown を通る) で固まる見込みが高い。その場合は softdog が救うが、softdog にできるのはリセット (再起動) だけである。e2e 試験は 4 回とも ACTION=reboot で行っており、poweroff の経路そのものは実機で試していない (sleep 中の job 衝突も device_shutdown も reboot と同じ経路を通るので、同じ結果になると判断した)。この再起動は許容した。再起動でリークは解消し、蓋が閉じていれば起動後の logind が通常どおりスリープさせるので、発熱と放電は止まる。強制リセットなので次回起動時に ext4 の `orphan cleanup` が出る (ジャーナルの軽い修復で、実害はない)

### 最終的な guard 構成 (実機に配置済み)

| ファイル | 役割 |
|---|---|
| `/usr/local/sbin/netdev-leak-check` | 署名が今も更新されているかを判定する (0 = ACTIVE) |
| `/usr/lib/systemd/system-sleep/48-netdev-leak-guard` | pre/post で判定し、ACTIVE なら 60 秒後に電源断を予約する (中止は猶予 60 秒の間だけ `sudo systemctl stop netdev-leak-poweroff.timer` で可能。発火後は止められない)。まず通常の job 投入を試し、拒否されたら thaw → `systemctl --force`。原本は `/root/48-netdev-leak-guard.bak-20260918` |
| `/etc/netdev-leak-guard.conf` | ACTION=poweroff (試験時のみ reboot)、GRACE=60、DRYRUN |
| `/usr/local/sbin/netdev-leak-watch` + `netdev-leak-watch.{service,timer}` (enabled、60 秒間隔) | 実行中の見張り。ACTIVE なら GNOME 通知 (critical) と wall で再起動を促す (boot ごとに初回、その後 30 分おき)。電源は切らない。GUI にログインしていないときは通知先がないのでログのみ。実リーク時に GNOME 通知「ネットワークのカーネル不具合を検知」が表示されることをユーザが画面で確認済み |
| `/etc/modules-load.d/softdog.conf` | softdog を常時ロードする (本機は iTCO_wdt が BIOS で無効で、hardware watchdog がない) |
| `/etc/modprobe.d/watchdog-stop-on-reboot.conf` | `options watchdog stop_on_reboot=0` |
| `/etc/systemd/system.conf.d/60-reboot-watchdog.conf` | `RebootWatchdogSec=5min` (シャットダウンの最終段が 5 分固まったらリセット)。通常時の実行中は watchdog を使わない (RuntimeWatchdog=0) |

リークした状態での手動の脱出手段: `sudo systemctl reboot --force` (素の `reboot` は sleep 処理中だと拒否される)。これでも固まる場合は、上記の softdog が 5 分でリセットする。

## 根本対策: 修正入り自前カーネル 6.12.107-xfrmfix1

### ビルド (opus サブエージェントに委譲し、バックポートの差分は本体で検証)

- ベース: stable v6.12.107 + Debian 6.12.107-1 のパッチ 78 本 (quiltimport) + 8045c0df98d4 のバックポート (ブランチ `xfrmfix-6.12.107`、src/linux-6.12.y 内)
- バックポートで上流と違う点は 2 つ。(1) 6.12 には `dev_hold` の周りに `spin_unlock/lock` がないので、`skb->dev`→`dev` の置換だけを適用した。(2) 6.12 の `xfrm_inner_mode_input()` は -EINPROGRESS を返さない (IP-TFS がない) ので、該当 hunk は省いた。全経路 (早期 drop / -EINPROGRESS / decaps / gro / transport_finish / drop) で「hold した元デバイスに 1 回だけ put」することを確認した
- config: 実機の `/boot/config-6.12.107+deb13-amd64` に対し、dpmwd 系と同じ調整 (SYSTEM_TRUSTED_KEYS 空、DEBUG_INFO_NONE、LOCALVERSION=-xfrmfix1)
- パッチ: `patches/linux/0001-xfrm-fix-dev-refcnt-async-resumption-6.12.patch`

### 導入と検証 (実機)

- headers → image を dpkg -i。DKMS で wl と facetimehd (patch 0001 適用済みのソース) が自動ビルドされた。GRUB の先頭が xfrmfix1 になり、`GRUB_DEFAULT=0` のまま既定で起動する。stock 6.12.107 / 6.12.95 は残してある
- 基本動作: WiFi 接続、wl / facetimehd ロード、`/dev/video0`、mem_sleep=deep、softdog と stop_on_reboot=0、netdev-leak-watch.timer がいずれも正常
- **修正の検証 (VPN を切る試験 ×3)**: 非同期復号 110 / 124 / 119 回の後に `nmcli con down GSNet` → **リーク署名 0 件**、nm-xfrm は消滅、D state のプロセス 0 (stock では同じ操作で毎回 1−N の署名が出た)
- **実スリープ**: VPN を張ったまま非同期 121 回 → `systemctl suspend` (RTC で +90 秒後に復帰) → 1 秒で S3 に入り、90 秒後に復帰。45-wl-unload は unloaded / reloaded、リーク 0、WiFi 再接続、nm-xfrm も正常に撤収

## 運用上の注意

- **Debian のカーネル更新時**: 標準の新版 (6.12.108 以降) が入ると、そちらが GRUB の先頭になり既定で起動する。セキュリティ更新は通るが、**修正が入っていなければデグレが戻る**。更新時は `8045c0df98d4` (「xfrm: Fix dev use-after-free in xfrm async resumption」) が収録されたかを changelog で確認する。収録済みなら xfrmfix1 は退役してよい。未収録なら、新版をベースに同じパッチで再ビルドする (手順は下記)
- guard の見張り (`/var/log/netdev-leak-guard.log`) は修正カーネル上でも残す。修正後に ACTIVE が出たら、別原因の新しいデータとして扱う
- ACTION を試験で reboot に変えたら、必ず poweroff に戻す (現在は poweroff)

## 再現方法

```bash
# --- 不具合の再現 (未修正カーネルで。リーク後は再起動が必要) ---
scp fpuload.py miminashi@macbookair2015.lan:/var/tmp/
ssh miminashi@macbookair2015.lan '
T=/sys/kernel/tracing
sudo nmcli con up GSNet; sleep 3
sudo sh -c "echo \"p:espdone esp4:esp_input_done\" >> $T/kprobe_events; echo 1 > $T/events/kprobes/espdone/enable"
for i in 1 2 3 4; do python3 /var/tmp/fpuload.py 45 & done     # カーネル FPU 負荷 (AF_ALG cbc(aes))
ping -q -c 150 -i 0.2 -s 1200 1.1.1.1; wait                      # VPN 経由の受信トラフィック
sudo cat $T/kprobe_profile                                       # espdone の回数 = N (非同期復号)
sudo nmcli con down GSNet; sleep 15
sudo dmesg | grep "unregister_netdevice: waiting"                # 未修正: nm-xfrm … Usage count = 1-N / 修正後: 出ない
'

# --- guard の e2e (上の状態から。ACTION=reboot にしておく) ---
ssh miminashi@macbookair2015.lan 'sudo sed -i "s/^ACTION=poweroff/ACTION=reboot/" /etc/netdev-leak-guard.conf; sudo systemctl suspend --no-block'
# → 約 10 分で自動再起動。確認後 ACTION=poweroff に戻す

# --- 修正カーネルのビルド (開発機、src/linux-6.12.y) ---
git fetch --depth 1 origin tag v6.12.107 && git checkout -b xfrmfix-6.12.107 v6.12.107
git quiltimport --patches ../debian-6.12.107-1/debian/patches      # linux_6.12.107-1.debian.tar.xz を展開したもの
git am ../../patches/linux/0001-xfrm-fix-dev-refcnt-async-resumption-6.12.patch
scp miminashi@macbookair2015.lan:/boot/config-6.12.107+deb13-amd64 .config
scripts/config --set-str SYSTEM_TRUSTED_KEYS "" --set-str SYSTEM_REVOCATION_KEYS "" \
  -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT -e DEBUG_INFO_NONE --set-str LOCALVERSION "-xfrmfix1"
make olddefconfig && rm -f include/config/auto.conf && make olddefconfig
make -j12 LOCALVERSION= bindeb-pkg
# 注意: パッケージの revision は src/linux-6.12.y の .version カウンタを引き継ぐ (今回は dpmwd の続きで -6)。
#       再ビルドで番号が小さくなると apt の版比較で古い方が優先されるので、LOCALVERSION を -xfrmfix2 等に変えて別パッケージにする
# 実機: sudo dpkg -i linux-headers-…xfrmfix1….deb linux-image-…xfrmfix1….deb (DKMS が wl/facetimehd を自動ビルド)
```

## 参照した過去のレポート

- [8/22 サスペンド不能→枯渇死 (初版 guard 導入、因果帰属は本レポートで訂正)](2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died.md)
- [6/28 カーネルソース解析 (H1 = xfrm→netdev 参照リーク仮説の初出)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [7/2 自前カーネルのビルド手順 (dpmwd1)](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [7/29 カメラ使用中 suspend の Oops 修正 (facetimehd patch)](2026-07-29_224045_camera_dead_after_suspend_while_in_use_fixed.md)
