# Phase C-7 第 2 段 (Rung 2): sysfs 半割り — 非 TB root port の D0 固定で真犯人を二分する

## Context

C-7 Rung 1 (2026-07-08_065626) で「TB downstream 4 ポートの d3cold_allowed=0 (+ TB 上流チェーン D0 常駐)」では hang を防げないことが確定した (有効 cycle 1/5 で hang、停止点 = 署名 B: i915 main resume entry の三度目の完全再現)。`pcie_port_pm=off` (hang 0/30) が保護し Rung 1 が保護しなかった容疑者は 2 群に絞られている:

- **(α) 非 TB root port 群**: 00:1c.1 (→02:00.0) / 00:1c.2 (→03:00.0 = wl) / 00:1c.5 (→04:00.0 = ahci) は sleep 時 D0→D3hot 遷移を実測済み。00:1c.0 (配下なし) は runtime D3hot のまま突入
- **(β) TB downstream 06:03-06 の D3hot そのもの** (D3cold ではなく)

本セッションは Rung 1 レポートの引継ぎ第 1 候補「**sysfs 半割り (リビルド不要、推奨)**」を実施する。子デバイス側に `d3cold_allowed=0` を書くと親 root port の bridge_d3 がクリアされ D0 常駐になる機序 (pci.c:3095-3159、Rung 1 で実証済み) を使い、Rung 1 の保護に **02:00.0 / 03:00.0 (wl) / 04:00.0 (ahci) への書込みを追加**して 00:1c.1 / 00:1c.2 / 00:1c.5 を D0 固定する。これで「非 D0 で sleep に入るポート = 00:1c.0 と 06:03-06 の D3hot のみ」まで絞れる。

**判定マトリクス**:
- **hang 再発** (1 回で成立、RTC decode で停止点実名取得) → 真犯人 ∈ {00:1c.0, 06:03-06 の D3hot}。00:1c.0 は配下なしで sysfs では D0 固定不可 → dpmwd5 (per-port quirk カーネル) へ
- **clean 0/30** (同摂動ベースライン 8/19≈42% に対し Fisher 片側 p≈1.7×10⁻⁴) → 真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5}。以後 1 本ずつ半割り (00:1c.2 = wl 親が必要条件 b'' との接点で最有力)

副目的として、引継ぎ候補 2「**radio on/off のポート電源遷移比較**」(軽量、dynamic debug 観測のみ、cycle 2 回) を同一 boot の smoke 段階に同梱する。00:1c.2 (wl 親) の suspend 時遷移が radio on/off で変わるかを見て、解釈 4 (wl 接点仮説) を検証する。

## 前提 (実機現状、2026-07-08 15:07 JST 確認済み)

- kernel 6.12.94-dpmwd4 稼働、cmdline に `pcie_port_pm=off` あり (C-6 構成で soak 中)
- pstore 空、pm_trace=0、watcher 停止、hooks 5 本 (50/58/59/60/70)、d3cold_allowed 全 1
- AC 接続、BAT 90%
- 現 boot (7/8 06:53〜) は suspend 0 回 (soak 経過は P0 で記録)
- 役割分担: ssh 操作全般 = Claude、テザリング・lid 開閉・WiFi 復旧 = ユーザ
- 注意: radio off / BT-PAN 中は開発機からの ssh が切れる。ログは実機の hook/watcher が自律収集し、WiFi 復旧後に回収する (従来どおり)

## 手順

### P0: preflight + soak 終了記録

1. dpmwd4 / pm_trace=0 / pstore 空 / delay_cnt=300 / hooks 5 本 / saved default / AC を確認
2. 現 soak 区間 (7/8 06:53〜) の suspend entry/exit ペア・fail・hang 0 を journal で記録 (soak 一時中断の台帳)
3. sysctl panic 3 種の現在値を記録 (終了時の復元用)

### P1: 介入切替 + デフォルト検収

1. `sudo cp /etc/default/grub /etc/default/grub.bak-c7r2`
2. `sudo sed -i 's/ pcie_port_pm=off//' /etc/default/grub` → `sudo update-grub && sudo sync` → 再起動 (**sync 必須**、grubenv 教訓)
3. 検収: `/proc/cmdline` に pcie_port_pm=off なし、数分後に 06:03-06 + 00:1c.0 が runtime D3hot/suspended に戻る (C-6 介入前スナップショット一致)

### P1b: radio on/off ポート遷移比較 (副目的、BT 不要)

1. dynamic debug 有効化: `pm_debug_messages=1` + `pci-driver.c +p` + `pci-acpi.c +p`
2. **cycle O1 (radio on)**: WiFi 接続のままユーザが lid cycle → journal の `Suspend power state` 行で 00:1c.x / 03:00.0 の遷移を記録
3. **cycle O2 (radio off)**: ユーザ (または Claude が ssh 切断覚悟で) `nmcli radio wifi off` → lid cycle → ユーザが radio on 復旧 → 同様に記録
4. 比較: 00:1c.2 と 03:00.0 (wl) の suspend 時 D-state が radio on/off で異なるか (異なれば解釈 4 の直接証拠)
5. 注意: radio-off 単独は歴史 pool で clean (無線なし 9/9) だが、万一 hang したらそれ自体一級データ (5 分放置 → 長押し → decode)

### P1c: Rung 2 適用 + 実効検収

1. 7 デバイスへ書込み:
   ```bash
   for p in 06:03.0 06:04.0 06:05.0 06:06.0 02:00.0 03:00.0 04:00.0; do
     echo 0 | sudo tee /sys/bus/pci/devices/0000:$p/d3cold_allowed
   done
   ```
2. 検収 (書込み直後の一時 D0 resume があるため 90 秒待ってから): 00:1c.1 / 00:1c.2 / 00:1c.5 / 00:1c.4 / 05:00.0 が runtime_status=active (D0 常駐)、06:03-06 が D3hot 復帰
3. **smoke S1 (WiFi、dynamic debug 継続)**: lid cycle 1 回 → sleep 中の実効を直接確認: 00:1c.1/2/5 が D0 のまま (Suspend power state 行なし or D0)、非 D0 は 00:1c.0 と 06:03-06 の D3hot のみ

### P2: arm + smoke + 本番

1. 本番前に dynamic debug / pm_debug_messages を無効化 (arm をベースライン同等へ)
2. arm: `sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1`、`pm_trace=1`、`SESSION-C7R2-START.marker` (epoch 記録)、watchers 起動 (C-6 再現方法のコマンド、ログ名 `cycle-watch-c7r2` / `vpn-watch-c7r2`)
3. **smoke S2-S3 (WiFi)**: lid cycle ×2 完走 + RTC decode 成功形 (`Magic 15:1`) 確認
4. **本番**: ユーザが BT-PAN 接続 → radio off → BT-PAN 上で `nmcli con up GSNet` → Claude 到達不能になる前に `sudo ip xfrm state | grep -c ^src` = 2 を確認 (sudo 必須の罠) → ユーザが lid cycle 反復 (閉 → 10-15 秒 → 開 → 電源短押し wake)
5. 目標 30 有効 cycle (C-6 同等の検出力)。hang したら即終了: 5 分以上放置 (crawl 否定確認) → 電源長押し → 再起動

### P3: 判定

- 有効性判定は PRE ファイルの ESP SA 双方向厳密一致 (`src 172.20.10.13 dst 160.16.210.47` / 逆向き)、SESSION marker epoch 以降のみ集計
- hang = unpaired PRE。hang 時は再起動直後の boot 時 kernel decode 行 (`journalctl -b 0 -k | grep -iE "magic|hash match"`) で停止点実名を取得 (RTC 生値は NTP 上書きされるため journal 永続行が正)
- pstore の有無を必ず確認 (panic 対象デバイスで対象 hang / 偽陽性を判別)

### P4: 復旧 + レポート

1. `sudo cp /etc/default/grub.bak-c7r2 /etc/default/grub` → `update-grub && sync` → 再起動 → 全ポート D0 常駐を検収 (`pcie_port_pm=off` 復帰 = soak 再開)
2. pm_trace=0 / sysctl 復元 / watcher 停止 / dynamic debug 無効を確認 (d3cold_allowed は再起動で自然揮発)
3. NTP 同期 + `hwclock --systohc` (RTC 汚染の掃除)
4. レポート作成: `report/` に新規 md (タイムスタンプは `TZ=Asia/Tokyo date` で取得)、添付ディレクトリに本プランファイル + 証跡 (marker / cycle-watch / PRE 台帳 / decode / D-state 比較ログ) をコピー、CLAUDE.md のセルフレビュー 2 段階を実施
5. メモリ (s2idle-btvpn-hang-mechanism-ladder.md) に C-7 第 2 段の結果を追記

## 統計・解釈の規約 (従来どおり)

- 本 arm の tag = `dpmwd4 + pm_trace=1 + d3cold_allowed=0(TB-downstream + 02/03/04:00.0)`。他 arm と合算しない
- ベースライン = pm_trace 摂動・無保護 pool 9/24 ≈ 38% (C-4/C-5/C-7R1)
- clean 判定は 0/30 で Fisher 片側 p≈1.7×10⁻⁴ (対 8/19)

## 検証 (verification)

- P1/P1c/P4 の各検収は sysfs (`runtime_status` / `d3cold_allowed`) と dynamic debug ログの実測で行う (設計値でなく実測で確認するのが C-7 R1 からの流儀)
- cycle 台帳は cycle-watch ログ (suspend entry/exit の short-unix ペア) + PRE/POST ファイルの突合で機械検証
- 判定成立後の実機状態がレポート「残置物」表と一致することを最終確認

## リスクと対処

- **hang 発生時**: 想定内 (判定成立)。ユーザ操作 = 5 分放置 → 電源長押し。decode は boot 時 journal 行で
- **dpmwd4 の DPM watchdog 偽陽性** (intel_pch_thermal 系): delay_cnt=300 で緩和済み。再起動検知時は pstore で対象 hang / 偽陽性を必ず判別
- **`journalctl --since` の RTC 汚染 timestamp**: 現 boot 調査は必ず `-b 0` を使う
- **ssh 断**: radio off / BT-PAN 中は到達不能が正常。焦って再試行の連打をしない (watcher が自律収集)
