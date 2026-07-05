# PCIe ポートの電源管理を切ったらハングが消えた — 名指し介入第 1 弾 (Phase C-6)

**サマリ**: C-5 で実名の付いた停止点 (TB2 ブリッジ / i915) への名指し介入第 1 弾として `pcie_port_pm=off` を適用し、高再現 arm (dpmwd4 + pm_trace=1、ベースライン hang 率 8/19 ≈ 42%) で 30 有効 cycle を回した結果、**hang 0/30**。Fisher exact 片側 **p ≈ 1.7×10⁻⁴** で「介入により hang が消滅した」が統計的に成立。署名 A (TB ブリッジ noirq entry) だけでなく**署名 B (i915 main entry) も同時に消えた**ことから、PCIe ポートの D3 遷移が両署名の上流にあることが強く示唆される。

- **実施日時**: 2026年7月6日 01:10 〜 02:05 JST
- **位置づけ**: [2026-07-06_002651](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md) (Phase C-5) の引継ぎ第 1 候補「名指し介入」を実施。観測フェーズから因果検証フェーズへの移行第 1 弾。

## 概要

前回 (C-5) までで、BT テザリング + VPN 使用中の lid close ハングの停止点は、resume 処理中の 2 箇所 — Thunderbolt 2 ブリッジの noirq 段入口と、内蔵 GPU (i915) の main 段入口 — に実名付きで特定されていた。名前が付いたことで、今回からは「観測を細かくする」のではなく「名指しで介入して因果を確かめる」段階に入った。

第 1 弾の介入には `pcie_port_pm=off` (PCIe ポートを省電力状態 D3 に落とさなくするカーネル起動オプション) を選んだ。停止点の片方である Thunderbolt ブリッジを直接狙う介入であり、カーネルの再ビルドが不要で、起動オプション 1 個の追加だけで済み、完全に可逆だからである。もう片方の候補だった i915 の省電力制限は、5 月の S3 時代に試して効果がなかった実績があるため後回しにした。

適用の実効性は起動前後の比較で確認した。介入前はハング停止点の実名そのものである 2 つのブリッジポートが省電力状態 (D3hot) に落ちていたが、介入後は全ポートが動作状態 (D0) に留まり続けた。その上で、これまでと同じ高再現条件 (計測カーネル dpmwd4 + pm_trace 有効 + BT テザリング + VPN + WiFi オフ) で lid 開閉を 30 回繰り返した。この条件での直近 2 セッションのハング率は約 42% (19 回中 8 回) であり、30 回やれば統計的にはほぼ確実に複数回ハングするはずだった。

結果はハング 0 回。30 回すべてが有効条件 (suspend 突入時点で BT テザリングのアドレスと VPN のカーネル内 SA が生存) を満たしていたことも、cycle ごとの自動記録で機械的に確認した。ベースラインとの比較は Fisher 検定で p ≈ 0.00017 となり、偶然の変動では説明できない。介入が効いたと結論してよい水準である。

注目すべきは、Thunderbolt 狙いの介入で i915 側の署名まで一緒に消えたことである。`pcie_port_pm=off` は Thunderbolt ブリッジだけでなく全 PCIe ポートに効く広域介入なので、「どのポートが真犯人か」まではまだ絞れていないが、少なくとも「PCIe ポートのどれかが D3 に落ちること」がハング機序の上流にあり、i915 の署名はその下流の被害者だった可能性が高い。C-4 以来の有力仮説「タイマや NMI の土台ごと止まる静かな停止」とも整合する — PCIe ポートの電源遷移が絡む深い省電力状態からの復帰不全、という絵である。

今後は 2 方向ある。1 つは絞り込み: 全ポート介入を狭めて (例: TB ポートだけ D3cold 禁止)、真犯人のポートを特定する。もう 1 つは実用: `pcie_port_pm=off` は常用してもデメリットが軽微 (待機電力の微増程度) なので、従来の回避策「WiFi radio 常時 on」に加わる、より条件の緩い恒久対策候補になった。パラメータは実機に残置してある。

## 添付ファイル

- [実装プラン](attachment/2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30/plan.md)
- [セッション証跡 (cmdline / cycle-watch / vpn-watch / per-cycle gate / TB スナップショット / 統計)](attachment/2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30/c6-evidence-raw.txt)

## 前提・目的

- **背景**: C-5 (002651) で hang 停止点が署名 A = pcieport 06:03.0/06:06.0 (Falcon Ridge TB2 downstream) noirq resume entry、署名 B = i915 (0000:00:02.0) main resume entry の 2 箇所に二極化。全監視沈黙から「タイマ/NMI 基盤ごと止まる静かな停止」(C-state 復帰不全系) が有力仮説。
- **目的**: 名指し介入第 1 弾 `pcie_port_pm=off` で署名 A の因果を検証する。判定軸 = 署名 A が消えるか / hang 率が変わるか / 署名が別デバイスへシフトするか。
- **介入選定の根拠**: `i915.enable_dc=0` は S3 時代 (5/10-5/22、[2026-05-22_022030](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md)) に適用して hang 頻度不変の実績があり事前確度が低い。`pcie_port_pm=off` は未実施 + リビルド不要 + 可逆。
- **arm tag**: `dpmwd4 + pm_trace=1 + pcie_port_pm=off`。ベースライン = 同摂動 arm (C-4 4/9 + C-5 4/10 = 8/19 ≈ 42%)。非摂動 pool (7.1%) とは合算しない。
- **役割分担**: ssh 操作全般 = Claude、テザリング・lid 開閉・WiFi 復旧 = ユーザ。

## 環境情報

- **実機**: MacBook Air 11" (Early 2015) / Debian 13 / kernel **6.12.94-dpmwd4** (C-5 と同一バイナリ、リビルドなし)
- cmdline: `... quiet no_console_suspend mem_sleep_default=s2idle panic=15 pcie_port_pm=off` (末尾が今回追加分)
- スリープ: `[s2idle]`、`intel_pch_thermal.delay_cnt=300`、hooks 5 本 (50/58/59/60/70、C-5 と同一)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28` (enx98e0d98d205e)、VPN: GSNet (strongSwan IKEv2、SA peer 160.16.210.47)、WiFi: `wl` loaded + radio off
- 電源: AC 接続、バッテリ 91%
- **セッション中の SA は BT-PAN アドレスで確立** (src 172.20.10.13 ⇔ 160.16.210.47): radio off 後にユーザが `nmcli con up GSNet` で再確立 (radio off 前の SA は WiFi アドレス 192.168.33.145 だった)

## 実験手順と検証ゲート (全通過)

| 段階 | 内容 | 結果 |
|---|---|---|
| P0 preflight | dpmwd4 稼働 / pm_trace=0 / pstore 空 / delay_cnt=300 / wl / hooks / saved default / AC | 全項目良好 |
| P0 介入前スナップショット | TB downstream 4 ポート (06:03.0/06:04.0/06:05.0/06:06.0) + 00:1c.0 | **runtime suspended / D3hot** (C-5 署名 A の 2 ポートを含む) |
| P1 介入適用 | `/etc/default/grub.bak-c6` バックアップ → `GRUB_CMDLINE_LINUX_DEFAULT` に `pcie_port_pm=off` 追加 → `update-grub && sync` → 再起動 (01:11:40 boot) | `/proc/cmdline` に反映確認 |
| P1 実効確認 | 介入後の同ポート群 | **全ポート active / D0** (boot 直後・4 分後とも。介入は実効) |
| P2 arm | sysctl hung_task/hardlockup/softlockup panic=1、pm_trace=1、SESSION-C6-START.marker (epoch 1783267993)、watchers (cycle-watch-c6 / vpn-watch-c6) | 稼働確認 |
| P2 smoke | WiFi のまま lid cycle ×2 | 2/2 完走。RTC 最終値 `Magic 15:1` + device:4e = C-5 成功形と同一 |
| P2 省略 | 合成 hang (t3) は省略 | decode 経路は C-5 で実弾検証済み + カーネル不変のため |

## 結果: hang 0/30 (全 cycle 有効)

- **suspend entry/exit 32 ペア** (cycle-watch-c6): smoke 2 + 本番 30。**unpaired PRE ゼロ = hang ゼロ** (本番 cycle は suspend entry 01:30:39 〜 02:01:53、最終 exit 02:02:23 JST)
- **BT_PAN_VALID 30/30**: 各 cycle の 70-h4-probe PRE スナップショットで (i) デフォルト経路 src 172.20.10.13、(ii) ESP SA が**双方向とも BT-PAN アドレスで厳密一致** (`src 172.20.10.13 dst 160.16.210.47` / `src 160.16.210.47 dst 172.20.10.13` の両行、30/30 全件照合済み)
- **pstore 空** (panic なし = 監視の偽陽性もなし)、watchdog 類は全 arm のまま沈黙する機会なし
- **統計**: 0/30 vs ベースライン 8/19 → **Fisher exact 片側 p = 1.68×10⁻⁴**。「pm_trace 摂動下 42% が偶然 0/30 になる」確率は (1-8/19)³⁰ ≈ 7.6×10⁻⁸
- 解釈上の注意: vpn-watch に xfrm=0 のサンプル 7 点があるが、全て resume 直後の NM teardown→再確立中 (cycle 間) のものであり、suspend 突入時点の SA は PRE ファイル側で全件確認済み
- **停止規則の逸脱 (clean 方向)**: プランの終了条件 (b) は「clean 12 cycle で終了」だったが、ユーザ判断で 30 cycle まで延長した。介入が効いていない方向 (hang 探し) の延長ではなく clean の追加確認方向の延長であり、結論を強める側にのみ働く (hang が 1 回でも出ればその時点で記録される設計のため、延長による見逃しバイアスはない)

## 実験タイムライン (JST)

| 日時 | 内容 |
|---|---|
| 7/6 01:10 | Preflight 検収 (dpmwd4 / pm_trace=0 / pstore 空 / AC 91%) + TB ポート介入前スナップショット (06:03.0-06:06.0 = D3hot) |
| 7/6 01:11 | grub.bak-c6 バックアップ → `pcie_port_pm=off` 追加 → update-grub + sync → 再起動 (01:11:40 boot、所要 ~20 秒) |
| 7/6 01:12-01:13 | 検収ゲート (cmdline 反映 / TB 全ポート D0 / pstore 空) → arm (sysctl ×3、pm_trace=1、SESSION-C6-START.marker epoch 1783267993 = 01:13:13、watchers 起動) |
| 7/6 01:16-01:17 | smoke ×2 (WiFi、ユーザ lid cycle) → 2/2 完走、RTC decode `Magic 15:1` + device:4e (成功形) |
| 7/6 01:19 頃 | ユーザが BT-PAN + GSNet on (この時点の SA は WiFi アドレス 192.168.33.145 で確立) → SA ×2 確認 → radio-off-detached 発行 (5 秒後 WiFi off、ssh 切断) |
| 7/6 01:20-01:30 | radio off により WiFi 上の VPN が失効 (vpn-watch: xfrm=0)。**BT-PAN アドレス自体も 01:21:50-01:25:50 は一時消失** (NM 再構成) → 01:26:10 に 172.20.10.13 + SA ×2 で復帰 (ユーザが `nmcli con up GSNet` 再確立、運用知見 1) → 01:27:30-01:29:50 に再フラップ → **01:30:10 に SA 安定、以後 cycle 開始** |
| 7/6 01:30:39-02:02:23 | **有効 cycle 30 本** (suspend entry 01:30:39 〜 02:01:53、最終 exit 02:02:23)。**hang 0 回**。ユーザ判断で計画の終了条件 12 を超えて 30 まで実施 |
| 7/6 02:02 頃 | ユーザ WiFi 復旧・報告 → 証跡機械検証 (32 ペア = smoke 2 + 本番 30、unpaired PRE ゼロ、BT_PAN_VALID 30/30、pstore 空) |
| 7/6 02:05 | テアダウン (pm_trace=0 / sysctl 0 / watchers 停止 / RTC 実時刻復旧 / NM 平常確認) → 証跡回収・本レポート |

## 運用知見 (C-6 で新たに確定・訂正した事項)

1. **radio off は WiFi 上で確立した VPN SA を道連れにする — arm 手順の順序を訂正**。C-5 手順の「GSNet up → SA ×2 確認 → radio off」では、radio off の時点で WiFi アドレス (192.168.33.x) で確立していた SA が無効になる。正しい順序は「BT-PAN 接続 → radio off → **BT-PAN 上で `nmcli con up GSNet` を手動再確立** (SA が 172.20.10.13 で張り直される) → cycle 開始」。C-5 知見 4 (GSNet autoconnect 不発 = 手動必須) の補強 + 順序の訂正。本セッションではユーザが cycle 開始前に再確立しており、全 30 cycle の PRE で BT-PAN アドレスの SA を確認済み (有効性に影響なし)。**C-5 との整合**: C-5 の本番 cycle 群でも vpn-watch は xfrm=2 を維持しており (C-5 証跡)、C-5 でも同等の手動再確立が実際には行われていた (C-5 知見 4 の「4 arm すべてで手動 con up が必要だった」がそれ) — 本知見は C-5 の有効性判定を覆すものではなく、手順書の記載順序が実態と食い違っていたことの訂正である。
2. **`ip xfrm state` は非 root だと `RTNETLINK answers: Operation not permitted` で 0 件に見える**。SA 確認は必ず `sudo ip xfrm state | grep -c ^src` で行うこと (本セッションで一度 SA=0 と誤認しかけた)。
3. **watcher の起動コマンドが C-5 までのレポートに未記載だった**。本セッションでは実機残置の C-5 ログの形式から逆算して再構成する手間が発生した。正確なコマンドは本レポートの「再現方法」に記録した (以後はコピーで再現可能)。
4. **vpn-watch の xfrm=0 サンプルは cycle 間の正常な過渡状態**。resume 直後は NM が BT-PAN/VPN を teardown→再確立するため、20 秒毎サンプリングに xfrm=0 が写る。cycle の有効性判定は vpn-watch ではなく **70-h4-probe の PRE ファイル (suspend 突入直前のスナップショット)** で行うのが正。

## 解釈

1. **介入マトリクスの「hang 消滅」行に該当**: `pcie_port_pm=off` は署名 A (TB ブリッジ) と**署名 B (i915) の両方**を消した。PCIe ポートの D3 遷移が両署名の共通上流にあることを強く示唆する。
2. **i915 署名は「被害者」だった可能性が高い**: 署名 B は i915 自身の main resume entry で止まっていたが、i915 に触れない介入で消えた。async resume の「最終書込み = 最後に活動していた thread ≠ 単独犯」という留保 (C-5) が現実のものとなった形。
3. **「静かな停止」仮説との整合**: PCIe ポート (特に配下が空のホットプラグ域 TB downstream) の D3 復帰が絡む深い省電力状態からの復帰不全、という機序なら、タイマ/NMI 基盤ごと止まる様相・全監視沈黙・部分的なハード応答 (バックライト) と矛盾しない。
4. **広域介入の留保**: `pcie_port_pm=off` は全 PCIe ポート (root port 00:1c.x 含む) に効く。「TB ポートが真犯人」とはまだ言えず、真犯人ポートの特定には絞り込み介入 (下記) が必要。
5. **n=30 の留保**: ベースライン側が 2 セッション (n=19) である点、セッション間の環境差 (温度・iPad 状態等) は完全には排除できない点は残る。ただし p ≈ 1.7×10⁻⁴ は本プロジェクトの bedrock 基準 (p<0.05) を 2 桁上回る。

## 次セッション引継ぎ (Phase C-7 候補)

1. **絞り込み介入 (推奨)**: `pcie_port_pm=off` を外し、代わりに TB 系ポートのみ `d3cold_allowed=0` (または `/sys/.../power/control=on`) を suspend 前フックで指定 → 署名 A/B が戻るか。戻らなければ「TB ポートの D3cold だけで説明可能」まで絞れる。戻れば root port 側 (00:1c.x) を含む範囲を順に狭める。
2. **統計強化**: 本 arm (pcie_port_pm=off) の cycle 追加で 0/50 級にする (現状でも十分強いが、恒久対策採用の根拠を厚くする)。
3. **恒久対策判断**: `pcie_port_pm=off` 常用の可否 (待機電力への影響を s2idle 一晩計測で確認) → 「WiFi radio 常時 on」より条件の緩い対策として置き換え検討。
4. **機序の残り**: なぜ BT-PAN + VPN + radio off のときだけ PCIe ポート D3 復帰が壊れるのか (トリガー条件と PCIe の接点、wl loaded + radio-off 状態が PCIe/PME に与える影響) は未解明のまま。

## 常用運用の指針 (ワークアラウンドとしての採用可否)

セッション後のユーザ問い合わせ「しばらく常用しても大丈夫か」への回答として、判断根拠と留意点をここに記録する。

**結論: 常用可。ただし「恒久対策として確定」ではなく「実運用 soak を兼ねた常用」の位置づけ。**

**常用を支持する根拠:**

1. 0/30 (Fisher p ≈ 1.7×10⁻⁴) は pm_trace=1 の高再現条件下 (ベースライン 42%) での結果であり、実使用 (pm_trace=0、非摂動の歴史的 hang 率 ~6-7%/cycle) ではさらに安全側に働くと期待できる。
2. 完全に可逆 (`/etc/default/grub` から 1 パラメータ削除 + update-grub && sync) で、機能面のデメリットなし (ホットプラグ等は正常)。
3. これまで禁じ手だった **BT テザリング + VPN + WiFi off の組み合わせも解禁してよい**。実使用でこのパターンを使うこと自体が非摂動条件での検証データ収集になり、C-7 候補 2 (統計強化) を日常使用が兼ねる。

**留意点 3 つ:**

1. **カーネルが dpmwd4 (自前ビルド) のまま**である点が、実は pcie_port_pm=off より大きい留意事項。(a) DPM watchdog が常時武装しており、正規に 60 秒超の suspend callback があると panic → 自動再起動する (既知の intel_pch_thermal 衝突は delay_cnt=300 で緩和済みだが、別の偽陽性の可能性はゼロではない — [2026-07-04_012628](2026-07-04_012628_dpmwd2_first_field_panic_pch_thermal_watchdog_false_positive.md) 参照)。(b) Debian のカーネルセキュリティ更新が当たらない。数週間の soak なら許容範囲だが、長期化するなら「stock カーネル + pcie_port_pm=off」への切替を検討する (パラメータはカーネル非依存だが、その構成での hang 検証は未実施)。
2. **待機電力の微増の可能性**: PCIe ポートが D3 に落ちなくなるため、s2idle 待機電力 (現状 ~0.7W) が上がりうる。定量計測は C-7 の課題 (恒久対策判断の材料)。
3. **hang が再発したらそれ自体が超一級のデータ** (0/30 の反例)。いつも通り 5 分以上放置 → 電源長押し → 復旧後に報告。pm_trace=0 のため RTC decode は不可だが、発生条件の記録だけでも価値がある。

**ユーザに報告を依頼した観察事項 (soak 中のウォッチリスト):** (i) 心当たりのない再起動 (= watchdog panic の疑い、pstore で判別可能)、(ii) hang の再発、(iii) バッテリ持ち/スリープ中の減りの体感悪化。数週間問題なければ、C-7 (真犯人ポート絞り込み) と合わせて恒久対策として確定させる。

## 残置物 (実機の現状、7/6 02:05 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd4 稼働 (saved default、C-5 から不変)。dpmwd3/2/1/stock 残置 |
| **cmdline** | **`pcie_port_pm=off` を追加・残置** (次セッション/常用評価のため。撤去 = `/etc/default/grub` から削除 + `update-grub && sync`)。バックアップ `/etc/default/grub.bak-c6` (今回)、`.bak-dpmwd` (182811 原本) |
| pm_trace / sysctl panic 系 | 0 / 全 0 (平常) |
| NM | radio on、OpenWrt 接続、autoconnect 平常 (GSNet=no / BT-PAN=no / OpenWrt=yes) |
| RTC / 時刻 | NTP 同期 + `hwclock --systohc` 済み (02:05 JST) |
| pstore | 両所在空。pstore-guard enabled |
| /var/log/h4-probe | SESSION-C6-START.marker (1783267993)、cycle-watch-c6.log、vpn-watch-c6.log、PRE/POST 64 本追加。削除しないこと |

## 再現方法

```bash
# 1) 介入適用 (実機)
sudo cp /etc/default/grub /etc/default/grub.bak-c6
sudo sed -i 's/panic=15"/panic=15 pcie_port_pm=off"/' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot
# 検収: cat /proc/cmdline に pcie_port_pm=off、
#        /sys/bus/pci/devices/0000:06:0{3,6}.0/power/runtime_status が active のまま

# 2) arm 〜 有効 cycle (C-5 の「hang-arm セッション」手順と同一。要点のみ)
sudo sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1
echo 1 | sudo tee /sys/power/pm_trace
echo "C6 session start $(date +%s)" | sudo tee /var/log/h4-probe/SESSION-C6-START.marker

# watchers (C-5 まで未記録だった正確なコマンド。ログ名の c6 は都度読み替え)
sudo systemd-run --unit=cycle-watch-c6 --collect bash -c \
  'journalctl -k -f -o short-unix | grep --line-buffered -E "PM: suspend (entry|exit)" >> /var/log/h4-probe/cycle-watch-c6.log'
sudo systemd-run --unit=vpn-watch-c6 --collect bash -c \
  'while true; do echo "$(date +%s) $(ip -o -4 addr show 2>/dev/null | grep -oE "172\.20\.10\.[0-9]+/[0-9]+" | head -1) xfrm=$(ip xfrm state | grep -c ^src)" >> /var/log/h4-probe/vpn-watch-c6.log; sleep 20; done'
# (vpn-watch は root 実行が必須 — 非 root の ip xfrm state は常に 0 になる。運用知見 2)
# BT-PAN 接続 → radio off 後に nmcli con up GSNet (SA が BT-PAN アドレスで確立される)
# sudo ip xfrm state | grep -c ^src → 2 を確認 (非 root では Operation not permitted になる罠)
# ユーザ: lid 閉 → 10-15 秒 → 開 → 電源短押し wake、反復

# 3) 判定 (hang なしの場合)
# 有効性: 本セッション (SESSION marker の epoch 以降) の各 PRE に BT-PAN アドレスの ESP SA が双方向あること
#   注意: epoch でフィルタしないと過去セッションの PRE (同形式) まで数えてしまう
EPOCH=$(awk '{print $NF}' /var/log/h4-probe/SESSION-C6-START.marker)
for f in /var/log/h4-probe/17*.pre; do e=$(basename $f .pre); [ "$e" -ge "$EPOCH" ] || continue; \
  grep -q "^src 172\.20\.10\.13 dst 160\.16\.210\.47$" "$f" && echo "$e OK" || echo "$e INVALID"; done
# hang ゼロ: unpaired PRE が無いこと (pre と post が交互に揃う)
```

## 関連レポート

- [2026-07-06_002651 Phase C-5 停止点の実名特定 (引継ぎ元、arm 手順・decode 手順の一次ソース)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-07-05_185344 Phase C-4 停止域の特定 (ベースライン 4/9 の出所)](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md)
- [2026-07-02_182811 GRUB 変更 + sync の教訓 (grubenv sync 漏れ)](2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e.md)
- [2026-05-22_022030 i915.enable_dc=0 の S3 時代不発 (介入順序の根拠)](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md)
- [2026-07-02_103415 hang-arm 条件の統計的根拠 (b'' bedrock)](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
