# Debian カーネル更新後に消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)

- **実施日時**: 2026年05月05日 00:09 (JST)
- **対象ホスト**: macbookair2015.lan (miminashi@)
- **OS**: Debian GNU/Linux 13 (trixie)
- **障害発生のきっかけ**: 2026年05月04日 23:02 (JST) の Debian アップデート (`packagekit role='update-packages'`) で `linux-image-6.12.85+deb13-amd64` が新規インストールされ、再起動後 `6.12.85+deb13-amd64` で起動

## 添付ファイル

- [実装プラン](attachment/2026-05-05_000905_kernel_dkms_recovery/plan.md)

## 参照レポート

- [MacBook Air 2015 WiFi接続問題 — 調査・修正レポート](2026-04-01_080116_wifi_fix.md) — `wl` の WPA-PSK-SHA256 非対応問題と暫定ワークアラウンド
- [NetworkManager WPA-PSK-SHA256 パッチ適用レポート](2026-04-01_182006_networkmanager_patch.md) — NM 1.52.1 への PMF=disable バグ修正パッチ (`+broadcomfix1`) と GNOME GUI 復旧

## 前提・目的

### 背景

2026-04-01 に MacBook Air 2015 の Broadcom BCM4360 Wi-Fi 問題に対し、NetworkManager 1.52.1 のソースに PMF=disable バグ修正パッチを当てた `+broadcomfix1` パッケージをビルドし、`apt-mark hold` で固定して GNOME GUI から Wi-Fi 操作可能な状態に復旧していた。

### 症状

2026-05-04 の Debian アップデート適用後、再起動すると **GNOME のシェルメニューに Wi-Fi が表示されなくなった**。

- `nmcli -f WIFI-HW general status` → `WIFI-HW: missing`
- `nmcli device status` の出力に `wlp3s0` が現れない
- `lsmod | grep wl` → `wl` モジュールが未ロード
- `ip link show wlp3s0` → `Device "wlp3s0" does not exist`

### 目的

新カーネル `6.12.85+deb13-amd64` 用に `broadcom-sta-dkms` を再ビルドし、`wl.ko` をロードして `wlp3s0` を復旧、NetworkManager (`1.52.1-1+broadcomfix1`) 経由で OpenWrt SSID に再接続して **GNOME GUI から Wi-Fi 操作できる状態に戻す**。同時に、今後カーネル更新で同じ事象が再発しないよう恒久対策を入れる。

## 環境情報

| 項目 | 値 |
|---|---|
| ハードウェア | MacBook Air 11", Early 2015 (Broadwell-U / Apple A1465) |
| Wi-Fi チップ | Broadcom BCM4360 802.11ac Dual Band [PCI 14e4:43a0] (rev 03), PCI 03:00.0 |
| Wi-Fi インターフェース | `wlp3s0` (MAC: 98:e0:d9:8d:20:5d) |
| OS | Debian 13 (trixie) |
| カーネル (障害時稼働) | `6.12.85+deb13-amd64` |
| カーネル (旧・正常) | `6.12.74+deb13+1-amd64` (DKMS ビルド済) |
| broadcom-sta-dkms | 6.30.223.271-26 (Debian trixie 標準) |
| NetworkManager | `1.52.1-1+broadcomfix1` (apt-mark hold 維持) |
| libnm0 | `1.52.1-1+broadcomfix1` (apt-mark hold 維持) |
| wpasupplicant | 2:2.10-24 |
| Secure Boot | **非対応** (MacBook Air 2015 は EFI + Secure Boot 非実装。MOK 署名は dkms 内部で行われるが UEFI 検証は無し) |

## 原因分析

### 直接原因

新カーネル `6.12.85+deb13-amd64` 用の `wl.ko` が存在しない。`/lib/modules/6.12.85+deb13-amd64/updates/dkms/` ディレクトリ自体が無い状態だった。

### 根本原因 (構造的弱点)

1. ホストには `linux-image-amd64` メタパッケージが入っており、Debian 標準の自動更新で新しい `linux-image-6.12.85+deb13-amd64` が引き込まれる
2. 一方で **`linux-headers-amd64` メタパッケージが未インストール** だった (旧カーネル `6.12.74+deb13+1-amd64` のヘッダのみ個別に入っていた)
3. `broadcom-sta-dkms` は `linux-headers-amd64` を `Recommends` していないため、ヘッダメタが入っていない構成だと **新カーネル用ヘッダが自動取得されず、DKMS が新カーネル向けに `wl.ko` をビルドできない**
4. 結果として新カーネル起動時に `wl` が読み込めず、`wlp3s0` 不在 → NetworkManager で WiFi デバイス未検出 → GNOME メニューに Wi-Fi 項目が出ない

### ログ証拠 (修復前)

```
$ uname -r
6.12.85+deb13-amd64

$ dkms status
broadcom-sta/6.30.223.271, 6.12.74+deb13+1-amd64, x86_64: installed
# → 新カーネル分が無い

$ ls /lib/modules/6.12.85+deb13-amd64/updates/dkms/
ls: cannot access ...: No such file or directory

$ modprobe -n -v wl
modprobe: FATAL: Module wl not found in directory /lib/modules/6.12.85+deb13-amd64

$ dpkg -l linux-headers-amd64
un  linux-headers-amd64  <none>   <none>   (description (no description))
# → メタが未インストール

$ nmcli -f WIFI-HW general status
WIFI-HW
missing
```

### 影響範囲外 (確認済みの「無事」な側面)

- `network-manager 1.52.1-1+broadcomfix1` / `libnm0 1.52.1-1+broadcomfix1` は `apt-mark showhold` に出ており hold 維持 → **過去の NM パッチ作業 (broadcomfix1) は今回の障害と無関係**
- `/etc/NetworkManager/conf.d/unmanage-wifi.conf` は不在 (前回 wpa_supplicant ワークアラウンドの残骸なし)
- `wpa_supplicant-nl80211@wlp3s0` と `systemd-networkd` は inactive (NM 経由運用に正しく戻っている)
- `/etc/modprobe.d/broadcom-sta{,-dkms}.conf` の `b43` / `bcma` / `brcm80211` blacklist は適切に有効 (競合なし)
- 有線 LAN (`enxc8a362e31cd2`) は接続済みで apt 実行可能

## 再現方法 (修正手順)

すべて開発マシンから ssh 経由で実機 (`macbookair2015.lan`) 上で実行。

### 0. 即時復旧経路の温存 (旧カーネル autoremove 防止)

```bash
ssh miminashi@macbookair2015.lan
sudo apt-mark hold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
apt-mark showhold
# 期待: libnm0 / linux-headers-6.12.74+deb13+1-amd64 / linux-image-6.12.74+deb13+1-amd64 / network-manager
```

新カーネルの DKMS ビルドが万一失敗しても GRUB から旧カーネルで起動して即時復旧できるよう、ビルド済みの旧カーネルを `apt autoremove` の対象から外す。

### 1. ヘッダメタパッケージの恒久投入

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y linux-headers-amd64
```

`linux-headers-amd64` メタを入れることで、現行カーネル用ヘッダ `linux-headers-6.12.85+deb13-amd64` を取得し、かつ今後カーネル更新時にもヘッダが自動追従する。

post-install hook (`/etc/kernel/header_postinst.d/dkms`) によりこの段階で `broadcom-sta` が自動再ビルドされた:

```
Autoinstall of module broadcom-sta/6.30.223.271 for kernel 6.12.85+deb13-amd64 (x86_64)
Building module(s).... done.
Signing module /var/lib/dkms/broadcom-sta/6.30.223.271/build/wl.ko
Installing /lib/modules/6.12.85+deb13-amd64/updates/dkms/wl.ko.xz
Running depmod..... done.
Autoinstall on 6.12.85+deb13-amd64 succeeded for module(s) broadcom-sta.
```

### 2. DKMS 再ビルドの明示確認

```bash
sudo dkms status
ls /lib/modules/6.12.85+deb13-amd64/updates/dkms/
```

期待 (実測):

```
broadcom-sta/6.30.223.271, 6.12.74+deb13+1-amd64, x86_64: installed
broadcom-sta/6.30.223.271, 6.12.85+deb13-amd64, x86_64: installed
-rw-r--r-- 1 root root 1511420  5月  5 00:07 wl.ko.xz
```

(自動ビルドが走っていなかった場合は `sudo dkms autoinstall -k 6.12.85+deb13-amd64`、ビルド失敗時は `/var/lib/dkms/broadcom-sta/6.30.223.271/build/make.log` を `grep -i error` で解析する。)

### 3. 競合チェック → wl ドライバロード

```bash
lsmod | grep -E '^b43|^bcma|^brcm'   # 競合ドライバ未ロードであること
grep -rE 'b43|bcma|brcm|^blacklist wl|^install wl' /etc/modprobe.d/   # blacklist 把握
sudo modprobe wl
lsmod | grep '^wl'
ip -d link show wlp3s0
```

### 4. NetworkManager 経由で接続復旧

modprobe 直後、NetworkManager が自動で前回作成済みプロファイル `OpenWrt` を起動する (今回はこれだけで接続成立)。

```bash
nmcli -f WIFI-HW,WIFI,STATE,CONNECTIVITY general status
nmcli radio
nmcli device status
```

自動接続されない場合は `nmcli connection up OpenWrt` を明示実行する。

### 5. 疎通テスト

```bash
ip -4 addr show wlp3s0 | grep inet
nmcli -f IN-USE,SSID,SIGNAL,RATE,SECURITY device wifi list ifname wlp3s0
ping -c3 -I wlp3s0 8.8.8.8
GW=$(ip route show dev wlp3s0 | awk '/default/ {print $3; exit}')
ping -c3 -I wlp3s0 "$GW"
```

### 6. GNOME メニュー目視確認 (ユーザ目視)

GNOME 右上のシェルメニューに Wi-Fi 項目が表示され、`OpenWrt` への接続状態が見えること。

## 検証結果

### DKMS / モジュール

```
$ sudo dkms status
broadcom-sta/6.30.223.271, 6.12.74+deb13+1-amd64, x86_64: installed
broadcom-sta/6.30.223.271, 6.12.85+deb13-amd64, x86_64: installed

$ ls /lib/modules/6.12.85+deb13-amd64/updates/dkms/
合計 1484
-rw-r--r-- 1 root root 1511420  5月  5 00:07 wl.ko.xz

$ lsmod | grep '^wl'
wl                   6459392  0
```

### インターフェースと NetworkManager 状態

```
$ ip -d link show wlp3s0 | head -2
3: wlp3s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
    link/ether 98:e0:d9:8d:20:5d ...

$ nmcli -f WIFI-HW,WIFI,STATE,CONNECTIVITY general status
WIFI-HW  WIFI  STATE     CONNECTIVITY 
有効     有効  接続済み  完全         

$ nmcli device status
DEVICE             TYPE      STATE            CONNECTION
enxc8a362e31cd2    ethernet  接続済み         Wired connection 1
wlp3s0             wifi      接続済み         OpenWrt
```

### SSID と疎通

```
$ nmcli -f IN-USE,SSID,SIGNAL,RATE,SECURITY device wifi list ifname wlp3s0
IN-USE  SSID                  SIGNAL  RATE        SECURITY
*       OpenWrt               100     270 Mbit/s  WPA2 WPA3

$ ip -4 addr show wlp3s0 | grep inet
    inet 192.168.33.145/24 brd 192.168.33.255 scope global dynamic noprefixroute wlp3s0

$ ping -c3 -W2 -I wlp3s0 192.168.33.1
3 packets transmitted, 2 received, ... rtt avg 2.98 ms

$ ping -c3 -W2 -I wlp3s0 8.8.8.8
3 packets transmitted, 3 received, 0% packet loss
rtt min/avg/max/mdev = 30.381/32.167/35.268/2.200 ms
```

| 検証項目 | 期待 | 実測 | 結果 |
|---|---|---|---|
| `dkms status` に新カーネル分 | あり | あり | ✅ |
| `wl.ko.xz` 配置 | `/lib/modules/6.12.85+deb13-amd64/updates/dkms/` | あり | ✅ |
| `lsmod` の wl | ロード済み | ロード済み (6459392 bytes) | ✅ |
| `ip link wlp3s0` | UP | UP, LOWER_UP | ✅ |
| `nmcli WIFI-HW` | 有効 | 有効 | ✅ |
| `nmcli device wlp3s0` | OpenWrt 接続済み | OpenWrt 接続済み | ✅ |
| ping ゲートウェイ | 応答あり | 192.168.33.1 へ avg 2.98 ms | ✅ |
| ping インターネット | 応答あり | 8.8.8.8 へ avg 32.2 ms | ✅ |

(注: 旧レポートの `192.168.1.145/24` から `192.168.33.145/24` にサブネットが変わっている。これは `OpenWrt` AP 側のネットワーク構成変更によるもので、本修復作業とは独立。本修復の検証としてはゲートウェイ・インターネットへの疎通成立をもって完了とする。)

## 教訓・予防策

### 1. DKMS モジュールを使うホストでは `linux-headers-amd64` メタを必ず入れる

- `broadcom-sta-dkms` (および多くの out-of-tree DKMS パッケージ) は `linux-headers-amd64` を **Recommends していない**
- `linux-image-amd64` メタだけ入っていてヘッダメタが無い構成では、カーネル更新に DKMS が追従できず、再起動後に該当モジュールが消える
- 今後同様の MacBook Air を再構築する場合 / 別の DKMS 利用ホストを構築する場合は、初期セットアップ時に必ず:
  ```bash
  sudo apt-get install -y linux-image-amd64 linux-headers-amd64
  ```
  をペアで入れる

### 2. カーネル更新後・再起動前の検証手順

`apt upgrade` でカーネル更新があった場合、**再起動前** に DKMS の状態を確認するワンライナーを定着させる:

```bash
sudo dkms status
# 全 target カーネル × 全 DKMS モジュールについて "installed" になっていることを確認
```

`installed` でない行があれば、その状態で再起動すると該当機能が消えるので、再起動前に手動で `sudo dkms autoinstall -k <kernel>` を実行する。

### 3. 旧カーネルを一時 hold して即時復旧経路を温存する

DKMS ビルドや新カーネル自体に問題があった場合の即時復旧として、GRUB から旧カーネルで起動できる状態を維持しておく:

```bash
sudo apt-mark hold linux-image-<old> linux-headers-<old>
```

`apt autoremove` で古いカーネルが消されると即時復旧経路が無くなるため、新カーネルでの正常稼働を一定期間確認するまでは hold しておく。問題が無いと確認できたら hold を外す。

### 4. apt-mark hold 中の NM パッケージは今回の障害とは無関係

`network-manager 1.52.1-1+broadcomfix1` と `libnm0 1.52.1-1+broadcomfix1` は前回 (2026-04-01) のパッチ適用以来 hold で固定しており、今回の障害には一切寄与していない。今後類似の障害発生時に「NM パッチが原因では?」と誤って疑わないこと。

### 5. Secure Boot 非該当の確認

MacBook Air 2015 は EFI で Secure Boot 非対応のため、DKMS の MOK 署名は実質的な検証を伴わない (生成された `mok.key` / `mok.pub` は使われない)。Secure Boot 環境のホストへ手順を流用する場合は別途 MOK enroll が必要。

## 今後の留意事項

- `network-manager` / `libnm0` の hold は **継続維持** する。upstream に PMF=disable バグ修正が取り込まれた版がリリースされるまで解除しない (前回レポート参照)
- 旧カーネル (`6.12.74+deb13+1-amd64`) の hold は、新カーネル `6.12.85` が一定期間 (数週間程度) 安定稼働すれば解除してよい:
  ```bash
  sudo apt-mark unhold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
  ```
- 今後カーネル更新があった場合は、`apt upgrade` 直後 (再起動前) に必ず `sudo dkms status` で全 DKMS モジュールが新カーネルに対し `installed` になっていることを確認する
