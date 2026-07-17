"""
Unit tests for qianchuan-writer Prompt template rendering.

Validates:
- {{name}} / {{soul}} / {{content_plan}} placeholders are replaced correctly
- Missing placeholders do not crash (fallback to empty string)
"""
import pytest

from app.services.qianchuan_writer_prompt import render_system_prompt


class TestRenderSystemPrompt:
    def test_all_placeholders_replaced(self):
        template = "达人：{{name}}\n档案：{{soul}}\n规划：{{content_plan}}"
        result = render_system_prompt(
            template,
            name="孙知羽",
            soul="一个有梦想的达人",
            content_plan="每周更新3条视频",
        )
        assert "{{name}}" not in result
        assert "{{soul}}" not in result
        assert "{{content_plan}}" not in result
        assert "孙知羽" in result
        assert "一个有梦想的达人" in result
        assert "每周更新3条视频" in result

    def test_missing_name_falls_back_to_empty(self):
        template = "达人：{{name}}"
        result = render_system_prompt(template, name=None, soul="x", content_plan="y")
        assert "{{name}}" not in result
        assert "达人：" in result

    def test_missing_soul_falls_back_to_empty(self):
        template = "档案：{{soul}}"
        result = render_system_prompt(template, name="x", soul=None, content_plan="y")
        assert "{{soul}}" not in result

    def test_missing_content_plan_falls_back_to_empty(self):
        template = "规划：{{content_plan}}"
        result = render_system_prompt(template, name="x", soul="y", content_plan=None)
        assert "{{content_plan}}" not in result

    def test_all_missing_does_not_crash(self):
        template = "{{name}} {{soul}} {{content_plan}}"
        # all None — should not raise
        result = render_system_prompt(template, name=None, soul=None, content_plan=None)
        assert "{{" not in result

    def test_multiple_occurrences(self):
        template = "{{name}}说：{{name}}来了！{{soul}}"
        result = render_system_prompt(
            template, name="陶然", soul="内容创作者", content_plan="x"
        )
        assert result.count("陶然") == 2
        assert "内容创作者" in result

    def test_template_with_special_chars(self):
        template = "「{{name}}」档案：\n> {{soul}}\n\n规划：{{content_plan}}"
        result = render_system_prompt(
            template, name="张三", soul="第一行\n第二行", content_plan="A\nB"
        )
        assert "「张三」" in result
        assert "> 第一行" in result

    def test_real_seed_template_renders(self):
        """使用接近真实种子 Prompt 的模板验证。"""
        template = """你是一个千川脚本仿写专家。任务：把原版脚本改写成「{{name}}」视角的仿写版本。

## {{name}} 人物档案
{{soul}}

## {{name}} 内容规划参考
{{content_plan}}

## 仿写铁律
1. 结构完全不变
2. 产品全部替换：结合{{name}}产品卖点"""
        result = render_system_prompt(
            template,
            name="孙知羽",
            soul="一个有梦想的90后短视频达人",
            content_plan="主打护肤+生活方式",
        )
        assert "「孙知羽」" in result
        assert "一个有梦想的90后短视频达人" in result
        assert "主打护肤+生活方式" in result
        assert "{{" not in result

    def test_appends_full_kol_and_product_context(self):
        result = render_system_prompt(
            "达人：{{name}}\n档案：{{soul}}",
            name="孙知羽",
            soul="基础人设",
            content_plan="内容规划",
            profile_sections=[
                ("真实经历", "在济州岛做过导游"),
                ("独家经历", "只属于她的故事"),
            ],
            product_fields={
                "产品昵称": "云朵面霜",
                "最主推卖点": "熬夜也不暗沉",
                "主推机制": "限时买一送一",
                "只有我有": "是，必须强调独家权益",
            },
        )

        assert "真实经历" in result
        assert "在济州岛做过导游" in result
        assert "独家经历" in result
        assert "云朵面霜" in result
        assert "熬夜也不暗沉" in result
        assert "限时买一送一" in result
        assert "只有我有" in result
