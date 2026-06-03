#!/usr/bin/env bash
# 生产 Compose 冒烟：构建、健康检查、登录、导出配置
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${1:-.env.prod.smoke}"
COMPOSE="docker compose --env-file $ENV_FILE -f docker-compose.prod.yml"
SMOKE_PORT="${HTTP_PORT:-8089}"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
  SMOKE_PORT="${HTTP_PORT:-8089}"
else
  echo "==> 生成临时 $ENV_FILE"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
SECRET_KEY=$SECRET
POSTGRES_PASSWORD=vela_smoke_test
PUBLIC_URL=http://127.0.0.1:${SMOKE_PORT}
HTTP_PORT=${SMOKE_PORT}
ALLOW_OPEN_REGISTRATION=false
SSO_ENABLED=false
EXPORT_TEMPLATE=law_school
EOF
  set -a && source "$ENV_FILE" && set +a
fi

cleanup() {
  echo "==> 停止容器..."
  $COMPOSE down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: 未检测到 docker，请安装 Docker Desktop 后重试 ./scripts/prod_smoke.sh"
  trap - EXIT
  exit 0
fi

echo "==> 构建并启动生产栈 (port ${SMOKE_PORT})..."
$COMPOSE up -d --build

echo "==> 等待 health..."
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${SMOKE_PORT}/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 3
  if [ "$i" -eq 60 ]; then
    echo "FAIL: health 超时" >&2
    $COMPOSE logs --tail=80
    exit 1
  fi
done

echo "==> health"
curl -s "http://127.0.0.1:${SMOKE_PORT}/api/v1/health" | python3 -m json.tool

echo "==> export/config"
curl -s "http://127.0.0.1:${SMOKE_PORT}/api/v1/export/config" | python3 -m json.tool

echo "==> login"
TOKEN="$(curl -sf -X POST "http://127.0.0.1:${SMOKE_PORT}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"legal@demo.vela","password":"Demo1234!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

echo "==> status (auth)"
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:${SMOKE_PORT}/api/v1/status" | python3 -m json.tool

echo ""
echo "Passed: 生产 Compose 冒烟 (http://127.0.0.1:${SMOKE_PORT})"
