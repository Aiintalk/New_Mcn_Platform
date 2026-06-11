# MCN_DevOps_Agent — M1 Sprint 1 任务指令

> 角色：MCN_DevOps_Agent（运维 Claude）  
> 工作目录：`deploy/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：`tasks/M1_Sprint0.md` 验收通过，`deploy/` 基础结构已创建  
> 完成后：回传 PM，等待 Sprint 4 部署指令

---

## 必读文档

1. `../project_docs/MCN_M1_部署与容量评估.md` ← 部署配置权威文档

---

## 本次任务：补充数据库环境配置

### 要做什么

1. 更新 `deploy/README.md`，在"本地开发"章节补充数据库信息：

   ```markdown
   ## 数据库环境（本地开发）

   | 项目 | 值 |
   |---|---|
   | 版本 | PostgreSQL 18.4 |
   | 地址 | localhost:5432 |
   | 用户 | postgres |
   | 密码 | admin123 |
   | M1 开发库 | mcn_m1（已创建） |
   | 旧系统库 | mcn_platform（保留，不操作） |
   | psql 路径 | D:\ProtgreSQL\bin\psql.exe |

   ## 建表步骤

   # 执行建表脚本（后端 Sprint 1 生成）
   D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -f backend/migrations/001_init.sql

   # 验证（应看到 11 张表）
   D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -c "\dt"
   ```

2. 新增 `deploy/scripts/init-db.sh`：
   ```bash
   #!/bin/bash
   # 初始化 mcn_m1 数据库表结构
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
   ```

3. 确认 `deploy/scripts/health-check.sh` 中后端地址为 `localhost:8000`

### 不做什么

- 不部署到测试服（Sprint 4 任务）
- 不修改业务代码

---

## 验收标准

1. `deploy/README.md` 包含数据库环境说明和建表步骤
2. `deploy/scripts/init-db.sh` 存在
3. `bash -n deploy/scripts/init-db.sh` 语法检查通过
4. 脚本中无明文密钥（密码通过环境变量传入）

---

## 完成后输出格式

```
# 运维 Claude 执行结果 — M1 Sprint 1
## 1. 本次任务
## 2. 更新的配置文件清单
## 3. 脚本语法验证结果
## 4. 需要 PM 决策的问题
## 5. 建议下一步
```
