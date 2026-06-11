# MCN Platform 工程化升级交付清单

> Phase 0-4 | 2026-06-10
> 补丁文件：`mcn_tdd_upgrade_phase0-4.patch`（238K）
> 应用方式：`git apply mcn_tdd_upgrade_phase0-4.patch`

---

## 一、变更概览

| 分类 | 新增文件 | 修改文件 | 测试数 |
|------|---------|---------|--------|
| 文档 | 3 | 0 | — |
| 后端基础设施 | 6 | 2 | — |
| 后端单元测试 | 6 | 0 | 50 |
| 后端集成测试 | 2 | 0 | 18 |
| 前端基础设施 | 2 | 2 | — |
| 前端测试 | 3 | 0 | 24 |
| 门禁脚本 | 1 | 0 | — |
| **合计** | **23** | **4** | **92** |

---

## 二、文件清单

### 2.1 文档（Phase 0）

| 文件 | 说明 |
|------|------|
| `CLAUDE.md`（项目根） | 项目级开发规范，Claude Code 每次会话自动加载。含技术栈、目录结构、后端/前端约定、覆盖率门禁铁律、TDD 流程、常用命令 |
| `docs/standards/MCN_Testing_Strategy.md` | 测试策略文档 v1.1。测试金字塔、分层覆盖率目标、命名规范、Fixture 模式、Mock 策略、TDD 红-绿-重构流程、4 条门禁铁律、交付报告格式 |
| `docs/standards/MCN_Backend_Coding_Standard.md` | 后端编码规范。命名、Router/Service/Model 模式、日志、Import 排序、错误码注册、代码质量阈值 |

### 2.2 后端测试基础设施（Phase 1）

| 文件 | 说明 |
|------|------|
| `backend/pytest.ini` | 新增 `--cov=app --cov-report=term-missing --cov-fail-under=10` |
| `backend/requirements.txt` | 新增 `pytest-cov>=5.0` |
| `backend/tests/conftest.py` | 根级共享 fixtures：测试数据库引擎/会话、admin/operator 用户和 token、auth headers |
| `backend/tests/unit/conftest.py` | `mock_db` fixture（AsyncMock，用于 Service 层单元测试） |
| `backend/tests/integration/conftest.py` | `test_client` fixture（httpx.AsyncClient + ASGITransport + get_db override） |
| `backend/tests/unit/__init__.py` + 4 个子目录 `__init__.py` | 测试目录结构 |
| `backend/tests/integration/__init__.py` + 2 个子目录 `__init__.py` | 测试目录结构（routers、models） |
| `backend/tests/e2e/__init__.py` | E2E 测试目录占位 |

### 2.3 后端单元测试（Phase 3，50 个测试）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/unit/core/test_security.py` | 8 | JWT 创建（payload 字段、过期时间）、验证（有效、过期、签名错误、格式错误） |
| `tests/unit/core/test_response.py` | 10 | `success_response`/`error_response` 结构、ErrorCode 常量、ApiResponse 序列化 |
| `tests/unit/core/test_config.py` | 4 | Settings 加载、默认值 |
| `tests/unit/middlewares/test_auth.py` | 11 | `get_current_user`（缺 token、无效 token、已删除用户、已禁用用户、token_version 不匹配、有效 token）、`require_admin`、`require_password_changed` |
| `tests/unit/services/test_credential_selector.py` | 7 | `pick_credential`（无可用密钥、正常选中、按 model 过滤）、`report_success`、`report_failure`（递增、触发 cooldown、低于阈值不触发） |
| `tests/unit/services/test_intake_report.py` | 10 | `_strip_markdown`（h1/h2/h3/加粗/斜体/下划线/混合）、`generate_docx`（文件创建、达人名称、markdown 标题） |

### 2.4 后端集成测试（Phase 3，18 个测试）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/integration/routers/test_auth.py` | 9 | 登录（有效/无效密码/不存在用户）、me（有效 token/无 token）、改密（密码不一致/旧密码错误）、登出（成功/无 token） |
| `tests/integration/routers/test_admin_users.py` | 9 | 用户列表分页/权限拦截、创建（成功/重名 409/权限拦截）、重置密码、禁用/启用、软删除 |

> 注意：集成测试需要 PostgreSQL 测试库 `mcn_test` 才能运行。

### 2.5 前端测试基础设施（Phase 2）

| 文件 | 说明 |
|------|------|
| `frontend/package.json` | 新增 devDependencies：vitest、@testing-library/react、@testing-library/jest-dom、@testing-library/user-event、jsdom、happy-dom。新增 scripts：`test`、`test:watch`、`test:coverage` |
| `frontend/package-lock.json` | 锁文件更新 |
| `frontend/vitest.config.ts` | Vitest 配置：jsdom 环境、v8 覆盖率、setup 文件 |
| `frontend/src/test/setup.ts` | jest-dom 导入 + Ant Design `matchMedia` polyfill |

### 2.6 前端测试（Phase 4，24 个测试）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `src/__tests__/unit/store/authStore.test.ts` | 6 | 初始状态、setAuth 存储 token 到 localStorage、mustChangePassword 标志、clearAuth 重置、updateUser 更新、localStorage 有 token 时 isAuthenticated 为 true |
| `src/__tests__/unit/api/request.test.ts` | 13 | get 带 auth header / query params / 跳过空参数、post 发 JSON body、AUTH_TOKEN_EXPIRED 清 auth 跳登录、AUTH_TOKEN_MISSING 同理、AUTH_FORCE_CHANGE_PASSWORD 跳改密、PERMISSION_DENIED 显示提示、HTTP 401 触发清 auth、patch/put/del 各方法 |
| `src/__tests__/components/pages/LoginPage.test.tsx` | 5 | 渲染输入框和按钮、空表单提交显示验证消息、管理员模式切换、页脚文案、登录按钮为 submit 类型 |

### 2.7 覆盖率门禁

| 文件 | 说明 |
|------|------|
| `backend/scripts/run_coverage.py` | 门禁脚本。`--gate` 模式：逐模块检查覆盖率 vs 目标线，不达标退出码 1；与上次基线对比下降超 2% 则退出码 2（不更新基线）；全部达标退出码 0 并更新基线 |

---

## 三、覆盖率目标

与 `MCN_Testing_Strategy.md` 第 9 节对齐：

| 后端模块 | 目标 | 前端模块 | 目标 |
|----------|------|----------|------|
| `app/core/` | ≥ 90% | `src/store/` | ≥ 80% |
| `app/models/` | ≥ 90% | `src/api/` | ≥ 80% |
| `app/services/` | ≥ 80% | `src/pages/` | ≥ 60% |
| `app/routers/` | ≥ 70% | | |
| `app/middlewares/` | ≥ 90% | | |
| `app/adapters/` | ≥ 60% | | |

---

## 四、关键设计决策

### 4.1 测试分类策略

- **Service 层**：Mock DB（`AsyncMock`），不依赖真实数据库
- **Router 层**：FastAPI `dependency_overrides[get_db]` 注入测试数据库，完整 HTTP 链路
- **中间件层**：Mock `AsyncSessionLocal` 返回自定义 async context manager
- **前端 store/api**：Mock `fetch` / `vi.hoisted` 解决 jsdom localStorage 时机问题

### 4.2 jsdom + Zustand localStorage 兼容方案

`authStore.ts` 在模块初始化时调用 `localStorage.getItem()`，而 vitest 的 jsdom 环境在模块预加载阶段 localStorage 不可用。解决方案：

```typescript
// 用 vi.hoisted 在所有 import 之前 polyfill localStorage
const store = vi.hoisted(() => {
  const s: Record<string, string> = {};
  Object.defineProperty(globalThis, 'localStorage', { value: { ... } });
  return s;
});
// 之后才 import authStore
import { useAuthStore } from '...';
```

### 4.3 Ant Design Form 测试限制

Ant Design Form.Item 的受控组件机制在 jsdom 中无法通过 `userEvent.type` 触发表单值收集。LoginPage 组件测试仅覆盖渲染验证和静态交互，表单提交流程的完整测试留待 E2E 阶段。

---

## 五、测试运行方式

```bash
# 后端单元测试（不需要数据库）
cd backend
source .venv/bin/activate
pytest tests/unit/ -v

# 后端集成测试（需要 PostgreSQL mcn_test 库）
pytest tests/integration/ -v

# 后端覆盖率门禁
python scripts/run_coverage.py --gate

# 前端测试
cd frontend
npx vitest run

# 前端覆盖率
npx vitest run --coverage
```

---

## 六、未完成（Phase 5-6）

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 5 | Sprint 3 后端 TDD 测试（Persona 模块，~66 个测试，全部红灯先行） | 未开始 |
| Phase 6 | Sprint 3 前端 TDD 测试（Persona API + 页面，~17 个测试） | 未开始 |
