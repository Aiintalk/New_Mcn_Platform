# 工程测试覆盖率提升 Round 2 + 门禁启用 — PR 变更说明

> 给：项目负责人 + 仓库管理员（郜郜）。
> 范围：`feature/test-coverage-round2` vs `main`。**25 文件，+~5600 / −12**。
> 一句话：补 **service 层 unit test + 路由 direct-call 测试** 把覆盖率门禁拉到 **6 目录全绿**，并**正式启用 CI 覆盖率门禁**（删 `continue-on-error`）+ 把门禁规范写入 `CLAUDE.md`/`AGENTS.md`。

郜郜重点关注：**§1 改了哪些已有文件（3 个非业务文件）**、**§4 门禁启用（CI 配置变更）**。

---

## §1. 改了哪些「已有文件」（3 个非业务文件，**0 业务代码**）

| 文件 | 改了什么 | 风险 |
|---|---|---|
| `.github/workflows/test.yml` | Coverage gate 步骤**删 `continue-on-error: true`**（warn-only → 严格门禁：不达标即 CI 失败）；注释更新为目标线 + 现状 | ⚠️ 见 §4：本 PR 后 CI 会**强制**卡覆盖率，本 PR 自带的测试已让各模块达标（有余量），合并即生效 |
| `CLAUDE.md` | 新增「八、覆盖率门禁」章节（目标表 + 5 条规矩：必须维持覆盖率/direct-call/prefix-scoped 清理等） | 低（纯文档，AI 指令） |
| `AGENTS.md` | 同 CLAUDE.md（Codex 镜像） | 低 |

> **0 业务代码改动**：不动 `app/`、契约、表、conftest、依赖。其余 22 个文件全是 `backend/tests/` 下**新测试文件**。

---

## §2. 新增测试文件（22 个，~255 测试）

### service 层 unit test（3 个，`services/` 73%→84%）
`test_kol_tikhub`(14→97%)、`test_benchmark_report`(14→100%)、`test_kol_scheduler`(37→80%)

### 路由 direct-call 测试（18 个，`routers/` 66%→73%）
直接 `await` 端点函数（绕过 httpx.ASGITransport 的 coverage 追踪不稳定）：
`test_intake_public_report`(30→74)、`test_operator_intake_direct_report`(41→93)、`test_admin_ai_coverage`(48→100)、`test_admin_benchmark_direct`、`test_operator_benchmark_direct`，+ 13 个 admin/operator 路由 direct-call（outputs/tasks/admin_kol_workspace/admin_users/admin_intake 等）。

---

## §3. 覆盖率门禁达标（核心数据）

**before（#41 合并后）→ after（本 PR）**，`cd backend && python scripts/run_coverage.py`：

| 模块 | 目标 | before | after | |
|---|---|---|---|---|
| `app/core/` | ≥90% | 100% | 100% | ✓ |
| `app/models/` | ≥90% | 100% | 100% | ✓ |
| `app/services/` | ≥80% | 73% | **83.8%** | ✓（原 FAIL） |
| `app/routers/` | ≥70% | 66% | **73.0%** | ✓（原 FAIL） |
| `app/adapters/` | ≥60% | 81% | 81.6% | ✓ |
| `app/middlewares/` | ≥90% | 100% | 100% | ✓ |
| 整体 | ≥48% | 74% | 79.0% | ✓ |

**6 目录全绿。** 各模块均有 3-4% 余量，吸收单进程测量的正常波动。

---

## §4. 门禁启用（郜郜必读 — CI 配置变更）

### 4.1 改了什么
`.github/workflows/test.yml` 的 `Coverage gate` 步骤：
- **删 `continue-on-error: true`** → 从"只告警不卡"变成"**不达标即 CI 失败、PR 不可合并**"。
- 该步骤跑 `python scripts/run_coverage.py --gate`，按 `scripts/run_coverage.py` 里 `COVERAGE_TARGETS` 逐模块卡。

### 4.2 标准（目标线，定义在 `scripts/run_coverage.py`）
| 模块 | 目标 |
|---|---|
| `app/core/` `app/models/` `app/middlewares/` | ≥ 90% |
| `app/services/` | ≥ 80% |
| `app/routers/` | ≥ 70% |
| `app/adapters/` | ≥ 60% |
| 整体 | ≥ 48% |

### 4.3 本 PR 自验
本 PR 的测试已让各模块达标（§3），所以**本 PR 的 CI 会通过 gate**。合并后 gate 永久生效，后续任何让覆盖率跌破目标线的 PR 都会 CI 红。

### 4.4 郜郜合并前确认
- 看 PR CI 的 `Coverage gate` 步骤是 **pass**（不是 continue-on-error 的 warn）。
- 合并后若想临时放宽某模块目标线：改 `scripts/run_coverage.py` 的 `COVERAGE_TARGETS` + 同步 `CLAUDE.md`/`AGENTS.md` 表。

### 4.5 本地复跑
```bash
cd backend && python scripts/run_coverage.py          # 只看数字
cd backend && python scripts/run_coverage.py --gate   # 严格门禁（退出码 0=过 / 1=不过）
```

---

## §5. 测试与质量

- 全量 `tests/unit + tests/integration` = **1954 passed, 1 skipped, 0 failed**，零回归
- 路由 direct-call（绕过 ASGITransport coverage 波动）；清理 fixture 用 prefix-scoped（`cov_%`）避免删其他测试遗留数据

---

## §6. 风险与回滚

- **业务风险=0**（0 业务代码）；CI 门禁变严是**有意为之**（覆盖率已达标）
- 回滚门禁：给 `Coverage gate` 步骤加回 `continue-on-error: true`（1 行）即可恢复 warn-only
- **部署**：无（无迁移/依赖/env/进程）

---

## §7. 已知遗留（不阻塞）
- `tool_extract_frames` 测试跑 ffmpeg 时留垃圾文件 `backend/scale='min(720,iw)':-2`（`-vf scale` 滤镜参数被误当输出文件名）——测试隔离小隐患，待单独修
- 5 个大路由仍 <70%（persona/subtitle/values_writer 等），但 **routers/ 目录已达标**，不影响门禁；拉更高总覆盖率为后续 round
