#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

free_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "==> 释放端口 ${port} (停止旧进程)..."
    kill $pids 2>/dev/null || true
    sleep 2
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      kill -9 $pids 2>/dev/null || true
      sleep 1
    fi
  fi
}

echo "==> Vela 出海法务平台 — 本地启动"

free_port 8000
free_port 5173

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
  cp backend/.env.example backend/.env
  echo "==> 已复制 backend/.env.example → backend/.env"
fi

echo "==> 初始化数据库与演示账户..."
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
echo "生成清单：登录 → 提交场景 → 一键生成演示清单"
echo ""

trap 'kill 0' EXIT

backend/.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend &
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
wait
