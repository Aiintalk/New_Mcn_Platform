"""
Unit tests for eval_* ORM models - schema, constraints, cascades.

Verifies Phase 1 of the AIGC evaluation data layer:
- metadata.create_all creates all 11 eval tables
- basic insert/query for each table
- soft-delete (deleted_at) column is present and nullable
- unique constraints (incl. partial unique indexes with NULLS NOT DISTINCT)
- ON DELETE CASCADE for runs -> case_results -> scores
- eval_runs.strategy_id FK
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import Base
from app.evaluation.constants import (
    DEFAULT_ADAPTER,
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
)
from app.evaluation.models import (
    EvalCaseResult,
    EvalDimension,
    EvalHumanLabel,
    EvalJudgeModel,
    EvalRubric,
    EvalRun,
    EvalSchedulePolicy,
    EvalScore,
    EvalStrategy,
    EvalTestCase,
    EvalVersion,
)
from app.models import (
    EvalCaseResult as EvalCaseResultReExported,
    EvalDimension as EvalDimensionReExported,
)

# ---------------------------------------------------------------------------
# Static schema introspection tests (no DB roundtrip)
# ---------------------------------------------------------------------------

_EXPECTED_TABLES = {
    "eval_dimensions",
    "eval_rubrics",
    "eval_test_cases",
    "eval_versions",
    "eval_runs",
    "eval_case_results",
    "eval_scores",
    "eval_human_labels",
    "eval_schedule_policies",
    "eval_strategies",
    "eval_judge_models",
}


def test_all_eval_tables_registered_in_metadata():
    """All 11 eval_ tables must be present in Base.metadata (registered via app.models)."""
    missing = _EXPECTED_TABLES - set(Base.metadata.tables.keys())
    assert not missing, f"Missing tables in metadata: {missing}"


def test_eval_models_re_exported_from_app_models():
    """Cross-package registration: app.models must export eval classes (conftest relies on this)."""
    assert EvalCaseResultReExported is EvalCaseResult
    assert EvalDimensionReExported is EvalDimension


def test_constants_have_expected_values():
    assert EVAL_TOOL_QIANCHUAN_WRITER == "qianchuan-writer"
    assert DEFAULT_STRATEGY_NAME == "default"
    assert DEFAULT_ADAPTER == "yunwu"


def test_tablename_prefix():
    for cls in (
        EvalDimension, EvalRubric, EvalTestCase, EvalVersion, EvalRun,
        EvalCaseResult, EvalScore, EvalHumanLabel, EvalSchedulePolicy,
        EvalStrategy, EvalJudgeModel,
    ):
        assert cls.__tablename__.startswith("eval_"), cls.__tablename__


def test_eval_run_has_strategy_id_fk():
    """eval_runs.strategy_id must be a FK to eval_strategies.id (v2)."""
    cols = {c.name: c for c in EvalRun.__table__.columns}
    assert "strategy_id" in cols
    fks = list(cols["strategy_id"].foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "eval_strategies"


def test_eval_strategy_has_scoring_override_triplet():
    """EvalStrategy must have all three scoring_*_override columns (v2 B-C3)."""
    cols = {c.name for c in EvalStrategy.__table__.columns}
    assert {
        "scoring_model_override",
        "scoring_provider_override",
        "scoring_adapter_override",
    }.issubset(cols)


def test_eval_version_has_source_kol_id():
    """eval_versions.source_kol_id (v2 关联维护) must exist."""
    cols = {c.name for c in EvalVersion.__table__.columns}
    assert "source_kol_id" in cols


# ---------------------------------------------------------------------------
# DB-backed tests (use the session-scoped test_engine via test_session fixture)
# ---------------------------------------------------------------------------


def _unique(suffix: str = "") -> str:
    """Generate a unique token per call (conftest does not rollback between tests)."""
    return uuid.uuid4().hex[:8] + suffix


@pytest_asyncio.fixture
async def dimension(test_session) -> EvalDimension:
    d = EvalDimension(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=f"copy_quality_{_unique()}",
        display_name="文案质量",
        default_weight=0.4000,
        score_min=1,
        score_max=10,
        prompt_template="评分模板 {{rubric_text}}",
        is_active=True,
    )
    test_session.add(d)
    await test_session.commit()
    await test_session.refresh(d)
    return d


@pytest_asyncio.fixture
async def test_case(test_session) -> EvalTestCase:
    tc = EvalTestCase(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=f"case-A-{_unique()}",
        input_payload={"product_info": "测试商品"},
        tags=["焦虑型", "美妆"],
        is_active=True,
    )
    test_session.add(tc)
    await test_session.commit()
    await test_session.refresh(tc)
    return tc


@pytest_asyncio.fixture
async def version(test_session) -> EvalVersion:
    v = EvalVersion(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=f"v1-{_unique()}",
        config_payload={"model_id": "x", "system_prompt_template": "tpl"},
        is_active=True,
    )
    test_session.add(v)
    await test_session.commit()
    await test_session.refresh(v)
    return v


@pytest_asyncio.fixture
async def strategy(test_session) -> EvalStrategy:
    # 注意：conftest.test_session 不在测试间 rollback，strategy.name 在 partial
    # unique index 下不能跨测试重复，故每次生成唯一 name。
    # DEFAULT_STRATEGY_NAME ("default") 仅在 migration seed 中使用。
    s = EvalStrategy(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=f"default_{_unique()}",
        test_case_selector={"all": True},
        dimension_weight_overrides={},
        rubric_selector={},
        is_active=True,
    )
    test_session.add(s)
    await test_session.commit()
    await test_session.refresh(s)
    return s


class TestEvalBasicCrud:
    async def test_insert_and_query_dimension(self, test_session, dimension):
        fetched = (
            await test_session.execute(
                select(EvalDimension).where(EvalDimension.id == dimension.id)
            )
        ).scalar_one()
        assert fetched.name == dimension.name
        assert float(fetched.default_weight) == pytest.approx(0.4, abs=1e-3)

    async def test_insert_test_case_with_tags(self, test_session, test_case):
        fetched = (
            await test_session.execute(
                select(EvalTestCase).where(EvalTestCase.id == test_case.id)
            )
        ).scalar_one()
        assert "美妆" in fetched.tags

    async def test_insert_rubric(self, test_session, dimension):
        r = EvalRubric(
            dimension_id=dimension.id,
            level=10,
            criteria="满分标准",
            scenario_tag=None,
            is_active=True,
        )
        test_session.add(r)
        await test_session.commit()
        await test_session.refresh(r)
        assert r.id is not None

    async def test_insert_judge_model(self, test_session):
        jm = EvalJudgeModel(
            model_id="glm-4.7",
            provider="yunwu",
            adapter="yunwu",
            applicable_output_type="copy",
            note="测试评委",
            is_active=True,
        )
        test_session.add(jm)
        await test_session.commit()
        await test_session.refresh(jm)
        assert jm.id is not None


class TestEvalSoftDelete:
    async def test_dimension_deleted_at_nullable(self, test_session, dimension):
        assert dimension.deleted_at is None
        dimension.deleted_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await test_session.commit()
        await test_session.refresh(dimension)
        assert dimension.deleted_at is not None


class TestEvalUniqueConstraints:
    async def test_case_results_unique_run_testcase(
        self, test_session, test_case, version, strategy
    ):
        run = EvalRun(
            version_id=version.id,
            strategy_id=strategy.id,
            name="run-1",
            trigger_type="manual",
            status="pending",
            total_cases=1,
        )
        test_session.add(run)
        await test_session.commit()
        await test_session.refresh(run)

        cr1 = EvalCaseResult(
            run_id=run.id, test_case_id=test_case.id, generated_output="A"
        )
        test_session.add(cr1)
        await test_session.commit()

        cr2 = EvalCaseResult(
            run_id=run.id, test_case_id=test_case.id, generated_output="B"
        )
        test_session.add(cr2)
        with pytest.raises(IntegrityError):
            await test_session.commit()
        await test_session.rollback()

    async def test_scores_unique_case_dim(self, test_session, test_case, version, strategy, dimension):
        run = EvalRun(
            version_id=version.id,
            strategy_id=strategy.id,
            name="run-s",
            trigger_type="manual",
            status="pending",
            total_cases=1,
        )
        test_session.add(run)
        await test_session.commit()
        await test_session.refresh(run)

        cr = EvalCaseResult(run_id=run.id, test_case_id=test_case.id, generated_output="X")
        test_session.add(cr)
        await test_session.commit()
        await test_session.refresh(cr)

        s1 = EvalScore(case_result_id=cr.id, dimension_id=dimension.id, ai_score=8)
        test_session.add(s1)
        await test_session.commit()

        s2 = EvalScore(case_result_id=cr.id, dimension_id=dimension.id, ai_score=9)
        test_session.add(s2)
        with pytest.raises(IntegrityError):
            await test_session.commit()
        await test_session.rollback()

    async def test_strategies_unique_tool_name_when_not_deleted(
        self, test_session
    ):
        """Partial unique index: same (tool_code, name) collides only when deleted_at IS NULL."""
        a = EvalStrategy(
            tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
            name="dup",
            test_case_selector={"all": True},
            is_active=True,
        )
        test_session.add(a)
        await test_session.commit()

        b = EvalStrategy(
            tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
            name="dup",
            test_case_selector={"all": True},
            is_active=True,
        )
        test_session.add(b)
        with pytest.raises(IntegrityError):
            await test_session.commit()
        await test_session.rollback()

    async def test_judge_models_unique_model_adapter_when_not_deleted(
        self, test_session
    ):
        a = EvalJudgeModel(
            model_id="glm-test",
            provider="yunwu",
            adapter="yunwu",
            applicable_output_type="copy",
            is_active=True,
        )
        test_session.add(a)
        await test_session.commit()

        b = EvalJudgeModel(
            model_id="glm-test",
            provider="yunwu",
            adapter="yunwu",
            applicable_output_type="video",
            is_active=True,
        )
        test_session.add(b)
        with pytest.raises(IntegrityError):
            await test_session.commit()
        await test_session.rollback()

    async def test_rubrics_unique_dim_scenario_level_active(
        self, test_session, dimension
    ):
        """NULLS NOT DISTINCT: NULL scenario_tag duplicates must collide when active."""
        r1 = EvalRubric(
            dimension_id=dimension.id,
            level=10,
            criteria="A",
            scenario_tag=None,
            is_active=True,
        )
        test_session.add(r1)
        await test_session.commit()

        r2 = EvalRubric(
            dimension_id=dimension.id,
            level=10,
            criteria="B",
            scenario_tag=None,
            is_active=True,
        )
        test_session.add(r2)
        with pytest.raises(IntegrityError):
            await test_session.commit()
        await test_session.rollback()

    async def test_rubrics_inactive_does_not_collide(
        self, test_session, dimension
    ):
        """When is_active=false, same (dim, scenario, level) does NOT collide."""
        r1 = EvalRubric(
            dimension_id=dimension.id,
            level=8,
            criteria="A",
            scenario_tag=None,
            is_active=True,
        )
        r2 = EvalRubric(
            dimension_id=dimension.id,
            level=8,
            criteria="B",
            scenario_tag=None,
            is_active=False,
        )
        test_session.add_all([r1, r2])
        await test_session.commit()  # should succeed
        assert r1.id is not None and r2.id is not None


class TestEvalCascade:
    async def test_delete_run_cascades_to_case_results_and_scores(
        self, test_session, test_case, version, strategy, dimension
    ):
        run = EvalRun(
            version_id=version.id,
            strategy_id=strategy.id,
            name="cascade-run",
            trigger_type="manual",
            status="completed",
            total_cases=1,
            completed_cases=1,
        )
        test_session.add(run)
        await test_session.commit()
        await test_session.refresh(run)

        cr = EvalCaseResult(
            run_id=run.id, test_case_id=test_case.id, generated_output="G"
        )
        test_session.add(cr)
        await test_session.commit()
        await test_session.refresh(cr)

        score = EvalScore(
            case_result_id=cr.id, dimension_id=dimension.id, ai_score=7
        )
        test_session.add(score)
        await test_session.commit()
        await test_session.refresh(score)

        cr_id = cr.id
        score_id = score.id
        run_id = run.id

        # Delete the run -> case_results and scores should cascade
        await test_session.delete(run)
        await test_session.commit()

        assert (
            await test_session.execute(
                select(EvalCaseResult).where(EvalCaseResult.id == cr_id)
            )
        ).scalar_one_or_none() is None
        assert (
            await test_session.execute(
                select(EvalScore).where(EvalScore.id == score_id)
            )
        ).scalar_one_or_none() is None


class TestEvalAdapterSkeleton:
    """Smoke tests for the LLMAdapter skeleton."""

    def test_adapter_registry_returns_yunwu(self):
        from app.evaluation.adapters import get_adapter
        from app.evaluation.adapters.base import LLMAdapter
        from app.evaluation.adapters.yunwu import YunwuAdapter

        adapter = get_adapter(DEFAULT_ADAPTER)
        assert isinstance(adapter, YunwuAdapter)
        # YunwuAdapter must satisfy the LLMAdapter Protocol (chat method)
        assert hasattr(adapter, "chat")
        assert callable(adapter.chat)
