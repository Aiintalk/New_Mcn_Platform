# MCN_Backend_Agent — M2 Sprint 2 任务指令（运营端首页数据接口）

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-08  
> 前置条件：M1 全部验收通过  
> 完成后：回传 PM，等待前端联调

---

## M2 Sprint 2 目标

为重设计后的运营端首页提供两个聚合统计接口：

1. `GET /api/operator/homepage/stats` — 数字统计卡片 + 个人使用情况
2. `GET /api/operator/homepage/trend` — 最近7天内容产出趋势

---

## 一、接口设计

### 1.1 `GET /api/operator/homepage/stats`

JWT 鉴权，`current_user.role in ["operator", "admin"]`

**响应：**
```json
{
  "today_outputs": 3,
  "week_outputs": 18,
  "in_progress_tasks": 2,
  "week_token_usage": 45200,
  "week_tool_count": 12,
  "recent_tools": [
    { "tool_name": "爆款标题生成", "tool_code": "title-gen", "last_used_at": "2026-06-08T14:30:00Z" },
    { "tool_name": "脚本创作", "tool_code": "script-gen", "last_used_at": "2026-06-07T10:15:00Z" }
  ],
  "last_login_at": "2026-06-08T09:00:00Z"
}
```

**各字段数据来源说明：**

| 字段 | 数据来源 | 查询条件 |
|------|----------|---------|
| `today_outputs` | `outputs` 表 | `operator_id = current_user.id` AND `DATE(created_at) = TODAY` |
| `week_outputs` | `outputs` 表 | `operator_id = current_user.id` AND `created_at >= 本周一 00:00` |
| `in_progress_tasks` | `task_jobs` 表 | `operator_id = current_user.id` AND `status = 'processing'` |
| `week_token_usage` | 见下方说明 | `operator_id = current_user.id` AND 本周 |
| `week_tool_count` | `task_jobs` 表 | `operator_id = current_user.id` AND `created_at >= 本周一 00:00` |
| `recent_tools` | `task_jobs` 表 JOIN `workspace_tools` | 按 `tool_code` 分组，取最近使用时间，返回最近3个 |
| `last_login_at` | `users` 表 `last_login_at` 字段（若存在）或 auth 日志 | `id = current_user.id` |

> ⚠️ **Token 用量字段说明：**  
> 请确认现有数据库中是否有记录 token 用量的表（如 `task_jobs.token_used`、`ai_usage` 等）。  
> - 若有，直接按 `operator_id` 和本周时间范围聚合 SUM
> - 若无，返回 `null`，前端显示「暂无数据」
> - 请在回传时告知实际字段来源

> ⚠️ **last_login_at 字段说明：**  
> 请确认 `users` 表是否有 `last_login_at` 字段。  
> - 若有，直接返回
> - 若无，返回 `null`，前端显示「—」
> - 不需要为此专门新增登录日志

---

### 1.2 `GET /api/operator/homepage/trend`

JWT 鉴权，`current_user.role in ["operator", "admin"]`

**响应：**
```json
{
  "trend": [
    { "date": "06-02", "count": 2 },
    { "date": "06-03", "count": 5 },
    { "date": "06-04", "count": 0 },
    { "date": "06-05", "count": 8 },
    { "date": "06-06", "count": 3 },
    { "date": "06-07", "count": 6 },
    { "date": "06-08", "count": 4 }
  ]
}
```

**查询逻辑：**
- 统计最近7天（含今天）每天的 outputs 产出数量
- 条件：`operator_id = current_user.id`
- 没有产出的日期也需返回，count 为 `0`（不能缺日期）
- `date` 格式：`MM-DD`（两位月份-两位日期）

---

## 二、路由文件

在已有的 operator 路由文件中追加这两个接口，**无需新建路由文件**。

路由注册位置：`backend/app/routers/operator.py`（或当前 operator 相关路由文件）

```python
@router.get("/homepage/stats")
async def get_homepage_stats(current_user: ..., db: ...):
    ...

@router.get("/homepage/trend")
async def get_homepage_trend(current_user: ..., db: ...):
    ...
```

---

## 三、注意事项

1. **时区**：本周/今日的时间边界按服务器时区（Asia/Shanghai）计算
2. **本周起始**：周一 00:00:00 为本周开始
3. **性能**：两个接口均为单用户查询，数据量小，无需缓存

---

## 四、验收标准

| 检查项 | 预期结果 |
|--------|---------|
| `GET /api/operator/homepage/stats` | 返回7个字段，token/last_login 若无数据返回 null |
| `GET /api/operator/homepage/trend` | 返回精确7条记录，无产出日期 count=0 |
| 日期无数据时 trend 不缺项 | 7条均返回，count=0 |
| 鉴权 | 未登录返回 401 |
| 数据隔离 | 仅返回当前用户的数据 |
