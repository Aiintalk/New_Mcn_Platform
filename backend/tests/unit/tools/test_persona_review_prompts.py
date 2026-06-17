"""单元测试：persona_review prompts 精确比对。"""
from app.tools.persona_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL


class TestPersonaReviewPrompts:
    def test_with_excel_contains_key_phrases(self):
        assert "抖音顶级内容操盘大师" in PROMPT_WITH_EXCEL
        assert "运营数据（点赞、完播率、5s完播率、投放金额等）" in PROMPT_WITH_EXCEL
        assert "投放效率分析" in PROMPT_WITH_EXCEL
        assert "完播率洞察" in PROMPT_WITH_EXCEL

    def test_without_excel_contains_key_phrases(self):
        assert "抖音顶级内容操盘大师" in PROMPT_WITHOUT_EXCEL
        assert "完整脚本文案**。你需要深入分析" in PROMPT_WITHOUT_EXCEL
        assert "投放效率分析" not in PROMPT_WITHOUT_EXCEL
        assert "完播率洞察" not in PROMPT_WITHOUT_EXCEL

    def test_with_excel_has_five_modules(self):
        """版本 A 有 5 个分析模块（1-5）"""
        for i in range(1, 6):
            assert f"{i}. **" in PROMPT_WITH_EXCEL

    def test_without_excel_has_three_modules(self):
        """版本 B 有 3 个分析模块（1-3），无投放和完播率模块"""
        assert "3. **值得新增的内容方向**" in PROMPT_WITHOUT_EXCEL
        assert "4. **" not in PROMPT_WITHOUT_EXCEL

    def test_prompts_are_different(self):
        assert PROMPT_WITH_EXCEL != PROMPT_WITHOUT_EXCEL

    def test_prompts_are_non_empty(self):
        assert len(PROMPT_WITH_EXCEL) > 100
        assert len(PROMPT_WITHOUT_EXCEL) > 100

    def test_with_excel_exact_opening(self):
        """原文开头精确比对"""
        assert PROMPT_WITH_EXCEL.startswith(
            "你是抖音顶级内容操盘大师。你研究过抖音上所有头部IP的内容策略"
        )

    def test_without_excel_exact_opening(self):
        assert PROMPT_WITHOUT_EXCEL.startswith(
            "你是抖音顶级内容操盘大师。你研究过抖音上所有头部IP的内容策略"
        )

    def test_requirements_section_identical(self):
        """两版本的「要求」部分完全一致"""
        requirements = (
            "- 你有完整脚本，分析要深入到具体的文案细节，不是只看标题\n"
            "- 引用脚本中的具体句子和段落来支撑你的判断\n"
            "- 语言直接，不客气，像一个严格但靠谱的操盘手给团队开复盘会\n"
            "- 不说正确的废话，每一条建议都要能直接执行\n"
            "- 如果某个模块没什么可说的，就跳过，不要凑字数"
        )
        assert requirements in PROMPT_WITH_EXCEL
        assert requirements in PROMPT_WITHOUT_EXCEL
