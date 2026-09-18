# 2026-09-18 ハング対策プラン: 原因は VPN の xfrm カーネルデグレ、修正カーネル + guard の作り直し

## Context

蓋を閉じて鞄に入れた MacBook がスリープせず発熱した。画面には `unregister_netdevice: waiting for enxce6023bad528 … = 12` /
`nm-xfrm-1860628 … = -10` と freeze 失敗が並んでいた。8/21 の枯渇死と同じ系統で、今日は 2 回起きている
(boot -2 14:51 は USB 抜去、boot -1 16:13 は WiFi の sleep teardown)。

### 判明した根本原因 (ソースで検証済み)
- **カーネル 6.12.94 で入ったデグレ** 4236c30b4 (上流 1c428b038400「xfrm: hold dev ref until after transport_finish NF_HOOK」) が原因。
  `net/xfrm/xfrm_input.c` では、`dev_hold(skb->dev)` で物理デバイスの参照を取ったまま暗号処理が非同期 (cryptd) に回る。
  再開後に `xfrmi_rcv_cb` (xfrm_interface_core.c:378-379) が `skb->dev` を nm-xfrm に書き換え、そのうえで decaps 経路が
  `dev_put(skb->dev)` するので、nm-xfrm 側に参照を返してしまう。**非同期復号 1 パケットにつき、物理デバイスが +1、nm-xfrm が -1 ずれる**。
  3 事例の値 (12/-10, 10/-8, 3/-1) は基準値 1 を差し引くとちょうど 1:1 になる (11/11, 9/9, 2/2)。
- 非同期になる理由: ESP は AES_CBC。実機の `cbc-aes-aesni` は async=yes (/proc/crypto で確認済み) で、softirq がカーネル FPU 区間に割り込むと cryptd に回る。
  そのため発生は確率的で、壊れた参照はセッション中に蓄積する。下位デバイスが消えた時点で初めて表に出る (USB 抜去や wl のアンロード)。
- 修正は上流の 8045c0df98d4「xfrm: Fix dev use-after-free in xfrm async resumption」(v7.2-rc1, Fixes: 1c428b038400)。
  コミットメッセージに同じ署名 `waiting for vti1 … Usage count = -2` が書かれている。Cc stable が付いておらず、6.12.110 まで未収録なので Debian 6.12.107 もまだ直っていない。
- 傍証: journal が残っている範囲 (7/4 以降、全て 6.12.94 以降) で発症したのは 8/6〜の 3 boot だけ。6/28 時点 (6.12.90) の grep 判別子は 5 回とも陰性だった。
- **8/22 レポートの因果帰属「cfg80211 WARN sme.c:848 / NM teardown 競合が引き金」は誤りなので訂正する** (WARN は非発症イベントにも出ていて無関係)。
  bypass-lan の設定変更や VPN の先行切断も効かない (破壊は teardown より前に蓄積済みのため)。

### guard (48-netdev-leak-guard) が効かなかった 3 つの欠陥 (journal で確認済み)
1. `systemctl poweroff` が logind に拒否された: `Action suspend-then-hibernate already in progress`。フックはその sleep 処理の中で動くので、必ず拒否される。
   ユーザが手動で打った `sudo reboot` / `halt` も同じ理由で効かなかった。
2. 失敗した transient unit `netdev-leak-poweroff.service` が残り、以後の systemd-run が全て rc=1 で失敗した。
3. dmesg のリングバッファが飽和して件数が減り (374→354)、「not growing」と誤判定した。

### ユーザ決定 (AskUserQuestion)
- カーネル: **6.12.107 に修正をバックポートした自前カーネル**を作る。stock は残し、Debian に修正が入ったら stock に戻す。
- guard: **実行中も監視して GNOME 通知**する。自動電源断は従来どおりスリープ試行時だけ。

## 実施手順

### Phase 1: guard の作り直し (実機、状態変更は本体が直接実行)
1. `/usr/lib/systemd/system-sleep/48-netdev-leak-guard` を改修する (原本は `.bak-20260918` として退避)。
   - 判定を「件数」から「**最新の署名行 (タイムスタンプ付き) が約 12 秒後に更新されたか**」に変える。これでリングバッファの飽和に左右されない。判定は共通スクリプト `/usr/local/sbin/netdev-leak-check` に切り出す。
   - post に加えて **pre でも判定する** (壊れた状態なら無駄な freeze 試行を待たない)。
   - 電源断は `systemctl start poweroff.target --job-mode=replace-irreversibly` にして logind を経由させない。unit は systemd-run の `--collect` で作り、事前に `reset-failed`、既に timer がアクティブなら何もしない。
     poweroff.target の JobTimeoutSec=30min / poweroff-force が最後の保険になる。
   - `/etc/netdev-leak-guard.conf` で ACTION=poweroff|reboot と DRYRUN を切り替えられるようにする (試験用)。
2. 実行時監視: `netdev-leak-watch.timer` (60 秒間隔) + `.service` を追加する。リークを検知したら、ログ出力・wall・ユーザセッション (uid 1000 の session bus) への
   `notify-send -u critical`「VPN のカーネル不具合でスリープ不能。蓋を閉じる前に再起動してください」を出す。通知は boot ごとに初回と、その後 30 分おき。
3. 手動の脱出手段を記録する: `sudo systemctl start reboot.target --job-mode=replace-irreversibly` (素の reboot は sleep 処理中だと拒否されるため)。

### Phase 2: 現行の stock 6.12.95 で不具合を再現 (ベースライン) し、guard を実戦で e2e 検証
1. tracefs の kprobe で `esp_input_done` (非同期完了の回数、= 未修正カーネルで漏れる参照の数) を数えるようにする。
2. VPN (GSNet) を WiFi 上で張り、VPN 経由で大きなダウンロードを流す。同時に AF_ALG (python の socket.AF_ALG で aes-cbc をループ) で
   カーネル FPU 負荷を全 CPU にかけ、非同期復号を誘発する。kprobe の回数が 0 より大きいことを確認する。
3. `sudo nmcli con down GSNet` → `waiting for nm-xfrm-* … Usage count = -N` が出れば再現成功 (nm-xfrm 側だけで露見するので WiFi は落とさず、ssh は維持できる)。
4. その壊れた状態を使って guard を試験する: conf を ACTION=reboot にし、実行時通知 (画面でユーザに確認してもらう) → `systemctl suspend` → freeze 失敗
   → guard → **D state のタスクを抱えたままでもクリーン再起動が完走するか**と所要時間を実測する。
   あわせて、sleep 中に `systemctl reboot` が拒否され `start reboot.target --job-mode=replace-irreversibly` なら通ることを確認する。
   終わったら ACTION=poweroff に戻す。
   (再現しなかった場合: 一時的な遅延フックで sleep 処理中の状態を作り、logind を迂回できることだけ単体で検証する)

### Phase 3: 修正カーネルのビルド (開発機、Phase 1-2 と並行可。定型のビルド作業は sonnet に委譲)
1. 実機で stock `linux-image-amd64` を 6.12.107-1 に更新する (セキュリティ更新、config の取得元、フォールバック用)。
2. `src/linux-6.12.y` に v6.12.107 タグを浅く fetch する。Debian 6.12.107-1 のパッチを適用し (前回と同じく quiltimport)、
   8045c0df98d4 を 6.12 のコードに合わせて手でバックポートする (xfrm_input.c で元の `dev` を退避、xfrm4/6_input.c から dev_put を除去、rcu の範囲を拡大)。
   衝突で難しければ 4236c30b4 の revert に切り替える。
3. 実機の `/boot/config-6.12.107+deb13-amd64` を元に `LOCALVERSION=-xfrmfix1` で `make -j12 LOCALVERSION= bindeb-pkg` (7/2 レポートの手順と落とし穴を踏襲)。
4. パッチは `patches/linux/0001-xfrm-fix-dev-refcnt-async-resumption-6.12.patch` としてリポジトリに保存する。

### Phase 4: 修正カーネルの導入と検証
1. headers → image を dpkg -i。DKMS で wl と facetimehd (patch 0001 適用済みのもの) が自動ビルドされることを確認する。
   `GRUB_DEFAULT=saved` + `grub-set-default` で xfrmfix1 を既定にし、sync してから再起動する。stock 6.12.107 は残す。
2. 基本動作: WiFi、カメラ、S3 の suspend/resume 1 サイクル (LID0 凍結 + RTC wakealarm の標準手順)、wl-unload フック、guard が no-op のままであること。
3. 修正の検証: Phase 2 と同じ負荷をかけ、kprobe で非同期の回数が 0 より大きいのに `nmcli con down GSNet` で `unregister_netdevice: waiting` が出ないことを確認する (3 回以上)。
   最後に VPN を張ったまま `modprobe -r wl` 相当を 45-wl-unload 経由の実際の suspend で確認する。

### Phase 5: 記録
- レポート `report/<ts>_vpn_xfrm_kernel_regression_netdev_leak_fix.md`。8/22 レポートの因果訂正を明記し、リンクする。プランを添付する。
- メモリ更新: 「低バッテリ時ハイバネ」の 8/21 項目の引き金の記述を訂正し、新しいメモリ (xfrm デグレ・自前カーネル運用・stock に戻す条件) を追加する。
- 運用メモ: Debian のカーネル更新ごとに `8045c0df98d4` の収録を確認する (収録されたら stock に戻す。未収録なら再ビルド)。
- commit はユーザ確認のうえで行う。

## 検証の要点 (完了条件)
- 修正カーネルで、非同期復号が 0 回より多く起きた VPN セッションを切断してもリーク署名が出ない。
- guard が「sleep 処理中」でも電源断/再起動に到達し、D state のタスクがあっても完走する (実測)。
- 実行時にリークが起きたら GNOME 通知が出る。
- 修正カーネル上で WiFi、カメラ、S3 の suspend/resume が従来どおり動く。
