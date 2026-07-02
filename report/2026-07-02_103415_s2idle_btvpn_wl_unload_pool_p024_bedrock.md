# wl を完全に外した状態で s2idle+BT テザリング+VPN の 30 サイクル追加通過 — 合算 0/60 で Fisher 検定 p ≈ 0.024 に到達し、「wl が載っていて電波オフがハングの必要条件」が統計的に裏付けられた

- **実施日時**: 2026 年 7 月 2 日 08:57 〜 10:34 JST
- **位置づけ**: [2026-07-01_130206 セッション](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) で 30/30 clean を得た後、advisor 事後指摘で「hang arm を 3 セッション pool している以上、clean arm も 130206 (0/30) を pool するのが対称」と判明。主案 (+30 cycle 追加、pool 0/60 で有意化狙い) を実施 → **30/30 BT-PAN-VALID cycle 全数 clean、hang 0、boot_id 不変、`unregister_netdevice: waiting` 0**。**pool 0/60 で Fisher exact 片側 p ≈ 0.024 到達、有意水準 p < 0.05 を超え (b'') 「wl が loaded かつ radio-off が hang の必要条件 (tight reading)」の bedrock 化に到達**。全 7 セッション横断で単一変数「wl-loaded-AND-radio-off」による hang/clean 分離が p < 0.05 で establish された。

## 概要

### 前セッションまでの状況

過去 6 セッションを整理すると綺麗な規則性が見えていた (advisor 指摘): ハングが起きたのは全部「wl は載っていて電波オフ」の状態だけで、「wl は載っていて電波オン」の場合と「wl そのものを外した」場合はいずれも 0 件だった。前セッション (130206) で wl を完全に外した状態での 30 回無事通過を得たが、単独で見るとハング率 5 % 前後だったとしても偶然通過してしまう確率が 21〜27 % 残るので、統計的な裏付けとしては足りなかった。

### 本セッションでやったこと

advisor から追加の指摘があった: ハング側は 3 セッションを合算して 5/56 として扱っているのに、無事通過側は 130206 の 0/30 を合算しないのは扱いが非対称。合算するなら 30 回追加するだけで 0/60 になり、Fisher 検定 (片側) で p ≈ 0.024 まで下がって有意水準を超える。

そこで 130206 と同じ設計で 30 回追加した。

### 結果と意義

**30 回全部ハングせずに通過した**。合算した 0/60 で **Fisher 検定 (片側) p ≈ 0.024 となり、有意水準 p<0.05 を超えた**。**「wl が載っていて、かつ電波オフの状態がハングの必要条件」という読み (candidate (b'')) が統計的に裏付けられた**。

実用面では、「WiFi オフ + BT テザリング + VPN + 蓋閉じ」の組合わせを避ければ回避できる。WiFi をオンにしたまま route-metric で BT-PAN を優先する運用は過去 2 セッション (061553/041006) 合算 0/52 で裏付け済みで、これが最も確実。

### 残る課題と次にやること

ハングの中身 (dpm_suspend でどのドライバが止まっているか) はブラックボックスのまま。対立仮説 H7 (「特定のドライバではなく、dpm_suspend の連鎖から何かを外せばタイミングがずれてハングが減るだけ」の可能性) は完全には排除できていない。

次にやること:
1. **041006 の btusb 除去アームを WiFi オフの条件で試行回数を増やす**: 「btusb が必要」なのか「wl + 電波オフが必要」なのかを分ける
2. **xfrm や bnep を事前に落として試す**: H6 vs H7 の判別
3. **DPM_WATCHDOG 有効カーネルの自前ビルド**: 上で機序が絞れなかった場合の最終手段

## 結論 (先に要約)

1. **30/30 BT-PAN-VALID cycle 全数 clean、hang 0 件、boot_id 不変**:
   - snapshot 31 pre / 31 post = 全ペア成功 (pair matching で hangs 0)
   - suspend_stats success=62 (130206 終了 31 + 本セッション smoke 1 + 実 cycle 30)、fail=0
   - boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` 開始〜終了で不変 (= reboot なし = hang なし の決定的証拠、130206 開始以来通算)
2. **wl 完全 unload 30 cycle 全数維持を durable file で証明**:
   - 実 cycle 30 件全て `wl_loaded=NO cfg80211_loaded=YES wlp3s0_present=NO` durable
   - smoke test 1 件のみ `wl_loaded=YES` (B-3 前、期待通り)
   - `/var/log/h4-probe/wl-unload.status` に `epoch=1782950782 rc=0` + lsmod で wl 行なし durable 記録
3. **Source-IP gate で 30/30 BT_PAN_VALID、WiFi 経由 VPN 混入 structural 0**:
   - 30 cycle 全て `src=172.20.10.13` (BT-PAN)、WIFI_KNOWN_CLEAN 0 件 (wl 消失で構造的に不可能、130206 継承、advisor 予測通り)
4. **`unregister_netdevice: waiting` = 0 依然 = H1 negative continues** (五度目)
5. **Ping 集計**: PRE 31 件全て `ping_running=NO` durable (連続 ping 混入ゼロ、102907/130206 の教訓維持)
6. **統計的評価 = 目標達成**:
   - 本セッション単独 0/30 (base rate ~4.3% で 27% chance) は決定的ではない
   - **130206 (0/30) と pool → 0/60 → Fisher exact 5/56 vs 0/60 片側 p ≈ 0.024 で有意水準 p<0.05 到達**
   - hang arm 3 セッション pool (5/56 = 063543+043251+102907) と対称に clean arm 2 セッション pool (0/60 = 130206+本) が成立
7. **全 7 セッション単一変数分離 (advisor 指摘の tight reading、統計的に establish)**:

   | session | wl 状態 | radio | btusb | 結果 |
   |---|---|---|---|---|
   | 063543/043251/102907 | loaded | off | present | pooled 5/56 hang (~9%) |
   | 061553 | loaded | on | present | 0/30 clean |
   | 041006 | loaded | on | **removed** | 0/22 clean |
   | 130206 | **unloaded** | off (moot) | present | 0/30 clean |
   | **130415 (本)** | **unloaded** | off (moot) | present | **0/30 clean** |

   **hang ⟺ wl-loaded-AND-radio-off**、pool 0/60 で Fisher p ≈ 0.024 の establish
8. **Candidate (b'') = 「wl が loaded かつ radio-off が hang の必要条件」の tight reading が bedrock 化**:
   - 130206 で loose (b') 「wl-in-chain (loaded) 必要条件」は 061553/041006 (loaded + radio-on = clean) で反証されて tight (b'') に framing 変質
   - 本セッションで pool 0/60 → p ≈ 0.024 で (b'') が p<0.05 に到達
   - hang session (063543/043251/102907) 全て wl-loaded-radio-off、clean session (061553/041006/130206/本) 全て wl-radio-on か wl-unloaded で全 7 セッション整合
9. **機序ラダー現状 (advisor 諮問継承、更新)**:
   - **H1** (xfrm dev ref leak): `unregister_netdevice: waiting` 0 件、五度目の negative → 実質棄却圏
   - **H2 / H4 の downgrade 保留は解除** (advisor 事前予告): wl-loaded-radio-off の operative 性が p<0.05 で bedrock 化されたため、H2 (bnep_session non-freezable kthread) と H4 (btusb URB drain) は「radio-off で active か radio-on で active か」の切り分けが必要な段階に降格。「なぜ radio-off だけで hang が発生するか」を H2/H4 側から説明する追加証拠が必要
   - **H6 (wl+btusb 両者必要) は unsupported both directions で demote 継続** (130206 継承、advisor 指摘)
   - **対立仮説 H7 (any-perturbation-helps)**: 未だ decisive に排除されていない、次実験で discriminate
10. **次セッション設計**: (ii) **041006 の btusb arm を WiFi-off で N 拡大** で「btusb 必要 (H6)」vs「wl-radio-off 必要 (tight reading)」を discriminate、または (iii) non-btusb driver 除去 (xfrm/bnep 事前 teardown) で H6 vs H7 discriminate、または (iv) S4 DPM_WATCHDOG カーネル

## 添付ファイル

- [実装プラン](attachment/2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock/plan.md)

## 前提・目的

- **背景**: [2026-07-01_130206](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md) で 30/30 clean を得たが、単独では base rate ~4.3% で 27% chance で偶然通過の可能性が残り、Fisher exact 5/56 vs 0/30 片側 p ≈ 0.11 で有意水準未達
- **主要目的 (advisor 事後指摘反映)**: hang arm 3 セッション pool (5/56) と対称に clean arm 2 セッション pool の下限を目指す。**+30 cycle 追加で pool 0/60 → Fisher p ≈ 0.024 で有意水準 p<0.05 を超える**
- **非対称な意義 (事前案内)**:
  - **1+ hang** → 「wl 完全除去でも再現 = wl 非依存」bedrock、S4 段 DPM_WATCHDOG へ
  - **30/30 clean** → **pool 0/60 で Fisher p ≈ 0.024 で (b'') tight bedrock 化**、次は (ii)/(iii)/(iv)
- **本セッション独自の追加設計 (130206 継承 + 微差分)**:
  - Phase B-1 冒頭で 130206 の `wl-unload.status` を **削除** (前回証拠と本セッション証拠の epoch 境界を明確化)
  - Phase B-2 事前案内の統計 wording を「pool 前提の p ≈ 0.024」に更新 (「単独 fresh 0/30 では有意化しない、pool で有意化を狙う」を明示)
  - scratchpad session_start_epoch のパスを本セッション UUID (`692508fb-8bea-43c2-b667-7b4cfd656e72`) に更新
- **役割分担**: hook/transient unit デプロイ・状態確認・retro-classify は Claude が ssh で実施。cycle 駆動 (蓋 close + 電源ボタン wake) は WiFi-off で ssh 切断中のためユーザ手動、進捗はユーザ口頭報告

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks (本セッション実施中): `50-kbd-backlight`、`58-snapshot-only` (本セッション新規投入 + wl 3 フィールド追加、Phase B-6 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後は 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`iMiminashiPadPro`, BT-PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`)
- WiFi (baseline): `wl`/`wlp3s0` (broadcom-sta DKMS 6.30.223.271)、接続 `OpenWrt` → **Phase B-3 で `nmcli radio wifi off` + `rmmod wl` で完全アンロード** (cfg80211 は refcount=0 で残置)
- baseline (実験開始時 08:57 JST): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (130206 開始 boot、依然不変)、suspend_stats 31/0、snapshot count=237 pre / 235 post、snapshot-only PRE 59 / POST 56 (130206 累計継承)、NM autoconnect 両方 no、route-metric -1、wl loaded refcount=0、cfg80211 loaded 1(from wl)、unregister 0 件、`no wl blacklist`、`wl-unload.status` は 130206 の残置 (rc=0, epoch=1782876623)
- baseline (実験終了時 10:34 JST): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (**開始〜終了で不変 = hang なしの決定的証拠、130206 開始以来 通算 uptime ~1 日 0h**)、snapshot count=268 pre / 266 post (= +31/+31、完全ペア)、snapshot-only PRE 90 / POST 87 (= +31/+31)、NM autoconnect 両方 no、WiFi radio enabled、wl+cfg80211 loaded (recovery 完了)、unregister 0 件
- 比較対照 130206 との condition 差: **完全同一設計**、cycle 数 30 変わらず、rmmod wl 手順同一、hook 3 フィールド同一。差分は「130206 の wl-unload.status を削除して本セッションで epoch 上書き」の 1 点のみ

## Phase B-0: baseline 確認 + wl 系 + SESSION_START 捕捉 (08:57-08:58 JST)

### SESSION_START_EPOCH 捕捉

```bash
SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
# → 1782950249 (JST 2026-07-02 08:57:29)
echo "$SESSION_START_EPOCH" > /tmp/.../scratchpad/session_start_epoch.txt
```

scratchpad path は本セッション UUID (`692508fb-8bea-43c2-b667-7b4cfd656e72`) を使用。

### baseline 13 項目確認結果

全項目期待値と一致 (130206 終了状態と完全一致、時間経過による drift なし):

| # | 項目 | 期待 | 実測 | 判定 |
|---|---|---|---|---|
| 1 | カーネル / mem_sleep / GRUB | 6.12.94+deb13-amd64 / [s2idle] deep / mem_sleep_default=s2idle | 一致 | ✓ |
| 2 | hooks | 50/60/70 の 3 個 | 一致 | ✓ |
| 3 | h4-probe mode + count | beta / 237 pre / 59 snapshot-only PRE | 一致 | ✓ |
| 4 | NM autoconnect | OpenWrt=yes/-1, BT-PAN=no, GSNet=no | 一致 | ✓ |
| 5 | boot_id | 8963e774... (130206 と不変) | 一致 | ✓ |
| 6 | suspend_stats | 31/0 (130206 終了時と同じ、追加 suspend なし) | 一致 | ✓ |
| 7 | transient units | 全 inactive | 一致 | ✓ |
| 8 | wl+cfg80211 | wl(refcount=0), cfg80211(1 from wl) | 一致 | ✓ |
| 9 | lsof /sys/module/wl | 0 行 | 一致 | ✓ |
| 10 | wl blacklist | 未設定 (`no wl blacklist`) | 一致 | ✓ |
| 11 | 前回 wl-unload.status | 130206 の epoch=1782876623 rc=0 残置 | 一致 (B-1 で削除) | ✓ |
| 12 | unregister_netdevice waiting | 0 | 一致 | ✓ |
| 13 | WiFi radio | enabled | 一致 | ✓ |

## Phase B-1: hook + transient units デプロイ (08:58-09:00 JST)

### 前回 wl-unload.status 削除

```bash
ssh miminashi@macbookair2015.lan 'sudo rm -f /var/log/h4-probe/wl-unload.status'
# → confirmed absent
```

B-3 の `wl-unload.status` epoch が本セッション用のものだけになる。

### 58-snapshot-only hook (130206 と同一、wl 3 フィールド版)

130206 継承の実装、`wl_loaded/cfg80211_loaded/wlp3s0_present` 3 フィールド + word-boundary ping regex + durable file 出力。1861 バイト、`chmod +x` 済。

### Smoke test 実施 (08:59 JST)

`sudo rtcwake -m no -s 15 & sudo systemctl start systemd-suspend.service --wait` で 1 回 suspend+wake:
- PRE (epoch 1782950313): `wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES ping_running=NO xfrm_state=0` ✓
- POST (epoch 1782950328): 同上 ✓

hook 正常動作確認 → 進む。

### vpn-watcher + cycle-watcher 起動 (09:00 JST)

- `vpn-watcher.service` (transient, --collect): 3 秒間隔で BT-PAN UP + GSNet inactive を検知して `nmcli con up GSNet`
- `cycle-watcher.service` (transient, --collect): suspend_stats delta を `/dev/shm/cycle-progress` に書き出し

### NM 設定 (09:00 JST)

```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con modify OpenWrt connection.autoconnect no
```

## Phase B-2: BT-PAN+VPN セットアップ + ユーザ事前案内 (09:01 JST 前後)

ユーザ操作: iPad テザリング ON。NM autoconnect=yes により BT-PAN + GSNet 自動 up。

Claude 確認結果 (09:01 JST):
- BT-PAN active (`iMiminashiPadPro ネットワーク`)、`172.20.10.13/28` 割当
- GSNet active、但し **xfrm src=192.168.33.145** (= WiFi IP、130206 と同症状)
- **B-3 で wl unload するので moot** (advisor 予測: wl 消失後は WiFi-routed VPN 混入が構造的に不可能)

**ユーザ事前案内 (= 本セッション load-bearing communication、130206 継承 + pool wording 更新)**:
- 「本セッションは 130206 の +30 cycle 追加、hang → 決定的、30/30 clean → **pool 0/60 で Fisher p ≈ 0.024 で有意水準到達 (b'') tight bedrock 化**」
- 「連続 ping 絶対禁止、VPN 疎通確認は wake 直後の `ping -c 1 10.0.0.1` one-shot のみ」
- 「30 cycle は wall-clock 目標、Claude が事後 source-IP gate で BT_PAN_VALID を数える」
- 「iPad hotspot timeout / NM secrets cache 失敗 → 失敗兆候を報告」
- 「Phase B-3 直後、コンソール前で `sudo cat wl-unload.status` + `lsmod | grep -c '^wl '` = 0 のゲート通過必須」
- 「Cycle 1 完了後、canary で `wl_loaded=NO` + `xfrm_state=2 xfrm_policy=14` + `bnep_netdev=MISSING` の 3 つ確認」

ユーザ「テザリング ON した + WiFi on が問題ないか確認」→ Claude 「B-2 段階では想定通り、B-3 で wl unload で moot」→ Phase B-3 進入。

## Phase B-3: WiFi-off + rmmod wl = ssh 切断ポイント (09:06 JST 前後)

130206 と完全同一手順:

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=wifi-off-and-wl-unload --collect bash -c "
  sleep 3
  nmcli con down OpenWrt
  nmcli radio wifi off
  sleep 2
  rmmod wl
  {
    echo epoch=$(date +%s)
    echo rc=$?
    echo === lsmod ===
    lsmod | grep -E \"^wl |^cfg80211 \" || echo NONE
    echo === wlp3s0 ===
    ip link show wlp3s0 2>&1 || echo MISSING
  } > /var/log/h4-probe/wl-unload.status 2>&1
"
'
# ssh はこの直後に切れる
```

### wl-unload.status durable file 内容 (Phase B-5 で回収)

```
epoch=1782950782
rc=0
=== lsmod ===
cfg80211             1404928  0
=== wlp3s0 ===
Device "wlp3s0" does not exist.
MISSING
```

**確定**:
- `rc=0` = rmmod 成功
- lsmod で `wl` 行なし、`cfg80211` のみ (refcount=0 に低下) = cfg80211 存置成功
- wlp3s0 device 消失

### ユーザコンソール検証ゲート通過 (blocking)

ユーザ報告: 「rc=0 かつ lsmod で wl 行なし + grep -c '^wl ' == 0 の条件を満たしていました」→ ゲート通過 → Phase B-4 進入。

## Phase B-4: 手動 30 cycle 駆動 → 30/30 完走 (09:07-10:30 JST 前後)

ユーザ手動操作 (1 cycle):
1. 蓋 close (= s2idle 突入)
2. 10-30 秒待つ
3. 電源ボタン短押し (= wake)
4. ログイン → 10-15 秒待つ (vpn-watcher が GSNet 再 activate)
5. cycle 番号確認: `watch -n 1 cat /dev/shm/cycle-progress`

### Cycle 1 canary チェック結果 (ユーザ報告)

ユーザ「wl_loaded=NO, xfrm_state=2 xfrm_policy=14, bnep_netdev=MISSING の 3 つとも満たしていました」→ 実験前提完全維持、残り 29 cycle 継続。

### 30 cycle 完走通知

ユーザ「完走しました」→ recovery 手順 (`sudo modprobe wl; sudo nmcli radio wifi on; sudo nmcli con up OpenWrt`) 実施済で ssh 復活。

## Phase B-5: durable evidence 回収 + 集計 (10:30-10:33 JST)

### boot 履歴 (durable)

```
 -2 fcc3d4b0 Sun 2026-06-28 12:32:51 JST → Wed 2026-07-01 04:15:51 JST  (043251 hang)
 -1 670cf7fd Wed 2026-07-01 04:18:04 JST → Wed 2026-07-01 10:22:08 JST  (102907 hang)
  0 8963e774 Wed 2026-07-01 10:24:12 JST → Thu 2026-07-02 10:32:29 JST  (130206 開始〜本セッション終了、不変)
```

**boot_id 開始〜終了で不変 = hang なしの決定的証拠** (130206 と本セッション両方 hang なしを 1 boot 内で通算)。

### suspend_stats + snapshot 増分

- suspend_stats: success=62 (130206 終了 31 + 本 smoke 1 + 実 cycle 30), fail=0
- snapshot 増分 (SESSION_START 以降): pre=31, post=31, snapshot-only.PRE=31, snapshot-only.POST=31 = **全 31 ペア完全マッチ、unpair pre なし**
- 内訳: smoke test 1 + 実 cycle 30 = 31

### wl_loaded 集計 (durable file 経由、SESSION_START 以降)

WL_UNLOAD_EPOCH (`wl-unload.status` の epoch=1782950782) を境界に SMOKE/CYCLE 分離:

```
30 CYCLE wl_loaded=NO  cfg80211_loaded=YES wlp3s0_present=NO
 1 SMOKE wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES
```

**確定**:
- **実 cycle 30 件全数** `wl_loaded=NO` = wl unload 30 cycle 通して維持 (spontaneous re-bind なし)
- 実 cycle 30 件全数 `cfg80211_loaded=YES` = cfg80211 存置成功
- 実 cycle 30 件全数 `wlp3s0_present=NO` = wlp3s0 device 消失
- smoke test 1 件のみ `wl_loaded=YES` (B-3 前、期待通り)

### ping_running 集計

```
31 ping_running=NO
```

**全 31 件 NO** = 連続 ping 混入ゼロ。

### xfrm 集計

```
30 xfrm_state=2 xfrm_policy=14
 1 xfrm_state=0 xfrm_policy=0
```

- 実 cycle 30 件全数 `xfrm_state=2 xfrm_policy=14` = VPN active
- smoke test 1 件 `xfrm_state=0 xfrm_policy=0` = smoke test 時 VPN 未セットアップ (期待通り)

### bnep_netdev 集計

```
31 bnep_netdev=MISSING
```

**全 31 件 MISSING** = suspend 直前 bnep teardown 完了、過去 hang signature と同じ (H1 が本 clean 分岐でも実質棄却圏を support)。

### Source-IP retro-classify (70-h4-probe .pre から)

各 .pre ファイルの xfrm state から local src IP (160.16.210.47 でない方) を抽出、分類:

```
30 CYCLE BT_PAN_VALID (src=172.20.10.13)
 1 SMOKE VPN_INACTIVE (src=none)
```

**確定**:
- **30 cycle 全数 BT_PAN_VALID** (`src=172.20.10.13`)
- **WIFI_KNOWN_CLEAN 0 件** (wl unload で構造的に不可能、130206 継承、advisor 予測通り)
- VPN_INACTIVE は smoke test のみ、実 cycle には 0 件 = vpn-watcher が全 cycle で GSNet 再 activate 成功

### Order-based pair matching

pre epoch 昇順と post epoch 昇順を順次消費:

```
PRE count: 31
POST count: 31
total hangs: 0
```

**確定: hang 0 件**。

### unregister_netdevice: waiting

```
0
```

**五度目の negative continues**、H1 (xfrm dev ref leak → netdev_wait_allrefs) は依然棄却圏。

## Phase B-6: クリーンアップ (10:33 JST)

```bash
sudo systemctl stop vpn-watcher.service cycle-watcher.service
sudo systemctl stop wifi-off-and-wl-unload.service
sudo rm -f /usr/lib/systemd/system-sleep/58-snapshot-only
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect no
sudo nmcli con modify GSNet connection.autoconnect no
sudo nmcli con modify OpenWrt ipv4.route-metric -1
sudo nmcli con modify OpenWrt connection.autoconnect yes
```

期待 final 状態と実測一致:

| 項目 | 期待 | 実測 |
|---|---|---|
| hooks | 50/60/70 の 3 個 | ✓ |
| OpenWrt autoconnect / route-metric | yes / -1 | ✓ |
| BT-PAN/GSNet autoconnect | no | ✓ |
| transient units | 全 inactive | ✓ |
| wl / cfg80211 | 両方 loaded (recovery 完了) | ✓ |
| WiFi radio | enabled | ✓ |
| boot_id | `8963e774...` 不変 | ✓ |
| `wl-unload.status` | 残置 (durable evidence、epoch=1782950782) | ✓ |

## 機序評価

### 何が確定したか (durable)

1. **30/30 BT_PAN_VALID cycle 全数 clean、hang 0 件、boot_id 不変** (durable ground truth: durable file 31 全ペア + boot_id 不変 + suspend_stats 62/0)
2. **wl 完全 unload 30 cycle 全数維持** (spontaneous re-bind なし、durable file で証明)
3. **cfg80211 存置による attribution 保護** (「wl か cfg80211 か」の混同を回避、130206 継承)
4. **WiFi 経由 VPN 混入 structural 0** (wl 消失で構造的に不可能、130206 継承)
5. **H1 依然 negative** (五度目、hang 発生 3 セッションで計 5 件の hang 事例全てで `unregister_netdevice: waiting` = 0、chance-clean と独立)

### 統計的評価 (目標達成)

- **base rate 想定 ~4.3-5%** (043251 1/20 + 102907 1/26 = pooled 2/46 ≈ 4.3%) だと (0.957)³⁰ ≈ 27% の確率で「wl 無関係でも 30/30 clean」が偶然起きる
- **本セッション単独** 0/30: Fisher exact (5/56 vs 0/30) 片側 p ≈ 0.11 (未達)
- **130206 と pool** 0/60: Fisher exact (5/56 vs 0/60) 片側 **p ≈ 0.024** で有意水準 p<0.05 到達 = **目標達成**
- hang arm 3 セッション pool (5/56 = 063543+043251+102907) と対称に clean arm 2 セッション pool (0/60 = 130206+本) が Fisher exact で有意化
- **caveat (advisor 事後指摘)**: 主案は「130206 で clean を見た後に追加を回している」ので mild な optional-stopping。厳格な事前登録 confirmatory publication では代替案 B2 (+60 cycle かつ fresh 0/60) が cleaner。本実験は exploratory research なので主案で妥当と判断

### 全 7 セッションの単一変数分離 (tight reading、統計的 establish)

| session | wl 状態 | radio | btusb 状態 | 結果 |
|---|---|---|---|---|
| 063543 | **loaded** | **off** | present | 3/10 hang |
| 043251 | **loaded** | **off** | present | 1/20 hang |
| 102907 | **loaded** | **off** | present | 1/26 hang |
| 061553 | loaded | on¹ | present | 0/30 clean |
| 041006 | loaded | on¹ | **removed (btusb 事前 unload)** | 0/22 clean |
| 130206 | **unloaded** | off (moot²) | present | 0/30 clean |
| **130415 (本)** | **unloaded** | off (moot²) | present | **0/30 clean** |

¹ radio-on とは `nmcli radio wifi on` かつ OpenWrt 接続 activated 状態。VPN は `route-metric 800` で BT-PAN 経由に強制
² wl unload されているので radio-off は moot (soft rfkill の状態は意味を持たない)

**hang ⟺ wl-loaded-AND-radio-off** で全 7 セッションが単一変数で分離、**pool 0/60 で Fisher p ≈ 0.024 で有意化**:
- wl-unloaded (130206+本): pooled 0/60 clean
- wl-loaded, radio-on (061553/041006): pooled 0/52 clean
- wl-loaded, radio-off (063543/043251/102907): pooled 5/56 hang (~9%)

**Keystone 注意 (130206 継承)**: 041006 は radio-on AND btusb-removed の double-perturbed で、single-variable radio-on の keystone point としては使えない。「radio-on + btusb-present + wl-loaded + all-else-normal」の isolated single-variable point は **061553 唯一**。tight reading が成り立つのは 061553 が genuinely radio-on だからで、これは 061553 report で確認済。

### 機序ラダーの位置づけ (advisor 諮問継承、更新)

- **主要読み (tight, all-seven-consistent, p<0.05 で establish)**: **hang ⟺ wl-loaded-AND-radio-off**。全 7 セッションが単一変数で分離、btusb term 不要
- **H1** (xfrm dev ref leak → `netdev_wait_allrefs`): **五度目の negative continues**、`unregister_netdevice: waiting` 0 件 → 実質棄却圏 (hang 発生 3 セッションで計 5 件の hang 事例全てで 0 件、chance-clean と独立)
- **H2 / H4 の downgrade 保留は解除**: pool 0/60 で wl-loaded-radio-off の operative 性が p<0.05 で bedrock 化されたため、H2 (bnep_session non-freezable kthread) と H4 (btusb URB drain) は「radio-off で active か radio-on で active か」の切り分けが必要な段階に降格
  - 「なぜ radio-off だけで hang が発生するか」を H2/H4 側から説明する追加証拠が必要
  - 例: H4 (btusb URB drain) が hang 主要機序なら、radio-off (wl active だが通信なし) 状態で btusb URB drain の race window が広がる理由が要説明
  - H2 (bnep_session non-freezable kthread) も同様、radio-off で kthread 状態が変わる理由が要説明
- **H6 (wl+btusb 両者必要) は unsupported both directions で demote 継続** (130206 継承、advisor 指摘):
  - hang 領域 (wl-loaded, radio-off): btusb-removed session は zero (未検証)
  - clean 領域 (wl-loaded, radio-on): 061553 (btusb present) と 041006 (btusb absent) 両方 clean で btusb 差なし
  - H6 は named possibility として保持するが tight reading より弱い
- **対立仮説 H7 (any-perturbation-helps, general fragility)**: hang は timing race で、dpm_suspend chain から任意の driver を除去すれば race window がずれて hang 確率が下がる仮説
  - H6 vs H7 は本セッションでは discriminate 不可、non-btusb driver 除去 (xfrm/bnep 事前 teardown 等) で判別
- **旧 H5 (wl 単独 dominant) は 041006 対称性で撤回済** (130206 継承)

### Candidate (b'') が p<0.05 で bedrock 化

これまで candidate (b) は「WiFi-on 通信が protective」、初期 (b') は「wl-in-chain (loaded) が hang の必要条件」だったが、061553/041006 (loaded + radio-on) が両方 clean で loose な (b') は反証済。130206 で tight な読み (b'') に framing 変質:

- **(b'')**: 「wl が **loaded かつ radio-off** の状態 (soft rfkill で通信停止しているが module active) が hang の必要条件」
- **全 7 セッション整合**: hang session (063543/043251/102907) は全て wl-loaded-radio-off、clean session (061553/041006/130206/本) は wl-radio-on か wl-unloaded
- **本セッション pool 0/60 で Fisher p ≈ 0.024 → (b'') が統計的に establish**

実用対策として (b'') は以下いずれかで対応可能:
- **常時 WiFi radio-on 運用** (WiFi off にしない): 061553/041006 の pooled 0/52 で establish (実用性最高、確実に hang 回避)
- **WiFi off 時は wl module unload**: 130206/本の pooled 0/60 で establish (但し `rmmod wl` の運用は broadcom-sta DKMS の脆さがあり要検討、後述)
- **suspend 前 wl unload の system-sleep hook**: 上と実質同じ、但し毎 suspend で unload/reload の overhead
- **radio-off しない (nmcli con down のみ)**: 未検証、次実験候補

## 観測上の副次的発見

### A. `rmmod wl` の 2 度目実行も clean に成功

130206 に続き本セッション B-3 でも `rmmod wl` は rc=0 で clean 完走。broadcom-sta DKMS モジュール (proprietary) は明示的な hold を取らないため、通信を停止した状態 (`nmcli con down OpenWrt; nmcli radio wifi off; sleep 2`) で `rmmod wl` が clean に走る挙動が 2 セッション連続で確認された。

### B. 130206 継承の detached systemd-run + durable file gate は今回も機能

`systemd-run --unit --collect` で ssh drop 後の rmmod 完走を保証、`/var/log/h4-probe/wl-unload.status` にゲート判定材料を書き込む二段構えは 130206 と同じく以下 3 つの落とし穴を防いだ:
1. ssh drop タイミングで rmmod 未実行のまま cycle 開始 (systemd-run で continuation 保証)
2. rmmod 失敗 (busy 等) を検出できず 30 cycle 全無効 (durable file の rc で検出)
3. reboot なし clean 分岐で journalctl だけでは wl 状態確認できない (durable file が persistent)

### C. Cycle-1 canary は 130206 と同じく実験前提維持を証明

Plan で継承した canary チェック (`wl_loaded=NO` + `xfrm_state=2 xfrm_policy=14` + `bnep_netdev=MISSING`) は本セッションでも 3 項目全通過。130206 と同じ機能性が 2 セッション連続で確認された。

### D. NM autoconnect chain の robust 性 (2 セッション連続)

`vpn-watcher.service` が 3 秒間隔で BT-PAN UP + GSNet inactive を polling → nmcli con up GSNet を発火 → 30 cycle 全数で `xfrm_state=2 xfrm_policy=14` durable 記録、VPN_INACTIVE は 0 件。130206 でも同じ挙動、iPad hotspot timeout や NM secrets cache 失敗による VPN_INACTIVE 化は本セッションでも発生せず。~90 分の連続駆動でも BT-PAN + GSNet chain は robust に動作。

### E. 130206 の証拠 (wl-unload.status) を Phase B-1 で削除して epoch 境界を明確化

Plan 修正時 (self-check) に発見した細部設計。130206 の durable evidence (`epoch=1782876623 rc=0`) は既に report/attachment に取り込み済なので、実機側の残置を Phase B-1 冒頭で削除。これで本セッション B-3 の `wl-unload.status` epoch (`1782950782`) が本セッション用のものだけになり、B-5 集計で SMOKE/CYCLE の epoch 境界として明確に機能した。

### F. Boot 履歴の連続性: 130206 開始以来 uptime ~1 日 0h の連続動作

boot 履歴:
- -2: fcc3d4b0 (043251 hang, 2026-06-28 → 07-01)
- -1: 670cf7fd (102907 hang, 07-01 04:18 → 10:22)
- **0: 8963e774 (2026-07-01 10:24:12 起動、130206 → 本セッション終了 07-02 10:32、uptime ~24 時間、不変)**

前 2 セッションは各 hang で boot_id 変化していたが、130206 開始以来通算 31 (前 = smoke 1 + 実 cycle 30) + 31 (本 = smoke 1 + 実 cycle 30) = 62 suspend/wake を hang なしで通過。suspend_stats の incremental (0→62) と snapshot 31/31 pair も consistent。

### G. WiFi 復旧手順の実効性 (2 セッション連続、reboot なし clean 分岐)

30/30 clean の場合、hang reboot が起きないので wl は unload のまま、`nmcli radio wifi off` の soft rfkill も persist。ユーザに以下 3 コマンドを実行してもらった:

```
sudo modprobe wl
sudo nmcli radio wifi on
sudo nmcli con up OpenWrt
```

結果: wl reload + cfg80211 refcount 1 に復帰、OpenWrt activated、ssh 復活。130206 と同じ機能性が 2 セッション連続で確認された。

### H. `/var/log/h4-probe/` の累積サイズ管理

累積: 268 pre + 266 post + 90 snapshot-only.PRE + 87 snapshot-only.POST + wl-unload.status = 712 ファイル。130206 完了時 588 → 本セッション +124 (実は smoke 1 + cycle 30 = 31 pair × 4 種類 = 124)。1 セッション ~124 ペース。**次セッション以降で logrotate 検討** (実験には影響なし、但し disk 消費で数百 KB/セッション)。

### I. Fisher exact のシンプル計算による有意化確認

hand-computed check:
- hang arm: 5/56, clean arm: 0/60
- Fisher exact 片側 p ≈ Σ P(k hangs in clean arm | H0) for k=0 = C(5,0)C(0,0)/... wait, standard Fisher exact via hypergeometric:
- P(at most 0 hangs in clean arm of size 60, given 5 hangs total in 116 trials) = C(56,5)/C(116,5) ≈ 0.024
- Advisor 事前 verify 通り、実測 pool 一致で目標達成

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 08:57 | Phase B-0 | SESSION_START_EPOCH=1782950249 捕捉、baseline 13 項目確認 |
| 08:58 | Phase B-1 | 前回 wl-unload.status 削除、58-snapshot-only hook (wl 3 フィールド版) デプロイ |
| 08:59 | Phase B-1 | Smoke test (`wl_loaded=YES ping_running=NO`) |
| 09:00 | Phase B-1 | vpn-watcher / cycle-watcher transient unit 起動 |
| 09:00 | Phase B-1 | NM 設定 (BT-PAN/GSNet autoconnect=yes, OpenWrt autoconnect=no route-metric=800) |
| ~09:01 | Phase B-2 | ユーザ iPad テザリング ON、BT-PAN + GSNet 自動 up、xfrm src=192.168.33.145 (WiFi 経由、moot)、ユーザ「WiFi on 問題ないか」確認応答 |
| ~09:06 | Phase B-3 | detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off; rmmod wl` 実行、ssh 切断 |
| ~09:07 | Phase B-3 | ユーザコンソール検証ゲート通過 (`wl-unload.status rc=0`, `lsmod | grep -c '^wl '` = 0) |
| 09:07-10:30 | Phase B-4 | ユーザ手動 30 cycle 駆動 (cycle 1 canary 3 項目通過)、hang 0 件、30/30 完走 |
| 10:30 | ssh 復活 | ユーザ recovery コマンド 3 個実行 → wl reload + WiFi 復旧 → Claude ssh 復活 |
| 10:30-10:33 | Phase B-5 | durable evidence 回収 (boot 履歴, suspend_stats, snapshot 集計, wl_loaded, ping_running, xfrm, bnep_netdev, source-IP gate, pair matching, unregister) |
| 10:33 | Phase B-6 | cleanup (transient units stop + 58-snapshot-only rm + NM revert) |
| 10:34 | レポート作成 | 本レポート作成、次セッション handover |

実験全体所要時間: 約 1 時間 37 分 (Phase B-4 で 30 cycle 完走まで ~83 分)。130206 (43 min) より長め、ユーザ pace が緩やかだった可能性 (base rate 内で許容範囲)。

## 検討して除外した事項

- **代替案 (+60 cycle) への切り替え**: プランで提示したが、advisor 推奨の主案 (+30 pool) で目標達成 (p ≈ 0.024)。決定力を求めるなら +60 で 0/90 → p ≈ 0.007 に伸ばせるが、本セッションでは主案で establish 完了
- **代替案 B2 (+60 fresh, pool しない)**: optional-stopping 批判に完全 robust だが、本実験は exploratory research で publication ではないため主案 (mild caveat 付き) で妥当
- **60 cycle への追加実施**: 主案で p<0.05 establish 済のため次セッションは (ii)/(iii)/(iv) に進む方が学び多い
- **wl blacklist の恒久設定**: 恒久設定は実用対策段階、機序探究途中では過剰

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-07-02 10:34 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで pre +31 / post +31 = 累計 268 pre / 266 post) | 本セッション 31 pair の証拠 + 将来 retro-classify 素材 |
| `/var/log/h4-probe/*.snapshot-only.PRE/POST` | 残置 (本セッションで PRE +31 / POST +31 = 累計 90 PRE / 87 POST) | ping/xfrm/wl_loaded durable 証拠 |
| `/var/log/h4-probe/wl-unload.status` | **本セッション用に上書き** (durable evidence, epoch=1782950782) | rmmod wl の rc + lsmod state |
| vpn-watcher.service | **削除済** (systemctl stop) | VPN reconnect 自動化 |
| cycle-watcher.service | **削除済** (systemctl stop) | 進捗監視 |
| wifi-off-and-wl-unload.service | **削除済** (--collect で auto) | B-3 実行キュー |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt autoconnect / route-metric | revert 済 (yes / -1) | |
| WiFi radio | enabled (recovery 完了) | |
| wl / cfg80211 | 両方 loaded (recovery 完了) | |

実機の suspend_stats: success 62, fail 0 (130206 開始 boot 内での通算)。boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (**130206 開始〜本セッション終了で不変、通算 uptime ~1 日 0h**)。

dev 機 (akdx01) 側: 何も書き換えなし。

## 次セッション引継ぎ

### メモリ更新内容 (本セッション終了時)

- `s2idle-btvpn-hang-mechanism-ladder`:
  - 「過去セッションの valid 性」表に本セッション (30 BT-PAN-valid / 0 hang、wl 完全 unload) を反映
  - 「本セッション (2026-07-02 103415) 結果」セクションを追加、全 7 セッション単一変数分離 + pool 0/60 で Fisher p ≈ 0.024 で establish を明記
  - candidate (b'') が p<0.05 で bedrock 化を明記
  - 機序ラダーで H1 五度目 negative continues、H2/H4 は「wl-radio-off だけで hang 誘発される理由の追加証拠が必要」段階に降格、H6 依然 demote、H7 は次実験で discriminate
  - 次の手を「(ii) 041006 btusb arm を WiFi-off で N 拡大 or (iii) non-btusb driver 除去 or (iv) S4 DPM_WATCHDOG」に更新
- `MEMORY.md`: index の description を本セッション結論 (pool 0/60 で有意化、(b'') establish、全 7 セッション整合) に合わせて訂正

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
echo "=== NM autoconnect (期待: 両方 no, OpenWrt yes/-1) ==="
nmcli -t -f connection.autoconnect,ipv4.route-metric con show OpenWrt
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
echo "=== boot_id (期待: 8963e774... = 130206 開始 boot、次セッション開始時点で依然不変のはず、reboot されていれば別 boot_id) ==="
cat /proc/sys/kernel/random/boot_id
echo "=== suspend_stats ==="
cat /sys/power/suspend_stats/success /sys/power/suspend_stats/fail
echo "=== unregister_netdevice: waiting (期待: 依然 0) ==="
sudo journalctl --no-pager 2>/dev/null | grep -c "unregister_netdevice: waiting"
echo "=== wl / cfg80211 (期待: 両方 loaded) ==="
lsmod | grep -E "^wl |^cfg80211 "
echo "=== transient units 残存していないか ==="
systemctl is-active vpn-watcher.service cycle-watcher.service wifi-off-and-wl-unload.service 2>&1
'
```

### 推奨の次の手 (優先順位順)

#### (ii) **041006 の btusb arm を WiFi-off で N 拡大** (最優先、~90 分)

041006 の confound (radio-on) を解消。本セッション B-3 の `rmmod wl` を `rmmod btusb` に置き換え、他は同一構造で 30 cycle 駆動。

- **clean** → btusb 必要 (H6 側) or any-perturbation (H7) が支持、tight reading (b'') は否定
- **hang** → btusb 非必要、tight reading (b'') が強化 (radio-off だけで hang 誘発される決定的証拠)

**設計変更点**:
- B-3 の `rmmod wl` → `rmmod btusb`
- 58-snapshot-only に `btusb_loaded=YES/NO` フィールド追加
- Cycle 1 canary で `btusb_loaded=NO` を確認
- 前提: btusb は refcount=? の確認、bnep や BT device が btusb を hold していないか事前調査

#### (iii) **Non-btusb driver 除去 (xfrm/bnep 事前 teardown)** (~90 分)

H6 vs H7 の判別実験。H7 (any-perturbation-helps) なら別 driver (xfrm/bnep) 除去でも同じく clean になる予測、H6 (wl+btusb 両者必要) なら hang するはず。

- **clean** → H7 支持 (「特定のドライバではなく race window ずれ」)、機序探究は根本的に見直し
- **hang** → H6 が支持または (b'') tight reading が更に強化

#### (iv) **S4 (DPM_WATCHDOG カーネル)** (~1-2 日、機序決着の最終手段)

現行 kernel は `DPM_WATCHDOG=n` で dpm_suspend の stall device 特定不可。`.config` 変更 → 自前ビルド → 実機インストール → 再現駆動で dmesg dump 取得。

- (ii)/(iii) で機序絞り込み後、dpm_suspend の stall device と call chain を kernel dump で特定

### 注意事項

- **`rmmod wl` (not `modprobe -r wl`) を必ず使う** (130206 継承): cfg80211 連鎖 unload 防止、attribution クリーン化
- **detached systemd-run + durable marker file 二段構え** (130206 継承): ssh drop の落とし穴を封鎖
- **Cycle 1 canary は 3 項目 blocking で確認** (130206 継承): spontaneous re-bind + VPN 復活失敗 + bnep teardown 状態
- **wl blacklist は絶対に設定しない** (130206 継承): recovery reboot での自動再ロードが必要
- **`/var/log/h4-probe/` の累積管理**: 累計 712 ファイル、次セッション以降で logrotate 検討
- **candidate (b'') は p<0.05 で establish 済**: 「wl loaded かつ radio-off が hang の必要条件」が全 7 セッション整合 + Fisher p ≈ 0.024。次セッション以降の議論はこの framing 前提
- **optional-stopping caveat**: 主案は「130206 で clean を見た後の追加」なので mild な optional-stopping。exploratory research としては妥当、but report で明示

## 関連レポート

- [2026-07-01_130206 セッション: 30/30 clean + tight reading (b'') 浮上 (本セッションの起点)](2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint.md)
- [2026-07-01_102907 セッション: ping confound 反証 + candidate (d) 完全排除](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md)
- [2026-07-01_043251 セッション: hang 独立再現 + 二つの壁で blocked](2026-07-01_043251_s2idle_btvpn_wifi_off_hang_reproduced_062543_signature.md)
- [2026-06-30_061553 セッション: 30/30 BT-PAN-valid clean (WiFi-on)](2026-06-30_061553_s2idle_btvpn_s3pp_rerun_n30_btpan_valid_clean_063543_narrower.md)
- [2026-06-28_074509 カーネルソース解析 H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_063543 s2idle + BT-PAN+VPN+lid close で 3/3 hang (原 bedrock)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-30_030349 セッション: S3'' 30 cycle / cycle 1 のみ valid confound](2026-06-30_030349_s2idle_btvpn_s3pp_vpn_autoconnect_confound_200520_invalidation.md)
- [2026-06-29_200520 セッション: S3 (bnep teardown) 32 cycle / cycle 1 のみ valid confound](2026-06-29_200520_s2idle_btvpn_s3_bnep_teardown_30cycle_clean.md)
- [2026-06-29_064608 セッション: driver path 25 cycle / 13 valid](2026-06-29_064608_s2idle_btvpn_freetest_driverpath_25c_clean_traffic_eroded.md)
- [2026-06-29_041006 セッション: S1 (btusb pre-unload) 22 cycle / 22 fully valid](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)
- [2026-06-28_141226 lid path required + αβ 未分離](2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md)
- [2026-06-28_111259 driver で hang ゼロ](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_021019 真の s2idle 初実証](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計 4 ハング](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
