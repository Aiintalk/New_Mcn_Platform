#!/bin/bash
# health-check.sh — 检查 MCN 后端健康状态

set -euo pipefail

RESPONSE=$(curl -s http://localhost:8000/api/health)
echo "$RESPONSE" | python3 -m json.tool
STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('status',''))")
if [ "$STATUS" != "ok" ]; then
  echo "ERROR: health check failed (status=$STATUS)"
  exit 1
fi
echo "OK: service is healthy"
