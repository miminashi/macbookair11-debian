---
name: check-disk-health
description: SSH先ホストのディスク（SSD/HDD）の健全性を調査する。dmesg、sysfs I/Oカウンタ、dd読み込みテスト、smartctlを使用し、レポートを生成する。
user-invocable: true
disable-model-invocation: true
argument-hint: "[user@host] [device]"
allowed-tools: Bash, Read, Write, Edit, Glob
---

# SSD/HDD 健全性チェック

SSH先ホストのディスクデバイスに対して健全性チェックを実施し、レポートを生成する。

## 引数

- `$ARGUMENTS[0]` — SSH接続先（例: `root@openwrt-rescue.lan`）
- `$ARGUMENTS[1]` — デバイス名（例: `sda`）。`/dev/` プレフィックスなし

両方の引数が必須。不足している場合はユーザーに確認すること。

## SSH接続方式

すべてのリモートコマンドは以下の形式で実行する:

```
ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null <host> '<command>'
```

- tmuxは使用しない
- 各コマンドを個別の `ssh` 呼び出しで実行する

## 実施手順

以下の手順を順番に実施する。各ステップの出力は後でレポートに含めるため、結果を記録しておくこと。

### 1. SSH接続確認

```
ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null <host> 'echo ok'
```

接続に失敗した場合は処理を中止し、ユーザーに報告する。

### 2. dmesgによるディスクエラー確認

2つのコマンドを実行する:

```
ssh ... 'dmesg | grep -i <device>'
```
→ デバイス認識情報を取得

```
ssh ... 'dmesg | grep -i -E "error|fail|ata|scsi|i/o"'
```
→ エラーメッセージを確認

### 3. デバイス基本情報

```
ssh ... 'fdisk -l /dev/<device>'
```
→ パーティション構成を取得

```
ssh ... 'cat /sys/block/<device>/device/model 2>/dev/null; cat /sys/block/<device>/device/state 2>/dev/null; cat /sys/block/<device>/size 2>/dev/null'
```
→ sysfs情報（model, state, size等）を取得

### 4. I/Oエラーカウンタ（テスト前）

以下のカウンタ値を記録する:

```
ssh ... 'for f in ioerr_cnt iodone_cnt iorequest_cnt iotmo_cnt; do echo "$f: $(cat /sys/block/<device>/device/$f 2>/dev/null || echo N/A)"; done'
```

### 5. dd読み込みテスト

**重要:** ddがハングする可能性があるため、リモート側で `timeout` コマンドを使うこと。Bash toolのtimeoutも余裕を持って設定すること（180秒以上）。

```
ssh ... 'timeout 60 dd if=/dev/<device> of=/dev/null bs=4096 count=1000 2>&1'
```

ddの終了コード・出力を記録する。タイムアウトした場合もその旨を記録して続行する。

### 6. テスト後のdmesg確認

```
ssh ... 'dmesg | tail -50'
```

新しいエラーメッセージが出現していないか確認する。

### 7. I/Oエラーカウンタ（テスト後）

手順4と同じコマンドを実行し、テスト前後の変化を記録する。

### 8. SMART情報取得

```
ssh ... 'smartctl -a /dev/<device> 2>&1'
```

失敗した場合は以下のオプションで再試行する:

1. `smartctl -s on -a /dev/<device> 2>&1` （SMARTを有効化してリトライ）
2. `smartctl -T permissive -a /dev/<device> 2>&1` （permissiveモード）
3. `smartctl -x /dev/<device> 2>&1` （拡張情報取得）

smartctlが利用不可な場合もエラーをレポートに記録して継続すること。

### 9. レポート生成

`report/` ディレクトリにMarkdownレポートを出力する。

**ファイル名:** `report/<hostname>_<device>_health_report.md`
（例: `report/openwrt-rescue.lan_sda_health_report.md`）

hostnameは `$ARGUMENTS[0]` の `@` 以降の部分を使用する。`@` がない場合はそのまま使用する。

**レポートに含める項目:**

1. **調査概要** — 対象ホスト、デバイス、調査日時
2. **デバイス基本情報** — モデル、シリアル番号、容量、インターフェース等
3. **パーティション構成** — fdisk出力の要約
4. **dmesgエラー分析** — 検出されたエラーメッセージの分析と解説
5. **I/Oエラーカウンタ推移** — テスト前後の比較表
6. **dd読み込みテスト結果** — 読み込み速度、エラーの有無
7. **SMART属性データ** — 取得できた場合は主要属性の解説付き
8. **総合診断** — 全体的な健全性の評価と推奨対応

## 注意事項

- ddがハングする可能性がある。必ずリモート側で `timeout` コマンドを使うこと
- Bash toolのtimeoutも余裕を持って設定すること（180秒以上）
- smartctlが利用不可な場合もエラーをレポートに記録して継続すること
- 各ステップでエラーが発生しても、可能な限り後続のステップを続行すること
- レポートファイル名にはホスト名とデバイス名を含めること
