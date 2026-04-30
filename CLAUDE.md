# CLAUDE.md

## レポート作成ルール

- レポートはプロジェクトルート以下の `report` ディレクトリに作成する
- レポートのタイトルは日本語で記載する
- レポートには日時（分まで）を入れる
- レポートのファイル名は `yyyy-mm-dd_hhmmss_レポート名.md` にする（ファイル名のレポート名は英語）
- タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` コマンドで取得すること（LLM が時刻を推測してはならない）
- レポート内の日時表記は JST (日本標準時) で記載すること。システムが UTC の場合は +9 時間に変換する
- 実験やタスクの前提条件・目的は専用のセクションを設けて記載する
- 実験の再現方法（手順・コマンド等）を記載する
- 実験に際して参照した過去のレポートがある場合は、そのレポートへのリンクを記載する
- 実験レポートにはサーバ構成・ストレージ構成等の環境情報を記載する
- レポートに添付ファイル（プランファイル、ログ、スクリーンショット等）がある場合は `report/attachment/<レポートファイル名>/` ディレクトリに格納し、レポート本文から相対パスでリンクすること
  - `<レポートファイル名>` は `.md` を除いたファイル名（例: `2026-02-21_143052_ceph_cluster_setup`）
  - リンク例: `[実装プラン](attachment/2026-02-21_143052_ceph_cluster_setup/plan.md)`
- **プランファイルの添付（必須）**: プランモードで作業を行った場合、レポート作成時に必ず以下の手順でプランファイルを添付すること:
  1. 添付ディレクトリを作成: `mkdir -p report/attachment/<レポートファイル名>/`
  2. プランファイルをコピー: `cp /home/miminashi/.claude/plans/<plan-name>.md report/attachment/<レポートファイル名>/plan.md`
     - `<plan-name>` はプランモード開始時に指定されたファイル名（例: `groovy-humming-candy`）
  3. レポート本文に `## 添付ファイル` セクションを設け、リンクを記載:
     ```markdown
     ## 添付ファイル

     - [実装プラン](attachment/<レポートファイル名>/plan.md)
     ```

### Discord 通知

レポート作成時（Write ツールで `report/` 直下に `.md` を書き込んだ時）、PostToolUse hook により Discord webhook で自動通知される。Webhook URL は `.env` の `DISCORD_WEBHOOK_URL` で設定する。

### 例

```
report/
  2026-02-21_143052_ceph_cluster_setup.md
  attachment/
    2026-02-21_143052_ceph_cluster_setup/
      plan.md
```

ファイル内の例:
````markdown
# Ceph クラスタ構築レポート

- **実施日時**: 2026年2月21日 14:30

## 添付ファイル

- [実装プラン](attachment/2026-02-21_143052_ceph_cluster_setup/plan.md)

## 前提・目的

Proxmox VE クラスタ上に Ceph ストレージを構築し、分散ストレージの基本性能を計測する。

- 背景: 複数ノードにまたがる高可用性ストレージが必要
- 目的: 3ノード Ceph クラスタを構築し、IOPS・スループットを計測する
- 前提条件: 3台の PVE ノードが同一ネットワーク上に存在すること

## 環境情報

- ノード1: 192.168.1.11 (Supermicro X10SRL-F, 64GB RAM, 4x SSD)
- ノード2: 192.168.1.12 (同上)
- ノード3: 192.168.1.13 (同上)
- Proxmox VE: 8.x
- Ceph: Reef

## 再現方法

1. 各ノードで Ceph パッケージをインストール
   ```bash
   pveceph install --repository no-subscription
   ```

2. Ceph モニタを作成
   ```bash
   pveceph mon create
   ```

3. OSD を追加
   ```bash
   pveceph osd create /dev/sdb
   ```
````

## サンドボックス内からの内部ネットワークアクセス (curl)

Claude Code のサンドボックス (Linux: bubblewrap) はネットワーク名前空間を分離しており、bash 内からの外向き通信はサンドボックスが提供する HTTP プロキシ (`localhost:3128`) または SOCKS5 プロキシ (`localhost:1080`) 経由でのみ可能。

### 落とし穴

サンドボックス内には `no_proxy=localhost,127.0.0.1,...,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,...` が設定されているため、**RFC1918 のプライベート IP** (`10.x`, `172.16-31.x`, `192.168.x`) に対して `curl` はプロキシをバイパスして直接接続を試みる。サンドボックス内には経路 (`ip route` が空) が無いので、即座に `Failed to connect ... ネットワークに届きません` で失敗する。

### 内部ネットワークへの curl 手順

1. **アクセスしたいホスト/ドメインを `sandbox.network.allowedDomains` に追加** (`.claude/settings.local.json`):

   ```json
   {
     "sandbox": {
       "enabled": true,
       "autoAllowBashIfSandboxed": true,
       "network": {
         "allowedDomains": ["10.1.6.1", "*.lan"]
       }
     }
   }
   ```

   - IP アドレス・ドメイン名・ワイルドカード (`*.example.com`) いずれも可
   - ポート指定は不要 (ホスト単位で許可)

2. **curl 実行時に `no_proxy` を空にして HTTP プロキシを明示**:

   ```bash
   no_proxy='' NO_PROXY='' curl -x http://localhost:3128 http://10.1.6.1:5032/path
   ```

   - 公開ドメインへのアクセスはこの工夫不要 (`no_proxy` にマッチしないので環境変数の `HTTP_PROXY` が自動で使われる)
   - プライベート IP / `*.local` / `*.lan` 等にアクセスする場合のみ必要

### 動作確認 (例)

```bash
# サンドボックス内かどうか
echo "$SANDBOX_RUNTIME"   # → 1 ならサンドボックス内
ip route                  # → 空ならネットワーク名前空間で隔離されている
echo "$HTTP_PROXY"        # → http://localhost:3128

# 内部 HTTP サーバから取得
no_proxy='' NO_PROXY='' curl -sS -x "$HTTP_PROXY" http://10.1.6.1:5032/pvese/REPORT.md/raw
```

サンドボックス自体を一時的に無効化する場合はスラッシュコマンド `/sandbox` で切り替える。
