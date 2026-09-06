# MCN Information System Platform · M1 Base Permission 权限规则

> 文档定位：本文件定义 M1 系统底座的登录、角色、路由、API、数据权限和强制改密规则。前端隐藏按钮不是权限，所有权限必须以后端校验为准。

---

## 1. 账号来源

M1 不开放自主注册。

```text
所有账号由管理员在后台统一开通。
```

不做：

```text
手机号注册
短信验证码登录
用户自主申请账号
公开注册入口
第三方 OAuth 登录
```

---

## 2. 角色定义

| 角色 | 入口 | 说明 |
|---|---|---|
| `admin` | `/admin` | 管理员，负责账号、工具配置、任务记录、产出记录、日志、服务配置 |
| `operator` | `/` | 运营人员，负责进入内容工作台、使用工具、查看自己的任务和产出 |

---

## 3. 登录后跳转规则

| 条件 | 跳转 |
|---|---|
| 用户不存在 | 停留 `/login`，提示账号或密码错误 |
| 密码错误 | 停留 `/login`，提示账号或密码错误 |
| 用户已停用 | 停留 `/login`，提示账号已停用，请联系管理员 |
| `password_changed_at = null` | 跳转 `/change-password` |
| `role = admin` 且已改密 | 跳转 `/admin` |
| `role = operator` 且已改密 | 跳转 `/` |

---

## 4. 强制改密规则

### 4.1 触发条件

用户满足以下任一条件，必须进入 `/change-password`：

```text
1. 管理员新建账号后首次登录
2. 管理员重置密码后再次登录
3. users.password_changed_at 为空
```

### 4.2 未改密期间允许访问的接口

只允许访问：

```text
GET  /api/auth/me
POST /api/auth/change-password
POST /api/auth/logout
```

禁止访问：

```text
/admin/*
/workspace/*
/tasks
/outputs
所有业务 API
```

### 4.3 改密成功后

```text
1. 更新 password_hash
2. 写入 password_changed_at
3. token_version + 1
4. 当前 Token 失效
5. 前端跳转 /login，要求重新登录
```

---

## 5. 前端路由权限

### 5.1 公共路由

| 路由 | 访问规则 |
|---|---|
| `/login` | 未登录可访问；已登录根据角色跳转 |
| `/change-password` | 仅登录且需要改密的用户访问 |

### 5.2 运营端路由

| 路由 | admin | operator | 说明 |
|---|---:|---:|---|
| `/` | ✅ | ✅ | 运营首页；admin 可访问但默认不跳转到这里 |
| `/workspace` | ✅ | ✅ | 内容工作台 |
| `/workspace/persona-writer` | ✅ | ✅ | 工具入口页；基层阶段只保留入口 |
| `/tasks` | ✅ | ✅ | 我的任务 |
| `/outputs` | ✅ | ✅ | 我的产出 |

### 5.3 管理端路由

| 路由 | admin | operator | 说明 |
|---|---:|---:|---|
| `/admin` | ✅ | ❌ | 数据看板 |
| `/admin/users` | ✅ | ❌ | 用户管理 |
| `/admin/kols` | ✅ | ❌ | 红人管理，基层可先占位 |
| `/admin/workspace` | ✅ | ❌ | 工具配置 |
| `/admin/tasks` | ✅ | ❌ | 全部任务 |
| `/admin/agent-tasks` | ✅ | ❌ | 智能体任务配置与运行监控；阶段一仅开放内容分析 |
| `/admin/outputs` | ✅ | ❌ | 全部产出 |
| `/admin/system` | ✅ | ❌ | 服务状态 |
| `/admin/logs` | ✅ | ❌ | 外部调用日志 |
| `/admin/audit` | ✅ | ❌ | 操作日志 |
| `/admin/config` | ✅ | ❌ | 服务配置 / 密钥池 |

### 5.4 operator 访问 `/admin/*`

前端处理：

```text
跳转 / 或展示 403 页面
```

后端处理：

```json
{
  "success": false,
  "code": "PERMISSION_DENIED",
  "message": "无权限访问",
  "data": null
}
```

---

## 6. API 权限规则

### 6.1 公共 API

| API | 权限 |
|---|---|
| `GET /api/health` | 公开 |
| `GET /api/version` | 公开 |
| `POST /api/auth/login` | 公开 |

### 6.2 登录用户 API

| API | admin | operator |
|---|---:|---:|
| `GET /api/auth/me` | ✅ | ✅ |
| `POST /api/auth/change-password` | ✅ | ✅ |
| `POST /api/auth/logout` | ✅ | ✅ |
| `GET /api/workspace/tools` | ✅ | ✅ |
| `GET /api/workspace/tools/{tool_code}` | ✅ | ✅ |
| `GET /api/tasks` | ✅ | ✅ |
| `GET /api/tasks/{task_id}` | ✅ | ✅，仅自己的 |
| `GET /api/outputs` | ✅ | ✅ |
| `GET /api/outputs/{output_id}` | ✅ | ✅，仅自己的 |
| `GET /api/files/{file_id}` | ✅ | ✅，仅自己的 |
| `POST /api/files/{file_id}/download-url` | ✅ | ✅，仅自己的 |

### 6.3 管理员 API

| API | admin | operator |
|---|---:|---:|
| `/api/admin/users/*` | ✅ | ❌ |
| `/api/admin/workspace/*` | ✅ | ❌ |
| `/api/admin/tasks/*` | ✅ | ❌ |
| `/api/admin/agent-tasks/*` | ✅ | ❌ |
| `/api/admin/outputs/*` | ✅ | ❌ |
| `/api/admin/files/*` | ✅ | ❌ |
| `/api/admin/logs/*` | ✅ | ❌ |
| `/api/admin/config/*` | ✅ | ❌ |

---

## 7. 数据权限规则

### 7.1 users

| 角色 | 可见范围 | 可操作 |
|---|---|---|
| admin | 全部未软删用户 | 创建、编辑、重置密码、启用、停用、删除 |
| operator | 只能通过 `/api/auth/me` 看自己 | 不可管理用户 |

### 7.2 task_jobs

| 角色 | 可见范围 |
|---|---|
| admin | 全部任务 |
| operator | `created_by = 当前用户` |

### 7.3 outputs

| 角色 | 可见范围 |
|---|---|
| admin | 全部产出 |
| operator | `created_by = 当前用户` |

### 7.4 files

| 角色 | 可见范围 |
|---|---|
| admin | 全部文件 |
| operator | 文件关联的 `task_jobs.created_by` 或 `outputs.created_by` 为当前用户 |

### 7.5 operation_logs

| 角色 | 可见范围 |
|---|---|
| admin | 全部操作日志 |
| operator | 不开放列表接口 |

### 7.6 external_service_logs

| 角色 | 可见范围 |
|---|---|
| admin | 全部外部调用日志 |
| operator | 不开放列表接口 |

### 7.7 service_credentials

| 角色 | 可见范围 |
|---|---|
| admin | 可查看密钥配置，但只显示 `secret_tail` |
| operator | 不可访问 |

### 7.8 agent_task_configs 与内容分析任务

| 角色 | 可见范围 | 可操作 |
|---|---|---|
| admin | 全部入驻成功项目的任务范围、周账号候选、输入上下文与全部内容分析运行记录（含内部周批次收尾实例） | 勾选项目、保存共享报告根目录、发起隔离测试、查看详情、对单条失败记录手动重试 |
| operator | 不开放 | 不开放；本期不提供项目级只读权限 |

入驻成功继续沿用现有全局口径：同一项目的 `persona` 与 `content_plan` 均非空。智能体任务配置不得放宽或改写该口径。项目范围按 `agent_code` 独立保存，当前只开放 `content-analysis`。日/周测试可使用全部入驻成功且必要数据库预检通过的项目，不要求进入持续自动运行范围；正式自动周调度仍只使用已选且预检通过项目。项目筛选只能收窄各自对应范围。管理员概览和配置响应可返回原始共享报告根目录引用供编辑，但运行历史中的账号标识统一只返回稳定哈希。周批次收尾只是管理员可见的内部正式任务对象，不新增接口或权限；自动创建与重新收尾不冒充管理员写操作，也不写管理员 `OperationLog`。

`PUT /api/admin/agent-tasks/*/config`、`POST /api/admin/agent-tasks/*/test-runs` 与 `POST /api/admin/agent-tasks/*/runs/{run_id}/retry` 均为管理员写操作，必须分别写入 `operation_logs`；日志只记录智能体编码、项目编号、任务编号、动作结果和是否已配置报告根目录，不记录完整 `sec_uid`、目录引用、人格、内容规划、飞书行或其他正文。自动 tick 只能使用部署配置的有效系统账号作为 `created_by`，缺失或失效时关闭失败，禁止回退为任一管理员账号。

---

## 8. 工具权限规则

### 8.1 工具状态

| 状态 | 运营端展示 | 可进入 | 可调用 API |
|---|---:|---:|---:|
| `online` | ✅ | ✅ | ✅ |
| `dev` | ✅，置灰 | ❌ | ❌ |
| `offline` | ✅，置灰 | ❌ | ❌ |
| `disabled` | ❌ 或置灰 | ❌ | ❌ |

### 8.2 工具配置

只有 `admin` 可以调整工具状态和工具配置。

```text
PATCH /api/admin/workspace/tools/{tool_code}
```

每次调整必须写入 `operation_logs`。

---

## 9. Token 与会话规则

### 9.1 Token 内容

JWT 至少包含：

```json
{
  "sub": "1",
  "username": "admin",
  "role": "admin",
  "token_version": 3,
  "exp": 1780000000
}
```

### 9.2 Token 失效场景

```text
1. 超过过期时间
2. 用户被停用
3. 用户被软删除
4. 用户密码被重置
5. 用户主动退出登录且 token_version 已递增
6. token_version 与数据库不一致
```

---

## 10. 后端权限校验顺序

所有受保护 API 必须按以下顺序校验：

```text
1. 是否携带 Token
2. Token 是否有效
3. 用户是否存在
4. 用户是否已停用 / 软删
5. 是否需要强制改密
6. 当前 API 是否允许该角色访问
7. 当前资源是否属于该用户，或用户是否为 admin
8. 执行业务逻辑
```

---

## 11. 前端权限处理要求

1. 前端必须有统一路由守卫。
2. 未登录访问受保护页面，跳转 `/login`。
3. 需要改密时，除 `/change-password` 外都跳转 `/change-password`。
4. operator 访问 `/admin/*`，展示 403 或跳转 `/`。
5. 前端隐藏按钮只是体验优化，不能代替后端权限。
6. 接口返回 `AUTH_TOKEN_EXPIRED` 时，清除本地 Token 并跳转 `/login`。
7. 接口返回 `AUTH_FORCE_CHANGE_PASSWORD` 时，跳转 `/change-password`。
8. 接口返回 `PERMISSION_DENIED` 时，展示无权限提示。

---

## 12. AI 开发硬性要求

1. 不允许只在前端做权限控制。
2. 不允许 operator 通过改接口参数查看其他人的任务和产出。
3. 不允许未改密用户访问业务接口。
4. 不允许停用用户继续使用旧 Token。
5. 不允许返回明文密码、明文密钥。
6. 不允许删除用户时物理删除数据。
7. 不允许管理员操作不写 `operation_logs`。
8. 不允许外部服务配置接口开放给 operator。
9. 不允许前端自行判断“工具可用”后绕过后端工具状态校验。
10. 所有权限变更必须同步更新本文档。

---

## 13. 内容分析项目库权限（M2 Sprint28）

| 操作 | admin | operator | 说明 |
|------|-------|----------|------|
| 按项目读取内容分析候选 | 允许 | 允许 | 必须显式传项目、分类和可用状态，禁止跨项目返回 |
| 人工加入千川正文 | 允许 | 允许 | 必须指定项目并写 `OperationLog`；不允许直接写跨项目机会池 |
| 停用或恢复候选 | 允许 | 允许 | 软状态变更，必须写 `OperationLog` |
| 人工补标千川开头 | 允许 | 允许 | 片段必须能回到原转写，必须写 `OperationLog` |
| 直接修改跨项目机会池或账号基准 | 禁止 | 禁止 | 本切片没有此类公共接口 |

自动任务的 `created_by` 只能使用部署配置中的系统服务账号，运行日志标记 `trigger_source=system`；配置缺失时自动执行失败关闭，禁止硬编码或冒充真实管理员。测试运行不得写正式项目库、跨项目机会、账号基准或正式飞书目录。
