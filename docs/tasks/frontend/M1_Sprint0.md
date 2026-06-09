# MCN_Frontend_Agent — M1 Sprint 0 任务指令

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：无（本节点为第一个节点）  
> 完成后：验收通过，再执行 `tasks/M1_Sprint1.md`

---

## 必读文档（执行前请先阅读，路径相对于项目根目录）

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Frontend_utf8_bom.md` ← **最高优先级，页面骨架**
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 接口契约

---

## 硬性约束（违反即返工）

| 约束 | 说明 |
|---|---|
| 主题色 `#f59a23` | 所有橙色使用 CSS 变量 `--accent`，不硬编码 |
| 接口字段 `snake_case` | API 层不得用 `camelCase` 字段名 |
| 不允许散落 fetch | 所有接口调用通过 `src/api/` 层 |
| 不允许新增未确认页面 | 额外页面先回传 PM |
| operator 不能访问 `/admin/*` | 路由守卫必须实现 |

---

## 本次任务：前端项目初始化

### 要做什么

1. 在 `frontend/` 初始化 Vite + React + TypeScript 项目（react-ts 模板）

2. 安装 Ant Design 5.x：`npm install antd`

3. 按 `MCN_M1_Base_Frontend` 第 4 节配置目录结构：
   ```
   src/
   ├── api/          # 接口层
   ├── components/   # 共享组件
   ├── layouts/      # 布局组件
   ├── routes/       # 路由守卫
   ├── pages/        # 页面
   ├── store/        # 状态管理
   └── types/        # TypeScript 类型
   ```

4. 配置全局 CSS 变量（参考 `../project_docs/mcn_workspace_ui.jsx` 中 BaseStyles）：
   ```css
   :root {
     --accent: #f59a23;
     --paper:  #f6f4ef;
     --card:   #ffffff;
     --ink:    #221c16;
     --body:   #f6f4ef;
   }
   ```

5. 实现 `src/api/request.ts`（统一请求层）：
   - `baseURL` 读 `VITE_API_BASE_URL` 环境变量
   - 自动带 `Authorization: Bearer <token>`
   - 解包 `success/code/message/data`
   - 401 / `AUTH_TOKEN_EXPIRED` → 清除 Token，跳 `/login`
   - `AUTH_FORCE_CHANGE_PASSWORD` → 跳 `/change-password`
   - `PERMISSION_DENIED` → Toast 提示"无权限访问"

6. 配置 React Router v6，注册路由占位（每个路由只渲染含路由名称的 `<div>`）：
   ```
   公共路由：  /login、/change-password
   运营端：    /、/workspace、/workspace/persona-writer、/tasks、/outputs
   管理员端：  /admin、/admin/users、/admin/kols、/admin/workspace、
              /admin/tasks、/admin/outputs、/admin/system、
              /admin/logs、/admin/audit、/admin/config
   兜底：      /403、/404
   ```

7. 实现 `ProtectedRoute`（骨架）：
   - token 为空 → 跳 `/login`
   - `mustChangePassword=true` 且非 `/change-password` → 跳 `/change-password`

8. 实现 `AdminRoute`（骨架）：
   - 非 admin role → 返回 403 页面

9. `.env.example`：
   ```
   VITE_API_BASE_URL=http://localhost:8000
   ```

10. 确认 `npm run dev` 无报错启动

### 不做什么

- 不实现登录逻辑（不调用 `/api/auth/login`）
- 不实现任何页面真实内容（只要占位 div）
- 不实现侧边栏或顶部导航
- 不接入任何真实 API

---

## 验收标准

1. `npm run dev` 无报错启动
2. 浏览器访问 `/login` 有占位内容
3. 未登录访问 `/admin/users` 自动跳转 `/login`
4. 文件结构符合 `MCN_M1_Base_Frontend` 第 4 节

---

## 完成后输出格式

```
# 前端 Claude 执行结果 — M1 Sprint 0
## 1. 本次任务
## 2. 完成内容
## 3. 修改文件清单
## 4. 路由清单（所有已注册路由）
## 5. 接口联调情况（本次无）
## 6. 自测结果（npm run dev 启动，/login 可访问）
## 7. 未完成事项
## 8. 需要 PM 决策的问题
## 9. 建议下一步
```

> ⚠️ 如发现需要新增文档未定义的路由或组件，先回传 PM，不要擅自新增。
