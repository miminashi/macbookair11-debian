# サスペンド不能に陥って再試行を繰り返しバッテリが尽きた障害の調査と対策

- **実施日時**: 2026年8月22日 16:00 (JST)
- **障害発生**: 2026年8月21日 17:30 〜 22:41 (JST)

## 概要

8月21日の夜、蓋を閉じてスリープさせたはずの MacBook Air が、翌朝には電源が落ちて作業状態が失われていた。一見すると8月上旬の「swap 満杯でハイバネート書き込みに失敗した」障害の再発に見えるが、調査の結果まったく別の新しい障害モードであることが確定した。今回は swap もハイバネート機構も健全で、そもそもハイバネート画像の書き込みに一度も到達していない。サスペンドの前段である「プロセスの freeze」が構造的に失敗し続けたのが原因である。

引き金は、蓋を閉じた瞬間に走る NetworkManager のネットワーク撤収処理だった。WiFi (broadcom-sta の wl ドライバ) の切断と VPN (strongSwan の xfrm インタフェース) の削除が並走した際の競合で、カーネル内のネットワークデバイス参照カウントが壊れた。wlp3s0 は参照が 10 残ったまま、VPN 側の nm-xfrm インタフェースは参照が -8 という負値 (アンダーフロー) になり、両デバイスの削除処理が永久に完了しない状態に陥った。この状態はカーネル内部の破壊であり、再起動以外に回復手段がない。

参照カウントが壊れると、削除完了を待つプロセス (VPN デーモン charon-nm と、sleep フックの modprobe) が kill 不能の D state で固まる。サスペンドはプロセス freeze の段階でこの 2 タスクに阻まれ、20 秒でタイムアウトして毎回失敗する。ところが蓋は閉じたままなので、logind は約 7 分周期でサスペンドを再試行し続けた。17:30 から 22:40 までの約 5 時間で 46 回の試行がすべて同じ失敗を繰り返し、その間システムは画面を閉じたまま稼働し続け、22:41 頃バッテリが枯渇して強制停止した。

競合の発生源自体には前兆があった。今回の障害と同じ場所の cfg80211 の警告 (WARN) が、8月6日以降ほぼ毎回のスリープ撤収時に出ており、前回 boot の 16 日間で計 30 回記録されていた。普段は警告だけで実害がないが、今回はタイミングが悪く参照カウントの破壊にまで至った。つまり「警告は高頻度・発症は低頻度」の確率的な競合であり、WiFi と VPN を併用してスリープする通常の使い方を続ける限り再発しうる。

そこで今回は、発症そのものではなく「発症後に枯渇死する構造」を断つフェイルセーフを導入した。sleep フックの post 段でリークの署名 (増え続ける unregister_netdevice メッセージ) を検知したら、60 秒の猶予の後にクリーンシャットダウンする仕組みで、実機で検知ロジックの動作検証まで完了している。これで最悪でも「きれいに電源が切れている」状態になり、ファイルシステム破損リスクと 5 時間の無駄な放電はなくなる。競合の窓を狭める VPN 先行切断や、コードレベルの根本調査は次アクションとした。

## 前提・目的

- 背景: 8/21 夜に lid close 後のスリープが失敗し、翌朝バッテリ切れの強制停止状態で発見された
- 目的: 障害の原因を journal から特定し、8/5 の swap 満杯障害 ([前回レポート](2026-08-05_233935_hibernate_write_failed_swap_full_battery_died.md)) との異同を判定し、必要な対策を講じる
- 運用前提: S3(deep) 本採用済み ([Phase 5 恒久化](2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload.md) 以降)。バッテリ時の lid close は suspend-then-hibernate

## 環境情報

- 機体: MacBook Air 11" (Early 2015, MacBookAir7,1)、Debian 13 (trixie)
- カーネル: 6.12.95+deb13-amd64 (stock)
- スリープ: S3 deep (GRUB 恒久)、sleep フック 45-wl-unload / 46-lid0-ac-policy / 47-facetimehd / 50-kbd-backlight / 60-s3-soak-log / 70-h4-probe
- WiFi: broadcom-sta (wl) DKMS + udev 保護 (99-c7r3-wl-d3cold.rules)
- swap 3 層: zram0 3.7G (prio 100) + /swapfile 8G (prio 50) + sda3 3.7G (prio -2) — 本障害時は健全
- VPN: NetworkManager + strongSwan (charon-nm)、GSNet 接続 (xfrm インタフェース nm-xfrm-1102441)
- ネットワーク: WiFi (wlp3s0) 接続中 + VPN 稼働中の状態で lid close (バッテリ駆動)

## 事象タイムライン (2026-08-21、すべて JST)

| 時刻 | 事象 |
|---|---|
| 17:14 | 直前の suspend/resume サイクルは正常完了 (wl reloaded) |
| 17:30:37 | lid close (バッテリ) → logind が suspend-then-hibernate 開始。NM sleep teardown 中に **cfg80211 WARN (sme.c:848)** 発生 |
| 17:30:49〜 | `unregister_netdevice: waiting for wlp3s0 ... Usage count = 10` / `nm-xfrm-1102441 ... Usage count = -8` の永久ループ開始 (以後 5 時間で 3,671 件) |
| 17:30:39 | pre フック 45-wl-unload の `modprobe -r wl` (PID 639913) が netdev_wait_allrefs で D state 永久ブロック (timeout 10 の SIGTERM/SIGKILL 無効) |
| 17:32:09 | フックタイムアウト (90s) 後に suspend 実行 → **freeze 失敗** (20 秒、charon-nm + modprobe の 2 タスク) → status=1 |
| 17:38〜22:35 | logind が約 6.7 分周期で再試行。**計 46 回すべて同一の freeze 失敗**。wl-unload.log に FAILED 49 件 |
| 22:40:58 | journal 途絶 = **バッテリ枯渇死** (ハイバネート書き込みには一度も到達せず) |
| 翌 04:13 | ユーザが AC 接続して電源投入。`EXT4-fs (sda2): orphan cleanup` = 不正終了の痕跡。pstore 空 (panic ではない) |

## 証拠と解析

### 1. 引き金: cfg80211 WARN (net/wireless/sme.c:848)

lid close の 0.3 秒後、NM の sleep teardown (wlp3s0 切断 + VPN 撤収が並走) の最中に発生:

```
WARNING: CPU: 3 PID: 631306 at net/wireless/sme.c:848 __cfg80211_connect_result+0x8be/0x8d0 [cfg80211]
Workqueue: cfg80211 cfg80211_event_work [cfg80211]
```

v6.12 ソース (`src/linux-6.12.y/net/wireless/sme.c`) で確認したところ、この行は `__cfg80211_connect_result()` 内の `WARN_ON(bss_not_found)`。wl が報告した接続結果イベントを処理する時点で、対象 BSS が既に (teardown により) bss リストから消えている競合状態を意味する。この WARN の error path は BSS 参照の解放だけして early return するため、sme の状態整理が不完全なまま残る。

重要なのは **この WARN 自体は 8/6 以降ほぼ毎回のスリープ撤収で発生していた** こと (前回 boot 16 日間で計 30 回、[添付: WARN 履歴](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/warn_history_boot-1.log))。30 回中 29 回は実害なし。WARN は「競合が起きた」ことの表示であり、破壊に至るかはタイミング次第の確率事象である。

全トレース: [添付: cfg80211_warn_trace.log](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/cfg80211_warn_trace.log)

### 2. 致命傷: netdev refcount 破壊 (回復不能)

WARN の 12 秒後から、2 つのネットワークデバイスの削除が永久に完了しなくなった:

```
unregister_netdevice: waiting for wlp3s0 to become free. Usage count = 10      (リーク: 参照 10 残留)
unregister_netdevice: waiting for nm-xfrm-1102441 to become free. Usage count = -8  (アンダーフロー: 負値)
```

wlp3s0 (wl) は参照リーク、nm-xfrm (VPN の xfrm インタフェース) は過剰解放で負値。WARN の瞬間、charon-nm は bypass policy を wlp3s0 から nm-xfrm へ付け替える処理の最中であり、両インタフェースの参照の受け渡しが壊れたことと整合する。以後この 2 デバイスの unregister は netdev_wait_allrefs で永久待機となり、**再起動以外に回復手段がない**。メッセージは 10 秒周期で journal 途絶まで 3,671 件続いた。

### 3. suspend 永久失敗の機序: freeze 失敗

unregister 完了を待つタスクは kill 不能の D state で固まる:

- charon-nm (netlink 経由の削除要求が `netdev_run_todo` 内で待機)
- 45-wl-unload の `modprobe -r wl` (netdev_wait_allrefs 待ち。`timeout 10` の SIGTERM も systemd の SIGKILL も D state には無効)

suspend はプロセス freeze 段階でこの 2 タスクに阻まれる:

```
Freezing user space processes failed after 20.007 seconds (2 tasks refusing to freeze, wq_busy=0):
task:charon-nm  state:D ... netdev_run_todo+0x333/0x530
```

[添付: freeze_failure.log](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/freeze_failure.log)

### 4. 枯渇死に至った構造: lid closed による無限再試行

freeze 失敗で systemd-suspend-then-hibernate.service は status=1 で失敗するが、蓋が閉じたままのため logind が即座に次の試行を開始する。1 サイクルは「suspend 試行 (~42 秒で失敗) + 固まった modprobe への stop-sigterm/final-sigterm タイムアウト処理 (~6 分)」の約 6.7 分で、17:30〜22:40 に **46 回** 繰り返された ([添付: retry_loop_excerpt.log](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/retry_loop_excerpt.log)、[添付: wl-unload_excerpt.log](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/wl-unload_excerpt.log))。

この間システムは lid closed のまま S0 で稼働し続け、22:40:58 に journal が途絶 ([添付: journal_last_lines.log](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/journal_last_lines.log))。今回 boot に orphan cleanup の痕跡があり pstore は空、つまり panic ではなく電源喪失 = バッテリ枯渇死である (17:30 時点の残量は未記録のため、枯渇までの正確な放電レートは算出できないが、lid closed の S0 アイドルで 5 時間強という経過は不自然ではない)。

## 8/5 の swap 満杯障害との違い

| | 8/5 障害 ([レポート](2026-08-05_233935_hibernate_write_failed_swap_full_battery_died.md)) | 今回 (8/21) |
|---|---|---|
| 失敗段階 | ハイバネート画像の書き込み (ENOSPC) | その遥か手前のプロセス freeze |
| swap | 満杯が原因 | 無関係 (3 層化対策も健全) |
| 原因 | 7 日連続稼働による swap 逼迫 | WiFi+VPN teardown 競合による netdev refcount 破壊 |
| 回復可能性 | 条件が変われば次回成功しうる | 再起動まで永久に失敗 |
| 結末 | S3 フォールバック中に枯渇 | S0 のまま再試行ループで枯渇 |

8/6 に導入した swap 3 層化 ([対策レポート](2026-08-06_010053_zram_swapfile_hibernate_swap_full_countermeasure.md)) は今回の障害とは無関係で、機能に問題はない。

## 過去の調査との関係

- 旧仮説 **H1 (xfrm → netdev 参照リーク → netdev_wait_allrefs)** ([2026-06-28 のソース解析](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) で提示、当時の resume hang の原因としては 5 回の検証で不支持) の signature が、**初めて実地で発現した**。ただし発現場所は当時追っていた「resume 側の無音 hang ([C-7 で解決済](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md))」ではなく、suspend 前段の teardown である。H1 は「棄却された仮説」ではなく「別の障害モードとして実在した」ことになる
- 必要条件は「WiFi 接続中 + VPN (xfrm) 稼働中の sleep teardown」。C 系列の hang の必要条件だった radio-off や BT-PAN は関与していない

## 実施した対策: フェイルセーフ hook (48-netdev-leak-guard)

発症後は再起動しか回復手段がないのに、蓋が閉じたまま枯渇まで再試行し続ける構造が実害 (作業状態喪失 + 不正終了) の直接原因である。そこで sleep フックの post 段でリーク署名を検知し、クリーンシャットダウンに倒すフックを新設した:

- 配置: 実機 `/usr/lib/systemd/system-sleep/48-netdev-leak-guard` ([添付: フック本体](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/48-netdev-leak-guard))
- 動作: post 段で dmesg の `unregister_netdevice: waiting` を計数 → 0 なら即 no-op (通常時のコストなし) → 存在する場合は 25 秒後に再計数し、**増え続けている場合のみ** wall 通知の上で 60 秒後の `systemctl poweroff` を systemd-run の transient timer でスケジュール
- 猶予中の中止手段: `sudo systemctl stop netdev-leak-poweroff.timer`
- 誤爆対策: 署名は正常時には出ない (10 秒以上待たされた場合のみ出力) うえ、「増加中」の確認で過去残渣とも判別。freeze 失敗一般 (一過性でありうる) ではなく回復不能な署名だけに反応する
- 可逆性: ファイルを rm すれば従来動作
- 検証済み (実機、2026-08-22 15:58-16:00): ①署名なしで即 no-op (0.02 秒、ログ出力なし) ②署名残渣 (増加なし) で「not growing」判定の no-op ③/dev/kmsg への擬似署名注入で増加を再現し ACTIVE 判定 → DRYRUN で poweroff 抑止を確認 ④systemd-run の transient timer が発火・自動消滅することを無害コマンドで確認

これにより最悪ケースは「発症 → 次の (失敗する) suspend 試行の post 段で検知 → 約 1.5 分後にクリーンシャットダウン」となり、5 時間の放電と不正終了は起きなくなる。シャットダウン自体は D state タスクを抱えたままでも完走する (systemd のタイムアウト処理を経るため数分停滞しうるが完了する)。

## 次アクション

1. **VPN 先行切断の設計検討**: NM の teardown で WiFi 切断と xfrm 削除が並走する競合窓を、suspend 前に VPN を先に閉じて狭める (logind inhibitor または NM dispatcher の設計検討が必要)
2. **根本のコードレベル調査** (opus 委譲候補): `__cfg80211_connect_result` の WARN error path の後始末不足と、wl (broadcom-sta) が teardown 中に connect result イベントを送出する挙動の解析。broadcom-sta は方法 B (Debian ソース) で取得済み (`src/broadcom-sta-6.30.223.271/`)
3. **観測継続**: `/var/log/netdev-leak-guard.log` をウォッチリストに追加。guard 発火 = 発症の一級データ (発症頻度の推定に使う)。WARN (sme.c:848) の頻度も journal で追える

## 再現・確認方法

障害自体は確率的競合のため意図的な再現は不可。証拠の確認手順:

```bash
# 障害 boot (-1) の WARN と refcount 破壊
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 --no-pager | grep -E "sme.c:848|unregister_netdevice" | head'

# freeze 失敗
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 --since "2026-08-21 17:32" --until "2026-08-21 17:33" -k --no-pager'

# 再試行ループ (46 回) と最期
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 --since "2026-08-21 17:30" --no-pager | grep -c "Starting systemd-suspend-then-hibernate"'
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -1 --no-pager | tail -3'

# フックの動作テスト (擬似署名、DRYRUN)
ssh miminashi@macbookair2015.lan 'echo "unregister_netdevice: waiting for leaktest0 to become free. Usage count = 1" | sudo tee /dev/kmsg >/dev/null
(sleep 8; echo "unregister_netdevice: waiting for leaktest0 to become free. Usage count = 2" | sudo tee /dev/kmsg >/dev/null) &
sudo LEAK_GUARD_DRYRUN=1 sh /usr/lib/systemd/system-sleep/48-netdev-leak-guard post test
sudo tail -3 /var/log/netdev-leak-guard.log'
```

## 添付ファイル

- [実装プラン](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/plan.md)
- [cfg80211 WARN 全トレース](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/cfg80211_warn_trace.log)
- [freeze 失敗のカーネルログ](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/freeze_failure.log)
- [再試行ループの journal 抜粋](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/retry_loop_excerpt.log)
- [journal 最終行 (枯渇死の瞬間)](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/journal_last_lines.log)
- [wl-unload.log 抜粋 (FAILED 49 件)](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/wl-unload_excerpt.log)
- [WARN 発生履歴 (前回 boot 30 件)](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/warn_history_boot-1.log)
- [フェイルセーフ hook 本体](attachment/2026-08-22_160000_suspend_freeze_fail_netdev_leak_battery_died/48-netdev-leak-guard)
