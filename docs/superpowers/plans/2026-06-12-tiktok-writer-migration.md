# TikTok 脚本仿写（tiktok-writer）迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧架构 `Ai_Toolbox/tiktok-writer-web/` 迁移到 MCN Platform 新架构，接入 JWT 鉴权、AI Key 池、审计日志，前端实现完整 5 步仿写工作流。

**Architecture:** 后端新增 `operator_tiktok_writer.py`（3 个接口）和共用 `word_export.py`（Markdown→docx），无新数据库表。前端新增 `TiktokWriterPage.tsx`（5 步流程页）。

**Tech Stack:** FastAPI · SQLAlchemy(asyncpg) · python-docx · yunwu adapter · React 19 · Ant Design 5 · TypeScript 6 · Vite 8

---

## 文件结构图

```
新建：
  backend/migrations/014_tiktok_writer.sql        ← workspace_tools INSERT
  backend/app/services/word_export.py             ← 共用 Markdown→docx（tiktok-writer 首用）
  backend/app/routers/operator_tiktok_writer.py   ← 3 个 API 接口
  backend/tests/unit/services/test_word_export.py ← word_export 单元测试
  backend/tests/integration/routers/test_operator_tiktok_writer.py ← 集成测试
  frontend/src/types/tiktokWriter.ts              ← TS 类型
  frontend/src/api/tiktokWriter.ts                ← 3 个 API 调用函数
  frontend/src/pages/operator/TiktokWriterPage.tsx ← 5 步仿写页面

修改（冻结区，改完跑全量回归）：
  backend/app/main.py                             ← 新增 router import + include_router
  frontend/src/App.tsx                            ← 新增 /workspace/tiktok-writer 路由
  frontend/src/pages/operator/WorkspacePage.tsx   ← 新增 tiktok-writer 导航分支
```

---

## 环境准备（开始前确认）

```bash
cd /Users/zhangchong/desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
python -c "from app.models.kol import Kol; print(Kol.persona)"   # 应输出 Column 对象
python -c "from app.models.output import Output; print(Output.task_id)"  # 同上
python -c "from app.adapters import yunwu; print(yunwu.chat_stream)"     # 应能导入
```

---

## Task 1: DB 注册 + 共用 Word 导出服务

**Files:**
- Create: `backend/migrations/014_tiktok_writer.sql`
- Create: `backend/app/services/word_export.py`
- Create: `backend/tests/unit/services/test_word_export.py`

### Step 1.1: 写 014 迁移文件

创建 `backend/migrations/014_tiktok_writer.sql`：

```sql
-- 014_tiktok_writer.sql
-- 注册 tiktok-writer 工具到 workspace_tools

INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'tiktok-writer',
    'TikTok 脚本仿写',
    '内容创作',
    '粘贴 TikTok 视频文案，AI 分析结构并仿写 Body，支持多轮迭代修改，最终导出 Word',
    'dev',
    '["AI生成","仿写","TikTok","英文","docx"]'::jsonb,
    15
)
ON CONFLICT (tool_code) DO NOTHING;
```

### Step 1.2: 执行迁移

```bash
PGPASSWORD=admin123 psql -h localhost -U mcn_user -d mcn_m1 \
  -f backend/migrations/014_tiktok_writer.sql
```

期望输出：`INSERT 0 1`

验证：

```bash
PGPASSWORD=admin123 psql -h localhost -U mcn_user -d mcn_m1 \
  -c "SELECT tool_code, tool_name, status FROM workspace_tools WHERE tool_code='tiktok-writer';"
```

期望：`tiktok-writer | TikTok 脚本仿写 | dev`

### Step 1.3: 先写 word_export 单元测试（TDD 红灯）

创建 `backend/tests/unit/services/test_word_export.py`：

```python
"""
Unit tests for app/services/word_export.py

测试 Markdown → docx 转换逻辑，全部用内存，无 DB 依赖。
"""
import io
import pytest
from docx import Document


# ── helpers ────────────────────────────────────────────────────────

def load_doc(docx_bytes: bytes) -> Document:
    return Document(io.BytesIO(docx_bytes))


def collect_text(doc: Document) -> list[str]:
    """返回文档所有段落的文本列表（空段落记为 ''）。"""
    return [p.text for p in doc.paragraphs]


# ── tests ──────────────────────────────────────────────────────────

class TestMarkdownToDocxBytes:

    def test_returns_bytes(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="Test Title",
            metadata_lines=["Topic: foo", "Exported: 2026-01-01"],
            content="Hello world",
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_valid_docx_format(self):
        """返回的 bytes 可以被 python-docx 正确加载。"""
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="My Title",
            metadata_lines=["Topic: t"],
            content="plain text",
        )
        doc = load_doc(result)
        texts = collect_text(doc)
        assert any("My Title" in t for t in texts)

    def test_title_in_document(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="PersonaName · TikTok Script",
            metadata_lines=[],
            content="body",
        )
        doc = load_doc(result)
        texts = collect_text(doc)
        assert any("PersonaName · TikTok Script" in t for t in texts)

    def test_metadata_lines_in_document(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=["Topic: https://example.com", "Exported: 2026-06-12"],
            content="body",
        )
        doc = load_doc(result)
        texts = collect_text(doc)
        assert any("Topic: https://example.com" in t for t in texts)
        assert any("Exported: 2026-06-12" in t for t in texts)

    def test_heading1_becomes_heading_paragraph(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="# My Heading",
        )
        doc = load_doc(result)
        headings = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert any("My Heading" in h.text for h in headings)

    def test_heading2_becomes_heading_paragraph(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="## Section Two",
        )
        doc = load_doc(result)
        headings = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert any("Section Two" in h.text for h in headings)

    def test_bold_text_has_bold_run(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="normal **bold word** after",
        )
        doc = load_doc(result)
        bold_runs = [
            run for p in doc.paragraphs for run in p.runs if run.bold and run.text.strip()
        ]
        assert any("bold word" in r.text for r in bold_runs)

    def test_bullet_list_item(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="- List item one",
        )
        doc = load_doc(result)
        texts = collect_text(doc)
        assert any("List item one" in t for t in texts)

    def test_ordered_list_rendered_as_plain(self):
        """1. xxx 应渲染为普通段落（保留原版 bug，不修复）。"""
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="1. First item",
        )
        doc = load_doc(result)
        # 不应变成 Heading
        headings = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert not any("First item" in h.text for h in headings)
        # 文本应存在于段落中
        texts = collect_text(doc)
        assert any("First item" in t for t in texts)

    def test_empty_line_produces_empty_paragraph(self):
        from app.services.word_export import markdown_to_docx_bytes
        result = markdown_to_docx_bytes(
            title="T",
            metadata_lines=[],
            content="line one\n\nline two",
        )
        doc = load_doc(result)
        texts = collect_text(doc)
        assert any(t == "" for t in texts)  # 空段落
        assert any("line one" in t for t in texts)
        assert any("line two" in t for t in texts)
```

### Step 1.4: 运行测试，确认红灯

```bash
cd backend
pytest tests/unit/services/test_word_export.py -v
```

期望：全部 FAILED（ImportError，模块未创建）

### Step 1.5: 实现 word_export.py

创建 `backend/app/services/word_export.py`：

```python
"""
app/services/word_export.py

共用 Markdown → Word 文档生成，返回 bytes。
tiktok-writer / 其他工具复用此模块。

支持语法：
  # / ## / ### → Heading 1/2/3
  - text / * text → Bullet List
  **bold** → Bold run
  空行 → 空段落
  1. xxx → 普通段落（保留原版有序列表 bug，不修复）
"""
import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


def _set_run_font(run, font_name: str, font_size_pt: int | None = None) -> None:
    run.font.name = font_name
    if font_size_pt is not None:
        run.font.size = Pt(font_size_pt)


def _parse_inline(para, text: str, font_name: str, font_size_pt: int | None) -> None:
    """将 **bold** 标记应用到 para 的 runs 上。"""
    parts = re.split(r"(\*\*.*?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = para.add_run(part[2:-2])
            run.bold = True
        else:
            run = para.add_run(part)
        _set_run_font(run, font_name, font_size_pt)


def markdown_to_docx_bytes(
    title: str,
    metadata_lines: list[str],
    content: str,
    font_name: str = "Arial",
    body_font_size_pt: int = 22,
) -> bytes:
    """
    生成 Word 文档并以 bytes 返回。

    Args:
        title: 文档标题行（居中，加粗）
        metadata_lines: 元数据行列表，如 ["Topic: ...", "Exported: ..."]（居中，小字）
        content: Markdown 格式的正文内容
        font_name: 正文字体，默认 Arial
        body_font_size_pt: 正文字号（pt），默认 22
    """
    doc = Document()

    # 标题（居中加粗）
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.name = font_name
    title_run.font.size = Pt(28)

    # 元数据行（居中，12pt）
    for meta in metadata_lines:
        mp = doc.add_paragraph()
        mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        mr = mp.add_run(meta)
        _set_run_font(mr, font_name, 12)

    # 间隔行
    doc.add_paragraph()

    # 正文：逐行解析 Markdown
    for line in content.split("\n"):
        stripped = line.strip()

        if not stripped:
            doc.add_paragraph()
            continue

        # Heading（# / ## / ###）
        h_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h_match:
            level = len(h_match.group(1))
            doc.add_heading(h_match.group(2), level=level)
            continue

        # Bullet list（- / *）
        if re.match(r"^[-*]\s+", stripped):
            text = re.sub(r"^[-*]\s+", "", stripped)
            try:
                para = doc.add_paragraph(style="List Bullet")
            except KeyError:
                # 样式不存在时退化为普通段落加前缀
                para = doc.add_paragraph()
                para.add_run("• ")
            _parse_inline(para, text, font_name, body_font_size_pt)
            continue

        # 普通段落（含有序列表——保留原版 bug，渲染为普通段落）
        para = doc.add_paragraph()
        _parse_inline(para, stripped, font_name, body_font_size_pt)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

### Step 1.6: 运行测试，确认绿灯

```bash
pytest tests/unit/services/test_word_export.py -v
```

期望：全部 PASSED

### Step 1.7: Commit

```bash
git add backend/migrations/014_tiktok_writer.sql \
        backend/app/services/word_export.py \
        backend/tests/unit/services/test_word_export.py
git commit -m "feat: add word_export shared service + 014 tiktok-writer DB registration"
```

---

## Task 2: 后端 Router

**Files:**
- Create: `backend/app/routers/operator_tiktok_writer.py`
- Create: `backend/tests/integration/routers/test_operator_tiktok_writer.py`

### Step 2.1: 先写集成测试（TDD 红灯）

创建 `backend/tests/integration/routers/test_operator_tiktok_writer.py`：

```python
"""
Integration tests for operator_tiktok_writer router.

需要：backend/tests/integration/conftest.py 提供 test_client + test_session。
test_client 已 override get_db，使用测试库 mcn_test。

覆盖：
- Auth：未授权 401
- /chat：空 messages 400、空 systemPrompt 400、正常流式调用（mock yunwu）
- /export-word：空 content 400、正常导出返回 docx、写 outputs 表
- /kols/personas：无数据返回空列表、有数据返回正确格式
"""
import io
from unittest.mock import AsyncMock, patch

import pytest
from docx import Document
from sqlalchemy import text

from app.models.kol import Kol
from app.models.output import Output


# ── Auth ────────────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_word_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Alice", "topic": "t", "content": "hello"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_kols_personas_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/tiktok-writer/kols/personas")
        assert resp.status_code == 401


# ── /chat ────────────────────────────────────────────────────────────

class TestChat:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [], "systemPrompt": "test prompt"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_empty_system_prompt_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_chat_streams_plain_text(self, test_client, operator_token):
        """mock yunwu.chat_stream，验证 StreamingResponse content-type 为 text/plain。"""

        async def mock_stream(*args, **kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        with patch("app.routers.operator_tiktok_writer.yunwu_adapter.chat_stream", side_effect=mock_stream):
            resp = await test_client.post(
                "/api/tools/tiktok-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "go"}],
                    "systemPrompt": "You are helpful.",
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "Hello world" in resp.text

    @pytest.mark.asyncio
    async def test_chat_with_create_job_writes_task_job(self, test_client, operator_token, test_session):
        """createJob=True 时后台写 task_jobs 记录。"""

        async def mock_stream(*args, **kwargs):
            yield "body result"

        with patch("app.routers.operator_tiktok_writer.yunwu_adapter.chat_stream", side_effect=mock_stream):
            resp = await test_client.post(
                "/api/tools/tiktok-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "go"}],
                    "systemPrompt": "You are helpful.",
                    "createJob": True,
                    "jobContext": {"tiktokUrl": "https://t.co/x", "likesCount": "200000", "selectedPersonaName": "Alice"},
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        # 等 background task 完成（StreamingResponse 完成后 background 已运行）
        result = await test_session.execute(
            text("SELECT tool_code FROM task_jobs WHERE tool_code='tiktok-writer' ORDER BY id DESC LIMIT 1")
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "tiktok-writer"


# ── /export-word ─────────────────────────────────────────────────────

class TestExportWord:
    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Alice", "topic": "t", "content": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_export_returns_docx_bytes(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={
                "personaName": "Alice",
                "topic": "https://tiktok.com/v/123",
                "content": "# Opening\nHello world\n\n**Bold** text",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]
        # 验证 docx 结构合法
        doc = Document(io.BytesIO(resp.content))
        texts = [p.text for p in doc.paragraphs]
        assert any("Alice" in t for t in texts)

    @pytest.mark.asyncio
    async def test_export_content_disposition_filename(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Bob", "topic": "t", "content": "Hello"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "TikTok_Script_Bob" in cd

    @pytest.mark.asyncio
    async def test_export_writes_output_record(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={
                "personaName": "Carol",
                "topic": "https://t.co/abc",
                "content": "Final script content here",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        result = await test_session.execute(
            text("SELECT tool_code, content FROM outputs WHERE tool_code='tiktok-writer' ORDER BY id DESC LIMIT 1")
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "tiktok-writer"
        assert "Final script content here" in row[1]


# ── /kols/personas ───────────────────────────────────────────────────

class TestKolsPersonas:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_personas(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "personas" in data
        assert isinstance(data["personas"], list)

    @pytest.mark.asyncio
    async def test_returns_kols_with_persona(self, test_client, operator_token, test_session):
        # 插入一条有 persona 的 kol
        await test_session.execute(text("""
            INSERT INTO kols (name, persona, content_plan, status, created_at, updated_at)
            VALUES ('TestCreator', 'Soul content here', 'Content plan here',
                    'active', NOW(), NOW())
        """))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        personas = resp.json()["personas"]
        assert any(p["name"] == "TestCreator" for p in personas)
        # 验证字段名与原 material-library 兼容
        target = next(p for p in personas if p["name"] == "TestCreator")
        assert "soul" in target
        assert "contentPlan" in target
        assert "Soul content here" in target["soul"]

    @pytest.mark.asyncio
    async def test_kols_without_persona_excluded(self, test_client, operator_token, test_session):
        """persona IS NULL 的 kol 不应出现在列表里。"""
        await test_session.execute(text("""
            INSERT INTO kols (name, persona, status, created_at, updated_at)
            VALUES ('NullPersonaCreator', NULL, 'active', NOW(), NOW())
        """))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        personas = resp.json()["personas"]
        assert not any(p["name"] == "NullPersonaCreator" for p in personas)
```

**注意**：测试用的 `operator_token` fixture 需在 `tests/integration/conftest.py` 中存在。检查现有 conftest：

```bash
grep "operator_token\|admin_token" backend/tests/integration/conftest.py | head -10
```

如果不存在，在 conftest.py 追加：

```python
# 在 tests/integration/conftest.py 末尾追加（若无 operator_token fixture）
from app.core.security import create_access_token

@pytest_asyncio.fixture
async def operator_token(test_session):
    """创建测试 operator 用户并返回 JWT token。"""
    from app.core.security import get_password_hash
    from sqlalchemy import text as sql_text
    result = await test_session.execute(sql_text("""
        INSERT INTO users (username, email, hashed_password, role, status,
                           password_changed_at, created_at, updated_at)
        VALUES ('op_tiktok', 'op_tiktok@test.com', :pw, 'operator', 'active',
                NOW(), NOW(), NOW())
        ON CONFLICT (username) DO UPDATE SET status='active'
        RETURNING id
    """), {"pw": get_password_hash("Test@12345")})
    await test_session.commit()
    user_id = result.fetchone()[0]
    return create_access_token({"sub": str(user_id)})
```

### Step 2.2: 运行测试，确认红灯

```bash
cd backend
pytest tests/integration/routers/test_operator_tiktok_writer.py -v 2>&1 | head -30
```

期望：ImportError 或 404（router 未注册）

### Step 2.3: 实现 operator_tiktok_writer.py

创建 `backend/app/routers/operator_tiktok_writer.py`：

```python
"""
app/routers/operator_tiktok_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/tools/tiktok-writer/chat          — AI 流式对话（raw text stream）
  POST /api/tools/tiktok-writer/export-word   — 导出 Word 文档
  GET  /api/tools/tiktok-writer/kols/personas — 达人人设列表（兼容 material-library 格式）
"""
import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db, AsyncSessionLocal
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services import word_export

router = APIRouter(prefix="/tools/tiktok-writer", tags=["tiktok-writer"])

DEFAULT_MODEL = "claude-opus-4-6-thinking"
# 429 指数退避等待时间（秒），最多重试 3 次
_RETRY_DELAYS = [2, 4, 6]


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


# ──────────────────────────────────────────────────────────────────────────
# POST /tools/tiktok-writer/chat
# ──────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    messages: list[dict]
    systemPrompt: str
    model: str = DEFAULT_MODEL
    createJob: bool = False  # True → Generate Body 步骤，后台写 task_jobs
    jobContext: dict | None = None  # {"tiktokUrl": "...", "likesCount": "...", "selectedPersonaName": "..."}


@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 流式对话，返回 raw text stream（非 SSE）。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if not body.systemPrompt.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "systemPrompt 不能为空"},
        )

    messages = [{"role": "system", "content": body.systemPrompt}] + body.messages
    user_id = current_user.id
    create_job = body.createJob
    job_context = body.jobContext or {}
    model_id = body.model or DEFAULT_MODEL

    state: dict = {"full_text": "", "start_time": time.monotonic()}

    async def generate():
        """流式生成，429 时最多重试 3 次（指数退避 2/4/6s）。"""
        delays = [0] + _RETRY_DELAYS  # 首次不等待
        for i, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with AsyncSessionLocal() as stream_db:
                    async for chunk in yunwu_adapter.chat_stream(
                        messages=messages,
                        db=stream_db,
                        model_id=model_id,
                        user_id=user_id,
                        feature="tiktok_writer_chat",
                        max_tokens=8192,
                    ):
                        state["full_text"] += chunk
                        yield chunk
                return  # 成功退出
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(_RETRY_DELAYS):
                    continue  # 重试
                yield f"\n\n[ERROR] {str(e)}"
                return

    async def write_task_job():
        """Generate Body 步骤的审计记录（background task）。"""
        if not create_job:
            return
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"TW-{int(time.time())}",
                tool_code="tiktok-writer",
                tool_name="TikTok 脚本仿写",
                status="completed",
                input_payload={
                    "tiktokUrl": job_context.get("tiktokUrl", ""),
                    "likesCount": job_context.get("likesCount", ""),
                    "selectedPersonaName": job_context.get("selectedPersonaName", ""),
                },
                created_by=user_id,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
            bg_db.add(task_job)
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ──────────────────────────────────────────────────────────────────────────
# POST /tools/tiktok-writer/export-word
# ──────────────────────────────────────────────────────────────────────────

class ExportWordRequest(BaseModel):
    personaName: str = "TikTok"
    topic: str = ""
    content: str
    taskJobId: int | None = None  # 关联已创建的 task_job（可选）


@router.post("/export-word")
async def export_word(
    body: ExportWordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成 Word 文档并写 outputs 表，返回 docx 二进制流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"{body.personaName} · TikTok Script"
    metadata = [
        f"Topic: {body.topic}" if body.topic.strip() else "Topic: —",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=title,
        metadata_lines=metadata,
        content=body.content,
    )

    # 写 outputs 表
    output = Output(
        title=f"TikTok Script · {body.personaName} · {date_str}",
        tool_code="tiktok-writer",
        tool_name="TikTok 脚本仿写",
        content=body.content,
        word_count=len(body.content.split()),
        task_id=body.taskJobId,
        created_by=current_user.id,
    )
    db.add(output)
    await db.commit()

    filename = f"TikTok_Script_{body.personaName}_{date_str}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ──────────────────────────────────────────────────────────────────────────
# GET /tools/tiktok-writer/kols/personas
# ──────────────────────────────────────────────────────────────────────────

@router.get("/kols/personas")
async def get_kol_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    查询 kols 表，返回有人设的达人列表。
    字段名与原 material-library /personas 接口兼容（soul / contentPlan）。
    """
    rows = (
        await db.execute(
            select(Kol.id, Kol.name, Kol.persona, Kol.content_plan)
            .where(Kol.persona.is_not(None))
            .where(Kol.deleted_at.is_(None))
            .order_by(Kol.name)
        )
    ).all()

    personas = [
        {
            "name": row.name,
            "soul": row.persona or "",
            "contentPlan": row.content_plan or "",
        }
        for row in rows
    ]
    return {"personas": personas}
```

**注意：TaskJob 的字段检查**。先确认 TaskJob model 有 `task_no`、`input_payload`、`started_at`、`finished_at`：

```bash
grep "task_no\|input_payload\|started_at\|finished_at" backend/app/models/task.py
```

若字段名不符，按实际字段名调整 router 中的 `TaskJob(...)` 构造。

### Step 2.4: 运行单元测试，确认 word_export 仍通过

```bash
pytest tests/unit/services/test_word_export.py -v
```

期望：全部 PASSED

### Step 2.5: Commit

```bash
git add backend/app/routers/operator_tiktok_writer.py \
        backend/tests/integration/routers/test_operator_tiktok_writer.py
git commit -m "feat: add operator_tiktok_writer router (chat + export-word + kols/personas)"
```

---

## Task 3: 注册 Router 到 main.py（冻结区变更）

**Files:**
- Modify: `backend/app/main.py`

### Step 3.1: 检查当前 main.py 末尾 router 列表

```bash
grep "tiktok" backend/app/main.py
```

期望：无输出（尚未注册）

### Step 3.2: 在 main.py 添加 import 和 include_router

在 `backend/app/main.py` 中：

1. 在最后一个 `from app.routers...` 行之后添加：
```python
from app.routers.operator_tiktok_writer import router as operator_tiktok_writer_router
```

2. 在最后一个 `app.include_router(...)` 行之后添加：
```python
app.include_router(operator_tiktok_writer_router, prefix="/api")
```

### Step 3.3: 验证后端启动无报错

```bash
cd backend && source .venv/bin/activate
python -c "from app.main import app; print('OK')"
```

期望：输出 `OK`，无 ImportError

### Step 3.4: 运行集成测试（绿灯）

```bash
pytest tests/integration/routers/test_operator_tiktok_writer.py -v
```

期望：全部 PASSED

### Step 3.5: 全量回归（冻结区改动必须跑）

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```

期望：无新增 FAILED（只跑单元+集成，跳过 E2E）

### Step 3.6: 覆盖率检查

```bash
pytest tests/unit/services/test_word_export.py \
       tests/integration/routers/test_operator_tiktok_writer.py \
       --cov=app.services.word_export \
       --cov=app.routers.operator_tiktok_writer \
       --cov-report=term-missing
```

期望：
- `word_export.py` ≥ 85%
- `operator_tiktok_writer.py` ≥ 70%

### Step 3.7: Commit

```bash
git add backend/app/main.py
git commit -m "feat: register operator_tiktok_writer router in main.py"
```

---

## Task 4: 前端 Types + API

**Files:**
- Create: `frontend/src/types/tiktokWriter.ts`
- Create: `frontend/src/api/tiktokWriter.ts`

### Step 4.1: 先写 API 单元测试（TDD 红灯）

创建 `frontend/src/__tests__/unit/api/tiktokWriter.test.ts`：

```typescript
/**
 * Unit tests for src/api/tiktokWriter.ts
 * Mock fetch/request，不发真实请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as requestModule from '../../../api/request';

vi.mock('../../../api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

// Mock useAuthStore for stream functions
vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

// Mock fetch for stream functions
const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('tiktokWriter API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getPersonas', () => {
    it('calls GET /api/tools/tiktok-writer/kols/personas', async () => {
      const { getPersonas } = await import('../../../api/tiktokWriter');
      vi.mocked(requestModule.get).mockResolvedValue({ personas: [] });
      await getPersonas();
      expect(requestModule.get).toHaveBeenCalledWith('/api/tools/tiktok-writer/kols/personas');
    });
  });

  describe('chatStream', () => {
    it('calls POST /api/tools/tiktok-writer/chat with correct headers', async () => {
      const { chatStream } = await import('../../../api/tiktokWriter');
      mockFetch.mockResolvedValue(new Response('ok'));
      await chatStream({ messages: [], systemPrompt: 'test' });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-writer/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
          }),
        }),
      );
    });

    it('includes createJob and jobContext when provided', async () => {
      const { chatStream } = await import('../../../api/tiktokWriter');
      mockFetch.mockResolvedValue(new Response('ok'));
      await chatStream({
        messages: [],
        systemPrompt: 'test',
        createJob: true,
        jobContext: { tiktokUrl: 'https://t.co/x', likesCount: '200000', selectedPersonaName: 'Alice' },
      });
      const body = JSON.parse(vi.mocked(mockFetch).mock.calls[0][1]!.body as string);
      expect(body.createJob).toBe(true);
      expect(body.jobContext.selectedPersonaName).toBe('Alice');
    });
  });

  describe('exportWord', () => {
    it('calls POST /api/tools/tiktok-writer/export-word with correct headers', async () => {
      const { exportWord } = await import('../../../api/tiktokWriter');
      const mockBlob = new Blob(['fake docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
      mockFetch.mockResolvedValue(new Response(mockBlob));
      await exportWord({ personaName: 'Alice', topic: 't', content: 'hello' });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-writer/export-word'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });
});
```

运行（确认红灯）：

```bash
cd frontend
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npx vitest run src/__tests__/unit/api/tiktokWriter.test.ts
```

期望：FAILED（模块不存在）

### Step 4.2: 创建 types/tiktokWriter.ts

创建 `frontend/src/types/tiktokWriter.ts`：

```typescript
// Types for TikTok 脚本仿写工具

export interface Persona {
  name: string;
  soul: string;
  contentPlan: string;
}

export interface GetPersonasResponse {
  personas: Persona[];
}

export interface ChatRequest {
  messages: Array<{ role: 'user' | 'assistant'; content: string }>;
  systemPrompt: string;
  model?: string;
  createJob?: boolean;
  jobContext?: {
    tiktokUrl: string;
    likesCount: string;
    selectedPersonaName: string;
  };
}

export interface ExportWordRequest {
  personaName: string;
  topic: string;
  content: string;
  taskJobId?: number;
}

// Step state types for the 5-step flow
export type Step = 1 | 2 | 3 | 4 | 5;

export interface StepState {
  tiktokUrl: string;
  transcript: string;
  likesCount: string;
  selectedPersona: Persona | null;

  hookEvaluation: string;       // Step 2 AI 返回的 PASS/FAIL + reason
  hookVerdict: 'PASS' | 'FAIL' | null;
  lockedOpening: string;        // Step 3 解析出的 Opening（锁定后不变）
  structureAnalysis: string;    // Step 3 AI 返回的完整结构分析

  aiBody: string;               // Step 4 最新的 Body（多轮修改更新此字段）
  finalBody: string;            // Step 5 用户可编辑的最终 Body
  rewriteMode: 'ai' | 'user';   // ai 直写 / 用户提供方向
  userIdeas: string;            // 用户提供方向模式的输入

  chatMessages: Array<{ role: 'user' | 'assistant'; content: string }>;
  isStreaming: boolean;
  currentStep: Step;
}
```

### Step 4.3: 创建 api/tiktokWriter.ts

创建 `frontend/src/api/tiktokWriter.ts`：

```typescript
import { get } from './request';
import type { ChatRequest, ExportWordRequest, GetPersonasResponse } from '../types/tiktokWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** 获取有人设的达人列表 */
export const getPersonas = () =>
  get<GetPersonasResponse>('/api/tools/tiktok-writer/kols/personas');

/** AI 对话（流式，返回原始 Response，由调用方自行读取 body stream） */
export async function chatStream(body: ChatRequest): Promise<Response> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/tiktok-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** 导出 Word 文档，返回 Blob */
export async function exportWord(body: ExportWordRequest): Promise<Blob> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-writer/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `Export failed: ${resp.status}`);
  }
  return resp.blob();
}
```

### Step 4.4: 运行 API 测试，确认绿灯

```bash
cd frontend
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npx vitest run src/__tests__/unit/api/tiktokWriter.test.ts
```

期望：全部 PASSED

### Step 4.5: Commit

```bash
git add frontend/src/types/tiktokWriter.ts \
        frontend/src/api/tiktokWriter.ts \
        frontend/src/__tests__/unit/api/tiktokWriter.test.ts
git commit -m "feat: add tiktok-writer TypeScript types and API layer"
```

---

## Task 5: 前端运营端页面

**Files:**
- Create: `frontend/src/pages/operator/TiktokWriterPage.tsx`

### Step 5.1: 实现 TiktokWriterPage.tsx

本页面实现 5 步仿写流程。篇幅较长，完整代码如下：

创建 `frontend/src/pages/operator/TiktokWriterPage.tsx`：

```tsx
/**
 * TikTok 脚本仿写页面（tiktok-writer）
 *
 * 5 步工作流：
 *   Step 1 · Source      — 粘贴链接 / 文案 / 点赞数
 *   Step 2 · Validate    — AI 评估 Opening Hook + 选择人设
 *   Step 3 · Structure   — AI 分析结构，解析 Opening
 *   Step 4 · Rewrite     — AI 仿写 Body + 多轮迭代
 *   Step 5 · Export      — 编辑 finalBody + 导出 Word
 */
import { useState, useRef } from 'react';
import { Button, Input, Select, Steps, message, Spin, Radio, Alert } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { chatStream, exportWord, getPersonas } from '../../api/tiktokWriter';
import type { Persona, StepState } from '../../types/tiktokWriter';

const { TextArea } = Input;

// ── 词数工具 ──────────────────────────────────────────────────────────────

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// ── System Prompt 构建函数（前端动态注入变量）────────────────────────────

function buildHookEvalPrompt(): string {
  return `You are a TikTok content strategist. Evaluate the opening hook of this TikTok script.

The "opening" is the first 1-3 sentences that grab attention.

Your task:
1. Identify the exact opening (first 1-3 sentences)
2. Rate if this opening would make a general audience stop scrolling and keep watching
3. Answer with PASS or FAIL

Format your response EXACTLY like this:
OPENING: [copy the exact opening sentences here]
---
VERDICT: [PASS or FAIL]
REASON: [1-2 sentences explaining why]`;
}

function buildStructurePrompt(): string {
  return `You are a TikTok script structure analyst. Analyze this TikTok script and break it into clear structural sections.

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
===NOTES_END===`;
}

function buildRewritePrompt(
  mode: 'ai' | 'user',
  originalWordCount: number,
  openingWordCount: number,
  structureAnalysis: string,
  persona: Persona | null,
  userIdeas: string,
): string {
  const bodyLimit = originalWordCount - openingWordCount;
  const personaContext = persona
    ? `\n\nCreator persona (light reference only):\nName: ${persona.name}\nStyle: ${persona.soul.slice(0, 500)}`
    : '';

  if (mode === 'ai') {
    return `You are a TikTok script rewriter. Your job is to rewrite ONLY the body of a TikTok script.

IRON RULES — VIOLATING ANY OF THESE IS A FAILURE:
1. DO NOT output the opening. The opening is handled separately and must not appear in your output.
2. Your output word count MUST be LESS than or equal to ${originalWordCount} words total (opening + your body combined). The opening is ${openingWordCount} words, so your body must be ≤ ${bodyLimit} words.
3. The content must be DIFFERENTIATED — not a paraphrase, not a synonym swap. Bring fresh angles, new examples, or unique perspective.
4. Maintain the SAME structure and flow as the original body.
5. The tone should feel natural, engaging, and native-level English for TikTok.
6. Do NOT be generic or mediocre. Every sentence should earn its place.

Output ONLY the rewritten body text. No headers, no labels, no explanations.${personaContext}

ORIGINAL STRUCTURE FOR REFERENCE:
${structureAnalysis}`;
  }

  return `You are a TikTok script rewriter. Your job is to rewrite ONLY the body of a TikTok script, incorporating the user's creative direction.

IRON RULES — VIOLATING ANY OF THESE IS A FAILURE:
1. DO NOT output the opening. The opening is handled separately and must not appear in your output.
2. Your output word count MUST be LESS than or equal to ${originalWordCount} words total (opening + your body combined). The opening is ${openingWordCount} words, so your body must be ≤ ${bodyLimit} words.
3. The USER'S IDEAS take priority. The reference script is secondary.
4. Maintain the SAME structure and flow as the original body.
5. The tone should feel natural, engaging, and native-level English for TikTok.

Output ONLY the rewritten body text. No headers, no labels, no explanations.${personaContext}

ORIGINAL STRUCTURE FOR REFERENCE:
${structureAnalysis}

USER'S CREATIVE DIRECTION:
${userIdeas}`;
}

function buildIteratePrompt(lockedOpening: string, aiBody: string, bodyLimit: number): string {
  return `You are revising a TikTok script body based on user feedback.

IRON RULES:
1. DO NOT include the opening in your output. Opening is: "${lockedOpening}"
2. Word count of your body must be ≤ ${bodyLimit} words.
3. Apply the user's feedback precisely.
4. Output ONLY the revised body text, nothing else.

Current body being revised:
${aiBody}`;
}

// ── Opening 解析（Step 3）────────────────────────────────────────────────

function extractOpening(aiOutput: string, transcript: string): { opening: string; body: string } {
  const startTag = '===OPENING_START===';
  const endTag = '===OPENING_END===';
  const startIdx = aiOutput.indexOf(startTag);
  const endIdx = aiOutput.indexOf(endTag);

  if (startIdx !== -1 && endIdx !== -1) {
    const opening = aiOutput.slice(startIdx + startTag.length, endIdx).trim();
    // 在原文中找 Opening，之后的是 Body
    const pos = transcript.indexOf(opening);
    if (pos !== -1) {
      return { opening, body: transcript.slice(pos + opening.length).trim() };
    }
    // 精确匹配失败：用词数做近似切割
    const openWc = wordCount(opening);
    const words = transcript.split(/\s+/);
    return {
      opening,
      body: words.slice(openWc).join(' '),
    };
  }
  // fallback：取前 2 句作为 Opening
  const sentences = transcript.split(/(?<=[.!?])\s+/);
  const opening = sentences.slice(0, 2).join(' ');
  return { opening, body: sentences.slice(2).join(' ') };
}

// ── 流式读取工具 ──────────────────────────────────────────────────────────

async function readStream(
  resp: Response,
  onChunk: (chunk: string) => void,
): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onChunk(chunk);
  }
  return full;
}

// ── 主组件 ────────────────────────────────────────────────────────────────

const INITIAL_STATE: StepState = {
  tiktokUrl: '',
  transcript: '',
  likesCount: '',
  selectedPersona: null,
  hookEvaluation: '',
  hookVerdict: null,
  lockedOpening: '',
  structureAnalysis: '',
  aiBody: '',
  finalBody: '',
  rewriteMode: 'ai',
  userIdeas: '',
  chatMessages: [],
  isStreaming: false,
  currentStep: 1,
};

export default function TiktokWriterPage() {
  const [state, setState] = useState<StepState>(INITIAL_STATE);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personasLoaded, setPersonasLoaded] = useState(false);
  const [iterateInput, setIterateInput] = useState('');
  const [streamBuffer, setStreamBuffer] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  function update(patch: Partial<StepState>) {
    setState(prev => ({ ...prev, ...patch }));
  }

  // ── Step 1 验证 ──────────────────────────────────────────────────────────

  const likesNum = parseInt(state.likesCount.replace(/,/g, ''), 10);
  const likesOk = !isNaN(likesNum) && likesNum >= 100_000;
  const step1Ok = state.transcript.trim().length > 0 && likesOk;

  // ── Step 2: 评估 Opening Hook ─────────────────────────────────────────────

  async function handleEvaluateHook() {
    update({ isStreaming: true, hookEvaluation: '', hookVerdict: null });
    setStreamBuffer('');
    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: state.transcript }],
        systemPrompt: buildHookEvalPrompt(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      const verdict = full.includes('VERDICT: PASS') ? 'PASS' : 'FAIL';
      update({ hookEvaluation: full, hookVerdict: verdict, isStreaming: false });
      setStreamBuffer('');
    } catch (e) {
      message.error(`评估失败：${e}`);
      update({ isStreaming: false });
    }
  }

  async function loadPersonas() {
    if (personasLoaded) return;
    try {
      const data = await getPersonas();
      setPersonas(data.personas);
      setPersonasLoaded(true);
    } catch {
      message.error('加载人设列表失败');
    }
  }

  // ── Step 3: 分析结构 ──────────────────────────────────────────────────────

  async function handleAnalyzeStructure() {
    update({ isStreaming: true, structureAnalysis: '', lockedOpening: '' });
    setStreamBuffer('');
    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: state.transcript }],
        systemPrompt: buildStructurePrompt(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      const { opening } = extractOpening(full, state.transcript);
      update({
        structureAnalysis: full,
        lockedOpening: opening,
        isStreaming: false,
        currentStep: 4,
      });
      setStreamBuffer('');
    } catch (e) {
      message.error(`结构分析失败：${e}`);
      update({ isStreaming: false });
    }
  }

  // ── Step 4: 生成 Body（首次）────────────────────────────────────────────

  async function handleGenerateBody() {
    const originalWc = wordCount(state.transcript);
    const openingWc = wordCount(state.lockedOpening);
    const bodyText = state.transcript
      .slice(state.transcript.indexOf(state.lockedOpening) + state.lockedOpening.length)
      .trim();

    const systemPrompt = buildRewritePrompt(
      state.rewriteMode,
      originalWc,
      openingWc,
      state.structureAnalysis,
      state.selectedPersona,
      state.userIdeas,
    );

    const userContent =
      state.rewriteMode === 'ai'
        ? `Here is the original body (without opening):\n\n${bodyText}`
        : `Here is the original body (without opening):\n\n${bodyText}\n\nMy ideas:\n${state.userIdeas}`;

    update({ isStreaming: true, aiBody: '' });
    setStreamBuffer('');

    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: userContent }],
        systemPrompt,
        createJob: true,
        jobContext: {
          tiktokUrl: state.tiktokUrl,
          likesCount: state.likesCount,
          selectedPersonaName: state.selectedPersona?.name ?? '',
        },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      update({
        aiBody: full,
        chatMessages: [{ role: 'user', content: userContent }, { role: 'assistant', content: full }],
        isStreaming: false,
      });
      setStreamBuffer('');
    } catch (e) {
      message.error(`生成失败：${e}`);
      update({ isStreaming: false });
    }
  }

  // ── Step 4: 多轮修改 ──────────────────────────────────────────────────────

  async function handleIterate() {
    if (!iterateInput.trim()) return;
    const originalWc = wordCount(state.transcript);
    const openingWc = wordCount(state.lockedOpening);
    const bodyLimit = originalWc - openingWc;

    const newMessages = [
      ...state.chatMessages,
      { role: 'user' as const, content: iterateInput },
    ];

    update({ isStreaming: true });
    setStreamBuffer('');
    setIterateInput('');

    try {
      const resp = await chatStream({
        messages: newMessages,
        systemPrompt: buildIteratePrompt(state.lockedOpening, state.aiBody, bodyLimit),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      update({
        aiBody: full,
        chatMessages: [...newMessages, { role: 'assistant', content: full }],
        isStreaming: false,
      });
      setStreamBuffer('');
    } catch (e) {
      message.error(`修改失败：${e}`);
      update({ isStreaming: false });
    }
  }

  // ── Step 5: 导出 Word ─────────────────────────────────────────────────────

  async function handleExport() {
    const content = `${state.lockedOpening}\n\n${state.finalBody || state.aiBody}`;
    try {
      const blob = await exportWord({
        personaName: state.selectedPersona?.name ?? 'TikTok',
        topic: state.tiktokUrl,
        content,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const date = new Date().toISOString().slice(0, 10);
      a.download = `TikTok_Script_${state.selectedPersona?.name ?? 'TikTok'}_${date}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('Word 文档已下载，已保存至产出中心');
    } catch (e) {
      message.error(`导出失败：${e}`);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">TikTok 脚本仿写</h1>
          <p className="page-desc">分析 TikTok 视频结构，AI 仿写新 Body，支持多轮迭代</p>
        </div>
      </div>

      <Steps
        current={state.currentStep - 1}
        items={[
          { title: 'Source' },
          { title: 'Validate' },
          { title: 'Structure' },
          { title: 'Rewrite' },
          { title: 'Export' },
        ]}
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* ── Step 1: Source ── */}
      {state.currentStep >= 1 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 1 · Source</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>TikTok 视频链接</label>
            <Input
              placeholder="https://www.tiktok.com/@..."
              value={state.tiktokUrl}
              onChange={e => update({ tiktokUrl: e.target.value })}
            />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>视频文案 *</label>
            <TextArea
              rows={8}
              placeholder="粘贴视频完整文案..."
              value={state.transcript}
              onChange={e => update({ transcript: e.target.value })}
            />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              点赞数 *（需 ≥ 100,000）
            </label>
            <Input
              placeholder="200000"
              value={state.likesCount}
              onChange={e => update({ likesCount: e.target.value })}
              style={{ width: 200 }}
              status={state.likesCount && !likesOk ? 'error' : undefined}
            />
            {state.likesCount && !likesOk && (
              <div style={{ color: 'var(--red-500)', fontSize: 12, marginTop: 4 }}>
                点赞数需 ≥ 100,000
              </div>
            )}
          </div>
          <Button
            type="primary"
            disabled={!step1Ok}
            onClick={() => update({ currentStep: 2 })}
          >
            Continue →
          </Button>
        </div>
      )}

      {/* ── Step 2: Validate ── */}
      {state.currentStep >= 2 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · Validate Opening Hook</h3>
          <Button
            type="primary"
            loading={state.isStreaming}
            onClick={handleEvaluateHook}
            style={{ marginBottom: 'var(--sp-3)' }}
          >
            Evaluate Opening Hook
          </Button>

          {(state.hookEvaluation || streamBuffer) && (
            <div style={{
              background: 'var(--gray-50)',
              padding: 'var(--sp-3)',
              borderRadius: 8,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              marginBottom: 'var(--sp-3)',
            }}>
              {state.isStreaming ? streamBuffer : state.hookEvaluation}
            </div>
          )}

          {state.hookVerdict && (
            <Alert
              type={state.hookVerdict === 'PASS' ? 'success' : 'warning'}
              message={`Verdict: ${state.hookVerdict}`}
              style={{ marginBottom: 'var(--sp-3)' }}
            />
          )}

          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              创作者人设（可选）
            </label>
            <Select
              style={{ width: '100%' }}
              placeholder="选择人设（可跳过）"
              allowClear
              onDropdownVisibleChange={open => open && loadPersonas()}
              options={personas.map(p => ({ value: p.name, label: p.name }))}
              onChange={(val) => {
                const found = personas.find(p => p.name === val) ?? null;
                update({ selectedPersona: found });
              }}
            />
          </div>

          <Button
            type="primary"
            disabled={!state.hookVerdict}
            onClick={() => update({ currentStep: 3 })}
          >
            Continue →
          </Button>
        </div>
      )}

      {/* ── Step 3: Structure ── */}
      {state.currentStep >= 3 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · Analyze Structure</h3>
          <Button
            type="primary"
            loading={state.isStreaming}
            onClick={handleAnalyzeStructure}
            style={{ marginBottom: 'var(--sp-3)' }}
          >
            Analyze Structure
          </Button>

          {(state.structureAnalysis || (state.isStreaming && streamBuffer)) && (
            <div style={{
              background: 'var(--gray-50)',
              padding: 'var(--sp-3)',
              borderRadius: 8,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              fontSize: 12,
              marginBottom: 'var(--sp-3)',
            }}>
              {state.isStreaming ? streamBuffer : state.structureAnalysis}
            </div>
          )}

          {state.lockedOpening && (
            <Alert
              type="info"
              message="Opening Locked"
              description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{state.lockedOpening}</pre>}
              style={{ marginBottom: 'var(--sp-3)' }}
            />
          )}
        </div>
      )}

      {/* ── Step 4: Rewrite ── */}
      {state.currentStep >= 4 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 4 · Rewrite Body</h3>

          <Radio.Group
            value={state.rewriteMode}
            onChange={e => update({ rewriteMode: e.target.value })}
            style={{ marginBottom: 'var(--sp-3)' }}
          >
            <Radio.Button value="ai">AI 直写</Radio.Button>
            <Radio.Button value="user">提供方向</Radio.Button>
          </Radio.Group>

          {state.rewriteMode === 'user' && (
            <TextArea
              rows={3}
              placeholder="描述你的创作方向..."
              value={state.userIdeas}
              onChange={e => update({ userIdeas: e.target.value })}
              style={{ marginBottom: 'var(--sp-3)' }}
            />
          )}

          <Button
            type="primary"
            loading={state.isStreaming}
            icon={<ReloadOutlined />}
            onClick={handleGenerateBody}
            style={{ marginBottom: 'var(--sp-3)' }}
          >
            Generate Body
          </Button>

          {(state.aiBody || (state.isStreaming && streamBuffer)) && (
            <>
              <div style={{
                background: 'var(--gray-50)',
                padding: 'var(--sp-3)',
                borderRadius: 8,
                whiteSpace: 'pre-wrap',
                marginBottom: 'var(--sp-3)',
                minHeight: 120,
              }}>
                {state.isStreaming ? streamBuffer : state.aiBody}
              </div>

              {/* 多轮修改输入 */}
              {!state.isStreaming && state.aiBody && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 'var(--sp-3)' }}>
                  <Input
                    placeholder="告诉 AI 如何修改..."
                    value={iterateInput}
                    onChange={e => setIterateInput(e.target.value)}
                    onPressEnter={handleIterate}
                  />
                  <Button onClick={handleIterate} disabled={!iterateInput.trim()}>
                    修改
                  </Button>
                </div>
              )}

              {!state.isStreaming && state.aiBody && (
                <Button
                  type="primary"
                  onClick={() => update({ finalBody: state.aiBody, currentStep: 5 })}
                >
                  Use This Body →
                </Button>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Step 5: Export ── */}
      {state.currentStep >= 5 && (
        <div className="card">
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 5 · Export</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              Final Body（可直接编辑）
            </label>
            <TextArea
              rows={12}
              value={state.finalBody || state.aiBody}
              onChange={e => update({ finalBody: e.target.value })}
            />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)', color: 'var(--gray-500)', fontSize: 12 }}>
            完整脚本词数：{wordCount(`${state.lockedOpening}\n\n${state.finalBody || state.aiBody}`)} words
          </div>
          <Button
            type="primary"
            size="large"
            icon={<DownloadOutlined />}
            onClick={handleExport}
          >
            Export Word Document
          </Button>
        </div>
      )}
    </div>
  );
}
```

### Step 5.2: 验证 TypeScript 编译

```bash
cd frontend
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npx tsc --noEmit
```

期望：无 TypeScript 错误（或只有与本文件无关的既有错误）

### Step 5.3: Commit

```bash
git add frontend/src/pages/operator/TiktokWriterPage.tsx
git commit -m "feat: add TiktokWriterPage 5-step rewrite flow"
```

---

## Task 6: 前端路由接入（冻结区变更）

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/operator/WorkspacePage.tsx`

### Step 6.1: 修改 App.tsx，新增路由

在 `frontend/src/App.tsx` 中：

1. 在 `import BenchmarkPage` 行之后添加：
```tsx
import TiktokWriterPage from './pages/operator/TiktokWriterPage';
```

2. 在 `<Route path="/workspace/benchmark" .../>` 行之后添加：
```tsx
<Route path="/workspace/tiktok-writer" element={<TiktokWriterPage />} />
```

### Step 6.2: 修改 WorkspacePage.tsx，新增导航分支

在 `WorkspacePage.tsx` 的 `handleToolClick` 函数中，在 `else if (t.tool_code === 'benchmark')` 行之后添加：

```tsx
else if (t.tool_code === 'tiktok-writer') navigate('/workspace/tiktok-writer');
```

### Step 6.3: 验证编译

```bash
cd frontend
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npx tsc --noEmit
```

期望：无 TypeScript 错误

### Step 6.4: 运行全量前端测试

```bash
PATH="/opt/homebrew/opt/node@25/bin:$PATH" npx vitest run
```

期望：无新增 FAILED

### Step 6.5: 验证后端全量回归

```bash
cd backend
pytest tests/ -v --tb=short 2>&1 | tail -20
```

期望：无新增 FAILED

### Step 6.6: Commit

```bash
git add frontend/src/App.tsx \
        frontend/src/pages/operator/WorkspacePage.tsx
git commit -m "feat: wire tiktok-writer route and workspace navigation"
```

---

## Task 7: 激活工具 + 端到端冒烟测试

### Step 7.1: 数据库切换工具状态为 online（验收完成后执行）

```bash
PGPASSWORD=admin123 psql -h localhost -U mcn_user -d mcn_m1 \
  -c "UPDATE workspace_tools SET status='online' WHERE tool_code='tiktok-writer';"
```

### Step 7.2: 浏览器手动冒烟测试

1. 打开 http://localhost:5173，登录运营端账号
2. 进入「创作中心」，确认「TikTok 脚本仿写」卡片可见且可点击
3. 点击进入，确认 5 步 Steps 显示正常
4. Step 1：填写示例文案（30+ 词）、点赞数 200000，点 Continue
5. Step 2：点击 Evaluate Opening Hook，确认 AI 流式返回 PASS/FAIL
6. Step 3：点击 Analyze Structure，确认解析出 Opening 并锁定
7. Step 4：点击 Generate Body，确认 AI 流式生成 Body
8. Step 5：点击 Export，确认弹出下载 .docx 文件
9. 登录管理端，进入「产出中心」，确认有新产出记录

### Step 7.3: Final commit

```bash
git add backend/migrations/014_tiktok_writer.sql
git commit -m "feat: activate tiktok-writer migration record" --allow-empty
git log --oneline -8  # 确认所有提交在位
```

---

## 自检：Spec 覆盖核对

| 需求项 | 任务 | 状态 |
|--------|------|------|
| POST /chat 流式 raw text | Task 2 | ✅ |
| 429 重试 3 次指数退避 | Task 2 router `_RETRY_DELAYS` | ✅ |
| POST /export-word 返回 docx | Task 2 | ✅ |
| GET /kols/personas 兼容格式 | Task 2 | ✅ |
| word_export 共用模块 | Task 1 | ✅ |
| task_jobs 写入（Generate Body） | Task 2 `createJob=True` | ✅ |
| outputs 写入（export-word） | Task 2 export_word handler | ✅ |
| JWT 鉴权 | Task 2 `require_operator` | ✅ |
| workspace_tools 注册 | Task 1 migration 014 | ✅ |
| 前端 5 步流程 | Task 5 | ✅ |
| 点赞数校验前端 | Task 5 `likesOk` | ✅ |
| Opening 解析前端 | Task 5 `extractOpening` | ✅ |
| System Prompt 前端构建 | Task 5 build*Prompt 函数 | ✅ |
| AI 直写 + 用户方向两种模式 | Task 5 `rewriteMode` | ✅ |
| 多轮修改 | Task 5 `handleIterate` | ✅ |
| 覆盖率 word_export ≥ 85% | Task 3 check | ✅ |
| 覆盖率 router ≥ 70% | Task 3 check | ✅ |
| 不实现历史记录 | 无对应任务 | ✅（不做） |
| 不修复有序列表 bug | Task 1 注释说明 | ✅（保留） |

---

## 注意事项

1. **TaskJob 字段确认**：Step 2.3 里的 `TaskJob(task_no=..., input_payload=..., started_at=..., finished_at=...)` 依赖这些字段存在，执行前务必运行确认命令。
2. **operator_token fixture**：若 `tests/integration/conftest.py` 中已有 `operator_token` fixture，跳过 Step 2.1 的追加步骤。
3. **yunwu provider**：代码中 `yunwu_adapter.chat_stream` 默认 provider 为 `"yunwu"`，与 benchmark 保持一致。若本地 Key 池用不同 provider，在 `chatStream` 调用中加 `provider=...` 参数。
4. **冻结区改动**：Task 3（main.py）和 Task 6（App.tsx / WorkspacePage.tsx）改动冻结区文件，改完必须跑全量回归。
