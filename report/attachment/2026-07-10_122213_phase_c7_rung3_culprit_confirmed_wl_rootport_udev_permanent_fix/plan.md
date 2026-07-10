# Phase C-7 Rung 3: 一本釣り — 03:00.0 (wl) 単独 `d3cold_allowed=0` で 00:1c.2 を D0 固定

## Context (なぜやるか)

Rung 2 (report/2026-07-09_205237) で hang の真犯人は非 TB ルートポート 3 本 {00:1c.1 (カメラ親), 00:1c.2 (wl 親), 00:1c.5 (SSD 親)} のいずれかに確定した。本セッションはその引継ぎ第 1 候補 **Rung 3 = 一本釣り** を実施する: `03:00.0` (wl = BCM4360) のみに `d3cold_allowed=0` を書いて **00:1c.2 単独を sleep 中 D0 固定**し、hang が消えるかで真犯人を 1 本に絞る。

00:1c.2 を最有力とする根拠は、hang の必要条件 b'' (wl loaded + radio off) との物理接点がこのポートだけであること。clean なら真犯人 ≈ 00:1c.2 が確定し、恒久対策は「ルートポート 1 本だけの D0 固定」(待機電力 ~0.7W 級と両立見込み) で `pcie_port_pm=off` (待機電力 4〜5 倍) を置き換える道が開ける。

## 実験設計

- **arm tag**: `dpmwd4 + pm_trace=1 + d3cold_allowed=0(03:00.0)` — 単独集計、他 arm と合算しない
- **ベースライン**: 同摂動無保護 pool 9/24 ≈ 38% (C-4/C-5/R1)
- **判定マトリクス** (ユーザ確認済み):
  - **clean 0/30** (全 BT_PAN_VALID、unpaired PRE ゼロ) → 真犯人 ≈ 00:1c.2 確定 (Fisher 片側 p ≈ 1.7×10⁻⁴ 級) → **Rung 3 構成を残置し、そのまま一晩 suspend で待機電力計測** (pcie_port_pm=off に戻さない。恒久対策検収の前倒し)
  - **hang 再発** → 1 回で判定成立 (00:1c.2 単独保護では不十分)。boot 時 kernel decode で停止点署名を回収 → 再起動後に次の一本 = `04:00.0` (→ 00:1c.5) を再適用して**同セッション続行** (それも hang なら `02:00.0` → 00:1c.1)。各 rung は arm tag 分離で単独集計
- **Rung 2 との差分に注意**: 今回は TB downstream への書込みも 02:00.0/04:00.0 への書込みも**行わない**。00:1c.1/00:1c.5/TB 系が従来どおり D3hot で sleep に入ることが実験の要 (smoke で実測確認する)
- **役割分担**: ssh 操作全般 = Claude、テザリング・radio off・GSNet 再確立・lid 開閉・WiFi 復旧 = ユーザ

## 手順 (Rung 1/2 の確立手順の流用、ログ名 c7r3)

### P0: preflight + soak 区間記録

- サンドボックスを `/sandbox` で無効化してもらう (ssh 経路確保)
- 検収: dpmwd4 稼働 (`uname -r`)、pm_trace=0、pstore 空、`intel_pch_thermal.delay_cnt=300`、hooks 5 本 (50/58/59/60/70)、saved default = dpmwd4、AC 接続
- 7/9 20:52 以降の soak 区間 (pcie_port_pm=off) の suspend ペア完全性・hang 0 を記録

### P1: 介入切替 (要再起動)

```bash
sudo cp /etc/default/grub /etc/default/grub.bak-c7r3
sudo sed -i 's/ pcie_port_pm=off//' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot
```
- 検収: `/proc/cmdline` に pcie_port_pm=off が無い、数分後に 06:03-06 + 00:1c.0 が runtime D3hot に戻る (C-6 介入前スナップショットと一致)

### P1b: 副観測 O3 (軽量、cycle 消費なし) — radio on/off の PME/wake 設定差

R2 引継ぎ 3 (機序 C-7 (iv))。O1/O2 で D-state 差は消去済みなので、次の層を観測:
- radio on / off それぞれで `sudo lspci -vv -s 03:00.0` と `-s 00:1c.2` の PME enable / PM 状態、`/sys/bus/pci/devices/0000:03:00.0/power/wakeup` と 00:1c.2 の同値を比較記録
- 差が出れば「radio off が D3hot 復帰を壊す」機序の直接手がかり。差ゼロもそれ自体が消去情報

### P1c: Rung 3 適用 + smoke S1 (実効の直接観測)

```bash
echo 0 | sudo tee /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed
```
- 90 秒後検収: **00:1c.2 = runtime active/D0**。03:00.0 自身は D0 のままになる想定 (R2 知見 4: endpoint は autosuspend しない、sleep 挙動には影響なし)
- smoke S1: dynamic debug + pm_debug_messages を有効化して WiFi のまま lid cycle 1 回 → sleep 中実効を実測:
  - `00:1c.2 = D0 のまま sleep` (これが介入の実効)
  - **00:1c.1 / 00:1c.5 = D3hot 遷移** (非保護に戻っていること = 実験の要)
  - TB 系・00:1c.0 は従来どおり
```bash
echo 1 | sudo tee /sys/power/pm_debug_messages
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
# 回収: journalctl -b 0 -k -o short-unix | grep -E "Suspend power state|power state changed by ACPI"
```

### P2: arm + smoke + 本番

- 観測系 (pm_debug/dynamic debug) を無効化してベースライン同等 arm に戻す
- arm: `sysctl kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1`、`pm_trace=1`、`SESSION-C7R3-START.marker` (epoch 記録)、watchers 起動 (C-6 レポート「再現方法」のコマンド、ログ名 c7r3):
  - cycle-watch-c7r3 (journalctl -k -f で PM: suspend entry/exit 追記)
  - vpn-watch-c7r3 (root 必須 — 非 root の `ip xfrm state` は常に 0)
- smoke S2-S3: WiFi のまま lid cycle ×2、decode 成功形 (`Magic 15:1`) を **resume 検知即読ワンショット** (R2 知見 2 の systemd-run ワンライナー) で確認
- 本番: ユーザが BT-PAN 接続 → radio off → **BT-PAN 上で `nmcli con up GSNet` 再確立** (C-6 知見 1 の順序) → Claude が `sudo ip xfrm state` で SA 双方向 (172.20.10.13 ⇔ 160.16.210.47) 確認 → lid cycle 反復 (閉 → 10-15 秒 → 開 → 電源短押し wake)
- 有効性判定は各 PRE の ESP SA 双方向厳密一致 (70-h4-probe PRE ファイル)。目標 **有効 30 cycle** (hang 1 回で当該 rung 打ち切り → decode 回収 → 次の一本へ)

### P3: 判定 + 復旧

- 台帳機械検証: SESSION epoch 以降の PRE 全数、paired/unpaired、BT_PAN_VALID 数、pstore、boot ID 不変
- 統計: Fisher 片側 (vs 9/24)
- **clean の場合**: pcie_port_pm=off には戻さず **Rung 3 構成 (03:00.0 の d3cold_allowed=0、sysfs のみ・再起動しない) を残置して一晩 suspend → 待機電力計測** (charge_now 差分、7/7 レポートの手法)。teardown (pm_trace=0 等) は計測開始前に済ませる。~0.7W 級に収まれば恒久対策 (boot 時フック/udev 化) の実装は次セッション
- **hang で全 rung 終了の場合**: `grub.bak-c7r3` から復元 → update-grub + sync + reboot → 全ポート D0 常駐検収 → 従来 soak 継続
- teardown: pm_trace=0、sysctl 3 種 =0、watchers 停止、`hwclock --systohc`、NM 平常確認

### P4: レポート作成 + メモリ更新

- `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得、`report/` に作成 (CLAUDE.md 規約: 概要は通読できる段落、前提・環境・再現方法・参照レポート)
- 証跡 (marker / cycle-watch / PRE 台帳 / vpn-watch / smoke D-state / O3 / pstore / boot) を `report/attachment/<レポート名>/` に回収、本プランを plan.md としてコピー
- メモリ `s2idle-btvpn-hang-mechanism-ladder.md` に Rung 3 の結果を追記、MEMORY.md 索引更新
- セルフレビュー 2 段階 (書き漏らし → 矛盾点検)

## 罠リスト (歴代知見の適用)

- grub 変更後は `sync` 必須 (182811)
- `ip xfrm state` は sudo 必須 (C-6 知見 2)
- 現 boot 調査は `journalctl -b 0` (--since は RTC 汚染 timestamp を拾う)
- 再起動判定は boot ID + systemd-run ユニット生存 (`uptime -s` は pm_trace 中信用不可、R2 知見 1)
- hang 時の decode は boot 時 kernel decode 行 (journal 永続)、成功形はワンショット即読 (R2 知見 2)
- `d3cold_allowed` 書込みは一時 resume を誘発 → 検収は 90 秒待ち (R1 知見 2)
- 03:00.0 は書込み後 runtime D0 のままになるが sleep 挙動には無影響 (R2 知見 4)
- /var/log/h4-probe の既存ファイルは削除しない

## 成功/検証基準

- smoke S1 で「00:1c.2 のみ D0 固定、00:1c.1/1c.5 は D3hot」の設計状態を実測確認できること
- 本番 cycle の有効性 (BT_PAN_VALID) が PRE で機械検証できること
- clean なら 0/30 + Fisher p、hang なら decode 署名の回収、いずれでも判定が成立すること
- 実験後に実機が保護状態 (ユーザ選択の構成) で soak 継続していること
