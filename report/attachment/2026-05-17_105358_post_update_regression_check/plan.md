# 2026-05-17 Debian アップデート後デグレチェック・レポート作成

## Context

`macbookair2015.lan` で 2026-05-17 に Debian アップデートを実施した。
このアップデートでは 1 日のうちに `linux-image-6.12.86` (10:19) → `linux-image-6.12.88` (10:28)
の **2 段階カーネル昇格** および libreoffice / firefox-esr / dnsmasq / libpng / libnghttp2 /
libav* 等の通常パッケージ更新が走った。

過去にこのプロジェクトで適用してきた以下のパッチ・ワークアラウンドが、
今回のアップデートで失われていないかを確認し、結果を report/ に記録する。

過去作業の概要 (README.md より):

1. **SSD 交換** (2026-03-30): 旧 SSD のハードウェア故障 → 交換 + 健全性確認
2. **Wi-Fi 系 (4/1)**: wpa_supplicant + systemd-networkd ワークアラウンド → NM `+broadcomfix1` パッチ版に置き換え
3. **broadcom-sta DKMS 修復 (5/5)**: `linux-headers-amd64` メタ投入で DKMS の自動追従を恒久化
4. **i915.enable_dc=0 暫定対策 (5/10)**: lid open S3 hang 対策、4-6 週間の継続観測フェーズ中

今回のアップデートで特に注目すべき点:

- 5/17 のカーネル 2 段昇格は **5/5 で入れた DKMS 恒久対策 (`linux-headers-amd64` メタ) の初の実戦テスト** に相当する
- カーネル更新を跨いで継続観測中の `i915.enable_dc=0` 監視窓 (5/10〜) が今回のアップデートでリセットされうるかの判定

## 調査結果サマリ (Phase 1 で取得済み)

ssh `miminashi@macbookair2015.lan` 経由で READ-ONLY 確認。すべて健全:

| 過去作業の維持確認項目 | 実機の現状 | 判定 |
|---|---|---|
| NM `1.52.1-1+broadcomfix1` | `dpkg -l` で `hi` (hold+installed) | ✅ |
| libnm0 `1.52.1-1+broadcomfix1` | `hi` | ✅ |
| `apt-mark showhold` | network-manager / libnm0 / linux-image-6.12.74 / linux-headers-6.12.74 | ✅ |
| `linux-headers-amd64` メタ | `6.12.88-1` (新カーネル追従) | ✅ |
| broadcom-sta DKMS | 6.12.74 / 85 / 86 / 88 全て `installed` | ✅ |
| `wl.ko.xz` (現カーネル) | `/lib/modules/6.12.88+deb13-amd64/updates/dkms/` あり (mtime 5/17 10:29 ← DKMS 自動再ビルドの証跡) | ✅ |
| `wl` モジュール | `lsmod` ロード済み (6459392 bytes) | ✅ |
| `wlp3s0` 接続状態 | OpenWrt 接続、IP `192.168.33.145/24` (WPA2 WPA3 シグナル 100) | ✅ |
| systemd-networkd / wpa_supplicant@wlp3s0 | 両方 inactive/disabled (旧ワークアラウンド残骸無し) | ✅ |
| `/etc/NetworkManager/conf.d/` | 空 (`unmanage-wifi.conf` 不在) | ✅ |
| `i915.enable_dc=0` (GRUB + /proc/cmdline) | 両方に残存 | ✅ |
| `/sys/module/i915/parameters/enable_dc` | `0` (実効) | ✅ |
| `/usr/local/sbin/check-suspend-resume.sh` | 設置済 (5/10 04:51) | ✅ |
| 5/10 以降の S3 hang | boot `f9c35ab3` (6.12.85 + `enable_dc=0`) で 66 suspend / 66 resume / diff=0 → **1 週間で 66 cycle 完走、hang 0** | ✅ |
| SSD I/O sysfs カウンタ | `ioerr_cnt=0xc`, `iotmo_cnt=0` (前回レポート時点の値と要比較) | ✅ |
| dmesg ata/scsi/i/o-error | なし | ✅ |
| filesystem state | `clean` | ✅ |

**結論: 今回のアップデートによる過去作業のデグレなし。**
特に 5/5 で入れた DKMS 恒久対策が今回のカーネル 2 段昇格で機能したことを確認。
`i915.enable_dc=0` の継続観測も中断なく継続できる。

## 残タスク

ユーザ確認の結果、レポートを report/ に作成すること、および
過去 (2026-03-30) のレポートで使われていた **smartmontools をインストールして
SMART 値を確認** することが本タスクのスコープに含まれる。

## 作業手順

### Step 1: タイムスタンプ取得

```bash
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
TZ=Asia/Tokyo date "+%Y年%m月%d日 %H:%M"
```

→ レポートファイル名 `yyyy-mm-dd_hhmmss_post_update_regression_check.md` に使用。
LLM の推測時刻は使わない (CLAUDE.md ルール)。

### Step 2: smartmontools インストールと SMART 取得 (ssh 経由、書き込みあり)

```bash
ssh miminashi@macbookair2015.lan '
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y smartmontools
  echo "--- smartctl version ---"
  sudo smartctl --version | head -2
  echo "--- SMART overall health ---"
  sudo smartctl -H /dev/sda
  echo "--- SMART attributes (key IDs) ---"
  sudo smartctl -A /dev/sda
  echo "--- SMART error log ---"
  sudo smartctl -l error /dev/sda
  echo "--- device info ---"
  sudo smartctl -i /dev/sda | head -15
'
```

抽出する主要属性 (2026-03-30 レポート値との比較対象):

- ID 1: Raw_Read_Error_Rate (baseline raw=0)
- ID 5: Reallocated_Sector_Ct (baseline raw=0) — **増えていないか最重要**
- ID 9: Power_On_Hours (baseline raw=37,133) — 経過時間の確認
- ID 194: Temperature_Celsius (baseline 39°C / min 19 / max 66)
- ID 197: Current_Pending_Sector (baseline raw=0) — **増えていないか最重要**
- ID 198: Offline_Uncorrectable (もしあれば)
- 全エラーログのカウント

### Step 3: 実機の関連状態を再取得 (レポート本文に貼る生データ)

Phase 1 取得済み出力をレポートに整形して貼り付ける。追加で:

```bash
ssh miminashi@macbookair2015.lan '
  echo "--- /proc/cmdline ---"; cat /proc/cmdline
  echo "--- dkms status ---"; sudo dkms status
  echo "--- dpkg NM/libnm0 ---"; dpkg -l network-manager libnm0 2>/dev/null | grep -E "^[hi][i]"
  echo "--- apt-mark hold ---"; apt-mark showhold
  echo "--- suspend/resume summary ---"; sudo /usr/local/sbin/check-suspend-resume.sh
  echo "--- nmcli ---"; nmcli -f WIFI-HW,WIFI,STATE,CONNECTIVITY general status; nmcli device status
'
```

### Step 4: レポートを書く

`report/<yyyy-mm-dd_hhmmss>_post_update_regression_check.md` を作成。
構造 (CLAUDE.md レポート作成ルール準拠):

```
# 2026-05-17 Debian アップデート後デグレチェック・レポート

- 実施日時: 2026年5月17日 HH:MM (JST)
- 対象ホスト: macbookair2015.lan

## 添付ファイル
- [実装プラン](attachment/<filename>/plan.md)

## 参照レポート
- カーネル更新で消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)
- NetworkManager WPA-PSK-SHA256 パッチ適用
- MacBook Air lid open 復帰失敗 (S3 hang) 切り分けと暫定対策
- SSD 健全性レポート (交換後) — SMART baseline

## 前提・目的
- 背景: 5/17 のアップデートで 6.12.86 → 6.12.88 の 2 段カーネル昇格
- 目的: 過去 4 系統の対策が維持されているかを 1 回まとめて確認
- 前提条件: ssh NOPASSWD sudo 設定済み

## 環境情報 (現在のホスト状態)
- カーネル, NM, DKMS, GRUB, 各バージョン

## 再現方法 (確認コマンド一覧)
- 上記 Step 2/3 の ssh コマンド群

## 結果
### アップデート内容 (5/17)
- 10:19 packagekit update: 6.12.86 + libreoffice/firefox-esr/...
- 10:28 packagekit update: 6.12.88 + dnsmasq/libpng/...

### 過去作業の維持状況 (表)
- 上のサマリ表 (12 項目)

### SMART (今回取得 vs 2026-03-30 ベースライン)
- 表で比較

### S3 hang 観測 (5/10 以降)
- boot f9c35ab3 の 66/66 完走
- 5/17 の短時間 boot 4 件 (アップデート再起動シーケンス)

## 教訓・観察
- 5/5 で入れた `linux-headers-amd64` メタ恒久対策の初実戦テスト合格
- `i915.enable_dc=0` 継続観測はカーネル昇格を跨いでも維持

## 今後
- `i915.enable_dc=0` 監視窓は当初 5/10 起点で 4-6 週間 = 2026-06-07 〜 2026-06-21
- 旧カーネル `6.12.74+deb13+1-amd64` の hold は 6.12.88 安定確認後に解除候補
```

### Step 5: 添付ディレクトリにプランをコピー

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
NAME="${TS}_post_update_regression_check"
mkdir -p "report/attachment/$NAME"
cp /home/miminashi/.claude/plans/macbook-air-debian-stateful-matsumoto.md "report/attachment/$NAME/plan.md"
```

### Step 6: README.md のレポート一覧テーブルに 1 行追記

最上行 (新しい順) に今回のレポートを追加。リンクは相対パス `report/<filename>`。
記載例:

```
| 2026-05-17 HH:MM | [Debian アップデート後デグレチェック (6.12.86→6.12.88 2 段昇格)](report/<filename>) | NM パッチ / DKMS 恒久対策 / i915.enable_dc=0 / SSD いずれもデグレなし。5/5 DKMS 自動追従対策の初実戦テスト合格 |
```

「適用済みパッチ・ワークアラウンドの概要」セクションには新規追記しない
(今回は新規対策ではなく、既存対策の維持確認なので)。

## 検証

1. **レポートファイルが生成され、ファイル名が CLAUDE.md ルール準拠** であること
   - 命名: `yyyy-mm-dd_hhmmss_post_update_regression_check.md`
   - 添付: `report/attachment/<同名>/plan.md` 存在
2. **README.md の一覧テーブル**に新しい行が追加されていること
3. **smartmontools 投入後** に `smartctl -H /dev/sda` が `PASSED` を返すこと
4. **Discord webhook** で自動通知が走ること (`.env` の `DISCORD_WEBHOOK_URL` 経由、PostToolUse hook)

## 重要な遵守事項 (CLAUDE.md より)

- タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (LLM 推測禁止)
- レポート内日時は JST 表記
- ssh 越しに実機側で実行する (開発マシン側で叩かない)
- `~/.ssh/` の個人鍵が使われる。リポジトリ直下の `.ssh/` は GitHub deploy key 専用

## 関連ファイル

- 編集対象:
  - `report/<新ファイル>` (新規作成)
  - `report/attachment/<新ファイル名>/plan.md` (新規作成)
  - `README.md` (1 行追記)
- 参照: `CLAUDE.md`, 既存 4 件のレポート (上記)
