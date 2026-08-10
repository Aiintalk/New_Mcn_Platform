# 工程测试覆盖率提升（Round 1）— PR 变更说明

> 给：项目负责人 + 仓库管理员（郜郜）。
> 范围：`feature/test-coverage-improvement` vs `main`（main = `3115ff1`）。**9 文件，+3356 / -0**。
> 一句话：为 9 个低覆盖路由补齐**集成测试**——**纯测试新增，零生产代码 / 零契约 / 零配置改动**。

郜郜重点关注：**§1 改了哪些已有文件（答：0 个）**、**§5 风险与回滚**。

---

## §1. 改了哪些「已有文件」

**0 个。**

- 不动任何生产代码（`app/` 下零改动）
- 不动任何接口契约 / 数据表 / 权限文档
- 不动 `conftest.py`（9 个路由早已在 `AsyncSessionLocal` patch 列表里）
- 不动 `requirements.txt` / `package.json` / 任何依赖
- 不动 CI / 配置

diff 全部是 **`backend/tests/integration/routers/` 下的 9 个新测试文件**。

---

## §2. 新增文件（9 个测试文件，179 个测试）

| 文件 | 行数 | 测试数 | 覆盖路由 / 端点 |
|---|---|---|---|
| `test_health.py` | 41 | 3 | health（2 端点，公开） |
| `test_admin_system.py` | 66 | 5 | admin_system（ai/tikhub 连通测试） |
| `test_admin_logs.py` | 92 | 8 | admin_logs（operation/external 日志分页+筛选） |
| `test_admin_benchmark.py` | 139 | 10 | admin_benchmark（configs/analyses CRUD + regenerate） |
| `test_files.py` | 168 | 10 | files（list/upload/download/delete + OSS mock） |
| `test_admin_ai.py` | 581 | 33 | admin_ai（keys/models CRUD ×11 端点 + stats） |
| `test_operator_benchmark.py` | 671 | 29 | operator_benchmark（fetch/analyze-SSE/history/export-word） |
| `test_intake_public.py` | 734 | 37 | intake_public（7 公开端点） |
| `test_operator_intake_direct.py` | 864 | 44 | operator_intake_direct（7 端点 + 用户隔离） |
| **合计** | **3356** | **179** | **9 路由 / 45 端点全覆盖** |

每个端点均有 happy path + error path（404/400/403/409/422/410）+ 鉴权（401/403）覆盖，无"仅 error-path"端点。

---

## §3. 覆盖率提升数据（before → after）

数据来源：`pytest tests/integration/routers/` 全量跑，coverage.py 行覆盖。before = main `3115ff1`，after = 本分支。

| 路由 | before | after | Δ | 达标 ≥70% |
|---|---|---|---|---|
| `admin_system.py` | 76% | **100%** | +24 | ✓ |
| `health.py` | 55% | **90%** | +35 | ✓ |
| `admin_logs.py` | 38% | **88%** | +50 | ✓ |
| `files.py` | 28% | **83%** | +55 | ✓ |
| `admin_benchmark.py` | 52% | **69%** | +17 | ✗（差 1%） |
| `operator_benchmark.py` | 30% | **63%** | +33 | ✗ |
| `admin_ai.py` | 28% | **48%** | +20 | ✗ |
| `operator_intake_direct.py` | 31% | **41%** | +10 | ✗ |
| `intake_public.py` | 22% | **28%** | +6 | ✗ |
| routers 模块总 | 61% | 63% | +2 | — |

- **4 / 9 达到 ≥70% 目标**
- 5 个未达标路由的 gap 在 **service 层报告生成后台任务 + SQL 聚合分支**（集成测试 mock 掉了，碰不到函数体），需 Round 2 service 层 unit test，单独 PR
- routers 总覆盖 +2% 有限：9 路由仅占 67 个路由文件的一小部分，模块内仍有 persona(23%) 等大块低覆盖路由不在本轮范围

详见 `docs/evaluation/测试报告-工程覆盖率提升.md`。

---

## §4. 测试与质量

- `tests/integration/routers/` 全量 = **1049 passed**（main 基线 870 → +179），exit 0，**零回归**
- 测试方法：`httpx` + `ASGITransport` 走真实路由 + 真实 auth 中间件 + 真实测试库；外部 adapter（yunwu/tikhub/oss/httpx）全 mock；后台报告任务 mock
- 隔离：`test_session` 全局 patch `AsyncSessionLocal`，不碰生产库；module 内 autouse 清理 fixture 解决 unique 约束 + 数据污染

---

## §5. 风险与回滚

- **零生产代码改动** → **零风险、零回滚成本**
- 回滚方式：不合并 / revert 该 PR，对运行系统无任何影响（无表迁移、无依赖变更、无配置变更、无进程变更）
- CI：纯测试新增，`pytest` 通过即绿

---

## §6. 部署

**无需任何部署动作。** 不涉及：DB 迁移、依赖安装、env 变量、新进程、Redis。合并即可。
