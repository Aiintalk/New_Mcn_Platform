#!/bin/bash
# init-db.sh — 初始化 mcn_m1 数据库表结构
# 使用前确认 mcn_m1 数据库已存在
set -e

DB_USER=${DB_USER:-postgres}
DB_HOST=${DB_HOST:-localhost}
DB_PASSWORD=${DB_PASSWORD:-admin123}
SQL_FILE=${SQL_FILE:-../backend/migrations/001_init.sql}

echo "执行建表脚本：$SQL_FILE"
PGPASSWORD=$DB_PASSWORD psql -U "$DB_USER" -h "$DB_HOST" -d mcn_m1 -f "$SQL_FILE"

echo "验证建表结果："
PGPASSWORD=$DB_PASSWORD psql -U "$DB_USER" -h "$DB_HOST" -d mcn_m1 -c "\dt"
echo "✅ 初始化完成"
