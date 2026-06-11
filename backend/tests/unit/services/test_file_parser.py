"""
Unit tests for file_parser service.
"""
import io

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.file_parser import parse_uploaded_file, MAX_CHARS


def _make_upload_file(filename: str, content: bytes) -> MagicMock:
    """创建 mock UploadFile。"""
    f = MagicMock()
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


@pytest.mark.asyncio
async def test_parse_txt_file():
    f = _make_upload_file("test.txt", "你好世界".encode("utf-8"))
    result = await parse_uploaded_file(f)
    assert result == "你好世界"


@pytest.mark.asyncio
async def test_parse_md_file():
    f = _make_upload_file("notes.md", "# 标题\n内容".encode("utf-8"))
    result = await parse_uploaded_file(f)
    assert "# 标题" in result
    assert "内容" in result


@pytest.mark.asyncio
async def test_parse_txt_truncation():
    long_text = "A" * 20000
    f = _make_upload_file("long.txt", long_text.encode("utf-8"))
    result = await parse_uploaded_file(f)
    assert len(result) == MAX_CHARS


@pytest.mark.asyncio
async def test_parse_unsupported_format():
    f = _make_upload_file("image.jpg", b"\xff\xd8\xff")
    with pytest.raises(ValueError, match="不支持的文件格式"):
        await parse_uploaded_file(f)


@pytest.mark.asyncio
async def test_parse_no_extension():
    f = _make_upload_file("README", b"content")
    with pytest.raises(ValueError, match="不支持的文件格式"):
        await parse_uploaded_file(f)
