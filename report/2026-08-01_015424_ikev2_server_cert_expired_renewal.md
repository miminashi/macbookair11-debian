# IKEv2 VPN が繋がらなくなった件 — サーバ証明書の期限切れを再発行で解消

- **実施日時**: 2026年8月1日 01:35〜01:54 (JST)

## 概要

MacBook Air の GNOME から IKEv2 VPN「GSNet」への接続が 2026 年 8 月 1 日未明から失敗するようになった。サーバ側のログでは EAP 認証の開始直後にクライアントから AUTH_FAILED が返っており、一見クライアント側の認証失敗に見える状況だった。

クライアント (MacBook) 側の charon-nm ログを確認したところ、原因は一目で確定した。サーバが提示した証明書 `CN=160.16.210.47` の有効期限が 2026 年 7 月 30 日 02:03 (JST) で切れており、クライアントが「subject certificate invalid」として接続を拒否していた。サーバログに残っていた AUTH_FAILED は、クライアントが検証失敗を通知したものである。この VPN サーバは 2021 年 7 月末に構築されており、当時 5 年 (1825 日) で発行したサーバ証明書がちょうど満期を迎えた形になる。

幸い、CA 証明書 (`CN=GSNet mmns CA`) は 2031 年まで有効で、サーバ上には構築当時の CA 秘密鍵とサーバ秘密鍵がそのまま残っていた。そこで、既存の鍵を再利用してサーバ証明書だけを再発行し、strongswan に読み込ませる方針をとった。鍵を変えないため、クライアント側の設定 (CA 証明書や接続プロファイル) には一切手を入れずに済む。

再発行と配置は問題なく完了したが、`ipsec rereadcerts` と `ipsec reload` ではメモリ上の旧証明書が入れ替わらず、サーバは古い証明書を送り続けた。`ipsec restart` で完全再起動したところ新証明書が有効になり、MacBook からの接続は EAP-MSCHAPv2 認証・仮想 IP 割り当て・トンネル経由の外部疎通まで全て正常に復旧した。

新しい証明書の期限は 2031 年 7 月 25 日で、CA 証明書の期限 (2031 年 7 月 28 日) とほぼ同時に切れる。次回は証明書だけでなく CA ごと更新する必要があり、その際はクライアント側の CA 証明書 (`~/ca-cert.pem`) の差し替えも必要になる点に注意。

## 前提・目的

- 背景: 2026-08-01 未明、MacBook Air (Debian 13) の GNOME GUI から IKEv2 VPN「GSNet」に接続できなくなった
- 目的: 原因を特定し、接続を復旧する
- 前提条件:
  - クライアント: macbookair2015.lan (ssh 可、sudo NOPASSWD)
  - サーバ: k.or6.jp = 160.16.210.47 (ssh 可、sudo はパスワード必須)

## 環境情報

| 項目 | 値 |
|---|---|
| クライアント | MacBook Air 11" (Early 2015), Debian 13, NetworkManager + charon-nm (strongswan) |
| クライアント接続設定 | NM 接続名 `GSNet` (uuid 55a75765-d99e-4bc5-a05c-78b38cdefd19)、CA=`~/ca-cert.pem` |
| サーバ | k.or6.jp (160.16.210.47)、Ubuntu、strongswan (ipsec.conf / stroke 系構成) |
| サーバ VPN 設定 | `/etc/ipsec.conf` conn ikev2-vpn: leftcert=server-cert.pem, rightauth=eap-mschapv2, rightsourceip=192.168.83.0/24 |
| PKI 資材 | サーバの `~/pki/` (CA 鍵・サーバ鍵・証明書、2021-07-31 構築時のもの) |

## 原因

**サーバ証明書 `CN=160.16.210.47` の有効期限切れ** (notAfter = 2026-07-29 17:03:48 GMT = JST 7/30 02:03)。

クライアント側 charon-nm ログ (2026-08-01 01:31:30 JST):

```
04[CFG]   using certificate "CN=160.16.210.47"
04[CFG]   using trusted ca certificate "CN=GSNet mmns CA"
04[CFG] subject certificate invalid (valid from Jul 31 02:03:48 2021 to Jul 30 02:03:48 2026)
04[IKE] no trusted RSA public key found for '160.16.210.47'
04[ENC] generating INFORMATIONAL request 2 [ N(AUTH_FAILED) ]
```

- サーバログの `parsed INFORMATIONAL request 2 [ N(AUTH_FAILED) ]` は、この**クライアント側の証明書検証失敗の通知**
- CA 証明書は 2031-07-28 まで有効 (クライアント・サーバとも同一) → CA・クライアント設定は無関係
- IKE_SA_INIT〜EAP-ID 要求までは正常に進行しており、ネットワーク・EAP 設定にも問題なし

## 対応内容

1. **サーバ証明書の再発行** (k.or6.jp、ubuntu ユーザ、sudo 不要):
   既存のサーバ鍵 `~/pki/private/server-key.pem` と CA 鍵 `~/pki/private/ca-key.pem` を再利用し、2021 年構築時と同じ `pki --issue` 手順で lifetime 1820 日 (CA の残存期間内) で再発行。旧証明書は `server-cert.pem.bak-20260801` としてバックアップ。
   - 新証明書: notBefore 2026-07-31 / notAfter **2031-07-25** (GMT)、SAN=IP:160.16.210.47
   - `openssl verify` (CA チェーン) OK、公開鍵ハッシュがサーバ鍵と一致することを確認
2. **配置** (sudo、tmux ペインでユーザがパスワード入力): `/etc/ipsec.d/certs/server-cert.pem` を新証明書で置換 (旧版は同ディレクトリに `.bak-20260801` で保存)
3. **`ipsec rereadcerts` + `ipsec reload` では反映されず** — 配置後もサーバはメモリ上の旧証明書を送信し続け、クライアントは同じ検証エラーで失敗した
4. **`sudo ipsec restart` で解消** — 完全再起動後、新証明書が有効になった

クライアント側・サーバ側とも設定ファイル・鍵の変更は無し (変更したのはサーバ証明書ファイル 1 つのみ)。

## 検証結果 (すべて green)

| 項目 | 結果 |
|---|---|
| `nmcli con up GSNet` (クライアント) | 成功 (「接続が正常にアクティベートされました」) |
| サーバ側 IKE ログ | `EAP method EAP_MSCHAPV2 succeeded` → `IKE_SA ikev2-vpn[1] established` → `assigning virtual IP 192.168.83.1` → `CHILD_SA established` |
| クライアント側トンネル | `nm-xfrm-*` インタフェースに 192.168.83.1/32 付与 |
| トンネル経由の外部疎通 | `curl https://ifconfig.me` → `160.16.210.47` (VPN サーバ経由で出ている) |

## 再現方法 (今後の証明書更新手順)

1. サーバで証明書を再発行 (sudo 不要):
   ```bash
   ssh k.or6.jp
   cp ~/pki/certs/server-cert.pem ~/pki/certs/server-cert.pem.bak-$(date +%Y%m%d)
   pki --pub --in ~/pki/private/server-key.pem --type rsa \
     | pki --issue --lifetime 1820 \
         --cacert ~/pki/cacerts/ca-cert.pem \
         --cakey ~/pki/private/ca-key.pem \
         --dn "CN=160.16.210.47" --san 160.16.210.47 \
         --flag serverAuth --flag ikeIntermediate --outform pem \
     > ~/pki/certs/server-cert.pem
   openssl x509 -in ~/pki/certs/server-cert.pem -noout -dates
   openssl verify -CAfile ~/pki/cacerts/ca-cert.pem ~/pki/certs/server-cert.pem
   ```
2. 配置と再起動 (sudo 必要):
   ```bash
   sudo cp ~/pki/certs/server-cert.pem /etc/ipsec.d/certs/server-cert.pem
   sudo ipsec restart   # rereadcerts / reload では反映されない (本件で実証)
   ```
3. クライアントから接続確認:
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo nmcli con up GSNet'
   ```
   (非 sudo の `nmcli con up` は ssh セッションからだと polkit で "Not authorized to control networking" になる)

## 教訓・注意点

- **strongswan (stroke 系) は証明書ファイルを置き換えても `ipsec rereadcerts` + `ipsec reload` ではメモリ上の証明書が入れ替わらない**ことがある。確実なのは `ipsec restart` (数秒の断のみ)
- サーバログの `AUTH_FAILED` はサーバ自身の失敗とは限らない。今回のようにクライアントの証明書検証失敗の通知でもあり得るため、**必ずクライアント側 (charon-nm) のログも見る**
- **次回期限: 2031-07-25 (サーバ証明書) / 2031-07-28 (CA)** — ほぼ同時に切れるため、次回は CA ごと更新し、クライアントの `~/ca-cert.pem` と `/var/www/html/ca-cert.pem` (配布用) の差し替えも必要

## 添付ファイル

- [実装プラン](attachment/2026-08-01_015424_ikev2_server_cert_expired_renewal/plan.md)
