# Phase C-6: 名指し介入第 1 弾 — pcie_port_pm=off で署名 A (TB2 ブリッジ) の因果検証

## Context

Phase C-5 (report 2026-07-06_002651) で、BT-PAN + VPN + WiFi radio-off 時の lid close ハングの停止点が
resume 経路上の 2 署名に二極化した:

- **署名 A**: Falcon Ridge TB2 downstream ブリッジ (pcieport 06:03.0 / 06:06.0) の **noirq resume entry** ×2
- **署名 B**: i915 (0000:00:02.0) の **main resume entry** ×2 (RTC 値まで完全同一)

4/4 が pre (entry) marker + 全監視 (DPM watchdog / hung_task / NMI hardlockup / softlockup、全 panic arm) 沈黙という
強制約から、「callback 長時間実行」でも「completion 待ち D 滞留」でもない、タイマ/NMI 基盤ごと止まる静かな停止
(C-state 復帰不全系) が有力仮説。実名が付いたことで観測フェーズから**因果検証フェーズ**へ移行できる。

Phase C-6 は名指し介入の第 1 弾として **`pcie_port_pm=off`** (署名 A 狙い、未実施、リビルド不要) を選択
(ユーザ確認済み)。`i915.enable_dc=0` は S3 時代 (5/10-5/22) に適用して hang 頻度が変わらなかった実績があり
事前確度が低いため後回し。dpmwd4 + pm_trace=1 の高再現 arm (hang 率 40-44%) は維持し、介入 1 変数のみ追加する。

- **仮説判定の軸**: 署名 A が消えるか / hang 率が変わるか / 署名が別デバイスにシフトするか
- **arm tag**: `dpmwd4 + pm_trace=1 + pcie_port_pm=off` — 既存摂動 pool (8/19 ≈ 42%) とは**合算しない**
- **役割分担**: ssh 操作全般 = Claude、テザリング・lid 開閉・強制電源断・WiFi 復旧 = ユーザ (今夜実施可、確認済み)
- sandbox は現在 disabled (settings.local.json) — ssh は直接通る

## P0: Preflight (読み取りのみ)

1. `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でセッション開始時刻取得
2. ssh 疎通 + 実機状態検収:
   - `uname -r` = `6.12.94-dpmwd4`、`/proc/cmdline` に `panic=15` あり・`pcie_port_pm` なし
   - `/sys/power/pm_trace` = 0、pm_test = none
   - pstore 空 (`/sys/fs/pstore`、`/var/lib/systemd/pstore`)
   - `intel_pch_thermal` delay_cnt=300、wl loaded、hooks 5 本、GRUB saved default = dpmwd4
   - AC 接続状態・バッテリ残量 (セッションは AC 推奨)
3. **介入前スナップショット**: TB 系ポートの runtime PM 状態
   `grep -H . /sys/bus/pci/devices/0000:0[56]*/power/runtime_status` (05:00.0 upstream、06:03.0/06:06.0 ほか)
   — 介入前は D3 (suspended) のはず。介入後との比較材料。

## P1: 介入適用 (pcie_port_pm=off)

1. バックアップ: `sudo cp /etc/default/grub /etc/default/grub.bak-c6`
   (`grub.bak-dpmwd` = 182811 時点の原本は別途残置済み、上書きしない)
2. `GRUB_CMDLINE_LINUX_DEFAULT` に `pcie_port_pm=off` を追加 → `sudo update-grub && sudo sync`
   (**grubenv/grub 変更後の sync は 182811 の教訓で必須**)
3. 再起動 (ユーザに事前通知)
4. 検収ゲート:
   - `/proc/cmdline` に `pcie_port_pm=off`、`uname -r` = dpmwd4
   - pm_trace=0 inert、pstore 空、wl loaded、delay_cnt=300
   - **効果のソフト確認**: TB ブリッジ runtime_status が suspended → active に変わること
     (pcie_port_pm=off は `pci_bridge_d3_disable` を立て、ブリッジを D3 に落とさなくなる)
   - 変化がなければ `lspci -s 06:03.0 -vv` 等で電源状態を直接確認し、記録した上で続行判断

## P2: arm + smoke

1. arm (再起動ごとに揮発、hang 復旧 boot 後も毎回再実行):
   ```
   sudo sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1
   echo 1 | sudo tee /sys/power/pm_trace
   ```
2. SESSION marker: `/var/log/h4-probe/SESSION-C6-START.marker` (epoch 記録)
3. watchers: cycle-watch / vpn-watch を `systemd-run --collect` で起動 (C-5 と同形、ログ名 *-c6.log)
4. smoke ×1-2 (WiFi のまま lid cycle) — suspend/resume 完走 + 最終 RTC 値が成功形 (`Magic 15:1` + device marker) であること
5. 合成 hang (t3) は今回**省略** (decode 経路は C-5 で実弾検証済み、カーネル不変)

## P3: 有効 cycle 反復 (ユーザ物理操作)

1. BT-PAN (iPad 172.20.10.13/28) 接続 → `sudo nmcli con up GSNet` (**autoconnect は効かない — C-5 知見 4、手動必須**)
   → SA 確認 `ip xfrm state | grep -c ^src` = 2 → radio off:
   `sudo systemd-run --unit=radio-off-detached --collect bash -c "sleep 5; nmcli con down OpenWrt; nmcli radio wifi off"`
2. ユーザ: lid 閉 → 10-15 秒 → 開 → **電源短押し**で wake (本機は lid/キーで復帰しない)、反復
3. 有効 cycle 判定: 70-h4-probe の src 172.20.10.13 + xfrm SA (BT_PAN_VALID)
4. **hang 発生時**:
   - **5 分以上放置** (監視判定窓の確保) → 電源 10 秒長押し → 起動 → ユーザが WiFi 復旧
     (`nmcli radio wifi on && nmcli con up OpenWrt`)
   - 即時 decode (正は journal、hwclock は不可 — C-5 知見 2):
     `sudo journalctl -b -k | grep -E "PM: +(RTC time|Magic|trace data|device marker)|hash matches"`
   - 署名分類: A (10:334 / 10:139 = TB noirq entry) / B (14:355 = i915 main entry) / 新規 marker / site
   - pstore 確認 (panic 有無、偽陽性判別)。hang PRE は unpaired PRE で帰属
   - 再 arm (P2-1) して継続。BT-PAN + GSNet も毎回手動再確立
   - 余力があれば hang 中の電源短押し→バックライト応答の再現性も観察 (C-5 論点 iii)
5. **終了条件** (いずれか): (a) decode 済み hang ≥ 2 回、(b) clean 有効 cycle ≥ 12 回
   (ベースライン 42% に対し 0/12 なら p ≈ 0.001 で「介入で hang 率が激減」と言える)、(c) ユーザの体力切れ

## P4: 解釈マトリクス

| 結果 | 解釈 | 次の一手 |
|---|---|---|
| 署名 A 消滅、B 残存、率同等 | TB ブリッジ D3 は A の因果経路上。B は独立 | (余力あれば同夜) i915.enable_dc=0 を追加し Arm 2 |
| hang 消滅 (0/12+) | TB ポート PM が両署名の上流 (または全域効果) | 次セッションで cycle 追加し統計強化、narrow 化 (d3cold_allowed=0) |
| 署名 A 残存 | pcie_port_pm=off では不十分 (platform/ACPI 電源リソース経由の D3cold?) | d3cold_allowed=0 個別指定、ACPI power resource 調査 |
| 率同等・署名が**別デバイスへシフト** | 名指しデバイスは被害者で真因は下層 (C-state/クロック基盤) | dpmwd5 (wait/callback 判別) + intel_idle.max_cstate 系介入へ転進 |

async resume の留保 (最終書込み = 最後に活動していた thread ≠ 単独犯) は解釈全体に維持する。
pcie_port_pm=off は全 PCIe ポート (root port 含む) に効く広域介入である点も解釈に明記。

## P5: テアダウン

- pm_trace=0、sysctl ×3 = 0、watchers 停止、NM 平常化 (radio on / autoconnect / route-metric)、
  RTC 復旧 (NTP 同期 + `hwclock --systohc`)、pstore 空確認
- **pcie_port_pm=off は残置がデフォルト** (次セッション継続用。可逆: /etc/default/grub から削除 +
  update-grub + sync)。残置/撤去は結果を見てユーザに確認し、レポートに記録

## P6: レポート + memory + commit

- `report/` に CLAUDE.md 規約どおり作成 (タイムスタンプは `TZ=Asia/Tokyo date`、概要は段落文 5-8 段落、
  前提・環境・再現方法・関連レポートリンク)
- 添付: 本プランファイル (`report/attachment/<レポート名>/plan.md` にコピー)、証跡 raw (per-boot decode /
  PRE-POST / src-IP gate / watcher log)
- memory `s2idle-btvpn-hang-mechanism-ladder.md` に (o) C-6 エントリ追記、MEMORY.md 索引行更新
- git commit (ローカル。push は求められた場合のみ `./.ssh/git.sh push`)

## 検証方法 (このプラン自体の成否判定)

- 介入の実効性: /proc/cmdline + TB ブリッジ runtime_status の pre/post 差分で確認
- 実験の成否: 終了条件 (a) または (b) に到達し、P4 マトリクスのどの行かを確定できること
- 変更の可逆性: grub.bak-c6 残置 + パラメータ 1 個の削除で完全復元可能なこと

## 主要参照

- 手順一次ソース: report/2026-07-06_002651 (再現方法・decode・知見 1-5)、2026-07-02_182811 (GRUB/sync)
- 事前確度の根拠: 2026-05-22_022030 (i915.enable_dc=0 の S3 時代不発)、2026-06-01_034724 (confound 整理)
