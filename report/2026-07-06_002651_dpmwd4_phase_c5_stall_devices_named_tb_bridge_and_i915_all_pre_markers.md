# ハング停止点のデバイス実名を取得 — Thunderbolt ブリッジと GPU の 2 署名に二極化 (Phase C-5 / dpmwd4)

**サマリ**: resume 側の pm_trace をデバイス書込みに置換した dpmwd4 で hang を 4 回再現し、4 回とも停止境界のデバイス実名の取得に成功。停止点は **(A) Thunderbolt 2 ブリッジ downstream ポートの noirq resume 入口** (2 回、06:03.0 / 06:06.0 の兄弟ポート) と **(B) i915 GPU (0000:00:02.0) の main resume 入口** (2 回、完全同一 decode) の 2 署名に二極化した。4/4 すべて **entry (pre) marker** であり、callback 完了 (exit) まで到達した停止例は無い。監視機構 (DPM watchdog / hung_task / NMI hardlockup / softlockup、全 panic arm) は正規の判定窓を確保した 3 hang で今回も全沈黙。

- **実施日時**: 2026年7月5日 20時頃 〜 7月6日 00:27 JST
- **位置づけ**: [2026-07-05_185344](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md) (Phase C-4) の引継ぎ第 1 候補 (dpmwd4 = デバイス実名の取得) を実施。C-4 で「resume noirq/early 段のデバイス境界」まで絞り込んだ停止点に、**実名が付いた**。

## 概要

前回 (C-4) までで、BT テザリング + VPN 使用中の lid close ハングは「スリープと wake 自体は成功し、デバイスを順に起こしていく resume 処理の途中の境界で止まる」ことが分かっていた。しかし前回の記録方式は容量の制約でデバイス名を捨てており、「どのデバイスの境界か」が最後の未知として残っていた。

今回は記録方式を作り替えた。resume 側の記録点が従来書いていた「ソース上の位置」をやめ、「どの段階のどの境界で、どのデバイスを扱っているか」を 1 つの値に詰めて RTC に書くようにした (dpmwd4)。書込み回数は前回と同一なので、計測による系への摂動は増えていない。較正は実スリープなしの往復試験、再起動越えの読み出し試験、スリープ中に強制電源断する予行の 3 段階で事前に実弾検証し、さらに本番前の成功 cycle で「正常完走時の最終値」の形も確認してから臨んだ。

結果、ハングを 4 回再現し、4 回とも停止境界のデバイス実名が取れた。内訳は綺麗に二極化した。2 回は Thunderbolt 2 コントローラ (Falcon Ridge) のダウンストリームブリッジ 2 ポート (06:03.0 と 06:06.0、いずれも配下が空のホットプラグ域) の noirq resume 入口。残る 2 回は内蔵 GPU (i915, 0000:00:02.0) の main resume 入口で、この 2 回は RTC の値まで完全に同一だった。つまり停止はランダムな場所で起きているのではなく、この機体の resume 経路上の特定の 2 箇所に集中している。

もう 1 つの発見は、4 回すべてが「入口 (entry) マーカー」で止まっていたことである。デバイス処理の完了側 (exit) で止まった例は 1 つもない。入口マーカーの直後にあるのは「上位デバイスの完了待ち」と「callback 本体」だが、callback が 60 秒を超えれば DPM watchdog が、完了待ちで 2 分を超えて眠れば hung_task がそれぞれ panic するよう仕掛けてあり、どちらも沈黙した。古典的な「callback が長い」「待ちで固まる」のどちらとも矛盾する、時計や NMI の土台ごと止まるような「静かな停止」という C-4 の描像が、場所の実名付きで補強された形になる。

また、ハング中に電源ボタンを短押しすると画面のバックライトだけが点灯する (映像は出ない) ことをユーザが観察した。ハードウェアの一部は生きて応答しており、C-4 で 1 例あった「電源断直前まで記録が書き続けられていた」事象とも整合する。完全な即死ではなく、部分的に生きたまま先へ進めない状態と見られる。

停止点に実名が付いたことで、次の一手は「もっと詳しく観測する」から「名指しで介入して因果を試す」に移れる。Thunderbolt ブリッジの電源管理を切る、i915 の省電力機能を制限するといった介入で hang 率が変わるかを検証できる段階になった。実用上の回避策は引き続き「WiFi radio を常時 on にしておく」ことで変わらない。

## 添付ファイル

- [実装プラン](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/plan.md)
- [dpmwd4 パッチ (4b279c26a)](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/dpmwd4-resume-device-markers.patch)
- [decode チートシート (site 18 + marker 6)](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/cheatsheet-dpmwd4.txt)
- [decode ヘルパ decode.py (marker/devlist 照合対応)](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/decode.py)
- [デバイス名スナップショット (674 名)](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/devlist-dpmwd4-boot.txt)
- [セッション証跡 (per-boot decode / PRE-POST / src-IP gate / watcher log)](attachment/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers/c5-evidence-raw.txt)

## 前提・目的

- **背景**: C-4 (185344) で停止域 = 「wake 成功後の dpm resume noirq/early 段のデバイス境界」(main.c:627/700/836) と確定。dpmwd3 の firmware-safe encoding は容量制約 (user 16 × file 397 = 6352 ≤ 8064) で dev チャネルを廃止していたため、デバイスが匿名のままだった。
- **目的**: dpmwd4 (resume 側 site 書込み → phase 別 pre/post デバイスマーカーへの置換) で hang 再演時に停止境界のデバイス実名を取得する。
- **役割分担**: ビルド・デプロイ・arm・回収・解釈 = Claude (ssh)、テザリング・lid cycle・強制電源断・WiFi 復旧 = ユーザ。

## dpmwd4 の設計

- **user field の分割**: user 0-9 = 従来の site 書込み (file = sdbm(line, path) % 397)、**user 10-15 = デバイスマーカー** (file = sdbm(7919, dev_name) % 397):
  - 10/11 = device_resume_noirq entry/exit、12/13 = device_resume_early entry/exit、14/15 = device_resume (main) entry/exit
- main.c の resume 側 6 TRACE 点をマーカーに置換 (site 書込みは削除)。**RTC 書込み回数は dpmwd3 と同一 (2 回/device/phase) = 摂動増なし**
- 副作用対応: s2idle site の user 10/11/12 → 7/8/9 に付替え、`generate_pm_trace()` に user ≤9 clamp (error 負値のマーカー偽装防止)
- boot 時 decode: marker なら dpm_list を hash 照合して `hash matches` で実名列挙 (旧 show_dev_hash 復活、mod 397)。`/sys/power/pm_trace_dev_match` も復活
- encoding 本体 (year=2027 署名、min/sec=0 で tick 猶予 60 分) は dpmwd3 のまま。容量検算 15+16×396=6351 < 8064
- commit `4b279c26a` (dpmwd3 7c86c3994 の上に 1 commit)。site hash 衝突ゼロを事前計算で確認 (main.c の行シフトで suspend 側 site hash も変わるため cheatsheet 全再生成)

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd4** (`CONFIG_PM_TRACE_RTC=y`、cmdline `panic=15`)
- ビルド機: 開発機 (12 コア)、`src/linux-6.12.y` HEAD `4b279c26a` (82 commits)、`make -j12 LOCALVERSION= bindeb-pkg` ~35 分、エラーゼロ
- スリープ: `[s2idle]`、`intel_pch_thermal.delay_cnt=300`、hooks: 50/58/59/60/70 (C-4 と同一)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28` (enx98e0d98d205e)、VPN: GSNet (strongSwan IKEv2、SA peer 160.16.210.47)、WiFi: `wl` loaded + `nmcli radio wifi off`
- **PCI トポロジ (今回の主役)**: `05:00.0-[06-6b]` = Falcon Ridge TB2 upstream、配下 `06:03.0-[08-38]` / `06:06.0-[6b]` 等の downstream ポート (いずれも配下バス空 = ホットプラグ域)。`0000:00:02.0` = HD Graphics 6000 (i915)

## 検証ゲート (全通過)

| ゲート | 内容 | 結果 |
|---|---|---|
| (a) | 起動 10 項目 (kernel/s2idle/pm_trace/wl/panic=15/delay_cnt/pstore 空/hooks 等) | 10/10。実時刻 RTC boot は `no trace data (year 2026)` と正しく棄却 |
| (t1) | pm_test=devices + pm_trace=1 で 1 cycle → hwclock 生値 offline decode | `Magic 15:1` = post-main marker + `device:4e` 一致 (成功 cycle の期待形) |
| (t2) | 値の warm reboot 生存 + kernel 自己 decode | `Magic 15:1` + `device marker: device_resume exit` + `acpi device:4e: hash matches`。`pm_trace_dev_match`=acpi |
| (t3) | 合成 hang (kbd/ff_pwr_btn/LNXPWRBN wake 無効化 → suspend → 強制電源断) | `Magic 3:332 → suspend.c:152` を正確に decode (dpmwd4 でも不変の site、電源断経路の実弾検証) |
| (t4) | 実 s2idle smoke cycle の最終値 (arm 冒頭で実施) | `Magic 15:1` + device:4e — 全 marker 書込みを含む実 cycle がスリープを壊さず、成功時最終値が期待形であることを確認 (観測できるのは最終値のみで、10-14 の個別発火は同一経路であることによる担保) |

## hang 再現結果 (デバイス実名)

| hang | 有効cycle | decode | marker | デバイス (dpm_list 照合) | 放置 | 経過 (最終TRACE→読取) |
|---|---|---|---|---|---|---|
| #1 | 3/3 | `Magic 10:334` | **noirq entry (pre)** | **pcieport 0000:06:03.0** (TB2 downstream、単独一致) | 10 分 | 12:15 |
| #2 | 2/2 | `Magic 14:355` | **main entry (pre)** | **pci 0000:00:02.0 (i915)** ほか衝突 2 (LNXSYBUS:00 / LNXCPU:06、callback 実質空で除外可能) | ~5 分 | 07:33 |
| #3 | 2/2 | `Magic 10:139` | **noirq entry (pre)** | **pcieport 0000:06:06.0** (TB2 downstream、#1 の兄弟) ほか衝突 2 (pci_bus 0000:03 / device:63、同上除外) | ~1 分 | 00:57 |
| #4 | 3/3 | `Magic 14:355` | **main entry (pre)** | **#2 と完全同一** (i915) | 6 分 | 07:19 |

1. **二極化**: 署名 (A) = TB2 downstream ブリッジの noirq entry (#1/#3、兄弟ポート)、署名 (B) = i915 の main entry (#2/#4、RTC 値まで同一)。停止はランダム位置ではなく resume 経路上の特定 2 箇所に集中。
2. **4/4 すべて pre (entry) marker**。exit marker で終わった停止例なし → 停止は「デバイス境界を越えた直後」ではなく「デバイスに取り掛かった直後」で起きる。
3. **監視機構の全沈黙を追認** (判定窓が有効な #1=10 分 / #2=約 5 分 / #4=6 分。#3 は放置 ~1 分のため沈黙判定から除外。**#2 の放置時間はユーザ申告が無く、経過 07:33 から電源断・boot 所要 ~2 分を引いた逆算推定**である点に留意): DPM watchdog 60s / hung_task_panic 120s / NMI hardlockup (panic=1) / softlockup — pstore 全 4 回空。entry marker 直後の古典的停止様式 2 つ (callback 長時間実行 → watchdog が捕捉するはず / dpm_wait_for_superior の D 状態滞留 → hung_task が捕捉するはず) の**双方が反証**され、「タイマ/NMI の土台ごと止まる静かな停止」(C-4 の残謎) が場所実名付きで強化された。
4. **新観察 (hang #4)**: ハング中の電源短押しで**バックライトのみ点灯** (映像なし) — EC/ハードは部分的に応答。C-4 hang #3 の「電源断直前まで TRACE 継続」と整合する「部分的に生きた停止」の傍証。
5. **async resume の解釈上の注意**: 最終書込み = 全体停止時点で最後に活動していた thread の位置であり、単独犯の証明ではない (計画時から既知の留保)。ただし 2×2 の収束は偶然の一様分布とは考えにくい。

## 統計への影響 (摂動 tag 付き)

- **本セッション: hang 4/10 有効 cycle = 40%** (arm 別: 3 cycle 中 1 / 2 中 1 / 2 中 1 / 3 中 1)。C-4 の dpmwd3+pm_trace arm (4/9 ≈ 44%) と一致し、**pm_trace=1 摂動下の高 hang 率が再現**。歴史 pool (非摂動 7.1%) へは合算せず別 arm として記録。
- **摂動 pool 累計 (参考値)**: dpmwd3 と dpmwd4 は RTC 書込み回数が同一 (2 回/device/phase) で摂動量は同等とみなせるため、pm_trace=1 arm の合算は **8/19 ≈ 42%**。非摂動 7.1% との乖離は 2 セッション連続で安定しており、偶然 (C-4 解釈候補 iii) の線はさらに弱まった。
- **「arm 直後の初回 lid close 濃縮」仮説 (C-4 論点 ii) への反証データ**: 今回 4 hang とも arm 後 2〜3 cycle 目で発生し、初回 cycle の hang は 0/4。C-4 までの n=3 の濃縮観察は偶然だった可能性が高まった。
- BT_PAN_VALID: **有効 10 cycle 全件で src 172.20.10.13 + xfrm SA (→160.16.210.47) を確認** (70-h4-probe source-IP gate)。hang 帰属は 4 件とも unpaired PRE で同定 (1783261609 / 1783263011 / 1783263801 / 1783264326)。

## 実験タイムライン (JST)

| 日時 | 内容 |
|---|---|
| 7/5 20:00 頃-20:41 | Phase P: dpmwd4 パッチ作成・hash 衝突ゼロ確認・decoder 往復自己テスト・commit 4b279c26a・ビルド開始 (20:41) |
| 7/5 20:41-21:18 | ビルド完走 (エラーゼロ)・scp・dpkg -i (dkms wl 自動ビルド)・grub-reboot ワンショット+sync → dpmwd4 起動 |
| 7/5 21:19-21:21 | ゲート (a) 10/10・saved default を dpmwd4 に変更+sync・デバイス名スナップショット (674 名) |
| 7/5 21:22-21:25 | (t1) pm_test cycle → Magic 15:1 + device:4e / (t2) warm reboot 生存 + kernel 自己 decode + pm_trace_dev_match |
| 7/5 21:26-21:37 頃 | (t3) 合成 hang → 強制電源断 → `3:332 → suspend.c:152` 一致 (経過 06:39)。時刻復旧 |
| 7/5 21:38-21:40 | Phase C-5 arm (sysctl×3 / NM / watchers / pm_trace=1、SESSION epoch 1783255126 = 21:38:46) |
| 7/5 22:00-22:07 | smoke×2 (22:00:26 / 22:06:48、WIFI_SRC) — 1 本目の最終値で (t4) 通過 |
| 7/5 22:10-22:20 頃 | BT-PAN + GSNet 確立 (SA ×2 確認) → radio off (wake は電源短押し — 本機は lid open/キーでは s2idle から復帰しない) |
| 7/5 23:19-23:26 | 有効 cycle 開始 (23:19:54) → cycle 3 (23:26:49) で **hang #1** → 10 分放置 → 電源断 → decode `10:334` = **pcieport 06:03.0 noirq entry** |
| 7/5 23:43-23:50 | 再 arm → cycle 2 (23:50:11) で **hang #2** → decode `14:355` = **i915 main entry** |
| 7/6 00:00-00:03 | 再 arm → cycle 2 (00:03:21) で **hang #3** (放置 ~1 分) → decode `10:139` = **pcieport 06:06.0 noirq entry** |
| 7/6 00:08-00:12 | 再 arm → cycle 3 (00:12:06) で **hang #4** → 6 分放置 (バックライト観察) → 00:18 頃電源断 → decode `14:355` = **#2 と同一** |
| 7/6 00:24-00:27 | テアダウン (pm_trace=0 / sysctl 0 / watchers 停止 / NM 平常化 / RTC 復旧)・証跡回収・本レポート |

## 証拠と検証

- **decode の信頼性**: encode/boot 越え/電源断経路をゲート t1-t4 で事前実弾検証。年署名は実時刻 boot の棄却実績あり。hang #2/#4 の同一値は「間に別値 (#3 の 10:139) と NTP 復旧・clean cycle 2 回を挟む」ことで stale 値の可能性を排除、経過 min:sec (07:33/07:19) も放置時間と整合。
- **hash 衝突の扱い**: mod 397 で 674 デバイス名 → 平均 1.7 名/hash。kernel が dpm_list 全走査で全一致を列挙し、「noirq/main callback を実質持たない擬似デバイス」(LNXSYBUS/LNXCPU/pci_bus/device:63) を除外する運用で単独候補化。#1 は単独一致。
- **罠の再確認**: hang PRE の帰属は「POST とペアにならない unpaired PRE」で同定 (C-4 確立)。boot 側 journal 境界とも整合。
- 証跡ファイル: 添付 c5-evidence-raw.txt (per-boot decode 行 / PRE-POST 全リスト / src-IP gate 10/10 / watcher log 末尾)。実機 /var/log/h4-probe に SESSION-C5-START.marker (epoch 1783255126)、cycle-watch-c5.log、vpn-watch-c5.log 残置。vpn-watcher は 20 秒毎に xfrm SA 数を記録しており、各 hang cycle 直前まで `xfrm=2` (SA 生存) が連続していることを裏付ける。

## 運用知見 (C-5 で新たに確定・訂正した事項)

1. **本機の s2idle wake 手段は電源ボタン短押しのみ**。lid open では復帰しない (既知、gpe70 マスク) が、**内蔵キーボード押下でも復帰しない** (`/sys/bus/usb/devices/1-5/power/wakeup=enabled` にもかかわらず)。**C-4 レポートの「lid open/キーで wake 自体は成功」という記述と食い違う** — C-4 の当該記述は decode 結果 (wake 成功) からの推論に wake 手段の想定を重ねたものだった可能性が高く、wake 手段の直接記録としては本レポートの観察 (電源短押しのみ) を正とする。hang 判定基準も「電源短押しで復帰しないこと」に更新。
2. **hang 復旧 boot では hwclock 生値の回収は間に合わない**。4 回とも、ユーザの WiFi 復旧後に ssh した時点で RTC は NTP + systohc により実時刻へ上書き済みだった。**decode の正は kernel が boot 極早期 (core_initcall) に読んで journal に残す「PM: RTC time / Magic number」行**であり、これは常に安全。C-4 手順の「hwclock -r 生値を即時回収」は、ネットワークが即復帰しない hang 復旧経路では実質不可能で、成功 cycle 直後の較正 (t1/t4) でのみ有効な手段だったと整理する。
3. **hwclock -r はローカルタイム表示** (`+09:00` 付き)。offline decode (decode.py) には UTC 生値が必要なので **-9h 換算してから渡す** (t1 で踏みかけた罠)。journal の RTC 行は UTC 生値なのでそのまま使える。
4. **GSNet は autoconnect=yes を設定しても BT-PAN 復帰後に自動起動しなかった** (本セッション 4 arm すべてで手動 `nmcli con up GSNet` が必要)。022842 手順の autoconnect 設定は VPN については実効性がなく、arm チェックリストに「SA ×2 確認後に radio off」を明示する (再現方法に反映済み)。
5. 合成 hang (t3) 中の見た目は実 hang と同一 (電源短押しにも無反応 — wake 無効化の効果) であり、**t3 実施時はユーザにその旨を事前共有しておくこと** (本セッションで「ハングでは?」の混乱が 1 回発生)。

## 結論

1. **Phase C-5 の主目的 (停止境界のデバイス実名) を達成**。3 セッション沈黙 → C-4 で段特定 → 本セッションで実名特定、と正の証拠の解像度が段階的に上がりきった。
2. 停止点は **(A) Falcon Ridge TB2 downstream ブリッジ (06:03.0/06:06.0) noirq entry** と **(B) i915 (00:02.0) main entry** の 2 署名に二極化 (各 2 回)。
3. **4/4 pre marker + 監視全沈黙**により、「callback 長時間実行」でも「completion 待ち D 滞留」でもない停止様式が確定的になった。タイマ/NMI 基盤ごと停止する機序 (深い C-state からの復帰不全、クロックゲーティング等) が有力仮説に浮上。
4. 摂動下 hang 率 40% は C-4 の 44% を再現。「arm 初回 cycle 濃縮」仮説には反証 (0/4)。
5. **実用対策は不変**: 常時 WiFi radio-on 運用 (歴史 pool 0/52 clean)。

## 次セッション引継ぎ (Phase C-6 候補)

1. **名指し介入 (推奨、リビルド不要)**: 停止点に実名が付いたので観測から因果検証へ移行できる。候補: (i) `pcie_port_pm=off` boot param で TB ブリッジの PM を止めて hang 率/署名の変化を見る、(ii) TB 側を D3 に落とさない (`/sys/bus/pci/devices/0000:06:*/power/control` 等)、(iii) i915 側 (`i915.enable_dc=0` 等)。署名 (A)/(B) のどちらかが消えるだけでも機序の切り分けが進む。
2. **dpmwd5 (小改造)**: entry marker を `dpm_wait_for_superior` の**後**に移動 (1 行 ×3)。現 entry marker は wait 前なので「wait 中」と「callback 中」が区別できない — 移動版との差分で停止が wait 側か callback 側かを判別できる。
3. 検証すべき論点: (i) pm_trace 摂動の機序 (rtc_lock spinlock の cycle 毎数百回取得が race 窓をどう広げるか)、(ii) 署名 (A)/(B) の出現順・条件依存性 (n=4 では不明)、(iii) バックライト点灯応答の再現性と、そのとき TRACE が動くか (hang 中の電源短押し→数分後に電源断、で最終値が変わるか)。
4. **stock 挙動との対応**: 摂動下の観測である留保は維持しつつ、症状・条件 (BT_PAN_VALID・黒画面・全沈黙) は歴史的 hang と同一。

## 残置物 (実機の現状、7/6 00:27 JST)

| 項目 | 状態 |
|---|---|
| kernel | **6.12.94-dpmwd4 稼働 (saved default)**。dpmwd3/2/1/stock 残置 (多段ロールバック可) |
| pm_trace / pm_test | 0 / none (inert) |
| hung_task_panic / hardlockup_panic / softlockup_panic | 0 / 0 / 0 (平常) |
| NM | autoconnect 平常化 (BT-PAN/GSNet=no, OpenWrt=yes)、route-metric 復元、radio on |
| RTC / 時刻 | NTP 同期 + `hwclock --systohc` 済み |
| sleep hooks | 5 本残置 (平常時 no-op) |
| pstore | 両所在空。pstore-guard enabled |
| /var/log/h4-probe | 本セッション分追加 (hang PRE = unpaired: 1783261609/1783263011/1783263801/1783264326、SESSION-C5-START.marker、watcher log 2 本、devlist)。削除しないこと |
| 開発機 | `src/linux-6.12.y` HEAD=4b279c26a (dpmwd4)、deb 成果物 `src/*dpmwd4*.deb` |

## 再現方法

### dpmwd4 のビルド・デプロイ

182811 と同一手順。差分は commit 4b279c26a (添付パッチ) と `CONFIG_LOCALVERSION="-dpmwd4"`。LOCALVERSION 変更後は `rm include/config/auto.conf && make olddefconfig`。

### 停止点 decode (hang 後)

```bash
# hang → 5 分以上放置 → 強制電源断 → 電源投入 → WiFi 復旧後、即時に:
ssh miminashi@macbookair2015.lan 'sudo journalctl -b -k | grep -E "PM: +(RTC time|Magic|trace data|device marker)|hash matches"'
# user 10-15 なら device marker: 続く "hash matches" 行が実名 (複数出たら callback 実質空の擬似デバイスを除外)
# user 0-9 なら site: 添付 cheatsheet-dpmwd4.txt で引く
# offline 照合: python3 decode.py "YYYY-MM-DD HH:MM:SS" --devlist devlist-dpmwd4-boot.txt
#   ← 渡す値は journal の「PM: RTC time」行 (UTC 生値) を使うこと。hwclock -r は
#     (1) hang 復旧 boot では NTP+systohc で既に上書き済み、(2) ローカルタイム表示 (+9h) の
#     二重の罠がある (運用知見 2/3 参照)
```

### hang-arm セッション (C-5 で確立した形)

```bash
# arm (再起動ごとに揮発分を再設定)
sudo sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1
echo 1 | sudo tee /sys/power/pm_trace
# (watchers: cycle/vpn を systemd-run --collect で任意起動)
sudo nmcli con up GSNet   # BT-PAN 接続後。SA 確認: ip xfrm state | grep -c ^src → 2
sudo systemd-run --unit=radio-off-detached --collect bash -c "sleep 5; nmcli con down OpenWrt; nmcli radio wifi off"
# ユーザ: lid 閉 → 10-15 秒 → 開 → 電源短押しで wake (本機は lid/キーで復帰しない)、反復
# hang: 5 分以上放置 → 電源 10 秒長押し → 起動 → nmcli radio wifi on && nmcli con up OpenWrt
```

## 関連レポート

- [2026-07-05_185344 Phase C-4 停止域の特定と dpmwd4 の設計 (引継ぎ元)](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md)
- [2026-07-04_170147 Phase C-3 firmware-safe encoding の確立](2026-07-04_170147_dpmwd2_phase_c3_pm_trace_firmware_rtc_reset_false_decode.md)
- [2026-07-04_012628 DPM watchdog 実戦発火能力の検証 (沈黙判定の根拠)](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md)
- [2026-07-03_021628 hang-arm セッション手順の一次ソース](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md)
- [2026-07-02_182811 カーネルビルド・デプロイ手順の一次ソース](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-07-02_103415 (b'') tight reading bedrock (hang-arm 条件の統計的根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
