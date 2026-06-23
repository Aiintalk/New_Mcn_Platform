"""
Unit tests for persona-writer Prompt template rendering.

Validates:
- 7 placeholders (name/soul/content_plan/transcript/structure_analysis/topic/is_custom) replaced correctly
- {{is_custom}}...{{/is_custom}} and {{!is_custom}}...{{/!is_custom}} conditional blocks
- Missing placeholders do not crash (fallback to empty string)
- Multiple occurrences replaced
- Real seed template renders
"""
import pytest

from app.services.persona_writer_prompt import render_prompt


class TestPlaceholderReplacement:
    """7 占位符替换测试"""

    def test_all_simple_placeholders_replaced(self):
        template = (
            "达人：{{name}}\n"
            "档案：{{soul}}\n"
            "规划：{{content_plan}}\n"
            "文案：{{transcript}}\n"
            "分析：{{structure_analysis}}\n"
            "选题：{{topic}}"
        )
        result = render_prompt(
            template,
            name="孙知羽",
            soul="一个有梦想的达人",
            content_plan="每周更新3条",
            transcript="对标文案正文",
            structure_analysis="开头+主体+收束",
            topic="独立女性的底线",
        )
        assert "{{" not in result
        assert "孙知羽" in result
        assert "一个有梦想的达人" in result
        assert "每周更新3条" in result
        assert "对标文案正文" in result
        assert "开头+主体+收束" in result
        assert "独立女性的底线" in result

    def test_name_placeholder(self):
        result = render_prompt("达人：{{name}}", name="陶然")
        assert "陶然" in result
        assert "{{" not in result

    def test_transcript_placeholder(self):
        result = render_prompt("文案：{{transcript}}", transcript="第一条文案")
        assert "第一条文案" in result

    def test_structure_analysis_placeholder(self):
        result = render_prompt("分析：{{structure_analysis}}", structure_analysis="骨架结构")
        assert "骨架结构" in result

    def test_topic_placeholder(self):
        result = render_prompt("选题：{{topic}}", topic="职场焦虑")
        assert "职场焦虑" in result


class TestConditionalBlocks:
    """is_custom 双模式条件块测试"""

    def test_is_custom_true_keeps_custom_block(self):
        template = (
            "{{is_custom}}这是自定义模式{{/is_custom}}"
            "{{!is_custom}}这是默认模式{{/!is_custom}}"
        )
        result = render_prompt(template, is_custom=True)
        assert "这是自定义模式" in result
        assert "这是默认模式" not in result

    def test_is_custom_false_keeps_default_block(self):
        template = (
            "{{is_custom}}这是自定义模式{{/is_custom}}"
            "{{!is_custom}}这是默认模式{{/!is_custom}}"
        )
        result = render_prompt(template, is_custom=False)
        assert "这是默认模式" in result
        assert "这是自定义模式" not in result

    def test_is_custom_none_defaults_to_true(self):
        template = (
            "{{is_custom}}自定义{{/is_custom}}"
            "{{!is_custom}}默认{{/!is_custom}}"
        )
        result = render_prompt(template, is_custom=None)
        assert "自定义" in result
        assert "默认" not in result

    def test_conditional_block_with_placeholders_inside(self):
        """条件块内部也包含占位符，替换后仍正确。"""
        template = (
            "{{is_custom}}员工想法：{{topic}}{{/is_custom}}"
            "{{!is_custom}}默认选题：{{topic}}{{/!is_custom}}"
        )
        result = render_prompt(template, is_custom=True, topic="我的想法")
        assert "员工想法：我的想法" in result
        assert "默认选题" not in result


class TestMissingFallback:
    """缺失值 fallback 为空字符串"""

    def test_all_none_does_not_crash(self):
        template = "{{name}} {{soul}} {{content_plan}} {{transcript}} {{structure_analysis}} {{topic}}"
        result = render_prompt(template)
        assert "{{" not in result

    def test_partial_none(self):
        result = render_prompt(
            "{{name}} - {{soul}}",
            name="张三",
            soul=None,
        )
        assert "张三" in result
        assert "{{soul}}" not in result


class TestMultipleOccurrences:
    """同一占位符多次出现全部替换"""

    def test_name_multiple_times(self):
        template = "{{name}}说：{{name}}来了！{{name}}走了。"
        result = render_prompt(template, name="李四")
        assert result.count("李四") == 3
        assert "{{" not in result


class TestRealTemplate:
    """接近真实种子 Prompt 的模板验证"""

    def test_writing_prompt_renders_custom_mode(self):
        """writing_prompt 在 custom 模式下正确渲染。"""
        template = """你是一个专业的人设内容仿写助手。

## 三条铁律
1. 写完整脚本
2. 结构参考对标原文。{{is_custom}}但员工的选题想法是核心{{/is_custom}}{{!is_custom}}仿写必须一一对应{{/!is_custom}}
3. 字数只少不多

## 优先级
{{is_custom}}1. 员工选题想法
2. 对标结构
3. 达人风格{{/is_custom}}
{{!is_custom}}1. 原文结构
2. 分析结果
3. 人格档案{{/!is_custom}}

### 达人档案
{{soul}}

## 对标文案
{{transcript}}

## 选题
{{topic}}"""
        result = render_prompt(
            template,
            soul="清华毕业的内容创作者",
            transcript="对标文案原文",
            topic="我的选题想法",
            is_custom=True,
        )
        assert "但员工的选题想法是核心" in result
        assert "仿写必须一一对应" not in result
        assert "1. 员工选题想法" in result
        assert "1. 原文结构" not in result
        assert "清华毕业的内容创作者" in result
        assert "对标文案原文" in result
        assert "我的选题想法" in result
        assert "{{" not in result

    def test_writing_prompt_renders_default_mode(self):
        """writing_prompt 在 default 模式下正确渲染。"""
        template = """铁律：
{{is_custom}}结构为想法服务{{/is_custom}}{{!is_custom}}仿写必须一一对应{{/!is_custom}}

优先级：
{{!is_custom}}1. 原文结构
2. 分析结果{{/!is_custom}}

### 达人档案
{{soul}}"""
        result = render_prompt(
            template,
            soul="达人档案",
            is_custom=False,
        )
        assert "仿写必须一一对应" in result
        assert "结构为想法服务" not in result
        assert "1. 原文结构" in result
        assert "达人档案" in result

    def test_evaluation_prompt_renders(self):
        """evaluation_prompt 渲染（只需 transcript）。"""
        template = "评估以下文案开头：\n{{transcript}}"
        result = render_prompt(template, transcript="这是一个测试文案")
        assert "这是一个测试文案" in result
        assert "{{" not in result

    def test_soul_content_with_curly_braces_no_double_replace(self):
        """soul 内容包含 {{name}} 文本时不会被二次替换（正则一次性替换保证）。

        re.sub 对原始模板字符串操作，soul 值中的 {{name}} 不在原始模板中，
        因此替换 soul 后其内容中的 {{name}} 残留——这是预期行为（防二次替换）。
        """
        template = "达人：{{name}}\n档案：{{soul}}"
        result = render_prompt(
            template,
            name="张三",
            soul="这个达人叫{{name}}，是个厉害的人",
        )
        # {{name}} 在原始模板中被替换为 "张三"
        assert "张三" in result
        # soul 值中的 {{name}} 残留（不在原始模板中，正则不匹配）
        # 这是防二次替换的核心测试点
        assert "这个达人叫{{name}}" in result
