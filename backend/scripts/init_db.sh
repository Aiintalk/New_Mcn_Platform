#!/bin/bash
# =====================================================================
# MCN Platform — 本地数据库一键初始化
# 用法：bash backend/scripts/init_db.sh
# 前提：本地 PostgreSQL 已启动，数据库 mcn_m1 已创建（用户 postgres）
# =====================================================================
set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-mcn_m1}"
DB_PASS="${DB_PASS:-postgres2026}"

echo "📦 开始初始化数据库: $DB_NAME"

MIGRATIONS_DIR="$(dirname "$0")/../migrations"

for f in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
  echo "  → 执行 $(basename $f) ..."
  PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$f" -q
done

# 种子数据（本地开发用，不提交 GitHub）
SEED_FILE="$(dirname "$0")/../seed_local.sql"
if [ -f "$SEED_FILE" ]; then
  echo "  → 执行 seed_local.sql ..."
  PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$SEED_FILE" -q
else
  echo "  ⚠️  seed_local.sql 不存在，跳过种子数据（请参考 seed_local.sql.example）"
fi

echo "✅ 数据库初始化完成"
