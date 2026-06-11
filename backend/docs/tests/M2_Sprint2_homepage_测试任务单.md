# MCN Platform · M2 Sprint 2 测试任务单（运营首页重设计）

> 测试范围：运营首页统计 + 趋势图 + 常用工具 + 前端图表渲染
> 测试时间：
> 测试人：
> 测试环境：本地开发环境

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 后端地址 | `http://localhost:8000` |
| 前端地址 | `http://localhost:5173` |
| 数据库 | PostgreSQL `mcn_m1` @ localhost:5432 |
| 测试账号 | admin（已改密）/ testop（operator，密码 Operator@123） |
| 前置条件 | 数据库中有 task_jobs / outputs / kols 等基础数据 |

---

## 第一章：统计卡片接口

### 1.1 GET `/api/operator/homepage/stats`

**前置：operator 已登录。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-001 | operator 调用 stats | 200，返回 `{ tasks_today, outputs_total, active_kols, tools_online }` | |
| HP-002 | 响应字段类型正确 | tasks_total / outputs_total / active_kols 为整数，tools_online 为整数 | |
| HP-003 | `tasks_today` 仅计算当天创建的任务 | DB 验证：`WHERE DATE(created_at) = TODAY AND created_by = operator_id` | |
| HP-004 | `outputs_total` 计算当前用户全部产出 | DB 验证：`WHERE created_by = operator_id AND deleted_at IS NULL` | |
| HP-005 | `active_kols` 计算活跃红人数 | 为非负整数 | |
| HP-006 | `tools_online` 计算在线工具数 | 为非负整数 | |
| HP-007 | 数据隔离：operator 只看自己的数据 | tasks_today 和 outputs_total 仅含当前 operator 的 | |
| HP-008 | admin 调用 stats | 200，返回全局数据（不按 operator 过滤） | |
| HP-009 | 未登录调用 stats | 401 / AUTH_TOKEN_MISSING | |

### 1.2 `tool_distribution`（工具占比）

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-010 | stats 响应包含 `tool_distribution` | 数组，每条含 `{ name, value }` | |
| HP-011 | 各工具 value 合理 | value 为正整数或 0 | |

### 1.3 `frequently_used_tools`（常用工具）

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-012 | stats 响应包含 `frequently_used_tools` | 数组，最多 6 个工具 | |
| HP-013 | 每个工具含必要字段 | 含 `id` / `name` / `icon` / `status` / `slug` 等 | |

---

## 第二章：趋势图接口

### 2.1 GET `/api/operator/homepage/trend`

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-014 | 默认 `?days=7` | 200，返回 `line_chart` 数组（7 条）+ `tool_distribution` | |
| HP-015 | `?days=30` | 200，返回 30 条数据 | |
| HP-016 | `?days=999`（非法值） | 200 或 400（以实际实现为准） | |
| HP-017 | `line_chart` 每条结构正确 | 含 `{ date, tasks, outputs }` | |
| HP-018 | `date` 格式正确 | 为 `MM-DD` 格式字符串 | |
| HP-019 | `tasks` 和 `outputs` 为非负整数 | 验证字段类型 | |
| HP-020 | 数据隔离：operator 只看自己的趋势 | 仅含 `created_by = operator_id` 的数据 | |
| HP-021 | admin 调用 trend | 200，返回全局趋势数据 | |

---

## 第三章：前端页面验证

**前置：operator 已登录，浏览器打开前端。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-022 | 打开运营首页 `/` | 显示 4 个统计卡片 | |
| HP-023 | 卡片数值与接口一致 | F12 Network 查看 stats 接口，比对页面展示 | |
| HP-024 | 折线图正常渲染 | recharts 折线图显示，有 X/Y 轴，有数据点 | |
| HP-025 | 环形图（工具占比）正常渲染 | recharts PieChart 显示 | |
| HP-026 | 常用工具区域展示 | 显示最多 6 个工具卡片 | |
| HP-027 | 导航栏正确 | 4 个导航项：概览 / 创作中心 / 任务中心 / 产出中心 | |
| HP-028 | F12 Console 无红色报错 | 页面 JS 无异常 | |

---

## 第四章：边界与异常

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| HP-029 | 无数据时打开首页 | 卡片显示 0，图表显示空状态或空图 | |
| HP-030 | `week_token_usage` 字段 | 返回 null（task_jobs 无 token 字段） | |
| HP-031 | 并发：20 个请求同时调 stats | 全部 200，响应时间 < 2s | |

---

## 一票否决项

```
1. operator 能看到其他 operator 的数据
2. API 响应结构不是 { success, code, message, data }
3. 无 JWT 也能请求到 stats/trend 接口
4. 列表无分页（如有分页接口）
```

---

## 测试结果汇总模板

```
项目：MCN Information System Platform
阶段：M2 Sprint 2 — 运营首页重设计
测试日期：
测试人：

总计：__ 项
通过：__ 项
失败：__ 项

一票否决项：无 / 有（描述）

失败项清单：
- 编号：xxx，失败原因：

结论：通过 / 不通过
```
