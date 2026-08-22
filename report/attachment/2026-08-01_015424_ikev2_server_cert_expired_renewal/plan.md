# IKEv2 (GSNet VPN) 接続不能の修正プラン

## Context

2026-08-01 未明から MacBook Air (Debian 13) の GNOME GUI から IKEv2 VPN「GSNet」(サーバ k.or6.jp = 160.16.210.47) に接続できなくなった。

**原因 (調査済み・確定)**: サーバ証明書 `CN=160.16.210.47` の有効期限切れ。

- クライアント側 charon-nm ログ (macbookair2015, 8/1 01:31:30):
  ```
  subject certificate invalid (valid from Jul 31 02:03:48 2021 to Jul 30 02:03:48 2026)
  no trusted RSA public key found for '160.16.210.47'
  → generating INFORMATIONAL request 2 [ N(AUTH_FAILED) ]
  ```
- サーバ実物 `/etc/ipsec.d/certs/server-cert.pem`: notAfter = **Jul 29 17:03:48 2026 GMT (= JST 7/30 02:03)** → 期限切れ
- CA 証明書 `CN=GSNet mmns CA` は **2031-07-28 まで有効** (クライアント側 `~/ca-cert.pem`・サーバ側とも同一) → CA・クライアント設定は変更不要
- サーバ側の EAP 認証設定 (`rightauth=eap-mschapv2`) やネットワークは正常 (IKE_SA_INIT〜EAP 開始まで進んでいる)

**修正方針**: サーバ (k.or6.jp) 上で、既存の CA 鍵 (`~/pki/private/ca-key.pem`) と既存のサーバ鍵 (`~/pki/private/server-key.pem`) を使ってサーバ証明書だけ再発行し、`/etc/ipsec.d/certs/` に配置して strongswan に再読込させる。鍵は再利用するので `/etc/ipsec.d/private/` と `ipsec.secrets` は変更不要。

発行手順は 2021 年の初回構築時と同じ (`~/.bash_history` に記録あり)。lifetime は CA の残存期間内に収まる **1820 日** (~2031-07-26) とする。

## 環境

| 項目 | 値 |
|---|---|
| サーバ | k.or6.jp (Ubuntu, user: ubuntu, ssh 鍵認証で接続可) |
| サーバ sudo | **パスワード必要** (NOPASSWD ではない) |
| CA 鍵 / サーバ鍵 | `~/pki/private/ca-key.pem` / `~/pki/private/server-key.pem` (ubuntu 所有、sudo 不要で読める) |
| 配置先 | `/etc/ipsec.d/certs/server-cert.pem` (root 所有 → sudo 必要) |
| クライアント | macbookair2015.lan、NM 接続名 `GSNet` (uuid 55a75765-…) |

## 実施手順

### 1. サーバ証明書の再発行 (sudo 不要、ubuntu のまま)

```bash
ssh k.or6.jp
# 旧証明書のバックアップ
cp ~/pki/certs/server-cert.pem ~/pki/certs/server-cert.pem.bak-20260801

pki --pub --in ~/pki/private/server-key.pem --type rsa \
  | pki --issue --lifetime 1820 \
      --cacert ~/pki/cacerts/ca-cert.pem \
      --cakey ~/pki/private/ca-key.pem \
      --dn "CN=160.16.210.47" --san 160.16.210.47 \
      --flag serverAuth --flag ikeIntermediate --outform pem \
  > ~/pki/certs/server-cert.pem

# 検証: notAfter が 2031 年、SAN に IP が入っていること
openssl x509 -in ~/pki/certs/server-cert.pem -noout -subject -dates -ext subjectAltName
openssl verify -CAfile ~/pki/cacerts/ca-cert.pem ~/pki/certs/server-cert.pem
# 鍵と一致すること (modulus 比較)
openssl x509 -in ~/pki/certs/server-cert.pem -noout -pubkey | sha256sum
openssl rsa -in ~/pki/private/server-key.pem -pubout 2>/dev/null | sha256sum
```

※ `pki` コマンドが PATH に無ければ `/usr/bin/pki` (strongswan-pki パッケージ)。

### 2. 配置と再読込 (sudo 必要 → tmux ペインでユーザがパスワード入力)

サーバの sudo はパスワード必須のため、**tmux でペインを split して実行し、パスワードはユーザが入力する** (Claude Code は tmux session 3 内で稼働確認済み):

```bash
tmux split-window -v "ssh -t k.or6.jp '\
  sudo cp /etc/ipsec.d/certs/server-cert.pem /etc/ipsec.d/certs/server-cert.pem.bak-20260801 && \
  sudo cp ~/pki/certs/server-cert.pem /etc/ipsec.d/certs/server-cert.pem && \
  sudo ipsec rereadcerts && sudo ipsec reload && \
  echo DONE; read -p \"Enterで閉じる\"'"
```

- ペインが開いたらユーザが sudo パスワードを入力 → `DONE` 表示を確認
- Claude 側は実行後、`/etc/ipsec.d/certs/server-cert.pem` の notAfter を read-only で確認して反映を検証する

(rereadcerts で反映されない場合のフォールバック: `sudo ipsec restart` — 数秒の断のみ)

### 3. 動作検証 (e2e)

```bash
# クライアント (macbookair2015) から接続
ssh miminashi@macbookair2015.lan 'nmcli con up GSNet'
# 確認: VPN トンネル確立・経路
ssh miminashi@macbookair2015.lan 'nmcli con show --active | grep -i gsnet; ip a show | grep 192.168.83'
# サーバ側ログで established を確認
ssh k.or6.jp 'journalctl -u strongswan-starter --since "-5 min" | tail -20'
```

成功条件: charon-nm 側で `IKE_SA GSNet established`、クライアントに 192.168.83.0/24 のアドレスが付与される。

### 4. レポート作成

`report/` に本件の調査・修正レポートを作成 (CLAUDE.md のレポートルールに従う。プランファイル添付、タイムスタンプは `TZ=Asia/Tokyo date` で取得)。

## 変更しないもの

- クライアント側の NM 接続設定・`~/ca-cert.pem` (CA は 2031 年まで有効)
- サーバの `/etc/ipsec.conf`・`/etc/ipsec.secrets`・サーバ秘密鍵
- `/var/www/html/ca-cert.pem` (CA 配布用、変更不要)

## 備考

- 次回期限は 2031 年 (CA と同時期)。CA ごと更新が必要になる旨をレポートに記載しておく。
- サーバ sudo がパスワード必須なため、手順 2 は tmux ペインを split して実行し、パスワード入力のみユーザが行う。
