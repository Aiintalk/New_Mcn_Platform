"""
Unit tests for _compute_status() in app.routers.admin_kols.

_compute_status 是红人入驻状态的核心业务规则（2026-07-12 PR #25 重构）：
status 从 DB 手动字段改为根据 persona + content_plan 动态计算。

覆盖 4 种正常状态 + 空白字符串边界（纯空格/Tab/换行应当作空）。

参考契约：backend/docs/base/MCN_M2_Base_API.md §6A.8
"""
from app.routers.admin_kols import _compute_status


# ---------------------------------------------------------------------------
# 4 种正常状态
# ---------------------------------------------------------------------------


def test_both_empty_returns_pending_onboarding():
    """persona + content_plan 都为 None / 空字符串 → pending_onboarding。"""
    assert _compute_status(None, None) == "pending_onboarding"
    assert _compute_status("", "") == "pending_onboarding"


def test_only_persona_returns_persona_done():
    """只有 persona → persona_done。"""
    assert _compute_status("人格档案内容", None) == "persona_done"
    assert _compute_status("人格档案内容", "") == "persona_done"


def test_only_content_returns_content_done():
    """只有 content_plan → content_done。"""
    assert _compute_status(None, "内容规划") == "content_done"
    assert _compute_status("", "内容规划") == "content_done"


def test_both_filled_returns_onboarded():
    """persona + content_plan 都有 → onboarded。"""
    assert _compute_status("人格", "内容") == "onboarded"


# ---------------------------------------------------------------------------
# 边界：纯空白字符串（空格 / Tab / 换行）应当作空
# ---------------------------------------------------------------------------


def test_whitespace_only_treated_as_empty():
    """纯空白字符（空格/Tab/换行）组合应当作空 → pending_onboarding。"""
    assert _compute_status("   \n\t ", "  ") == "pending_onboarding"
    assert _compute_status("\t\t", "\n\n") == "pending_onboarding"


def test_whitespace_persona_with_real_content_returns_content_done():
    """persona 为纯空白、content_plan 有内容 → content_done（空白 ≠ 有内容）。"""
    assert _compute_status("  ", "内容规划") == "content_done"
    assert _compute_status("\n\t", "内容规划") == "content_done"
