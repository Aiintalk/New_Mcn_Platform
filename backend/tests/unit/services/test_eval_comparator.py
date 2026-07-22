"""
Unit tests for comparator.compare_runs.

Validates (spec §7.2 / plan Phase 2):
- Cross-run alignment by test_case_id (NOT case_result_id — PKs differ across runs)
- Overall average delta (run_b - run_a)
- Per-dimension average delta
- Sample-level ↑↓→ classification (up / down / same)
- Empty runs handled gracefully

Uses test_session fixture (metadata.create_all + real PostgreSQL test DB).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER
from app.evaluation.models import (
    EvalCaseResult,
    EvalDimension,
    EvalRun,
    EvalScore,
    EvalStrategy,
    EvalTestCase,
    EvalVersion,
)
from app.evaluation.services.comparator import (
    CaseDelta,
    ComparisonReport,
    DimensionDelta,
    compare_runs,
)


def _uid(prefix: str = "") -> str:
    """唯一标识（conftest 不在测试间 rollback，需唯一）。"""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers: build dimension + version + strategy (shared across runs)
# ---------------------------------------------------------------------------


async def _make_dimension(test_session, name, weight=0.4):
    d = EvalDimension(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid(name),
        display_name=name,
        default_weight=weight,
        score_min=1,
        score_max=10,
        prompt_template="评分 {{rubric_text}}",
        is_active=True,
    )
    test_session.add(d)
    await test_session.commit()
    await test_session.refresh(d)
    return d


async def _make_version_strategy(test_session):
    v = EvalVersion(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid("v"),
        config_payload={"model_id": "test", "system_prompt_template": "tpl"},
        is_active=True,
    )
    test_session.add(v)
    await test_session.commit()
    await test_session.refresh(v)

    s = EvalStrategy(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid("default"),
        test_case_selector={"all": True},
        dimension_weight_overrides={},
        rubric_selector={},
        is_active=True,
    )
    test_session.add(s)
    await test_session.commit()
    await test_session.refresh(s)
    return v, s


async def _make_run(test_session, version, strategy, name="run"):
    r = EvalRun(
        version_id=version.id,
        strategy_id=strategy.id,
        name=_uid(name),
        trigger_type="manual",
        status="completed",
        total_cases=0,
    )
    test_session.add(r)
    await test_session.commit()
    await test_session.refresh(r)
    return r


async def _make_test_case(test_session, name="case"):
    tc = EvalTestCase(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid(name),
        input_payload={"product_info": "test"},
        tags=[],
        is_active=True,
    )
    test_session.add(tc)
    await test_session.commit()
    await test_session.refresh(tc)
    return tc


async def _add_case_result_with_scores(
    test_session, run, test_case, dim_scores: dict
):
    """
    在 run 中为 test_case 创建 case_result + 每维度 score。

    Args:
        dim_scores: {dimension: score_float} 映射
    """
    cr = EvalCaseResult(
        run_id=run.id,
        test_case_id=test_case.id,
        generated_output=f"output-{test_case.id}-{run.id}",
    )
    test_session.add(cr)
    await test_session.commit()
    await test_session.refresh(cr)

    for dim, sc in dim_scores.items():
        s = EvalScore(
            case_result_id=cr.id,
            dimension_id=dim.id,
            ai_score=sc,
            ai_reasoning=f"score={sc}",
        )
        test_session.add(s)
    await test_session.commit()
    return cr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompareRunsBasicAlignment:
    """跨 run 按 test_case_id 对齐 + 基本计算。"""

    async def test_aligns_by_test_case_id_not_case_result_id(self, test_session):
        """关键：case_result 主键跨 run 不同，按 test_case_id 对齐。"""
        dim = await _make_dimension(test_session, "copy_quality")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "shared_case")

        run_a = await _make_run(test_session, version, strategy, "runA")
        run_b = await _make_run(test_session, version, strategy, "runB")

        cr_a = await _add_case_result_with_scores(test_session, run_a, tc, {dim: 6})
        cr_b = await _add_case_result_with_scores(test_session, run_b, tc, {dim: 8})

        # case_result 主键确实不同
        assert cr_a.id != cr_b.id

        report = await compare_runs(run_a.id, run_b.id, test_session)
        assert isinstance(report, ComparisonReport)
        assert len(report.case_deltas) == 1
        assert report.case_deltas[0].test_case_id == tc.id
        assert report.case_deltas[0].delta == pytest.approx(2.0)

    async def test_overall_delta_computation(self, test_session):
        """总体平均分 delta = avg_b - avg_a。"""
        dim = await _make_dimension(test_session, "copy_quality")
        version, strategy = await _make_version_strategy(test_session)
        tc1 = await _make_test_case(test_session, "case1")
        tc2 = await _make_test_case(test_session, "case2")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        # Run A: tc1=6, tc2=8 → avg=7.0
        await _add_case_result_with_scores(test_session, run_a, tc1, {dim: 6})
        await _add_case_result_with_scores(test_session, run_a, tc2, {dim: 8})
        # Run B: tc1=8, tc2=8 → avg=8.0
        await _add_case_result_with_scores(test_session, run_b, tc1, {dim: 8})
        await _add_case_result_with_scores(test_session, run_b, tc2, {dim: 8})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        assert report.overall_avg_a == pytest.approx(7.0)
        assert report.overall_avg_b == pytest.approx(8.0)
        assert report.overall_delta == pytest.approx(1.0)

    async def test_report_contains_run_ids(self, test_session):
        """报告回显 run_a_id / run_b_id。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        report = await compare_runs(run_a.id, run_b.id, test_session)
        assert report.run_a_id == run_a.id
        assert report.run_b_id == run_b.id


class TestCompareRunsDimensionDelta:
    """每维度平均分 diff。"""

    async def test_multi_dimension_deltas(self, test_session):
        """多维度：每维度独立计算 avg diff。"""
        dim_copy = await _make_dimension(test_session, "copy_quality", 0.4)
        dim_conv = await _make_dimension(test_session, "conversion", 0.35)
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        # Run A: copy=6, conv=5
        await _add_case_result_with_scores(
            test_session, run_a, tc, {dim_copy: 6, dim_conv: 5}
        )
        # Run B: copy=8, conv=7
        await _add_case_result_with_scores(
            test_session, run_b, tc, {dim_copy: 8, dim_conv: 7}
        )

        report = await compare_runs(run_a.id, run_b.id, test_session)
        assert len(report.dimension_deltas) == 2

        dim_ids = {d.dimension_id for d in report.dimension_deltas}
        assert dim_copy.id in dim_ids
        assert dim_conv.id in dim_ids

        for dd in report.dimension_deltas:
            if dd.dimension_id == dim_copy.id:
                assert dd.avg_a == pytest.approx(6.0)
                assert dd.avg_b == pytest.approx(8.0)
                assert dd.delta == pytest.approx(2.0)
            elif dd.dimension_id == dim_conv.id:
                assert dd.avg_a == pytest.approx(5.0)
                assert dd.avg_b == pytest.approx(7.0)
                assert dd.delta == pytest.approx(2.0)

    async def test_dimension_delta_only_in_run_a(self, test_session):
        """维度仅在 run_a 有评分 → avg_b=0, delta=0-avg_a。"""
        dim = await _make_dimension(test_session, "only_a_dim")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        await _add_case_result_with_scores(test_session, run_a, tc, {dim: 7})
        # run_b 无评分
        cr_b = EvalCaseResult(run_id=run_b.id, test_case_id=tc.id, generated_output="x")
        test_session.add(cr_b)
        await test_session.commit()

        report = await compare_runs(run_a.id, run_b.id, test_session)
        # 维度存在但 run_b 无评分
        dim_delta = next(d for d in report.dimension_deltas if d.dimension_id == dim.id)
        assert dim_delta.avg_a == pytest.approx(7.0)
        assert dim_delta.avg_b == pytest.approx(0.0)


class TestCompareRunsCaseDirection:
    """样本级 ↑↓→ 分类。"""

    async def test_up_down_same_classification(self, test_session):
        """三种方向：up(改善) / down(恶化) / same(持平)。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        tc_up = await _make_test_case(test_session, "up")
        tc_same = await _make_test_case(test_session, "same")
        tc_down = await _make_test_case(test_session, "down")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        # Run A: up=6, same=8, down=9
        await _add_case_result_with_scores(test_session, run_a, tc_up, {dim: 6})
        await _add_case_result_with_scores(test_session, run_a, tc_same, {dim: 8})
        await _add_case_result_with_scores(test_session, run_a, tc_down, {dim: 9})
        # Run B: up=8(+2→up), same=8(0→same), down=6(-3→down)
        await _add_case_result_with_scores(test_session, run_b, tc_up, {dim: 8})
        await _add_case_result_with_scores(test_session, run_b, tc_same, {dim: 8})
        await _add_case_result_with_scores(test_session, run_b, tc_down, {dim: 6})

        report = await compare_runs(run_a.id, run_b.id, test_session)

        # 按 test_case_id 找各自方向
        dirs = {cd.test_case_id: cd.direction for cd in report.case_deltas}
        assert dirs[tc_up.id] == "up"
        assert dirs[tc_same.id] == "same"
        assert dirs[tc_down.id] == "down"

        # summary 计数
        assert report.summary == {"up": 1, "down": 1, "same": 1}

    async def test_case_delta_values(self, test_session):
        """case delta 的 avg_a / avg_b / delta 正确。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        await _add_case_result_with_scores(test_session, run_a, tc, {dim: 5})
        await _add_case_result_with_scores(test_session, run_b, tc, {dim: 9})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        cd = report.case_deltas[0]
        assert cd.avg_a == pytest.approx(5.0)
        assert cd.avg_b == pytest.approx(9.0)
        assert cd.delta == pytest.approx(4.0)

    async def test_case_with_multiple_dimensions_avg(self, test_session):
        """case 有多维度时，avg 是各维度平均。"""
        dim1 = await _make_dimension(test_session, "d1")
        dim2 = await _make_dimension(test_session, "d2")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        # Run A: d1=6, d2=8 → avg=7.0
        await _add_case_result_with_scores(test_session, run_a, tc, {dim1: 6, dim2: 8})
        # Run B: d1=8, d2=10 → avg=9.0
        await _add_case_result_with_scores(test_session, run_b, tc, {dim1: 8, dim2: 10})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        cd = report.case_deltas[0]
        assert cd.avg_a == pytest.approx(7.0)
        assert cd.avg_b == pytest.approx(9.0)
        assert cd.delta == pytest.approx(2.0)
        assert cd.direction == "up"

    async def test_case_only_in_run_a_marked_only_a(self, test_session):
        """case 仅在 run_a → direction="only_a"。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "only_a")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        await _add_case_result_with_scores(test_session, run_a, tc, {dim: 7})
        # run_b 无此 case

        report = await compare_runs(run_a.id, run_b.id, test_session)
        cd = next(c for c in report.case_deltas if c.test_case_id == tc.id)
        assert cd.direction == "only_a"
        # only_a 不计入 up/down/same
        assert report.summary == {"up": 0, "down": 0, "same": 0}

    async def test_case_only_in_run_b_marked_only_b(self, test_session):
        """case 仅在 run_b → direction="only_b"。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "only_b")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        # run_a 无此 case
        await _add_case_result_with_scores(test_session, run_b, tc, {dim: 7})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        cd = next(c for c in report.case_deltas if c.test_case_id == tc.id)
        assert cd.direction == "only_b"


class TestCompareRunsEdgeCases:
    async def test_both_runs_empty(self, test_session):
        """两次 run 都无评分 → delta=0, 空列表。"""
        version, strategy = await _make_version_strategy(test_session)
        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        report = await compare_runs(run_a.id, run_b.id, test_session)
        assert report.overall_avg_a == 0.0
        assert report.overall_avg_b == 0.0
        assert report.overall_delta == 0.0
        assert report.dimension_deltas == []
        assert report.case_deltas == []
        assert report.summary == {"up": 0, "down": 0, "same": 0}

    async def test_case_delta_includes_name(self, test_session):
        """case_delta 回带 test_case_name。"""
        dim = await _make_dimension(test_session, "copy")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "named_case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        await _add_case_result_with_scores(test_session, run_a, tc, {dim: 5})
        await _add_case_result_with_scores(test_session, run_b, tc, {dim: 7})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        cd = report.case_deltas[0]
        assert cd.test_case_name is not None
        assert cd.test_case_name.startswith("named_case")

    async def test_dimension_delta_includes_name(self, test_session):
        """dimension_delta 回带 dimension_name。"""
        dim = await _make_dimension(test_session, "named_dim")
        version, strategy = await _make_version_strategy(test_session)
        tc = await _make_test_case(test_session, "case")

        run_a = await _make_run(test_session, version, strategy, "A")
        run_b = await _make_run(test_session, version, strategy, "B")

        await _add_case_result_with_scores(test_session, run_a, tc, {dim: 5})
        await _add_case_result_with_scores(test_session, run_b, tc, {dim: 7})

        report = await compare_runs(run_a.id, run_b.id, test_session)
        dd = report.dimension_deltas[0]
        assert dd.dimension_name is not None
        assert dd.dimension_name.startswith("named_dim")
