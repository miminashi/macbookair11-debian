# Phase C-8: 機序解明 (C-7 (iv)) + stock カーネル戻し

## Context

[Rung 3 レポート (2026-07-10_122213)](../projects/macbookair11-debian/report/2026-07-10_122213_phase_c7_rung3_culprit_confirmed_wl_rootport_udev_permanent_fix.md) で真犯人 00:1c.2 (wl 親ポート) が確定し、udev rule (`99-c7r3-wl-d3cold.rules`) による恒久対策が採用済み。残課題は:

1. **C-7 (iv) 機序**: radio off が 00:1c.2 の D3hot 復帰を壊す動的機序 (O1/O2/O3 で runtime 設定差は全消去済み → suspend/resume 中の動的挙動に限定)
2. **stock カーネル戻し**: 恒久対策がカーネル非依存になったため、dpmwd4 → stock 6.12.94 へ戻してセキュリティ更新を再開する条件が整った

ユーザ決定 (AskUserQuestion 済み):
- **スコープ = 両方** (機序解明を dpmwd4 残存中に先に実施 → その後 stock 切替検証)
- **トレースは保護ありのみ** (d3cold_allowed=0 のまま。無保護 cycle での hang リスクは取らない)
- 7/10 以降の非摂動 soak は**体感異常なし** (セッション冒頭に機械検収する)

## 前提

- 操作対象は ssh 先 `miminashi@macbookair2015.lan` (sudo NOPASSWd)。**セッション開始時に `/sandbox` でサンドボックス一時無効化をユーザに依頼** (LAN 経路確保)
- ユーザの立ち会いが必要な操作: lid 開閉、radio on/off (detached systemd-run パターンで自動復帰可)、BT-PAN テザリング、再起動立ち会い
- 現状: kernel 6.12.94-dpmwd4 (saved default)、cmdline に pcie_port_pm=off なし、udev rule 適用中、pm_trace/sysctl panic 系すべて平常 (0)

## Phase 0: soak 検収 (機械確認)

7/10 12:25 以降の非摂動 soak をレポート用に記録:

- boot ID 履歴 (`journalctl --list-boots`) で原因不明の再起動がないこと
- pstore 空、`/var/log/h4-probe` の PRE/POST ペアで unpaired (hang) ゼロ
- `d3cold_allowed` = 0 (03:00.0)、udev rule 現存、`uname -r` = dpmwd4
- `/var/log/s3-soak.log` から suspend 回数・待機電力の傾向 (4%/h 想定との乖差)

## Phase A: 機序解明 C-7 (iv) — 保護あり callback トレース比較

### A-1. broadcom-sta ソース取得 (方法 B) — 開発機、実機不要

1. 実機の導入版確認: `ssh ... 'dpkg-query -W -f="${Version}\n" broadcom-sta-dkms'`
2. 開発機 `src/` で `apt-get source broadcom-sta-dkms=<版>` (deb-src 不可なら実機側で取得して scp、または sources.debian.org)

### A-2. ソース読解 — suspend/resume 経路の radio 依存分岐を特定

- `src/broadcom-sta-*/` の `wl_linux.c` 等から PCI suspend/resume callback (`wl_suspend`/`wl_resume` 系) を読む
- 着目点: **radio off (WLC_DOWN / mpc) 状態で suspend/resume 時に何を省略・追加するか** — chip down 済みだと resume で再初期化をスキップする、PCI config save/restore の条件分岐、PME/D3 まわりの直接レジスタ操作、親ポートのリンクに影響する処理 (リンク無効化・clkreq 等)
- 成果物: 「radio on/off で実行パスがどう分かれるか」の経路図 (A-3 のトレース解釈に使う)

### A-3. 実機トレース採取 — 3 arm × 各 1〜2 cycle (保護あり、hang リスクなし)

観測系 (すべて揮発、cycle 後に戻す):

```bash
echo 1 | sudo tee /sys/kernel/debug/pm_debug_messages   # per-callback trace
echo "file drivers/pci/pci-driver.c +p" | sudo tee /sys/kernel/debug/dynamic_debug/control
echo "file drivers/pci/pci-acpi.c +p"   | sudo tee /sys/kernel/debug/dynamic_debug/control
# 必要なら drivers/pci/pcie/aspm.c +p も追加
```

| arm | 条件 | 目的 |
|---|---|---|
| T1 | WiFi radio **on** (通常) | 正常系ベースライン |
| T2 | radio **off** (BT/VPN なし) | 必要条件 b'' の最小形。radio off は detached systemd-run で自動復帰 (R3 レポート「再現方法」2 のパターン) |
| T3 | radio off + BT-PAN + VPN | hang 全条件 (保護ありなので安全)。差が T2 で出なければこちらが本命 |

各 cycle 後に journal から抽出・比較:

- wl (03:00.0) / 00:1c.2 の suspend・resume callback の**呼び出し順・所要時間** (`calling ... @ / ... returned 0 after N usecs`)
- D-state 遷移行 (`PCI PM: Suspend power state` / `power state changed by ACPI`) — 00:1c.2 は D0 のままのはず (保護あり)、wl 自身は D3hot
- resume 側: config restore、link retrain / AER / ASPM 関連メッセージの有無・タイミング差

### A-4. 分析・判定

- radio on/off で wl callback の挙動差 (時間・順序・スキップ) が**見えるか**が判定点
- 見える → A-2 のソース経路と突き合わせて機序仮説を具体化 (例: 「radio off だと resume callback が X を省略し、親ポートの D3hot 復帰時のリンク再訓練と競合する」)
- 見えない → 「保護あり観測では差は D-state 遷移そのものに隠れる」と記録し、無保護観測 (hang リスクあり) を次回候補として引継ぎ。**本セッションでは無保護に進まない (ユーザ決定)**

## Phase B: stock カーネル戻し

dpmwd4 の役目 (watchdog / pm_trace) は Phase A 終了で完了。以後は udev rule だけで hang 抑止が成立するはず (カーネル非依存) — これを実証する。

1. **事前確認**: /boot に stock `6.12.94` イメージ現存、grub メニューエントリ確認、`intel_pch_thermal` の delay_cnt=300 が modprobe.d 側にあること (カーネル非依存で stock にも効く)、hooks 5 本残置
2. **ワンショット起動で試験**: `grub-reboot '<stock エントリ>'` → 再起動 (恒久 default はまだ dpmwd4 のまま = 電源断でも安全側)
3. **検収 (stock 上)**: `uname -r` = stock / udev rule により d3cold_allowed=0 自動適用 / pstore 系・hooks 動作 / **smoke: WiFi lid cycle 1-2 回 + dynamic debug で「00:1c.2 = D0 のまま sleep」を stock でも実測**
4. **hang 検証 (非摂動でよい、R3 引継ぎ 2 の指定どおり)**: BT-PAN + VPN + radio off で lid cycle を可能な範囲で数回〜 (ユーザ都合に合わせる。0/10 級でも「stock + udev rule の初回検証」として価値あり。本格統計は以後の常用 soak で蓄積)
5. **問題なければ恒久化**: `grub-set-default` を stock へ (saved default 切替 + `sync`)。**dpmwd4 は /boot に残置** (ロールバック = saved default を戻すだけ)
6. **セキュリティ更新再開**: linux-image の hold/pin 有無を確認して解除、`apt update && apt upgrade` の適用方針をユーザに提示 (カーネル更新が来た場合も udev rule は継続機能)
7. **stock soak 移行**: BT+VPN+radio-off 解禁のまま常用継続。ウォッチリスト従来どおり (hang 再発 / 不明再起動 / 電力)

問題が出た場合: ワンショット起動なので再起動だけで dpmwd4 に戻る。stock 固有の問題 (udev rule 不適用等) はその場で調査し、恒久化を見送って報告。

## Phase C: レポート作成

- `report/yyyy-mm-dd_hhmmss_<英語名>.md` (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)
- 概要は平易な日本語の段落 5 本目安、前提・環境情報・再現方法・引継ぎを含める
- 本プランファイルを `report/attachment/<レポート名>/plan.md` にコピーし「添付ファイル」セクションからリンク
- トレース生ログ・diff・broadcom-sta 該当コード断片も添付に格納
- 統計注意: stock + udev rule の cycle は新 arm tag として分離集計

## 検証 (このセッションの完了条件)

1. Phase 0 の soak 検収結果が記録されている
2. A-3 の 3 arm トレースが採取され、radio on/off の callback 差の有無が判定されている (A-2 のソース経路と突き合わせ済み)
3. 実機が stock 6.12.94 + udev rule で稼働し、smoke で 00:1c.2 D0 固定を実測済み、saved default 恒久化済み (または見送り理由が記録されている)
4. レポート + 添付一式がコミット可能な状態

## 役割分担

- Claude: ssh 操作全般、観測系 arm/disarm、ログ解析、ソース読解、grub 操作、レポート
- ユーザ: /sandbox 切替、lid 開閉、radio off (detached unit 起動は Claude、物理確認はユーザ)、BT-PAN テザリング・VPN 再確立、再起動立ち会い
