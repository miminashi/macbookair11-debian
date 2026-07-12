# Phase C-9: 無保護トレース — radio-off 短縮経路 × 親 D3hot 復帰のバスレベル観測

## Context

C-8 (report/2026-07-12_060000) で機序は「半解明」まで到達した: wl は毎 resume に 4360 PCIe2 war (PLL 再プログラム + config space 退避/復元) を実行し、radio off ではこれが 54ms→22ms の短縮経路 (war 実行 + 本初期化中断) になる。**未解明の最後の 1 点 = 「この短縮経路が、無保護の親ポート 00:1c.2 の D3hot 復帰を具体的にどうバスレベルで壊すか」**。これは無保護 (d3cold_allowed=1) で hang を起こしながら観測するしかなく、C-8 ではスコープ外だった。

ユーザ決定 (今セッション): **トレースのみ実施** (クリーンアップは後日)、カーネルは **dpmwd4 + pm_trace** (hang 時の停止点 RTC decode が取れる唯一の構成)。hang 率 ~38-44% を引き受ける。

## 実機の現状 (読み取り確認済み、2026-07-12 06:15 JST)

- stock 6.12.95+deb13 稼働中 (05:54 boot、検収再起動直後)、pstore 空、udev rule 機能中 (d3cold_allowed=0)
- dpmwd4 grub エントリ残置: `gnulinux-advanced-147f49dc-...>gnulinux-6.12.94-dpmwd4-advanced-147f49dc-...`
- **GRUB_DEFAULT=0 (最新=6.12.95)。saved_entry は stock 6.12.94 を指す (未使用)**
- hooks 5 本残置 (50-kbd-backlight / 58-snapshot-only / 59-pmtrace-timefix / 60-s3-soak-log / 70-h4-probe)、delay_cnt=300、AC 接続・バッテリ 91%
- **00:1c.2 に AER capability なし** (lspci -vv 実測) → AER チャネルは使えない。LnkSta: 2.5GT/s x1
- decode.py は開発機 `report/attachment/2026-07-05_185344_*/decode.py` (+ decode-cheatsheet.txt) に残置

## 設計上の要点 (今回特有)

1. **hang 強制断後の再起動が stock に落ちる問題**: GRUB_DEFAULT=0 のため、hang → 電源断 → 再起動は 6.12.95 で立ち上がり、**dpmwd3/4 独自の firmware-safe RTC エンコーディングを decode できない** (歴代 C-5〜C-7 は default=saved→dpmwd4 だったので成立していた)。
   → **セッション中だけ default を dpmwd4 に変更** (`GRUB_DEFAULT=0→saved` + `grub-set-default <dpmwd4 エントリ>` + `update-grub && sync`、原本 `grub.bak-c9`)。撤収時に `GRUB_DEFAULT=0` へ戻す。
2. **udev rule は触らない**: 無保護化は runtime の `echo 1 > /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed` のみ。毎 boot 後に udev が 0 へ戻すため **hang 再起動のたびに再設定が必要** (= 事故で無保護が残らない安全構造)。
3. **観測目的優先の摂動方針**: 歴代の統計 arm と違い、本番 cycle 中も dynamic debug (pci-driver.c/pci-acpi.c +p) を有効のまま走らせる。**arm tag = c9 として分離、歴代 pool と合算しない**。
4. **hang cycle 自身の journal 行は失われる** (resume 中の printk は flush 前に電源断)。hang cycle の一次データは boot 時 kernel decode (journal 永続) のみ。バスレベルの新情報は主に**成功 cycle の near-miss 検出** (snapshot 差分) から取る。

## 実施手順

### P0: dpmwd4 切替 (Claude, ssh)

```bash
sudo cp /etc/default/grub /etc/default/grub.bak-c9
sudo sed -i 's/^GRUB_DEFAULT=0/GRUB_DEFAULT=saved/' /etc/default/grub
sudo update-grub && sudo sync
sudo grub-set-default "gnulinux-advanced-147f49dc-e854-47df-a721-b304a1c0c7bd>gnulinux-6.12.94-dpmwd4-advanced-147f49dc-e854-47df-a721-b304a1c0c7bd"
sudo sync && sudo reboot
```

preflight: `uname -r` = 6.12.94-dpmwd4 / pstore 空 / pm_trace=0 / d3cold_allowed=0 (udev) / delay_cnt=300 / hooks 5 本。

### P1: arm + 無保護化 + 観測系 (Claude)

- `sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1`
- `echo 1 > /sys/power/pm_trace`、marker `SESSION-C9-START` (epoch 付き、/var/log/h4-probe/)
- watchers (C-6 レポート「再現方法」と同一コマンド、ログ名 c9): cycle-watch-c9 / vpn-watch-c9 (root、`ip xfrm state` は sudo 必須)
- **新規: bus-watch-c9** (systemd-run loop): journal の `PM: suspend exit` を trigger に、resume 直後の `lspci -vv -s 00:1c.2` / `-s 03:00.0` / `lspci -xxx` (config space) / LnkSta / d3cold_allowed を `/var/log/h4-probe/c9-bus-watch/<epoch>.snap` に保存 (成功 cycle の near-miss 検出用)
- dynamic debug: `echo "file drivers/pci/pci-driver.c +p" / "file drivers/pci/pci-acpi.c +p"` → dynamic_debug/control (本番中も有効のまま)
- 無保護化: `echo 1 | sudo tee /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed`
- smoke: WiFi on のまま lid cycle 1 回 → dynamic debug で **00:1c.2 が D3hot で sleep すること** (無保護の実効) を実測確認

### P2: 本番 cycle (ユーザ主体)

- ユーザ: iPad BT-PAN 接続 → WiFi radio off → `nmcli con up GSNet` → Claude が `sudo ip xfrm state | grep -c ^src` = 2 を確認
- ユーザ: lid 閉 → 10-15 秒 → 開 → 電源短押し wake、反復
- **終了条件: hang 2 回 (decode 2 点確保) または有効 15 cycle 到達** (0/15 なら「無保護率の変動」として記録、それ自体がデータ)
- **hang 時の手順**: 5 分放置 → 電源長押し → 電源 on (default=dpmwd4 で起動) → Claude が即座に boot decode 回収 (`journalctl -b 0 -k | grep -iE "magic|hash match"`、journal 永続なので焦らなくてよいが RTC 生値は ~11 分で NTP 上書き) → pstore 確認 → **再 arm** (sysctl ×3 + pm_trace=1 + d3cold_allowed=1 + watchers + dynamic debug 再設定) → 続行

### P3: 解析 (Claude)

- hang cycle: decode → 署名分類 (A: TB noirq / B: i915 main entry / 新規)。直前 PRE の wl callback 時間が 22ms 短縮経路であることを journal で確認 (hang 直前 cycle の suspend 側行は残る)
- 成功 cycle: bus-watch snapshot の cycle 間差分 (LnkSta 速度/幅の変動、config space 差分、リンク再訓練痕跡)、D-state 遷移ログ、wl resume callback 時間分布
- C-8 の保護あり T2/T3 との比較で「無保護時だけに出る差」を抽出

### P4: 撤収 + レポート (Claude)

```bash
# 実機: pm_trace=0、watchers 停止、dynamic debug 無効化、sysctl 0 戻し
sudo sed -i 's/^GRUB_DEFAULT=saved/GRUB_DEFAULT=0/' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot   # → stock 6.12.95
# 検収: uname / d3cold_allowed=0 (udev 自動復元) / pstore / smoke 1 cycle
```

- レポート `report/2026-07-12_HHMMSS_phase_c9_unprotected_trace_*.md` (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)。本プランを `report/attachment/<レポート名>/plan.md` に添付。証跡 (decode、bus-watch 抜粋、台帳) も添付
- memory (s2idle-btvpn-hang-mechanism-ladder.md) に C-9 追記

## 判定・統計の扱い

- BT_PAN_VALID: 各 PRE に BT-PAN アドレス (172.20.10.13 ↔ 160.16.210.47) の ESP SA 双方向 (SESSION-C9-START epoch でフィルタ)
- hang 判定: unpaired PRE (ペア窓は休憩考慮、boot ID + POST 総数で相互確認)
- **c9 arm は「dpmwd4 + pm_trace + dynamic debug 常時 on + 無保護」の新 tag。歴代 pool (9/24) とは参考比較のみ、合算しない**

## リスク・既知の罠

- hang ~38-44%/cycle、強制断 (fs リスクは歴代同様に引き受け済み)
- pm_trace 中は RTC 汚染 timestamp が journal に混入 → 調査は必ず `journalctl -b 0`。`uptime -s` も狂う (再起動判定は boot ID で)
- 59-pmtrace-timefix hook は pm_trace=1 ガードで自動作動 (触らない)
- 決着後の宿題 (今回スコープ外): クリーンアップ (autoremove/dpmwd1-3 purge/6.12.74 hold 整理、stock 6.12.94 の manual 保持判断)、pm_async=0 判別実験 (resume 直列化で hang が消えるかは「i915 窓内並走」構造の直接検証になるが、有意性に ~30 clean cycle 必要なため次セッション候補として記録のみ)

## 役割分担

- Claude: ssh 操作・grub 切替・arm/再 arm・decode 回収・解析・レポート
- ユーザ: BT-PAN/VPN/radio 操作、lid 開閉、hang 時の電源長押し・再投入
