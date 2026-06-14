# 千川剪辑预审（qianchuan-edit-review）迁移实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧版 Next.js 独立工具迁移到新平台，新增 JWT 鉴权和报告持久化，功能 100% 还原。

**Architecture:** 后端 5 个新路由文件（截帧/转录/流式对话/导出Word/保存报告），挂 `/api/tools/` 前缀；前端新增 API 模块 + 页面组件 + 路由注册；一个数据库迁移脚本注册工具入口。

**Tech Stack:** FastAPI · asyncio subprocess · httpx · python-docx · yunwu adapter · React 19 · Ant Design 5 · Vite

---

## 文件清单

### 新建（后端）
- `backend/app/routers/tool_extract_frames.py` — ffmpeg截帧接口
- `backend/app/routers/tool_transcribe.py` — Whisper转录接口
- `backend/app/routers/tool_chat_stream.py` — 多模态SSE流式接口
- `backend/app/routers/tool_export_word.py` — Word导出接口
- `backend/app/routers/tool_qianchuan_edit_review.py` — 保存报告到outputs表
- `backend/migrations/019_qianchuan_edit_review.sql` — 注册workspace_tools入口
- `backend/tests/integration/routers/test_tool_extract_frames.py`
- `backend/tests/integration/routers/test_tool_transcribe.py`
- `backend/tests/integration/routers/test_tool_chat_stream.py`
- `backend/tests/integration/routers/test_tool_export_word.py`
- `backend/tests/integration/routers/test_tool_qianchuan_edit_review.py`

### 修改（后端）
- `backend/app/main.py` — 注册 5 个新路由
- `backend/tests/conftest.py` — `_SESSION_LOCAL_PATCH_TARGETS` 新增 2 条

### 新建（前端）
- `frontend/src/api/qianchuanEditReview.ts` — 5 个接口封装
- `frontend/src/pages/operator/QianChuanEditReviewPage.tsx` — 主页面

### 修改（前端）
- `frontend/src/App.tsx` — 新增路由 `/workspace/qianchuan-edit-review`

---

## Task 1: 数据库迁移 — 注册工具入口

**Files:**
- Create: `backend/migrations/019_qianchuan_edit_review.sql`

- [ ] **Step 1: 创建迁移文件**

```sql
-- 019_qianchuan_edit_review.sql
-- 注册千川剪辑预审工具到 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
  'qianchuan-edit-review',
  '千川剪辑预审',
  '千川',
  '上传原版爆款与我方成片，AI看画面+文案，给出剪辑和画面插入建议',
  'online',
  '["AI生成","千川","剪辑","多模态","docx"]'::jsonb,
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools WHERE category = '千川')
)
ON CONFLICT (tool_code) DO NOTHING;
```

- [ ] **Step 2: 执行迁移**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 -f migrations/019_qianchuan_edit_review.sql
```

预期输出：`INSERT 0 1`（或 `INSERT 0 0` 若已存在）

- [ ] **Step 3: 验证**

```bash
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 -c \
  "SELECT tool_code, tool_name, category, status FROM workspace_tools WHERE tool_code='qianchuan-edit-review';"
```

预期：返回 1 行，status=online。

---

## Task 2: 后端 — 截帧接口

**Files:**
- Create: `backend/app/routers/tool_extract_frames.py`
- Create: `backend/tests/integration/routers/test_tool_extract_frames.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/integration/routers/test_tool_extract_frames.py`：

```python
"""Integration tests for tool_extract_frames router."""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/extract-frames",
            files={"file": ("v.mp4", b"fake", "video/mp4")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_file_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/extract-frames",
            data={"count": "3"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422  # FastAPI validation: file field missing


class TestExtractFrames:
    @pytest.mark.asyncio
    async def test_returns_frames_and_duration(self, test_client, operator_token):
        fake_frame_b64 = "data:image/jpeg;base64,/9j/fake"

        async def mock_extract(video_path, count):
            return [{"time": 0.0, "base64": fake_frame_b64}], 10.5

        with patch(
            "app.routers.tool_extract_frames._extract_frames",
            side_effect=mock_extract,
        ):
            resp = await test_client.post(
                "/api/tools/extract-frames",
                files={"file": ("v.mp4", b"fake_video_bytes", "video/mp4")},
                data={"count": "3"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "frames" in body
        assert "duration" in body
        assert body["duration"] == 10.5
        assert len(body["frames"]) == 1
        assert body["frames"][0]["base64"] == fake_frame_b64

    @pytest.mark.asyncio
    async def test_ffprobe_failure_returns_400(self, test_client, operator_token):
        async def mock_extract_fail(video_path, count):
            raise ValueError("无法读取视频时长")

        with patch(
            "app.routers.tool_extract_frames._extract_frames",
            side_effect=mock_extract_fail,
        ):
            resp = await test_client.post(
                "/api/tools/extract-frames",
                files={"file": ("v.mp4", b"bad_video", "video/mp4")},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/integration/routers/test_tool_extract_frames.py -v
```

预期：FAILED（ImportError 或 404，因为路由未创建）

- [ ] **Step 3: 实现截帧路由**

创建 `backend/app/routers/tool_extract_frames.py`：

```python
"""
app/routers/tool_extract_frames.py

POST /api/tools/extract-frames
接收视频文件，用 ffmpeg 截帧，返回 base64 帧列表。
"""
import asyncio
import base64
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_TOTAL_TIMEOUT = 60  # 总截帧超时（秒）
_FRAME_TIMEOUT = 10  # 单帧 ffmpeg 超时（秒）


async def _extract_frames(
    video_path: str,
    count: int,
) -> tuple[list[dict], float]:
    """
    用 ffprobe 读时长，再逐帧 ffmpeg 截图，返回 (frames, duration)。
    frames: [{"time": float, "base64": "data:image/jpeg;base64,..."}]
    失败时抛 ValueError。
    """
    # 1. ffprobe 读时长
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=15)
    except asyncio.TimeoutError:
        raise ValueError("ffprobe 超时")

    duration_str = stdout.decode().strip()
    try:
        duration = float(duration_str)
    except ValueError:
        raise ValueError("无法读取视频时长")
    if duration <= 0:
        raise ValueError("无法读取视频时长")

    # 2. 计算截帧时间点：固定 0s/1s/2s + 剩余均匀分布
    fixed = [0.0, 1.0, 2.0]
    times: list[float] = [t for t in fixed if t < duration]
    if duration > 4 and count > len(times):
        remaining = count - len(times)
        step = (duration - 3.0) / (remaining + 1)
        for i in range(1, remaining + 1):
            t = min(3.0 + step * i, duration - 0.1)
            times.append(round(t, 1))
    times = times[:count]

    # 3. 逐帧截图
    tmp_dir = Path(f"/tmp/frames-{uuid.uuid4()}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict] = []

    try:
        for t in times:
            out_path = tmp_dir / f"frame_{t:.2f}.jpg"
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-ss", f"{t:.2f}",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "3",
                "-vf", "scale='min(720,iw)':-2",
                str(out_path),
                "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=_FRAME_TIMEOUT)
            except asyncio.TimeoutError:
                continue  # 跳过超时帧

            if out_path.exists():
                img_bytes = out_path.read_bytes()
                b64 = base64.b64encode(img_bytes).decode()
                frames.append({
                    "time": round(t, 1),
                    "base64": f"data:image/jpeg;base64,{b64}",
                })
                out_path.unlink(missing_ok=True)
    finally:
        # 清理临时目录（失败也忽略）
        try:
            video_file = Path(video_path)
            if video_file.exists():
                video_file.unlink()
            tmp_dir.rmdir()
        except Exception:
            pass

    return frames, round(duration, 1)


@router.post("/extract-frames")
async def extract_frames(
    file: UploadFile = File(...),
    count: int = Form(default=8),
    current_user: User = Depends(require_password_changed),
):
    """截帧接口：接收视频，返回 base64 帧列表和时长。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "请上传视频文件"})

    # 保存到临时文件
    ext = Path(file.filename).suffix or ".mp4"
    tmp_dir = Path(f"/tmp/frames-{uuid.uuid4()}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(tmp_dir / f"input{ext}")

    content = await file.read()
    Path(video_path).write_bytes(content)

    try:
        frames, duration = await asyncio.wait_for(
            _extract_frames(video_path, count),
            timeout=_TOTAL_TIMEOUT,
        )
    except (ValueError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=400, detail={"code": "EXTRACT_FAILED", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": f"截帧失败: {e}"})

    return {"frames": frames, "duration": duration}
```

- [ ] **Step 4: 注册路由到 main.py**

在 `backend/app/main.py` 中添加（在现有 router imports 末尾）：

```python
from app.routers.tool_extract_frames import router as tool_extract_frames_router
```

在 `app.include_router(admin_qianchuan_review_router, prefix="/api")` 之后添加：

```python
app.include_router(tool_extract_frames_router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/integration/routers/test_tool_extract_frames.py -v
```

预期：3 个测试全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/tool_extract_frames.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_tool_extract_frames.py \
        backend/migrations/019_qianchuan_edit_review.sql
git commit -m "feat: add extract-frames API and DB migration for qianchuan-edit-review"
```

---

## Task 3: 后端 — 转录接口

**Files:**
- Create: `backend/app/routers/tool_transcribe.py`
- Create: `backend/tests/integration/routers/test_tool_transcribe.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/integration/routers/test_tool_transcribe.py`：

```python
"""Integration tests for tool_transcribe router."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/transcribe",
            files={"file": ("v.mp4", b"fake", "video/mp4")},
        )
        assert resp.status_code == 401


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_file_too_large_returns_400(self, test_client, operator_token):
        # 26MB fake file
        big_content = b"x" * (26 * 1024 * 1024)
        resp = await test_client.post(
            "/api/tools/transcribe",
            files={"file": ("big.mp4", big_content, "video/mp4")},
            data={"language": "zh"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_success_returns_text(self, test_client, operator_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "这是转录的文字内容"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.routers.tool_transcribe.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.post(
                "/api/tools/transcribe",
                files={"file": ("v.mp4", b"fake_video", "video/mp4")},
                data={"language": "zh"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert resp.json()["text"] == "这是转录的文字内容"

    @pytest.mark.asyncio
    async def test_upstream_429_retries_and_fails(self, test_client, operator_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.routers.tool_transcribe.httpx.AsyncClient", return_value=mock_client), \
             patch("app.routers.tool_transcribe.asyncio.sleep", new_callable=AsyncMock):
            resp = await test_client.post(
                "/api/tools/transcribe",
                files={"file": ("v.mp4", b"fake_video", "video/mp4")},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 502
        # 验证重试了 3 次
        assert mock_client.post.call_count == 3
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/integration/routers/test_tool_transcribe.py -v
```

预期：FAILED（404，路由未创建）

- [ ] **Step 3: 实现转录路由**

创建 `backend/app/routers/tool_transcribe.py`：

```python
"""
app/routers/tool_transcribe.py

POST /api/tools/transcribe
接收视频文件，调云雾 Whisper 转录，返回文字。
"""
import asyncio
import os

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_MAX_SIZE = 25 * 1024 * 1024  # 25MB
_RETRY_DELAYS = [3, 6, 9]      # 429 重试间隔（秒）
_TIMEOUT = 120                  # httpx 超时


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    current_user: User = Depends(require_password_changed),
):
    """转录接口：接收视频，调云雾 Whisper，返回文字。"""
    content = await file.read()

    if len(content) > _MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": "文件不能超过 25MB"},
        )

    api_key = os.environ.get("YUNWU_API_KEY", "")
    base_url = os.environ.get("YUNWU_BASE_URL", "https://yunwu.ai/v1")
    url = f"{base_url}/audio/transcriptions"

    last_resp = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)

            form_data = {
                "model": (None, "gpt-4o-transcribe"),
                "language": (None, language),
                "file": (file.filename or "audio.mp4", content, "application/octet-stream"),
            }
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files=form_data,
            )
            last_resp = resp

            if resp.status_code == 429:
                if attempt < len(_RETRY_DELAYS):
                    continue
            break

    if last_resp is None or last_resp.status_code != 200:
        status_code = last_resp.status_code if last_resp else 0
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_ERROR", "message": f"转录失败（{status_code}），请稍后重试"},
        )

    result = last_resp.json()
    return {"text": result.get("text", "")}
```

- [ ] **Step 4: 注册路由到 main.py**

在 `backend/app/main.py` 的 imports 区域添加：

```python
from app.routers.tool_transcribe import router as tool_transcribe_router
```

在 `app.include_router(tool_extract_frames_router, prefix="/api")` 之后添加：

```python
app.include_router(tool_transcribe_router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/integration/routers/test_tool_transcribe.py -v
```

预期：4 个测试全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/tool_transcribe.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_tool_transcribe.py
git commit -m "feat: add transcribe API for qianchuan-edit-review"
```

---

## Task 4: 后端 — 多模态流式对话接口

**Files:**
- Create: `backend/app/routers/tool_chat_stream.py`
- Create: `backend/tests/integration/routers/test_tool_chat_stream.py`
- Modify: `backend/tests/conftest.py:46-66`（新增 patch target）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/integration/routers/test_tool_chat_stream.py`：

```python
"""Integration tests for tool_chat_stream router."""
from unittest.mock import AsyncMock, patch

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "system_prompt": "你是专家",
                "model": "gpt-4o",
                "max_tokens": 100,
            },
        )
        assert resp.status_code == 401


class TestChatStream:
    @pytest.mark.asyncio
    async def test_system_prompt_prepended(self, test_client, operator_token):
        """验证 system_prompt 被拼入 messages 首位。"""
        captured_messages = []

        async def fake_stream(messages, db, model_id, user_id, feature, max_tokens, **kwargs):
            captured_messages.extend(messages)
            yield "chunk1"
            yield "chunk2"

        with patch("app.routers.tool_chat_stream.yunwu_adapter.chat_stream", side_effect=fake_stream):
            resp = await test_client.post(
                "/api/tools/chat-stream",
                json={
                    "messages": [{"role": "user", "content": "分析这个视频"}],
                    "system_prompt": "你是千川剪辑预审专家",
                    "model": "gpt-4o",
                    "max_tokens": 8000,
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[0]["content"] == "你是千川剪辑预审专家"
        assert captured_messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [],
                "system_prompt": "你是专家",
                "model": "gpt-4o",
                "max_tokens": 8000,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_system_prompt_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "system_prompt": "  ",
                "model": "gpt-4o",
                "max_tokens": 8000,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/integration/routers/test_tool_chat_stream.py -v
```

预期：FAILED（404）

- [ ] **Step 3: 实现 chat-stream 路由**

创建 `backend/app/routers/tool_chat_stream.py`：

```python
"""
app/routers/tool_chat_stream.py

POST /api/tools/chat-stream
通用多模态 SSE 流式接口，透传 messages + system_prompt 给 yunwu.chat_stream()。
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_RETRY_DELAYS = [2, 4, 6]  # 429 重试间隔（秒）


class ChatStreamRequest(BaseModel):
    messages: list[dict]
    system_prompt: str
    model: str = "gpt-4o"
    max_tokens: int = 8000


@router.post("/chat-stream")
async def chat_stream(
    body: ChatStreamRequest,
    current_user: User = Depends(require_password_changed),
):
    """多模态流式接口：拼 system_prompt → 调 yunwu.chat_stream → StreamingResponse。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if not body.system_prompt.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "system_prompt 不能为空"},
        )

    messages = [{"role": "system", "content": body.system_prompt}] + body.messages
    user_id = current_user.id
    model_id = body.model
    max_tokens = body.max_tokens

    async def generate():
        delays = [0] + _RETRY_DELAYS
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
                        feature="qianchuan_edit_review_chat",
                        max_tokens=max_tokens,
                    ):
                        yield chunk
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(delays) - 1:
                    continue
                yield f"\n\n[ERROR] {str(e)}"
                return

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )
```

- [ ] **Step 4: 注册路由 + 更新 conftest.py**

在 `backend/app/main.py` 添加：

```python
from app.routers.tool_chat_stream import router as tool_chat_stream_router
```

```python
app.include_router(tool_chat_stream_router, prefix="/api")
```

在 `backend/tests/conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS` 列表中，在最后一个条目之后添加：

```python
    "app.routers.tool_chat_stream.AsyncSessionLocal",
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/integration/routers/test_tool_chat_stream.py -v
```

预期：4 个测试全部 PASSED

- [ ] **Step 6: 确认守卫测试仍通过**

```bash
pytest tests/integration/test_convention_guard.py -v
```

预期：全部 PASSED（#7 红线：conftest 已注册新路由）

- [ ] **Step 7: 提交**

```bash
git add backend/app/routers/tool_chat_stream.py \
        backend/app/main.py \
        backend/tests/conftest.py \
        backend/tests/integration/routers/test_tool_chat_stream.py
git commit -m "feat: add chat-stream API for multimodal SSE streaming"
```

---

## Task 5: 后端 — Word 导出接口

**Files:**
- Create: `backend/app/routers/tool_export_word.py`
- Create: `backend/tests/integration/routers/test_tool_export_word.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/integration/routers/test_tool_export_word.py`：

```python
"""Integration tests for tool_export_word router."""
import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "# 标题\n内容", "title": "测试报告"},
        )
        assert resp.status_code == 401


class TestExportWord:
    @pytest.mark.asyncio
    async def test_returns_docx_file(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "# 开头剪辑\n\n## 时长与删减\n\n- 删掉第5秒到第8秒", "title": "千川剪辑预审报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "application/vnd.openxmlformats" in resp.headers["content-type"]
        assert "content-disposition" in resp.headers
        assert "千川预审报告_" in resp.headers["content-disposition"]
        assert len(resp.content) > 1000  # 有效的 docx 文件应大于 1KB

    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "", "title": "报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_default_title_when_omitted(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "## 节奏问题\n\n内容很好"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "千川预审报告_" in resp.headers["content-disposition"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/integration/routers/test_tool_export_word.py -v
```

预期：FAILED（404）

- [ ] **Step 3: 实现 export-word 路由**

创建 `backend/app/routers/tool_export_word.py`：

```python
"""
app/routers/tool_export_word.py

POST /api/tools/export-word
接收 Markdown 报告文本，生成 Word 文档并返回文件流。
"""
import io
import re
from datetime import datetime, timezone

import pytz
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_FONT = "微软雅黑"
_BODY_SIZE = 22  # half-points = 11pt


def _set_font(run, size_hpt: int | None = None) -> None:
    run.font.name = _FONT
    run.element.rPr.rFonts.set(qn("w:eastAsia"), _FONT)
    if size_hpt is not None:
        run.font.size = Pt(size_hpt / 2)


def _parse_inline(para, text: str) -> None:
    """将 **bold** 解析为加粗 run，其余为普通 run。"""
    parts = re.split(r"(\*\*.*?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = para.add_run(part[2:-2])
            run.bold = True
        else:
            run = para.add_run(part)
        _set_font(run, _BODY_SIZE)


def _markdown_to_doc(doc: Document, content: str) -> None:
    for line in content.split("\n"):
        stripped = line.rstrip()

        if stripped == "":
            doc.add_paragraph()
            continue

        # H1/H2/H3
        h_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h_match:
            level = len(h_match.group(1))
            spacings = {1: (240, 120), 2: (200, 100), 3: (160, 80)}
            before, after = spacings[level]
            p = doc.add_heading(h_match.group(2), level=level)
            p.paragraph_format.space_before = Pt(before / 20)
            p.paragraph_format.space_after = Pt(after / 20)
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", stripped):
            text = re.sub(r"^[-*]\s+", "", stripped)
            try:
                para = doc.add_paragraph(style="List Bullet")
            except KeyError:
                para = doc.add_paragraph()
            _parse_inline(para, text)
            continue

        # 引用
        if stripped.startswith("> "):
            text = stripped[2:]
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Pt(18)
            run = para.add_run(text)
            run.italic = True
            run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            _set_font(run, _BODY_SIZE)
            continue

        # 普通段落
        para = doc.add_paragraph()
        _parse_inline(para, stripped)


class ExportWordRequest(BaseModel):
    content: str
    title: str = "千川剪辑预审报告"


@router.post("/export-word")
async def export_word(
    body: ExportWordRequest,
    current_user: User = Depends(require_password_changed),
):
    """Word 导出接口：Markdown → .docx 文件流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "内容为空"},
        )

    doc = Document()

    # 标题（居中）
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(body.title)
    title_run.bold = True
    _set_font(title_run, 32)

    # 导出时间（居中，Asia/Shanghai）
    tz = pytz.timezone("Asia/Shanghai")
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    time_para = doc.add_paragraph()
    time_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    time_run = time_para.add_run(f"导出时间：{now_str}")
    _set_font(time_run, 20)

    doc.add_paragraph()  # 间隔行

    _markdown_to_doc(doc, body.content)

    buf = io.BytesIO()
    doc.save(buf)
    file_bytes = buf.getvalue()

    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"千川预审报告_{date_str}.docx"
    from urllib.parse import quote
    encoded = quote(filename)

    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
```

> **注意**：`pytz` 已在 requirements.txt 中（被其他模块使用）。如没有，在 requirements.txt 中追加 `pytz`。

- [ ] **Step 4: 确认 pytz 依赖**

```bash
grep "pytz" /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/requirements.txt
```

若无输出，执行：
```bash
echo "pytz" >> /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/requirements.txt
pip install pytz
```

- [ ] **Step 5: 注册路由到 main.py**

```python
from app.routers.tool_export_word import router as tool_export_word_router
```

```python
app.include_router(tool_export_word_router, prefix="/api")
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
pytest tests/integration/routers/test_tool_export_word.py -v
```

预期：4 个测试全部 PASSED

- [ ] **Step 7: 提交**

```bash
git add backend/app/routers/tool_export_word.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_tool_export_word.py
git commit -m "feat: add export-word API for qianchuan-edit-review"
```

---

## Task 6: 后端 — 保存报告接口

**Files:**
- Create: `backend/app/routers/tool_qianchuan_edit_review.py`
- Create: `backend/tests/integration/routers/test_tool_qianchuan_edit_review.py`
- Modify: `backend/tests/conftest.py`（新增 patch target，如路由使用 AsyncSessionLocal）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/integration/routers/test_tool_qianchuan_edit_review.py`：

```python
"""Integration tests for tool_qianchuan_edit_review router."""
import pytest
from sqlalchemy import text


class TestAuth:
    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={"title": "测试报告", "report": "报告内容"},
        )
        assert resp.status_code == 401


class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_returns_standard_envelope(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "千川剪辑预审_2026-06-14",
                "report": "## 开头剪辑\n\n建议从第2秒切入",
                "original_duration": 32.5,
                "ours_duration": 28.0,
                "original_frame_count": 8,
                "ours_frame_count": 8,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "id" in body["data"]
        assert "created_at" in body["data"]

    @pytest.mark.asyncio
    async def test_save_writes_to_outputs_table(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "测试标题",
                "report": "报告正文内容",
                "original_duration": 10.0,
                "ours_duration": 12.0,
                "original_frame_count": 5,
                "ours_frame_count": 6,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        output_id = resp.json()["data"]["id"]
        row = (await test_session.execute(
            text("SELECT tool_code, tool_name, title, content, word_count, content_json FROM outputs WHERE id=:id"),
            {"id": output_id},
        )).fetchone()

        assert row is not None
        assert row[0] == "qianchuan-edit-review"
        assert row[1] == "千川剪辑预审"
        assert row[2] == "测试标题"
        assert row[3] == "报告正文内容"
        assert row[4] == len("报告正文内容")
        assert row[5]["original_duration"] == 10.0

    @pytest.mark.asyncio
    async def test_save_writes_operation_log(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "日志测试",
                "report": "内容",
                "original_duration": 5.0,
                "ours_duration": 5.0,
                "original_frame_count": 3,
                "ours_frame_count": 3,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        output_id = resp.json()["data"]["id"]

        log = (await test_session.execute(
            text("SELECT action, target_type, target_id FROM operation_logs WHERE target_id=:id AND target_type='output'"),
            {"id": output_id},
        )).fetchone()

        assert log is not None
        assert log[0] == "qianchuan_edit_review_save_output"

    @pytest.mark.asyncio
    async def test_empty_report_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={"title": "标题", "report": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/integration/routers/test_tool_qianchuan_edit_review.py -v
```

预期：FAILED（404）

- [ ] **Step 3: 实现保存报告路由**

创建 `backend/app/routers/tool_qianchuan_edit_review.py`：

```python
"""
app/routers/tool_qianchuan_edit_review.py

POST /api/tools/qianchuan-edit-review/outputs
保存剪辑预审报告到 outputs 表。
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_password_changed
from app.models.log import OperationLog
from app.models.output import Output
from app.models.user import User

router = APIRouter(prefix="/tools/qianchuan-edit-review", tags=["qianchuan-edit-review"])

TOOL_CODE = "qianchuan-edit-review"
TOOL_NAME = "千川剪辑预审"


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SaveOutputRequest(BaseModel):
    title: str
    report: str
    original_duration: float = 0.0
    ours_duration: float = 0.0
    original_frame_count: int = 0
    ours_frame_count: int = 0


@router.post("/outputs")
async def save_output(
    request: Request,
    body: SaveOutputRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_password_changed),
):
    """保存剪辑预审报告到 outputs 表。"""
    if not body.report.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "报告内容不能为空"},
        )

    output = Output(
        title=body.title or TOOL_NAME,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.report,
        content_json={
            "original_duration": body.original_duration,
            "ours_duration": body.ours_duration,
            "original_frame_count": body.original_frame_count,
            "ours_frame_count": body.ours_frame_count,
        },
        word_count=len(body.report),
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_edit_review_save_output",
        target_type="output",
        target_id=output.id,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(output)

    return success_response(data={
        "id": output.id,
        "created_at": output.created_at.isoformat(),
    })
```

- [ ] **Step 4: 注册路由到 main.py**

```python
from app.routers.tool_qianchuan_edit_review import router as tool_qianchuan_edit_review_router
```

```python
app.include_router(tool_qianchuan_edit_review_router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/integration/routers/test_tool_qianchuan_edit_review.py -v
```

预期：5 个测试全部 PASSED

- [ ] **Step 6: 运行守卫测试**

```bash
pytest tests/integration/test_convention_guard.py -v
```

预期：全部 PASSED（红线 #1 #2 均满足）

- [ ] **Step 7: 提交**

```bash
git add backend/app/routers/tool_qianchuan_edit_review.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_tool_qianchuan_edit_review.py
git commit -m "feat: add save-output API for qianchuan-edit-review (red-line #1 #2 compliant)"
```

---

## Task 7: 后端 — 全量测试验收

- [ ] **Step 1: 运行全部后端测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/ -v --tb=short 2>&1 | tail -30
```

预期：无新增失败（只关注新增的失败，不要求解决历史问题）

- [ ] **Step 2: 确认守卫全通过**

```bash
pytest tests/integration/test_convention_guard.py -v
```

预期：全部 PASSED

---

## Task 8: 前端 — API 模块

**Files:**
- Create: `frontend/src/api/qianchuanEditReview.ts`

- [ ] **Step 1: 创建 API 模块**

创建 `frontend/src/api/qianchuanEditReview.ts`：

```typescript
/**
 * qianchuanEditReview.ts
 * 千川剪辑预审工具的接口封装。
 *
 * fetch 例外说明（红线 #3）：
 *   - extractFrames: FormData 上传
 *   - transcribeVideo: FormData 上传
 *   - chatStream: SSE 流式（getReader）
 *   - exportWord: Blob 下载（.blob()）
 *   - saveOutput: 走 request.ts（标准 JSON）
 */
import { post } from './request'
import { useAuthStore } from '../store/authStore'

// authStore 路径：frontend/src/store/authStore.ts（注意是 store，不是 stores）

export interface Frame {
  time: number
  base64: string
}

export interface ExtractFramesResult {
  frames: Frame[]
  duration: number
}

export interface SaveOutputBody {
  title: string
  report: string
  original_duration: number
  ours_duration: number
  original_frame_count: number
  ours_frame_count: number
}

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** 截帧：FormData 上传，原生 fetch（例外：FormData）*/
export async function extractFrames(file: File, count = 8): Promise<ExtractFramesResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('count', String(count))

  const resp = await fetch('/api/tools/extract-frames', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '截帧失败')
  }
  return resp.json()
}

/** 转录：FormData 上传，原生 fetch（例外：FormData）*/
export async function transcribeVideo(file: File, language = 'zh'): Promise<{ text: string }> {
  const form = new FormData()
  form.append('file', file)
  form.append('language', language)

  const resp = await fetch('/api/tools/transcribe', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '转录失败')
  }
  return resp.json()
}

/** 流式预审：SSE 读取，原生 fetch（例外：getReader）*/
export function chatStream(
  messages: Array<{ role: string; content: unknown }>,
  systemPrompt: string,
  model = 'gpt-4o',
  maxTokens = 8000,
): Promise<Response> {
  return fetch('/api/tools/chat-stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ messages, system_prompt: systemPrompt, model, max_tokens: maxTokens }),
  })
}

/** 导出 Word：Blob 下载，原生 fetch（例外：.blob()）*/
export async function exportWord(content: string, title = '千川剪辑预审报告'): Promise<Blob> {
  const resp = await fetch('/api/tools/export-word', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ content, title }),
  })
  if (!resp.ok) throw new Error('导出失败')
  return resp.blob()
}

/** 保存报告：标准 JSON，走 request.ts（红线 #3）*/
export function saveOutput(body: SaveOutputBody): Promise<{ id: number; created_at: string }> {
  return post<{ id: number; created_at: string }>('/api/tools/qianchuan-edit-review/outputs', body)
}
```

- [ ] **Step 2: 运行前端守卫测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx vitest run src/__tests__/unit/api/conventionGuard.test.ts
```

预期：PASSED（所有 fetch 调用均有例外标注）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/qianchuanEditReview.ts
git commit -m "feat: add qianchuanEditReview API module (red-line #3 compliant)"
```

---

## Task 9: 前端 — 页面组件

**Files:**
- Create: `frontend/src/pages/operator/QianChuanEditReviewPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 检查 authStore token 字段名**

```bash
grep -n "token\|getToken\|accessToken" /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend/src/stores/authStore.ts | head -10
```

确认 `useAuthStore.getState().token` 的字段名正确，如不同需同步修改 `qianchuanEditReview.ts` 中的 `getAuthHeaders`。

- [ ] **Step 2: 创建页面组件**

创建 `frontend/src/pages/operator/QianChuanEditReviewPage.tsx`：

```tsx
import { useState, useRef } from 'react'
import { Button, message } from 'antd'
import { DownloadOutlined, SaveOutlined } from '@ant-design/icons'
import {
  extractFrames,
  transcribeVideo,
  chatStream,
  exportWord,
  saveOutput,
  type Frame,
} from '../../api/qianchuanEditReview'

/* ── System Prompt（硬编码，随请求传后端）── */
const SYSTEM_PROMPT = `你是千川广告剪辑预审专家。视频已经拍完，现在是剪辑阶段。你会同时看到两条视频的**文案转录**和**关键帧截图**（标注了时间戳）。

结合文案和画面一起分析，对比「原版爆款」和「我方版本」，给出剪辑层面的优化建议。

严格限制：文案内容、拍摄角度、演员表演已经无法修改。只提以下剪辑能做的调整：
- 删减/压缩片段（砍掉哪一段，精确到哪句话、第几秒）
- 调整片段顺序（把哪段提前/延后）
- 节奏调整（哪里加快/放慢、转场节奏）
- 字幕/花字建议（哪里加强调字幕、什么样式）
- BGM/音效建议
- 开头剪辑（前3秒怎么剪更抓人）
- **画面插入建议**（在哪个位置插入什么类型的画面，如产品特写、使用效果、对比画面、文字卡片、用户评价截图等）

## 输出格式

### 开头剪辑（前三秒）
原版开头：[画面+文案怎么切入]
我方开头：[画面+文案怎么切入]
剪辑建议：[具体怎么改，比如从第X秒切入、插入什么画面]

### 时长与删减
原版约X秒 vs 我方约X秒，[需要砍掉哪些段落，精确到第几秒到第几秒]

### 节奏问题
[哪里拖沓需要加速、哪里信息太密需要留白、转场是否流畅]

### 画面插入建议
[在第X秒处插入什么画面（产品特写/效果对比/使用场景/文字卡片等），为什么要插]

### 核心问题 Top 3
1. [一句话，限定在剪辑+画面插入能改的范围]
2. [一句话]
3. [一句话]

### 剪辑修改清单
1. [具体操作：剪什么/插什么/调什么]
2. [具体操作]
3. [具体操作]
4. [如有需要继续]

要求：每句话都要有信息量，不要废话。所有建议必须是剪辑师能直接执行的，不要说"重拍""重写文案"。`

/* ── Markdown 渲染（简版，与旧版一致）── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.*)/g, '<h3 style="font-weight:bold;font-size:14px;margin:16px 0 4px">$1</h3>')
    .replace(/## (.*)/g, '<h2 style="font-weight:bold;font-size:16px;margin:20px 0 8px">$1</h2>')
    .replace(/# (.*)/g, '<h1 style="font-weight:bold;font-size:18px;margin:24px 0 8px">$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n(\d+)\. /g, '<br/>$1. ')
    .replace(/\n\n/g, '</p><p style="margin-top:8px">')
    .replace(/\n/g, '<br/>')
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.7 }}
      dangerouslySetInnerHTML={{ __html: `<p>${html}</p>` }}
    />
  )
}

/* ── Types ── */
interface VideoSide {
  file: File | null
  transcript: string
  frames: Frame[]
  duration: number
}

const EMPTY_SIDE: VideoSide = { file: null, transcript: '', frames: [], duration: 0 }

/* ── Main Component ── */
export default function QianChuanEditReviewPage() {
  const [original, setOriginal] = useState<VideoSide>({ ...EMPTY_SIDE })
  const [ours, setOurs] = useState<VideoSide>({ ...EMPTY_SIDE })
  const [processing, setProcessing] = useState<Record<string, string>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [report, setReport] = useState('')
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const reportRef = useRef<HTMLDivElement>(null)

  /* ── 处理视频（截帧 + 转录）── */
  async function processVideo(side: 'original' | 'ours') {
    const data = side === 'original' ? original : ours
    const setter = side === 'original' ? setOriginal : setOurs
    if (!data.file) { message.error('请先上传视频文件'); return }

    setProcessing(prev => ({ ...prev, [side]: '截帧中...' }))

    try {
      const frameResult = await extractFrames(data.file, 8)
      setter(prev => ({ ...prev, frames: frameResult.frames, duration: frameResult.duration }))

      setProcessing(prev => ({ ...prev, [side]: '转录文案中...' }))
      const transResult = await transcribeVideo(data.file, 'zh')
      setter(prev => ({ ...prev, transcript: transResult.text }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : '处理失败')
    } finally {
      setProcessing(prev => { const n = { ...prev }; delete n[side]; return n })
    }
  }

  /* ── 构建多模态消息（完全保留旧版逻辑）── */
  function buildMessage() {
    const parts: Array<{ type: string; text?: string; image_url?: { url: string } }> = []

    let text = `## 原版爆款素材\n**时长**：${original.duration ? `${original.duration}秒` : '未知'}\n**文案**：\n${original.transcript || '未提供'}\n\n`
    if (original.frames.length > 0) {
      text += `**原版关键帧**（${original.frames.length}帧）：\n`
      parts.push({ type: 'text', text })
      original.frames.forEach(f => {
        parts.push({ type: 'text', text: `原版 第${f.time}秒：` })
        parts.push({ type: 'image_url', image_url: { url: f.base64 } })
      })
    } else {
      parts.push({ type: 'text', text })
    }

    text = `\n---\n\n## 我方版本（已拍摄完成）\n**时长**：${ours.duration ? `${ours.duration}秒` : '未知'}\n**文案**：\n${ours.transcript || '未提供'}\n\n`
    if (ours.frames.length > 0) {
      text += `**我方关键帧**（${ours.frames.length}帧）：\n`
      parts.push({ type: 'text', text })
      ours.frames.forEach(f => {
        parts.push({ type: 'text', text: `我方 第${f.time}秒：` })
        parts.push({ type: 'image_url', image_url: { url: f.base64 } })
      })
    } else {
      parts.push({ type: 'text', text })
    }

    return parts
  }

  /* ── 开始预审 ── */
  async function analyze() {
    if (!original.transcript && !ours.transcript && original.frames.length === 0 && ours.frames.length === 0) {
      message.error('请先处理视频（截帧+转录）再预审')
      return
    }
    setAnalyzing(true)
    setReport('')

    try {
      const resp = await chatStream(
        [{ role: 'user', content: buildMessage() }],
        SYSTEM_PROMPT,
        'gpt-4o',
        8000,
      )
      if (!resp.ok) throw new Error('AI 分析请求失败')

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应')

      const decoder = new TextDecoder()
      let fullText = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        fullText += decoder.decode(value, { stream: true })
        setReport(fullText)
      }
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '分析出错')
    } finally {
      setAnalyzing(false)
    }
  }

  /* ── 导出 Word ── */
  async function handleExportWord() {
    if (!report) return
    setExporting(true)
    try {
      const blob = await exportWord(report, '千川剪辑预审报告')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `千川剪辑预审_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

  /* ── 保存报告 ── */
  async function handleSave() {
    if (!report) return
    setSaving(true)
    try {
      await saveOutput({
        title: `千川剪辑预审_${new Date().toISOString().slice(0, 10)}`,
        report,
        original_duration: original.duration,
        ours_duration: ours.duration,
        original_frame_count: original.frames.length,
        ours_frame_count: ours.frames.length,
      })
      message.success('报告已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  /* ── 渲染单侧面板 ── */
  function renderSide(side: 'original' | 'ours') {
    const data = side === 'original' ? original : ours
    const setter = side === 'original' ? setOriginal : setOurs
    const label = side === 'original' ? '原版爆款' : '我方成片'
    const isProcessing = !!processing[side]
    const statusText = processing[side] || ''

    const colors = side === 'original'
      ? { border: '#6ee7b7', dot: '#10b981', text: '#065f46', btn: '#059669', btnHover: '#047857' }
      : { border: '#93c5fd', dot: '#3b82f6', text: '#1e3a8a', btn: '#2563eb', btnHover: '#1d4ed8' }

    return (
      <div style={{
        flex: 1,
        border: `2px solid ${colors.border}`,
        borderRadius: 12,
        padding: 20,
        background: '#fff',
      }}>
        <h2 style={{ color: colors.text, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 12, height: 12, borderRadius: '50%', background: colors.dot, display: 'inline-block' }} />
          {label}
        </h2>

        {/* 视频上传区 */}
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              border: '2px dashed #d1d5db',
              borderRadius: 8,
              padding: 16,
              textAlign: 'center',
              cursor: 'pointer',
              background: '#fafafa',
            }}
            onClick={() => document.getElementById(`file-${side}`)?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              const f = e.dataTransfer.files[0]
              if (f && f.type.startsWith('video/')) {
                setter(prev => ({ ...prev, file: f, transcript: '', frames: [], duration: 0 }))
              }
            }}
          >
            <input
              id={`file-${side}`}
              type="file"
              accept="video/*"
              style={{ display: 'none' }}
              onChange={e => {
                const f = e.target.files?.[0] || null
                if (f) setter(prev => ({ ...prev, file: f, transcript: '', frames: [], duration: 0 }))
                else setter({ ...EMPTY_SIDE })
              }}
            />
            {data.file ? (
              <div style={{ fontSize: 13, color: '#374151' }}>
                {data.file.name}{' '}
                <span style={{ color: '#9ca3af' }}>({(data.file.size / 1024 / 1024).toFixed(1)}MB)</span>
                {data.duration > 0 && <span style={{ color: '#9ca3af' }}> · {data.duration}秒</span>}
                <button
                  style={{ marginLeft: 8, color: '#f87171', background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={e => { e.stopPropagation(); setter({ ...EMPTY_SIDE }) }}
                >✕</button>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: '#9ca3af' }}>拖入或点击上传视频（最大25MB）</div>
            )}
          </div>

          {data.file && (
            <Button
              type="primary"
              block
              style={{ marginTop: 8, background: isProcessing ? '#9ca3af' : colors.btn }}
              disabled={isProcessing}
              onClick={() => processVideo(side)}
            >
              {isProcessing ? statusText : data.frames.length > 0 ? '重新处理' : '截帧 + 提取文案'}
            </Button>
          )}
        </div>

        {/* 截帧预览 */}
        {data.frames.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>已提取 {data.frames.length} 帧截图</div>
            <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 4 }}>
              {data.frames.slice(0, 5).map((f, i) => (
                <img
                  key={i}
                  src={f.base64}
                  alt={`${f.time}s`}
                  style={{ height: 48, borderRadius: 4, border: '1px solid #e5e7eb', flexShrink: 0 }}
                  title={`${f.time}秒`}
                />
              ))}
              {data.frames.length > 5 && (
                <div style={{
                  height: 48, width: 48, borderRadius: 4, border: '1px solid #e5e7eb',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, color: '#9ca3af', flexShrink: 0,
                }}>
                  +{data.frames.length - 5}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 文案文本框 */}
        <div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>文案内容</div>
          <textarea
            style={{
              width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
              borderRadius: 8, fontSize: 13, height: 112, resize: 'vertical',
              boxSizing: 'border-box', outline: 'none', fontFamily: 'inherit',
            }}
            placeholder="点击上方按钮自动提取，或直接粘贴文案..."
            value={data.transcript}
            onChange={e => setter(prev => ({ ...prev, transcript: e.target.value }))}
          />
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 'bold', color: '#1f2937', margin: 0 }}>千川剪辑预审</h1>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>上传两个视频，AI看画面+文案，给出剪辑和画面插入建议</p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        {renderSide('original')}
        {renderSide('ours')}
      </div>

      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <Button
          type="primary"
          size="large"
          style={{
            padding: '0 32px',
            height: 48,
            fontSize: 16,
            fontWeight: 'bold',
            background: analyzing ? '#9ca3af' : 'linear-gradient(to right, #2563eb, #4f46e5)',
            border: 'none',
          }}
          disabled={analyzing}
          onClick={analyze}
        >
          {analyzing ? '正在预审...' : '开始预审'}
        </Button>
      </div>

      {report && (
        <div ref={reportRef} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 17, fontWeight: 'bold', color: '#1f2937', margin: 0 }}>剪辑预审报告</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                icon={<DownloadOutlined />}
                style={{ background: exporting ? '#9ca3af' : '#16a34a', color: '#fff', border: 'none' }}
                disabled={exporting}
                onClick={handleExportWord}
              >
                {exporting ? '导出中...' : '导出 Word'}
              </Button>
              <Button
                icon={<SaveOutlined />}
                type="primary"
                disabled={saving}
                onClick={handleSave}
              >
                {saving ? '保存中...' : '保存报告'}
              </Button>
            </div>
          </div>
          <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 16 }}>
            <SimpleMarkdown text={report} />
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 注册路由到 App.tsx**

在 `frontend/src/App.tsx` 的 import 区域末尾添加：

```tsx
import QianChuanEditReviewPage from './pages/operator/QianChuanEditReviewPage';
```

在 `<Route path="/workspace/qianchuan-review" ...` 附近添加（保持千川工具路由聚在一起）：

```tsx
<Route path="/workspace/qianchuan-edit-review" element={<QianChuanEditReviewPage />} />
```

- [ ] **Step 4: 运行前端类型检查**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx tsc --noEmit
```

预期：无错误或仅有与本次改动无关的已有错误

- [ ] **Step 5: 运行前端守卫测试**

```bash
npx vitest run src/__tests__/unit/api/conventionGuard.test.ts
```

预期：PASSED

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/qianchuanEditReview.ts \
        frontend/src/pages/operator/QianChuanEditReviewPage.tsx \
        frontend/src/App.tsx
git commit -m "feat: add QianChuanEditReviewPage and route registration"
```

---

## Task 10: 集成验证

- [ ] **Step 1: 重启后端确认路由注册**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
curl -s http://localhost:8000/api/tools/extract-frames 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail', {}).get('code','?'))"
```

预期：`METHOD_NOT_ALLOWED` 或 `UNAUTHORIZED`（说明路由存在且鉴权生效）

- [ ] **Step 2: 检查工具在工作台中显示**

```bash
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 -c \
  "SELECT tool_code, tool_name, status FROM workspace_tools WHERE tool_code='qianchuan-edit-review';"
```

预期：返回 1 行

- [ ] **Step 3: 运行全部后端测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
pytest tests/ -v --tb=short -q 2>&1 | tail -20
```

- [ ] **Step 4: 运行全部前端测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx vitest run
```

- [ ] **Step 5: 最终提交**

```bash
git add docs/superpowers/specs/2026-06-14-qianchuan-edit-review-design.md \
        docs/superpowers/plans/2026-06-14-qianchuan-edit-review.md
git commit -m "docs: add design and implementation plan for qianchuan-edit-review migration"
```
