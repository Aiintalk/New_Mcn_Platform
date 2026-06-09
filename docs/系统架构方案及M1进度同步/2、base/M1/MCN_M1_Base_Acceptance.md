# MCN Information System Platform · M1 Base 验收标准

> 文档定位：本文件只验收 M1 系统底座，不验收 persona-writer 的完整迁移、AI 真实生成、TikHub 真实解析和 Word 真实导出。

---

## 1. 验收范围

本阶段验收：

```text
1. 前端工程启动
2. 后端工程启动
3. PostgreSQL 连接
4. JWT 登录
5. 首次登录强制改密
6. admin / operator 权限
7. 用户管理
8. 内容工作台工具列表
9. 任务记录
10. 产出记录
11. 文件记录结构
12. 操作日志
13. 外部服务调用日志结构
14. 服务配置 / 密钥池结构
15. 测试服可部署基础能力
```

本阶段不验收：

```text
1. persona-writer 完整业务迁移
2. AI 真实生成质量
3. TikHub 真实视频解析
4. Word 真实导出样式
5. 视频上传与留档
6. 短视频模块
7. 直播模块
8. 内容规划模块
9. Redis 队列
10. 正式生产环境部署
```

---

## 2. 总体验收标准

| 编号 | 模块 | 验收项 | 通过标准 |
|---|---|---|---|
| B-001 | 工程 | 前端可启动 | 执行启动命令后能访问前端页面 |
| B-002 | 工程 | 后端可启动 | 后端服务无报错启动 |
| B-003 | 工程 | 健康检查 | `GET /api/health` 返回 `status=ok` |
| B-004 | 工程 | 数据库连接 | `/api/health` 中 `database=ok` |
| B-005 | 工程 | 前后端联通 | 前端能成功请求 `/api/health` |

---

## 3. 认证与权限验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| AUTH-001 | 访问登录页 | 无 | 打开 `/login` | 正常显示登录页 |
| AUTH-002 | 不提供注册入口 | 无 | 查看 `/login` | 页面无注册按钮、无申请账号入口 |
| AUTH-003 | 管理员登录成功 | 已有 admin 账号 | 输入正确账号密码 | 跳转 `/admin` |
| AUTH-004 | 运营登录成功 | 已有 operator 账号 | 输入正确账号密码 | 跳转 `/` |
| AUTH-005 | 密码错误 | 已有账号 | 输入错误密码 | 提示账号或密码错误 |
| AUTH-006 | 停用账号登录 | 用户 `status=disabled` | 输入正确密码 | 提示账号已停用 |
| AUTH-007 | 首次登录强制改密 | `password_changed_at=null` | 登录账号 | 跳转 `/change-password` |
| AUTH-008 | 改密成功 | 已进入改密页 | 输入旧密码、新密码、确认密码 | 提示成功，清除 Token，跳转 `/login` |
| AUTH-009 | 新密码不一致 | 已进入改密页 | 两次新密码不一致 | 提示确认密码不一致 |
| AUTH-010 | 未登录访问业务页 | 无 Token | 打开 `/workspace` | 跳转 `/login` |
| AUTH-011 | operator 访问后台 | operator 已登录 | 打开 `/admin/users` | 返回 403 或跳转 `/` |
| AUTH-012 | 过期 Token | Token 过期 | 请求任意受保护 API | 清除 Token，跳转 `/login` |

---

## 4. 用户管理验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| USER-001 | 查看用户列表 | admin 已登录 | 打开 `/admin/users` | 展示用户列表和分页 |
| USER-002 | 创建运营账号 | admin 已登录 | 新建 `operator` 用户 | 创建成功，返回随机初始密码 |
| USER-003 | 创建管理员账号 | admin 已登录 | 新建 `admin` 用户 | 创建成功，返回随机初始密码 |
| USER-004 | 用户名重复 | 已存在 username | 使用相同 username 创建 | 返回 `USERNAME_ALREADY_EXISTS` |
| USER-005 | 重置密码 | admin 已登录 | 点击重置密码 | 返回随机初始密码，用户下次登录需改密 |
| USER-006 | 停用账号 | admin 已登录 | 停用用户 | 用户状态变为 `disabled` |
| USER-007 | 启用账号 | 用户已停用 | 启用用户 | 用户状态变为 `enabled` |
| USER-008 | 删除账号 | admin 已登录 | 删除用户并确认 | 写入 `deleted_at`，列表不再展示 |
| USER-009 | operator 访问用户 API | operator 已登录 | 请求 `/api/admin/users` | 返回 `PERMISSION_DENIED` |
| USER-010 | 操作日志 | admin 操作用户 | 创建 / 重置 / 停用 | `operation_logs` 有记录 |

---

## 5. 内容工作台验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| WS-001 | 查看工具列表 | 登录用户 | 打开 `/workspace` | 显示工具卡片 |
| WS-002 | 人设脚本仿写上线 | 工具状态 `online` | 查看工具卡片 | 显示已上线，可进入 |
| WS-003 | 开发中工具置灰 | 工具状态 `dev` | 查看工具卡片 | 显示开发中，不可进入 |
| WS-004 | 工具详情 | 登录用户 | 请求 `/api/workspace/tools/persona-writer` | 返回工具详情 |
| WS-005 | 管理员查看工具配置 | admin 已登录 | 打开 `/admin/workspace` | 显示全部工具配置 |
| WS-006 | 管理员更新工具状态 | admin 已登录 | 修改工具状态 | 更新成功，写入操作日志 |
| WS-007 | operator 修改工具配置 | operator 已登录 | 请求工具配置接口 | 返回 `PERMISSION_DENIED` |

---

## 6. 任务记录验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| TASK-001 | 我的任务列表 | operator 已登录 | 打开 `/tasks` | 只显示当前用户任务 |
| TASK-002 | 任务分页 | 任务数 > 20 | 切换分页 | 分页正常 |
| TASK-003 | 任务筛选 | 存在多状态任务 | 按状态筛选 | 返回对应状态任务 |
| TASK-004 | 查看任务详情 | 当前用户有任务 | 打开任务详情 | 显示任务基础信息和 task_logs |
| TASK-005 | operator 查看他人任务 | 存在他人任务 | 请求他人 `task_id` | 返回 `PERMISSION_DENIED` 或 `TASK_NOT_FOUND` |
| TASK-006 | admin 查看全部任务 | admin 已登录 | 打开 `/admin/tasks` | 显示全部任务 |
| TASK-007 | 任务状态枚举 | 存在任务 | 查看返回数据 | 只能出现 pending/processing/success/failed/cancelled |

---

## 7. 产出记录验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| OUT-001 | 我的产出列表 | operator 已登录 | 打开 `/outputs` | 只显示当前用户产出 |
| OUT-002 | 产出分页 | 产出数 > 20 | 切换分页 | 分页正常 |
| OUT-003 | 产出搜索 | 存在目标标题 | 输入关键词 | 返回匹配产出 |
| OUT-004 | 产出详情 | 当前用户有产出 | 打开详情 / 抽屉 | 显示产出内容 |
| OUT-005 | operator 查看他人产出 | 存在他人产出 | 请求他人 `output_id` | 返回无权限或不存在 |
| OUT-006 | admin 查看全部产出 | admin 已登录 | 打开 `/admin/outputs` | 显示全部产出 |

---

## 8. 文件记录验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| FILE-001 | 文件详情 | 用户有文件 | 请求 `/api/files/{file_id}` | 返回文件信息，不返回本地路径 |
| FILE-002 | 获取下载地址 | 用户有文件 | 请求 download-url | 返回临时签名 URL |
| FILE-003 | 下载操作日志 | 用户请求下载 | 请求 download-url | `operation_logs` 写入 `download_file` |
| FILE-004 | operator 下载他人文件 | 存在他人文件 | 请求他人文件 | 返回无权限或不存在 |
| FILE-006 | 文件不落本地盘 | 有文件记录 | 检查 files 数据 | 只保存 OSS key，不保存应用本地文件路径 |

> **FILE-005 不在 M1 验收范围**：`GET /api/admin/files` 全量文件列表在 M1 阶段无实际意义——persona-writer 尚未上线，`files` 表不会有真实数据写入。待 persona-writer 完整迁移后（M1 后续 Sprint）再纳入验收。

---

## 9. 日志验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| LOG-001 | 登录日志 | 用户登录成功 | 查看 `operation_logs` | 有 `login` 记录 |
| LOG-002 | 用户管理日志 | admin 创建用户 | 查看 `operation_logs` | 有 `create_user` 记录 |
| LOG-003 | 工具配置日志 | admin 修改工具 | 查看 `operation_logs` | 有 `update_tool_config` 记录 |
| LOG-004 | 操作日志页面 | admin 已登录 | 打开 `/admin/audit` | 展示操作日志列表 |
| LOG-005 | operator 访问操作日志 | operator 已登录 | 请求操作日志 API | 返回 `PERMISSION_DENIED` |
| LOG-006 | 外部调用日志页面 | admin 已登录 | 打开 `/admin/logs` | 展示外部调用日志列表或空状态 |
| LOG-007 | 外部日志字段 | 存在调用日志 | 查看记录 | 包含 service/status/duration_ms/task_id 等字段 |

---

## 10. 服务配置验收

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|
| CFG-001 | 查看密钥池 | admin 已登录 | 打开 `/admin/config` | 显示密钥列表 |
| CFG-002 | 密钥不明文回显 | 存在密钥 | 查看页面和 API | 只显示 `secret_tail` |
| CFG-003 | 新增密钥 | admin 已登录 | 新增 AI 密钥 | 保存成功，写入加密密钥 |
| CFG-004 | 停用密钥 | 存在 enabled 密钥 | 点击停用 | 状态变为 disabled |
| CFG-005 | 启用密钥 | 存在 disabled 密钥 | 点击启用 | 状态变为 enabled |
| CFG-006 | operator 访问配置 | operator 已登录 | 请求配置 API | 返回 `PERMISSION_DENIED` |
| CFG-007 | 操作日志 | admin 管理密钥 | 新增 / 停用 / 启用 | `operation_logs` 有记录 |

---

## 11. 前端页面验收

| 编号 | 页面 | 验收项 | 通过标准 |
|---|---|---|---|
| FE-001 | `/login` | 登录页风格 | 符合品牌橙、白卡片、内部系统提示 |
| FE-002 | `/change-password` | 改密页 | 字段完整，成功后重新登录 |
| FE-003 | `/` | 运营首页 | 有工作台入口、最近任务、最近产出 |
| FE-004 | `/workspace` | 内容工作台 | 工具双列卡片，状态清晰 |
| FE-005 | `/workspace/persona-writer` | 占位页 | 只展示工具说明和下一阶段提示 |
| FE-006 | `/tasks` | 我的任务 | 分页、筛选、空状态正常 |
| FE-007 | `/outputs` | 我的产出 | 搜索、预览、分页、下载入口正常 |
| FE-008 | `/admin` | 数据看板 | KPI、趋势、任务概况、服务概览 |
| FE-009 | `/admin/users` | 用户管理 | 分页、新建、重置、停用、删除 |
| FE-010 | `/admin/workspace` | 工具配置 | 工具状态配置正常 |
| FE-011 | `/admin/tasks` | 任务记录 | 全量任务分页正常 |
| FE-012 | `/admin/outputs` | 产出记录 | 全量产出分页正常 |
| FE-013 | `/admin/system` | 服务状态 | 健康概览正常 |
| FE-014 | `/admin/logs` | 调用日志 | 外部调用明细分页正常 |
| FE-015 | `/admin/audit` | 操作日志 | 行为审计分页正常 |
| FE-016 | `/admin/config` | 服务配置 | 密钥池管理不显示明文 |

---

## 12. 部署基础验收

| 编号 | 场景 | 操作步骤 | 预期结果 |
|---|---|---|---|
| DEP-001 | 后端启动 | 启动 FastAPI | 无报错 |
| DEP-002 | 前端构建 | 执行前端 build | 构建成功 |
| DEP-003 | Nginx 访问 | 访问前端域名 | 正常打开页面 |
| DEP-004 | API 反代 | 请求 `/api/health` | 返回成功 |
| DEP-005 | 数据库迁移 | 执行建表脚本 | 表结构创建成功 |
| DEP-006 | 环境变量 | 检查 `.env` | DB/JWT/OSS/AI 等变量完整或预留 |
| DEP-007 | 日志轮转 | 检查日志配置 | 不会无限写满磁盘 |
| DEP-008 | 安全端口 | 检查端口 | PostgreSQL 不对公网暴露 |

---

## 13. 一票否决项

出现以下任一情况，本阶段不通过：

```text
1. 系统开放自主注册
2. operator 可以访问 /admin/*
3. operator 可以看到他人任务或产出
4. 密码或密钥明文入库
5. API 返回结构不统一
6. 关键 API 不校验 JWT
7. 前端直接调用 AI / TikHub / OSS Secret
8. 文件落应用服务器本地盘
9. 用户删除为物理删除
10. 日志表完全没有写入
11. 页面长列表无分页，导致页面无限拉长
12. 未确认 API 文档就随意新增接口
```

---

## 14. 验收结论模板

```text
项目：MCN Information System Platform
阶段：M1 Base 系统底座
验收日期：YYYY-MM-DD
验收人：

验收结果：通过 / 不通过 / 有条件通过

通过项：
1.
2.
3.

问题项：
1.
2.
3.

整改要求：
1.
2.
3.

是否允许进入 persona-writer 迁移阶段：是 / 否
```

