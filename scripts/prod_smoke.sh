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
SCENARIO_ID_FILE=""
COMPOSE=()

cleanup() {
  local status=$?
  trap - EXIT
  if [ "$status" -ne 0 ] && [ "${#COMPOSE[@]}" -gt 0 ]; then
    echo "==> 失败证据：Compose 状态与末尾日志" >&2
    "${COMPOSE[@]}" ps --all >&2 || true
    "${COMPOSE[@]}" logs --no-color --tail=200 >&2 || true
  fi
  if [ "${#COMPOSE[@]}" -gt 0 ]; then
    echo "==> 清理隔离 smoke 项目 ${PROJECT_NAME}..."
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ -n "$ENV_FILE" ]; then
    rm -f "$ENV_FILE"
  fi
  if [ -n "$SCENARIO_ID_FILE" ]; then
    rm -f "$SCENARIO_ID_FILE"
  fi
  exit "$status"
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
  "INSTANCE_ORGANIZATION=Vela controlled smoke" \
  "PUBLIC_URL=http://127.0.0.1:${SMOKE_PORT}" \
  "HTTP_PORT=${SMOKE_PORT}" \
  "ALLOW_OPEN_REGISTRATION=false" \
  "ALLOW_PASSWORD_LOGIN=true" \
  "RATE_LIMIT_ENABLED=true" \
  "SSO_ENABLED=false" \
  "SSO_PROVIDER_NAME=Enterprise SSO" \
  "SSO_ISSUER_URL=" \
  "SSO_CLIENT_ID=" \
  "SSO_CLIENT_SECRET=" \
  "SSO_REDIRECT_URI=" \
  "SSO_DEFAULT_ROLE=business" \
  "EXPORT_TEMPLATE=law_school" \
  "EXPORT_ORG_NAME=Vela Smoke" \
  "EXPORT_ORG_DEPARTMENT=Legal" \
  "EXPORT_RECIPIENT_LABEL=Management" \
  "LLM_POLISH_ENABLED=false" > "$ENV_FILE"

# Compose gives the caller's exported shell variables precedence over --env-file.
# Remove every variable interpolated by docker-compose.prod.yml so the isolated,
# generated env file remains the only smoke configuration source.
unset SECRET POSTGRES_PASSWORD SECRET_KEY INSTANCE_ORGANIZATION PUBLIC_URL HTTP_PORT
unset ALLOW_OPEN_REGISTRATION ALLOW_PASSWORD_LOGIN RATE_LIMIT_ENABLED SEED_DEMO_USERS
unset SSO_ENABLED SSO_PROVIDER_NAME SSO_ISSUER_URL SSO_CLIENT_ID
unset SSO_CLIENT_SECRET SSO_REDIRECT_URI SSO_DEFAULT_ROLE
unset EXPORT_TEMPLATE EXPORT_ORG_NAME EXPORT_ORG_DEPARTMENT EXPORT_RECIPIENT_LABEL
unset LLM_POLISH_ENABLED

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

run_alembic() {
  local operation="$1"
  local target="$2"
  "${COMPOSE[@]}" exec -T backend python -c '
import sys
from alembic import command
from alembic.config import Config
from scripts.container_entrypoint import configure_database_url
configure_database_url()
config = Config("/app/alembic.ini")
if sys.argv[1] == "current":
    command.current(config, verbose=True)
else:
    getattr(command, sys.argv[1])(config, sys.argv[2])
' "$operation" "$target"
}

echo "==> PostgreSQL version and Alembic 0008 lifecycle"
POSTGRES_VERSION="$("${COMPOSE[@]}" exec -T db psql -U vela -d vela -Atc 'SHOW server_version')"
echo "PostgreSQL ${POSTGRES_VERSION}"
run_alembic current head
run_alembic downgrade 20260719_0007
run_alembic upgrade 20260719_0008
run_alembic downgrade 20260719_0007
run_alembic upgrade head
MIGRATION_HEAD="$("${COMPOSE[@]}" exec -T backend python -c '
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from scripts.container_entrypoint import configure_database_url
connection_url = configure_database_url()
with create_engine(connection_url).connect() as connection:
    print(MigrationContext.configure(connection).get_current_revision())
')"
if [ "$MIGRATION_HEAD" != "20260719_0008" ]; then
  echo "FAIL: unexpected migration head ${MIGRATION_HEAD}" >&2
  exit 1
fi

assert_container_hardening() {
  local service="$1"
  local protected_path="$2"
  local uid cap_eff no_new_privs
  uid="$("${COMPOSE[@]}" exec -T "$service" id -u)"
  cap_eff="$("${COMPOSE[@]}" exec -T "$service" sh -c "awk '/^CapEff:/ {print \$2}' /proc/1/status")"
  no_new_privs="$("${COMPOSE[@]}" exec -T "$service" sh -c "awk '/^NoNewPrivs:/ {print \$2}' /proc/1/status")"
  if [ "$uid" = "0" ] || [ "$cap_eff" != "0000000000000000" ] || [ "$no_new_privs" != "1" ]; then
    echo "FAIL: ${service} 未满足非 root / 无 capabilities / no-new-privileges" >&2
    exit 1
  fi
  if "${COMPOSE[@]}" exec -T "$service" sh -c "touch '$protected_path'" >/dev/null 2>&1; then
    echo "FAIL: ${service} 根文件系统不是只读" >&2
    exit 1
  fi
  "${COMPOSE[@]}" exec -T "$service" sh -c 'touch /tmp/.vela-smoke-write && rm /tmp/.vela-smoke-write'
}

echo "==> container least privilege"
assert_container_hardening backend /app/.vela-rootfs-probe
assert_container_hardening frontend /usr/share/nginx/html/.vela-rootfs-probe
db_pid1_uid="$("${COMPOSE[@]}" exec -T db sh -c "awk '/^Uid:/ {print \$2}' /proc/1/status")"
if [ "$db_pid1_uid" != "70" ]; then
  echo "FAIL: PostgreSQL PID 1 未按官方 entrypoint 降权为 UID 70" >&2
  exit 1
fi

echo "==> provision disposable smoke users"
# Keep the production image seed-free and its root filesystem read-only: the
# disposable smoke helper is streamed from the trusted checkout over stdin.
"${COMPOSE[@]}" exec -T backend env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app \
  python -c 'import sys; from scripts.container_entrypoint import configure_database_url; configure_database_url(); path = "/app/scripts/seed_demo_user.py"; exec(compile(sys.stdin.read(), path, "exec"), {"__name__": "__main__", "__file__": path})' \
  < "$ROOT/backend/scripts/seed_demo_user.py"

"${COMPOSE[@]}" exec -T backend env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app \
  python -c 'import sys; from scripts.container_entrypoint import configure_database_url; configure_database_url(); path = "/app/scripts/seed_finalist_smoke_admin.py"; exec(compile(sys.stdin.read(), path, "exec"), {"__name__": "__main__", "__file__": path})' \
  < "$ROOT/backend/scripts/seed_finalist_smoke_admin.py"

echo "==> PostgreSQL migration head and model drift"
"${COMPOSE[@]}" exec -T -e VELA_ENTRYPOINT_MODE=check backend python -m scripts.container_entrypoint

echo "==> full business/legal API golden path on PostgreSQL"
SCENARIO_ID_FILE="$(mktemp "${TMPDIR:-/tmp}/vela-finalist-scenario.XXXXXX")"
VELA_API="http://127.0.0.1:${SMOKE_PORT}/api/v1" \
  VELA_E2E_SCENARIO_ID_FILE="$SCENARIO_ID_FILE" \
  VELA_PRESERVE_FINALIST_SCENARIO=true \
  bash scripts/verify_e2e.sh
FINALIST_SCENARIO_ID="$(tr -d '[:space:]' < "$SCENARIO_ID_FILE")"
if ! python3 -c 'import sys; assert int(sys.argv[1]) > 0' "$FINALIST_SCENARIO_ID" 2>/dev/null; then
  echo "FAIL: finalist scenario id is invalid" >&2
  exit 1
fi

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
assert user.get("organization") == "Vela controlled smoke", "user escaped instance organization"
print(token)
')"
unset LOGIN_RESPONSE

echo "==> export/config (auth)"
curl -fsS -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:${SMOKE_PORT}/api/v1/export/config" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("template") == "law_school", "unexpected export template"
assert payload.get("docx_label") == "法律研究意见书", "unexpected export label"
assert isinstance(payload.get("org_name"), str) and payload["org_name"].strip(), "missing org label"
print(json.dumps(payload, ensure_ascii=False, indent=2))
'

echo "==> status (auth)"
curl -fsS -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:${SMOKE_PORT}/api/v1/status" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload.get("database") == "ok", "database status is not ok"
assert isinstance(payload.get("chroma"), dict), "chroma status is not an object"
print(json.dumps(payload, ensure_ascii=False, indent=2))
'

echo "==> built SPA assets and browser login"
if [ ! -x "$ROOT/frontend/node_modules/.bin/playwright" ]; then
  echo "FAIL: 缺少 Playwright；请先在 frontend 执行 npm ci 并安装 Chromium。" >&2
  exit 1
fi
(
  cd "$ROOT/frontend"
  VELA_E2E_BASE_URL="http://127.0.0.1:${SMOKE_PORT}" \
    VELA_E2E_SCENARIO_ID="$FINALIST_SCENARIO_ID" \
    npm run test:e2e
)
unset TOKEN

mkdir -p "$ROOT/security-artifacts"
FINAL_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
BACKEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$("${COMPOSE[@]}" ps -q backend)")"
FRONTEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$("${COMPOSE[@]}" ps -q frontend)")"
POSTGRES_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$("${COMPOSE[@]}" ps -q db)")"
{
  printf 'commit_sha=%s\n' "$FINAL_SHA"
  printf 'postgresql_version=%s\n' "$POSTGRES_VERSION"
  printf 'migration_head=%s\n' "$MIGRATION_HEAD"
  printf 'backend_image_digest=%s\n' "$BACKEND_IMAGE_ID"
  printf 'frontend_image_digest=%s\n' "$FRONTEND_IMAGE_ID"
  printf 'postgres_image_digest=%s\n' "$POSTGRES_IMAGE_ID"
  printf 'finalist_scenario_id=%s\n' "$FINALIST_SCENARIO_ID"
  printf 'api_golden_path=passed\n'
  printf 'browser_roles=business,legal,admin\n'
  printf 'browser_e2e=passed\n'
  printf 'readiness=passed\n'
} | tee "$ROOT/security-artifacts/finalist-runtime-evidence.txt"

echo ""
echo "Passed: 生产 Compose 冒烟 (http://127.0.0.1:${SMOKE_PORT})"
