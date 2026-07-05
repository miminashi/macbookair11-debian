# dpmwd2 初の実戦 panic 捕獲 (intel_pch_thermal 偽陽性) — レポート作成 + 緩和策適用

## Context

ユーザが「普段使い中にハング→自動再起動」を体感。調査の結果、事象は完全に解明済み:

### 確定した事象 (調査済み・すべて読み取りのみで確認)

- **7/3 21:11:23 JST**: lid close → suspend-then-hibernate 開始 (当該ブートで 35 回目の suspend、前 34 回は clean)
- **21:11:24 頃 noirq 段**: `intel_pch_thermal 0000:00:1f.6` の `suspend_noirq` が
  「CPU-PCH current temp [74C] > threshold [50C], Start cooling...」で冷却待ちループ突入
  (msleep(100ms) × 最大 600 回 = 最大 ~60 秒。runtime param 確認済み: delay_cnt=600, delay_timeout=100)
- **60 秒後**: dpmwd2 の DPM watchdog (TIMEOUT=60s、late/noirq 拡張パッチ) が発火
  → `**** DPM device timeout ****` → `Kernel panic - not syncing: intel_pch_thermal 0000:00:1f.6: unrecoverable failure`
- **panic=15** → 21:12:27 自動再起動 → 21:13 dpmwd2 で再ブート
- **pstore 完全動作**: EFI pstore に 25 パート保存 → systemd-pstore が
  `/var/lib/systemd/pstore/1783080747/001/` に回収済み (dmesg.txt 再構成込み、計 152KB、
  per-device pm_debug ログ + 完全なバックトレース入り)

### 判定: 調査対象 hang ではなく watchdog 偽陽性

1. **条件不一致**: BT-PAN なし (bnep_netdev=MISSING, kbnepd NOT FOUND)、WiFi radio-on 接続中
   = pooled 0/52 clean の安全条件。wl-radio-off 系 hang とは別事象。
2. **機序が自明**: driver の正規ループ上限 (~60-63s) が watchdog timeout (60s) と正確に衝突。
   driver は 600 回で諦めて警告後 suspend 続行する設計なので、watchdog がなければ
   最大 ~63 秒の遅延の後 suspend は正常完了していた (真のハングではない)。
   バックトレースも `intel_pch_thermal_suspend_noirq → msleep` で正規ループ中を示す。
3. 発生条件 = 「機体が温まった状態 (PCH ≥50°C) で lid close + 冷却が 60 秒以内に完了しない」
   → **普段使い後の lid close で毎回 panic reboot のリスク = 実用上の緊急課題**

### 副次的収穫 (レポートに記録すべき)

- **dpmwd2 の noirq watchdog → panic → pstore 保存 → 回収の全パスが実戦で end-to-end 検証された**
  (前回レポート 021628 の残課題「late/noirq panic 自己申告能力は未検証」が解消)
- pstore-guard.service は「no pstore record found」と誤判定 (systemd-pstore が先に回収したため
  /sys/fs/pstore が空だった)。今回ダンプは失われておらず実害なし、だが guard の設計穴として記録。

## 実施内容

### 1. 緩和策の適用 (実機、即時・可逆)

`intel_pch_thermal.delay_cnt` を 600 → **300** (最大冷却待ち 30 秒、watchdog 60s に対し 2 倍マージン):

```bash
# 恒久 (次回ブート以降)
ssh miminashi@macbookair2015.lan 'echo "options intel_pch_thermal delay_cnt=300" | sudo tee /etc/modprobe.d/intel-pch-thermal.conf'
# 即時 (再起動不要、param は 0644 で runtime 変更可)
ssh miminashi@macbookair2015.lan 'echo 300 | sudo tee /sys/module/intel_pch_thermal/parameters/delay_cnt'
```

- 副作用: 冷却 30 秒で打ち切られた場合 S0ix 深度が浅くなる可能性のみ (suspend 自体は成功)。
- 代替案 (今回は見送り、レポートに記載): dpmwd3 で DPM_WATCHDOG_TIMEOUT=120 リビルド
  (対象 hang は永久停止なので 120s でも検出能力は落ちない。次回リビルド時に併合検討)。

### 2. panic ダンプの持ち帰り (attachment 用)

```bash
ssh miminashi@macbookair2015.lan 'sudo cat /var/lib/systemd/pstore/1783080747/001/dmesg.txt' > report/attachment/<レポート名>/pstore-dmesg.txt
```

### 3. レポート作成

- パス: `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md`
- 内容: 上記の事象タイムライン / ダンプ解析 (バックトレース引用) / 偽陽性判定の根拠 3 点 /
  pstore e2e 実戦検証達成 / pstore-guard の穴 / 緩和策 (適用コマンド・検証・ロールバック) /
  参照レポート ([021628], [182811], [002608]) / 環境情報
- 添付: plan.md (本ファイル) + pstore-dmesg.txt
- **hang 統計への計上**: 対象 hang ではないので wl-radio-off 系の hang/clean pool には入れない
  (当該ブートの 34 clean suspend は通常使用でありプロトコル cycle でもないため統計外) と明記。

### 4. メモリ更新

`s2idle-btvpn-hang-mechanism-ladder.md` に (j) 追記:
- dpmwd2 の panic 自己申告能力は実戦検証済み (未検証課題解消)
- intel_pch_thermal 冷却ループ (最大60s) と watchdog 60s の衝突 → delay_cnt=300 緩和適用済み
- 「PCH 高温時の lid close」偽陽性は今後の cycle 試験でも起こりうる点に注意
  (hang 判定時は pstore の panic 内容で対象 hang か偽陽性かを必ず判別する)

### 5. 検証

- `cat /sys/module/intel_pch_thermal/parameters/delay_cnt` → 300
- modprobe.d ファイルの存在確認
- (機会があれば) 温まった状態での lid close suspend が panic せず完走することを次回通常使用で観察

## 変更しないもの

- dpmwd2 カーネル・GRUB 設定・watchdog timeout (現状維持。偽陽性源は driver 側パラメータで塞ぐ)
- pstore-guard.sh の修正は今回スコープ外 (穴はレポートに記録のみ。systemd-pstore が
  自動回収するため実害が薄い)
- Phase C-2 の統計 (0/29) は変更なし
