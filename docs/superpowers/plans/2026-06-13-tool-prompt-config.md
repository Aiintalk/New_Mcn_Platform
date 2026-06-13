# tiktok-writer & qianchuan-review Prompt 管理端配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 tiktok-writer（2个静态 Prompt + 模型）和 qianchuan-review（2个 Prompt + 模型）新增管理端可配置功能，参照 selling-point-extractor 的完整实现模式。

**Architecture:** 每个工具新建独立配置表（`tiktok_writer_configs` / `qianchuan_review_configs`），迁移 SQL 写入初始 Prompt 原文；后端新增 admin router（GET/PUT configs）+ 修改 operator router 从 DB 读配置而非硬编码；前端新增管理 Tab，注册进 `WorkspaceConfigPage`。tiktok-writer 只将 `hook_eval`（评估 Opening）和 `structure`（分析结构）两个纯静态 Prompt 纳入配置，`rewrite_*` 和 `iterate` 因含动态插值保留前端。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy asyncpg / React 19 / TypeScript / Ant Design 5

---

## 文件清单

### 新建

| 路径 | 职责 |
|------|------|
| `backend/migrations/017_tiktok_writer_configs.sql` | 新建 tiktok_writer_configs 表 + 初始数据 |
| `backend/migrations/018_qianchuan_review_configs.sql` | 新建 qianchuan_review_configs 表 + 初始数据 |
| `backend/app/models/tiktok_writer.py` | TiktokWriterConfig ORM 模型 |
| `backend/app/models/qianchuan_review.py` | QianchuanReviewConfig ORM 模型 |
| `backend/app/routers/admin_tiktok_writer.py` | 管理端 GET/PUT tiktok_writer_configs |
| `backend/app/routers/admin_qianchuan_review.py` | 管理端 GET/PUT qianchuan_review_configs |
| `frontend/src/pages/admin/TiktokWriterConfigTab.tsx` | tiktok-writer 管理 Tab |
| `frontend/src/pages/admin/QianchuanReviewConfigTab.tsx` | qianchuan-review 管理 Tab |
| `backend/tests/integration/routers/test_admin_tiktok_writer.py` | admin router 集成测试 |
| `backend/tests/integration/routers/test_admin_qianchuan_review.py` | admin router 集成测试 |

### 修改

| 路径 | 改动 |
|------|------|
| `backend/app/models/__init__.py` | 注册两个新 ORM 模型 |
| `backend/app/main.py` | 注册两个新 admin router |
| `backend/app/routers/operator_tiktok_writer.py` | `/chat` 接口从 DB 读 `hook_eval`/`structure` Prompt + 模型，不再接收前端传来的 systemPrompt（仅用于这两步）|
| `backend/app/services/qianchuan_review_service.py` | `generate_review_stream` 从 DB 读 Prompt + 模型替代硬编码常量 |
| `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | 追加两个 Tab |
| `frontend/src/pages/operator/TiktokWriterPage.tsx` | Step1（hook_eval）和 Step2（structure）不再 `buildHookEvalPrompt()`/`buildStructurePrompt()`，改调新接口从后端获取 Prompt + 模型 |

---

## Task 1：数据库迁移 — tiktok_writer_configs 表

**Files:**
- Create: `backend/migrations/017_tiktok_writer_configs.sql`

- [ ] **Step 1: 创建迁移 SQL**

```sql
-- 017_tiktok_writer_configs.sql
-- tiktok-writer 工具 Prompt + 模型配置表

CREATE TABLE tiktok_writer_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_tiktok_writer_configs_updated BEFORE UPDATE ON tiktok_writer_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 初始数据：hook_eval（评估 Opening Hook，纯静态）
INSERT INTO tiktok_writer_configs (config_key, system_prompt, is_active) VALUES
('hook_eval',
'You are a TikTok content strategist. Evaluate the opening hook of this TikTok script.

The "opening" is the first 1-3 sentences that grab attention.

Your task:
1. Identify the exact opening (first 1-3 sentences)
2. Rate if this opening would make a general audience stop scrolling and keep watching
3. Answer with PASS or FAIL

Format your response EXACTLY like this:
OPENING: [copy the exact opening sentences here]
---
VERDICT: [PASS or FAIL]
REASON: [1-2 sentences explaining why]',
true);

-- 初始数据：structure（分析脚本结构，纯静态）
INSERT INTO tiktok_writer_configs (config_key, system_prompt, is_active) VALUES
('structure',
'You are a TikTok script structure analyst. Analyze this TikTok script and break it into clear structural sections.

CRITICAL TASK: You must clearly separate the OPENING (hook) from the BODY.

Format your response EXACTLY like this:

===OPENING_START===
[paste the exact opening sentences here, word for word, no changes]
===OPENING_END===

===STRUCTURE===
1. Opening hook: [describe the technique used]
2. [Section name]: [describe what happens]
3. [Section name]: [describe what happens]
...
===STRUCTURE_END===

===NOTES===
- Key storytelling techniques used
- Tone and pacing observations
===NOTES_END===',
true);
```

- [ ] **Step 2: 执行迁移（在终端运行）**

```bash
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 \
  -f /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/migrations/017_tiktok_writer_configs.sql
```

预期输出：`CREATE TABLE` / `CREATE TRIGGER` / `INSERT 0 1` / `INSERT 0 1`

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/migrations/017_tiktok_writer_configs.sql
git commit -m "feat: add tiktok_writer_configs table (017 migration)"
```

---

## Task 2：数据库迁移 — qianchuan_review_configs 表

**Files:**
- Create: `backend/migrations/018_qianchuan_review_configs.sql`

- [ ] **Step 1: 创建迁移 SQL**

```sql
-- 018_qianchuan_review_configs.sql
-- qianchuan-review 工具 Prompt + 模型配置表

CREATE TABLE qianchuan_review_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_qianchuan_review_configs_updated BEFORE UPDATE ON qianchuan_review_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 初始数据：with_excel（有投放数据时的复盘 Prompt）
INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) VALUES
('with_excel',
'你是千川投流素材复盘专家。你研究过大量千川跑量素材的共性规律，深谙什么样的千川脚本能跑量、什么样的结构能转化。你对开头hook、卖点结构、行动号召、投放效率有极深的实战理解。

你现在要帮投放团队做一期千川素材的复盘分析。

用户会给你本期所有千川素材的**完整脚本文案**以及投放数据（消耗、ROI、转化数、转化成本、3s完播率、点击率、CPM等）。你需要从「花钱效率」视角做深度复盘。

请输出以下模块（**不是每个都必须写，根据数据情况判断哪些有必要**）：

1. **跑量素材拆解**（消耗高 = 平台认可）
   - 哪几条素材消耗最高？
   - 从脚本层面拆解：开头用了什么hook、卖点怎么排的、行动号召怎么设计的
   - 跑量素材之间有没有共性规律（开头类型、结构、节奏）
   - 这套规律怎么复用到下一批素材，给出具体方向

2. **高ROI素材分析**（花钱少但转化好）
   - 哪些素材 ROI 最高？
   - 对比跑量素材，高ROI素材在脚本层面有什么不同
   - 是开头更精准筛人？还是卖点更打痛点？还是行动号召更强？

3. **开头效率分析**（3s完播率是核心）
   - 3s完播率 Top 3 和 Bottom 3，对照脚本开头原文分析
   - 3s高但转化低 = 开头吸引了错误人群，分析原因
   - 3s低 = 开头就劝退了，分析哪里出了问题
   - 给出下一批素材的开头方向建议

4. **亏损素材诊断**（消耗高但ROI差）
   - 哪些素材花了钱但没转化？
   - 是人群不对（开头筛人不精准）？还是卖点没打到（内容和产品脱节）？还是行动号召太弱？
   - 直接说该停就停，给理由

5. **卖点结构洞察**
   - 不同卖点顺序的表现差异
   - 哪类卖点放在前面转化更好
   - 下一批素材推荐的卖点排列

6. **投放效率建议**
   - 整体 CPM 趋势，成本是在涨还是降
   - 建议追投哪些素材、停投哪些
   - 下一批素材的产量和方向建议

要求：
- 你有完整脚本，分析必须引用具体文案细节，不是只看标题
- 所有判断必须有数据支撑，不说"感觉"
- 语言直接，像一个花自己钱投流的操盘手在复盘
- 每条建议都能直接执行
- 如果某个模块没有足够数据支撑，跳过，不凑字数',
true);

-- 初始数据：without_excel（仅脚本时的复盘 Prompt）
INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) VALUES
('without_excel',
'你是千川投流素材复盘专家。你研究过大量千川跑量素材的共性规律，深谙什么样的千川脚本能跑量、什么样的结构能转化。你对开头hook、卖点结构、行动号召、投放效率有极深的实战理解。

你现在要帮投放团队做一期千川素材的复盘分析。

用户会给你本期所有千川素材的**完整脚本文案**。你需要从「花钱效率」视角做深度复盘。

请输出以下模块（**不是每个都必须写，根据数据情况判断哪些有必要**）：

1. **最好的素材**：哪几条脚本写得最好？
   - 开头hook怎么抓人的（前3秒做了什么）
   - 卖点怎么排的、行动号召怎么设计的
   - 跑量潜力判断

2. **建议淘汰的素材**：哪些脚本质量不行？
   - 开头没吸引力？卖点散？行动号召弱？
   - 直接说该砍就砍，给理由

3. **卖点结构分析**
   - 不同卖点排列方式的优劣
   - 推荐的卖点结构

4. **开头类型分析**
   - 各素材开头分别用了什么类型的hook
   - 哪种开头类型在千川场景下效率更高
   - 下一批素材的开头方向建议

5. **新素材方向**：基于好素材的共性规律，推荐新方向
   - 具体到什么角度、什么开头、什么结构

要求：
- 你有完整脚本，分析必须引用具体文案细节，不是只看标题
- 分析要深入到具体的文案句子和段落
- 语言直接，像一个花自己钱投流的操盘手在复盘
- 每条建议都能直接执行
- 如果某个模块没有足够内容支撑，跳过，不凑字数',
true);
```

- [ ] **Step 2: 执行迁移（在终端运行）**

```bash
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 \
  -f /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/migrations/018_qianchuan_review_configs.sql
```

预期输出：`CREATE TABLE` / `CREATE TRIGGER` / `INSERT 0 1` / `INSERT 0 1`

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/migrations/018_qianchuan_review_configs.sql
git commit -m "feat: add qianchuan_review_configs table (018 migration)"
```

---

## Task 3：后端模型 + 注册

**Files:**
- Create: `backend/app/models/tiktok_writer.py`
- Create: `backend/app/models/qianchuan_review.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 tiktok_writer.py 模型**

```python
# backend/app/models/tiktok_writer.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class TiktokWriterConfig(Base):
    """tiktok-writer 工具配置（Prompt + 模型，管理端可配置）"""
    __tablename__ = "tiktok_writer_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 2: 创建 qianchuan_review.py 模型**

```python
# backend/app/models/qianchuan_review.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class QianchuanReviewConfig(Base):
    """qianchuan-review 工具配置（Prompt + 模型，管理端可配置）"""
    __tablename__ = "qianchuan_review_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 3: 注册到 `__init__.py`**

在 `backend/app/models/__init__.py` 末尾追加两行 import 和 `__all__` 条目：

```python
from app.models.tiktok_writer import TiktokWriterConfig
from app.models.qianchuan_review import QianchuanReviewConfig
```

在 `__all__` 列表末尾追加：
```python
    "TiktokWriterConfig",
    "QianchuanReviewConfig",
```

- [ ] **Step 4: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/models/tiktok_writer.py \
        backend/app/models/qianchuan_review.py \
        backend/app/models/__init__.py
git commit -m "feat: add TiktokWriterConfig and QianchuanReviewConfig ORM models"
```

---

## Task 4：后端 admin router — tiktok-writer

**Files:**
- Create: `backend/app/routers/admin_tiktok_writer.py`
- Create: `backend/tests/integration/routers/test_admin_tiktok_writer.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 先写集成测试（TDD 红灯）**

创建 `backend/tests/integration/routers/test_admin_tiktok_writer.py`：

```python
"""Integration tests for admin_tiktok_writer router."""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def seed_configs(test_session):
    for key, prompt in [('hook_eval', 'Hook Eval Prompt'), ('structure', 'Structure Prompt')]:
        await test_session.execute(text(
            "INSERT INTO tiktok_writer_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/tiktok-writer/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/tiktok-writer/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_returns_list(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/tiktok-writer/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        keys = [c["config_key"] for c in data["data"]]
        assert "hook_eval" in keys
        assert "structure" in keys

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/tiktok-writer/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        cfg = next(c for c in resp.json()["data"] if c["config_key"] == "hook_eval")
        for field in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
            assert field in cfg


class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.put(
            "/api/admin/tiktok-writer/configs/hook_eval",
            json={"system_prompt": "new"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/tiktok-writer/configs/hook_eval",
            json={"system_prompt": "Updated Hook Prompt", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        row = (await test_session.execute(
            text("SELECT system_prompt FROM tiktok_writer_configs WHERE config_key='hook_eval'")
        )).fetchone()
        assert row[0] == "Updated Hook Prompt"

    @pytest.mark.asyncio
    async def test_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/tiktok-writer/configs/nonexistent",
            json={"system_prompt": "x"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"
```

- [ ] **Step 2: 运行，确认红灯**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/integration/routers/test_admin_tiktok_writer.py -v 2>&1 | tail -5
```

预期：404 或 ImportError（路由未注册）

- [ ] **Step 3: 创建 admin_tiktok_writer.py**

```python
"""
app/routers/admin_tiktok_writer.py

管理端接口（admin 角色）：
  GET /api/admin/tiktok-writer/configs        — 配置列表
  PUT /api/admin/tiktok-writer/configs/{key}  — 更新配置（Prompt / 模型 / 激活状态）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.tiktok_writer import TiktokWriterConfig
from app.models.user import User

router = APIRouter(prefix="/admin/tiktok-writer", tags=["admin-tiktok-writer"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(TiktokWriterConfig))).scalars().all()
    return success_response(data=[
        {
            "id": c.id,
            "config_key": c.config_key,
            "ai_model_id": c.ai_model_id,
            "system_prompt": c.system_prompt,
            "is_active": c.is_active,
            "updated_at": _ts(c.updated_at),
        }
        for c in configs
    ])


@router.put("/configs/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        update(TiktokWriterConfig)
        .where(TiktokWriterConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(TiktokWriterConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    await db.commit()
    return success_response(data={"config_key": config_key})
```

- [ ] **Step 4: 注册到 main.py**

在 `backend/app/main.py` 的 import 区（`admin_selling_point_router` 之后）追加：
```python
from app.routers.admin_tiktok_writer import router as admin_tiktok_writer_router
```

在 `app.include_router(admin_selling_point_router, prefix="/api")` 之后追加：
```python
app.include_router(admin_tiktok_writer_router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认绿灯**

```bash
pytest tests/integration/routers/test_admin_tiktok_writer.py -v 2>&1 | tail -8
```

预期：`7 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/routers/admin_tiktok_writer.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_admin_tiktok_writer.py
git commit -m "feat: add admin_tiktok_writer router (GET/PUT configs)"
```

---

## Task 5：后端 admin router — qianchuan-review

**Files:**
- Create: `backend/app/routers/admin_qianchuan_review.py`
- Create: `backend/tests/integration/routers/test_admin_qianchuan_review.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 先写集成测试（TDD 红灯）**

创建 `backend/tests/integration/routers/test_admin_qianchuan_review.py`：

```python
"""Integration tests for admin_qianchuan_review router."""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def seed_configs(test_session):
    for key, prompt in [('with_excel', 'With Excel Prompt'), ('without_excel', 'Without Excel Prompt')]:
        await test_session.execute(text(
            "INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-review/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_returns_list(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        keys = [c["config_key"] for c in data["data"]]
        assert "with_excel" in keys
        assert "without_excel" in keys

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        cfg = next(c for c in resp.json()["data"] if c["config_key"] == "with_excel")
        for field in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
            assert field in cfg


class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/with_excel",
            json={"system_prompt": "new"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/with_excel",
            json={"system_prompt": "Updated With Excel Prompt", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        row = (await test_session.execute(
            text("SELECT system_prompt FROM qianchuan_review_configs WHERE config_key='with_excel'")
        )).fetchone()
        assert row[0] == "Updated With Excel Prompt"

    @pytest.mark.asyncio
    async def test_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/nonexistent",
            json={"system_prompt": "x"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"
```

- [ ] **Step 2: 运行，确认红灯**

```bash
pytest tests/integration/routers/test_admin_qianchuan_review.py -v 2>&1 | tail -5
```

预期：404 或 ImportError

- [ ] **Step 3: 创建 admin_qianchuan_review.py**

```python
"""
app/routers/admin_qianchuan_review.py

管理端接口（admin 角色）：
  GET /api/admin/qianchuan-review/configs        — 配置列表
  PUT /api/admin/qianchuan-review/configs/{key}  — 更新配置
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.qianchuan_review import QianchuanReviewConfig
from app.models.user import User

router = APIRouter(prefix="/admin/qianchuan-review", tags=["admin-qianchuan-review"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(QianchuanReviewConfig))).scalars().all()
    return success_response(data=[
        {
            "id": c.id,
            "config_key": c.config_key,
            "ai_model_id": c.ai_model_id,
            "system_prompt": c.system_prompt,
            "is_active": c.is_active,
            "updated_at": _ts(c.updated_at),
        }
        for c in configs
    ])


@router.put("/configs/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        update(QianchuanReviewConfig)
        .where(QianchuanReviewConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(QianchuanReviewConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    await db.commit()
    return success_response(data={"config_key": config_key})
```

- [ ] **Step 4: 注册到 main.py**

在 `admin_tiktok_writer_router` import 之后追加：
```python
from app.routers.admin_qianchuan_review import router as admin_qianchuan_review_router
```

在 `app.include_router(admin_tiktok_writer_router, prefix="/api")` 之后追加：
```python
app.include_router(admin_qianchuan_review_router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认绿灯**

```bash
pytest tests/integration/routers/test_admin_qianchuan_review.py -v 2>&1 | tail -8
```

预期：`7 passed`

- [ ] **Step 6: 运行全量回归确认无回归**

```bash
pytest tests/unit/ tests/integration/ -q --no-header 2>&1 | tail -5
```

预期：全部 passed，0 failed

- [ ] **Step 7: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/routers/admin_qianchuan_review.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_admin_qianchuan_review.py
git commit -m "feat: add admin_qianchuan_review router (GET/PUT configs)"
```

---

## Task 6：operator_tiktok_writer — 从 DB 读 Prompt + 模型

**Files:**
- Modify: `backend/app/routers/operator_tiktok_writer.py`

> **背景：** tiktok-writer 的 `/chat` 接口当前接收前端传来的 `systemPrompt` 和 `model`。Step1（hook_eval）和 Step2（structure）改为后端从 DB 读取，但 Step3/Step4 的 `rewrite_*` 和 `iterate` Prompt 因含动态插值继续由前端构建传入。
>
> 实现方式：新增 `GET /api/tools/tiktok-writer/config` 接口，返回 `hook_eval` 和 `structure` 的 Prompt + 模型供前端在调用 `/chat` 时直接用；operator `/chat` 接口保持不变（仍接收前端传来的 systemPrompt）。这样最小改动，无需前端大重构。

- [ ] **Step 1: 先写单元测试（TDD 红灯）**

在现有集成测试文件（若有）或新建，确认 GET /config 接口：

在 `backend/tests/integration/routers/test_operator_tiktok_writer.py` 末尾追加（先读文件确认已有内容后追加）：

```python
class TestGetConfig:
    @pytest.mark.asyncio
    async def test_get_config_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/tiktok-writer/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_config_returns_prompts_and_model(self, test_client, operator_token, test_session):
        from sqlalchemy import text as sa_text
        await test_session.execute(sa_text(
            "INSERT INTO tiktok_writer_configs (config_key, system_prompt, is_active) "
            "VALUES ('hook_eval', 'Test Hook Prompt', true), "
            "('structure', 'Test Structure Prompt', true) "
            "ON CONFLICT (config_key) DO NOTHING"
        ))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/tiktok-writer/config",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "hook_eval_prompt" in data
        assert "structure_prompt" in data
        assert "model_id" in data
```

- [ ] **Step 2: 运行，确认红灯**

```bash
pytest tests/integration/routers/test_operator_tiktok_writer.py::TestGetConfig -v 2>&1 | tail -5
```

预期：404（接口未实现）

- [ ] **Step 3: 在 operator_tiktok_writer.py 新增 GET /config 接口**

在文件顶部 import 区追加：
```python
from app.models.tiktok_writer import TiktokWriterConfig
```

在 `DEFAULT_MODEL = "claude-opus-4-6-thinking"` 之后追加辅助函数：

```python
async def _get_config(key: str, db: AsyncSession) -> TiktokWriterConfig:
    """从 DB 读取激活的配置，不存在则抛 503。"""
    config = (await db.execute(
        select(TiktokWriterConfig)
        .where(TiktokWriterConfig.config_key == key)
        .where(TiktokWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"tiktok-writer 配置 '{key}' 未激活，请联系管理员"},
        )
    return config


async def _resolve_model(config: TiktokWriterConfig, db: AsyncSession) -> str:
    """解析配置绑定的模型 ID，无绑定则返回默认值。"""
    from sqlalchemy import text as sa_text
    if not config.ai_model_id:
        return DEFAULT_MODEL
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL
```

在 `router = APIRouter(...)` 之后，`require_operator` 函数之后，`/chat` 接口之前，新增：

```python
@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """返回 hook_eval 和 structure 的 Prompt + 模型，供前端调用 /chat 时使用。"""
    hook_cfg = await _get_config("hook_eval", db)
    struct_cfg = await _get_config("structure", db)
    # 两个配置共用同一个模型（取 hook_eval 的绑定模型）
    model_id = await _resolve_model(hook_cfg, db)
    return {
        "success": True,
        "data": {
            "hook_eval_prompt": hook_cfg.system_prompt or "",
            "structure_prompt": struct_cfg.system_prompt or "",
            "model_id": model_id,
        },
    }
```

- [ ] **Step 4: 运行测试，确认绿灯**

```bash
pytest tests/integration/routers/test_operator_tiktok_writer.py::TestGetConfig -v 2>&1 | tail -5
```

预期：`2 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/routers/operator_tiktok_writer.py \
        backend/tests/integration/routers/test_operator_tiktok_writer.py
git commit -m "feat: add GET /config endpoint to tiktok-writer (reads DB prompt+model)"
```

---

## Task 7：operator_qianchuan_review_service — 从 DB 读 Prompt + 模型

**Files:**
- Modify: `backend/app/services/qianchuan_review_service.py`
- Modify: `backend/app/routers/operator_qianchuan_review.py`

> **背景：** `generate_review_stream()` 当前硬编码使用 `PROMPT_WITH_EXCEL`/`PROMPT_WITHOUT_EXCEL` 和 `DEFAULT_MODEL = "claude-sonnet-4-6"`。改为接收调用方传入的 `system_prompt` 和 `model_id` 参数，由 router 层从 DB 读取后传入。

- [ ] **Step 1: 修改 qianchuan_review_service.py**

将 `generate_review_stream` 函数签名和实现从：

```python
async def generate_review_stream(
    items: list[dict],
    has_excel: bool,
    db: AsyncSession,
    user_id: int,
    task_id: int | None = None,
) -> AsyncGenerator[str, None]:
    system_prompt = PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL
    ...
    async for chunk in yunwu_adapter.chat_stream(
        messages=messages,
        db=db,
        model_id=DEFAULT_MODEL,
        ...
    ):
```

改为：

```python
async def generate_review_stream(
    items: list[dict],
    system_prompt: str,
    model_id: str,
    db: AsyncSession,
    user_id: int,
    task_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    调用 AI 流式生成复盘报告。
    system_prompt 和 model_id 由调用方从 DB 读取后传入（不再硬编码）。
    """
    # 移除原来的 system_prompt = PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL
    ...
    async for chunk in yunwu_adapter.chat_stream(
        messages=messages,
        db=db,
        model_id=model_id,
        ...
    ):
```

- [ ] **Step 2: 修改 operator_qianchuan_review.py 的 generate 接口**

在文件顶部 import 区追加：
```python
from app.models.qianchuan_review import QianchuanReviewConfig
```

在 `router = APIRouter(...)` 之后追加两个辅助函数：

```python
async def _get_qr_config(key: str, db: AsyncSession) -> QianchuanReviewConfig:
    config = (await db.execute(
        select(QianchuanReviewConfig)
        .where(QianchuanReviewConfig.config_key == key)
        .where(QianchuanReviewConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"qianchuan-review 配置 '{key}' 未激活，请联系管理员"},
        )
    return config


async def _resolve_qr_model(config: QianchuanReviewConfig, db: AsyncSession) -> str:
    from sqlalchemy import text as sa_text
    if not config.ai_model_id:
        return "claude-sonnet-4-6"
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else "claude-sonnet-4-6"
```

在 `generate` 接口的 `items = merge_scripts_and_excel(...)` 之后，调用 `generate_review_stream` 之前，读取 DB 配置：

```python
    # 从 DB 读取 Prompt + 模型
    config_key = "with_excel" if has_excel else "without_excel"
    qr_config = await _get_qr_config(config_key, db)
    system_prompt = qr_config.system_prompt or ""
    model_id = await _resolve_qr_model(qr_config, db)
```

并将 `generate_review_stream` 调用改为：

```python
                async for chunk in generate_review_stream(
                    items=items,
                    system_prompt=system_prompt,
                    model_id=model_id,
                    db=stream_db,
                    user_id=user_id,
                    task_id=task_id,
                ):
```

- [ ] **Step 3: 在集成测试中确保 generate 接口仍正常（seed 配置）**

在 `backend/tests/integration/routers/test_operator_qianchuan_review.py` 的 `TestGenerate.test_generate_returns_stream_and_task_id_header` 测试之前，追加 fixture（或在文件顶部追加）：

```python
@pytest.fixture(autouse=True)
async def seed_qr_configs(test_session):
    from sqlalchemy import text as sa_text
    for key, prompt in [('with_excel', 'Test Prompt With Excel'), ('without_excel', 'Test Prompt Without Excel')]:
        await test_session.execute(sa_text(
            "INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield
```

- [ ] **Step 4: 运行集成测试确认绿灯**

```bash
pytest tests/integration/routers/test_operator_qianchuan_review.py -v 2>&1 | tail -8
```

预期：全部 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/services/qianchuan_review_service.py \
        backend/app/routers/operator_qianchuan_review.py \
        backend/tests/integration/routers/test_operator_qianchuan_review.py
git commit -m "feat: qianchuan-review generate reads prompt+model from DB instead of hardcoded"
```

---

## Task 8：前端 — tiktok-writer 从后端拉 Prompt + 模型

**Files:**
- Modify: `frontend/src/api/tiktokWriter.ts`
- Modify: `frontend/src/pages/operator/TiktokWriterPage.tsx`

> **背景：** Step1（hook_eval）和 Step2（structure）的 Prompt 改为从 `GET /api/tools/tiktok-writer/config` 拉取。页面加载时请求一次并存入 state，后续调用 `/chat` 时直接使用。Step3/Step4 的动态 Prompt 保持原有前端构建逻辑。

- [ ] **Step 1: 在 tiktokWriter.ts 追加 getConfig API 函数**

在 `frontend/src/api/tiktokWriter.ts` 末尾追加：

```typescript
export interface TiktokWriterConfig {
  hook_eval_prompt: string;
  structure_prompt: string;
  model_id: string;
}

/** 从后端获取 hook_eval 和 structure 的 Prompt + 模型 */
export async function getTiktokWriterConfig(): Promise<TiktokWriterConfig> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-writer/config`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`获取配置失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}
```

- [ ] **Step 2: 修改 TiktokWriterPage.tsx 使用后端 Prompt**

**2a. 在文件顶部 import 中追加 `getTiktokWriterConfig` 和 `TiktokWriterConfig`：**

```typescript
import { chatStream, exportWord, getPersonas, getTiktokWriterConfig, type TiktokWriterConfig } from '../../api/tiktokWriter';
```

**2b. 在组件 state 中追加 toolConfig state（紧接其他 useState 之后）：**

```typescript
const [toolConfig, setToolConfig] = useState<TiktokWriterConfig | null>(null);
```

**2c. 在 `useEffect` 加载 personas 的地方同步加载 config（追加到现有 useEffect 或新增）：**

```typescript
useEffect(() => {
  getTiktokWriterConfig()
    .then(setToolConfig)
    .catch(() => {}); // 加载失败不阻断页面
}, []);
```

**2d. Step1 发起 hook_eval 调用时，从 `toolConfig` 取 Prompt 和模型：**

找到调用 `chatStream` 传 `systemPrompt: buildHookEvalPrompt()` 的地方，改为：

```typescript
const resp = await chatStream({
  messages: [{ role: 'user', content: state.transcript }],
  systemPrompt: toolConfig?.hook_eval_prompt ?? buildHookEvalPrompt(),
  model: toolConfig?.model_id,
  // ...其他字段不变
});
```

**2e. Step2 发起 structure 调用时，同样改为：**

```typescript
const resp = await chatStream({
  messages: [{ role: 'user', content: state.transcript }],
  systemPrompt: toolConfig?.structure_prompt ?? buildStructurePrompt(),
  model: toolConfig?.model_id,
  // ...其他字段不变
});
```

Step3/Step4 的 `buildRewritePrompt(...)` 和 `buildIteratePrompt(...)` 调用**保持不变**。

- [ ] **Step 3: 检查 TypeScript 编译**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend && npx tsc --noEmit 2>&1 | head -20
```

预期：0 错误

- [ ] **Step 4: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add frontend/src/api/tiktokWriter.ts \
        frontend/src/pages/operator/TiktokWriterPage.tsx
git commit -m "feat: tiktok-writer Step1/2 reads prompt+model from backend config"
```

---

## Task 9：前端管理 Tab — TiktokWriterConfigTab + QianchuanReviewConfigTab

**Files:**
- Create: `frontend/src/pages/admin/TiktokWriterConfigTab.tsx`
- Create: `frontend/src/pages/admin/QianchuanReviewConfigTab.tsx`
- Modify: `frontend/src/pages/admin/WorkspaceConfigPage.tsx`

- [ ] **Step 1: 创建 TiktokWriterConfigTab.tsx**

```typescript
// frontend/src/pages/admin/TiktokWriterConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { App } from 'antd';
import { get, put } from '../../api/request';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';

interface TiktokWriterConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}

const CONFIG_LABELS: Record<string, string> = {
  hook_eval: 'Opening Hook 评估',
  structure: '脚本结构分析',
};

export default function TiktokWriterConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<TiktokWriterConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<TiktokWriterConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mdResp] = await Promise.all([
        get<{ data: TiktokWriterConfig[] }>('/api/admin/tiktok-writer/configs'),
        getAiModels().catch(() => ({ items: [] as AiModelItem[], total: 0 })),
      ]);
      setConfigs((cfgResp as any)?.data ?? []);
      setModels(mdResp.items ?? []);
    } catch { message.error('加载配置失败'); }
    finally { setLoading(false); }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  function openEdit(cfg: TiktokWriterConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await put(`/api/admin/tiktok-writer/configs/${editingConfig.config_key}`, {
        ai_model_id: values.ai_model_id ?? null,
        system_prompt: values.system_prompt ?? null,
        is_active: true,
      });
      message.success('配置已保存');
      setEditingConfig(null);
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  if (loading) return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;

  return (
    <>
      <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--gray-500)' }}>
        仅 Step1（Hook 评估）和 Step2（结构分析）支持配置；Step3/4 的动态 Prompt 由前端构建。
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>}
        {configs.map(cfg => (
          <div key={cfg.config_key} className="card">
            <div className="card-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{CONFIG_LABELS[cfg.config_key] ?? cfg.config_key}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>config_key: {cfg.config_key}</div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => openEdit(cfg)}>编辑</button>
              </div>
              <div style={{ display: 'flex', gap: 20, fontSize: 13 }}>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>模型：</span>
                  <span style={{ color: cfg.ai_model_id ? 'var(--gray-800)' : 'var(--danger)' }}>
                    {cfg.ai_model_id
                      ? (models.find(m => m.id === cfg.ai_model_id)?.name ?? `ID:${cfg.ai_model_id}`)
                      : '⚠ 未配置（使用默认）'}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>Prompt：</span>
                  <span style={{ color: cfg.system_prompt ? 'var(--success)' : 'var(--warning)' }}>
                    {cfg.system_prompt ? `已设置（${cfg.system_prompt.length} 字）` : '未设置'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal
        title={editingConfig ? (CONFIG_LABELS[editingConfig.config_key] ?? editingConfig.config_key) : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnHidden
      >
        <Form form={configForm} layout="vertical" onFinish={saveConfig} style={{ marginTop: 16 }}>
          <Form.Item label="AI 模型" name="ai_model_id">
            <Select
              placeholder="选择已配置的 AI 模型（留空使用默认 claude-opus-4-6-thinking）"
              options={models.filter(m => m.status === 'active').map(m => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="系统 Prompt" name="system_prompt">
            <Input.TextArea rows={14} placeholder="输入系统 Prompt..." style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: 创建 QianchuanReviewConfigTab.tsx**

```typescript
// frontend/src/pages/admin/QianchuanReviewConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { App } from 'antd';
import { get, put } from '../../api/request';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';

interface QianchuanReviewConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}

const CONFIG_LABELS: Record<string, string> = {
  with_excel: '含投放数据复盘',
  without_excel: '仅脚本复盘',
};

export default function QianchuanReviewConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<QianchuanReviewConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<QianchuanReviewConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mdResp] = await Promise.all([
        get<{ data: QianchuanReviewConfig[] }>('/api/admin/qianchuan-review/configs'),
        getAiModels().catch(() => ({ items: [] as AiModelItem[], total: 0 })),
      ]);
      setConfigs((cfgResp as any)?.data ?? []);
      setModels(mdResp.items ?? []);
    } catch { message.error('加载配置失败'); }
    finally { setLoading(false); }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  function openEdit(cfg: QianchuanReviewConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await put(`/api/admin/qianchuan-review/configs/${editingConfig.config_key}`, {
        ai_model_id: values.ai_model_id ?? null,
        system_prompt: values.system_prompt ?? null,
        is_active: true,
      });
      message.success('配置已保存');
      setEditingConfig(null);
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  if (loading) return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>}
        {configs.map(cfg => (
          <div key={cfg.config_key} className="card">
            <div className="card-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{CONFIG_LABELS[cfg.config_key] ?? cfg.config_key}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>config_key: {cfg.config_key}</div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => openEdit(cfg)}>编辑</button>
              </div>
              <div style={{ display: 'flex', gap: 20, fontSize: 13 }}>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>模型：</span>
                  <span style={{ color: cfg.ai_model_id ? 'var(--gray-800)' : 'var(--danger)' }}>
                    {cfg.ai_model_id
                      ? (models.find(m => m.id === cfg.ai_model_id)?.name ?? `ID:${cfg.ai_model_id}`)
                      : '⚠ 未配置（使用默认）'}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>Prompt：</span>
                  <span style={{ color: cfg.system_prompt ? 'var(--success)' : 'var(--warning)' }}>
                    {cfg.system_prompt ? `已设置（${cfg.system_prompt.length} 字）` : '未设置'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal
        title={editingConfig ? (CONFIG_LABELS[editingConfig.config_key] ?? editingConfig.config_key) : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnHidden
      >
        <Form form={configForm} layout="vertical" onFinish={saveConfig} style={{ marginTop: 16 }}>
          <Form.Item label="AI 模型" name="ai_model_id">
            <Select
              placeholder="选择已配置的 AI 模型（留空使用默认 claude-sonnet-4-6）"
              options={models.filter(m => m.status === 'active').map(m => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="系统 Prompt" name="system_prompt">
            <Input.TextArea rows={14} placeholder="输入系统 Prompt..." style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

- [ ] **Step 3: 注册两个 Tab 到 WorkspaceConfigPage.tsx**

在文件顶部 import 区追加：
```typescript
import TiktokWriterConfigTab from './TiktokWriterConfigTab';
import QianchuanReviewConfigTab from './QianchuanReviewConfigTab';
```

在 `items` 数组的 `selling-point` Tab 之后追加：
```typescript
{ key: 'tiktok-writer', label: 'TikTok 脚本仿写', children: <TiktokWriterConfigTab /> },
{ key: 'qianchuan-review', label: '千川脚本复盘', children: <QianchuanReviewConfigTab /> },
```

- [ ] **Step 4: 检查 TypeScript 编译**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend && npx tsc --noEmit 2>&1 | head -20
```

预期：0 错误

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add frontend/src/pages/admin/TiktokWriterConfigTab.tsx \
        frontend/src/pages/admin/QianchuanReviewConfigTab.tsx \
        frontend/src/pages/admin/WorkspaceConfigPage.tsx
git commit -m "feat: add TiktokWriter and QianchuanReview admin config tabs"
```

---

## Task 10：功能测试 + 全量回归

- [ ] **Step 1: 后端全量回归**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/unit/ tests/integration/ -q --no-header 2>&1 | tail -5
```

预期：全部 passed，0 failed

- [ ] **Step 2: 前端 tsc 编译**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend && npx tsc --noEmit 2>&1
```

预期：0 错误

- [ ] **Step 3: 验证管理端 Tab 出现**

在浏览器访问 `http://localhost:5173/admin/workspace`，确认：
- 「TikTok 脚本仿写」Tab 出现，显示 `hook_eval` 和 `structure` 两张配置卡
- 「千川脚本复盘」Tab 出现，显示 `with_excel` 和 `without_excel` 两张配置卡
- 每张卡可点击「编辑」，弹出 Modal，可修改 Prompt 和模型

- [ ] **Step 4: 验证接口正常**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123456"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['access_token'])")

# tiktok-writer 配置接口
curl -s http://localhost:8000/api/admin/tiktok-writer/configs \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['success'], len(d['data']), 'configs')"

# qianchuan-review 配置接口
curl -s http://localhost:8000/api/admin/qianchuan-review/configs \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['success'], len(d['data']), 'configs')"

# tiktok-writer operator GET /config
curl -s http://localhost:8000/api/tools/tiktok-writer/config \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['success'], list(d['data'].keys()))"
```

预期：
```
True 2 configs
True 2 configs
True ['hook_eval_prompt', 'structure_prompt', 'model_id']
```
