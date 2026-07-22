"""
Unit tests for rubric_resolver.build_scoring_prompt.

Validates (spec §6.4 / plan Phase 2):
- {{rubric_text}} filled with level×criteria sorted by level DESC
- double-curly placeholders {{xxx}} rendered from context
- missing context values fallback to empty string
- double-curly vs single-curly distinction ({{xxx}} replaced, {xxx} untouched)
- scenario_tag not involved in selection (caller-provided rubrics used as-is)
"""
from app.evaluation.services.rubric_resolver import build_scoring_prompt


class _Dim:
    """轻量 EvalDimension 桩（避免 DB 依赖）。"""

    def __init__(self, prompt_template, score_min=1, score_max=10):
        self.prompt_template = prompt_template
        self.score_min = score_min
        self.score_max = score_max


class _Rubric:
    """轻量 EvalRubric 桩。"""

    def __init__(self, level, criteria, scenario_tag=None):
        self.level = level
        self.criteria = criteria
        self.scenario_tag = scenario_tag


class TestBuildScoringPromptRubricText:
    def test_rubric_text_assembled_descending_by_level(self):
        """rubrics 按 level 降序拼入 {{rubric_text}}。"""
        dim = _Dim("评分标准：\n{{rubric_text}}")
        rubrics = [
            _Rubric(level=5, criteria="中等"),
            _Rubric(level=10, criteria="满分"),
            _Rubric(level=1, criteria="差"),
        ]
        result = build_scoring_prompt(dim, rubrics, {})
        # 降序：10 → 5 → 1
        assert "10分：满分" in result
        assert "5分：中等" in result
        assert "1分：差" in result
        idx_10 = result.index("10分")
        idx_5 = result.index("5分")
        idx_1 = result.index("1分")
        assert idx_10 < idx_5 < idx_1

    def test_empty_rubrics_produces_empty_rubric_text(self):
        """rubrics 为空时 {{rubric_text}} → 空串。"""
        dim = _Dim("标准[{{rubric_text}}]结束")
        result = build_scoring_prompt(dim, [], {})
        assert "{{rubric_text}}" not in result
        assert "标准[]" in result or "标准\n结束" not in result

    def test_rubric_none_criteria_treated_as_empty(self):
        """criteria=None 时按空串处理。"""
        dim = _Dim("{{rubric_text}}")
        rubrics = [_Rubric(level=10, criteria=None)]
        result = build_scoring_prompt(dim, rubrics, {})
        assert "10分：" in result


class TestBuildScoringPromptPlaceholders:
    def test_context_placeholders_filled(self):
        """context 中的 {{persona}} / {{product_info}} 被正确填充。"""
        dim = _Dim("达人：{{persona}}\n产品：{{product_info}}")
        result = build_scoring_prompt(
            dim, [], {"persona": "护肤达人", "product_info": "云朵面霜"}
        )
        assert "{{persona}}" not in result
        assert "{{product_info}}" not in result
        assert "护肤达人" in result
        assert "云朵面霜" in result

    def test_generated_output_filled(self):
        """{{generated_output}} 从 context 取值。"""
        dim = _Dim("被评脚本：\n{{generated_output}}")
        result = build_scoring_prompt(
            dim, [], {"generated_output": "这是生成的文案"}
        )
        assert "这是生成的文案" in result
        assert "{{generated_output}}" not in result

    def test_missing_context_falls_back_to_empty(self):
        """context 中缺失的占位符 → 空串。"""
        dim = _Dim("[{{persona}}]-[{{missing_key}}]")
        result = build_scoring_prompt(dim, [], {"persona": "达人"})
        assert "{{persona}}" not in result
        assert "{{missing_key}}" not in result
        # persona 被填充，missing_key 变空串
        assert "达人" in result
        assert "[]" in result  # missing_key → 空

    def test_none_value_falls_back_to_empty(self):
        """context 中值为 None → 空串。"""
        dim = _Dim("[{{persona}}]")
        result = build_scoring_prompt(dim, [], {"persona": None})
        assert "{{persona}}" not in result
        assert "[]" in result

    def test_all_placeholders_combined(self):
        """综合：rubric_text + context 字段同时渲染。"""
        dim = _Dim(
            "评分标准：\n{{rubric_text}}\n\n"
            "被评脚本：{{generated_output}}\n"
            "达人：{{persona}}\n"
            "产品：{{product_info}}"
        )
        rubrics = [_Rubric(level=10, criteria="满分"), _Rubric(level=8, criteria="良好")]
        result = build_scoring_prompt(
            dim,
            rubrics,
            {
                "generated_output": "生成的文案",
                "persona": "达人A",
                "product_info": "面霜",
            },
        )
        assert "{{" not in result  # 所有占位符均已替换
        assert "10分：满分" in result
        assert "8分：良好" in result
        assert "生成的文案" in result
        assert "达人A" in result
        assert "面霜" in result


class TestBuildScoringPromptDoubleCurly:
    def test_single_curly_not_replaced(self):
        """单花括号 {xxx} 不被替换（只有双花括号 {{xxx}} 被处理）。"""
        dim = _Dim("单{soul}双{{soul}}")
        result = build_scoring_prompt(dim, [], {"soul": "人设"})
        # 单花括号保留，双花括号替换
        assert "{soul}" in result
        assert "{{soul}}" not in result
        # "人设" 出现一次（来自 {{soul}} 的替换）
        assert result.count("人设") == 1

    def test_no_residual_double_curly(self):
        """渲染后无残留 {{...}}（缺失值也变空串）。"""
        dim = _Dim("{{a}}{{b}}{{c}}")
        result = build_scoring_prompt(dim, [], {"a": "1"})
        assert "{{" not in result
        assert "1" in result


class TestBuildScoringPromptEdgeCases:
    def test_dimension_none_prompt_template(self):
        """dimension.prompt_template=None → 返回空串。"""
        dim = _Dim(None)
        result = build_scoring_prompt(dim, [], {"persona": "x"})
        assert result == ""

    def test_dimension_none(self):
        """dimension=None 不崩溃，返回空串。"""
        result = build_scoring_prompt(None, [], {"persona": "x"})
        assert result == ""

    def test_context_none(self):
        """context=None 不崩溃。"""
        dim = _Dim("{{rubric_text}}")
        result = build_scoring_prompt(dim, [], None)
        assert "{{rubric_text}}" not in result

    def test_rubrics_none(self):
        """rubrics=None 不崩溃，按空列表处理。"""
        dim = _Dim("[{{rubric_text}}]")
        result = build_scoring_prompt(dim, None, {})
        assert "{{rubric_text}}" not in result
