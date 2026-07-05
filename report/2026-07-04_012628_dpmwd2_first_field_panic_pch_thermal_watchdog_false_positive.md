# dpmwd2 初の実戦 panic 捕獲 — intel_pch_thermal 冷却ループと DPM watchdog 60s の衝突 (偽陽性) の解明と緩和

- **実施日時**: 2026年7月4日 01:26 JST (事象発生: 2026年7月3日 21:11 JST)
- **作業者**: Claude Code (ユーザ報告「普段使い中にハング→自動再起動」の状況確認依頼)

## 添付ファイル

- [実装プラン](attachment/2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive/plan.md)
- [pstore panic ダンプ (dmesg.txt 再構成版、503 行)](attachment/2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive/pstore-dmesg.txt)

## 前提・目的

- **背景**: dpmwd2 カーネル (DPM_WATCHDOG=y TIMEOUT=60s + late/noirq 拡張パッチ + panic=15) を
  [2026-07-03_021628](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md) で導入し、
  suspend hang の停止段特定のための常時監視体制で運用中だった。
- **契機**: ユーザが 7/3 夜の普段使い中に「ハングが発生して自動で再起動したように見えた」と報告。
- **目的**: 事象の正体を特定し、(a) 調査対象の hang (wl-radio-off 系) かどうかを判定、
  (b) 実害があれば緩和する。

## 結論 (TL;DR)

1. **dpmwd2 の DPM watchdog が初めて実戦で panic を発火し、pstore ダンプの捕獲に成功した**。
   watchdog → panic → EFI pstore 25 パート保存 → systemd-pstore 回収の全パスが実戦で
   end-to-end 動作。021628 の残課題「late/noirq panic 自己申告能力は未検証」が解消された。
2. ただし**中身は調査対象 hang ではなく watchdog の偽陽性**: `intel_pch_thermal` の
   suspend_noirq が持つ正規の「PCH 冷却待ちループ」(最大 ~60 秒) が、watchdog timeout
   (ちょうど 60 秒) と正確に衝突した。watchdog がなければ suspend は最大 ~63 秒の遅延の後
   正常完了していた。
3. **実害**: 機体が温まった状態 (PCH ≥50°C) で lid close するたびに panic reboot → 作業状態喪失
   のリスク。**緩和策として `intel_pch_thermal.delay_cnt` を 600→300 (冷却待ち上限 30 秒、
   watchdog に対し 2 倍マージン) に変更・適用済み** (runtime + modprobe.d、再起動不要・可逆)。
4. 本事象は wl-radio-off 系 hang の統計 (hang pooled 5/56 / clean pooled 0/112) には
   **計上しない** (条件不一致、かつプロトコル cycle 外の通常使用)。

## 環境情報

- 実機: MacBook Air 11" (Early 2015, MacBookAir7,1) / Debian 13 (trixie) / RAM 3.7GiB
- カーネル: **6.12.94-dpmwd2** (CONFIG_DPM_WATCHDOG=y, TIMEOUT=60s, late/noirq 拡張パッチ
  commit `b90248d63`, PM_TRACE_RTC=y ビルド時有効・runtime off)
- カーネル cmdline: `quiet no_console_suspend mem_sleep_default=s2idle panic=15`
- WiFi: broadcom-sta-dkms 6.30.223.271-26 (`wl`)、事象時 **radio-on・AP 接続中**
- BT-PAN: **なし** (snapshot-only プローブ: bnep_netdev=MISSING, kbnepd=NOT FOUND)
- suspend 方式: lid close → suspend-then-hibernate (s2idle)

## 事象タイムライン (2026-07-03 JST、journalctl -b -1 と pstore ダンプより)

| 時刻 | 事象 |
|---|---|
| 01:13 | dpmwd2 でブート (当該ブート開始) |
| 〜21:11 | 通常使用。当該ブート内で suspend entry 34 回、すべて clean (20:45 の resume まで確認) |
| 21:11:23 | `systemd-logind: Lid closed.` → `Suspending, then hibernating...` |
| 21:11:24-25 | suspend フック正常実行 (`kbd-backlight-sleep`, `70-h4-probe` pre) → `Performing sleep operation 'suspend'` を最後に journal 途絶 |
| 21:11:25頃 | (pstore) main/late 段は全デバイス正常通過。noirq 段で `intel_pch_thermal 0000:00:1f.6` が冷却ループ突入 |
| 21:12:25頃 | (pstore) DPM watchdog 発火 → **Kernel panic** |
| 21:12:27 | 1783080747 (unix time) = EFI pstore 書き込み。panic=15 で 15 秒後に自動リブート |
| 21:13:02 | dpmwd2 で再ブート。systemd-pstore がダンプを `/var/lib/systemd/pstore/1783080747/001/` に回収 |

## pstore ダンプ解析

ダンプはカーネル時刻入り。suspend entry = 71871.22、noirq 段の当該コールバック開始 = 71872.28、
watchdog 発火 = 71932.98 (**コールバック開始から 60.7 秒 = TIMEOUT=60s + タイマスラック**)。

### 冷却ループ突入の証拠 (ダンプ 399-400 行目)

```
<6>[71872.279712] intel_pch_thermal 0000:00:1f.6: PM: calling pci_pm_suspend_noirq @ 114249, parent: pci0000:00
<4>[71872.279726] intel_pch_thermal 0000:00:1f.6: CPU-PCH current temp [74C] higher than the threshold temp [50C], S0ix might fail. Start cooling...
```

### watchdog 発火とバックトレース (抜粋)

```
<0>[71932.979828] intel_pch_thermal 0000:00:1f.6: PM: **** DPM device timeout ****
<0>[71932.979898]  intel_pch_thermal_suspend_noirq.cold+0x4b/0x11a [intel_pch_thermal]
<0>[71932.979920]  pci_pm_suspend_noirq+0x79/0x2a0
<0>[71932.979933]  dpm_run_callback+0x4a/0x150
<0>[71932.979945]  device_suspend_noirq+0xfa/0x330
<0>[71932.980036] Kernel panic - not syncing: intel_pch_thermal 0000:00:1f.6: unrecoverable failure
```

スタックは `intel_pch_thermal_suspend_noirq → msleep → schedule_timeout` で、driver が
**設計どおりの冷却待ち msleep 中**だったことを示す (デッドロックや busy-loop ではない)。

### driver 側の正規ループ (src/linux-6.12.y `drivers/thermal/intel/intel_pch_thermal.c`)

```c
static unsigned int delay_timeout = 100;   /* module_param, 0644 */
static unsigned int delay_cnt = 600;       /* module_param, 0644 */
...
while (pch_delay_cnt < delay_cnt) {
        /* 温度が閾値未満になったら break */
        msleep(delay_timeout);
}
/* 上限到達時は "CPU-PCH is hot ... S0ix might fail" を警告して継続 (return 0) */
```

最大待ち時間 = 100ms × 600 回 ≈ **60〜63 秒** (msleep は指定値以上眠る)。
watchdog TIMEOUT=60s と正確に衝突する — **PCH が 60 秒以内に 50°C まで冷えなければ必ず panic**。
実機の閾値・実測 (事象時 74°C、lid close でパッシブ冷却) では 60 秒内の冷却完了は期待できない。

## 判定: 調査対象 hang ではなく偽陽性 (根拠 3 点)

1. **条件不一致**: 事象時は BT-PAN なし・WiFi radio-on 接続中 (lid close で NM が正常 teardown)。
   これは [2026-07-02_103415](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) で
   establish した clean 条件 (wl-radio-on pooled 0/52) であり、hang の必要条件
   「wl loaded かつ radio-off」を満たさない。
2. **機序が自明かつ有限**: driver のループは 600 回で必ず打ち切られ警告後に suspend を継続する
   設計。watchdog がなければ「suspend が最大 ~63 秒遅れる」だけで正常完了していた。
   永久停止する調査対象 hang (journal 途絶 + 電源断まで無反応) とは別物。
3. **バックトレースが正規パス**: 停止点は msleep のスケジューラ待ちであり、URB drain
   (H4) や netdev refcount 待ち (H1) 等の仮説群のどれとも一致しない。

### hang 統計への扱い

本事象は wl-radio-off 系 hang/clean pool に**計上しない**。当該ブートの clean 34 suspend も
プロトコル cycle ではない通常使用のため統計外。Phase C-2 の 0/29 は変更なし。

### 今後の hang 判定への注意 (重要)

dpmwd2 運用下では「hang → panic → 自動再起動」が仕様になったため、**再起動を検知したら
必ず pstore ダンプの panic 対象デバイスを確認し、対象 hang か本件型の偽陽性かを判別する**こと。
`intel_pch_thermal ... unrecoverable failure` なら偽陽性 (緩和後は原則発生しないはず)。

## 副次的収穫

### 1. dpmwd2 の panic 自己申告能力の実戦検証が完了

021628 時点で「dpmwd2 の late/noirq panic 自己申告能力は未検証」だった。本事象で
**noirq 段 watchdog → panic → EFI pstore (25 パート・152KB) → systemd-pstore 回収**の
全パスが実戦条件 (lid close・console suspend 済) で動作することが確認された。
per-device pm_debug ログもダンプに完全収録されており、対象 hang が dpmwd2 下で再現すれば
停止デバイスは確実に特定できる。

### 2. pstore-guard の設計穴 (記録のみ、修正は今回スコープ外)

`pstore-guard.service` は起動時に「no pstore record found, nothing to guard」と報告した。
原因は systemd-pstore が先に `/sys/fs/pstore` → `/var/lib/systemd/pstore/` へ回収し、
guard が見る時点で `/sys/fs/pstore` が空だったため。今回はダンプが失われていないので実害は
ないが、guard の「未回収ダンプがある間 suspend をブロックする」意図は現構成では機能しない
(systemd-pstore が常に先に回収する)。修正するなら guard はアーカイブディレクトリの
新規エントリも見るべき。

## 緩和策 (適用済み)

`intel_pch_thermal.delay_cnt` を 600 → **300** (冷却待ち上限 30 秒 = watchdog 60s の 1/2)。

```bash
# 恒久 (次回ブート以降、modprobe.d)
ssh miminashi@macbookair2015.lan \
  'echo "options intel_pch_thermal delay_cnt=300" | sudo tee /etc/modprobe.d/intel-pch-thermal.conf'
# 即時 (再起動不要、param は 0644)
ssh miminashi@macbookair2015.lan \
  'echo 300 | sudo tee /sys/module/intel_pch_thermal/parameters/delay_cnt'
```

- **適用確認済み**: runtime 値 300 / modprobe.d ファイル作成済み (2026-07-04 01:27 JST)
- 副作用: 冷却が 30 秒で打ち切られた場合に S0ix 深度が浅くなる可能性のみ
  (driver は警告して suspend を継続する。suspend 自体は成功する)
- ロールバック: `sudo rm /etc/modprobe.d/intel-pch-thermal.conf` +
  `echo 600 | sudo tee /sys/module/intel_pch_thermal/parameters/delay_cnt`
- 代替案 (見送り): dpmwd3 で DPM_WATCHDOG_TIMEOUT=120 リビルド。対象 hang は永久停止なので
  120s でも検出能力は落ちないが、リビルド工数と再デプロイリスクに見合わないため driver 側
  パラメータで塞いだ。**次回カーネルをリビルドする機会があれば TIMEOUT=120 への変更を併合検討**。

## 再現方法 (本事象の確認手順)

1. 再起動履歴と crash 判定: `ssh miminashi@macbookair2015.lan 'last -x reboot shutdown | head'`
2. pstore アーカイブ確認: `sudo ls /var/lib/systemd/pstore/` (unix time 名のディレクトリ)
3. panic 内容: `sudo grep -nE "DPM device timeout|Kernel panic" /var/lib/systemd/pstore/<ts>/001/dmesg.txt`
4. 冷却ループ突入の有無: 同ファイルを `grep "Start cooling"`
5. 前ブート末尾 (suspend 突入の確認): `sudo journalctl -b -1 -n 30`
6. (偽陽性の再現条件) PCH ≥50°C の状態で lid close — 緩和適用前の delay_cnt=600 では
   冷却が 60 秒を超えると必ず panic した。緩和後は発生しないはず。

## 参照した過去レポート

- [2026-07-03_021628 dpmwd2 デプロイ + Phase C-2 29 cycle clean (watchdog 拡張パッチ・config の一次ソース)](2026-07-03_021628_dpmwd2_deploy_phase_c2_29cycle_clean.md)
- [2026-07-02_182811 dpmwd1 ビルド・デプロイ・pstore e2e 検証](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-07-03_002608 dpmwd1 hang 再現・panic 沈黙・停止段絞り込み](2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md)
- [2026-07-02_103415 wl unload pool p=0.024 bedrock (clean 条件の統計的根拠)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
