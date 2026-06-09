#!/bin/bash
# stop.sh — 停止 MCN 后端服务

set -euo pipefail

echo "▶ 停止 MCN API 服务..."
pm2 stop mcn-api 2>/dev/null && echo "✓ pm2 进程已停止" || echo "⚠ mcn-api 进程不存在或已停止"

echo "✓ 服务已停止"
