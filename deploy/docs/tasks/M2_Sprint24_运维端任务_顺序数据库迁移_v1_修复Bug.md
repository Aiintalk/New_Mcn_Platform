# M2 Sprint 24 运维端任务：顺序数据库迁移 v1（修复 Bug）

## 根因

旧 `deploy/scripts/init-db.sh` 固定只执行 `001_init.sql`；后续部署把“执行新 migration”留成手工注释。代码更新与数据库结构更新没有同一闸门，因此生产可部署读取 050 新字段的代码，却遗漏 050。

## 修复

- `init-db.sh` 改为调用 `backend/scripts/run_migrations.py`。
- 迁移按数字前缀、完整文件名排序。
- `schema_migrations` 记录文件名、版本、SHA-256 校验和、执行方式和时间。
- 每个文件在独立事务内执行并登记；失败回滚该文件。
- PostgreSQL advisory lock 防止并发部署。
- 既有库没有账本时必须显式核对并传 `--baseline-through`。
- 已由旧流程人工执行的后续文件可在核实结构后用 `--adopt-existing` 单独登记。

## 生产边界

本任务只交付代码与运行手册。备份、首次基线、生产迁移、服务重启和页面复验均需 PM 在变更窗口单独批准。

详细步骤见 `deploy/README.md` §3.3。
