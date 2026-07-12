# 旧カーネルの整理 (ハウスキーピング) レポート

- **実施日時**: 2026年07月12日 23:06 (JST)
- **対象機**: MacBook Air 11" (Early 2015) / `macbookair2015.lan` / Debian 13 (trixie)

## 概要

Phase C-9 で suspend hang の調査・対策が一旦クローズし、実機は stock 6.12.95 カーネル + udev rule 保護での常用 soak に入っている。調査期間中に積み上がった旧カーネル (セキュリティ更新で置き換わった 6.12.73〜6.12.90 台、調査用自前ビルドの dpmwd1〜3、旧 known-good として hold していた 6.12.74) がディスクと GRUB メニューを圧迫していたため、前セッションが [NEXT_SESSION.md](attachment/2026-07-12_230643_housekeeping_old_kernels_cleanup/next_session.md) として残した手順に従い整理を実施した。

作業はすべて apt 経由のパッケージ削除で、稼働中カーネル・hang 恒久対策 (udev rule)・調査証跡には一切触れていない。再起動も不要のまま完了した。事前にユーザ確認のうえ、hang 全条件 0/30 検証済みの直近 stock である 6.12.94 image は apt-mark manual でフォールバックとして保持した。

結果、旧カーネル群 26 パッケージの autoremove、dpmwd1〜3 の purge (6 パッケージ)、6.12.74 の hold 解除 + purge (3 パッケージ) がすべて完了し、実機に残るカーネルは「6.12.95 (稼働中) + 6.12.94 stock (フォールバック) + dpmwd4 (再演用)」の 3 本に整理された。検収では稼働カーネル・hold (libnm0/network-manager のみ)・udev rule・調査証跡の無傷をすべて確認した。

残課題は 1 点のみ: purge 済みカーネル 6 版の `/lib/modules/` に depmod 生成物と DKMS 残骸 (計 ~33MB、実害なし) が残っている。手動 `rm -rf` が承認済みプラン外として権限拒否されたため見送った (削除コマンドは「残課題」セクション参照)。

## 添付ファイル

- [実装プラン](attachment/2026-07-12_230643_housekeeping_old_kernels_cleanup/plan.md)
- [引き継ぎ書 NEXT_SESSION.md](attachment/2026-07-12_230643_housekeeping_old_kernels_cleanup/next_session.md) (実施後にリポジトリからは削除)

## 前提・目的

- 背景: [C-9 レポート](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md) で hang 調査がクローズし、実機は stock 6.12.95+deb13 + udev 保護で soak 中。調査期間中の旧カーネルが多数残存していた
- 目的: NEXT_SESSION.md (前セッション作成、dry-run 確認済み) に基づくディスク整理。hang 対策には触らない
- 前提条件: 全コマンドは ssh 経由で実機に対して実行 (sudo NOPASSWD)。再起動不要

## 環境情報

- 対象機: MacBook Air 11" (Early 2015)、Debian 13 (trixie)
- 稼働カーネル: 6.12.95+deb13-amd64 (作業前後で不変)
- ルート FS: /dev/sda2 92GB (作業後: 使用 16GB / 空き 71GB / 19%)

## 実施内容と結果

### 1. 6.12.94 stock image の保持 (ユーザ確認済み)

```
sudo apt-mark manual linux-image-6.12.94+deb13-amd64
→ linux-image-6.12.94+deb13-amd64 は手動でインストールしたと設定されました。
```

直後の `apt-get -s autoremove` で当該 image が削除対象から外れたことを確認。
なお **headers (linux-headers-6.12.94+deb13) は autoremove 対象に残り、手順 2 で削除された**。フォールバック起動には headers 不要で、wl (DKMS) モジュールは `/lib/modules/6.12.94+deb13-amd64/updates/dkms/wl.ko.xz` としてビルド済みのまま残存しているため、6.12.94 での起動 + WiFi は引き続き可能 (ただし今後 broadcom-sta-dkms が更新された場合、6.12.94 向けの再ビルドは headers 不在でスキップされる点は留意)。

### 2. apt autoremove (26 パッケージ)

dry-run で対象を再確認 (6.12.94 image が対象外・dpmwd 系不在を目視) してから実行。削除されたもの:

- linux-image: 6.12.73 / 6.12.85 / 6.12.86 / 6.12.88 / 6.12.90 / 6.12.90+deb13.1 (6 個)
- linux-headers (amd64 + common): 6.12.85 / 6.12.86 / 6.12.88 / 6.12.90 / 6.12.90+deb13.1 / 6.12.94 (12 個)
- linux-kbuild: 6.12.85 / 6.12.86 / 6.12.88 / 6.12.90 / 6.12.90+deb13.1 / 6.12.94 (6 個)
- libwoff1 (1 個)

### 3. dpmwd1〜3 の purge (dpmwd4 は残置)

```
sudo apt-get -y purge linux-image-6.12.94-dpmwd{1,2,3} linux-headers-6.12.94-dpmwd{1,2,3}
```

設定ファイル込みで削除完了。dpmwd4 (image + headers) は C-9 引き継ぎどおり再演用に残置。

### 4. 6.12.74 の hold 解除 + purge

```
sudo apt-mark unhold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64
sudo apt-get -y purge linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-common
```

旧 known-good としての役割終了 (stock 6.12.95 検収済み) につき削除完了。

## 検収結果

| 項目 | 結果 | 判定 |
|---|---|---|
| `uname -r` | 6.12.95+deb13-amd64 (不変) | OK |
| `apt-mark showhold` | libnm0 / network-manager のみ | OK (broadcomfix hold は無傷) |
| linux-image 一覧 | 6.12.95 / 6.12.94 stock / 6.12.94-dpmwd4 / メタパッケージ linux-image-amd64 | OK (期待どおり 3 本 + meta) |
| linux-headers 一覧 | 6.12.95 (amd64+common) / dpmwd4 / メタパッケージ | OK (dpmwd4 headers 残置) |
| grub.cfg menuentry 数 | 13 (purge 時に update-grub 自動実行済み) | OK |
| GRUB default | `GRUB_DEFAULT=0` = 先頭エントリ (6.12.95) | OK ※ |
| `/boot` | vmlinuz/initrd とも 6.12.95・6.12.94・dpmwd4 の 3 組のみ (計 252MB) | OK |
| udev rule `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` | 残存 (7/10 のまま) | OK |
| `/var/log/h4-probe/` / `/usr/local/bin/c9-bus-snap.sh` | 残存 | OK |
| `df -h /` | 使用 16GB / 空き 71GB (19%) | 回収完了 (見込み ~1GB 級) |

※ grubenv に `saved_entry=...dpmwd4...` が残っているが、`GRUB_DEFAULT=0` のため参照されない inert な残骸 (C-9 撤収時の既知事項)。

## 残課題

- **`/lib/modules/` の残骸 (~33MB、実害なし)**: purge 済み 6 版 (6.12.73 / 6.12.85 / 6.12.86 / 6.12.88 / 6.12.90 / 6.12.90+deb13.1) に depmod 生成物 + DKMS wl の残骸が各 ~5.5MB 残存。手動 `rm -rf` が承認済みプラン外として実行拒否されたため見送り。掃除する場合は実機で:

  ```bash
  sudo rm -rf /lib/modules/6.12.{73,85,86,88,90}+deb13-amd64 /lib/modules/6.12.90+deb13.1-amd64
  ```

- C-9 レポート由来の任意 follow-up (保護あり bus-watch 比較 / BAR0+0x1408 の実名 / 無人 wake 源) は優先度低のまま未着手 (本作業のスコープ外)

## 再現方法

NEXT_SESSION.md (添付) のコマンドをそのまま順に実行した。要点のみ:

```bash
# 1. フォールバック保持 (autoremove より先)
ssh miminashi@macbookair2015.lan 'sudo apt-mark manual linux-image-6.12.94+deb13-amd64'
# 2. autoremove (dry-run 確認後)
ssh miminashi@macbookair2015.lan 'sudo apt-get -s autoremove | grep ^Remv'
ssh miminashi@macbookair2015.lan 'sudo apt-get -y autoremove'
# 3. dpmwd1-3 purge / 4. 6.12.74 unhold + purge / 5. 検収
# (コマンド詳細は添付 NEXT_SESSION.md の手順 3〜5 のとおり)
```

## 参照した過去のレポート

- [Phase C-9: 無保護トレースで TB noirq 停止とバスエラー痕跡](2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md) — dpmwd4 残置・stock 復帰の経緯
- [Phase C-8: wl war 機序解明と stock カーネル復帰](2026-07-12_060000_phase_c8_wl_war_mechanism_traced_and_stock_kernel_restored.md) — 6.12.95 検収 = 6.12.74 hold の役割終了根拠
