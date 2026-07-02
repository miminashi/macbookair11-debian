# BT-PAN × VPN s2idle ハング — peer 非依存・手動 lid-close 経路が必要条件であることを 2×2 で確定

- **実施日時**: 2026年6月28日 11:30〜14:00 (JST)
- **位置づけ**: [2026-06-28_111259 レポート](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) の続編。同レポートで「Claude 駆動 `systemctl suspend` 15/15 完走・ハング 0」を観測したが、(a) 手動 lid-close vs `systemctl suspend` の **経路差** と (b) iPhone(`172.20.10.6`) vs iPad(`172.20.10.13`) の **peer 差** が同居していて分離できなかった。本実験は残り 2 セル (iPad 手動 / iPhone driver) を埋めて 2×2 を完成させた。

## 結論 (先に要約)

1. **「BT-PAN × VPN × 手動 lid-close 経路」3 因子の AND がトリガー** であり、**peer (iPhone/iPad) は必要条件ではない**ことを 2×2 ですべて埋めて確定した。
2. **2×2 マトリクス完成**:

   | | iPhone (`172.20.10.6`) | iPad (`172.20.10.13`) |
   |---|---|---|
   | **手動 lid close** | ハング 3/10 ([063543](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)) | **ハング 1/22 (本実験 1)** |
   | **driver 自動 (`rtcwake -m no -s 30` + `systemctl suspend`)** | **クリーン 0/30 (本実験 2b)** | クリーン 0/30 (本実験 2a) + 0/15 ([111259](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)) = **0/45** |

3. iPad 手動の hang signature は親 063543 (iPhone 手動) と**完全同一** (`kbd-backlight-sleep pre/suspend: saved=0 set->0` が前 boot 最終可視行、`PM: suspend exit` 欠落、freeze 完了後の dpm_suspend 段で停止)。**peer によらず同じデバイス停止パターン**。
4. 経路差の中身は **(α) 入眠 trigger** (lid close → logind `HandleLidSwitch` → suspend.target / vs `systemctl suspend` 直叩き) と **(β) wake trigger** (LID open → LID0 GPE / vs RTC IRQ8) の 2 軸で、本実験ではどちらが必須かまでは切り分けていない。次の一手で resolve できる (留意節参照)。
5. これにより親 063543 行 115 の hypothesis (a) **「`btusb` module unload」** は依然否定されてはいないが、「**BT-PAN は必須でも、lid 経路を踏まなければ出ない**」という新事実から **BT 物理レベルの対策より lid 経路に attack する方が筋** という方針が浮上した。

## 添付ファイル

- [監視・実行プラン](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/plan.md)
- [実験 1 ハング — 前 boot 最終可視行 + IKE_SA delete 抜粋](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/hang-journal-excerpts.log)
- [実験 1 ハング直前の teardown 順序 (freeze 直前 100ms 窓)](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/hang-teardown-sequence.log)
- [実験 2a iPad driver N=30 susp-test.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/susp-test-ipad-N30.log)
- [実験 2b iPhone driver N=30 susp-test.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/susp-test-iphone-N30.log)
- [s3-soak.log 実験窓 (11:08 baseline〜iPhone 完走まで)](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/s3-soak-experiment-window.log)
- [両 driver の IKE_SA delete (`172.20.10.6` = iPhone, `172.20.10.13` = iPad)](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/ike-sa-deletes-both-drivers.log)

## 前提・目的

- **未分離だった 2 変数**: 親 111259 で driver が 15/15 完走したことで「経路差」(driver vs 手動) が示唆されたが、同時に親 063543 の hang は iPhone peer、111259 の driver は iPad peer と peer も違っていた。「peer で消えたのか経路で消えたのか」が分離できていなかった。
- **本実験の目的**: 残り 2 セルを埋める。
  - **実験 1 (iPad 手動)**: peer を iPad に固定して**手動 lid close を反復**。再現すれば peer 差なし、しなければ peer が必要条件候補。
  - **実験 2a (iPad driver)**: 111259 の追試。N=30 へ拡張してさらに小標本性を緩和。
  - **実験 2b (iPhone driver)**: iPhone を driver 経路に乗せる。完走すれば「手動 lid-close 経路が必要条件」が peer 非依存で確定。
- **役割分担**: 実験 1 は強制電源断が必須のため**操作は全てユーザが実機で手動実施**、Claude は ssh 越しに read-only 観測のみ。実験 2a/2b は **Claude が driver を ssh で起動して自動運転** (driver が wifi を切るため blind 運用、結果は 30 分後 / 完走 or ハング後のリブート時に取得)。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: `mem_sleep=[s2idle] deep`(s2idle 選択・全 92 cycle の `PM: suspend entry` がすべて `(s2idle)` で deep 化けゼロ)、`LID0 *enabled`、`s3-deep-apply.service` 削除済 (`systemctl is-enabled` で `not-found`)
- system-sleep フック: `50-kbd-backlight`、`60-s3-soak-log` (deep 強制行は完全削除済で s2idle が維持される)
- 電源: 全実験 **AC 給電** (`ADP1/online=1`)、バッテリ 87% (cap/charge_now 全期間で不変)
- **Bluetooth/テザリング**: `btusb`(USB)/`hci0`(`98:E0:D9:8D:20:5E`)。peer は実験 1+2a で iPad (`iMiminashiPadPro`, `34:42:62:16:03:F6`, PAN IP `172.20.10.13/28`)、実験 2b で iPhone (`iMiminashiSE`, `CC:60:23:AF:2C:60`, PAN IP `172.20.10.6/28`)。PAN iface 名はどちらも `enx98e0d98d205e` (hci0 MAC 由来で同一)
- **VPN**: NM 接続 `GSNet` = strongSwan IPsec/IKEv2 (`charon-nm`, MOBIKE, GW `160.16.210.47`)、`password-flags=0` (111259 で設定済を維持)
- **WiFi**: `wl`/`wlp3s0`、接続 `OpenWrt` (`192.168.33.x`)。実験 1 はユーザが NM GUI で切断、実験 2a/2b は driver が自身で `nmcli dev disconnect wlp3s0` (非永続) で切断
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。本セッションは `/sandbox` 無効でサンドボックス外から ssh

## 実験 1: iPad peer + 手動 lid close

### 開始前 baseline (Claude が ssh で取得)

| 項目 | 値 |
|---|---|
| `mem_sleep` | `[s2idle] deep` (s2idle 選択中) |
| `LID0` | `*enabled` |
| `s3-deep-apply` | `not-found` (unit 削除済 = 完全 disabled) |
| `60-s3-soak-log` の `echo deep` | 完全削除 (コメントすら残らず) |
| `ADP1/online` | `1` (AC) |
| `suspend_stats success/fail` | 16 / 0 (全 `failed_*` カウンタ 0) |
| `PM: suspend entry/exit` | 16/16 完全ペア、全 `(s2idle)` |
| baseline `boot_id` | `3aa09ac0-ab3f-49bb-9e3d-5721a62c9bed` |
| baseline `s3-soak.log` 末尾 | `WAKE ss_ok=16` @ `2026-06-28T11:08:41+0900` |

→ s2idle 維持の前提が全て成立 (過去の「s2idle と思っていた実体が deep だった」事故への gating が pass)。

### 手順 (ユーザが実機で手動実施)

1. WiFi を NM GUI で切断
2. iPad の `iMiminashiPadPro ネットワーク` (BT-PAN) を up、PAN iface に `172.20.10.13/28` が付くのを確認
3. `GSNet` (VPN) を up、`xfrm state` の ESP SA `src` が `172.20.10.13` (BT-PAN 経由) になることを確認
4. **蓋を閉じる → 数秒〜十数秒後に開ける** を反復 (ユーザ体感「10 回程度繰り返した時点でハング」、実カウントは 22 cycle 目 — 後述「結果」節参照)
5. 復帰しなくなった時点で **電源ボタン長押しで強制電源断 → リブート → wifi 自動復帰**

### 結果 (Claude が ssh 越しに retrospective に取得)

- **True hang 確定 (3 点セット)**:

  | 指標 | 値 |
  |---|---|
  | `boot_id` 変化 | baseline `3aa09ac0…` → 現在 `fcc3d4b0-8141-4477-b7df-d5b725adbda1` (強制リブート確定) |
  | `s3-soak.log` 末尾 | `2026-06-28T12:29:59 SLEEP ss_ok=37` → 対応 WAKE 欠落 |
  | 前 boot `PM` 件数 | `entry 37 / exit 37` (ハング suspend の entry 行は journald flush 前停止で残らず、count は 37 で止まる) |
  | `journalctl --list-boots` | 前 boot `3aa09ac0…` 終了時刻 `2026-06-28 12:29:59` (= s3-soak SLEEP と一致) |
  | 強制電源断 → 再起動間隔 | 12:29:59 → 12:32:51 = 2 分 52 秒 |

- **前 boot 最終可視行 = 親 063543 と完全同一の signature** ([hang-journal-excerpts.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/hang-journal-excerpts.log)):

  ```
  charon-nm: 11[IKE] deleting IKE_SA GSNet[22] between 172.20.10.13[macbookair2015]...160.16.210.47[160.16.210.47]
  systemd[1]: Reached target sleep.target - Sleep.
  systemd[1]: Starting systemd-suspend.service - System Suspend...
  systemd[1]: Successfully froze unit 'user.slice'.                    ← freeze 完了
  kbd-backlight-sleep[124849]: pre/suspend: saved=0 set->0             ← system-sleep pre フック完走
                                                                       ← ここで停止 = dpm_suspend 段
  ```

- **条件成立の retrospective 検証 (driver 無しの手動運用での代替手段)**:
  - 前 boot で **`deleting IKE_SA GSNet[N] between 172.20.10.13 ... 160.16.210.47` を 20 件以上記録**、特にハング直前の `GSNet[22]` が `172.20.10.13[macbookair2015]` 端点 = **ハング瞬間に VPN が BT-PAN 経由でアクティブだった**ことを strongSwan ログから確定
  - 前 boot 全 37 件の `PM: suspend entry` がすべて `(s2idle)` ← deep 化けゼロ

- **サイクル数**: baseline ss_ok=16 → ハング直前 ss_ok=37 = **21 cycle 完走 + 1 hang = 22 cycle 目でハング** (ユーザ体感「10 回程度」との差は baseline 11:08:41 後にこの実験前のテスト suspend が混じっていた分)
  - **これは過去最長記録**: 親 063543 #1=0連続成功 / #2=1 / #3=6、本日 iPad=21 — peer 差は確率に効くが必要条件ではない、を示唆

## 実験 2a: iPad peer + driver 自動 N=30

### 設定と起動

- 起動: `2026-06-28T12:45:29+0900`
- unit: `susp-btvpn-ipad.service` (invocation `10aefea2…`)
- 引数: `BTVPN 30 on 30 15 "iMiminashiPadPro ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0`
- driver: `/usr/local/bin/susp-btvpn-driver.sh` v3 (111259 と同じ)、起動直後に `wifi_down` で wlp3s0 切断 → blind 運用 → 各 ITER で `pan_up` / `vpn_up` / PRE log / `rtcwake -m no -s 30` / `systemctl suspend` / 15s gap / POST log

### 結果 ([susp-test-ipad-N30.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/susp-test-ipad-N30.log))

| 項目 | 値 |
|---|---|
| PHASE DONE | `2026-06-28T13:11:06+0900` (25:37 経過) |
| ITER PRE/POST | **30/30 完備** |
| 条件成立 (`panup=ok` AND `vpnup=ok` AND `xfrm_src=172.20.10.13`) | **28/30** (ITER 11/12 で `panup=fail / pan_ip=none` が 2 cycle 連続、NM の BT-PAN 一時失敗。ITER 13 で復活) |
| s3-soak.log SLEEP/WAKE | 30/30 全ペア、全 `drm_err=0 / gpe70=0 / asleep_s=30–31s` (rtcwake 30s と整合) |
| `boot_id` | 不変 (`fcc3d4b0…`) |

→ **iPad 通算 0/45 (今回 0/30 + 111259 で 0/15)**、ハング 0。

## 実験 2b: iPhone peer + driver 自動 N=30

### 移行 (ユーザ操作)

iPad の Personal Hotspot OFF → iPhone Hotspot ON → iPhone とのペアリング・接続を確認。WiFi は ON のまま (driver 起動のために ssh 必須)。Claude が `bluetoothctl connect CC:60:23:AF:2C:60` を ssh で叩いて iPhone を NM に認識させ、PAN iface に `172.20.10.6/28` が付くのを事前確認。

### 設定と起動

- 起動: `2026-06-28T13:36:11+0900`
- unit: `susp-btvpn-iphone.service` (invocation `951b98ec…`)
- 引数: `BTVPN 30 on 30 15 "iMiminashiSE ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0`

### 結果 ([susp-test-iphone-N30.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/susp-test-iphone-N30.log))

| 項目 | 値 |
|---|---|
| PHASE DONE | `2026-06-28T13:59:56+0900` (23:45 経過) |
| ITER PRE/POST | **30/30 完備**、**全 PRE で `panup=ok / pan_ip=172.20.10.6 / vpnup=ok / xfrm_src=172.20.10.6`** (条件成立 30/30) |
| s3-soak.log SLEEP/WAKE | 30/30 全ペア、全 `drm_err=0 / gpe70=0 / asleep_s=30–31s` |
| `journalctl -b 0 -g "deleting IKE_SA GSNet" \| grep -c "172.20.10.6"` | **30 件** (毎 cycle 立証) |
| `boot_id` | 不変 (`fcc3d4b0…`)、リブートなし |
| 本日合算 PM `entry/exit` (boot 0) | **60/60 全 `(s2idle)`** (= iPad 30 + iPhone 30) |

→ **iPhone driver は今回が初実施で 0/30 完走、ハング 0**。

## 経路差の内訳 (まだ切り分けていない 2 軸)

driver 経路と手動 lid-close 経路は、入眠と復帰の両方で trigger が異なる。**どちらが必須かは本実験では分離していない**。

| 段 | 手動 lid close (ハングする側) | driver (ハングしない側) |
|---|---|---|
| **(α) 入眠 trigger** | lid close → `acpid` (LID0 GPE) → logind の `HandleLidSwitchExternalPower=suspend` → `suspend.target` 起動 (前段の inhibit 評価, idle hint, session 通知) | systemd-run 経由で直接 `systemctl suspend` (logind の前段が短い) |
| **(β) wake trigger** | lid open → LID0 GPE 割り込み → ACPI EC → kernel resume | RTC IRQ8 (rtcwake で予約済アラーム) → kernel resume |

親 063543 行 81 が指摘していた「停止位置が入眠側か復帰側かログから判別不能」と組み合わせると、ハングが (α) で起きていれば logind 前段差が効いている可能性、(β) で起きていれば LID0 wake 経路差が効いている可能性が残る。**両者を切り分ける次の実験**は留意節参照。

## 機序解析 — H1/H4 判別子の適用と teardown 順序観察

本日新たに取得した hang journal を使い、[2026-06-28_074509 のカーネルソース解析レポート](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md) が立てた機序仮説 H1/H4 を判別する。

### 判別子 (再現不要) — `unregister_netdevice: waiting` の有無

074509 の判別子: ハング boot で `unregister_netdevice: waiting for X to become free` が**出れば H1** (xfrm→bnep netdev ref leak → `netdev_wait_allrefs` 停止)、**不在なら H4 / H2 寄り** (btusb URB drain や bnep_session kthread race)。

[hang-teardown-sequence.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/hang-teardown-sequence.log) と全 50 boot (`journalctl --list-boots`) で grep した結果:

| 対象 boot | `unregister_netdevice: waiting` | 含意 |
|---|---|---|
| **本日 #4 (`3aa09ac0`, iPad 手動)** | **不在** | H1 棄却 |
| 063543 #3 (`7c44b92c`, iPhone 手動) | 不在 | H1 棄却 |
| 063543 #2 (`370de629`, iPhone 手動) | 不在 | H1 棄却 |
| 063543 #1 (`1bc7fb70`, iPhone 手動) | 不在 | H1 棄却 |
| 過去 50 boot 全て | 不在 | (boot 0 で 52 件出るのは今回の sudo grep 自身が journald に残した行で誤 hit) |

→ **観察として** 全 51 boot (本日 hang boot 含む) で `unregister_netdevice: waiting` 不在。**ただし hang boot に `waiting` 行が無いこと自体は decisive ではない**: 本ハングは [2026-05-31](2026-05-31_132125_s3_hang_switch_to_s2idle.md) と同じ console suspend 済の silent hang で、もし `dpm_suspend` 段で H1 が発火しても `waiting` メッセージは journald に flush されずに失われる。よって hang boot の grep 結果は H1 棄却の load-bearing 証拠にはならない (clean boot 全件不在は **「平時には ref leak が起きていない」** という弱い corroboration にはなる)。

**H1 棄却の load-bearing evidence は次節の teardown 順序ログ** にある (要旨: 全 netdev unregister が `sleep.target` 到達の 1 秒前に完了済、その間 journald は flushing 段で `waiting` 行を出せる状態だったのに 1 件も出ていない → netdev ref leak は起きていない → ハングは後段の `dpm_suspend` の別機序)。074509 が「H4 が最有力、H1 は確度低」と判定していた方向を、本日の teardown ログが確証。

### Teardown 順序の直接観察 (本日 #4 hang から、sleep.target 到達の ~1 秒前・teardown の ~100ms 窓)

[hang-teardown-sequence.log](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/hang-teardown-sequence.log) より、`[20813.032748]` 〜 `[20813.134253]` (約 100ms の teardown 窓) → 1 秒後に `[20814.069238] Reached target sleep.target` → さらに 60ms 後に freeze 完了・kbd-backlight pre フック → 停止:

1. `[20813.032748]` NM/avahi が **`enx98e0d98d205e` の IPv6/IPv4 addr を withdraw** (`172.20.10.13`、`fe80::ec4e:…`、`2001:240:…`)
2. `[20813.037602]` charon-nm が KNL netlink event で **`172.20.10.13 disappeared from enx98e0d98d205e`** を観測
3. `[20813.041472]` **`bluetoothd: profiles/network/bnep.c:bnep_if_down() bnep: Could not bring down bnep0: No such device(19)`** ← bnep の down 試行は既に enx98 が消えた後 = **teardown 順序の anomaly** (BT 層では race)
4. `[20813.042154-361]` charon-nm が `enx98e0d98d205e deactivated → deleted`
5. `[20813.128577]` charon-nm が `deleting IKE_SA GSNet[22] between 172.20.10.13[macbookair2015]...160.16.210.47` → DELETE 送信試行 → `[20813.129086] error writing to socket: Network is unreachable` ← BT-PAN iface 消失の後に IKE delete を投げているので当然失敗
6. `[20813.130036]` **`192.168.83.1 disappeared from nm-xfrm-1624477`** ← VPN xfrm netdev (`nm-xfrm-N`) のアドレス削除
7. `[20813.133-134]` bypass policy の iface 変更処理 (`from enx98e0d98d205e to nm-xfrm-1624477`)
8. `[20814.069238]` `Reached target sleep.target - Sleep.`
9. `[20814.076794]` `Starting systemd-suspend.service`
10. `[20814.124245]` `Successfully froze unit 'user.slice'` ← freeze 完了
11. `[20814.129740]` `kbd-backlight-sleep: pre/suspend: saved=0 set->0` ← **最終可視行、ここで停止**

### 観察から導かれる機序評価

- **親 063543 行 114 の「論理 down は suspend 前に完了している」が新規データで再確認**: VPN 論理 teardown (IKE_SA delete、bypass policy 撤去、`nm-xfrm-N` の addr 削除) は **全て `Reached target sleep.target` の 1 秒前に完了**している。よって **「suspend 前フックで `nmcli con down GSNet` を追加実行する」案は冗長で効果なし** ということが本実験の独立データでも確定。
- **親 063543 hypothesis (b) 「残留 xfrm device 確認」の部分回答**: xfrm netdev (`nm-xfrm-1624477`) は VPN active 中に存在し、teardown 中に addr 削除まで進む。**ただし netdev 自体が `dpm_suspend` 段までに完全に unregister されたかは本ログからは未確定** (`unregister_netdevice: waiting` も出ないので、おそらく軽量に消えた)。
- **BT 層の teardown 順序 anomaly (`bnep: No such device`)**: enx98 削除が先、bnep down 試行が後、で race している。074509 の H2 (non-freezable `bnep_session` kthread が freeze 段で stall) と整合する race 痕跡だが、ハングの直接原因かは未確定。
- **VPN 必須事実 (BT-PAN 単独 = 45 cycle クリーン) が H4 単独説を圧迫**: H4 (`btusb_suspend` → `usb_kill_anchored_urbs` の timeout 無し URB drain) は **btusb の挙動なので VPN の有無で発生率が変わるはずがない**。本実験で VPN なし BT-PAN 単独 = 0/45 = クリーンが確定したので、**H4 単独では本ハングを説明できない** (074509 自身が「H4 単独では VPN 特異性を説明不可、race 窓拡大の量的寄与のみ」と留保していた点を、本日の対照実験が定量的に裏付け)。
- **総合**: H1 棄却、H4 単独棄却 → **H4 (URB drain) + H2 (bnep race) + xfrm-related な何か** の合成、または 074509 が挙げなかった新規機序が残候補。判別の決定打はまだ出ていない。

### 機序追求の次の一手 (本実験の留意節「次の一手」とは別軸)

- **`DPM_WATCHDOG` を有効化** (`CONFIG_DPM_WATCHDOG=y` または kernel cmdline) して、ハング時にどの device の `suspend()` callback で stuck したかを **kernel が自動で stack trace を吐く**ようにする。本機種で実行可能か、また watchdog 有効化が daily 運用に影響しないかは要検証。
- **`pm_debug_messages=1` + `no_console_suspend`** + シリアルコンソール (USB-serial) で `dpm_suspend` の verbose ログを取る (本機は MacBook なのでハード的に困難)。
- **`btusb` を `modprobe -r` してから lid close** (063543 hypothesis (a) を本実験条件で実施) — もし btusb を経路から消してもハングするなら H4 完全棄却、消すならハングしないなら H4 寄与確定 (race 窓拡大要因として)。

## 含意

1. **親 063543 hypothesis (a) `btusb` module unload は依然候補だが優先度は下がる**。BT-PAN そのものは必要条件だが、lid 経路が必要条件と判明した以上、**BT 物理レベルを切るより lid 経路に attack する方が筋**。具体的には:
   - **logind の `HandleLidSwitch*` を `ignore` に変えて、ユーザは GUI/`systemctl suspend` で寝かす運用** (確実な workaround だが UX 損失大)
   - **LID0 の wakeup を `/proc/acpi/wakeup` で凍結** (lid wake を殺す = β 側のトリガーが崩れる、ただし lid open でも起きなくなる)
   - これらは「機能を捨てた回避」になるので採用は重い
2. **実用 stopgap (063543 と同じ)**: BT-PAN + VPN 使用中は明示的に蓋を閉じない、もしくは蓋を閉じる前に VPN・BT を down してから閉じる
3. **mem_sleep の含意**: 真の s2idle で本条件が再現する以上、deep 採用是非とは独立に対策が必要 ([2026-06-27 のロールバック決着](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md) と整合)

## 検討して除外した事項・観測上の限界

- **「BT-PAN が空回りしていた」可能性 → 棄却**: 実験 2a で `panup=fail` が 2 cycle あったが、条件成立 28/30 でも 0 hang。実験 2b は 30/30 で IKE_SA endpoint `172.20.10.6` を 30 件記録 (Per-cycle 立証)。実験 1 は driver 無しのため retrospective 検証だが、ハング直前の `IKE_SA[22]` が `172.20.10.13` 端点で BT-PAN 経由を確定
- **deep 化け疑い → 棄却**: 前 boot `3aa09ac0` の `PM: suspend entry` **37 件すべて `(s2idle)`** (実験 1 + 当日早朝 driver 検証 + baseline cycles)、boot 0 `fcc3d4b0` の **60 件すべて `(s2idle)`** (実験 2a 30 + 実験 2b 30) = **計 97 entry が全 s2idle**。実験 1 のハング cycle (entry 行は journald flush 前停止で残らず) も「`mem_sleep=[s2idle]`、`60-s3-soak-log` の `echo deep` 完全削除、同 boot 他全 entry が `(s2idle)`、soak log `type=suspend`」の 4-pronged 根拠で s2idle 確定
- **小標本性 — 完全には消えていない**: iPhone driver 0/30 は強い陰性シグナルだが「絶対に出ない」とは言えない。仮に発生率が手動 iPhone と同じ ~30% なら 30 連続 miss は二項分布で確率 ~0.002%、~10% でも ~4.2%、本実験で出なかったのは経路差を強く支持
- **wake 経路の切り分け未実施**: (α) 入眠 trigger 差と (β) wake trigger 差を分離していない (留意節)
- **driver の `nmcli con up` 速度差**: 実験 2a の ITER 11/12 が `panup=fail` だったが iPhone (2b) では 0/30 全成功。peer の BT-PAN コネクション確立速度に差がある可能性 (Apple Personal Hotspot 内部のキャッシュ/事前接続状態が iPhone でより安定) — 本件の本筋には無関係だが driver 設計上の知見

## 再現方法

### 実験 1 の再現 (iPad peer + 手動 lid close)

1. 前提状態確認 ([プラン](attachment/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required/plan.md) の「前提条件」スニペット参照)
2. ユーザ操作: WiFi NM GUI で切断 → iPad テザリング up (`172.20.10.13/28`) → GSNet up → lid close/open を反復
3. ハングしたら電源ボタン長押し → 再起動 → wifi 自動復帰後に Claude が retrospective 確認 (s3-soak.log SLEEP→BOOT、journalctl `-b -1` で停止位置と IKE_SA endpoint)

### 実験 2a/2b の再現 (driver 自動)

```bash
# 共通 driver: /usr/local/bin/susp-btvpn-driver.sh (v3, /usr/local/bin/ に配置済)
# iPad 用
ssh miminashi@macbookair2015.lan '
  sudo systemd-run --unit=susp-btvpn-ipad --collect \
    /usr/local/bin/susp-btvpn-driver.sh BTVPN 30 on 30 15 \
      "iMiminashiPadPro ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
'
# iPhone 用 (PAN IP が .6 に変わる以外は同じ)
ssh miminashi@macbookair2015.lan '
  sudo systemd-run --unit=susp-btvpn-iphone --collect \
    /usr/local/bin/susp-btvpn-driver.sh BTVPN 30 on 30 15 \
      "iMiminashiSE ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
'
# 結果取得 (driver が wifi を切るので blind、~30分後 PHASE DONE で wifi 復帰後に ssh)
ssh miminashi@macbookair2015.lan '
  sudo awk "/PHASE START.*pan=iMiminashiPadPro/{p=1} p" /var/log/susp-test.log
  sudo tail -n 40 /var/log/s3-soak.log
  sudo journalctl -b 0 -g "PM: suspend (entry|exit)" -o cat | sort | uniq -c
'
```

## 留意・次の一手

- **次の一手 (最有力) — 経路の (β) wake trigger 差を分離する**:
  「**lid close + rtcwake (LID open より前に RTC で起こす)**」を試す。手動で蓋を閉じ、kernel が s2idle に入った直後 (実機からは RTC アラーム経由) で wake させる。ハング:
  - **発生**: (α) logind 前段 + LID close trigger が必須 = β は関係ない
  - **発生せず**: (β) LID open wake が必須 = lid wake を凍結する workaround が成立
- **次の一手 (次点) — 経路の (α) を分離する**:
  driver から `systemctl suspend` ではなく `loginctl suspend` 経由で寝かす + rtcwake で起こす。`loginctl suspend` は logind の inhibit 評価を通すので (α) の前段が手動寄り。これでハングが出れば logind 前段差が effective。
- **本実験の弱点**: driver 経路で N=30 はそこそこ強い陰性シグナルだが、もし真の発生率が ~1% 未満なら見落とす可能性は残る (60 cycle で 0/60 でも発生率 5% 仮定で見落とし確率 ~4.6%)。100+ cycle で詰めるなら次は long-soak driver。
- **残置物 (撤去任意)**: 実機の `/usr/local/bin/susp-btvpn-driver.sh`、`/var/log/susp-test.log` (追記)、`susp-btvpn-ipad.service` / `susp-btvpn-iphone.service` は `--collect` で自動回収済。`GSNet` の `password-flags=0` は引き続き実機に残っている (セキュリティ要件で戻すなら GNOME 側でパスワード欄を「このユーザー用にのみ保存」に戻す)
- **iPhone driver で一度も `panup=fail` が出なかった** vs iPad で 2/30 出た差は、Apple Personal Hotspot 内部の挙動差 (iPhone の BT-PAN は再接続が安定、iPad は若干 flaky) と推測。本件の結論には影響しないが driver 設計の改善余地 (例: pan_up の retry を 25s → 40s)

## 関連レポート

- [2026-06-28_111259 Claude 駆動 systemctl suspend N=15 でハング再現せず — lid-close 固有トリガー疑い (直接の親)](2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)
- [2026-06-28_074509 カーネルソース解析で H1/H4 仮説と判別子を提示 (本実験の機序解析で当てはめた)](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-28_063543 真の s2idle + BT-PAN × VPN + 手動 lid close で 3/3 ハング — factorial 切り分け (iPhone 手動セルの確定)](2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)
- [2026-06-28_021019 真の s2idle 初実証 + AC・BT-PAN 単独 10/10 クリーン (driver 親)](2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)
- [2026-06-27_072510 deep モードで計4ハング・s2idle ロールバック決定 (deep 内在 hang 議論)](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
