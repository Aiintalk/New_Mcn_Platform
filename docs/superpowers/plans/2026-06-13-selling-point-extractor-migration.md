# selling-point-extractor 迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧架构 Node.js 产品卖点提取器迁移到新 FastAPI+React 平台，加 JWT 认证、Prompt/模型管理端可配置、历史记录存 outputs 表、产出接入产出中心。

**Architecture:** 后端新增 `selling_point_config` 表（复用 benchmark_configs 模式存 Prompt+模型）、`operator_selling_point.py` router（5 个接口）、扩展 `file_parser.py`（新增 .pages/.doc/pdfplumber 支持）。前端新增 `SellingPointPage.tsx`（运营端 3 步页面）+ `SellingPointConfigTab.tsx`（管理端配置）。

**Tech Stack:** FastAPI · SQLAlchemy asyncpg · PostgreSQL · React 19 · TypeScript · Ant Design 5 · pdfplumber · python-snappy

---

## 文件清单

### 新建
| 文件 | 说明 |
|------|------|
| `backend/migrations/015_selling_point_extractor.sql` | 建表 + 插入初始配置 + workspace_tools 注册 |
| `backend/app/models/selling_point.py` | SellingPointConfig ORM 模型 |
| `backend/app/routers/operator_selling_point.py` | 运营端 5 个接口 |
| `backend/app/routers/admin_selling_point.py` | 管理端配置接口（GET/PUT configs） |
| `backend/tests/unit/services/test_selling_point_file_parser.py` | file_parser 单元测试 |
| `backend/tests/integration/routers/test_operator_selling_point.py` | router 集成测试 |
| `backend/tests/integration/routers/test_admin_selling_point.py` | 管理端 router 测试 |
| `frontend/src/types/sellingPoint.ts` | TS 类型定义 |
| `frontend/src/api/sellingPoint.ts` | API 封装（chat/parseFile/history/adminConfig） |
| `frontend/src/pages/operator/SellingPointPage.tsx` | 运营端 3 步页面 |
| `frontend/src/pages/admin/SellingPointConfigTab.tsx` | 管理端配置 Tab |

### 修改
| 文件 | 修改内容 |
|------|---------|
| `backend/app/services/file_parser.py` | 新增 `parse_selling_point_file()` + `.pages`/`.doc`/pdfplumber |
| `backend/app/main.py` | 注册两个新 router |
| `frontend/src/App.tsx` | 新增路由 `/workspace/selling-point-extractor` |
| `frontend/src/pages/operator/WorkspacePage.tsx` | 新增 tool_code 跳转 |
| `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | 新增「产品卖点提取器」Tab |

---

## Task 1: 数据库迁移 + ORM 模型

**Files:**
- Create: `backend/migrations/015_selling_point_extractor.sql`
- Create: `backend/app/models/selling_point.py`

- [ ] **Step 1: 创建迁移 SQL 文件**

```sql
-- backend/migrations/015_selling_point_extractor.sql

-- 1. 配置表（Prompt + 模型，管理端可配置）
CREATE TABLE selling_point_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_selling_point_configs_updated BEFORE UPDATE ON selling_point_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. 初始配置（原 System Prompt 原文）
INSERT INTO selling_point_configs (config_key, system_prompt, is_active) VALUES
('extract', '你是一个专业的产品卖点提取专家，专门为短视频带货场景提炼产品卖点。

用户会提供以下资料（部分可选）：
1. **产品Brief**：品牌方提供的产品介绍资料（可能有多份文档）
2. **达人文案脚本**：头部达人讲解该产品的视频文案（可能有多份文案）

---

## 输出要求

直接输出一张极致卖点卡，不要输出任何分析过程、维度拆解、评分或中间步骤。

---

## 🔥 极致卖点卡

按以下四个板块输出，每个板块最多2句话，只写结论，不解释原因：

**【机制】**
提取最强的价格机制和赠品信息，直接写出来。没有则写"无特别机制"。

**【背书】**
提取最强的明星/权威认证/渠道背书，直接写出来。没有则写"暂无权威背书"。

**【口碑】**
提取用户使用时长、复购数据、真实反馈，直接写出来。没有则写"暂无口碑数据"。

**【产品力】**
第一句：列出核心成分或配方组合（只写名称，不解释作用）。
第二句：用2-3个感知词概括配方覆盖的维度，如"防、抗、补都全了"——根据产品自行提炼，不套模板。
严禁出现任何功效宣称，禁止"减少/促进/抑制/改善/修复/对抗"等动词。

---

## 规则

- 从资料中提取真实信息，不编造
- 多份文档综合分析，不只看第一份
- 如果只有Brief没有文案，最后补一句「建议补充达人文案以丰富口碑板块」', true);

-- 3. 注册到 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'selling-point-extractor',
    '产品卖点提取器',
    '选题分析',
    '上传产品Brief + 达人文案，AI提炼机制/背书/口碑/产品力四板块极致卖点卡，支持多轮追问，导出.md',
    'online',
    '["AI生成","卖点提炼","Brief分析","文档上传"]'::jsonb,
    3
)
ON CONFLICT (tool_code) DO UPDATE
    SET status = 'online',
        tool_name = EXCLUDED.tool_name,
        description = EXCLUDED.description,
        tags = EXCLUDED.tags;
```

- [ ] **Step 2: 执行迁移**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
PGPASSWORD=admin123 psql -U mcn_user -h localhost -p 5432 -d mcn_m1 \
  -f backend/migrations/015_selling_point_extractor.sql
```

Expected output:
```
CREATE TABLE
CREATE TRIGGER
INSERT 0 1
INSERT 0 1
```

- [ ] **Step 3: 创建 ORM 模型**

```python
# backend/app/models/selling_point.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class SellingPointConfig(Base):
    """管理端配置（Prompt + 模型）"""
    __tablename__ = "selling_point_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: 注册模型到 models/__init__.py**

查看现有 `backend/app/models/__init__.py` 后追加：
```python
from app.models.selling_point import SellingPointConfig  # noqa: F401
```

- [ ] **Step 5: 验证表已创建**

```bash
PGPASSWORD=admin123 psql -U mcn_user -h localhost -p 5432 -d mcn_m1 \
  -c "\d selling_point_configs"
```

Expected: 显示表结构（6 列）。

- [ ] **Step 6: Commit**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/migrations/015_selling_point_extractor.sql \
        backend/app/models/selling_point.py \
        backend/app/models/__init__.py
git commit -m "feat: add selling_point_configs table and ORM model"
```

---

## Task 2: 扩展 file_parser.py（selling-point 专用解析函数）

**Files:**
- Modify: `backend/app/services/file_parser.py`
- Test: `backend/tests/unit/services/test_selling_point_file_parser.py`

> 注意：`parse_selling_point_file()` 是独立新函数，不改动已有 `parse_uploaded_file()`。
> .pages 解析：中文字符 ≥5 保留，无日历噪音过滤（与 livestream-writer 不同）。

- [ ] **Step 1: 安装依赖**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pip install pdfplumber python-snappy
```

Expected: `Successfully installed pdfplumber-... python-snappy-...`

- [ ] **Step 2: 先写失败测试**

```python
# backend/tests/unit/services/test_selling_point_file_parser.py
"""Unit tests for parse_selling_point_file（selling-point 专用解析函数）"""
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.file_parser import parse_selling_point_file


def _mock_file(filename: str, content: bytes) -> MagicMock:
    f = MagicMock()
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


# ---------- txt / md ----------

@pytest.mark.asyncio
async def test_txt_returns_text():
    result = await parse_selling_point_file(_mock_file("brief.txt", "产品卖点内容".encode()))
    assert result == "产品卖点内容"

@pytest.mark.asyncio
async def test_md_returns_text():
    result = await parse_selling_point_file(_mock_file("script.md", "# 标题\n内容".encode()))
    assert "标题" in result

@pytest.mark.asyncio
async def test_txt_no_truncation():
    """selling-point 版本不截断（原版截断 8000）"""
    long = "中文内容" * 5000
    result = await parse_selling_point_file(_mock_file("long.txt", long.encode()))
    assert len(result) == len(long)

# ---------- docx ----------

@pytest.mark.asyncio
async def test_docx_extracts_paragraphs():
    from docx import Document
    doc = Document()
    doc.add_paragraph("第一段卖点")
    doc.add_paragraph("第二段说明")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    result = await parse_selling_point_file(_mock_file("brief.docx", buf.read()))
    assert "第一段卖点" in result
    assert "第二段说明" in result

# ---------- pdf (pdfplumber) ----------

@pytest.mark.asyncio
async def test_pdf_extracts_text():
    import unittest.mock as mock
    import pdfplumber
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "玻尿酸、烟酰胺"
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    with mock.patch("app.services.file_parser.pdfplumber") as mp:
        mp.open.return_value = mock_pdf
        result = await parse_selling_point_file(_mock_file("product.pdf", b"%PDF"))
    assert "玻尿酸" in result

# ---------- .doc ----------

@pytest.mark.asyncio
async def test_doc_returns_hint():
    result = await parse_selling_point_file(_mock_file("old.doc", b"\xd0\xcf\x11"))
    assert ".doc 格式暂不支持" in result

# ---------- .pages ----------

def _make_pages_zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Index/Document.iwa", b"\x00\x00\x00\x00" + text.encode())
    buf.seek(0)
    return buf.read()

@pytest.mark.asyncio
async def test_pages_extracts_chinese():
    pages_bytes = _make_pages_zip("这是一段产品卖点说明，超过十个中文字的内容测试。")
    result = await parse_selling_point_file(_mock_file("doc.pages", pages_bytes))
    assert "产品卖点" in result

@pytest.mark.asyncio
async def test_pages_filters_short_chinese():
    """中文 <5 的片段应被过滤"""
    pages_bytes = _make_pages_zip("ab两字" + "A" * 20)
    result = await parse_selling_point_file(_mock_file("noise.pages", pages_bytes))
    assert "两字" not in result

@pytest.mark.asyncio
async def test_pages_no_calendar_filter():
    """selling-point 不过滤日历型中文，和 livestream-writer 不同"""
    pages_bytes = _make_pages_zip("一月二月三月四月五月六月七月八月")
    result = await parse_selling_point_file(_mock_file("cal.pages", pages_bytes))
    assert "一月" in result

@pytest.mark.asyncio
async def test_pages_missing_iwa():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dummy.txt", "nothing")
    buf.seek(0)
    result = await parse_selling_point_file(_mock_file("empty.pages", buf.read()))
    assert "格式异常" in result

@pytest.mark.asyncio
async def test_pages_invalid_zip():
    result = await parse_selling_point_file(_mock_file("bad.pages", b"not a zip"))
    assert "格式异常" in result

# ---------- 未知格式 ----------

@pytest.mark.asyncio
async def test_unknown_ext_utf8_decode():
    result = await parse_selling_point_file(_mock_file("data.csv", "产品名,价格\n精华,299".encode()))
    assert "精华" in result
```

- [ ] **Step 3: 运行，确认失败**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/unit/services/test_selling_point_file_parser.py -v 2>&1 | head -20
```

Expected: `ImportError` 或 `FAILED`（函数未定义）。

- [ ] **Step 4: 在 file_parser.py 末尾追加实现**

在 `backend/app/services/file_parser.py` 文件顶部的 `import io` 后追加 `import re` 和 `import pdfplumber`，然后在文件末尾追加：

```python
# 在文件顶部 import io 下面加：
import re
import pdfplumber

# 在文件末尾追加：

# ---------------------------------------------------------------------------
# selling-point-extractor 专用解析函数（独立，不改动 parse_uploaded_file）
# ---------------------------------------------------------------------------

async def parse_selling_point_file(file: UploadFile) -> str:
    """
    selling-point-extractor 专用文件解析，返回纯文本（无截断）。

    支持：.txt / .md / .docx / .pdf（pdfplumber）/ .pages（zipfile+snappy）
          .doc（返回提示文本）/ 其他（UTF-8 解码）
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_bytes = await file.read()

    if ext in ("txt", "md"):
        return content_bytes.decode("utf-8", errors="replace")
    elif ext == "docx":
        return _parse_docx(content_bytes)
    elif ext == "pdf":
        return _parse_pdf_plumber(content_bytes)
    elif ext == "pages":
        return _parse_pages_selling_point(content_bytes)
    elif ext == "doc":
        return "[.doc 格式暂不支持，请转换为 .docx 或 .pdf 后上传]"
    else:
        return content_bytes.decode("utf-8", errors="replace")


def _parse_pdf_plumber(content: bytes) -> str:
    """用 pdfplumber 提取文本。"""
    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texts.append(page_text)
    return "\n".join(texts)


def _parse_pages_selling_point(content: bytes) -> str:
    """
    解析 Apple Pages 文件（selling-point 版本）。
    过滤条件：中文字符 ≥5（无日历噪音过滤）。
    """
    import zipfile
    try:
        import snappy
    except ImportError:
        import cramjam as snappy  # type: ignore

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            try:
                iwa_data = zf.read("Index/Document.iwa")
            except KeyError:
                return "[.pages 文件格式异常，未找到文档内容]"
    except zipfile.BadZipFile:
        return "[.pages 文件格式异常，无法解压]"

    try:
        decompressed = snappy.decompress(iwa_data[4:])
        if isinstance(decompressed, memoryview):
            decompressed = bytes(decompressed)
    except Exception:
        decompressed = iwa_data

    raw = decompressed.decode("utf-8", errors="ignore")
    pattern = (
        r"[一-鿿　-〿＀-￯，。！？、；：""''（）【】《》"
        r"a-zA-Z0-9\s%.+\-·\/…]{10,}"
    )
    segments = re.findall(pattern, raw)
    result = []
    for s in segments:
        s = s.strip()
        if len(re.findall(r"[一-鿿]", s)) >= 5:
            result.append(s)
    return "\n".join(result)
```

- [ ] **Step 5: 运行测试，确认全部通过**

```bash
pytest tests/unit/services/test_selling_point_file_parser.py -v
```

Expected: 所有测试 PASSED。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/file_parser.py \
        backend/tests/unit/services/test_selling_point_file_parser.py
git commit -m "feat: add parse_selling_point_file with .pages/.doc/pdfplumber support"
```

---

## Task 3: 后端管理端 Router（admin_selling_point.py）

**Files:**
- Create: `backend/app/routers/admin_selling_point.py`
- Test: `backend/tests/integration/routers/test_admin_selling_point.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/integration/routers/test_admin_selling_point.py
"""Integration tests for admin_selling_point router."""
import pytest
from sqlalchemy import text


class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/selling-point/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_config_list(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/selling-point/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert any(c["config_key"] == "extract" for c in data["data"])


class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": "new prompt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_system_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": "更新后的 Prompt 内容", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        row = (await test_session.execute(
            text("SELECT system_prompt FROM selling_point_configs WHERE config_key='extract'")
        )).fetchone()
        assert row[0] == "更新后的 Prompt 内容"

    @pytest.mark.asyncio
    async def test_update_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/nonexistent",
            json={"system_prompt": "x"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/integration/routers/test_admin_selling_point.py -v 2>&1 | head -10
```

Expected: `FAILED`（路由未注册）。

- [ ] **Step 3: 实现 admin_selling_point.py**

```python
# backend/app/routers/admin_selling_point.py
"""
管理端接口（admin 角色）：
  GET /api/admin/selling-point/configs        — 配置列表
  PUT /api/admin/selling-point/configs/{key}  — 更新配置
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.selling_point import SellingPointConfig
from app.models.user import User

router = APIRouter(prefix="/admin/selling-point", tags=["admin-selling-point"])


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(SellingPointConfig))).scalars().all()
    return success_response(data=[
        {
            "id": c.id,
            "config_key": c.config_key,
            "ai_model_id": c.ai_model_id,
            "system_prompt": c.system_prompt,
            "is_active": c.is_active,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
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
        update(SellingPointConfig)
        .where(SellingPointConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(SellingPointConfig.id)
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

在 `backend/app/main.py` 中追加：
```python
from app.routers.admin_selling_point import router as admin_selling_point_router
# ...在 include_router 列表末尾：
app.include_router(admin_selling_point_router, prefix="/api")
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/integration/routers/test_admin_selling_point.py -v
```

Expected: 所有测试 PASSED。

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin_selling_point.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_admin_selling_point.py
git commit -m "feat: add admin selling-point config router (GET/PUT)"
```

---

## Task 4: 后端运营端 Router（operator_selling_point.py）

**Files:**
- Create: `backend/app/routers/operator_selling_point.py`
- Test: `backend/tests/integration/routers/test_operator_selling_point.py`

> 核心：chat 接口从 DB 读取 Prompt 和 model_id，不再硬编码。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/integration/routers/test_operator_selling_point.py
"""Integration tests for operator_selling_point router."""
import io
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from sqlalchemy import text


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/selling-point-extractor/history")
        assert resp.status_code == 401


# ---------- Chat ----------

class TestChat:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_config_not_found_returns_503(self, test_client, operator_token, test_session):
        """配置不存在或未激活时返回 503。"""
        await test_session.execute(
            text("UPDATE selling_point_configs SET is_active=false WHERE config_key='extract'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": [{"role": "user", "content": "分析"}]},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 503

        # 恢复
        await test_session.execute(
            text("UPDATE selling_point_configs SET is_active=true WHERE config_key='extract'")
        )
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_chat_streams_plain_text(self, test_client, operator_token):
        async def mock_stream(*args, **kwargs):
            for chunk in ["【机制】", "无特别机制"]:
                yield chunk

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析产品"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "【机制】" in resp.text


# ---------- Parse File ----------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_parse_txt(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("brief.txt", "产品卖点内容".encode(), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data and "filename" in data
        assert "产品卖点" in data["text"]

    @pytest.mark.asyncio
    async def test_parse_doc_hint(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("old.doc", b"\xd0\xcf\x11", "application/msword")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert ".doc 格式暂不支持" in resp.json()["text"]

    @pytest.mark.asyncio
    async def test_parse_docx(self, test_client, operator_token):
        from docx import Document
        doc = Document()
        doc.add_paragraph("玻尿酸保湿成分")
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("p.docx", buf.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "玻尿酸" in resp.json()["text"]


# ---------- History ----------

class TestHistory:
    @pytest.mark.asyncio
    async def test_save_and_list(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='selling-point-extractor'")
        )
        await test_session.commit()

        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"productName": "测试产品", "result": "卖点卡内容测试"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["success"] is True

        list_resp = await test_client.get(
            "/api/tools/selling-point-extractor/history",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert list_resp.status_code == 200
        records = list_resp.json()["records"]
        assert any(r["productName"] == "测试产品" for r in records)

    @pytest.mark.asyncio
    async def test_save_and_get_single(self, test_client, operator_token):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={
                "productName": "单条测试",
                "result": "完整卖点卡内容",
                "chatHistory": [{"role": "user", "content": "分析"}],
                "briefFiles": [{"name": "b.pdf", "text": "说明"}],
                "scriptFiles": [],
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["id"]

        get_resp = await test_client.get(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert get_resp.status_code == 200
        rec = get_resp.json()["record"]
        assert rec["productName"] == "单条测试"
        assert len(rec["briefFiles"]) == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/selling-point-extractor/history?id=999999",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete(self, test_client, operator_token, test_session):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"productName": "待删除", "result": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["id"]

        del_resp = await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert del_resp.status_code == 200

        row = (await test_session.execute(
            text(f"SELECT deleted_at FROM outputs WHERE id={record_id}")
        )).fetchone()
        assert row[0] is not None  # 软删除，物理记录仍在

        get_resp = await test_client.get(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_result_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/integration/routers/test_operator_selling_point.py -v 2>&1 | head -10
```

Expected: FAILED（路由未注册）。

- [ ] **Step 3: 实现 operator_selling_point.py**

```python
# backend/app/routers/operator_selling_point.py
"""
运营端接口（JWT 鉴权，operator / admin）：
  POST   /api/tools/selling-point-extractor/chat        — AI 流式对话
  POST   /api/tools/selling-point-extractor/parse-file  — 文件解析
  GET    /api/tools/selling-point-extractor/history     — 查询历史列表 / 单条
  POST   /api/tools/selling-point-extractor/history     — 保存历史记录
  DELETE /api/tools/selling-point-extractor/history     — 软删除
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.middlewares.auth import get_current_user
from app.models.output import Output
from app.models.selling_point import SellingPointConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_selling_point_file

router = APIRouter(prefix="/tools/selling-point-extractor", tags=["selling-point-extractor"])

TOOL_CODE = "selling-point-extractor"
TOOL_NAME = "产品卖点提取器"
CONFIG_KEY = "extract"


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


async def _get_active_config(db: AsyncSession) -> SellingPointConfig:
    """从 DB 读取激活的配置，不存在则抛 503。"""
    config = (await db.execute(
        select(SellingPointConfig)
        .where(SellingPointConfig.config_key == CONFIG_KEY)
        .where(SellingPointConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": "卖点提取配置未激活，请联系管理员"},
        )
    return config


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )

    config = await _get_active_config(db)

    # 取模型 ID：配置有绑定则用，否则用平台默认
    ai_model = None
    if config.ai_model_id:
        from app.models.log import AiModel  # 避免循环 import
        from sqlalchemy import select as sa_select
        ai_model = (await db.execute(
            sa_select(AiModel).where(AiModel.id == config.ai_model_id)
        )).scalar_one_or_none()

    model_id = ai_model.model_id if ai_model else "claude-sonnet-4-6"
    system_prompt = config.system_prompt or ""
    messages = [{"role": "system", "content": system_prompt}] + body.messages
    user_id = current_user.id

    async def generate():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    user_id=user_id,
                    feature="selling_point_chat",
                    max_tokens=8192,
                ):
                    yield chunk
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def write_task_job():
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"SP-{int(time.time())}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "briefFileCount": sum(
                        1 for m in body.messages
                        if m.get("role") == "user" and "产品Brief" in m.get("content", "")
                    ),
                    "scriptFileCount": sum(
                        1 for m in body.messages
                        if m.get("role") == "user" and "达人文案脚本" in m.get("content", "")
                    ),
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    try:
        text = await parse_selling_point_file(file)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        )
    return {"text": text, "filename": file.filename}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class SaveHistoryRequest(BaseModel):
    productName: str = "未命名产品"
    result: str
    chatHistory: list[dict] = []
    briefFiles: list[dict] = []
    scriptFiles: list[dict] = []


@router.get("/history")
async def get_history(
    id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if id is not None:
        row = await db.get(Output, id)
        if row is None or row.deleted_at is not None or row.tool_code != TOOL_CODE:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "记录不存在"},
            )
        cj = row.content_json or {}
        return {
            "record": {
                "id": str(row.id),
                "productName": row.title,
                "result": row.content or "",
                "chatHistory": cj.get("chatHistory", []),
                "briefFiles": cj.get("briefFiles", []),
                "scriptFiles": cj.get("scriptFiles", []),
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        }

    rows = (await db.execute(
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
        .order_by(Output.created_at.desc())
    )).scalars().all()

    return {
        "records": [
            {
                "id": str(r.id),
                "productName": r.title,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
                "summary": (r.content or "")[:100].replace("\n", " ") + "..."
                if r.content and len(r.content) > 100 else (r.content or ""),
            }
            for r in rows
        ]
    }


@router.post("/history")
async def save_history(
    body: SaveHistoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.result.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "result 不能为空"},
        )
    output = Output(
        title=body.productName or "未命名产品",
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.result,
        content_json={
            "chatHistory": body.chatHistory,
            "briefFiles": body.briefFiles,
            "scriptFiles": body.scriptFiles,
        },
        word_count=len(body.result),
        created_by=current_user.id,
    )
    db.add(output)
    await db.commit()
    await db.refresh(output)
    return {"success": True, "id": str(output.id)}


@router.delete("/history")
async def delete_history(
    id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    row = await db.get(Output, id)
    if row is None or row.deleted_at is not None or row.tool_code != TOOL_CODE:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "记录不存在"},
        )
    row.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}
```

> 注意：`AiModel` 在 `app/models/log.py` 中定义，需确认路径，若不对则改为正确路径。

- [ ] **Step 4: 注册到 main.py**

在 `backend/app/main.py` 追加：
```python
from app.routers.operator_selling_point import router as operator_selling_point_router
# ...
app.include_router(operator_selling_point_router, prefix="/api")
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/integration/routers/test_operator_selling_point.py -v
```

Expected: 所有测试 PASSED。

- [ ] **Step 6: 确认 AiModel 路径**

```bash
grep -rn "class AiModel" backend/app/models/ backend/app/
```

若 `AiModel` 不在 `app.models.log`，修正 Task 4 Step 3 中的 import。

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/operator_selling_point.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_operator_selling_point.py
git commit -m "feat: add operator selling-point router (chat/parse-file/history)"
```

---

## Task 5: 前端类型 + API 封装

**Files:**
- Create: `frontend/src/types/sellingPoint.ts`
- Create: `frontend/src/api/sellingPoint.ts`

- [ ] **Step 1: 创建类型定义**

```typescript
// frontend/src/types/sellingPoint.ts
export interface UploadedFile {
  name: string;
  text: string;
}

export interface HistoryItem {
  id: string;
  productName: string;
  createdAt: string;
  summary: string;
}

export interface HistoryRecord {
  id: string;
  productName: string;
  result: string;
  chatHistory: Array<{ role: string; content: string }>;
  briefFiles: UploadedFile[];
  scriptFiles: UploadedFile[];
  createdAt: string;
}

export interface SellingPointConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string;
  is_active: boolean;
  updated_at: string;
}
```

- [ ] **Step 2: 创建 API 封装**

```typescript
// frontend/src/api/sellingPoint.ts
import { get, put } from './request';
import type { HistoryItem, HistoryRecord, SellingPointConfig, UploadedFile } from '../types/sellingPoint';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = '/api/tools/selling-point-extractor';

async function getToken(): Promise<string | null> {
  return (await import('../store/authStore')).useAuthStore.getState().token;
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** AI 流式对话，返回原始 Response */
export async function chatStream(messages: Array<{ role: string; content: string }>): Promise<Response> {
  const token = await getToken();
  return fetch(`${BASE_URL}${PREFIX}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ messages }),
  });
}

/** 解析上传文件 */
export async function parseFile(file: File): Promise<{ text: string; filename: string }> {
  const token = await getToken();
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch(`${BASE_URL}${PREFIX}/parse-file`, {
    method: 'POST',
    headers: authHeaders(token),
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `Parse failed: ${resp.status}`);
  }
  return resp.json();
}

/** 获取历史列表 */
export const getHistoryList = () =>
  get<{ records: HistoryItem[] }>(`${PREFIX}/history`);

/** 获取单条历史 */
export const getHistoryRecord = (id: string) =>
  get<{ record: HistoryRecord }>(`${PREFIX}/history?id=${id}`);

/** 保存历史记录 */
export async function saveHistory(body: {
  productName: string;
  result: string;
  chatHistory: Array<{ role: string; content: string }>;
  briefFiles: UploadedFile[];
  scriptFiles: UploadedFile[];
}): Promise<{ success: boolean; id: string }> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Save failed: ${resp.status}`);
  return resp.json();
}

/** 软删除历史记录 */
export async function deleteHistoryRecord(id: string): Promise<void> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/history?id=${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
}

// -- Admin API --

export const getAdminSellingPointConfigs = () =>
  get<SellingPointConfig[]>('/api/admin/selling-point/configs');

export const updateAdminSellingPointConfig = (
  key: string,
  data: { ai_model_id?: number | null; system_prompt?: string; is_active?: boolean }
) =>
  put<null>(`/api/admin/selling-point/configs/${key}`, data);
```

- [ ] **Step 3: Commit**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add frontend/src/types/sellingPoint.ts frontend/src/api/sellingPoint.ts
git commit -m "feat: add sellingPoint TS types and API client"
```

---

## Task 6: 前端运营端页面（SellingPointPage.tsx）

**Files:**
- Create: `frontend/src/pages/operator/SellingPointPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/operator/WorkspacePage.tsx`

> 逻辑与旧 page.tsx 完全一致，差异：1）调用 api/sellingPoint.ts 的封装函数；2）不再自带 SYSTEM_PROMPT（从后端接口获取，在 chat 请求中不需传，由后端从 DB 读取）；3）消息裁剪和 .md 导出保留在前端。

- [ ] **Step 1: 创建 SellingPointPage.tsx**

此文件较长，完整内容如下（基于旧 page.tsx，替换 fetch 调用为 api 封装，移除 SYSTEM_PROMPT 常量，保留其他所有逻辑）：

```tsx
// frontend/src/pages/operator/SellingPointPage.tsx
import { useState, useRef } from 'react';
import type { UploadedFile, HistoryItem, HistoryRecord } from '../../types/sellingPoint';
import {
  chatStream,
  parseFile,
  getHistoryList,
  getHistoryRecord,
  saveHistory,
  deleteHistoryRecord,
} from '../../api/sellingPoint';

interface ChatMsg { role: string; content: string }

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.*)/g, '<h3 class="text-xl font-bold mt-8 mb-3 text-gray-800">$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p class="mb-3">')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return (
    <div
      className="prose max-w-none text-[15px] leading-relaxed text-gray-700"
      dangerouslySetInnerHTML={{ __html: `<p class="mb-3">${html}</p>` }}
    />
  );
}

function extractProductName(result: string): string {
  const m = result.match(/资料概览[\s\S]*?\n([\s\S]*?)(?:\n---|\n###)/);
  if (m) {
    const text = m[1].replace(/<[^>]+>/g, '').trim();
    if (text.length > 0) return text.slice(0, 20) + (text.length > 20 ? '...' : '');
  }
  return '未命名产品';
}

function trimMessages(msgs: ChatMsg[]): ChatMsg[] {
  if (msgs.length <= 10) return msgs;
  const first = msgs[0];
  const last8 = msgs.slice(-8);
  if (last8.includes(first)) return last8;
  return [first, ...last8];
}

export default function SellingPointPage() {
  const [step, setStep] = useState(1);
  const [briefFiles, setBriefFiles] = useState<UploadedFile[]>([]);
  const [scriptFiles, setScriptFiles] = useState<UploadedFile[]>([]);
  const [briefExtra, setBriefExtra] = useState('');
  const [scriptExtra, setScriptExtra] = useState('');
  const [uploadingBrief, setUploadingBrief] = useState(false);
  const [uploadingScript, setUploadingScript] = useState(false);

  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([]);
  const [followUpResult, setFollowUpResult] = useState('');
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const briefRef = useRef<HTMLInputElement>(null);
  const scriptRef = useRef<HTMLInputElement>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const data = await getHistoryList();
      setHistoryList(data.records || []);
    } catch { setHistoryList([]); }
    finally { setHistoryLoading(false); }
  }

  async function loadHistoryRecord(id: string) {
    try {
      const data = await getHistoryRecord(id);
      if (data.record) {
        const rec: HistoryRecord = data.record;
        setResult(rec.result);
        setChatHistory(rec.chatHistory || []);
        setBriefFiles(rec.briefFiles || []);
        setScriptFiles(rec.scriptFiles || []);
        setFollowUpResult('');
        setFollowUp('');
        setShowHistory(false);
        setStep(3);
      }
    } catch { setError('加载历史记录失败'); }
  }

  async function handleDeleteHistory(id: string) {
    try {
      await deleteHistoryRecord(id);
      setHistoryList(prev => prev.filter(h => h.id !== id));
    } catch { setError('删除失败'); }
  }

  async function handleSaveHistory(analysisResult: string, history: ChatMsg[]) {
    try {
      const productName = extractProductName(analysisResult);
      await saveHistory({ productName, result: analysisResult, chatHistory: history, briefFiles, scriptFiles });
    } catch { console.error('Failed to save history'); }
  }

  async function handleFilesUpload(files: FileList, type: 'brief' | 'script') {
    const setter = type === 'brief' ? setBriefFiles : setScriptFiles;
    const setUploading = type === 'brief' ? setUploadingBrief : setUploadingScript;
    setUploading(true);
    setError('');
    for (const file of Array.from(files)) {
      try {
        const data = await parseFile(file);
        setter(prev => [...prev, { name: data.filename, text: data.text }]);
      } catch { setError(`文件 ${file.name} 上传失败`); }
    }
    setUploading(false);
    if (type === 'brief' && briefRef.current) briefRef.current.value = '';
    if (type === 'script' && scriptRef.current) scriptRef.current.value = '';
  }

  function removeFile(type: 'brief' | 'script', index: number) {
    if (type === 'brief') setBriefFiles(prev => prev.filter((_, i) => i !== index));
    else setScriptFiles(prev => prev.filter((_, i) => i !== index));
  }

  const hasBrief = briefFiles.length > 0 || briefExtra.trim();
  const hasScript = scriptFiles.length > 0 || scriptExtra.trim();

  async function handleAnalyze() {
    setLoading(true);
    setError('');
    setResult('');
    setFollowUpResult('');
    setChatHistory([]);
    setStep(3);

    let userMsg = '';
    if (hasBrief) {
      const parts: string[] = [];
      briefFiles.forEach((f, i) => parts.push(`【文档${i + 1}：${f.name}】\n${f.text}`));
      if (briefExtra.trim()) parts.push(`【补充内容】\n${briefExtra.trim()}`);
      userMsg += `## 产品Brief（共${briefFiles.length}份文档${briefExtra.trim() ? ' + 补充内容' : ''}）\n\n${parts.join('\n\n---\n\n')}\n\n`;
    }
    if (hasScript) {
      const parts: string[] = [];
      scriptFiles.forEach((f, i) => parts.push(`【文案${i + 1}：${f.name}】\n${f.text}`));
      if (scriptExtra.trim()) parts.push(`【补充内容】\n${scriptExtra.trim()}`);
      userMsg += `## 达人文案脚本（共${scriptFiles.length}份文案${scriptExtra.trim() ? ' + 补充内容' : ''}）\n\n${parts.join('\n\n---\n\n')}\n\n`;
    }
    userMsg += '请综合以上所有资料，严格按照 机制→背书→可视化→种草 的顺序逐维度分析，提炼卖点并排序。';

    try {
      const res = await chatStream([{ role: 'user', content: userMsg }]);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setResult(full);
      }
      const finalHistory: ChatMsg[] = [{ role: 'user', content: userMsg }, { role: 'assistant', content: full }];
      setChatHistory(finalHistory);
      await handleSaveHistory(full, finalHistory);
    } catch { setError('分析失败，请重试'); }
    finally { setLoading(false); }
  }

  async function handleFollowUp() {
    if (!followUp.trim() || !chatHistory.length) return;
    setFollowUpLoading(true);
    setFollowUpResult('');
    const allMessages: ChatMsg[] = [...chatHistory, { role: 'user', content: followUp }];
    const messages = trimMessages(allMessages);
    try {
      const res = await chatStream(messages);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setFollowUpResult(full);
      }
      setChatHistory([...allMessages, { role: 'assistant', content: full }]);
      setFollowUp('');
    } catch { setError('追问失败，请重试'); }
    finally { setFollowUpLoading(false); }
  }

  function handleReset() {
    setStep(1); setBriefFiles([]); setScriptFiles([]);
    setBriefExtra(''); setScriptExtra(''); setResult('');
    setError(''); setFollowUp(''); setFollowUpResult(''); setChatHistory([]);
  }

  const stepLabels = ['上传Brief', '达人文案', '卖点分析'];

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-amber-50">
      <div className="bg-gradient-to-r from-orange-500 to-amber-500 text-white">
        <div className="max-w-3xl mx-auto px-6 py-10">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-4xl">🎯</span>
            <h1 className="text-3xl font-bold tracking-tight">产品卖点提取器</h1>
          </div>
          <p className="text-orange-100 text-base">上传产品Brief + 达人文案，AI帮你提炼最炸裂的卖点</p>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="max-w-3xl mx-auto px-6 pt-8 pb-2">
        <div className="flex items-center justify-between mb-8">
          {stepLabels.map((label, i) => {
            const num = i + 1;
            const isActive = step === num;
            const isDone = step > num;
            return (
              <div key={num} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all ${isActive ? 'bg-orange-500 text-white shadow-lg shadow-orange-200' : isDone ? 'bg-orange-500 text-white' : 'bg-gray-200 text-gray-400'}`}>
                    {isDone ? '✓' : num}
                  </div>
                  <span className={`mt-2 text-xs font-medium ${isActive ? 'text-orange-600' : isDone ? 'text-orange-400' : 'text-gray-400'}`}>{label}</span>
                </div>
                {i < stepLabels.length - 1 && (
                  <div className={`h-[2px] w-full mx-2 mt-[-18px] ${step > num ? 'bg-orange-400' : 'bg-gray-200'}`} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 pb-16">
        {error && <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4 text-sm text-red-600 mb-6">{error}</div>}

        {/* History Modal */}
        {showHistory && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowHistory(false)}>
            <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
                <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2"><span>📋</span> 历史记录</h2>
                <button onClick={() => setShowHistory(false)} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {historyLoading ? <div className="text-center py-12 text-gray-400">加载中...</div>
                : historyList.length === 0 ? <div className="text-center py-12 text-gray-400">暂无历史记录</div>
                : <div className="space-y-3">
                    {historyList.map(item => (
                      <div key={item.id} className="border border-orange-100 rounded-xl p-4 hover:bg-orange-50/50 transition group">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0 cursor-pointer" onClick={() => loadHistoryRecord(item.id)}>
                            <h3 className="font-semibold text-gray-800 text-sm truncate">{item.productName}</h3>
                            <p className="text-xs text-gray-400 mt-1">{new Date(item.createdAt).toLocaleString('zh-CN')}</p>
                            <p className="text-xs text-gray-500 mt-2 line-clamp-2">{item.summary}</p>
                          </div>
                          <button onClick={e => { e.stopPropagation(); handleDeleteHistory(item.id); }} className="text-gray-300 hover:text-red-500 transition text-sm shrink-0 opacity-0 group-hover:opacity-100">删除</button>
                        </div>
                      </div>
                    ))}
                  </div>}
              </div>
            </div>
          </div>
        )}

        {/* Step 1 */}
        {step === 1 && (
          <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="w-12 h-12 rounded-xl bg-orange-100 flex items-center justify-center text-2xl">📄</span>
                <div><h2 className="text-xl font-bold text-gray-800">上传产品Brief</h2><p className="text-sm text-gray-400 mt-0.5">支持 PDF、Word、TXT 格式，可上传多个文件</p></div>
              </div>
              <button onClick={() => { setShowHistory(true); loadHistory(); }} className="text-sm text-orange-500 hover:text-orange-600 border border-orange-200 rounded-lg px-4 py-2 hover:bg-orange-50 transition flex items-center gap-1.5"><span>📋</span> 历史记录</button>
            </div>
            <input ref={briefRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple className="hidden" onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'brief'); }} />
            {briefFiles.length > 0 && (
              <div className="mb-4 space-y-2">
                {briefFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 bg-green-50 border border-green-100 rounded-xl px-4 py-3">
                    <span className="text-green-500 text-lg">✅</span>
                    <span className="text-sm text-green-700 truncate flex-1">{f.name}</span>
                    <button className="text-gray-400 hover:text-red-500 transition text-lg" onClick={() => removeFile('brief', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => briefRef.current?.click()} disabled={uploadingBrief} className="w-full border-2 border-dashed border-orange-200 rounded-xl py-8 text-base text-orange-400 hover:border-orange-400 hover:text-orange-500 hover:bg-orange-50/50 transition disabled:opacity-50 mb-5">
              {uploadingBrief ? '正在解析文件...' : briefFiles.length > 0 ? '+ 继续添加文件' : '点击上传文件（可多选）'}
            </button>
            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">也可以直接粘贴补充内容</label>
              <textarea className="w-full border border-gray-200 rounded-xl px-5 py-4 text-[15px] resize-none focus:outline-none focus:ring-2 focus:ring-orange-300 leading-relaxed" rows={6} placeholder="粘贴产品Brief内容..." value={briefExtra} onChange={e => setBriefExtra(e.target.value)} />
            </div>
            <button onClick={() => setStep(2)} className="w-full bg-gradient-to-r from-orange-500 to-amber-500 text-white font-semibold py-4 rounded-xl text-base hover:from-orange-600 hover:to-amber-600 transition shadow-lg shadow-orange-200">
              {hasBrief ? '下一步：上传达人文案' : '跳过，直接上传达人文案'}
            </button>
          </div>
        )}

        {/* Step 2 */}
        {step === 2 && (
          <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <span className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center text-2xl">🎬</span>
              <div><h2 className="text-xl font-bold text-gray-800">上传达人文案脚本</h2><p className="text-sm text-gray-400 mt-0.5">头部达人的讲解文案，可上传多个文件</p></div>
            </div>
            {hasBrief && <div className="flex items-center gap-1.5 mb-4 text-xs text-gray-400"><span>✓</span><span>Brief已就绪（{briefFiles.length}份{briefExtra.trim() ? ' + 补充' : ''}）</span></div>}
            <input ref={scriptRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple className="hidden" onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'script'); }} />
            {scriptFiles.length > 0 && (
              <div className="mb-4 space-y-2">
                {scriptFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 bg-green-50 border border-green-100 rounded-xl px-4 py-3">
                    <span className="text-green-500 text-lg">✅</span>
                    <span className="text-sm text-green-700 truncate flex-1">{f.name}</span>
                    <button className="text-gray-400 hover:text-red-500 transition text-lg" onClick={() => removeFile('script', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => scriptRef.current?.click()} disabled={uploadingScript} className={`w-full border-2 border-dashed rounded-xl py-8 text-base transition disabled:opacity-50 mb-5 ${hasScript ? 'border-amber-200 text-amber-400 hover:border-amber-400' : 'border-amber-300 text-amber-500 bg-amber-50/30 hover:border-amber-400'}`}>
              {uploadingScript ? '正在解析文件...' : scriptFiles.length > 0 ? '+ 继续添加文件' : '📎 点击上传达人文案（可多选）'}
            </button>
            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">也可以直接粘贴补充内容</label>
              <textarea className="w-full border border-gray-200 rounded-xl px-5 py-4 text-[15px] resize-none focus:outline-none focus:ring-2 focus:ring-amber-300 leading-relaxed" rows={6} placeholder="粘贴达人文案脚本..." value={scriptExtra} onChange={e => setScriptExtra(e.target.value)} />
            </div>
            <div className="flex items-center gap-4">
              <button onClick={() => setStep(1)} className="px-6 py-4 border border-gray-200 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition">上一步</button>
              <button onClick={handleAnalyze} disabled={loading || (!hasBrief && !hasScript)} className="flex-1 bg-gradient-to-r from-orange-500 to-amber-500 text-white font-semibold py-4 rounded-xl text-base hover:from-orange-600 hover:to-amber-600 transition disabled:opacity-50 shadow-lg shadow-orange-200">
                {hasScript ? '开始提取卖点' : '请先上传达人文案 ↑'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3 */}
        {step === 3 && (
          <div>
            {loading && !result && (
              <div className="bg-white rounded-2xl border border-orange-100 p-12 shadow-sm text-center">
                <svg className="animate-spin h-10 w-10 mx-auto mb-4 text-orange-500" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                <p className="text-gray-500 text-base">AI 正在分析你的产品资料...</p>
                <p className="text-gray-300 text-sm mt-2">共 {briefFiles.length + scriptFiles.length} 份文档，请稍候</p>
              </div>
            )}
            {result && (
              <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm mb-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2"><span>📊</span> 卖点分析报告</h2>
                  <button onClick={() => navigator.clipboard.writeText(result)} className="text-sm text-orange-500 hover:text-orange-600 border border-orange-200 rounded-lg px-4 py-2 hover:bg-orange-50 transition">复制全文</button>
                </div>
                <SimpleMarkdown text={result} />
              </div>
            )}
            {followUpResult && (
              <div className="bg-white rounded-2xl border border-amber-100 p-8 shadow-sm mb-6">
                <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2 mb-6"><span>💬</span> 追问回复</h2>
                <SimpleMarkdown text={followUpResult} />
              </div>
            )}
            {result && !loading && (
              <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm mb-6">
                <h3 className="text-sm font-semibold text-gray-600 mb-1">和 AI 聊聊</h3>
                <div className="flex gap-3">
                  <input type="text" className="flex-1 border border-gray-200 rounded-xl px-5 py-3.5 text-[15px] focus:outline-none focus:ring-2 focus:ring-orange-300" placeholder="比如：帮我把卖点一的话术再优化一下..." value={followUp} onChange={e => setFollowUp(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); } }} />
                  <button onClick={handleFollowUp} disabled={followUpLoading || !followUp.trim()} className="bg-orange-500 text-white px-6 py-3.5 rounded-xl text-sm font-semibold hover:bg-orange-600 transition disabled:opacity-50">
                    {followUpLoading ? '思考中...' : '发送'}
                  </button>
                </div>
              </div>
            )}
            {result && !loading && (() => {
              const source = followUpResult || result;
              const cardMatch = source.match(/(?:##\s*)?🔥\s*极致卖点卡([\s\S]*?)(?=(?:##\s*)?💡\s*AI|$)/);
              const aiMatch = source.match(/(?:##\s*)?💡\s*AI补充建议[\s\S]*$/);
              const cardContent = cardMatch ? ('## 🔥 极致卖点卡' + cardMatch[1]).trim() : '';
              const fullCard = cardContent + (aiMatch ? '\n\n' + aiMatch[0] : '');
              if (!fullCard) return null;
              return (
                <div className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl border-2 border-orange-200 p-8 shadow-sm">
                  <div className="flex items-center justify-between mb-5">
                    <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2"><span>🔥</span> 最终卖点卡</h2>
                    <div className="flex gap-2">
                      <button onClick={() => navigator.clipboard.writeText(fullCard)} className="text-sm text-orange-600 hover:text-orange-700 border border-orange-300 rounded-lg px-4 py-2 hover:bg-orange-100 transition font-medium">复制卖点卡</button>
                      <button onClick={() => { const blob = new Blob([fullCard], { type: 'text/markdown;charset=utf-8' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = '极致卖点卡.md'; a.click(); URL.revokeObjectURL(url); }} className="text-sm text-white bg-orange-500 hover:bg-orange-600 rounded-lg px-4 py-2 transition font-medium shadow-sm">保存到电脑</button>
                    </div>
                  </div>
                  <SimpleMarkdown text={fullCard} />
                </div>
              );
            })()}
            <div className="text-center mt-6"><button onClick={handleReset} className="text-sm text-gray-400 hover:text-orange-500 transition">重新开始分析新产品</button></div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 注册路由到 App.tsx**

在 `frontend/src/App.tsx` 中追加 import 和 Route：
```tsx
// import 区块末尾追加
import SellingPointPage from './pages/operator/SellingPointPage';

// Route 列表中 tiktok-writer 路由后追加
<Route path="/workspace/selling-point-extractor" element={<SellingPointPage />} />
```

- [ ] **Step 3: 更新 WorkspacePage.tsx 的跳转逻辑**

在 `frontend/src/pages/operator/WorkspacePage.tsx` 的 `handleToolClick` 函数中，在 `tiktok-writer` 分支后追加：
```tsx
else if (t.tool_code === 'selling-point-extractor') navigate('/workspace/selling-point-extractor');
```

- [ ] **Step 4: 启动前端，目视验证路由可访问**

```bash
# 确认前端服务在运行（应已启动）
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
```

Expected: `200`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/operator/SellingPointPage.tsx \
        frontend/src/App.tsx \
        frontend/src/pages/operator/WorkspacePage.tsx
git commit -m "feat: add SellingPointPage and route /workspace/selling-point-extractor"
```

---

## Task 7: 前端管理端配置 Tab（SellingPointConfigTab.tsx）

**Files:**
- Create: `frontend/src/pages/admin/SellingPointConfigTab.tsx`
- Modify: `frontend/src/pages/admin/WorkspaceConfigPage.tsx`

- [ ] **Step 1: 创建 SellingPointConfigTab.tsx**

```tsx
// frontend/src/pages/admin/SellingPointConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select, message } from 'antd';
import { getAdminSellingPointConfigs, updateAdminSellingPointConfig } from '../../api/sellingPoint';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';
import type { SellingPointConfig } from '../../types/sellingPoint';

const CONFIG_LABELS: Record<string, string> = {
  extract: '卖点提取配置',
};

export default function SellingPointConfigTab() {
  const [configs, setConfigs] = useState<SellingPointConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<SellingPointConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mds] = await Promise.all([
        getAdminSellingPointConfigs(),
        getAiModels().then(r => (r as { items?: AiModelItem[] }).items ?? r as AiModelItem[]).catch(() => [] as AiModelItem[]),
      ]);
      setConfigs(Array.isArray(cfgResp) ? cfgResp : (cfgResp as { data?: SellingPointConfig[] }).data ?? []);
      setModels(mds);
    } catch { message.error('加载配置失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  function openEdit(cfg: SellingPointConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await updateAdminSellingPointConfig(editingConfig.config_key, {
        ai_model_id: values.ai_model_id ?? null,
        system_prompt: values.system_prompt ?? undefined,
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
                      : '⚠ 未配置'}
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
          <Form.Item label="AI 模型" name="ai_model_id" rules={[{ required: true, message: '请选择模型' }]}>
            <Select
              placeholder="选择已配置的 AI 模型"
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

- [ ] **Step 2: 注册到 WorkspaceConfigPage.tsx**

```tsx
// 在 import 区块追加
import SellingPointConfigTab from './SellingPointConfigTab';

// 在 Tabs items 数组末尾追加
{ key: 'selling-point', label: '产品卖点提取器', children: <SellingPointConfigTab /> },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/admin/SellingPointConfigTab.tsx \
        frontend/src/pages/admin/WorkspaceConfigPage.tsx
git commit -m "feat: add SellingPointConfigTab to admin workspace config"
```

---

## Task 8: 全量回归测试 + 覆盖率验证

**Files:**
- 不新增文件，只运行测试

- [ ] **Step 1: 运行后端全量测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 所有测试 PASSED，无新增失败。

- [ ] **Step 2: 验证新模块覆盖率**

```bash
pytest tests/unit/services/test_selling_point_file_parser.py \
       tests/integration/routers/test_operator_selling_point.py \
       tests/integration/routers/test_admin_selling_point.py \
       --cov=app/services/file_parser \
       --cov=app/routers/operator_selling_point \
       --cov=app/routers/admin_selling_point \
       --cov-report=term-missing 2>&1 | grep -E "file_parser|operator_selling|admin_selling|TOTAL|passed|failed"
```

Expected 覆盖率目标：
- `operator_selling_point.py` ≥ 70%
- `admin_selling_point.py` ≥ 70%
- `file_parser.py`（selling-point 新增部分）≥ 80%

- [ ] **Step 3: 运行前端测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && nvm use 20
npx vitest run 2>&1 | tail -10
```

Expected: 所有测试 PASSED，无新增失败。

- [ ] **Step 4: Commit（如有测试文件未提交）**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git status
```

若有遗漏则补 commit。

---

## Task 9: 文档落地

**Files:**
- Create: `docs/pm/M2_Sprint05_selling-point-extractor_需求文档.md`
- Create: `backend/docs/tasks/M2_Sprint05_后端任务_selling-point-extractor_v1.md`
- Create: `frontend/docs/tasks/M2_Sprint05_前端任务_selling-point-extractor_v1.md`
- Create: `backend/docs/tests/M2_Sprint05_测试报告_selling-point-extractor_v1.md`
- Modify: `backend/docs/base/MCN_M2_Base_API.md`
- Modify: `docs/pm/PM_记忆与状态_M2.md`

- [ ] **Step 1: 创建需求文档**（由 PM 落地，内容基于本计划和需求文档原文）

- [ ] **Step 2: 创建后端任务单 + 前端任务单**（记录实际新增/修改文件、接口、测试结果）

- [ ] **Step 3: 创建测试报告**（记录测试用例数、覆盖率数据）

- [ ] **Step 4: 更新 MCN_M2_Base_API.md**（追加 Sprint 5 章节，5 个接口 + 管理端 2 个接口）

- [ ] **Step 5: 更新 PM_记忆与状态_M2.md**（Sprint 5 完成状态）

- [ ] **Step 6: 最终 Commit**

```bash
git add docs/ backend/docs/ frontend/docs/
git commit -m "docs: add Sprint 5 selling-point-extractor task docs and test report"
```

---

## 自检：Spec 覆盖

| 需求 | 对应 Task |
|------|----------|
| JWT 认证 | Task 3/4（require_operator） |
| Prompt/模型管理端可配置（红线 4） | Task 1（selling_point_configs 表）+ Task 3（admin router）+ Task 7（管理 Tab） |
| AI 调用走 credentials Key 池 | Task 4（yunwu_adapter.chat_stream） |
| 历史记录存 outputs 表 | Task 4（save_history → Output 表） |
| 历史全员共享 | Task 4（不加 created_by 过滤） |
| 软删除 | Task 4（deleted_at） |
| 产出接入产出中心（红线 2） | Task 1（tool_code='selling-point-extractor' 存 outputs 表，产出中心按 tool_code 展示） |
| 工具入口在创作中心（红线 1） | Task 6（WorkspacePage 跳转 + workspace_tools 注册） |
| 工具纳入功能配置（红线 5） | Task 1（workspace_tools 插入） |
| AI 调用写日志（红线 6） | Task 4（yunwu_adapter 内置写 ai_call_logs） |
| 文件解析 .pages/.doc/pdfplumber | Task 2（parse_selling_point_file） |
| 消息裁剪留前端 | Task 6（trimMessages 在 SellingPointPage） |
| .md 导出留前端 | Task 6（Blob 下载） |
| 历史记录不迁移 | 无需操作 |
| 全量回归 | Task 8 |
| 文档落地 | Task 9 |
