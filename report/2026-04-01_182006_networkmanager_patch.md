# NetworkManager WPA-PSK-SHA256 パッチ適用レポート

- **実施日時**: 2026年4月1日 18:20 (JST)
- **対象ホスト**: macbookair2015.lan (miminashi@)
- **OS**: Debian GNU/Linux 13 (trixie), kernel 6.12.74+deb13+1-amd64

## 添付ファイル

- [実装プラン](attachment/2026-04-01_182006_networkmanager_patch/plan.md)

## 参照レポート

- [MacBook Air 2015 WiFi接続問題 — 調査・修正レポート](2026-04-01_080116_wifi_fix.md) — 本作業の前提となるワークアラウンド

## 前提・目的

前回レポートにて、NetworkManager を回避し wpa_supplicant + systemd-networkd で直接 WiFi を管理するワークアラウンドを適用した。このワークアラウンドにより WiFi 接続は可能になったが、GNOME の GUI から WiFi 操作ができないという課題が残っていた。

本作業では NetworkManager のソースコードを修正し、`pmf=disable` 設定が `key_mgmt` に正しく反映されるようにすることで、NetworkManager 経由での WiFi 接続を復旧する。

## 環境情報

| 項目 | 値 |
|---|---|
| WiFiチップ | Broadcom BCM4360 802.11ac Dual Band (rev 03) |
| ドライバ | `wl` (broadcom-sta-dkms 6.30.223.271-26) |
| インターフェース | `wlp3s0` |
| NetworkManager（修正前） | 1.52.1-1 |
| NetworkManager（修正後） | 1.52.1-1+broadcomfix1 |
| wpa_supplicant | 2:2.10-24 |
| ビルド環境 | MacBook Air 本体 (i5-5250U, 4GB RAM, Debian 13) |

## バグ分析

### 問題のコード

ファイル: `src/core/supplicant/nm-supplicant-config.c`（関数 `nm_supplicant_config_add_setting_wireless_security`）

#### バグ1: WPA-PSK-SHA256 が pmf=disable を無視（983-984行目）

```c
if (_get_capability(priv, NM_SUPPL_CAP_TYPE_PMF))
    g_string_append(key_mgmt_conf, " WPA-PSK-SHA256");
```

supplicant の PMF 機能の有無のみチェックし、ユーザーの PMF 設定（`pmf=disable`）を無視していた。このため `key_mgmt=WPA-PSK WPA-PSK-SHA256` が wpa_supplicant に渡され、`wl` ドライバが `ERROR @wl_set_key_mgmt : invalid cipher group (1027076)` で失敗していた。

**このバグは upstream main ブランチ（1.57.4-dev）にも存在する。**

#### バグ2: SAE が STA モードで pmf=disable を無視（1015行目）

```c
&& (!is_ap || pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)) {
```

`!is_ap` が STA モードで常に `true` となるため、PMF disable チェックが STA モードでは無効化されていた。

**このバグは upstream main ブランチでは修正済み**（`(!is_ap || ...)` → `(...)` に簡略化）。

### PMF パラメータの流れ

1. ユーザー設定: `nmcli connection modify OpenWrt wifi-sec.pmf disable`
2. `nm-device-wifi.c:2981`: `nm_setting_wireless_security_get_pmf()` で設定値を取得
3. `nm-device-wifi.c:3012`: `nm_supplicant_config_add_setting_wireless_security()` に `pmf` パラメータとして渡す
4. `nm-supplicant-config.c:983`: **ここで `pmf` 値が無視されていた（バグ1）**

## 修正内容

### パッチ（diff）

```diff
--- a/src/core/supplicant/nm-supplicant-config.c
+++ b/src/core/supplicant/nm-supplicant-config.c
@@ -980,7 +980,8 @@ nm_supplicant_config_add_setting_wireles
     } else if (nm_streq(key_mgmt, "wpa-psk")) {
         if (pmf != NM_SETTING_WIRELESS_SECURITY_PMF_REQUIRED)
             g_string_append(key_mgmt_conf, "WPA-PSK");
-        if (_get_capability(priv, NM_SUPPL_CAP_TYPE_PMF))
+        if (_get_capability(priv, NM_SUPPL_CAP_TYPE_PMF)
+            && pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)
             g_string_append(key_mgmt_conf, " WPA-PSK-SHA256");
         if (!is_ap && _get_capability(priv, NM_SUPPL_CAP_TYPE_FT))
             g_string_append(key_mgmt_conf, " FT-PSK");
@@ -1012,7 +1013,7 @@ nm_supplicant_config_add_setting_wireles
         if (_get_capability(priv, NM_SUPPL_CAP_TYPE_SAE)
             && _get_capability(priv, NM_SUPPL_CAP_TYPE_PMF)
             && _get_capability(priv, NM_SUPPL_CAP_TYPE_BIP)
-            && (!is_ap || pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)) {
+            && (pmf != NM_SETTING_WIRELESS_SECURITY_PMF_DISABLE)) {
             g_string_append(key_mgmt_conf, " SAE");
             if (!is_ap && _get_capability(priv, NM_SUPPL_CAP_TYPE_FT))
                 g_string_append(key_mgmt_conf, " FT-SAE");
```

### 修正の効果

`pmf=disable` を設定した場合の `key_mgmt` 値:

| | 修正前 | 修正後 |
|---|---|---|
| key_mgmt | `WPA-PSK WPA-PSK-SHA256 FT-PSK SAE FT-SAE` | `WPA-PSK FT-PSK` |
| ieee80211w | `0` | `0` |

## ビルド・インストール手順（再現方法）

### 1. ビルド環境構築

```bash
sudo apt-get build-dep -y network-manager
sudo apt-get install -y quilt devscripts
```

### 2. ソースパッケージ取得

```bash
cd /tmp
apt-get source network-manager=1.52.1-1
```

### 3. パッチ作成

```bash
cd /tmp/network-manager-1.52.1
export QUILT_PATCHES=debian/patches
quilt new fix-wpa-psk-sha256-pmf-disable.patch
quilt add src/core/supplicant/nm-supplicant-config.c
# 上記 diff の2箇所を修正
quilt refresh
```

### 4. changelog 更新

```bash
DEBEMAIL="local@macbookair2015.lan" DEBFULLNAME="Local Build" \
  dch --local +broadcomfix "Fix WPA-PSK-SHA256 and SAE ignoring pmf=disable (Broadcom wl compat)"
```

### 5. ビルド（OOM 対策で parallel=2）

```bash
sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'
DEB_BUILD_OPTIONS="nocheck parallel=2" dpkg-buildpackage -b -us -uc
```

### 6. インストール

```bash
sudo dpkg -i /tmp/network-manager_1.52.1-1+broadcomfix1_amd64.deb \
              /tmp/libnm0_1.52.1-1+broadcomfix1_amd64.deb
sudo apt-mark hold network-manager libnm0
```

### 7. ワークアラウンド解除と WiFi 接続設定

```bash
sudo systemctl stop wpa_supplicant-nl80211@wlp3s0
sudo systemctl disable wpa_supplicant-nl80211@wlp3s0
sudo systemctl stop systemd-networkd
sudo systemctl disable systemd-networkd
sudo rm /etc/NetworkManager/conf.d/unmanage-wifi.conf
sudo systemctl restart NetworkManager
sudo nmcli device set wlp3s0 managed yes
sudo nmcli connection add type wifi ifname wlp3s0 ssid "OpenWrt" \
  con-name "OpenWrt" wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "meganekkomoemoe" wifi-sec.pmf disable
sudo nmcli connection up "OpenWrt"
```

## 検証結果

### key_mgmt 確認

```
Config: added 'key_mgmt' value 'WPA-PSK'
Config: added 'psk' value '<hidden>'
Config: added 'ieee80211w' value '0'
```

`WPA-PSK-SHA256` および `SAE` が key_mgmt から除外されていることを確認。

### ドライバエラー確認

パッチ適用後（18:16以降）に `ERROR @wl_set_key_mgmt` / `invalid cipher group` の新規エラーは発生していない。

### 接続状態

```
DEVICE             TYPE      STATE            CONNECTION
enxc8a362e31cd2    ethernet  接続済み         Wired connection 1
wlp3s0             wifi      接続済み         OpenWrt
```

### 疎通テスト

| 宛先 | 結果 |
|---|---|
| 192.168.1.1 (ルーター) | 2/3 received, avg 3.1ms |
| 8.8.8.8 (Internet) | 3/3 received, avg 227ms |

## 今後の留意事項

- `apt-mark hold` により `network-manager` と `libnm0` のアップグレードを保留中
- upstream にバグ1の修正が取り込まれた Debian パッケージがリリースされたら、hold を解除してアップグレードする:
  ```bash
  sudo apt-mark unhold network-manager libnm0
  sudo apt-get upgrade
  ```
- バグ1（WPA-PSK-SHA256）は upstream main にも存在するため、upstream への報告を検討すべき
