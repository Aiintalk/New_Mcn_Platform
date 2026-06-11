# MCN_Frontend_Agent — M1 Sprint 3 任务指令

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-06（已更新：补充 AI/TikHub 测试面板 + Key Pool config 字段）  
> 前置条件：Sprint 2 验收通过，后端 Sprint 3 全量 API 就绪后联调  
> 完成后：回传 PM，等待测试 Claude 介入

---

## 必读文档

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Frontend_utf8_bom.md` ← 页面骨架
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 接口契约
3. `../project_docs/mcn_workspace_ui.jsx` ← 设计规范

---

## ⚠️ Sprint 2 工作台修正（先确认）

`GET /api/workspace/tools` 已修正为返回 `online + dev` 状态工具（共 5 条）。
请确认 `/workspace` 页面现在展示 5 个工具卡片，其中 `persona-writer` 可点击，其余 4 个显示"开发中"徽标且不可点击。如有不符请先调整前端逻辑再继续。

---

## 本次任务：全量 Mock 替换为真实 API + 管理员功能页完整实现

---

## Step 1：补充 API 文件

**`src/api/system.ts`：**
```typescript
// POST /api/admin/system/ai-test
export const testAIConnection: () => Promise<AITestResult>

// POST /api/admin/system/tikhub-test
export const testTikHubConnection: () => Promise<ServiceTestResult>
```

**`src/api/tasks.ts`：**
```typescript
// GET /api/tasks
export const getTasks: (params: TaskListParams) => Promise<PagedData<TaskJob>>

// GET /api/tasks/{task_id}
export const getTask: (task_id: number) => Promise<TaskDetail>

// GET /api/admin/tasks
export const adminGetTasks: (params: AdminTaskListParams) => Promise<PagedData<TaskJob>>
```

**`src/api/outputs.ts`：**
```typescript
// GET /api/outputs
export const getOutputs: (params: OutputListParams) => Promise<PagedData<Output>>

// GET /api/outputs/{output_id}
export const getOutput: (output_id: number) => Promise<Output>

// DELETE /api/outputs/{output_id}
export const deleteOutput: (output_id: number) => Promise<void>

// GET /api/admin/outputs
export const adminGetOutputs: (params: AdminOutputListParams) => Promise<PagedData<Output>>
```

**`src/api/logs.ts`：**
```typescript
// GET /api/admin/logs/operation
export const getOperationLogs: (params: LogListParams) => Promise<PagedData<OperationLog>>

// GET /api/admin/logs/external
export const getExternalLogs: (params: LogListParams) => Promise<PagedData<ExternalServiceLog>>
```

**`src/api/credentials.ts`：**
```typescript
// GET /api/admin/config/credentials
export const getCredentials: () => Promise<ServiceCredential[]>

// POST /api/admin/config/credentials
export const createCredential: (data: CreateCredentialRequest) => Promise<ServiceCredential>

// PATCH /api/admin/config/credentials/{id}
export const updateCredential: (id: number, data: UpdateCredentialRequest) => Promise<ServiceCredential>

// DELETE /api/admin/config/credentials/{id}
export const deleteCredential: (id: number) => Promise<void>
```

---

## Step 2：类型补充（`src/types/`）

新增 `src/types/task.ts`、`output.ts`、`log.ts`、`credential.ts`、`system.ts`，字段名与 API 文档完全一致（`snake_case`）。

`system.ts` 类型：
```typescript
interface AITestResult {
  status: 'ok' | 'error'
  model?: string
  latency_ms: number
  reply?: string
  error?: string
}

interface ServiceTestResult {
  status: 'ok' | 'error'
  latency_ms: number
  error?: string
  [key: string]: unknown
}
```

---

## Step 3：运营端 Mock → 真实 API 替换

**`/tasks` — 我的任务（替换 Mock）**
- 接入 `GET /api/tasks`
- 支持 `status` 筛选 Tab（全部 / 进行中 / 成功 / 失败）
- 点击任务行展开 `task_logs`（调 `GET /api/tasks/{task_id}`）
- 分页组件联动真实 `pagination` 数据

**`/outputs` — 我的产出（替换 Mock）**
- 接入 `GET /api/outputs`
- 支持 `tool_code` 筛选
- 每条产出右侧：查看详情（弹窗展示 content）、删除（二次确认）
- 删除后刷新列表

**`/` — 运营首页（替换 Mock）**
- 调 `GET /api/tasks?page=1&page_size=5` 展示最近 5 条任务
- 调 `GET /api/outputs?page=1&page_size=5` 展示最近 5 条产出

---

## Step 4：管理员端功能页完整实现

**`/admin` — 数据看板（接入统计数据）**
- 用 `GET /api/admin/users`（total 字段）展示用户总数
- 用 `GET /api/admin/tasks`（total 字段）展示任务总数
- 用 `GET /api/admin/outputs`（total 字段）展示产出总数
- 工具数固定从 `GET /api/admin/workspace/tools` 取

**`/admin/tasks` — 管理员任务记录（接入真实 API）**
- 接入 `GET /api/admin/tasks`
- 展示所有用户任务，额外显示 `created_by_username`
- 支持按用户、状态、工具筛选

**`/admin/outputs` — 管理员产出记录（接入真实 API）**
- 接入 `GET /api/admin/outputs`
- 支持查看详情、软删除

**`/admin/audit` — 操作日志（接入真实 API）**
- 接入 `GET /api/admin/logs/operation`
- 展示：用户名 / action / target_type / target_id / ip / created_at
- 支持按用户、action 筛选，只读不可操作

**`/admin/logs` — 外部调用日志（接入真实 API）**
- 接入 `GET /api/admin/logs/external`
- 展示：service / action / status / duration_ms / created_at
- 支持按 service、status 筛选，只读

**`/admin/config` — 服务配置/密钥池（接入真实 API）**
- 接入 `GET/POST/PATCH/DELETE /api/admin/config/credentials`
- 展示：provider / label / secret_tail / status / weight / config（JSONB 简要展示，如 model 字段）
- 创建时：
  - 输入 provider / label / secret（password 类型）/ weight / quota_limit
  - **config 字段**：展示为可编辑 JSON textarea（provider=ai 时预填模板 `{"model":"claude-haiku-4-5-20251001","base_url":"https://yunwu.ai/v1"}`）
  - 提交后只展示 secret_tail
- 支持启用/停用、修改 weight、删除（二次确认）
- ⚠️ secret 输入框用 password 类型，禁止展示明文

**`/admin/system` — 服务状态与测试（完整实现）**
- 调 `GET /api/health` 展示后端状态（database / status / time），每 30 秒自动刷新
- **AI 连通性测试区块**：
  - 展示当前 Key 池状态（调 `GET /api/admin/config/credentials?provider=ai` 统计可用数量）
  - "测试 AI 连接"按钮 → 调 `POST /api/admin/system/ai-test`
  - 展示结果：状态（ok/error）、模型名称、延迟（ms）、AI 回复内容
  - 测试中显示 Loading，超时或失败显示红色错误信息
- **TikHub 连通性测试区块**：
  - "测试 TikHub 连接"按钮 → 调 `POST /api/admin/system/tikhub-test`
  - 展示结果：状态（ok/error）、延迟（ms）

**`/admin/kols` — 红人管理（占位页保留）**
- 显示"功能即将上线"，不实现业务逻辑

---

## 硬性约束

- 替换 Mock 的同时，删除所有 Mock 数据变量，不允许 Mock 与真实 API 共存
- 所有分页组件联动真实 `pagination.total / page / page_size`
- `/admin/config` 密钥输入框必须是 `type="password"`
- `secret_enc` 字段不允许出现在任何前端代码中
- 所有接口调用通过 `src/api/` 层

---

## 验收标准

1. `/tasks` 接入真实 API，分页正常，无 Mock 数据残留
2. `/outputs` 删除后列表刷新，软删除生效（后端 `deleted_at` 有值）
3. `/admin/audit` 可看到 Sprint 1-2 期间的历史操作日志
4. `/admin/config` 创建密钥后只展示 `secret_tail`，不展示明文
5. `/admin/system` 展示 `database=ok` 状态，AI 测试按钮可点击并展示 `status/model/latency_ms`
6. `/workspace` 现在展示 5 个工具卡片（1 个 online 可点击，4 个 dev 置灰）
7. 全项目 `npx tsc --noEmit` 零报错
8. 无散落 fetch，无 Mock 数据残留

---

## 完成后输出格式

```
# 前端 Claude 执行结果 — M1 Sprint 3
## 1. 本次任务
## 2. 完成内容（按页面列出）
## 3. 修改文件清单
## 4. 接入真实 API 的页面（联调确认）
## 5. 仍为占位的页面（说明原因）
## 6. 自测结果
## 7. 未完成事项
## 8. 需要 PM 决策的问题
## 9. 建议下一步
```
