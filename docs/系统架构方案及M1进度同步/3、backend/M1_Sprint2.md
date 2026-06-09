# MCN_Backend_Agent — M1 Sprint 2 任务指令

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-05  
> 前置条件：Sprint 1 验收通过，联调通过，11 张表已建立  
> 完成后：回传 PM，等待 Sprint 3 指令

---

## 必读文档

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 最高优先级
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Permission_utf8_bom.md` ← 权限规则

---

## ⚠️ Sprint 1 遗留确认（先做）

联调期间发现 HTTPException 响应格式问题，已在 `app/main.py` 加全局处理器。
请先确认以下两点再继续：

1. `app/main.py` 中存在 `@app.exception_handler(HTTPException)` 处理器，将所有 HTTPException 包装为标准 `{success, code, message, data}` 格式
2. 重新启动服务后修复仍然生效（`curl -X GET http://localhost:8000/api/auth/me` 不带 token，响应为标准格式而非 `{"detail":...}`）

如未持久化，请先修复再执行本节点任务。

---

## 本次任务：工作台工具 API

### Step 1：运营端工具列表 API（`app/routers/workspace.py`）

实现以下接口，严格遵守 `MCN_M1_Base_API` 工作台相关章节：

**`GET /api/workspace/tools`**（需登录 + 已改密）
- 返回 `status = 'online'` 的工具列表（operator 和 admin 均可访问）
- 按 `sort_order ASC` 排序
- 返回字段：`id / tool_code / tool_name / category / description / status / tags / sort_order`
- 返回结构：`{success, code, message, data: {items: [...]}}`（工具列表无需分页）

**`GET /api/workspace/tools/{tool_code}`**（需登录 + 已改密）
- 返回单个工具详情
- `status != 'online'` 或不存在 → 返回 `RESOURCE_NOT_FOUND`

### Step 2：管理员工具配置 API（`app/routers/admin_workspace.py`）

实现以下接口，全部需要 `admin` 权限：

**`GET /api/admin/workspace/tools`**（admin + 已改密）
- 返回全部工具（不过滤 status）
- 支持 `status` 筛选参数
- 按 `sort_order ASC` 排序

**`PATCH /api/admin/workspace/tools/{tool_code}`**（admin + 已改密）
- 可更新字段：`tool_name / description / status / tags / config / sort_order`
- 写 `operation_logs`：`action=update_workspace_tool`
- 不存在 → `RESOURCE_NOT_FOUND`

### Step 3：注册路由

在 `app/main.py` 中注册：
```python
from app.routers import workspace, admin_workspace
app.include_router(workspace.router, prefix="/api")
app.include_router(admin_workspace.router, prefix="/api")
```

---

## 不做什么

- 不实现 tasks/outputs/files/logs/credentials API（Sprint 3）
- 不实现 AI/TikHub/OSS 真实调用
- 不实现 KOL 管理 API（Sprint 3 或后续）

---

## 验收标准

1. `GET /api/workspace/tools` 返回 `status=online` 的工具列表，`persona-writer` 工具可见
2. `GET /api/workspace/tools/{tool_code}` 查 `persona-writer` 返回详情
3. `GET /api/admin/workspace/tools` 返回全部 5 个工具（含 `dev` 状态）
4. `PATCH /api/admin/workspace/tools/benchmark` 修改 `description`，操作日志有记录
5. operator Token 调 `/api/admin/workspace/tools` → `PERMISSION_DENIED`
6. 未改密账号调工具接口 → `AUTH_FORCE_CHANGE_PASSWORD`

---

## 完成后输出格式

```
# 后端 Claude 执行结果 — M1 Sprint 2
## 1. 本次任务
## 2. 完成内容
## 3. 新增 API 清单（含路径、方法、权限）
## 4. 修改文件清单
## 5. 自测结果（curl 命令 + 实际响应）
## 6. HTTPException 处理器确认（贴出代码片段）
## 7. 未完成事项
## 8. 需要 PM 决策的问题
## 9. 建议下一步
```
