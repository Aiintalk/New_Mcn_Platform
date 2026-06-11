# MCN Information System Platform · 代码审核标准

> 文档定位：本文件是全平台通用代码审核标准，适用于前端（React/TypeScript）和后端（Python/FastAPI）。
> 所有人工审核和 AI 辅助审核均以本文件为准。

---

## 1. 审核触发时机

以下情形**必须**进行代码审核，不得跳过：

| 触发条件 | 审核范围 |
|----------|----------|
| PR 合并到 `main` / `develop` | 全部变更文件 |
| 新增 API 接口 | 接口实现 + 权限校验 + 日志写入 |
| 新增数据库表或字段 | migration 文件 + 对应 model + 文档同步更新 |
| 修改鉴权、权限判断逻辑 | 鉴权中间件 + 所有受影响接口 |
| 修改 AI 调用链路 | adapter + 日志写入 + 并发控制 |
| 修改密钥管理逻辑 | 加密存储 + 脱敏展示 + 轮换策略 |

---

## 2. 审核严重级别

| 级别 | 含义 | 处理要求 |
|------|------|----------|
| **CRITICAL** | 安全漏洞、数据丢失风险 | 必须修复，PR 不得合并 |
| **HIGH** | 功能缺陷、权限绕过、日志缺失 | 必须修复，修复后重新审核 |
| **MEDIUM** | 可维护性问题、不符合规范 | 建议修复，不阻塞合并 |
| **LOW** | 风格建议、命名优化 | 可选，下次迭代处理 |

---

## 3. 安全审核清单（必查）

- [ ] 不包含明文密码、API Key、Token（查 `.env` 是否被 commit）
- [ ] SQL 查询使用参数化，无字符串拼接
- [ ] 用户输入经过 Pydantic 校验（后端）或 Form 校验（前端）
- [ ] 文件操作路径经过清理，无路径穿越风险
- [ ] 鉴权中间件覆盖所有需要保护的接口
- [ ] operator 数据隔离：查询包含 `created_by = 当前用户` 过滤
- [ ] AI / TikHub / OSS 密钥不出现在响应体中
- [ ] 错误信息不暴露数据库结构、文件路径、内部错误堆栈

---

## 4. 后端（Python/FastAPI）审核要点

### 4.1 接口规范

- [ ] 所有接口响应使用统一格式：`{ success, code, message, data }`
- [ ] 字段命名使用 `snake_case`
- [ ] 接口有对应的 Pydantic Request / Response schema（定义在 router 文件内，不单独建 schemas/ 文件）
- [ ] 接口已在 `MCN_M1_Base_API.md` 或 `MCN_M2_Base_API.md` 中登记
- [ ] HTTP 方法语义正确（GET 不改写数据、DELETE 走软删）

### 4.2 数据库操作

- [ ] 使用 SQLAlchemy ORM，复杂查询允许参数化的 `text()` SQL，禁止字符串拼接 SQL
- [ ] 软删除表不物理删除，使用 `deleted_at` 或 `is_active=false`
- [ ] 涉及 operator 权限的查询包含数据隔离过滤
- [ ] 批量操作有事务保护

### 4.3 日志写入

- [ ] 关键操作写入 `operation_logs`（登录、创建、删除、导出等）
- [ ] 外部服务调用写入 `external_service_logs` 或 `ai_call_logs`
- [ ] 任务型操作先创建 `task_jobs`，结束后更新状态

### 4.4 错误处理

- [ ] 有具体的 `HTTPException` 而非通用 500
- [ ] 捕获外部服务异常，写日志后返回友好错误
- [ ] AI 调用在 `finally` 块中释放并发槽位（`active_requests - 1`）

### 4.5 代码质量

- [ ] 函数不超过 50 行（超过需拆分）
- [ ] 文件不超过 800 行
- [ ] 无注释掉的废代码
- [ ] 无 `print()` 调试语句（使用 `logging`）
- [ ] 有 type hint

---

## 5. 前端（React/TypeScript）审核要点

### 5.1 类型安全

- [ ] 无 `any` 类型（或有注释说明原因）
- [ ] API 响应有对应的 TypeScript interface 定义
- [ ] Props 有明确的类型定义

### 5.2 接口调用

- [ ] 所有接口调用通过统一的 `request` 封装（`request.ts`，基于 fetch）
- [ ] 不直接调用 AI / TikHub / OSS / ASR，必须走后端代理
- [ ] 接口错误有统一的 toast/notification 提示

### 5.3 权限控制

- [ ] 路由有权限守卫（admin 路由 operator 不可访问）
- [ ] 按钮/操作在无权限时隐藏或 disabled，不仅依赖后端拦截
- [ ] Token 过期后自动跳转登录页

### 5.4 状态管理

- [ ] 不在全局 store 存敏感信息（密钥、完整 Token 不存 localStorage 明文）
- [ ] 异步请求有 loading、error 状态处理
- [ ] 列表页有分页，不一次性请求全部数据

### 5.5 代码质量

- [ ] 组件不超过 300 行（超过需拆分）
- [ ] 无 `console.log` 调试语句
- [ ] 样式使用 CSS 变量（`var(--brand)` 等），不硬编码颜色
- [ ] 无魔法数字，提取为命名常量

---

## 6. 数据库 Migration 审核要点

- [ ] migration 是纯 SQL 文件（如 `001_init.sql`），非 Alembic，无 `upgrade()`/`downgrade()`
- [ ] 新字段有合理的默认值，不破坏现有数据
- [ ] 新增索引不影响写入性能（超大表需离线索引）
- [ ] 对应的表文档（`MCN_M1_Base_Database.md` 或 `MCN_M2_Base_Database.md`）已同步更新

---

## 7. 不审核的范围

以下内容不在代码审核范围内，由专项 QA 或运营验收：

- AI Prompt 内容质量
- 报告生成的内容准确性
- UI 视觉细节（颜色、间距微调）
- 业务数据的正确性（由验收标准文档覆盖）

---

## 8. 审核流程

```
1. PR 提交者自查本文档清单
2. 指定审核人进行 code review（至少 1 人）
3. 发现 CRITICAL / HIGH 问题，提交评论，PR 打回
4. 提交者修复后，重新请求 review
5. 无 CRITICAL / HIGH 问题，审核人 Approve
6. PM 确认功能符合需求后，合并 PR
```

---

## 9. 修订记录

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-06-08 | 初始版本，覆盖 M1 + M2 阶段 |
