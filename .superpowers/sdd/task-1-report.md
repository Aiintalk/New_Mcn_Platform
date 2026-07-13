# Task 1 完成报告：统一红人上下文与唯一当前商品

## 状态

完成。仅提交本任务的代码、契约、迁移、测试和本报告；未处理既有未跟踪需求文档与计划文件。

## 改动

- 新增 `backend/app/services/kol_context.py`：统一读取红人姓名、`persona`、`content_plan` 与五分区档案；空字段不进入输入分段；红人不存在时返回明确 404。服务还提供按 ID 从数据库读取未软删除商品，以及读取当前商品的入口，供后续脚本工具复用。
- 将 `kol_active_products` 约束为每个 `kol_id` 只能关联一个当前商品；`PUT /active-products` 保留原路径和数组格式以兼容既有调用，但拒绝多个商品 ID，写入时仍整体替换。
- 新增迁移 `049_kol_active_products_single_current_product.sql`。迁移先检测历史重复关联；存在重复时中止而不自动删除数据，需人工确认后再处理。
- 删除仍被任一红人选为当前商品的产品时返回明确提示，避免软删除后遗留无效当前商品。
- 工作台首页改为单选“当前商品”，切换后只提交最新商品；当前商品卡显示所有非空产品业务字段。
- 更新 M2 API 和数据库事实源契约。

## RED 证据

- 后端：新增四项测试后，旧实现表现为：多商品接口仍返回 200、当前商品仍可删除、统一上下文服务不存在；共 `4 failed / 16 passed`。
- 前端：新增“选择产品乙后只提交乙”断言，旧实现提交 `[10, 11]` 而非 `[11]`，断言失败。

## GREEN 证据

- 后端：`source /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/.venv/bin/activate && pytest tests/integration/routers/test_operator_workspace.py -q`：`20 passed`（由控制会话在本机 PostgreSQL 测试库执行）。
- 前端：`npm test -- src/__tests__/components/pages/KolWorkspacePage.test.tsx`：`22 passed`。
- 差异检查：`git diff --check` 通过。

## 已知问题

- `npm run build` 未通过，但错误均位于本任务未修改的既有测试、API 和其他页面；本任务文件不再出现在构建错误中。前端定向测试仍通过。构建错误需在独立的全局 TypeScript 清理任务中处理。
- 前端定向测试保留既有 React Router、Ant Design 和 jsdom 警告；本任务未修改这些无关告警。
- 生产环境执行迁移前，如果历史上存在同一红人多个商品关联，迁移会安全中止，需要运营先确认保留哪个当前商品。

## 自审

- 检查了写操作：更新当前商品和删除产品成功路径均写入 OperationLog；被拦截的删除没有写入成功操作日志。
- 检查了接口兼容：保留 `GET/PUT /active-products` 与 `product_ids` 响应结构，独立页调用不会因路径或响应类型变化而失效。
- 检查了数据安全：没有自动清理历史关联；迁移检测到重复数据后中止。

## 本任务文件

- `backend/app/models/kol_active_product.py`
- `backend/app/services/kol_context.py`
- `backend/app/routers/operator_workspace.py`
- `backend/app/routers/operator_qianchuan_products.py`
- `backend/migrations/049_kol_active_products_single_current_product.sql`
- `backend/docs/base/MCN_M2_Base_API.md`
- `backend/docs/base/MCN_M2_Base_Database.md`
- `backend/tests/integration/routers/test_operator_workspace.py`
- `frontend/src/pages/operator/workspace/WorkspaceDashboard.tsx`
- `frontend/src/__tests__/components/pages/KolWorkspacePage.test.tsx`
