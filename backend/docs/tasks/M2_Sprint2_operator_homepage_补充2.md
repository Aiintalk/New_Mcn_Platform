# MCN_Backend_Agent — M2 Sprint 2 补充任务2（管理端使用日志接口）

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-09  
> 前置条件：M2 Sprint 2 主任务已完成  
> 完成后：回传 PM，等待前端联调

---

## 背景

管理员需要查看各运营人员的功能使用记录，包括：用了哪个功能、什么时间、生成了多少次。  
数据已在现有表中（`persona_reports`、`kol_intake_submissions`、`kol_intake_operator_sessions`、`outputs`、`task_jobs`），只需新增聚合查询接口。

---

## 一、新增接口

新建文件 `backend/app/routers/admin_usage_log.py`

---

### 1.1 GET `/api/admin/usage-logs` — 使用日志列表

JWT 鉴权，`current_user.role == "admin"`

Query 参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数，最大50 |
| `user_id` | int | null | 筛选指定运营 |
| `feature` | str | null | 筛选功能：`kol-intake` / `persona-positioning` / `other` |
| `date_from` | date | null | 开始日期（含），格式 `YYYY-MM-DD` |
| `date_to` | date | null | 结束日期（含），格式 `YYYY-MM-DD` |

**查询逻辑：**

从以下多个数据源聚合，UNION ALL 合并：

```sql
-- 1. 红人入驻问卷（运营直发会话）
SELECT
    u.id         AS user_id,
    u.username   AS username,
    u.display_name AS display_name,
    'kol-intake' AS feature,
    '红人入驻问卷' AS feature_name,
    s.created_at AS created_at
FROM kol_intake_operator_sessions s
JOIN users u ON u.id = s.operator_id

UNION ALL

-- 2. 人格定位
SELECT
    u.id, u.username, u.display_name,
    'persona-positioning',
    '人格定位',
    r.created_at
FROM persona_reports r
JOIN users u ON u.id = r.operator_id

UNION ALL

-- 3. 其他 AI 任务（task_jobs）
SELECT
    u.id, u.username, u.display_name,
    COALESCE(j.tool_code, 'other'),
    COALESCE(t.tool_name, '其他工具'),
    j.created_at
FROM task_jobs j
JOIN users u ON u.id = j.created_by
LEFT JOIN workspace_tools t ON t.tool_code = j.tool_code
```

按 `created_at` 倒序分页返回。

**响应：**
```json
{
  "total": 156,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "user_id": 3,
      "username": "operator01",
      "display_name": "张三",
      "feature": "persona-positioning",
      "feature_name": "人格定位",
      "created_at": "2026-06-09T14:30:00Z"
    }
  ]
}
```

---

### 1.2 GET `/api/admin/usage-logs/summary` — 使用汇总统计

JWT 鉴权，`current_user.role == "admin"`

Query 参数：`date_from` / `date_to`（同上，默认最近30天）

**响应：**
```json
{
  "date_from": "2026-05-10",
  "date_to": "2026-06-09",
  "total_count": 156,
  "by_feature": [
    { "feature": "kol-intake",           "feature_name": "红人入驻问卷", "count": 89 },
    { "feature": "persona-positioning",  "feature_name": "人格定位",     "count": 34 },
    { "feature": "other",                "feature_name": "其他工具",      "count": 33 }
  ],
  "by_user": [
    { "user_id": 3, "username": "operator01", "display_name": "张三", "count": 67 },
    { "user_id": 4, "username": "operator02", "display_name": "李四", "count": 52 }
  ]
}
```

`by_user` 返回使用次数 TOP 10，按 count 倒序。

---

## 二、路由注册

`backend/app/main.py`：

```python
from app.routers import admin_usage_log

app.include_router(admin_usage_log.router, prefix="/api/admin", tags=["admin-usage-log"])
```

---

## 三、注意事项

1. **persona_reports 表依赖**：此表由 M2 Sprint 3 创建，若 Sprint 3 未执行，`persona-positioning` 来源的 UNION 分支直接跳过（用 `IF EXISTS` 或捕获异常）。Sprint 2 补充2 先只聚合已存在的表。

2. **数据隔离**：管理员可查看全部运营人员数据，无需 `user_id` 过滤（除非传了筛选参数）。

3. **时区**：日期边界按 Asia/Shanghai 时区计算。

---

## 四、验收标准

| 检查项 | 预期结果 |
|--------|---------|
| `GET /api/admin/usage-logs` | 返回分页列表，含 user、feature、时间 |
| `feature=kol-intake` 筛选 | 只返回问卷相关记录 |
| `user_id=3` 筛选 | 只返回指定运营的记录 |
| `GET /api/admin/usage-logs/summary` | 返回 by_feature + by_user 汇总 |
| 非管理员请求 | 返回 403 |
