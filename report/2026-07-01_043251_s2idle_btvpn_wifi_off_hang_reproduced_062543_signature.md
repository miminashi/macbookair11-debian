# WiFi-off で BT-PAN+VPN 蓋閉じハングを独立再現 — 063543 と同シグネチャ、ただし WiFi-on 抑制説は未確定

- **実施日時**: 2026 年 7 月 1 日 03:46 〜 04:30 (JST)
- **位置づけ**: [2026-06-30_061553 セッション](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) で達成した 30/30 BT-PAN-valid clean に対する **one-variable-back: WiFi-off**。Phase A で過去 2 セッション (041006, 064608) を source-IP retro-classify で bedrock 化、Phase B で WiFi-off 条件下 30 valid cycle 駆動を企図 → **cycle 20 で hang 発生**。「WiFi-on protective」結論は二つの壁 (statistical power N=1 hang 不足 + ping confound 未解消) で establish 不可。**Headline は (1) 063543 と同 signature で hang 独立再現、(2) candidate (d) baseline 低い説を更に弱める**。

## 結論 (先に要約)

1. **Phase A 完了 — 過去セッション bedrock 化**:
   - **041006 (S1 btusb pre-unload)**: 22/22 全 BT_PAN_VALID (src=172.20.10.13)、WiFi 経由混入 **0** → 「22/22 valid hang 0」を source-IP gate でも維持、bedrock 化
   - **064608 (driver path)**: 13 BT_PAN_VALID + 12 VPN_INACTIVE + WiFi 経由 0 → 過去 claim「~14 valid」が 13 に微訂正 (1 cycle 差、機序ラダーへの影響なし)
2. **Phase B 完了 — WiFi-off で hang 再現**:
   - **20 BT-PAN-valid cycle 試行で 19 完走 + 1 hang** (boot_id `fcc3d4b0` → `670cf7fd` 変化、pre=180 / post=**179** で 1 ペア欠落確定)
   - hang cycle = 20 番目 = 2026-07-01 04:15:50 JST
   - 全 20 cycle が source-IP gate で BT_PAN_VALID 確定 (`src=172.20.10.13`、WiFi 経由混入 0)
3. **Hang signature が 063543 と同一**:
   - `xfrm_state=2 / xfrm_policy=14` (= 半分、teardown 進行中で suspend 突入)
   - charon-nm の VPN delete が `error writing to socket: Network is unreachable` で 3 回 retransmit (= bnep 既に teardown 後)
   - `PM: suspend entry (s2idle)` が kernel 最終ログ、後続の `PM: suspend exit` 欠落 = **dpm_suspend stall** = 063543 (3/3 hang) と完全一致
   - 074509 のカーネルソース解析 (H1/H2/H4 仮説) で予測した「dpm_suspend 段 dpm_watchdog 無効化下での無音永久 loop」が再現
4. **「WiFi-on が protective」結論は establish されない** (advisor 指摘):
   - **第一の理由 (statistical power)**: 0/30 (061553) vs 1/20 (本セッション) は Fisher 正確検定 p ≈ 0.4 = 同じ rate で全く矛盾なし。低 rate (~2%) 仮定で「0/30 then 1/20」の joint probability ≈ 18%。**N=1 hang では強い結論は引き出せない、これは ping confound と独立の binding constraint**
   - **第二の理由 (ping confound、緩和された caveat)**: ユーザ自認で「連続 ping は他セッションでもだいたいやっていた、ただし必ず全部やっていたかは覚えていない」。h4-probe pre snapshot に ps/pgrep は無いので 061553 で直接検証は不可能 (xfrm `oseq=15/cycle` パターンは 061553 と本セッションで一致、但しこれは ping signature ではなく **ambient GNOME traffic (avahi/mDNS/NM connectivity/timesyncd/IPv6 ND/DNS) の ~1/sec floor とも整合**で非診断的)
   - → **次セッションは「WiFi-off + 明示的に連続 ping 禁止」で再実施 + N を増やす**で両方の constraint を解消する必要
5. **但し durable な headline は残る (advisor 指摘で訂正)**:
   - (a) **hang は独立再現された** (= 063543 と同 signature)、本プロジェクト 2 件目の verified hang
   - (b) **candidate (d) (「ベースラインは ~0」説 =「物差し自体が信用できない、ハングはほぼ無いんじゃないか」という説) は更に弱まる** — 二度目の verified hang で「063543 の 3 hang は外れ値」説は維持困難
   - (c) **WiFi 共通項ヒント (弱い示唆)**: 063543 (WiFi-off + hang)、本セッション (WiFi-off + hang)、061553 (WiFi-on + clean) — **2 つの hang セッションは WiFi-off を共有、唯一の clean は WiFi-on**。但しユーザ自認で「ping は他セッションでもだいたい流していた」 = ping の有無は 3 セッション間で揃っているか不明、当初書いた「連続 ping は本セッションだけ」という非対称性 argument は前提が崩れている。WiFi-on/off の共通項は残るが、N が小さい (063543 N=10, 本セッション N=20, 061553 N=30) ので統計的に弱い signal
   - (d) **連続 ping が機序を変えた可能性は構造的に薄い**: hang attempt cycle 20 の journal で「04:15:45 bnep teardown 完了 (172.20.10.13 disappeared)」が「04:15:51 PM: suspend entry」の **~6 秒前** = ping は既に dead interface に erroring していた状態で suspend 突入 → 「extra in-flight URB が race 窓拡大」(074509 H4) の論理は本 hang に適用しにくい → 但し別経路で ping が race を変えた可能性まで否定はできない
6. **次セッション設計**: **WiFi-off + 明示的に連続 ping 禁止 (= one-shot per-cycle 検証のみ) + N≥30 で 1+ hang 再現確認** で再駆動 (二つの壁 = ping confound + statistical power の両方を解消)。1+ hang 再現なら 60 cycle まで延長して再現性確認 → candidate (b) WiFi-off 強化、30/30 clean なら連続 ping が load-bearing だった可能性 or 統計的揺らぎの可能性で更に検証が必要

## 添付ファイル

- [実装プラン (本セッションで実施したもの、advisor 指摘 3 点を修正済の最終版)](attachment/2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature/plan.md)

## 通読版: 経緯と本セッションの位置づけ

(レポート全体の流れを散文でまとめる。細かい数値・コマンド・signature 比較は後続セクション参照。)

### このプロジェクトでやっていること

このマシンを外で使うとき、Bluetooth テザリング + VPN の状態で蓋を閉じると、数回に一度ハングして強制電源断するしかなくなる。バッテリは残っていても作業が飛ぶので不便。直近 1 週間は「何がトリガーか」を条件を切り替えながら一つずつ切り分ける作業を続けている。

### 前回 ([061553](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md)) までの整理

前回、WiFi を on にしたまま 30 cycle 連続でハングなしを達成した。だが元のハング ([063543](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md), 3/3 hang) と比べて条件が 4 つ違う:

- (a) BT-PAN の相手機 (iPhone → iPad)
- (b) WiFi (off → on)
- (c) 観測フック (薄 → 厚)
- (d) そもそも元の 3 ハング rate が想定より低い (= 偶然多かった説)

どれが効いたかは分からない。「条件を一つずつ戻して試す (one-variable-back)」しかない。本セッションはその第一弾で **(b) WiFi を off に戻す** を選んだ。

### やったこと

- **Phase A** (前準備、10 分): 過去 2 セッション (041006, 064608) の各 cycle で VPN が BT-PAN 経由だったか WiFi 経由だったかを後追いで確認、過去結果が「本当に valid だったか」を盤石化
- **Phase B** (本実験、80 分予定): WiFi を off にして他は前回と同じ条件で 30 valid cycle 駆動。WiFi off 中は ssh が切れるのでユーザ手動駆動 + 永続ディスク上の `.pre`/`.post` ファイル pair 欠落を hang 検出の確実な根拠とする (advisor 指摘で設計)

### 起きたこと

Phase A は予定通り完了 (過去 2 セッションとも WiFi 経由の混入なし、過去 claim を維持)。

Phase B は **20 cycle 目でハング発生**。reboot 後にユーザが WiFi を戻し、Claude が永続ディスク上の証拠 (`/var/log/h4-probe/` の pre/post ペア欠落) を回収して cycle 20 (04:15:50 JST) のハングを確定。19 cycle は完走、全 20 cycle とも VPN は BT-PAN 経由で確立 (= 真の N=20 valid 試行で 1 ハング)。

ハングの kernel ログ signature (PM: suspend entry の後 exit 欠落、xfrm policy が teardown 途中の半分、Network unreachable retransmit ×3 等) は **063543 の 3/3 ハングと完全に同じ**。dpm_suspend 段で永久 stall するという 074509 のカーネルソース解析の予測が二度目に再現された形。

### 解釈で詰まった点 (重要)

集計が終わって「WiFi-on が hang を抑えていた」と書こうとした段階で advisor から **二つの独立した壁** を指摘された:

**(1) そもそも統計的に弱い**: 0/30 (前回) と 1/20 (本セッション) は Fisher 正確検定で p ≈ 0.4 = 偶然そのバラツキになる確率が 4 割 → 同じ hang rate で全く矛盾しない。**1 hang では「WiFi-on が hang を抑えていた」とまでは到底言えない**。これは ping 議論と独立した、データ量自体の問題。

**(2) ping の confound 疑い (但し softening 必要)**: 当初「ユーザが本セッションだけ連続 ping を走らせていた = 二変数 contamination」と書いたが、後でユーザから「連続 ping は他セッションでもだいたいやっていた、ただし全部かは覚えていない」との情報。前回 061553 でも ping が流れていた可能性は十分ある。但し h4-probe pre snapshot には process list (ps/pgrep) が無いので直接検証は不可能。xfrm の oseq パターン (15 packets/cycle, 061553 と本セッションで一致) は ping と整合だが ambient GNOME 通信 (avahi/mDNS, NM connectivity 等) の ~1/sec floor とも整合で非診断的。→ **「本セッション固有の汚染」とは言い切れない、但し「両セッション通底のノイズ」とも断定できない**。

→ **「WiFi-on が protective」結論は本セッション単独では成立しない**。次セッションで「WiFi-off + 連続 ping 明示禁止 + N を増やす」で両方の壁を解消する必要。

### でも捨ててはいけない収穫

二つの条件が同時に違うので候補 (b) は確定できないが、以下は確実:

1. **ハングを独立に再現できた** — 063543 と signature 一致、本プロジェクト 2 件目の verified hang。durable な証拠で cycle 単位まで特定済
2. **候補 (d) (元の hang は偶然) はもう厳しい** — 二回独立に同じ signature で出たので、**「ベースラインは ~0」説**（=「物差し自体が信用できない、ハングはほぼ無いんじゃないか」という説）はもう持たない
3. **WiFi-off 側に分がある証拠もある (proof ではない、軽い示唆)** — 063543 と本セッションは両方 WiFi-off で hang を出した、唯一の clean (= 061553) は WiFi-on。WiFi-on/off が共通項として残る。さらにハングが起きた時点ではすでに bnep (BT-PAN のネットワーク) は片付けられた後で、連続 ping は消えたインターフェース宛にエラーを返し続けるだけの状態だった = ping が「URB (USB 転送) を流し続けて race 窓を広げた」という筋書きは構造的にも薄い (= ping を仮に犯人扱いしようとしても機序面で弱い)

### 次にやること

二つの壁 (statistical power + ping confound) の両方を解消する設計:
- **WiFi-off** (本セッションと同じ)
- **連続 ping 明示禁止** (= ping confound 解消) — 駆動開始前にユーザに事前案内
- **N を増やす** (= statistical power 確保) — 30 cycle で 1+ hang なら 60 cycle まで延長して再現性確認

結果分岐:
- 30+ cycle で 1+ hang 再現 → 「WiFi-off (連続 ping 抜きで) hang を出す」確定 → 機序探求 (= WiFi の何がスリープ chain を変えるか) へ
- 30/30 clean → 「連続 ping が hang に load-bearing だった」可能性、または「063543/本セッションが偶然両方 hang を引いた」可能性 (statistical power の問題)。更に検証必要

## 前提・目的

- **背景**: [2026-06-30_061553 セッション](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md) で 30/30 BT-PAN-valid clean を達成、本セッションは one-variable-back: WiFi-off で candidate (b) を discriminate する設計
- **本セッションのみで意味のある追加目的**: (1) 過去 041006/064608 を source-IP gate で bedrock 化、(2) hang 検出の durable ground truth (`/var/log/h4-probe/` `.pre`/`.post` ペア) を実証
- **役割分担**: hook/transient unit デプロイ・状態確認・retro-classify は Claude が ssh で実施。NM GUI 操作 (BT-PAN/GSNet up は autoconnect=yes で自動) と物理 lid close/wake、background ping 制御はユーザ手動。WiFi off で ssh 切断中はユーザに口頭で進捗報告依頼

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep` (s2idle 選択)、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)、LID0 `*enabled`
- system-sleep hooks (本セッション実施中): `50-kbd-backlight`、`58-snapshot-only` (本セッションで新規投入、Phase B-6 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後は 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, BT-PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`)
- WiFi: `wl`/`wlp3s0`、接続 `OpenWrt` → **本セッション Phase B-3 で `nmcli radio wifi off` で完全 disable** (wl モジュールはロード状態のまま = 063543 と同じ soft rfkill レベル)
- baseline (実験開始時 03:46 JST): boot_id `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (061553 終了時から不変)、suspend_stats success=221 fail=0、snapshot count=160 pre、NM autoconnect 両方 no、route-metric -1、wl loaded refcount=0、unregister 0 件
- baseline (実験終了時 04:30 JST): boot_id `670cf7fd-ad6d-4f42-90c8-0d8f359099e2` (**hang reboot で変化**)、uptime ~12 分、suspend_stats success=0 fail=0 (新 boot リセット)、snapshot count=180 pre / 179 post、NM autoconnect 両方 no (Phase B-6 cleanup)、route-metric -1、wl loaded refcount=0、unregister 0 件
- 比較対照 063543 との condition 差: peer = iPhone→**iPad**、WiFi = off→**off (同じ、`nmcli radio wifi off`)**、hook = 50/60 のみ→**50/60/70 + 58**、traffic = 素 traffic→**連続 ping** (但しユーザ自認で 063543 にも ping が走っていた可能性あり、h4-probe に ps 無く直接検証不可、副次的発見 D 参照)、駆動 = 手動 lid close + 電源ボタン wake (同じ)

## Phase A: 041006 / 064608 source-IP retro-classify (~03:43-03:45 JST、Phase B より前)

### 実行スクリプト

```bash
ssh miminashi@macbookair2015.lan 'bash -s' <<'OUTER_EOF'
for SESSION in "041006_S1|2026-06-29 03:25 JST|2026-06-29 03:57 JST" \
               "064608_driver|2026-06-29 05:43 JST|2026-06-29 06:43 JST"; do
  NAME=$(echo "$SESSION" | cut -d"|" -f1)
  START=$(echo "$SESSION" | cut -d"|" -f2)
  END=$(echo "$SESSION" | cut -d"|" -f3)
  EPOCH_START=$(date -d "$START" +%s)
  EPOCH_END=$(date -d "$END" +%s)
  echo "=== $NAME ($START 〜 $END, epoch $EPOCH_START〜$EPOCH_END) ==="
  for f in /var/log/h4-probe/*.pre; do
    TS=$(basename "$f" .pre)
    if [ "$TS" -ge "$EPOCH_START" ] && [ "$TS" -le "$EPOCH_END" ]; then
      LOCAL_SRC=$(sudo sed -n '/^=== ip xfrm state ===$/,/^=== ip xfrm policy ===$/{/^=== /d; p}' "$f" | grep "^src " | awk '{print $2}' | grep -v "^160\.16\.210\.47" | head -1)
      # 三分類: VPN_INACTIVE / BT_PAN_VALID / WIFI_KNOWN_CLEAN
    fi
  done
done
OUTER_EOF
```

### Phase A 結果

| セッション | total cycle | BT_PAN_VALID (src=172.20.10.*) | VPN_INACTIVE | WIFI_KNOWN_CLEAN | 過去 claim | source-IP gate 後 |
|---|---|---|---|---|---|---|
| 041006_S1 (03:25:38〜03:56:42) | 22 | **22** | 0 | **0** | 22/22 valid | **22/22 BT_PAN_VALID 維持** |
| 064608_driver (05:43:54〜06:40:43) | 25 | **13** | 12 | **0** | ~14 valid | **13 BT_PAN_VALID + 12 inactive (1 cycle 差)** |

両セッションとも WiFi 経由 VPN 混入は **0 件** → state count gate ベースの過去 valid claim は本質的に維持。041006 は full bedrock 化、064608 は 14→13 で微訂正 (機序ラダーへの影響なし)。**過去レポートを更新する必要なし**、メモリ `s2idle-btvpn-hang-mechanism-ladder` の「過去セッションの valid 性」表のみ反映。

### Phase A 副次的観察

- 064608 の 12 VPN_INACTIVE 期間 (05:47:57〜05:59:19) は v2 の iperf3 死亡 + VPN tunnel dead 期間 (報告本文と一致)
- 041006 の cycle 間隔は中央値 ~60 秒、064608 v3 の cycle 間隔は ~60 秒だが終盤 (06:39:54〜06:40:43) で 5 秒間隔に短縮 (= ユーザのキー押下 wake で早期 wake → 即時再 suspend、報告本文と一致)

## Phase B: WiFi-off で 30 valid cycle 駆動 (03:46-04:18 JST → hang で中断)

### Phase B-0: 開始時 baseline 確認 (03:46-03:46 JST)

実機 ssh で baseline 7 項目を確認、全て期待値と一致 (boot_id `fcc3d4b0...` 不変、suspend_stats 221/0、hooks 3 個、mode=beta、autoconnect 両方 no、route-metric -1、transient units 全 inactive、unregister 0 件、wl loaded refcount=0)。

### Phase B-1: hook + transient units デプロイ (03:46 JST)

#### 58-snapshot-only hook

061553 と同じスクリプト (bnep delta / kbnepd 存在 / netdev 存在 / xfrm state+policy count を logger で記録)、`/usr/lib/systemd/system-sleep/58-snapshot-only` に install。手動 smoke test で正常動作確認。

#### vpn-watcher + cycle-watcher

`systemd-run --unit=vpn-watcher --collect` で 3 秒間隔 poll で「BT-PAN UP かつ GSNet inactive → `nmcli con up GSNet`」を起動。cycle-watcher で suspend_stats delta を `/dev/shm/cycle-progress` に書き出し。両 unit active 確認。

#### NM autoconnect=yes 設定

```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
```

### Phase B-2: BT-PAN + VPN セットアップ (~03:47 JST)

ユーザ操作で iPad テザリング ON。NM autoconnect=yes により BT-PAN + GSNet が自動 up。

**問題発覚**: xfrm src=**192.168.33.145** (= WiFi IP) = VPN が WiFi 経由で確立されていた。原因: WiFi metric 600 < BT-PAN metric 750 で default route が WiFi 経由、autoconnect 動作時に charon-nm が WiFi 経路を選択。

**判断**: 本セッションは Phase B-3 で WiFi-off にするため、route-metric 調整は moot。WiFi off 後に vpn-watcher が GSNet を再 activate すれば、唯一残る経路 (BT-PAN) で再確立されるはず。そのまま Phase B-3 に進入。

### Phase B-3: WiFi-off (03:48 JST) — ssh 切断ポイント

```bash
sudo nmcli con down OpenWrt
sudo nmcli radio wifi off
```

実行直後に ssh 切断 (=期待動作)。これ以降、Claude は実機の状態を見ることができず、ユーザが手動で進める。

### Phase B-4: 手動 30 valid cycle 駆動 (~03:58-04:15 JST) → hang

ユーザが手動 lid close + 電源ボタン wake を繰り返した。連続駆動中、ユーザは各 cycle で `nmcli con show --active` で BT-PAN + GSNet active 確認、`ping 10.0.0.1` で VPN 疎通確認。**この ping を background で連続実行していた** (= ping confound、機序評価セクション + 副次的発見 D で議論。但しユーザ自認では他セッションでも同様の可能性あり、本セッション固有の汚染とは断定できない)。

**本セッション後の durable evidence (`/var/log/h4-probe/`) から復元した cycle 構造**:

| cycle | pre 時刻 (JST) | post 時刻 (JST) | asleep | xfrm src | 状況 |
|---|---|---|---|---|---|
| 1 | 03:58:50 | 03:58:59 | 9s | 172.20.10.13 | 完走 (asleep 短い = lid open or 電源 wake 早め) |
| 2 | 03:59:41 | 04:00:01 | 20s | 172.20.10.13 | 完走 |
| 3 | 04:00:33 | 04:02:08 | 95s | 172.20.10.13 | 完走 (asleep 長い) |
| 4 | 04:02:40 | 04:02:45 | 5s | 172.20.10.13 | 完走 |
| 5 | 04:03:27 | 04:04:07 | 40s | 172.20.10.13 | 完走 |
| 6 | 04:04:39 | 04:04:45 | 6s | 172.20.10.13 | 完走 |
| 7 | 04:05:17 | 04:05:32 | 15s | 172.20.10.13 | 完走 |
| 8 | 04:06:04 | 04:06:23 | 19s | 172.20.10.13 | 完走 |
| 9 | 04:06:55 | 04:07:09 | 14s | 172.20.10.13 | 完走 |
| 10 | 04:07:41 | 04:07:47 | 6s | 172.20.10.13 | 完走 |
| 11 | 04:08:19 | 04:08:26 | 7s | 172.20.10.13 | 完走 |
| 12 | 04:08:58 | 04:09:06 | 8s | 172.20.10.13 | 完走 |
| 13 | 04:09:40 | 04:09:58 | 18s | 172.20.10.13 | 完走 |
| 14 | 04:10:30 | 04:10:44 | 14s | 172.20.10.13 | 完走 |
| 15 | 04:11:16 | 04:11:30 | 14s | 172.20.10.13 | 完走 |
| 16 | 04:12:02 | 04:12:41 | 39s | 172.20.10.13 | 完走 |
| 17 | 04:13:13 | 04:13:27 | 14s | 172.20.10.13 | 完走 |
| 18 | 04:13:56 | 04:14:21 | 25s | 172.20.10.13 | 完走 |
| 19 | 04:14:53 | 04:15:18 | 25s | 172.20.10.13 | 完走 |
| **20** | **04:15:50** | **— 欠落 —** | — | **172.20.10.13** | **HANG** |

集計: **20 BT-PAN-valid cycle 試行 / 19 完走 / 1 hang**。ユーザ体感の「14 cycle くらい」は実数 20 とずれているが、これは lid close 数のカウントが体感ベースだったため (durable な journal evidence で 20 確定)。

### Phase B-5: Hang signature 解析 (04:25-04:30 JST)

#### Hang cycle (cycle 20) の journal 抜粋

```
04:15:30 charon-nm: IKE_SA GSNet[22] established between 172.20.10.13[macbookair2015]...160.16.210.47[160.16.210.47]
04:15:30 vpn-watcher: 接続が正常にアクティベートされました
04:15:37 systemd-logind: Lid closed.
04:15:45 systemd-logind: Suspending...
04:15:45 NetworkManager: device (wlp3s0): state change: unavailable -> unmanaged (reason 'unmanaged-sleeping')
04:15:45 NetworkManager: device (34:42:62:16:03:F6): state change: activated -> deactivating (reason 'sleeping')
04:15:45 NetworkManager: dhcp4 (enx98e0d98d205e): canceled DHCP transaction
04:15:45 charon-nm: 172.20.10.13 disappeared from enx98e0d98d205e
04:15:45 charon-nm: interface enx98e0d98d205e deactivated
04:15:45 charon-nm: interface enx98e0d98d205e deleted
04:15:45 charon-nm: old path is not available anymore, try to find another
04:15:45 charon-nm: no route found to reach 160.16.210.47, MOBIKE update deferred
04:15:45 charon-nm: deleting IKE_SA GSNet[22]
04:15:45 charon-nm: sending DELETE for IKE_SA GSNet[22]
04:15:45 charon-nm: error writing to socket: Network is unreachable
04:15:47 charon-nm: retransmit 1 of request with message ID 7
04:15:47 charon-nm: error writing to socket: Network is unreachable
04:15:50 charon-nm: retransmit 2 of request with message ID 7
04:15:50 charon-nm: error writing to socket: Network is unreachable
04:15:50 systemd: Reached target sleep.target - Sleep.
04:15:50 systemd: Starting systemd-suspend.service - System Suspend...
04:15:50 systemd-sleep: Successfully froze unit 'user.slice'.
04:15:50 kbd-backlight-sleep: pre/suspend: saved=84 set->0
04:15:50 snapshot-only: [PRE] bnep_rx=0 bnep_tx=0
04:15:50 snapshot-only: [PRE] kbnepd_session=NOT FOUND
04:15:50 snapshot-only: [PRE] bnep_netdev=MISSING
04:15:50 snapshot-only: [PRE] xfrm_state=2 xfrm_policy=14    ← 半分! NM teardown 進行中
04:15:51 70-h4-probe: phase=pre file=/var/log/h4-probe/1782846950.pre
04:15:51 systemd-sleep: Performing sleep operation 'suspend'...
04:15:51 kernel: PM: suspend entry (s2idle)    ← これが最終 kernel log
(以降 PM: suspend exit なし → dpm_suspend で永久 stall)
```

#### 063543 hang との signature 一致

| 観察項目 | 063543 (3/3 hang) | 本セッション cycle 20 hang |
|---|---|---|
| Network is unreachable retransmit | 3 回 (各 hang) | **3 回 (= 1 + retransmit 1, 2)** ✓ |
| bnep teardown 完了タイミング | suspend entry 前 | **suspend entry の ~6 秒前** ✓ |
| snapshot-only xfrm_policy | **14** (= teardown 半分) | **14** ✓ |
| PM: suspend entry の存在 | あり (s2idle) | **あり (s2idle)** ✓ |
| PM: suspend exit の有無 | **欠落** | **欠落** ✓ |
| boot_id 変化 | あり (各 hang ごと) | **あり** (`fcc3d4b0` → `670cf7fd`) ✓ |
| `unregister_netdevice: waiting` | 0 件 | **0 件** ✓ (= H1 仮説 negative continues) |

**全 6 項目で 063543 と一致** → 074509 のカーネルソース解析 (H1/H2/H4 仮説) で予測した「dpm_suspend 段 dpm_watchdog 無効化下での無音永久 loop」が再現された。

### Phase B-6: クリーンアップ (04:25-04:30 JST)

```bash
sudo rm -f /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
# vpn-watcher / cycle-watcher は reboot で既に削除済 (transient unit --collect)
```

期待 final 状態 (= 本セッション開始時と一致):

| 項目 | 期待 | 実測 |
|---|---|---|
| hooks | 50/60/70 の 3 個 | ✓ |
| transient units (vpn-watcher / cycle-watcher) | 全 inactive (reboot 消失) | ✓ |
| NM autoconnect (BT-PAN / GSNet) | 両方 no | ✓ |
| OpenWrt route-metric | -1 | ✓ |
| WiFi radio | enabled | ✓ |
| boot_id | `670cf7fd...` (hang reboot 後) | ✓ |
| suspend_stats | 0/0 (新 boot 開始) | ✓ |
| snapshot count | 180 pre / 179 post (= +20/+19) | ✓ |

設定面のクリーンアップ完了。dev 機 (akdx01) 側: 何も書き換えなし。

## 機序評価 (advisor 確定 framing)

### 何が確定したか (durable、二つの壁の議論と独立)

1. **Hang は独立再現された** = 063543 と完全に同 signature、本プロジェクト 2 件目の verified hang
2. **source-IP gate で 20/20 BT_PAN_VALID 確定** = WiFi 経由 VPN 混入は 0、真の N=20 valid trial set
3. **dpm_suspend 段 stall 機序が再確認**: `xfrm_policy=14 (半分)` + `Network is unreachable retransmit 3 回` + `PM: suspend entry` のみで exit 欠落 = 074509 カーネルソース解析の予測通り
4. **`unregister_netdevice: waiting` は依然 0 件** = H1 仮説 (xfrm dev ref leak) は negative continues、H2/H4 (bnep kthread non-freezable / btusb URB drain) のいずれかが残候補

### Candidate (d) (「ベースラインは ~0」説 =「物差し自体が信用できない、ハングはほぼ無いんじゃないか」という説) は更に弱まる

063543 の 3 hang を「外れ値」とする (d) を採用すると、本セッションの 1 hang も外れ値扱いになるが、二度独立に同 signature で再現したことで「ベースラインは ~0」説は維持困難。**(d) は更に explicitly downweighted**、bedrock は強化方向。

### Candidate (b) (WiFi-on protective) は **establish されない**

#### Binding constraint #1: statistical power (これが第一の壁)

0/30 (061553、WiFi-on) vs 1/20 (本セッション、WiFi-off) の比較:
- Fisher 正確検定: p ≈ 0.4 (= 同じ hang rate と仮定して全く矛盾なし)
- 共通低 rate (~2%) の null hypothesis 下で「0/30 then 1/20」joint probability ≈ 18% (= 18 回試したら 1 回起きる)
- 各 95% CI: 061553 = [0%, ~12%]、本セッション = [0.1%, ~25%] → **CI が完全に重なる**
- **N=1 hang では統計的に区別不能**。ping confound を完全に解消したとしても、現在のサンプルサイズでは「WiFi-on protective」は establish できない

これは ping confound と独立した binding constraint。次セッションが clean re-run で 1+ hang を再現しても **N をもっと増やす必要** がある (e.g., 30 valid + 60 valid 両側で repro)。

#### Binding constraint #2: ping confound (緩和された caveat)

ユーザ自認で「連続 ping は他セッションでもだいたいやっていた、ただし全部かは覚えていない」。**ping は本セッション固有ではなく、各セッション通底のノイズだった可能性**:

- (i) **直接検証は不可能**: h4-probe pre snapshot は process list (ps/pgrep) を capture していない → 061553 で実際に ping が走っていたか kernel 側証拠から確認できない
- (ii) **xfrm `oseq` パターンは非診断的**: 061553 と本セッション両方で `oseq ≈ 15/cycle` だが、これは:
  - 連続 ping (1/sec × 15s 程度) と整合
  - 但し **ambient GNOME traffic (avahi/mDNS, NM connectivity check, timesyncd, IPv6 ND, DNS) の ~1/sec floor** とも整合 — tunnel selector が `0.0.0.0/0` なので全 OS traffic が VPN を経由
  - oseq が cycle 期間 (5s〜95s) に対してほぼ一定 (15 packets) なのは 1/sec ping の signature とは矛盾 (本来 oseq は awake window 長さに比例するはず) → ambient の指紋に近い
  - = oseq は「ping が走っていた」とも「走っていなかった」とも言える非診断的データ
- (iii) **ユーザ記憶の不確実性**: 「だいたい」は「全部」ではない、061553 で実際に流していたか不明

**結論**: 「本セッション固有の contamination」という強い表現は不適切。但し「ping が共通だった」とも断定できない → 次セッションは **明示的に連続 ping 禁止** で confound を排除する必要

#### 弱い示唆 (proof ではない、framing としてのヒント): WiFi 共通項

(上記 binding constraint に従属する弱い signal として残置):

**(a) WiFi 共通項ヒント**:
- 063543: WiFi-off + 3 hang (ping 有無不明)
- 本セッション: WiFi-off + 1 hang (ping あり)
- 061553: WiFi-on + 0 hang (ping 有無不明)
- 共通: **WiFi-off は 2 つの hang セッションで共有、WiFi-on は唯一の clean セッションで共有**
- 但しユーザ自認で「ping は他セッションでもだいたい流していた」 = 当初書いた「連続 ping は本セッションだけ」という非対称性 argument は前提が崩れている。WiFi-on/off の共通項のみ残る
- N が小さく (063543 N=10, 本セッション N=20, 061553 N=30) statistical power 不足は Binding constraint #1 で既述

**(b) 連続 ping が hang を増やした構造的論理は弱い**:
- hang attempt cycle 20 の journal で「04:15:45 bnep teardown 完了 (172.20.10.13 disappeared)」が「04:15:51 PM: suspend entry」の **~6 秒前**
- ping は既に dead interface に erroring していた状態で suspend 突入 (= bnep が落ちた後の ping は kernel で immediately ENETUNREACH で reject、btusb 経由 URB は発行されない)
- 074509 H4 仮説の「extra in-flight URB が race 窓拡大」は **本 hang attempt には適用しにくい** (btusb URB は ping 由来ではすでに発行されていない)
- → 連続 ping が H4 経路で hang を増やした可能性は構造的に薄い (但し別経路で race を変えた可能性まで否定はできない)

### advisor 確定 one-liner (訂正版)

> WiFi-off + BT-PAN+VPN → 1 hang / 20 BT-PAN-valid cycle、063543 と同 signature。**hang 独立再現と candidate (d) 弱化は確実**。但し WiFi-protective 結論は (i) N=1 hang の statistical power 不足 + (ii) 連続 ping の confound 未解消 (ユーザ自認では他セッションも ping ありの可能性、ただし直接検証不可) の二つの壁で establish されない。次セッションは clean re-run (= 連続 ping 明示禁止 + N 拡大) で両方解消する必要。

### 0/30 と 1/20 の確率論的位置づけ

- 061553 (WiFi-on、ping 有無不明): 0/30 → hang rate point estimate ~0 (95% CI 上限 ~0.12 = 12%)
- 063543 (WiFi-off、ping 有無不明): 3/10 ≒ 30% (実装上の cell)
- 本セッション (WiFi-off + 連続 ping 確定): 1/20 = **5%** (95% CI [0.1%, 25%])

二つの WiFi-off セッション (063543 と本セッション) の hang rate (30% と 5%) の差は連続 ping の影響かもしれないし、統計的揺らぎ (N=10 vs N=20) かもしれないし、別の未観測 condition 差かもしれない。N が小さいので結論は出ない。

### 機序ラダーの位置づけ

074509 のカーネルソース解析で挙がった 3 仮説:
- **H1**: xfrm dev ref leak → `netdev_wait_allrefs` で stall。判別子 = `unregister_netdevice: waiting`。本セッション後も 0 件 = **H1 negative continues**
- **H2**: bnep_session kthread が non-freezable → freezing で stall。判別子 = `bnep_session` thread state。本セッションでは snapshot-only [PRE] で `kbnepd_session=NOT FOUND` 観察 = bnep teardown 完了後 = kthread もう存在しない → suspend 直前時点では H2 は適用しない
- **H4**: `btusb_suspend → usb_kill_anchored_urbs → urb.c:713` の URB drain timeout 無し → bulk_anchor で stall。本セッションは bnep 既に teardown 後 = bulk_anchor は空のはず (但し btusb はまだ ロード状態 refcount=0 + bluetooth 経由参照 44) → URB drain は他の経路 (= HCI command URB?) の可能性

→ **本 hang は H2/H4 のいずれにも 100% fit しない**。dpm_suspend のどこで stall したかを更に絞り込むには `DPM_WATCHDOG=y` の自前ビルドカーネル (= S4 段、機序ラダーの最終手段) が必要。次セッションは clean re-run (= 連続 ping 排除) で WiFi-off の hang 性質をまず確定し、その後 H1/H2/H4 lab の S4 段に進むか判断。

## 観測上の副次的発見 (運用知見・methodology)

### A. NM autoconnect=yes + WiFi metric 600 < BT-PAN metric 750 で VPN が WiFi 経由になる

Phase B-2 で観察。NM autoconnect=yes により BT-PAN + GSNet が自動 up したが、xfrm src=192.168.33.145 = WiFi IP = VPN が WiFi 経由で確立。原因:
- WiFi (OpenWrt) のデフォルト metric は 600 (= dhcp 取得時)
- BT-PAN (iMiminashiPadPro) のデフォルト metric は 750
- 600 < 750 で default route が WiFi 経由
- charon-nm が VPN initiate 時の source IP を default route から自動選択 → WiFi IP

含意: 061553 では `nmcli con modify OpenWrt ipv4.route-metric 800` で WiFi を downweight していた (本セッションは Phase B-3 で WiFi off にするため moot と判断)。本セッションのように WiFi-on の状態で VPN を BT-PAN 経由にしたい場合は metric 調整必須。

### B. WiFi off で ssh が完全切断 + dev 機からの状態回収は WiFi 復活後のみ

WiFi-off 中は dev 機 (akdx01) から実機 (macbookair2015.lan) への ssh 不可。実機側 transient unit (vpn-watcher, cycle-watcher) は自律動作するが、Claude は状態を観測不能。

含意: ユーザに口頭で進捗報告依頼。durable な evidence (= 永続ディスク上の `.pre`/`.post` ファイル、`journalctl --no-pager -b -1`) は WiFi 復活後に Claude が ssh で完全回収可能 → 本セッションでも hang 発生時刻 (04:15:50) を分単位で特定、cycle 20 journal で hang signature 完全分析を達成。

### C. hang reboot で /dev/shm + suspend_stats + transient units が全部消える (durable 観測の重要性)

- `/dev/shm/cycle-progress` (tmpfs) → reboot で消失 (本セッションでも実証)
- `/sys/power/suspend_stats/success` (per-boot 値) → 新 boot で 0 リセット
- `systemd-run --unit=... --collect` の transient unit → reboot で消失
- → 本セッション cycle 数推定は durable な `/var/log/h4-probe/*.pre` の epoch ベース集計で実施 (advisor が ExitPlanMode 前に指摘した方式が完璧に機能)

含意: 次セッション以降も hang 検出の ground truth は `/var/log/h4-probe/` の `.pre` (時刻順で sequence 化、`.post` が pair しない epoch = hang) + `60-s3-soak-log` SLEEP/WAKE ペア欠落、の二段構え。`/dev/shm` 系は便宜的監視のみと割り切る。

### D. 連続 ping background の扱い (当初「contamination」と framing したが事後 softening)

経緯:
1. ユーザは cycle 中 background で `ping 10.0.0.1` を流していた (= 各 cycle で VPN 疎通を目視確認するため)
2. 当初 advisor が「これは 061553 (連続 ping 無し) との二変数差分 = contamination」と framing した
3. 事後にユーザから「連続 ping は他セッション (061553 含む) でもだいたいやっていた、ただし必ず全部やっていたかは覚えていない」との情報
4. 直接検証を試みたが h4-probe pre snapshot は process list (ps/pgrep) を含まない → 061553 で実際に流していたか kernel 証拠から判定不能
5. xfrm `oseq=15/cycle` パターンは 061553 と本セッション両方で一致 — 連続 ping (1/sec) とも、ambient GNOME traffic (avahi/mDNS, NM connectivity, timesyncd 等の 0.0.0.0/0 tunnel 経由 ~1/sec floor) とも整合で **非診断的**

教訓:
- **次セッション以降は「連続 ping 明示禁止」**: 確実に confound を排除するため。VPN 疎通確認は wake 後の `ping -c 1` (one-shot) のみ
- **観測ツールに process list を追加すべき**: 70-h4-probe に `ps -eo pid,comm | head -30` or `pgrep -a ping` を追加すれば、次セッション以降は ping 有無を事後検証可能 (= 同種の framing 混乱を防止)
- **「contamination 確定」と言い切るには直接証拠が必要**: oseq 等の間接指標は ambient floor で薄まる、process list の方が確実

### E. h4-probe の `.pre` snapshot は本セッションで 3 役立った

1. **source-IP retro-classify** (Phase A): 041006/064608 を 5 分で bedrock 化
2. **本セッション 20 cycle の retro-classify** (Phase B): 全 cycle BT_PAN_VALID 確定 (WiFi 経由 0 件 = 「WiFi-off は機能していた」を実証)
3. **hang cycle 特定** (cycle 20): `.pre` だけ存在して `.post` が無い 1 cycle を時刻順 sequence で発見

設計時 (041006 セッション) 想定していた「H4 / xfrm 切り分け用 multi-purpose snapshot」が **過去 3 セッションで合計 4 回想定外の用途で活用** (200520 confound 発見、061553 WiFi 混入チェック、本セッション Phase A bedrock 化 + Phase B hang cycle 特定)。今後の hook 設計もこの方針継続。

### F. cycle 20 の VPN 再確立は 12 秒 (061553 と一致)

cycle 20 の wake (04:15:18) → 次の lid close (04:15:37) の間に vpn-watcher が VPN を再確立:
- 04:15:30: IKE_SA GSNet[22] established (= wake から ~12 秒で確立)
- 12 秒は 061553 の T_reconnect 観察と完全一致 → vpn-watcher の動作は安定して predictable

### G. 連続 ping は bnep teardown 完了後 ~6 秒 erroring で済んでいた

cycle 20 の hang attempt journal で:
- 04:15:45: 172.20.10.13 disappeared from enx98e0d98d205e (= bnep teardown)
- 04:15:51: PM: suspend entry
- 中間 ~6 秒で連続 ping は kernel から `ENETUNREACH` で reject されていた (btusb URB は発行されない)

含意: 連続 ping が「btusb URB を race 窓拡大」(074509 H4 仮説) する論理は構造的に薄い → 本 hang を H4 frame に当てはめる試みは慎重に (本セッションの hang は H4 とは異なる経路で起きた可能性が高い)。

### H. Cycle 19 (完走) と Cycle 20 (hang) の pre snapshot は state-level で identical = timing race の証拠

cycle 19 (04:14:53) と cycle 20 (04:15:50) の 70-h4-probe pre snapshot を比較した結果、観測 state は全く同一:

| 項目 | cycle 19 (完走) | cycle 20 (HANG) |
|---|---|---|
| wlp3s0 link state | DOWN | DOWN (同じ) |
| btusb refcount | 0 | 0 (同じ) |
| wl refcount | 0 | 0 (同じ) |
| bluetooth refcount | 44 (btrtl,btmtk,btintel,btbcm,bnep,btusb,rfcomm) | 44 (同じ) |
| xfrm state count (snapshot-only PRE) | 2 | 2 (同じ) |
| xfrm policy count (snapshot-only PRE) | 14 | 14 (同じ) |
| bnep_netdev | MISSING (= teardown 完了後) | MISSING (同じ) |
| kbnepd_session | NOT FOUND | NOT FOUND (同じ) |

含意: **hang は predictable な state 差ではなく、timing/race で起きた**。observable な state は両 cycle で identical → hang を観測ベースの state 差から予測することは構造的に不可能 = 074509 で予測した dpm_suspend 段の race condition と整合。dmesg-watchdog 系の動的観測 (= S4 自前ビルドカーネル) が必要なゆえん。

### I. WiFi-off 後も wlp3s0 device の rx/tx counter は保持されている

cycle 19 と cycle 20 両方の pre snapshot の `/proc/net/dev` で wlp3s0 が同一の counter を示す:
```
wlp3s0: 29170056  182425  ...  31367872  176266  ...
```

含意:
- WiFi-off (`nmcli radio wifi off`) は soft rfkill のみで wl ドライバはロード状態のまま (= 計画段階で advisor が指摘した「wl が dpm_suspend chain に居続ける」と整合)
- WiFi-off 後の wlp3s0 link は DOWN だが、kernel 内部の device 構造体は維持され、counter も保持される
- → cycle 19→20 の間に wlp3s0 経由で traffic は流れていない (counter 不変)
- → 本セッション WiFi-off は機能していた (= advisor の懸念のうち「実は WiFi 経由で何か流れていた」は否定)
- 但し「wl が dpm_suspend chain に居ること自体」が hang 決定因かどうかは別問題で、`modprobe -r wl` 実験が必要 (= 次セッション以降の優先事項 (ii))

### J. lsmod refcount: btusb=0 だが bluetooth=44 で間接保持

cycle 20 hang attempt 時の lsmod:
```
btusb       81920  0
btrtl       32768  1 btusb
btbcm       24576  1 btusb
btmtk       32768  1 btusb
btintel     69632  1 btusb
wl        6459392  0
bluetooth 1093632  44 btrtl,btmtk,btintel,btbcm,bnep,btusb,rfcomm
```

含意:
- btusb の直接 refcount=0 (= 「使われていない」) だが、bluetooth サブシステム経由で refcount=44 (= 大量の参照、`bnep,btusb,rfcomm` 等が見える)
- = btusb device は依然 dpm_suspend chain に登録されており、`btusb_suspend` が呼ばれる経路は維持されている
- 074509 H4 仮説 (`btusb_suspend` → `usb_kill_anchored_urbs`) は本 hang attempt でも path-on (= 仮説経路は依然 alive)
- 但し bnep が既に teardown された状態 (snapshot-only PRE で `bnep_netdev=MISSING, kbnepd_session=NOT FOUND`) なので、bulk_anchor の URB queue は空のはず → URB drain が timeout で stall する直接的な引き金は見えない (= H4 が本 hang を完全説明できる根拠は弱い)

### K. NM teardown は 5 秒、その後 1 秒で PM suspend entry の tight timing window

cycle 20 hang attempt journal で:
- 04:15:37: Lid closed
- 04:15:45: Suspending... + NM teardown 開始 (8 秒の delay = systemd-logind の inhibitor lock + ユーザ session freeze)
- 04:15:45-50: NM teardown 進行 (5 秒、wlp3s0 unmanaged、BT-PAN deactivating → disconnected、bnep teardown、charon-nm IKE_SA delete 試行 + retransmit ×3)
- 04:15:50: Reached target sleep.target
- 04:15:50: systemd-suspend.service start
- 04:15:50: kbd-backlight-sleep + 58-snapshot-only PRE + 70-h4-probe PRE
- 04:15:51: PM: suspend entry (s2idle)

含意:
- NM teardown は **5 秒** で完了 (= NM 側は速い、bnep/xfrm/charon-nm を順次解体)
- sleep.target 到達後 system-sleep フック実行から PM suspend entry までは **1 秒** (= フック処理は速い)
- 「lid close → suspend 突入」全体で 14 秒 (lid close から PM suspend entry まで) で、その間に NM teardown が一通り完走
- この timing で 19 cycle 連続成功した後の 20 cycle 目で hang = **timing window のジッタが race condition のトリガー** との見方と整合
- 064608 report で観察された `device-suspend 所要時間 = 390-498 msec` (= 1 cycle あたり) は本セッションでも同じはず (但し hang cycle はそれが完了しなかった)

### L. `bluetooth hci0:12 enx98e0d98d205e: renamed from bnep0 (while UP)` が wake ごとに recurring

cycle 19 と cycle 20 両方の dmesg tail で観察:
- cycle 19 pre snapshot dmesg tail: `[木  7月  2 01:16:40 2026] bluetooth hci0:12 enx98e0d98d205e: renamed from bnep0 (while UP)`
- cycle 20 pre snapshot dmesg tail: `[木  7月  2 01:17:58 2026] bluetooth hci0:12 enx98e0d98d205e: renamed from bnep0 (while UP)`

(注: dmesg のタイムスタンプは uptime ベース = 01:16:40 等は「起動からの相対時刻」、JST 03:46+1:16 = 06:02 系ではなく、PM:suspend で時計が止まる + 弱い skew で本来のリアルタイムから乖離する。)

含意:
- 各 wake で BT-PAN netdev が `bnep0 → enx98e0d98d205e` に rename される現象が、**直接観察できた cycle 19 と cycle 20 で確認** (各 pre snapshot の dmesg tail) + 064608 でも同パターン観察 → 毎 cycle 構造的に発生していると推定
- これは udev/networkd の persistent-naming rules が wake 後の bnep up に対して USB MAC ベースの altname を当てる動作で、NM の autoconnect=yes と vpn-watcher の働きで cycle が回るたびに発生
- 各 cycle で BT-PAN device が一度 die → re-attach する流れが構造的に組み込まれている (= 074509 H1 仮説の「xfrm dev ref leak → netdev_wait_allrefs」が起きるとすれば、この毎-cycle rename がトリガーになる可能性) → 但し本セッションでも `unregister_netdevice: waiting` は 0 件で H1 は negative continues

### M. cycle 20 は IKE_SA[22] = 22 回目の IKE 確立 (Phase B-2 setup の 2 回が加算)

cycle 20 で IKE_SA は `GSNet[22]` として確立されていた:
```
04:15:30 charon-nm: IKE_SA GSNet[22] established between 172.20.10.13[macbookair2015]...160.16.210.47[160.16.210.47]
```

cycle 駆動は 20 回なので 20 個の IKE_SA で済むはずだが、22 個になっていた。差分の 2 個は Phase B-2 段階で発生したと推定 (cycle 1 の IKE_SA 番号を journal で直接確認していないため ±1 の誤差は残る):
- 候補 1: Phase B-2 で autoconnect=yes により最初に確立された **WiFi 経由 VPN** (xfrm src=192.168.33.145)、Claude が `nmcli con down GSNet` した時点で deleted
- 候補 2: vpn-watcher が再 activate した時の試行 (BT-PAN 経由 or WiFi 経由かは未確定、autoconnect/vpn-watcher の race で複数回試行された可能性)
- いずれにせよ Phase B-4 cycle 1〜20 で各 wake 時に IKE_SA 確立 (= 20 個) → 累計 22 個

含意:
- charon-nm は 22 回の IKE_SA 確立を全て成功させた (= charon-nm 側に hang 要因なし、本 hang は kernel device-suspend chain で発生)
- IKE_SA delete 試行 (各 suspend 前) で `Network is unreachable` retransmit が起きるパターンも本セッションで再確認 (cycle 1 vs cycle 20、030349 と整合)
- 「VPN 確立は問題なし、teardown 経路に race の温床あり」が裏付けられる

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| ~03:43-03:45 | **Phase A** (Phase B より先に実施) | 041006 22/22 BT_PAN_VALID + 064608 13 BT_PAN_VALID + 12 inactive + WiFi 経由 0 確定 |
| ~03:45-03:46 | Phase B-0 | baseline 確認 (boot_id `fcc3d4b0...`, suspend_stats 221/0, hooks 3 個, autoconnect 両方 no, mode=beta) |
| ~03:46-03:47 | Phase B-1 | 58-snapshot-only hook 投入 + vpn-watcher/cycle-watcher 起動 (cycle-watcher start `03:46:22`) + autoconnect=yes 設定 |
| 03:47-03:48 | Phase B-2 | iPad テザリング ON, BT-PAN/GSNet 自動 up, **xfrm src=192.168.33.145 = WiFi 経由 VPN 発覚** (route metric 順 WiFi 600 < BT-PAN 750) |
| ~03:48 | Phase B-3 | `nmcli con down OpenWrt && nmcli radio wifi off` → **ssh 切断** |
| 03:58-04:15 | Phase B-4 | ユーザ手動 lid close + 電源ボタン wake で 20 cycle 駆動 (= 19 完走 + cycle 20 で hang) |
| 04:15:50 | **HANG 発生** | cycle 20、journal `PM: suspend entry (s2idle)` が最終、`PM: suspend exit` 欠落 = dpm_suspend stall (= 063543 と同 signature) |
| ~04:15-04:18 | hang reboot | ユーザが強制電源断 → reboot → 手動で `nmcli radio wifi on` で WiFi 復活 |
| 04:25-04:30 | Phase B-5 + B-6 | Claude が ssh 復活、durable evidence で 20 cycle 集計 + hang signature 解析、Phase B-6 cleanup |
| 04:30 | advisor 諮問 + レポート作成 | 「WiFi-protective は二つの壁 (statistical power + ping confound) で establish 不可、durable headline (hang 独立再現 + candidate (d) 弱化) は ping 議論と独立に残る」framing 確定、本レポート作成 |

注: Phase A の正確な時刻は記録していないが、Phase B-0 baseline 確認の前に sequentially 実行 (Claude は単一 agent で並列実行不可)。

実験全体所要時間: 約 1 時間 (Phase B-4 で hang 発生で早期中断 → 想定 80-100 分から短縮)。

## 検討して除外した事項

- **bt-pan-keepalive を投入する案**: ExitPlanMode 前に advisor が「second-variable change になり one-variable-back が崩れる」と flag → drop して 061553 と同じ「on-demand のみ」運用とした。**但しユーザ自身が善意で連続 ping を background で走らせていた** (advisor 当初は「本セッション固有の汚染」と判断したが、事後ユーザ自認で「他セッションも同様の可能性あり」、framing は softening → 副次的発見 D 参照)。次セッションでは「ユーザの連続 ping も明示的に禁止 + 70-h4-probe に process list 追加で事後検証可能化」を事前案内
- **`modprobe -r wl` まで踏み込む WiFi off**: ExitPlanMode 前に advisor が「063543 と同じ soft rfkill レベル (= `nmcli radio wifi off`) で揃える、`modprobe -r wl` は別実験」と判断 → 本セッションでは soft rfkill のみ実施。「wl が dpm_suspend chain に居ること自体」が決定因かは別途検証必要
- **WiFi metric を 800 に変更してから WiFi-off**: Phase B-2 で WiFi 経由 VPN 発覚した時の対応として metric=800 設定案もあったが、Phase B-3 で WiFi-off にするため moot と判断、そのまま進めた (結果的に WiFi 経由でも一旦 active だった瞬間が ~30 秒間あるが、Phase B-4 cycle 駆動中は全 cycle BT-PAN-valid で問題なし)

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-07-01 04:30 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット (本セッションでも source-IP gate + hang cycle 特定で必須) |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで pre +20 / post +19 = 累計 180 pre / 179 post) | 本セッション 20 cycle の証拠 + 将来 retro-classify 素材 |
| vpn-watcher.service | **削除済** (reboot で消失) | VPN reconnect 自動化 |
| cycle-watcher.service | **削除済** (同上) | 進捗監視 |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt route-metric | -1 (未変更、本セッションでは触らず) | |
| WiFi radio | enabled (hang reboot 後にユーザが `nmcli radio wifi on` で手動復活) | |

実機の suspend_stats: success 0, fail 0 (新 boot 開始時 = 04:18 JST)。boot_id `670cf7fd-ad6d-4f42-90c8-0d8f359099e2` (本セッション hang reboot で変化、起動時刻 2026-07-01 04:18 JST)。

dev 機 (akdx01) 側: 何も書き換えなし。`src/linux-6.12.y` 等の clone は前セッションから残置。

## 次セッション引継ぎ

### メモリ更新内容 (本セッション終了時)

- `s2idle-btvpn-hang-mechanism-ladder`: 全面改訂
  - 「過去セッションの valid 性」表に 041006 (22/22 BT_PAN_VALID 確定) + 064608 (13 + 12 inactive 確定) + 本セッション (20/20 BT_PAN_VALID, 1 hang) を反映
  - 「本セッション (2026-07-01) 結果」セクションを追加
  - 「次の手」リストを「clean re-run (WiFi-off + on-demand only)」を最優先に更新
  - 「連続 ping background は confound 源、次セッション以降は明示的禁止 + 70-h4-probe に process list 追加で事後検証可能化」を How to apply 節に明記 (当初の「contamination 確定」表現はユーザ事後申告で softening)
- `MEMORY.md`: index の description を本セッション結果に合わせて訂正

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
echo "=== boot_id (期待: 670cf7fd... = 本セッション hang reboot 後) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats (新 boot で 0 開始) ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting"
echo "=== transient units 残存していないか ==="
systemctl is-active vpn-watcher.service cycle-watcher.service 2>&1
'
```

### 推奨の次の手 (優先順位順)

#### (i) **WiFi-off で 30+ valid cycle (clean re-run = 連続 ping 明示禁止 + statistical power 拡大)** (最優先、~80-150 分)

本セッションの二つの壁 (statistical power + ping confound) の両方を解消する clean version。設計:
- WiFi-off (本セッションと同じ、`nmcli radio wifi off`)
- iPad + 70/58 hook + vpn-watcher 維持
- **連続 ping を明示的に禁止** (ユーザ verification は wake 後の `ping -c 1 10.0.0.1` のみ、background ping は事前案内で禁止)
- **70-h4-probe に process list (ps/pgrep) を追加**: 事後検証で「ping が実際に走っていなかった」を直接確認可能にする
- 30 cycle 駆動 + 1+ hang なら 60 cycle まで延長 (= statistical power 確保)
- 結果:
  - **30 cycle で 1+ hang 再現** → 60 cycle まで延長して再現性確認 → 「WiFi-off は連続 ping 無しでも hang を出す」確定 → **candidate (b) 強化**
  - **30/30 clean** → 連続 ping が load-bearing だった可能性 or 偶然 (statistical power 不足) — 追加検証必要

#### (ii) **`modprobe -r wl` まで踏み込む実験** (advanced、~80-100 分)

candidate (b) を更に sharp に discriminate。soft rfkill (= `nmcli radio wifi off`) では wl モジュールがロード状態のまま dpm_suspend chain に参加するため、本セッションで 1 hang 出た部分が「wl-in-chain」由来か「WiFi-radio-off」由来かは区別不能。`sudo modprobe -r wl` で完全に外して 30 valid cycle 駆動すれば三変数目の discriminate になる。但し再 modprobe (lsmod 復元) の手間と broadcom-sta の機能確認が必要。

#### (iii) 064608 の cycle 13 (= post 時刻 06:40:43 直前) と本セッション cycle 20 の dmesg 比較 (~30 分)

両セッションとも cycle 駆動の最後 (= hang or 完走最終) の `.pre` snapshot に dmesg tail 300 を含む。比較で「hang 直前と完走最終の dmesg 差」を観察できる可能性。

#### (iv) S4 (DPM_WATCHDOG カーネル) (~1-2 日、機序未確定時の最終手段)

dpm_suspend のどこで stall したかを特定するには dpm_watchdog を有効化した自前ビルドカーネルが必要。064608 で advisor が指摘した経路で実施。

### 注意事項

- **次セッション開始時にユーザに事前案内**: 「cycle 駆動中の background ping は禁止 (= confound 排除)。VPN 疎通確認は wake 後の `ping -c 1 10.0.0.1` のみ」 — また、過去セッション (061553 等) でも background ping を流していた可能性があることをユーザが事後申告した点も明示的に共有
- **70-h4-probe に process list を追加推奨**: `ps -eo pid,comm | head -30` か `pgrep -a ping` を追加すれば、次セッション以降は ping 有無を kernel snapshot から直接確認可能。本セッションの framing 混乱 (= 事後 ping 有無の verifiability 欠如) を構造的に防止
- **本セッション 1 hang は durable headline**: 候補 (d) を弱める材料として bedrock を強化する方向、独立した hang 観測として今後も参照可能 (この結論は ping confound と独立)
- **candidate (b) は establish されていない**: 二つの壁 (statistical power N=1 不足 + ping confound 未解消) が両方残っている。clean re-run (= 連続 ping 明示禁止 + N≥30 で 1+ hang 再現確認) で初めて言及可能
- **063543 は依然 bedrock**: per-cell active verification あり + ユーザ実体験 corroborate あり + 本セッション独立再現で更に強化、機序検討の前提として維持
- **次セッションでも source-IP retro-classify は必須**: state count gate ベースの判定だけでは WiFi 経由 VPN を valid と誤判定するリスクは恒常的に存在 (061553 で実証、本セッションでも Phase A で検証手順を確立)
- **`/var/log/h4-probe/` の累積管理**: 累計 180 pre + 179 post = 359 ファイル (各 ~58KB) ≒ 20MB。1 ヶ月積み増しすると 60MB+ で disk 圧迫の可能性。logrotate or 月次手動削除を次セッションで検討

## 関連レポート

- [2026-06-30_061553 セッション: 30/30 BT-PAN-valid clean (本セッションの起点 = one-variable-back の対象)](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md)
- [2026-06-30_030349 セッション: S3'' 30 cycle / cycle 1 のみ valid confound (source-IP gate 必須性を最初に示唆)](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md)
- [2026-06-29_200520 セッション: S3 (bnep teardown) 32 cycle / cycle 1 のみ valid confound](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md)
- [2026-06-29_064608 セッション: driver path 25 cycle / 13 valid (source-IP retro-classify 結果)](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md)
- [2026-06-29_041006 セッション: S1 (btusb pre-unload) 22 cycle / 22 fully valid (source-IP retro-classify 確定)](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説 (本セッション cycle 20 hang signature と完全一致)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang (本セッション hang と同 signature の bedrock、依然有効)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
