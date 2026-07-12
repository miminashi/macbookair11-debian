# 次セッション引き継ぎ: ハウスキーピング (旧カーネル整理・dpmwd 退役処理)

作成: 2026-07-12 23:15 JST (Phase C-9 クローズ時)

## 位置づけ

hang 問題の調査・対策は [C-9](report/2026-07-12_220709_phase_c9_unprotected_trace_stall_at_tb_noirq_and_bus_error_residue.md) で一旦クローズ済み。
実機は **stock 6.12.95+deb13 + udev rule 保護** で常用 soak 中。本引き継ぎは残ったディスク整理のみで、
hang 対策に触る箇所はない。所要 ~10 分想定。

## 実施内容 (2026-07-12 06:15 JST 時点の実機調査に基づく)

### 1. stock 6.12.94 image をフォールバックとして保持 (autoremove より先に実施)

`linux-image-6.12.94+deb13-amd64` は hang 全条件 0/30 検証済みの直近 stock だが **autoremove の削除対象に入っている**。
残す場合は先に manual マークする (推奨):

```bash
ssh miminashi@macbookair2015.lan 'sudo apt-mark manual linux-image-6.12.94+deb13-amd64'
```

残さない判断なら (6.12.95 + dpmwd4 で足りるとみなす)、このステップをスキップして 2 で消える。

### 2. apt autoremove (旧カーネル群 26 パッケージ)

対象 (dry-run 確認済み): 6.12.73〜6.12.90 台の linux-image / linux-headers / linux-kbuild + libwoff1。
dpmwd1-4 はローカル manual インストールのため **autoremove 対象外** (消えない)。

```bash
ssh miminashi@macbookair2015.lan 'sudo apt-get -s autoremove | grep ^Remv'   # 対象を再確認してから
ssh miminashi@macbookair2015.lan 'sudo apt-get -y autoremove'
```

### 3. dpmwd1-3 の purge (dpmwd4 は残置)

dpmwd4 は再演用に残す (C-9 引継ぎ: pm_trace decode 込みの再演は dpmwd4 が唯一の手段)。
dpmwd1-3 は役割終了 (各 /boot 実体 ~85MB/個):

```bash
ssh miminashi@macbookair2015.lan 'sudo apt-get -y purge \
  linux-image-6.12.94-dpmwd1 linux-headers-6.12.94-dpmwd1 \
  linux-image-6.12.94-dpmwd2 linux-headers-6.12.94-dpmwd2 \
  linux-image-6.12.94-dpmwd3 linux-headers-6.12.94-dpmwd3'
```

### 4. 6.12.74 の hold 解除 + 削除

旧 known-good として hold していたもの。stock 6.12.95 検収済みのため役割終了:

```bash
ssh miminashi@macbookair2015.lan 'sudo apt-mark unhold linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64 && \
  sudo apt-get -y purge linux-image-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-amd64 linux-headers-6.12.74+deb13+1-common'
```

### 5. 検収

```bash
ssh miminashi@macbookair2015.lan '
uname -r                                   # 6.12.95+deb13-amd64 のまま (稼働カーネルは触っていない)
apt-mark showhold                          # libnm0 / network-manager のみ残ること
dpkg -l | grep -cE "^ii +linux-image"      # 期待: 6.12.95 + dpmwd4 (+ 手順1 実施なら 6.12.94)
sudo grep -c menuentry /boot/grub/grub.cfg # エントリ数が減っていること (purge が update-grub を自動実行)
df -h /'                                   # 回収量の確認 (~1GB 前後見込み)
```

## 触ってはいけないもの

| 対象 | 理由 |
|---|---|
| `libnm0` / `network-manager` の hold | broadcomfix パッチ入りの意図的 hold (hang 問題とは別件) |
| `linux-image-6.12.94-dpmwd4` / 同 headers | 再演用に残置 (C-9 引継ぎ) |
| `/etc/udev/rules.d/99-c7r3-wl-d3cold.rules` | hang 恒久対策の本体 |
| `/var/log/h4-probe/` 一式 | 歴代セッションの証跡 (削除しないこと) |
| `/usr/local/bin/c9-bus-snap.sh` | 保護あり bus-watch 比較 (安価な follow-up) 用に残置 |

## 備考

- 再起動は不要 (稼働中カーネルに触らない)。実施後、通常の soak 継続
- ハウスキーピングとは別の任意 follow-up (優先度低) は C-9 レポートの「次セッション引継ぎ」参照:
  保護あり bus-watch 比較 / BAR0+0x1408 の実名 / 無人 wake 源の消去法
- 完了したらこのファイルは削除してよい
