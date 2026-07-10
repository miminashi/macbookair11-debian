# 真犯人は WiFi の親ポートと確定、1 ポートだけの保護を恒久対策に採用 — 一本釣り介入 (Phase C-7 第 3 段)

**サマリ**: Rung 2 で 3 本に絞られていた容疑者から、`03:00.0` (wl = BCM4360) のみに `d3cold_allowed=0` を書いて親ルートポート **00:1c.2 単独を sleep 中 D0 固定**する一本釣り介入 (Rung 3) を高再現 arm で検証した結果、**hang 0/37 (全 BT_PAN_VALID、unpaired PRE ゼロ、pstore 空)**。同摂動無保護ベースライン 9/24 ≈ 38% に対し Fisher 片側 **p ≈ 7.5×10⁻⁵** で「介入により hang 消滅」が成立し、**真犯人 ≈ 00:1c.2 (wl の親ポート) が確定**した。待機電力は一晩 6.43 h の実測で **≈ 1.6 W (≈4%/h)** — 従来ベースライン 0.70 W には届かないが `pcie_port_pm=off` の 2.8〜3.4 W のほぼ半分であり、ユーザ判断で **udev rule による恒久対策として採用** (再起動 e2e 検証済み、`pcie_port_pm=off` は grub から撤去恒久)。副観測 O3 では radio on/off の PME/wake 設定が完全同一 (lspci -vv バイト一致) であることも確認し、radio off の寄与は runtime に見える設定差ではないという消去も得た。

- **実施日時**: 2026年7月9日 23:00 〜 7月10日 12:25 JST
- **位置づけ**: [C-7 Rung 2](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md) の引継ぎ候補 1 (一本釣り、最有力 = 00:1c.2)、候補 2 (恒久対策の実装 + 待機電力検収)、候補 3 (PME/wake 設定差観測) を同一セッションで実施。

## 概要

前回 (Rung 2) までで、BT テザリング + VPN + WiFi オフ時の lid close ハングの必要要素は、非 Thunderbolt ルートポート 3 本 — カメラ親 00:1c.1、WiFi 親 00:1c.2、SSD 親 00:1c.5 — のいずれかの sleep 中 D3hot 遷移にあると確定していた。今回はこの 3 本から一本を釣り上げる最終段である。ハングの必要条件「wl ロード済みかつ radio オフ」との物理接点を持つのは WiFi の親ポート 00:1c.2 だけなので、まずこれを単独で保護した。手段は前回までと同じ sysfs ノブの応用で、wl デバイス (03:00.0) に `d3cold_allowed=0` を書くと親の 00:1c.2 だけが sleep 中も D0 に固定される。スモークテストの実測で「D0 のまま sleep するポートは 00:1c.2 ただ 1 本、00:1c.1 / 00:1c.5 / Thunderbolt 系はすべて従来どおり D3hot」という一本釣りの設計状態を確認した上で本番に入った。

結果は明確だった。高再現条件 (計測カーネル + pm_trace + BT テザリング + VPN + WiFi オフ) での lid 開閉 37 回で、ハングは一度も出なかった。無保護なら 4 割近くハングする条件であり、統計的にも介入の効果は疑いない水準 (p ≈ 7.5×10⁻⁵) にある。00:1c.1 と 00:1c.5 は無保護のまま 37 回すべてを生き延びたので、この 2 本は容疑から外れ、**ハングには 00:1c.2 が sleep 中に D3hot へ落ちることが必要**、と一本に絞り込めた。ハングの物理的な絵はこれで「wl を積んだポートの省電力遷移が、radio オフ + BT テザリング + VPN の条件下でのみ復帰に失敗する」というところまで具体化したことになる。

続けて、恒久対策の検収として待機電力を実測した。バッテリ駆動で一晩 6 時間 26 分 suspend させたところ、平均消費は約 1.6 W (毎時 4% 減) だった。期待していた従来ベースライン 0.7 W 級には収まらなかった — ルートポート 1 本の D0 常駐でも、チップセットの深い省電力状態をある程度は阻害するようだ — が、これまで常用してきた広域介入 `pcie_port_pm=off` の約 3 W に比べれば半分である。この結果をユーザに提示し、「hang 抑止は同等 (0/37 で実証)、待機電力は半減」のトレードオフで恒久対策として採用する判断となった。

恒久化は udev rule で実装した。boot 時に wl デバイスが registration された時点で `d3cold_allowed=0` が自動で書かれる仕組みで、ライブの再適用テストと実際の再起動の両方で自動適用を検証済みである。あわせて `pcie_port_pm=off` は grub から恒久に撤去した。カーネル起動オプションに依存しない対策になったので、将来 stock カーネルへ戻す際もこの rule はそのまま機能する。モバイル持ち出し時は毎時 4% の減りがまだ残るため、従来どおりシャットダウンかハイバネートを推奨する。

軽量な副観測も一つ消去を積んだ。radio on と off とで wl とその親ポートの PME/wake 関連設定 (lspci -vv の全出力、sysfs の wakeup、/proc/acpi/wakeup) を比較したところ、リンク状態の 1 行を除いて完全に同一だった。前回の「suspend 時の最終 D-state も同一」と合わせると、radio off がハングを引き起こす機序は、ユーザ空間から runtime に観測できる電源・wake 設定の層にはなく、suspend/resume 処理中の動的な振る舞い (wl ドライバの suspend callback の挙動、リンクトレーニング、ASPM 等) に絞られてきた。ここは未解明のまま次セッションの課題として残る。

## 添付ファイル

- [実験プラン](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/plan.md)
- [セッション証跡 (marker / cycle-watch / PRE 台帳 / smoke S1 D-state / rtc-catch / vpn-watch / pstore / boot)](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/c7r3-evidence-raw.txt)
- [待機電力計測 + 恒久化検証の証跡 (s3-soak.log / udev rule / 再起動後検収 / grub 現状)](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/c7r3-power-and-permanence.txt)
- [観測 O3: radio on の PME/wake 設定](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/o3-radio-on-pme.txt)
- [観測 O3: radio off の PME/wake 設定](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/o3-radio-off-pme.txt)
- [O3 採取スクリプト (o3-capture.sh)](attachment/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix/o3-capture.sh)

## 前提・目的

- **背景**: [Rung 2](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md) で真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5} が確定。必要条件 b'' (wl loaded + radio off、[bedrock](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)) との物理接点から 00:1c.2 (wl 親) が最有力
- **目的**: (a) 03:00.0 単独への `d3cold_allowed=0` (= 00:1c.2 単独 D0 固定) で hang が消えるかにより真犯人を 1 本に絞る、(b) clean なら恒久対策を実装し待機電力を検収する、(c) 副観測 O3 = radio on/off の PME/wake 設定差 (Rung 2 引継ぎ 3)
- **判定設計** (プラン時にユーザ合意済み): clean 0/30 級 → 真犯人 ≈ 00:1c.2 確定 → Rung 3 構成残置で一晩待機電力計測 / hang 再発 → 1 回で判定成立、次の一本 (04:00.0 → 00:1c.5) に同セッション続行
- **役割分担**: ssh 操作全般 = Claude、テザリング・radio off・GSNet 再確立・lid 開閉・WiFi 復旧・AC 抜き差し = ユーザ

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / kernel **6.12.94-dpmwd4** (C-5 から不変、リビルドなし)
- 実験時 cmdline: `... quiet no_console_suspend mem_sleep_default=s2idle panic=15` (`pcie_port_pm=off` を撤去。**今回は実験後も復帰させず撤去恒久**)
- スリープ: s2idle、`intel_pch_thermal.delay_cnt=300`、hooks 5 本 (50/58/59/60/70)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28`、VPN: GSNet (strongSwan IKEv2、SA peer 160.16.210.47)、WiFi: `wl` loaded + radio off
- 電源: 本番 cycle は AC 接続 (BAT 90%)、待機電力計測はバッテリ駆動 (91% 開始)
- PCIe トポロジ (Rung 2 と同一): 00:1c.1 (→ 02:00.0 FaceTime カメラ) / **00:1c.2 (→ 03:00.0 BCM4360 = wl)** / 00:1c.5 (→ 04:00.0 Samsung SSD AHCI) / TB チェーン 00:1c.4 → 05:00.0 → 06:00.0 / 06:03-06

## 実験手順と検証ゲート

| 段階 | 内容 | 結果 |
|---|---|---|
| P0 preflight | dpmwd4 / pm_trace=0 / pstore 空 / delay_cnt=300 / hooks 5 本 / saved default / AC 90% / sysctl panic 3 種 =0 | 全項目良好 |
| P0 soak 記録 | 7/9 20:52 boot (R2 後) 以降 suspend 0 回のまま中断 (soak 区間クリーン) | 記録済み |
| P1 介入切替 | grub バックアップ `.bak-c7r3` → `pcie_port_pm=off` 削除 → update-grub + sync → 再起動 (7/9 23:03 boot) | cmdline 反映確認 |
| P1 デフォルト検収 | 06:03-06 + 00:1c.0 = D3hot/suspended、他 D0 | C-6 介入前スナップショットと完全一致 |
| P1b 観測 O3 | radio on (23:07) / off (23:08、detached で自動復帰) の PME/wake 設定比較 | **完全同一** (下記) |
| P1c Rung 3 適用 | `d3cold_allowed=0` を **03:00.0 のみ**へ (23:10)。TB 側・02/04:00.0 へは書かない | 90 秒後検収: 03:00.0 d3cold=0、他は全デバイス従来どおり |
| P1c smoke S1 | WiFi lid cycle 1 回、dynamic debug で sleep 中実効を実測 (23:13) | **00:1c.2 = D0 のまま sleep** / **00:1c.1・00:1c.5 = D3hot 遷移** (非保護に復帰) / TB チェーン (00:1c.4/05:00.0/06:00.0/07:00.0) = D3hot / 06:03-06・00:1c.0 = 行なし (runtime D3hot のまま) / wl 03:00.0 自身は従来どおり D3hot (endpoint の省電力は維持) = 一本釣りの設計状態 |
| P2 arm | 観測系無効化 → sysctl panic 3 種 =1、pm_trace=1、SESSION-C7R3-START.marker (epoch 1783606496)、cycle-watch-c7r3 / vpn-watch-c7r3 | 稼働確認 |
| P2 smoke S2-S3 | WiFi lid cycle ×2。S2 は resume 検知即読ワンショットで RTC 生値捕獲 | 2/2 完走。RTC 生値 `2027-08-03 00:00:00` → **decode `Magic 15:1` (成功形)** = e2e 検証済み |
| P2 本番 | BT-PAN → radio off → BT-PAN 上で GSNet 再確立 → lid cycle 反復 (7/9 23:20 〜 7/10 04:24、休憩を挟みつつ) | **hang 0、BT_PAN_VALID 37** |
| P3 計測 | teardown (04:28) → AC 切断 → lid close (04:45) → 一晩 suspend → wake (11:11) | 6.43 h 連続 suspend、≈1.6 W |
| P3 恒久化 | udev rule 作成 → ライブ trigger テスト → 再起動 (12:20 boot) | **再起動後も d3cold_allowed=0 自動適用を検収** |

## 結果 1: hang 0/37、真犯人 ≈ 00:1c.2 確定

### cycle 台帳 (機械検証、証跡参照)

- SESSION epoch 1783606496 以降の PRE = 39 本、**全 39 本 paired (unpaired = hang ゼロ)**
- 内訳: **BT_PAN_VALID 37** / INVALID 2 (smoke S2/S3 = 設計どおり)。Rung 2 と異なりセットアップ過渡の INVALID はゼロ (全本番 cycle が有効)
- 有効性は各 PRE の ESP SA 双方向厳密一致 (`src 172.20.10.13 dst 160.16.210.47` / 逆向き) で判定
- ユーザの体感回数「32 回程度」に対し機械計上は 37 本 (体感と台帳のズレは既知、判定は台帳が正)
- pstore 空 (watchdog panic なし)、boot ID 不変 (セッション中の再起動なし)、pm_trace / d3cold_allowed はセッション終端まで維持を確認

### 統計

- **Rung 3 arm (`dpmwd4 + pm_trace=1 + d3cold_allowed=0(03:00.0)`): hang 0/37** — 同摂動無保護ベースライン 9/24 ≈ 38% に対し **Fisher 片側 p ≈ 7.5×10⁻⁵**
- 比較: Rung 1 (00:1c.2 非保護) は 1/5 で hang、Rung 2 (3 本保護) は 0/30、Rung 3 (00:1c.2 のみ保護) は 0/37 — 3 段の梯子が「00:1c.2 が必要要素」で一貫
- arm tag 分離の原則どおり、他 arm (pcie_port_pm=off 0/30、Rung 2 0/30、無保護 9/24) とは合算しない

### 絞り込みの確定

- **hang には 00:1c.2 の sleep 中 D3hot 遷移が必要** (00:1c.2 だけを D0 に固定すれば消える)
- **00:1c.1 / 00:1c.5 は容疑から外れた**: Rung 3 では両方とも無保護 (D3hot 遷移を smoke S1 で実測) のまま 37 cycle 生き延びた。厳密には「00:1c.2 との連言でのみ寄与」の可能性は残るが、00:1c.2 の保護だけで hang が切れることが実証されたので、対策の観点では 00:1c.2 のみで完結する
- 必要条件 b'' (wl loaded + radio off) と真犯人ポート (wl の親) が物理的に結びつき、C-6 以来の「PCIe ポート D3 遷移が上流」解釈が最終形に到達した。i915 署名 (B) の被害者説も維持 (今回も i915 には触れていない)

## 結果 2: 副観測 O3 — radio on/off で PME/wake 設定も完全同一

radio on / off それぞれで `lspci -vv` (03:00.0 / 00:1c.2 全出力)、sysfs `power/wakeup`、`/proc/acpi/wakeup` を採取し diff した:

- **lspci -vv はバイト単位で同一** (156 行中、差分はヘッダと wlp3s0 リンク状態 UP/DOWN の 2 箇所のみ)
- 両条件とも: 03:00.0 = D0, PME-Enable-, wakeup=disabled / 00:1c.2 = D0, PME-Enable-, PMEStatus-, wakeup=disabled
- `/proc/acpi/wakeup`: RP02/RP03/ARPT すべて disabled で不変

O1/O2 (Rung 2、suspend 時最終 D-state 同一) に続き、「radio off が runtime に観測できる電源・wake 設定を変える」可能性も消去。radio off の寄与は suspend/resume 処理中の動的な層 (wl ドライバの suspend/resume callback の内部動作、リンクトレーニング、ASPM 状態等) に絞られた。

## 結果 3: 待機電力 ≈ 1.6 W — pcie_port_pm=off の半分、ベースラインの 2.3 倍

| 項目 | 値 |
|---|---|
| 計測区間 | 7/10 04:45:07 → 11:11:00 JST (asleep_s=23,153 = **6.43 h**、連続 1 cycle、途中 wake なし) |
| 条件 | バッテリ駆動 (AC=0)、WiFi radio on、BT/VPN なし、lid close (type=suspend-then-hibernate、hibernate 遷移なし) |
| charge_now | 4,633,000 → 3,280,000 µAh (**Δ1.353 Ah**、capacity 91% → 65%) |
| **平均待機電力** | **≈ 1.6 W** (0.210 A × ~7.7 V) = **≈ 4.0 %/h** |
| 補助データ | 別の 36 分 suspend (11:26-12:02) でも Δ89,000 µAh → ≈1.1 W と同オーダー |

| 構成 | 待機電力 | hang 抑止 |
|---|---|---|
| 素の s2idle (無保護) | ~0.70 W ([6/19-20 計測](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)) | ✗ (必要条件成立時 ~38-42%) |
| `pcie_port_pm=off` (全ポート D0) | 2.8〜3.4 W ([7/7 定量化](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)) | ✓ (0/30) |
| **Rung 3 (00:1c.2 のみ D0)** | **≈ 1.6 W** | **✓ (0/37)** |

ルートポート 1 本の D0 常駐でも PCH の深い省電力状態をある程度阻害するため 0.7 W 級には収まらないが、広域介入比で半減。この結果をユーザに提示し、**恒久対策として採用**の判断となった (選択肢: 恒久化 / 現 boot のみ残置 / 従来構成復帰、のうち恒久化を選択)。

## 恒久対策の実装 (udev rule)

```
# /etc/udev/rules.d/99-c7r3-wl-d3cold.rules
ACTION=="add", SUBSYSTEM=="pci", KERNEL=="0000:03:00.0", ATTR{d3cold_allowed}="0"
```

- **検証 1 (ライブ)**: `d3cold_allowed` を一旦 1 に戻し `udevadm trigger --action=add` → 0 に再適用されることを確認
- **検証 2 (boot e2e)**: 再起動 (7/10 12:20 boot) → udev により自動で 0 が適用されていることを確認
- カーネル起動オプション非依存 (将来 stock カーネルへ戻しても機能する)。撤去 = rule を rm して再起動
- `pcie_port_pm=off` は grub から**撤去恒久** (off 入り原本のバックアップは `/etc/default/grub.bak-c7r3`)

## 解釈

1. **判定マトリクス「clean」に該当、一本釣り成功**: C-5 で実名が挙がり、C-6 で「PCIe ポート D3 遷移が上流」と分かり、R1→R2→R3 の梯子で 00:1c.2 まで絞り込む、という因果検証の設計が最後まで機能した
2. **機序の絵の現在形**: 「wl (BCM4360) を配下に持つルートポート 00:1c.2 が sleep 中に D3hot へ遷移し、radio off + BT-PAN + VPN の条件下でのみ、その復帰過程で外部観測の全くできない静かな停止に至る」。radio off の寄与箇所は O1/O2/O3 の消去により suspend/resume 中の動的挙動に限定された
3. **i915 署名 B は最後まで被害者だった**: 3 レポート連続で i915 に触れない介入が hang を消した。async resume の「最終書込み = 最後に動いていた thread」解釈で一貫
4. **恒久対策のトレードオフ**: 待機電力 1.6 W は「lid close で放置する使い方」では従来比 2.3 倍の減りだが、hang の実害 (作業状態喪失) と `pcie_port_pm=off` の 3 W に比べれば妥当な妥協点。モバイル持ち出しはハイバネート/シャットダウン推奨を継続
5. **統計の留保**: ベースライン 9/24 は 3 セッション合算 (C-4/C-5/R1) であり、セッション間の環境差は完全には排除できない。ただし p ≈ 7.5×10⁻⁵ は bedrock 基準 (p<0.05) を 3 桁近く上回る

## 次セッション引継ぎ (C-7 残課題)

1. **機序の残り (C-7 (iv)、最後の未解明)**: radio off が 00:1c.2 の D3hot 復帰を壊す動的機序。観測候補 = (a) radio on/off での wl suspend/resume callback の実行時間・順序差 (pm_debug_messages + dynamic debug で callback トレース比較、cycle 2 回で済む)、(b) ASPM 状態・リンクトレーニングログ、(c) wl ドライバ (broadcom-sta) ソースの suspend 経路読解 (方法 B で Debian ソース取得)
2. **stock カーネル戻しの検討**: 恒久対策がカーネル非依存 (udev rule) になったため、dpmwd4 → stock 6.12.94 へ戻す条件が整った (C-6 留意点 1 = セキュリティ更新・watchdog 偽陽性リスクの解消)。stock + udev rule 構成での hang 検証 (非摂動でよい) を経て切替
3. **非摂動 soak の継続**: 現構成 (dpmwd4 + udev rule、pm_trace=0) での常用が非摂動検証データを兼ねる。BT+VPN+radio-off も解禁継続。ウォッチリスト: (i) hang 再発 (0/37 の反例 = 一級データ)、(ii) 原因不明の再起動 (pstore で判別)、(iii) 待機電力の体感 (4%/h 想定との乖離)
4. **統計の注意**: 今後 hang 率を扱う際、本セッションの 0/37 は arm tag `d3cold_allowed=0(03:00.0)` として分離集計する

## 常用運用 (実験後の状態)

- **恒久構成 = dpmwd4 + udev rule (00:1c.2 D0 固定)。`pcie_port_pm=off` は撤去恒久**
- lid close 放置の減りは ~4%/h (従来 pcie_port_pm=off 比で半減)。**モバイル持ち出しはシャットダウンまたはハイバネート推奨を継続** ([7/7 指針](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md))
- hang 再発時はいつも通り: 5 分以上放置 → 電源長押し → 復旧後に報告 (pm_trace=0 のため decode は不可だが発生条件の記録に価値)

## 残置物 (実機の現状、7/10 12:25 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd4 (saved default、不変)。dpmwd3/2/1/stock 残置 |
| cmdline | `pcie_port_pm=off` **撤去恒久** (`quiet no_console_suspend mem_sleep_default=s2idle panic=15`)。バックアップ `.bak-c7r3` (off 入り原本)、`.bak-c7r2`、`.bak-c7` 残存 |
| **udev rule** | **`/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` 新規・恒久** (03:00.0 → d3cold_allowed=0、boot 検証済み) |
| d3cold_allowed | 03:00.0 = 0 (udev 自動適用)、他は全て 1 |
| pm_trace / sysctl panic 系 / pm_debug / dynamic debug | すべて 0 / 無効 (平常) |
| RTC / 時刻 | `hwclock --systohc` 済み、NTP 同期正常 |
| pstore | 空。pstore-guard enabled |
| /var/log/h4-probe | SESSION-C7R3-START.marker (1783606496)、cycle-watch-c7r3.log、vpn-watch-c7r3.log、rtc-catch-c7r3.log、o3-radio-{on,off}-pme.txt、PRE/POST 39 対追加。**削除しないこと** |
| /var/log/s3-soak.log | 待機電力計測の SLEEP/WAKE 行 (7/10 04:45 / 11:11) を含む |

## 再現方法

```bash
# 1) 介入切替 (実機、要再起動) — R1/R2 と同一
sudo cp /etc/default/grub /etc/default/grub.bak-c7r3
sudo sed -i 's/ pcie_port_pm=off//' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot

# 2) 観測 O3 (radio on/off の PME/wake 設定比較、BT/VPN なし、cycle 不要)
#    radio off は ssh を切断するため detached で実行し自動復帰させる:
sudo systemd-run --unit=o3-radio-off --collect bash -c \
  'sleep 5; nmcli radio wifi off; sleep 20; /tmp/o3-capture.sh off; nmcli radio wifi on'
#    (o3-capture.sh = lspci -vv / power/wakeup / /proc/acpi/wakeup を採取、添付参照)

# 3) Rung 3 適用 (sysfs、再起動で揮発 — 恒久化前の実験形)
echo 0 | sudo tee /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed
# 検収 (90 秒後): 03:00.0 の d3cold_allowed=0。
# smoke 1 cycle (dynamic debug) で sleep 中実効を実測:
#   00:1c.2 = "Suspend power state: D0"、00:1c.1/00:1c.5 = D3hot、TB チェーン = D3hot

# 4) arm 〜 cycle 〜 判定は C-6 レポート「再現方法」と同一 (ログ名 c6→c7r3 読み替え)
#    smoke の decode 成功形確認は R2 の「resume 検知即読ワンショット」で (Magic 15:1)

# 5) 待機電力計測 (clean 後)
#    teardown (pm_trace=0, sysctl=0, watchers 停止, hwclock --systohc) → AC 切断 →
#    lid close で数時間放置 → wake 後に /var/log/s3-soak.log の SLEEP/WAKE 行から
#    Δcharge_now [µAh] × 電圧 [~7.7V] / asleep_s で算出

# 6) 恒久化 (udev rule)
sudo tee /etc/udev/rules.d/99-c7r3-wl-d3cold.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="pci", KERNEL=="0000:03:00.0", ATTR{d3cold_allowed}="0"
EOF
sudo udevadm control --reload
# ライブ検証: echo 1 > .../d3cold_allowed → udevadm trigger --action=add ... → 0 に戻る
# boot 検証: 再起動 → d3cold_allowed=0 を確認

# 7) 撤去 (恒久対策をやめる場合)
sudo rm /etc/udev/rules.d/99-c7r3-wl-d3cold.rules && sudo reboot
```

## 運用知見 (C-7 R3 で新たに確定した事項)

1. **h4-probe の POST ファイルは resume 時刻の epoch で命名される** (PRE と同名ではない)。ペア判定は「PRE epoch の直後 (2 分以内) の .post が存在するか」で行う。同名 .post を探すと全 cycle が unpaired に見える罠 (本セッションで一度誤判定しかけた)
2. **udev rule の `ATTR{d3cold_allowed}="0"` は coldplug (boot) と手動 trigger の両方で機能する**。sysfs ノブの恒久化手段として suspend 前フックより単純で、書込みタイミングも早い (デバイス registration 時)
3. **バッテリ駆動の lid close は type=suspend-then-hibernate になる** (AC 接続時は type=suspend)。今回の 6.43 h では hibernate 遷移せず s2idle 1 cycle で完走 (ss_ok +1、asleep_s 連続)。計測時は soak ログの type 欄で条件を記録しておくこと
4. **ユーザ体感の cycle 数と機械計上はズレる** (今回 32 体感 vs 37 台帳)。n の集計は必ず PRE 台帳側で行う (021628 の「1 ズレ」知見の一般形)

## 参照レポート

- [2026-07-09_205237 Phase C-7 Rung 2: 真犯人 ∈ 非 TB root port 3 本 (本実験の引継ぎ元)](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md)
- [2026-07-08_065626 Phase C-7 Rung 1: TB のみ保護では不十分 (d3cold_allowed の機序裏取り)](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md)
- [2026-07-07_230853 soak 中間観測: pcie_port_pm=off の待機電力 2.8-3.4W (比較基準)](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)
- [2026-07-06_020526 Phase C-6: pcie_port_pm=off で hang 0/30 (arm 手順の一次ソース)](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)
- [2026-07-06_002651 Phase C-5: 停止点実名 = 署名 A (TB) / 署名 B (i915)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-07-02_103415 必要条件 b'' (wl loaded + radio off) の bedrock](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
