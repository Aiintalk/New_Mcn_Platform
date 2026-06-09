# 后端/运维任务单 · kol-intake 数据库更新

> 执行时机：前端「页面整合」任务完成后执行（或与前端同步执行均可）。
> 执行方式：在生产/测试数据库中直接执行以下 SQL，或在后端开发工具（如 DBeaver、psql）中运行。

---

## 执行 SQL

```sql
UPDATE workspace_tools
SET tool_name = '红人信息采集助手',
    status    = 'online'
WHERE tool_code = 'kol-intake';
```

### 说明

| 字段 | 原值 | 新值 | 原因 |
|------|------|------|------|
| `tool_name` | `红人入驻问卷` | `红人信息采集助手` | 产品改名 |
| `status` | `dev` | `online` | 功能已上线，开放运营端访问 |

---

## 验证

执行后运行以下查询确认结果：

```sql
SELECT tool_code, tool_name, status
FROM workspace_tools
WHERE tool_code = 'kol-intake';
```

预期输出：

| tool_code | tool_name | status |
|-----------|-----------|--------|
| kol-intake | 红人信息采集助手 | online |

---

## 影响范围

- 运营端「创作中心」工具卡片显示名称更新为「红人信息采集助手」
- 工具状态由开发中变为在线，运营可正常点击进入
- 路由、API、其他表均不受影响
