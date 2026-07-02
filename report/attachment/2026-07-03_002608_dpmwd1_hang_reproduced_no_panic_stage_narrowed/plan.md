# S4: DPM_WATCHDOG 自前カーネルで dpm_suspend の stall device をカーネル自身に自白させる

## Context

- 103415 セッションで (b'')「wl loaded かつ radio-off が hang の必要条件」が Fisher p ≈ 0.024 で bedrock 化したが、**hang の中身 (dpm_suspend でどのドライバが止まるか) はブラックボックスのまま**。H7 (any-perturbation-helps) も未排除。
- 方法論監査 (092013) は「snapshot 系 gate の精緻化は限界収穫逓減 (102907 で hang 直前 snapshot が正常時と identical と実証済)、**S4 (DPM_WATCHDOG) + pstore が機序決着の唯一の出口**」と指摘。ユーザもこれを選択。
- (ii)/(iii) の discriminate 実験より S4 を先行させる根拠: S4 は「以後発生する**すべての** hang が driver 名+device 名入りの panic として自己申告する」複利投資であり、監査推奨 #1 (base rate 確定) / #2 (battery セル) の実験も S4 カーネル上で回せば全 hang が自己診断つきになる。Phase C の再現セッション自体が hang arm の base rate 蓄積にもなる。

### 事前検証で確定した事実 (本プラン策定時に確認済)

- 実機 config: `PM_DEBUG=y` / `EXPERT=y` / `PSTORE=y` → `DPM_WATCHDOG` の依存 (`PM_DEBUG && PSTORE && EXPERT`) は充足。config 変更のみで有効化可
- `dpm_watchdog_handler` (src/linux-6.12.y `drivers/base/power/main.c:512-520`) は `dev_emerg` + stuck task の `show_stack` + **`panic("%s %s: unrecoverable failure", dev_driver_string, dev_name)`** → panic メッセージ自体に driver 名+device 名が刻まれ pstore に残る
- watchdog は `device_suspend` と `device_resume` の両方に設置 → **α/β (入眠側/復帰側) 判別も同時に解決**。ただし suspend_late/noirq/PM_SUSPEND_PREPARE notifier は非カバー (解釈ルールを Phase C に定義)
- efi_pstore は実機で registered 済 (041006) だが**実 panic の end-to-end 検証は未実施** → Phase B のゲート (b) で sysrq crash テスト必須
- src/linux-6.12.y = v6.12.94 ちょうど (クリーン)。Debian パッチ 97 本 (src/debian-6.12.94-1/debian/patches) は **series 順なら全本適用可** (dry-run 済; strict 失敗 5 本は全て series 内の直前パッチへの連鎖依存)
- 開発機: Debian 13 / 12 コア / 32GB / 113GB 空き / ccache あり。**`libelf-dev` のみ未インストール** (objtool に必須)
- 実機 config で `DETECT_HUNG_TASK=y` / `DEFAULT_HUNG_TASK_TIMEOUT=120` を確認済 → `kernel.hung_task_panic=1` は sysctl だけで有効化可。発火は最大 ~240 秒後 (timeout 120s + 検査周期)
- pstore backend 名は `KBUILD_MODNAME` = `efi_pstore` (ゲート (a) の期待値)。`/proc/sysrq-trigger` への書き込みは `kernel.sysrq` マスクをバイパスするため crash テストに sysctl 変更は不要
- 実機 config は `CONFIG_LOCALVERSION=""` (stock の `+deb13-amd64` は Debian ビルドシステムの env 由来) → `--set-str LOCALVERSION "-dpmwd1"` と衝突しない
- Plan agent レビューで判明した罠 (下記手順に反映済):
  - **`make bindeb-pkg` はツリー内 `debian/` を `rm -rf` する** (`scripts/package/mkdebian:125`) → debian/ コピー+quilt 直当ては不可、`git quiltimport` でコミット化する
  - quilt 適用のままだと dirty tree で localversion に `+` が付き `6.12.94-dpmwd1+` になる → quiltimport で解消
  - DEBUG_INFO 無効化は `--disable DEBUG_INFO` では効かない → `-d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT -e DEBUG_INFO_NONE`
  - 実機 /boot/config には `SYSTEM_TRUSTED_KEYS` 等の行が最初から存在しない (Debian の rules.real が除去) → 空文字化は防御的 no-op
  - `MODULE_SIG_FORCE` 無効 + Secure Boot なし → 未署名 dkms wl のロード拒否リスクなし
  - `sort -V` では `6.12.94-dpmwd1` が `6.12.94+deb13-amd64` より新しい側 → 放置でも custom が GRUB 先頭になる公算大。**ロールバック時は stock を明示指定する必要**がある
  - Apple の EFI NVRAM は小容量 + panic 時 nonblocking 経路は残量 <5KB で書き込み拒否 → panic ループでの蓄積を防ぐ運用 (回収後レコード削除 + boot 時ガード unit) が必要

### stock との差分 (説明責任用)

挙動に関わる差分は **DPM_WATCHDOG=y (TIMEOUT=60) のみ** (device callback が 60 秒を超えない限り完全に inert。現状 hang は強制電源断で終わるので panic+自動再起動は厳密に改善)。非挙動差分: DEBUG_INFO/BTF なし (ビルド時間短縮)、モジュール署名鍵がエフェメラル、Debian パッチ 97 本は同一適用。

## 作業分担 (エージェント委任)

手順が確定していて検証ゲートが機械的なものはサブエージェントに委任し、メインループ (Fable) は「ユーザ対話ゲート」「実機の起動系 (GRUB/reboot) の状態変更判断」「panic レコードの機序解釈」「レポート最終化」に専念する。

| 作業 | 担当 | 理由 |
|---|---|---|
| Phase A 全体 (libelf-dev install → branch + quiltimport → config 調整 → bindeb-pkg → 成果物検証) | **sonnet エージェント (background)** | コマンド列と grep ゲートが本プランで確定済み。ビルド ~1-2h の待ちを背景化し、メインループは完了通知後にゲート出力 (`CONFIG_DPM_WATCHDOG=y` / `.deb` 生成) だけ検収 |
| Phase B-1,2 (.deb scp → dpkg -i → dkms/vmlinuz 確認) | **sonnet エージェント** | 機械的。出力 (dkms status 等) をメインループが検収 |
| Phase B-3〜8 (GRUB 変更、reboot 調整、ゲート (a)(a2)(b)、デフォルト化、ガード unit) | **メインループ** | 起動系の不可逆性判断とユーザのコンソール前作業 (crash テスト) の対話進行が必要 |
| Phase C 準備物の作成 (pstore ガード unit、58-snapshot-only hook、vpn-watcher/cycle-watcher の transient unit 定義) | **sonnet エージェント** | 過去セッションの attachment/レポートに実装が残っており再生成は機械的。デプロイ前にメインループがレビュー |
| Phase C セッション進行 (baseline 確認、ユーザ案内、canary 判定、hang 対応) | **メインループ** | ユーザとのリアルタイム対話が本体 |
| Phase C 事後集計 (snapshot pair matching、source-IP retro-classify、wl_loaded/ping/xfrm 集計) | **sonnet エージェント** | 103415 までのセッションで確立済みの機械的レシピ。結果をメインループが検収 |
| pstore panic レコードの stack 解釈・機序ラダー (H2/H4/H6/H7) への当てはめ | **メインループ** (必要に応じ **opus** に独立解釈させてクロスチェック) | 本プランの成果物そのもの。誤読コストが最大の箇所 |
| レポートドラフト (タイムライン・環境情報・再現手順の定型部) | **opus エージェント** | 定型構造は CLAUDE.md ルール + 過去レポートで確定。結論・機序評価セクションはメインループが執筆・最終化 |

## Phase A: 開発機でカーネルビルド (~1-2h、ビルド待ち含む)

1. `sudo apt install libelf-dev`
2. 実機から config 取得: `scp miminashi@macbookair2015.lan:/boot/config-6.12.94+deb13-amd64 src/` (ssh 必要 → /sandbox 無効化 or allowedDomains)
3. `src/linux-6.12.y` でブランチ + Debian パッチをコミットとして取り込み:
   ```bash
   git checkout -b dpmwd/6.12.94 v6.12.94
   git quiltimport --patches ../debian-6.12.94-1/debian/patches
   ```
   (git status がクリーンであること = localversion に `+` が付かない前提を確認)
4. config 調整:
   ```bash
   cp ../config-6.12.94+deb13-amd64 .config
   make olddefconfig
   scripts/config -e DPM_WATCHDOG --set-val DPM_WATCHDOG_TIMEOUT 60 \
     --set-str SYSTEM_TRUSTED_KEYS "" --set-str SYSTEM_REVOCATION_KEYS "" \
     -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT -e DEBUG_INFO_NONE \
     --set-str LOCALVERSION "-dpmwd1"
   make olddefconfig   # 再解決 (必須)
   grep -E "DPM_WATCHDOG|DEBUG_INFO_NONE|LOCALVERSION" .config  # 最終確認ゲート
   ```
5. `make -j12 bindeb-pkg` → `src/` 直下に `linux-image-6.12.94-dpmwd1_*.deb` + `linux-headers-6.12.94-dpmwd1_*.deb`

## Phase B: 実機デプロイ + 検証ゲート (~30-60 分、ユーザのコンソール前作業あり)

前提: /sandbox 無効化 (ssh 用)。ユーザには「sysrq crash テストで意図的に 1 回 panic + 自動再起動させる」ことを事前案内。

1. `.deb` 2 個を scp → `sudo dpkg -i` (postinst が initramfs / update-grub / **dkms autoinstall** を自動実行)
2. 確認: `dkms status` で broadcom-sta が `6.12.94-dpmwd1` 向けに built、`/boot/vmlinuz-6.12.94-dpmwd1` 存在
3. GRUB 設定 (可逆):
   - `GRUB_CMDLINE_LINUX_DEFAULT` に `panic=15` を追加 (panic 後 15 秒で自動再起動 → pstore 回収が容易に。sysctl でなく cmdline にするのは gate (b) の crash テスト時点から効かせるため)
   - `GRUB_DEFAULT=saved` + `update-grub` + **`grub-set-default` で saved default をまず stock に明示設定** (sort 順では dpmwd1 が先頭に来るため、これを先にやらないと下のワンショットのフォールバック先も dpmwd1 になりフェイルセーフが成立しない)
   - **初回ブートは `grub-reboot` のワンショット**で dpmwd1 を指定 (起動不能・panic 時は saved default = stock に自動フォールバック) → ユーザが再起動
4. ゲート (a) 起動後: `uname -r` = `6.12.94-dpmwd1`、`/boot/config-6.12.94-dpmwd1` で `DPM_WATCHDOG=y`、wl loaded + WiFi 動作、`/sys/module/pstore/parameters/backend` = `efi_pstore`
5. ゲート (a2): smoke suspend/wake 1 cycle (`rtcwake -m no -s 15` + `systemctl start systemd-suspend.service --wait`)
6. `grub-set-default` で saved default を stock から dpmwd1 に切り替え = 恒久デフォルト化 (submenu は `gnulinux-advanced-<UUID>>gnulinux-6.12.94-dpmwd1-advanced-<UUID>` の `>` 連結 ID 形式。ID は `/boot/grub/grub.cfg` から採取、`grub-editenv list` で確認)。**ゲート (b) より前に行うのは、crash テストで「panic → 自動再起動 → dpmwd1 に復帰」という Phase C が依存するループ全体を検証するため**
7. **ゲート (b) pstore end-to-end 検証 (blocking)**: ユーザがコンソール前で `echo c | sudo tee /proc/sysrq-trigger` → panic → 15 秒後自動再起動 → `uname -r` = dpmwd1 に復帰していること + `/sys/fs/pstore/dmesg-efi-*` にダンプがあることを確認 → **内容確認後レコード削除** (NVRAM 残量温存)。ここで書き込み失敗なら Apple NVRAM の制約が判明 → ramoops 検討に分岐 (本プラン外)
8. pstore ガード unit 投入: boot 時に `/sys/fs/pstore` に dmesg レコードが残っていたら `systemd-inhibit --what=sleep --mode=block sleep infinity` を張る **Type=simple** の service (panic 再起動 → lid 閉のまま再 suspend → 再 hang → NVRAM 蓄積のループを遮断)。レコード回収・削除後は `systemctl stop` で inhibitor を解除する運用

## Phase C: hang 再現セッション (~90 分/回、ユーザ手動 lid cycle)

hang arm (063543/043251/102907) と同一設計を dpmwd1 カーネル上で再演:

- wl **loaded** + `nmcli radio wifi off` (rmmod しない)、BT-PAN + GSNet autoconnect、vpn-watcher / cycle-watcher transient unit、58-snapshot-only hook 再デプロイ、source-IP gate / cycle-1 canary は既存プロトコルを踏襲
- セッション中のみ `sysctl kernel.hung_task_panic=1` (khungtaskd は freeze されないため、watchdog 非カバーの pre-freeze/notifier 段の uninterruptible stall も panic 化して拾う。終了時 revert)
- N=30/セッション。pooled rate ~9% なら P(≥1 hang) ≈ 94%、~5% でも ≈ 79%。出なければもう 1 セッション
- **hang 時の手順 (ユーザ)**: wake しない → **即 lid を開けて ≥5 分待つ** (DPM watchdog は 60 秒、hung_task_panic は最大 ~240 秒後に発火するため) → panic=15 で自動再起動していれば evidence 確保済 / 再起動しなければ従来通り強制電源断 → 再起動後は WiFi radio off が persist しているので、ユーザが `nmcli radio wifi on` + `nmcli con up OpenWrt` で ssh 復旧 → Claude が pstore 回収 + レコード削除 + ガード unit の inhibitor を `systemctl stop` で解除 → セッション継続可否を判断。**継続する場合は `kernel.hung_task_panic=1` を再設定** (sysctl は再起動で消える) し、ユーザが `nmcli radio wifi off` で再現条件に復帰 (wl は loaded のままなので rmmod 系の再手順は不要)

### 結果の解釈マトリクス (事前定義)

| 観測 | 解釈 |
|---|---|
| panic + `<driver> <dev>: unrecoverable failure` (suspend 側 stack) | **機序決着の直接証拠**。stall device と call chain が確定、H2/H4/H6/H7 を直接判別 |
| panic + resume 側 stack | hang は β (復帰側) — 現行手法で原理的に不能だった α/β 判別が決着 |
| hung_task panic | pre-freeze / notifier 段の stall — 074509 の「hci_suspend_dev 経路排除できず」が的中の可能性 |
| hang するが panic なし (5 分超) | 失敗ではなく判別情報: suspend_late/noirq/IRQ-off ハードロック等の非カバー段 → 次段 (ramoops console + pm_print_times、または watchdog を late/noirq へ拡張する小パッチ) へ |

## ロールバック / 撤収

- stock カーネル (6.12.94+deb13-amd64) は残置。ロールバック = `grub-set-default` で **stock を明示指定** (sort 順で dpmwd1 が先頭に来るため放置では戻らない) + `panic=15` を GRUB から除去 + `update-grub`
- キャンペーン終了時: `dpkg -r` で dpmwd1 の image/headers を除去、ガード unit 削除
- キャンペーン中は dpmwd1 を常用してよい (inert であり、日常の実 hang も自己申告化されるメリットのみ)

## 成果物

- レポート: `report/yyyy-mm-dd_hhmmss_*.md` (CLAUDE.md ルール準拠、本プランを attachment に添付、Phase B と Phase C は別レポートでも可)
- メモリ更新: `s2idle-btvpn-hang-mechanism-ladder` に S4 着手と結果を反映

## 検証方法

- Phase A: `.config` の `CONFIG_DPM_WATCHDOG=y` / `CONFIG_DPM_WATCHDOG_TIMEOUT=60` grep、bindeb-pkg の .deb 生成
- Phase B: ゲート (a)/(a2)/(b) が blocking — 特に (b) の sysrq → pstore 実ダンプ回収が evidence chain 全体の end-to-end 検証
- Phase C: hang 発生時に pstore から driver 名入り panic レコードが回収できること (解釈マトリクスに従い、panic 不発も判別情報として記録)
