from app.services.kol_context import KolContext


def test_prompt_sections_labels_positioning_and_facts_without_dropping_fields():
    context = KolContext(
        kol_id=43,
        name="达人",
        persona="完整人格",
        content_plan="内容规划",
        background="基本身份",
        experience="真实经历",
        relationships="关系网",
        unique_story="独家经历",
        extra_notes="其他补充",
    )

    assert context.prompt_sections() == [
        ("人格档案（角色定位和表达原则）", "完整人格"),
        ("内容规划（内容方向和创作策略）", "内容规划"),
        ("人物事实：基本身份", "基本身份"),
        ("人物事实：真实经历", "真实经历"),
        ("人物事实：关系网", "关系网"),
        ("人物事实：独家经历", "独家经历"),
        ("人物事实：其他补充", "其他补充"),
    ]


def test_prompt_sections_still_skips_blank_values():
    context = KolContext(
        kol_id=43,
        name="达人",
        persona=" ",
        content_plan=None,
        background="基本身份",
        experience=None,
        relationships="",
        unique_story="\n",
        extra_notes="其他补充",
    )

    assert context.prompt_sections() == [
        ("人物事实：基本身份", "基本身份"),
        ("人物事实：其他补充", "其他补充"),
    ]
