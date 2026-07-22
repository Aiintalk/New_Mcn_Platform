"""
Unit tests for generator.render_generation_prompt + generate.

Validates (spec §6.1 / plan Phase 2):
- Two-step rendering: render_system_prompt (name/soul/content_plan) + eval renderer (其余字段)
- **soul ← input_payload['persona']** (KolContext field is persona, template uses {{soul}})
- generate_fn injected as mock callable (no real AI call)
- Missing fields fallback to empty string
"""
from unittest.mock import AsyncMock

import pytest

from app.evaluation.services.generator import generate, render_generation_prompt


class _Version:
    """轻量 EvalVersion 桩。"""

    def __init__(self, config_payload):
        self.config_payload = config_payload


class _TestCase:
    """轻量 EvalTestCase 桩。"""

    def __init__(self, input_payload):
        self.input_payload = input_payload


class TestRenderGenerationPrompt:
    def test_name_soul_content_plan_rendered(self):
        """{{name}}/{{soul}}/{{content_plan}} 被 render_system_prompt 正确渲染。"""
        template = "达人：{{name}}\n人设：{{soul}}\n规划：{{content_plan}}"
        payload = {
            "name": "孙知羽",
            "persona": "护肤达人",
            "content_plan": "每周3条",
        }
        result = render_generation_prompt(template, payload)
        assert "{{name}}" not in result
        assert "{{soul}}" not in result
        assert "{{content_plan}}" not in result
        assert "孙知羽" in result
        assert "护肤达人" in result
        assert "每周3条" in result

    def test_soul_from_persona(self):
        """关键：{{soul}} 取 input_payload['persona']，不是 input_payload['soul']。"""
        template = "人设：{{soul}}"
        payload = {"persona": "正确的人设", "soul": "不应该用这个"}
        result = render_generation_prompt(template, payload)
        assert "正确的人设" in result
        assert "不应该用这个" not in result

    def test_product_info_rendered_by_eval_renderer(self):
        """{{product_info}} 由 eval 自有渲染器（step 2）处理。"""
        template = "产品：{{product_info}}"
        payload = {"product_info": "云朵面霜"}
        result = render_generation_prompt(template, payload)
        assert "云朵面霜" in result
        assert "{{product_info}}" not in result

    def test_original_script_rendered(self):
        """{{original_script}} 由 eval 渲染器处理。"""
        template = "参考脚本：{{original_script}}"
        payload = {"original_script": "原版文案"}
        result = render_generation_prompt(template, payload)
        assert "原版文案" in result

    def test_missing_name_falls_back_to_empty(self):
        """缺失 name → 空串。"""
        template = "[{{name}}]"
        result = render_generation_prompt(template, {"persona": "x"})
        assert "{{name}}" not in result
        assert "[]" in result

    def test_missing_persona_falls_back_to_empty(self):
        """缺失 persona → {{soul}} 空串（不是报错）。"""
        template = "[{{soul}}]"
        result = render_generation_prompt(template, {"name": "x"})
        assert "{{soul}}" not in result
        assert "[]" in result

    def test_missing_product_info_falls_back_to_empty(self):
        """缺失 product_info → 空串。"""
        template = "[{{product_info}}]"
        result = render_generation_prompt(template, {"name": "x"})
        assert "{{product_info}}" not in result
        assert "[]" in result

    def test_all_missing_payload_keys(self):
        """input_payload 完全缺失相关 key → 所有占位符变空串，无残留。"""
        template = "{{name}}-{{soul}}-{{content_plan}}-{{product_info}}"
        result = render_generation_prompt(template, {})
        assert "{{" not in result

    def test_combined_placeholders(self):
        """综合：name/soul/content_plan + product_info 同时渲染。"""
        template = (
            "达人：{{name}}\n人设：{{soul}}\n规划：{{content_plan}}\n"
            "产品：{{product_info}}\n参考：{{original_script}}"
        )
        payload = {
            "name": "陶然",
            "persona": "内容创作者",
            "content_plan": "日常分享",
            "product_info": "精华液",
            "original_script": "参考脚本",
        }
        result = render_generation_prompt(template, payload)
        assert "{{" not in result
        assert "陶然" in result
        assert "内容创作者" in result
        assert "日常分享" in result
        assert "精华液" in result
        assert "参考脚本" in result

    def test_none_payload(self):
        """input_payload=None 不崩溃。"""
        template = "{{name}}{{product_info}}"
        result = render_generation_prompt(template, None)
        assert "{{" not in result

    def test_none_template(self):
        """template=None 不崩溃。"""
        result = render_generation_prompt(None, {"name": "x"})
        assert result == ""

    def test_single_curly_not_replaced(self):
        """单花括号 {xxx} 不被 eval 渲染器替换。"""
        template = "{name}-{{name}}"
        result = render_generation_prompt(template, {"name": "张三"})
        assert "{name}" in result  # 单花括号保留
        assert "张三" in result  # 双花括号被替换


class TestGenerate:
    async def test_generate_calls_generate_fn_with_rendered_prompt(self):
        """generate 调 generate_fn 时传入渲染后的 system prompt。"""
        captured_messages = []

        async def mock_generate_fn(messages):
            captured_messages.extend(messages)
            return "生成的文案"

        version = _Version({"system_prompt_template": "达人：{{name}}"})
        test_case = _TestCase({"name": "孙知羽"})

        result = await generate(mock_generate_fn, version, test_case)

        assert result == "生成的文案"
        assert len(captured_messages) == 1
        assert captured_messages[0]["role"] == "system"
        assert "孙知羽" in captured_messages[0]["content"]
        assert "{{name}}" not in captured_messages[0]["content"]

    async def test_generate_uses_version_config_payload_template(self):
        """generate 从 version.config_payload['system_prompt_template'] 取模板。"""
        async def mock_generate_fn(messages):
            return messages[0]["content"]  # 返回 prompt 本身便于断言

        version = _Version({"system_prompt_template": "产品：{{product_info}}"})
        test_case = _TestCase({"product_info": "面霜"})

        result = await generate(mock_generate_fn, version, test_case)
        assert "面霜" in result

    async def test_generate_returns_generated_text(self):
        """generate 返回 generate_fn 的输出。"""
        async def mock_generate_fn(messages):
            return "AI 生成的文本"

        result = await generate(
            mock_generate_fn,
            _Version({"system_prompt_template": "tpl"}),
            _TestCase({}),
        )
        assert result == "AI 生成的文本"

    async def test_generate_soul_from_persona(self):
        """generate 渲染时 soul ← persona。"""
        captured = []

        async def mock_generate_fn(messages):
            captured.append(messages[0]["content"])
            return "ok"

        await generate(
            mock_generate_fn,
            _Version({"system_prompt_template": "人设：{{soul}}"}),
            _TestCase({"persona": "达人档案"}),
        )
        assert "达人档案" in captured[0]

    async def test_generate_with_async_mock(self):
        """generate 兼容 unittest.mock.AsyncMock。"""
        mock_fn = AsyncMock(return_value="mock output")
        result = await generate(
            mock_fn,
            _Version({"system_prompt_template": "tpl"}),
            _TestCase({}),
        )
        assert result == "mock output"
        mock_fn.assert_awaited_once()
        # 验证调用参数
        call_kwargs = mock_fn.call_args.kwargs
        assert "messages" in call_kwargs
        assert call_kwargs["messages"][0]["role"] == "system"

    async def test_generate_empty_config_payload(self):
        """config_payload 为空 → 模板空串，不崩溃。"""
        async def mock_generate_fn(messages):
            assert messages[0]["content"] == ""
            return "output"

        result = await generate(
            mock_generate_fn,
            _Version({}),
            _TestCase({"name": "x"}),
        )
        assert result == "output"
