# MCN_Frontend_Agent — M1 Sprint 1 任务指令

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：`tasks/M1_Sprint0.md` 验收通过，路由占位已完成  
> 完成后：回传 PM，等待 Sprint 2 指令

---

## 必读文档（执行前请先阅读，路径相对于项目根目录）

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Frontend_utf8_bom.md` ← **最高优先级，页面骨架**
2. `../project_docs/mcn_workspace_ui.jsx` ← **前端设计文档（风格/颜色/字体/组件）**
3. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 接口契约
4. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Permission_utf8_bom.md` ← 权限规则

---

## Step 1：安装依赖

```bash
npm install zustand
```

---

## Step 2：类型定义（`src/types/`）

**`src/types/api.ts`：**
```typescript
export interface ApiResponse<T> {
  success: boolean
  code: string
  message: string
  data: T | null
}

export interface Pagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface PagedData<T> {
  items: T[]
  pagination: Pagination
}
```

**`src/types/user.ts`：**
```typescript
export interface UserInfo {
  id: number
  username: string
  real_name: string
  role: 'admin' | 'operator'
  status: 'enabled' | 'disabled'
  must_change_password: boolean
  last_login_at: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  must_change_password: boolean
  user: UserInfo
}
```

---

## Step 3：AuthStore（`src/store/authStore.ts`）

```typescript
interface AuthState {
  token: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  mustChangePassword: boolean
  setAuth: (token: string, user: UserInfo, mustChangePassword: boolean) => void
  clearAuth: () => void
  updateUser: (user: UserInfo) => void
}
```

- token 持久化到 localStorage（key: `mcn_token`）
- 刷新时从 localStorage 恢复 token，user 信息重新调 `/api/auth/me` 获取

---

## Step 4：完善 `src/api/request.ts` + 新增 `src/api/auth.ts`

**request.ts 确保处理：**
1. `baseURL = import.meta.env.VITE_API_BASE_URL`（默认 `http://localhost:8000`）
2. 自动带 `Authorization: Bearer <token>`（从 authStore 读取）
3. `success=false` → 抛出含 code+message 的错误对象
4. `AUTH_TOKEN_EXPIRED` 或 401 → `authStore.clearAuth()` + 跳转 `/login`
5. `AUTH_FORCE_CHANGE_PASSWORD` → 跳转 `/change-password`
6. `PERMISSION_DENIED` → `message.error('无权限访问')`

**`src/api/auth.ts`：**
```typescript
// POST /api/auth/login
export const login: (username: string, password: string) => Promise<LoginResponse>

// GET /api/auth/me
export const getMe: () => Promise<UserInfo>

// POST /api/auth/change-password
export const changePassword: (
  old_password: string,
  new_password: string,
  confirm_password: string
) => Promise<void>

// POST /api/auth/logout
export const logout: () => Promise<void>
```

---

## Step 5：ProtectedRoute + AdminRoute 真实实现

**`src/routes/ProtectedRoute.tsx`：**
- token 为空 → `<Navigate to="/login" replace />`
- `mustChangePassword=true` 且非 `/change-password` → `<Navigate to="/change-password" replace />`
- 组件挂载时调 `getMe()`，失败则 `clearAuth()` + 跳转 `/login`
- 通过 → `<Outlet />`

**`src/routes/AdminRoute.tsx`：**
- 继承 ProtectedRoute 校验
- `user.role !== 'admin'` → `<Navigate to="/403" replace />`

---

## Step 6：`/login` 登录页（`src/pages/LoginPage.tsx`）

对照 `mcn_workspace_ui.jsx` 中登录相关组件实现：

- 渐变橙色背景（login-bg 动效）
- 居中白色卡片（login-card 动效）
- Logo + 平台名：**达人说AI运营平台**
- 表单：账号输入框 + 密码输入框 + 登录按钮
- 页脚："内部系统 · 忘记密码请联系管理员"
- **无注册入口**

登录成功逻辑：
1. 调 `login(username, password)`
2. `authStore.setAuth(token, user, mustChangePassword)`
3. `mustChangePassword=true` → `navigate('/change-password')`
4. `role=admin` → `navigate('/admin')`
5. `role=operator` → `navigate('/')`

错误处理：
- `AUTH_INVALID_PASSWORD` → `message.error('账号或密码错误')`
- `AUTH_USER_DISABLED` → `message.error('账号已停用，请联系管理员')`
- 其他 → `message.error(error.message)`

---

## Step 7：`/change-password` 改密页（`src/pages/ChangePasswordPage.tsx`）

- 字段：当前密码 + 新密码 + 确认新密码
- 前端校验：新密码 ≥ 8 位，两次一致
- 调 `changePassword()`
- 成功 → `clearAuth()` → `navigate('/login')` → `message.success('密码已修改，请重新登录')`

---

## Step 8：AppShell（`src/layouts/AppShell.tsx`）

- 左侧固定侧边栏：展开 240px / 收起 64px
- 折叠状态持久化 localStorage（key: `mcn_sidebar_collapsed`）
- 顶部右侧：`user.real_name` + 角色标签 + 退出登录
- 退出：`logout()` → `clearAuth()` → `navigate('/login')`

侧边栏菜单按 role 区分：

**operator 菜单：**
- 首页 `/`
- 内容工作台 `/workspace`
- 我的任务 `/tasks`
- 我的产出 `/outputs`

**admin 菜单：**
- 数据看板 `/admin`
- 用户管理 `/admin/users`
- 红人管理 `/admin/kols`
- 工具配置 `/admin/workspace`
- 任务记录 `/admin/tasks`
- 产出记录 `/admin/outputs`
- 服务状态 `/admin/system`
- 调用日志 `/admin/logs`
- 操作日志 `/admin/audit`
- 服务配置 `/admin/config`

---

## Step 9：更新路由配置

- `/login` → `<LoginPage />`（无 Shell，无 ProtectedRoute）
- `/change-password` → `<ChangePasswordPage />`（无 Shell，无 ProtectedRoute）
- 其余路由包裹 `<ProtectedRoute>` + `<AppShell>`
- `/admin/*` 额外包裹 `<AdminRoute>`
- `/403`、`/404` → 对应提示页
- 其余页面保留 Sprint 0 占位 div（Sprint 2 替换）

---

## 不做什么

- 不实现运营首页/工作台/任务/产出的真实数据
- 不实现管理员各子页面的真实数据（保留占位 div）
- 不实现 persona-writer 业务逻辑

---

## 验收标准

1. `/login` 有橙色品牌风格，无注册入口
2. admin 登录后跳转 `/admin`
3. operator 登录后跳转 `/`
4. `password_changed_at=null` 账号登录跳转 `/change-password`
5. 改密成功后清除 Token，跳转 `/login`
6. 未登录访问 `/workspace` 跳转 `/login`
7. operator 访问 `/admin/users` 跳转 `/403`
8. Token 过期后接口自动清除 Token 并跳转 `/login`
9. AppShell 侧边栏折叠状态刷新后保持

---

## 完成后输出格式

```
# 前端 Claude 执行结果 — M1 Sprint 1
## 1. 本次任务
## 2. 完成内容
## 3. 修改文件清单
## 4. 路由清单（标注真实实现 vs 占位）
## 5. 接口联调情况（是否与后端联调通过）
## 6. 自测结果（登录→跳转→改密→重登录 完整流程）
## 7. 未完成事项
## 8. 需要 PM 决策的问题
## 9. 建议下一步
```

> ⚠️ 所有接口调用通过 `src/api/` 层，不允许在组件里散落 fetch/axios。  
> ⚠️ 颜色全部走 CSS 变量（`--accent: #f59a23`），不在 JSX 里硬编码。  
> ⚠️ 如需新增 API 文档未定义的接口，先停下回传 PM。
