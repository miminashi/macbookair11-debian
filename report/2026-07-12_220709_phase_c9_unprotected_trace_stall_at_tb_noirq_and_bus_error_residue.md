# 保護を外して 3 回ハングを再現し、停止デバイスの実名とバス上のエラー痕跡を取得した (Phase C-9)

**サマリ**: C-8 で唯一残っていた「radio-off の短縮経路が無保護の親ポート D3hot 復帰をバスレベルでどう壊すか」に踏み込むため、udev 保護を runtime で一時解除 (d3cold_allowed=1) し、dpmwd4 + pm_trace で hang を 3 回再現・全 decode に成功した。**hang #1 = 署名 B (i915 main entry、`14:355` 完全一致、通算 4 度目)、hang #3 = 署名 A (`10:204` = pcieport **0000:06:05.0** の resume noirq entry、一意 decode)、hang #2 (放置 14 時間の汚染 decode) も hour 汚染補正の総当たりで **同じ 06:05.0 の PME service device / TB NHI** に収束** — 署名 A の停止域が「TB サブツリーの noirq 復帰域」であることが 3 例目で強固になった。新設した bus-watch (resume ごとの lspci -vv/-xxx snapshot) からは、**radio-off cycle の 6/11 で wl の `DevSta: CorrErr+`、1 cycle で `NonFatalErr+` (非致命の uncorrectable)、AER HeaderLog に「wl BAR0+0x1408 への MemWr 失敗 TLP」の記録、親 00:1c.2 に `<MAbort+` (Master Abort 受信) とリンク断/再確立のラッチ**という、radio-off 経路が毎 cycle バスにエラーを撒いている直接証拠が得られた (radio-on smoke は残渣ゼロ)。副産物として「無保護 arm で lid close 放置は危険 (無人 wake → hang #2)」という運用知見も得た。セッション終了時に stock 6.12.95 + udev 保護へ完全復帰済み。

- **実施日時**: 2026年7月12日 06:20 〜 22:55 JST (hang #2 の放置 07:01〜21:24 を含む。22:51 の stock 検収 smoke まで)
- **位置づけ**: [C-8](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md) の引継ぎ 2 (機序の残り、無保護トレース) を実施

## 概要

前回 C-8 までで、ハングの必要条件 (wl の親ポート 00:1c.2 が sleep 中に D3hot に落ちること) と、radio-off が wl の resume を 54ms→22ms の「workaround は走るが本初期化を中断する」短縮経路に変えることまでは分かっていた。しかし、その短縮経路が親ポートの D3hot 復帰を実際にどう壊すのかは、無保護でハングを起こしながら観測するしかなく、未着手だった。今回はユーザがハング率 ~38% を引き受ける判断をし、udev rule 本体は温存したまま runtime だけ保護を外して、ハングの現場を 3 回押さえた。

停止点の decode は 3 回とも取れた。1 回目は歴代 4 度目となる署名 B (i915 の main resume entry、RTC 値まで完全一致)。3 回目はクリーンな一意 decode で、署名 A の正体が **Thunderbolt downstream port 0000:06:05.0 の resume noirq entry** と実名で確定した (C-5 では兄弟ポート 06:03.0/06:06.0 だった)。2 回目は就寝中に無人でハングして 14 時間放置されたため RTC が時刻進行で汚染されたが、エンコーディングの数学的性質 (user フィールドは汚染不変、デバイス hash は 1 時間あたり −21) を使った総当たり補正で、「lid close から 23 分以内に何かが機械を起こし、同じ 06:05.0 の PME service device (または TB NHI) の noirq entry で止まった」ことまで復元できた。3 回目のクリーン decode が同じポートを指したことで、この補正の妥当性も裏づけられた。

新設した bus-watch (resume のたびに親ポートと wl の PCI config space を丸ごと保存する観測系) は、期待していた「事故の痕跡」をはっきり捉えた。radio-off の成功 cycle の約半数で、wl エンドポイントに correctable error がラッチされており、1 cycle では non-fatal uncorrectable error まで出ていた。さらに AER の HeaderLog には「CPU から wl の BAR0+0x1408 への Memory Write が失敗した」という TLP がそのまま記録されていた。親ポート側にも Master Abort の受信とリンクの断/再確立がラッチされていた。radio-on の smoke ではこれらの残渣が一切出ないことと合わせ、「radio-off の短縮経路は毎 resume バスレベルでダーティであり、たまにそれが致命傷になる」という C-8 の機序の絵に、初めて物的証拠が付いた。

興味深いのは、これらの残渣が per-cycle で観測できた理由そのものが C-8 で特定した workaround の動作だという点である。エラー状態ビットは write-1-clear なので通常は一度立つと立ちっぱなしになるが、wl の workaround が毎 resume に config space を退避/復元する際に前 cycle のビットをクリアしてしまう。つまり snapshot に「+」が写っていれば、それはその cycle の復元以降に新たに起きたエラーである。

副産物が 2 つある。1 つは hang #2 の発生様態で、lid close 後に誰も触っていないのに resume が始まってハングした。本機の s2idle は電源短押しでしか起きないはずで、この無人 wake の源は未特定である (wakeup が有効なのは内蔵キーボード USB と LID0 のみと確認)。無保護 arm 中の lid close 放置は「就寝中にハングして電力を垂れ流す」リスクがあると分かったのは、今後の再演セッションへの重要な運用知見になる。もう 1 つは統計で、今回の arm (dynamic debug 常時オン込み) は 3/13 ≈ 23% のハング率だった。歴代 pool とは摂動条件が違うため分離集計とする。

「静かな死」の最終トリガ (エラーがどう伝播してタイマも NMI も止めるのか) は依然直接観測できていないが、これはバスアナライザ級の観測が要る領域であり、ソフトウェアから取れる証拠としては今回でほぼ出尽くしたと考える。実用対策 (udev rule) は今回の結果でも揺るがず、セッション終了時に stock 6.12.95 + 保護ありへ完全復帰した。

## 添付ファイル

- [実験プラン](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/plan.md)
- [hang #2 の hour 汚染補正 k-sweep 表](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/hang2-k-sweep-decode.txt)
- [bus-watch 残渣集計 (DevSta/HeaderLog/TLP decode)](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/c9-bus-residue-summary.txt)
- [bus-watch snapshot 全 13 枚](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/c9-bus-watch/)
- [D-state / callback 時間の journal 抜粋](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/journal-dstate-callbacks.txt)
- [TB callback 時間と 3 hang の boot decode 行](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/tb-callbacks-and-decodes.txt)
- [cycle-watch ログ](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/cycle-watch-c9.log) / [vpn-watch ログ](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/vpn-watch-c9.log)
- [stock 検収 smoke の D-state 抜粋 (00:1c.2 のみ D0)](attachment/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue/c9-stock-smoke-dstate.txt)

## 前提・目的

- **背景**: [C-8](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md) で機序は「半解明」。未解明の 1 点 = radio-off 短縮経路が無保護の親 D3hot 復帰をバスレベルでどう壊すか
- **目的**: (a) 無保護 + BT/VPN/radio-off で hang を再現し pm_trace decode で停止点を再確認、(b) 成功 cycle の bus 状態 snapshot からエラー痕跡 (near-miss) を検出
- **ユーザ決定**: トレースのみ (クリーンアップは後日) / dpmwd4 + pm_trace 構成 / hang 率 ~38-44% を引受け / 終了条件 = hang 2 回 or 有効 15 cycle (hang #2 の decode 汚染を受け 3 回目まで延長)
- **役割分担**: ssh 操作・arm/再 arm・decode・解析 = Claude、BT/VPN/radio/lid/電源操作 = ユーザ

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 (trixie)
- カーネル: セッション中 **6.12.94-dpmwd4** (grub default を一時変更、原本 `/etc/default/grub.bak-c9`)、終了時 **6.12.95+deb13-amd64 (stock) に復帰**
- 保護解除: runtime の `d3cold_allowed=1` のみ (udev rule `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` は不変 = 再起動ごとに保護へ自動復帰)
- arm: pm_trace=1 + sysctl panic 3 種 + dynamic debug (pci-driver.c / pci-acpi.c +p、本番中も有効 = 歴代 arm と異なる摂動、統計分離)
- 観測系: cycle-watch-c9 / vpn-watch-c9 (歴代同型) + **新設 bus-watch-c9** (`/usr/local/bin/c9-bus-snap.sh`: resume 検知 +2 秒で 00:1c.2 と 03:00.0 の lspci -vv/-xxx を保存)
- BT/VPN: iPad BT-PAN 172.20.10.13/28 + GSNet (SA peer 160.16.210.47)、AC 接続 (バッテリ 91%)

## 結果 1: hang 3 回の再現と decode

| # | 発生時刻 (JST) | 有効 cycle | decode (boot 時 kernel 行) | 解釈 |
|---|---|---|---|---|
| 1 | 07/12 06:46 (PRE 1783806393) | batch1 の 4 回目 | `Magic 14:355` + `pci 0000:00:02.0` | **署名 B** (i915 main resume entry)。C-5/C-7 Rung1 と RTC 値まで完全一致、通算 4 度目 |
| 2 | 07/12 07:01 lid close → 無人 wake (PRE 1783807283) | batch2 の 8 回目 | `Magic 10:395` (汚染) → k=14 補正で `10:101` | **署名 A 系**。device_resume_noirq entry @ **0000:06:05.0:pcie204 (PME service) or 0000:07:00.0 (TB NHI)** |
| 3 | 07/12 21:42 (PRE 1783860170) | batch3 の 2 回目 | `Magic 10:204` + `pcieport 0000:06:05.0` (一意) | **署名 A**。device_resume_noirq entry @ **TB downstream port 06:05.0** |

- 全 hang cycle が BT_PAN_VALID (PRE に ESP SA 双方向)、pstore 3 回とも空 (歴代同様の静かな停止)、wl は全 cycle radio-off 短縮経路 (suspend 10µs / resume 22.3ms) を通っていた
- **署名 A の実名が 3 例に**: C-5 の 06:03.0 / 06:06.0 に加え今回 06:05.0 (+PME service/NHI) — 停止域は「特定の 1 デバイス」ではなく **TB サブツリーの noirq 復帰域** と読むのが妥当
- 署名 B と署名 A は resume の異なる段 (main の i915 窓 / noirq の TB 域) で起きる別々の「窓」であり、どちらも 00:1c.2 D0 固定で消える (C-6/C-7) = 共通上流は親ポートの D3hot 遷移

### hang #2 の hour 汚染補正 (新手法)

14.4 時間の放置で RTC が時刻進行し boot 時読み値が汚染されたが、dpmwd3/4 エンコーディング (`val = (mon-1) + (mday-1)*12 + hour*336`、user = val%16) の性質から:

- **user フィールドは hour 汚染に対して不変** (336 = 21×16 ≡ 0 mod 16) → 「user=10 = device_resume_noirq entry」は汚染下でも確定
- file (デバイス hash) は経過 1 時間あたり −21 → 経過時間 k を 0〜14 で総当たりし、実機の全デバイス名 (dpm_list 相当 578 名) の sdbm hash と照合
- k=13 (07:24-08:24 wake) は一致なし、k=14 (lid close 07:01:23 〜 07:24 の wake) で `0000:06:05.0:pcie204` / `0000:07:00.0` が一致。「発見時に本体が温かい = hang が長時間継続」とも整合し、k=14 を採用
- hang #3 のクリーン decode (`10:204` = 06:05.0 本体) が同一ポートを指したことで補正の妥当性を相互確認

## 結果 2: bus-watch が捉えたエラー痕跡 (radio-off 経路はダーティ)

resume ごとの config space snapshot 13 枚 (baseline 1 + radio-on smoke 1 + radio-off 成功 cycle 11) の比較:

| 観測点 | radio-on smoke | radio-off cycle (11 枚) |
|---|---|---|
| wl `DevSta: CorrErr+` | − | **6/11 で + (per-cycle 判定)** |
| wl `DevSta: NonFatalErr+` | − | **1/11 で +** (807105、非致命 uncorrectable) |
| wl AER HeaderLog | 全 0 | **`40000001 0000000f c1201408` が batch2 以降残存** |
| wl config 残差 0xAA (07→03、lspci 未 decode 領域) | − (baseline と完全一致) | **11/11 で残存** (radio-off 恒常マーカー) |
| 親 00:1c.2 `<MAbort+` / Slot `PresDet+ LinkState+` | 初回 cycle でラッチ | (一回性ラッチのため per-cycle 判定不能) |

- **HeaderLog の TLP decode**: MWr32 (1DW、requester = CPU) → 宛先 `0xc1201408` = **wl BAR0 (0xc1200000, 32K) + 0x1408**。「CPU から wl チップのレジスタへの Memory Write が endpoint 側でエラーとして記録された」ことの直接証拠。記録時点は batch1 終端〜batch2 初回 snapshot の間で、候補 = (i) hang #1 の死の窓 (バッテリ 3.3Vaux で sticky レジスタが強制断を生き残った場合)、(ii) 強制断後 boot の wl_up (war は boot でも走る)、(iii) batch2 cycle 1。一意特定は不能だが、いずれでも「war/初期化経路の MMIO write がバスレベルで失敗することがある」ことは確定
- **per-cycle 判定が可能な理由**: DevSta/AER status は RW1C で通常累積するが、**wl の war が毎 resume に config space を退避/復元する際に前 cycle のビットをクリアする** (C-8 で特定した `si_pcie_configspace_cache` の副作用)。snapshot の「+」はその cycle の復元以降に新規発生したエラー
- 正常時の callback 時間 (hang boot の成功 cycle で確認): 06:05.0 の resume_noirq = **11.7ms** (D3hot→D0)、i915 main resume = **445ms**、wl main resume = **22.3ms** — C-8 の窓構造と完全一致

## 結果 3 (副産物): 無人 wake の発見と無保護運用の危険

- hang #2 は lid close (07:01:23) 後、**誰も触っていないのに 23 分以内に resume が開始**され (k=14 補正)、noirq 段で hang、14 時間電力を垂れ流して本体が温まった状態で発見された
- 本機の s2idle wake は「電源短押しのみ」が確立事実だったため、この無人 wake の源は謎。wakeup 有効デバイスは **LID0 (/proc/acpi/wakeup) と usb 1-5 (内蔵キーボード/トラックパッド、power/wakeup=enabled)** のみと確認 (BT コントローラは disabled = iPad 側トラフィック起因ではない)
- **運用教訓: 無保護 arm 中は lid close 放置をしない** (cycle 終了時は lid を開けたままにする)

## 統計

- **c9 arm (dpmwd4 + pm_trace + dynamic debug 常時オン + 無保護): hang 3 / 有効 13 cycle ≈ 23%** (clean 10、ほかに VPN 瞬断の INVALID clean 1)
- 歴代の無保護 arm (pm_trace、dynamic debug オフ) 9/24 ≈ 38% とは摂動条件が異なるため**合算しない** (参考比較のみ。差は n が小さく有意ではない)
- 3 hang の署名内訳: B ×1、A ×2 — C-4〜C-5 期 (B ×2、A ×2 + 初期 2 回) と同様に両署名が混在して出る

## 撤収検収 (実機の現状、7/12 22:10 JST)

| 項目 | 状態 |
|---|---|
| kernel | **6.12.95+deb13-amd64 (stock) 復帰済み**。dpmwd4 は grub 残置 (再演可) |
| grub | `GRUB_DEFAULT=0` 復元済み (`update-grub` + sync 済み、原本 `grub.bak-c9` 残置)。saved_entry は dpmwd4 を指すが DEFAULT=0 のため未使用 |
| 保護 | udev rule 不変、再起動で自動復帰済み (**d3cold_allowed=0 実測**) |
| arm 解除 | pm_trace=0 (stock には機構ごと無し)、sysctl panic 系 0、dynamic debug 無効、watchers 停止 |
| pstore | 空 |
| 残置物 | `/usr/local/bin/c9-bus-snap.sh` (保護あり比較の follow-up 用)、`/var/log/h4-probe/` に C9 marker・cycle/vpn-watch ログ・c9-bus-watch/ (**削除しないこと**) |
| stock smoke | **実施済み (7/12 22:51 JST)**: WiFi on lid cycle → PRE/POST ペア成立 (1783863109/1783863141)、dynamic debug 一時有効化で **00:1c.2 のみ D0 で sleep** (wl/TB 系/他 root port は D3hot) = 保護ありの正しい形を実測確認。dynamic debug は検収後に無効へ復旧済み |

## 次セッション引継ぎ

1. **非摂動 soak 継続 (stock 6.12.95 + udev rule)**: C-8 の引継ぎと同じ。ウォッチリスト: hang 再発 / 原因不明の再起動 / 待機電力
2. **安価な follow-up (任意、hang リスクなし)**: 保護あり (d3cold=0) + BT/VPN/radio-off cycle で bus-watch を回し、CorrErr/HeaderLog 残渣が保護下でも出るか比較 → 「残渣は無保護特有か、radio-off 特有か」を切り分けられる。`c9-bus-snap.sh` 残置済みで即実施可
3. **未解明の残り (任意、優先度低)**: (i) BAR0+0x1408 のレジスタ実名 (blob レジスタマップの追加解析)、(ii) 無人 wake の源 (usb 1-5 wakeup を disable して soak する消去法が安価)、(iii) 「静かな死」の最終伝播機構 (ソフトウェア観測はほぼ出尽くし、バスアナライザ級が必要)
4. **クリーンアップ (C-8 引継ぎ 3、未実施)**: apt autoremove (26 pkg、stock 6.12.94 image を含む点に注意) / dpmwd1-3 purge / 6.12.74 hold 整理
5. **統計の注意**: c9 arm (3/13) は新 tag。歴代 pool と合算しない

## 再現方法

```bash
# 1) grub default を dpmwd4 へ一時変更 (hang 強制断後も dpmwd4 で起動させ decode を成立させる)
sudo cp /etc/default/grub /etc/default/grub.bak-c9
sudo sed -i 's/^GRUB_DEFAULT=0/GRUB_DEFAULT=saved/' /etc/default/grub
sudo update-grub && sudo sync
sudo grub-set-default "gnulinux-advanced-<UUID>>gnulinux-6.12.94-dpmwd4-advanced-<UUID>"
sudo sync && sudo reboot

# 2) arm + 無保護化 + 観測系 (再起動のたびに再実行)
sudo sysctl -w kernel.hung_task_panic=1 kernel.hardlockup_panic=1 kernel.softlockup_panic=1
echo 1 | sudo tee /sys/power/pm_trace
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
sudo systemd-run --unit=bus-watch-c9 --collect /usr/local/bin/c9-bus-snap.sh   # 新設観測系
echo 1 | sudo tee /sys/bus/pci/devices/0000:03:00.0/d3cold_allowed             # 無保護化 (udev rule は触らない)
# smoke: WiFi on で lid cycle 1 回 → journal で 00:1c.2 が D3hot で sleep することを確認

# 3) 本番 cycle: BT-PAN + GSNet + radio off で lid 開閉。hang したら 5 分放置 → 長押し → 電源 on
#    → 起動直後に decode 回収: journalctl -b 0 -k | grep -iE "magic|hash match"
#    (60 分以内の再起動なら無汚染。放置した場合は k-sweep 補正: user は不変、file は -21/h)

# 4) 撤収: 手順 1-2 の逆操作 + GRUB_DEFAULT=0 復元 + reboot → stock で d3cold_allowed=0 を検収
```

## 運用知見 (C-9 で新たに確定した事項)

1. **hour 汚染 decode の補正手法が確立**: user = val%16 は 336≡0 (mod 16) より汚染不変、file は −21/h。経過時間 k を総当たりし全デバイス名 (dpm_list 相当、`find /sys/devices -name power -type d` の親 basename ~578 名) の sdbm hash と照合すれば、長時間放置後でも停止デバイス候補を復元できる
2. **GRUB_DEFAULT=0 環境での hang 再演は default の一時変更が必須**: 強制断後の boot が stock に落ちると dpmwd3/4 独自エンコーディングを decode できない (歴代セッションは default=saved→dpmwd4 だったため顕在化しなかった)
3. **wl の war による config space 退避/復元は RW1C エラービットを毎 resume クリアする** → snapshot 比較で per-cycle のエラー発生判定ができる (逆に「累積カウンタ」としては使えない)
4. **hang cycle の journal 行は watcher のファイル出力ごと失われる** (page cache が強制断で消える)。PRE ファイル (h4-probe) は今回も 3/3 生き残ったが、cycle-watch ログの hang cycle エントリは 3/3 消えた — hang 判定は PRE 台帳が正
5. **バッテリ機の sticky AER レジスタは電源長押しを生き残る可能性がある** (3.3Vaux)。HeaderLog 等の帰属判定では「強制断でリセットされたはず」を前提にしないこと
6. **無保護 arm 中の lid close 放置は禁止** (結果 3)。cycle 終了時は lid を開けたまま報告を待つ

## 参照レポート

- [2026-07-12_060000 Phase C-8: wl war 機序特定 + stock 復帰 (本セッションの引継ぎ元)](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md)
- [2026-07-10_122213 Phase C-7 Rung 3: 真犯人 00:1c.2 確定・udev rule 恒久化](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md)
- [2026-07-08_065626 Phase C-7 Rung 1: 署名 B 三度目 (Magic 14:355 同値)](2026-07-08_065626_phase_c7_rung1_tb_d3cold_block_insufficient_signature_b_returned.md)
- [2026-07-06_002651 Phase C-5: 署名 A/B の初出 (dpmwd4 デバイス実名 decode)](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-07-05_185344 Phase C-4: firmware-safe pm_trace エンコーディングの設計](2026-07-05_185344_dpmwd3_phase_c4_hang_stall_located_resume_noirq_early_all_watchdogs_silent.md)
