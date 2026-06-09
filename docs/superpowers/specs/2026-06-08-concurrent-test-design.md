# MCN Platform · 并发多用户测试设计文档

**日期：** 2026-06-08  
**作者：** QA Claude  
**状态：** 已批准，待实施

---

## 1. 背景与目标

MCN Platform M1 已完成第一章工程基础验收。本文档设计一套**并发多用户测试套件**，目标是：

1. **数据隔离安全**：20-50 个 operator 并发操作时，互相看不到对方的任务/产出/文件
2. **竞态条件防护**：多 admin 同时操作同一资源时，系统行为确定、无脏写
3. **性能基线**：核心接口在 20-50 并发下的 P50/P95/P99 延迟和错误率

---

## 2. 技术选型

| 工具 | 用途 | 原因 |
|------|------|------|
| `pytest` + `pytest-asyncio` | 测试框架 | 语义清晰，断言友好，易集成 CI |
| `httpx.AsyncClient` | 异步 HTTP 客户端 | 已在 requirements.txt，零新依赖 |
| `asyncio.gather()` | 并发模拟 | 标准库，轻量，足够 20-50 并发 |
| 自定义 `reporter.py` | Markdown 报告生成 | 与已有测试报告格式一致 |

---

## 3. 目录结构

```
backend/tests/concurrent/
├── conftest.py          # fixtures：批量创建测试用户、获取 token、teardown 清理
├── test_isolation.py    # 数据隔离测试
├── test_race.py         # 竞态条件测试
├── test_perf.py         # 性能基线测试
└── reporter.py          # 收集结果 → 生成 Markdown 报告

docs/tests/M1/
└── MCN_M1_Concurrent_Test_Report.md   # 自动生成的测试报告（运行后产出）
```

---

## 4. Fixtures 设计（conftest.py）

### 4.1 批量用户创建

测试开始前，以 admin 身份批量创建 `N=20` 个 operator 测试账号：

```
用户名规则：  conc_op_{i}  (i = 0..19)
初始密码：    系统默认初始密码（Mcn@123）
改密后密码：  ConcTest@{i:04d}
角色：        operator
```

每个用户拿到自己的 JWT token，存入 `dict[username -> token]`。

### 4.2 Teardown 清理

所有测试完成后，软删除所有 `conc_op_*` 账号，删除测试中产生的 outputs/tasks/files。确保测试幂等可重复执行。

### 4.3 并发执行器工具函数

```python
async def run_concurrent(coros: list) -> list[dict]:
    """并发执行协程列表，返回 [{success, status_code, latency_ms, data/error}]"""
```

---

## 5. 测试场景设计

### 5.1 数据隔离测试（test_isolation.py）

#### ISO-001：并发查询任务列表 — 各自只见自己的任务

**步骤：**
1. 为 op_0 和 op_1 各插入 3 条 task_jobs（created_by 不同）
2. 20 个 operator 同时 `GET /api/tasks`
3. 断言：每个 operator 的响应只包含自己的任务，total 不超过自己创建的数量

**预期：** 20/20 通过，无一用户看到他人任务

---

#### ISO-002：并发查询产出列表 — 各自只见自己的产出

**步骤：**
1. 为 op_0 和 op_1 各插入 2 条 output
2. 20 个 operator 同时 `GET /api/outputs`
3. 断言：每个 operator 返回数据的 `created_by` 均为自身 user_id

**预期：** 20/20 通过

---

#### ISO-003：跨用户访问 task — 全部 403

**步骤：**
1. 取 op_0 的某个 task_id
2. op_1 ~ op_19 同时 `GET /api/tasks/{task_id_of_op0}`
3. 断言：所有请求返回 `PERMISSION_DENIED`

**预期：** 19/19 均 403

---

#### ISO-004：跨用户访问 output — 全部 403

同 ISO-003，对象换为 output。

---

### 5.2 竞态条件测试（test_race.py）

#### RACE-001：并发创建同名用户 — 只有一个成功

**步骤：**
1. 20 个并发请求同时 `POST /api/admin/users`，username 均为 `race_target_user`
2. 收集所有响应
3. 断言：`success=true` 的响应恰好为 **1 条**，其余为 `USERNAME_ALREADY_EXISTS`
4. 数据库验证：`SELECT COUNT(*) FROM users WHERE username='race_target_user'` = 1

**预期：** 1 成功，19 失败，DB 只有 1 条记录

---

#### RACE-002：并发重置同一用户密码 — 最终状态确定

**步骤：**
1. 20 个 admin token 同时 `POST /api/admin/users/{id}/reset-password`（同一 user）
2. 断言：所有请求均返回 `success=true`（重置密码是幂等操作，每次都合法）
3. 验证：目标用户用系统默认初始密码 `Mcn@123` 能成功登录（所有并发重置的结果一致，不存在多个密码冲突）

**预期：** 20/20 均返回成功，目标用户可用默认初始密码登录，系统无 5xx

---

#### RACE-003：并发停用/启用同一账号 — 最终状态确定不崩溃

**步骤：**
1. 10 个 admin 同时 `POST /api/admin/users/{id}/disable`
2. 另 10 个 admin 同时 `POST /api/admin/users/{id}/enable`
3. 断言：无请求返回 5xx；最终账号状态为 `enabled` 或 `disabled` 之一（非中间态）

**预期：** 0 个 5xx，最终状态确定

---

#### RACE-004：改密后旧 Token 全部失效

**步骤：**
1. op_0 登录拿到 token_old
2. op_0 调用 `POST /api/auth/change-password` 改密
3. 20 个并发请求使用 token_old 访问 `GET /api/tasks`
4. 断言：全部返回 `AUTH_TOKEN_EXPIRED` 或 `AUTH_INVALID_TOKEN`

**预期：** 20/20 均 401，无任何请求穿透

---

### 5.3 性能基线测试（test_perf.py）

并发数：**20**（默认），可通过环境变量 `CONCURRENT_USERS` 调整至 50。

每个接口跑 **3 轮**，取平均值，统计 P50/P95/P99 延迟（单位 ms）。

#### 性能基线阈值

| 接口 | P50 目标 | P95 目标 | P99 目标 | 错误率 |
|------|----------|----------|----------|--------|
| `POST /api/auth/login` | < 200ms | < 500ms | < 1000ms | 0% |
| `GET /api/health` | < 50ms | < 100ms | < 200ms | 0% |
| `GET /api/tasks` | < 300ms | < 800ms | < 1500ms | 0% |
| `GET /api/outputs` | < 300ms | < 800ms | < 1500ms | 0% |
| `GET /api/workspace/tools` | < 200ms | < 500ms | < 1000ms | 0% |
| `GET /api/admin/users` | < 300ms | < 800ms | < 1500ms | 0% |

测试断言：P95 超阈值记为 `WARN`，P99 超阈值记为 `FAIL`，错误率 > 0 记为 `FAIL`。

---

## 6. 报告格式（reporter.py 生成）

报告写入 `docs/tests/M1/MCN_M1_Concurrent_Test_Report.md`，格式：

```markdown
# MCN Platform · M1 并发多用户测试报告

测试日期：YYYY-MM-DD HH:MM
并发用户数：20
测试环境：http://localhost:8000

## 一、数据隔离（4 项）
| 编号 | 场景 | 并发数 | 通过 | 失败 | 结论 |
...

## 二、竞态条件（4 项）
...

## 三、性能基线（6 接口）
| 接口 | P50 | P95 | P99 | 错误率 | 结论 |
...

## 汇总
总计 N 项，通过 X 项，失败 Y 项
结论：通过 / 不通过 / 有条件通过
```

---

## 7. 运行方式

```bash
cd backend

# 安装测试依赖（一次性）
pip install pytest pytest-asyncio

# 运行并发测试，自动生成报告
pytest tests/concurrent/ -v --tb=short

# 调整并发数
CONCURRENT_USERS=50 pytest tests/concurrent/test_perf.py -v
```

---

## 8. 依赖变更

`requirements.txt` 新增（仅测试依赖）：

```
pytest>=8.0
pytest-asyncio>=0.23
```

`httpx` 已有，无需重复添加。

---

## 9. 范围说明

- **本次不包含**：前端 E2E 并发测试、文件上传并发、WebSocket 并发
- **本次不包含**：数据库连接池耗尽测试（需 100+ 并发，超出本次范围）
- **本次不包含**：Locust Web UI 报告（留待后续压测阶段）
