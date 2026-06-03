#!/usr/bin/env bash
# 当终端无法解析 github.com 时，写入 /etc/hosts 绕过 DNS（需管理员密码）
set -euo pipefail

GITHUB_IP="${GITHUB_IP:-140.82.121.4}"
MARKER="# vela-github-dns-fix"

if ping -c1 -t2 github.com &>/dev/null; then
  echo "github.com 已可解析，无需修复 DNS。"
  exit 0
fi

if grep -q "$MARKER" /etc/hosts 2>/dev/null; then
  echo "hosts 中已有 GitHub 修复条目。"
  exit 0
fi

BLOCK="
$MARKER
$GITHUB_IP github.com
$GITHUB_IP api.github.com
$GITHUB_IP codeload.github.com
$GITHUB_IP gist.github.com
$GITHUB_IP ssh.github.com
"

if [[ "$(uname)" == "Darwin" ]]; then
  printf '%s' "$BLOCK" | osascript -e 'do shell script "cat >> /etc/hosts" with administrator privileges'
else
  printf '%s' "$BLOCK" | sudo tee -a /etc/hosts >/dev/null
fi

dscacheutil -flushcache 2>/dev/null || true
killall -HUP mDNSResponder 2>/dev/null || true

echo "已写入 /etc/hosts，github.com -> $GITHUB_IP"
ping -c1 github.com && echo "DNS 修复成功。" || echo "请重启终端后再试 git push。"
