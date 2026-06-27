# Sprint 18 — 红人工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立红人工作台基础架构——Migration 034-037、ORM 模型、后端 13 个接口、前端 Shell + Dashboard + 千川产品库 Module。

**Architecture:** 方案 D：WorkspacePage 作为 Shell，用 activeTab 状态条件渲染各模块组件；工作台是独立路由 `/kol-workspace/:kol_id`，不嵌套 OperatorLayout 侧边栏；工具页后续改造为 Module 组件（本 Sprint 只做 Shell 和 Dashboard + 产品库）。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncpg + PostgreSQL；React 19 + TypeScript 6 + Ant Design 5 + react-router-dom 6；pytest + httpx；vitest + @testing-library/react

---

## 文件清单

**后端新建：**
- `backend/migrations/034_kols_persona_details.sql`
- `backend/migrations/035_qianchuan_products.sql`
- `backend/migrations/036_kol_benchmarks.sql`
- `backend/migrations/037_kol_active_products.sql`
- `backend/app/models/qianchuan_product.py`
- `backend/app/models/kol_benchmark.py`
- `backend/app/models/kol_active_product.py`
- `backend/app/routers/operator_qianchuan_products.py`
- `backend/app/routers/operator_workspace.py`
- `backend/tests/integration/routers/test_operator_qianchuan_products.py`
- `backend/tests/integration/routers/test_operator_workspace.py`
- `backend/tests/integration/routers/test_operator_kols_persona.py`

**后端修改：**
- `backend/app/models/kol.py` — 追加 5 列
- `backend/app/models/__init__.py` — 追加 3 个新模型导出
- `backend/app/routers/admin_kols.py` — 追加 2 个 persona-details 接口
- `backend/app/main.py` — 注册 2 个新 router
- `backend/tests/conftest.py` — 追加 2 个 patch 路径

**前端新建：**
- `frontend/src/types/kolWorkspace.ts`
- `frontend/src/api/qianchuanProducts.ts`
- `frontend/src/api/kolWorkspace.ts`
- `frontend/src/pages/operator/KolWorkspacePage.tsx`
- `frontend/src/pages/operator/workspace/WorkspaceDashboard.tsx`
- `frontend/src/pages/operator/workspace/QianchuanProductsModule.tsx`
- `frontend/src/__tests__/components/pages/KolWorkspacePage.test.tsx`

**前端修改：**
- `frontend/src/App.tsx` — 新增路由 + lazy import
- `frontend/src/pages/admin/KolsPage.tsx` — 每行加「进入工作台」按钮

---

## Task 1: Migration 文件 034-037

**Files:**
- Create: `backend/migrations/034_kols_persona_details.sql`
- Create: `backend/migrations/035_qianchuan_products.sql`
- Create: `backend/migrations/036_kol_benchmarks.sql`
- Create: `backend/migrations/037_kol_active_products.sql`

- [ ] **Step 1: 写 034_kols_persona_details.sql**

```sql
-- kols 表新增 5 个人物档案分区字段（Sprint 18）
ALTER TABLE kols ADD COLUMN IF NOT EXISTS background     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS experience     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS relationships  TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS unique_story   TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS extra_notes    TEXT;
```

- [ ] **Step 2: 写 035_qianchuan_products.sql**

```sql
-- 千川产品库（千川直播带货场景，与 seeding_writer_products 独立）
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
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_nickname
    ON qianchuan_products(nickname) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_created_by
    ON qianchuan_products(created_by);
CREATE TRIGGER trg_qianchuan_products_updated
    BEFORE UPDATE ON qianchuan_products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

- [ ] **Step 3: 写 036_kol_benchmarks.sql**

```sql
-- 达人对标账号（工作台首页展示，与 benchmark_analyses 独立）
CREATE TABLE IF NOT EXISTS kol_benchmarks (
    id           BIGSERIAL PRIMARY KEY,
    kol_id       BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20)  NOT NULL CHECK (account_type IN ('content','livestream')),
    description  TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kol_benchmarks_kol_id ON kol_benchmarks(kol_id);
CREATE TRIGGER trg_kol_benchmarks_updated
    BEFORE UPDATE ON kol_benchmarks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

- [ ] **Step 4: 写 037_kol_active_products.sql**

```sql
-- 达人在售商品关联（多对多：kol ↔ qianchuan_product）
CREATE TABLE IF NOT EXISTS kol_active_products (
    id         BIGSERIAL PRIMARY KEY,
    kol_id     BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES qianchuan_products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kol_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_kol_id
    ON kol_active_products(kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_product_id
    ON kol_active_products(product_id);
```

- [ ] **Step 5: 在本地数据库执行 migrations**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
python - <<'EOF'
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('DATABASE_URL','').replace('postgresql+asyncpg://','postgresql://')
async def run():
    conn = await asyncpg.connect(url)
    for f in ['034_kols_persona_details.sql','035_qianchuan_products.sql',
              '036_kol_benchmarks.sql','037_kol_active_products.sql']:
        sql = open(f'migrations/{f}').read()
        print(f'>>> {f}')
        await conn.execute(sql)
        print('    ✓')
    await conn.close()
asyncio.run(run())
EOF
```

Expected: 4 行 `✓`

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/034_kols_persona_details.sql \
        backend/migrations/035_qianchuan_products.sql \
        backend/migrations/036_kol_benchmarks.sql \
        backend/migrations/037_kol_active_products.sql
git commit -m "feat(db): migrations 034-037 — kol persona fields + qianchuan products + benchmarks + active products"
```

---

## Task 2: ORM 模型

**Files:**
- Create: `backend/app/models/qianchuan_product.py`
- Create: `backend/app/models/kol_benchmark.py`
- Create: `backend/app/models/kol_active_product.py`
- Modify: `backend/app/models/kol.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 新建 qianchuan_product.py**

```python
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class QianchuanProduct(Base):
    __tablename__ = "qianchuan_products"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    nickname            = Column(String(100), nullable=False)
    core_selling_point  = Column(String(200), nullable=True)
    visualization       = Column(Text, nullable=True)
    mechanism           = Column(Text, nullable=True)
    mechanism_exclusive = Column(Boolean, nullable=False, default=False)
    endorsement         = Column(Text, nullable=True)
    user_feedback       = Column(Text, nullable=True)
    unique_selling      = Column(Text, nullable=True)
    awards              = Column(String(500), nullable=True)
    efficacy_proof      = Column(Text, nullable=True)
    created_by          = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at          = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 2: 新建 kol_benchmark.py**

```python
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class KolBenchmark(Base):
    __tablename__ = "kol_benchmarks"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id       = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(20), nullable=False)   # 'content' | 'livestream'
    description  = Column(Text, nullable=True)
    sort_order   = Column(Integer, nullable=False, default=0)
    created_by   = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 3: 新建 kol_active_product.py**

```python
from sqlalchemy import BigInteger, Column, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class KolActiveProduct(Base):
    __tablename__ = "kol_active_products"
    __table_args__ = (UniqueConstraint("kol_id", "product_id", name="uq_kol_active_products"),)

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id     = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("qianchuan_products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: 在 kol.py 末尾追加 5 列**

在 `deleted_at` 那行之前，追加：

```python
    # 人物档案 5 分区（Sprint 18）
    background    = Column(Text, nullable=True)
    experience    = Column(Text, nullable=True)
    relationships = Column(Text, nullable=True)
    unique_story  = Column(Text, nullable=True)
    extra_notes   = Column(Text, nullable=True)
```

- [ ] **Step 5: 在 __init__.py 追加导出**

找到文件末尾，追加：

```python
from .qianchuan_product import QianchuanProduct
from .kol_benchmark import KolBenchmark
from .kol_active_product import KolActiveProduct
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/qianchuan_product.py \
        backend/app/models/kol_benchmark.py \
        backend/app/models/kol_active_product.py \
        backend/app/models/kol.py \
        backend/app/models/__init__.py
git commit -m "feat(models): add QianchuanProduct, KolBenchmark, KolActiveProduct; extend Kol with persona detail fields"
```

---

## Task 3: 后端集成测试 — 千川产品库（TDD 先写测试）

**Files:**
- Create: `backend/tests/integration/routers/test_operator_qianchuan_products.py`

- [ ] **Step 1: 写测试文件**

```python
"""
Integration tests for operator_qianchuan_products router.

Covers:
- Auth: 401 without token, 200 operator OK, 200 admin OK
- GET  /api/operator/qianchuan-products  (list, pagination, search)
- POST /api/operator/qianchuan-products  (create, validation)
- PUT  /api/operator/qianchuan-products/{id}  (update)
- DELETE /api/operator/qianchuan-products/{id}  (soft delete)
"""
import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _create_product(test_session, nickname="大红瓶", mechanism_exclusive=False):
    result = await test_session.execute(text(
        "INSERT INTO qianchuan_products (nickname, core_selling_point, mechanism_exclusive) "
        "VALUES (:nickname, '美白', :me) RETURNING id"
    ), {"nickname": nickname, "me": mechanism_exclusive})
    pid = result.scalar()
    await test_session.commit()
    return pid


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_list_no_token(self, test_client):
        resp = await test_client.get("/api/operator/qianchuan-products")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get("/api/operator/qianchuan-products", headers=admin_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/operator/qianchuan-products",
            headers={"Authorization": "Bearer invalid_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/operator/qianchuan-products
# ---------------------------------------------------------------------------

class TestListProducts:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_headers, test_session):
        await test_session.execute(text("DELETE FROM kol_active_products"))
        await test_session.execute(text("DELETE FROM qianchuan_products"))
        await test_session.commit()
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["items"] == []
        assert body["data"]["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_products(self, test_client, operator_headers, test_session):
        await _create_product(test_session, "大红瓶")
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        body = resp.json()
        names = [p["nickname"] for p in body["data"]["items"]]
        assert "大红瓶" in names

    @pytest.mark.asyncio
    async def test_search_by_nickname(self, test_client, operator_headers, test_session):
        await _create_product(test_session, "搜索专用产品ABC")
        resp = await test_client.get(
            "/api/operator/qianchuan-products?q=搜索专用",
            headers=operator_headers,
        )
        body = resp.json()
        assert any("搜索专用" in p["nickname"] for p in body["data"]["items"])

    @pytest.mark.asyncio
    async def test_soft_deleted_not_returned(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "软删测试产品")
        await test_session.execute(
            text("UPDATE qianchuan_products SET deleted_at = NOW() WHERE id = :id"), {"id": pid}
        )
        await test_session.commit()
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        names = [p["nickname"] for p in resp.json()["data"]["items"]]
        assert "软删测试产品" not in names


# ---------------------------------------------------------------------------
# POST /api/operator/qianchuan-products
# ---------------------------------------------------------------------------

class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_create_success(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"nickname": "新品番茄精华", "core_selling_point": "提亮", "mechanism_exclusive": False},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["nickname"] == "新品番茄精华"
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_create_missing_nickname(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"core_selling_point": "美白"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_exclusive(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"nickname": "独家机制产品", "mechanism_exclusive": True},
            headers=operator_headers,
        )
        assert resp.json()["data"]["mechanism_exclusive"] is True


# ---------------------------------------------------------------------------
# PUT /api/operator/qianchuan-products/{id}
# ---------------------------------------------------------------------------

class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_update_success(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "待更新产品")
        resp = await test_client.put(
            f"/api/operator/qianchuan-products/{pid}",
            json={"nickname": "已更新产品", "core_selling_point": "保湿"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["nickname"] == "已更新产品"

    @pytest.mark.asyncio
    async def test_update_not_found(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/operator/qianchuan-products/999999",
            json={"nickname": "不存在"},
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/operator/qianchuan-products/{id}
# ---------------------------------------------------------------------------

class TestDeleteProduct:
    @pytest.mark.asyncio
    async def test_soft_delete(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "待删除产品")
        resp = await test_client.delete(
            f"/api/operator/qianchuan-products/{pid}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True
        # 验证 deleted_at 已设置
        row = await test_session.execute(
            text("SELECT deleted_at FROM qianchuan_products WHERE id = :id"), {"id": pid}
        )
        assert row.scalar() is not None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, test_client, operator_headers):
        resp = await test_client.delete(
            "/api/operator/qianchuan-products/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试（预期全部失败，因为 router 还没写）**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/integration/routers/test_operator_qianchuan_products.py -v 2>&1 | tail -20
```

Expected: 大部分 FAILED（404 路由不存在）或 ERROR

---

## Task 4: 实现 operator_qianchuan_products router

**Files:**
- Create: `backend/app/routers/operator_qianchuan_products.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: 写 operator_qianchuan_products.py**

```python
"""
app/routers/operator_qianchuan_products.py

千川产品库接口（运营端，JWT operator/admin 鉴权）：
  GET    /api/operator/qianchuan-products         — 列表（分页+搜索）
  POST   /api/operator/qianchuan-products         — 新建
  PUT    /api/operator/qianchuan-products/{id}    — 编辑
  DELETE /api/operator/qianchuan-products/{id}    — 软删除
"""
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.kol_active_product import KolActiveProduct
from app.models.log import OperationLog
from app.models.qianchuan_product import QianchuanProduct
from app.models.user import User

router = APIRouter(prefix="/operator/qianchuan-products", tags=["operator-qianchuan-products"])

_PAGE_SIZE_ALLOWED = {10, 20, 50}


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(status_code=403,
                            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"})
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(status_code=403,
                            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"})
    return current_user


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _product_to_dict(p: QianchuanProduct) -> dict:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "core_selling_point": p.core_selling_point,
        "visualization": p.visualization,
        "mechanism": p.mechanism,
        "mechanism_exclusive": p.mechanism_exclusive,
        "endorsement": p.endorsement,
        "user_feedback": p.user_feedback,
        "unique_selling": p.unique_selling,
        "awards": p.awards,
        "efficacy_proof": p.efficacy_proof,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ProductRequest(BaseModel):
    nickname: str
    core_selling_point: Optional[str] = None
    visualization: Optional[str] = None
    mechanism: Optional[str] = None
    mechanism_exclusive: bool = False
    endorsement: Optional[str] = None
    user_feedback: Optional[str] = None
    unique_selling: Optional[str] = None
    awards: Optional[str] = None
    efficacy_proof: Optional[str] = None


class UpdateProductRequest(BaseModel):
    nickname: Optional[str] = None
    core_selling_point: Optional[str] = None
    visualization: Optional[str] = None
    mechanism: Optional[str] = None
    mechanism_exclusive: Optional[bool] = None
    endorsement: Optional[str] = None
    user_feedback: Optional[str] = None
    unique_selling: Optional[str] = None
    awards: Optional[str] = None
    efficacy_proof: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=None)
async def list_products(
    page: int = 1,
    page_size: int = 20,
    q: Optional[str] = None,
    current_user: User = Depends(require_operator),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        base_q = select(QianchuanProduct).where(QianchuanProduct.deleted_at.is_(None))
        if q:
            base_q = base_q.where(QianchuanProduct.nickname.ilike(f"%{q}%"))

        total_row = await session.execute(
            select(func.count()).select_from(base_q.subquery())
        )
        total = total_row.scalar() or 0

        rows = await session.execute(
            base_q.order_by(QianchuanProduct.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [_product_to_dict(p) for p in rows.scalars().all()]

        return success_response(data={
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": math.ceil(total / page_size) if total else 0,
            },
        })


@router.post("", response_model=None)
async def create_product(
    body: ProductRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        product = QianchuanProduct(
            nickname=body.nickname,
            core_selling_point=body.core_selling_point,
            visualization=body.visualization,
            mechanism=body.mechanism,
            mechanism_exclusive=body.mechanism_exclusive,
            endorsement=body.endorsement,
            user_feedback=body.user_feedback,
            unique_selling=body.unique_selling,
            awards=body.awards,
            efficacy_proof=body.efficacy_proof,
            created_by=current_user.id,
        )
        session.add(product)
        await session.flush()

        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="create_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product.id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(product)
        return success_response(data=_product_to_dict(product))


@router.put("/{product_id}", response_model=None)
async def update_product(
    product_id: int,
    body: UpdateProductRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(QianchuanProduct).where(
                QianchuanProduct.id == product_id,
                QianchuanProduct.deleted_at.is_(None),
            )
        )
        product = row.scalar_one_or_none()
        if not product:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "产品不存在")

        updates: dict = {
            k: v for k, v in body.model_dump(exclude_none=True).items()
        }
        updates["updated_at"] = datetime.now(timezone.utc)

        await session.execute(
            update(QianchuanProduct)
            .where(QianchuanProduct.id == product_id)
            .values(**updates)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(product)
        return success_response(data=_product_to_dict(product))


@router.delete("/{product_id}", response_model=None)
async def delete_product(
    product_id: int,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(QianchuanProduct).where(
                QianchuanProduct.id == product_id,
                QianchuanProduct.deleted_at.is_(None),
            )
        )
        product = row.scalar_one_or_none()
        if not product:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "产品不存在")

        await session.execute(
            update(QianchuanProduct)
            .where(QianchuanProduct.id == product_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        return success_response(data={"id": product_id})
```

- [ ] **Step 2: 在 main.py 注册 router**

在文件 import 区追加：
```python
from app.routers import operator_qianchuan_products
```

在最后一个 `app.include_router` 后追加：
```python
app.include_router(operator_qianchuan_products.router, prefix="/api")
```

- [ ] **Step 3: 在 conftest.py 的 _SESSION_LOCAL_PATCH_TARGETS 追加**

```python
    "app.routers.operator_qianchuan_products.AsyncSessionLocal",
```

- [ ] **Step 4: 运行测试（预期全部通过）**

```bash
pytest tests/integration/routers/test_operator_qianchuan_products.py -v 2>&1 | tail -20
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/operator_qianchuan_products.py \
        backend/app/main.py \
        backend/tests/conftest.py \
        backend/tests/integration/routers/test_operator_qianchuan_products.py
git commit -m "feat(backend): operator qianchuan-products CRUD (list/create/update/soft-delete) with tests"
```

---

## Task 5: 后端集成测试 — 工作台（TDD 先写测试）

**Files:**
- Create: `backend/tests/integration/routers/test_operator_workspace.py`

- [ ] **Step 1: 写测试文件**

```python
"""
Integration tests for operator_workspace router.

Covers:
- GET /{kol_id}/dashboard  (聚合：kol info + benchmarks + active_products)
- GET/POST/PUT/DELETE /{kol_id}/benchmarks
- GET/PUT /{kol_id}/active-products
"""
import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _create_kol(test_session, name="测试达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, status) VALUES (:name, 'signed') RETURNING id"
    ), {"name": name})
    kid = result.scalar()
    await test_session.commit()
    return kid


async def _create_product(test_session, nickname="测试产品"):
    result = await test_session.execute(text(
        "INSERT INTO qianchuan_products (nickname) VALUES (:n) RETURNING id"
    ), {"n": nickname})
    pid = result.scalar()
    await test_session.commit()
    return pid


async def _create_benchmark(test_session, kol_id, account_name="小鹿", account_type="content"):
    result = await test_session.execute(text(
        "INSERT INTO kol_benchmarks (kol_id, account_name, account_type) "
        "VALUES (:kid, :name, :type) RETURNING id"
    ), {"kid": kol_id, "name": account_name, "type": account_type})
    bid = result.scalar()
    await test_session.commit()
    return bid


# ---------------------------------------------------------------------------
# GET /{kol_id}/dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_no_token(self, test_client, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_dashboard_kol_not_found(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/workspace/999999/dashboard",
                                     headers=operator_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_dashboard_structure(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session, "仪表盘达人")
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "kol" in data
        assert "benchmarks" in data
        assert "content" in data["benchmarks"]
        assert "livestream" in data["benchmarks"]
        assert "active_products" in data

    @pytest.mark.asyncio
    async def test_dashboard_with_benchmarks(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        await _create_benchmark(test_session, kid, "小鹿内容", "content")
        await _create_benchmark(test_session, kid, "橙子直播", "livestream")
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard",
                                     headers=operator_headers)
        data = resp.json()["data"]
        assert len(data["benchmarks"]["content"]) == 1
        assert len(data["benchmarks"]["livestream"]) == 1
        assert data["benchmarks"]["content"][0]["account_name"] == "小鹿内容"


# ---------------------------------------------------------------------------
# Benchmarks CRUD
# ---------------------------------------------------------------------------

class TestBenchmarks:
    @pytest.mark.asyncio
    async def test_create_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.post(
            f"/api/operator/workspace/{kid}/benchmarks",
            json={"account_name": "新账号", "account_type": "content", "description": "测试简介"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["account_name"] == "新账号"
        assert body["data"]["account_type"] == "content"

    @pytest.mark.asyncio
    async def test_create_benchmark_invalid_type(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.post(
            f"/api/operator/workspace/{kid}/benchmarks",
            json={"account_name": "非法类型", "account_type": "invalid"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        bid = await _create_benchmark(test_session, kid, "原名称")
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/benchmarks/{bid}",
            json={"account_name": "新名称", "account_type": "livestream"},
            headers=operator_headers,
        )
        assert resp.json()["data"]["account_name"] == "新名称"

    @pytest.mark.asyncio
    async def test_delete_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        bid = await _create_benchmark(test_session, kid, "待删对标")
        resp = await test_client.delete(
            f"/api/operator/workspace/{kid}/benchmarks/{bid}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True
        # 验证物理删除
        row = await test_session.execute(
            text("SELECT id FROM kol_benchmarks WHERE id = :id"), {"id": bid}
        )
        assert row.scalar() is None

    @pytest.mark.asyncio
    async def test_delete_benchmark_not_found(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.delete(
            f"/api/operator/workspace/{kid}/benchmarks/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Active Products
# ---------------------------------------------------------------------------

class TestActiveProducts:
    @pytest.mark.asyncio
    async def test_list_active_products_empty(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/active-products",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_update_active_products(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        pid1 = await _create_product(test_session, "产品A")
        pid2 = await _create_product(test_session, "产品B")
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/active-products",
            json={"product_ids": [pid1, pid2]},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert set(body["data"]["active_product_ids"]) == {pid1, pid2}

    @pytest.mark.asyncio
    async def test_update_active_products_replaces(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        pid1 = await _create_product(test_session, "旧产品")
        pid2 = await _create_product(test_session, "新产品")
        # 先设置 pid1
        await test_client.put(f"/api/operator/workspace/{kid}/active-products",
                               json={"product_ids": [pid1]}, headers=operator_headers)
        # 替换成 pid2
        await test_client.put(f"/api/operator/workspace/{kid}/active-products",
                               json={"product_ids": [pid2]}, headers=operator_headers)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/active-products",
                                     headers=operator_headers)
        ids = [p["id"] for p in resp.json()["data"]]
        assert pid2 in ids
        assert pid1 not in ids

    @pytest.mark.asyncio
    async def test_update_active_products_invalid_id(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/active-products",
            json={"product_ids": [999999]},
            headers=operator_headers,
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行（预期失败）**

```bash
pytest tests/integration/routers/test_operator_workspace.py -v 2>&1 | tail -10
```

Expected: FAILED（路由不存在）

---

## Task 6: 实现 operator_workspace router

**Files:**
- Create: `backend/app/routers/operator_workspace.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: 写 operator_workspace.py**

```python
"""
app/routers/operator_workspace.py

红人工作台接口（运营端）：
  GET    /api/operator/workspace/{kol_id}/dashboard
  GET    /api/operator/workspace/{kol_id}/benchmarks
  POST   /api/operator/workspace/{kol_id}/benchmarks
  PUT    /api/operator/workspace/{kol_id}/benchmarks/{id}
  DELETE /api/operator/workspace/{kol_id}/benchmarks/{id}
  GET    /api/operator/workspace/{kol_id}/active-products
  PUT    /api/operator/workspace/{kol_id}/active-products
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, validator
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.kol_active_product import KolActiveProduct
from app.models.kol_benchmark import KolBenchmark
from app.models.qianchuan_product import QianchuanProduct
from app.models.user import User

router = APIRouter(prefix="/operator/workspace", tags=["operator-workspace"])


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(status_code=403,
                            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"})
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(status_code=403,
                            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"})
    return current_user


def _product_to_dict(p: QianchuanProduct) -> dict:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "core_selling_point": p.core_selling_point,
        "visualization": p.visualization,
        "mechanism": p.mechanism,
        "mechanism_exclusive": p.mechanism_exclusive,
        "endorsement": p.endorsement,
        "user_feedback": p.user_feedback,
        "unique_selling": p.unique_selling,
        "awards": p.awards,
        "efficacy_proof": p.efficacy_proof,
    }


def _benchmark_to_dict(b: KolBenchmark) -> dict:
    return {
        "id": b.id,
        "kol_id": b.kol_id,
        "account_name": b.account_name,
        "account_type": b.account_type,
        "description": b.description,
        "sort_order": b.sort_order,
    }


async def _get_kol_or_404(session, kol_id: int) -> Kol:
    row = await session.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )
    kol = row.scalar_one_or_none()
    if not kol:
        raise HTTPException(status_code=404,
                            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "达人不存在"})
    return kol


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/{kol_id}/dashboard", response_model=None)
async def get_dashboard(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        kol = await _get_kol_or_404(session, kol_id)

        benchmarks_rows = await session.execute(
            select(KolBenchmark)
            .where(KolBenchmark.kol_id == kol_id)
            .order_by(KolBenchmark.sort_order.asc())
        )
        benchmarks = benchmarks_rows.scalars().all()

        active_rows = await session.execute(
            select(QianchuanProduct)
            .join(KolActiveProduct, KolActiveProduct.product_id == QianchuanProduct.id)
            .where(KolActiveProduct.kol_id == kol_id, QianchuanProduct.deleted_at.is_(None))
        )
        active_products = active_rows.scalars().all()

        return success_response(data={
            "kol": {
                "id": kol.id,
                "name": kol.name,
                "avatar_url": kol.avatar_url,
                "category": kol.category,
            },
            "benchmarks": {
                "content": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "content"],
                "livestream": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "livestream"],
            },
            "active_products": [_product_to_dict(p) for p in active_products],
        })


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

class BenchmarkRequest(BaseModel):
    account_name: str
    account_type: Literal["content", "livestream"]
    description: Optional[str] = None
    sort_order: int = 0


@router.get("/{kol_id}/benchmarks", response_model=None)
async def list_benchmarks(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        rows = await session.execute(
            select(KolBenchmark)
            .where(KolBenchmark.kol_id == kol_id)
            .order_by(KolBenchmark.sort_order.asc())
        )
        benchmarks = rows.scalars().all()
        return success_response(data={
            "content": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "content"],
            "livestream": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "livestream"],
        })


@router.post("/{kol_id}/benchmarks", response_model=None)
async def create_benchmark(
    kol_id: int,
    body: BenchmarkRequest,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        b = KolBenchmark(
            kol_id=kol_id,
            account_name=body.account_name,
            account_type=body.account_type,
            description=body.description,
            sort_order=body.sort_order,
            created_by=current_user.id,
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        return success_response(data=_benchmark_to_dict(b))


@router.put("/{kol_id}/benchmarks/{benchmark_id}", response_model=None)
async def update_benchmark(
    kol_id: int,
    benchmark_id: int,
    body: BenchmarkRequest,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        row = await session.execute(
            select(KolBenchmark).where(KolBenchmark.id == benchmark_id, KolBenchmark.kol_id == kol_id)
        )
        b = row.scalar_one_or_none()
        if not b:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "对标账号不存在")
        b.account_name = body.account_name
        b.account_type = body.account_type
        b.description = body.description
        b.sort_order = body.sort_order
        b.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(b)
        return success_response(data=_benchmark_to_dict(b))


@router.delete("/{kol_id}/benchmarks/{benchmark_id}", response_model=None)
async def delete_benchmark(
    kol_id: int,
    benchmark_id: int,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        row = await session.execute(
            select(KolBenchmark).where(KolBenchmark.id == benchmark_id, KolBenchmark.kol_id == kol_id)
        )
        b = row.scalar_one_or_none()
        if not b:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "对标账号不存在")
        await session.delete(b)
        await session.commit()
        return success_response(data={"id": benchmark_id})


# ---------------------------------------------------------------------------
# Active Products
# ---------------------------------------------------------------------------

class ActiveProductsRequest(BaseModel):
    product_ids: list[int]


@router.get("/{kol_id}/active-products", response_model=None)
async def list_active_products(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        rows = await session.execute(
            select(QianchuanProduct)
            .join(KolActiveProduct, KolActiveProduct.product_id == QianchuanProduct.id)
            .where(KolActiveProduct.kol_id == kol_id, QianchuanProduct.deleted_at.is_(None))
        )
        products = rows.scalars().all()
        return success_response(data=[_product_to_dict(p) for p in products])


@router.put("/{kol_id}/active-products", response_model=None)
async def update_active_products(
    kol_id: int,
    body: ActiveProductsRequest,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)

        # 校验 product_ids 全部存在且未软删
        if body.product_ids:
            rows = await session.execute(
                select(QianchuanProduct.id).where(
                    QianchuanProduct.id.in_(body.product_ids),
                    QianchuanProduct.deleted_at.is_(None),
                )
            )
            found_ids = {r[0] for r in rows.all()}
            missing = set(body.product_ids) - found_ids
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "VALIDATION_ERROR", "message": f"产品 {missing} 不存在"},
                )

        # 整体替换：删旧 → 插新
        await session.execute(
            delete(KolActiveProduct).where(KolActiveProduct.kol_id == kol_id)
        )
        for pid in body.product_ids:
            session.add(KolActiveProduct(kol_id=kol_id, product_id=pid))
        await session.commit()

        return success_response(data={"active_product_ids": body.product_ids})
```

- [ ] **Step 2: 在 main.py 注册**

```python
from app.routers import operator_workspace
# ...
app.include_router(operator_workspace.router, prefix="/api")
```

- [ ] **Step 3: 在 conftest.py 追加 patch 路径**

```python
    "app.routers.operator_workspace.AsyncSessionLocal",
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/integration/routers/test_operator_workspace.py -v 2>&1 | tail -20
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/operator_workspace.py \
        backend/app/main.py \
        backend/tests/conftest.py \
        backend/tests/integration/routers/test_operator_workspace.py
git commit -m "feat(backend): operator workspace router — dashboard, benchmarks CRUD, active-products"
```

---

## Task 7: 人物档案接口 + 测试（TDD）

**Files:**
- Create: `backend/tests/integration/routers/test_operator_kols_persona.py`
- Modify: `backend/app/routers/admin_kols.py`

- [ ] **Step 1: 写测试**

```python
"""
Integration tests for persona-details endpoints on admin_kols router.
GET/PUT /api/operator/kols/{kol_id}/persona-details
"""
import pytest
from sqlalchemy import text


async def _create_kol(test_session, name="人设达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, status) VALUES (:name, 'signed') RETURNING id"
    ), {"name": name})
    kid = result.scalar()
    await test_session.commit()
    return kid


class TestGetPersonaDetails:
    @pytest.mark.asyncio
    async def test_get_no_token(self, test_client, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_empty(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["kol_id"] == kid
        assert data["background"] is None

    @pytest.mark.asyncio
    async def test_get_not_found(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/kols/999999/persona-details",
                                     headers=operator_headers)
        assert resp.status_code == 404


class TestUpdatePersonaDetails:
    @pytest.mark.asyncio
    async def test_update_success(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "85后，杭州人", "experience": "曾经当过护士"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["background"] == "85后，杭州人"
        assert body["data"]["experience"] == "曾经当过护士"

    @pytest.mark.asyncio
    async def test_update_partial(self, test_client, operator_headers, test_session):
        """只传部分字段，其他字段保持原值"""
        kid = await _create_kol(test_session)
        # 先写入全量
        await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "初始背景", "experience": "初始经历"},
            headers=operator_headers,
        )
        # 只更新 background
        await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "更新后背景"},
            headers=operator_headers,
        )
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details",
                                     headers=operator_headers)
        data = resp.json()["data"]
        assert data["background"] == "更新后背景"
        assert data["experience"] == "初始经历"   # 未传的字段保持原值
```

- [ ] **Step 2: 在 admin_kols.py 末尾追加两个接口**

首先在 import 区追加（若没有）：
```python
from app.middlewares.auth import get_current_user, require_admin
```

然后在文件末尾追加：

```python
# ---------------------------------------------------------------------------
# Persona Details（运营端，任何登录用户可读写）
# ---------------------------------------------------------------------------

_operator_router = APIRouter(prefix="/operator/kols", tags=["operator-kols"])


async def _require_operator_kols(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(status_code=403,
                            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"})
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(status_code=403,
                            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"})
    return current_user


class PersonaDetailsRequest(BaseModel):
    background: Optional[str] = None
    experience: Optional[str] = None
    relationships: Optional[str] = None
    unique_story: Optional[str] = None
    extra_notes: Optional[str] = None


def _persona_dict(kol: Kol) -> dict:
    return {
        "kol_id": kol.id,
        "background": kol.background,
        "experience": kol.experience,
        "relationships": kol.relationships,
        "unique_story": kol.unique_story,
        "extra_notes": kol.extra_notes,
        "updated_at": _ts(kol.updated_at),
    }


@_operator_router.get("/{kol_id}/persona-details", response_model=None)
async def get_persona_details(
    kol_id: int,
    current_user: User = Depends(_require_operator_kols),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )
        kol = row.scalar_one_or_none()
        if not kol:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "达人不存在")
        return success_response(data=_persona_dict(kol))


@_operator_router.put("/{kol_id}/persona-details", response_model=None)
async def update_persona_details(
    kol_id: int,
    body: PersonaDetailsRequest,
    request: Request,
    current_user: User = Depends(_require_operator_kols),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )
        kol = row.scalar_one_or_none()
        if not kol:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "达人不存在")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["updated_at"] = datetime.now(timezone.utc)

        await session.execute(
            update(Kol).where(Kol.id == kol_id).values(**updates)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_kol_persona_details",
            target_type="kol",
            target_id=kol_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(kol)
        return success_response(data=_persona_dict(kol))
```

- [ ] **Step 3: 在 main.py 注册 _operator_router**

```python
from app.routers.admin_kols import router as admin_kols_router, _operator_router as operator_kols_router
# ...
app.include_router(operator_kols_router, prefix="/api")
```

- [ ] **Step 4: conftest.py 不需要额外追加**（_operator_router 共用 admin_kols 的 AsyncSessionLocal，已在 patch 列表）

- [ ] **Step 5: 运行测试**

```bash
pytest tests/integration/routers/test_operator_kols_persona.py -v 2>&1 | tail -20
```

Expected: 全部 PASSED

- [ ] **Step 6: 运行全量后端测试**

```bash
pytest tests/ -v --ignore=tests/concurrent --ignore=tests/integration/test_oss_live.py 2>&1 | tail -30
```

Expected: 全部 PASSED，无新增 FAILED

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/admin_kols.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_operator_kols_persona.py
git commit -m "feat(backend): persona-details GET/PUT endpoints on operator/kols router"
```

---

## Task 8: 前端类型定义 + API 层

**Files:**
- Create: `frontend/src/types/kolWorkspace.ts`
- Create: `frontend/src/api/qianchuanProducts.ts`
- Create: `frontend/src/api/kolWorkspace.ts`

- [ ] **Step 1: 写 types/kolWorkspace.ts**

```typescript
// Types for KOL Workspace (Sprint 18)

export interface QianchuanProduct {
  id: number;
  nickname: string;
  core_selling_point: string | null;
  visualization: string | null;
  mechanism: string | null;
  mechanism_exclusive: boolean;
  endorsement: string | null;
  user_feedback: string | null;
  unique_selling: string | null;
  awards: string | null;
  efficacy_proof: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface QianchuanProductsPage {
  items: QianchuanProduct[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export type QianchuanProductFormData = Omit<
  QianchuanProduct,
  'id' | 'created_by' | 'created_at' | 'updated_at'
>;

export interface KolBenchmark {
  id: number;
  kol_id: number;
  account_name: string;
  account_type: 'content' | 'livestream';
  description: string | null;
  sort_order: number;
}

export interface WorkspaceDashboardData {
  kol: {
    id: number;
    name: string;
    avatar_url: string | null;
    category: string | null;
  };
  benchmarks: {
    content: KolBenchmark[];
    livestream: KolBenchmark[];
  };
  active_products: QianchuanProduct[];
}

export interface PersonaDetails {
  kol_id: number;
  background: string | null;
  experience: string | null;
  relationships: string | null;
  unique_story: string | null;
  extra_notes: string | null;
  updated_at: string | null;
}

export type WorkspaceTab =
  | 'dashboard'
  | 'persona'
  | 'products'
  | 'qianchuan-writer'
  | 'values-writer'
  | 'script-review'
  | 'film-review'
  | 'retrospective'
  | 'references';
```

- [ ] **Step 2: 写 api/qianchuanProducts.ts**

```typescript
import { get, post, put, del } from './request';
import type {
  QianchuanProduct,
  QianchuanProductFormData,
  QianchuanProductsPage,
} from '../types/kolWorkspace';

export function getQianchuanProducts(params?: {
  page?: number;
  page_size?: number;
  q?: string;
}): Promise<QianchuanProductsPage> {
  return get<QianchuanProductsPage>('/api/operator/qianchuan-products', params);
}

export function createQianchuanProduct(
  data: QianchuanProductFormData,
): Promise<QianchuanProduct> {
  return post<QianchuanProduct>('/api/operator/qianchuan-products', data);
}

export function updateQianchuanProduct(
  id: number,
  data: Partial<QianchuanProductFormData>,
): Promise<QianchuanProduct> {
  return put<QianchuanProduct>(`/api/operator/qianchuan-products/${id}`, data);
}

export function deleteQianchuanProduct(id: number): Promise<{ id: number }> {
  return del<{ id: number }>(`/api/operator/qianchuan-products/${id}`);
}
```

- [ ] **Step 3: 写 api/kolWorkspace.ts**

```typescript
import { get, put, post, del } from './request';
import type {
  WorkspaceDashboardData,
  KolBenchmark,
  QianchuanProduct,
  PersonaDetails,
} from '../types/kolWorkspace';

export function getWorkspaceDashboard(kolId: number): Promise<WorkspaceDashboardData> {
  return get<WorkspaceDashboardData>(`/api/operator/workspace/${kolId}/dashboard`);
}

export function getBenchmarks(
  kolId: number,
): Promise<{ content: KolBenchmark[]; livestream: KolBenchmark[] }> {
  return get(`/api/operator/workspace/${kolId}/benchmarks`);
}

export function createBenchmark(
  kolId: number,
  data: Omit<KolBenchmark, 'id' | 'kol_id'>,
): Promise<KolBenchmark> {
  return post<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks`, data);
}

export function updateBenchmark(
  kolId: number,
  id: number,
  data: Partial<Omit<KolBenchmark, 'id' | 'kol_id'>>,
): Promise<KolBenchmark> {
  return put<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks/${id}`, data);
}

export function deleteBenchmark(kolId: number, id: number): Promise<{ id: number }> {
  return del<{ id: number }>(`/api/operator/workspace/${kolId}/benchmarks/${id}`);
}

export function getActiveProducts(kolId: number): Promise<QianchuanProduct[]> {
  return get<QianchuanProduct[]>(`/api/operator/workspace/${kolId}/active-products`);
}

export function updateActiveProducts(
  kolId: number,
  productIds: number[],
): Promise<{ active_product_ids: number[] }> {
  return put(`/api/operator/workspace/${kolId}/active-products`, { product_ids: productIds });
}

export function getPersonaDetails(kolId: number): Promise<PersonaDetails> {
  return get<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`);
}

export function updatePersonaDetails(
  kolId: number,
  data: Partial<Omit<PersonaDetails, 'kol_id' | 'updated_at'>>,
): Promise<PersonaDetails> {
  return put<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`, data);
}
```

- [ ] **Step 4: TypeScript 编译检查**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: 无报错

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/kolWorkspace.ts \
        frontend/src/api/qianchuanProducts.ts \
        frontend/src/api/kolWorkspace.ts
git commit -m "feat(frontend): add kolWorkspace types and API layer"
```

---

## Task 9: KolWorkspacePage Shell

**Files:**
- Create: `frontend/src/pages/operator/KolWorkspacePage.tsx`

- [ ] **Step 1: 新建目录**

```bash
mkdir -p /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend/src/pages/operator/workspace
```

- [ ] **Step 2: 写 KolWorkspacePage.tsx**

```tsx
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Spin } from 'antd';
import {
  HomeOutlined,
  UserOutlined,
  ShoppingOutlined,
  ScissorOutlined,
  HeartOutlined,
  SearchOutlined,
  VideoCameraOutlined,
  BarChartOutlined,
  FolderOutlined,
  LeftOutlined,
} from '@ant-design/icons';
import type { WorkspaceTab } from '../../types/kolWorkspace';
import WorkspaceDashboard from './workspace/WorkspaceDashboard';
import QianchuanProductsModule from './workspace/QianchuanProductsModule';

interface NavItem {
  tab: WorkspaceTab;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { tab: 'dashboard',          label: '工作台首页',  icon: <HomeOutlined /> },
  { tab: 'persona',            label: '人物档案',    icon: <UserOutlined />,         disabled: true },
  { tab: 'products',           label: '产品库',      icon: <ShoppingOutlined /> },
  { tab: 'qianchuan-writer',   label: '千川仿写',    icon: <ScissorOutlined />,      disabled: true },
  { tab: 'values-writer',      label: '价值观仿写',  icon: <HeartOutlined />,        disabled: true },
  { tab: 'script-review',      label: '千川脚本预审', icon: <SearchOutlined />,      disabled: true },
  { tab: 'film-review',        label: '千川成片预审', icon: <VideoCameraOutlined />, disabled: true },
  { tab: 'retrospective',      label: '复盘',        icon: <BarChartOutlined />,     disabled: true },
  { tab: 'references',         label: '素材库',      icon: <FolderOutlined />,       disabled: true },
];

export default function KolWorkspacePage() {
  const { kol_id } = useParams<{ kol_id: string }>();
  const navigate = useNavigate();
  const kolId = Number(kol_id);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('dashboard');
  const [kolName, setKolName] = useState('');
  const [loading, setLoading] = useState(true);

  // kolName 由 WorkspaceDashboard 加载后回传，loading 在首次拿到名字后结束
  function handleKolLoaded(name: string) {
    setKolName(name);
    setLoading(false);
  }

  // 校验 kolId
  useEffect(() => {
    if (isNaN(kolId)) navigate('/404', { replace: true });
  }, [kolId, navigate]);

  if (isNaN(kolId)) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-page)' }}>
      {/* 顶部栏 */}
      <header style={{
        height: 52,
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 var(--sp-5)',
        gap: 'var(--sp-3)',
        flexShrink: 0,
      }}>
        <button
          onClick={() => navigate('/admin/kols')}
          style={{
            display: 'flex', alignItems: 'center', gap: 'var(--sp-1)',
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--gray-500)', fontSize: 13,
          }}
        >
          <LeftOutlined style={{ fontSize: 11 }} />
          红人列表
        </button>
        <span style={{ color: 'var(--border)', fontSize: 16 }}>|</span>
        {loading ? (
          <Spin size="small" />
        ) : (
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-800)' }}>
            {kolName} · 工作台
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
          <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>系统运行中</span>
        </div>
      </header>

      {/* 主体：左侧导航 + 内容区 */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左侧导航 */}
        <nav style={{
          width: 160,
          flexShrink: 0,
          background: 'var(--bg-card)',
          borderRight: '1px solid var(--border)',
          padding: 'var(--sp-3) var(--sp-2)',
          overflowY: 'auto',
        }}>
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.tab;
            return (
              <button
                key={item.tab}
                onClick={() => { if (!item.disabled) setActiveTab(item.tab); }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--sp-2)',
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  marginBottom: 2,
                  cursor: item.disabled ? 'not-allowed' : 'pointer',
                  background: isActive ? 'var(--brand-light)' : 'transparent',
                  color: isActive
                    ? 'var(--brand)'
                    : item.disabled
                    ? 'var(--gray-300)'
                    : 'var(--gray-600)',
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 13,
                  textAlign: 'left',
                  opacity: item.disabled ? 0.5 : 1,
                  transition: 'background 0.15s',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* 内容区 */}
        <main style={{ flex: 1, overflowY: 'auto', padding: 'var(--sp-6)' }}>
          {activeTab === 'dashboard' && (
            <WorkspaceDashboard kolId={kolId} onKolLoaded={handleKolLoaded} />
          )}
          {activeTab === 'products' && (
            <QianchuanProductsModule />
          )}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/operator/KolWorkspacePage.tsx
git commit -m "feat(frontend): KolWorkspacePage shell with sidebar nav and tab switching"
```

---

## Task 10: WorkspaceDashboard 模块

**Files:**
- Create: `frontend/src/pages/operator/workspace/WorkspaceDashboard.tsx`

- [ ] **Step 1: 写 WorkspaceDashboard.tsx**

```tsx
import { useState, useEffect, useCallback } from 'react';
import { App, Button, Form, Input, Modal, Popconfirm, Radio, Skeleton, Tag } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  getWorkspaceDashboard,
  createBenchmark,
  updateBenchmark,
  deleteBenchmark,
  updateActiveProducts,
} from '../../../api/kolWorkspace';
import { getQianchuanProducts } from '../../../api/qianchuanProducts';
import type {
  WorkspaceDashboardData,
  KolBenchmark,
  QianchuanProduct,
} from '../../../types/kolWorkspace';

interface WorkspaceDashboardProps {
  kolId: number;
  onKolLoaded?: (name: string) => void;
}

export default function WorkspaceDashboard({ kolId, onKolLoaded }: WorkspaceDashboardProps) {
  const { message } = App.useApp();
  const [data, setData] = useState<WorkspaceDashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  // 对标账号 modal
  const [benchmarkModal, setBenchmarkModal] = useState(false);
  const [editingBenchmark, setEditingBenchmark] = useState<KolBenchmark | null>(null);
  const [benchmarkForm] = Form.useForm();
  const [benchmarkSaving, setBenchmarkSaving] = useState(false);

  // 在售商品 modal
  const [productModal, setProductModal] = useState(false);
  const [allProducts, setAllProducts] = useState<QianchuanProduct[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [productSaving, setProductSaving] = useState(false);
  const [productSearch, setProductSearch] = useState('');

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getWorkspaceDashboard(kolId);
      setData(result);
      onKolLoaded?.(result.kol.name);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载工作台失败');
    } finally {
      setLoading(false);
    }
  }, [kolId, message, onKolLoaded]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  // ── 对标账号 ──────────────────────────────────────────────────────────────

  function openCreateBenchmark() {
    setEditingBenchmark(null);
    benchmarkForm.resetFields();
    benchmarkForm.setFieldsValue({ account_type: 'content', sort_order: 0 });
    setBenchmarkModal(true);
  }

  function openEditBenchmark(b: KolBenchmark) {
    setEditingBenchmark(b);
    benchmarkForm.setFieldsValue(b);
    setBenchmarkModal(true);
  }

  async function handleBenchmarkSave() {
    const values = await benchmarkForm.validateFields();
    setBenchmarkSaving(true);
    try {
      if (editingBenchmark) {
        await updateBenchmark(kolId, editingBenchmark.id, values);
        message.success('已更新');
      } else {
        await createBenchmark(kolId, values);
        message.success('已添加');
      }
      setBenchmarkModal(false);
      loadDashboard();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setBenchmarkSaving(false);
    }
  }

  async function handleDeleteBenchmark(id: number) {
    try {
      await deleteBenchmark(kolId, id);
      message.success('已删除');
      loadDashboard();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }

  // ── 在售商品 ──────────────────────────────────────────────────────────────

  async function openProductModal() {
    try {
      const result = await getQianchuanProducts({ page_size: 50 });
      setAllProducts(result.items);
      setSelectedIds(new Set(data?.active_products.map((p) => p.id) ?? []));
      setProductSearch('');
      setProductModal(true);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载产品库失败');
    }
  }

  async function handleProductSave() {
    setProductSaving(true);
    try {
      await updateActiveProducts(kolId, Array.from(selectedIds));
      message.success('已更新');
      setProductModal(false);
      loadDashboard();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '更新失败');
    } finally {
      setProductSaving(false);
    }
  }

  const filteredProducts = allProducts.filter((p) =>
    p.nickname.includes(productSearch)
  );

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (!data) return null;

  const renderBenchmarkGroup = (items: KolBenchmark[], label: string) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--brand)', marginBottom: 'var(--sp-3)' }}>
        {label}（{items.length} 个）
      </div>
      {items.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--gray-400)', padding: 'var(--sp-3) 0' }}>暂无</div>
      ) : (
        items.map((b) => (
          <div key={b.id} className="card" style={{ padding: 'var(--sp-3)', marginBottom: 'var(--sp-2)', position: 'relative' }}
               onClick={() => openEditBenchmark(b)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{b.account_name}</span>
                <Tag style={{ marginLeft: 8 }}>{b.account_type === 'content' ? '内容' : '直播'}</Tag>
                {b.description && (
                  <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>{b.description}</div>
                )}
              </div>
              <Popconfirm title="确认删除？" onConfirm={(e) => { e?.stopPropagation(); handleDeleteBenchmark(b.id); }}
                          onClick={(e) => e.stopPropagation()}>
                <DeleteOutlined style={{ color: 'var(--gray-300)', fontSize: 13, cursor: 'pointer' }}
                                onClick={(e) => e.stopPropagation()} />
              </Popconfirm>
            </div>
          </div>
        ))
      )}
    </div>
  );

  return (
    <div>
      {/* 对标账号 */}
      <div className="card" style={{ padding: 'var(--sp-5)', marginBottom: 'var(--sp-4)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)' }}>
          <div>
            <div className="card-title">对标账号</div>
            <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>内容对标和直播对标分开维护</div>
          </div>
          <Button size="small" icon={<PlusOutlined />} onClick={openCreateBenchmark}>添加对标账号</Button>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-4)' }}>
          {renderBenchmarkGroup(data.benchmarks.content, '内容对标')}
          {renderBenchmarkGroup(data.benchmarks.livestream, '直播对标')}
        </div>
      </div>

      {/* 目前在售商品 */}
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)' }}>
          <div>
            <div className="card-title">目前在售商品</div>
            <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>展示当前可用于内容和直播脚本的商品池</div>
          </div>
          <Button size="small" icon={<EditOutlined />} onClick={openProductModal}>管理商品</Button>
        </div>
        {data.active_products.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--gray-400)', padding: 'var(--sp-4) 0' }}>
            暂无在售商品，点击「管理商品」选择
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-3)' }}>
            {data.active_products.map((p) => (
              <div key={p.id} className="card" style={{ padding: 'var(--sp-3)', width: 200, flexShrink: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{p.nickname}</div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4 }}>
                  {p.core_selling_point && <Tag color="pink">{p.core_selling_point}</Tag>}
                  {p.mechanism_exclusive && <Tag color="red">只有我有</Tag>}
                </div>
                {p.mechanism && (
                  <div style={{ fontSize: 12, color: 'var(--gray-500)', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                    {p.mechanism}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 对标账号 Modal */}
      <Modal
        title={editingBenchmark ? '编辑对标账号' : '添加对标账号'}
        open={benchmarkModal}
        onCancel={() => setBenchmarkModal(false)}
        onOk={handleBenchmarkSave}
        confirmLoading={benchmarkSaving}
        okText="保存"
        cancelText="取消"
      >
        <Form form={benchmarkForm} layout="vertical" style={{ marginTop: 'var(--sp-4)' }}>
          <Form.Item name="account_name" label="账号名" rules={[{ required: true, message: '请填写账号名' }]}>
            <Input placeholder="如：小鹿内容实验室" />
          </Form.Item>
          <Form.Item name="account_type" label="类型" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="content">内容对标</Radio>
              <Radio value="livestream">直播对标</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="description" label="简介（选填）">
            <Input.TextArea rows={2} placeholder="一句话说明这个账号的参考价值" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 在售商品 Modal */}
      <Modal
        title="管理在售商品"
        open={productModal}
        onCancel={() => setProductModal(false)}
        onOk={handleProductSave}
        confirmLoading={productSaving}
        okText="确认"
        cancelText="取消"
        width={560}
      >
        <Input.Search
          placeholder="搜索产品昵称"
          value={productSearch}
          onChange={(e) => setProductSearch(e.target.value)}
          style={{ marginBottom: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}
        />
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          {filteredProducts.map((p) => (
            <div key={p.id}
                 onClick={() => setSelectedIds((prev) => {
                   const next = new Set(prev);
                   next.has(p.id) ? next.delete(p.id) : next.add(p.id);
                   return next;
                 })}
                 style={{
                   display: 'flex', alignItems: 'center', gap: 'var(--sp-3)',
                   padding: 'var(--sp-2) var(--sp-3)',
                   borderRadius: 'var(--radius-sm)',
                   cursor: 'pointer',
                   background: selectedIds.has(p.id) ? 'var(--brand-light)' : 'transparent',
                   marginBottom: 2,
                 }}>
              <input type="checkbox" readOnly checked={selectedIds.has(p.id)} style={{ cursor: 'pointer' }} />
              <span style={{ fontSize: 13, fontWeight: 500 }}>{p.nickname}</span>
              {p.core_selling_point && (
                <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{p.core_selling_point}</span>
              )}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/operator/workspace/WorkspaceDashboard.tsx
git commit -m "feat(frontend): WorkspaceDashboard — benchmark management + active products"
```

---

## Task 11: QianchuanProductsModule

**Files:**
- Create: `frontend/src/pages/operator/workspace/QianchuanProductsModule.tsx`

- [ ] **Step 1: 写 QianchuanProductsModule.tsx**

```tsx
import { useState, useEffect, useCallback } from 'react';
import {
  App, Button, Checkbox, Form, Input, Modal, Popconfirm, Table, Tag,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  getQianchuanProducts,
  createQianchuanProduct,
  updateQianchuanProduct,
  deleteQianchuanProduct,
} from '../../../api/qianchuanProducts';
import type { QianchuanProduct, QianchuanProductFormData } from '../../../types/kolWorkspace';

const EMPTY_FORM: QianchuanProductFormData = {
  nickname: '',
  core_selling_point: null,
  visualization: null,
  mechanism: null,
  mechanism_exclusive: false,
  endorsement: null,
  user_feedback: null,
  unique_selling: null,
  awards: null,
  efficacy_proof: null,
};

export default function QianchuanProductsModule() {
  const { message } = App.useApp();
  const [items, setItems] = useState<QianchuanProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QianchuanProduct | null>(null);
  const [form] = Form.useForm<QianchuanProductFormData>();
  const [saving, setSaving] = useState(false);

  const loadProducts = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getQianchuanProducts({ page, page_size: 20, q: search || undefined });
      setItems(result.items);
      setTotal(result.pagination.total);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [page, search, message]);

  useEffect(() => { loadProducts(); }, [loadProducts]);

  function openCreate() {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue(EMPTY_FORM);
    setModalOpen(true);
  }

  function openEdit(p: QianchuanProduct) {
    setEditing(p);
    form.setFieldsValue({
      nickname: p.nickname,
      core_selling_point: p.core_selling_point,
      visualization: p.visualization,
      mechanism: p.mechanism,
      mechanism_exclusive: p.mechanism_exclusive,
      endorsement: p.endorsement,
      user_feedback: p.user_feedback,
      unique_selling: p.unique_selling,
      awards: p.awards,
      efficacy_proof: p.efficacy_proof,
    });
    setModalOpen(true);
  }

  async function handleSave() {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateQianchuanProduct(editing.id, values);
        message.success('已更新');
      } else {
        await createQianchuanProduct(values);
        message.success('已创建');
      }
      setModalOpen(false);
      loadProducts();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteQianchuanProduct(id);
      message.success('已删除');
      loadProducts();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }

  const columns: ColumnsType<QianchuanProduct> = [
    {
      title: '产品昵称',
      dataIndex: 'nickname',
      key: 'nickname',
      render: (v: string, r: QianchuanProduct) => (
        <div>
          <span style={{ fontWeight: 600 }}>{v}</span>
          {r.mechanism_exclusive && <Tag color="red" style={{ marginLeft: 6 }}>只有我有</Tag>}
        </div>
      ),
    },
    {
      title: '最主推卖点',
      dataIndex: 'core_selling_point',
      key: 'core_selling_point',
      render: (v: string | null) => v ? <Tag color="pink">{v}</Tag> : '—',
    },
    {
      title: '主推机制',
      dataIndex: 'mechanism',
      key: 'mechanism',
      render: (v: string | null) => v
        ? <span style={{ fontSize: 12, color: 'var(--gray-600)' }}>{v.slice(0, 40)}{v.length > 40 ? '…' : ''}</span>
        : '—',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: QianchuanProduct) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川产品库</h1>
          <p className="page-desc">所有千川脚本工具共用的产品信息，全团队共享</p>
        </div>
        <div className="page-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建产品</Button>
        </div>
      </div>

      <div className="card">
        <div style={{ padding: 'var(--sp-4)', borderBottom: '1px solid var(--border)' }}>
          <Input.Search
            placeholder="搜索产品昵称"
            allowClear
            onSearch={(v) => { setSearch(v); setPage(1); }}
            style={{ maxWidth: 300 }}
          />
        </div>
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="small"
        />
      </div>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editing ? '编辑产品' : '新建产品'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 'var(--sp-4)' }}>
          <Form.Item name="nickname" label="产品昵称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如：大红瓶、番茄精华（脚本里统一怎么称呼）" />
          </Form.Item>
          <Form.Item name="core_selling_point" label="最主推卖点">
            <Input placeholder="几个字即可，如：美白 / 舒缓 / 控油" />
          </Form.Item>
          <Form.Item name="visualization" label="可视化演示点">
            <Input.TextArea rows={2} placeholder="可拍摄的产品演示点" />
          </Form.Item>
          <Form.Item name="mechanism" label="主推机制">
            <Input.TextArea rows={2} placeholder="价格钩子或促销力度，如：买一送一、破价" />
          </Form.Item>
          <Form.Item name="mechanism_exclusive" valuePropName="checked">
            <Checkbox>只有我有（脚本必须写出「只有我有」）</Checkbox>
          </Form.Item>
          <Form.Item name="endorsement" label="推荐来源/背书">
            <Input.TextArea rows={2} placeholder="如：明星同款、知名渠道入驻" />
          </Form.Item>
          <Form.Item name="user_feedback" label="用户反馈">
            <Input.TextArea rows={2} placeholder="如：小红书素人测评、复购率数据" />
          </Form.Item>
          <Form.Item name="unique_selling" label="独家卖点">
            <Input.TextArea rows={2} placeholder="与同类产品最不同的地方，如：独家专利成分" />
          </Form.Item>
          <Form.Item name="awards" label="获奖荣誉">
            <Input placeholder="如：xxx大奖、榜单第一（没有可留空）" />
          </Form.Item>
          <Form.Item name="efficacy_proof" label="功效承诺">
            <Input.TextArea rows={2} placeholder="如：28天实测亮度提升30%（没有可留空）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/operator/workspace/QianchuanProductsModule.tsx
git commit -m "feat(frontend): QianchuanProductsModule — list/create/edit/delete with search"
```

---

## Task 12: 前端路由注册 + KolsPage 入口

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/admin/KolsPage.tsx`

- [ ] **Step 1: 在 App.tsx 添加 lazy import 和路由**

在 lazy imports 区追加：
```tsx
const KolWorkspacePage = lazy(() => import('./pages/operator/KolWorkspacePage'));
```

在 ProtectedRoute 区（operator routes 之前）追加独立路由（不嵌套 OperatorLayout）：
```tsx
{/* KOL Workspace — 独立布局，不用 OperatorLayout */}
<Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />
```

- [ ] **Step 2: 在 KolsPage.tsx 操作列追加「进入工作台」按钮**

找到 KolsPage 中每行的 action 操作区，追加：
```tsx
import { useNavigate } from 'react-router-dom';

// 在组件内：
const navigate = useNavigate();

// 在操作列的按钮区追加（具体位置参考现有编辑/删除按钮旁）：
<Button
  size="small"
  type="primary"
  ghost
  onClick={() => navigate(`/kol-workspace/${kol.id}`)}
>
  进入工作台
</Button>
```

- [ ] **Step 3: TypeScript 编译检查**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: 无新增报错

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/admin/KolsPage.tsx
git commit -m "feat(frontend): add /kol-workspace/:kol_id route and workspace entry in KolsPage"
```

---

## Task 13: 前端单元测试

**Files:**
- Create: `frontend/src/__tests__/components/pages/KolWorkspacePage.test.tsx`

- [ ] **Step 1: 写测试文件**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock react-router-dom useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock API
const mockGetWorkspaceDashboard = vi.fn();
const mockGetQianchuanProducts = vi.fn();
const mockCreateBenchmark = vi.fn();
const mockUpdateBenchmark = vi.fn();
const mockDeleteBenchmark = vi.fn();
const mockUpdateActiveProducts = vi.fn();
const mockCreateQianchuanProduct = vi.fn();
const mockUpdateQianchuanProduct = vi.fn();
const mockDeleteQianchuanProduct = vi.fn();

vi.mock('../../../api/kolWorkspace', () => ({
  getWorkspaceDashboard: (...a: unknown[]) => mockGetWorkspaceDashboard(...a),
  getBenchmarks: vi.fn().mockResolvedValue({ content: [], livestream: [] }),
  createBenchmark: (...a: unknown[]) => mockCreateBenchmark(...a),
  updateBenchmark: (...a: unknown[]) => mockUpdateBenchmark(...a),
  deleteBenchmark: (...a: unknown[]) => mockDeleteBenchmark(...a),
  updateActiveProducts: (...a: unknown[]) => mockUpdateActiveProducts(...a),
  getPersonaDetails: vi.fn().mockResolvedValue({ kol_id: 1, background: null }),
  updatePersonaDetails: vi.fn(),
}));

vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts: (...a: unknown[]) => mockGetQianchuanProducts(...a),
  createQianchuanProduct: (...a: unknown[]) => mockCreateQianchuanProduct(...a),
  updateQianchuanProduct: (...a: unknown[]) => mockUpdateQianchuanProduct(...a),
  deleteQianchuanProduct: (...a: unknown[]) => mockDeleteQianchuanProduct(...a),
}));

const MOCK_DASHBOARD = {
  kol: { id: 1, name: '慧敏', avatar_url: null, category: '美妆' },
  benchmarks: {
    content: [{ id: 1, kol_id: 1, account_name: '小鹿内容', account_type: 'content', description: '测试描述', sort_order: 0 }],
    livestream: [],
  },
  active_products: [
    { id: 1, nickname: '大红瓶', core_selling_point: '美白', mechanism: '买一送一', mechanism_exclusive: false,
      visualization: null, endorsement: null, user_feedback: null, unique_selling: null, awards: null,
      efficacy_proof: null, created_by: null, created_at: null, updated_at: null },
  ],
};

const MOCK_PRODUCTS_PAGE = {
  items: [
    { id: 1, nickname: '大红瓶', core_selling_point: '美白', mechanism: null, mechanism_exclusive: false,
      visualization: null, endorsement: null, user_feedback: null, unique_selling: null, awards: null,
      efficacy_proof: null, created_by: null, created_at: null, updated_at: null },
  ],
  pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
};

function renderWorkspace(kolId = '1') {
  return render(
    <App>
      <MemoryRouter initialEntries={[`/kol-workspace/${kolId}`]}>
        <Routes>
          <Route path="/kol-workspace/:kol_id" element={
            (() => {
              const KolWorkspacePage = require('../../../pages/operator/KolWorkspacePage').default;
              return <KolWorkspacePage />;
            })()
          } />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetWorkspaceDashboard.mockResolvedValue(MOCK_DASHBOARD);
  mockGetQianchuanProducts.mockResolvedValue(MOCK_PRODUCTS_PAGE);
});

describe('KolWorkspacePage Shell', () => {
  it('renders top bar with kol name after loading', async () => {
    renderWorkspace();
    await waitFor(() => expect(screen.getByText(/慧敏/)).toBeTruthy());
    expect(screen.getByText(/工作台/)).toBeTruthy();
  });

  it('shows sidebar navigation', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('工作台首页'));
    expect(screen.getByText('产品库')).toBeTruthy();
    expect(screen.getByText('千川仿写')).toBeTruthy();
  });

  it('defaults to dashboard tab', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('对标账号'));
  });

  it('switches to products tab on click', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('产品库'));
    fireEvent.click(screen.getByText('产品库'));
    await waitFor(() => screen.getByText('千川产品库'));
  });

  it('disabled tabs do not switch on click', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('千川仿写'));
    fireEvent.click(screen.getByText('千川仿写'));
    // 仍然显示 dashboard 内容
    await waitFor(() => expect(screen.queryByText('对标账号')).toBeTruthy());
  });

  it('navigates to /404 for invalid kol_id', async () => {
    renderWorkspace('abc');
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/404', { replace: true }));
  });
});

describe('WorkspaceDashboard', () => {
  it('shows benchmark accounts', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('小鹿内容'));
  });

  it('shows active products', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('大红瓶'));
  });

  it('shows empty state when no benchmarks', async () => {
    mockGetWorkspaceDashboard.mockResolvedValue({
      ...MOCK_DASHBOARD,
      benchmarks: { content: [], livestream: [] },
    });
    renderWorkspace();
    await waitFor(() => expect(screen.getAllByText('暂无').length).toBeGreaterThan(0));
  });
});

describe('QianchuanProductsModule', () => {
  it('shows product list in products tab', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('产品库'));
    fireEvent.click(screen.getByText('产品库'));
    await waitFor(() => screen.getByText('千川产品库'));
    await waitFor(() => screen.getByText('大红瓶'));
  });

  it('opens create modal on new product click', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('产品库'));
    fireEvent.click(screen.getByText('产品库'));
    await waitFor(() => screen.getByText('新建产品'));
    fireEvent.click(screen.getByText('新建产品'));
    await waitFor(() => screen.getByText('产品昵称'));
  });

  it('validates nickname required', async () => {
    renderWorkspace();
    await waitFor(() => screen.getByText('产品库'));
    fireEvent.click(screen.getByText('产品库'));
    await waitFor(() => screen.getByText('新建产品'));
    fireEvent.click(screen.getByText('新建产品'));
    await waitFor(() => screen.getByText('保存'));
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => screen.getByText('必填'));
  });
});
```

- [ ] **Step 2: 运行测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx vitest run src/__tests__/components/pages/KolWorkspacePage.test.tsx 2>&1 | tail -30
```

Expected: 全部 PASSED

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/components/pages/KolWorkspacePage.test.tsx
git commit -m "test(frontend): KolWorkspacePage shell + dashboard + products module unit tests"
```

---

## Task 14: 全量验证

- [ ] **Step 1: 运行后端全量测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/ -v --ignore=tests/concurrent --ignore=tests/integration/test_oss_live.py 2>&1 | tail -40
```

Expected: 全部 PASSED，无回归

- [ ] **Step 2: 运行覆盖率检查**

```bash
python scripts/run_coverage.py --gate 2>&1 | tail -20
```

Expected: 不低于基线

- [ ] **Step 3: 运行前端全量测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx vitest run --coverage 2>&1 | tail -30
```

Expected: 全部 PASSED

- [ ] **Step 4: 启动服务，手动验证黄金路径**

```bash
# 后端（已运行，不需重启）
# 前端（已运行，不需重启）
# 打开 http://localhost:5175
```

验证清单：
- [ ] 进入 `/admin/kols`，每行显示「进入工作台」按钮
- [ ] 点击「进入工作台」跳转到 `/kol-workspace/1`（或对应 ID）
- [ ] 工作台顶部显示达人名字
- [ ] 左侧导航显示 9 个菜单，禁用项灰色无响应
- [ ] Dashboard 显示对标账号 + 在售商品
- [ ] 点击「添加对标账号」弹窗可填写保存
- [ ] 点击「产品库」切换到千川产品库页面
- [ ] 产品库可新建、编辑、删除产品

- [ ] **Step 5: 最终 Commit**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add .
git commit -m "feat: Sprint 18 完成 — 红人工作台 Shell + Dashboard + 千川产品库（后端13接口+前端Module）"
```

