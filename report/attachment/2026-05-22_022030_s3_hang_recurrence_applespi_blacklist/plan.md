# MacBook Air lid open 復帰失敗 (S3 hang) 再発対応 — Phase B 候補 2 適用

## Context

2026-05-10 に `i915.enable_dc=0` を暫定対策として導入し、4-6 週間の継続観測フェーズに
入っていた ([前回レポート](../../projects/macbookair11-debian/report/2026-05-10_055032_lid_open_resume_hang.md))。
12 日後の 2026-05-19 09:15:58 にスリープ復帰失敗が再発したことが、`journalctl -b -1`
末尾のログ停止位置から確定:

```
5月 19 09:15:58 macbookair2015 systemd-sleep[221678]: Performing sleep operation 'suspend'...
(以降、ログ完全停止 → 強制電源オフが必要となり、5/22 01:33:48 に手動起動)
```

12 日間で 1 件 ≒ 週 0.58 件で、元の頻度 (週 0.7 件) と統計的にほぼ区別不能なため、
`i915.enable_dc=0` 単独では本件を解決できないと判断する。前回プランの Phase B 候補 2
(`applespi` ブラックリスト) に進む。

**今回ハングシグネチャの重要な変化**:
- 前回観測した 4 件のハングはすべて `PM: suspend entry (deep)` で停止していた
- 今回の停止位置はそれより**早い段階** (`systemd-sleep[...] Performing sleep operation 'suspend'...`
  直後、カーネルが `PM: suspend entry` ログを書く前)
- これは device suspend phase で停止していることを示唆 → applespi.suspend フック等の
  デバイスドライバ起因仮説と整合
- 既存の検出スクリプト `check-suspend-resume.sh` は `PM: suspend entry` カウンタ依存
  のため**今回は検出できなかった**。実機ログを直接読まないと再発を見落とすリスクがある

## 採用方針

ユーザ確認済みの 3 つの変更を同一の reboot サイクルで適用する:

1. **applespi モジュール blacklist** (Phase B 候補 2 / 主因仮説への対処)
2. **`no_console_suspend` カーネルパラメータ追加** (次回 hang 時の debug 情報確保)
3. **検出スクリプト強化** (今回のような早期ハングも検出できるよう改善)

`i915.enable_dc=0` は残す (副作用小、理論的根拠あり、2 変数同時で attribution は諦める)。

## 実装手順 (実機 `macbookair2015.lan` 上で実行)

すべて ssh 経由で実行。NOPASSWD sudo 設定済み。

### Step 1: 現状バックアップ

```bash
ssh miminashi@macbookair2015.lan '
  sudo cp -av /etc/default/grub /etc/default/grub.bak.$(date +%Y%m%d_%H%M%S)
  ls -la /etc/default/grub*
'
```

### Step 2: applespi blacklist 設定

```bash
ssh miminashi@macbookair2015.lan '
  sudo tee /etc/modprobe.d/disable-applespi.conf > /dev/null << "EOF"
# MBA 7,1 では applespi が bind するデバイスは存在しない (USB トラックパッド/キーボード)。
# 未使用ドライバが suspend hook 経由で不安定要因になる懸念があり、
# i915.enable_dc=0 だけでは S3 hang が再発したため (2026-05-19 再現確認) blacklist する。
# 参照: report/2026-05-10_055032_lid_open_resume_hang.md (Phase B 候補 2)
blacklist applespi
EOF
  sudo update-initramfs -u
'
```

### Step 3: `no_console_suspend` を grub に追加

```bash
ssh miminashi@macbookair2015.lan '
  sudo sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=\"quiet i915.enable_dc=0\"|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet i915.enable_dc=0 no_console_suspend\"|" /etc/default/grub
  grep ^GRUB_CMDLINE /etc/default/grub
  sudo update-grub
'
```

### Step 4: 検出スクリプトを v2 へ更新

新方式: 各 boot の末尾 200 行をチェックし、graceful shutdown マーカー
(`Reached target Shutdown`, `Reached target Power-Off`, `systemd-shutdown`,
`systemd[1]: Shutting down`, `Power down.` 等) が無い boot を「強制電源オフ ≒ ハング候補」
として分類。さらに最終行に `Performing sleep operation 'suspend'` が含まれていれば
S3 hang 確定と扱う。

```bash
ssh miminashi@macbookair2015.lan '
  sudo tee /usr/local/sbin/check-suspend-resume.sh > /dev/null << "SCRIPT"
#!/bin/bash
# 全 boot の suspend/resume 件数差分 と ungraceful shutdown を一覧表示。
# 旧 v1 (PM: suspend entry/exit カウント差) は早期 hang を見逃すため、
# 各 boot の末尾ログから graceful shutdown マーカーの有無も判定する。
GRACE_RE="Reached target (Power-Off|Reboot|Shutdown|System Shutdown|Halt|Final Step)|systemd-shutdown\[1\]:|Power down\.|Linux version|systemd\[1\]: Shutting down"
HANG_RE="Performing sleep operation .suspend.|PM: suspend entry"
last_offset=$(journalctl --list-boots --no-pager | tail -1 | awk "{print \$1}")
journalctl --list-boots --no-pager | while read off bid rest; do
  se=$(journalctl -b "$off" _TRANSPORT=kernel -g "PM: suspend entry" --no-pager 2>/dev/null | wc -l)
  re=$(journalctl -b "$off" _TRANSPORT=kernel -g "PM: suspend exit"  --no-pager 2>/dev/null | wc -l)
  tail_lines=$(journalctl -b "$off" --no-pager 2>/dev/null | tail -200)
  if echo "$tail_lines" | grep -qE "$GRACE_RE"; then
    grace="graceful"
  elif [ "$off" = "$last_offset" ]; then
    grace="current"
  else
    grace="UNGRACEFUL"
  fi
  hang=""
  if [ "$grace" = "UNGRACEFUL" ]; then
    if echo "$tail_lines" | tail -10 | grep -qE "$HANG_RE"; then
      hang=" [S3-HANG]"
    else
      hang=" [crash?]"
    fi
  fi
  printf "boot=%s off=%4s suspend=%-3d resume=%-3d diff=%-2d %s%s\n" \
    "${bid:0:8}" "$off" "$se" "$re" "$((se-re))" "$grace" "$hang"
done
SCRIPT
  sudo chmod 755 /usr/local/sbin/check-suspend-resume.sh
'
```

### Step 5: reboot して反映

```bash
ssh miminashi@macbookair2015.lan 'sudo systemctl reboot'
# 30-60 秒待って ssh 再接続を待つ
```

### Step 6: 反映確認

```bash
ssh miminashi@macbookair2015.lan '
  echo "=== /proc/cmdline ==="
  cat /proc/cmdline
  echo
  echo "=== applespi loaded? ==="
  lsmod | grep -E "applespi" || echo "(applespi not loaded — OK)"
  echo
  echo "=== modprobe.d ==="
  ls /etc/modprobe.d/
  echo
  echo "=== check-suspend-resume.sh ==="
  sudo /usr/local/sbin/check-suspend-resume.sh
'
```

期待値:
- `/proc/cmdline` に `i915.enable_dc=0 no_console_suspend` の両方が含まれる
- `lsmod | grep applespi` が空 (blacklist 効いている)
- 新スクリプトが今回の前 boot (`77cd5397`) を `UNGRACEFUL [S3-HANG]` として正しく分類
- `/etc/modprobe.d/disable-applespi.conf` が存在

## 検証

### 即時検証 (実装直後)

上記 Step 6 の出力で 4 つの期待値がすべて満たされること。

### 軽量動作確認 (manual smoke test, 数 cycle)

ユーザに依頼: 蓋を閉じる → 30 秒以上待つ → 蓋を開ける、を 3-5 cycle 繰り返し、
通常通り復帰することを確認 (この cycle 数では reproducer にならないが、
applespi 無効化で deg がないかの最低限チェック)。

```bash
ssh miminashi@macbookair2015.lan 'sudo /usr/local/sbin/check-suspend-resume.sh | tail -5'
```

### 継続観測 (4-6 週間)

前回プランと同様、本実装は理論ベースの暫定設定。実環境継続使用で再発有無を判定する。
頻度週 0.7 件を仮定すると:

| 観測期間 | 期待 hang 件数 | 0 件で済む確率 |
|---|---:|---:|
| 2 週間 | 1.4 | ≈ 25% |
| 4 週間 | 2.8 | ≈ 6% |
| 6 週間 | 4.2 | ≈ 1.5% |

判定: 4 週間 0 件 → 効果ありと暫定判断、6 週間 0 件 → 恒久採用。
判定窓中盤 (〜2026-06-19) と終盤 (〜2026-07-03) にユーザ依頼で
`sudo /usr/local/sbin/check-suspend-resume.sh | tail -10` を実行し進捗確認。

### 再発時の次の一手 (Phase B 候補 3: `pcie_aspm=off`)

`applespi` 無効化でも hang が再発した場合、grub に `pcie_aspm=off` を追加する。
副作用として待機電力が増えるため最後の手段。実装は今回と同じパターン
(`/etc/default/grub` 編集 → `update-grub` → reboot)。

## ロールバック

```bash
ssh miminashi@macbookair2015.lan '
  sudo rm /etc/modprobe.d/disable-applespi.conf
  sudo update-initramfs -u
  # 5/22 のバックアップを採用 (今回作成したもの)
  ls /etc/default/grub.bak.* | sort | tail -1 | xargs -I{} sudo cp -av {} /etc/default/grub
  sudo update-grub
  sudo systemctl reboot
'
```

## レポート作成 (実装後)

`CLAUDE.md` の規約に従い:

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
NAME="${TS}_s3_hang_recurrence_applespi_blacklist"
mkdir -p report/attachment/${NAME}/
cp /home/miminashi/.claude/plans/1-parallel-rabin.md report/attachment/${NAME}/plan.md
# 実装ログ・前 boot のハングログ末尾も attachment へ
# 本文に「実施日時」「環境情報」「前提・目的」「実装手順」「結果」「フォロー」セクション
```

`README.md` の「レポート一覧」にも追記、「適用済みパッチ・ワークアラウンドの概要」
の S3 hang 暫定対策の説明を更新。
