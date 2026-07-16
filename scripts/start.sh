#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

require_free_port() {
  local port="$1"
  if ! python3 - "$port" <<'PY'
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
    echo "REFUSED: 127.0.0.1:${port} 已被占用；请自行停止对应服务或改用其他端口。" >&2
    exit 2
  fi
}

BACKEND_PID=""
FRONTEND_PID=""
OPENER_PID=""

cleanup() {
  local pid
  for pid in "$OPENER_PID" "$FRONTEND_PID" "$BACKEND_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$OPENER_PID" "$FRONTEND_PID" "$BACKEND_PID"; do
    if [ -n "$pid" ]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

echo "==> Vela 出海法务平台 — 本地启动"

require_free_port 8000
require_free_port 5173

# Backend
if [ ! -d "backend/.venv" ]; then
  echo "==> 创建 Python 虚拟环境..."
  python3 -m venv backend/.venv
fi

echo "==> 安装后端依赖..."
backend/.venv/bin/pip install -q -r backend/requirements.txt
echo "==> 安装 RAG 依赖 (ChromaDB)..."
backend/.venv/bin/pip install -q -r backend/requirements-rag.txt

if [ ! -f "backend/.env" ]; then
  if [ -f "backend/.env.example" ]; then
    cp backend/.env.example backend/.env
    echo "==> 已复制 backend/.env.example → backend/.env"
  else
    echo "==> 发布包未包含 .env*；本地将使用开发默认值。LLM Key 请通过环境变量安全注入。"
  fi
fi

echo "==> 初始化本地开发数据库与演示账户（生产部署不会执行）..."
backend/.venv/bin/python backend/scripts/seed_demo_user.py

# Frontend
if [ ! -d "frontend/node_modules" ]; then
  echo "==> 安装前端依赖..."
  (cd frontend && npm install)
fi

echo ""
echo "启动服务："
echo "  后端 API:  http://127.0.0.1:8000"
echo "  API 文档:  http://127.0.0.1:8000/docs  （应能看到「协查场景」接口）"
echo "  前端页面:  http://127.0.0.1:5173"
echo "  演示账户:  法务 legal@demo.vela / 业务 biz@demo.vela （密码均为 Demo1234!）"
echo ""
echo "正式链路：业务上传并确认知情 → 法务确认范围并生成 → 复核定稿"
echo ""

(backend/.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend) &
BACKEND_PID=$!
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

# 等待前端就绪后自动打开浏览器（macOS / Linux）
(
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "http://127.0.0.1:5173" >/dev/null 2>&1; then
      if command -v open >/dev/null 2>&1; then
        open "http://127.0.0.1:5173"
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://127.0.0.1:5173"
      fi
      break
    fi
    sleep 1
  done
) &
OPENER_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
