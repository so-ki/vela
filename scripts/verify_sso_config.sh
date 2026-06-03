#!/usr/bin/env bash
# 校验 SSO 环境变量与公开配置接口（无需真实 IdP 登录）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${VELA_API:-http://127.0.0.1:8000/api/v1}"

echo "==> SSO 配置检查"
echo "API: $API"

cfg="$(curl -sf "$API/auth/sso/config")"
echo "$cfg" | python3 -m json.tool

enabled="$(echo "$cfg" | python3 -c "import sys,json; print(json.load(sys.stdin)['enabled'])")"
if [ "$enabled" = "True" ] || [ "$enabled" = "true" ]; then
  echo "SSO 已启用，检查登录跳转..."
  loc="$(curl -sI "$API/auth/sso/login" | awk '/^[Ll]ocation:/ {print $2}' | tr -d '\r')"
  if [ -z "$loc" ]; then
    echo "FAIL: /auth/sso/login 未返回 Location" >&2
    exit 1
  fi
  echo "OK: 重定向至 IdP → $loc"
else
  echo "SSO 未启用（开发环境正常）。生产请在 .env.prod 设置 SSO_ENABLED=true 及 OIDC 四元组。"
  echo "详见 DEPLOYMENT.md「SSO 配置」与「本地 Keycloak 联调」。"
fi

echo "Done."
