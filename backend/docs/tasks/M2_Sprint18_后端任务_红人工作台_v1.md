# M2 Sprint18 后端任务 — 红人工作台（v1）

> 编写时间：2026-06-25
> 需求来源：`docs/pm/M2_Sprint18-22_红人工作台_需求文档.md` § Sprint 18
> 契约来源：`backend/docs/base/MCN_M2_Base_API.md` §24 · `MCN_M2_Base_Database.md` §28-31
> 后端约定：`backend/docs/后端开发约定.md`（必读，动手前通读）

---

## 一、任务范围

| # | 内容 | 说明 |
|---|------|------|
| 1 | Migration 034-037 | kols 加 5 列 + 新建 qianchuan_products / kol_benchmarks / kol_active_products |
| 2 | ORM 模型 | QianchuanProduct、KolBenchmark、KolActiveProduct；扩展 Kol 模型 |
| 3 | Router：千川产品库 | 4 个接口（列表/新建/编辑/软删除） |
| 4 | Router：工作台首页聚合 | 1 个接口（GET dashboard） |
| 5 | Router：对标账号 | 4 个接口（列表/新建/编辑/删除） |
| 6 | Router：在售商品 | 2 个接口（列表/整体替换） |
| 7 | Router：人物档案 | 2 个接口（读取/更新） |
| 8 | 注册到 main.py | 新 Router 挂载 |
| 9 | conftest 补丁 | 新增 AsyncSessionLocal 路由注册到测试 patch 列表 |

**不做清单（本 Sprint 严禁越界）：**
- 不做价值观仿写、复盘、千川脚本预审（后续 Sprint）
- 不做 workspace_tools 表操作（工作台不走工具注册流程）
- 不做 Gemini 相关（Sprint 23）
- 不改现有工具（千川仿写、种草仿写等）的任何后端逻辑

---

## 二、Migration 文件

### 034_kols_persona_details.sql

```sql
-- kols 表新增 5 个人物档案分区字段
ALTER TABLE kols ADD COLUMN IF NOT EXISTS background     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS experience     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS relationships  TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS unique_story   TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS extra_notes    TEXT;
```

### 035_qianchuan_products.sql

```sql
CREATE TABLE IF NOT EXISTS qianchuan_products (
    id                   BIGSERIAL PRIMARY KEY,
    nickname             VARCHAR(100) NOT NULL,
    core_selling_point   VARCHAR(200),
    visualization        TEXT,
    mechanism            TEXT,
    mechanism_exclusive  BOOLEAN NOT NULL DEFAULT FALSE,
    endorsement          TEXT,
    user_feedback        TEXT,
    unique_selling       TEXT,
    awards               VARCHAR(500),
    efficacy_proof       TEXT,
    created_by           BIGINT REFERENCES users(id) ON DELETE SET NULL,
    deleted_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_nickname   ON qianchuan_products(nickname) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_created_by ON qianchuan_products(created_by);
CREATE TRIGGER trg_qianchuan_products_updated BEFORE UPDATE ON qianchuan_products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 036_kol_benchmarks.sql

```sql
CREATE TABLE IF NOT EXISTS kol_benchmarks (
    id           BIGSERIAL PRIMARY KEY,
    kol_id       BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('content', 'livestream')),
    description  TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kol_benchmarks_kol_id ON kol_benchmarks(kol_id);
CREATE TRIGGER trg_kol_benchmarks_updated BEFORE UPDATE ON kol_benchmarks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### 037_kol_active_products.sql

```sql
CREATE TABLE IF NOT EXISTS kol_active_products (
    id         BIGSERIAL PRIMARY KEY,
    kol_id     BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES qianchuan_products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kol_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_kol_id     ON kol_active_products(kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_product_id ON kol_active_products(product_id);
```

---

## 三、ORM 模型

文件位置：`backend/app/models/`

### qianchuan_product.py（新建）

```python
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.sql import func
from app.database import Base

class QianchuanProduct(Base):
    __tablename__ = "qianchuan_products"
    id                  = Column(BigInteger, primary_key=True)
    nickname            = Column(String(100), nullable=False)
    core_selling_point  = Column(String(200))
    visualization       = Column(Text)
    mechanism           = Column(Text)
    mechanism_exclusive = Column(Boolean, nullable=False, default=False)
    endorsement         = Column(Text)
    user_feedback       = Column(Text)
    unique_selling      = Column(Text)
    awards              = Column(String(500))
    efficacy_proof      = Column(Text)
    created_by          = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    deleted_at          = Column(TIMESTAMP(timezone=True))
    created_at          = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at          = Column(TIMESTAMP(timezone=True), server_default=func.now())
```

### kol_benchmark.py（新建）

```python
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func
from app.database import Base

class KolBenchmark(Base):
    __tablename__ = "kol_benchmarks"
    id           = Column(BigInteger, primary_key=True)
    kol_id       = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(20), nullable=False)   # content / livestream
    description  = Column(Text)
    sort_order   = Column(Integer, nullable=False, default=0)
    created_by   = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at   = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=func.now())
```

### kol_active_product.py（新建）

```python
from sqlalchemy import BigInteger, Column, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base

class KolActiveProduct(Base):
    __tablename__ = "kol_active_products"
    __table_args__ = (UniqueConstraint("kol_id", "product_id"),)
    id         = Column(BigInteger, primary_key=True)
    kol_id     = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("qianchuan_products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
```

### kol.py（扩展，新增 5 列）

在现有 `Kol` 类中追加：
```python
background    = Column(Text)
experience    = Column(Text)
relationships = Column(Text)
unique_story  = Column(Text)
extra_notes   = Column(Text)
```

### `__init__.py`（追加导出）

```python
from .qianchuan_product import QianchuanProduct
from .kol_benchmark import KolBenchmark
from .kol_active_product import KolActiveProduct
```

---

## 四、Router 文件

### 4.1 operator_qianchuan_products.py（新建）

路径：`backend/app/routers/operator_qianchuan_products.py`
路由前缀：`/api/operator/qianchuan-products`

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/` | `list_products` | 分页列表，支持 q 搜索，过滤 deleted_at IS NULL |
| POST | `/` | `create_product` | 新建，写 OperationLog |
| PUT | `/{id}` | `update_product` | 编辑，写 OperationLog |
| DELETE | `/{id}` | `delete_product` | 软删除（deleted_at=NOW()），写 OperationLog |

**业务约定：**
- 列表过滤 `deleted_at IS NULL`
- DELETE 只设 `deleted_at`，不物理删除
- 写 OperationLog：`action=create/update/delete_qianchuan_product`，`resource_type="qianchuan_product"`，`resource_id=str(product.id)`

### 4.2 operator_workspace.py（新建）

路径：`backend/app/routers/operator_workspace.py`
路由前缀：`/api/operator/workspace`

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/{kol_id}/dashboard` | `get_dashboard` | 聚合：kol 基本信息 + benchmarks（按 type 分组）+ active_products |
| GET | `/{kol_id}/benchmarks` | `list_benchmarks` | 对标账号，按 sort_order ASC |
| POST | `/{kol_id}/benchmarks` | `create_benchmark` | 新建对标账号 |
| PUT | `/{kol_id}/benchmarks/{id}` | `update_benchmark` | 编辑 |
| DELETE | `/{kol_id}/benchmarks/{id}` | `delete_benchmark` | 物理删除 |
| GET | `/{kol_id}/active-products` | `list_active_products` | 在售商品列表（JOIN qianchuan_products） |
| PUT | `/{kol_id}/active-products` | `update_active_products` | 整体替换：先删旧关联，再批量插入新关联 |

**dashboard 聚合逻辑：**
```
1. SELECT kols WHERE id=kol_id AND deleted_at IS NULL（404 if not found）
2. SELECT kol_benchmarks WHERE kol_id=kol_id ORDER BY sort_order ASC
   → 按 account_type 分组为 content / livestream 两个列表
3. SELECT qianchuan_products JOIN kol_active_products WHERE kol_id=kol_id AND deleted_at IS NULL
4. 组装返回
```

**update_active_products 逻辑：**
```
1. 接收 product_ids 列表
2. DELETE FROM kol_active_products WHERE kol_id=kol_id
3. INSERT INTO kol_active_products (kol_id, product_id) VALUES (...) （批量）
4. 校验 product_ids 中每个 id 存在且未软删除（不存在则 400）
```

### 4.3 operator_kols.py（已有文件，追加 2 个接口）

> 若已有此 router 文件，在文件末尾追加；若无，新建。

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/api/operator/kols/{kol_id}/persona-details` | `get_persona_details` | 读取 kols 表 5 分区字段 |
| PUT | `/api/operator/kols/{kol_id}/persona-details` | `update_persona_details` | PATCH 语义更新（未传字段保持原值），写 OperationLog |

**get_persona_details 返回：**
```json
{
  "kol_id": 1,
  "background": "...",
  "experience": "...",
  "relationships": "...",
  "unique_story": "...",
  "extra_notes": "...",
  "updated_at": "2026-06-25T00:00:00Z"
}
```

**update_persona_details：**
- 仅更新请求体中 **非 null** 的字段（PATCH 语义），null 表示"不改"
- 写 OperationLog：`action=update_kol_persona_details`，`resource_type="kol"`，`resource_id=str(kol_id)`

---

## 五、main.py 注册

```python
from app.routers import operator_qianchuan_products, operator_workspace

app.include_router(operator_qianchuan_products.router)
app.include_router(operator_workspace.router)
# operator_kols router 若已注册则无需重复，仅追加接口即可
```

---

## 六、conftest.py 补丁

新 router 中用到 `AsyncSessionLocal` 的，需注册到 `backend/tests/conftest.py` 的 patch 列表（见 CLAUDE.md 红线 #7）。按现有 conftest 中 patch 列表的格式追加对应模块路径。

---

## 七、TDD 要求

每个 Router 文件对应一个集成测试文件，路径：
- `backend/tests/integration/routers/test_operator_qianchuan_products.py`
- `backend/tests/integration/routers/test_operator_workspace.py`
- `backend/tests/integration/routers/test_operator_kols_persona.py`

**每个接口必须覆盖：**
1. 正常路径（200/201）
2. 参数校验失败（422）
3. 不存在资源（404）
4. 权限校验（401 无 token）
5. 关键业务约束（如：update_active_products 传入不存在 product_id → 400）

**覆盖率目标：** Services ≥ 80%，Routers ≥ 70%

---

## 八、开发红线核查（完成后自查）

- [ ] 所有非流式接口返回标准信封 `{success, code, message, data}`
- [ ] POST/PUT/DELETE 均写 OperationLog
- [ ] 未使用裸 session，均通过 `get_db()` 依赖注入
- [ ] 软删除接口只设 `deleted_at`，不物理删除
- [ ] conftest patch 列表已更新
- [ ] migration 文件已按顺序命名（034-037）

---

## 九、验收口径

1. `pytest tests/integration/routers/test_operator_qianchuan_products.py` 全部通过
2. `pytest tests/integration/routers/test_operator_workspace.py` 全部通过
3. `pytest tests/integration/routers/test_operator_kols_persona.py` 全部通过
4. `python scripts/run_coverage.py --gate` 不低于基线
5. Migration 034-037 在本地 `mcn_m1` 库执行成功，所有表/列/约束均存在
