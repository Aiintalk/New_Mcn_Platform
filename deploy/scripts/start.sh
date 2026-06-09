#!/bin/bash
# start.sh — 启动 MCN 后端服务（Python FastAPI + uvicorn）
# 依赖：.venv 已创建，backend/.env 已就位

# 切换到 backend 目录
cd "$(dirname "$0")/../../backend"

source .venv/bin/activate 2>/dev/null || true

# 确保日志和 PID 目录存在
mkdir -p ../deploy/logs ../deploy/pids

nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  > ../deploy/logs/backend.log 2>&1 &
echo $! > ../deploy/pids/backend.pid
echo "后端已启动，PID: $!"

# 重载 Nginx（如已安装）
nginx -t && sudo nginx -s reload 2>/dev/null || echo "Nginx 未安装或无权限，跳过"
