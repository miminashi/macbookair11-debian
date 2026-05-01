#!/usr/bin/env bash
# git wrapper: deploy key (.ssh/config) を使って git を実行する。
#
# サンドボックス内 ($SANDBOX_RUNTIME=1) では:
#   - github.com:22 への直接接続が拒否されるため、
#     HTTP CONNECT proxy (localhost:3128) 経由で ssh.github.com:443 に接続する
#   - known_hosts は github.com で記録されているので HostKeyAlias=github.com で揃える
#   - サンドボックス proxy は散発的に "Bad Gateway" を返すので最大 3 回リトライ
#
# Usage:
#   ./.ssh/git.sh push
#   ./.ssh/git.sh fetch
#   ./.ssh/git.sh ls-remote origin
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$ROOT/.ssh/config"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: $CONFIG が見つかりません。" >&2
  echo "  .ssh/README.md の「初回セットアップ」を実行して config を生成してください。" >&2
  exit 1
fi

SSH_CMD="ssh -F $CONFIG"
MAX_ATTEMPTS=1

if [[ "${SANDBOX_RUNTIME:-}" == "1" ]]; then
  SSH_CMD="$SSH_CMD \
-o ProxyCommand='socat - PROXY:localhost:%h:%p,proxyport=3128' \
-o Hostname=ssh.github.com \
-o Port=443 \
-o HostKeyAlias=github.com"
  MAX_ATTEMPTS=3
fi

export GIT_SSH_COMMAND="$SSH_CMD"

attempt=1
rc=0
while [[ "$attempt" -le "$MAX_ATTEMPTS" ]]; do
  if [[ "$attempt" -gt 1 ]]; then
    echo "[git.sh] attempt $attempt/$MAX_ATTEMPTS (sandbox proxy retry)" >&2
    sleep 1
  fi
  set +e
  git "$@"
  rc=$?
  set -e
  [[ "$rc" -eq 0 ]] && exit 0
  attempt=$((attempt + 1))
done

exit "$rc"
