# S3 スリープ再挑戦 — lid open 復帰は復活できる (ただし wl unload が条件)

- **実施日時**: 2026年7月13日 03:16〜17:55 (JST、05:55〜13:58 は Phase 4 自動計測、17:29〜 Phase 5 恒久化)
- **執筆者**: Claude Fable 5
- **対象機**: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / kernel 6.12.95+deb13-amd64 (stock)

## 概要

この MacBook は長らく「スリープからの復帰は電源ボタンを押すしかない」状態だった。いま使っているスリープ方式 (s2idle) では、蓋を開けたことを知らせる信号がマシンに届かないためである。蓋を開けるだけで復帰する昔ながらの動作は、より深いスリープ方式である S3 でしか実現できない。その S3 は 6 月末に「眠ったまま二度と起きなくなる事故 (ハング) が避けられない」という理由で断念した経緯がある。しかし 7 月に入ってハングの根本原因が突き止められ、対策も入った。原因が分かった今なら S3 を安全に使えるのではないか — それを確かめるのが今回の再挑戦である。

結果からいえば、蓋開け復帰は取り戻せた。今日一日の検証で、蓋を開けるだけの復帰を 38 回試してすべて成功し、失敗は一度もなかった。ただし道のりは想定と少し違った。s2idle で完璧に効いていたハング対策が、S3 ではまったく効かなかったのである。負荷の強い条件で試すとすぐにハングが再発した。S3 は眠りに入るとき周辺装置の電源を根こそぎ切ってしまうため、「電源を切らせないことでハングを防ぐ」という対策の前提そのものが成り立たない、というのが理由だと考えている。

そこで別の手を試した。これまでの調査で、ハングは「無線 LAN のドライバが読み込まれたまま、かつ無線をオフにしている」ときにしか起きないと分かっている。ならば眠る直前にドライバごと外してしまえばよい。実際にそうして同じ負荷条件で 21 回試したところ、ハングは一度も起きなかった。ドライバを外したままだった場合との差は統計的にも有意で、「眠る前に無線 LAN ドライバを外す」ことが S3 を安全に使うための鍵だと確定した。

一つだけ残った制約がバッテリ駆動時の挙動である。この機体のファームウェアには、バッテリ駆動で蓋開け復帰を有効にしたまま眠ると、蓋に触れていないのに 6 秒で勝手に起きてしまう癖があり、これは今も変わっていなかった。誤起床と蓋開け復帰は同じ信号を使っているため選り分けられない。そこで「AC 接続中は蓋開け復帰を有効に、バッテリ駆動では従来どおり電源ボタンで復帰」という自動切替で折り合いをつけた。

うれしい副産物もあった。スリープ中の消費電力を一晩かけて計測したところ、S3 は現行構成の約 17 分の 1 しか電気を食わないことが分かった。蓋を閉じたまま一晩放置してもバッテリはほとんど減らない。

ユーザの採用判断を受けて、同日中に恒久設定まで済ませた。眠る前に無線 LAN ドライバを外す仕掛け、バッテリ時だけ蓋開け復帰を止める仕掛け、起動時に S3 を選ぶ仕掛けの 3 点で、いずれも簡単に元へ戻せる作りにしてある。AC・バッテリ両方の実地確認と再起動後の確認まで通し、本機は今日から「AC につないでいれば蓋を開けるだけで起きる」マシンに戻った。代償は復帰のたびに WiFi の再接続へ数秒かかることだけである。今後 1〜2 週間ふだん通り使って問題が出なければ、正式採用として仕上げる。

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

## Phase 5: 恒久化 (実施済み、17:29〜17:52 JST)

ユーザ採用判断を受け、以下 3 点を実機に配置した (すべて可逆、**GRUB は s2idle 据置のまま**)。

| 新設物 | 役割 | ロールバック |
|---|---|---|
| `/usr/lib/systemd/system-sleep/45-wl-unload` | pre で `modprobe -r wl` (10s timeout)、post で reload。常時 unload (radio 状態の条件分岐なし = 安全側)。フラグ `/run/wl-unloaded`、ログ `/var/log/wl-unload.log` | `rm` 一発 |
| `/usr/lib/systemd/system-sleep/46-lid0-ac-policy` | pre で「battery かつ LID0 enabled」のときのみ凍結、post で復元。ガード付きトグル。フラグ `/run/lid0-frozen`、ログ `/var/log/lid0-ac-policy.log` | `rm` 一発 |
| `s3-deep-select.service` + `/usr/local/sbin/s3-deep-select.sh` | 起動時に `mem_sleep=deep` を選択する oneshot (LID0 には触らない = 旧 s3-deep-apply との違い)。BOOT-DEEP マーカーを s3-soak.log に記録 | `systemctl disable` + 再起動 |

**検証結果 (全 green)**:
- **Test A (AC lid wake ×2)**: LID0 no-op (enabled 維持)、lid open で即復帰 (gpe70 +1 ずつ)、wl unload/reload 動作。
- **Test B (バッテリ ×1)**: type=suspend-then-hibernate 経路でフック発火、**LID0 凍結 → 50 秒 hold (6 秒 spurious なし・gpe70 凍結) → 電源ボタン復帰 → LID0 自動復元**。
- **WiFi 再接続**: resume → wl reload → NM activated (assoc+DHCP 完了) まで**約 5 秒** (17:39:37 → 17:39:42)。
- **再起動 e2e**: reboot 後に deep 自動選択 (BOOT-DEEP、新 boot_id)、service active、udev 保護・LID0 enabled・フック残存 → 初 lid cycle も wl unload/reload・gpe70 wake・drm_err=0 で完走。
- 副観測: STH 経路 (`pre(suspend-then-hibernate)`) でも両フックが正しく発火する。

## 実機の最終状態

- **常用構成 = S3 (deep) + udev 保護 + 45-wl-unload + 46-lid0-ac-policy + s3-deep-select.service (enabled)**
- GRUB: `mem_sleep_default=s2idle` 据置 (フェイルセーフ: service を disable して再起動すれば s2idle)
- 旧 `s3-deep-apply.service`: disabled のまま残置 (**enable 禁止** — LID0 無条件凍結の旧仕様。soak 通過後に削除推奨)
- watcher (cycle-watch-s3r / vpn-watch-s3r / bus-watch-c9) 停止済み。marker/ログは /var/log/h4-probe/ に残置

## 今後 (soak と残課題)

1. **常用 soak 1〜2 週間** (全条件解禁)。ウォッチリスト: (i) hang 再発 (wl unload 下では初の反例 = 一級データ。5 分放置 → 長押し → 報告)、(ii) `wl-unload.log` の FAILED 行 (unload/reload 失敗 → WiFi 不通の形で顕在化)、(iii) バッテリ spurious wake (lid0-ac-policy の取りこぼし、s3-soak.log の asleep_s で判別)、(iv) 待機電力の体感 (モバイル解禁可否)。
2. soak 通過後: **GRUB `mem_sleep_default=deep` 化** (二段構えの本採用) + 旧 s3-deep-apply 削除などのクリーンアップ。
3. 残課題 (優先度低): S3 hang の停止点実名 (dpmwd4+pm_trace で decode 可能。S3 は syscore/pm_trace 本来の土俵なので s2idle より素直に取れる見込み)、edge case「バッテリで suspend 中に AC を挿しても次の resume まで lid wake は無効のまま」(仕様として許容)。

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
