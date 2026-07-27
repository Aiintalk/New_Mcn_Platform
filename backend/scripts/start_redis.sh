#!/bin/bash
# =====================================================================
# 评测模块 Redis（dev）—— 独立 docker 容器，仅评测模块使用
#
# 为什么独立容器：Redis 只服务评测模块异步运行（arq），与主工程其它部分解耦；
# 将来评测工程独立部署时，连同此 Redis 一起迁出，不影响主工程。
#
# 用法：bash backend/scripts/start_redis.sh
# 默认端口 6379，可用 REDIS_PORT=6380 bash ... 改端口
# .env 里：REDIS_URL=redis://localhost:6379/0
# =====================================================================
set -e
NAME=mcn-redis
PORT=${REDIS_PORT:-6379}

if docker ps --format '{{.Names}}' | grep -q "^${NAME}$"; then
  echo "✓ ${NAME} 已在运行 → $(docker port "$NAME" 6379 | head -1)"
else
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -p "${PORT}:6379" redis:7-alpine >/dev/null
  sleep 1
  echo "✓ 已启动 ${NAME}（redis:7-alpine）→ localhost:${PORT}"
fi
echo "  健康检查：$(docker exec "$NAME" redis-cli ping)"
echo "  REDIS_URL=redis://localhost:${PORT}/0"
