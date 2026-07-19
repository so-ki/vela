#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPETITION_DB="$ROOT/backend/data/vela_competition.db"
COMPETITION_CHROMA="$ROOT/backend/data/chroma_competition"
COMPETITION_MATERIALS="$ROOT/backend/data/scenario_materials_competition"
BACKEND_URL="http://127.0.0.1:8010"
FRONTEND_URL="http://127.0.0.1:5180"
PYTHON_BIN="$ROOT/backend/.venv/bin/python"
PYTHON_BOOTSTRAP=""

export VELA_APP_MODE="competition"
export VELA_COMPETITION_DB_PATH="$COMPETITION_DB"
export DATABASE_URL="sqlite:///$COMPETITION_DB"
export APP_ENV="development"
export CHROMA_PERSIST_DIR="$COMPETITION_CHROMA"
export VELA_SCENARIO_MATERIALS_DIR="$COMPETITION_MATERIALS"
export ALLOW_OPEN_REGISTRATION="false"
export ALLOW_PASSWORD_LOGIN="true"
export CORPUS_AGENT_ENABLED="false"
export LLM_POLISH_ENABLED="false"
export CORS_ORIGINS="$FRONTEND_URL"
export FRONTEND_URL="$FRONTEND_URL"
export PUBLIC_API_URL="$BACKEND_URL"

require_free_port() {
  local port="$1"
  if ! "$PYTHON_BOOTSTRAP" - "$port" <<'PY'
import socket
import sys

sock = socket.socket()
try:
    sock.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
  then
    echo "REFUSED: 127.0.0.1:${port} 已被占用；比赛启动不会复用未知服务。" >&2
    exit 2
  fi
}

ordinary_database_state() {
  "$PYTHON_BOOTSTRAP" - "$ROOT" "$COMPETITION_DB" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
competition = Path(sys.argv[2]).resolve()
ignored_parts = {".git", ".venv", "node_modules", ".pytest_cache"}
rows = []
for path in root.rglob("*"):
    if not path.is_file() or path.resolve() == competition:
        continue
    if any(part in ignored_parts for part in path.parts):
        continue
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f"{path.relative_to(root)}:{digest}")
print("\n".join(sorted(rows)))
PY
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local pid="$3"
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "REFUSED: ${label} 进程在就绪前退出。" >&2
      return 1
    fi
    sleep 1
  done
  echo "REFUSED: 等待 ${label} 就绪超时：${url}" >&2
  return 1
}

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  local pid
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    if [ -n "$pid" ]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "==> Vela 比赛专用干净入口"

if [ -x "$PYTHON_BIN" ]; then
  PYTHON_BOOTSTRAP="$PYTHON_BIN"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BOOTSTRAP="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BOOTSTRAP="$(command -v python3)"
else
  echo "REFUSED: 未找到 Python 3。" >&2
  exit 2
fi
if ! "$PYTHON_BOOTSTRAP" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
then
  echo "REFUSED: 比赛入口需要 Python 3.12+。" >&2
  exit 2
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "REFUSED: 未找到 Node.js/npm。" >&2
  exit 2
fi
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)'; then
  echo "REFUSED: 比赛入口需要 Node.js 20+。" >&2
  exit 2
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "REFUSED: 未找到 curl，无法执行服务就绪检查。" >&2
  exit 2
fi

require_free_port 8010
require_free_port 5180

if [ ! -x "$PYTHON_BIN" ]; then
  echo "==> 创建 Python 虚拟环境"
  "$PYTHON_BOOTSTRAP" -m venv "$ROOT/backend/.venv"
fi
if ! "$PYTHON_BIN" -c 'import alembic, fastapi, sqlalchemy, uvicorn' >/dev/null 2>&1; then
  echo "==> 安装后端锁定依赖"
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.lock"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "==> 安装前端锁定依赖"
  (cd "$ROOT/frontend" && npm ci)
fi

ORDINARY_DATABASES_BEFORE="$(ordinary_database_state)"

echo "==> 仅重建比赛数据库：$COMPETITION_DB"
"$PYTHON_BIN" "$ROOT/backend/scripts/seed_competition_demo.py" --reset-database

echo "==> 对比赛数据库执行 Alembic migrations"
(cd "$ROOT/backend" && "$PYTHON_BIN" -m alembic upgrade head)

echo "==> Seed 两个演示账户与 Aurora 主演示项目"
SEED_OUTPUT="$("$PYTHON_BIN" "$ROOT/backend/scripts/seed_competition_demo.py")"
echo "$SEED_OUTPUT"
AURORA_SCENARIO_ID="$(echo "$SEED_OUTPUT" | sed -n 's/^AURORA_SCENARIO_ID=//p' | tail -n 1)"
if [ -z "$AURORA_SCENARIO_ID" ]; then
  echo "REFUSED: seed 未返回 Aurora 场景 ID。" >&2
  exit 2
fi

ORDINARY_DATABASES_AFTER_SEED="$(ordinary_database_state)"
if [ "$ORDINARY_DATABASES_BEFORE" != "$ORDINARY_DATABASES_AFTER_SEED" ]; then
  echo "REFUSED: 检测到普通开发数据库发生变化，停止启动。" >&2
  exit 2
fi

COMPETITION_PATH="/competition/$AURORA_SCENARIO_ID/overview"
COMPETITION_URL="$FRONTEND_URL$COMPETITION_PATH"
AUTO_OPEN_URL="$FRONTEND_URL/login?redirect=%2Fcompetition%2F$AURORA_SCENARIO_ID%2Foverview"

echo "==> 启动比赛后端与前端"
(cd "$ROOT" && "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --app-dir "$ROOT/backend") &
BACKEND_PID=$!
(
  cd "$ROOT/frontend"
  VITE_APP_MODE="competition" \
  VITE_COMPETITION_SCENARIO_ID="$AURORA_SCENARIO_ID" \
  VITE_API_PROXY="$BACKEND_URL" \
  npm run dev -- --host 127.0.0.1 --port 5180
) &
FRONTEND_PID=$!

wait_for_url "后端" "$BACKEND_URL/docs" "$BACKEND_PID"
wait_for_url "前端" "$FRONTEND_URL" "$FRONTEND_PID"

ORDINARY_DATABASES_AFTER_START="$(ordinary_database_state)"
if [ "$ORDINARY_DATABASES_BEFORE" != "$ORDINARY_DATABASES_AFTER_START" ]; then
  echo "REFUSED: 服务启动后检测到普通开发数据库发生变化。" >&2
  exit 2
fi

echo ""
echo "比赛服务已就绪："
echo "  前端地址: $FRONTEND_URL"
echo "  后端地址: $BACKEND_URL"
echo "  演示法务: legal@demo.vela"
echo "  演示业务: biz@demo.vela"
echo "  密码: Demo1234!"
echo "  Aurora 场景 ID: $AURORA_SCENARIO_ID"
echo "  比赛主演示完整 URL: $COMPETITION_URL"
echo "  自动打开 URL: $AUTO_OPEN_URL"
echo "  普通开发数据库未被修改: 是"
echo ""

if [ "${VELA_SKIP_BROWSER_OPEN:-0}" != "1" ]; then
  if command -v open >/dev/null 2>&1; then
    open "$AUTO_OPEN_URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$AUTO_OPEN_URL"
  else
    echo "提示: 当前环境没有可用的系统浏览器打开命令，请手动访问自动打开 URL。"
  fi
fi

wait "$BACKEND_PID" "$FRONTEND_PID"
