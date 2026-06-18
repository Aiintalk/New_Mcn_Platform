# tiktok-review 迁移实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧架构 `tiktok-review-web` 迁移到新 MCN Platform，实现 TT内容复盘工具（两侧文案输入 + AI流式分析 + 产出中心 + 导出Word + 管理端Prompt配置）。

**Architecture:** 后端新增 SQLAlchemy 模型 + 两个路由文件（运营端/管理端）+ 数据库迁移；前端新增类型/API层/运营端页面/管理端Tab，全部沿用已迁工具模式（qianchuan-review / tiktok-writer）。

**Tech Stack:** Python 3.10 · FastAPI · SQLAlchemy asyncpg · pytest-asyncio · React 19 · TypeScript · Ant Design 5 · Vitest

---

## 文件清单

### 新建
| 文件 | 说明 |
|------|------|
| `backend/migrations/026_tiktok_review.sql` | 建表 + workspace_tools 注册 + 默认配置种子 |
| `backend/app/models/tiktok_review.py` | TiktokReviewConfig SQLAlchemy 模型 |
| `backend/app/routers/operator_tiktok_review.py` | 运营端 4 个接口 |
| `backend/app/routers/admin_tiktok_review.py` | 管理端 2 个接口 |
| `backend/tests/integration/routers/test_operator_tiktok_review.py` | 后端集成测试 |
| `frontend/src/types/tiktokReview.ts` | 前端类型定义 |
| `frontend/src/api/tiktokReview.ts` | 前端 API 层 |
| `frontend/src/pages/operator/TiktokReviewPage.tsx` | 运营端主页面 |
| `frontend/src/pages/admin/TiktokReviewConfigTab.tsx` | 管理端配置 Tab |
| `frontend/src/__tests__/unit/api/tiktokReview.test.ts` | 前端单元测试 |

### 修改
| 文件 | 改动 |
|------|------|
| `backend/app/models/__init__.py` | 追加 TiktokReviewConfig 导入 |
| `backend/app/main.py` | 注册两个新路由 |
| `backend/tests/conftest.py` | 追加 AsyncSessionLocal patch 路径 |
| `frontend/src/App.tsx` | 追加懒加载 import + Route |
| `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | 追加 TiktokReviewConfigTab |
| `backend/docs/base/MCN_M2_Base_API.md` | 追加 §20 tiktok-review 接口 |
| `backend/docs/base/MCN_M2_Base_Database.md` | 追加 §21 tiktok_review_configs 表 |

---

## Task 1: 数据库迁移

**Files:**
- Create: `backend/migrations/026_tiktok_review.sql`

- [ ] **Step 1: 创建迁移文件**

```sql
-- 026_tiktok_review.sql
-- tiktok-review 工具：配置表 + workspace_tools 注册 + 默认 Prompt

-- ============================================================
-- 表：tiktok_review_configs
-- ============================================================
CREATE TABLE IF NOT EXISTS tiktok_review_configs (
    id            SERIAL PRIMARY KEY,
    config_key    VARCHAR(50)  NOT NULL UNIQUE,
    ai_model_id   INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    system_prompt TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_tiktok_review_configs_updated ON tiktok_review_configs;
CREATE TRIGGER trg_tiktok_review_configs_updated
    BEFORE UPDATE ON tiktok_review_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- workspace_tools 注册
-- ============================================================
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'tiktok-review',
    'TT内容复盘',
    '内容创作',
    '上传/粘贴两条TikTok视频文案（原版爆款+仿写版），AI从7个维度对比分析差距，输出流式复盘报告，支持导出Word',
    'dev',
    '["AI生成","TikTok","复盘","内容分析","docx"]'::jsonb,
    16
)
ON CONFLICT (tool_code) DO NOTHING;

-- ============================================================
-- 默认配置（含旧工具 SYSTEM_PROMPT）
-- ============================================================
INSERT INTO tiktok_review_configs (config_key, system_prompt, is_active)
VALUES (
    'default',
    '你是一个TikTok爆款内容分析专家，精通短视频算法机制、内容策略和跨平台差异。

你的任务是对比分析两条TikTok视频——一条是爆款原版，一条是仿写版——找出仿写版没爆的原因，并给出具体可执行的改进建议。

请从以下7个维度进行**逐项对比分析**：

1. **开头钩子（前3秒）**：TikTok算法最看重的完播率起点。两版的开头设计有什么区别？哪个更有吸引力？
2. **人设/身份背书**：两个创作者的身份标签和可信度差异
3. **标题策略**：标题的点击欲望对比（TT的标题影响推荐）
4. **内容节奏**：语速、信息密度、停顿感、转场节奏
5. **视觉呈现**：场景、构图、画面信息量、产品展示方式
6. **情绪价值**：观众看完后得到了什么？有没有争议性/互动性？
7. **平台适配**：TT和ins的算法/用户偏好差异分析

**输出格式要求**：
- 每个维度先分析原版，再分析仿写版，最后给出对比结论
- 分析完7个维度后，输出「核心问题诊断」（3-5个最关键的问题）
- 最后输出「具体改进建议」（不要泛泛而谈，要具体到"下一条视频应该怎么改"）

用中文输出。',
    true
)
ON CONFLICT (config_key) DO NOTHING;
```

- [ ] **Step 2: 执行迁移**

```bash
cd backend
PGPASSWORD=admin123 psql -h localhost -p 5432 -U mcn_user -d mcn_m1 -f migrations/026_tiktok_review.sql
```

期望输出：`CREATE TABLE` / `CREATE TRIGGER` / `INSERT 0 1`（各两次）

- [ ] **Step 3: 验证迁移结果**

```bash
PGPASSWORD=admin123 psql -h localhost -p 5432 -U mcn_user -d mcn_m1 -c "\d tiktok_review_configs"
PGPASSWORD=admin123 psql -h localhost -p 5432 -U mcn_user -d mcn_m1 -c "SELECT tool_code, status FROM workspace_tools WHERE tool_code='tiktok-review';"
PGPASSWORD=admin123 psql -h localhost -p 5432 -U mcn_user -d mcn_m1 -c "SELECT config_key, is_active, length(system_prompt) FROM tiktok_review_configs;"
```

期望：表存在（7个字段）；workspace_tools 有 tiktok-review dev 记录；configs 有 default 行 system_prompt 长度 > 0。

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/026_tiktok_review.sql
git commit -m "feat(db): 026_tiktok_review - 配置表 + workspace_tools 注册 + 默认Prompt"
```

---

## Task 2: 后端模型 + 注册

**Files:**
- Create: `backend/app/models/tiktok_review.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 SQLAlchemy 模型**

`backend/app/models/tiktok_review.py`:

```python
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class TiktokReviewConfig(Base):
    """tiktok-review 工具配置（Prompt + 模型，管理端可配置）"""
    __tablename__ = "tiktok_review_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 2: 注册到 models/__init__.py**

在 `backend/app/models/__init__.py` 末尾 import 列表处追加：

在 `from app.models.qianchuan_collection import ...` 行**之后**添加：
```python
from app.models.tiktok_review import TiktokReviewConfig
```

在 `__all__` 列表末尾添加：
```python
    "TiktokReviewConfig",
```

- [ ] **Step 3: 验证模型可导入**

```bash
cd backend && source .venv/bin/activate
python -c "from app.models.tiktok_review import TiktokReviewConfig; print('OK', TiktokReviewConfig.__tablename__)"
```

期望输出：`OK tiktok_review_configs`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/tiktok_review.py backend/app/models/__init__.py
git commit -m "feat(model): TiktokReviewConfig 模型"
```

---

## Task 3: 后端运营端路由（含测试）

**Files:**
- Create: `backend/app/routers/operator_tiktok_review.py`
- Create: `backend/tests/integration/routers/test_operator_tiktok_review.py`

- [ ] **Step 1: 先写测试文件（TDD）**

`backend/tests/integration/routers/test_operator_tiktok_review.py`:

```python
"""Integration tests for operator_tiktok_review router."""
from unittest.mock import patch

import pytest
from sqlalchemy import text as sa_text


@pytest.fixture(autouse=True)
async def seed_tr_config(test_session):
    await test_session.execute(sa_text(
        "INSERT INTO tiktok_review_configs (config_key, system_prompt, is_active) "
        "VALUES ('default', 'Test Prompt', true) ON CONFLICT (config_key) DO NOTHING"
    ))
    await test_session.commit()
    yield


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "a", "original_likes": "1万",
                  "copycat_transcript": "b", "copycat_likes": "500"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "报告内容", "title": "TT复盘"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_outputs_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/tiktok-review/outputs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_word_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "报告内容"},
        )
        assert resp.status_code == 401


# ---------- generate ----------

class TestGenerate:
    @pytest.mark.asyncio
    async def test_both_empty_transcripts_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "   ", "original_likes": "",
                  "copycat_transcript": "", "copycat_likes": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_no_config_returns_503(self, test_client, operator_token, test_session):
        await test_session.execute(sa_text(
            "UPDATE tiktok_review_configs SET is_active = false WHERE config_key = 'default'"
        ))
        await test_session.commit()
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "原版文案", "original_likes": "1万",
                  "copycat_transcript": "仿写文案", "copycat_likes": "500"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == "CONFIG_NOT_FOUND"
        # 恢复
        await test_session.execute(sa_text(
            "UPDATE tiktok_review_configs SET is_active = true WHERE config_key = 'default'"
        ))
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_generate_streams_text(self, test_client, operator_token):
        async def fake_stream(*args, **kwargs):
            yield "复盘"
            yield "结果"

        with patch(
            "app.routers.operator_tiktok_review.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/tiktok-review/generate",
                json={"original_transcript": "原版文案", "original_likes": "1万",
                      "copycat_transcript": "仿写文案", "copycat_likes": "500"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "复盘" in resp.text
        assert "x-task-id" in resp.headers

    @pytest.mark.asyncio
    async def test_generate_only_one_side_ok(self, test_client, operator_token):
        """只填原版文案（仿写版为空）应允许生成。"""
        async def fake_stream(*args, **kwargs):
            yield "ok"

        with patch(
            "app.routers.operator_tiktok_review.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/tiktok-review/generate",
                json={"original_transcript": "原版文案", "original_likes": "1万",
                      "copycat_transcript": "", "copycat_likes": ""},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "  ", "title": "TT复盘"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_save_creates_output(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "这是完整的复盘报告", "title": "TT复盘_2026-06-18"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "output_id" in data["data"]
        assert isinstance(data["data"]["output_id"], int)


# ---------- outputs ----------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_returns_list(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_outputs_pagination(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs?page=1&size=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200


# ---------- export-word ----------

class TestExportWord:
    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "  "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_export_returns_docx(self, test_client, operator_token):
        import io
        from docx import Document
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "## 开头钩子\n**原版**：开门见山\n**仿写版**：略显平淡"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]
        doc = Document(io.BytesIO(resp.content))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "TT" in texts or "复盘" in texts

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "报告内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "TT" in cd or "tiktok" in cd.lower()
```

- [ ] **Step 2: 运行测试，确认全部 FAIL（路由尚未创建）**

```bash
cd backend && source .venv/bin/activate
pytest tests/integration/routers/test_operator_tiktok_review.py -v 2>&1 | tail -20
```

期望：全部 FAILED / ERROR（ImportError 或 404）

- [ ] **Step 3: 创建运营端路由**

`backend/app/routers/operator_tiktok_review.py`:

```python
"""
app/routers/operator_tiktok_review.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/tools/tiktok-review/generate   — SSE 流式生成复盘报告
  POST /api/tools/tiktok-review/save       — 保存报告到 outputs 表
  GET  /api/tools/tiktok-review/outputs    — 历史报告列表
  POST /api/tools/tiktok-review/export-word — 导出 Word 文档
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.task import TaskJob
from app.models.tiktok_review import TiktokReviewConfig
from app.models.user import User
from app.services import word_export

router = APIRouter(prefix="/tools/tiktok-review", tags=["tiktok-review"])

TOOL_CODE = "tiktok-review"
TOOL_NAME = "TT内容复盘"
DEFAULT_MODEL = "claude-opus-4-6-thinking"


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_tr_config(db: AsyncSession) -> TiktokReviewConfig:
    config = (await db.execute(
        select(TiktokReviewConfig)
        .where(TiktokReviewConfig.config_key == "default")
        .where(TiktokReviewConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": "tiktok-review 配置未激活，请联系管理员"},
        )
    return config


async def _resolve_model(config: TiktokReviewConfig, db: AsyncSession) -> str:
    if not config.ai_model_id:
        return DEFAULT_MODEL
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    original_transcript: str = ""
    original_likes: str = ""
    copycat_transcript: str = ""
    copycat_likes: str = ""


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """SSE 流式生成复盘报告。X-Task-Id header 供前端保存时使用。"""
    if not body.original_transcript.strip() and not body.copycat_transcript.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "至少需要一侧有文案内容才能分析"},
        )

    config = await _get_tr_config(db)
    system_prompt = config.system_prompt or ""
    model_id = await _resolve_model(config, db)

    user_message = (
        f"## 原版爆款\n"
        f"**点赞数**：{body.original_likes or '未知'}\n"
        f"**文案转录**：\n{body.original_transcript or '未提供'}\n\n"
        f"---\n\n"
        f"## 仿写版\n"
        f"**点赞数**：{body.copycat_likes or '未知'}\n"
        f"**文案转录**：\n{body.copycat_transcript or '未提供'}"
    )

    task_no = f"TR-{int(time.time() * 1000)}"
    task_job = TaskJob(
        task_no=task_no,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        status="processing",
        input_payload={
            "original_likes": body.original_likes,
            "copycat_likes": body.copycat_likes,
        },
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task_job)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_generate",
        target_type="task_job",
        target_id=None,
        detail={"original_likes": body.original_likes, "copycat_likes": body.copycat_likes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(task_job)
    task_id = task_job.id

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    user_id = current_user.id
    start_time = time.monotonic()

    async def generate_stream():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    user_id=user_id,
                    feature="tiktok_review_generate",
                    max_tokens=8192,
                ):
                    yield chunk
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def update_task_status():
        duration_ms = int((time.monotonic() - start_time) * 1000)
        async with AsyncSessionLocal() as bg_db:
            job = await bg_db.get(TaskJob, task_id)
            if job:
                job.status = "success"
                job.finished_at = datetime.now(timezone.utc)
                job.duration_ms = duration_ms
                await bg_db.commit()

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Task-Id": str(task_id)},
        background=BackgroundTask(update_task_status),
    )


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------

class SaveRequest(BaseModel):
    content: str
    title: str = "TT内容复盘报告"
    task_id: int | None = None


@router.post("/save")
async def save_report(
    body: SaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存报告到 outputs 表。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    output = Output(
        title=body.title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        task_id=body.task_id,
        content=body.content,
        word_count=len(body.content),
        created_by=current_user.id,
    )
    db.add(output)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_save",
        target_type="output",
        target_id=None,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(output)

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def get_outputs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """operator 只看自己的；admin 看全部。"""
    query = (
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
    )
    if current_user.role == "operator":
        query = query.where(Output.created_by == current_user.id)

    all_rows = (
        await db.execute(query.order_by(Output.created_at.desc()))
    ).scalars().all()
    total = len(all_rows)

    start = (page - 1) * size
    rows = all_rows[start: start + size]

    items = [
        {
            "id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "preview": (r.content or "")[:100],
            "word_count": r.word_count,
        }
        for r in rows
    ]

    return success_response(data={"items": items, "total": total})


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    title: str = "TT内容复盘报告"


@router.post("/export-word")
async def export_word_doc(
    body: ExportWordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成 Word 文档并返回 docx 二进制流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    metadata = [f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=body.title,
        metadata_lines=metadata,
        content=body.content,
    )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_export_word",
        target_type="output",
        target_id=None,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    filename = f"TT复盘报告_{date_str}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: 注册路由到 main.py**

在 `backend/app/main.py` 中，找到其他 operator 路由的 include 行，在其后追加：

```python
from app.routers import operator_tiktok_review
app.include_router(operator_tiktok_review.router, prefix="/api")
```

- [ ] **Step 5: 注册 AsyncSessionLocal patch 到 conftest.py**

在 `backend/tests/conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS` 列表末尾追加：

```python
    "app.routers.operator_tiktok_review.AsyncSessionLocal",
```

- [ ] **Step 6: 运行测试，确认全部 PASS**

```bash
cd backend && source .venv/bin/activate
pytest tests/integration/routers/test_operator_tiktok_review.py -v
```

期望：全部 PASSED

- [ ] **Step 7: 检查覆盖率**

```bash
pytest tests/integration/routers/test_operator_tiktok_review.py \
  --cov=app/routers/operator_tiktok_review \
  --cov-report=term-missing
```

期望：覆盖率 ≥ 70%

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/operator_tiktok_review.py \
        backend/tests/integration/routers/test_operator_tiktok_review.py \
        backend/app/main.py \
        backend/tests/conftest.py
git commit -m "feat(backend): operator_tiktok_review 路由 + 集成测试"
```

---

## Task 4: 后端管理端路由

**Files:**
- Create: `backend/app/routers/admin_tiktok_review.py`

- [ ] **Step 1: 创建管理端路由**

`backend/app/routers/admin_tiktok_review.py`:

```python
"""
app/routers/admin_tiktok_review.py

管理端接口（admin 角色）：
  GET  /api/admin/tiktok-review/configs           — 配置列表
  PUT  /api/admin/tiktok-review/configs/{key}     — 更新配置（Prompt / 模型）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.tiktok_review import TiktokReviewConfig
from app.models.user import User

router = APIRouter(prefix="/admin/tiktok-review", tags=["admin-tiktok-review"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(TiktokReviewConfig))).scalars().all()
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        update(TiktokReviewConfig)
        .where(TiktokReviewConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(TiktokReviewConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="update_tiktok_review_config",
        target_type="config",
        target_id=None,
        detail={"config_key": config_key, "ai_model_id": body.ai_model_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": config_key})
```

- [ ] **Step 2: 注册管理端路由到 main.py**

在 `backend/app/main.py` 中，找到 `operator_tiktok_review` 的 include 行后追加：

```python
from app.routers import admin_tiktok_review
app.include_router(admin_tiktok_review.router, prefix="/api")
```

- [ ] **Step 3: 快速验证管理端路由可访问**

```bash
cd backend && source .venv/bin/activate
python -c "
import asyncio
from app.main import app
routes = [r.path for r in app.routes]
assert any('admin/tiktok-review' in r for r in routes), 'admin route missing'
print('OK - routes registered')
"
```

期望：`OK - routes registered`

- [ ] **Step 4: 运行全量后端测试，确认无回归**

```bash
cd backend && source .venv/bin/activate
pytest tests/integration/ -v --tb=short 2>&1 | tail -30
```

期望：所有原有测试 PASSED，无新增失败

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_tiktok_review.py backend/app/main.py
git commit -m "feat(backend): admin_tiktok_review 路由"
```

---

## Task 5: 前端类型 + API 层（含测试）

**Files:**
- Create: `frontend/src/types/tiktokReview.ts`
- Create: `frontend/src/api/tiktokReview.ts`
- Create: `frontend/src/__tests__/unit/api/tiktokReview.test.ts`

- [ ] **Step 1: 创建类型文件**

`frontend/src/types/tiktokReview.ts`:

```typescript
export interface VideoSide {
  file: File | null;
  transcript: string;
  likes: string;
}

export interface TiktokReviewOutput {
  id: number;
  title: string;
  created_at: string | null;
  preview: string;
  word_count: number | null;
}

export interface TiktokReviewConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}

export interface GenerateRequest {
  original_transcript: string;
  original_likes: string;
  copycat_transcript: string;
  copycat_likes: string;
}

export interface SaveRequest {
  content: string;
  title?: string;
  task_id?: number | null;
}

export interface OutputsResponse {
  items: TiktokReviewOutput[];
  total: number;
}
```

- [ ] **Step 2: 创建 API 层**

`frontend/src/api/tiktokReview.ts`:

```typescript
import { get, post, put } from './request';
import { useAuthStore } from '../store/authStore';
import type {
  GenerateRequest,
  SaveRequest,
  TiktokReviewConfig,
  TiktokReviewOutput,
  OutputsResponse,
} from '../types/tiktokReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** SSE 流式生成复盘报告，返回原始 Response，由调用方读取 body stream */
export async function generateStream(body: GenerateRequest): Promise<Response> {
  const token = useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/tiktok-review/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** 保存报告到产出中心 */
export async function saveReport(body: SaveRequest): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/tiktok-review/save', body);
}

/** 获取历史报告列表 */
export async function getOutputs(page = 1, size = 10): Promise<OutputsResponse> {
  return get<OutputsResponse>('/api/tools/tiktok-review/outputs', { page, size });
}

/** 导出 Word，返回 Blob */
export async function exportWord(content: string, title?: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-review/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, title: title ?? 'TT内容复盘报告' }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `Export failed: ${resp.status}`);
  }
  return resp.blob();
}

/** 管理端：获取配置列表 */
export async function getAdminConfigs(): Promise<TiktokReviewConfig[]> {
  return get<TiktokReviewConfig[]>('/api/admin/tiktok-review/configs');
}

/** 管理端：更新配置 */
export async function updateAdminConfig(
  configKey: string,
  data: { ai_model_id: number | null; system_prompt: string | null; is_active: boolean }
): Promise<{ config_key: string }> {
  return put<{ config_key: string }>(`/api/admin/tiktok-review/configs/${configKey}`, data);
}
```

- [ ] **Step 3: 先写前端单元测试**

`frontend/src/__tests__/unit/api/tiktokReview.test.ts`:

```typescript
/**
 * Unit tests for src/api/tiktokReview.ts
 * Mock fetch/request，不发真实请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as requestModule from '../../../api/request';

vi.mock('../../../api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('tiktokReview API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('saveReport', () => {
    it('calls POST /api/tools/tiktok-review/save with correct body', async () => {
      const { saveReport } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.post).mockResolvedValue({ output_id: 42 });
      const result = await saveReport({ content: '报告内容', title: 'TT复盘' });
      expect(requestModule.post).toHaveBeenCalledWith(
        '/api/tools/tiktok-review/save',
        { content: '报告内容', title: 'TT复盘' }
      );
      expect(result.output_id).toBe(42);
    });

    it('throws when post fails', async () => {
      const { saveReport } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.post).mockRejectedValue(new Error('保存失败'));
      await expect(saveReport({ content: '内容' })).rejects.toThrow('保存失败');
    });
  });

  describe('getOutputs', () => {
    it('calls GET /api/tools/tiktok-review/outputs with pagination', async () => {
      const { getOutputs } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.get).mockResolvedValue({ items: [], total: 0 });
      await getOutputs(2, 5);
      expect(requestModule.get).toHaveBeenCalledWith(
        '/api/tools/tiktok-review/outputs',
        { page: 2, size: 5 }
      );
    });
  });

  describe('exportWord', () => {
    it('calls POST /api/tools/tiktok-review/export-word with correct headers', async () => {
      const { exportWord } = await import('../../../api/tiktokReview');
      const mockBlob = new Blob(['fake docx']);
      mockFetch.mockResolvedValue(new Response(mockBlob, { status: 200 }));
      await exportWord('报告内容', 'TT复盘报告');
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-review/export-word'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        })
      );
    });

    it('throws when export fails', async () => {
      const { exportWord } = await import('../../../api/tiktokReview');
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: { message: '导出失败' } }), { status: 500 })
      );
      await expect(exportWord('内容')).rejects.toThrow('导出失败');
    });
  });

  describe('getAdminConfigs', () => {
    it('calls GET /api/admin/tiktok-review/configs', async () => {
      const { getAdminConfigs } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.get).mockResolvedValue([]);
      await getAdminConfigs();
      expect(requestModule.get).toHaveBeenCalledWith('/api/admin/tiktok-review/configs');
    });
  });

  describe('updateAdminConfig', () => {
    it('calls PUT /api/admin/tiktok-review/configs/:key', async () => {
      const { updateAdminConfig } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.put).mockResolvedValue({ config_key: 'default' });
      await updateAdminConfig('default', {
        ai_model_id: null,
        system_prompt: 'New prompt',
        is_active: true,
      });
      expect(requestModule.put).toHaveBeenCalledWith(
        '/api/admin/tiktok-review/configs/default',
        { ai_model_id: null, system_prompt: 'New prompt', is_active: true }
      );
    });
  });

  describe('generateStream', () => {
    it('calls POST /api/tools/tiktok-review/generate with auth header', async () => {
      const { generateStream } = await import('../../../api/tiktokReview');
      mockFetch.mockResolvedValue(new Response('stream', { status: 200 }));
      await generateStream({
        original_transcript: '原版',
        original_likes: '1万',
        copycat_transcript: '仿写',
        copycat_likes: '500',
      });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-review/generate'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        })
      );
    });
  });
});
```

- [ ] **Step 4: 运行前端测试**

```bash
cd frontend
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 20
npx vitest run src/__tests__/unit/api/tiktokReview.test.ts
```

期望：6 个测试全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/tiktokReview.ts \
        frontend/src/api/tiktokReview.ts \
        frontend/src/__tests__/unit/api/tiktokReview.test.ts
git commit -m "feat(frontend): tiktokReview 类型 + API 层 + 单元测试"
```

---

## Task 6: 前端运营端页面

**Files:**
- Create: `frontend/src/pages/operator/TiktokReviewPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 创建运营端页面**

`frontend/src/pages/operator/TiktokReviewPage.tsx`:

```tsx
// frontend/src/pages/operator/TiktokReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import { App } from 'antd';
import { useAuthStore } from '../../store/authStore';
import { generateStream, saveReport, exportWord } from '../../api/tiktokReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/* ── Markdown 渲染 ── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 style="font-size:14px;font-weight:600;margin:16px 0 8px">$1</h3>')
    .replace(/## (.+)/g, '<h2 style="font-size:16px;font-weight:600;margin:20px 0 8px">$1</h2>')
    .replace(/# (.+)/g, '<h1 style="font-size:18px;font-weight:700;margin:24px 0 10px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--gray-800)' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

interface VideoSide {
  file: File | null;
  transcript: string;
  likes: string;
}

const EMPTY_SIDE: VideoSide = { file: null, transcript: '', likes: '' };

/* ── 单侧输入面板 ── */
function SidePanel({
  side,
  data,
  onChange,
  transcribing,
  onTranscribe,
}: {
  side: 'original' | 'copycat';
  data: VideoSide;
  onChange: (patch: Partial<VideoSide>) => void;
  transcribing: boolean;
  onTranscribe: () => void;
}) {
  const label = side === 'original' ? '原版爆款' : '仿写版';
  const borderColor = side === 'original' ? '#d1fae5' : '#bfdbfe';
  const dotColor = side === 'original' ? '#10b981' : '#3b82f6';
  const titleColor = side === 'original' ? '#065f46' : '#1e40af';

  function handleFileDrop(file: File | null) {
    onChange({ file });
  }

  return (
    <div style={{
      flex: 1, border: `2px solid ${borderColor}`, borderRadius: 12,
      padding: 20, background: '#fff', minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 16, color: titleColor }}>{label}</span>
      </div>

      {/* 视频上传 */}
      <div
        style={{
          border: '2px dashed #e5e7eb', borderRadius: 8, padding: 16,
          textAlign: 'center', cursor: 'pointer', marginBottom: 8,
          background: '#fafafa',
        }}
        onClick={() => document.getElementById(`file-${side}`)?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault();
          const f = e.dataTransfer.files[0];
          if (f && f.type.startsWith('video/')) handleFileDrop(f);
        }}
      >
        <input
          id={`file-${side}`}
          type="file"
          accept="video/*"
          style={{ display: 'none' }}
          onChange={e => handleFileDrop(e.target.files?.[0] || null)}
        />
        {data.file ? (
          <div style={{ fontSize: 13, color: '#374151' }}>
            {data.file.name}
            <span style={{ color: '#9ca3af', marginLeft: 6 }}>
              ({(data.file.size / 1024 / 1024).toFixed(1)}MB)
            </span>
            <button
              style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#f87171' }}
              onClick={e => { e.stopPropagation(); handleFileDrop(null); }}
            >✕</button>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#9ca3af' }}>上传视频自动转文案（最大25MB）</div>
        )}
      </div>

      {data.file && (
        <button
          disabled={transcribing}
          onClick={onTranscribe}
          style={{
            width: '100%', padding: '8px 0', borderRadius: 8, border: 'none',
            background: transcribing ? '#9ca3af' : '#7c3aed', color: '#fff',
            fontSize: 13, fontWeight: 600, cursor: transcribing ? 'not-allowed' : 'pointer',
            marginBottom: 8,
          }}
        >
          {transcribing ? '转录中...' : '转文案'}
        </button>
      )}

      {/* 文案文本框 */}
      <textarea
        style={{
          width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb',
          borderRadius: 8, fontSize: 13, height: 112, resize: 'vertical',
          outline: 'none', boxSizing: 'border-box', marginBottom: 8,
        }}
        placeholder="上传视频自动转录，或直接粘贴文案..."
        value={data.transcript}
        onChange={e => onChange({ transcript: e.target.value })}
      />

      {/* 点赞数 */}
      <input
        type="text"
        style={{
          width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb',
          borderRadius: 8, fontSize: 13, outline: 'none', boxSizing: 'border-box',
        }}
        placeholder="点赞数（如 16万）"
        value={data.likes}
        onChange={e => onChange({ likes: e.target.value })}
      />
    </div>
  );
}

/* ── 主页面 ── */
export default function TiktokReviewPage() {
  const { message } = App.useApp();
  const [original, setOriginal] = useState<VideoSide>({ ...EMPTY_SIDE });
  const [copycat, setCopycat] = useState<VideoSide>({ ...EMPTY_SIDE });
  const [transcribing, setTranscribing] = useState<'original' | 'copycat' | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState('');
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  async function handleTranscribe(side: 'original' | 'copycat') {
    const data = side === 'original' ? original : copycat;
    if (!data.file) return;
    setTranscribing(side);
    try {
      const token = useAuthStore.getState().token;
      const form = new FormData();
      form.append('file', data.file);
      form.append('language', 'ko');
      const resp = await fetch(`${BASE_URL}/api/tools/transcribe`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json?.detail?.message ?? '转录失败');
      const text = json?.data?.text ?? '';
      if (side === 'original') setOriginal(prev => ({ ...prev, transcript: text }));
      else setCopycat(prev => ({ ...prev, transcript: text }));
    } catch (e) {
      message.error(e instanceof Error ? e.message : '转录出错');
    } finally {
      setTranscribing(null);
    }
  }

  const handleAnalyze = useCallback(async () => {
    if (!original.transcript.trim() && !copycat.transcript.trim()) {
      message.warning('至少需要一侧有文案内容才能分析');
      return;
    }
    setAnalyzing(true);
    setReport('');
    setTaskId(null);
    try {
      const resp = await generateStream({
        original_transcript: original.transcript,
        original_likes: original.likes,
        copycat_transcript: copycat.transcript,
        copycat_likes: copycat.likes,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.detail?.message ?? `分析请求失败: ${resp.status}`);
      }

      const tid = resp.headers.get('x-task-id');
      if (tid) setTaskId(Number(tid));

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');
      const decoder = new TextDecoder();
      let fullText = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
        setReport(fullText);
      }
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '分析出错');
    } finally {
      setAnalyzing(false);
    }
  }, [original, copycat, message]);

  async function handleSave() {
    if (!report) return;
    setSaving(true);
    try {
      const date = new Date().toISOString().slice(0, 10);
      await saveReport({
        content: report,
        title: `TT复盘报告_${date}`,
        task_id: taskId,
      });
      message.success('报告已保存到产出中心');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    if (!report) return;
    setExporting(true);
    try {
      const date = new Date().toISOString().slice(0, 10);
      const blob = await exportWord(report, `TT复盘报告_${date}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `TT复盘报告_${date}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '32px 16px' }}>
      {/* 标题 */}
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1f2937', margin: 0 }}>TT内容复盘</h1>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 6 }}>
          上传/粘贴两条视频文案，AI找出差距
        </p>
      </div>

      {/* 两栏输入 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <SidePanel
            side="original"
            data={original}
            onChange={patch => setOriginal(prev => ({ ...prev, ...patch }))}
            transcribing={transcribing === 'original'}
            onTranscribe={() => handleTranscribe('original')}
          />
          <SidePanel
            side="copycat"
            data={copycat}
            onChange={patch => setCopycat(prev => ({ ...prev, ...patch }))}
            transcribing={transcribing === 'copycat'}
            onTranscribe={() => handleTranscribe('copycat')}
          />
        </div>
      </div>

      {/* 开始复盘按钮 */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <button
          disabled={analyzing}
          onClick={handleAnalyze}
          style={{
            padding: '12px 32px', borderRadius: 12, border: 'none',
            background: analyzing
              ? '#9ca3af'
              : 'linear-gradient(to right, #7c3aed, #2563eb)',
            color: '#fff', fontSize: 15, fontWeight: 700,
            cursor: analyzing ? 'not-allowed' : 'pointer',
            boxShadow: analyzing ? 'none' : '0 4px 12px rgba(124,58,237,0.3)',
          }}
        >
          {analyzing ? '正在分析...' : '开始复盘'}
        </button>
      </div>

      {/* 复盘报告 */}
      {report && (
        <div
          ref={reportRef}
          style={{
            background: '#fff', border: '1px solid #e5e7eb',
            borderRadius: 12, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1f2937', margin: 0 }}>复盘报告</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                disabled={saving}
                onClick={handleSave}
                style={{
                  padding: '6px 16px', borderRadius: 8, border: 'none',
                  background: saving ? '#9ca3af' : '#2563eb', color: '#fff',
                  fontSize: 13, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? '保存中...' : '保存'}
              </button>
              <button
                disabled={exporting}
                onClick={handleExport}
                style={{
                  padding: '6px 16px', borderRadius: 8, border: 'none',
                  background: exporting ? '#9ca3af' : '#059669', color: '#fff',
                  fontSize: 13, fontWeight: 600, cursor: exporting ? 'not-allowed' : 'pointer',
                }}
              >
                {exporting ? '导出中...' : '导出 Word'}
              </button>
            </div>
          </div>
          <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 16 }}>
            <SimpleMarkdown text={report} />
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 注册路由到 App.tsx**

在 `frontend/src/App.tsx` 中：

在懒加载 import 块（`const QianchuanCollectionPage = lazy(...)` 行之后）追加：
```typescript
const TiktokReviewPage = lazy(() => import('./pages/operator/TiktokReviewPage'));
```

注意：文件顶部已有 `TiktokWriterPage` 的 lazy import，新 `TiktokReviewPage` 要另起一行，不要混淆。

在运营端 Routes 中（`/workspace/tiktok-writer` 路由之后）追加：
```tsx
<Route path="/workspace/tiktok-review" element={<TiktokReviewPage />} />
```

- [ ] **Step 3: 验证前端编译无报错**

```bash
cd frontend
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 20
npx tsc --noEmit 2>&1 | head -20
```

期望：无 TypeScript 错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/operator/TiktokReviewPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): TiktokReviewPage 运营端页面 + 路由注册"
```

---

## Task 7: 前端管理端 Tab

**Files:**
- Create: `frontend/src/pages/admin/TiktokReviewConfigTab.tsx`
- Modify: `frontend/src/pages/admin/WorkspaceConfigPage.tsx`

- [ ] **Step 1: 创建管理端 Tab 组件**

`frontend/src/pages/admin/TiktokReviewConfigTab.tsx`:

```tsx
// frontend/src/pages/admin/TiktokReviewConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { App } from 'antd';
import { getAdminConfigs, updateAdminConfig } from '../../api/tiktokReview';
import { getAiModels } from '../../api/ai';
import type { TiktokReviewConfig } from '../../types/tiktokReview';
import type { AiModelItem } from '../../api/ai';

export default function TiktokReviewConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<TiktokReviewConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<TiktokReviewConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mdResp] = await Promise.all([
        getAdminConfigs(),
        getAiModels().catch(() => ({ items: [] as AiModelItem[], total: 0 })),
      ]);
      setConfigs(Array.isArray(cfgResp) ? cfgResp : []);
      setModels(mdResp.items ?? []);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  function openEdit(cfg: TiktokReviewConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await updateAdminConfig(editingConfig.config_key, {
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
        {configs.length === 0 && (
          <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>
        )}
        {configs.map(cfg => (
          <div key={cfg.config_key} className="card">
            <div className="card-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>TT内容复盘 · {cfg.config_key}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>
                    config_key: {cfg.config_key}
                  </div>
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
        title={editingConfig ? `TT内容复盘 · ${editingConfig.config_key}` : ''}
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
            <Input.TextArea
              rows={14}
              placeholder="输入系统 Prompt..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
```

- [ ] **Step 2: 注册 Tab 到 WorkspaceConfigPage.tsx**

在 `frontend/src/pages/admin/WorkspaceConfigPage.tsx` 中：

在 import 区（`import QianchuanPreviewConfigTab` 行之后）追加：
```typescript
import TiktokReviewConfigTab from './TiktokReviewConfigTab';
```

在 `items` 数组（`{ key: 'qianchuan-preview', ... }` 行之后）追加：
```tsx
{ key: 'tiktok-review', label: 'TT内容复盘', children: <TiktokReviewConfigTab /> },
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 20
npx tsc --noEmit 2>&1 | head -20
```

期望：无 TypeScript 错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/admin/TiktokReviewConfigTab.tsx \
        frontend/src/pages/admin/WorkspaceConfigPage.tsx
git commit -m "feat(frontend): TiktokReviewConfigTab 管理端配置 Tab"
```

---

## Task 8: 契约文档更新

**Files:**
- Modify: `backend/docs/base/MCN_M2_Base_API.md`
- Modify: `backend/docs/base/MCN_M2_Base_Database.md`

- [ ] **Step 1: 追加 Base_API §20**

在 `backend/docs/base/MCN_M2_Base_API.md` 末尾追加：

```markdown
---

## 20. tiktok-review（Sprint 13）

基础路径：`/api/tools/tiktok-review`（operator/admin 鉴权）
管理端路径：`/api/admin/tiktok-review`（admin 鉴权）

### 20.1 POST /generate

SSE 流式生成复盘报告。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `original_transcript` | string | 原版爆款文案（与 copycat_transcript 至少一个非空） |
| `original_likes` | string | 原版点赞数（可选，如"1万"） |
| `copycat_transcript` | string | 仿写版文案 |
| `copycat_likes` | string | 仿写版点赞数 |

Response：`text/plain; charset=utf-8`（裸文本流）

Response Header：`X-Task-Id: <task_id>`（供保存时使用）

错误：两侧文案均为空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND

### 20.2 POST /save

保存报告到 outputs 表。

Request（JSON）：`{ "content": "报告正文", "title": "TT复盘报告_2026-06-18", "task_id": 123 }`

Response（200）：`{ "success": true, "code": "OK", "data": { "output_id": 456 } }`

错误：content 为空 → 400 INVALID_INPUT

### 20.3 GET /outputs

历史报告列表。

Query 参数：`page`（默认1）、`size`（默认10，最大100）

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "items": [{ "id": 1, "title": "TT复盘报告_2026-06-18", "created_at": "...", "preview": "...", "word_count": 800 }],
    "total": 5
  }
}
```

operator 只看自己的；admin 看全部。

### 20.4 POST /export-word

导出 Word。

Request（JSON）：`{ "content": "报告正文", "title": "TT复盘报告" }`

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`（docx 二进制）

错误：content 为空 → 400 INVALID_INPUT

### 20.5 GET /admin/configs

获取配置列表（admin）。

Response（200）：`{ "success": true, "data": [{ "id": 1, "config_key": "default", "ai_model_id": null, "system_prompt": "...", "is_active": true, "updated_at": "..." }] }`

### 20.6 PUT /admin/configs/{config_key}

更新配置（admin）。

Request（JSON）：`{ "ai_model_id": 2, "system_prompt": "新 Prompt", "is_active": true }`

Response（200）：`{ "success": true, "data": { "config_key": "default" } }`

错误：config_key 不存在 → 404 RESOURCE_NOT_FOUND
```

- [ ] **Step 2: 追加 Base_Database §21**

在 `backend/docs/base/MCN_M2_Base_Database.md` 末尾追加：

```markdown
---

## 21. tiktok_review_configs（Sprint 13）

**迁移文件**：`026_tiktok_review.sql`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 主键 |
| `config_key` | VARCHAR(50) UNIQUE | 是 | 配置标识，当前只有 `default` |
| `ai_model_id` | INTEGER | 否 | 关联 ai_models.id，NULL 时使用默认模型 |
| `system_prompt` | TEXT | 否 | 系统 Prompt |
| `is_active` | BOOLEAN | 是 | 是否激活，默认 true |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动） |

**触发器**：`trg_tiktok_review_configs_updated`（自动更新 updated_at）

### 21.1 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `tiktok-review` | TT内容复盘 | 内容创作 | `dev` | 16 |
```

- [ ] **Step 3: Commit**

```bash
git add backend/docs/base/MCN_M2_Base_API.md backend/docs/base/MCN_M2_Base_Database.md
git commit -m "docs: Base_API §20 + Base_Database §21 tiktok-review 接口和表说明"
```

---

## Task 9: 全量验证

- [ ] **Step 1: 运行全量后端集成测试**

```bash
cd backend && source .venv/bin/activate
pytest tests/integration/ -v --tb=short 2>&1 | tail -30
```

期望：所有测试 PASSED，无新增失败

- [ ] **Step 2: 运行覆盖率门禁**

```bash
cd backend && source .venv/bin/activate
python scripts/run_coverage.py --gate 2>&1 | tail -20
```

期望：所有层通过门禁（不低于各层目标值）

- [ ] **Step 3: 运行全量前端单元测试**

```bash
cd frontend
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 20
npx vitest run --coverage 2>&1 | tail -20
```

期望：所有测试 PASSED

- [ ] **Step 4: 手动冒烟测试（前端已启动的情况下）**

验证以下流程：
1. 访问 http://localhost:5173/workspace/tiktok-review — 页面正常加载
2. 在原版爆款文本框粘贴任意文案，点「开始复盘」— SSE 流式报告逐字出现
3. 点「保存」— Toast 提示"报告已保存到产出中心"
4. 点「导出 Word」— 浏览器触发 .docx 文件下载
5. 访问 http://localhost:5173/admin/workspace，切到「TT内容复盘」Tab — 配置页面正常显示

- [ ] **Step 5: 迁移检查清单复核**

逐项确认：
- [x] 迁移红线 1：入口在 `/workspace/tiktok-review`（创作中心下）
- [x] 迁移红线 2：报告 save 接入 outputs 表（产出中心）
- [x] 迁移红线 3：AI 走 yunwu_adapter，不自直连
- [x] 迁移红线 4：Prompt + 模型在 WorkspaceConfigPage 管理端可配
- [x] 迁移红线 5：workspace_tools 注册（status=dev，管理端可改为 online）
- [x] 迁移红线 6：AI 调用走 yunwu_adapter.chat_stream（内部写 ai_call_logs）
- [x] 契约文档：Base_API §20 + Base_Database §21 已更新

- [ ] **Step 6: 最终 Commit（如有遗漏文件）**

```bash
git status
# 确认无意外未提交文件后执行：
git commit -m "chore: tiktok-review Sprint 13 全量验证通过" --allow-empty
```

---

## Task 10: 文档落地 + PM 记忆更新

**Files:**
- Modify: `backend/docs/README.md`
- Modify: `docs/pm/PM_记忆与状态_M2.md`

- [ ] **Step 1: 更新后端 README**

在 `backend/docs/README.md` 的「工具列表」或相应章节追加 tiktok-review 条目：

```
| tiktok-review | TT内容复盘 | operator_tiktok_review.py / admin_tiktok_review.py | Sprint 13 |
```

- [ ] **Step 2: 更新 PM 记忆与状态**

在 `docs/pm/PM_记忆与状态_M2.md` 中，在 Sprint 12 完成记录之后追加 Sprint 13 完成块：

```markdown
### M2 Sprint 13 — TT内容复盘（tiktok-review）✅ 完成

**核心定位**：迁移旧工具，两侧视频文案对比 + AI 7维度分析 + 产出中心 + 导出Word + 管理端Prompt配置。

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 026 | ✅ 已执行 | `tiktok_review_configs` 表 + workspace_tools 注册（status=dev）+ 默认Prompt |
| 后端运营端 4 个接口 | ✅ 完成 | `operator_tiktok_review.py`（generate/save/outputs/export-word） |
| 后端管理端 2 个接口 | ✅ 完成 | `admin_tiktok_review.py`（configs GET/PUT） |
| SQLAlchemy 模型 | ✅ 完成 | `app/models/tiktok_review.py` |
| main.py 注册 | ✅ 完成 | 两个 router 已 include |
| 后端集成测试 | ✅ 通过 | 12 条，覆盖率 ≥ 70% |
| 前端 API 层 | ✅ 完成 | `tiktokReview.ts`，前端单元测试 6 条通过 |
| 前端运营端页面 | ✅ 完成 | `TiktokReviewPage.tsx`，路由 `/workspace/tiktok-review` |
| 前端管理端 Tab | ✅ 完成 | `TiktokReviewConfigTab.tsx`，WorkspaceConfigPage 已注册 |
| 契约文档 | ✅ 已更新 | Base_API §20、Base_Database §21 迁移 026 |
| 全量回归 | ✅ 通过 | 后端集成测试全部 PASSED |
```

- [ ] **Step 3: Commit 文档**

```bash
git add backend/docs/README.md docs/pm/PM_记忆与状态_M2.md
git commit -m "docs: Sprint 13 tiktok-review 文档落地 + PM 记忆更新"
```

---

## 完成标准（DoD 检查）

全部 Task 1~10 完成后，确认以下全部满足：

- [ ] 后端集成测试 12 条全部 PASSED
- [ ] 覆盖率门禁通过（operator_tiktok_review ≥ 70%）
- [ ] 前端单元测试 6 条全部 PASSED
- [ ] TypeScript 无编译错误
- [ ] 全量后端回归无新增失败
- [ ] 冒烟测试 5 项全部通过
- [ ] 迁移红线 1~6 全部满足
- [ ] 契约文档已更新
- [ ] README 已更新
- [ ] PM 记忆已更新
