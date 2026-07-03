"""
yunwu.py adapter 防御性单测：
- 流式 chat_stream：SSE 含 choices:[] 帧不抛 IndexError
- 非流式 chat：响应 choices:[] 时抛 RuntimeError 而非 IndexError
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeStreamResponse:
    """模拟 httpx stream response，按行吐 SSE 帧。"""

    def __init__(self, lines: list[str], status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            from httpx import HTTPStatusError
            raise HTTPStatusError("err", request=None, response=self)

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        return _FakeStreamContext(self._response)


class _FakeNonStreamResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            from httpx import HTTPStatusError
            raise HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._data


class _FakeNonStreamClient:
    def __init__(self, response: _FakeNonStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_chat_stream_handles_empty_choices_in_trailing_chunk():
    """siliconflow 结尾帧 choices:[] 仅含 usage，不应抛 IndexError。"""
    from app.adapters import yunwu

    # 3 帧：正常 delta + usage-only 结尾帧 + [DONE]
    lines = [
        'data: ' + json.dumps({
            "choices": [{"delta": {"content": "hello"}, "index": 0}],
        }),
        'data: ' + json.dumps({
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }),
        'data: [DONE]',
    ]
    fake_resp = _FakeStreamResponse(lines)
    fake_client = _FakeAsyncClient(fake_resp)

    # mock 数据库交互
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=(1, "k", "https://example.com"))))
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    chunks = []
    with patch("httpx.AsyncClient", return_value=fake_client):
        async for chunk in yunwu.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            db=mock_db,
            model_id="Qwen3-Omni",
            provider="siliconflow",
            max_tokens=4096,
        ):
            chunks.append(chunk)

    assert chunks == ["hello"]


@pytest.mark.asyncio
async def test_chat_handles_empty_choices_in_non_stream_response():
    """非流式 chat 响应 choices:[] 时应抛 RuntimeError（含 provider 信息），而非 IndexError。"""
    from app.adapters import yunwu

    fake_resp = _FakeNonStreamResponse({
        "choices": [],
        "usage": {"prompt_tokens": 10},
    })
    fake_client = _FakeNonStreamClient(fake_resp)

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=(1, "k", "https://example.com"))))
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    with patch("httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(RuntimeError) as exc_info:
            await yunwu.chat(
                messages=[{"role": "user", "content": "hi"}],
                db=mock_db,
                model_id="test-model",
                provider="siliconflow",
                max_tokens=100,
            )
    # 错误信息包含 provider 标识，便于运维定位
    assert "siliconflow" in str(exc_info.value)
    assert "empty choices" in str(exc_info.value)
