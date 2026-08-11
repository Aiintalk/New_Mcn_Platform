# 工程测试覆盖率提升 Round 2（门禁达标）— PR 变更说明

> 给：项目负责人 + 仓库管理员（郜郜）。
> 范围：`feature/test-coverage-round2` vs `main`（main 含已合 #41）。**21 文件，+5580 / -0**。
> 一句话：补 **service 层 unit test + 路由 direct-call 测试**，把覆盖率门禁从 2 个 FAIL 拉到 **6 目录全绿**——**纯测试新增，零生产代码改动**。

郜郜重点关注：**§1 改了哪些已有文件（答：0 个）**、**§3 门禁达标**。

---

## §1. 改了哪些「已有文件」

**0 个。** 不动 `app/`、契约、表、conftest、依赖、CI、配置。diff 全部是 `backend/tests/` 下 21 个**新测试文件**。

---

## §2. 新增文件（21 个，~255 测试）

### service 层 unit test（3 个，services/ 73%→84%）
| 文件 | 覆盖提升 |
|---|---|
| `tests/unit/services/test_kol_tikhub.py` | kol_tikhub 14%→97% |
| `tests/unit/services/test_benchmark_report.py` | benchmark_report 14%→100% |
| `tests/unit/services/test_kol_scheduler.py` | kol_scheduler 37%→80% |

### 路由 direct-call 测试（18 个，routers/ 66%→73%）
直接 `await` 端点函数（绕过 httpx.ASGITransport 的 coverage 追踪不稳定）：
`test_intake_public_report`（30→74）、`test_operator_intake_direct_report`（41→93）、`test_admin_ai_coverage`（48→100）、`test_admin_benchmark_direct`、`test_operator_benchmark_direct`，以及 13 个 admin/operator 路由 direct-call（outputs/tasks/admin_kol_workspace/admin_users/admin_intake 等）。

---

## §3. 覆盖率门禁达标（核心）

**before（#41 合并后）→ after（本 PR）**，`python scripts/run_coverage.py`：

| 模块 | before | after | 目标 | |
|---|---|---|---|---|
| app/core/ | 100% | 100% | 90% | ✓ |
| app/models/ | 100% | 100% | 90% | ✓ |
| **app/services/** | **73%** | **83.8%** | 80% | ✓（原 FAIL） |
| **app/routers/** | **66%** | **73.0%** | 70% | ✓（原 FAIL） |
| app/adapters/ | 81% | 81.6% | 60% | ✓ |
| app/middlewares/ | 100% | 100% | 90% | ✓ |
| 整体 | 74% | 79.0% | 48% | ✓ |

**6 目录全绿 → 覆盖率门禁（`run_coverage.py --gate`）已可启用。** 启用动作为 Round 4：删 `.github/workflows/test.yml` 里 coverage gate 步骤的 `continue-on-error: true`。

---

## §4. 测试与质量

- 全量 `tests/unit + tests/integration` = **1954 passed, 1 skipped, 0 failed**，零回归
- 测试方法：service 层纯函数单测（mock 外部 adapter）；路由 direct-call（绕过 ASGITransport 的 coverage 追踪波动，稳定记录端点体）
- **清理 fixture 用 prefix-scoped**（`WHERE name LIKE 'cov_%'`），不删全表——避免破坏其他测试依赖的遗留数据（教训：`delete(table)` 会级联失败）

---

## §5. 风险与回滚

- **零生产代码改动** → 零风险、零回滚。revert 即可，对运行系统无影响
- **部署**：无（无迁移、无依赖、无 env、无进程）

---

## §6. 已知遗留（不阻塞本 PR）
- `tool_extract_frames` 测试跑 ffmpeg 时会留一个垃圾文件 `backend/scale='min(720,iw)':-2`（13 字节，`-vf scale` 滤镜参数被误当输出文件名）——测试隔离小隐患，待单独修
- 5 个路由仍 <70%（persona/subtitle/values_writer 等大模块），但 **routers/ 目录已达标**，不影响门禁；要拉到更高总覆盖率为后续 round
