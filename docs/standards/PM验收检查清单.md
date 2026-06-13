# PM 验收检查清单（Sprint 级 + 子任务级）

> 每次签收前必须逐条过一遍。不过的项不能放行。
> 使用方式：复制本模板到验收文档中，逐条标注 ✅ / ❌。

---

## 一、子任务级检查（每次代码完成后）

### 1.1 代码规范

- [ ] 非流式接口返回 `success_response(data=...)`，不是裸 dict
- [ ] 用户写操作（POST/PUT/PATCH/DELETE）有 `OperationLog`
- [ ] 错误码使用 `ErrorCode` 枚举或 `detail={"code": "...", "message": "..."}`
- [ ] `updated_at` 手动设置（无 `onupdate`）
- [ ] 软删除查询带 `.where(deleted_at.is_(None))`

### 1.2 前端规范

- [ ] JSON 调用走 `request.ts`（`get/post/put/del`）
- [ ] 流式 / FormData / Blob 保留原生 fetch 但手动解包 `.data`
- [ ] 样式引用 CSS 变量，无硬编码
- [ ] 运营端入口在「创作中心」，管理端配置在「工具配置」

### 1.3 测试

- [ ] 新功能有对应测试（单元 or 集成）
- [ ] 测试覆盖正常路径 + 错误路径 + 边界条件
- [ ] `pytest tests/unit/ tests/integration/ -v` 全绿
- [ ] 新增 router 已注册到 `conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS`

---

## 二、Sprint 级检查（功能整体验收时）

### 2.1 契约文档

- [ ] `MCN_M2_Base_API.md` 已更新（新增/修改的接口有章节）
- [ ] `MCN_M2_Base_Database.md` 已更新（新增的表有定义 + 迁移已登记）
- [ ] API 响应格式示例为标准信封 `{success, code, message, data}`

### 2.2 任务文档

- [ ] 需求文档已在 `docs/pm/` 落地
- [ ] 各端任务文档已在 `{端}/docs/tasks/` 落地（v1 + 迭代 v2+）
- [ ] 各端验收文档已落地（含本检查清单或等价内容）

### 2.3 README

- [ ] 根目录 `README.md` 功能模块列表已更新
- [ ] `backend/docs/README.md` router/model/migration 清单已更新
- [ ] `frontend/docs/README.md` api/page/type 清单已更新
- [ ] 文件计数与实际一致

### 2.4 回归

- [ ] 全量测试通过（`pytest tests/unit/ tests/integration/ -v`）
- [ ] 旧功能没有被改坏
- [ ] `docs/pm/PM_记忆与状态*.md` 已更新

---

## 三、一票否决项（9 条，任一出现即不通过）

- [ ] 无自主注册（未登录用户不能创建账号）
- [ ] operator 不能越权访问 admin 接口
- [ ] 用户不能看到他人的隔离数据
- [ ] 密码/密钥不明文存储
- [ ] 响应结构为标准 `{success, code, message, data}`
- [ ] 无 JWT 不能拿到受保护数据
- [ ] 前端不直连 AI / TikHub / OSS（必须后端代理）
- [ ] 不做物理删除（用 `deleted_at` 软删除）
- [ ] 列表接口有分页（或量小可证明不需要）
