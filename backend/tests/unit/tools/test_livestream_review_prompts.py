"""精确比对 livestream-review System Prompt 常量（与原始 page.tsx 逐字一致）。"""
from app.tools.livestream_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL


# ---------- PROMPT_WITH_EXCEL ----------

def test_prompt_with_excel_starts_correctly():
    assert PROMPT_WITH_EXCEL.startswith("你是直播间运营复盘专家。")


def test_prompt_with_excel_mentions_excel_data():
    assert "GMV、峰值在线、平均停留时长、成交单数、互动数据等" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_has_seven_modules():
    assert "1. **开场留人分析**" in PROMPT_WITH_EXCEL
    assert "2. **留存诊断**" in PROMPT_WITH_EXCEL
    assert "3. **互动设计拆解**" in PROMPT_WITH_EXCEL
    assert "4. **转化话术效率**" in PROMPT_WITH_EXCEL
    assert "5. **亏损场次诊断**" in PROMPT_WITH_EXCEL
    assert "6. **人设一致性**" in PROMPT_WITH_EXCEL
    assert "7. **下场优化建议**" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_requirement_data_support():
    assert '所有判断必须有数据支撑，不说"感觉"' in PROMPT_WITH_EXCEL


def test_prompt_with_excel_requirement_direct_language():
    assert "语言直接，像一个跟主播一起复盘的操盘手在开会" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_requirement_executable():
    assert "每条建议都能直接执行，主播下次就能改" in PROMPT_WITH_EXCEL


def test_prompt_with_excel_requirement_skip_empty():
    assert "如果某个模块没有足够数据支撑，跳过，不凑字数" in PROMPT_WITH_EXCEL


# ---------- PROMPT_WITHOUT_EXCEL ----------

def test_prompt_without_excel_starts_correctly():
    assert PROMPT_WITHOUT_EXCEL.startswith("你是直播间运营复盘专家。")


def test_prompt_without_excel_no_data_mention():
    assert "GMV、峰值在线" not in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_has_five_modules():
    assert "1. **最好的脚本段落**" in PROMPT_WITHOUT_EXCEL
    assert "2. **建议重写的段落**" in PROMPT_WITHOUT_EXCEL
    assert "3. **互动话术分析**" in PROMPT_WITHOUT_EXCEL
    assert "4. **转化逻辑分析**" in PROMPT_WITHOUT_EXCEL
    assert "5. **新脚本方向**" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_requirement_cite_original():
    assert "分析必须引用具体话术原文，不是只看标题" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_requirement_deep_analysis():
    assert "分析要深入到具体的话术句子和段落" in PROMPT_WITHOUT_EXCEL


def test_prompt_without_excel_requirement_skip_empty():
    assert "如果某个模块没有足够内容支撑，跳过，不凑字数" in PROMPT_WITHOUT_EXCEL


# ---------- 两版 Prompt 共同约束 ----------

def test_prompts_are_different():
    assert PROMPT_WITH_EXCEL != PROMPT_WITHOUT_EXCEL


def test_both_prompts_mention_livestream_expert():
    for p in [PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL]:
        assert "直播间运营复盘专家" in p
