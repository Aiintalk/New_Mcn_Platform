# MCN Platform · M1 测试任务单

> 给测试 Claude 的执行任务单。逐章按顺序测试，每条记录 ✅ 通过 / ❌ 失败 + 失败原因。

---

## 环境启动

### 后端

```bash
cd mcn-platform/backend
pip install -r requirements.txt
cp .env.example .env        # 已有 .env 则跳过
uvicorn app.main:app --reload --port 8000
```

确认启动成功：`GET http://localhost:8000/api/health` 返回 `status: ok`。

### 前端

```bash
cd mcn-platform/frontend
npm install
npm run dev
```

确认启动成功：浏览器打开 `http://localhost:5173`，跳转到 `/login`。

### 测试账号

初始 admin 账号由 seed 自动创建：

| 账号 | 密码 | 角色 |
|------|------|------|
| `admin` | `Admin@123456` | admin |

operator 账号在测试 USER 章节时由 admin 创建。

---

## 第一章：工程基础

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| B-001 | 访问 `http://localhost:5173` | 跳转到 `/login`，页面正常渲染 | |
| B-002 | 后端启动日志 | 无报错，Uvicorn 监听 8000 | |
| B-003 | `GET /api/health` | `{ "status": "ok" }` | |
| B-004 | `/api/health` 响应 | 包含 `database: "ok"` | |
| B-005 | 前端请求 health | 打开 `/login` 后 F12 Network，确认前端可联通后端 | |

---

## 第二章：认证与权限

**前置：admin 首次登录，密码已改过（seed 默认已改密）。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| AUTH-001 | 访问 `/login` | 显示登录页，无注册按钮 | |
| AUTH-002 | 登录页检查 | 页面无「注册」「申请账号」入口 | |
| AUTH-003 | admin 正确账号密码登录 | 跳转 `/admin` | |
| AUTH-004 | 用正确 operator 账号登录（先在 USER 章节创建） | 跳转 `/`（运营首页） | |
| AUTH-005 | 密码填错登录 | 提示「账号或密码错误」 | |
| AUTH-006 | 停用账号登录（先在 USER 章节停用） | 提示「账号已停用」 | |
| AUTH-007 | 新建一个 operator，不改密直接登录 | 跳转 `/change-password` | |
| AUTH-008 | 改密页填旧密码 + 新密码 + 确认密码，提交 | 提示成功，清 Token，跳转 `/login` | |
| AUTH-009 | 改密页两次新密码不一致，提交 | 提示「确认密码不一致」 | |
| AUTH-010 | 未登录直接访问 `/workspace` | 跳转 `/login` | |
| AUTH-011 | operator 登录后访问 `/admin/users` | 返回 403 或跳转 `/` | |
| AUTH-012 | 手动清空 localStorage Token，刷新页面 | 跳转 `/login` | |

---

## 第三章：用户管理

**前置：admin 已登录。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| USER-001 | 打开 `/admin/users` | 显示用户列表和分页 | |
| USER-002 | 新建一个 `operator` 账号（记录账号名备用） | 创建成功，页面返回初始密码 | |
| USER-003 | 新建一个 `admin` 账号 | 创建成功，返回初始密码 | |
| USER-004 | 使用已存在的 username 再次创建 | 提示用户名已存在 | |
| USER-005 | 对某个用户点「重置密码」 | 返回新的初始密码，提示该用户下次需改密 | |
| USER-006 | 停用一个 operator 账号 | 状态变为 disabled | |
| USER-007 | 启用刚停用的账号 | 状态变为 enabled | |
| USER-008 | 删除一个账号并确认 | 列表中消失（软删，数据库 deleted_at 有值） | |
| USER-009 | operator 登录后请求 `GET /api/admin/users` | 返回 403 / PERMISSION_DENIED | |
| USER-010 | 上述操作后查看操作日志 `/admin/audit` | 有 `create_user` / `reset_password` / `disable_user` 等记录 | |

---

## 第四章：内容工作台

**前置：operator 或 admin 已登录。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| WS-001 | operator 打开 `/workspace` | 显示工具卡片列表 | |
| WS-002 | 查看「人设脚本仿写」卡片 | 显示状态标签，可点击进入（进入后是占位页） | |
| WS-003 | 查看「对标分析助手」等 dev 状态工具 | 卡片置灰或标注「开发中」，不可进入 | |
| WS-004 | `GET /api/workspace/tools/persona-writer` | 返回工具详情 | |
| WS-005 | admin 打开 `/admin/workspace` | 显示全部工具配置 | |
| WS-006 | admin 修改某工具状态（如改为 offline） | 更新成功，操作日志有 `update_tool_config` | |
| WS-007 | operator 请求 `PATCH /api/admin/workspace/tools/{id}` | 返回 403 / PERMISSION_DENIED | |

---

## 第五章：任务记录

**前置：operator 已登录，系统中存在至少一条任务（可手动通过 API 写入，或使用 seed 数据）。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| TASK-001 | operator 打开 `/tasks` | 只显示当前用户创建的任务 | |
| TASK-002 | 任务数 > 20 时切换分页 | 分页正常，数据不重复 | |
| TASK-003 | 按状态筛选任务 | 只返回对应状态的任务 | |
| TASK-004 | 打开某任务详情 | 显示任务基础信息和执行日志 | |
| TASK-005 | operator A 请求 operator B 的 task_id | 返回 403 或 TASK_NOT_FOUND | |
| TASK-006 | admin 打开 `/admin/tasks` | 显示全部用户的任务 | |
| TASK-007 | 查看任务返回数据的 status 字段 | 只出现 pending/processing/success/failed/cancelled | |

---

## 第六章：产出记录

**前置：operator 已登录，系统中存在至少一条产出。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| OUT-001 | operator 打开 `/outputs` | 只显示当前用户的产出 | |
| OUT-002 | 产出数 > 20 时切换分页 | 分页正常 | |
| OUT-003 | 输入关键词搜索产出 | 返回标题匹配的产出 | |
| OUT-004 | 打开产出详情/抽屉 | 显示产出正文内容 | |
| OUT-005 | operator A 请求 operator B 的 output_id | 返回无权限或不存在 | |
| OUT-006 | admin 打开 `/admin/outputs` | 显示全部用户的产出 | |

---

## 第七章：文件记录

**前置：系统中存在至少一条文件记录（可手动插入测试数据）。**

> FILE-005（admin 全量文件列表）不在本次验收范围，跳过。

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| FILE-001 | `GET /api/files/{file_id}` | 返回文件信息，无本地路径字段 | |
| FILE-002 | `GET /api/files/{file_id}/download-url` | 返回含 `download_url` 的对象 | |
| FILE-003 | 请求 download-url 后查操作日志 | `operation_logs` 有 `download_file` 记录 | |
| FILE-004 | operator A 请求 operator B 的文件 | 返回无权限或不存在 | |
| FILE-006 | 查看 files 表或接口返回字段 | 有 `oss_key` 字段，无应用本地文件路径 | |

---

## 第八章：日志

**前置：admin 已登录，前面各章节操作已产生日志。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| LOG-001 | 查看 `operation_logs` 或 `/admin/audit` | 有 `login` 记录 | |
| LOG-002 | 查看用户管理操作 | 有 `create_user` 记录 | |
| LOG-003 | 查看工具配置操作 | 有 `update_tool_config` 记录 | |
| LOG-004 | admin 打开 `/admin/audit` | 显示操作日志列表，支持分页 | |
| LOG-005 | operator 请求 `GET /api/admin/logs/operations` | 返回 403 / PERMISSION_DENIED | |
| LOG-006 | admin 打开 `/admin/logs` | 显示外部调用日志列表或空状态 | |
| LOG-007 | 查看外部调用日志字段 | 包含 service / status / duration_ms / task_id 字段 | |

---

## 第九章：服务配置（密钥池）

**前置：admin 已登录。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| CFG-001 | 打开 `/admin/config` | 显示密钥列表 | |
| CFG-002 | 查看密钥展示 | 只显示后四位（`secret_tail`），无明文 | |
| CFG-003 | 新增一条 AI 密钥 | 保存成功 | |
| CFG-004 | 停用该密钥 | 状态变为 disabled | |
| CFG-005 | 启用该密钥 | 状态变为 enabled | |
| CFG-006 | operator 请求密钥 API | 返回 403 / PERMISSION_DENIED | |
| CFG-007 | 上述操作后查看操作日志 | 有 `create_credential` / `disable_credential` / `enable_credential` 记录 | |

---

## 第十章：前端页面完整性

快速过一遍路由，确认每个页面能正常打开、无白屏、无 JS 报错（F12 Console 无红色错误）。

| 编号 | 路由 | 角色 | 预期 | 结果 |
|------|------|------|------|------|
| FE-001 | `/login` | 无 | 登录页，品牌橙色风格 | |
| FE-002 | `/change-password` | 已登录 | 改密表单完整 | |
| FE-003 | `/` | operator | 运营首页，有统计卡片 | |
| FE-004 | `/workspace` | operator | 工具卡片双列 | |
| FE-005 | `/workspace/persona-writer` | operator | 占位页「正在开发中」 | |
| FE-006 | `/tasks` | operator | 任务列表，分页、筛选 | |
| FE-007 | `/outputs` | operator | 产出列表，搜索、分页 | |
| FE-008 | `/admin` | admin | 数据看板，4 个统计卡片 | |
| FE-009 | `/admin/users` | admin | 用户管理，新建/重置/停用/删除 | |
| FE-010 | `/admin/workspace` | admin | 工具配置列表 | |
| FE-011 | `/admin/tasks` | admin | 全量任务列表 | |
| FE-012 | `/admin/outputs` | admin | 全量产出列表 | |
| FE-013 | `/admin/system` | admin | 服务状态页 | |
| FE-014 | `/admin/logs` | admin | 外部调用日志 | |
| FE-015 | `/admin/audit` | admin | 操作日志列表 | |
| FE-016 | `/admin/config` | admin | 密钥池管理，无明文密钥 | |

---

## 一票否决项（任一出现则整体不通过）

测试过程中如遇到以下情况，**立即停止并标记整体不通过**：

```
1. 系统有自主注册入口
2. operator 能成功访问 /admin/* 页面或接口
3. operator 能看到其他用户的任务或产出
4. 密码或密钥在数据库或接口中明文出现
5. API 响应结构不是 { success, code, message, data }
6. 无 JWT 也能请求到受保护接口数据
7. 前端直接调用 AI / TikHub / OSS（F12 Network 中出现直连外部服务的请求）
8. 删除用户/产出/任务为物理删除（数据库记录直接消失）
9. 列表页无分页，数据量大时页面无限拉长
```

---

## 测试结果汇总模板

测试完成后填写：

```
项目：MCN Information System Platform
阶段：M1 Base 系统底座
测试日期：
测试人：

总计：__ 项
通过：__ 项
失败：__ 项
跳过：1 项（FILE-005，有意推迟）

一票否决项：无 / 有（描述）

失败项清单：
- 编号：xxx，失败原因：

结论：通过 / 不通过 / 有条件通过
```
