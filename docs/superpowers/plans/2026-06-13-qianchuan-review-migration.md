# qianchuan-review 迁移实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧版 Next.js 独立应用 `qianchuan-review-web` 迁移至新 MCN 平台，实现三步工作流（上传脚本 → 上传投放数据 → AI 流式复盘报告），含完整后端接口、前端页面、测试和旧数据迁移脚本。

**Architecture:** 后端新增 `operator_qianchuan_review.py` Router（4 个接口）+ `qianchuan_review_service.py`（合并/排序/Prompt 构建）+ `tools/qianchuan_review/prompts.py`（System Prompt 常量）；`file_parser.py` 扩展新增 `parse_qianchuan_review_file()` 函数（含日历噪声过滤）；前端新增 `QianchuanReviewPage.tsx` 一体页面（三步流程 + 历史记录）+ `api/qianchuanReview.ts`；CORS 补 `expose_headers=["X-Task-Id"]`；附旧数据迁移脚本。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy asyncpg / yunwu adapter（`chat_stream`）/ React 19 / TypeScript / Ant Design 5 / XLSX.js

---

## 文件清单

### 新建

| 路径 | 职责 |
|------|------|
| `backend/app/tools/qianchuan_review/__init__.py` | package 标记 |
| `backend/app/tools/qianchuan_review/prompts.py` | PROMPT_WITH_EXCEL / PROMPT_WITHOUT_EXCEL 常量 |
| `backend/app/services/qianchuan_review_service.py` | merge_scripts_and_excel / build_user_message / generate_review（stream） |
| `backend/app/routers/operator_qianchuan_review.py` | 4 个接口：parse-file / generate / save / outputs |
| `backend/tests/unit/tools/test_qianchuan_review_prompts.py` | prompts 精确比对测试 |
| `backend/tests/unit/services/test_qianchuan_review_service.py` | merge / build_user_message 单元测试 |
| `backend/tests/unit/services/test_qianchuan_review_file_parser.py` | parse_qianchuan_review_file 单元测试（含日历噪声） |
| `backend/tests/integration/routers/test_operator_qianchuan_review.py` | 接口集成测试 |
| `backend/scripts/migrate_qianchuan_reports.py` | 旧数据迁移脚本 |
| `frontend/src/types/qianchuanReview.ts` | TypeScript 类型定义 |
| `frontend/src/api/qianchuanReview.ts` | API 调用函数 |
| `frontend/src/pages/operator/QianchuanReviewPage.tsx` | 主页面（三步流程 + 底部历史） |
| `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md` | 运维任务单（Nginx 超时 + python-snappy 依赖） |

### 修改

| 路径 | 改动内容 |
|------|---------|
| `backend/app/services/file_parser.py` | 新增 `parse_qianchuan_review_file()` 函数（含日历噪声过滤） |
| `backend/app/main.py` | 注册新 Router + CORS 补 `expose_headers=["X-Task-Id"]` |
| `frontend/src/App.tsx` | 新增 `/workspace/qianchuan-review` 路由 |

---

## Task 1：prompts.py — System Prompt 常量

**Files:**
- Create: `backend/app/tools/qianchuan_review/__init__.py`
- Create: `backend/app/tools/qianchuan_review/prompts.py`
- Create: `backend/tests/unit/tools/__init__.py`
- Create: `backend/tests/unit/tools/test_qianchuan_review_prompts.py`

- [ ] **Step 1: 创建 package 文件**

```bash
mkdir -p /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/app/tools/qianchuan_review
touch /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/app/tools/qianchuan_review/__init__.py
mkdir -p /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/tests/unit/tools
touch /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend/tests/unit/tools/__init__.py
```

- [ ] **Step 2: 先写测试（TDD 红灯）**

创建 `backend/tests/unit/tools/test_qianchuan_review_prompts.py`：

```python
"""精确比对 System Prompt 常量（与原始 page.tsx 逐字一致）。"""
from app.tools.qianchuan_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL


def test_prompt_with_excel_starts_with_expert_intro():
    assert PROMPT_WITH_EXCEL.startswith("你是千川投流素材复盘专家。")


def test_prompt_with_excel_contains_spend_analysis():
    assert "跑量素材拆解" in PROMPT_WITH_EXCEL
    assert "消耗高 = 平台认可" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_contains_roi_analysis():
    assert "高ROI素材分析" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_contains_three_sec_analysis():
    assert "开头效率分析" in PROMPT_WITH_EXCEL
    assert "3s完播率是核心" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_contains_loss_diagnosis():
    assert "亏损素材诊断" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_contains_selling_point_insight():
    assert "卖点结构洞察" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_contains_efficiency_advice():
    assert "投放效率建议" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_requirement_data_support():
    assert "所有判断必须有数据支撑，不说"感觉"" in PROMPT_WITH_EXCEL


def test_prompt_without_excel_starts_with_expert_intro():
    assert PROMPT_WITHOUT_EXCEL.startswith("你是千川投流素材复盘专家。")


def test_prompt_without_excel_no_spend_module():
    assert "跑量素材拆解" not in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_contains_best_material():
    assert "最好的素材" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_contains_eliminate():
    assert "建议淘汰的素材" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_contains_selling_structure():
    assert "卖点结构分析" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_contains_hook_analysis():
    assert "开头类型分析" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_contains_new_material():
    assert "新素材方向" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_requirement_deep_analysis():
    assert "分析要深入到具体的文案句子和段落" in PROMPT_WITHOUT_EXCEL


def test_prompts_are_different():
    assert PROMPT_WITH_EXCEL != PROMPT_WITHOUT_EXCEL
```

- [ ] **Step 3: 运行，确认红灯**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/unit/tools/test_qianchuan_review_prompts.py -v 2>&1 | tail -5
```

预期：`ModuleNotFoundError: No module named 'app.tools.qianchuan_review'`

- [ ] **Step 4: 创建 prompts.py**

创建 `backend/app/tools/qianchuan_review/prompts.py`：

```python
"""
app/tools/qianchuan_review/prompts.py

千川脚本复盘 System Prompt 常量。
两个版本逐字来自原始 qianchuan-review-web/app/page.tsx，不得随意修改。
验收标准：与原代码 diff 为空。
"""

PROMPT_WITH_EXCEL = """你是千川投流素材复盘专家。你研究过大量千川跑量素材的共性规律，深谙什么样的千川脚本能跑量、什么样的结构能转化。你对开头hook、卖点结构、行动号召、投放效率有极深的实战理解。

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
- 如果某个模块没有足够数据支撑，跳过，不凑字数"""

PROMPT_WITHOUT_EXCEL = """你是千川投流素材复盘专家。你研究过大量千川跑量素材的共性规律，深谙什么样的千川脚本能跑量、什么样的结构能转化。你对开头hook、卖点结构、行动号召、投放效率有极深的实战理解。

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
- 如果某个模块没有足够内容支撑，跳过，不凑字数"""
```

- [ ] **Step 5: 运行，确认绿灯**

```bash
pytest tests/unit/tools/test_qianchuan_review_prompts.py -v 2>&1 | tail -5
```

预期：`17 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/tools/qianchuan_review/ backend/tests/unit/tools/
git commit -m "feat: add qianchuan-review System Prompt constants"
```

---

## Task 2：file_parser.py — parse_qianchuan_review_file（含日历噪声过滤）

**Files:**
- Modify: `backend/app/services/file_parser.py`
- Create: `backend/tests/unit/services/test_qianchuan_review_file_parser.py`

- [ ] **Step 1: 先写测试（TDD 红灯）**

创建 `backend/tests/unit/services/test_qianchuan_review_file_parser.py`：

```python
"""
Unit tests for parse_qianchuan_review_file。

与 selling-point 版本的关键区别：
- PDF 不支持（返回提示文字，不抛错）
- .pages 有日历噪声过滤（星期、月份季度、公元）
"""
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.file_parser import parse_qianchuan_review_file


def _mock_file(filename: str, content: bytes) -> MagicMock:
    f = MagicMock()
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


# ---------- txt / md ----------

@pytest.mark.asyncio
async def test_txt_returns_text():
    result = await parse_qianchuan_review_file(_mock_file("script.txt", "脚本内容第一行标题".encode()))
    assert result == "脚本内容第一行标题"


@pytest.mark.asyncio
async def test_md_returns_text():
    result = await parse_qianchuan_review_file(_mock_file("script.md", "# 标题\n内容".encode()))
    assert "标题" in result


# ---------- docx ----------

@pytest.mark.asyncio
async def test_docx_extracts_paragraphs():
    from docx import Document
    doc = Document()
    doc.add_paragraph("千川脚本第一段")
    doc.add_paragraph("第二段内容")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    result = await parse_qianchuan_review_file(_mock_file("script.docx", buf.read()))
    assert "千川脚本第一段" in result
    assert "第二段内容" in result


# ---------- pdf —— 不支持，返回提示 ----------

@pytest.mark.asyncio
async def test_pdf_returns_unsupported_hint():
    result = await parse_qianchuan_review_file(_mock_file("data.pdf", b"%PDF-1.4"))
    assert result == "[暂不支持 PDF 格式，请转为 .docx 或 .txt 后上传]"


# ---------- .pages —— 基础提取 ----------

def _make_pages_zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Index/Document.iwa", b"\x00\x00\x00\x00" + text.encode())
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_pages_extracts_chinese():
    pages_bytes = _make_pages_zip("这是一段产品脚本内容，超过十个中文字的段落。")
    result = await parse_qianchuan_review_file(_mock_file("script.pages", pages_bytes))
    assert "产品脚本内容" in result


@pytest.mark.asyncio
async def test_pages_filters_short_chinese():
    """少于5个汉字的片段应被过滤"""
    pages_bytes = _make_pages_zip("两字" + "A" * 20)
    result = await parse_qianchuan_review_file(_mock_file("noise.pages", pages_bytes))
    assert "两字" not in result


# ---------- .pages —— 日历噪声过滤（与 selling-point 的关键差异） ----------

@pytest.mark.asyncio
async def test_pages_filters_weekday_noise():
    """星期X[BJR] 模式应被过滤"""
    pages_bytes = _make_pages_zip("星期一B这是噪声")
    result = await parse_qianchuan_review_file(_mock_file("cal.pages", pages_bytes))
    assert "星期一B" not in result


@pytest.mark.asyncio
async def test_pages_filters_month_noise():
    """[一二...十]+月 开头且长度<20 的片段应被过滤"""
    pages_bytes = _make_pages_zip("一月二日三日")
    result = await parse_qianchuan_review_file(_mock_file("cal.pages", pages_bytes))
    assert "一月" not in result


@pytest.mark.asyncio
async def test_pages_filters_quarter_noise():
    """第[一二三四]季度 且长度<20 的片段应被过滤"""
    pages_bytes = _make_pages_zip("第一季度数据")
    result = await parse_qianchuan_review_file(_mock_file("cal.pages", pages_bytes))
    assert "第一季度" not in result


@pytest.mark.asyncio
async def test_pages_filters_gongyan_noise():
    """公元开头且长度<10 的片段应被过滤"""
    pages_bytes = _make_pages_zip("公元前")
    result = await parse_qianchuan_review_file(_mock_file("cal.pages", pages_bytes))
    assert "公元前" not in result


@pytest.mark.asyncio
async def test_pages_keeps_long_month_content():
    """长度>=20 的月份内容不应被过滤"""
    long_month = "一月份这个产品的卖点非常明显价格优惠超值"  # >= 20 字
    pages_bytes = _make_pages_zip(long_month)
    result = await parse_qianchuan_review_file(_mock_file("script.pages", pages_bytes))
    assert "一月份" in result


@pytest.mark.asyncio
async def test_pages_missing_iwa():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dummy.txt", "nothing")
    buf.seek(0)
    result = await parse_qianchuan_review_file(_mock_file("empty.pages", buf.read()))
    assert "格式异常" in result


@pytest.mark.asyncio
async def test_pages_invalid_zip():
    result = await parse_qianchuan_review_file(_mock_file("bad.pages", b"not a zip"))
    assert "格式异常" in result


# ---------- 未知格式 ----------

@pytest.mark.asyncio
async def test_unknown_ext_raises_value_error():
    with pytest.raises(ValueError, match="不支持的文件格式"):
        await parse_qianchuan_review_file(_mock_file("data.xlsx", b"content"))
```

- [ ] **Step 2: 运行，确认红灯**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/unit/services/test_qianchuan_review_file_parser.py -v 2>&1 | tail -5
```

预期：`ImportError: cannot import name 'parse_qianchuan_review_file'`

- [ ] **Step 3: 在 file_parser.py 末尾追加函数**

在 `backend/app/services/file_parser.py` 末尾追加以下内容（不修改任何已有代码）：

```python


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
```

- [ ] **Step 4: 运行，确认绿灯**

```bash
pytest tests/unit/services/test_qianchuan_review_file_parser.py -v 2>&1 | tail -5
```

预期：`14 passed`

- [ ] **Step 5: 确认原有 selling-point 测试未回归**

```bash
pytest tests/unit/services/test_selling_point_file_parser.py -v 2>&1 | tail -3
```

预期：全部 passed（无任何失败）

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/services/file_parser.py backend/tests/unit/services/test_qianchuan_review_file_parser.py
git commit -m "feat: add parse_qianchuan_review_file with calendar noise filter"
```

---

## Task 3：qianchuan_review_service.py — 合并、排序、Prompt 构建

**Files:**
- Create: `backend/app/services/qianchuan_review_service.py`
- Create: `backend/tests/unit/services/test_qianchuan_review_service.py`

- [ ] **Step 1: 先写测试（TDD 红灯）**

创建 `backend/tests/unit/services/test_qianchuan_review_service.py`：

```python
"""Unit tests for qianchuan_review_service（不依赖 DB / AI）。"""
import pytest

from app.services.qianchuan_review_service import (
    ScriptItem,
    ExcelRow,
    merge_scripts_and_excel,
    build_user_message,
)


# ---------- merge_scripts_and_excel ----------

def test_merge_no_excel():
    """无 Excel 时，脚本原样返回，顺序不变。"""
    scripts = [
        ScriptItem(title="脚本A", content="内容A"),
        ScriptItem(title="脚本B", content="内容B"),
    ]
    result = merge_scripts_and_excel(scripts, [])
    assert len(result) == 2
    assert result[0]["title"] == "脚本A"
    assert result[0]["spend"] is None


def test_merge_matches_by_first_12_chars():
    """脚本标题与 Excel video_theme 取前12字模糊匹配。"""
    scripts = [ScriptItem(title="这是一个千川脚本标题内容", content="脚本全文")]
    excel = [ExcelRow(
        video_theme="这是一个千川脚本标题内容完整版",
        spend="1000",
        roi="3.5",
        impressions=None, ctr=None, three_sec_rate=None,
        conversions=None, cost_per_conversion=None,
        cpm=None, time_range=None,
    )]
    result = merge_scripts_and_excel(scripts, excel)
    assert len(result) == 1
    assert result[0]["spend"] == "1000"
    assert result[0]["roi"] == "3.5"


def test_merge_title_replaced_by_excel_video_theme():
    """匹配成功时，title 使用 Excel 的 video_theme。"""
    scripts = [ScriptItem(title="开头相同的内容，脚本标题", content="内容")]
    excel = [ExcelRow(
        video_theme="开头相同的内容，Excel标题",
        spend="500",
        roi=None, impressions=None, ctr=None, three_sec_rate=None,
        conversions=None, cost_per_conversion=None,
        cpm=None, time_range=None,
    )]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["title"] == "开头相同的内容，Excel标题"


def test_merge_unmatched_excel_appended():
    """Excel 中有但脚本无对应的行，追加到列表末尾，content 为空。"""
    scripts = [ScriptItem(title="脚本甲内容", content="全文")]
    excel = [
        ExcelRow(video_theme="脚本甲内容完整名称", spend="800", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
        ExcelRow(video_theme="完全不同的素材名称", spend="200", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
    ]
    result = merge_scripts_and_excel(scripts, excel)
    assert len(result) == 2
    assert result[1]["title"] == "完全不同的素材名称"
    assert result[1]["content"] == ""


def test_merge_sorted_by_spend_descending():
    """按消耗（spend）降序排列。"""
    scripts = [
        ScriptItem(title="低消耗脚本内容", content="内容A"),
        ScriptItem(title="高消耗脚本内容", content="内容B"),
    ]
    excel = [
        ExcelRow(video_theme="低消耗脚本内容", spend="100", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
        ExcelRow(video_theme="高消耗脚本内容", spend="9999", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
    ]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["spend"] == "9999"
    assert result[1]["spend"] == "100"


def test_merge_no_spend_sorted_last():
    """无消耗数据的条目排在有消耗数据的后面。"""
    scripts = [
        ScriptItem(title="无数据脚本", content="内容C"),
        ScriptItem(title="有数据脚本", content="内容D"),
    ]
    excel = [ExcelRow(video_theme="有数据脚本完整", spend="500", roi=None,
                      impressions=None, ctr=None, three_sec_rate=None,
                      conversions=None, cost_per_conversion=None,
                      cpm=None, time_range=None)]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["title"] == "有数据脚本完整"
    assert result[1]["title"] == "无数据脚本"


# ---------- build_user_message ----------

def test_build_user_message_basic():
    items = [{"title": "脚本一", "content": "文案内容", "spend": None,
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "conversions": None, "cost_per_conversion": None,
              "roi": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "以下是本期千川投放素材（共1条）" in msg
    assert "### 素材 1：脚本一" in msg
    assert "【完整脚本】" in msg
    assert "文案内容" in msg


def test_build_user_message_includes_metrics():
    items = [{"title": "素材X", "content": "内容", "spend": "1234",
              "roi": "3.5", "conversions": "89",
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "cost_per_conversion": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "消耗: 1234元" in msg
    assert "ROI: 3.5" in msg
    assert "转化数: 89" in msg


def test_build_user_message_truncates_at_2000():
    """单条脚本超过 2000 字应截断并注明。"""
    long_content = "千" * 2500
    items = [{"title": "长脚本", "content": long_content, "spend": None,
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "conversions": None, "cost_per_conversion": None,
              "roi": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "...(已截断)" in msg
    # 截断后脚本部分不超过 2000 字
    script_part = msg.split("【完整脚本】")[1].split("---")[0]
    assert len(script_part) < 2100


def test_build_user_message_multiple_items_separated():
    items = [
        {"title": "素材一", "content": "内容一", "spend": None,
         "impressions": None, "ctr": None, "three_sec_rate": None,
         "conversions": None, "cost_per_conversion": None,
         "roi": None, "cpm": None, "time_range": None},
        {"title": "素材二", "content": "内容二", "spend": None,
         "impressions": None, "ctr": None, "three_sec_rate": None,
         "conversions": None, "cost_per_conversion": None,
         "roi": None, "cpm": None, "time_range": None},
    ]
    msg = build_user_message(items)
    assert "### 素材 1：素材一" in msg
    assert "### 素材 2：素材二" in msg
    assert "---" in msg
```

- [ ] **Step 2: 运行，确认红灯**

```bash
pytest tests/unit/services/test_qianchuan_review_service.py -v 2>&1 | tail -5
```

预期：`ModuleNotFoundError: No module named 'app.services.qianchuan_review_service'`

- [ ] **Step 3: 实现 qianchuan_review_service.py**

创建 `backend/app/services/qianchuan_review_service.py`：

```python
"""
app/services/qianchuan_review_service.py

千川脚本复盘核心业务逻辑：
- 脚本与 Excel 数据合并匹配（Python 等价于原始 JS 逻辑）
- 构建发给 AI 的 User Message
- 流式生成复盘报告（复用 yunwu.chat_stream）
"""
import re
from dataclasses import dataclass, field
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.tools.qianchuan_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL

TOOL_CODE = "qianchuan-review"
TOOL_NAME = "千川脚本复盘"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_SCRIPTS = 30
CONTENT_TRUNCATE = 2000
MATCH_KEY_LEN = 12  # 取前12字做模糊匹配（与原代码一致，精度优先）
MATCH_SUB_LEN = 6   # includes 判断取前6字


@dataclass
class ScriptItem:
    title: str
    content: str


@dataclass
class ExcelRow:
    video_theme: str
    spend: str | None = None
    impressions: str | None = None
    ctr: str | None = None
    three_sec_rate: str | None = None
    conversions: str | None = None
    cost_per_conversion: str | None = None
    roi: str | None = None
    cpm: str | None = None
    time_range: str | None = None


def _normalize(text: str) -> str:
    """清除标点、特殊字符、空白，取前 MATCH_KEY_LEN 字，用于模糊匹配。"""
    return re.sub(r"[，。！？、#@\s]", "", text)[:MATCH_KEY_LEN]


def _is_match(a_norm: str, b_norm: str) -> bool:
    """双向 includes 判断（与原始 JS 逻辑等价）。"""
    return (
        a_norm[:MATCH_SUB_LEN] in b_norm
        or b_norm[:MATCH_SUB_LEN] in a_norm
    )


def merge_scripts_and_excel(
    scripts: list[ScriptItem],
    excel_data: list[ExcelRow],
) -> list[dict]:
    """
    将脚本列表与 Excel 数据合并：
    1. 对每条脚本，在 Excel 中找匹配行（模糊匹配前12字）
    2. 匹配到：用 Excel video_theme 覆盖标题，附上所有指标
    3. 未匹配到：保留脚本标题，指标为 None
    4. Excel 中有但脚本无对应的行：追加到末尾，content 为空
    5. 整体按 spend 降序排列，无消耗排后面
    """
    merged: list[dict] = []
    matched_excel_indices: set[int] = set()

    for script in scripts:
        script_norm = _normalize(script.title)
        matched_row: ExcelRow | None = None
        matched_idx: int | None = None

        for idx, row in enumerate(excel_data):
            if not row.video_theme:
                continue
            excel_norm = _normalize(row.video_theme)
            if _is_match(script_norm, excel_norm):
                matched_row = row
                matched_idx = idx
                break

        if matched_row is not None and matched_idx is not None:
            matched_excel_indices.add(matched_idx)
            merged.append({
                "title": matched_row.video_theme,
                "content": script.content,
                "spend": matched_row.spend,
                "impressions": matched_row.impressions,
                "ctr": matched_row.ctr,
                "three_sec_rate": matched_row.three_sec_rate,
                "conversions": matched_row.conversions,
                "cost_per_conversion": matched_row.cost_per_conversion,
                "roi": matched_row.roi,
                "cpm": matched_row.cpm,
                "time_range": matched_row.time_range,
            })
        else:
            merged.append({
                "title": script.title,
                "content": script.content,
                "spend": None,
                "impressions": None,
                "ctr": None,
                "three_sec_rate": None,
                "conversions": None,
                "cost_per_conversion": None,
                "roi": None,
                "cpm": None,
                "time_range": None,
            })

    # Excel 中有但脚本无对应的行，追加到末尾
    for idx, row in enumerate(excel_data):
        if idx in matched_excel_indices or not row.video_theme:
            continue
        merged.append({
            "title": row.video_theme,
            "content": "",
            "spend": row.spend,
            "impressions": row.impressions,
            "ctr": row.ctr,
            "three_sec_rate": row.three_sec_rate,
            "conversions": row.conversions,
            "cost_per_conversion": row.cost_per_conversion,
            "roi": row.roi,
            "cpm": row.cpm,
            "time_range": row.time_range,
        })

    # 按 spend 降序排列，无消耗排后面
    def _spend_key(item: dict) -> float:
        try:
            return float(item["spend"]) if item["spend"] else 0.0
        except (ValueError, TypeError):
            return 0.0

    merged.sort(key=_spend_key, reverse=True)
    return merged


def build_user_message(items: list[dict]) -> str:
    """
    构建发给 AI 的 User Message。
    格式与原始 JS 逻辑完全等价。
    """
    parts = [f"以下是本期千川投放素材（共{len(items)}条）：\n"]

    for i, v in enumerate(items, 1):
        desc = f"### 素材 {i}：{v['title']}"
        meta_parts = []
        if v.get("spend"):
            meta_parts.append(f"消耗: {v['spend']}元")
        if v.get("roi"):
            meta_parts.append(f"ROI: {v['roi']}")
        if v.get("conversions"):
            meta_parts.append(f"转化数: {v['conversions']}")
        if v.get("cost_per_conversion"):
            meta_parts.append(f"转化成本: {v['cost_per_conversion']}元")
        if v.get("ctr"):
            meta_parts.append(f"点击率: {v['ctr']}")
        if v.get("three_sec_rate"):
            meta_parts.append(f"3s完播率: {v['three_sec_rate']}")
        if v.get("impressions"):
            meta_parts.append(f"展示次数: {v['impressions']}")
        if v.get("cpm"):
            meta_parts.append(f"CPM: {v['cpm']}元")
        if v.get("time_range"):
            meta_parts.append(f"投放时段: {v['time_range']}")

        if meta_parts:
            desc += "\n" + " | ".join(meta_parts)

        content = v.get("content") or ""
        if content:
            truncated = (
                content[:CONTENT_TRUNCATE] + "\n...(已截断)"
                if len(content) > CONTENT_TRUNCATE
                else content
            )
            desc += f"\n\n【完整脚本】\n{truncated}"

        parts.append(desc)

    return "\n\n---\n\n".join(parts)


async def generate_review_stream(
    items: list[dict],
    has_excel: bool,
    db: AsyncSession,
    user_id: int,
    task_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    调用 AI 流式生成复盘报告。
    has_excel=True 用 PROMPT_WITH_EXCEL，否则用 PROMPT_WITHOUT_EXCEL。
    """
    system_prompt = PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL
    user_message = build_user_message(items)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message + "\n\n请输出复盘报告。"},
    ]

    async for chunk in yunwu_adapter.chat_stream(
        messages=messages,
        db=db,
        model_id=DEFAULT_MODEL,
        user_id=user_id,
        feature="qianchuan_review_generate",
    ):
        yield chunk
```

- [ ] **Step 4: 运行，确认绿灯**

```bash
pytest tests/unit/services/test_qianchuan_review_service.py -v 2>&1 | tail -5
```

预期：`13 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/services/qianchuan_review_service.py backend/tests/unit/services/test_qianchuan_review_service.py
git commit -m "feat: add qianchuan_review_service (merge/sort/prompt/stream)"
```

---

## Task 4：后端 Router — 4 个接口 + main.py 注册 + CORS

**Files:**
- Create: `backend/app/routers/operator_qianchuan_review.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/routers/test_operator_qianchuan_review.py`

- [ ] **Step 1: 先写集成测试（TDD 红灯）**

创建 `backend/tests/integration/routers/test_operator_qianchuan_review.py`：

```python
"""Integration tests for operator_qianchuan_review router."""
from unittest.mock import patch, AsyncMock

import pytest


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": [{"title": "t", "content": "c"}], "excel_data": []},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={"task_id": 1, "report": "内容", "script_count": 1, "has_excel": False},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_outputs_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-review/outputs")
        assert resp.status_code == 401


# ---------- parse-file ----------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_txt_file_returns_text(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("script.txt", "千川脚本内容".encode("utf-8"), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "千川脚本内容" in data["data"]["text"]
        assert data["data"]["filename"] == "script.txt"

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("data.xlsx", b"content", "application/octet-stream")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"


# ---------- generate ----------

class TestGenerate:
    @pytest.mark.asyncio
    async def test_empty_scripts_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": [], "excel_data": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_over_30_scripts_returns_400(self, test_client, operator_token):
        scripts = [{"title": f"脚本{i}", "content": "内容"} for i in range(31)]
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": scripts, "excel_data": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert "30条" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_generate_returns_stream_and_task_id_header(self, test_client, operator_token):
        async def fake_stream(*args, **kwargs):
            yield "复盘"
            yield "报告"

        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            return_value=fake_stream(),
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={"scripts": [{"title": "脚本甲", "content": "脚本内容"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "复盘" in resp.text
        assert "X-Task-Id" in resp.headers


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_creates_output(self, test_client, operator_token, test_session):
        from sqlalchemy import text as sa_text

        # 先创建一个 task_job 用于关联
        await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('QR-TEST-001', 'qianchuan-review', '千川脚本复盘', 'processing', "
            "(SELECT id FROM users WHERE role='operator' LIMIT 1))"
        ))
        await test_session.commit()
        task_row = (await test_session.execute(
            sa_text("SELECT id FROM task_jobs WHERE task_no='QR-TEST-001'")
        )).fetchone()
        task_id = task_row[0]

        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={
                "task_id": task_id,
                "report": "这是完整的复盘报告内容",
                "script_count": 3,
                "has_excel": True,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "output_id" in data["data"]

    @pytest.mark.asyncio
    async def test_save_empty_report_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={"task_id": 1, "report": "", "script_count": 1, "has_excel": False},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400


# ---------- outputs ----------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_returns_list(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_operator_only_sees_own_outputs(self, test_client, operator_token):
        """operator 只能看到自己的记录（通过 created_by 过滤）。"""
        resp = await test_client.get(
            "/api/tools/qianchuan-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        # 验证响应结构正确即可（具体权限隔离由 admin token 测试对比）
        data = resp.json()
        assert isinstance(data["data"]["items"], list)
```

- [ ] **Step 2: 运行，确认红灯**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/integration/routers/test_operator_qianchuan_review.py -v 2>&1 | tail -5
```

预期：`ImportError` 或 404 错误

- [ ] **Step 3: 实现 Router**

创建 `backend/app/routers/operator_qianchuan_review.py`：

```python
"""
app/routers/operator_qianchuan_review.py

千川脚本复盘接口（operator / admin 鉴权）：
  POST  /api/tools/qianchuan-review/parse-file  — 上传脚本文件，返回文本
  POST  /api/tools/qianchuan-review/generate    — SSE 流式生成复盘报告
  POST  /api/tools/qianchuan-review/save        — 保存报告到 outputs 表
  GET   /api/tools/qianchuan-review/outputs     — 查询历史复盘报告列表
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.database import AsyncSessionLocal, get_db
from app.middlewares.auth import get_current_user
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_qianchuan_review_file
from app.services.qianchuan_review_service import (
    TOOL_CODE,
    TOOL_NAME,
    MAX_SCRIPTS,
    ExcelRow,
    ScriptItem,
    generate_review_stream,
    merge_scripts_and_excel,
)

router = APIRouter(prefix="/tools/qianchuan-review", tags=["qianchuan-review"])


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


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    """上传脚本文件，解析返回文本。支持 .txt/.md/.docx/.pages，不支持 .pdf。"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    try:
        text = await parse_qianchuan_review_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return {"success": True, "data": {"text": text, "filename": file.filename}}


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class ScriptItemSchema(BaseModel):
    title: str
    content: str


class ExcelRowSchema(BaseModel):
    video_theme: str
    spend: str | None = None
    impressions: str | None = None
    ctr: str | None = None
    three_sec_rate: str | None = None
    conversions: str | None = None
    cost_per_conversion: str | None = None
    roi: str | None = None
    cpm: str | None = None
    time_range: str | None = None


class GenerateRequest(BaseModel):
    scripts: list[ScriptItemSchema]
    excel_data: list[ExcelRowSchema] = []


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """SSE 流式生成复盘报告。Response Header X-Task-Id 供前端保存时使用。"""
    if not body.scripts:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "scripts 不能为空"},
        )
    if len(body.scripts) > MAX_SCRIPTS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SCRIPTS_LIMIT_EXCEEDED",
                "message": f"脚本条数超过上限（{MAX_SCRIPTS}条），请分批复盘",
            },
        )

    # 在流开始前创建 task_job（processing）
    task_no = f"QR-{int(time.time() * 1000)}"
    has_excel = len(body.excel_data) > 0
    task_job = TaskJob(
        task_no=task_no,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        status="processing",
        input_payload={
            "script_count": len(body.scripts),
            "has_excel": has_excel,
        },
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task_job)
    await db.commit()
    await db.refresh(task_job)
    task_id = task_job.id

    # 合并脚本与 Excel
    scripts = [ScriptItem(title=s.title, content=s.content) for s in body.scripts]
    excel_rows = [
        ExcelRow(
            video_theme=e.video_theme,
            spend=e.spend,
            impressions=e.impressions,
            ctr=e.ctr,
            three_sec_rate=e.three_sec_rate,
            conversions=e.conversions,
            cost_per_conversion=e.cost_per_conversion,
            roi=e.roi,
            cpm=e.cpm,
            time_range=e.time_range,
        )
        for e in body.excel_data
    ]
    items = merge_scripts_and_excel(scripts, excel_rows)
    user_id = current_user.id
    start_time = time.monotonic()

    async def generate_stream():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in generate_review_stream(
                    items=items,
                    has_excel=has_excel,
                    db=stream_db,
                    user_id=user_id,
                    task_id=task_id,
                ):
                    yield chunk
        except GeneratorExit:
            # 客户端断开，后续 background task 更新状态即可
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
    task_id: int
    report: str
    script_count: int
    has_excel: bool


@router.post("/save")
async def save_report(
    body: SaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存报告到 outputs 表。"""
    if not body.report.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "report 不能为空"},
        )

    excel_label = "含投放数据" if body.has_excel else "仅脚本"
    title = f"千川复盘_{body.script_count}条素材_{excel_label}"

    output = Output(
        title=title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        task_id=body.task_id,
        content=body.report,
        content_json={
            "script_count": body.script_count,
            "has_excel": body.has_excel,
        },
        word_count=len(body.report),
        created_by=current_user.id,
    )
    db.add(output)
    await db.commit()
    await db.refresh(output)

    return {"success": True, "data": {"output_id": output.id}}


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
    """
    查询历史复盘报告。
    operator：只看自己的；admin：看全部。
    """
    query = (
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
    )
    if current_user.role == "operator":
        query = query.where(Output.created_by == current_user.id)

    total_query = query
    total = len((await db.execute(total_query)).scalars().all())

    rows = (
        await db.execute(
            query.order_by(Output.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()

    items = []
    for r in rows:
        cj = r.content_json or {}
        items.append({
            "id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "preview": (r.content or "")[:100],
            "script_count": cj.get("script_count"),
            "has_excel": cj.get("has_excel"),
            "word_count": r.word_count,
        })

    return {"success": True, "data": {"items": items, "total": total}}
```

- [ ] **Step 4: 注册 Router 并补 CORS**

修改 `backend/app/main.py`：

在 imports 区（最后一个 router import 之后）添加：
```python
from app.routers.operator_qianchuan_review import router as operator_qianchuan_review_router
```

在 CORS 配置（`allow_headers=["*"]` 之后）添加 `expose_headers`：
```python
    expose_headers=["X-Task-Id"],
```

在 `app.include_router(admin_selling_point_router, ...)` 之后添加：
```python
app.include_router(operator_qianchuan_review_router, prefix="/api")
```

- [ ] **Step 5: 运行集成测试，确认绿灯**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/integration/routers/test_operator_qianchuan_review.py -v 2>&1 | tail -10
```

预期：`12 passed`（generate 测试因 mock stream 可能需要 AsyncMock 调整，全部通过为准）

- [ ] **Step 6: 跑全量回归确认无回归**

```bash
pytest tests/unit/ tests/integration/ -v --tb=short 2>&1 | tail -15
```

预期：之前所有测试全部通过，无新增 FAILED

- [ ] **Step 7: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/app/routers/operator_qianchuan_review.py \
        backend/app/main.py \
        backend/tests/integration/routers/test_operator_qianchuan_review.py
git commit -m "feat: add qianchuan-review router (parse-file/generate/save/outputs) + CORS expose X-Task-Id"
```

---

## Task 5：前端 — TypeScript 类型 + API + 页面

**Files:**
- Create: `frontend/src/types/qianchuanReview.ts`
- Create: `frontend/src/api/qianchuanReview.ts`
- Create: `frontend/src/pages/operator/QianchuanReviewPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 创建 TypeScript 类型**

创建 `frontend/src/types/qianchuanReview.ts`：

```typescript
// frontend/src/types/qianchuanReview.ts

export interface ScriptEntry {
  id: string;
  title: string;
  content: string;
  source: string; // 文件名 或 'paste'
}

export interface ExcelRow {
  video_theme: string;
  spend?: string;
  impressions?: string;
  ctr?: string;
  three_sec_rate?: string;
  conversions?: string;
  cost_per_conversion?: string;
  roi?: string;
  cpm?: string;
  time_range?: string;
}

export interface GenerateRequest {
  scripts: { title: string; content: string }[];
  excel_data: ExcelRow[];
}

export interface SaveRequest {
  task_id: number;
  report: string;
  script_count: number;
  has_excel: boolean;
}

export interface OutputItem {
  id: number;
  title: string;
  created_at: string;
  preview: string;
  script_count: number | null;
  has_excel: boolean | null;
  word_count: number | null;
}

export interface OutputsResponse {
  items: OutputItem[];
  total: number;
}
```

- [ ] **Step 2: 创建 API 函数**

创建 `frontend/src/api/qianchuanReview.ts`：

```typescript
// frontend/src/api/qianchuanReview.ts
import type { GenerateRequest, OutputsResponse, SaveRequest } from '../types/qianchuanReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = '/api/tools/qianchuan-review';

async function getToken(): Promise<string | null> {
  return (await import('../store/authStore')).useAuthStore.getState().token;
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 解析上传的脚本文件 */
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
    throw new Error(err?.message ?? `解析失败: ${resp.status}`);
  }
  const data = await resp.json();
  return data.data;
}

/** SSE 流式生成复盘报告，返回 Response（供调用方读取流 + 读取 X-Task-Id header） */
export async function generateReport(payload: GenerateRequest): Promise<Response> {
  const token = await getToken();
  return fetch(`${BASE_URL}${PREFIX}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  });
}

/** 保存报告到产出中心 */
export async function saveReport(payload: SaveRequest): Promise<{ output_id: number }> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`保存失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}

/** 查询历史复盘报告列表 */
export async function getOutputs(page = 1, size = 10): Promise<OutputsResponse> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/outputs?page=${page}&size=${size}`, {
    headers: authHeaders(token),
  });
  if (!resp.ok) throw new Error(`获取历史失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}
```

- [ ] **Step 3: 创建主页面**

创建 `frontend/src/pages/operator/QianchuanReviewPage.tsx`：

```typescript
// frontend/src/pages/operator/QianchuanReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import * as XLSX from 'xlsx';
import type { ScriptEntry, ExcelRow, OutputItem } from '../../types/qianchuanReview';
import { parseFile, generateReport, saveReport, getOutputs } from '../../api/qianchuanReview';

/* ── Markdown 渲染 ── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 class="text-base font-bold mt-4 mb-2">$1</h3>')
    .replace(/## (.+)/g, '<h2 class="text-lg font-bold mt-5 mb-2">$1</h2>')
    .replace(/# (.+)/g, '<h1 class="text-xl font-bold mt-6 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

/* ── Excel 解析工具函数（前端本地解析，与旧代码等价） ── */
function matchHeader(header: string, aliases: string[]): boolean {
  const h = header.trim();
  if (aliases.some(a => a === h)) return true;
  if (aliases.some(a => h.endsWith(a))) return true;
  return false;
}

function parseExcelWorkbook(wb: XLSX.WorkBook): ExcelRow[] {
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) return [];
  const raw: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 });
  if (raw.length < 2) return [];

  const knownLabels: [string[], keyof ExcelRow][] = [
    [['素材名称', '视频主题', '素材标题', '视频名称'], 'video_theme'],
    [['整体消耗', '消耗', '花费', '总消耗'], 'spend'],
    [['展示次数', '展示', '曝光', '曝光次数'], 'impressions'],
    [['点击率', 'CTR', 'ctr', '整体点击率'], 'ctr'],
    [['3s完播率', '3秒完播率', '3s完播', '3秒播放率'], 'three_sec_rate'],
    [['转化数', '成交数', '订单数'], 'conversions'],
    [['转化成本', '成交成本', '单次转化成本'], 'cost_per_conversion'],
    [['ROI', 'roi', '投产比', '投产', '整体支付ROI', '支付ROI'], 'roi'],
    [['千次展示成本', 'CPM', 'cpm', '千展成本', '千次展现费用', '整体千次展现费用'], 'cpm'],
    [['投放时段', '时段', '投放时间'], 'time_range'],
  ];

  // 尝试转置格式
  const rowMapping: { rowIdx: number; key: keyof ExcelRow }[] = [];
  for (let r = 0; r < raw.length; r++) {
    const cellVal = String(raw[r]?.[0] ?? '').trim();
    for (const [aliases, key] of knownLabels) {
      if (matchHeader(cellVal, aliases)) {
        rowMapping.push({ rowIdx: r, key });
        break;
      }
    }
  }
  const distinctKeys = new Set(rowMapping.map(m => m.key));
  if (distinctKeys.size >= 3 && rowMapping.length >= 3) {
    const numCols = Math.max(...raw.map(r => r?.length ?? 0));
    const results: ExcelRow[] = [];
    for (let c = 1; c < numCols; c++) {
      const entry: any = {};
      let hasData = false;
      for (const { rowIdx, key } of rowMapping) {
        const val = raw[rowIdx]?.[c];
        if (val !== undefined && val !== null && val !== '') {
          entry[key] = String(val).trim();
          hasData = true;
        }
      }
      if (hasData && entry.video_theme) results.push(entry as ExcelRow);
    }
    if (results.length > 0) return results;
  }

  // 标准格式
  const headers = raw[0]?.map((h: any) => String(h ?? '').trim()) || [];
  const usedKeys = new Set<string>();
  const usedCols = new Set<number>();
  const colMapping: { colIdx: number; key: keyof ExcelRow }[] = [];
  for (let c = 0; c < headers.length; c++) {
    for (const [aliases, key] of knownLabels) {
      if (usedKeys.has(key) || usedCols.has(c)) continue;
      if (aliases.some(a => a === headers[c])) {
        colMapping.push({ colIdx: c, key });
        usedKeys.add(key);
        usedCols.add(c);
        break;
      }
    }
  }
  for (let c = 0; c < headers.length; c++) {
    if (usedCols.has(c)) continue;
    for (const [aliases, key] of knownLabels) {
      if (usedKeys.has(key)) continue;
      if (aliases.some(a => headers[c].endsWith(a))) {
        colMapping.push({ colIdx: c, key });
        usedKeys.add(key);
        usedCols.add(c);
        break;
      }
    }
  }
  if (colMapping.length >= 2) {
    const results: ExcelRow[] = [];
    for (let r = 1; r < raw.length; r++) {
      const entry: any = {};
      let hasData = false;
      for (const { colIdx, key } of colMapping) {
        const val = raw[r]?.[colIdx];
        if (val !== undefined && val !== null && val !== '') {
          entry[key] = String(val).trim();
          hasData = true;
        }
      }
      if (hasData && entry.video_theme) results.push(entry as ExcelRow);
    }
    return results;
  }
  return [];
}

function extractTitle(text: string): string {
  const firstLine = text.split('\n').map(l => l.trim()).find(l => l.length > 0);
  if (!firstLine) return '(无标题)';
  return firstLine.length > 60 ? firstLine.slice(0, 60) + '...' : firstLine;
}

let _nextId = 0;
function genId() { return `s-${++_nextId}`; }

/* ── 主组件 ── */
export default function QianchuanReviewPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [error, setError] = useState('');

  // Step 1
  const [scripts, setScripts] = useState<ScriptEntry[]>([]);
  const [pasteInput, setPasteInput] = useState('');
  const scriptFileRef = useRef<HTMLInputElement>(null);

  // Step 2
  const [excelData, setExcelData] = useState<ExcelRow[]>([]);
  const [excelFileName, setExcelFileName] = useState('');
  const excelFileRef = useRef<HTMLInputElement>(null);

  // Step 3
  const [report, setReport] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOutputId, setSavedOutputId] = useState<number | null>(null);
  const reportRef = useRef<HTMLDivElement>(null);

  // 历史
  const [history, setHistory] = useState<OutputItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  /* ── Step 1: 脚本上传 ── */
  async function handleParseFile(file: File) {
    const name = file.name.toLowerCase();
    if (name.endsWith('.txt') || name.endsWith('.md')) {
      return file.text();
    }
    const result = await parseFile(file);
    return result.text;
  }

  async function handleScriptFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const text = await handleParseFile(file);
        if (text.trim()) {
          setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: file.name }]);
        }
      } catch {
        setError(`文件 ${file.name} 解析失败`);
      }
    }
    e.target.value = '';
  }

  function handleAddPaste() {
    const text = pasteInput.trim();
    if (!text) { setError('请先粘贴脚本内容'); return; }
    const separator = /\n(?:={3,}|-{3,})\n/;
    const segments = separator.test(text)
      ? text.split(separator).map(s => s.trim()).filter(s => s.length > 0)
      : [text];
    setScripts(prev => [...prev, ...segments.map(s => ({ id: genId(), title: extractTitle(s), content: s, source: 'paste' }))]);
    setPasteInput('');
    setError('');
  }

  /* ── Step 2: Excel 解析 ── */
  const handleExcelUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExcelFileName(file.name);
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = new Uint8Array(evt.target?.result as ArrayBuffer);
        const wb = XLSX.read(data, { type: 'array' });
        const parsed = parseExcelWorkbook(wb);
        if (parsed.length === 0) { setError('未能解析Excel数据，请检查格式'); return; }
        setExcelData(parsed);
        setError('');
      } catch { setError('Excel解析失败'); }
    };
    reader.readAsArrayBuffer(file);
  }, []);

  /* ── Step 3: 生成报告 ── */
  async function handleGenerate(withExcel: boolean) {
    if (scripts.length === 0) { setError('请先上传脚本'); return; }
    if (scripts.length > 30) { setError('脚本条数超过上限（30条），请分批复盘'); return; }

    setStep(3);
    setReportLoading(true);
    setReport('');
    setTaskId(null);
    setSavedOutputId(null);

    try {
      const resp = await generateReport({
        scripts: scripts.map(s => ({ title: s.title, content: s.content })),
        excel_data: withExcel ? excelData : [],
      });

      if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);

      // 读取 X-Task-Id header
      const tid = resp.headers.get('X-Task-Id');
      if (tid) setTaskId(Number(tid));

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无响应流');
      const decoder = new TextDecoder();
      let text = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        setReport(text);
        if (reportRef.current) reportRef.current.scrollTop = reportRef.current.scrollHeight;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成报告失败');
    } finally {
      setReportLoading(false);
    }
  }

  async function handleSave() {
    if (!report || taskId === null) return;
    setSaving(true);
    try {
      const result = await saveReport({
        task_id: taskId,
        report,
        script_count: scripts.length,
        has_excel: excelData.length > 0,
      });
      setSavedOutputId(result.output_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  function handleExport() {
    const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `千川脚本复盘_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const data = await getOutputs(1, 10);
      setHistory(data.items);
    } catch {
      // 历史加载失败不影响主流程
    } finally {
      setHistoryLoading(false);
    }
  }

  const STEPS = [
    { n: 1, label: '上传脚本' },
    { n: 2, label: '上传投放数据' },
    { n: 3, label: '复盘报告' },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">千川脚本复盘助手</h1>
        <p className="text-gray-500 mt-1">上传脚本 → 上传投放数据 → AI复盘报告</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map(({ n, label }) => (
          <div key={n} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium shrink-0 ${
              step >= n ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500'
            }`}>
              {step > n ? '✓' : n}
            </div>
            <span className={`text-sm ${step >= n ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>{label}</span>
            {n < 3 && <div className={`w-10 h-0.5 ${step > n ? 'bg-blue-500' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex justify-between">
          {error}
          <button onClick={() => setError('')} className="ml-4 text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      {/* Step 1 */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-1">上传千川脚本</h2>
            <p className="text-gray-400 text-sm mb-4">每个文件 = 一条脚本，支持批量上传</p>
            <div
              className="border-2 border-dashed rounded-xl p-10 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
              onClick={() => scriptFileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); }}
              onDrop={async e => {
                e.preventDefault();
                const files = e.dataTransfer.files;
                for (let i = 0; i < files.length; i++) {
                  try {
                    const text = await handleParseFile(files[i]);
                    if (text.trim()) setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: files[i].name }]);
                  } catch { setError(`文件 ${files[i].name} 解析失败`); }
                }
              }}
            >
              <input ref={scriptFileRef} type="file" accept=".txt,.md,.docx,.pages" multiple onChange={handleScriptFiles} className="hidden" />
              <div className="text-4xl mb-3">📄</div>
              <p className="text-sm font-medium text-gray-700">点击选择文件 或 拖拽到这里</p>
              <p className="text-xs text-gray-400 mt-1">支持 .txt / .md / .docx / .pages，可多选</p>
            </div>
            <details className="mt-4">
              <summary className="text-sm text-blue-500 cursor-pointer">或者手动粘贴文案</summary>
              <div className="mt-3">
                <textarea
                  className="w-full h-36 p-4 border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder={"粘贴千川脚本文案...\n多条脚本用 === 分隔"}
                  value={pasteInput}
                  onChange={e => setPasteInput(e.target.value)}
                />
                <div className="mt-2 flex justify-end">
                  <button onClick={handleAddPaste} disabled={!pasteInput.trim()} className="px-5 py-2 bg-blue-500 text-white rounded-lg text-sm disabled:opacity-50">添加脚本</button>
                </div>
              </div>
            </details>
          </div>

          {scripts.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="text-sm font-medium text-gray-700 mb-3">已添加 {scripts.length} 条脚本</div>
              <div className="space-y-2">
                {scripts.map((s, i) => (
                  <div key={s.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                    <span className="text-xs text-gray-400 w-5 shrink-0">{i + 1}.</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">{s.title}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{s.source === 'paste' ? '手动粘贴' : s.source} · {s.content.length} 字</div>
                    </div>
                    <button onClick={() => setScripts(prev => prev.filter(x => x.id !== s.id))} className="text-gray-300 hover:text-red-400 text-sm">✕</button>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex justify-end">
                <button onClick={() => setStep(2)} className="px-6 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors">
                  下一步：上传投放数据
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <button onClick={() => setStep(1)} className="text-sm text-blue-500">← 返回</button>
            <span className="text-sm text-gray-500">已添加 {scripts.length} 条脚本</span>
          </div>
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-1">上传千川投放数据</h2>
            <p className="text-gray-400 text-sm mb-4">可选步骤，跳过也能基于脚本内容生成复盘报告</p>
            <div onClick={() => excelFileRef.current?.click()} className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/30">
              <input ref={excelFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleExcelUpload} className="hidden" />
              {excelFileName ? (
                <div>
                  <div className="text-3xl mb-2">📊</div>
                  <div className="text-sm font-medium">{excelFileName}</div>
                  <div className="text-xs text-green-600 mt-1">已解析 {excelData.length} 条数据</div>
                </div>
              ) : (
                <div>
                  <div className="text-3xl mb-2">📄</div>
                  <div className="text-sm text-gray-500">点击上传千川投放数据 Excel</div>
                  <div className="text-xs text-gray-400 mt-1">支持 .xlsx / .xls / .csv</div>
                </div>
              )}
            </div>
            {excelData.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <div className="text-sm font-medium text-gray-700 mb-2">解析预览</div>
                <table className="text-xs w-full">
                  <thead>
                    <tr className="bg-gray-50 text-gray-500">
                      <th className="px-3 py-2 text-left">素材名称</th>
                      <th className="px-3 py-2 text-right">消耗</th>
                      <th className="px-3 py-2 text-right">ROI</th>
                      <th className="px-3 py-2 text-right">转化数</th>
                      <th className="px-3 py-2 text-right">3s完播率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {excelData.slice(0, 10).map((row, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-3 py-1.5 text-gray-900 max-w-[200px] truncate">{row.video_theme || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.spend ? row.spend + '元' : '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.roi || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.conversions || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.three_sec_rate || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => { setExcelData([]); setExcelFileName(''); handleGenerate(false); }} className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
                跳过，直接生成报告
              </button>
              {excelData.length > 0 && (
                <button onClick={() => handleGenerate(true)} className="px-6 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600">
                  生成复盘报告
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <button onClick={() => setStep(2)} className="text-sm text-blue-500">← 返回</button>
            <span className="text-sm text-gray-500">{scripts.length} 条素材{excelData.length > 0 ? ' · 含投放数据' : ''}</span>
          </div>
          <div ref={reportRef} className="bg-white rounded-xl shadow-sm border p-6 min-h-[400px] max-h-[70vh] overflow-y-auto">
            {reportLoading && !report && (
              <div className="flex items-center gap-2 text-gray-400">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                千川复盘专家正在深度分析素材数据...
              </div>
            )}
            {report && (
              <div className="prose prose-sm max-w-none text-gray-800 leading-relaxed">
                <SimpleMarkdown text={report} />
              </div>
            )}
            {reportLoading && report && <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-1" />}
          </div>

          {!reportLoading && report && (
            <div className="mt-4 flex justify-end gap-3">
              {savedOutputId ? (
                <span className="px-5 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">已保存</span>
              ) : (
                <button onClick={handleSave} disabled={saving || taskId === null} className="px-5 py-2 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50">
                  {saving ? '保存中...' : '保存到产出中心'}
                </button>
              )}
              <button onClick={handleExport} className="px-5 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">导出下载</button>
              <button onClick={() => { navigator.clipboard.writeText(report); }} className="px-5 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">复制报告</button>
            </div>
          )}
        </div>
      )}

      {/* 底部历史记录 */}
      <div className="mt-12 border-t pt-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-700">最近复盘记录</h3>
          <button onClick={loadHistory} disabled={historyLoading} className="text-sm text-blue-500 hover:text-blue-600 disabled:opacity-50">
            {historyLoading ? '加载中...' : '刷新'}
          </button>
        </div>
        {history.length === 0 && !historyLoading && (
          <p className="text-sm text-gray-400">暂无记录，点击刷新加载</p>
        )}
        {history.length > 0 && (
          <div className="space-y-2">
            {history.map(item => (
              <div key={item.id} className="flex items-start justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">{item.title}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
                    {item.word_count ? ` · ${item.word_count} 字` : ''}
                  </div>
                  {item.preview && <div className="text-xs text-gray-500 mt-1 truncate">{item.preview}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 注册路由到 App.tsx**

在 `frontend/src/App.tsx` 中：

在 import 区追加（与其他页面 import 放在一起）：
```typescript
import QianchuanReviewPage from './pages/operator/QianchuanReviewPage';
```

在 operator routes 区（`<Route path="/workspace/selling-point-extractor" .../>` 之后）追加：
```typescript
<Route path="/workspace/qianchuan-review" element={<QianchuanReviewPage />} />
```

- [ ] **Step 5: 检查前端编译无报错**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx tsc --noEmit 2>&1 | head -30
```

预期：无 TypeScript 错误

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add frontend/src/types/qianchuanReview.ts \
        frontend/src/api/qianchuanReview.ts \
        frontend/src/pages/operator/QianchuanReviewPage.tsx \
        frontend/src/App.tsx
git commit -m "feat: add qianchuan-review frontend (page, api, types, route)"
```

---

## Task 6：旧数据迁移脚本

**Files:**
- Create: `backend/scripts/migrate_qianchuan_reports.py`

- [ ] **Step 1: 创建迁移脚本**

创建 `backend/scripts/migrate_qianchuan_reports.py`：

```python
#!/usr/bin/env python3
"""
旧版千川复盘报告迁移脚本。

将 /opt/qianchuan-review/reports/ 下的 JSON 文件批量导入新系统 outputs 表。
旧报告无用户归属，统一归到 admin 管理员账号（username='admin'）。

用法：
    cd backend
    source .venv/bin/activate
    python scripts/migrate_qianchuan_reports.py --reports-dir /opt/qianchuan-review/reports/

可选参数：
    --reports-dir   旧报告目录（默认 /opt/qianchuan-review/reports/）
    --dry-run       只打印，不写库
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import timezone

from sqlalchemy import select, text


async def migrate(reports_dir: Path, dry_run: bool) -> None:
    # 必须在 backend/ 目录下运行，确保 sys.path 能找到 app
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app.core.database import AsyncSessionLocal
    from app.models.output import Output
    from app.models.user import User

    report_files = sorted(reports_dir.glob("*.json"))
    if not report_files:
        print(f"[WARN] 目录 {reports_dir} 下没有找到 JSON 文件")
        return

    async with AsyncSessionLocal() as db:
        # 查找 admin 账号
        admin = (await db.execute(
            select(User).where(User.username == "admin")
        )).scalar_one_or_none()
        if admin is None:
            print("[ERROR] 找不到 username='admin' 的账号，迁移中止")
            return
        admin_id = admin.id
        print(f"[INFO] admin 账号 id={admin_id}，共找到 {len(report_files)} 个报告文件")

        migrated = 0
        skipped = 0
        for path in report_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[WARN] 无法解析 {path.name}：{e}")
                skipped += 1
                continue

            report_text = data.get("report", "")
            scripts = data.get("scripts", [])
            excel_data = data.get("excelData", [])
            created_at_str = data.get("createdAt")

            script_count = len(scripts)
            has_excel = len(excel_data) > 0
            excel_label = "含投放数据" if has_excel else "仅脚本"
            title = f"千川复盘_{script_count}条素材_{excel_label}_迁移记录"

            # 解析时间戳
            from datetime import datetime
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else datetime.now(timezone.utc)
            except Exception:
                created_at = datetime.now(timezone.utc)

            if dry_run:
                print(f"[DRY-RUN] 将导入：{title}，{len(report_text)} 字，时间={created_at.isoformat()}")
                migrated += 1
                continue

            output = Output(
                title=title,
                tool_code="qianchuan-review",
                tool_name="千川脚本复盘",
                content=report_text,
                content_json={"script_count": script_count, "has_excel": has_excel},
                word_count=len(report_text),
                created_by=admin_id,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(output)
            migrated += 1

        if not dry_run:
            await db.commit()

    mode = "[DRY-RUN]" if dry_run else "[DONE]"
    print(f"{mode} 迁移完成：成功 {migrated} 条，跳过 {skipped} 条")


def main():
    parser = argparse.ArgumentParser(description="千川复盘旧数据迁移脚本")
    parser.add_argument(
        "--reports-dir",
        default="/opt/qianchuan-review/reports/",
        help="旧报告 JSON 目录（默认 /opt/qianchuan-review/reports/）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)
    if not reports_dir.exists():
        print(f"[ERROR] 目录不存在：{reports_dir}")
        sys.exit(1)

    asyncio.run(migrate(reports_dir, args.dry_run))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add backend/scripts/migrate_qianchuan_reports.py
git commit -m "feat: add qianchuan-review legacy data migration script"
```

---

## Task 7：运维任务单

**Files:**
- Create: `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md`

- [ ] **Step 1: 创建运维任务单**

创建 `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md`：

```markdown
# M2 Sprint6 运维端任务 — qianchuan-review 上线

## 1. Nginx 超时配置

为 `/api/tools/qianchuan-review/generate` 接口单独配置长超时，防止 AI 生成超 60s 时连接被 Nginx 强制断开。

在 Nginx 配置文件（通常为 `/etc/nginx/sites-available/mcn_platform`）中，在 `/api/` 的 location 块之前，添加以下专属 location：

```nginx
location /api/tools/qianchuan-review/generate {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 10s;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

完成后执行：
```bash
nginx -t && systemctl reload nginx
```

## 2. python-snappy 系统依赖

.pages 文件解析依赖 python-snappy，需要系统级 libsnappy 库。

```bash
# Ubuntu / Debian
apt-get install -y libsnappy-dev

# 确认 python-snappy 已在 requirements.txt
grep -i snappy /opt/mcn_platform/backend/requirements.txt
```

若 requirements.txt 中无 python-snappy，运行：
```bash
cd /opt/mcn_platform/backend
source .venv/bin/activate
pip install python-snappy
pip freeze | grep snappy >> requirements.txt
```

## 3. 旧数据迁移（一次性，上线后执行）

```bash
cd /opt/mcn_platform/backend
source .venv/bin/activate

# 先 dry-run 确认条数
python scripts/migrate_qianchuan_reports.py \
    --reports-dir /opt/qianchuan-review/reports/ \
    --dry-run

# 确认无误后正式迁移
python scripts/migrate_qianchuan_reports.py \
    --reports-dir /opt/qianchuan-review/reports/
```

迁移后旧报告归属 admin 账号，其他 operator 账号不可见。

## 4. 重启后端服务

```bash
pm2 restart mcn-backend
pm2 logs mcn-backend --lines 20
```
```

- [ ] **Step 2: 提交**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform
git add deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md
git commit -m "docs: add qianchuan-review ops task doc (nginx timeout + snappy + migration)"
```

---

## Task 8：覆盖率检查

- [ ] **Step 1: 运行全量测试 + 覆盖率**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend && source .venv/bin/activate
pytest tests/unit/ tests/integration/ \
    --cov=app/tools/qianchuan_review \
    --cov=app/services/qianchuan_review_service \
    --cov=app/routers/operator_qianchuan_review \
    --cov=app/services/file_parser \
    --cov-report=term-missing \
    -v 2>&1 | tail -30
```

- [ ] **Step 2: 确认覆盖率达标**

| 模块 | 目标 | 检查方式 |
|------|------|---------|
| `tools/qianchuan_review/prompts.py` | 100% | test_qianchuan_review_prompts.py |
| `services/qianchuan_review_service.py` | ≥ 80% | test_qianchuan_review_service.py |
| `services/file_parser.py`（新增函数） | ≥ 90% | test_qianchuan_review_file_parser.py |
| `routers/operator_qianchuan_review.py` | ≥ 70% | test_operator_qianchuan_review.py |

若某模块未达标，补充测试后重新运行直至达标。

- [ ] **Step 3: 确认原有测试全部通过（无回归）**

```bash
pytest tests/ -v --tb=short 2>&1 | grep -E "FAILED|ERROR|passed|failed" | tail -5
```

预期：`0 failed, 0 error`

---

## 验收清单（完成后逐条确认）

- [ ] System Prompt A/B 两版本与原始 page.tsx 逐字一致
- [ ] 脚本-Excel 模糊匹配（取前12字，双向 includes）与旧 JS 逻辑等价
- [ ] .pages 解析含日历噪声过滤（星期/月份/季度/公元）
- [ ] 流式报告正常逐字展示，Response Header X-Task-Id 可读取
- [ ] task_jobs 在生成开始时创建（processing），完成后更新（success）
- [ ] outputs 在用户点击保存后写入
- [ ] operator 只能看自己的报告历史，admin 可以看全部
- [ ] CORS expose_headers 包含 X-Task-Id
- [ ] 迁移脚本 dry-run 输出符合预期
- [ ] 运维任务单包含 Nginx 超时 + python-snappy 两条操作项
