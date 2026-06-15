"""
app/services/file_parser.py

解析上传文件，提取纯文本。
支持 .docx / .pdf / .txt / .md 格式。
"""
import io
import re
import zipfile

import pdfplumber

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
        try:
            return _parse_docx(content_bytes)
        except Exception as e:
            raise ValueError(f".docx 文件解析失败: {e}") from e
    elif ext == "pdf":
        try:
            return _parse_pdf_plumber(content_bytes)
        except Exception as e:
            raise ValueError(f".pdf 文件解析失败: {e}") from e
    elif ext == "pages":
        return _parse_pages_selling_point(content_bytes)
    elif ext == "doc":
        return "[.doc 格式暂不支持，请转换为 .docx 或 .pdf 后上传]"
    else:
        # 其他格式（如 .csv）尝试 UTF-8 解码，而非 raise ValueError
        # 这与旧版 parse_uploaded_file 的 raise 行为不同，是有意为之
        return content_bytes.decode("utf-8", errors="replace")


def _parse_pdf_plumber(content: bytes) -> str:
    """用 pdfplumber 提取文本（selling-point 版本）。"""
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
    过滤条件：中文字符 ≥5，无日历噪音过滤。
    """
    try:
        import snappy  # python-snappy
    except ImportError:
        import cramjam as snappy  # type: ignore  # cramjam 是 python-snappy 的替代库

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
    except Exception:  # noqa: BLE001
        # snappy 解压失败（可能未压缩，UncompressError/DecompressionError），回退到原始字节
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


# ---------------------------------------------------------------------------
# qianchuan-review 专用解析函数
# ---------------------------------------------------------------------------

async def parse_qianchuan_review_file(file: UploadFile) -> str:
    """
    qianchuan-review 专用文件解析，返回纯文本（无截断）。

    支持：.txt / .md / .docx / .pages
    不支持：.pdf（返回提示文字）
    其他格式：抛 ValueError

    .pages 含日历噪声过滤（与旧 JS 逻辑等价）：
    - 星期[一二三四五六日][BJR]
    - [一二...十]+月 开头且长度 < 20
    - 第[一二三四]季度 且长度 < 20
    - 公元 开头且长度 < 10
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_bytes = await file.read()

    if ext in ("txt", "md"):
        return content_bytes.decode("utf-8", errors="replace")
    elif ext == "docx":
        try:
            return _parse_docx(content_bytes)
        except Exception as e:
            raise ValueError(f".docx 文件解析失败: {e}") from e
    elif ext == "pdf":
        return "[暂不支持 PDF 格式，请转为 .docx 或 .txt 后上传]"
    elif ext == "pages":
        return _parse_pages_qianchuan_review(content_bytes)
    else:
        raise ValueError(f"不支持的文件格式: .{ext}（支持 .txt / .md / .docx / .pages）")


async def parse_livestream_review_file(file: UploadFile) -> str:
    """
    livestream-review 专用文件解析，与 qianchuan-review 逻辑完全相同。
    支持：.txt / .md / .docx / .pages；不支持 .pdf（返回提示文字）。
    """
    return await parse_qianchuan_review_file(file)


def _parse_pages_qianchuan_review(content: bytes) -> str:
    """
    解析 Apple Pages 文件（qianchuan-review 版本）。
    与 selling-point 版本的差异：增加日历噪声过滤（与原始 JS 逻辑等价）。
    """
    try:
        import snappy  # python-snappy
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
    except Exception:  # noqa: BLE001
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
        chinese_count = len(re.findall(r"[一-鿿]", s))
        if chinese_count < 5:
            continue
        # 日历噪声过滤（与原始 JS 逻辑等价）
        # [BJR] 为 Pages .iwa 序列化日历字段后缀（非自然语言，直接过滤）
        if re.search(r"星期[一二三四五六日][BJR]", s):
            continue
        if re.match(r"^[一二三四五六七八九十]+月", s) and len(s) < 20:
            continue
        if re.search(r"第[一二三四]季度", s) and len(s) < 20:
            continue
        if s.startswith("公元") and len(s) < 10:
            continue
        result.append(s)
    return "\n".join(result)
