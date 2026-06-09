# MCN_Backend_Agent — M2 Sprint 2 补充任务（运营端首页接口补充）

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/app/routers/operator_homepage.py`  
> PM 生成时间：2026-06-08  
> 前置条件：M2 Sprint 2 主任务已完成  
> 完成后：回传 PM

---

## 背景

设计稿评审后发现现有 `/api/operator/homepage/stats` 接口缺少以下数据，需在原文件基础上补充，**无需新增接口**。

---

## 一、`GET /api/operator/homepage/stats` 响应补充字段

在原有响应基础上新增 3 处：

### 1.1 统计卡片同比变化率

```json
{
  "today_outputs": 12,
  "today_outputs_change": "+40.0%",   // 新增：今日 vs 昨日，格式 "+40.0%" / "-5.0%" / "0%"

  "week_outputs": 56,
  "week_outputs_change": "+17.4%",    // 新增：本周 vs 上周，格式同上

  "in_progress_tasks": 2,
  // 进行中任务不需要变化率

  "week_token_usage": null,
  // Token 无变化率（字段不存在）
  ...
}
```

**计算规则：**

| 字段 | 分子 | 分母 | 说明 |
|------|------|------|------|
| `today_outputs_change` | 今日产出数 - 昨日产出数 | 昨日产出数 | 昨日为 0 时返回 `null` |
| `week_outputs_change` | 本周产出数 - 上周产出数 | 上周产出数 | 上周为 0 时返回 `null` |

格式化规则：
- 正数：`"+40.0%"`
- 负数：`"-5.0%"`
- 零：`"0%"`
- 分母为 0：返回 `null`（前端显示「—」）

---

### 1.2 工具使用占比（饼图数据）

```json
{
  ...
  "tool_usage_breakdown": [
    { "tool_name": "爆款标题生成", "tool_code": "title-gen",    "count": 24, "percentage": 43.6 },
    { "tool_name": "视频脚本创作", "tool_code": "script-gen",   "count": 12, "percentage": 21.7 },
    { "tool_name": "AI图文创作",   "tool_code": "image-text",   "count": 9,  "percentage": 16.4 },
    { "tool_name": "抖音内容分析", "tool_code": "douyin-analysis","count": 5, "percentage": 9.1 },
    { "tool_name": "其他",         "tool_code": null,            "count": 5,  "percentage": 9.1 }
  ]
}
```

**查询逻辑：**
1. 统计当前用户本周内 `task_jobs` 按 `tool_code` 分组的条数
2. 取前 4 名单独列出，剩余合并为「其他」（`tool_code: null`）
3. `percentage` 保留一位小数，各项加和应等于 100（注意四舍五入误差处理）
4. 若本周无任务，返回空数组 `[]`

---

### 1.3 常用工具数量调整

将原有 `recent_tools` 从返回最近 **3 条** 改为 **6 条**：

```json
{
  ...
  "recent_tools": [
    { "tool_name": "爆款标题生成", "tool_code": "title-gen",     "last_used_at": "2026-06-08T14:30:00Z" },
    { "tool_name": "视频脚本创作", "tool_code": "script-gen",    "last_used_at": "2026-06-08T11:00:00Z" },
    { "tool_name": "AI图文创作",   "tool_code": "image-text",    "last_used_at": "2026-06-07T16:20:00Z" },
    { "tool_name": "抖音内容分析", "tool_code": "douyin-analysis","last_used_at": "2026-06-07T10:00:00Z" },
    { "tool_name": "批量脚本创作", "tool_code": "batch-script",  "last_used_at": "2026-06-06T15:30:00Z" },
    { "tool_name": "内容日历",     "tool_code": "calendar",      "last_used_at": "2026-06-05T09:00:00Z" }
  ]
}
```

查询方式：按 `tool_code` 分组取最近一次 `created_at`，排序后取 TOP 6。

---

## 二、完整响应示例（修改后）

```json
{
  "today_outputs": 12,
  "today_outputs_change": "+40.0%",
  "week_outputs": 56,
  "week_outputs_change": "+17.4%",
  "in_progress_tasks": 2,
  "week_token_usage": null,
  "week_tool_count": 56,
  "tool_usage_breakdown": [
    { "tool_name": "爆款标题生成", "tool_code": "title-gen",  "count": 24, "percentage": 43.6 },
    { "tool_name": "视频脚本创作", "tool_code": "script-gen", "count": 12, "percentage": 21.7 },
    { "tool_name": "AI图文创作",   "tool_code": "image-text", "count": 9,  "percentage": 16.1 },
    { "tool_name": "抖音内容分析", "tool_code": "douyin-analysis", "count": 5, "percentage": 8.9 },
    { "tool_name": "其他",         "tool_code": null,          "count": 6,  "percentage": 10.7 }
  ],
  "recent_tools": [
    { "tool_name": "爆款标题生成", "tool_code": "title-gen",  "last_used_at": "2026-06-08T14:30:00Z" },
    { "tool_name": "视频脚本创作", "tool_code": "script-gen", "last_used_at": "2026-06-08T11:00:00Z" },
    { "tool_name": "AI图文创作",   "tool_code": "image-text", "last_used_at": "2026-06-07T16:20:00Z" },
    { "tool_name": "抖音内容分析", "tool_code": "douyin-analysis", "last_used_at": "2026-06-07T10:00:00Z" },
    { "tool_name": "批量脚本创作", "tool_code": "batch-script","last_used_at": "2026-06-06T15:30:00Z" },
    { "tool_name": "内容日历",     "tool_code": "calendar",   "last_used_at": "2026-06-05T09:00:00Z" }
  ],
  "last_login_at": "2026-06-08T09:00:00Z"
}
```

---

## 三、验收标准

| 检查项 | 预期结果 |
|--------|---------|
| `today_outputs_change` 昨日有数据 | 返回 `"+xx.x%"` 或 `"-xx.x%"` |
| `today_outputs_change` 昨日为 0 | 返回 `null` |
| `week_outputs_change` 上周为 0 | 返回 `null` |
| `tool_usage_breakdown` 本周有任务 | 返回最多5项（前4 + 其他），percentage 之和 ≈ 100 |
| `tool_usage_breakdown` 本周无任务 | 返回 `[]` |
| `recent_tools` | 返回最多 6 条，按最近使用时间降序 |
