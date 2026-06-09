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

