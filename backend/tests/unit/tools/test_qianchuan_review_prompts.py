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
    assert '所有判断必须有数据支撑，不说"感觉"' in PROMPT_WITH_EXCEL


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
