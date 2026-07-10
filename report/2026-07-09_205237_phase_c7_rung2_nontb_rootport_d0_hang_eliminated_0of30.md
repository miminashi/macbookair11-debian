# 非 Thunderbolt ルートポート 3 本の保護で hang が消えた — 真犯人はカメラ・WiFi・SSD のいずれかのポートに絞り込み (Phase C-7 第 2 段)

**サマリ**: Rung 1 の保護 (TB downstream 4 ポート `d3cold_allowed=0`) に加えて、子デバイス 02:00.0 (FaceTime カメラ)・03:00.0 (wl = BCM4360)・04:00.0 (SSD) へも `d3cold_allowed=0` を書き、親ルートポート 00:1c.1 / 00:1c.2 / 00:1c.5 を sleep 中 D0 に固定する絞り込み介入 (Rung 2) を高再現 arm で検証した結果、**hang 0/30 (全 BT_PAN_VALID、unpaired PRE ゼロ、pstore 空)**。同摂動ベースライン 8/19 ≈ 42% に対し Fisher 片側 p ≈ 1.7×10⁻⁴ で「介入により hang 消滅」が成立。Rung 1 (hang 1/5) との差分は非 TB ルートポート 3 本の保護のみであり、**真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5} が確定**した。00:1c.2 は wl の親ポートであり、hang の必要条件 b'' (wl loaded + radio off) との物理接点として引き続き最有力。副観測として radio on/off の suspend 時 D-state 比較も実施し、**最終 D-state は両条件で完全同一** (radio off が効くのは D-state 以外の層) という重要な消去も得た。

- **実施日時**: 2026年7月8日 15:07 〜 7月9日 20:52 JST
- **位置づけ**: [C-7 Rung 1](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md) の引継ぎ候補 1 (sysfs 半割り、推奨) と候補 2 (radio on/off 遷移比較) を同一セッションで実施。

## 概要

前回 (Rung 1) では、ハングの停止点として実名の挙がった Thunderbolt ポート群だけを保護しても、ハングは i915 側の署名で生き残ることが分かった。容疑者として残ったのは「広域介入 `pcie_port_pm=off` が保護し、Rung 1 が保護しなかったもの」、すなわち sleep 中に省電力状態 (D3hot) で過ごす非 Thunderbolt のルートポート群と、Thunderbolt ポートの D3hot そのものの 2 群だった。今回はこの 2 群を二分する実験を行った。

手段は前回と同じ sysfs ノブ `d3cold_allowed=0` の応用である。このノブは書き込んだデバイス自身の D3cold を禁止するだけでなく、副作用としてその上流ブリッジチェーンを D0 常駐に固定する。そこで Rung 1 の書込み (TB downstream 4 ポート) に加えて、非 TB ルートポート配下の子デバイス 3 つ — FaceTime カメラ (02:00.0)、WiFi の wl (03:00.0)、SSD (04:00.0) — にも書き込むことで、親ルートポート 00:1c.1 / 00:1c.2 / 00:1c.5 を D0 固定した。スモークテストの実測で「sleep 中もこの 3 ポートは D0 に留まり、非 D0 で sleep に入るのは 00:1c.0 と TB 系の D3hot のみ」という設計どおりの状態を確認した上で本番に入った。

結果は明確だった。Rung 1 で 5 回目に出たハングが、同じ高再現条件 (計測カーネル + pm_trace + BT テザリング + VPN + WiFi オフ) で 30 回やって一度も出なかった。統計的にも Fisher 片側 p ≈ 1.7×10⁻⁴ で「保護により hang 消滅」が成立する。Rung 1 と Rung 2 の差分は非 TB ルートポート 3 本の保護だけなので、ハングの必要要素はこの 3 本のいずれか (または複数) にあると確定した。逆に、Rung 2 でも保護しなかった 00:1c.0 と TB 系の D3hot は、ハングを起こすのに十分でないことが分かった (Rung 1 でも非保護のままハングした側の要素ではない)。

もうひとつの収穫は軽量な副観測から出た。WiFi の radio on と off で suspend 時の各デバイスの最終電源状態を比較したところ、全ポート・全デバイスで完全に同一だった。wl も、その親ポート 00:1c.2 も、radio の状態に関わらず同じ D3hot に落ちる。つまり「radio off がポートの電源遷移そのものを変える」という単純な機序は否定され、radio off が効いているのは最終 D-state 以外の層 — wake/PME の設定、リンク状態、resume 側の復帰処理、あるいは wl ドライバの内部状態 — にあることが分かった。

次の一手は 3 本の中の一本釣りである。必要条件 b'' との接点から 00:1c.2 (wl 親) が最有力なので、03:00.0 だけに `d3cold_allowed=0` を書く単独保護 (Rung 3) で clean になれば真犯人はほぼ 00:1c.2 に確定する。ハングと省電力を両立する恒久対策も、ルートポート 1 本だけの D0 固定で済むなら待機電力の代償はごく小さいはずで、`pcie_port_pm=off` (待機電力 4〜5 倍) を置き換えられる見込みが立ってきた。実験後は従来どおり `pcie_port_pm=off` を復帰させて soak を継続している。

## 添付ファイル

- [実験プラン](attachment/2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30/plan.md)
- [セッション証跡 (marker / cycle-watch / PRE 台帳 / S4 RTC キャッチ / vpn-watch / S1 実効実測 / pstore / boot)](attachment/2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30/c7r2-evidence-raw.txt)
- [観測 O1: radio on の suspend 時 D-state](attachment/2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30/o1-radio-on-dstate.txt)
- [観測 O2: radio off の suspend 時 D-state](attachment/2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30/o2-radio-off-dstate.txt)

## 前提・目的

- **背景**: [Rung 1](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md) で「TB サブツリー D3cold 単独犯」説が棄却され、容疑者 = (α) 非 TB root port 群 {00:1c.1, 00:1c.2, 00:1c.5} (sleep 時 D0→D3hot 実測) + 00:1c.0 (runtime D3hot 突入)、(β) TB downstream の D3hot、の 2 群に絞られていた
- **目的**: (a) Rung 1 の保護 + 非 TB root port 3 本の D0 固定 (= sysfs 半割り) で hang が消えるかにより (α) と (β) を判別する、(b) 副観測として radio on/off でポート電源遷移が変わるか (Rung 1 解釈 4) を検証する
- **判定設計**: hang 再発 → 真犯人 ∈ {00:1c.0, 06:00.0, 06:03-06 の D3hot} → dpmwd5 (per-port quirk) へ / clean 0/30 → 真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5} (Fisher 片側 p ≈ 1.7×10⁻⁴)
- **役割分担**: ssh 操作全般 = Claude、テザリング・lid 開閉・WiFi 復旧 = ユーザ

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / kernel **6.12.94-dpmwd4** (C-5 から不変、リビルドなし)
- 実験時 cmdline: `... quiet no_console_suspend mem_sleep_default=s2idle panic=15` (`pcie_port_pm=off` を撤去、実験後に復帰)
- スリープ: s2idle、`intel_pch_thermal.delay_cnt=300`、hooks 5 本 (50/58/59/60/70)
- BT/テザリング: iPad BT-PAN `172.20.10.13/28`、VPN: GSNet (strongSwan IKEv2、SA peer 160.16.210.47)、WiFi: `wl` loaded + radio off
- 電源: AC 接続 (開始時 BAT 90%)
- PCIe トポロジと今回の役者 (lspci 実名):
  - 00:1c.0 (Root Port #1、配下なし) / 00:1c.1 (#2 → 02:00.0 **FaceTime HD カメラ**) / 00:1c.2 (#3 → 03:00.0 **BCM4360 = wl**) / 00:1c.5 (#6 → 04:00.0 **Samsung SSD AHCI**)
  - TB チェーン: 00:1c.4 → 05:00.0 (upstream) → 06:00.0 (→ 07:00.0 NHI) / 06:03.0〜06:06.0 (downstream)

## 実験手順と検証ゲート

| 段階 | 内容 | 結果 |
|---|---|---|
| P0 preflight | dpmwd4 / pm_trace=0 / pstore 空 / delay_cnt=300 / hooks 5 本 / saved default / AC 90% / sysctl panic 3 種 =0 記録 | 全項目良好 |
| P0 soak 記録 | 7/8 06:53 boot 以降 suspend 0 回のまま中断 (soak 区間クリーン) | 記録済み |
| P1 介入切替 | grub バックアップ `.bak-c7r2` → `pcie_port_pm=off` 削除 → update-grub + sync → 再起動 (7/8 16:26 boot) | cmdline 反映確認 |
| P1 デフォルト検収 | 06:03-06 + 00:1c.0 = D3hot/suspended、他 D0 (C-6 介入前スナップショットと一致) | 完全一致 |
| P1b 観測 O1 | radio on のまま lid cycle、dynamic debug で D-state 実測 (7/8 16:28) | 全 D-state 取得 |
| P1b 観測 O2 | radio off (BT/VPN なし) で lid cycle、同様に実測 (7/9 13:48) | **O1 と完全同一** |
| P1c Rung 2 適用 | `d3cold_allowed=0` を 7 デバイスへ (06:03.0/06:04.0/06:05.0/06:06.0 + 02:00.0/03:00.0/04:00.0) | 90 秒後検収: 00:1c.1/2/4/5 + 05:00.0/06:00.0 = D0 常駐、06:03-06 = D3hot 復帰 |
| P1c smoke S1 | WiFi lid cycle 1 回、dynamic debug で sleep 中実効を実測 | **00:1c.1/2/5 = D0 のまま sleep** (O1/O2 では D3hot)、00:1c.4/05:00.0 = D0、非 D0 は 00:1c.0・06:00.0・06:03-06 の D3hot のみ |
| P2 arm | 観測系無効化 → sysctl panic 3 種 =1、pm_trace=1、SESSION-C7R2-START.marker (epoch 1783577736)、cycle-watch-c7r2 / vpn-watch-c7r2 | 稼働確認 |
| P2 smoke S2-S4 | WiFi lid cycle ×3。S4 は resume 検知即読ワンショットで RTC 生値捕獲 | 3/3 完走。S4 RTC 生値 `2027-08-03 00:00:01` → **decode `Magic 15:1` (成功形)** = encode→RTC→decode の e2e 検証済み |
| P2 本番 | BT-PAN → radio off → GSNet 再確立 → lid cycle 反復 (7/9 15:33〜20:43) | **hang 0、BT_PAN_VALID 30** |

## 結果: hang 0/30、真犯人 ∈ {00:1c.1, 00:1c.2, 00:1c.5}

### cycle 台帳 (機械検証、証跡参照)

- SESSION epoch 1783577736 以降の PRE = 36 本、**全 36 本 paired (unpaired = hang ゼロ)**
- 内訳: **BT_PAN_VALID 30** / INVALID 6 (smoke S2/S3/S4 の 3 本 = 設計どおり、本番冒頭のセットアップ過渡 2 本、本番中の SA 欠落過渡 1 本)
- 有効性は各 PRE の ESP SA 双方向厳密一致 (`src 172.20.10.13 dst 160.16.210.47` / 逆向き) で判定
- 本番は当初 27 有効で完走 → 事前設計の n=30 に揃えるため 3 有効 cycle を追加 (ユーザ合意の上)
- pstore 空 (dpmwd4 の watchdog panic なし)、boot ID 不変 (セッション中の再起動なし)

### 統計

- **Rung 2 arm (`dpmwd4 + pm_trace=1 + d3cold_allowed=0(TB-downstream ×4 + 02/03/04:00.0)`): hang 0/30** — 同摂動無保護ベースライン 8/19 ≈ 42% に対し **Fisher 片側 p ≈ 1.7×10⁻⁴**
- 比較: Rung 1 arm (非 TB root port 非保護) は 1/5 で hang。Rung 1 → Rung 2 の差分は 00:1c.1/2/5 の D0 固定のみ
- pm_trace 摂動・無保護 pool は 9/24 ≈ 38% のまま不変 (本セッションは保護 arm のみで無保護データなし)。arm tag 分離の原則どおり合算しない

### 副観測: radio on/off で suspend 時の最終 D-state は完全同一 (O1/O2)

| デバイス | O1 (radio on) | O2 (radio off) |
|---|---|---|
| wl 03:00.0 | D3hot | D3hot |
| 00:1c.2 (wl 親) | D3hot | D3hot |
| 00:1c.1 / 00:1c.5 | D3hot / D3hot | D3hot / D3hot |
| TB チェーン (00:1c.4/05:00.0/06:00.0/07:00.0) | D3hot | D3hot |
| i915 00:02.0 | D3hot | D3hot |
| 00:1c.0 / 06:03-06 | 行なし (runtime D3hot のまま) | 行なし (同左) |

Rung 1 解釈 4 の単純形「radio off が 00:1c.2 系の電源遷移を変える」は**否定**。radio off の寄与は最終 D-state 以外の層 (PME/wake 設定、リンク状態、resume 側処理、wl ドライバ内部状態など) にある。

## 解釈

1. **判定マトリクス「clean 0/30」に該当**: hang の必要要素は非 TB ルートポート 3 本 {00:1c.1 (カメラ), 00:1c.2 (wl), 00:1c.5 (SSD)} のいずれか (または複数) の sleep 中 D3hot 遷移にある。C-6 の「PCIe ポート D3 遷移が署名 A/B の共通上流」解釈が一段具体化した
2. **消去された容疑者**: 00:1c.0・06:00.0・06:03-06 の D3hot は、Rung 1 (hang 発生) と Rung 2 (hang 消滅) の両方で非保護のまま変わっていないので、**この群だけでは hang を起こせない** (単独犯説は消去)。厳密には「00:1c.1/2/5 のいずれかとの連言 (共犯) で必要」という構造は残るが、その場合でも 00:1c.1/2/5 側を保護すれば hang は切れることが今回実証されたので、絞り込みと恒久対策の観点では 00:1c.1/2/5 に集中してよい
3. **00:1c.2 (wl 親) が引き続き最有力**: 必要条件 b'' (wl loaded + radio off) との物理接点はこのポートのみ。ただし O1/O2 比較により機序は「D-state の違い」ではなく、D3hot に落ちたポートの**復帰時**の振る舞いが radio off + BT-PAN + VPN の条件下でのみ壊れる、という形に絞られる (停止域が resume 側 [C-4] であることとも整合)
4. **i915 署名 (B) の被害者説は維持**: 今回も i915 には一切触れていないのに hang が消えた。署名 B は「最後に動いていた thread の記録」であり当事者ではない、という C-6/R1 の解釈と整合
5. **恒久対策の見通し**: 真犯人が 1 本に絞れれば、そのポートだけの D0 固定 (配下の子 1 つへの `d3cold_allowed=0` 書込み、suspend 前フックで可能) で hang 抑止と待機電力 ~0.7W 級の両立が狙える。`pcie_port_pm=off` (待機電力 4〜5 倍) の置き換え候補

## 次セッション引継ぎ (C-7 第 3 段候補)

1. **Rung 3 = 一本釣り (推奨)**: `03:00.0` (wl) のみに `d3cold_allowed=0` → 00:1c.2 単独 D0 固定 (TB 側の書込みは不要 — TB は容疑者から外れたため)。clean 0/30 なら真犯人 ≈ 00:1c.2 確定。hang なら次は 00:1c.5 (SSD、放置ポートの中で使用頻度が高い) → 00:1c.1 の順
2. **恒久対策の実装形**: 真犯人確定後、(a) cmdline 不要の suspend 前フックで対象子デバイスに `d3cold_allowed=0` を書く、または (b) boot 時 udev rule / oneshot で恒久化。待機電力の一晩計測で 0.7W 級に収まるかを検収
3. **機序の残り (C-7 (iv))**: radio off が「D3hot からの復帰」を壊す仕組みは未解明。O1/O2 で D-state 差は消去済みなので、次の観測候補は radio on/off での PME/wake 設定差 (`/sys/.../power/wakeup`、PME enable ビット、`lspci -vv` の PM 状態) と、resume 順序・リンクトレーニングの差
4. **統計の注意**: Rung 3 も arm tag 分離 (`d3cold_allowed=0(03:00.0)` 単独) で集計する

## 常用運用 (実験後の状態)

- **`pcie_port_pm=off` を復帰済み** (grub.bak-c7r2 から復元 + update-grub + sync + 再起動、全ポート D0 常駐を検収)。soak 継続
- ウォッチリスト従来どおり: (i) 原因不明の再起動 (pstore で判別)、(ii) hang 再発、(iii) 待機電力 (悪化は既知・定量化済み)
- モバイル持ち出し時はシャットダウンまたはハイバネート ([7/7 レポート](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md) の指針)

## 残置物 (実機の現状、7/9 20:52 JST)

| 項目 | 状態 |
|---|---|
| kernel | 6.12.94-dpmwd4 (saved default、不変)。dpmwd3/2/1/stock 残置 |
| cmdline | `pcie_port_pm=off` **復帰済み** (C-6 と同一)。バックアップ `/etc/default/grub.bak-c7r2` (= off 入り原本)、`.bak-c7` (R1 時のもの) も残存 |
| d3cold_allowed | 全ポート 1 (再起動で自然揮発を検収済み) |
| pm_trace / sysctl panic 系 / pm_debug / dynamic debug | すべて 0 / 無効 (平常) |
| RTC / 時刻 | `hwclock --systohc` 済み、NTP 同期正常 |
| pstore | 空。pstore-guard enabled |
| /var/log/h4-probe | SESSION-C7R2-START.marker (1783577736)、cycle-watch-c7r2.log、vpn-watch-c7r2.log、rtc-catch-s4.log、PRE/POST 追加分。**削除しないこと** |

## 再現方法

```bash
# 1) 介入切替 (実機、要再起動) — R1 と同一
sudo cp /etc/default/grub /etc/default/grub.bak-c7r2
sudo sed -i 's/ pcie_port_pm=off//' /etc/default/grub
sudo update-grub && sudo sync && sudo reboot

# 2) 観測 O1/O2 (radio on/off の D-state 比較、BT/VPN なし)
echo 1 | sudo tee /sys/power/pm_debug_messages
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
# radio on で lid cycle 1 回 → radio off (nmcli radio wifi off) で 1 回
# 回収: journalctl -b 0 -k -o short-unix | grep -E "Suspend power state|power state changed by ACPI"

# 3) Rung 2 適用 (sysfs、再起動で揮発)
for p in 06:03.0 06:04.0 06:05.0 06:06.0 02:00.0 03:00.0 04:00.0; do
  echo 0 | sudo tee /sys/bus/pci/devices/0000:$p/d3cold_allowed
done
# 検収 (90 秒後): 00:1c.1/2/4/5 + 05:00.0/06:00.0 が runtime_status=active
# smoke 1 cycle で sleep 中実効を実測: 00:1c.1/2/5 が "Suspend power state: D0"

# 4) arm 〜 cycle 〜 判定は C-6 レポート「再現方法」と同一 (ログ名 c6→c7r2 読み替え)
#    smoke の decode 成功形確認は「resume 検知即読ワンショット」で (運用知見 2 参照):
sudo systemd-run --unit=rtc-catch --collect bash -c '
  journalctl -k -f -o cat -n 0 | grep -m1 --line-buffered "PM: suspend exit" >/dev/null
  for i in 1 2 3; do echo "$(date +%s.%N) $(cat /sys/class/rtc/rtc0/date) $(cat /sys/class/rtc/rtc0/time)" >> /var/log/h4-probe/rtc-catch.log; done'
# decode: report/attachment/2026-07-05_185344_*/decode.py "YYYY-MM-DD HH:MM:SS" → Magic 15:1 が成功形

# 5) 復旧
sudo cp /etc/default/grub.bak-c7r2 /etc/default/grub
sudo update-grub && sudo sync && sudo reboot
```

## 運用知見 (C-7 R2 で新たに確定した事項)

1. **pm_trace セッション中の `uptime -s` は信用できない**: pm_trace が RTC を破壊すると `timekeeping_resume` の sleep 長計算が狂い、boottime クロックに誤った sleep 時間が注入される。`uptime -s` が実 boot 時刻から数時間ずれて「再起動したように見える」罠 (今回 3.4 時間ずれた)。**再起動の有無は boot ID (`journalctl --list-boots`) と systemd-run ユニットの生存で判定する**
2. **成功 cycle の decode 確認は「resume 検知即読ワンショット」で**: 59-pmtrace-timefix hook が post で timesyncd を再起動するため、RTC encoded 値は resume 後すぐ上書きされる (R1 の「~11 分」より実測はるかに速い)。`journalctl -k -f | grep -m1 "PM: suspend exit"` をトリガに RTC を即読する systemd-run ワンショットなら、resume 後 0.01 秒で生値 (`Magic 15:1`) を捕獲できる
3. **`d3cold_allowed=0` の親 D0 固定は子デバイス側への書込みでも機能する** (機序 2 の実証第 2 例): endpoint (カメラ/wl/SSD) に書けば親 root port が sleep 中も D0 に留まることを dynamic debug の実測で確認。endpoint 自身は従来どおり D3hot に落ちる
4. **wl の runtime PM は endpoint への `d3cold_allowed` 書込み後 D0 のままになる** (02/03/04:00.0 は runtime autosuspend しない設定のため書込み時の一時 resume から戻らない)。sleep 時の挙動には影響なし

## 参照レポート

- [2026-07-08_065626 Phase C-7 Rung 1: TB のみ保護では不十分 (本実験の引継ぎ元)](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md)
- [2026-07-07_230853 soak 中間観測: 待機電力 4〜5 倍の定量化 (絞り込みの動機)](2026-07-07_230853_s2idle_standby_power_increase_on_pcie_port_pm_off.md)
- [2026-07-06_020526 Phase C-6: pcie_port_pm=off で hang 0/30 (ベースライン・arm 手順の一次ソース)](2026-07-06_020526_phase_c6_pcie_port_pm_off_hang_eliminated_0of30.md)
- [2026-07-06_002651 Phase C-5: 停止点実名 = 署名 A (TB) / 署名 B (i915)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-07-05_185344 Phase C-4: dpmwd3 firmware-safe pm_trace と decode.py](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md)
- [2026-07-02_103415 必要条件 b'' (wl loaded + radio off) の bedrock](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
