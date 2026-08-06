#!/usr/bin/env bash
# init-db.sh — 按顺序执行尚未登记的数据库迁移。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd -P)
PYTHON_BIN=${PYTHON_BIN:-"$PROJECT_ROOT/backend/.venv/bin/python"}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "找不到后端 Python 环境：$PYTHON_BIN" >&2
  echo "请先在 backend/.venv 安装 requirements.txt，或通过 PYTHON_BIN 指定解释器。" >&2
  exit 1
fi

"$PYTHON_BIN" "$PROJECT_ROOT/backend/scripts/run_migrations.py" "$@"
