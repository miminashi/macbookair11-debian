# NetworkManager WPA-PSK-SHA256 パッチ適用プラン

## Context

MacBook Air 2015 (Debian 13) で WiFi 接続に使用している Broadcom BCM4360 の `wl` ドライバが `WPA-PSK-SHA256` をサポートしていない。NetworkManager 1.52.1 は WPA2+WPA3 トランジションモードの AP に接続する際、ユーザーが `pmf=disable` を設定しても `key_mgmt` に `WPA-PSK-SHA256` を自動追加してしまい、接続に失敗する。

現在のワークアラウンド（NM を回避して wpa_supplicant + systemd-networkd で直接管理）では GNOME GUI から WiFi 操作ができず不便。NM のソースコードを修正してこの問題を解決する。

## バグの詳細

ファイル: `src/core/supplicant/nm-supplicant-config.c`

### バグ1: WPA-PSK-SHA256 が pmf=disable を無視（983-984行目）

```c
// 現状: supplicant の PMF 機能のみチェックし、ユーザー設定を無視
if (_get_capability(priv, NM_SUPPL_CAP_TYPE_PMF))
    g_string_append(key_mgmt_conf, " WPA-PSK-SHA256");
```

**修正:**
```c
if (_get_capability(priv, NM_SUPPL_CAP_TYPE_PMF)
    && pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)
    g_string_append(key_mgmt_conf, " WPA-PSK-SHA256");
```

### バグ2: SAE が STA モードで pmf=disable を無視（1015行目）

```c
// 現状: !is_ap が STA モードで常に true → PMF disable チェックが無効
&& (!is_ap || pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)) {
```

**修正** (upstream main ブランチと同一):
```c
&& (pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)) {
```

## 実装手順

### Step 1: MacBook Air 上でビルド環境を構築

```bash
ssh miminashi@macbookair2015.lan
sudo apt-get build-dep -y network-manager
sudo apt-get install -y quilt devscripts
```

### Step 2: Debian ソースパッケージを取得

```bash
cd /tmp
apt-get source network-manager=1.52.1-1
cd network-manager-1.52.1
```

### Step 3: quilt パッチを追加

```bash
export QUILT_PATCHES=debian/patches
quilt new fix-wpa-psk-sha256-pmf-disable.patch
quilt add src/core/supplicant/nm-supplicant-config.c
```

`src/core/supplicant/nm-supplicant-config.c` に対して上記2箇所の修正を適用後:

```bash
quilt refresh
```

### Step 4: changelog を更新

```bash
dch --local +broadcomfix "Fix WPA-PSK-SHA256 and SAE ignoring pmf=disable (Broadcom wl compat)"
```

→ バージョン: `1.52.1-1+broadcomfix1`

### Step 5: ビルド

**注意**: MacBook Air はメモリ 4GB のため OOM に注意。並列度を制限し、ビルド前にメモリを開放する。

```bash
# ビルド前にキャッシュ開放（OOM 対策）
sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'
# 並列度を2に制限してメモリ消費を抑える
DEB_BUILD_OPTIONS="nocheck parallel=2" dpkg-buildpackage -b -us -uc
```

もし OOM Killer が発動した場合は `parallel=1` で再試行する。

推定ビルド時間: 20-40分 (i5-5250U, 並列度2)

### Step 6: パッチ済みパッケージをインストール

```bash
cd /tmp
sudo dpkg -i network-manager_1.52.1-1+broadcomfix1_amd64.deb libnm0_1.52.1-1+broadcomfix1_amd64.deb
sudo apt-mark hold network-manager libnm0
```

### Step 7: ワークアラウンドを解除し NM で WiFi を管理

```bash
# ワークアラウンドのサービス停止
sudo systemctl stop wpa_supplicant-nl80211@wlp3s0
sudo systemctl disable wpa_supplicant-nl80211@wlp3s0
sudo systemctl stop systemd-networkd
sudo systemctl disable systemd-networkd

# NM にインターフェースを戻す
sudo rm /etc/NetworkManager/conf.d/unmanage-wifi.conf
sudo systemctl restart NetworkManager

# WiFi 接続プロファイル作成 (pmf=disable が鍵)
nmcli connection add type wifi ifname wlp3s0 ssid "OpenWrt" \
  con-name "OpenWrt" \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "meganekkomoemoe" \
  wifi-sec.pmf disable

nmcli connection up "OpenWrt"
```

## 検証方法

1. **key_mgmt 確認**: `sudo journalctl -u NetworkManager --since "5 minutes ago" | grep key_mgmt`
   - 期待: `WPA-PSK` のみ（`WPA-PSK-SHA256` や `SAE` がないこと）
2. **ドライバエラー確認**: `dmesg | grep -i "wl_set_key_mgmt\|invalid cipher"` — 新しいエラーなし
3. **接続確認**: `ping -I wlp3s0 -c3 192.168.1.1 && ping -I wlp3s0 -c3 8.8.8.8`
4. **GNOME GUI 確認**: GNOME Settings > WiFi から OpenWrt に接続できること

## ロールバック手順

```bash
sudo apt-mark unhold network-manager libnm0
sudo apt-get install --reinstall network-manager=1.52.1-1
# ワークアラウンドを再適用（report/2026-04-01_080116_wifi_fix.md 参照）
```

## 重要ファイル

- `src/core/supplicant/nm-supplicant-config.c` — パッチ対象（983-984行, 1015行）
- `/etc/NetworkManager/conf.d/unmanage-wifi.conf` — 削除対象（ワークアラウンド）
- `/etc/wpa_supplicant/wpa_supplicant-nl80211-wlp3s0.conf` — ワークアラウンド設定（残しておいてもよい）

## リスク

- **SSH 切断**: USB Ethernet (`enxc8a362e31cd2`) 経由のため NM 再起動でも影響なし
- **apt upgrade による上書き**: `apt-mark hold` で防止
- **ビルド失敗**: `build-dep` で依存関係は解決済み、ディスク 80GB 空きあり
- **OOM**: メモリ 4GB のため、ビルド並列度を2に制限。OOM 発生時は `parallel=1` に下げて再試行

## レポート作成

作業完了後、CLAUDE.md のレポート作成ルールに従いレポートを作成する。

### レポート内容

- **ファイル名**: `report/yyyy-mm-dd_HHMMSS_networkmanager_patch.md`（タイムスタンプは `date +%Y-%m-%d_%H%M%S` で取得）
- **タイトル**: 「NetworkManager WPA-PSK-SHA256 パッチ適用レポート」
- **セクション構成**:
  1. **前提・目的**: 前回レポート (`report/2026-04-01_080116_wifi_fix.md`) で採用したワークアラウンドの課題と、NM ソースコード修正の動機
  2. **環境情報**: MacBook Air のハードウェア・OS・NM バージョン等
  3. **バグ分析**: `nm-supplicant-config.c` の該当コードの詳細と、upstream main ブランチとの差分
  4. **修正内容**: パッチの具体的な変更内容（diff 付き）
  5. **ビルド・インストール手順**: 再現方法としてのコマンド列
  6. **検証結果**: key_mgmt ログ、dmesg、疎通テスト、GNOME GUI 確認の結果
  7. **参照レポート**: `report/2026-04-01_080116_wifi_fix.md` へのリンク
  8. **添付ファイル**: 本プランファイルを `report/attachment/<レポートファイル名>/plan.md` にコピー

### 添付ファイル

```
report/attachment/yyyy-mm-dd_HHMMSS_networkmanager_patch/
  plan.md  ← /home/miminashi/.claude/plans/crystalline-napping-liskov.md のコピー
```
