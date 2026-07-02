# DPM_WATCHDOG=y 自前カーネル (6.12.94-dpmwd1) のビルド・実機デプロイと pstore end-to-end 検証の完了 (S4 着手)

- **実施日時**: 2026 年 7 月 2 日 11:54 〜 18:28 JST (プラン承認〜レポート作成。ビルド完了 12:40 〜 実機デプロイ 18:15 の間は中断あり)
- **位置づけ**: [2026-07-02_103415 セッション](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) の推奨次の手 (iv)、および [2026-07-02_092013 方法論監査](2026-07-02_092013_hang_investigation_methodology_audit.md) が「機序決着の唯一の出口」とした S4 (DPM_WATCHDOG 有効カーネル) に着手。本セッションは Phase A (開発機でのカーネルビルド) と Phase B (実機へのデプロイ + pstore end-to-end 検証ゲート) を完了させ、次の Phase C (dpmwd1 上での hang 再演 + kernel dump 取得) の準備までを行う。

## 概要

### 背景

これまでの 7 セッションで hang は「wl が loaded かつ radio-off」の条件でのみ発生することが Fisher exact 片側 p ≈ 0.024 で統計的に establish された ([103415](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)) が、hang の中身 (dpm_suspend でどのドライバが止まっているか) はブラックボックスのままだった。現行 stock カーネル (`6.12.94+deb13-amd64`) は `CONFIG_DPM_WATCHDOG=n` で、dpm_suspend 段の stall device を特定できない。方法論監査 ([092013](2026-07-02_092013_hang_investigation_methodology_audit.md)) は、これ以上の再現サイクルを重ねても機序特定には到達せず、DPM_WATCHDOG 有効カーネルで stall した device callback の stack trace を取得することが機序決着の唯一の出口だと結論した。

### 本セッションでやったこと

DPM_WATCHDOG=y の自前カーネル `6.12.94-dpmwd1` を開発機 (akdx01) でビルドし、実機 (macbookair2015.lan) にデプロイして、hang panic の dump が pstore 経由で確実に回収できることを end-to-end で検証した。

- **Phase A**: upstream v6.12.94 に Debian パッチ 79 本を取り込み、実機の stock config をベースに `CONFIG_DPM_WATCHDOG=y` / `TIMEOUT=60` を有効化して `bindeb-pkg` でビルド。ビルド時のトラブル 2 件 (LOCALVERSION の `+` 付与、olddefconfig の auto.conf 非同期) を解決し、`linux-image-6.12.94-dpmwd1` を得た。
- **Phase B**: 実機にデプロイ (dkms が wl を dpmwd1 向けに自動再ビルド + MOK 署名)。起動ゲート (a)、s2idle smoke ゲート (a2)、sysrq crash による pstore ゲート (b) を通過。crash テストは 2 回実施し、grubenv の sync 漏れに起因する「panic 後に stock 起動」の落とし穴を発見・解決して「panic → dpmwd1 自動復帰」ループを確立した。pstore-guard.service も導入し、未回収 dump がある間は suspend/lid を block する仕組みを整えた。

### 結果

- 自前カーネルは実機で稼働中 (GRUB saved default = dpmwd1、stock 残置でロールバック可能)。
- crash panic の dump が efi_pstore → systemd-pstore 経由で `/var/lib/systemd/pstore/` に回収され、`dmesg.txt` 172KB に panic メッセージ・full stack・per-device PM ログまで残ることを確認。本番の hang panic では dpm シーケンス全体が dump に残る見込み。
- Phase C (hang 再演 + dump 取得) の準備物はレビュー済デプロイ待ち。

## 添付ファイル

- [実装プラン](attachment/2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e/plan.md)
- [crash テスト 1 回目の pstore 証拠 (dmesg.txt 172KB 含む)](attachment/2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e/pstore-crashtest1.tar.gz)
- [crash テスト 2 回目の pstore 証拠](attachment/2026-07-02_182811_dpm_watchdog_kernel_build_deploy_pstore_e2e/pstore-crashtest2.tar.gz)

## 前提・目的

- **背景**: [103415](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md) で hang の必要条件 (wl-loaded-AND-radio-off) は統計的に establish されたが、dpm_suspend でどの device callback が stall するかは不明。[092013 方法論監査](2026-07-02_092013_hang_investigation_methodology_audit.md) が DPM_WATCHDOG=y カーネルでの stack trace 取得を機序決着の唯一の出口と結論。
- **目的**: DPM_WATCHDOG=y の自前カーネル `6.12.94-dpmwd1` をビルド・デプロイし、hang panic の dump が pstore で確実に回収できることを end-to-end で検証する。実際の hang 再演 (Phase C) はその dump 回収経路が信頼できることを確認してから行う。
- **前提条件**:
  - 実機導入版に厳密一致させるため、upstream v6.12.94 + Debian パッケージのパッチ (`debian-6.12.94-1`) を使う (CLAUDE.md 方法 A+B の折衷)。
  - DPM_WATCHDOG=y は挙動差分を最小化する (60 秒超の device callback が無い限り inert)。
  - stock からのロールバックを常に確保する (GRUB saved default + grub-reboot ワンショット)。
- **役割分担**: カーネルビルド・config 検収・デプロイ・ゲート判定は Claude が実施 (Phase A は開発機ローカル、Phase B は実機に ssh)。実機コンソール前での起動確認・crash テストの目視は必要に応じてユーザ。

## 環境情報

- **実機 (運用・修正対象)**: MacBook Air 11" (Early 2015) / Debian 13 (trixie) / 旧カーネル `6.12.94+deb13-amd64` → 新カーネル `6.12.94-dpmwd1` (本セッションで導入、稼働中)。GRUB saved default = dpmwd1、stock 残置 (ロールバック可)。s2idle / system-sleep hooks / NM 設定は 103415 終了時のまま不変。
- **開発機 (ビルド機)**: akdx01 / Debian 13 (trixie) / 12 コア / 32GB RAM。
- **スリープ**: `[s2idle] deep`、GRUB `mem_sleep_default=s2idle no_console_suspend` (恒久)。
- **BT/テザリング/VPN**: 103415 と同一構成 (Phase C で使用)。
- **実験系の残置物 (実機)**: `pstore-guard.service` (enabled)、GRUB `panic=15`、`/etc/default/grub.bak-dpmwd` (元 GRUB 設定バックアップ)。
- **crash テストの pstore 証拠**: レポート attachment に格納 (添付ファイルセクション参照)。実機側レコードは NVRAM 温存のため削除済。

## Phase A: カーネルビルド (開発機 akdx01)

### ソース取得と Debian パッチ取り込み

`src/linux-6.12.y` (upstream v6.12.94) に `dpmwd/6.12.94` ブランチを切り、Debian パッケージのパッチを quiltimport で取り込んだ:

```bash
cd src/linux-6.12.y
git checkout -b dpmwd/6.12.94 v6.12.94
git quiltimport \
  --author "Debian Kernel Team <debian-kernel@lists.debian.org>" \
  --patches ../debian-6.12.94-1/debian/patches
```

- **パッチは 79 本** (事前レビューの「97 本」は数え間違い): `series` ファイル 115 行中、コメント 18 行 + 空行 18 行を除いた実パッチが 79 本。
- 全 79 本がクリーンに適用され、tree はクリーン。`git rev-list v6.12.94..HEAD --count` = 79 で検収。

### config 生成

実機の `/boot/config-6.12.94+deb13-amd64` をベースに、DPM_WATCHDOG 有効化 + ビルド簡略化のための調整を行った:

```bash
scp miminashi@macbookair2015.lan:/boot/config-6.12.94+deb13-amd64 ../
cp ../config-6.12.94+deb13-amd64 .config
scripts/config \
  -e DPM_WATCHDOG \
  --set-val DPM_WATCHDOG_TIMEOUT 60 \
  --set-str SYSTEM_TRUSTED_KEYS "" \
  --set-str SYSTEM_REVOCATION_KEYS "" \
  -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
  -e DEBUG_INFO_NONE \
  --set-str LOCALVERSION "-dpmwd1"
make olddefconfig
```

- `SYSTEM_TRUSTED_KEYS` / `SYSTEM_REVOCATION_KEYS` を空にして Debian 署名鍵依存を外す (エフェメラル署名)。
- `DEBUG_INFO_NONE` を有効化してビルド時間・成果物サイズを削減 (DWARF/BTF なし)。
- `make olddefconfig` で依存関係を再解決。

### ビルド時トラブルと解決

1. **`make kernelrelease` が `6.12.94-dpmwd1+` (末尾に `+`)**:
   `CONFIG_LOCALVERSION_AUTO=n` の環境で HEAD がタグ直上にない (= quiltimport でコミットが積まれた) 場合、`scripts/setlocalversion --short` が構造的に `+` を付与する仕様 (dirty tree が原因ではない)。ビルドは env `LOCALVERSION` を空で渡して抑止し、`6.12.94-dpmwd1` を得た:

   ```bash
   make -j12 LOCALVERSION= bindeb-pkg
   ```

2. **2 回目の olddefconfig で `include/config/auto.conf` に LOCALVERSION が同期されない**:
   `scripts/config` で `.config` を書き換えた後、Kbuild の incremental syncconfig が `auto.conf` に LOCALVERSION を反映しない癖があった。`auto.conf` を削除して再生成することで解決。

### 成果物と検収

- `linux-image-6.12.94-dpmwd1` (85MB) + `linux-headers-6.12.94-dpmwd1` (8.8MB)。
- deb パッケージ内 config で `CONFIG_DPM_WATCHDOG=y` / `CONFIG_DPM_WATCHDOG_TIMEOUT=60` を検収済。
- **stock との挙動差分は DPM_WATCHDOG=y のみ** (60 秒超の device callback が無い限り inert)。非挙動差分は DEBUG_INFO/BTF なし、署名鍵エフェメラルの 2 点。

## Phase B: 実機デプロイ + 検証ゲート (macbookair2015.lan)

### デプロイ

```bash
sudo dpkg -i linux-headers-6.12.94-dpmwd1_*.deb
sudo dpkg -i linux-image-6.12.94-dpmwd1_*.deb
```

- image の postinst で dkms が broadcom-sta (wl) 6.30.223.271 を dpmwd1 向けに自動ビルド + MOK 署名、initramfs 生成、`update-grub` を完了。

### GRUB 設定 (フェイルセーフ付き)

- `GRUB_DEFAULT=saved` 化。
- `GRUB_CMDLINE_LINUX_DEFAULT` に `panic=15` 追加 (panic 後 15 秒で自動再起動)。
- 元設定を `/etc/default/grub.bak-dpmwd` にバックアップ。
- saved default をまず **stock** に設定 → `grub-reboot` ワンショットで dpmwd1 を初回起動 (起動不能時に次回 stock へ戻るフェイルセーフ)。

### ゲート (a): 起動確認 — 全通過

| # | 項目 | 期待 | 実測 | 判定 |
|---|---|---|---|---|
| 1 | uname | 6.12.94-dpmwd1 | 一致 | ✓ |
| 2 | CONFIG_DPM_WATCHDOG | y / TIMEOUT=60 | 一致 | ✓ |
| 3 | cmdline | panic=15 を含む | 一致 | ✓ |
| 4 | wl | loaded + WiFi 動作 | 一致 | ✓ |
| 5 | pstore backend | efi_pstore | 一致 | ✓ |
| 6 | pstore 内容 | 空 | 一致 | ✓ |

### ゲート (a2): s2idle smoke — 通過

`rtcwake` + `systemd-suspend` で s2idle を 1 cycle:

- `PM: suspend entry` / `PM: suspend exit` クリーン。
- `suspend_stats` success=1 / fail=0。

### ゲート (b): sysrq crash テスト (pstore end-to-end) — 2 回実施

#### 1 回目: panic → 15 秒自動再起動 → stock 起動 (想定外) だが pstore は完璧

- sysrq crash trigger で panic → `panic=15` で 15 秒後に自動再起動 → **stock カーネルで起動 (想定外)**。
- ただし pstore 回収経路は完璧に動作:
  - efi_pstore が panic dump を EFI 変数に ~20+ 分割で書き込み。
  - systemd-pstore が `/var/lib/systemd/pstore/` へ回収、`dmesg.txt` 172KB。
  - dump 内容に `Kernel panic - not syncing: sysrq triggered crash`、`6.12.94-dpmwd1`、`sysrq_handle_crash` の full stack、さらに `70-h4-probe` hook が有効化する `pm_debug_messages` の per-device PM ログ (`PM: calling ... @` 行) まで含まれることを確認。
  - **本番の hang panic では dpm シーケンス全体が dump に残ることが裏付けられた**。

#### stock 起動の原因 (grubenv の sync 漏れ)

- 直前の `grub-set-default` (dpmwd1) による grubenv 書き込みが、panic 時点でディスク上の最終位置に未反映だった。
- GRUB は ext4 ジャーナルを再生せずディスクの古いブロックを読むため、古い (stock) デフォルトで起動した。
- Linux が再起動後にジャーナルを反映し、grubenv は dpmwd1 を示していた — この非対称が原因の証拠。

#### 2 回目: sync 後に再テスト → panic → dpmwd1 自動復帰を確認

- stock 上から `sync` を実施した後に再度 crash テスト → **panic → 自動で dpmwd1 に復帰**を確認。
- 「panic → dpmwd1」ループの検証完了。
- **教訓**: grubenv 変更後は必ず `sync` する。

### pstore-guard.service のデプロイ + enable

- 未回収 dump がある間、`systemd-inhibit --what=sleep:handle-lid-switch --mode=block` で suspend / lid 処理を block する Type=simple の service (boot 時に `/sys/fs/pstore` と `/var/lib/systemd/pstore/` の両方を判定)。
- **設計知見**: `LidSwitchIgnoreInhibited=yes` (logind デフォルト) 対策として、`--what` に `sleep` だけでなく `handle-lid-switch` を併記することが必須。
- レコード無しの状態で exit 0 する正常動作を確認済。

## 検証結果まとめ

1. **自前カーネル `6.12.94-dpmwd1` が実機で稼働中** (uname / config / cmdline 検収済、wl 動作)。
2. **CONFIG_DPM_WATCHDOG=y / TIMEOUT=60** を deb 内 config と実機の両方で確認。
3. **pstore end-to-end 経路が信頼できる**: efi_pstore → systemd-pstore の回収で panic dump に panic メッセージ・full stack・per-device PM ログが残る。
4. **「panic → dpmwd1 自動復帰」ループ確立** (grubenv sync 漏れの落とし穴を解消)。
5. **pstore-guard.service が未回収 dump 中の suspend/lid を block** (dump 上書き防止)。
6. **ロールバック確保**: stock 残置 + GRUB saved default + grub.bak-dpmwd。

## 再現方法

### Phase A: ビルド (開発機、Debian 13, deb-src 設定済)

```bash
# 1) upstream v6.12.94 を取得しブランチを切る
cd src
git clone --depth 1 --branch v6.12.94 \
  https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git linux-6.12.y
cd linux-6.12.y
git checkout -b dpmwd/6.12.94 v6.12.94

# 2) 実機導入版に一致する Debian ソース (パッチ) を取得
#    本セッションでは 074509 セッションで取得済みの src/debian-6.12.94-1/ (linux 6.12.94-1
#    の debian/ ディレクトリ) を利用した。新規取得する場合は deb-src 設定済み環境で
#    `apt-get source linux=6.12.94-1` (または sources.debian.org から同版を取得)

# 3) Debian パッチ 79 本を取り込む
git quiltimport \
  --author "Debian Kernel Team <debian-kernel@lists.debian.org>" \
  --patches ../debian-6.12.94-1/debian/patches
git rev-list v6.12.94..HEAD --count   # → 79 を確認

# 4) 実機の stock config をベースに DPM_WATCHDOG を有効化
scp miminashi@macbookair2015.lan:/boot/config-6.12.94+deb13-amd64 ../
cp ../config-6.12.94+deb13-amd64 .config
scripts/config \
  -e DPM_WATCHDOG \
  --set-val DPM_WATCHDOG_TIMEOUT 60 \
  --set-str SYSTEM_TRUSTED_KEYS "" \
  --set-str SYSTEM_REVOCATION_KEYS "" \
  -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
  -e DEBUG_INFO_NONE \
  --set-str LOCALVERSION "-dpmwd1"
make olddefconfig
# olddefconfig で auto.conf に LOCALVERSION が同期されない場合:
rm -f include/config/auto.conf && make olddefconfig

# 5) LOCALVERSION の "+" 付与を env で抑止してビルド
make -j12 LOCALVERSION= bindeb-pkg
```

### Phase B: デプロイ + 検証 (実機)

```bash
# 1) デプロイ (headers → image の順)
sudo dpkg -i linux-headers-6.12.94-dpmwd1_*.deb
sudo dpkg -i linux-image-6.12.94-dpmwd1_*.deb

# 2) GRUB フェイルセーフ設定
sudo cp /etc/default/grub /etc/default/grub.bak-dpmwd
# GRUB_DEFAULT=saved 化 + GRUB_CMDLINE_LINUX_DEFAULT に panic=15 追加
sudo update-grub
sudo grub-set-default <stock のエントリ>
sudo sync            # ← grubenv 変更後は必ず sync (1 回目 crash テストの教訓)
sudo grub-reboot <dpmwd1 のエントリ>   # 初回のみ dpmwd1、以降 stock に戻る

# 3) 再起動後ゲート (a) 確認
uname -r
grep DPM_WATCHDOG /boot/config-6.12.94-dpmwd1
cat /proc/cmdline
cat /sys/module/pstore/parameters/backend 2>/dev/null; ls /sys/fs/pstore/

# 4) ゲート (a2): s2idle smoke
sudo rtcwake -m no -s 15 & sudo systemctl start systemd-suspend.service --wait

# 5) ゲート (b): sysrq crash テスト
sudo sync            # ← 必須
echo c | sudo tee /proc/sysrq-trigger   # panic → 15 秒後自動再起動
# 再起動後、pstore 回収を確認
ls /var/lib/systemd/pstore/
```

## 次セッション (Phase C) 引継ぎ

### 実験設計

- hang arm は 103415 と同一設計 (wl loaded + radio off + BT-PAN + VPN + 手動 lid close 30 cycle) を dpmwd1 上で再演。
- `kernel.hung_task_panic=1` を併用 (pre-freeze 段の hang も panic で捕捉)。

### hang 発生時の手順

1. 即 lid open。
2. **5 分以上待つ**。
3. `panic=15` で自動再起動 → 起動しなければ強制電源断。
4. 再起動後に pstore 回収。

### 解釈マトリクス

| dump の内容 | 解釈 |
|---|---|
| suspend 側の device callback stack | 機序決着 (どの driver が stall したか) |
| resume 側の stack | β 判別 (resume 段の問題) |
| hung_task の stack | pre-freeze 段の hang |
| panic が全く無い | DPM_WATCHDOG がカバーしない段での停止 (それ自体が判別情報) |

### 準備物 (レビュー済デプロイ待ち)

`scratchpad/phase-bc-materials/` に配置:

- `58-snapshot-only` (103415 の hook を逐語復元)。
- transient units (vpn-watcher / cycle-watcher 等)。
- `session-commands.md` (Phase C 手順のコマンド集)。

## 実験全体タイムライン

| 時刻 (JST) | フェーズ | 内容 |
|---|---|---|
| 〜11:54 | プランニング | 事前検証 (Kconfig 依存・dpm_watchdog 実装・実機 config・ビルド環境) + Plan agent 設計レビュー + プラン承認 |
| 11:54-12:04 | Phase A-prep | sonnet 委任: 実機 config 取得 (11:55)、quiltimport 79 本、config 調整、kernelrelease ゲート |
| 12:05 頃 | Phase A | ユーザが libelf-dev インストール、`make -j12 LOCALVERSION= bindeb-pkg` 開始 |
| 12:40 | Phase A | ビルド完了、成果物検収 (linux-image 85MB / headers 8.8MB、deb 内 config で CONFIG_DPM_WATCHDOG=y/60) |
| (中断) | — | ユーザのデプロイ承認待ち |
| 18:15 | Phase B | 実機デプロイ dpkg -i (dkms が wl 自動再ビルド + MOK 署名、initramfs、update-grub) |
| 18:17 頃 | Phase B | GRUB フェイルセーフ設定 (GRUB_DEFAULT=saved、panic=15、saved=stock、grub-reboot ワンショット=dpmwd1) |
| 18:19 | Phase B | ユーザ再起動 → dpmwd1 初回起動、ゲート (a) 全通過 |
| 18:21 | Phase B | ゲート (a2) s2idle smoke 通過 (rtcwake wake 18:21:04)、saved default を dpmwd1 に切替 |
| 18:22 | Phase B | ゲート (b) crash テスト 1 回目 (panic 18:21:57) → 自動再起動 → **stock 起動 (想定外)**、pstore は 172KB 完全回収 |
| 18:23-25 | Phase B | stock 起動の原因究明 (grubenv sync 漏れ)、pstore 証拠退避 + レコード削除 |
| 18:26 | Phase B | ゲート (b) crash テスト 2 回目 (sync 後) → panic → **dpmwd1 自動復帰確認** |
| 18:27 | Phase B | pstore-guard.service デプロイ + enable (18:27:51 正常動作確認) |
| 18:28 | レポート作成 | 本レポート作成、Phase C handover |

## 残置物 (実機の現状)

| パス / 項目 | 状態 | 用途 |
|---|---|---|
| kernel 6.12.94-dpmwd1 | 稼働中 (GRUB saved default) | DPM_WATCHDOG=y カーネル |
| kernel 6.12.94+deb13-amd64 (stock) | 残置 | ロールバック用 |
| `pstore-guard.service` | enabled | 未回収 dump 中の suspend/lid block |
| GRUB `panic=15` | 設定済 | panic 後 15 秒自動再起動 |
| `/etc/default/grub.bak-dpmwd` | 残置 | 元 GRUB 設定バックアップ |
| system-sleep hooks / NM / s2idle | 103415 終了時のまま不変 | |
| 実機側 pstore レコード | 削除済 (NVRAM 温存) | crash テスト分は開発機に退避 |

開発機 (akdx01) 側: ビルド成果物 (deb 2 個) + crash テスト pstore 証拠を保持。

## 関連レポート

- [2026-07-02_103415 セッション: pool 0/60 で Fisher p ≈ 0.024、(b'') tight reading bedrock 化 (本セッションの起点、次の手 (iv))](2026-07-02_103415_s2idle_btvpn_wl_unload_pool_p024_bedrock.md)
- [2026-07-02_092013 方法論監査: S4 (DPM_WATCHDOG) を機序決着の唯一の出口と結論](2026-07-02_092013_hang_investigation_methodology_audit.md)
- [2026-06-28_074509 カーネルソース解析: S4 (DPM_WATCHDOG) 初出、H1/H2/H4 仮説](2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md)
- [2026-06-29_041006 セッション: efi_pstore registered 確認](2026-06-29_041006_s2idle_btvpn_hang_s1_btusb_unload_clean.md)
