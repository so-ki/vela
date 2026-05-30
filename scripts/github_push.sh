#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REMOTE="${1:-https://github.com/so-ki/vela.git}"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE"
else
  git remote add origin "$REMOTE"
fi
git branch -M main
echo "推送到: $REMOTE"
echo "若提示密码，请粘贴 GitHub Token: https://github.com/settings/tokens (勾选 repo)"
git push -u origin main
echo "邀请测试者: https://github.com/so-ki/vela/settings/access"
