# WiFi ドライバが復帰のたびに行う隠れた初期化処理を特定し、カーネルを通常版へ戻した (Phase C-8)

**サマリ**: broadcom-sta (wl) の Debian ソース + バイナリ blob の逆アセンブルにより、**resume のたびに wl が BCM4360 専用の PCIe workaround (`wlc_bmac_4360_pcie2_war` = PLL 再プログラム + PCIe config space 退避/復元) を実行している**ことをソースレベルで特定した。実機トレース (pm_print_times の callback 時間) では radio on/off で wl の resume callback が **54ms ↔ 22ms** と再現性よく分岐し (BT/VPN は不変)、必要条件 b'' (radio off) の寄与箇所が callback レベルで初めて実測された。さらに **i915 の resume callback ~440ms の内側で wl の war が並走する**構造が確認され、hang 署名 B (i915 main entry) の「被害者説」に機序的な実体が与えられた。後半では恒久対策 (udev rule) がカーネル非依存であることを利用して **stock カーネルへ復帰**: 6.12.94+deb13 で hang 全条件 30 cycle をハングゼロで完走 (0/30、全 BT_PAN_VALID) した上で恒久化し、セキュリティ更新を再開して 6.12.95+deb13 へ更新、新カーネルでも udev rule と wl (dkms 自動ビルド) の動作を検収した。**dpmwd 計測カーネル系は今日で退役** (grub メニューには残置、ロールバック可)。

- **実施日時**: 2026年7月12日 03:20 〜 06:00 JST
- **位置づけ**: [C-7 Rung 3](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md) の引継ぎ 1 (機序 C-7 (iv)) と 2 (stock カーネル戻し) を同一セッションで実施

## 概要

前回までで、BT テザリング + VPN + WiFi オフ時の suspend ハングは「wl を配下に持つルートポート 00:1c.2 の sleep 中 D3hot 遷移」が必要条件であることまで確定し、udev rule による 1 ポート D0 固定を恒久対策として採用済みだった。残っていた最大の謎は「なぜ radio off がハングの必要条件なのか」である。runtime に観測できる設定差は前回までの O1/O2/O3 ですべて消去されており、suspend/resume 処理中の動的な挙動だけが残されていた。

今回はまず wl ドライバの中身に踏み込んだ。Debian ソース (broadcom-sta 6.30.223.271-26) のオープン部分を読み、本体のバイナリ blob も逆アセンブルして追ったところ、はっきりした構造が出てきた。wl は suspend のたびに「BCM4360 専用 PCIe workaround」の実行予約フラグをリセットし、resume のたびに wl_up 経由でこの workaround を 1 回実行する。workaround の中身は PMU の PLL 再プログラムで、実行前に PCIe config space を丸ごと退避することから、endpoint の PCIe コアを激しく擾乱する処理であることが分かる。つまり「復帰のたびに WiFi チップが自分のリンクを一度揺らす」動作が仕様として組み込まれていた。

次に実機で suspend/resume の callback 時間を 3 条件 (radio on / radio off / radio off+BT+VPN、いずれも保護あり) で計測した。radio off では wl の suspend callback が 9µs で即返り (チップは事前 down 済み)、resume callback は radio on の 54ms から 22ms へ短縮される。BT/VPN を足しても 22ms のまま変わらない。radio off の寄与は wl の resume 経路の分岐として固定的に現れることが実測で確定し、「workaround は走るが本初期化を中断する」radio off 特有の中途半端な up/down 経路が、壊れる側の経路として名指しできるようになった。もう一つの収穫として、i915 の resume callback (~440ms、全デバイス中最長) の内側でこの workaround が並走することも分かり、ハング時の pm_trace が i915 を指していた理由 (最後に main entry を書いたのが i915 だった) が構造として説明できた。

後半はカーネルの正常化である。恒久対策が udev rule というカーネル非依存の形になったため、計測用の自前カーネル (dpmwd4) を維持する理由がなくなっていた。stock 6.12.94+deb13 をワンショット起動で試験し、udev rule の自動適用と「00:1c.2 だけ D0 で sleep」を実測で確認した上で、ハング全条件 (BT+VPN+radio off) の lid 開閉 30 回をハングゼロで完走した。これを受けて default を stock に恒久化し、保留していたセキュリティ更新を再開。カーネル 6.12.95 が入り、dkms が wl を自動ビルドし、再起動後の新カーネルでも udev rule が機能することまで一気通貫で検収した。

これで実用上の問題はすべて解消された状態になった。残る未解明は「radio off の短縮経路が、無保護の親ポート D3hot 復帰を具体的にどうバスレベルで壊すか」の一点だが、これは無保護でハングを起こしながら観測する必要があり、今回はユーザ判断でスコープ外とした。常用は stock + udev rule の soak として継続する。

## 添付ファイル

- [実験プラン](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/plan.md)
- [A-2 ソース/blob 解析メモ (逆アセンブル抜粋含む)](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/a2-source-blob-analysis.md)
- [T1 トレース (radio on)](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/c8-t1-full.log) / [T2 (radio off)](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/c8-t2-full.log) / [T3 (radio off+BT+VPN)](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/c8-t3-full.log)
- [stock hang 検証の PRE/POST 台帳](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/c8-stock-hangtest-ledger.txt)
- [stock smoke の D-state 抜粋 (6.12.94 / 6.12.95)](attachment/2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored/c8-smoke-dstate-excerpts.txt)

## 前提・目的

- **背景**: [Rung 3](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md) で真犯人 00:1c.2 (wl 親) 確定、udev rule 恒久対策採用済み。引継ぎ課題 = (1) C-7 (iv) 機序 (radio off の動的寄与)、(2) stock カーネル戻し
- **目的**: (a) broadcom-sta ソース読解 (方法 B) で radio 依存分岐を特定、(b) 保護あり 3 条件トレースで callback 差を実測、(c) stock + udev rule の hang 検証を経て恒久化・セキュリティ更新再開
- **ユーザ決定** (プラン時): スコープ = 機序解明→stock 戻しの両方 / トレースは**保護ありのみ** (無保護 cycle の hang リスクは取らない) / 7/10 以降の soak は体感異常なし
- **役割分担**: ssh 操作・ソース解析・grub 操作 = Claude、lid 開閉・radio/BT/VPN 操作 = ユーザ

## 環境情報

- 実機: MacBook Air 11" (Early 2015) / Debian 13 (trixie)
- カーネル: セッション開始時 6.12.94-dpmwd4 → 終了時 **6.12.95+deb13-amd64 (stock、セキュリティ更新適用後)**
- cmdline: `quiet no_console_suspend mem_sleep_default=s2idle panic=15` (不変、pcie_port_pm=off なし)
- 恒久対策: `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` (03:00.0 → d3cold_allowed=0 = 00:1c.2 D0 固定)
- wl: broadcom-sta-dkms **6.30.223.271-26**、BT/VPN: iPad BT-PAN 172.20.10.13/28 + GSNet (SA peer 160.16.210.47)
- 解析対象ソース: `src/broadcom-sta-6.30.223.271/` (apt-get source、Debian パッチ 37 本適用済み)、blob = `amd64/lib/wlc_hybrid.o_shipped` (7.3MB、ローカルシンボル残存)

## Phase 0: soak 検収 (7/10 12:20 boot 〜 7/12 03:20)

- boot ID 単一 (再起動なし)、pstore 空、udev rule 適用継続 (d3cold_allowed=0)
- suspend 3 回 (11.0h / 1.1h / 24.8h) すべて PRE/POST ペア成立 = **hang 0/3**
- バッテリ区間 (7/11 00:56-02:03、1.12h) の待機電力 ≈ **1.2W** — Rung 3 実測 1.6W と同オーダー、異常なし
- ユーザ体感の異常なしと機械検収が一致

## 結果 1 (A-1/A-2): wl の suspend/resume 経路と「4360 PCIe2 war」の特定

ソース (wl_linux.c) と blob 逆アセンブルから確定した経路:

| タイミング | 処理 | 出典 |
|---|---|---|
| suspend (main 段) | `wl_suspend` → `wl_down()` (ガードなし無条件) + `hw_up=FALSE` → `si_pci_sleep()` | wl_linux.c:825-849 |
| `si_pci_sleep` の実効 | **`do_4360_pcie2_war = 0` (war 再アーム) のみ**。`pcicore_sleep` は PCIE core 0x820 rev3-5 専用で BCM4360 (Gen2 core 0x83c) では no-op | blob 0x1ecf6 / 0x19015 |
| resume (main 段) | `wl_resume` → 無条件 `wl_up()` → `wlc_up` → `wlc_bmac_hw_up` → **`wlc_bmac_4360_pcie2_war`** | wl_linux.c:857-885 + blob 0x65656 |
| war の中身 | chip 4360/4352/43602 限定、フラグ 0 のとき 1 回実行: PMU レジスタ確認 → **`si_pcie_configspace_cache()` (PCIe config space 退避)** → `si_pmu_pllcontrol` で PLL 再プログラム → 復元 | blob 0x65338 |

- **毎 resume で endpoint の PCIe コアを擾乱する処理が仕様として走る** (suspend でフラグがリセットされるため毎回)
- Linux では `wl_osl_pcie_rc` がスタブ (return 0、wl_linux.c:2117) = war は常に進行。wl が親ポートに直接触れる経路はない → 親への影響はリンク層経由で間接
- `WL_ERROR` は `BCMDBG_ERR` 未定義 (Makefile でコメントアウト) のため **wl は journal に一切出力しない** → 観測は callback 時間 (`PM: calling ... / returned ... after N usecs` 行) が主観測子。この行の出所は本機に既設の恒久 fixture `/etc/tmpfiles.d/pm_print_times.conf` (毎 boot `pm_print_times=1`) であり、pm_debug_messages ではない (本セッション中に判明、運用知見 7 参照)

## 結果 2 (A-3/A-4): radio on/off の callback 差を実測、署名 B の構造説明

dpmwd4 上、保護あり (d3cold_allowed=0)、各条件 2 cycle、journal マーカー C8-T1/T2/T3:

| wl callback | T1: radio on | T2: radio off | T3: radio off+BT+VPN |
|---|---|---|---|
| `pci_pm_suspend` (main) | 4937 / 1013 µs | **9 / 8 µs** | **9 / 20 µs** |
| `suspend_noirq` (D3hot 突入) | ~11.1 ms | ~11.0-11.4 ms | ~11.3-12.5 ms |
| `resume_noirq` (D0 復帰) | ~11.5 ms | ~11.4-11.9 ms | ~11.5 ms |
| **`pci_pm_resume` (main = wlc_up + war)** | **54.8 / 54.3 ms** | **22.4 / 22.3 ms** | **22.3 / 24.1 ms** |

1. **radio off の寄与は wl の main 段 callback に固定的に現れる**: suspend は即 return (`wl_down` が no-op = チップ事前 down 済みの直接証拠)、resume は 54ms→22ms の短縮経路。noirq 段 (D-state 遷移そのもの) は 3 条件で差がない
2. **T3 は T2 と同一シグネチャ** → BT/VPN は wl callback を変えない。b'' (radio off) の寄与は wl 層で完結し、BT/VPN の寄与は別の層 (resume 並行動作) にあることが分離できた
3. 22ms の解釈: war (PLL 再プログラム) は実行しつつ、radio blocked で本初期化 (PHY/radio init) を省略する中途半端な up 経路。「radio off だけがハングする」に対応する候補経路が実名で特定された
4. **署名 B の構造説明**: i915 の `pci_pm_resume` は **~443ms** で全デバイス中最長。async resume により i915 entry → +数ms 00:1c.2 → wl (war 実行 22-55ms) → i915 return の順で **wl の war が i915 の callback 窓の完全に内側で並走**する。この窓でバスレベルの死が起これば pm_trace の最終値は「i915 main entry」になる = C-5 以来の被害者説の実体。この構造は dpmwd4 の T1/T2/T3 だけでなく、**stock の smoke と hang 検証全 30 cycle でも毎回同一** (hang 条件下の wl resume は全 cycle 22.3-23.2ms = radio-off 短縮経路で一貫) を journal で確認した

## 結果 3 (Phase B): stock カーネル復帰 + セキュリティ更新再開

| 段階 | 内容 | 結果 |
|---|---|---|
| ワンショット試験 | `grub-reboot` で stock 6.12.94+deb13 起動 (default は dpmwd4 のまま) | 起動成功 |
| 検収 | udev rule 自動適用 (d3cold_allowed=0) / wl ロード (dkms ビルド済み) / s2idle / delay_cnt=300 / pstore 空 | 全項目良好 |
| smoke | WiFi lid cycle 1 回 + dynamic debug | **00:1c.2 = D0 で sleep** (1c.1/1c.5/TB は D3hot)。wl callback は dpmwd4 と同一シグネチャ (war は stock でも走る) |
| **hang 検証** | BT-PAN + VPN + radio off、lid cycle (追加摂動なし = 常用 soak と同条件。恒久 fixture の pm_print_times=1 と h4-probe hook 由来の pm_debug_messages=1 は歴代 cycle と共通) | **hang 0/30、全 30 BT_PAN_VALID、boot ID 単一、pstore 空** (台帳ペア判定済み、長休憩 1 回 430s ペアを含む) |
| 恒久化 | `grub-set-default` → stock、`GRUB_DEFAULT=saved→0` へ戻し (新カーネル自動起動) | grubenv / grub 検収済み |
| 更新再開 | `apt-get upgrade` + `dist-upgrade` で全セキュリティ更新 + **linux-image 6.12.95-1** | **dkms が wl を 6.12.95 用に自動ビルド** |
| 6.12.95 検収 | 再起動 → udev rule 自動適用 → smoke 1 cycle | **00:1c.2 = D0 で sleep** = 更新再開の e2e 完結 |

- 統計: stock + udev rule arm は **hang 0/30** — 無保護ベースライン 9/24 ≈ 38% に対し Fisher 片側 p ≈ 1.7×10⁻⁴ (ただしベースラインは dpmwd4+pm_trace 摂動 arm、非摂動 stock とは arm tag を分離して扱う)
- **dpmwd1-4 は退役** (grub メニュー・/boot に残置、ロールバック = メニュー選択のみ)。セキュリティ更新は通常運用に復帰

## 解釈

1. **C-7 (iv) は「半解明」まで前進**: radio off の寄与は「wl resume の短縮経路 (war 実行 + 本初期化中断)」として callback レベルで実名化された。ただし、それが無保護の親 D3hot 復帰をバスレベルでどう壊すかは未観測 (無保護トレースが必要、今回スコープ外)
2. **機序の絵の現在形**: 「resume のたびに wl は PLL 再プログラムで自リンクを揺らす。radio on ならフル初期化で正常に収束する。radio off だと中途半端な up/down 経路になり、親 00:1c.2 が D3hot から復帰する過渡 (かつ i915 の 440ms callback と並走する混雑した窓) と重なったとき、まれにバスレベルの静かな死に至る。BT/VPN は wl 層ではなくこの窓の並行動作側に寄与する」
3. **署名 B は最後まで被害者だった**: 逆説的だが、i915 が指名された理由は「一番長い callback の内側で事故が起きるから」という時間構造であり、i915 自体の関与を示すものではなかった
4. **恒久対策の設計勝ち**: udev rule (カーネル非依存) にしておいたことで、stock 復帰もカーネル更新も対策に触れずに通った。今後のカーネル更新でも rule はそのまま機能する

## 次セッション引継ぎ

1. **非摂動 soak 継続 (stock 6.12.95 + udev rule)**: BT+VPN+radio-off 解禁のまま常用。ウォッチリスト: (i) hang 再発 (0/30+0/37 の反例 = 一級データ)、(ii) 原因不明の再起動、(iii) 待機電力の体感 (4%/h 想定)。**stock には dpm watchdog も pm_trace もない**ため、hang 時は発生条件の記録が主 (5 分放置 → 電源長押し → 報告)
2. **機序の残り (任意、優先度低)**: 無保護 (d3cold_allowed=1 に一時復帰) + radio off + BT/VPN のトレース採取。hang 率 ~38% を引き受ける判断が必要。dpmwd4 が grub に残っているので pm_trace decode 込みの再演も可能
3. **クリーンアップ候補 (任意)**: `apt autoremove` (旧カーネル 6.12.73-90 の image/headers 多数)、旧 hold (linux-image-6.12.74) の整理、dpmwd1-3 の /boot からの削除 (dpmwd4 は当面残置推奨)
4. **統計の注意**: stock+udev rule の 0/30 は新 arm tag として分離集計。歴代 pool と合算しない

## 残置物 (実機の現状、7/12 06:00 JST)

| 項目 | 状態 |
|---|---|
| kernel | **6.12.95+deb13-amd64 (stock、稼働中)**。6.12.94+deb13 / dpmwd1-4 残置 |
| grub | `GRUB_DEFAULT=0` (最新カーネル自動起動、バックアップ `/etc/default/grub.bak-c8` = saved 時代)。saved_entry は stock 6.12.94 を指すが DEFAULT=0 のため未使用 |
| udev rule | `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` 不変・機能中 (6.12.95 で検収済み) |
| セキュリティ更新 | **再開済み** (7/12 適用完了)。hold は libnm0/network-manager (broadcomfix、意図的) と旧 6.12.74 のみ |
| 観測系 | dynamic debug 無効、sysctl panic 系 = 0、pm_trace なし (stock)。**恒久 fixture: pm_print_times=1 (tmpfiles.d) + pm_debug_messages=1 (h4-probe hook が毎 suspend 再有効化)** = 歴代 soak と同条件 |
| pstore | 空 |
| /var/log/h4-probe | C8 マーカー群 (C8-T1/T2/T3-START、C8-STOCK-*)、PRE/POST 台帳継続。**削除しないこと** |
| 開発機 src/ | broadcom-sta-6.30.223.271/ (解析済み、コミット対象外) |

## 再現方法

```bash
# 1) ソース取得と blob 解析 (開発機)
cd src && apt-get source broadcom-sta-dkms=6.30.223.271-26
cd broadcom-sta-6.30.223.271/amd64
objdump -dr lib/wlc_hybrid.o_shipped > /tmp/wlc.disas
grep -n "do_4360_pcie2_war\|wlc_bmac_4360_pcie2_war\|si_pci_sleep" /tmp/wlc.disas
# → si_pci_sleep (0x1ecf6) が do_4360_pcie2_war=0、wlc_bmac_hw_up (0x65656) が war (0x65338) を呼ぶ

# 2) callback トレース (実機、保護あり、hang リスクなし)
echo 1 | sudo tee /sys/power/pm_print_times           # callback 時間行の本体 (本機は tmpfiles.d で常時 1)
echo 1 | sudo tee /sys/power/pm_debug_messages        # 補助 (注: /sys/kernel/debug/ ではない)
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
logger "T1-START"  # 各条件 (radio on / off / off+BT+VPN) で lid cycle 2 回
journalctl -b 0 -o short-precise | awk '/T1-START/{f=1} f' | \
  grep -E "0000:03:00\.0|0000:00:1c\.2" | grep -E "calling|returned|Suspend power state"

# 3) stock 切替 (ワンショット試験 → 恒久化)
sudo grub-reboot "gnulinux-advanced-<UUID>>gnulinux-6.12.94+deb13-amd64-advanced-<UUID>"
sudo sync && sudo reboot
# 検収後:
sudo grub-set-default "<同エントリ>" && sudo sync
sudo sed -i "s/^GRUB_DEFAULT=saved/GRUB_DEFAULT=0/" /etc/default/grub
sudo update-grub && sudo sync

# 4) セキュリティ更新再開
sudo apt-get -y upgrade && sudo apt-get -y dist-upgrade   # 新カーネルは dist-upgrade 側
sudo /usr/sbin/dkms status | grep 6.12.95                 # wl 自動ビルド確認
sudo reboot  # → d3cold_allowed=0 と smoke で検収
```

## 運用知見 (C-8 で新たに確定した事項)

1. **pm_debug_messages のパスは `/sys/power/pm_debug_messages`** (debugfs 側ではない。debugfs パスへの sudo tee は EACCES で失敗する)
2. **カーネル metapackage の更新は `apt-get upgrade` では入らない** (新規パッケージ依存のため「保留」になる)。`dist-upgrade` が必要
3. **`grub-reboot` (next_entry) はワンショット試験に安全**: 電源断でも次回は saved/default 側で起動。恒久化は別途 grub-set-default または GRUB_DEFAULT=0
4. **wl は journal に一切ログを出さない** (BCMDBG_ERR 無効ビルド)。wl の挙動観測は callback 時間・順序 (pm_print_times、知見 7) が実質唯一の非侵襲観測子
5. **blob 解析は objdump -dr で十分実用**: broadcom-sta の blob はローカルシンボルが残っており、リロケーション名 (do_4360_pcie2_war 等) から意味が読める。brcmsmac (オープン) の同名関数と突き合わせると解釈が速い
6. PRE/POST ペア判定の時間窓は休憩を考慮する (今回 300s 窓で 430s sleep を一度 unpaired と誤判定しかけた。boot ID 単一 + POST 総数一致で相互確認する)
7. **callback 時間行 (`PM: calling ... / returned ... after N usecs`) の出所は `pm_print_times=1`** であり、`/etc/tmpfiles.d/pm_print_times.conf` が毎 boot 恒久適用している (過去フェーズの残置 fixture)。また **`70-h4-probe` hook が毎 suspend で `pm_debug_messages=1` を再有効化**するため、手動で 0 にしても次の suspend で戻る。つまり本機の「非摂動」の実体は「pm_print_times + pm_debug_messages 常時オン」であり、歴代 soak・全 arm がこの同条件下にある (統計の扱いは不変、記述上の正確化)

## 参照レポート

- [2026-07-10_122213 Phase C-7 Rung 3: 真犯人 00:1c.2 確定・udev rule 恒久化 (本セッションの引継ぎ元)](2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md)
- [2026-07-09_205237 Phase C-7 Rung 2: 副観測 O1/O2 (radio on/off で D-state 同一)](2026-07-09_205237_phase_c7_rung2_nontb_rootport_d0_hang_eliminated_0of30.md)
- [2026-07-06_002651 Phase C-5: 署名 B (i915 main entry) の初出](2026-07-06_002651_dpmwd4_phase_c5_stall_devices_named_tb_bridge_and_i915_all_pre_markers.md)
- [2026-07-02_103415 必要条件 b'' (wl loaded + radio off) の bedrock](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
