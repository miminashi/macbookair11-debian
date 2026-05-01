# `.ssh/` — このリポジトリ専用の GitHub Deploy Key

このリポジトリ (`miminashi/macbookair11-debian`) の GitHub remote には、
ユーザ個人の SSH 鍵ではなく **このリポジトリ専用の deploy key** で接続する。
鍵と SSH 設定はすべてこのディレクトリにまとまっている。

## 接続方式

**`GIT_SSH_COMMAND` で `.ssh/config` を指定する方式**:

- `~/.ssh/config` も `.git/config` も書き換えない
- git 実行時に `GIT_SSH_COMMAND="ssh -F .ssh/config" git ...` の形で指定する
- 推奨は同梱ラッパー `.ssh/git.sh` を使うこと
- remote URL は通常通り `git@github.com:miminashi/macbookair11-debian.git` で良い

(参考: `git config core.sshCommand` 方式と `~/.ssh/config Include` 方式は採用していない。
Claude Code のサンドボックスが `.git/config` と `~/.ssh/config` への書き込みを
ブロックするため、両方ともサンドボックス内では実行できない。)

## 運用ポリシー

- **秘密鍵 (`id_ed25519`)・公開鍵 (`id_ed25519.pub`)・SSH config (`config`) は
  リポジトリにコミットしない** (`.gitignore` で除外)。マシンごとに以下のセットアップで生成する。
- GitHub Deploy keys への公開鍵登録は **ユーザが手動で行う**。
- このリポジトリへの `git push` / `git fetch` は **必ずラッパー `.ssh/git.sh`
  または `GIT_SSH_COMMAND="ssh -F .../.ssh/config" git ...`** を経由する。
  素の `git push` は個人鍵で認証してしまうため使わない。

## ディレクトリの中身

| ファイル | 役割 | コミット |
|---|---|---|
| `README.md` | このファイル | する |
| `git.sh` | `GIT_SSH_COMMAND` を設定して `git` を exec するラッパー | する |
| `known_hosts` | github.com の SSH ホスト鍵 (`api.github.com/meta` 由来) | する |
| `id_ed25519` | 秘密鍵 (パーミッション 600) | **しない** |
| `id_ed25519.pub` | 公開鍵 | **しない** |
| `config` | SSH config (絶対パス) | **しない** |

## 初回セットアップ (クローン直後・新マシンで 1 回だけ)

### Step 1. 鍵ペアを生成

```bash
cd <リポジトリのルート>
chmod 700 .ssh
ssh-keygen -t ed25519 -N '' \
  -C "deploy-key:miminashi/macbookair11-debian (host: $(hostname -s))" \
  -f .ssh/id_ed25519
chmod 600 .ssh/id_ed25519
chmod 644 .ssh/id_ed25519.pub
```

- `-N ''` でパスフレーズなし (非対話で `git push` するため)
- `-C` のコメントに「どのリポジトリの・どのホスト用か」を記録しておくと、
  GitHub の Deploy keys 一覧で識別しやすい

### Step 2. `.ssh/config` を作成

リポジトリのルートで以下のワンライナーを実行 (`$PWD` が絶対パスに展開される):

```bash
ROOT="$PWD"
cat > .ssh/config <<EOF
Host github.com
  User git
  IdentityFile $ROOT/.ssh/id_ed25519
  IdentitiesOnly yes
  UserKnownHostsFile $ROOT/.ssh/known_hosts
  StrictHostKeyChecking yes
EOF
chmod 600 .ssh/config
```

> **注意**: SSH の `IdentityFile` などは絶対パス (または `~`) のみ許容するため、
> リポジトリを別パスに移動した場合は `.ssh/config` を作り直すこと。

### Step 3. 公開鍵を GitHub に登録

```bash
cat .ssh/id_ed25519.pub
```

の出力を:

1. GitHub の対象リポジトリ (`miminashi/macbookair11-debian`) を開く
2. **Settings → Deploy keys → "Add deploy key"**
3. **Title**: `hostname -s` 等のマシン識別名
4. **Key**: 上記コマンドの出力をそのまま貼り付け
5. push が必要なら **"Allow write access"** にチェック → **"Add key"**

未登録のまま `git push` するとサーバ側で認証拒否される。

### Step 4. (まだ origin が無ければ) git remote を追加

```bash
git remote add origin git@github.com:miminashi/macbookair11-debian.git
```

remote URL は通常通り `github.com` で良い (alias 不要)。

## 使い方

push / fetch / clone などは **必ず** 以下のいずれかの形で実行する:

### 方法 1. ラッパーを使う (推奨)

```bash
./.ssh/git.sh push
./.ssh/git.sh fetch
./.ssh/git.sh ls-remote origin
```

### 方法 2. `GIT_SSH_COMMAND` 環境変数を都度指定

```bash
GIT_SSH_COMMAND="ssh -F /home/miminashi/projects/macbookair11-debian/.ssh/config" git push
```

### 方法 3. シェル別名 (永続化したい場合)

`~/.bashrc` 等に追記:

```bash
alias gitd='GIT_SSH_COMMAND="ssh -F /home/miminashi/projects/macbookair11-debian/.ssh/config" git'
```

以後 `gitd push` / `gitd fetch` で deploy key 経由になる。

## 動作確認

```bash
ssh -F .ssh/config -T git@github.com
```

期待される出力:

```
Hi miminashi/macbookair11-debian! You've successfully authenticated, but GitHub does not provide shell access.
```

deploy key は shell を許さないので exit code は 1 になるが、
"You've successfully authenticated" が出ていれば認証は成功している。

または:

```bash
./.ssh/git.sh ls-remote origin
```

でリモート refs が取得できれば OK。

## Claude Code サンドボックス内での利用

Claude Code のサンドボックス (`$SANDBOX_RUNTIME=1`) からは以下の制約があり、
普通の SSH 接続では github.com に届かない:

- TCP 22 番ポートへの直接接続は許可されていない
- 利用できる外向き経路は HTTP CONNECT proxy (`localhost:3128`) と
  SOCKS5 proxy (`localhost:1080`) のみ
- `~/.ssh/config` と `.git/config` への書き込みもブロックされる

`.ssh/git.sh` ラッパーはこの環境を **自動検出** して以下を行う:

1. **HTTP CONNECT proxy 経由で `ssh.github.com:443` へ接続** (GitHub が SSH を 443
   ポートでも提供しているため)。具体的には ssh の `ProxyCommand` に
   `socat - PROXY:localhost:%h:%p,proxyport=3128` を渡す
2. **`HostKeyAlias=github.com`** で本来の `github.com` ホスト鍵を使って検証
   (`known_hosts` に `ssh.github.com` のエントリは無いため)
3. **最大 3 回までリトライ**。サンドボックス proxy は散発的に "Bad Gateway" を返すため

### 使用例 (サンドボックス内)

```bash
./.ssh/git.sh push
./.ssh/git.sh fetch
./.ssh/git.sh ls-remote origin
```

ラッパーが `$SANDBOX_RUNTIME` を見て自動的に proxy 経由 / 直接接続を切り替える
ので、サンドボックス内外で同じコマンドが使える。

### 3 回リトライしても失敗する場合

ラッパーをもう一度起動するか、サンドボックスを `/sandbox` で一時無効化する。
プロキシの不安定さは Claude Code 環境側の特性なので、コード側では解消できない。

### 環境変数で直接実行する場合 (サンドボックス内)

ラッパーを使わず GIT_SSH_COMMAND で直接やるなら:

```bash
GIT_SSH_COMMAND="ssh -F /home/miminashi/projects/macbookair11-debian/.ssh/config \
  -o ProxyCommand='socat - PROXY:localhost:%h:%p,proxyport=3128' \
  -o Hostname=ssh.github.com -o Port=443 -o HostKeyAlias=github.com" \
  git push
```

## 鍵の再生成 (ローテーション・漏洩時)

1. GitHub の Settings → Deploy keys から **古い公開鍵を削除**
2. ローカルの鍵ペアと config を削除:
   ```bash
   rm -f .ssh/id_ed25519 .ssh/id_ed25519.pub .ssh/config
   ```
3. **Step 1 (鍵生成) と Step 2 (config 作成) を再度実行**
4. **新しい公開鍵を GitHub に登録** (Step 3)

## known_hosts の検証

`known_hosts` は `https://api.github.com/meta` の `ssh_keys` フィールドから生成している。
正しさを再確認するには:

```bash
diff <(curl -sS https://api.github.com/meta | jq -r '.ssh_keys[] | "github.com " + .') \
     .ssh/known_hosts
```

差分が無ければ最新の GitHub 公開ホスト鍵と一致している。

GitHub がホスト鍵をローテートした場合は同じコマンドで再生成する:

```bash
curl -sS https://api.github.com/meta | jq -r '.ssh_keys[] | "github.com " + .' \
  > .ssh/known_hosts
```

## セキュリティ注意

- `id_ed25519` (秘密鍵)、`id_ed25519.pub` (公開鍵)、`config` (絶対パス) はすべて
  `.gitignore` で除外している。`git add -f` 等で **絶対に commit しないこと**。
- パスフレーズは付けていない (非対話で `git push` するため)。
  漏洩時は速やかに GitHub から削除し、上記「鍵の再生成」手順でローテートする。
- 素の `git push` を使うと個人鍵で認証されてしまう (アクセス権が無ければ失敗するが、
  あれば成功して deploy key の意味が薄れる)。**必ずラッパーまたは `GIT_SSH_COMMAND` 経由
  で実行すること**。
