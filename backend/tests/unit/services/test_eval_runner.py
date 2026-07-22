"""
Unit tests for runner.execute_run (Phase 3 运行编排层).

Validates（spec §6.1/§6.5/§2.9.4 + plan Phase 3）:
- Happy path: N case × M 维度 → 全部 case_results/scores 落库 + run.status=completed
- run.metadata['resolved_scoring'] 含 model_id/provider/adapter 三键（B-C2）
- run.strategy_id 指向传入的策略（一期 default）
- case 级错误隔离：单 case 异常 → run 仍 completed, failed_cases+=1, error 落入 metadata['errors']
- 权重三级覆盖：strategy.dimension_weight_overrides > version.config_payload.dimension_weights > dimension.default_weight

AI 全 mock：测试注入 mock generate_fn/score_fn 绕过 adapter/credentials（B-I1）。
使用 test_session fixture（metadata.create_all + real PostgreSQL test DB）。
"""
import json
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.constants import (
    DEFAULT_ADAPTER,
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
    RUN_STATUS_COMPLETED,
    TRIGGER_TYPE_MANUAL,
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
from app.evaluation.services.runner import execute_run


def _uid(prefix: str = "") -> str:
    """唯一标识（conftest 不在测试间 rollback，需唯一）。"""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 跨测试数据隔离：test_session fixture 不 rollback，每个测试前清理 eval_* 表
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _isolate_eval_tables(test_session: AsyncSession):
    """每个测试前清理 eval_* 数据，避免跨测试累积干扰 _get_active_dimensions 等聚合查询。"""
    # 按依赖顺序删除（子表先于父表）
    await test_session.execute(delete(EvalHumanLabel))
    await test_session.execute(delete(EvalScore))
    await test_session.execute(delete(EvalCaseResult))
    await test_session.execute(delete(EvalRun))
    await test_session.execute(delete(EvalRubric))
    await test_session.execute(delete(EvalDimension))
    await test_session.execute(delete(EvalTestCase))
    await test_session.execute(delete(EvalStrategy))
    await test_session.execute(delete(EvalVersion))
    await test_session.execute(delete(EvalSchedulePolicy))
    await test_session.execute(delete(EvalJudgeModel))
    await test_session.commit()
    yield


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


async def _make_dimension(test_session, name, weight=0.4, score_min=1, score_max=10):
    d = EvalDimension(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid(name),
        display_name=name,
        default_weight=weight,
        score_min=score_min,
        score_max=score_max,
        prompt_template=(
            "评分 {{rubric_text}} 被评：{{generated_output}} 达人：{{persona}}"
        ),
        is_active=True,
    )
    test_session.add(d)
    await test_session.commit()
    await test_session.refresh(d)
    return d


async def _make_rubrics(test_session, dimension_id, levels=(10, 8, 6)):
    """default 变体：scenario_tag IS NULL。"""
    for lv in levels:
        r = EvalRubric(
            dimension_id=dimension_id,
            level=lv,
            criteria=f"level-{lv}-criteria",
            scenario_tag=None,  # default 变体
            is_active=True,
        )
        test_session.add(r)
    await test_session.commit()


async def _make_version(
    test_session,
    *,
    model_id="gen-model",
    provider="yunwu",
    scoring_model_id="judge-model",
    scoring_provider="yunwu",
    scoring_adapter="yunwu",
    dimension_weights=None,
):
    config_payload = {
        "model_id": model_id,
        "provider": provider,
        "system_prompt_template": "写文案 {{name}} {{product_info}}",
        "scoring_model_id": scoring_model_id,
        "scoring_provider": scoring_provider,
        "scoring_adapter": scoring_adapter,
    }
    if dimension_weights is not None:
        config_payload["dimension_weights"] = dimension_weights
    v = EvalVersion(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid("v"),
        config_payload=config_payload,
        is_active=True,
    )
    test_session.add(v)
    await test_session.commit()
    await test_session.refresh(v)
    return v


async def _make_strategy(
    test_session,
    *,
    name=DEFAULT_STRATEGY_NAME,
    weight_overrides=None,
    scoring_model_override=None,
    scoring_provider_override=None,
    scoring_adapter_override=None,
    test_case_selector=None,
):
    s = EvalStrategy(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid(name),
        test_case_selector=test_case_selector or {"all": True},
        dimension_weight_overrides=weight_overrides or {},
        rubric_selector={},
        scoring_model_override=scoring_model_override,
        scoring_provider_override=scoring_provider_override,
        scoring_adapter_override=scoring_adapter_override,
        is_active=True,
    )
    test_session.add(s)
    await test_session.commit()
    await test_session.refresh(s)
    return s


async def _make_test_case(test_session, name="case", tags=None):
    tc = EvalTestCase(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid(name),
        input_payload={
            "name": "达人A",
            "persona": "美妆博主",
            "content_plan": "种草",
            "product_info": "粉底液",
        },
        tags=tags or [],
        is_active=True,
    )
    test_session.add(tc)
    await test_session.commit()
    await test_session.refresh(tc)
    return tc


async def _make_run(test_session, version, strategy, filter_tags=None):
    r = EvalRun(
        version_id=version.id,
        strategy_id=strategy.id,
        name=_uid("run"),
        trigger_type=TRIGGER_TYPE_MANUAL,
        status="pending",
        filter_tags=filter_tags or [],
        total_cases=0,
        metadata_={},
    )
    test_session.add(r)
    await test_session.commit()
    await test_session.refresh(r)
    return r


def _ok_score_json(score=8):
    return json.dumps(
        {
            "score": score,
            "reasoning": f"score={score}",
            "strengths": ["a"],
            "weaknesses": ["b"],
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecuteRunHappyPath:
    """Happy path：N case × M 维度 → 全部落库 + run completed。"""

    async def test_3_cases_2_dims_all_persisted(self, test_session: AsyncSession):
        dim1 = await _make_dimension(test_session, "copy_quality", 0.4)
        dim2 = await _make_dimension(test_session, "conversion_power", 0.35)
        await _make_rubrics(test_session, dim1.id)
        await _make_rubrics(test_session, dim2.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc1 = await _make_test_case(test_session, "case1")
        tc2 = await _make_test_case(test_session, "case2")
        tc3 = await _make_test_case(test_session, "case3")

        run = await _make_run(test_session, version, strategy)

        gen_calls = []
        score_calls = []

        async def mock_generate(*, messages):
            gen_calls.append(messages)
            return f"output-{len(gen_calls)}"

        async def mock_score(*, messages):
            score_calls.append(messages)
            return _ok_score_json(7)

        await execute_run(
            run.id,
            test_session,
            generate_fn=mock_generate,
            score_fn=mock_score,
        )

        await test_session.refresh(run)
        assert run.status == RUN_STATUS_COMPLETED
        assert run.completed_cases == 3
        assert run.failed_cases == 0

        case_results = (
            (
                await test_session.execute(
                    select(EvalCaseResult).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(case_results) == 3
        for cr in case_results:
            assert cr.generated_output  # 非空
            assert cr.input_snapshot is not None  # 输入快照已固化

        case_result_ids = [cr.id for cr in case_results]
        scores = (
            (
                await test_session.execute(
                    select(EvalScore).where(
                        EvalScore.case_result_id.in_(case_result_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(scores) == 6  # 3 case × 2 dim
        for s in scores:
            assert s.ai_score == 7.0
            assert s.ai_reasoning == "score=7"
            assert s.weight_used is not None

        assert len(gen_calls) == 3
        assert len(score_calls) == 6  # 3 case × 2 dim


class TestResolvedScoringMetadata:
    """run.metadata['resolved_scoring'] 含 model_id/provider/adapter 三键（B-C2）。"""

    async def test_metadata_contains_three_keys(self, test_session: AsyncSession):
        version = await _make_version(
            test_session,
            scoring_model_id="glm-5.2",
            scoring_provider="yunwu",
            scoring_adapter="yunwu",
        )
        strategy = await _make_strategy(test_session)
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        await test_session.refresh(run)
        meta = run.metadata_ or {}
        assert "resolved_scoring" in meta
        rs = meta["resolved_scoring"]
        assert set(rs.keys()) >= {"model_id", "provider", "adapter"}
        assert rs["model_id"] == "glm-5.2"
        assert rs["provider"] == "yunwu"
        assert rs["adapter"] == "yunwu"

    async def test_strategy_override_takes_priority(self, test_session: AsyncSession):
        """strategy.scoring_*_override 覆盖 version.config_payload.scoring_*。"""
        version = await _make_version(
            test_session,
            scoring_model_id="version-judge",
            scoring_provider="yunwu",
            scoring_adapter="yunwu",
        )
        strategy = await _make_strategy(
            test_session,
            scoring_model_override="strategy-judge",
            scoring_provider_override="strategy-provider",
            scoring_adapter_override="yunwu",
        )
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        await test_session.refresh(run)
        rs = run.metadata_["resolved_scoring"]
        assert rs["model_id"] == "strategy-judge"
        assert rs["provider"] == "strategy-provider"


class TestStrategyIdBinding:
    """run.strategy_id 指向传入策略（一期恒 default）。"""

    async def test_run_strategy_id_matches(self, test_session: AsyncSession):
        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        # run 已绑定 strategy_id（_make_run 时设的）——验证 execute_run 不破坏它
        await test_session.refresh(run)
        assert run.strategy_id == strategy.id


class TestCaseLevelIsolation:
    """case 级错误隔离：单 case 失败不中断 run。"""

    async def test_second_case_raises_run_still_completed(
        self, test_session: AsyncSession
    ):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc1 = await _make_test_case(test_session, "case1")
        tc2 = await _make_test_case(test_session, "case2")
        tc3 = await _make_test_case(test_session, "case3")

        run = await _make_run(test_session, version, strategy)

        counter = {"n": 0}

        async def flaky_generate(*, messages):
            counter["n"] += 1
            if counter["n"] == 2:
                raise RuntimeError("case2 boom")
            return f"ok-{counter['n']}"

        async def mock_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id,
            test_session,
            generate_fn=flaky_generate,
            score_fn=mock_score,
        )

        await test_session.refresh(run)
        assert run.status == RUN_STATUS_COMPLETED  # 不是 failed
        assert run.completed_cases == 2  # case1 + case3 成功
        assert run.failed_cases == 1  # case2 失败

        meta = run.metadata_ or {}
        errors = meta.get("errors", [])
        assert len(errors) == 1
        assert "case2 boom" in errors[0]

        # 失败 case 不写 case_result（或写但标错）——这里验证成功 case 落库数 = 2
        case_results = (
            (
                await test_session.execute(
                    select(EvalCaseResult).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(case_results) == 2


class TestWeightThreeLevelOverride:
    """权重三级覆盖：strategy > version > dimension.default（B-权重）。"""

    async def test_strategy_override_wins(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", weight=0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(
            test_session,
            dimension_weights={str(dim.id): 0.3},  # 版本级
        )
        strategy = await _make_strategy(
            test_session,
            weight_overrides={str(dim.id): 0.5},  # 策略级（最 specific）
        )
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (
                await test_session.execute(
                    select(EvalScore).join(
                        EvalCaseResult, EvalCaseResult.id == EvalScore.case_result_id
                    ).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .first()
        )
        assert score is not None
        assert float(score.weight_used) == pytest.approx(0.5)  # 策略级生效

    async def test_version_override_when_no_strategy(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", weight=0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(
            test_session,
            dimension_weights={str(dim.id): 0.35},
        )
        strategy = await _make_strategy(test_session)  # 无 override
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (
                await test_session.execute(
                    select(EvalScore).join(
                        EvalCaseResult, EvalCaseResult.id == EvalScore.case_result_id
                    ).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .first()
        )
        assert score is not None
        assert float(score.weight_used) == pytest.approx(0.35)

    async def test_dimension_default_when_no_override(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", weight=0.42)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)  # 无 dimension_weights
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (
                await test_session.execute(
                    select(EvalScore).join(
                        EvalCaseResult, EvalCaseResult.id == EvalScore.case_result_id
                    ).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .first()
        )
        assert score is not None
        assert float(score.weight_used) == pytest.approx(0.42)


class TestTestCaseSelector:
    """strategy.test_case_selector 解析：{"all":true} / {"tags":[...]} / {"ids":[...]}。"""

    async def test_filter_by_tags(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(
            test_session,
            test_case_selector={"tags": ["skincare"]},
        )
        tc1 = await _make_test_case(test_session, "case1", tags=["skincare"])
        tc2 = await _make_test_case(test_session, "case2", tags=["diet"])
        tc3 = await _make_test_case(test_session, "case3", tags=["skincare", "lite"])

        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        await test_session.refresh(run)
        # 只有 tc1 + tc3 命中 skincare tag
        assert run.completed_cases == 2

    async def test_filter_by_ids(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        tc1 = await _make_test_case(test_session, "case1")
        tc2 = await _make_test_case(test_session, "case2")
        tc3 = await _make_test_case(test_session, "case3")

        strategy = await _make_strategy(
            test_session,
            test_case_selector={"ids": [tc1.id, tc3.id]},
        )
        run = await _make_run(test_session, version, strategy)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=noop_score
        )

        await test_session.refresh(run)
        assert run.completed_cases == 2


class TestDefaultRubricVariant:
    """rubric 一期 default 变体：scenario_tag IS NULL 的 active rubrics。"""

    async def test_only_default_variant_rubrics_selected(
        self, test_session: AsyncSession
    ):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        # default 变体（scenario_tag IS NULL）
        await _make_rubrics(test_session, dim.id, levels=(10, 8))
        # scenario 变体（一期不选）
        test_session.add(
            EvalRubric(
                dimension_id=dim.id,
                level=10,
                criteria="skincare-only",
                scenario_tag="skincare",
                is_active=True,
            )
        )
        await test_session.commit()

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)

        captured_score_msgs = []

        async def noop_gen(*, messages):
            return "x"

        async def capture_score(*, messages):
            captured_score_msgs.append(messages[0]["content"])
            return _ok_score_json()

        await execute_run(
            run.id, test_session, generate_fn=noop_gen, score_fn=capture_score
        )

        # 评分 prompt 应包含 default 变体 criteria，不含 skincare 变体
        assert len(captured_score_msgs) == 1
        prompt = captured_score_msgs[0]
        assert "level-10-criteria" in prompt  # default 变体文本
        assert "skincare-only" not in prompt  # scenario 变体未选


class TestProductionAdapterBinding:
    """generate_fn/score_fn 为 None 时走 adapter_registry 绑定（生产路径）。"""

    async def test_none_fns_use_adapter_registry(self, test_session: AsyncSession):
        from app.evaluation.services import runner as runner_mod

        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)

        # mock adapter + get_adapter，验证绑定逻辑
        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = _ok_score_json(9)

        def fake_get_adapter(name):
            assert name == DEFAULT_ADAPTER
            return mock_adapter

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(runner_mod, "get_adapter", fake_get_adapter)

            await execute_run(run.id, test_session)  # 不传 fn

        await test_session.refresh(run)
        assert run.status == RUN_STATUS_COMPLETED
        # mock_adapter.chat 被调用：generate（1 case）+ score（1 dim）= 2 次
        assert mock_adapter.chat.await_count == 2
