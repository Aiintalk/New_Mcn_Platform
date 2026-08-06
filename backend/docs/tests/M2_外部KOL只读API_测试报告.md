# M2 — 外部 KOL 只读 API 测试报告

> 测试日期：2026-08-05  
> 测试对象：`GET /api/external/kols`、`GET /api/external/kols/{id}`  
> 相关代码：`backend/app/routers/external_kols.py`  
> 数据来源：`kols` 表，只读，不新增业务表

---

## 一、结论

| 项目 | 结果 | 说明 |
|------|------|------|
| 外部 KOL API 单元测试 | 通过 | 14/14 通过 |
| 外部 KOL API 集成测试 | 通过 | 7/7 通过 |
| 后端开发红线守卫 | 通过 | 6/6 通过 |
| 外部 KOL API 定向验证 | 通过 | 27/27 通过 |
| 后端覆盖率门禁 `run_coverage.py --gate` | 不作为本轮验收项 | 同事已确认无需为全局覆盖率补无关测试 |

**验收口径**：本次只保留与外部 KOL API 直接相关的正规单元测试、集成测试和红线守卫；此前为了提升全局覆盖率而添加的无关测试已删除。

---

## 二、覆盖范围

新增测试文件：

- `backend/tests/unit/routers/test_external_kols_unit.py`
- `backend/tests/integration/routers/test_external_kols.py`

| 用例 | 覆盖点 |
|------|--------|
| `test_missing_key_returns_401` | 缺少 `X-API-Key` 返回 `401 EXTERNAL_API_KEY_INVALID` |
| `test_invalid_key_returns_401` | 错误密钥返回 `401 EXTERNAL_API_KEY_INVALID` |
| `test_unconfigured_key_returns_503` | 未配置 `EXTERNAL_KOLS_API_KEY` 返回 `503 EXTERNAL_API_KEY_NOT_CONFIGURED` |
| `test_list_filters_paginates_and_omits_raw_by_default` | 列表分页、关键词、平台、计算状态筛选、默认不返回 `tikhub_raw`、排除软删 |
| `test_detail_includes_raw_by_default` | 详情默认返回 `tikhub_raw` |
| `test_detail_can_omit_raw` | 详情可通过 `include_raw=false` 不返回原始 JSON |
| `test_detail_not_found_returns_standard_envelope` | 详情不存在返回标准信封 `404 RESOURCE_NOT_FOUND` |

单元测试补充覆盖：

- `require_external_kols_api_key` 正常、错误密钥、未配置密钥。
- `_compute_status` 四种计算状态。
- `_kol_to_dict` 默认隐藏 raw、按需返回 raw。
- 列表空数据分页边界。
- 详情不存在边界。

---

## 三、执行记录

### 1. 定向测试 + 红线守卫

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

说明：
- 外部 KOL API 单元测试：14 passed
- 外部 KOL API 集成测试：7 passed
- 后端红线守卫：6 passed
- 默认 `TEST_DB_URL` 使用 `mcn_user/admin123` 时本机测试库认证失败；本次按本机 PostgreSQL 可用账号 `postgres/admin123` 指向 `mcn_test` 后通过。

### 2. 覆盖率口径

同事已确认本轮不需要为了全局覆盖率基线补无关测试，因此不再把 `scripts/run_coverage.py --gate` 作为本次外部 KOL 只读 API 的合并前置项。

本轮保留的测试都直接覆盖新接口本身，避免为了拉高 `app/services/`、`app/routers/` 总体覆盖率而加入与本需求无关的测试。

---

## 四、验收说明

外部 KOL API 已满足本轮功能验收：

- 只读访问 `kols` 表，不暴露数据库端口或数据库账号。
- 使用 `X-API-Key` 鉴权，密钥来自 `EXTERNAL_KOLS_API_KEY`。
- 返回标准信封 `{success, code, message, data}`。
- 支持分页、关键词、平台、计算状态筛选和 `tikhub_raw` 可选返回。
- 契约文档已落地到 `backend/docs/base/MCN_M2_Base_API.md`。
- 数据库说明已落地到 `backend/docs/base/MCN_M2_Base_Database.md`。
- 后端任务和验收文档已落地到 `backend/docs/tasks/`。
- 运维部署注意事项已落地到 `deploy/docs/tasks/M2_Sprint24_运维端任务_外部KOL只读API部署配置_v1.md`。

**待跟进**：阿里云部署时由运维配置 `EXTERNAL_KOLS_API_KEY`、Nginx/HTTPS、安全组和调用方域名的 CORS 白名单。
