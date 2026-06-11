"""
Unit tests for persona_docx service.
"""
import os

import pytest

from app.services.persona_docx import (
    generate_persona_docx,
    generate_questionnaire_template,
)


def test_generate_profile_docx():
    content = "# 测试达人 · 人格档案 v1.0\n\n## 一句话定位\n测试定位\n\n- **特点1**: 值1\n- **特点2**: 值2\n\n1. 第一条\n2. 第二条\n\n> 引用文本\n\n普通段落 **粗体** 内容。"
    path = generate_persona_docx(99991, "profile", content, "测试达人")
    assert os.path.exists(path)
    assert "99991_profile.docx" in path
    os.remove(path)


def test_generate_plan_docx():
    content = "# 测试达人 · 内容规划\n\n## 内容体系\n\n内容线1\n内容线2"
    path = generate_persona_docx(99992, "plan", content, "测试达人")
    assert os.path.exists(path)
    assert "99992_plan.docx" in path
    os.remove(path)


def test_generate_questionnaire_template():
    path = generate_questionnaire_template()
    assert os.path.exists(path)
    assert path.endswith("questionnaire_template.docx")
    os.remove(path)


def test_generate_docx_with_empty_content():
    path = generate_persona_docx(99993, "profile", "", "空达人")
    assert os.path.exists(path)
    os.remove(path)
