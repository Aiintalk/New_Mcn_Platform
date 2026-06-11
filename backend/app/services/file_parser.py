"""
app/services/file_parser.py

解析上传文件，提取纯文本。
支持 .docx / .pdf / .txt / .md 格式。
"""
import io

from fastapi import UploadFile

MAX_CHARS = 8000  # 截断上限，与旧架构一致


async def parse_uploaded_file(file: UploadFile) -> str:
    """
    解析上传文件，返回提取的纯文本。

    支持：
    - .docx → python-docx 提取段落文本
    - .pdf  → pypdf 提取文本
    - .txt / .md → 直接 UTF-8 解码

    输出截断至 MAX_CHARS 字符。

    Raises:
        ValueError: 不支持的文件格式
        RuntimeError: 解析失败
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    content_bytes = await file.read()

    if ext == "docx":
        text = _parse_docx(content_bytes)
    elif ext == "pdf":
        text = _parse_pdf(content_bytes)
    elif ext in ("txt", "md"):
        text = content_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"不支持的文件格式: .{ext}（支持 .docx / .pdf / .txt / .md）")

    return text[:MAX_CHARS]


def _parse_docx(content: bytes) -> str:
    """用 python-docx 提取段落文本。"""
    from docx import Document

    doc = Document(io.BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _parse_pdf(content: bytes) -> str:
    """用 pypdf 提取文本。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    texts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            texts.append(page_text)
    return "\n".join(texts)
