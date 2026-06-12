# MCN_DevOps_Agent — M2 Sprint 3 任务指令（对标分析助手）

> **角色**：运维  
> **PM 生成日期**：2026-06-10  
> **前置依赖**：后端代码已合并  
> **完成后**：回传 PM

---

## M2 Sprint 3 运维任务

### 任务 1：执行数据库迁移

```bash
psql -U postgres -d mcn_platform -f backend/migrations/007_benchmark.sql
```

**验证：**

```sql
-- 1. 表存在
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('benchmark_configs', 'benchmark_analyses');

-- 2. 初始 Prompt 配置
SELECT config_key, is_active, length(system_prompt) as prompt_len
FROM benchmark_configs;
-- 预期：1 行，config_key='analyze', is_active=true, prompt_len > 0

-- 3. workspace_tools 注册
SELECT tool_code, tool_name, status FROM workspace_tools WHERE tool_code = 'benchmark';
-- 预期：1 行，status='online'

-- 4. 索引
SELECT indexname FROM pg_indexes WHERE tablename = 'benchmark_analyses';
-- 预期：idx_benchmark_analyses_user, idx_benchmark_analyses_created
```

---

### 任务 2：创建报告存储目录

```bash
mkdir -p backend/storage/benchmark_reports
chmod 755 backend/storage/benchmark_reports
```

**验证：**
```bash
ls -la backend/storage/benchmark_reports
# 预期：目录存在，权限 755
```

---

### 任务 3：重启后端服务

```bash
# 开发环境
pkill -f "uvicorn app.main:app"
cd backend && uvicorn app.main:app --reload --port 8000 &

# 生产环境（systemctl）
sudo systemctl restart mcn-backend

# 生产环境（pm2）
pm2 restart mcn-backend
```

**验证：**
```bash
curl -s http://localhost:8000/api/health | jq .
# 预期：{"status": "ok"}
```

---

## 联调修复记录（2026-06-10）

| # | 问题 | 修复 |
|---|------|------|
| 1 | ORM 模型 `is_active` 类型与数据库不匹配（Integer vs Boolean） | 已修正为 `Column(Boolean)`，需重启后端 |
| 2 | TikHub `get_sec_user_id` 响应格式与代码预期不一致 | 已修正解析逻辑 |

**注意：** 以上修复已包含在代码中，无需额外迁移操作，重启后端即可生效。

---

## 验收标准

| # | 检查项 | 验证方法 | 预期结果 |
|---|--------|----------|----------|
| 1 | benchmark_configs 表 | `SELECT count(*) FROM benchmark_configs` | 1 |
| 2 | benchmark_analyses 表 | `SELECT count(*) FROM benchmark_analyses` | 0（空表） |
| 3 | workspace_tools 注册 | `SELECT status FROM workspace_tools WHERE tool_code='benchmark'` | online |
| 4 | 存储目录 | `ls backend/storage/benchmark_reports` | 目录存在 |
| 5 | 后端启动 | `curl http://localhost:8000/api/health` | 200 OK |
| 6 | 路由注册 | `curl http://localhost:8000/docs` 查看 OpenAPI | /operator/benchmark/* 和 /admin/benchmark/* 存在 |
