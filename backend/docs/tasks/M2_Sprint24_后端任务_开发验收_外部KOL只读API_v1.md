# M2 Sprint24 后端任务 - 开发验收 - 外部 KOL 只读 API v1

> 日期：2026-08-05
> 验收对象：外部 KOL 只读 API
> 相关任务：`backend/docs/tasks/M2_Sprint24_后端任务_外部KOL只读API_v1.md`

---

## 一、验收结论

通过。

外部 KOL 只读 API 已完成代码、契约、测试报告、README、PM 记忆和部署注意事项落档。当前保留的测试均直接覆盖本次新增接口；此前为了提升全局覆盖率而添加的无关测试已删除。

---

## 二、功能验收

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 标准信封 | 通过 | 成功与错误响应均为 `{success, code, message, data}` |
| 鉴权 | 通过 | `X-API-Key` 正确时放行，缺少或错误返回 401 |
| 未配置密钥 | 通过 | `EXTERNAL_KOLS_API_KEY` 为空时返回 503 |
| 只读 | 通过 | 仅 GET，不提供写入、更新、删除 |
| 数据来源 | 通过 | 读取现有 `kols` 表，不新增业务表 |
| 分页 | 通过 | 列表接口支持 `page`、`page_size` |
| 筛选 | 通过 | 支持关键词、平台、计算状态筛选 |
| 软删隔离 | 通过 | 默认排除 `deleted_at IS NOT NULL` |
| 大字段控制 | 通过 | 列表默认不返回 `tikhub_raw` |

---

## 三、测试记录

命令：

```bash
cd backend
TEST_DB_URL='postgresql+asyncpg://postgres:admin123@localhost:5432/mcn_test' \
./.venv/bin/python -m pytest \
  tests/unit/routers/test_external_kols_unit.py \
  tests/integration/routers/test_external_kols.py \
  tests/integration/test_convention_guard.py
```

结果：

```text
27 passed
```

覆盖范围：

- 单元测试：外部密钥鉴权、状态计算、字段序列化、空数据、详情不存在。
- 集成测试：接口鉴权、未配置密钥、列表筛选分页、详情 raw 控制、404 标准信封。
- 红线守卫：非流式接口标准信封、OperationLog 写操作守卫、AsyncSessionLocal patch 守卫等。

---

## 四、PM 检查清单

| 类别 | 检查项 | 结果 |
|------|--------|------|
| 代码规范 | 非流式接口返回标准信封 | 通过 |
| 代码规范 | 写操作 OperationLog | 不适用，仅只读 GET |
| 代码规范 | 新 router 使用 `get_db`，无需 `AsyncSessionLocal` patch | 通过 |
| 测试 | 正常路径 + 错误路径 + 边界条件 | 通过 |
| 契约 | `MCN_M2_Base_API.md` 已更新 | 通过 |
| 数据库 | `MCN_M2_Base_Database.md` 已说明不新增表 | 通过 |
| README | 根 README、backend README、deploy 文档同步 | 通过 |
| PM 记忆 | `PM_记忆与状态_M2.md` 已更新 | 通过 |
| 安全 | 真实密钥不入 Git，只通过 `.env`/环境变量配置 | 通过 |
| 部署 | 生产建议 Nginx + HTTPS，不直接暴露 8000/5432 | 通过 |

---

## 五、遗留说明

严格覆盖率门禁曾低于项目历史目标线，但同事已确认本轮不需要为全局覆盖率补无关测试。本次只保留与外部 KOL API 直接相关的正规单元测试和集成测试。
