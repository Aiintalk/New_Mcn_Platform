# MCN_Frontend_Agent — M1 Sprint 2 任务指令

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-05  
> 前置条件：Sprint 1 联调通过，后端 Sprint 2 工作台 API 就绪  
> 完成后：回传 PM，等待 Sprint 3（全量接口联调）指令

---

## 必读文档

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Frontend_utf8_bom.md` ← 页面骨架
2. `../project_docs/mcn_workspace_ui.jsx` ← 设计规范（组件/颜色/布局）
3. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 接口契约

---

## 本次任务：运营端 + 管理员端页面真实实现

Sprint 2 目标：所有页面从占位 div 升级为有真实 UI 结构的页面，部分页面接入真实 API（已就绪的），未就绪 API 的页面使用符合字段规范的 Mock 数据（Sprint 3 替换）。

---

## 新增 API 文件

**`src/api/workspace.ts`：**
```typescript
// GET /api/workspace/tools
export const getTools: () => Promise<WorkspaceTool[]>

// GET /api/workspace/tools/{tool_code}
export const getTool: (tool_code: string) => Promise<WorkspaceTool>

// GET /api/admin/workspace/tools
export const adminGetTools: (params?: { status?: string }) => Promise<WorkspaceTool[]>

// PATCH /api/admin/workspace/tools/{tool_code}
export const adminUpdateTool: (tool_code: string, data: Partial<WorkspaceTool>) => Promise<WorkspaceTool>
```

**`src/api/users.ts`（填充真实实现）：**
```typescript
// GET /api/admin/users
export const getUsers: (params: UserListParams) => Promise<PagedData<UserInfo>>

// POST /api/admin/users
export const createUser: (data: CreateUserRequest) => Promise<CreateUserResponse>

// PATCH /api/admin/users/{id}
export const updateUser: (id: number, data: UpdateUserRequest) => Promise<UserInfo>

// POST /api/admin/users/{id}/reset-password
export const resetPassword: (id: number) => Promise<ResetPasswordResponse>

// POST /api/admin/users/{id}/enable
export const enableUser: (id: number) => Promise<void>

// POST /api/admin/users/{id}/disable
export const disableUser: (id: number) => Promise<void>

// DELETE /api/admin/users/{id}
export const deleteUser: (id: number) => Promise<void>
```

---

## 页面实现清单

### 运营端

**`/workspace` — 内容工作台（接入真实 API）**
- 调用 `GET /api/workspace/tools` 获取工具列表
- 以卡片形式展示每个工具（`tool_name / description / category / tags`）
- `status=online` 的卡片可点击，点击跳转 `/workspace/{tool_code}`
- `status=dev` 的卡片显示"开发中"徽标，不可点击
- 参考 `mcn_workspace_ui.jsx` 的 WorkspaceGrid 组件风格
- 加载中显示 Skeleton，空状态显示 EmptyState

**`/workspace/persona-writer` — 人设仿写（占位页，不实现业务）**
- 显示"功能开发中，敬请期待"
- 不实现 AI 生成逻辑

**`/` — 运营首页（Mock 数据）**
- 欢迎语：`你好，{user.real_name}`
- 最近 5 条任务记录（Mock 数据，字段结构与 API 文档一致）
- Sprint 3 接入真实 `/api/tasks` 接口

**`/tasks` — 我的任务（Mock 数据）**
- 任务列表，分页展示
- 字段：task_no / tool_name / status / created_at
- Status 展示用 Tag/Badge 区分颜色
- Sprint 3 接入真实 `/api/tasks` 接口

**`/outputs` — 我的产出（Mock 数据）**
- 产出列表，分页展示
- 字段：title / tool_name / word_count / created_at
- Sprint 3 接入真实 `/api/outputs` 接口

---

### 管理员端

**`/admin/users` — 用户管理（接入真实 API）**
- 列表：分页、keyword 搜索、status/role 筛选
- 操作：创建用户（弹窗）、重置密码、启用/停用、软删除
- 创建成功后显示 initial_password（只显示一次，提示截图保存）
- 参考 `mcn_workspace_ui.jsx` 中用户管理相关组件风格

**`/admin/workspace` — 工具配置（接入真实 API）**
- 工具列表（含 dev 状态）
- 可编辑：tool_name / description / status / sort_order
- PATCH 提交后刷新列表

**`/admin` — 数据看板（Mock 数据）**
- 统计卡片：用户数、今日任务数、产出数、工具数
- Sprint 3 接入真实统计接口

**`/admin/tasks`、`/admin/outputs` — 管理员视图（Mock 数据）**
- 结构同运营端，但展示所有用户的数据
- Sprint 3 接入真实接口

**`/admin/kols`、`/admin/system`、`/admin/logs`、`/admin/audit`、`/admin/config` — 占位页**
- 显示"功能即将上线"或简单空状态
- Sprint 3 实现

---

## 硬性约束

- Mock 数据字段名必须与 API 文档完全一致（`snake_case`），不得自创字段
- 所有接口调用通过 `src/api/` 层
- 颜色走 CSS 变量，不硬编码
- 长列表必须有分页组件（即使是 Mock 数据也要有分页 UI）
- `/workspace/persona-writer` 严禁实现任何 AI/TikHub 调用

---

## 验收标准

1. `/workspace` 展示工具卡片，`persona-writer` 状态为 online 且可点击
2. `/admin/users` 可真实创建用户，创建后显示 initial_password
3. `/admin/users` 可启用/停用/软删除用户，列表实时更新
4. `/admin/workspace` 可修改工具 description/status
5. `/tasks`、`/outputs` 有分页 UI（Mock 数据可接受）
6. 所有页面 TypeScript 零报错
7. 无散落 fetch，无硬编码颜色

---

## 完成后输出格式

```
# 前端 Claude 执行结果 — M1 Sprint 2
## 1. 本次任务
## 2. 完成内容（按页面列出）
## 3. 修改文件清单
## 4. 接入真实 API 的页面（已联调）
## 5. 使用 Mock 数据的页面（Sprint 3 替换）
## 6. 自测结果
## 7. 未完成事项
## 8. 需要 PM 决策的问题
## 9. 建议下一步
```
