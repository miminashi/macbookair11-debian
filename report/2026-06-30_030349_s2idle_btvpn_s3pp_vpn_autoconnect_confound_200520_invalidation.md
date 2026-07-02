# S3'' (traffic-only off) 30 cycle 駆動 → VPN autoconnect 不安定が判明、200520 32/32 clean も同 confound

- **実施日時**: 2026 年 6 月 30 日 01:00 〜 03:00 (JST)
- **位置づけ**: [2026-06-29_200520 S3 (bnep teardown) 32 cycle clean レポート](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) の次セッション引継ぎ (i) S3' の advisor レビューで「H2/H4 を分離できない設計欠陥」と判明し、代替設計 **S3'' = traffic-only off (heavy traffic を最初から走らせず軽 traffic 条件で snapshot のみ取得)** で 30 cycle を駆動した検証セッション。**結果として 0/30 hang を達成したが、retro-classify で「cycle 2-30 が VPN inactive 状態で suspend していた」ことが判明し、本実験 (および 200520 の 32/32 clean) は元の hang condition (BT-PAN+VPN 併用) を再現していなかった**ことが確定した。method + confound discovery として閉じ、rerun は次セッションへ引継ぎ。

## 結論 (先に要約)

1. **表面的事実**: 30 cycle 手動 lid close 全 clean (boot_id `fcc3d4b0...` 不変、suspend_stats 157→187、fail=0、PM entry/exit ペア完備)。
2. **しかしこの 0/30 は invalid signal**: retro-classify (`58-snapshot-only` の xfrm state snapshot) で:
   - **cycle 1 のみ xfrm state=2 / policy=14** (= VPN teardown 進行中、IKE_SA delete failed の状態)
   - **cycle 2-30 (29 cycle) はすべて xfrm state=0 / policy=0** (= VPN 完全 inactive、BT-PAN 単独状態)
   - `journalctl` で確認: cycle 2-30 期間中 (`02:25-02:55 JST`) の **IKE_SA established / delete イベントはゼロ**、active connections に GSNet は無し
   - → cycle 1 で VPN が teardown されてから cycle 2-30 は **NM autoconnect が機能せず VPN 再接続されなかった**
   - cycle 2-30 (29 cycle) は実質 [2026-06-28_063543](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) の対照セル「BT-PAN 単独 0/15」と同条件 → 0 hang は当然
   - **有効 trial は cycle 1 (N=1) のみ、clean = 何も結論できない**
3. **重大な副次的発見 (本日付の最高インパクト)**: 直前セッション [2026-06-29_200520](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) の 32/32 clean も同 confound:
   - 70-h4-probe (200520 セッションで既に動いていた hook) の .pre snapshot 32 個を retro-classify
   - **cycle 1 (19:05:12) のみ xfrm state=2、cycle 2-32 (31 cycle) はすべて xfrm state=0 / policy=0**
   - → **200520 の「H2 もしくは teardown timing が hang の必要条件成分」結論は重大 confound あり**
   - 200520 の S3 hook (57-bnep-down: `nmcli con down + bluetoothctl disconnect`) の効果は実証できていない可能性
   - cycle 2-32 が VPN inactive 状態 = 063543 対照セル相当 → S3 hook が無くても 0/31 だった可能性が高い
4. **本日のメソドロジー発見** (技術的に有用):
   - **A. NM の network teardown は `sleep.target` 到達より前に完了**: `Lid closed → NM sleep requested → BT-PAN/VPN/charon-nm teardown → Reached target sleep.target → systemd-suspend.service` の順 (cycle 1 タイムラインで実証)
   - **B. system-sleep/pre フックは NM teardown 完了後に走る**: 当初の S3'' 設計「bnep/xfrm/bnep netdev を完全 up のまま snapshot」は **構造的に不可能** (advisor も認めた誤った前提)
   - **C. cycle 1 で観測した xfrm residue (state=2 / policy=14) は kernel suspend に持ち越されている**: bnep は完全 teardown 済 (kthread NOT FOUND、netdev MISSING) なのに xfrm state が 2 個残存 → bnep 消失後の xfrm cleanup は非同期で残る、という新発見 (= 074509 の H1 機序「xfrm dev ref leak」を弱く支持する直接観察)
   - **D. VPN autoconnect は resume 後に確実に再接続されない**: GSNet の `connection.autoconnect=yes` でも、cycle 1 で teardown された後 cycle 2-30 で再接続されなかった (BT-PAN は autoconnect 機能していた = 非対称)
5. **次セッションの正しい設計** (advisor 確定): VPN watcher loop (例: `while: if bnep0 up && GSNet not active → nmcli con up GSNet`) で各 cycle 前に VPN を強制 up し、`58-snapshot-only` の xfrm_state>0 で valid cycle を gate して 30 valid cycles を集める。1-2 cycle で gate 動作を smoke test してから 30 cycle に進む。

## 添付ファイル

- [実装プラン (本セッションで実施したもの、矛盾修正後の最終版)](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/plan.md)
- [200520 32 cycle の xfrm state retro-classify 表](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/200520-retro-classify.md)
- [cycle 1 タイムライン (NM teardown vs sleep.target vs PM suspend entry の順序実証)](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/cycle1-timeline.log)
- [58-snapshot-only 全発火ログ (本セッション全 31 件 = smoke test 1 + cycle 1-30)](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/58-snapshot-only.log)
- [s3-soak.log 抜粋](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/s3-soak-excerpt.log)

## 通読版: 経緯と本セッションの位置づけ

(本レポート単体で全体像が掴めるよう散文でまとめる。細かい事実・数値・コマンドは後続の構造化セクション参照。)

### 何のためにやっているか

MacBook Air 11" (Early 2015) を日常用ノート PC として常用しているユーザの実害として、外出先で BT テザリング + VPN を使った状態で蓋を閉じてスリープに入ると、数回に一度ハングして強制電源断が必要になる事象がある。バッテリ残量は十分あるのに作業状態を喪失する。本プロジェクトの目的は、この**ハングを恒久的に消す**こと。

### このセッションに入るまでに分かっていたこと

ハングは特定の組み合わせ「BT テザリング + VPN + s2idle スリープ + 手動で蓋を閉じる」で 10% 前後の頻度で起きる。直前のセッション ([2026-06-29_200520](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md)) では「スリープ直前に Bluetooth 接続を明示的に切断するフック (S3 hook)」を入れて 32 回連続でハングなしを達成し、「Bluetooth 接続の片付けタイミングがハングの必要条件」と結論していた。次の検証は、その結論を「H2 (片付け途中の Bluetooth カーネルスレッドが居残ったまま suspend に入るのが原因)」と「H4 (USB の通信終了待ちが永久に終わらないのが原因)」のどちらかに絞り込むことだった。

### 本セッションの設計と狙い

引継ぎ案だった S3' は、事前の advisor (相談役) レビューで設計欠陥が見つかり却下された。理由は、Bluetooth ネットデバイスを止めると IP 通信そのものが流れなくなるので、H2 でも H4 でも同じ結果になり区別がつかないため。

代わりに採用したのが **S3'' = traffic-only off**: BT/VPN/Bluetooth カーネルスレッドはそのまま生かしておき、ping flood (重いトラフィック) だけを最初から流さない状態で 30 回スリープを試す。判定は単純で、ハングが 1 回でも出れば「H2 寄り (= 重いトラフィック量に依存しない)」、30 回ともクリーンなら「H4 寄り (= 重いトラフィック量に依存する) を示唆」というもの。元のハング観測 (063543) も実はトラフィック量が軽い状態で起きていたので、ハングが出る方が予想に整合する設計だった。

### 実際に起きたこと

最初の cycle (cycle 1) でスリープに入った直後、snapshot を取ったところ予想外の状態が記録された: Bluetooth カーネルスレッドは既に消失、ネットデバイスも消失、xfrm (VPN の暗号化テーブル) は 2 件だけ残存。当初は「実験前提が崩壊した」と判断して advisor に再確認したところ、advisor 自身が前回の助言を訂正した: **「Bluetooth を生かしたまま suspend に入る」という前提自体が間違いだった**。NetworkManager は蓋を閉じた瞬間に Bluetooth/VPN を片付け始め、それが完了してから systemd の sleep target に到達するため、system-sleep の pre フックが走る時点では既に Bluetooth は消えている。むしろ H2 の機序 (= 「片付け中の Bluetooth スレッドが残っている」) と整合する状態だった。

そのまま続行し、ユーザに cycle 2-30 を実施してもらった結果、30 回すべてクリーン。表面的には「H4 寄り」と書く準備をしていた。

ところが結果集計で xfrm の状態を見直したとき、深刻な異常に気づいた。**cycle 1 のみ xfrm の状態が残っていて、cycle 2-30 はすべて 0 件**だった。実機を確認すると VPN (GSNet) は active な接続から消えており、journal でも cycle 2-30 期間中に IKE_SA (VPN セッション) が再確立されたイベントはゼロ件。つまり **cycle 1 で VPN が切断されてから、cycle 2 以降は一度も再接続されていなかった**。`connection.autoconnect=yes` を設定していたにも関わらず、resume 後に VPN は復活していなかった。

cycle 2-30 (29 cycle) はすべて「BT テザリングだけ復活して VPN は無い状態」で suspend に入っていたことになる。これは過去レポート 063543 の対照セル「BT 単独 → 0/15 クリーン」と同じ条件であり、ハングが出ないのは当然だった。**有効な試行は cycle 1 のみ (N=1)、結果はクリーン。ここから機序を結論することはできない**。

### この発見が直前セッションに波及した

advisor から「200520 の 32/32 clean も同じ問題ではないか?」という指摘があった。既設の snapshot フック (`70-h4-probe`) が幸い `ip xfrm state` を capture していたので、200520 の 32 個分の snapshot を後追いで分類できた。結果は予想通り: **200520 も cycle 1 のみ xfrm 残存、cycle 2-32 (31 cycle) はすべて 0**。

つまり 200520 の「S3 hook (Bluetooth を明示的に切断) で 32 回クリーン」という結論は、実は **「BT 単独状態で 31 回クリーン (= 過去から既知)」+「BT+VPN 状態で 1 回クリーン (= S3 hook 介入あり)」** に分解される。S3 hook の効果は N=1 でしか測れておらず、実証されていなかった。

### この発見の意味

過去 1 週間で積み上げた「N 回連続クリーン」系の結果は、すべて同じ confound に陥っている可能性が高い。S1 (22/22 clean) と S3 (32/32 clean) と本セッション (30/30 clean) はいずれも「cycle 1 のみ VPN active、以降は VPN なし」というパターンの疑いがある。

一方、ハングそのものを観測した 063543 の 3/3 hang は別格で、当時はユーザが手動で各セルの状態を確認しながら進めていた (suspend 直前に VPN が active だったことを `deleting IKE_SA GSNet[N]` の journal 行で確認していた)。つまり 063543 は valid な観測として残る。問題は、その後の「対策を入れて連続クリーンを取った」セッション群が、対策を測れていなかったということ。

次のセッションでは、VPN が確実に毎 cycle 再接続されるように watcher loop を入れて、有効な試行を 30 回集めるところから rerun する必要がある。

### この実験から実際に得られた本物の知見

機序判定としては失敗だが、メソドロジーと観察として 4 つの新発見があった:

1. **NetworkManager の片付けタイミング**を初めてログで完全に追えた。蓋を閉じてから systemd-suspend が走るまでの間に、NM が VPN/BT を片付け、charon-nm が IKE セッションを delete し、Bluetooth ネットデバイスが消える順序が確定した。
2. **VPN の片付け残骸 (xfrm state)** がカーネル suspend に持ち越されている直接観察。Bluetooth は完全に消えているのに xfrm state は 2 件残っていた → 過去レポート 074509 で立てた仮説 H1 (xfrm の参照カウント漏れ) を弱く支持する material。
3. **VPN の autoconnect は信頼できない**: BT-PAN autoconnect は機能するのに、strongSwan/charon-nm 系の VPN は resume 後に確実には再接続されない非対称性を実証した。
4. **多目的 snapshot は将来の再分析に効く**: 70-h4-probe が xfrm state を capture していたおかげで、200520 の confound を遡及的に発見できた。今後の snapshot フックでも「目先の目的だけでなく、将来の再分析に有用な情報も広めに採る」が正しい設計指針と確定。

## 前提・目的

- **背景**: 200520 の引継ぎ (i) S3' (bluetoothctl disconnect 抜き) を実施予定だったが、advisor レビューで「bnep netdev teardown → bulk traffic 自然消失 → H2/H4 両方 0 hang 予測 → 分離不能」と判明し却下
- **代替設計 S3''**: traffic-gen (ping flood) を最初から走らせず軽 traffic 条件 (= 063543 元再現条件) を再現、pre フック (`58-snapshot-only`) は snapshot のみ。BT-PAN+VPN+bnep_session+xfrm を完全 up のまま suspend に進入させて hang が出るか観測
- **判定設計**: 1+ hang / 30 → heavy traffic 不要 = H2 強支持、0/30 clean → H4 示唆 (確率 4% で bound)
- **役割分担**: NM/hook デプロイ・cycle カウント支援・状態確認は Claude が ssh で実施。NM GUI 操作 (BT-PAN/GSNet up) と物理 lid close/wake はユーザ手動

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、LID0 `*enabled`
- system-sleep フック (実験中): `50-kbd-backlight`、**`58-snapshot-only`** (今回新規、Phase 4 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後では 3 個
- 電源: 全実験 AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer は iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`、xfrm interface `nm-xfrm-1048531`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.0/24`)。実験中は route-metric -1 → 800 に下げて VPN を BT-PAN 経由に強制、終了後 auto に revert
- baseline (実験開始時): boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動以来不変、200520 終了時から不変)、suspend_stats success=157 fail=0、h4-mode=beta、autoconnect 両方 no、route-metric -1
- dev 機 (akdx01): 何も書き換えなし、`src/linux-6.12.y` と `src/debian-6.12.94-1` 残置

## 実施内容と結果

### Phase 0: 一時設定 (01:00-01:07 JST)

実機 ssh で:
```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con up OpenWrt
```

ユーザ操作: iPad テザリング ON → NM GUI で BT-PAN up → GSNet up。

設定後の確認 (ssh):
- active: GSNet:vpn, iMiminashiPadPro ネットワーク:bluetooth, OpenWrt:802-11-wireless
- bnep netdev: `enx98e0d98d205e` (172.20.10.13/28)、`nm-xfrm-1048531`
- xfrm state: `src 172.20.10.13 dst 160.16.210.47` (VPN endpoint = BT-PAN IP) ✓
- route to 10.0.0.1: `dev nm-xfrm-1048531 src 192.168.83.1` (VPN tunnel 経由) ✓
- BT-PAN metric 750 < WiFi metric 800 ✓
- state=2 / policy=29 → baseline 揃え完了

### Phase 1: 58-snapshot-only hook 投入 (01:07-01:08 JST)

実機 ssh で:
```bash
sudo tee /usr/lib/systemd/system-sleep/58-snapshot-only > /dev/null << 'EOF'
#!/bin/sh
case "$1" in
  pre)
    rx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_before=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    sleep 0.5
    rx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/rx_bytes 2>/dev/null || echo 0)
    tx_after=$(cat /sys/class/net/enx98e0d98d205e/statistics/tx_bytes 2>/dev/null || echo 0)
    logger -t 58-snapshot-only "bnep delta 500ms: rx=$((rx_after-rx_before))B tx=$((tx_after-tx_before))B"
    if pgrep -f kbnepd > /dev/null 2>&1; then
      logger -t 58-snapshot-only "bnep_session kthread alive (H2 driver present)"
    else
      logger -t 58-snapshot-only "WARN bnep_session kthread NOT FOUND"
    fi
    if ip -br link show 2>/dev/null | grep -qE "^(bnep0|enx98e0d98d205e)[[:space:]]"; then
      logger -t 58-snapshot-only "bnep netdev present"
    else
      logger -t 58-snapshot-only "WARN bnep netdev MISSING"
    fi
    xfrm_state=$(ip xfrm state 2>/dev/null | grep -c "^src ")
    xfrm_policy=$(ip xfrm policy 2>/dev/null | grep -c "^src ")
    logger -t 58-snapshot-only "xfrm: state=${xfrm_state} policy=${xfrm_policy}"
    ;;
esac
EOF
sudo chmod 755 /usr/lib/systemd/system-sleep/58-snapshot-only
```

**プラン変更点** (実装時に判明、advisor も追認): bnep_session kthread の実際の名前は `[kbnepd bnep0]`。plan で書いた `pgrep -af 'kbnepd|\[bnep'` は dash の sh で BRE/ERE が機能せずマッチしないため、`pgrep -f kbnepd` (kbnepd を含むものを fixed string で grep) に簡略化。

手動 smoke test (`sudo /usr/lib/.../58-snapshot-only pre suspend`) で 4 行全て正常出力を確認:
- bnep delta 500ms: rx=0B tx=38B (= 軽 traffic、ほぼ idle)
- bnep_session kthread alive (H2 driver present) ✓
- bnep netdev present ✓
- xfrm: state=2 policy=29 ✓

cycle-watcher transient unit 起動 (実機側):
```bash
sudo systemd-run --unit=cycle-watcher --collect bash -c '...'  # 詳細は plan.md
```

### Phase 2: cycle 1 - 重大観察 (01:11 JST)

ユーザに「蓋閉じ → 待機 → 電源ボタン短押し」を依頼。cycle 1 結果:
- 01:11:34 `Lid closed`
- 01:11:34 NM `sleep requested` → BT-PAN/VPN/charon-nm teardown 開始 (`interface enx98e0d98d205e deactivated/deleted`、`deleting IKE_SA GSNet[1]`)
- 01:11:34 `bluetoothd: profiles/network/bnep.c:bnep_if_down() bnep: Could not bring down bnep0: No such device(19)` ← bnep は既に消えた
- 01:11:35 `Reached target sleep.target` ← NM teardown 完了**後**
- 01:11:35 `Starting systemd-suspend.service`
- 01:11:36 `58-snapshot-only` pre 発火: **kthread NOT FOUND、netdev MISSING、state=2 policy=14**
- 01:11:36 `PM: suspend entry (s2idle)`
- 01:11:57 `PM: suspend of devices complete after 482.710 msecs` + `PM: suspend exit` + `Lid opened`

**当初判断**: 「kthread NOT FOUND / netdev MISSING」を「実験前提崩壊」と解釈し、Phase 2 を中断して advisor に諮問。

**advisor 訂正** (重要、advisor 自身が前回の助言を訂正):
> 「bnep を up に保つ」は私 (advisor) の誤った前提だった。H2 の正しい記述は「freeze 窓を越える async teardown が in-flight」で、teardown 自体が driver。bnep を up に保つと逆に H2 を抑制してしまう。cycle 1 の状態は H2-relevant condition かつ canonical-hang condition (063543 の 3/3 hang も同じ「bnep torn-down-before-suspend」状態)。続行して問題なし。

→ verification criterion「kthread alive every cycle」を捨て、torn-down-before-freeze を正常状態として継続。

**新発見** (advisor の指摘): cycle 1 で xfrm state=2 / policy=14 (= bnep 完全 teardown 後でも xfrm が部分残留) を観測 = **kernel suspend に xfrm residue が持ち越されている直接観察**。074509 の H1 機序 (xfrm dev ref leak) を弱く支持する citable finding。

### Phase 2: cycle 2-30 駆動 (02:25-02:55 JST)

ユーザに cycle 2-30 (29 cycle) を実施してもらった。各 cycle:
- 蓋閉じ → 30-60 秒待機 → 電源ボタン短押し wake
- 全 cycle で 58-snapshot-only が pre 発火、ログを記録

全 30 cycle 統計:

| 指標 | 期待 (clean) | 実測 |
|---|---|---|
| boot_id | `fcc3d4b0...` 不変 | ✓ 不変 |
| suspend_stats success delta | +30 | **+30** (157→187) |
| suspend_stats fail | 0 | **0** |
| PM entry/exit ペア | 30/30 | **187/187** (累計、本実験 30/30) |
| 58-snapshot-only 発火 | 30 回 | **31 回** (cycle 1-30 + 手動 smoke test 1 回) |
| bnep delta 500ms | <10KB | **rx/tx 全 30/30 cycle で 0B/0B**、cycle 1 smoke test (手動実行) のみ tx=38B |
| WARN bnep_session kthread NOT FOUND | n/a (cycle 1 で発覚し以降は「正常状態」と再解釈) | **30/30 cycle 全件**、手動 smoke test のみ alive |
| WARN bnep netdev MISSING | n/a (同上) | **30/30 cycle 全件**、手動 smoke test のみ present |
| xfrm state | cycle 1 のみ state=2 (= VPN teardown 進行中)、以降 0 | cycle 1 **state=2** (policy=14)、**cycle 2-30 全 29 件で state=0 / policy=0** |

つまり cycle 2-30 (29 cycle) は **snapshot 出力が完全に一様** (delta 0/0、kthread NOT FOUND、netdev MISSING、xfrm 0/0)。cycle 1 のみ xfrm state=2 / policy=14 で他と異なる = **本実験で「BT-PAN+VPN active 状態で suspend に進入」したのは cycle 1 のみ** が retro-classify から確定。

**ここまで「30/30 clean」と判断、判定は H4 を示唆 (確率 4% bound)** と書く準備をしていたが、xfrm 分布で confound が露見した (次節)。

### Phase 3: 結果集計 - 衝撃の retro-classify 発見 (02:55-03:00 JST)

xfrm 分布を集計したところ:

| ts | xfrm_state | xfrm_policy |
|---|---|---|
| 01:07:17 (手動 smoke test) | 2 | 29 |
| 01:11:36 (cycle 1) | **2** | **14** |
| 02:25:10 (cycle 2) | 0 | 0 |
| 02:26:00 (cycle 3) | 0 | 0 |
| ... (省略) ... | 0 | 0 |
| 02:55:25 (cycle 30) | 0 | 0 |

**cycle 1 のみ xfrm state=2 / policy=14、cycle 2-30 はすべて state=0 / policy=0**。

確認:
- 現在の active connections: BT-PAN (`iMiminashiPadPro ネットワーク`)、OpenWrt のみ。**GSNet は不在**
- `journalctl --since 02:00:00 --until 03:00:00` で `IKE_SA established` / `deleting IKE_SA` 検索 → **ゼロ件**
- → **cycle 1 で VPN が teardown されてから cycle 2-30 では一度も再接続されていなかった**

つまり cycle 2-30 (29 cycle) は VPN inactive 状態 = 063543 対照セル「BT-PAN 単独 0/15」と同条件 → 0 hang は当然。

**有効 trial (= VPN active かつ lid close suspend) は cycle 1 のみ (N=1)、clean = 何も結論できない**。

### 衝撃の retro-classify 第二弾: 200520 32/32 clean も同 confound

advisor の指摘で 70-h4-probe (200520 セッションで既に稼働していた hook) の .pre snapshot を確認すると **`ip xfrm state` を capture している**。200520 の 32 cycle 分の .pre snapshot を retro-classify:

| cycle | ts (JST) | xfrm_state | xfrm_policy |
|---|---|---|---|
| 1 | 19:05:12 | **2** | 0 |
| 2 | 19:20:54 | 0 | 0 |
| 3 | 19:24:29 | 0 | 0 |
| ... (省略) ... | ... | 0 | 0 |
| 32 | 20:01:11 | 0 | 0 |

(完全な表は[添付](attachment/2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation/200520-retro-classify.md))

**200520 も cycle 1 のみ xfrm_state=2、cycle 2-32 (31 cycle) はすべて state=0 / policy=0** という同一パターン。

→ **200520 の「32/32 clean → H2 もしくは teardown timing が hang の必要条件成分」結論は重大 confound あり**:
- 200520 の S3 hook (57-bnep-down: `nmcli con down + bluetoothctl disconnect`) の効果は **実証できていない**
- cycle 2-32 が VPN inactive 状態 = 063543 対照セル相当 → S3 hook が無くても 0/31 だった可能性が高い

cycle 1 の policy が 200520 と本セッションで差がある (200520=0、本セッション=14) のは、teardown の進行度の揺らぎ (charon-nm の uninstall 順序の違い、各 cycle で snapshot された micro-second タイミングのずれ) と推定。両者とも state=2 は IKE_SA が deleting 進行中 (実 SA がまだ kernel に残っている) を意味する。

### Phase 4: Cleanup (03:00-03:03 JST)

```bash
sudo systemctl stop cycle-watcher.service
sudo rm /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con up OpenWrt
sudo rm -f /var/log/cycle-watcher.log
```

クリーンアップ後の実機状態: hooks 3 個 (50-kbd-backlight, 60-s3-soak-log, 70-h4-probe)、NM autoconnect 両方 no、route-metric -1、h4-mode=beta、transient units 両方 inactive、snapshot count pre=126 (= 96 + 30)、suspend_stats=187/0、boot_id 不変。**前セッション開始時の状態へ完全に巻き戻し**。

## 機序評価

### 確定的な観察

1. **VPN autoconnect は resume 後に確実に再接続されない (本セッションの最重要発見)**: GSNet `connection.autoconnect=yes` 設定でも、cycle 1 で teardown された後 cycle 2-30 で再接続イベントゼロ。BT-PAN は autoconnect が機能した (cycle 1 resume 直後の log で `iMiminashiPadPro ネットワーク` auto-activating + `interface bnep0 activated` 確認) = **非対称**
2. **NM teardown timing**: `Lid closed` → NM `sleep requested` → BT-PAN/VPN teardown 完了 → `Reached target sleep.target` → `systemd-suspend.service` → `system-sleep/pre` の順 (cycle 1 タイムラインで実証)
3. **xfrm residue が kernel suspend に持ち越し**: cycle 1 で bnep 完全 teardown 後でも xfrm state=2 / policy=14 残存 → 074509 の H1 機序 (xfrm dev ref leak → netdev_wait_allrefs) を弱く支持する初の直接観察。但し `unregister_netdevice: waiting` は依然出ていない (= netdev_wait_allrefs に到達せず正常 cleanup されている) ので H1 確定にはならない
4. **本実験の 0/30 clean は invalid signal**: 有効 trial は cycle 1 のみ (N=1)、clean だが N=1 では何も結論不能

### 200520 への含意 (本日付の最高インパクト)

- 200520 の 32/32 clean は **本質的に「BT-PAN 単独 + bnep teardown 介入 + 31 cycle」(= 063543 対照セルと同等条件) で 31/31 clean、加えて cycle 1 のみ valid (BT-PAN+VPN active で suspend) で 1/1 clean** に分解される
- 200520 の S3 hook (57-bnep-down) の効果は **N=1 (cycle 1) でしか測れていない**。31 cycle (cycle 2-32) は VPN なしなので S3 hook の有無は判定に影響しなかった
- **200520 の「H2 もしくは teardown timing が hang の必要条件成分」結論は、本セッションの retro-classify を踏まえて downgrade すべき**: 「N=1 観察、効果は実証されていない」

### 過去セッションへの波及確認 (要追加調査)

200520 と本セッションが同 confound に陥ったなら、より過去のセッション (S1 [041006] と driver path [064608]) も同様か要確認:
- [041006] S0 + S0.5 + S1 (btusb pre-unload) 22/22 clean → 70-h4-probe による xfrm state capture があるはず、retro-classify 可能
- [064608] 25 cycle driver path (free test) → driver path は `systemctl suspend` 駆動なので NM の sleep handler は走らない (lid close 経路と異なる)。VPN active な状態のまま suspend されるはず。要確認
- [063543] 元の 3/3 hang 観測 → ユーザ手動でしっかり factorial を確認している (各セルで active 検証あり) ので、これは valid なはず

→ **次セッション開始時に [041006] と [064608] も retro-classify することを推奨**。本日のセッションで時間切れのため未実施。

### 否定された / 確証された仮説

- **H1 (xfrm dev ref leak → netdev_wait_allrefs)**: 本セッションで bnep 完全 teardown 後の xfrm residue (state=2 policy=14) を直接観察 → 弱く支持。但し `unregister_netdevice: waiting` 不在 (依然 0 件) で確度 高 ではない
- **H2 (bnep_session non-freezable kthread が in-flight)**: 本実験では有効 trial が N=1 のみで判定不能
- **H4 (btusb URB drain)**: 同上
- **VPN autoconnect 機能の脆さ**: 確定 (本セッション cycle 2-30 で再接続ゼロ + 200520 retro-classify)

## 観測上の副次的発見

### A. NM teardown timing が cycle 1 タイムラインで初めて完全に可視化された

```
01:11:34.0 Lid closed (logind)
01:11:34.0 NetworkManager: sleep requested → ASLEEP state
01:11:34.1 wlp3s0: deactivating
01:11:34.1 BT-PAN (34:42:62:16:03:F6): deactivating
01:11:34.4 charon-nm: interface enx98e0d98d205e deactivated/deleted
01:11:34.4 charon-nm: deleting IKE_SA GSNet[1] between 172.20.10.13...160.16.210.47
01:11:34.6 NetworkManager: 全 device unmanaged-sleeping 完了
01:11:35.x Reached target sleep.target
01:11:35.x Starting systemd-suspend.service
01:11:36.x 58-snapshot-only pre 発火 (kthread NOT FOUND, netdev MISSING, state=2 policy=14)
01:11:36.x kernel: PM: suspend entry (s2idle)
01:11:57.x kernel: PM: suspend of devices complete after 482.710 msecs (= device suspend < 500ms)
01:11:57.x kernel: PM: suspend exit / Lid opened (= 電源ボタン短押し wake)
```

これは 063543 で記述された「NM は毎回 suspend 前に VPN/BT-PAN を soft teardown 済み」の **完全実証** = 「suspend 前フックで `nmcli connection down GSNet` を再実行する案は、システムが既にやっていることの反復」(063543 line 114) の論拠を強化。

### B. cycle 1 で IKE_SA delete が retransmit 失敗

```
01:11:34 charon-nm: sending packet: from 172.20.10.13[49768] to 160.16.210.47[4500] (80 bytes) (= IKE delete request)
01:11:34 charon-nm: error writing to socket: Network is unreachable
01:11:36 charon-nm: retransmit 1 of request with message ID 7
01:11:36 charon-nm: error writing to socket: Network is unreachable
01:11:57 charon-nm: retransmit 2 of request with message ID 7 (= suspend exit 後)
01:11:57 charon-nm: error writing to socket: Network is unreachable
```

bnep netdev が消えた後の IKE delete request 送信が失敗 → IKE_SA delete が完了しないまま suspend に入る → kernel に xfrm state=2 が残存 (= cycle 1 snapshot で state=2 を観測した理由)。これは GW (160.16.210.47) からは「クライアントが突然消えた」状態に見え、GW 側で IKE_SA timeout で cleanup される (DPD)。

### C. cycle 2-30 で VPN が再接続されなかった原因の仮説

- **(a) NM の VPN autoconnect は VPN-only モードで動作**: VPN を BT-PAN の上に張る場合、NM が「BT-PAN が up したら VPN を auto-activate」する依存解決を行うが、これは strongSwan/charon-nm の場合うまく動作しない既知の問題
- **(b) IKE_SA が dangling**: cycle 1 で delete が成立せず GW 側で SA が残っているが、ローカルからは消えた状態。NM が「VPN は既に gone」と判断、再接続を試みない
- **(c) charon-nm のプロセス状態**: cycle 1 で `Network is unreachable` retransmit が継続中、新規 IKE_SA establishment を試みない

→ 真因は要追加調査。次セッションは「VPN autoconnect に頼らず watcher loop で強制再接続」する設計で回避すれば valid trial が確保できる。

### D. 70-h4-probe の汎用性が retroactive analysis に効いた

70-h4-probe は元々 H4 / xfrm 切り分け用の **多目的 snapshot** として設計されており、本セッションの「VPN active 検証」目的とは別の使い方で:
- `ip xfrm state` を capture していたので、200520 32 cycle 分を retro-classify できた
- これが無ければ「200520 の 32/32 clean に同 confound あり」を本セッションで発見できなかった (発見が次セッション以降に遅延した可能性)
- **教訓**: snapshot 系の hook は「将来の再分析に有用な情報も含めて広めに capture する」が正解 (本セッションの教訓を 70-h4-probe デザイン段階で先取りしていた、と言える)

### E. cycle 1 の bnep delta rx=0B tx=0B の意味

cycle 1 snapshot (01:11:36) では bnep の rx/tx delta が 0/0 = traffic 完全停止。これは:
- NM teardown が完了 (= 01:11:34) → bnep netdev は既に DOWN もしくは削除済 → IP traffic は流れない
- BUT bnep netdev は (snapshot 時点で) MISSING = 既に消えていた → そもそも /sys/class/net/enx98e0d98d205e は存在せず rx_bytes は 0

つまり「軽 traffic を観測」ではなく「もう何も観測できない (netdev 自体が無い)」状態だった。これも本実験の設計上の問題を浮き彫りに。

### F. 手動 smoke test と cycle 1 の hook 動作差

| ts | source | kthread | netdev | state/policy |
|---|---|---|---|---|
| 01:07:17 | 手動 (`pre suspend` 引数) | alive | present | 2 / 29 |
| 01:11:36 | cycle 1 systemd-suspend | **NOT FOUND** | **MISSING** | 2 / 14 |

手動実行は systemd-suspend.service の context ではないので NM teardown は走らず、bnep_session/netdev が alive のままだった (= 当初の S3'' 設計が想定していた「bnep up のまま」状態を観測)。cycle 1 で systemd-suspend が走った時点では既に NM が teardown を完了している。**手動と systemd-suspend で hook の意味が変わる** という重要な insight。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 01:00 〜 01:07 | Phase 0 | NM 一時設定 + ユーザ操作 (iPad テザリング ON → BT-PAN/GSNet up) + 設定確認 (xfrm state=2 policy=29 確認) |
| 01:07 〜 01:08 | Phase 1 | 58-snapshot-only hook 投入 + syntax check + 手動 smoke test (state=2 policy=29 確認) + cycle-watcher 起動 |
| 01:11:34 | cycle 1 開始 | ユーザ lid close |
| 01:11:36 | cycle 1 snapshot | **WARN kthread NOT FOUND / netdev MISSING、state=2 policy=14** ← 重大観察 |
| 01:11:57 | cycle 1 wake | 電源ボタン短押し (asleep_s=21) |
| 01:11-02:25 | (advisor 諮問) | 「kthread NOT FOUND は H2-relevant condition」と訂正 → 続行判断 |
| 02:25:29 | cycle 2 (success=159) | cycle-watcher.log 初回 cycle 観測 |
| 02:25 〜 02:33 | cycle 2-10 | 9 cycle 連続 (各 ~40-50 秒間隔) |
| 02:33:05 | cycle 10 (success=167) | ユーザ「いま何回目ですか?」確認 (1 回目) → ~3 分 gap |
| 02:36 〜 02:48 | cycle 11-24 | 14 cycle 連続 (各 ~40-90 秒間隔) |
| 02:48:56 | cycle 24 (success=181) | ユーザ「いま何回目ですか?」確認 (2 回目) → ~3 分 gap |
| 02:51 〜 02:55 | cycle 25-30 | 最終 6 cycle |
| 02:55:32 | cycle 30 完了 (success=187) | 30 cycle 駆動終了、ユーザ「いま何回目?」(3 回目) で完了通知 |
| 02:55 〜 03:00 | Phase 3 集計 | xfrm 分布で cycle 2-30 すべて state=0 / policy=0 と判明 → VPN 再接続不在を確定 |
| 03:00 (advisor) | retro-classify 提案 | 200520 32 cycle の 70-h4-probe .pre から xfrm state を抽出 |
| 03:00 〜 03:01 | 200520 retro-classify | **200520 も cycle 1 のみ state=2、cycle 2-32 すべて state=0** と判明 |
| 03:01 〜 03:03 | Phase 4 cleanup | hook 削除、autoconnect revert、cycle-watcher stop |
| 03:03 〜 | Phase 5 レポート | (本ファイル作成) + メモリ更新 ([[s2idle-btvpn-hang-mechanism-ladder]] と MEMORY.md) |

実験全体所要時間: 約 **2 時間**。Phase 2 cycle 駆動は **30 分** (cycle 2-30 を 02:25-02:55 で完走、cycle 1 は advisor 諮問のため孤立して 01:11)。ユーザの cycle 駆動テンポは平均 ~60 秒/cycle (蓋閉じ + 待機 + 電源ボタン wake + 次 cycle 準備)。

## 検討して除外した事項

- **Phase 2 中の rerun (今セッションで VPN watcher 投入 + 30 cycle)**: ユーザに選択肢を提示したが、03:00 JST で既に 30 lid-close 実施済の負担を考慮し、**次セッション rerun を選択**。本セッションは method + confound discovery として閉じる
- **過去全セッションの一括 retro-classify**: 041006 / 064608 / 200520 / 本セッションを 70-h4-probe snapshot で全 retro-classify する案。本セッションは時間切れのため、200520 (= 直前セッション、最重要) のみ実施。041006 / 064608 は次セッション開始時の優先タスクとして引継ぎ
- **bluetoothctl disconnect 抜き S3'-orig**: advisor 設計欠陥指摘で本セッション開始前に却下済 (本プラン Context 節)

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-06-30 03:03 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット (xfrm state capture が retro-classify に効いた) |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 (前セッションから) | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで +30 ペア = 60 ファイル) | 本セッション 30 cycle の証拠 + retro-classify 素材 |
| cycle-watcher.service | **削除済** (transient unit、stop で消える) | 進捗監視 |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | revert 済 (-1 = auto) | |
| `/var/log/cycle-watcher.log` | 削除済 (evidence は journalctl + h4-probe pre snapshot に残置) | |

実機の suspend_stats: success 187, fail 0 (start 157 → +30)。boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (起動時刻 2026-06-28 12:32:55 JST、本セッション終了時 uptime ~1 日 14.5 時間、起動以来不変)。

dev 機 (akdx01) 側: 何も書き換えなし。`src/linux-6.12.y`, `src/debian-6.12.94-1` は前セッションから残置。

## 次セッション引継ぎ

### メモリ更新済 (本セッション終了時、次セッションは更新済の状態を前提)

- `~/.claude/projects/-home-miminashi-projects-macbookair11-debian/memory/s2idle-btvpn-hang-mechanism-ladder.md`: 全面改訂。「N/N clean」系結果は valid trial 数を retro-classify で確認するまで信用しないこと、本セッションと 200520 が cycle 1 のみ valid だった事実、VPN autoconnect 不安定性、次の手 (i)-(iii) の順序を反映
- `~/.claude/projects/-home-miminashi-projects-macbookair11-debian/memory/MEMORY.md`: `s2idle-btvpn-hang-mechanism-ladder` 行の description を本セッション結果に合わせて訂正

→ 次セッション開始時にメモリ index を再読すれば本セッションの結論が即時参照可能

### 開始時に確認すべきこと

```bash
ssh miminashi@macbookair2015.lan '
echo "=== alive + mem_sleep ==="
uname -r; cat /sys/power/mem_sleep; cat /proc/cmdline
echo "=== system-sleep hooks (期待: 50/60/70 の 3 個) ==="
ls /usr/lib/systemd/system-sleep/
echo "=== h4-probe infra (期待: mode=beta) ==="
sudo cat /var/lib/h4-probe/mode
echo "snapshot count: $(sudo ls /var/log/h4-probe/*.pre 2>/dev/null | wc -l) pre"
echo "=== NM autoconnect (期待: 両方 no) ==="
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
nmcli -t -f ipv4.route-metric con show OpenWrt
echo "=== boot_id (期待: fcc3d4b0... が残っているか、もしくは再起動済か) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats (期待: success=187 fail=0) ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting" || echo "0"
'
```

### 推奨の次の手 (優先順位順)

#### (i) 過去セッションの retro-classify (最優先、cycle 駆動不要、~30 分)

- **041006** (S0 + S0.5 + S1 22/22 clean): 70-h4-probe の .pre snapshot で xfrm state を retro-classify。22 cycle のうち何 cycle が valid (state>0) だったかを確認
- **064608** (driver path 25 cycle、heavy traffic 2/25): driver path (`systemctl suspend` 駆動) は NM の sleep handler が走らないはずなので xfrm active のまま suspend していると予想。本当にそうかを 70-h4-probe で検証
- **200520** (本セッションで実施済): cycle 1 のみ valid を確定

retro-classify 用コマンド (本セッションで使用したものを汎用化):
```bash
EPOCH_START=$(date -d "2026-06-29 04:00 JST" +%s)  # 適宜変更
EPOCH_END=$(date -d "2026-06-29 05:30 JST" +%s)
for f in /var/log/h4-probe/*.pre; do
  TS=$(basename "$f" .pre)
  if [ "$TS" -ge "$EPOCH_START" ] && [ "$TS" -le "$EPOCH_END" ]; then
    ISO=$(TZ=Asia/Tokyo date -d "@$TS" +%H:%M:%S)
    XFRM_S=$(sudo sed -n "/^=== ip xfrm state ===$/,/^=== ip xfrm policy ===$/{/^=== /d; p}" "$f" | grep -c "^src ")
    echo "$ISO xfrm_state=$XFRM_S"
  fi
done
```

判定:
- 041006 / 064608 / 200520 が全て「cycle 1 のみ valid」 → 過去 1 週間の「clean N/N」結果はすべて N=1 単発観測。プロジェクト全体の論証を見直す必要
- 041006 / 064608 のどちらかで複数 cycle valid → そちらは部分的に有効、論証の一部は維持可能

#### (ii) VPN watcher loop + 30 cycle rerun (本来の S3'' の正しい実施)

retro-classify が完了したら本来の rerun。設計:

**VPN watcher** (実機側 transient unit):
```bash
sudo systemd-run --unit=vpn-watcher --collect bash -c '
while true; do
  if ip -br link show enx98e0d98d205e 2>/dev/null | grep -q "UP"; then
    if ! nmcli -t -f NAME con show --active | grep -q "^GSNet$"; then
      logger -t vpn-watcher "BT-PAN up but GSNet inactive, re-activating"
      nmcli con up GSNet 2>&1 | logger -t vpn-watcher
    fi
  fi
  sleep 3
done
'
```

**gate** (58-snapshot-only の xfrm_state>0 を valid trial の定義に使う): 各 cycle 後に `journalctl -t 58-snapshot-only -b` で当該 cycle の xfrm_state が 0 なら invalid とカウント。30 valid cycles に到達するまで継続。

**smoke test**: rerun 開始前に 1-2 cycle で VPN watcher が動くことを確認:
1. BT-PAN+VPN up
2. lid close → wake (1 cycle)
3. journalctl で `IKE_SA established` が cycle 後に出現することを確認
4. 次 cycle の snapshot で xfrm_state>0 を確認

これが通ったら 30 valid cycles を駆動。invalid cycle が混ざるなら追加 cycle で valid trial を集める。

#### (iii) 上記 retro-classify と rerun の結果から、機序仮説を再評価

- 200520 retro-classify が confound 確定 → S3 hook (bnep teardown) の効果は再検証必要
- 041006 / 064608 の状況次第で H2 / H4 / H1 の確度が変動
- 「真の hang 観測 (063543 の 3/3)」と「N=1 単発観測 (cycle 1 系)」の連結で論証を再構築

### 推奨順

**(i) 過去 retro-classify (~30 分) → (ii) VPN watcher + rerun (~80 分) → (iii) 機序再評価 (15-30 分)**。1 セッションで (i) + (ii) は完走可能。(iii) は結果に応じて。

### 注意事項

- **本セッション・200520 含めた「N/N clean」系結果を機序判定に使うことは禁忌**: retro-classify で valid trial 数を確定するまで保留
- **063543 の 3/3 hang は valid**: 各セルで active 検証あり (line 60-69) で confound なし → 機序検討の基盤として依然信頼可能
- **lid wake 経路は s2idle で機能しない**: 200520 副次的発見 B (本セッションでも cycle 1 を電源ボタン短押しで wake させて確認、cycle 2-30 もすべて電源ボタン短押し)
- **70-h4-probe の xfrm state capture は維持すべき**: retro-classify の価値が判明したため、今後の hook も「将来の再分析に有用な multi-purpose snapshot」を意識
- **VPN autoconnect 問題は本機固有の可能性**: Debian 13 + NM + strongSwan/charon-nm + BT-PAN trunk という構成依存。upstream 報告候補だが、本プロジェクトの優先事項ではない (watcher で workaround 可能)

## 関連レポート

- [2026-06-29_200520 セッション 3: S3 (bnep teardown) 32 cycle clean](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md) — 直前セッション、本セッションで confound 判明
- [2026-06-29_064608 セッション 2: driver path + heavy traffic 25/25 clean (heavy traffic 2/25)](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md) — driver path、次セッションで retro-classify 必要
- [2026-06-29_041006 セッション 1: S0 + S0.5 + S1 22/22 clean](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md) — S1 (btusb pre-unload)、次セッションで retro-classify 必要
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) — 機序仮説、本レポート判定根拠
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md) — 元の 3/3 hang 観測、各セル active 検証あり = valid (本セッションの confound 議論では信頼できる基盤として残る)
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
