# MCN Information System Platform · M1 Base Frontend 页面骨架

> 文档定位：本文件定义 M1 系统底座阶段的前端页面、路由、组件复用、接口绑定和开发边界。本文不展开 persona-writer 的完整业务页面，只保留内容工作台入口和占位。

---

## 1. 前端技术栈

```text
React
Vite
Ant Design
TypeScript 建议使用
```

样式必须遵守现有《MCN 内容工作台 · 前端设计文档》。页面风格为：

```text
暖纸底 + 白色卡片 + 品牌橙 #f59a23 + 灰色文字层级 + 编辑感数字
```

---

## 2. 设计硬约束

1. 主题色固定为 `#f59a23`。
2. 颜色和字体优先走 CSS 变量。
3. 不允许页面内随意写死新颜色。
4. 不允许新增一套与现有风格冲突的组件。
5. 所有卡片、按钮、输入框、状态徽标、抽屉、弹窗应复用共享组件。
6. 所有长列表必须分页。
7. 概览页只展示最近 5 条，其余跳转到完整列表页。
8. 当前在线、详情、长内容建议用 Drawer。
9. 登录页不提供自主注册入口。
10. Mock 数据必须集中放置，字段必须与 API 文档一致。

---

## 3. 路由结构

### 3.1 公共路由

```text
/login
/change-password
```

### 3.2 运营端路由

```text
/
/workspace
/workspace/persona-writer
/tasks
/outputs
```

### 3.3 管理端路由

```text
/admin
/admin/users
/admin/kols
/admin/workspace
/admin/tasks
/admin/outputs
/admin/system
/admin/logs
/admin/audit
/admin/config
```

### 3.4 兜底路由

```text
/403
/404
```

---

## 4. 基础目录建议

```text
src/
├── api/
│   ├── request.ts
│   ├── auth.ts
│   ├── users.ts
│   ├── workspace.ts
│   ├── tasks.ts
│   ├── outputs.ts
│   ├── files.ts
│   └── logs.ts
│
├── components/
│   ├── Card.tsx
│   ├── Button.tsx
│   ├── Field.tsx
│   ├── StatusChip.tsx
│   ├── PageHeader.tsx
│   ├── Pager.tsx
│   ├── EmptyState.tsx
│   ├── Modal.tsx
│   ├── Drawer.tsx
│   └── Toast.tsx
│
├── layouts/
│   ├── AuthLayout.tsx
│   └── AppShell.tsx
│
├── routes/
│   ├── ProtectedRoute.tsx
│   └── AdminRoute.tsx
│
├── pages/
│   ├── LoginPage.tsx
│   ├── ChangePasswordPage.tsx
│   ├── operator/
│   │   ├── HomePage.tsx
│   │   ├── WorkspacePage.tsx
│   │   ├── PersonaWriterPlaceholder.tsx
│   │   ├── TasksPage.tsx
│   │   └── OutputsPage.tsx
│   └── admin/
│       ├── AdminDashboardPage.tsx
│       ├── UsersPage.tsx
│       ├── KolsPage.tsx
│       ├── WorkspaceConfigPage.tsx
│       ├── AdminTasksPage.tsx
│       ├── AdminOutputsPage.tsx
│       ├── ServiceStatusPage.tsx
│       ├── ExternalLogsPage.tsx
│       ├── OperationLogsPage.tsx
│       └── ServiceConfigPage.tsx
│
├── store/
│   └── authStore.ts
│
├── types/
│   ├── api.ts
│   ├── user.ts
│   ├── workspace.ts
│   ├── task.ts
│   ├── output.ts
│   └── file.ts
│
└── main.tsx
```

---

## 5. 共享组件

| 组件 | 用途 |
|---|---|
| `Card` | 所有内容卡片 |
| `PrimaryButton` | 主按钮 |
| `GhostButton` | 次按钮 |
| `DangerButton` | 危险按钮 |
| `Field` | 表单输入 |
| `StatusChip` | 状态徽标 |
| `Tag` | 标签 |
| `CategoryBadge` | 分类徽标 |
| `Modal` | 弹窗 |
| `Drawer` | 详情 / 长列表抽屉 |
| `PageHeader` | 页面标题区 |
| `Stat` | KPI 卡片 |
| `Pager` | 分页 |
| `EmptyState` | 空状态 |
| `Toast` | 成功 / 失败 / 加载提示 |

开发要求：

```text
能复用共享组件的地方，不允许重复造样式。
```

---

## 6. 全局 Shell

### 6.1 外壳结构

```text
左侧固定侧边栏
顶部用户区 / 操作区
主内容区
```

### 6.2 侧边栏

展开宽度：

```text
240px
```

收起宽度：

```text
64px
```

折叠状态需要持久化到 `localStorage`。

### 6.3 运营菜单

| 名称 | 路由 |
|---|---|
| 首页 | `/` |
| 内容工作台 | `/workspace` |
| 我的任务 | `/tasks` |
| 我的产出 | `/outputs` |

### 6.4 管理员菜单

| 分组 | 名称 | 路由 |
|---|---|---|
| 主功能 | 数据看板 | `/admin` |
| 主功能 | 用户管理 | `/admin/users` |
| 主功能 | 红人管理 | `/admin/kols` |
| 主功能 | 工具配置 | `/admin/workspace` |
| 主功能 | 任务记录 | `/admin/tasks` |
| 主功能 | 产出记录 | `/admin/outputs` |
| 系统运维 | 服务状态 | `/admin/system` |
| 系统运维 | 调用日志 | `/admin/logs` |
| 系统运维 | 操作日志 | `/admin/audit` |
| 系统运维 | 服务配置 | `/admin/config` |

---

## 7. 页面骨架定义

## 7.1 `/login` 登录页

### 页面目标

用户输入账号和密码登录系统。

### 页面元素

```text
1. Logo / 平台名：达人说AI运营平台
2. 账号输入框
3. 密码输入框
4. 登录按钮
5. 内部系统提示
6. 忘记密码请联系管理员
```

### 调用接口

```text
POST /api/auth/login
```

### 交互规则

| 场景 | 行为 |
|---|---|
| 登录成功且需要改密 | 跳转 `/change-password` |
| 登录成功且 `role=admin` | 跳转 `/admin` |
| 登录成功且 `role=operator` | 跳转 `/` |
| 密码错误 | Toast 提示 |
| 账号停用 | Toast 提示 |

---

## 7.2 `/change-password` 强制改密页

### 页面目标

新账号或重置密码后的账号必须修改密码。

### 页面元素

```text
1. 当前密码
2. 新密码
3. 确认新密码
4. 确认修改按钮
```

### 调用接口

```text
POST /api/auth/change-password
```

### 成功后行为

```text
清除 Token → 跳转 /login → 提示重新登录
```

---

## 7.3 `/` 运营首页

### 页面目标

运营人员进入系统后的工作入口。

### 页面模块

```text
1. 问候语
2. 我的 KPI 概览
3. 快速开始：内容工作台入口
4. 进行中任务 / 草稿，最多展示 5 条
5. 最近产出，最多展示 5 条
```

### 调用接口

```text
GET /api/auth/me
GET /api/tasks?page=1&page_size=5
GET /api/outputs?page=1&page_size=5
GET /api/workspace/tools
```

---

## 7.4 `/workspace` 内容工作台

### 页面目标

展示内容工具卡片，是旧 Ai_Toolbox 工具统一入口。

### 页面模块

```text
1. PageHeader：内容工作台
2. 工具卡片双列网格
3. 工具状态：已上线 / 开发中 / 已下线
4. 空状态
```

### 调用接口

```text
GET /api/workspace/tools
```

### 交互规则

| 工具状态 | 交互 |
|---|---|
| `online` | 可点击进入 |
| `dev` | 置灰，提示开发中 |
| `offline` | 置灰，提示已下线 |
| `disabled` | 不展示或置灰 |

---

## 7.5 `/workspace/persona-writer` 人设脚本仿写占位页

### 当前阶段定位

基层阶段只保留入口占位，不实现完整迁移逻辑。

### 页面内容

```text
1. PageHeader：人设脚本仿写
2. 工具说明
3. 当前状态：M1 下一阶段迁移
4. 返回内容工作台按钮
```

### 不做内容

```text
1. 不做真实 AI 生成
2. 不做 TikHub 解析
3. 不做 Word 导出
4. 不做 Prompt 迁移
```

---

## 7.6 `/tasks` 我的任务

### 页面目标

展示当前用户自己的任务。

### 页面模块

```text
1. 周期统计：本周 / 本月 / 全年
2. 筛选：状态 / 工具 / 关键词
3. 任务列表
4. 失败原因
5. 查看产出按钮
6. 分页
7. 空状态
```

### 调用接口

```text
GET /api/tasks
GET /api/tasks/{task_id}
```

### 权限

operator 只能看到自己的任务。

---

## 7.7 `/outputs` 我的产出

### 页面目标

展示当前用户自己的产出。

### 页面模块

```text
1. 搜索
2. 工具筛选
3. 产出列表
4. 预览抽屉
5. 下载按钮
6. 分页
7. 空状态
```

### 调用接口

```text
GET /api/outputs
GET /api/outputs/{output_id}
POST /api/files/{file_id}/download-url
```

---

## 7.8 `/admin` 数据看板

### 页面目标

管理员查看平台运行概览。

### 页面模块

```text
1. 在线用户数
2. 今日产出
3. 今日工具调用
4. 任务成功率
5. 近 7 日内容产出趋势
6. 今日任务概况
7. 外部服务调用概览
```

### 调用接口

基层阶段可先使用：

```text
GET /api/admin/tasks?page=1&page_size=5
GET /api/admin/outputs?page=1&page_size=5
GET /api/admin/logs/external?page=1&page_size=5
```

后续可补充 dashboard 聚合接口。

---

## 7.9 `/admin/users` 用户管理

### 页面目标

管理员管理账号。

### 页面模块

```text
1. 用户列表
2. 用户总数
3. 新建账号
4. 编辑用户
5. 重置密码
6. 启用 / 停用
7. 删除二次确认
8. 当前在线抽屉
9. 分页
```

### 调用接口

```text
GET    /api/admin/users
POST   /api/admin/users
GET    /api/admin/users/{user_id}
PATCH  /api/admin/users/{user_id}
POST   /api/admin/users/{user_id}/reset-password
POST   /api/admin/users/{user_id}/enable
POST   /api/admin/users/{user_id}/disable
DELETE /api/admin/users/{user_id}
```

---

## 7.10 `/admin/workspace` 工具配置

### 页面目标

管理员查看和配置内容工作台工具。

### 页面模块

```text
1. 工具列表
2. 工具状态
3. 工具说明
4. 上线 / 下线 / 开发中状态调整
5. 阈值配置入口
```

### 调用接口

```text
GET /api/workspace/tools
PATCH /api/admin/workspace/tools/{tool_code}
```

---

## 7.11 `/admin/tasks` 任务记录

### 页面目标

管理员查看全部任务。

### 页面模块

```text
1. 筛选：状态 / 工具 / 用户 / 关键词
2. 全量任务列表
3. 任务详情抽屉
4. task_logs 展示
5. 分页
```

### 调用接口

```text
GET /api/admin/tasks
GET /api/admin/tasks/{task_id}
```

---

## 7.12 `/admin/outputs` 产出记录

### 页面目标

管理员查看全部产出。

### 页面模块

```text
1. 筛选：工具 / 用户 / 关键词
2. 全量产出列表
3. 产出预览抽屉
4. 下载文件
5. 分页
```

### 调用接口

```text
GET /api/admin/outputs
GET /api/admin/outputs/{output_id}
POST /api/files/{file_id}/download-url
```

---

## 7.13 `/admin/system` 服务状态

### 页面目标

展示系统和外部服务健康状态。

### 页面模块

```text
1. 后端服务状态
2. 数据库状态
3. AI 服务状态
4. TikHub 状态
5. OSS 状态
6. ASR 状态预留
7. 24h 调用趋势
8. 配额消耗概览
```

### 调用接口

基层阶段可使用：

```text
GET /api/health
GET /api/admin/logs/external?page=1&page_size=20
```

---

## 7.14 `/admin/logs` 调用日志

### 页面目标

查看外部服务调用明细。

### 调用接口

```text
GET /api/admin/logs/external
```

---

## 7.15 `/admin/audit` 操作日志

### 页面目标

查看用户关键操作审计。

### 调用接口

```text
GET /api/admin/logs/operation
```

---

## 7.16 `/admin/config` 服务配置

### 页面目标

管理外部服务密钥池。

### 页面模块

```text
1. AI 密钥池
2. TikHub 密钥池
3. ASR 密钥池预留
4. OSS 配置提示
5. 新增密钥
6. 启用 / 停用密钥
7. 删除密钥二次确认
```

### 调用接口

```text
GET  /api/admin/config/credentials
POST /api/admin/config/credentials
POST /api/admin/config/credentials/{credential_id}/enable
POST /api/admin/config/credentials/{credential_id}/disable
```

### 安全要求

```text
密钥只显示后四位，不允许明文回显。
```

---

## 8. API 请求层要求

### 8.1 request 统一封装

必须封装统一请求层，处理：

```text
1. baseURL
2. Authorization Header
3. success/code/message/data 解包
4. 401 自动退出
5. AUTH_FORCE_CHANGE_PASSWORD 自动跳转
6. PERMISSION_DENIED 提示无权限
7. Toast 错误提示
```

### 8.2 禁止页面内直接 fetch

不允许在页面组件里散落：

```ts
fetch('/api/xxx')
axios.get('/api/xxx')
```

必须通过 `src/api/*` 调用。

---

## 9. Mock 数据规则

基层开发早期允许 Mock，但必须遵守：

1. Mock 字段与 API 文档一致。
2. Mock 数据集中管理。
3. 不允许页面里临时写多个版本 Mock。
4. 接入真实接口后必须删除无用 Mock。
5. Mock 状态枚举必须使用正式枚举。

---

## 10. 当前阶段不做

```text
1. persona-writer 完整迁移
2. AI 真实生成
3. TikHub 真实解析
4. Word 真实导出
5. 视频上传
6. 短视频模块
7. 直播模块
8. 内容规划模块
9. Redis 队列
10. 自动化部署
```

---

## 11. 前端基层验收

1. `/login` 可以访问。
2. 登录成功后根据角色跳转。
3. 新账号首次登录进入 `/change-password`。
4. operator 访问 `/admin/*` 被拦截。
5. admin 可以进入 `/admin`。
6. `/workspace` 可以展示工具卡片。
7. `online` 工具可点击，`dev` 工具置灰。
8. `/tasks` 可以分页展示当前用户任务。
9. `/outputs` 可以分页展示当前用户产出。
10. `/admin/users` 可以分页展示用户并创建账号。
11. `/admin/workspace` 可以查看工具配置。
12. `/admin/tasks` 可以查看全部任务。
13. `/admin/outputs` 可以查看全部产出。
14. `/admin/logs` 可以查看外部调用日志。
15. `/admin/audit` 可以查看操作日志。
16. `/admin/config` 不显示明文密钥。

