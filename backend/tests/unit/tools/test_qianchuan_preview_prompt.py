"""千川文案预审 Prompt 常量单元测试。"""
import pytest
from app.tools.qianchuan_preview.prompts import PROMPT_DEFAULT


class TestPromptDefault:
    def test_prompt_is_string(self):
        assert isinstance(PROMPT_DEFAULT, str)

    def test_prompt_not_empty(self):
        assert len(PROMPT_DEFAULT) > 100

    def test_prompt_contains_key_sections(self):
        assert "文案A" in PROMPT_DEFAULT
        assert "文案B" in PROMPT_DEFAULT
        assert "开头前三秒" in PROMPT_DEFAULT
        assert "购买欲望" in PROMPT_DEFAULT
        assert "修改清单" in PROMPT_DEFAULT

    def test_prompt_contains_format_requirement(self):
        assert "输出格式（严格遵守）" in PROMPT_DEFAULT

    def test_prompt_no_preset_winner(self):
        assert "不要预设谁更好" in PROMPT_DEFAULT

    def test_prompt_text_only_review(self):
        assert "不要提画面、剪辑、拍摄相关的建议" in PROMPT_DEFAULT

    def test_prompt_matches_migration_seed(self):
        assert "前台法则" in PROMPT_DEFAULT
        assert "时长控制" in PROMPT_DEFAULT
        assert "结构与卖点" in PROMPT_DEFAULT
