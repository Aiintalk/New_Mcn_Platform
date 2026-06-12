#!/bin/bash
# =====================================================================
# MCN Platform — 测试数据库一键初始化
# 用法：bash backend/scripts/init_test_db.sh
# 效果：创建 mcn_test 数据库（表由 conftest.py 的 Base.metadata.create_all 自动建删）
# =====================================================================
set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_PASS="${DB_PASS:-admin123}"
TEST_DB="${TEST_DB:-mcn_test}"

echo "🔧 初始化测试数据库: $TEST_DB"

# 创建数据库（如果不存在）
DB_EXISTS=$(PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$TEST_DB'" 2>/dev/null || echo "")

if [ "$DB_EXISTS" = "1" ]; then
  echo "  ✅ 数据库 $TEST_DB 已存在，跳过创建"
else
  PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -c \
    "CREATE DATABASE $TEST_DB;" -q
  echo "  ✅ 数据库 $TEST_DB 创建成功"
fi

echo ""
echo "📋 说明："
echo "  - 测试表由 conftest.py 自动管理（session 开始建表、结束删表）"
echo "  - 无需手动建表，直接运行: cd backend && pytest tests/ -v"
echo ""
echo "✅ 测试数据库初始化完成"
