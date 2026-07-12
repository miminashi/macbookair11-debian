# ハウスキーピング実施プラン (NEXT_SESSION.md ベース)

## Context

Phase C-9 で hang 調査はクローズ済みで、実機 (macbookair2015.lan) は stock 6.12.95 + udev 保護で soak 中。前セッションが残したディスク整理 (旧カーネル 26 パッケージの autoremove、役割を終えた dpmwd1-3 の purge、6.12.74 の hold 解除+削除) を NEXT_SESSION.md の手順どおり実施する。hang 対策には一切触らない。所要 ~10 分、再起動不要。

ユーザ確認済み: **6.12.94 stock はフォールバックとして残す** (手順 1 を実施)。

## 前提

- 全コマンドは `ssh miminashi@macbookair2015.lan '...'` で実機に対して実行 (sudo NOPASSWD)
- サンドボックスは LAN 経路がないため、ssh 実行時はサンドボックス外実行 (dangerouslyDisableSandbox) を用いる

## 実施手順 (NEXT_SESSION.md のコマンドをそのまま使用)

1. **6.12.94 を manual マーク** (autoremove より先):
   `sudo apt-mark manual linux-image-6.12.94+deb13-amd64`
2. **autoremove**: まず `apt-get -s autoremove | grep ^Remv` で対象を再確認し、6.12.94 image が対象から外れていること・dpmwd 系が含まれないことを目視してから `apt-get -y autoremove`
3. **dpmwd1-3 purge** (dpmwd4 は再演用に残置):
   `linux-image/headers-6.12.94-dpmwd{1,2,3}` の 6 パッケージ
4. **6.12.74 hold 解除 + purge**:
   `apt-mark unhold` → image/headers/headers-common の 3 パッケージ purge
5. **検収** (NEXT_SESSION.md 手順 5 のとおり):
   - `uname -r` = 6.12.95+deb13-amd64 のまま
   - `apt-mark showhold` = libnm0 / network-manager のみ
   - `dpkg -l | grep linux-image` = 6.12.95 + dpmwd4 + 6.12.94 の 3 つ
   - grub.cfg の menuentry 数減少、`df -h /` で回収量確認 (~1GB 見込み)
   - GRUB default が stock 6.12.95 を指したままであることも確認 (grubenv / GRUB_DEFAULT=0)

## 触らないもの (ガードレール)

- `libnm0` / `network-manager` の hold (broadcomfix、別件)
- dpmwd4 image/headers (再演用)
- `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` (恒久対策本体)
- `/var/log/h4-probe/`、`/usr/local/bin/c9-bus-snap.sh`

## 完了後 (リポジトリ側)

1. `report/` に短いハウスキーピングレポートを作成 (CLAUDE.md のレポートルール準拠: TZ=Asia/Tokyo のタイムスタンプ、概要セクション、検収結果、本プランを attachment に添付)
2. NEXT_SESSION.md を削除 (「完了したらこのファイルは削除してよい」)
3. レポート追加 + NEXT_SESSION.md 削除をコミット

## 検証方法

手順 5 の検収コマンド出力をレポートに転記し、期待値と一致することを確認する。実機の稼働カーネル・hold・udev rule が無傷であることが合格条件。
