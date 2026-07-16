#!/usr/bin/env bash
# 生产 Compose 冒烟：构建、健康检查、登录、导出配置
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "$#" -ne 0 ]; then
  echo "REFUSED: prod_smoke 不接受现有 env 文件或参数；它只使用自建临时配置。" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "PENDING: 未检测到 Docker；生产 Compose smoke 尚未执行。" >&2
  exit 2
fi

SMOKE_PORT="${VELA_SMOKE_PORT:-8089}"
if ! python3 -c 'import sys; value=int(sys.argv[1]); assert 1024 <= value <= 65535' "$SMOKE_PORT" 2>/dev/null; then
  echo "REFUSED: VELA_SMOKE_PORT 必须是 1024..65535 的整数。" >&2
  exit 2
fi
PROJECT_NAME="vela-smoke-$$-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
ENV_FILE=""
COMPOSE=()

cleanup() {
  if [ "${#COMPOSE[@]}" -gt 0 ]; then
    echo "==> 清理隔离 smoke 项目 ${PROJECT_NAME}..."
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ -n "$ENV_FILE" ]; then
    rm -f "$ENV_FILE"
  fi
}
trap cleanup EXIT

umask 077
ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/vela-smoke.XXXXXX.env")"
chmod 600 "$ENV_FILE"
SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32) + "@%:/")')"
printf '%s\n' \
  "SECRET_KEY=$SECRET" \
  "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
  "PUBLIC_URL=http://127.0.0.1:${SMOKE_PORT}" \
  "HTTP_BIND_ADDRESS=127.0.0.1" \
  "HTTP_PORT=${SMOKE_PORT}" \
  "ALLOW_OPEN_REGISTRATION=false" \
  "ALLOW_PASSWORD_LOGIN=true" \
  "SEED_DEMO_USERS=true" \
  "SSO_ENABLED=false" \
  "SSO_PROVIDER_NAME=Enterprise SSO" \
  "SSO_ISSUER_URL=" \
  "SSO_CLIENT_ID=" \
  "SSO_CLIENT_SECRET=" \
  "SSO_REDIRECT_URI=" \
  "SSO_DEFAULT_ROLE=legal" \
  "EXPORT_TEMPLATE=law_school" \
  "EXPORT_ORG_NAME=Vela Smoke" \
  "EXPORT_ORG_DEPARTMENT=Legal" \
  "EXPORT_RECIPIENT_LABEL=Management" \
  "QWEN_API_KEY=" \
  "LLM_POLISH_ENABLED=false" > "$ENV_FILE"

# Compose gives the caller's exported shell variables precedence over --env-file.
# Remove every variable interpolated by docker-compose.prod.yml so the isolated,
# generated env file remains the only smoke configuration source.
unset SECRET POSTGRES_PASSWORD SECRET_KEY PUBLIC_URL HTTP_BIND_ADDRESS HTTP_PORT
unset ALLOW_OPEN_REGISTRATION ALLOW_PASSWORD_LOGIN SEED_DEMO_USERS
unset SSO_ENABLED SSO_PROVIDER_NAME SSO_ISSUER_URL SSO_CLIENT_ID
unset SSO_CLIENT_SECRET SSO_REDIRECT_URI SSO_DEFAULT_ROLE
unset EXPORT_TEMPLATE EXPORT_ORG_NAME EXPORT_ORG_DEPARTMENT EXPORT_RECIPIENT_LABEL
unset QWEN_API_KEY LLM_POLISH_ENABLED

COMPOSE=(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.prod.yml)

echo "==> 构建并启动生产栈 (port ${SMOKE_PORT})..."
"${COMPOSE[@]}" up -d --build

echo "==> 等待 health..."
for i in $(seq 1 60); do
  if curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:${SMOKE_PORT}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 3
  if [ "$i" -eq 60 ]; then
    echo "FAIL: health 超时" >&2
    "${COMPOSE[@]}" logs --tail=80
    exit 1
  fi
done

echo "==> health"
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/v1/health" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("status") == "ok", "health status is not ok"
assert payload.get("environment") == "production", "health environment is not production"
print(json.dumps(payload, ensure_ascii=False, indent=2))
'

echo "==> export/config"
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/v1/export/config" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("template") == "law_school", "unexpected export template"
assert payload.get("docx_label") == "法律研究意见书", "unexpected export label"
assert isinstance(payload.get("org_name"), str) and payload["org_name"].strip(), "missing org label"
print(json.dumps(payload, ensure_ascii=False, indent=2))
'

echo "==> login"
LOGIN_RESPONSE="$(curl -fsS -X POST "http://127.0.0.1:${SMOKE_PORT}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"legal@demo.vela","password":"Demo1234!"}')"
TOKEN="$(printf '%s' "$LOGIN_RESPONSE" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
token = payload.get("access_token")
user = payload.get("user") or {}
assert isinstance(token, str) and token.strip(), "missing access token"
assert user.get("email") == "legal@demo.vela", "unexpected login user"
assert user.get("role") == "legal", "unexpected login role"
print(token)
')"
unset LOGIN_RESPONSE

echo "==> status (auth)"
curl -fsS -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:${SMOKE_PORT}/api/v1/status" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("database") == "ok", "database status is not ok"
assert isinstance(payload.get("chroma"), dict), "chroma status is not an object"
print(json.dumps(payload, ensure_ascii=False, indent=2))
'
unset TOKEN

echo ""
echo "Passed: 生产 Compose 冒烟 (http://127.0.0.1:${SMOKE_PORT})"
