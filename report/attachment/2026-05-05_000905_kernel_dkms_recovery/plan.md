# MacBook Air 2015 — カーネル更新で消えた Wi-Fi の修復

## Context

- **対象機**: macbookair2015.lan (MacBook Air 11" Early 2015) / Debian 13 trixie
- **症状**: 2026-05-04 の Debian アップデート適用後、GNOME のシェルメニューに Wi-Fi が出てこなくなった。`nmcli` で `WIFI-HW: missing`、`wlp3s0` が `nmcli device status` に現れない。
- **発生のきっかけ**: 2026-05-04 23:02 の `packagekit role='update-packages'` で `linux-image-6.12.85+deb13-amd64` が新規インストールされ、再起動後 `6.12.85+deb13-amd64` で起動。
- **目的**: 新カーネルで `wl` (broadcom-sta-dkms) を再ビルドし、`wlp3s0` を復旧、NetworkManager (`1.52.1-1+broadcomfix1`) 経由で OpenWrt SSID に再接続して GNOME GUI から Wi-Fi 操作できる状態に戻す。同時に、今後カーネル更新で同じ事象が再発しないよう恒久対策を入れる。

参照する過去レポート:
- [`report/2026-04-01_080116_wifi_fix.md`](../../projects/macbookair11-debian/report/2026-04-01_080116_wifi_fix.md) — `wl` の WPA-PSK-SHA256 非対応問題と暫定ワークアラウンド (wpa_supplicant + systemd-networkd)
- [`report/2026-04-01_182006_networkmanager_patch.md`](../../projects/macbookair11-debian/report/2026-04-01_182006_networkmanager_patch.md) — NM 1.52.1 への PMF=disable バグ修正パッチ (`+broadcomfix1`) と GNOME GUI 復旧

## 確定済みの原因 (Phase 1 で SSH 経由調査済み)

1. 稼働カーネルが `6.12.85+deb13-amd64` に上がっている (`uname -r` で確認)
2. `linux-headers-amd64` メタパッケージが未インストール。インストール済みのヘッダは `linux-headers-6.12.74+deb13+1-amd64` のみ → **新カーネル用ヘッダ `linux-headers-6.12.85+deb13-amd64` が無い**
3. その結果 `broadcom-sta-dkms` が新カーネル用に `wl.ko` をビルドできていない:
   - `dkms status` → `broadcom-sta/6.30.223.271, 6.12.74+deb13+1-amd64, x86_64: installed` (旧カーネル用のみ)
   - `/lib/modules/6.12.85+deb13-amd64/updates/dkms/` ディレクトリ自体が存在しない
   - `modprobe -n wl` → `Module wl not found in directory /lib/modules/6.12.85+deb13-amd64`
4. `wl` 不在 → `wlp3s0` 未生成 → NetworkManager が WiFi デバイスを認識できず GNOME メニューに表示されない
5. 構造的弱点: **`broadcom-sta-dkms` は `linux-headers-amd64` を Recommends しない**ため、ヘッダメタを明示的に入れていないと DKMS が新カーネルに追従しない

無事な側面 (Phase 1 で再確認済み):
- `network-manager 1.52.1-1+broadcomfix1` / `libnm0 1.52.1-1+broadcomfix1` は `apt-mark showhold` に出ており hold 維持
- `/etc/NetworkManager/conf.d/unmanage-wifi.conf` は不在 (前回ワークアラウンドの残骸なし)
- `wpa_supplicant-nl80211@wlp3s0` と `systemd-networkd` は inactive (NM 経由運用に正しく戻っている)
- 有線 LAN (`enxc8a362e31cd2`) は接続済みなので apt は実行可能
- MacBook Air 2015 は EFI で Secure Boot 非対応 → MOK 署名問題は該当せず

## 修正手順 (推奨アプローチのみ)

すべて `ssh miminashi@macbookair2015.lan` 経由で実施。

### 0. 即時復旧経路の温存 (旧カーネル autoremove 防止)

```bash
sudo apt-mark hold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
apt-mark showhold   # network-manager / libnm0 と上記2つが並ぶこと
```

新カーネルの DKMS ビルドが万一失敗しても、GRUB から旧カーネル `6.12.74+deb13+1-amd64` で起動して即時復旧できるようにしておく。

### 1. ヘッダメタパッケージの恒久投入

```bash
sudo apt-get update
sudo apt-get install -y linux-headers-amd64
```

`linux-headers-amd64` メタを入れることで、現行カーネル用ヘッダ (`linux-headers-6.12.85+deb13-amd64`) を取得し、かつ今後カーネル更新時にもヘッダが自動追従するようになる。

### 2. broadcom-sta-dkms の再ビルドを明示確認 (楽観しない)

`apt install` の post-install hook で `dkms autoinstall` が走ることが多いが、楽観しない。

```bash
sudo dkms status
ls /lib/modules/6.12.85+deb13-amd64/updates/dkms/wl.ko* 2>/dev/null
```

期待: `dkms status` の出力に `broadcom-sta/6.30.223.271, 6.12.85+deb13-amd64, x86_64: installed` が含まれる。**含まれていなければ明示再ビルド**:

```bash
sudo dkms autoinstall -k 6.12.85+deb13-amd64
# 必要なら
sudo dpkg-reconfigure broadcom-sta-dkms
```

ビルド失敗時のログは `/var/lib/dkms/broadcom-sta/6.30.223.271/build/make.log` を `grep -i error` で確認。

### 3. ドライバロード前の競合チェック → ロード

```bash
lsmod | grep -E 'b43|bcma|brcm'                 # 競合ドライバが既ロードでないこと
ls /etc/modprobe.d/ | xargs -I{} grep -l -E 'b43|bcma|brcm|wl' /etc/modprobe.d/{} 2>/dev/null
sudo modprobe wl
ip link show wlp3s0                              # デバイス出現確認
```

### 4. NetworkManager 経由で接続復旧

```bash
nmcli -f WIFI-HW,WIFI general status             # WIFI-HW: enabled になること
rfkill list                                       # ソフト/ハードブロックなしを確認
nmcli device status                              # wlp3s0 が wifi として認識
nmcli connection up OpenWrt                      # 前回作成済みプロファイル
```

### 5. 疎通テスト

```bash
ping -c 3 -I wlp3s0 192.168.1.1                  # ルーター
ping -c 3 -I wlp3s0 8.8.8.8                      # インターネット
```

### 6. GNOME メニュー目視確認 (ユーザ依頼)

ユーザに目視確認を依頼: GNOME 右上のシェルメニューに Wi-Fi の項目が現れ、`OpenWrt` への接続状態が表示されること。

### 7. CLAUDE.md に「操作対象 = ssh 接続先の MacBook Air」を明記

このリポジトリ自体は開発マシン側に置かれており、`report/` 等は開発マシンで管理するが、**実機の状態確認・修正はすべて ssh 経由で `macbookair2015.lan` に対して行う**。今回のように開発マシン側で `nmcli` や `dpkg -l network-manager` を実行しても無関係な情報になる。今後の Claude セッションでも誤らないよう、CLAUDE.md の冒頭近くに「操作対象 (ssh 接続先)」セクションを追加する。

追記する内容 (案):

```markdown
## 操作対象 (ssh 接続先)

このリポジトリは開発マシン上に置かれているが、**運用・修正対象機は別ホストの MacBook Air 11" (Early 2015)** であり、すべての診断・修正コマンドは ssh 経由で実機に対して実行する。

| 項目 | 値 |
|---|---|
| ホスト名 | `macbookair2015.lan` |
| IP (有線) | `192.168.1.145` (DHCP 固定割当) |
| ユーザ | `miminashi` |
| 接続コマンド | `ssh miminashi@macbookair2015.lan` |
| OS | Debian 13 (trixie) |

`nmcli` / `dpkg` / `dmesg` / `dkms` 等の診断は **すべて ssh 越しに実機で実行する**。開発マシン側で実行しても無関係な出力になるので注意。

### サンドボックスから ssh 接続する手順

Claude Code のサンドボックスはネットワーク名前空間を分離しており、デフォルトでは LAN 経路がないため `macbookair2015.lan` への ssh は通らない。次のいずれかの方法で経路を確保する:

- **推奨**: `.claude/settings.local.json` の `sandbox.network.allowedDomains` に `macbookair2015.lan` と `192.168.1.145` を追加
- もしくは `/sandbox` スラッシュコマンドでサンドボックスを一時無効化

### ssh 鍵の運用

- ssh 接続用の鍵はユーザの `~/.ssh/` 配下にある個人鍵を利用する (GitHub deploy key 用の `.ssh/` とは別)
- 鍵の場所や `~/.ssh/config` は Claude では編集しない
```

実装ステップ:
1. `CLAUDE.md` を読んで挿入位置を決める (冒頭の「レポート作成ルール」の前あたりが適切)
2. 上記セクションを `Edit` ツールで追記
3. `git status` で変更確認 → ユーザ依頼があればコミット (本プランでは自動コミットしない)

### 8. レポート作成

`report/yyyy-mm-dd_hhmmss_kernel_dkms_recovery.md` を `TZ=Asia/Tokyo date` 取得のタイムスタンプで作成し、CLAUDE.md のレポート規約に従って以下を記載:

- 過去レポート 2 件へのリンク
- 環境情報 (ホスト, OS, kernel before/after, broadcom-sta-dkms バージョン, NM バージョン)
- 症状・原因分析・修正手順 (再現可能な形)
- 検証結果
- 教訓・予防策セクション:
  - `broadcom-sta-dkms` は `linux-headers-amd64` を Recommends しないため、DKMS モジュール持ちホストではメタを必ず手動投入する運用にする
  - カーネル更新後・**再起動前**に `dkms status` で新 target カーネル分が `installed` になっているか検証する手順
  - 旧カーネルを `apt-mark hold` で保持し、即時復旧経路を温存する運用 (`APT::NeverAutoRemove-Kernels` の代替として)
  - `apt-mark hold` 中の NM パッチパッケージは今回問題に無関係だった旨 (混同防止)
  - Secure Boot 非該当の明記 (MacBook Air 2015 は EFI で Secure Boot 不支持)

このプランファイルを `report/attachment/<レポートファイル名>/plan.md` にコピーして添付。

## 検証チェックリスト

| # | 確認 | 期待結果 |
|---|---|---|
| 1 | `dkms status` | `broadcom-sta/6.30.223.271, 6.12.85+deb13-amd64, x86_64: installed` を含む |
| 2 | `ls /lib/modules/6.12.85+deb13-amd64/updates/dkms/wl.ko*` | 存在する |
| 3 | `lsmod \| grep ^wl` | `wl` がロード済み |
| 4 | `ip link show wlp3s0` | デバイス存在、`state UP` 可能 |
| 5 | `rfkill list` (or `nmcli radio`) | wifi ブロックなし |
| 6 | `nmcli -f WIFI-HW,WIFI general status` | `WIFI-HW: enabled`, `WIFI: enabled` |
| 7 | `nmcli device status` | `wlp3s0  wifi  接続済み  OpenWrt` |
| 8 | `ping -c3 -I wlp3s0 192.168.1.1` / `8.8.8.8` | 全 ICMP 応答 |
| 9 | GNOME シェルメニュー (ユーザ目視) | Wi-Fi 項目表示、OpenWrt 接続中 |

## ロールバック / 即時復旧経路

新カーネル `6.12.85` で `wl` がどうしても動かない場合の即時復旧:

1. GRUB から `6.12.74+deb13+1-amd64` で起動 (旧カーネル `wl.ko` は既存のまま使用可)
2. `apt-mark hold` で `linux-image-6.12.74+deb13+1-amd64` / `linux-headers-6.12.74+deb13+1-amd64` を保護済みなので autoremove で消えない
3. その状態で `make.log` を解析し、必要なら upstream パッチや `broadcom-sta-dkms` 新版を検討
4. 最終手段として前回の wpa_supplicant + systemd-networkd ワークアラウンドに退避 (`unmanage-wifi.conf` 復活)

## Critical Files

実機 (macbookair2015.lan) 上:
- `/lib/modules/6.12.85+deb13-amd64/updates/dkms/wl.ko*` (修正後存在すべき)
- `/var/lib/dkms/broadcom-sta/6.30.223.271/build/make.log` (失敗時の解析対象)
- `/etc/NetworkManager/conf.d/unmanage-wifi.conf` (不在維持確認)
- `/etc/modprobe.d/*.conf` (blacklist 競合確認)
- `/boot/grub/grub.cfg` (旧カーネル起動エントリの存在確認)

開発マシン (このリポジトリ):
- `report/yyyy-mm-dd_hhmmss_kernel_dkms_recovery.md` (新規作成)
- `report/attachment/<レポートファイル名>/plan.md` (このプランを添付)

## 編集 / 実行が必要なコマンド一覧 (まとめ)

```bash
ssh miminashi@macbookair2015.lan
sudo apt-mark hold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
sudo apt-get update
sudo apt-get install -y linux-headers-amd64
sudo dkms status
sudo dkms autoinstall -k 6.12.85+deb13-amd64   # 自動で走っていなければ
sudo modprobe wl
nmcli connection up OpenWrt
ping -c3 -I wlp3s0 8.8.8.8
```

実行は私 (Claude) が SSH 経由で行う想定。`sudo` パスワードが必要な箇所はユーザに対話で入力してもらう (または事前に NOPASSWD 設定があれば自動)。
