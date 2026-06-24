"""
Unit tests for seeding_writer_prompt.render_prompt.

Covers:
- All 14 placeholders individually
- Missing value fallback (None → empty string)
- Multiple occurrences of same placeholder
- Real template snippets
- Prevention of secondary substitution (soul containing {{name}})
"""
from app.services.seeding_writer_prompt import render_prompt


class TestIndividualPlaceholders:
    """Each of the 14 placeholders renders correctly."""

    def test_name(self):
        result = render_prompt("达人：{{name}}", name="孙知羽")
        assert result == "达人：孙知羽"

    def test_soul(self):
        result = render_prompt("档案：{{soul}}", soul="美妆达人")
        assert result == "档案：美妆达人"

    def test_content_plan(self):
        result = render_prompt("规划：{{content_plan}}", content_plan="每周3条")
        assert result == "规划：每周3条"

    def test_product_name(self):
        result = render_prompt("产品：{{product_name}}", product_name="精华液")
        assert result == "产品：精华液"

    def test_product_category(self):
        result = render_prompt("品类：{{product_category}}", product_category="护肤")
        assert result == "品类：护肤"

    def test_product_price(self):
        result = render_prompt("价格：{{product_price}}", product_price="299元")
        assert result == "价格：299元"

    def test_product_selling_points(self):
        result = render_prompt(
            "卖点：{{product_selling_points}}",
            product_selling_points="胶原促生\n紧致提拉",
        )
        assert result == "卖点：胶原促生\n紧致提拉"

    def test_product_target_audience(self):
        result = render_prompt(
            "人群：{{product_target_audience}}",
            product_target_audience="25-35岁女性",
        )
        assert result == "人群：25-35岁女性"

    def test_product_scenario(self):
        result = render_prompt(
            "场景：{{product_scenario}}",
            product_scenario="日常护肤",
        )
        assert result == "场景：日常护肤"

    def test_references(self):
        result = render_prompt(
            "参考：{{references}}",
            references="爆款文案A\n\n---\n\n爆款文案B",
        )
        assert result == "参考：爆款文案A\n\n---\n\n爆款文案B"

    def test_transcript(self):
        result = render_prompt(
            "对标：{{transcript}}",
            transcript="这是一条种草文案",
        )
        assert result == "对标：这是一条种草文案"

    def test_structure_analysis(self):
        result = render_prompt(
            "拆解：{{structure_analysis}}",
            structure_analysis="开头钩子：痛点型",
        )
        assert result == "拆解：开头钩子：痛点型"

    def test_topic(self):
        result = render_prompt("选题：{{topic}}", topic="夏日防晒")
        assert result == "选题：夏日防晒"

    def test_raw_text(self):
        result = render_prompt(
            "原文：{{raw_text}}",
            raw_text="产品说明书全文",
        )
        assert result == "原文：产品说明书全文"


class TestMissingFallback:
    """Missing / None values fallback to empty string."""

    def test_none_value_becomes_empty(self):
        result = render_prompt("达人：[{{name}}]", name=None)
        assert result == "达人：[]"

    def test_no_args_at_all(self):
        result = render_prompt("达人：{{name}} 产品：{{product_name}}")
        assert result == "达人： 产品："

    def test_partial_args(self):
        result = render_prompt(
            "{{name}} - {{product_name}} - {{topic}}",
            name="达人A",
        )
        assert result == "达人A -  - "


class TestMultipleOccurrences:
    """Same placeholder appearing multiple times."""

    def test_repeated_placeholder(self):
        result = render_prompt(
            "{{name}}说：{{name}}认为{{product_name}}好用",
            name="孙知羽",
            product_name="精华液",
        )
        assert result == "孙知羽说：孙知羽认为精华液好用"

    def test_all_14_in_one_template(self):
        template = (
            "{{name}}|{{soul}}|{{content_plan}}|"
            "{{product_name}}|{{product_category}}|{{product_price}}|"
            "{{product_selling_points}}|{{product_target_audience}}|{{product_scenario}}|"
            "{{references}}|{{transcript}}|{{structure_analysis}}|"
            "{{topic}}|{{raw_text}}"
        )
        result = render_prompt(
            template,
            name="N", soul="S", content_plan="C",
            product_name="PN", product_category="PC", product_price="PP",
            product_selling_points="PS", product_target_audience="PT",
            product_scenario="PSC",
            references="R", transcript="T", structure_analysis="SA",
            topic="TO", raw_text="RT",
        )
        assert result == "N|S|C|PN|PC|PP|PS|PT|PSC|R|T|SA|TO|RT"


class TestSecondarySubstitutionPrevention:
    """soul / content_plan containing {{name}} must not cause secondary substitution."""

    def test_soul_containing_name_placeholder(self):
        """If soul = '{{name}} is great', {{name}} in soul should NOT be replaced."""
        result = render_prompt(
            "soul={{soul}} name={{name}}",
            name="达人A",
            soul="这个达人叫{{name}}",
        )
        # soul's {{name}} should remain literal, only top-level {{soul}} and {{name}} replaced
        assert result == "soul=这个达人叫{{name}} name=达人A"

    def test_transcript_containing_placeholder(self):
        result = render_prompt(
            "transcript={{transcript}}",
            transcript="文案含{{topic}}占位",
            topic="不应替换",
        )
        assert result == "transcript=文案含{{topic}}占位"


class TestWhitespaceTolerance:
    """Placeholder with extra whitespace inside braces."""

    def test_whitespace_in_braces(self):
        result = render_prompt("达人：{{ name }} 产品：{{product_name }}", name="A", product_name="B")
        assert result == "达人：A 产品：B"

    def test_newline_in_braces(self):
        result = render_prompt("{{\nname\n}}", name="X")
        assert result == "X"


class TestRealTemplateSnippets:
    """Realistic template snippets from the seed prompts."""

    def test_writing_prompt_snippet(self):
        template = """产品名称：{{product_name}}
产品品类：{{product_category}}
价格：{{product_price}}
核心卖点：{{product_selling_points}}
目标人群：{{product_target_audience}}
使用场景：{{product_scenario}}

## 对标文案
{{transcript}}

## 达人档案
{{soul}}
"""
        result = render_prompt(
            template,
            product_name="玻尿酸精华", product_category="护肤", product_price="299",
            product_selling_points="保湿\n修护", product_target_audience="干皮",
            product_scenario="早晚", transcript="原文...", soul="美妆达人",
        )
        assert "玻尿酸精华" in result
        assert "299" in result
        assert "原文..." in result
        assert "{{" not in result  # No residual placeholders

    def test_no_residual_placeholders_after_render(self):
        template = "{{name}} {{soul}} {{topic}} {{raw_text}}"
        result = render_prompt(template, name="A", soul="B", topic="C", raw_text="D")
        assert "{{" not in result
        assert "}}" not in result

    def test_empty_template_returns_empty(self):
        assert render_prompt("") == ""
