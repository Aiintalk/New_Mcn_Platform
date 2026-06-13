# MCN Platform · 测试策略

> 版本 v1.0 | 2026-06-10
> 本文件定义 MCN 平台的测试体系：金字塔分层、覆盖率目标、命名规范、Fixture 模式、Mock 策略、TDD 流程。

---

## 1. 测试金字塔

```
         ╱  E2E  ╲          10%  — 完整 HTTP 链路（需运行中的服务器）
        ╱─────────╲
       ╱ 集成测试  ╲         20%  — Router + 真实测试 DB
      ╱─────────────╲
     ╱   单元测试    ╲       70%  — Service（Mock DB）、Core 工具函数
    ╱─────────────────╲
```

| 层级 | 后端 | 前端 |
|------|------|------|
| **单元** | core/、services/（Mock DB）、models/ | store/、api/（Mock fetch） |
| **集成** | routers/（TestClient + 测试 DB） | 组件渲染 + Mock API |
| **E2E** | httpx 对运行中的服务发请求 | 浏览器自动化（暂不实施） |

---

## 2. 覆盖率目标

| 后端模块 | 最低覆盖率 | 说明 |
|----------|-----------|------|
| `app/core/` | 90% | 安全、配置、响应封装 — 系统根基 |
| `app/models/` | 90% | ORM 模型约束、默认值、关系 |
| `app/services/` | 80% | 业务逻辑，Mock DB 测试 |
| `app/routers/` | 70% | API 接口，集成测试 |
| `app/adapters/` | 60% | 外部服务适配器，依赖第三方可用性 |
| `app/middlewares/` | 90% | 鉴权中间件，安全关键 |

| 前端模块 | 最低覆盖率 | 说明 |
|----------|-----------|------|
| `src/store/` | 80% | 状态管理逻辑 |
| `src/api/` | 80% | API 调用封装和错误处理 |
| `src/pages/` | 60% | 页面组件（渲染 + 交互） |

**执行规则：**
- 每次重大迭代后必须运行覆盖率统计
- 新代码导致覆盖率低于目标线时，先补测试再继续开发
- 覆盖率数字不是终点 — 测试质量（正常路径 + 错误路径 + 边界条件）更重要

---

## 3. 测试命名规范

### 格式

```
test_{被测单元}_{场景}_{预期结果}
```

### 示例

```python
# 后端
test_create_access_token_valid_payload_returns_signed_jwt
test_verify_token_expired_token_raises_401
test_pick_credential_skips_cooldown_credentials
test_login_invalid_password_returns_AUTH_INVALID_PASSWORD
```

```typescript
// 前端（使用 describe/it 风格，测试描述用自然语言）
describe('authStore', () => {
  it('stores token and updates state on setAuth', () => { ... })
  it('clears auth and redirects on AUTH_TOKEN_EXPIRED', () => { ... })
})

describe('LoginPage', () => {
  it('disables login button when fields are empty', () => { ... })
})
```

---

## 4. 后端测试分类

### 4.1 单元测试（Mock DB）

**目录**: `backend/tests/unit/`

| 子目录 | 测试目标 | Mock 策略 |
|--------|---------|----------|
| `core/` | security.py、response.py、config.py | 不需要 Mock（纯函数） |
| `services/` | credential_selector.py、intake_report.py 等 | Mock `AsyncSession`（`unittest.mock.AsyncMock`） |
| `models/` | ORM 模型约束验证 | Mock Session 或用测试 DB |
| `middlewares/` | auth.py 鉴权逻辑 | Mock `AsyncSessionLocal` + patch `verify_token` |

**单元测试 conftest 模式：**

```python
# tests/unit/conftest.py
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_db():
    """提供 Mock AsyncSession，用于 Service 层单元测试。"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session
```

### 4.2 集成测试（真实测试 DB）

**目录**: `backend/tests/integration/`

| 子目录/文件 | 测试目标 | 策略 |
|--------|---------|------|
| `routers/` | 所有 API 端点 | FastAPI TestClient + 测试数据库 |
| `test_convention_guard.py` | 开发红线自动化守卫 | AST 静态分析扫描（红线 #1 标准信封、#2 OperationLog） |
| `test_credential_pool.py` | AI 凭证池并发安全 | 多 session + asyncio.gather 验证 FOR UPDATE SKIP LOCKED |

**集成测试 conftest 模式：**

```python
# tests/integration/conftest.py
import httpx
from app.main import app
from app.core.database import get_db

@pytest.fixture
async def test_client(test_session):
    """FastAPI TestClient，override get_db 使用测试数据库。"""
    async def override_get_db():
        yield test_session
    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()
```

### 4.3 E2E 测试

**目录**: `backend/tests/intake/`、`backend/tests/concurrent/`

现有模式保持不变 — 对运行中的服务发 HTTP 请求。

---

## 5. 前端测试分类

### 5.1 单元测试

**目录**: `frontend/src/__tests__/unit/`

| 子目录 | 测试目标 | Mock 策略 |
|--------|---------|----------|
| `store/` | authStore 等 Zustand store | 直接调用 store 方法 |
| `api/` | request.ts 封装和各 API 模块 | Mock `globalThis.fetch` |

### 5.2 组件测试

**目录**: `frontend/src/__tests__/components/`

- React Testing Library 渲染组件
- Mock API 调用（`vi.mock('src/api/xxx')`）
- 用户交互（`@testing-library/user-event`）

---

## 6. Fixture 模式

### 后端 Fixture 层次

```
tests/conftest.py          ← 根级：测试引擎、测试会话、用户 fixtures、JWT、headers
tests/unit/conftest.py     ← 单元：mock_db、mock_session_factory
tests/integration/conftest.py  ← 集成：test_client（带 dependency override）
tests/intake/conftest.py   ← E2E：保留现有模式
```

### 核心 Fixtures

**根级（tests/conftest.py）**

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `test_engine` | session | 测试数据库异步引擎 |
| `test_session` | function | 测试数据库会话（每个测试后回滚） |
| `admin_user` | function | 在测试 DB 中创建 admin 用户 |
| `operator_user` | function | 在测试 DB 中创建 operator 用户（已改密） |
| `admin_token` | function | admin JWT |
| `operator_token` | function | operator JWT |
| `admin_headers` | function | admin 的 `{"Authorization": "Bearer {token}"}` |
| `operator_headers` | function | operator 的 `{"Authorization": "Bearer {token}"}` |

**集成测试级（tests/integration/conftest.py）**

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `test_client` | function | httpx.AsyncClient + ASGI Transport + get_db override |

---

## 7. Mock 策略详解

### 后端 Service 层

```python
from unittest.mock import AsyncMock, patch

async def test_pick_credential_returns_enabled():
    mock_session = AsyncMock()
    # 模拟 execute 返回结果
    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = [mock_credential]
    mock_session.execute.return_value = mock_result

    result = await pick_credential("ai", mock_session)
    assert result.id == mock_credential.id
```

### 后端 Router 层（集成）

```python
# 用 FastAPI dependency override 注入测试 DB 和测试用户
async def override_get_current_user():
    return test_user

app.dependency_overrides[get_current_user] = override_get_current_user
# ... 测试结束后 app.dependency_overrides.clear()
```

### 前端 API 层

```typescript
// vitest mock
vi.mock('../src/api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

test('login calls correct endpoint', async () => {
  const { post } = await import('../src/api/request')
  vi.mocked(post).mockResolvedValue({ access_token: 'xxx', ... })
  await login('admin', 'pass')
  expect(post).toHaveBeenCalledWith('/api/auth/login', { username: 'admin', password: 'pass' })
})
```

---

## 8. TDD 红-绿-重构流程

### 严格模式（Sprint 3 及之后的新功能必须遵循）

```
1. 写测试
   - 定义预期行为（接口输入 → 输出、DB 状态变更、错误码）
   - 运行测试 → 红灯（实现不存在）

2. 写实现
   - 最少代码让测试通过
   - 运行测试 → 绿灯
   - 不做额外优化

3. 重构
   - 保持绿灯
   - 清理代码、提取公共逻辑、改善命名
   - 运行测试 → 仍绿灯

4. 提交
   - 一个完整的 red-green-refactor 循环 = 一次提交
```

### 宽松模式（已有代码补测试）

- 先写测试覆盖已有行为
- 测试失败时说明发现了 bug → 修复
- 测试通过说明行为符合预期 → 继续

---

## 9. 覆盖率门禁

### 分层目标（底线，不可妥协）

| 后端模块 | 最低覆盖率 | 说明 |
|----------|-----------|------|
| `app/core/` | ≥ 90% | 安全、配置、响应封装 — 系统根基 |
| `app/models/` | ≥ 90% | ORM 模型约束、默认值、关系 |
| `app/services/` | ≥ 80% | 业务逻辑，Mock DB 测试 |
| `app/routers/` | ≥ 70% | API 接口，集成测试 |
| `app/adapters/` | ≥ 60% | 外部服务适配器，依赖第三方可用性 |
| `app/middlewares/` | ≥ 90% | 鉴权中间件，安全关键 |
| **后端整体** | ≥ 75% | 加权平均 |

| 前端模块 | 最低覆盖率 | 说明 |
|----------|-----------|------|
| `src/store/` | ≥ 80% | 状态管理逻辑 |
| `src/api/` | ≥ 80% | API 调用封装和错误处理 |
| `src/pages/` | ≥ 60% | 页面组件（渲染 + 交互） |
| **前端整体** | ≥ 70% | 加权平均 |

### 门禁规则（4 条铁律）

| # | 规则 | 执行方式 |
|---|------|---------|
| 1 | **覆盖率有底线**：上述分层目标不可妥协 | `scripts/run_coverage.py --gate` 逐模块检查，任一模块不达标即退出非零 |
| 2 | **迭代交付包含覆盖率数据**：每次重大需求迭代完成后，必须重新运行覆盖率统计，结果作为交付报告的一部分 | 无覆盖率数据不算完成 |
| 3 | **覆盖率下降即阻塞**：新代码导致覆盖率低于目标线时，必须先补测试再继续开发功能 | `--gate` 对比上次基线，下降超 2% 即警告 |
| 4 | **测试质量 > 测试数量**：覆盖正常路径 + 错误路径 + 边界条件。仅测 happy path 即使数字达标仍需补充 | Code Review 时检查测试质量维度 |

### 门禁脚本

```bash
# 后端门禁（推荐在每次 commit 前运行）
cd backend && python scripts/run_coverage.py --gate

# 手动运行完整覆盖率报告
cd backend && pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# 前端门禁
cd frontend && npx vitest run --coverage
```

`scripts/run_coverage.py --gate` 行为：
1. 运行 `pytest --cov=app --cov-report=json:.coverage_report.json --override-ini=addopts=`
2. 逐模块对比覆盖率与目标线
3. 任一模块低于目标 → 打印红色警告 + 退出码 1
4. 与上次基线（`.coverage_baseline.json`）对比，整体下降超 2% → 退出码 2（门禁失败，不更新基线）
5. 全部达标 → 退出码 0 + 更新基线

### 交付报告格式

每次迭代交付时，覆盖率数据按以下格式呈现：

```
## 覆盖率报告 — Sprint X / BugFix-XX

| 模块 | 覆盖率 | 目标 | 状态 |
|------|--------|------|------|
| app/core/ | 92% | ≥90% | ✅ |
| app/models/ | 88% | ≥90% | ❌ 需补测试 |
| ... | | | |
| 整体 | 78% | ≥75% | ✅ |
```

---

## 10. 测试文件组织

### 后端目录结构

```
backend/tests/
├── conftest.py                    # 根级共享 fixtures
├── unit/
│   ├── conftest.py                # mock session factory
│   ├── core/
│   │   ├── test_security.py
│   │   ├── test_response.py
│   │   └── test_config.py
│   ├── services/
│   │   ├── test_credential_selector.py
│   │   └── test_intake_report.py
│   ├── models/
│   │   └── test_user_model.py
│   └── middlewares/
│       └── test_auth.py
├── integration/
│   ├── conftest.py                # 真实测试 DB + test client
│   ├── test_convention_guard.py   # 规范守卫（AST 扫描红线 #1 #2）
│   ├── test_credential_pool.py    # AI 凭证池并发安全（21 条）
│   └── routers/
│       ├── test_auth.py
│       ├── test_admin_users.py
│       └── test_persona.py
├── intake/                        # E2E（已有）
└── concurrent/                    # 并发测试（已有）
```

### 前端目录结构

```
frontend/src/__tests__/
├── unit/
│   ├── store/
│   │   └── authStore.test.ts
│   └── api/
│       ├── request.test.ts
│       └── persona.test.ts
└── components/
    └── pages/
        ├── LoginPage.test.tsx
        └── PersonaPage.test.tsx
```

---

## 11. 修订记录

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-06-10 | 初始版本 |
| v1.1 | 2026-06-10 | 补充覆盖率门禁铁律 + 分层底线 + 门禁脚本 + 交付报告格式 |
| v1.2 | 2026-06-13 | 新增规范守卫测试 + 凭证池并发测试分类；更新集成测试目录树 |
