#!/usr/bin/env bash
# 修复 GitHub DNS 并推送 main 分支
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 检查 github.com 解析…"
if ! ping -c1 -t3 github.com &>/dev/null; then
  echo "==> 无法解析 github.com，尝试修复 hosts（会弹出管理员密码框）…"
  bash "$ROOT/scripts/fix-github-dns.sh"
fi

echo "==> 当前待推送提交："
git log origin/main..HEAD --oneline 2>/dev/null || git log -5 --oneline

echo "==> 推送到 origin/main …"
git push -u origin main

echo "==> 完成。可在 https://github.com/so-ki/vela 查看。"
