# Thunderbolt ポートだけの絞り込み保護では hang は防げなかった — 絞り込み介入第 1 段 (Phase C-7)

**サマリ**: C-6 の広域介入 `pcie_port_pm=off` (hang 0/30) を撤去し、代わりに Thunderbolt downstream 4 ポートのみ `d3cold_allowed=0` で保護する絞り込み介入 (Rung 1) を高再現 arm で検証した結果、**有効 cycle 5 回目で hang 再発** (BT_PAN_VALID、boot 時 RTC decode = `Magic 14:355` + `pci 0000:00:02.0: hash matches`)。停止点は **C-5 署名 B (i915 の main resume entry) の完全再現**で、署名 A (TB noirq) は出なかった。TB サブツリーの保護 (D3cold 禁止 + 上流チェーン D0 常駐) だけでは不十分と確定し、`pcie_port_pm=off` を即日復帰させた。

- **実施日時**: 2026年7月8日 01:10 〜 06:56 JST
- **位置づけ**: [2026-07-07_230853](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) (待機電力 4〜5 倍の定量化) を受けた C-7 (i) 絞り込み実験の第 1 段。[C-6](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md) 引継ぎ候補 1 の実施。

## 概要

前回までで、BT テザリング + VPN + WiFi オフ時の lid close ハングは `pcie_port_pm=off` (全 PCIe ポートを省電力状態に落とさない起動オプション) で完全に抑止できることが確立していた。しかしこの対策は代償が大きく、7/7 の調査で suspend 中の待機電力が従来の 4〜5 倍 (約 3 W、鞄の中で発熱するレベル) に跳ね上がることが定量化された。そこで今回は、保護範囲を「ハングの停止点として実名の挙がった Thunderbolt ポート群だけ」に絞り込み、ハング抑止と省電力の両立を狙った。

絞り込みの手段にはカーネルの sysfs ノブ `d3cold_allowed=0` を選んだ。事前にカーネルソース (実機と同一の v6.12.94) で効果を裏取りしたところ、このノブを Thunderbolt downstream 4 ポートに書くと、(1) ポート自身は「電源まで切れる D3cold」への遷移だけが禁止され (リンクを止める D3hot までは従来どおり許可 = 省電力維持)、(2) 副作用としてその上流ブリッジチェーンが D0 常駐に固定される、という二段の効果を持つことが確認できた。スモークテストで実効も検証済みで、suspend 中の各デバイスの電源状態を直接ログに出させて「downstream 4 ポートは D3hot 止まり、上流 (05:00.0 と root port 00:1c.4) は D0 のまま」という設計どおりの状態を確認した上で本番に入った。

結果は明確だった。C-6 と同じ高再現条件 (計測カーネル + pm_trace + BT テザリング + VPN + WiFi オフ) で、有効 cycle 5 回目に lid close ハングが再発した。広域介入では 30 回やっても一度も出なかったものが、絞り込みでは 5 回目で出た。ハング率はむしろ無保護時のベースライン (約 42%) と整合しており、この絞り込みには保護効果がなかったと判断できる。

再起動後の RTC 解読で得られた停止点も示唆的だった。停止点は内蔵 GPU (i915) の main resume 入口 — C-5 で「署名 B」と呼んでいた停止点の完全再現 — であり、Thunderbolt ポートの署名 A は出なかった。保護した Thunderbolt 側の署名だけが消え、ハングそのものは i915 側の署名で生き残った形である。これは C-6 の解釈「i915 署名は被害者で、真の上流は PCIe ポートの省電力遷移」と整合しつつ、その「真の上流」が Thunderbolt サブツリーの D3cold ではないことを意味する。容疑者として残るのは、スモークテストで「sleep を D0 でなく D3hot で過ごす」ことを実測した非 Thunderbolt の root port 群 (00:1c.1 / 00:1c.2 / 00:1c.5 は sleep 時に D3hot へ遷移、00:1c.0 は runtime の D3hot のまま突入) と、Thunderbolt downstream の D3hot そのものである。特に 00:1c.2 の配下は WiFi の `wl` デバイスであり、ハングの必要条件「wl ロード済みかつ radio オフ」との接点として今後の有力な手がかりになる。

実験はハング 1 回で判定成立のため即日終了し、`pcie_port_pm=off` を復帰させて実機を保護状態に戻した (全ポート D0 常駐を検収済み)。常用 soak は従来構成で継続、モバイル持ち出し時はシャットダウンかハイバネートという 7/7 の運用指針も継続する。次の一手は、sysfs だけで可能な「非 TB root port 側の D0 固定」による半割り検証か、任意ポートを D0 固定できる計測カーネル (dpmwd5) での本格的な二分探索である。

## 添付ファイル

- [実験プラン](attachment/2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned/plan.md)
- [セッション証跡 (marker / cycle-watch / PRE 台帳 / hang PRE / boot decode / vpn-watch / 復旧後状態)](attachment/2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned/c7-evidence-raw.txt)
- [smoke 3 の D-state 実測 (dynamic debug による suspend 時電源状態ログ)](attachment/2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned/c7-smoke3-dstate-capture.txt)

## 前提・目的

- **背景 1**: C-6 で `pcie_port_pm=off` により hang 0/30 (Fisher 片側 p≈1.7×10⁻⁴)。ただし全 PCIe ポートに効く広域介入のため真犯人ポート未特定のまま常用 soak へ
- **背景 2**: [2026-07-07_230853](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) で soak ウォッチリスト (iii) が現実化 — suspend 中待機電力 2.8〜3.4 W ≈ 従来 0.70 W の 4〜5 倍。モバイル運用の実害が確定し絞り込みの優先度が上昇
- **目的**: (a) 保護範囲を TB downstream 4 ポートに絞って hang 署名が戻るかで真犯人を絞り込む、(b) hang 抑止と待機電力 0.7 W 級の両立構成を探す
- **判定設計**: hang 1 回で「絞り込み不十分」が成立 (RTC decode で停止点実名も取れる)。clean なら 30 cycle で p≈1.7×10⁻⁴
- **役割分担**: ssh 操作全般 = Claude、テザリング・lid 開閉・WiFi 復旧 = ユーザ

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / kernel **6.12.94-dpmwd4** (C-5 から不変、リビルドなし)
- 実験時 cmdline: `... quiet no_console_suspend mem_sleep_default=s2idle panic=15` (**pcie_port_pm=off を撤去**した状態、実験後に復帰)
- スリープ: s2idle、`intel_pch_thermal.delay_cnt=300`、hooks 5 本 (50/58/59/60/70)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28`、VPN: GSNet (strongSwan IKEv2、SA peer 160.16.210.47)、WiFi: `wl` loaded + radio off (hang 必要条件 b'' 成立を PRE で確認)
- 電源: AC 接続
- PCIe トポロジ (今回のログで確定):
  - TB チェーン: **root port 00:1c.4** → 05:00.0 (upstream) → 06:00.0 (→ 07:00.0 thunderbolt NHI) / **06:03.0〜06:06.0 (downstream、配下空、C-5 署名 A の 2 ポートを含む)**
  - その他 root port: 00:1c.0 (配下なし)、00:1c.1 (→ 02:00.0)、00:1c.2 (→ **03:00.0 = wl**)、00:1c.5 (→ 04:00.0 = ahci)

## 機序の裏取り (v6.12.94 ソース、実験設計の根拠)

`src/linux-6.12.y` (実機稼働版と同一) で事前確認した `d3cold_allowed=0` の効果:

1. **ポート自身の D3cold 禁止**: `acpi_pci_choose_state()` が上限を D3hot にキャップ (pci-acpi.c:926)。runtime / system sleep の両経路 (`pci_target_state` → `platform_pci_choose_state`、pci.c:2695) に効く。D3hot までは従来どおり許可 = runtime 省電力は維持される
2. **上流チェーンの D0 固定 (副作用)**: sysfs write が `pci_bridge_d3_update()` を呼び (pci-sysfs.c:579)、`pci_dev_check_d3cold()` (pci.c:3095) が `!d3cold_allowed` で false を返すため、上流 bridge の `bridge_d3` がクリアされ上位へ伝播 (pci.c:3117-3159)。bridge_d3=false のポートは runtime も system sleep も D0 常駐
3. 比較: `pcie_port_pm=off` は `pci_bridge_d3_disable=true` (pci.c:3046) で全ポートの bridge_d3 を一括不可にする広域版

つまり Rung 1 (TB downstream 4 ポートへ書込み) は「downstream 4 ポート = D3hot 止まり、上流 05:00.0 / 00:1c.4 = D0 常駐」を作る。デフォルト時の runtime D3hot 組 (06:03-06 + 00:1c.0) はほぼそのままなので、待機電力コストはほぼゼロのはずだった (この読み自体は smoke で実証されたが、hang 抑止に足りなかった)。

## 実験手順と検証ゲート

| 段階 | 内容 | 結果 |
|---|---|---|
| P0 preflight | dpmwd4 / pm_trace=0 / pstore 空 / delay_cnt=300 / hooks 5 本 / saved default / AC 91% | 全項目良好 |
| P0 soak 終了記録 | 7/6〜 soak: suspend entry/exit 36/36 ペア完全、fail=0、hang 0 | soak は hang 0 のまま終了 |
| P1 介入切替 | grub バックアップ `.bak-c7` → `pcie_port_pm=off` 削除 → update-grub + sync → 再起動 (01:12 boot) | cmdline 反映確認 |
| P1 デフォルト復帰検収 | ポート状態が C-6 介入前スナップショットと一致するか | **完全一致** (06:03-06 + 00:1c.0 = D3hot/suspended、他 D0) |
| P1 Rung 1 適用 | 06:03.0/06:04.0/06:05.0/06:06.0 へ `d3cold_allowed=0` | 書込み直後 D0 に一時 resume → 90 秒後 **D3hot に再サスペンド** (設計どおり)、05:00.0/00:1c.4 は active 継続 |
| P2 arm | sysctl panic 3 種 =1、pm_trace=1、SESSION-C7-START.marker (epoch 1783440948)、cycle-watch-c7 / vpn-watch-c7 | 稼働確認 |
| P2 smoke | WiFi のまま lid cycle ×3 (3 回目は dynamic debug で D-state 実測) | 3/3 完走。RTC decode `Magic 15:1` (成功形)。**D-state 実測: 06:03-06 は noirq skip で D3hot のまま (D3cold 遷移なし)、05:00.0 / 00:1c.4 は sleep 中も D0** = Rung 1 実効を直接確認 |
| P2 本番前 | pm_debug_messages / dynamic debug を無効化 (arm をベースライン同等に戻す)、arm 状態再検収 | pm_trace=1・sysctl=1・watchers active・d3cold_allowed=0 ×4 |
| P2 本番 | BT-PAN 接続 → radio off (detached) → ユーザが BT-PAN 上で `nmcli con up GSNet` 再確立 → lid cycle | **有効 cycle 5 回目で hang** |

## 結果: 有効 cycle 1/5 で hang 再発、停止点 = 署名 B (i915 main resume entry)

### cycle 台帳 (機械検証、証跡 [3])

| PRE epoch | 種別 | 有効性 | ペア |
|---|---|---|---|
| 1783441584 / 1783441651 / 1783444198 | smoke ×3 (WiFi) | INVALID (設計どおり) | paired |
| 1783452791 | 本番 1 | BT_PAN_VALID | paired |
| 1783454182 | 本番 2 | BT_PAN_VALID | paired |
| 1783460290 | 本番 3 | BT_PAN_VALID | paired |
| 1783460393 | 本番 4 | BT_PAN_VALID | paired |
| **1783460452** | **本番 5 (≈06:40 JST)** | **BT_PAN_VALID** | **unpaired = hang** |

- 有効性は各 PRE の ESP SA 双方向厳密一致 (`src 172.20.10.13 dst 160.16.210.47` / 逆向き) で判定。hang cycle も両方向成立
- hang cycle の PRE: `wl_loaded=YES` + `wlp3s0 DOWN` (radio off) = 必要条件 b'' 成立、`kbnepd_session=NOT FOUND` / `bnep_netdev=MISSING` は NM teardown 先行の既知の正常過渡 (063543)
- ユーザ操作: hang 後 6 分放置 (復帰なし = crawl 否定を追認) → 電源長押し → 再起動 (06:49:19 JST boot)

### 停止点 decode (証跡 [5])

再起動直後の boot 時 kernel decode (journal、汚染時刻表示 "7月28 01:07" は既知の RTC 汚染):

```
PM:   Magic number: 14:355
pci 0000:00:02.0: hash matches
```

- **marker 14 = device_resume entry (pre, main phase)、device hash = i915 (0000:00:02.0)** — C-5 の署名 B (2 回、RTC 値まで完全同一だったもの) の**三度目の完全再現**
- 署名 A (TB downstream noirq entry) は出なかった — 保護した側の署名だけが消えた
- pstore 空 = DPM watchdog (late/noirq 拡張) / hung_task / hardlockup / softlockup 全 arm でまた完全沈黙 (歴代 hang と同様相 = 「静かな停止」)
- 副次確認: `acpi LNXSYBUS:00` / `LNXCPU:06` の hash matches 併記は device hash (mod 397) の衝突による複数候補列挙で、C-5 の署名 B 同定時と同じ decode 結果。PCI デバイスの i915 が本命

### 統計

- **Rung 1 arm (`dpmwd4 + pm_trace=1 + d3cold_allowed=0(TB-downstream)`): hang 1/5 (20%)** — ベースライン (同摂動無保護 arm 8/19 ≈ 42%) と整合する率であり、保護効果は確認できない (C-6 の 0/30 との対比が決定的)
- pm_trace 摂動・無保護側 pool 更新: C-4 4/9 + C-5 4/10 + C-7 Rung1 1/5 = **9/24 ≈ 38%**
- arm tag 分離の原則どおり、非摂動 pool (~7%) / pcie_port_pm=off arm (0/30) とは合算しない

## 解釈

1. **判定マトリクス「hang 再発・署名 B」に該当**: TB downstream の D3cold 禁止 + TB 上流チェーン (05:00.0 / 00:1c.4) の D0 常駐では hang を防げない。「TB サブツリーの D3cold が単独犯」説は棄却
2. **署名 A の消滅 + 署名 B の残存**は、C-6 の「i915 署名 = 被害者 (async resume の最終書込み)」解釈と整合する。TB ポートを保護したので TB 署名は出ようがなく、hang 本体は残って i915 が引き続き「最後に動いていた thread」として記録された、という絵。ただし「i915 が当事者」の可能性も完全には排除されない (S3 時代の `i915.enable_dc=0` 不発 [2026-05-22_022030] は消極的な反証)
3. **残る容疑者**: `pcie_port_pm=off` が保護し Rung 1 が保護しなかったもの = (α) 非 TB root port 群のうち sleep を D3hot で過ごすもの (**00:1c.1 / 00:1c.2 / 00:1c.5** は suspend 時に D0→D3hot 遷移を smoke 3 で実測 [証跡 c7-smoke3-dstate-capture.txt]、**00:1c.0** は runtime D3hot のまま突入)、(β) TB downstream 06:03-06 の D3hot そのもの (D3cold でなく)。今回の結果はこの 2 群を区別できない
4. **wl との接点 (新しい手がかり)**: 00:1c.2 の配下は 03:00.0 = `wl` (BCM4360)。hang の必要条件 b'' 「wl loaded かつ radio off」と、00:1c.2 の sleep 中 D3 遷移が結びつく可能性がある (radio on/off で 00:1c.2 系の電源遷移がどう変わるかは未観測 — 次実験の観測対象)。C-7 (iv) 「なぜ radio-off が条件か」に初めて具体的な物理経路の候補が立った
5. **トポロジ訂正**: TB チェーンの root port は **00:1c.4** (プラン段階では 00:1c.1 と誤推定していた。callback ログの `parent:` 表記で確定)。bridge_d3 クリアの伝播は正しい経路 (00:1c.4) に効いていたため、実験の有効性には影響なし

## 次セッション引継ぎ (C-7 第 2 段候補)

1. **sysfs 半割り (リビルド不要、推奨)**: 子デバイス側に `d3cold_allowed=0` を書くと親 root port を D0 固定できる (機序 2)。`02:00.0 / 03:00.0 (wl) / 04:00.0 (ahci)` へ書けば 00:1c.1/1c.2/1c.5 が D0 常駐になり、Rung 1 と併用すると「非 D0 で sleep に入るポート = 00:1c.0 と 06:03-06 の D3hot のみ」まで絞れる。これで hang が消えれば真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5} (以後 1 本ずつ半割り)、消えなければ真犯人 ∈ {00:1c.0, 06:03-06 の D3hot} (00:1c.0 は配下なしのため sysfs では D0 固定不可 → dpmwd5 へ)
2. **radio on/off でのポート電源比較観測 (軽量、cycle 不要)**: dynamic debug + pm_debug_messages で radio on と off の suspend 1 回ずつを比較し、00:1c.2 (wl 親) の遷移差を見る。解釈 4 の検証
3. **dpmwd5**: per-port bridge_d3 強制 off の quirk (カーネルパッチ) で任意サブセットの完全二分探索。sysfs 半割りで足りない場合の最終手段
4. 恒久対策の現状: 当面は `pcie_port_pm=off` 常用継続 (hang 0 実績) + モバイル時シャットダウン/ハイバネート。両立構成は第 2 段以降に持ち越し

## 常用運用 (実験後の状態)

- **`pcie_port_pm=off` を即日復帰済み** (grub.bak-c7 から復元 + update-grub + sync + 再起動、全ポート D0 常駐を検収)。soak 継続
- ウォッチリスト従来どおり: (i) 原因不明の再起動、(ii) hang 再発、(iii) 待機電力 (悪化は既知・定量化済み)
- モバイル持ち出し時はシャットダウンまたはハイバネート ([7/7 レポート](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) の指針)

## 残置物 (実機の現状、7/8 06:56 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd4 (saved default、不変)。dpmwd3/2/1/stock 残置 |
| cmdline | `pcie_port_pm=off` **復帰済み** (C-6 と同一)。バックアップ `/etc/default/grub.bak-c7` (= off 入り原本) |
| d3cold_allowed | 全ポート 1 (再起動で自然揮発、恒久化はしていない) |
| pm_trace / sysctl panic 系 / pm_debug / dynamic debug | すべて 0 / 無効 (平常) |
| RTC / 時刻 | NTP 同期 + `hwclock --systohc` 済み |
| pstore | 空。pstore-guard enabled |
| /var/log/h4-probe | SESSION-C7-START.marker (1783440948)、cycle-watch-c7.log、vpn-watch-c7.log、PRE/POST 追加分。**削除しないこと** |

## 再現方法

```bash
# 1) 介入切替 (実機、要再起動)
sudo cp /etc/default/grub /etc/default/grub.bak-c7
sudo sed -i 's/ pcie_port_pm=off//' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot
# 検収: /proc/cmdline に pcie_port_pm=off が無い、
#        数分後に 06:03-06 + 00:1c.0 が runtime_status=suspended / D3hot に戻る

# 2) Rung 1 適用 (sysfs、再起動で揮発)
for p in 06:03.0 06:04.0 06:05.0 06:06.0; do
  echo 0 | sudo tee /sys/bus/pci/devices/0000:$p/d3cold_allowed
done
# 検収: 対象 4 ポートが (一時 D0 resume 後) D3hot に再サスペンド、
#        05:00.0 と 00:1c.4 が active/D0 のまま

# 3) 実効の直接観測 (smoke 時のみ、本番前に無効化)
echo 1 | sudo tee /sys/power/pm_debug_messages
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
# smoke 1 cycle 後: journalctl -b 0 -k | grep "Suspend power state"
# → 06:03-06 は行なし (noirq skip = runtime D3hot のまま)、05:00.0/00:1c.4 は D0

# 4) arm 〜 cycle 〜 判定は C-6 レポート「再現方法」と同一 (ログ名 c6→c7 読み替え)
#    RTC decode は再起動直後の journal: journalctl -b 0 -k | grep -iE "magic|hash match"
#    (RTC 生値は resume/boot 後 ~11 分でカーネルの NTP 書き戻しに上書きされる。
#     boot 時 decode 行は journal に永続するのでそちらが確実)

# 5) 復旧
sudo cp /etc/default/grub.bak-c7 /etc/default/grub
sudo update-grub && sudo sync && sudo reboot
```

## 運用知見 (C-7 で新たに確定した事項)

1. **RTC 生値の読み取りは resume 後 ~11 分が期限**: NTP 同期中のカーネルは 11 分周期で system time を RTC に書き戻すため、pm_trace の encoded 値は上書きされる。成功形の確認は cycle 直後に読むか、hang 時は **boot 時 kernel decode 行 (journal に永続) を使う**のが確実
2. **`d3cold_allowed` の sysfs write はポートを一時 D0 に resume させる** (store 内の runtime resume)。autosuspend で数十秒後に D3hot へ戻るので、検収は 90 秒程度待ってから
3. **suspend 時の各デバイス最終 D-state は dynamic debug で直接観測できる**: `pci-driver.c:910` (`PCI PM: Suspend power state`) と `pci-acpi.c:1108` (`power state changed by ACPI`) の +p 指定。pm_debug_messages と併用すると callback トレース付きで読める。noirq skip したデバイスは行が出ない (= runtime 状態のまま突入した傍証になる)
4. **TB チェーンの root port は 00:1c.4** (00:1c.1 ではない)。00:1c.1→02:00.0、00:1c.2→03:00.0 (wl)、00:1c.5→04:00.0 (ahci)

## 参照レポート

- [2026-07-07_230853 soak 中間観測: 待機電力 4〜5 倍の定量化 (本実験の動機)](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)
- [2026-07-06_020526 Phase C-6: pcie_port_pm=off で hang 0/30 (ベースライン・arm 手順の一次ソース)](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)
- [2026-07-06_002651 Phase C-5: 停止点実名 = 署名 A (TB) / 署名 B (i915)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-05-22_022030 i915.enable_dc=0 の S3 時代不発 (解釈 2 の傍証)](2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md)
- [2026-07-02_103415 必要条件 b'' (wl loaded + radio off) の bedrock](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
