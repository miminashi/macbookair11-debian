# 外出中の発熱の原因調査 — pcie_port_pm=off による待機電力の悪化 (約 4〜5 倍)

- **実施日時**: 2026年7月7日 23:08 (JST)
- **調査対象期間**: 2026年7月7日 18:05〜22:45 (外出前後の suspend 2 回)

## 概要

MacBook Air を鞄に入れて持ち出したところ、帰宅時に本体が使い捨てカイロ程度に発熱していた、というユーザ報告を受けて状況を調査した。sleep 中のハング (Phase C で追跡してきた対象 hang) の再発や、watchdog 偽陽性による panic・再起動をまず疑ったが、いずれも起きていなかった。uptime は 7月6日 01:23 の boot から途切れておらず、pstore は空、suspend の失敗カウントもゼロで、外出中の suspend/resume は journal・soak ログの両方で完全にペアが揃っていた。

発熱の正体は、suspend 中のバッテリ放電の定量化で確定した。system-sleep フック (60-s3-soak-log) が記録している suspend 前後の charge_now の差分から待機電力を算出すると、外出中の 2 回の suspend でそれぞれ約 2.8 W、約 3.4 W を消費していた。これは過去に実測した s2idle の待機電力 約 0.70 W の 4〜5 倍にあたる。3 W 前後を密閉した鞄の中で放熱し続ければ筐体がカイロ程度に温まるのは妥当で、鞄に入れる直前約 50 分間のバッテリ駆動使用 (残量 78%→50%) による余熱も上乗せされていたと考えられる。

原因は、Phase C-6 で hang 対策として導入し常用 soak 中の `pcie_port_pm=off` である。このパラメータは Thunderbolt downstream 4 ポートを含む PCIe ポート群を runtime D3 に落とさず D0 常駐にする (調査時点でも 06:03.0 / 06:06.0 が D0/active であることを実機確認)。ポートが D0 に留まると PCH が深い省電力ステートに入れないため、s2idle 中の消費電力が跳ね上がる。これは C-6 レポートおよび常用 soak 開始時のウォッチリストで「(iii) 待機電力悪化」として予見していた既知の代償が実地で現実化・定量化されたものであり、故障や新規の異常ではない。

副次的な収穫として、C-7 の残課題だった「(iii) 恒久対策評価 (待機電力計測)」が今回の外出で事実上完了した。数値が明確に悪い (モバイル運用で suspend 中でも 1 時間あたり約 7〜9% の残量を失う) ことが分かったため、hang 抑止と待機電力を両立させる C-7 (i) の絞り込み実験 — `pcie_port_pm=off` を外して TB ポートのみ `d3cold_allowed=0` 等でピンポイントに D3 を禁止し、hang 署名が戻らないか確認する — の優先度が上がった。

なお soak 自体の成績は良好で、hang 0 継続 (本調査期間も 0/3)、原因不明の再起動もゼロである。`pcie_port_pm=off` は引き続き実機に残置し soak を継続する。

## 添付ファイル

- [調査・レポート作成プラン](attachment/2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off/plan.md)

## 前提・目的

- 背景: Phase C-6 ([2026-07-06_020526](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)) で `pcie_port_pm=off` により対象 hang が 0/30 で消滅 (Fisher 片側 p≈1.7e-4)。2026-07-06 からこの構成のまま常用 soak を開始し、ウォッチリストとして (i) 原因不明の再起動、(ii) hang 再発、(iii) 待機電力悪化、の 3 点を監視していた
- きっかけ: ユーザが本機を鞄に入れて外出したところ、hang はなかったが本体が使い捨てカイロ程度に発熱していた
- 目的: 発熱の原因を特定し、ウォッチリスト 3 点の消化状況を確認する

## 環境情報

- 機体: MacBook Air 11" (Early 2015)、Debian 13 (trixie)
- カーネル: 6.12.94-dpmwd4 (自前ビルド、DPM watchdog 拡張 + firmware-safe pm_trace)
- cmdline: `... quiet no_console_suspend mem_sleep_default=s2idle panic=15 pcie_port_pm=off`
- sleep 方式: s2idle (`/sys/power/mem_sleep` = `[s2idle] deep`)、pm_trace=0 (inert)
- バッテリ: charge_full 4,649 mAh / design 5,100 mAh (health 約 91%)、voltage_min_design 7.6 V
- boot: 2026-07-06 01:23:32 JST から連続稼働 (調査時点で uptime 1 日 21 時間)
- 計測手段: `/usr/lib/systemd/system-sleep/60-s3-soak-log` が suspend 前後に `/var/log/s3-soak.log` へ記録する charge_now (µAh)・capacity (%)・suspend_stats

## 調査結果

### 1. ハング・panic・再起動はなし (ウォッチリスト (i)(ii) クリーン)

- uptime: 7/6 01:23 boot のまま連続稼働 → watchdog 偽陽性 panic による自動再起動なし
- `/sys/fs/pstore/`: 空 → panic dump なし
- `suspend_stats`: success=36, fail=0
- journal (`-b 0`) と soak ログの SLEEP/WAKE ペア: 欠落なし (unpaired PRE ゼロ)

### 2. 外出中の suspend は正常に成立していた

当日 (7/7) のタイムライン (journal + `/var/log/s3-soak.log`、時刻は JST):

| 時刻 | イベント | AC | cap | charge_now (µAh) |
|---|---|---|---|---|
| 18:05:06 | WAKE (7/6 06:13 から 35.9 h の AC 接続 suspend から復帰) | 1 | 90% | 4,584,000 |
| 19:19:26 | SLEEP (lid close、直後に AC 抜去とみられる) | 1 | 90% | 4,584,000 |
| 21:03:41 | WAKE (lid open、asleep 6,255 s) | 0 | 78% | 3,947,000 |
| 21:03〜21:56 | バッテリ駆動で使用 (cap 78%→50%) | 0 | — | — |
| 21:56:29 | SLEEP (suspend-then-hibernate 経由) | 0 | 50% | 2,518,000 |
| 22:45:36 | WAKE (lid open、asleep 2,947 s) | 0 | 43% | 2,147,000 |

- 2 回とも suspend entry (s2idle) → lid open による正常 wake で、**途中の勝手な wake (spurious wake) は journal にもフックログにも記録なし**
- drm_err=0、gpe70=0 (フック記録)
- 21:56 の suspend が `suspend-then-hibernate` 型なのはバッテリ駆動時の設定によるもので、49 分では HibernateDelaySec に達せず通常の s2idle 区間として扱える

### 3. 発熱の正体 = suspend 中の放電が従来の 4〜5 倍

charge_now 差分から待機電力を算出 (公称 7.6 V 換算):

| 区間 | 消費 | 時間 | 待機電力 |
|---|---|---|---|
| 19:19→21:03 | 637 mAh (cap 90%→78%) | 6,255 s (1.74 h) | **約 2.8 W** |
| 21:56→22:45 | 371 mAh (cap 50%→43%) | 2,947 s (0.82 h) | **約 3.4 W** |

- 従来の s2idle 実測 約 0.70 W (2026-06 の S3 復活検証時に計測した比較値、[C-6 レポート](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md) でも待機電力評価の基準として参照) の **約 4〜5 倍** (区間 1: 4.0 倍、区間 2: 4.9 倍)
- 換算は保守的な公称電圧 7.6 V を使用。放電中の実電圧は 7.8〜8.0 V 程度のため実際はやや高め (区間 2 は 3.6 W 前後の可能性)
- 区間 1 は SLEEP 時点で ac=1 のため、suspend 後しばらく AC が繋がっていた場合、真の放電時間は 6,255 s より短く実待機電力は 2.8 W より高い可能性がある (下限値)。区間 2 は両端 ac=0 のクリーンな計測
- モバイル運用への影響: **suspend 中でも 1 時間あたり約 7〜9% の残量を失う** (区間 1: 6.9%/h、区間 2: 8.5%/h。0.70 W なら約 2%/h)

発熱の解釈: 約 3 W の連続放熱は、通気のない鞄の中では筐体を体温超〜40°C 台に温めるのに十分で、「使い捨てカイロ程度の熱さ」という体感と整合する。鞄投入直前 53 分間のバッテリ駆動使用 (28% 消費 ≈ 平均 11〜12 W) による筐体余熱も初期温度として上乗せされている。なお調査時点 (22:48、AC 充電 35 W 中) の実測温度は PCH 60.5°C / package 58°C / バッテリ 36.3°C で、復帰後の使用と急速充電による通常の発熱範囲だった。

### 4. 原因 = pcie_port_pm=off による PCIe ポート D0 常駐 (既知の代償)

- 調査時点で TB downstream ポート 06:03.0 / 06:06.0 は `power_state=D0` / `runtime_status=active` を実機確認 (C-6 導入時の想定どおり)
- `pcie_port_pm=off` は root port (00:1c.x) 含む PCIe ポート群全体の runtime D3 を禁止するため、s2idle 中も PCH が深い省電力ステート (PC state) に入れず、待機消費が数 W 台に張り付く
- これは C-6 常用 soak 開始時にウォッチリスト (iii) として予見していた既知のトレードオフの現実化であり、**故障・新規異常ではない**

## 再現方法

1. suspend 前後のバッテリ記録を確認 (フックが自動記録):
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo tail -20 /var/log/s3-soak.log'
   ```
2. 待機電力を算出: 連続する SLEEP/WAKE 行の charge_now 差分 (µAh) と WAKE 行の asleep_s から

   ```
   W = (charge_now_SLEEP - charge_now_WAKE) / 1e6 [Ah] × 7.6 [V] ÷ (asleep_s / 3600) [h]
   ```

   例 (区間 2): (2,518,000 − 2,147,000)/1e6 × 7.6 ÷ (2947/3600) = 3.44 W
3. spurious wake の有無を確認:
   ```bash
   ssh miminashi@macbookair2015.lan 'journalctl -b 0 -o short-iso --no-pager | grep -E "PM: suspend (entry|exit)|Lid (opened|closed)"'
   ```
4. 再起動・panic の有無を確認:
   ```bash
   ssh miminashi@macbookair2015.lan 'uptime -s; sudo ls -la /sys/fs/pstore/'
   ```
5. PCIe ポートの電源状態を確認:
   ```bash
   ssh miminashi@macbookair2015.lan 'cat /sys/bus/pci/devices/0000:06:03.0/power_state /sys/bus/pci/devices/0000:06:03.0/power/runtime_status'
   ```

> 注意: `journalctl --since` で過去の boot を跨ぐ検索をすると、pm_trace 実験時代の RTC 汚染タイムスタンプ (2027 年等) が混入して時系列が壊れる。現 boot の調査は必ず `-b 0` で絞ること。

## 常用 soak ウォッチリスト消化状況 (2026-07-06 開始、7/7 時点)

| 項目 | 状況 |
|---|---|
| (i) 原因不明の再起動 (watchdog 偽陽性) | **なし** (uptime 連続、pstore 空) |
| (ii) hang 再発 | **なし** (soak 開始後 0 件、本調査期間 0/3) |
| (iii) 待機電力悪化 | **現実化・定量化** (2.8〜3.4 W ≈ 従来の 4〜5 倍、本レポート) |

## 今後の選択肢

- **C-7 (i) 絞り込み実験の優先度が上がった**: `pcie_port_pm=off` (広域) を外し、TB downstream ポートのみ `d3cold_allowed=0` や個別 `power/control=on` 等でピンポイントに D3 を禁止して、(a) hang 署名が戻らないこと、(b) 待機電力が 0.7 W 級に戻ること、の両立を確認する。今回の定量化により「広域 off のままでは モバイル運用の実害 (発熱 + 7〜8%/h の残量消費) が大きい」ことが確定したため
- 当面の運用ワークアラウンド: 長時間鞄に入れて持ち歩く場合は suspend でなくシャットダウン (またはハイバネート) を使うと発熱・電池消費とも回避できる
- soak 自体は継続 (hang 0 の実績蓄積中)。`pcie_port_pm=off` は残置

## 参照レポート

- [Phase C-6: pcie_port_pm=off で hang 0/30 (導入経緯とウォッチリスト)](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)
- [Phase C-5: 停止境界のデバイス実名 = TB ブリッジ / i915](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
