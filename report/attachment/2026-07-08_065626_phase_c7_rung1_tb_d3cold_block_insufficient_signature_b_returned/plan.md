# Phase C-7 (i): 絞り込み介入 — TB downstream ポートのみ d3cold_allowed=0 で hang 抑止と待機電力の両立を検証

## Context (背景と目的)

- C-6 で `pcie_port_pm=off` (広域介入) により対象 hang が 0/30 で消滅 (Fisher 片側 p≈1.7×10⁻⁴)、以後常用 soak 中。
- 7/7 レポート (2026-07-07_230853) で soak ウォッチリスト (iii) が現実化: **suspend 中待機電力 2.8〜3.4 W ≈ 従来 s2idle 0.70 W の 4〜5 倍** (≈7〜9%/h 消費、鞄内発熱)。モバイル運用の実害が確定し、C-7 (i) 絞り込みの優先度が上昇。
- 本実験の目的は 2 つ:
  - **(a) 真犯人の絞り込み**: 広域 `pcie_port_pm=off` を外し、TB downstream ポートのみ `d3cold_allowed=0` にして hang 署名が戻るかを見る。戻らなければ「TB downstream ポートの D3cold (電源断) が hang の必要条件」まで絞れる。戻れば「D3hot→D0 resume でも hang する」が確定し次の rung へ。
  - **(b) 実用**: hang 抑止と待機電力 0.7 W 級の両立構成を確立する。

## 機序の裏取り (v6.12.94 ソース、実験設計の根拠)

`src/linux-6.12.y` (実機稼働版と同一) で確認済み:

| ノブ | 効果 (ソース根拠) |
|---|---|
| `pcie_port_pm=off` (現行) | `pci_bridge_d3_disable=true` → 全 PCIe ポートの bridge_d3 不可 (pci.c:3046)。runtime も system sleep も D0 常駐 = 電力 4〜5 倍の元凶 |
| **`d3cold_allowed=0` をポート X に書く (今回の Rung 1)** | (1) X 自身の target state が **D3hot 止まり** (D3cold 禁止): `acpi_pci_choose_state` が d_max=D3_HOT にキャップ (pci-acpi.c:926)、runtime/system sleep 両経路 (`pci_target_state`→`platform_pci_choose_state`, pci.c:2695) に効く。(2) sysfs write が `pci_bridge_d3_update(X)` を呼び (pci-sysfs.c:579)、**X の上流 bridge chain (05:00.0 → 00:1c.1) の bridge_d3 がクリアされ D0 常駐** (pci.c:3117-3159, `pci_dev_check_d3cold` pci.c:3095 が `!d3cold_allowed` で false) |
| `power/control=on` (Rung 2 候補) | runtime D3 のみ禁止。system sleep では `pci_prepare_to_sleep` が別途 target を決めるため D3hot に落ちうる (単独では不完全、実効は pm_debug_messages で経験的確認要) |

**重要な事前知見** (C-6 証跡 c6-evidence-raw.txt): 介入前 (デフォルト) の runtime D3hot 組は **06:03.0 / 06:04.0 / 06:05.0 / 06:06.0 (TB downstream、配下空) + 00:1c.0 のみ**。05:00.0 (TB upstream)・06:00.0・00:1c.1/2/4/5 は元々 D0 常駐。
→ Rung 1 の runtime 状態はデフォルトとほぼ同一 (downstream 4 ポートは D3hot に落ちたまま) で、**変わるのは sleep 中の D3cold 禁止だけ。待機電力コストはほぼゼロと期待できる**。

## 実験設計

### 介入 (Rung 1)

```bash
# pcie_port_pm=off を撤去 (要再起動) した後、sysfs で:
for p in 06:03.0 06:04.0 06:05.0 06:06.0; do
  echo 0 | sudo tee /sys/bus/pci/devices/0000:$p/d3cold_allowed
done
```

- 対象 = TB downstream 4 ポート全部 (署名 A の 06:03.0/06:06.0 を含む対称スコープ)。00:1c.0 は**意図的にデフォルトのまま** (hang が戻った場合の判別材料)
- sysfs は再起動で揮発。セッション中は再起動しないので手動適用で足りる (採用時に永続化)

### arm 条件 (C-6 と同一の高再現条件)

- kernel 6.12.94-dpmwd4 + pm_trace=1 + sysctl panic 3 種 + BT-PAN (iPad 172.20.10.x) + GSNet VPN + WiFi radio off
- **arm tag: `dpmwd4 + pm_trace=1 + d3cold_allowed=0(TB-downstream)`** — ベースライン = 同摂動 arm 8/19 ≈ 42% (C-4+C-5)。pcie_port_pm=off arm (0/30) とも非摂動 pool (7.1%) とも合算しない
- 有効性判定は 70-h4-probe の PRE ファイル (BT-PAN アドレスの ESP SA 双方向) で機械確認

### 判定マトリクス

| 結果 | 解釈 | 次アクション |
|---|---|---|
| hang 0/30 + 電力 ~0.7 W | **D3cold が hang の必要条件** (D3hot resume は無害)。両立構成成立 | 永続化して soak 切替 (ユーザ回答済み) |
| hang 0/30 だが電力高止まり | hang 面は成功、電力面で想定外 (他要因が PCH を起こしている) | ポート状態スナップショットで犯人捜し、構成は当日判断 |
| hang 再発・署名 A (06:0x noirq entry) | **D3hot→D0 resume でも hang する** → D3cold 単独犯説棄却 | pcie_port_pm=off へ復帰。Rung 2 (per-port D0 pin = dpmwd5 quirk 等) を次回検討 |
| hang 再発・別署名 (00:1c.0 系など) | 真犯人が TB downstream 以外にもいる | decode 結果を記録し、対象を追加した Rung 1' を設計 |

hang 1 回で判定には十分 (decode で停止点実名が取れる)。clean 側は 30 cycle で p≈1.7×10⁻⁴。

## セッション手順

役割分担: ssh 操作全般 = Claude、テザリング・lid 開閉・WiFi 復旧 = ユーザ。実機コマンドはすべて `ssh miminashi@macbookair2015.lan` 越し (サンドボックスは `/sandbox` で一時無効化)。

### P0: preflight (C-6 と同一 + 今回追加分)

1. dpmwd4 稼働 / pm_trace=0 / pstore 空 / delay_cnt=300 / hooks 5 本 / saved default / AC 接続を確認
2. soak 終了スナップショット: soak 期間 (7/6〜) の hang 0 実績を `/var/log/s3-soak.log` と journal で最終確認 (レポート用)
3. 現状ポート状態記録 (pcie_port_pm=off 下: 全 D0 のはず)

### P1: 介入切替 (要再起動)

1. `sudo cp /etc/default/grub /etc/default/grub.bak-c7`
2. `GRUB_CMDLINE_LINUX_DEFAULT` から ` pcie_port_pm=off` を削除 → `update-grub && sync` (**sync 必須**、182811 の教訓) → 再起動
3. 検収: `/proc/cmdline` に pcie_port_pm=off が無い / 数分後に 06:03-06 が runtime suspended/D3hot へ戻る (デフォルト挙動復帰の実効確認) / 00:1c.0 D3hot / pstore 空
4. **Rung 1 適用**: 4 ポートへ `d3cold_allowed=0` → 検収: 各 `d3cold_allowed`=0、06:03-06 は D3hot のまま (期待どおり)、05:00.0/00:1c.1 の runtime_status=active 継続
5. (best-effort) `pm_debug_messages=1` で WiFi のまま smoke 1 cycle → journal (`-b 0`) から対象ポートの suspend 時 target state (D3hot 止まりか) を確認できれば記録。取れなくても続行 (判定は hang 有無と電力で行う)

### P2: arm + 本番 cycle

1. sysctl: `hung_task_panic=1 hardlockup_panic=1 softlockup_panic=1`
2. `pm_trace=1`、`SESSION-C7-START.marker` (epoch)、watchers 起動 (C-6 再現方法のコマンドをログ名 c7 で流用: cycle-watch-c7 / vpn-watch-c7。vpn-watch は root 必須)
3. smoke ×2 (WiFi のまま、ユーザ lid cycle) → RTC decode が成功形 (`Magic 15:1` + device:4e 相当) であること
4. ユーザ: BT-PAN 接続 → radio off → **BT-PAN 上で `nmcli con up GSNet` を手動再確立** (C-6 運用知見 1 の正順) → Claude: `sudo ip xfrm state | grep -c ^src` = 2 を確認 (**sudo 必須**)
5. 本番 cycle ×30: lid 閉 → 10-15 秒 → 開 → 電源短押し wake (本機の s2idle wake は電源短押しのみ)。cycle-watch のペア成立を随時確認

### 停止規則

- **hang 発生 → その場で終了 (判定成立)**: 5 分以上放置 (crawl 否定の再確認) → 電源長押し → 再起動 → RTC decode (59-pmtrace-timefix hook 稼働、firmware-safe encoding。**成功 cycle 対照と boot リセット値 00:00:13 の罠に注意** — decode は必ず対照付きで) + pstore 確認 → 判定マトリクスに従う
- clean 30 cycle 到達 → P3 へ
- watchdog panic (pstore にダンプあり) → 偽陽性か対象 hang かを pstore の対象デバイスで判別 (012628 の手順)

### P3: 待機電力計測 (clean の場合、同夜 2〜3 時間区間)

1. テアダウン先行: `pm_trace=0` (RTC 汚染防止)、sysctl 3 種 → 0、watchers 停止、RTC 実時刻復旧 (`hwclock` / NTP)、WiFi 復旧
2. **d3cold_allowed=0 は維持したまま** (同一 boot 内なので揮発しない)、AC を抜いてバッテリ suspend 2〜3 時間
3. 60-s3-soak-log の charge_now 差分から算出: `W = ΔmAh/1000 × 7.6 ÷ h`。**判定: ≤1.0 W なら成功** (0.7 W 級復帰)、2 W 台なら「電力高止まり」行へ
4. 両端 ac=0 のクリーン区間になるよう、suspend 突入後に AC が残らないこと (7/7 レポート区間 1 の下限値問題を回避)

### P4: 残置構成の切替 (clean + 電力良好の場合、ユーザ回答済み方針)

1. 永続化: systemd oneshot service (前例 = s3-deep-apply.service の形式) で boot 時に 4 ポートへ `d3cold_allowed=0` を書く `c7-tb-d3cold-off.service` を作成・enable
2. `pcie_port_pm=off` は撤去済みのまま → **新 soak 構成 = dpmwd4 + d3cold_allowed=0(TB) で常用 soak 継続**。ウォッチリスト: (i) hang 再発 (超一級データ、5 分放置→長押し→報告)、(ii) 原因不明再起動 (pstore で判別)、(iii) 待機電力 (0.7 W 級維持の確認)
3. hang 再発時の即時退避 = `pcie_port_pm=off` 復帰 (`grub.bak-c7` から戻す or sed 追加 + update-grub && sync)

hang が戻った場合: `pcie_port_pm=off` を即日復帰 (モバイル時はシャットダウン/ハイバネート運用継続) し、decode 結果を記録して終了。

### レポート

- `report/` に C-7 レポート作成 (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)、本プランを `report/attachment/<レポート名>/plan.md` へコピー、証跡 (cycle-watch / PRE 照合 / ポート状態スナップショット / 電力計算) を添付
- メモリ (s2idle-btvpn-hang-mechanism-ladder) に C-7 結果を追記

## 統計設計

- clean 判定: 0/30 vs ベースライン 8/19 → Fisher 片側 p≈1.7×10⁻⁴ (C-6 と同等)
- 途中経過の目安: 0/12 時点で p≈0.0096 (有意水準到達、以降は強化)
- hang 判定: 1 回で decode により定性的に成立 (率の比較は不要)

## 罠リスト (既知、セッション中に踏まないこと)

- `ip xfrm state` は非 root で 0 件に見える → 必ず sudo
- radio off は WiFi 上の SA を道連れ → radio off **後** に GSNet 再確立
- grubenv/grub 変更後は `sync` 必須
- journal 調査は必ず `-b 0` (pm_trace 時代の RTC 汚染 timestamp 混入)
- cycle-watcher は smoke を cycle に計上 → 本番カウントは SESSION marker epoch 以降の PRE で照合
- RTC decode は成功 cycle 対照を必ず取る (boot リセット値 00:00:13 = `Magic 0:1:0` の偽 main.c:1728 に注意)
- pm_trace=1 中の hour 汚染 (60 分超放置) は decode.py の -1h 補正で解読可

## 検証 (verification)

- 介入の実効: sysfs 読み戻し + ポート runtime 状態スナップショット (P1-4)、best-effort で pm_debug_messages (P1-5)
- hang 有無: cycle-watch の suspend entry/exit ペア (unpaired PRE ゼロ = hang ゼロ) + pstore 空
- cycle 有効性: PRE ファイルの BT-PAN アドレス ESP SA 双方向照合 (30/30)
- 電力: soak ログ charge_now 差分 ≤1.0 W
- 永続化 (P4): 再起動 → service 発火 → 4 ポートの d3cold_allowed=0 を読み戻し確認

## 参照

- [7/7 soak 中間観測 (本実験の動機)](report/2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)
- [C-6 pcie_port_pm=off 0/30 (arm 手順・watcher コマンド・ベースラインの一次ソース)](report/2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)
- [C-5 停止点実名 (署名 A/B、decode 手順)](report/2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- ソース根拠: `src/linux-6.12.y/drivers/pci/pci.c:3037` (pci_bridge_d3_possible), `pci.c:3090` (pci_dev_check_d3cold), `pci.c:3117` (pci_bridge_d3_update), `pci.c:2695` (pci_target_state), `pci-acpi.c:926` (acpi_pci_choose_state の D3cold キャップ), `pci-sysfs.c:568` (d3cold_allowed_store)
