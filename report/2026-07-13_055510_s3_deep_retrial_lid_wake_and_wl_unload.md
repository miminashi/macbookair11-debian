# S3 スリープ再挑戦 — lid open 復帰は復活できる (ただし wl unload が条件)

- **実施日時**: 2026年7月13日 03:16〜14:05 (JST、05:55〜13:58 は Phase 4 自動計測)
- **執筆者**: Claude Fable 5
- **対象機**: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / kernel 6.12.95+deb13-amd64 (stock)

## 概要

suspend hang 問題の真因確定 (wl 親ポート 00:1c.2 の D3 復帰不全、Phase C-7/C-8) を受けて、6/27 に no-go とした S3 (deep) スリープを再検証した。狙いは s2idle では構造的に不可能な「lid open でスリープ復帰」の復活である。当時の no-go の根拠だった「内在的 S3-deep hang」が実は現真因と同根なら、恒久対策 (udev rule) つきの S3 は成立するかもしれない、という仮説からの再挑戦だった。

結果は「半分当たり・半分外れ・最後に別の道が開けた」。まず lid wake そのものは疑いなく復活した。今日一日で **lid open による S3 復帰は 38 回成功・失敗 0** (gpe70 経由の配送を毎回確認)、4 分放置後の復帰も含めて完璧に動いた。しかし外れた方は udev 保護の効力で、s2idle では 0/67 を叩き出した保護が、**S3 では最強ストレス条件 (BT-PAN + VPN + WiFi radio-off) で hang 2/4 (50%)** と全く無力だった。S3 ではプラットフォームがバス電源そのものを落とすため、ソフトウェア上 D0 を維持しても意味がない — 保護の実効メカニズムが S3 には存在しないのだと解釈できる。

そこで開けた別の道が wl unload である。C-7 (f) で確立した bedrock「hang の必要条件 = wl が loaded かつ radio-off」が S3 にも当てはまるなら、suspend 前に wl を module ごと外せば hang は消えるはずで、実際に **wl unload アームは同一ストレス条件で 21/21 全 clean** (全 cycle を BT_PAN_VALID + wl unload の両方で機械確認)。wl loaded 2/4 との対比は Fisher 片側 p = 0.02 で有意であり、bedrock は S3 に拡張された。「S3 + suspend 時 wl unload フック」が lid wake 復活の採用候補構成として確定した。

残る障壁だったバッテリ時 spurious wake (gpe70 = LID0 _PRW) も再確認した。バッテリ + LID0 有効の S3 は今も **決定論的に 6 秒で誤起床** (3/3、gpe70 毎回 +1) し、LID0 凍結で 63 秒完走する対照も取れた。firmware 挙動は 6/18 から不変であり、恒久ポリシーは「**AC 接続時のみ LID0 有効 = AC では lid open 復帰、バッテリでは従来通り電源ボタン復帰**」の動的切替が妥当である。

最後の待機電力も文句なしだった。`s3-soak-measure.sh` による 8 時間計測 (バッテリ、LID0 凍結) の結果は **0.0917W** — 無保護時代の 0.098W (6/19) と同じ桁で udev 保護の電力ペナルティはゼロ、現行 s2idle+保護 (~1.6W) の約 1/17 である。全検証は runtime の `echo deep` のみで行っており、GRUB・service・フックは一切変更していない (強制断 → 再起動で自動的に s2idle へ戻るフェイルセーフを 2 回の hang で実地確認済み)。恒久化 (wl unload フック + AC 連動 LID0 + deep 化 oneshot) はユーザの採否判断を経て次のステップで行う。

## 前提・目的

- 背景: hang 問題解決後も、s2idle の制約で「lid open で復帰」ができない (復帰は電源ボタン短押しのみ)。lid wake は S3 でのみ機能する (gpe70 経由)。
- 目的: udev 保護つき S3 で hang が消えているかを検証し、消えていれば lid wake を復活させる。
- 仮説: 6/27 の「内在的 S3-deep hang」は現真因 (wl war × 親ポート D3 復帰) と同根 → 保護で消えるはず。**この仮説は棄却された** (保護は S3 で無力)。代わりに bedrock (wl loaded ∧ radio-off = 必要条件) の S3 拡張が成立した。
- 安全設計: 全フェーズ runtime `echo deep > /sys/power/mem_sleep` のみ。再起動で s2idle に自動復帰。

## 環境情報

- 対象機: MacBook Air 11" (Early 2015)、Debian 13 (trixie)、kernel **6.12.95+deb13-amd64 (stock)**
- cmdline: `quiet no_console_suspend mem_sleep_default=s2idle panic=15` (不変)
- udev 保護: `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` (03:00.0 d3cold_allowed=0) — 全フェーズで有効のまま
- LID0: `*enabled` で開始 (Phase 4 計測中のみ凍結、終了後に戻す)
- ストレス条件: iPad BT-PAN (enx98e0d98d205e, 172.20.10.13/28) + strongSwan GSNet (SA peer 160.16.210.47) + `nmcli radio wifi off`
- 計測ハーネス: 70-h4-probe (PRE/POST 台帳)、cycle-watch/vpn-watch (systemd-run)、c9-bus-snap.sh (AER 残渣)、60-s3-soak-log
- 電源: Phase 1-2 は AC (バッテリ 91%)、Phase 3-4 はバッテリ (89%)

## Phase 0: 現状検収

C-9 撤収検収 (2026-07-12) との差分は 1 点のみ: `s3-deep-apply.service` は「unit ごと削除済み」と記録されていたが、実際は **unit + スクリプトとも残存・disabled** だった (起動時発火はないので検証に影響なし)。他は全て記録通り (6.12.95 / s2idle / d3cold=0 / LID0 enabled / hooks 5 本 / pstore 空)。

**Phase 5 での注意**: `/usr/local/sbin/s3-deep-apply.sh` を流用する場合、LID0 凍結行 (2 節) の除去が必要 (今回の設計では LID0 は AC 連動の動的制御にするため)。

## Phase 1: S3 smoke — 保護の実効性と lid wake (結果: lid wake 完全復活)

1. runtime deep 化 + dynamic debug (`pci-driver.c +p`, `pci-acpi.c +p`)
2. **cycle 1 (rtcwake 60s)**: 完走。journal で真の S3 (`Preparing to enter system sleep state S3` → `Waking up from S3`) を確認。**`PCI PM: Suspend power state:` で D0 なのは 00:1c.2 のみ** (wl・他 root port・TB 系は D3hot) — s2idle 時の smoke と完全同型で、**ソフトウェア層では保護は S3 でも作動している**。
3. **cycle 2-16 (lid wake ×15、AC)**: 全て lid open だけで復帰。**gpe70 が 0 → 15** (lid wake が gpe70 経由である動かぬ証拠。s2idle 時代は常に 0)。4 分 15 秒スリープの回も即復帰。drm/i915 エラー 0。
   - 1 回だけユーザが誤って電源ボタンを押下 (04:19:09) したが、押下時点で既に復帰済み → 新たな suspend を誘発 → 即 wake の無害な挙動でデータ汚染なし。
4. resume 後の `ACPI _REG evaluation failed (5)` は C-8 の clean な s2idle cycle ログ (c8-t1〜t3-full.log) にも同一の形で出ている**既知の無害ノイズ**と確認 (S3 特有でも新規でもない)。

## Phase 2: hang ストレス (結果: 保護は S3 で無力 = hang 2/4)

marker `SESSION-S3R-START` (epoch 1783884430) 以降、BT-PAN + GSNet + radio-off の lid close cycle。

| PRE epoch | JST | paired | BT_PAN_VALID | wl loaded | 判定 |
|---|---|---|---|---|---|
| 1783886365 | 04:59:25 | ✓ | ✓ | ✓ | clean |
| 1783886404 | 05:00:04 | ✓ | ✓ | ✓ | clean |
| 1783886510 | 05:01:50 | **✗** | ✓ | ✓ | **hang #1** (5 分放置 → 長押し断) |
| 1783887696 | 05:21:36 | **✗** | ✓ | ✓ | **hang #2** (wl unload 手順の失念による再現 = 意図せぬ追試) |

- **wl loaded アーム: hang 2/4 (50%)**。s2idle + 同保護の 0/67 (Rung 2 0/30 + Rung 3 0/37) と対照的で、**udev 保護は S3 の hang を防げない**。
- 解釈: S3 ではプラットフォームがバス電源を落とすため、suspend 時にソフトウェア D-state を D0 に保っても resume は実質フルパワーオンからの復帰になる。s2idle の保護実効 (「D3 に入れない」) に相当するメカニズムが S3 には存在しない。**6/27 の「内在的 S3-deep hang」もこの同根現象だった可能性が濃厚** (当時の「suspend 側停止」判断は C-4 (m) で訂正済みの対称性錯誤に基づく)。
- hang の物証: journal は hang cycle の `PM: suspend entry` すら flush されず (既知)、PRE ファイル (durable) と s3-soak.log の WAKE 欠落が ground truth。pstore 空 (stock は watchdog なし、想定通り)。
- **新観測 (bus-watch)**: clean だった S3 radio-off cycle の resume 後 **AER 残渣ゼロ** (DevSta 全て CorrErr-)。s2idle radio-off では 6/11 で CorrErr+ が出ていたのと対照的で、S3 の完全再給電では config 残渣が残らない (または壊れ方が異なる) ことを示唆。

## Phase 2b: wl unload アーム (結果: 21/21 全 clean、bedrock の S3 拡張成立)

marker `SESSION-S3R3-START` (epoch 1783887906) 以降、同一ストレス条件 + `sudo modprobe -r wl` で lid cycle。

- **PRE 台帳 21 件 (1783888020〜1783889027) 全て paired・BT_PAN_VALID・wl_loaded=0** (PRE の lsmod セクションで機械確認)。unpaired 0。真の S3 完走 21 回、gpe70 +21 (全て lid wake)、drm_err 0。
- **統計**: wl loaded 2/4 vs wl unloaded 0/21 → Fisher 片側 **p = C(4,2)/C(25,2) = 6/300 = 0.02** で有意。
- **結論: bedrock「hang の必要条件 = wl loaded ∧ radio-off」は S3 (deep) にも成立**。s2idle での wl-unloaded pooled 0/60 (130206/103415) と整合。
- 採用候補構成 = **S3 + udev 保護 (残置) + suspend 時 wl unload フック**。BT-PAN/VPN は wl 非依存なので機能犠牲なし。代償は resume 後の WiFi 再接続数秒 (radio-on 運用時)。

## Phase 3: バッテリ spurious wake (結果: 不変 = AC 連動 LID0 ポリシーが妥当)

バッテリ駆動 (AC=0) + LID0 enabled で `rtcwake -m mem -s 60` ×3:

| cycle | elapsed | gpe70 |
|---|---|---|
| 1 | 6s | 21 → 22 |
| 2 | 6s | 22 → 23 |
| 3 | 6s | 23 → 24 |

対照 (LID0 凍結): elapsed **63s** (完走)、gpe70 不変。→ 6/18 の観測と寸分違わず、**バッテリ S3 の 6 秒 spurious wake (gpe70 = LID0 _PRW) は firmware 挙動として不変**。

恒久ポリシー: **AC 時のみ LID0 有効** の動的切替 (system-sleep フックで AC 状態を見て /proc/acpi/wakeup をガード付きトグル)。

- AC で lid close → lid open で復帰 (今回実証した挙動)
- バッテリで lid close → sleep は保たれ、復帰は従来通り電源ボタン (suspend-then-hibernate も現行のまま機能)

## Phase 4: 待機電力 8 時間計測 (結果: 0.0917W = 保護の電力ペナルティなし)

05:54:57 JST に `s3-soak-measure.sh 28800 1800 s3r` を起動 (systemd-run unit `s3r-night`、バッテリ 89%、LID0 凍結、deep 選択)。13:57:50 JST に自動完了。

```
RESULT dq=88000 uAh dEnergy=0.7362 Wh dt=8.024 h V_mean=8.366 V W=0.0917 W cap_drop=2% segments=22 spurious=6
```

| 構成 | 待機電力 |
|---|---|
| **S3 + udev 保護 (今回)** | **0.0917 W** (2%/8h) |
| S3 無保護 (6/19) | 0.0980 W (2%/8h) |
| s2idle + udev 保護 (現行常用) | ~1.6 W (4%/h) |
| s2idle + pcie_port_pm=off (撤去済) | 2.8〜3.4 W |

- **保護あり/なしで S3 待機電力は同一の桁** (0.09W 級) → udev 保護 (ソフト D0) は S3 では電力面でも no-op = 「S3 はバス電源を落とすため保護が無力」という Phase 2 の機序解釈のダメ押し。
- **現行 s2idle+保護の約 1/17**。ゲージ非依存の傍証: 8 時間で容量低下 2pt (89→87%)。1.6W なら ~26pt 減るはず。
- 健全性: 22 セグメント全て rc=0、suspend fail=0、boot_id 不変、gpe70 は 8 時間凍結のまま (=LID0 凍結が効いた)。spurious=6 は計測初期のユーザの電源ボタン押下由来 (re-suspend ループが即再投入、積分への影響は無視できる)。
- 計測終了後、LID0 は `*enabled` に復帰済み (14:0x JST、ガード付きトグルで確認)。

## 実機に残した状態 (要注意)

- **mem_sleep = deep (runtime)** — この boot 中は deep のまま。再起動すれば s2idle に戻る。**恒久化 (wl unload フック) 前に BT+VPN+radio-off で lid close すると hang し得るため、常用に戻すなら再起動して s2idle にするのが安全**。
- LID0 = `*enabled` (Phase 4 終了後に復帰済み)。
- watcher (cycle-watch-s3r / vpn-watch-s3r / bus-watch-c9) は停止済み。marker 3 個とログは /var/log/h4-probe/ に残置 (歴史データ)。
- GRUB・udev rule・フック類: 一切変更なし。

## 次セッションへの引き継ぎ (Phase 5 = 恒久化)

1. ~~Phase 4 の RESULT 回収 + LID0 復帰~~ (完了、上記)
2. 採否最終判断 (ユーザ)。採用なら:
   - **wl unload フック** (新規 system-sleep フック): pre で `modprobe -r wl`、post で `modprobe wl` + NM 再スキャン。radio-on 時も含め常時 unload が簡潔 (bedrock は radio-off 時のみ必要条件だが、常時 unload なら条件分岐不要で安全側)。resume 後の WiFi 再接続遅延を実測して許容判断。
   - **AC 連動 LID0 フック** (新規): pre で `ac=0 かつ *enabled → toggle`、post で `ac=1 かつ *disabled → toggle`。/proc/acpi/wakeup はトグルなのでガード必須。
   - **deep 化 oneshot**: 旧 s3-deep-apply.sh から LID0 凍結節を除いた版を新設・enable。GRUB `mem_sleep_default=deep` 化は 1〜2 週間の常用 soak 通過後 (6/20 と同じ二段構え)。
   - 検証: フック経由の実 lid cycle (AC/battery 両方) + BT-PAN+VPN+radio-off 追加 cycle で 0/30 級に積み増し。
3. 不採用なら: `echo s2idle > /sys/power/mem_sleep` (または再起動) だけで現状復帰。

## 運用知見・罠 (新規)

1. **udev 保護 (d3cold_allowed=0) の実効は s2idle 限定**。S3 ではソフトウェア D0 でもプラットフォームがバス電源を落とすため無力。「保護あり = 安全」を S3 に外挿してはならない (今回 2/4 で実証)。
2. **wl unload の検証は PRE の lsmod セクションで機械確認できる** (`grep -cE "^wl " *.pre`)。手順失念 (hang #2) も台帳から客観判定できた。
3. **bus-watch の残渣 grep は DevSta/UESta/CESta に限定すること**。`CorrErr+` の裸 grep は DevCtl (報告有効化ビット) と CEMsk に誤マッチする (今回一度誤検知しかけた)。
4. rtcwake -m mem は systemd 経路を通らずフック未発火 (既知) — h4-probe 台帳に rtcwake cycle は載らない。今日の台帳 (24 PRE) が lid 経由 cycle のみなのはこのため。
5. watcher (systemd-run --collect) は再起動で消える。hang → 強制断のたびに再起動が必要。

## 再現方法 (要点)

```bash
# deep 化 (runtime、可逆)
ssh miminashi@macbookair2015.lan 'echo deep | sudo tee /sys/power/mem_sleep'
# D-state 確認用 dynamic debug
ssh ... 'echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control'
# S3 1 cycle + D-state 確認
ssh ... 'sudo rtcwake -m mem -s 60'
ssh ... 'sudo journalctl -k -b 0 | grep "Suspend power state" | grep -v D3'
# ストレス条件 (ユーザ操作): iPad BT-PAN → nmcli radio wifi off → nmcli con up GSNet
#   wl unload アームはさらに: sudo modprobe -r wl (lsmod | grep ^wl が空を確認)
# lid 閉 10-15s → lid 開 (S3 なので lid open で復帰する)、20-30s 間隔で反復
# 検証: /var/log/h4-probe/*.pre の台帳 (ペア判定は PRE epoch +180s 以内の .post)
# バッテリ spurious: AC を抜いて sudo rtcwake -m mem -s 60 → elapsed 6s なら spurious
```

## 添付ファイル

- [実装プラン](attachment/2026-07-13_055510_s3_deep_retrial_lid_wake_and_wl_unload/plan.md)

## 参照レポート

- S3 断念の経緯: [2026-06-18_142303_why_not_s3_deep_sleep.md](2026-06-18_142303_why_not_s3_deep_sleep.md)
- S3 復活評価 (lid wake / gpe70 spurious): [2026-06-18_233837_s3_revival_evaluation.md](2026-06-18_233837_s3_revival_evaluation.md)
- S3 待機電力 (無保護 0.098W): [2026-06-19_094329_s3_battery_standby_power.md](2026-06-19_094329_s3_battery_standby_power.md)
- S3 hang 4 件と no-go: [2026-06-27_072510_bluetooth_vpn_lid_close_hang.md](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)
- bedrock (wl loaded ∧ radio-off): [2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
- 真因確定 + udev rule: [2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md)
- wl war 機序 + stock 復帰: [2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md)
- C-9 無保護トレース (bus-watch 新設): [2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md)
- 調査総括: [2026-07-13_005126_suspend_hang_investigation_summary.md](2026-07-13_005126_suspend_hang_investigation_summary.md)
