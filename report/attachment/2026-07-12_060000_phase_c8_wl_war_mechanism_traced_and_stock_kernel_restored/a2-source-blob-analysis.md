# A-2 broadcom-sta 6.30.223.271-26 ソース読解メモ (2026-07-12)

## 取得
- src/broadcom-sta-6.30.223.271/ (apt-get source、Debian パッチ 37 本適用済み)
- オープン部分: amd64/src/wl/sys/wl_linux.c (OSL glue)。本体は lib/wlc_hybrid.o_shipped (バイナリ blob、7.3MB、シンボルは残存 4091 個)

## suspend/resume 経路 (wl_linux.c)
- wl_suspend (wl_linux.c:825, SIMPLE_DEV_PM_OPS = main 段 .suspend):
  - WL_ERROR("PCI Suspend handler") ※不可視 (下記)
  - WOWL 非対応なら wl_down(wl) + wl->pub->hw_up = FALSE  (wl_linux.c:841-842)
  - si_pci_sleep(sih)  (wl_linux.c:846-847)
- wl_resume (wl_linux.c:857): 無条件 wl_up(wl)  (wl_linux.c:881)
- wl_up (wl_linux.c:1455): if (pub->up) return 0; → wlc_up(blob)
- wl_down (wl_linux.c:1476): ガードなし無条件 (netif_down → wlc_down(blob) → callbacks SPINWAIT)
- WL_ERROR は BCMDBG_ERR 未定義で no-op (Makefile:149 で `#EXTRA_CFLAGS += -DBCMDBG_ASSERT -DBCMDBG_ERR` コメントアウト) → **wl は journal に一切出力しない**

## blob 逆アセンブル (objdump -dr lib/wlc_hybrid.o_shipped)
- si_pci_sleep (0x1ecf6):
  ```
  do_4360_pcie2_war = 0;      // ← グローバルフラグを毎 suspend でリセット (war 再アーム)
  pcicore_sleep(sii->pch);
  ```
- pcicore_sleep (0x19015): PCIE core id 0x820 かつ corerev 3-5 のみ LinkControl bit1 (ASPM L1 enable) を config write でクリア。**BCM4360 は PCIe Gen2 core (0x83c) なので no-op** → 本機での si_pci_sleep の実効 = war フラグリセットのみ
- wlc_bmac_4360_pcie2_war (0x65338, brcmsmac 非公開の hybrid 独自 war):
  - 対象 chip: 0xa9c4 (43602) / 0x4360 / 0x4352、chiprev<=2、PCI bus
  - wl_osl_pcie_rc(wl,0,0)==1 なら skip → Linux ではスタブ return 0 (wl_linux.c:2117) = **常に進行**
  - ガード: do_4360_pcie2_war != 0 なら skip。実行時に =1 セット (1 回だけ実行、次の suspend で再アーム)
  - 中身: si_corereg(chipc 0x120/0x124=pmu chipcontrol addr/data) 読み、フィールド==2 なら skip、
    それ以外: **si_pcie_configspace_cache()** → si_pmu_pllcontrol(reg10, 分周値...) PLL 再プログラム
    → osl_delay → si_corereg... (以降 config space restore を含むはず)
  - **PCIe config space の退避/復元を伴う = endpoint PCIe コアへの破壊的操作**
- 呼び出し元: wlc_bmac_hw_up (0x65656) のみ (chip 4360/4352/43602 のとき)
  → 経路: wl_resume → wl_up → wlc_up → wlc_bmac_hw_up (hw_up==FALSE のとき) → war
- si_pcie_configspace_get/cache/restore は 0x83c (PCIe Gen2) / 0x820 両対応 (0x1ed12-)

## 本機での毎 suspend/resume サイクルの実効 (radio 状態不問)
1. suspend (main 段): wl_down + hw_up=FALSE + war 再アーム
2. resume (main 段, async): wl_up → wlc_bmac_hw_up → **4360 PCIe2 war = PLL 再プログラム + config space 退避/復元が毎回走る**

## radio on/off の差 (仮説、A-3 で検証)
- radio ON: suspend 時 pub->up=TRUE → wl_down がフル teardown。resume 時 wlc_up がフル up (PHY/radio init 完走)
- radio OFF: chip は事前 down 済み (+mpc で更に深い省電力状態の可能性)。suspend 時 wl_down は 2 度目 (ほぼ no-op)。
  resume 時 wlc_up は war 実行後に radio disabled で短縮/中断経路 (blob 内、mpc down 戻し?) の可能性
- 観測子: pm_debug_messages の 03:00.0 callback 所要時間 (suspend/resume 両側) の radio on/off 差
- 機序仮説 (現時点の最有力): radio off で chip 内部 (PLL/クロック, mpc) が深い状態のまま親 00:1c.2 が D3hot に入り、
  resume 側の L1 exit / link 応答性が radio on 時と異なる → 親 D3hot 復帰と wl resume war の PCIe 擾乱の相互作用。
  wl は Linux では親ポートに直接触れない (wl_osl_pcie_rc スタブ) → 寄与はリンク層経由で間接

## dkms 版数 (実機)
- broadcom-sta-dkms 6.30.223.271-26、stock 6.12.94+deb13-amd64 用ビルド済み (Phase B で追加ビルド不要)

## A-3/A-4 トレース結果 (2026-07-12 04:15-04:27 JST、全て保護あり d3cold_allowed=0)
- 観測: pm_debug_messages=1 + dynamic debug (pci-driver.c:910 / pci-acpi.c:1108 系)。各 arm 2 cycle、journal マーカー C8-T1/T2/T3-START
- T1 radio on:  wl suspend(main) 4937/1013 µs、suspend_noirq ~11.1ms、resume_noirq ~11.5ms、resume(main) 54849/54275 µs
- T2 radio off: wl suspend(main) 9/8 µs、noirq 両側 ~11ms (T1 と同)、resume(main) 22391/22329 µs
- T3 radio off+BT-PAN+VPN: wl suspend(main) 9/20 µs、resume(main) 22301/24070 µs = **T2 と同一シグネチャ**
- 判定: radio off の差は wl の main 段 callback に固定的に現れる (suspend 即 return = wl_down no-op / resume 54ms→22ms の短縮経路)。BT/VPN は wl callback を変えない
- **署名 B の機序的説明**: i915 の pci_pm_resume(main) は ~440ms (最長)。async resume で wl の resume(main) = 4360 war 実行はこの窓の完全に内側で並走 (i915 entry → +10ms 1c.2 → wl 22-55ms → i915 return 441ms)。この窓でバスレベル死 → pm_trace 最終値 = i915 main entry = 被害者説の実体
- 残る未解明 (無保護観測が必要、今回スコープ外): 無保護 (親 D3hot) + radio off + BT/VPN で war の PCIe 擾乱が親の D3hot 復帰をどう壊すかのバスレベル詳細
- ログ: scratchpad/c8-logs/c8-t{1,2,3}-full.log (レポート添付用)

## 訂正 (セッション終盤に判明)
- 上記「pm_debug_messages の callback 所要時間」の帰属は不正確: callback 時間行 (PM: calling/returned) の出所は
  pm_print_times=1 (/etc/tmpfiles.d/pm_print_times.conf で毎 boot 恒久適用の既設 fixture)。
  また 70-h4-probe hook が毎 suspend で pm_debug_messages=1 を再有効化する。詳細はレポート本文の運用知見 7。
