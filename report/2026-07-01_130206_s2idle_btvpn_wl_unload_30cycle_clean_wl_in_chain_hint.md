# wl 完全 unload + s2idle + BT-PAN + VPN + lid close で 30/30 clean — wl-loaded-AND-radio-off tight reading 浮上

- **実施日時**: 2026 年 7 月 1 日 12:19 〜 13:02 (JST)
- **位置づけ**: [2026-07-01_102907 セッション](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) で「hang 3 度目独立再現 + ping confound 反証 + candidate (d) 完全排除」を達成したが、WiFi-off はすべて `nmcli radio wifi off` の soft rfkill のみで **wl モジュールは dpm_suspend chain にロード状態のまま**だった。事前 framing は loose な「wl-in-chain (loaded) が hang の必要条件か」の切り分けとして `rmmod wl` で wl のみ完全アンロード (cfg80211 存置) → 30 cycle 駆動。**結果: 30/30 BT_PAN_VALID cycle 全数 clean、hang 0 件**。base rate ~4.3-5% では (0.957)³⁰ ≈ 27% (5% で 21%) で「wl 無関係でも起きうる」ため決定的ではない。**加えて 全 6 セッション横断で単一変数「wl-loaded-AND-radio-off」で綺麗に hang/clean が分離される tight reading が浮上** (advisor 指摘): 事前の loose (b') = 「wl-in-chain (loaded) 必要条件」は 061553/041006 (loaded + radio-on = clean) で反証、tight な (b'') = 「wl が loaded かつ radio-off の状態が hang の必要条件」に framing 変質。初期に浮上した H6 (wl+btusb 両者必要) は clean 領域で btusb 差なし + hang 領域で btusb 未検証 = unsupported both directions で demote (advisor 指摘)。

## 結論 (先に要約)

1. **30/30 BT_PAN_VALID cycle 全数 clean、hang 0 件、boot_id 不変**:
   - snapshot 31 pre / 31 post = 全ペア成功 (pair matching で hangs 0)
   - suspend_stats success=31 (smoke test 1 + 実 cycle 30)、fail=0
   - boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` 開始〜終了で不変 (= reboot なし = hang なし の決定的証拠)
2. **wl 完全 unload 30 cycle 全数維持を durable file で証明**:
   - 実 cycle 30 件全て `wl_loaded=NO cfg80211_loaded=YES wlp3s0_present=NO` durable
   - smoke test 1 件のみ `wl_loaded=YES` (B-3 前、期待通り)
   - `/var/log/h4-probe/wl-unload.status` に `rc=0` + lsmod で wl 行なし durable 記録
3. **Source-IP gate で 30/30 BT_PAN_VALID、WiFi 経由 VPN 混入 structural 0**:
   - 30 cycle 全て `src=172.20.10.13` (BT-PAN)、WIFI_KNOWN_CLEAN 0 件 (wl 消失で構造的に不可能、advisor 予測通り)
   - 102907 の source-IP retro-classify (setup 段階で WiFi 経由 VPN 一時確立が起きた) より **cleaner**
4. **`unregister_netdevice: waiting` = 0 依然 = H1 negative continues** (四度目)
5. **Ping 集計**: PRE 31 件全て `ping_running=NO` durable (連続 ping 混入ゼロ、102907 の教訓維持)
6. **統計的評価 (advisor 事前警告通り、決定的ではない)**:
   - base rate 想定 ~4.3% (043251/102907 pooled 2/46) で (0.957)³⁰ ≈ **27%**、~5% で (0.95)³⁰ ≈ 21% の確率で「wl 無関係でも 30/30 clean」が偶然起きる
   - Fisher exact 5/56 (WiFi-off wl-loaded pooled) vs 0/30 (WiFi-off wl-unloaded): 片側 p ≈ 0.11、有意水準 p<0.05 到達せず
   - **統計的には establish されていない**、次は wl-unload N=60+ 拡大で bedrock 化する必要
7. **全 6 セッション単一変数分離 (tight reading, advisor 指摘)**:

   | session | wl 状態 | btusb | 結果 |
   |---|---|---|---|
   | 063543/043251/102907 | loaded, radio-off | present | pooled 5/56 hang |
   | 061553 | loaded, radio-on | present | 0/30 clean |
   | 041006 | loaded, radio-on | **removed** | 0/22 clean |
   | 130206 (本) | **unloaded** (radio-off) | present | 0/30 clean |

   **hang ⟺ wl-loaded-AND-radio-off** で全 6 セッションが単一変数で分離される、btusb term 不要。single-variable radio-on の keystone は 061553 唯一 (041006 は radio-on AND btusb-removed の double-perturbed)
8. **Candidate (b) → (b') → (b'') に framing 変質**:
   - 初期 (b') 「wl-in-chain (loaded) が hang の必要条件」は 061553/041006 (loaded + radio-on = clean) で反証
   - tight な **(b'')**: 「wl が **loaded かつ radio-off** の状態が hang の必要条件」全 6 セッション整合
9. **機序ラダー現状 (advisor 諮問経て確定)**:
   - **H1** (xfrm dev ref leak): `unregister_netdevice: waiting` 0 件、四度目の negative → 実質棄却圏 (hang session 5 件全てで 0、chance-clean と独立)
   - **H2** (bnep_session non-freezable kthread) と **H4** (btusb URB drain) の downgrade は本セッションでは **保留**: 本 30/30 clean が chance の可能性 (~21-27%) が残るため、H2/H4 の弱化を本 0/30 のみを根拠に主張するのは論理的に不整合。wl-loaded-radio-off の operative 性が N=60+ で bedrock 化されて初めて H2/H4 の相対的地位を語れる
   - **H6 (wl+btusb 両者必要仮説) は unsupported both directions で demote** (advisor 指摘): hang 領域 (wl-loaded, radio-off) で btusb-removed session は zero (未検証)、clean 領域 (wl-loaded, radio-on) では 061553 (btusb present) と 041006 (btusb removed) 両方 clean で btusb 差なし。H6 は named possibility として保持するが tight reading より弱い
   - **H7 (any-perturbation-helps, general fragility)**: hang は timing race で dpm_suspend chain から任意の driver 除去で race window がずれて hang 確率が下がる。H6 vs H7 は本セッションでは discriminate 不可、non-btusb driver 除去 (xfrm/bnep 事前 teardown) で判別
   - **旧 H5 (wl 単独 dominant) は 041006 対称性で撤回**
10. **次セッション設計**: (i) **wl-unload N=60+ 拡大** で 60/60 clean → Fisher p ≈ 0.024 で有意化 → **(b'') tight bedrock 化**、(ii) 041006 の btusb arm を WiFi-off で N 拡大 → 「btusb 必要」vs「wl-radio-off 必要」discriminate、(iii) 途中 hang → wl 非依存に revert、S4 段 (DPM_WATCHDOG) で dpm_suspend stall device 特定

## 添付ファイル

- [実装プラン](attachment/2026-07-01_130206_s2idle_btvpn_wl_unload_30cycle_clean_wl_in_chain_hint/plan.md)

## 通読版: 経緯と本セッションの位置づけ

### このプロジェクトでやっていること

MacBook Air 11" を外に持ち出して、Bluetooth テザリング (iPad の Personal Hotspot) と VPN をつないだ状態で蓋を閉じると、数回に一度、寝るはずのマシンが応答しなくなり、電源長押しで強制電源断するしかなくなる。バッテリは残っていても、開いていた作業状態は全部飛ぶので、地味に困る。

ここ 1 週間ほど、条件を少しずつ変えながら「何が悪さをしているのか」を絞り込んでいる。

### 前セッションまでで分かっていたこと

WiFi をオフにした状態 (`nmcli radio wifi off`) で 3 セッション連続でハングを再現できていて、「WiFi オフ + テザリング + VPN + 蓋閉じ」で、数 % から 30 % くらいの確率でハングする、というところまでは固まっていた。

ただ WiFi オフといっても、`nmcli radio wifi off` は電波を止めるだけで、WiFi のドライバ (wl) 自体はカーネルに残ったままだった。なので「ハングしているのは、そこにドライバがいるせいなのか、それとも wl とは無関係な Bluetooth 側や USB 側の問題なのか」がまだ切り分けられていなかった。

### 本セッションでやったこと

前セッションと同じ WiFi オフの状態にした上で、さらに `sudo rmmod wl` で **wl ドライバをカーネルから完全に外して**からユーザに蓋の開閉を 30 回繰り返してもらった。ドライバが本当に外れたままだったかを後で確認できるように、毎回のスナップショットに wl の状態を記録するようにしてある。

### 起きたこと

**30 回全部、ハングなしで通過した**。

- ハングして強制電源断していれば起動 ID (boot_id) が変わるはずが、開始から終了まで変わっていない
- 30 回全部のスナップショットで「wl は外れたまま」が記録されていた
- VPN も 30 回全部きちんと Bluetooth 経由で張り直されていた

### 意義

数字の上ではまだ決定的ではない。もともとのハング率が 5 % 前後だと想定すると、「wl が実は関係なくても、たまたま 30 回すべて通過する」確率が 21〜27 % ほどあるからで、統計的な検定 (Fisher) を通しても有意なところまではまだ届いていない。

**それでも、過去 6 セッション全体を並べ直してみると、綺麗な規則性が見えてきた** (advisor の指摘):

- ハングが出た 3 セッションはどれも **「wl は載っている、電波はオフ」** の状態
- ハングが出なかった 3 セッションはどれも **「wl は載っているが電波はオン」** か **「wl そのものを外している」** のどちらか

つまり「wl が **載っていて、かつ電波オフ**」という組合わせのときだけハングする、と読める。「wl が dpm_suspend に居ればハング」という以前の粗い見方だと、電波オンで clean な 2 セッションを説明できないので、「wl が載っていて電波オフ」というより厳しい条件に読み直すのが妥当。

同時に、少し前に「wl と btusb (Bluetooth USB) の両方が居ることが必要条件では」という仮説 (H6) を書いたけれど、これは根拠を吟味すると弱いことが分かった。btusb を外した 041006 セッションは同時に「電波オン」でもあり、clean だったのは btusb を外したせいなのか電波オンだったせいなのか区別が付かない。ハング側でも btusb を外した実験はまだやっていない。なので「wl+btusb 両方必要」は「今の所その可能性はあるね」くらいまで格下げする。

### 次にやること

1. **wl 完全アンロードで 60 回まで延長**: 今回と同じ手順で 60 回試して、60/60 clean が出れば統計的にも有意になる (p ≈ 0.024)。「wl が載っていて電波オフのときだけハングする」がここで固まる
2. **btusb を外して電波オフで試す**: 041006 の実験を電波オフでやり直す。ここで clean になれば「btusb を外せば良い」ことになるし、ハングすれば「btusb は無関係、wl が問題」がより強く言える
3. **wl / btusb 以外のドライバ (xfrm や bnep) を suspend 前に落として試す**: それでも clean になるなら、「特定のドライバではなく、何かを外せば race のタイミングがずれるだけ」の可能性 (H7) を考える必要がある
4. **DPM_WATCHDOG を有効にした自前ビルドカーネル**: 上の実験で機序が絞れなかったときの最終手段。カーネル自身に「suspend でどのドライバが止まったか」を吐き出させる

## 前提・目的

- **背景**: [2026-07-01_102907 セッション](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md) で hang 独立再現 (3 度目) + ping confound 反証 + candidate (d) 完全排除を達成、但し WiFi-off はすべて soft rfkill のみ = wl in dpm_suspend chain の状態、「wl-in-chain が hang の必要条件か」未検証
- **主要目的 (事前 framing)**: `rmmod wl` (cfg80211 は存置) で wl を完全アンロード → 30 cycle 駆動、hang の有無で「wl-in-chain (loaded) が hang の必要条件か」を切り分け。事後 advisor 諮問で全 6 セッション単一変数分離が浮上し tight な (b'')「wl-loaded-AND-radio-off」に framing 変質
- **非対称な意義 (事前案内)**:
  - **1+ hang** → 「wl 完全除去でも hang = wl 非依存」bedrock、機序探究は BT/USB/xfrm 側へ (S4 段 DPM_WATCHDOG カーネルに進む)
  - **30/30 clean** → 弱い示唆にすぎない (base rate ~5% で 21% の確率で偶然)、要 N=60+ 拡大
- **本セッション独自の追加設計**:
  - `rmmod wl` (not `modprobe -r wl`) で cfg80211 を残置 → attribution クリーン化
  - detached systemd-run で B-3 実行 → ssh drop 後も rmmod 完走
  - ユーザコンソール検証ゲート (blocking) を B-3 と B-4 の間に配置
  - 58-snapshot-only hook に `wl_loaded/cfg80211_loaded/wlp3s0_present` 3 フィールド追加
  - Cycle 1 canary で `wl_loaded=NO + xfrm_state=2` 両方確認 (spontaneous PCI re-bind + VPN 復活失敗の両方の barn door を封鎖)
- **役割分担**: hook/transient unit デプロイ・状態確認・retro-classify は Claude が ssh で実施。cycle 駆動 (蓋 close + 電源ボタン wake) は WiFi-off で ssh 切断中のためユーザ手動、進捗 (30 cycle 完走 or 途中 hang) はユーザ口頭報告

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)
- system-sleep hooks (本セッション実施中): `50-kbd-backlight`、`58-snapshot-only` (本セッション新規投入 + wl 3 フィールド追加、Phase B-6 で削除)、`60-s3-soak-log`、`70-h4-probe` の 4 個。実験前後は 3 個
- 電源: 全 cycle AC 給電
- BT/テザリング: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)、peer = iPad (`iMiminashiPadPro`, BT-PAN IP `172.20.10.13/28`)
- VPN: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`, tunnel inner IP `192.168.83.1/32`)
- WiFi (baseline): `wl`/`wlp3s0` (broadcom-sta DKMS 6.30.223.271)、接続 `OpenWrt` → **Phase B-3 で `nmcli radio wifi off` + `rmmod wl` で完全アンロード** (cfg80211 は refcount=0 で残置)
- baseline (実験開始時 12:19 JST): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (102907 hang reboot 後、不変)、suspend_stats 0/0、snapshot count=206 pre / 204 post、snapshot-only PRE 28 / POST 25 (102907 累計)、NM autoconnect 両方 no、route-metric -1、wl loaded refcount=0、cfg80211 loaded 1(from wl)、unregister 0 件、`no wl blacklist`
- baseline (実験終了時 13:02 JST): boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (**開始〜終了で不変 = hang なしの決定的証拠**)、snapshot count=237 pre / 235 post (= +31/+31、完全ペア)、snapshot-only PRE 59 / POST 56 (= +31/+31)、NM autoconnect 両方 no、WiFi radio enabled、wl+cfg80211 loaded (recovery 完了)、unregister 0 件
- 比較対照 102907 との condition 差: **`rmmod wl` 追加** (102907 は soft rfkill のみ)、それ以外は同一 (peer=iPad、WiFi=off、hook=50/60/70+58 with pgrep+wl 追加、駆動=手動 lid close + 電源ボタン wake)

## Phase B-0: baseline 確認 + wl 系 + SESSION_START 捕捉 (12:19-12:20 JST)

### SESSION_START_EPOCH 捕捉

```bash
SESSION_START_EPOCH=$(ssh miminashi@macbookair2015.lan 'date +%s')
# → 1782875995 (JST 2026-07-01 12:19:55)
echo "$SESSION_START_EPOCH" > /tmp/.../scratchpad/session_start_epoch.txt
```

hardcode 排除のため開発機の scratchpad に保存 (102907 継承)。

### baseline 10 項目確認結果

全項目期待値と一致:

| # | 項目 | 期待 | 実測 | 判定 |
|---|---|---|---|---|
| 1 | カーネル / mem_sleep | 6.12.94+deb13-amd64 / [s2idle] deep | 一致 | ✓ |
| 2 | GRUB cmdline | mem_sleep_default=s2idle no_console_suspend | 一致 | ✓ |
| 3 | hooks | 50/60/70 の 3 個 | 一致 | ✓ |
| 4 | h4-probe mode | beta | 一致 | ✓ |
| 5 | NM autoconnect + route-metric | OpenWrt=yes/-1, BT-PAN=no, GSNet=no | 一致 | ✓ |
| 6 | boot_id | 8963e774-4a15-4ec3-9ae4-0cb1f929d645 | 一致 | ✓ |
| 7 | suspend_stats | 0/0 | 一致 | ✓ |
| 8 | transient units | 全 inactive | 一致 | ✓ |
| 9 | lsmod wl+cfg80211 | wl(refcount=0), cfg80211(1 from wl) | 一致 | ✓ |
| 10 | wl blacklist | 未設定 (`no wl blacklist`) | 一致 | ✓ |
| 11 | lsof /sys/module/wl | 0 行 | 一致 | ✓ |

## Phase B-1: hook + transient units デプロイ (12:20-12:23 JST)

### 58-snapshot-only hook (102907 base + wl/cfg80211/wlp3s0 3 フィールド追加)

**102907 base** に以下 3 フィールドを追加、他は完全同一:
- `wl_loaded=YES/NO` (`lsmod | grep -q '^wl '` で判定、末尾スペースで anchor)
- `cfg80211_loaded=YES/NO`
- `wlp3s0_present=YES/NO` (`ip link show wlp3s0`)

Word-boundary regex (`(^|[ /])ping( |$)`) は 102907 で発見した bug (`gsd-housekeeping` false match) 対策を継承。

### Smoke test 実施 (12:20 JST)

`sudo rtcwake -m no -s 15; sudo systemctl start systemd-suspend.service --wait` で 1 回 suspend+wake:
- PRE (epoch 1782876053): `wl_loaded=YES cfg80211_loaded=YES wlp3s0_present=YES ping_running=NO` ✓
- POST (epoch 1782876069): 同上 ✓

hook 正常動作確認 → 進む。

### vpn-watcher + cycle-watcher 起動 (12:22 JST)

- `vpn-watcher.service` (transient, --collect): 3 秒間隔で BT-PAN UP + GSNet inactive を検知して `nmcli con up GSNet`
- `cycle-watcher.service` (transient, --collect): suspend_stats delta を `/dev/shm/cycle-progress` に書き出し

### NM 設定 (12:23 JST)

```bash
sudo nmcli con modify "iMiminashiPadPro ネットワーク" connection.autoconnect yes
sudo nmcli con modify GSNet connection.autoconnect yes
sudo nmcli con modify OpenWrt ipv4.route-metric 800
sudo nmcli con modify OpenWrt connection.autoconnect no  # 本セッション追加
```

`OpenWrt autoconnect=no` は本セッション追加 (wlp3s0 消失後の autoconnect 失敗 log spam 抑制、B-6 で revert)。

## Phase B-2: BT-PAN+VPN セットアップ + ユーザ事前案内 (12:28 JST 前後)

ユーザ操作: iPad テザリング ON。NM autoconnect=yes により BT-PAN + GSNet 自動 up。

Claude 確認結果 (12:29 JST):
- BT-PAN active (`iMiminashiPadPro ネットワーク`)、`172.20.10.13/28` 割当
- GSNet active、但し **xfrm src=192.168.33.145** (= WiFi IP、102907 と同症状)
- **B-3 で wl unload するので moot** (advisor 予測: wl 消失後は WiFi-routed VPN 混入が構造的に不可能)

**ユーザ事前案内 (= 本セッション load-bearing communication)**:
- 「本セッションは wl 完全 unload の切り分け実験、**hang 発生 → 決定的**、30/30 clean → 弱い示唆にすぎない (~21% で wl 無関係でも起きうる)」
- 「連続 ping 絶対禁止、VPN 疎通確認は wake 直後の `ping -c 1 10.0.0.1` one-shot のみ」
- 「30 cycle は wall-clock 目標、Claude が事後 source-IP gate で BT_PAN_VALID を数える」
- 「iPad hotspot timeout / NM secrets cache 失敗 → 失敗兆候を報告」
- 「Phase B-3 直後、コンソール前で `sudo cat wl-unload.status` + `lsmod | grep -c '^wl '` = 0 のゲート通過必須」
- 「Cycle 1 完了後、canary で `wl_loaded=NO` + `xfrm_state=2 xfrm_policy=14` の両方確認」

ユーザ「テザリング ON した」→ Phase B-3 進入。

## Phase B-3: WiFi-off + rmmod wl = ssh 切断ポイント (12:29 JST 前後)

**設計上の重要決定**:
- **`rmmod wl` を使う** (`modprobe -r wl` 禁止): `modprobe -r` は依存を連鎖 unload するので cfg80211 まで外れる → clean 分岐で「wl か cfg80211 か」の attribution が不能。`rmmod` は名指しのみで、wl は refcount=0 の leaf なので安全
- **detached systemd-run で非 ssh 依存に**: ssh は wlp3s0 経由なので `nmcli con down OpenWrt` で切れる、systemd-run --unit --collect で切断後も rmmod 完走
- **durable marker file** (`/var/log/h4-probe/wl-unload.status`) にゲート判定材料を書き込む

```bash
ssh miminashi@macbookair2015.lan '
sudo systemd-run --unit=wifi-off-and-wl-unload --collect bash -c "
  sleep 3
  nmcli con down OpenWrt
  nmcli radio wifi off
  sleep 2
  rmmod wl
  {
    echo epoch=\$(date +%s)
    echo rc=\$?
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
epoch=1782876623
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

ユーザ報告: 「ゲート通過、cycle 1 開始します」→ Phase B-4 進入。

## Phase B-4: 手動 30 cycle 駆動 → 30/30 完走 (12:31-12:58 JST 前後)

ユーザ手動操作 (1 cycle):
1. 蓋 close (= s2idle 突入)
2. 10-30 秒待つ
3. 電源ボタン短押し (= wake、lid open は s2idle で構造的に効かない)
4. ログイン → 10-15 秒待つ (vpn-watcher が GSNet 再 activate)
5. cycle 番号確認: `watch -n 1 cat /dev/shm/cycle-progress`

### Cycle 1 canary チェック結果 (ユーザ報告)

Cycle 1 完了後 (蓋 close → 電源ボタン wake → login) にユーザが最新 snapshot-only PRE を確認:
- `wl_loaded=NO` ✓ (= wl unload 継続、spontaneous PCI re-bind なし)
- `xfrm_state=2 xfrm_policy=14` ✓ (= VPN が BT-PAN 経由で再確立、下限 OK)
- `bnep_netdev=MISSING` ✓ (= suspend 直前 bnep teardown 完了、過去 hang signature と一致)

**実験前提完全維持、残り 29 cycle 継続**。

### 30 cycle 完走通知

ユーザ「30 cycle 完走しました」→ recovery 手順 (`sudo modprobe wl; sudo nmcli radio wifi on; sudo nmcli con up OpenWrt`) 実施を依頼、ssh 復活確認 (13:00 JST)。

## Phase B-5: durable evidence 回収 + 集計 (13:00-13:02 JST)

### boot 履歴 (durable)

```
 -2 fcc3d4b0 Sun 2026-06-28 12:32:51 JST → Wed 2026-07-01 04:15:51 JST  (043251 hang)
 -1 670cf7fd Wed 2026-07-01 04:18:04 JST → Wed 2026-07-01 10:22:08 JST  (102907 hang)
  0 8963e774 Wed 2026-07-01 10:24:12 JST → 現在 (13:00:29+)           (本セッション、開始〜終了不変)
```

**boot_id 開始〜終了で不変 = hang なしの決定的証拠** (hang していれば強制電源断で reboot、新 boot_id が生成される)。

### suspend_stats + snapshot 増分

- suspend_stats: success=31, fail=0
- snapshot 増分 (SESSION_START 以降): pre=31, post=31, snapshot-only.PRE=31, snapshot-only.POST=31 = **全 31 ペア完全マッチ、unpair pre なし**
- 内訳: smoke test 1 + 実 cycle 30 = 31

### wl_loaded 集計 (durable file 経由、SESSION_START 以降)

WL_UNLOAD_EPOCH (`wl-unload.status` の epoch=1782876623) を境界に SMOKE/CYCLE 分離:

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

**全 31 件 NO** = 連続 ping 混入ゼロ、102907 の教訓を維持。

### xfrm 集計

```
30 xfrm_state=2 xfrm_policy=14
 1 xfrm_state=0 xfrm_policy=0
```

- 実 cycle 30 件全数 `xfrm_state=2 xfrm_policy=14` = VPN active (詳細は source-IP gate で確認)
- smoke test 1 件 `xfrm_state=0 xfrm_policy=0` = smoke test 時 VPN 未セットアップ (期待通り)

### Source-IP retro-classify (70-h4-probe .pre から)

各 .pre ファイルの xfrm state から local src IP (160.16.210.47 でない方) を抽出、分類:

```
30 CYCLE BT_PAN_VALID
 1 SMOKE VPN_INACTIVE
```

**確定**:
- **30 cycle 全数 BT_PAN_VALID** (`src=172.20.10.13`)
- **WIFI_KNOWN_CLEAN 0 件** (wl unload で構造的に不可能、advisor 予測通り、102907 より cleaner)
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

**四度目の negative continues**、H1 (xfrm dev ref leak → netdev_wait_allrefs) は依然棄却圏。

## Phase B-6: クリーンアップ (13:02 JST)

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
| `wl-unload.status` | 残置 (durable evidence) | ✓ |

## 機序評価

### 何が確定したか (durable)

1. **30/30 BT_PAN_VALID cycle 全数 clean、hang 0 件、boot_id 不変** (durable ground truth: durable file 31 全ペア + boot_id 不変 + suspend_stats 31/0)
2. **wl 完全 unload 30 cycle 全数維持** (spontaneous re-bind なし、durable file で証明)
3. **cfg80211 存置による attribution 保護** (「wl か cfg80211 か」の混同を回避)
4. **WiFi 経由 VPN 混入 structural 0** (wl 消失で構造的に不可能、advisor 予測通り)
5. **H1 依然 negative** (四度目)

### 統計的評価 (advisor 事前警告通り、決定的ではない)

- **base rate 想定 ~4.3-5%** (043251 1/20 + 102907 1/26 = pooled 2/46 ≈ 4.3%) だと (0.957)³⁰ ≈ **27%**、または 5% で (0.95)³⁰ ≈ 21% の確率で「wl 無関係でも 30/30 clean」が偶然起きる
- **Fisher exact 5/56 vs 0/30**: 片側 p ≈ 0.11、有意水準 p<0.05 到達せず
- **統計的には establish されていない**
- **N=60 拡大時の projection**: 0/60 clean なら Fisher 5/56 vs 0/60 は片側 p ≈ **0.024** で有意水準 p<0.05 到達

### 全 6 セッションの単一変数分離 (advisor 指摘、tight reading)

| session | wl 状態 | btusb 状態 | 結果 |
|---|---|---|---|
| 063543 | **loaded, radio-off** | present | 3/10 hang |
| 043251 | **loaded, radio-off** | present | 1/20 hang |
| 102907 | **loaded, radio-off** | present | 1/26 hang |
| 061553 | loaded, radio-on¹ | present | 0/30 clean |
| 041006 | loaded, radio-on¹ | **removed (btusb 事前 unload)** | 0/22 clean |
| 130206 (本) | **unloaded** (radio-off) | present | 0/30 clean |

¹ radio-on とは `nmcli radio wifi on` かつ OpenWrt 接続 activated 状態。VPN は `route-metric 800` で BT-PAN 経由に強制 (WiFi 経由 VPN 混入は source-IP gate で 0 確認済)。

**hang ⟺ wl-loaded-AND-radio-off** で全 6 セッションが単一変数で分離される (advisor 指摘):
- wl-unloaded (130206): 1 セッション clean
- wl-loaded, radio-on (061553/041006): 2 セッション pooled 0/52 clean
- wl-loaded, radio-off (063543/043251/102907): 3 セッション pooled 5/56 hang (~9%)

**Keystone 注意 (advisor 指摘)**: 041006 は **radio-on AND btusb-removed** の double-perturbed で、single-variable radio-on の keystone point としては使えない。「radio-on + btusb-present + wl-loaded + all-else-normal」の isolated single-variable point は **061553 唯一**。tight reading が成り立つのは 061553 が genuinely radio-on だからで、これは 061553 report で `nmcli con modify OpenWrt ipv4.route-metric 800; nmcli con up OpenWrt` (WiFi active、metric で BT-PAN を優先) を確認済。

**Framing 訂正**: 「wl-in-chain (loaded) が hang の必要条件」は loose な読み (061553/041006 で反証)。**tight な読みは「wl が loaded かつ radio-off (soft rfkill されているが module active) で hang」**。130206 の 30/30 は tight 読みの necessary condition テストとして valid。

**統計的検定は依然 establish 未達**: 本セッション 0/30 は 21-27% で chance の可能性 (base rate ~4.3-5%)、Fisher 5/56 vs 0/30 片側 p ≈ 0.11。次は N=60+ で 60/60 clean → p ≈ 0.024 で bedrock 化。

### 機序ラダーの位置づけ (advisor 全6セッション単一変数分離指摘反映、更新)

- **主要読み (tight, all-six-consistent)**: **hang ⟺ wl-loaded-AND-radio-off**。全 6 セッションが単一変数で分離、btusb term 不要
  - wl-unloaded (130206): 0/30 clean
  - wl-loaded, radio-on (061553/041006): 0/52 clean
  - wl-loaded, radio-off (063543/043251/102907): 5/56 hang (~9%)
- **H1** (xfrm dev ref leak → `netdev_wait_allrefs`): **四度目の negative continues**、`unregister_netdevice: waiting` 0 件 → 実質棄却圏 (hang 発生 session 全 5 hang で 0 件、chance-clean と独立)
- **H2 / H4 の downgrade は本セッションでは保留**: 本セッション 30/30 clean が 21-27% で chance の可能性 (base rate ~4.3-5%) が残る。同じ null hypothesis から H4 (btusb URB drain) 弱化を導くのは論理的に不整合 (chance-clean なら H2/H4 は untouched)。**wl-loaded-radio-off の operative 性が N=60+ で bedrock 化されて初めて H2/H4 の相対的地位を語れる** (advisor 指摘)
- **H6 (both-required interaction, wl + btusb 両方が必要条件) は unsupported both directions に demote** (advisor 指摘):
  - hang 領域 (wl-loaded, radio-off): **btusb-removed session は zero、H6 の btusb 半分は untested**
  - clean 領域 (wl-loaded, radio-on): 061553 (btusb present) と 041006 (btusb absent) は両方 0/N clean = **btusb 存在は clean 領域で差を作らなかった**
  - → H6 の btusb 必要性は 041006 の 1 点 (WiFi-on で btusb 関係なし場面) から import しており、grounded な証拠なし。**H6 は named possibility として保持するが、tight reading より弱い**
- **対立仮説 H7 (any-perturbation-helps, general fragility)**: hang は timing race で、dpm_suspend chain から **任意の driver を除去すれば race window がずれて hang 確率が下がる**。物理的に plausible: hang signature (`Network unreachable retransmit 3 回 + dpm_suspend stall`) は timing-sensitive race を suggest
- **判別実験の訂正 (advisor 指摘)**:
  - 「041006 の btusb 除去 arm を WiFi-off で N 拡大」は H6 vs H7 を separate **しない** (両方が clean を predict)。この実験が separate するのは **「btusb 必要」vs「wl-radio-off 必要 (tight reading)」**
    - clean なら → btusb 必要 (H6 側) or any-perturbation (H7)、wl-radio-off tight reading は否定
    - hang なら → btusb 非必要、wl-radio-off tight reading が supported
  - H6 vs H7 を separate するには **non-btusb driver 除去** (xfrm や bnep 事前 teardown 等) が必要
- **旧 H5 (wl 単独 dominant) は 041006 との整合で撤回**: 041006 で btusb 除去 = clean は「btusb 側にも hang 経路がある」を強く示唆、wl 単独では hang を説明不可

### Candidate (b) → (b') → (b'') に変質、tight reading 反映

これまで candidate (b) は「WiFi-on 通信が protective」、初期 (b') は「wl-in-chain (loaded) が hang の必要条件」だったが、**061553/041006 (loaded + radio-on) が両方 clean で loose な (b') は反証** (advisor 指摘)。tight な読みで書き直し:

- **(b'')**: 「wl が **loaded かつ radio-off** の状態 (soft rfkill で通信停止しているが module active) が hang の必要条件」
- **全 6 セッション整合**: hang session (063543/043251/102907) は全て wl-loaded-radio-off、clean session (061553/041006/130206) は wl-radio-on か wl-unloaded
- **N=60+ 拡大は (b'') の tight 版を test**: wl-unloaded で 60/60 clean → 「wl-unloaded は sufficient for clean」bedrock 化。但し「wl-loaded-radio-off が hang trigger」の tight reading そのものは、wl-loaded-radio-off で N を増やして hang rate を bedrock 化する別実験でしか establish されない (063543 3/10 の bedrock を横に置いた場合)
- 実用対策としては (b'') が確定すれば「suspend 前 wl unload の system-sleep hook」or「WiFi radio を off にしない (常時 on 運用)」で対策可能。041006 (WiFi-on + BT-PAN 経由 VPN via route-metric) の 22/22 clean は後者の実用性を supports

## 観測上の副次的発見

### A. `rmmod wl` の実行結果は refcount=0 で即座に成功

Explore 事前調査で `wl 6459392 0` (refcount=0)、`sys/module/wl を開いているプロセス 0 行` を確認済。実際に systemd-run detached 経由で `rmmod wl` を実行 → durable file に `rc=0` 記録、lsmod から wl 行が消失、cfg80211 の refcount が 1→0 に低下。

含意: broadcom-sta DKMS モジュール (proprietary) は明示的な hold を取らないため、通信を停止した状態 (`nmcli con down OpenWrt; nmcli radio wifi off; sleep 2`) で `rmmod wl` が clean に走る。

### B. Detached systemd-run + durable file gate の設計が機能

`systemd-run --unit --collect` で ssh drop 後の rmmod 完走を保証、`/var/log/h4-probe/wl-unload.status` にゲート判定材料を書き込む二段構えは以下 3 つの落とし穴を防いだ:
1. ssh drop タイミングで rmmod 未実行のまま cycle 開始 (systemd-run で continuation 保証)
2. rmmod 失敗 (busy 等) を検出できず 30 cycle 全無効 (durable file の rc で検出)
3. reboot なし clean 分岐で journalctl だけでは wl 状態確認できない (durable file が persistent)

### C. Cycle-1 canary は spontaneous re-bind + VPN 復活失敗の両方を封鎖

Plan 時点では `wl_loaded=NO` のみのチェックだったが、advisor 指摘で `xfrm_state=2 xfrm_policy=14` を追加。結果として:
- `wl_loaded=NO` = wl unload 継続 (PCI re-bind による自動 modprobe が起きていない) — 1 barn door
- `xfrm_state=2 xfrm_policy=14` = VPN が BT-PAN 経由で再確立 (wl unload 後 vpn-watcher が routing 切り替えて GSNet 再 activate 成功) — もう 1 barn door

両方通過することで「実験前提の完全維持」が blocking gate で確認できた。

### D. `cfg80211` 存置は attribution クリーン化に寄与

`rmmod wl` (not `modprobe -r wl`) の選択により cfg80211 の refcount が 1→0 に低下、モジュール自体は残置。実 cycle 30 件全数で `cfg80211_loaded=YES wl_loaded=NO` を durable 記録。

含意: 30/30 clean が出た場合の attribution は **「wl は必要条件、cfg80211 は関係なし (or 少なくとも wl なしでは stall しない)」** で clean。もし `modprobe -r wl` で cfg80211 まで外していたら「wl か cfg80211 のどちらか」までしか絞れなかった。

### E. NM autoconnect=yes + BT-PAN + GSNet の VPN 再確立チェーンは 30 cycle 全数で機能

`vpn-watcher.service` が 3 秒間隔で `ip -br link show enx98e0d98d205e | grep UP` + `nmcli GENERAL.STATE GSNet | grep activated` を polling、activate 未完成なら `nmcli con up GSNet` を発火。結果として 30 cycle 全数で `xfrm_state=2 xfrm_policy=14` durable 記録、VPN_INACTIVE は 0 件。

含意: 102907 で懸念した「iPad hotspot timeout + NM secrets cache 失敗」による VPN_INACTIVE 化は本セッションでは発生せず。~40 分の連続駆動で BT-PAN + GSNet chain は robust に動作。

### F. Boot 履歴の連続性: 102907 hang reboot 後 → 本セッション hang なし = boot_id 不変で証明

boot 履歴:
- -2: fcc3d4b0 (043251 hang)
- -1: 670cf7fd (102907 hang)
- **0: 8963e774 (2026-07-01 10:24:12 起動、本セッション開始 12:19 → 終了 13:02 で uptime 2h38m、不変)**

前 2 セッションは各 hang で boot_id 変化していたが、本セッションは開始〜終了で不変 → durable な hang なし証拠。suspend_stats の incremental (0→31) と snapshot 31/31 pair も consistent。

### G. WiFi 復旧手順の実効性 (clean 分岐、reboot なし)

30/30 clean の場合、hang reboot が起きないので wl は unload のまま、`nmcli radio wifi off` の soft rfkill も persist。ユーザに以下 3 コマンドを実行してもらった:

```
sudo modprobe wl
sudo nmcli radio wifi on
sudo nmcli con up OpenWrt
```

結果: wl reload + cfg80211 refcount 1 に復帰、OpenWrt activated、ssh 復活 (13:00 JST)。plan 予測通り機能。

### H. `/var/log/h4-probe/` の累積サイズ管理は近い将来 logrotate 検討

累積: 237 pre + 235 post + 59 snapshot-only.PRE + 56 snapshot-only.POST + wl-unload.status = 588 ファイル。1 セッション ~30 pair 増えるペースで、logrotate or 月次手動削除を次セッション以降で検討。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 12:19 | Phase B-0 | SESSION_START_EPOCH=1782875995 捕捉、baseline 10 項目確認 |
| 12:20 | Phase B-1 | 58-snapshot-only hook (wl 3 フィールド追加) デプロイ + smoke test (`wl_loaded=YES ping_running=NO`) |
| 12:22 | Phase B-1 | vpn-watcher / cycle-watcher transient unit 起動 |
| 12:23 | Phase B-1 | NM 設定 (BT-PAN/GSNet autoconnect=yes, OpenWrt autoconnect=no route-metric=800) |
| ~12:28 | Phase B-2 | ユーザ iPad テザリング ON、BT-PAN + GSNet 自動 up、xfrm src=192.168.33.145 (WiFi 経由、moot) |
| ~12:29 | Phase B-3 | detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off; rmmod wl` 実行、ssh 切断 |
| ~12:30 | Phase B-3 | ユーザコンソール検証ゲート通過 (`wl-unload.status rc=0`, `lsmod | grep -c '^wl '` = 0) |
| 12:31-12:58 | Phase B-4 | ユーザ手動 30 cycle 駆動 (cycle 1 canary 通過)、hang 0 件、30/30 完走 |
| 13:00 | ssh 復活 | ユーザ recovery コマンド 3 個実行 → wl reload + WiFi 復旧 → Claude ssh 復活 |
| 13:00-13:02 | Phase B-5 | durable evidence 回収 (boot 履歴, suspend_stats, snapshot 集計, wl_loaded, ping_running, source-IP gate, pair matching, unregister) |
| 13:02 | Phase B-6 | cleanup (transient units stop + 58-snapshot-only rm + NM revert) |
| 13:02 | レポート作成 | 本レポート作成、次セッション handover |

実験全体所要時間: 約 43 分 (Phase B-4 で 30 cycle 完走まで ~30 分)。102907 (2 時間、cycle 26 で hang) より短縮。

## 検討して除外した事項

- **60 cycle への即時延長**: 30/30 clean の時点で本セッション「30/30 clean + 全 6 セッション tight reading 浮上」headline は確定、延長は次セッションの別タイトルで実施 (plan 記載通り)
- **`modprobe -r wl` で cfg80211 も同時 unload**: attribution 弱化のため排除、`rmmod wl` を選択
- **wl blacklist の恒久設定**: 恒久設定は実用対策段階、機序探究の途中では過剰 (blacklist 誤投入で recovery 失敗のリスクもあり)

## 残置物 (Macbook 側の現状)

クリーンアップ完了後 (2026-07-01 13:02 JST):

| パス | 状態 | 用途 |
|---|---|---|
| `/usr/lib/systemd/system-sleep/50-kbd-backlight` | 残置 | キーボード LED |
| `/usr/lib/systemd/system-sleep/60-s3-soak-log` | 残置 | SLEEP/WAKE durable log |
| `/usr/lib/systemd/system-sleep/70-h4-probe` | 残置 (前セッションから) | pre/post スナップショット |
| `/usr/lib/systemd/system-sleep/58-snapshot-only` | **削除済** | 本セッションのみ用 |
| `/usr/local/bin/h4-mode` | 残置 | mode 切替 (現在 beta) |
| `/var/lib/h4-probe/mode` | 残置 = `beta` | mode ラベル |
| `/var/log/h4-probe/*.{pre,post}` | 残置 (本セッションで pre +31 / post +31 = 累計 237 pre / 235 post) | 本セッション 31 pair の証拠 + 将来 retro-classify 素材 |
| `/var/log/h4-probe/*.snapshot-only.PRE/POST` | 残置 (本セッションで PRE +31 / POST +31 = 累計 59 PRE / 56 POST) | ping/xfrm/wl_loaded durable 証拠 |
| `/var/log/h4-probe/wl-unload.status` | 残置 (durable evidence) | rmmod wl の rc + lsmod state |
| vpn-watcher.service | **削除済** (systemctl stop) | VPN reconnect 自動化 |
| cycle-watcher.service | **削除済** (systemctl stop) | 進捗監視 |
| wifi-off-and-wl-unload.service | **削除済** (--collect で auto) | B-3 実行キュー |
| autoconnect (BT-PAN, GSNet) | revert 済 (no) | |
| OpenWrt autoconnect / route-metric | revert 済 (yes / -1) | |
| WiFi radio | enabled (recovery 完了) | |
| wl / cfg80211 | 両方 loaded (recovery 完了) | |

実機の suspend_stats: success 31, fail 0 (本セッション開始 boot 内での累積)。boot_id `8963e774-4a15-4ec3-9ae4-0cb1f929d645` (**本セッション開始〜終了で不変 = hang なしの決定的証拠**)。

dev 機 (akdx01) 側: 何も書き換えなし。

## 次セッション引継ぎ

### メモリ更新内容 (本セッション終了時)

- `s2idle-btvpn-hang-mechanism-ladder`:
  - 「過去セッションの valid 性」表に本セッション (30 BT-PAN-valid / 0 hang、wl 完全 unload) を反映
  - 「本セッション (2026-07-01 130206) 結果」セクションを追加、全 6 セッション単一変数分離 tight reading を明記
  - candidate (b) → (b') → (b'') に framing 変質: 「wl loaded かつ radio-off が hang の必要条件」の tight reading。loose (b') 「wl-in-chain (loaded) 必要条件」は 061553/041006 で反証
  - 機序ラダーで H1 negative continues (四度目)、H2/H4 の downgrade は本 30/30 clean が chance の可能性で保留、041006 と本 130206 の対称性から浮上した H6 (両者必要仮説) は unsupported both directions で demote、H7 (any-perturbation) と co-equal、旧 H5 (wl 単独責任) は 041006 対称性で撤回
  - 次の手を「wl-unload N=60+ 拡大 で (b'') tight bedrock 化 or 041006 の btusb arm を WiFi-off で N 拡大して btusb 必要 vs wl-radio-off 必要 discriminate or S4 DPM_WATCHDOG カーネル」に更新
- `MEMORY.md`: index の description を本セッション結論 (tight reading + (b'') + H6 demote) に合わせて訂正

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
echo "=== NM autoconnect (期待: 両方 no, OpenWrt yes) ==="
nmcli -t -f connection.autoconnect,ipv4.route-metric con show OpenWrt
nmcli -t -f connection.autoconnect con show "iMiminashiPadPro ネットワーク"
nmcli -t -f connection.autoconnect con show GSNet
echo "=== boot_id (期待: 8963e774... = 本セッション開始 boot、次セッション開始時点で不変のはず) ==="
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

#### (i) **wl-unload N=60+ 拡大** (最優先、~150-200 分)

本セッション設計を継承 (58-snapshot-only + wl 3 フィールド + rmmod wl + Cycle 1 canary + ゲート)、cycle 数のみ 30 → 60 に拡大。

**設計**:
- Phase 構成は本セッションと同一 (B-0 〜 B-6)
- Phase B-4 の目標を wall-clock 60 cycle に変更
- Cycle 1 canary + 30 cycle 中間 canary (念のため)
- 60/60 clean → Fisher 5/56 vs 0/60 は片側 p ≈ 0.024 で有意水準 p<0.05 到達 → **candidate (b'') bedrock 化 = 「wl-loaded-AND-radio-off が hang の必要条件 (tight reading)」確定**
- 途中 hang → wl 非依存に revert、S4 段へ

#### (ii) **041006 の btusb arm を WiFi-off で N 拡大** (~150-200 分)

041006 の confound (radio-on) を解消、「btusb 必要 (H6 側)」vs「wl-radio-off 必要 (tight reading)」を discriminate。設計は本セッション B-3 の rmmod wl を rmmod btusb に置き換え、他は同一構造。

- **clean** → btusb 必要 (H6 側) or any-perturbation (H7) が支持、tight reading (b'') は否定
- **hang** → btusb 非必要、tight reading (b'') が supported

#### (iii) **Non-btusb driver 除去 (xfrm/bnep 事前 teardown)** (~150-200 分)

H6 vs H7 の判別実験。H7 (any-perturbation-helps) なら別 driver (xfrm/bnep) 除去でも同じく clean になる予測、H6 (wl+btusb 両者必要) なら hang するはず。

#### (iv) **S4 (DPM_WATCHDOG カーネル)** (~1-2 日、機序決着の最終手段)

現行 kernel は `DPM_WATCHDOG=n` で dpm_suspend の stall device 特定不可。`.config` 変更 → 自前ビルド → 実機インストール → 再現駆動で dmesg dump 取得。

- (i) で 60/60 clean + (ii)/(iii) で機序絞り込み後、dpm_suspend の stall device と call chain を kernel dump で特定
- (i) で途中 hang → wl 非依存確定、H2/H4 のどちらが stall しているか DPM_WATCHDOG で特定

### 注意事項

- **`rmmod wl` (not `modprobe -r wl`) を必ず使う**: cfg80211 連鎖 unload 防止、attribution クリーン化
- **detached systemd-run + durable marker file 二段構え**: ssh drop の落とし穴を封鎖 (本セッション B-3 で実証)
- **Cycle 1 canary は `wl_loaded=NO` + `xfrm_state=2` の両方を blocking で確認**: spontaneous PCI re-bind + VPN 復活失敗の両方の barn door を封鎖 (本セッションで実効性確認)
- **base rate ~4.3-5% での 30/30 clean は 21-27% 確率で偶然起きる**: 統計的 establish には N=60+ 必要 (60/60 で Fisher p ≈ 0.024 に到達)
- **wl blacklist は絶対に設定しない**: recovery reboot での自動再ロードが必要、blacklist 投入で ssh 復活不能
- **`/var/log/h4-probe/` の累積管理**: 累計 588 ファイル、次セッション以降で logrotate 検討
- **candidate (b) は (b') → (b'') に変質**: 「WiFi-on protective」→ (loose) 「wl-in-chain (loaded) が hang の必要条件」→ (tight) **「wl loaded かつ radio-off が hang の必要条件」**。全 6 セッション整合の tight reading、次セッション以降の議論はこの framing で

## 関連レポート

- [2026-07-01_102907 セッション: ping confound 反証 + candidate (d) 完全排除 (本セッションの起点)](2026-07-01_102907_s2idle_btvpn_noping_wifioff_hang_reproduced_ping_confound_ruled_out.md)
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
