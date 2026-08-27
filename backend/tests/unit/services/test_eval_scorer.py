"""
Unit tests for scorer.parse_score_response + score.

Validates (spec §6.4/§6.5 / plan Phase 2):
- JSON parse three strategies: ① direct json.loads → ② regex {...} → ③ code block
- Score clamping to [score_min, score_max]
- Missing fields default (strengths/weaknesses empty list)
- score_fn injected as mock callable (no real AI call)
- score() uses rubric_resolver.build_scoring_prompt internally
"""
from unittest.mock import AsyncMock

import pytest

from app.evaluation.services.scorer import ParsedScore, parse_score_response, score
from app.evaluation.services.rubric_resolver import build_scoring_prompt


class _Dim:
    """轻量 EvalDimension 桩。"""

    def __init__(self, prompt_template="评分：{{rubric_text}}\n输出：{{generated_output}}",
                 score_min=1, score_max=10):
        self.prompt_template = prompt_template
        self.score_min = score_min
        self.score_max = score_max


class _Rubric:
    """轻量 EvalRubric 桩。"""

    def __init__(self, level, criteria):
        self.level = level
        self.criteria = criteria


class TestParseScoreResponseStrategy1Direct:
    """策略 ①：直接 json.loads。"""

    def test_direct_json_full_fields(self):
        raw = '{"score": 8, "reasoning": "钩子强", "strengths": ["开头好"], "weaknesses": ["结尾弱"]}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 8
        assert parsed.reasoning == "钩子强"
        assert "开头好" in parsed.strengths
        assert "结尾弱" in parsed.weaknesses

    def test_direct_json_score_only(self):
        raw = '{"score": 5}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 5
        assert parsed.reasoning == ""
        assert parsed.strengths == []
        assert parsed.weaknesses == []


class TestParseScoreResponseStrategy2Regex:
    """策略 ②：正则/子串提取 {...}。"""

    def test_extract_from_surrounding_text(self):
        raw = '评分结果如下：\n{"score": 7, "reasoning": "中等"}\n以上是评分。'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 7
        assert parsed.reasoning == "中等"

    def test_extract_with_whitespace(self):
        raw = '前缀文字 {"score": 9, "reasoning": "好"} 后缀文字'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 9
        assert parsed.reasoning == "好"


class TestParseScoreResponseStrategy3CodeBlock:
    """策略 ③：代码块提取。"""

    def test_json_code_block(self):
        raw = '```json\n{"score": 6, "reasoning": "及格"}\n```'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 6
        assert parsed.reasoning == "及格"

    def test_plain_code_block(self):
        raw = '```\n{"score": 4, "reasoning": "差"}\n```'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 4
        assert parsed.reasoning == "差"

    def test_code_block_with_surrounding_text(self):
        raw = 'AI 评委回复：\n```json\n{"score": 10, "reasoning": "满分"}\n```\n完毕'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 10
        assert parsed.reasoning == "满分"


class TestParseScoreResponseClamp:
    """score 范围校验。"""

    def test_clamp_high_score(self):
        raw = '{"score": 15}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 10  # clamp to max

    def test_clamp_low_score(self):
        raw = '{"score": -3}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 1  # clamp to min

    def test_score_at_min_boundary(self):
        raw = '{"score": 1}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 1

    def test_score_at_max_boundary(self):
        raw = '{"score": 10}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 10

    def test_float_score_accepted(self):
        """AI 返回浮点分也能解析。"""
        raw = '{"score": 8.5}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 8.5

    def test_string_score_accepted(self):
        """score 为字符串数字也能解析。"""
        raw = '{"score": "7"}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 7.0


class TestParseScoreResponseDefaults:
    """缺失字段默认值。"""

    def test_missing_strengths_defaults_empty(self):
        raw = '{"score": 8, "reasoning": "好"}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.strengths == []

    def test_missing_weaknesses_defaults_empty(self):
        raw = '{"score": 8}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.weaknesses == []

    def test_missing_reasoning_defaults_empty(self):
        raw = '{"score": 8}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.reasoning == ""

    def test_null_fields_default(self):
        """字段值为 null → 默认值。"""
        raw = '{"score": 8, "reasoning": null, "strengths": null, "weaknesses": null}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 8
        assert parsed.reasoning == ""
        assert parsed.strengths == []
        assert parsed.weaknesses == []

    def test_strengths_non_list_defaults_empty(self):
        """strengths 不是 list → 默认空 list。"""
        raw = '{"score": 8, "strengths": "不是列表"}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.strengths == []


class TestParseScoreResponseFailure:
    """完全无法解析的情况。"""

    def test_unparseable_returns_default(self):
        """完全无法解析 → score=score_min, reasoning=失败信息。"""
        raw = "这不是JSON"
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 1  # clamp(0, 1, 10) = 1
        assert "Failed to parse" in parsed.reasoning
        assert parsed.strengths == []
        assert parsed.weaknesses == []

    def test_empty_string(self):
        parsed = parse_score_response("", 1, 10)
        assert parsed.score == 1
        assert "Failed" in parsed.reasoning

    def test_none_input(self):
        parsed = parse_score_response(None, 1, 10)
        assert parsed.score == 1

    def test_json_array_not_object_strategy1_falls_through(self):
        """json.loads 返回 list（非 dict）→ 策略①跳过；策略②提取内层 {...} 成功。"""
        raw = '[{"score": 8}]'
        parsed = parse_score_response(raw, 1, 10)
        # 策略②从数组中提取出内层对象 {"score": 8}
        assert parsed.score == 8

    def test_truly_unparseable_text(self):
        """完全无 JSON 结构的文本 → 解析失败。"""
        raw = "这完全不是JSON也没有花括号"
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 1
        assert "Failed" in parsed.reasoning

    def test_missing_score_key(self):
        """缺 score key → 默认 0 → clamp 到 score_min。"""
        raw = '{"reasoning": "no score"}'
        parsed = parse_score_response(raw, 1, 10)
        assert parsed.score == 1  # clamp(0, 1, 10) = 1
        assert parsed.reasoning == "no score"


class TestScoreEntryPoint:
    """score() 主入口测试。"""

    async def test_score_calls_score_fn_with_scoring_prompt(self):
        """score 调 score_fn 时传入渲染后的评分 prompt。"""
        captured_messages = []

        async def mock_score_fn(messages):
            captured_messages.extend(messages)
            return '{"score": 8, "reasoning": "好"}'

        dim = _Dim(prompt_template="评分标准：{{rubric_text}}\n输出：{{generated_output}}\n达人：{{persona}}")
        rubrics = [_Rubric(level=10, criteria="满分")]

        parsed = await score(
            mock_score_fn, dim, rubrics, "生成的文案", {"persona": "达人"}
        )

        assert parsed.score == 8
        assert len(captured_messages) == 1
        assert captured_messages[0]["role"] == "user"
        # prompt 包含渲染后的内容
        assert "10分：满分" in captured_messages[0]["content"]
        assert "生成的文案" in captured_messages[0]["content"]
        assert "达人" in captured_messages[0]["content"]

    async def test_score_returns_parsed_result(self):
        """score 返回 ParsedScore。"""
        async def mock_score_fn(messages):
            return '{"score": 9, "reasoning": "优秀", "strengths": ["a"], "weaknesses": ["b"]}'

        parsed = await score(mock_score_fn, _Dim(), [], "output", {})
        assert isinstance(parsed, ParsedScore)
        assert parsed.score == 9
        assert parsed.reasoning == "优秀"

    async def test_score_with_async_mock(self):
        """score 兼容 AsyncMock。"""
        mock_fn = AsyncMock(return_value='{"score": 7}')
        parsed = await score(mock_fn, _Dim(), [], "test output", {})
        assert parsed.score == 7
        mock_fn.assert_awaited_once()

    async def test_score_uses_dimension_score_range(self):
        """score 从 dimension 取 score_min/score_max 传给 parser。"""
        async def mock_score_fn(messages):
            return '{"score": 150}'  # 超出范围

        dim = _Dim(score_min=1, score_max=10)
        parsed = await score(mock_fn := mock_score_fn, dim, [], "output", {})
        assert parsed.score == 10  # clamp 到 max

    async def test_score_injects_generated_output_into_context(self):
        """score 把 generated_output 注入 context 供 {{generated_output}} 使用。"""
        captured = []

        async def mock_score_fn(messages):
            captured.append(messages[0]["content"])
            return '{"score": 5}'

        dim = _Dim(prompt_template="输出：{{generated_output}}")
        await score(mock_score_fn, dim, [], "这是被评文本", {})
        assert "这是被评文本" in captured[0]

    async def test_score_empty_context(self):
        """context=None 不崩溃。"""
        async def mock_score_fn(messages):
            return '{"score": 5}'

        parsed = await score(mock_score_fn, _Dim(), [], "output", None)
        assert parsed.score == 5


class TestScoreJsonGuards:
    """P0 评分可信度：首尾双约束 + 解析失败重试（run21 兜底 1 分回归）。"""

    async def test_prompt_has_head_and_tail_guards(self):
        """组装的 prompt 首部有任务声明、末尾有 JSON 强守卫（含实际分值范围）。"""
        captured = []

        async def mock_fn(messages):
            captured.append(messages[0]["content"])
            return '{"score": 8}'

        dim = _Dim(prompt_template="标准：{{rubric_text}}", score_min=1, score_max=10)
        await score(mock_fn, dim, [], "文本", {})

        p = captured[0]
        assert p.startswith("【任务】")                      # 首部守卫
        assert "整数1-10" in p                              # 末尾守卫带实际范围
        # 顺序：头守卫 < 模板内容 < 尾守卫
        assert p.index("【任务】") < p.index("标准：") < p.rindex("【输出要求】")

    async def test_parse_failure_retries_once_then_succeeds(self):
        """首次输出非 JSON → 自动纠错重评一次，第二次成功则不落兜底分。"""
        calls = []

        async def flaky_fn(messages):
            calls.append(messages[0]["content"])
            if len(calls) == 1:
                return "我觉得这条文案写得挺好的，给 9 分吧！"   # 无 JSON
            return '{"score": 9, "reasoning": "重试成功"}'

        parsed = await score(flaky_fn, _Dim(), [], "文本", {})
        assert len(calls) == 2                               # 恰好重试一次
        assert "无法被解析为 JSON" in calls[1]                # 重试带纠错提示
        assert parsed.score == 9                             # 真实分，非兜底
        assert parsed.parse_failed is False

    async def test_retry_also_fails_falls_back_with_flag(self):
        """两次都解析失败 → 落兜底分且 parse_failed=True（可追溯异常评分）。"""
        async def bad_fn(messages):
            return "还是不给 JSON"

        parsed = await score(bad_fn, _Dim(), [], "文本", {})
        assert parsed.score == 1                             # 兜底 = score_min
        assert parsed.parse_failed is True
        assert parsed.reasoning == "Failed to parse AI response"

    async def test_success_first_try_no_retry(self):
        """首次成功不重试（省一次模型调用）。"""
        calls = []

        async def ok_fn(messages):
            calls.append(1)
            return '{"score": 7}'

        parsed = await score(ok_fn, _Dim(), [], "文本", {})
        assert len(calls) == 1
        assert parsed.score == 7
