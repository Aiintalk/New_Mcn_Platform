"""
Unit tests for document_parser.parse_files_to_text.

Covers:
- TXT file success
- PDF file (mock pypdf)
- DOCX file (mock python-docx)
- XLSX file (mock openpyxl)
- PPTX file (mock python-pptx)
- Multiple files merged
- Text truncation at 8000 chars
- All files fail → raises ValueError
"""
import io
from unittest.mock import patch, MagicMock

import pytest

from app.services.document_parser import parse_files_to_text, _MAX_TEXT_LENGTH


class _FakeUploadFile:
    """Simulates fastapi.UploadFile for testing."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_txt_file_success():
    f = _FakeUploadFile("test.txt", b"Hello World\xef\xb8\x8f")
    result = await parse_files_to_text([f])
    assert "Hello World" in result
    assert "=== 文件: test.txt ===" in result


@pytest.mark.asyncio
async def test_md_file_success():
    f = _FakeUploadFile("readme.md", b"# Title\n\nSome content")
    result = await parse_files_to_text([f])
    assert "# Title" in result


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_pdf")
async def test_pdf_file_success(mock_extract_pdf):
    mock_extract_pdf.return_value = "PDF content here"
    f = _FakeUploadFile("doc.pdf", b"fake pdf bytes")
    result = await parse_files_to_text([f])
    assert "PDF content here" in result
    assert "=== 文件: doc.pdf ===" in result


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_docx")
async def test_docx_file_success(mock_extract_docx):
    mock_extract_docx.return_value = "DOCX paragraph text"
    f = _FakeUploadFile("doc.docx", b"fake docx bytes")
    result = await parse_files_to_text([f])
    assert "DOCX paragraph text" in result


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_xlsx")
async def test_xlsx_file_success(mock_extract_xlsx):
    mock_extract_xlsx.return_value = "[Sheet1]\nA,B,C\n1,2,3"
    f = _FakeUploadFile("data.xlsx", b"fake xlsx bytes")
    result = await parse_files_to_text([f])
    assert "[Sheet1]" in result
    assert "1,2,3" in result


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_pptx")
async def test_pptx_file_success(mock_extract_pptx):
    mock_extract_pptx.return_value = "Slide 1 text Slide 2 text"
    f = _FakeUploadFile("slides.pptx", b"fake pptx bytes")
    result = await parse_files_to_text([f])
    assert "Slide 1 text" in result


@pytest.mark.asyncio
async def test_multiple_files_merged():
    f1 = _FakeUploadFile("a.txt", b"Content A")
    f2 = _FakeUploadFile("b.txt", b"Content B")
    result = await parse_files_to_text([f1, f2])
    assert "Content A" in result
    assert "Content B" in result
    assert "=== 文件: a.txt ===" in result
    assert "=== 文件: b.txt ===" in result


@pytest.mark.asyncio
async def test_single_short_file_is_rejected():
    f = _FakeUploadFile("short.txt", b"too short")
    with pytest.raises(ValueError, match="无法从文件中提取有效文字内容"):
        await parse_files_to_text([f])


@pytest.mark.asyncio
async def test_truncation_at_max_length():
    long_text = "X" * (_MAX_TEXT_LENGTH + 500)
    f = _FakeUploadFile("big.txt", long_text.encode("utf-8"))
    result = await parse_files_to_text([f])
    assert len(result) <= _MAX_TEXT_LENGTH + 200  # allow for file header


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_pdf")
async def test_single_file_fail_skipped_but_others_succeed(mock_extract_pdf):
    mock_extract_pdf.side_effect = Exception("PDF parse error")
    f1 = _FakeUploadFile("bad.pdf", b"corrupted")
    f2 = _FakeUploadFile("good.txt", b"Good text content here")
    result = await parse_files_to_text([f1, f2])
    assert "Good text content here" in result
    assert "bad.pdf" not in result  # failed file skipped


@pytest.mark.asyncio
@patch("app.services.document_parser._extract_pdf")
async def test_all_files_fail_raises_value_error(mock_extract_pdf):
    mock_extract_pdf.side_effect = Exception("Parse error")
    f = _FakeUploadFile("bad.pdf", b"corrupted")
    with pytest.raises(ValueError, match="无法从文件中提取有效文字内容"):
        await parse_files_to_text([f])


@pytest.mark.asyncio
async def test_empty_file_list_raises():
    with pytest.raises(ValueError, match="请上传文件"):
        await parse_files_to_text([])


@pytest.mark.asyncio
async def test_unsupported_extension_treated_as_text():
    f = _FakeUploadFile("data.csv", b"col1,col2\nval1,val2")
    result = await parse_files_to_text([f])
    assert "col1,col2" in result


@pytest.mark.asyncio
async def test_xls_old_format_raises_value_error():
    f = _FakeUploadFile("old.xls", b"fake xls")
    with pytest.raises(ValueError, match="不支持 .xls"):
        await parse_files_to_text([f])
