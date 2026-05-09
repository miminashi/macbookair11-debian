# MacBook Air lid open 復帰失敗 (S3 hang) 切り分けと暫定対策

- **実施日時**: 2026年5月10日 04:25 〜 05:50 JST
- **対象ホスト**: `macbookair2015.lan` (MacBookAir7,1)

## 添付ファイル

- [実装プラン](attachment/2026-05-10_055032_lid_open_resume_hang/plan.md)
- [全 boot の suspend/resume 集計 (実験後最終状態)](attachment/2026-05-10_055032_lid_open_resume_hang/all_boots_summary.txt)

## 前提・目的

### 背景

`macbookair2015.lan` (MacBook Air 11" Early 2015 / MacBookAir7,1, Debian 13 / kernel
6.12.85+deb13-amd64) で、ときどき lid open でのスリープ復帰に失敗し、画面真っ暗で電源
ボタン押下にも反応しない状態となる。電源ボタン長押しで強制電源オフ → 起動しないと
復帰できない。再現はランダムで、頻度は十数回〜数十回に 1 回程度。

### 目的

1. 失敗時のログから症状を再現可能なシグネチャとして特定する。
2. 失敗が S3 (deep sleep) 経路特有か、経路非依存かを切り分ける。
3. 候補となる回避策を 1 つずつ適用し、効果が見込めそうなものを暫定採用する。

### 前提条件

- ssh `miminashi@macbookair2015.lan` 経由で操作可能 (NOPASSWD sudo 設定済み)。
- S3 deep を維持したまま修正することがゴール (s2idle 常用は battery / lid wake 不可・
  KB バックライト点灯の理由で許容できないと判断)。
- 過去レポート参照: 直接の関連は無いが、本機の Debian 化シリーズに連なる。
  - [カーネル更新で消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)](2026-05-05_000905_kernel_dkms_recovery.md)

## 環境情報

- ハードウェア: Apple MacBookAir7,1 (Broadwell-U, 11" Early 2015)
  - GPU: Intel HD Graphics 6000 (`8086:1626`)
  - 内蔵ディスプレイ: eDP-1 (PSR 非対応 — `Sink support: PSR = no`)
  - Wi-Fi: Broadcom BCM4360 802.11ac (PCI 03:00.0)、`broadcom-sta-dkms` (`wl`)
  - SSD: APPLE SSD SM0128G (128GB SATA)
  - Trackpad/Keyboard: USB (`bcm5974` driver)
- OS: Debian 13 (trixie)、kernel `6.12.85+deb13-amd64`
- 関連カーネルモジュール (実験開始時点):
  - `wl`, `bcm5974`, `applespi`(本機未使用だが auto-load されている), `i915`, `applesmc`
- 実験開始時のカーネルパラメータ:
  - `BOOT_IMAGE=/boot/vmlinuz-6.12.85+deb13-amd64 root=UUID=... ro quiet`
  - 実質 `quiet` のみ (S3/i915 系 workaround は未適用)
- 各種 PM 状態:
  - `/sys/power/mem_sleep` = `s2idle [deep]` (deep がデフォルト)
  - ACPI wake: `LID0` enabled, `XHC1` enabled, `RP01-06` enabled, `ARPT` disabled
  - `i915` モジュールパラメータ実効値 (実験前): `enable_dc=-1`, `enable_psr=-1` (=auto)

## 観測事実 (実験前のログ集計)

journal を `2026-04-01 〜 2026-05-10` の全 boot で `_TRANSPORT=kernel`
かつ `PM: suspend entry` / `PM: suspend exit` を grep:

| boot id (先頭 8 文字) | suspend_entries | resume_exits | 差 |
|---|---:|---:|---:|
| dab93bc3 | 32 | 32 | 0 |
| **edea8161** | 18 | 17 | **1 (ハング)** |
| **b4415a38** | 13 | 12 | **1 (ハング)** |
| **8ffbacdb** | 5 | 4 | **1 (ハング)** |
| **139bb7e4** | 10 | 9 | **1 (ハング)** |
| 123fcf32 (実験開始時の現 boot) | 11 | 11 | 0 |
| (その他、suspend 数が少ない短時間 boot は省略) | | | |

- 16 boot 中 4 boot で `suspend > resume` (= ハング 1 件)。差分が 2 以上の boot は無し。
- ハングした 4 boot はいずれも、journal 末尾が `PM: suspend entry (deep)` で終わり、
  以降カーネル/ユーザランドの両方で**完全に**ログが途絶えており、次の boot で復帰している。
  これは「S3 (deep sleep) 経路でカーネルが固まり、強制電源オフでしか脱出できなかった」
  事象と完全に一致する。
- ハング直前の最終ユーザランドメッセージは共通して
  `gnome-shell: Cursor update failed: drmModeAtomicCommit: 無効な引数です` (i915 DRM)。
  ただしこの警告は成功 suspend の直前にも頻発しており (86 件 / 132 cycle、約 65%)、
  失敗特異マーカーではない (i915 周辺の不安定性は示唆)。
- 5/4 のカーネル更新 (6.12.74 → 6.12.85) を跨いで失敗が継続 (5/8 のハングは新カーネル下)。
- 失敗率は概ね 5-10%。
- 内蔵パネル `eDP-1` は **PSR 非対応** (`Sink support: PSR = no`)。
  したがって一般によく挙がる `i915.enable_psr=0` は本機では効果なし (= 採用候補から除外)。

## 採用方針

**Phase A (切り分け実験室実験) → Phase B (S3 維持の本修正)** の 2 段階。
失敗率が低いため長期観測ではなく、ユーザが手動で蓋開閉を繰り返す
セッション内実験 (~1 時間) で短時間に切り分ける。各候補は 1 変数ずつ適用 → 観測 → 次へ。

### Phase A (切り分け): S3 ベースライン と s2idle の対照試験

- **A-1**: 現状 (S3 deep) のまま 30 cycle 蓋開閉 → ハング件数を計測。
- **A-2**: `mem_sleep_default=s2idle` を grub に追加 → reboot →
  同じ手順で 10 cycle (s2idle が常用候補不可と確定したため短縮)。
- 期待される結果と意味:
  - A-1 で 1 件以上 & A-2 で 0 件 → 問題は S3 経路に限定 → Phase B 候補の優先度高い。
  - A-1 / A-2 ともに 0 件 → 30 cycle では再現せず (失敗率 5% で 30 cycle なら期待値 1.5)。
  - A-2 でも発生 → 問題は S3 非依存。Phase B の候補順位を入れ替え。

### Phase B (本修正): S3 維持 + 個別パラメータ試行

候補を 1 つずつ適用:

1. **`i915.enable_dc=0`** (Broadwell + i915 の Display Controller ステート起因の S3
   復帰ハング既知事例に対する古典的回避策。失敗直前の DRM 警告とも整合)。
2. (改善しなければ) **`applespi` ブラックリスト** (本機は未使用だが auto-load されている)。
3. (それでも改善しなければ) **`pcie_aspm=off`** (Thunderbolt/PCIe 起因。最後の手段、
   待機電力増加の副作用大)。

### 採用しなかった選択肢

- **`mem_sleep_default=s2idle` の常用**: A-2 中に判明した実用上の問題で確定的に却下:
  - lid open では wake せず、キーボード押下が必要 (運用上重大な不便)。
  - s2idle 中はキーボードバックライトが点灯しっぱなし (= 多くのデバイスは通電継続)。
  - 加えて消費電力も S3 比で増える。
- **`i915.enable_psr=0`**: 内蔵パネルが PSR 非対応 (`Sink support: PSR = no`) のため
  そもそも PSR が active でなく、適用しても効果なし。

## 再現方法 (実験プロトコル)

### 初期セットアップ (実機側)

1. 監視スクリプトを設置:

   ```bash
   sudo tee /usr/local/sbin/check-suspend-resume.sh > /dev/null << 'EOF'
   #!/bin/bash
   # 全 boot の suspend/resume 件数差分を表示 (kernel transport のみ)
   for bid in $(journalctl --list-boots --no-pager | awk '{print $2}'); do
     se=$(journalctl -b "$bid" _TRANSPORT=kernel -g "PM: suspend entry" --no-pager 2>/dev/null | wc -l)
     re=$(journalctl -b "$bid" _TRANSPORT=kernel -g "PM: suspend exit" --no-pager 2>/dev/null | wc -l)
     if [ "$se" -gt 0 ] || [ "$re" -gt 0 ]; then
       printf "boot=%s suspend=%d resume=%d diff=%d\n" "${bid:0:8}" "$se" "$re" "$((se-re))"
     fi
   done
   EOF
   sudo chmod 755 /usr/local/sbin/check-suspend-resume.sh
   ```

   ※ `_TRANSPORT=kernel` で sudo 監査ログ (`COMMAND=... 'PM: suspend entry' ...`) の
   誤検出を排除する。最初これを忘れて値が 2 倍化するバグを踏んだ。

2. grub バックアップ:

   ```bash
   sudo cp -av /etc/default/grub /etc/default/grub.bak.$(date +%Y%m%d_%H%M%S)
   ```

### 各 phase の手順

- 開始前: `sudo systemctl reboot` で fresh boot (suspend カウンタを 0 起点に)。
- ユーザは:
  1. 蓋を閉じる
  2. 30 秒以上待つ (debounce / suspend 完了を確実にするため。短いと 1 cycle が
     カウントされない問題を実際に踏んだ)
  3. 蓋を開ける (s2idle の場合はキーボード押下も必要)
  4. ssh で生存確認 → 次の cycle へ
- ハングしたら強制電源オフ → 起動 → カウント続行。
- 各 cycle 後 ssh で `sudo /usr/local/sbin/check-suspend-resume.sh | tail -1` を実行。
- 完了後、結果ファイルに保存:

  ```bash
  sudo /usr/local/sbin/check-suspend-resume.sh > /tmp/phase_<name>_result.txt
  ```

  ※ `/tmp` は tmpfs のため reboot で消える。次フェーズに進む前に開発側に scp する
  か、`$HOME` に置く。今回 A-1 と A-2 のファイルは reboot で失った。
  最終 boot (B-1) の保存ファイルが全 boot の集計を持っていたので報告には支障なし。

### Phase A-2 切替手順

```bash
sudo sed -i 's|^GRUB_CMDLINE_LINUX_DEFAULT="quiet"|GRUB_CMDLINE_LINUX_DEFAULT="quiet mem_sleep_default=s2idle"|' /etc/default/grub
sudo update-grub
sudo systemctl reboot
# 復帰後: cat /sys/power/mem_sleep → "[s2idle] deep"
```

### Phase B-1 切替手順

```bash
sudo sed -i 's|^GRUB_CMDLINE_LINUX_DEFAULT="quiet mem_sleep_default=s2idle"|GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"|' /etc/default/grub
sudo update-grub
sudo systemctl reboot
# 復帰後: cat /proc/cmdline に i915.enable_dc=0 が含まれること、
#         sudo cat /sys/module/i915/parameters/enable_dc → 0 を確認
```

## 結果

### Phase A / B の cycle 計測結果

| Phase | boot id | mem_sleep (active) | カーネル param | cycle | hang |
|---|---|---|---|---:|---:|
| A-1 | `4aa927f2` | deep (S3) | (なし) | 30/30 | 0 |
| A-2 | `7ee3734f` | s2idle | `mem_sleep_default=s2idle` | 10/10 | 0 |
| B-1 | `f9c35ab3` | deep (S3) | `i915.enable_dc=0` | 30/30 | 0 |
| **合計** | | | | **70** | **0** |

(A-2 は当初 30 cycle 予定だったが、s2idle が lid open で wake しない / KB バックライトが
点灯しっぱなしで実用不可と確定したため 10 cycle で打ち切り。)

詳細な全 boot の suspend/resume 集計:
[all_boots_summary.txt](attachment/2026-05-10_055032_lid_open_resume_hang/all_boots_summary.txt)

### 統計的解釈

実験前の失敗率は概ね 5% (10〜30 cycle に 1 回程度)。

- A-1 (S3 baseline、変更なし) の 30 cycle で hang 0 件:
  期待値 ≈ 1.5、Poisson(1.5) で 0 件確率 ≈ 22%。
- B-1 (S3 + `i915.enable_dc=0`) の 30 cycle で hang 0 件:
  これも単独では同じ 22% の偶然確率。
- A-1 + B-1 + A-2 = 70 cycle 通算で hang 0 件:
  仮に同じ失敗率を仮定すれば期待値 ≈ 3.5、Poisson(3.5) で 0 件確率 ≈ 3%。

#### 重要: 本実験は `i915.enable_dc=0` の効果を validate していない

**A-1 (変更なし) で既に 30/30 通ってしまった**ため、「30 cycle のラピッドファイア試験は
そもそも本件の reproducer になっていない」ことが確定した。B-1 (`i915.enable_dc=0` 適用後)
でも 30/0 だったが、これは変更の効果ではなく**ベースラインと変わらないという結果**であり、
A-1 と B-1 の差から効果を抽出することはできない。

したがって `i915.enable_dc=0` を暫定設定として残すことの根拠は:

- **理論面**: Broadwell + i915 の Display Controller (DC5/DC6) ステート起因の S3
  復帰ハングは Intel/freedesktop バグトラッカーや Arch Linux フォーラムで複数報告のある
  既知不具合パターンであり、本件のシグネチャ (DRM 警告直後の S3 ハング) とも整合する。
- **経験面**: **無し** (本実験では効果を観測できなかった)。

つまり「採用」というより「**理論ベースの暫定設定として置き、長期観測で効果の有無を判定する**」
位置付けである。

### A-2 で判明した s2idle の追加問題

- s2idle 中は **lid open で wake しない**。キーボード押下が必要。これは PM 周りの
  wakeup source 設定の問題で、実用上常用に耐えない。
- s2idle 中は **キーボードバックライトが点灯しっぱなし** (s2idle は software-only freeze
  なので多くのデバイスが通電状態のまま)。
- 上記により s2idle は最終フォールバックとしても採用しない方向に確定。

### 暫定採用構成 (実験完了時点)

実機 `macbookair2015.lan` の永続設定:

- `/etc/default/grub`:
  ```
  GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"
  ```
- `/proc/cmdline`:
  ```
  BOOT_IMAGE=/boot/vmlinuz-6.12.85+deb13-amd64 root=UUID=... ro quiet i915.enable_dc=0
  ```
- `/sys/power/mem_sleep` = `s2idle [deep]` (S3 deep が active、変更なし)
- `/sys/module/i915/parameters/enable_dc` = `0`
- `/usr/local/sbin/check-suspend-resume.sh` (今後の継続観測用、設置済み)

## 今後のフォロー (継続観測)

### 観測期間の校正

実験前の元データ (2026-04-01 〜 2026-05-10、約 6 週間) で hang 4 件 ≈ 週 0.7 件の頻度。
これを直接適用すると:

| 観測期間 | 期待 hang 件数 | 0 件で済む確率 (Poisson) |
|---|---:|---:|
| 2 週間 | 1.4 | ≈ 25% |
| 4 週間 | 2.8 | ≈ 6% |
| 6 週間 | 4.2 | ≈ 1.5% |

→ 「2 週間 0 hang」では `i915.enable_dc=0` 採用の正当化として弱い (4 回に 1 回は偶然
0 になる)。**判定窓は最低 4 週間 (〜2026-06-07 目安)、できれば 6 週間 (〜2026-06-21)** を
推奨する。

### フォロー手順

1. **4〜6 週間の実環境継続使用** で再発の有無を確認する。
   - 0 件のまま 6 週間経過なら `i915.enable_dc=0` を恒久採用とみなしてよい。
   - 4 週間時点で 0 件なら「効いている可能性が高い (有意水準 ~6%)」が、断定はできない。
   - 1 件以上発生したら次候補 (`applespi` blacklist) に進む。
2. 観測コマンド (定期的に手動実行か cron 化を検討):
   ```bash
   ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh | tail -10'
   ```
3. ハング発生時の手順 (再発した場合):
   - 強制電源オフ → 起動。
   - 直前 boot のログ末尾を確認:
     ```bash
     prev=$(sudo journalctl --list-boots --no-pager | tail -2 | head -1 | awk '{print $2}')
     sudo journalctl -b "$prev" --no-pager | tail -50
     ```
     `PM: suspend entry (deep)` で終わっていれば本件と同じ S3 ハング。
   - `sudo /usr/local/sbin/check-suspend-resume.sh` で diff の推移を記録し、
     プランの Phase B 候補 2 (`applespi` blacklist) → 候補 3 (`pcie_aspm=off`) へと進める。

### 再発時の次の一手 (Phase B 候補 2: applespi blacklist)

```bash
ssh miminashi@macbookair2015.lan
sudo tee /etc/modprobe.d/disable-applespi.conf << 'EOF'
# MBA 7,1 では applespi が bind するデバイスは存在しない (本機は USB トラックパッド/
# キーボード)。未使用ドライバが suspend/resume hook 経由で不安定要因になる懸念があり、
# i915.enable_dc=0 で改善しなかった場合の次手として無効化する。
blacklist applespi
EOF
sudo update-initramfs -u
sudo systemctl reboot
# 再起動後: lsmod | grep applespi → (空) であること確認
```

詳細は [プランファイル](attachment/2026-05-10_055032_lid_open_resume_hang/plan.md) の
「Phase B 候補 2: applespi ブラックリスト適用」セクションを参照。

## ロールバック手順

`i915.enable_dc=0` を外して元に戻す場合:

```bash
ssh miminashi@macbookair2015.lan
# /etc/default/grub.bak.20260510_045057 に実験開始前の状態あり
sudo cp -av /etc/default/grub.bak.20260510_045057 /etc/default/grub
sudo update-grub
sudo systemctl reboot
```
