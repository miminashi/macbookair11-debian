# MacBook Air lid open 復帰失敗 (S3 hang) の段階的修正

## Context

MacBook Air 11" Early 2015 (`macbookair2015.lan`, MacBookAir7,1, Debian 13 / kernel 6.12.85) で、
ときどき lid open でのスリープ復帰に失敗し、電源ボタン長押しでの強制電源オフを要する。

### 観測事実 (2026-04-01 〜 2026-05-10、journal 上の全 boot を対象に集計)

| boot id (先頭 8 文字) | suspend_entries | resume_exits | 差 |
|---|---:|---:|---:|
| dab93bc3 | 32 | 32 | 0 |
| **edea8161** | 18 | 17 | **1 (ハング)** |
| **b4415a38** | 13 | 12 | **1 (ハング)** |
| **8ffbacdb** | 5 | 4 | **1 (ハング)** |
| **139bb7e4** | 10 | 9 | **1 (ハング)** |
| 123fcf32 (現 boot) | 28 | 28 | 0 |

- 16 boot 中 4 boot で `PM: suspend entry (deep)` の直後に journal が完全に途絶えており、
  これらは**いずれも次の boot まで一切のカーネル/ユーザランドログが残っていない**。
  S3 (deep sleep) 経路でのカーネルハング = 強制電源オフが必要だった事象と一致する。
- 失敗率は概ね 5-10% (10〜30 cycle に 1 回程度)。
- 失敗直前の共通シグネチャは `gnome-shell: Cursor update failed: drmModeAtomicCommit: 無効な引数です`
  (DRM/i915) だが、この警告は成功時にも頻発しており (86 件 / 132 suspend、約 65%)、
  失敗特異マーカーではない (i915 周辺の不安定性は示唆)。
- 5/4 のカーネル更新 (6.12.74 → 6.12.85) を跨いで失敗が継続している (5/8 の失敗は新カーネル下)。

### 既知パラメータの状態

- `/sys/power/mem_sleep` = `s2idle [deep]` (deep=S3 がデフォルト)。
- `/proc/cmdline` = `BOOT_IMAGE=/boot/vmlinuz-6.12.85+deb13-amd64 root=UUID=... ro quiet`
  (S3/i915 系の workaround は未適用)。
- 内蔵パネル `eDP-1`: `Sink support: PSR = no` 。**PSR は使用されていないため
  `i915.enable_psr=0` は無効** (一般論として頻出する対処だがこの機種では的外れ)。
- `i915` モジュールパラメータ実効値: `enable_dc = -1` (=自動)、`enable_psr = -1` (=自動だが PSR は未使用)。
- ACPI `LID0` wake は enabled、Wi-Fi (ARPT) wake は disabled、XHC1/RP01-06 wake は enabled。
- `applespi` (新型 MBP のキーボード SPI ドライバ) が auto-load されているが
  本機 (MBA 7,1) は USB キーボード/トラックパッド (`bcm5974`) で `applespi` のクライアントは無い。
- `mem_sleep_default=s2idle` への切替は user の選択により**採用しない** (S3 を維持する方針)。

### ゴール

S3 (deep sleep) を維持したまま、lid open 復帰失敗を 0 にする。
失敗率が低いため、修正後も継続的に suspend/resume mismatch をモニタして判定する。

## 採用方針: 2 段階構成 (切り分け実験 → 本修正)

最終目標は **S3 deep を維持したまま** lid open 復帰失敗を 0 にすること。
ただし「i915 系個別パラメータの効果」を確認する前に、**そもそも問題が S3 経路特有かを切り分け**ておく。
切り分けの結果次第で、後続候補の優先順位/採否を判断する。

「複数同時に変えると効いた要因が判らなくなる」ため、各候補を**1 変数ずつ**適用 → 観測 → 次へ。
各試行後、最低 30 cycle の suspend/resume を回し、`suspend_entries == resume_exits` を維持できるか確認する。

### Phase A (切り分け実験室実験): S3 ベースライン と s2idle の対照試験

長期観察ではなく、**ユーザが手動で蓋開閉を繰り返す実験室実験**で短時間に切り分ける。

- **目的**: 失敗が S3 経路特有か、経路非依存かを 1 セッション内 (~1-2 時間) で切り分ける。
- **プロトコル**:
  1. **A-1: S3 ベースライン**。現状 (`deep`) のまま、蓋開閉を **30 cycle** 繰り返し
     ハング件数を記録。1 cycle = 蓋を閉じる → 30 秒待つ → 蓋を開けて復帰確認 → 復帰したら次へ。
     (ハングしたら強制電源オフ → 起動 → カウント続行。各ハング時のログを記録)
  2. **A-2: s2idle 切替**。`mem_sleep_default=s2idle` を grub に追加 → reboot →
     同じ手順で **30 cycle** 繰り返し。
  3. 比較: A-1 と A-2 のハング件数を比較。
- **期待される結果と意味**:
  - A-1 で 1 件以上ハング & A-2 で 0 ハング → 問題は **S3 経路に限定**。Phase B (i915 系個別対処) で本修正へ。
  - A-1 / A-2 ともにハングなし → 30 cycle では再現せず (失敗率 ~5% で 30 cycle なら期待値 1.5、サンプル不足)。
    cycle 数を 50, 100 と増やすか、長期観測へ切替を判断。
  - A-2 でも**ハングが起きる** → 問題は S3 非依存 (DRM/USB/PCIe など別レイヤ)。
    Phase B 候補の優先順位を i915 → applespi blacklist 優先に入れ替え。
- **実験中の役割分担**:
  - ユーザ: 物理的に蓋を開閉 (ssh では復帰イベントを発生させられないため)。
    ハング発生時は強制電源オフ → 起動 → 次の cycle へ。
  - assistant: 各 cycle 前後にログ取得・カウント、A-2 への切替操作 (grub 編集 + reboot)、
    最終比較レポート生成。
- **副作用**: A-2 中だけ s2idle が active。実験終了後すぐに S3 へ戻すので電池消費の影響は実験時間内のみ。

### Phase B (本修正): S3 維持 + 個別パラメータ試行

Phase A 終了後、`mem_sleep_default=s2idle` を**外して** S3 deep に戻したうえで、以下を 1 候補ずつ試す。
Phase A の結果に応じて優先順位を入れ替える (s2idle で完治していれば候補 1 → 2、s2idle でも再発していれば候補 2 → 1 を優先)。

### 候補 1: `i915.enable_dc=0` (Phase B、優先試行)

- 根拠: Broadwell/Skylake 世代の i915 で、Display Controller (DC5/DC6) のステート遷移が
  S3 復帰時にハングを引き起こす既知事例が複数あり (Intel/freedesktop バグトラッカー、Arch Linux フォーラム)。
  PSR が使われていない本機でも DC ステート起因のハングは独立して起こり得る。
  失敗直前の DRM 警告 (drmModeAtomicCommit エラー) も i915 内部状態の不整合を示唆。
- 副作用: 軽微。アイドル時の i915 省電力が一段階浅くなり、待機電力が小幅 (数百 mW オーダー) 増えるのみ。
  画面表示への悪影響は基本的に無し。

### 候補 2: `applespi` のブラックリスト (候補 1 で改善しなければ)

- 根拠: 本機は `applespi` が結びつくデバイス (MBP 13,*+ の SPI キーボード) を持たないが、
  モジュール自体は load されており PM hook を提供している。未使用ドライバが suspend/resume 経路で
  例外パスを踏む例は複数報告がある。
- 適用方法: `/etc/modprobe.d/disable-applespi.conf` に `blacklist applespi` を記述 → `update-initramfs -u`。
- 副作用: ほぼ皆無 (本機ではデバイスが無いため何も失われない)。

### 候補 3: `pcie_aspm=off` (候補 1, 2 でも改善しなければ)

- 根拠: dmesg に `thunderbolt 0000:07:00.0: device link creation from 0000:06:00.0 failed` が
  記録されており、Thunderbolt/PCIe ASPM 周辺で suspend/resume 不安定の懸念がある。
- 副作用: アイドル時の PCIe 省電力が完全に無効化されるため、待機/アイドル電力が顕著に増える
  (数 W オーダー)。バッテリ持ちが悪化するため**最後の手段**。

### 失敗時の段階的フォールバック (候補 3 まで効果なし)

- ARPT (`pci:0000:03:00.0` BCM4360) wake の明示無効化 →
  XHC1 (USB 0000:00:14.0) wake の無効化 → 最終的に `mem_sleep_default=s2idle` への撤退判断。
  ここまで来た時点でユーザに再相談する。

## 実施手順 (実機: `ssh miminashi@macbookair2015.lan`)

### Phase A: 実験室実験の進行手順

#### Phase A 開始前 (初期セットアップ)

1. ベースライン測定スクリプトを設置 (下記「共通」セクション)。
2. grub バックアップ:
   ```bash
   sudo cp -av /etc/default/grub /etc/default/grub.bak.$(date +%Y%m%d_%H%M%S)
   ```
3. 開始時点の全 boot の suspend/resume 集計を記録 (実験の初期スナップショット):
   ```bash
   sudo /usr/local/sbin/check-suspend-resume.sh > /tmp/baseline_initial.txt
   ```

#### A-1: S3 ベースライン (現状のまま)

1. 現 boot を起点に suspend cycle カウンタをリセットする目的で**1 回 reboot** (任意だが結果が読みやすくなる)。
   ```bash
   sudo systemctl reboot
   ```
2. 復帰後、ssh で接続を確認 (`cat /sys/power/mem_sleep` → `s2idle [deep]` のまま) し、
   ユーザに蓋開閉実験開始を依頼。
3. ユーザは:
   - 蓋を閉じる → 30 秒待機 → 蓋を開けて復帰確認 → ssh で `last` などを叩いて生存確認 → 次の cycle。
   - **ハングしたら**: 電源ボタン長押しで強制電源オフ → 起動 → assistant に通知 → cycle カウントは継続。
4. **30 cycle 完了後**、結果を記録:
   ```bash
   sudo /usr/local/sbin/check-suspend-resume.sh > /tmp/phase_a1_result.txt
   ```
   差分 `(diff)` の合計 = A-1 のハング件数。

#### A-2: s2idle へ切替

1. `/etc/default/grub` の編集:
   ```diff
   - GRUB_CMDLINE_LINUX_DEFAULT="quiet"
   + GRUB_CMDLINE_LINUX_DEFAULT="quiet mem_sleep_default=s2idle"
   ```
2. `sudo update-grub && sudo systemctl reboot`
3. 復帰後の確認:
   ```bash
   cat /sys/power/mem_sleep            # → "[s2idle] deep" (s2idle が active)
   ```
4. ユーザに同手順で **30 cycle** 蓋開閉を依頼。
5. 完了後:
   ```bash
   sudo /usr/local/sbin/check-suspend-resume.sh > /tmp/phase_a2_result.txt
   ```

#### Phase A 終了後 (S3 へ復帰、Phase B 開始準備)

1. `/etc/default/grub` から `mem_sleep_default=s2idle` を削除し、`update-grub && reboot`。
2. `cat /sys/power/mem_sleep` → `s2idle [deep]` (deep がアクティブ) を確認。
3. A-1 と A-2 の結果を比較し、Phase B の候補優先順位を決定 (前述「期待される結果と意味」を参照)。

### 共通: ベースライン測定スクリプトの設置 (Phase A 開始時に同時実施)

`/usr/local/sbin/check-suspend-resume.sh` を新設 (root 所有, mode 755):

```bash
#!/bin/bash
# 全 boot の suspend/resume 件数差分を表示
for bid in $(journalctl --list-boots --no-pager | awk '{print $2}'); do
  se=$(journalctl -b "$bid" -g "PM: suspend entry" --no-pager 2>/dev/null | wc -l)
  re=$(journalctl -b "$bid" -g "PM: suspend exit" --no-pager 2>/dev/null | wc -l)
  if [ "$se" -gt 0 ] || [ "$re" -gt 0 ]; then
    printf "boot=%s suspend=%d resume=%d diff=%d\n" "${bid:0:8}" "$se" "$re" "$((se-re))"
  fi
done
```

### Phase B 候補 1: `i915.enable_dc=0` 適用

1. 現状バックアップ:
   ```bash
   sudo cp -av /etc/default/grub /etc/default/grub.bak.$(date +%Y%m%d_%H%M%S)
   ```
2. `/etc/default/grub` の編集 (1 行のみ):
   ```diff
   - GRUB_CMDLINE_LINUX_DEFAULT="quiet"
   + GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"
   ```
3. ブートローダ再生成: `sudo update-grub`
4. 再起動: `sudo systemctl reboot` (ssh セッションは切断される)
5. 復帰後の確認:
   ```bash
   cat /proc/cmdline                                 # i915.enable_dc=0 が含まれるか
   cat /sys/module/i915/parameters/enable_dc         # → 0
   ```

### 候補 1 のロールバック (効果なしの場合)

```bash
sudo cp -av /etc/default/grub.bak.YYYYMMDD_HHMMSS /etc/default/grub
sudo update-grub
sudo systemctl reboot
```

### 候補 2: applespi ブラックリスト適用 (候補 1 ロールバック後 or 候補 1 と入れ替え)

1. `/etc/modprobe.d/disable-applespi.conf` を新規作成 (root, 644):
   ```
   # MBA 7,1 では applespi が bind するデバイスは存在しないが、
   # 未使用ドライバが suspend/resume hook 経由で不安定要因になる懸念があるため無効化。
   blacklist applespi
   ```
2. initramfs 再生成: `sudo update-initramfs -u`
3. 再起動 → `lsmod | grep applespi` が空になることを確認

### 候補 2 のロールバック

```bash
sudo rm /etc/modprobe.d/disable-applespi.conf
sudo update-initramfs -u
sudo systemctl reboot
```

### 候補 3: `pcie_aspm=off` 適用 (候補 1+2 で改善しない場合のみ)

1. `/etc/default/grub`:
   ```diff
   - GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0"
   + GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_dc=0 pcie_aspm=off"
   ```
2. `sudo update-grub && sudo systemctl reboot`

## 検証手順

### Phase B 各候補適用後の判定基準

Phase A と同じ実験室実験プロトコルを使う:

1. 候補を適用 → reboot → ユーザに蓋開閉 30 cycle を依頼。
2. 完了後 `sudo /usr/local/sbin/check-suspend-resume.sh` で diff を確認。
3. 30 cycle で 0 ハングなら「暫定的に効いている」と判定し、その状態で**日常使用に戻す**。
4. その後 **2 週間** の継続使用で実環境での再発有無を最終確認 (失敗率 5-10% のため
   30 cycle ですり抜ける可能性は残る)。

### 統計的注意点

- 失敗率 ~5% で 30 cycle なら、ハング期待値 ≈ 1.5 件 (Poisson)。
  「30 cycle で 0 ハング」が偶然起きる確率は P(0; λ=1.5) ≈ 22%。決定打にはならない。
- A-1 と A-2 の差が**統計的に意味を持つには 50 cycle 以上が望ましい**。
  ただし時間と物理操作の負担を考慮し、まず 30 cycle で実施して傾向を見る。
  傾向が判別不能なら追加 cycle を検討。

### 失敗 (=ハング) が再発した場合の手順

1. 強制電源オフ後に起動。
2. 直前 boot のログ末尾を確認:
   ```bash
   prev=$(sudo journalctl --list-boots --no-pager | tail -2 | head -1 | awk '{print $2}')
   sudo journalctl -b "$prev" --no-pager | tail -50
   ```
   `PM: suspend entry (deep)` で終わっていれば S3 ハング (本件と同じ症状)。
3. `sudo /usr/local/sbin/check-suspend-resume.sh` で全 boot の diff 推移を記録。
4. 候補を次に進める or ロールバックの判断材料にする。

## 修正対象ファイル

実機 (`macbookair2015.lan`) 上のファイル:

- `/etc/default/grub` (Phase A、Phase B 候補 1, 3)
- `/etc/modprobe.d/disable-applespi.conf` (Phase B 候補 2、新規)
- `/usr/local/sbin/check-suspend-resume.sh` (新規、観測用)

開発側リポジトリ (このマシン): プランファイルとレポートのみ。
本リポジトリの設定はマシン構成記録としてレポート (`report/`) に残す。

## レポート作成

実装後、`report/yyyy-mm-dd_hhmmss_lid_open_resume_hang.md` を作成し以下を記録:

- 観測事実 (本プランの「Context」と同等の表)
- 適用した候補と前後の diff/ ログ変化
- プランファイル (`/home/miminashi/.claude/plans/macbook-air-lid-open-fuzzy-feigenbaum.md`)
  を `report/attachment/<同名>/plan.md` にコピーしてリンク

タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (CLAUDE.md 規約)。

## 補足: 今回採用しなかった選択肢

- **`mem_sleep_default=s2idle` の常用**: 蓋を閉じた長時間放置でバッテリ消費が許容できないため
  常用は不可。**切り分け実験 (Phase A) としてのみ一時適用**し、Phase B 開始前に外す。
  S3 個別パラメータが全滅した場合の最終フォールバックとしてのみ再検討する。
- **`i915.enable_psr=0`**: 内蔵パネルが PSR をサポートしていないため適用しても効果なし。
