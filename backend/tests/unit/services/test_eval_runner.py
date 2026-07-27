"""
Unit tests for runner.execute_case（Phase 3 单 case 执行）+ resolve_test_cases。

execute_case 是 worker.run_case_job_logic 经 execute= 注入的真实执行：
generate（LLM）→ 多维 score（LLM）→ 写 case_result + scores（单次 commit）。
异常不捕获，由 run_case_job_logic 收尾（job→failed + aggregate）。因此本文件**只验
case 级产物**（case_result/scores），run 计数收尾在 test_eval_worker.py 的 aggregate 测。

Validates（spec §6.1/§6.5/§2.9 + plan Phase 3）：
- Happy: 1 job × M 维 → 1 case_result + M scores，字段正确 + 输入快照固化
- 权重三级覆盖：strategy.dimension_weight_overrides > version.config_payload > dimension.default
- case 级失败隔离：generate/score 抛错 → execute_case 抛错，**不落任何半成品**
- adapter 绑定：generate_fn/score_fn=None → 走 get_adapter
- job 绑定正确 test_case（不串 case）
- default rubric 变体选择（scenario_tag IS NULL）
- resolve_test_cases：{"all"}/{"tags"}/{"ids"} 三种 selector

AI 全 mock：注入 mock generate_fn/score_fn 绕过 adapter/credentials（B-I1）。
使用 test_session fixture（real PostgreSQL test DB）。
"""
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.constants import (
    DEFAULT_ADAPTER,
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
    TRIGGER_TYPE_MANUAL,
)
from app.evaluation.models import (
    EvalCaseJob,
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
from app.evaluation.services.runner import execute_case, resolve_test_cases


def _uid(prefix: str = "") -> str:
    """唯一标识（conftest 不在测试间 rollback，需唯一）。"""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
async def _isolate_eval_tables(test_session: AsyncSession):
    """每个测试前清理 eval_* 数据，避免跨测试累积干扰聚合查询。"""
    await test_session.execute(delete(EvalHumanLabel))
    await test_session.execute(delete(EvalScore))
    await test_session.execute(delete(EvalCaseResult))
    await test_session.execute(delete(EvalCaseJob))
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


async def _make_job(test_session, run, test_case, status="pending"):
    """建一条 case-job（绑 run + 唯一 test_case）。"""
    j = EvalCaseJob(run_id=run.id, test_case_id=test_case.id, status=status)
    test_session.add(j)
    await test_session.commit()
    await test_session.refresh(j)
    return j


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
# Happy path
# ---------------------------------------------------------------------------


class TestExecuteCaseHappyPath:
    """1 job × M 维 → 1 case_result + M scores，字段正确 + 输入快照固化。"""

    async def test_one_case_two_dims_persisted(self, test_session: AsyncSession):
        dim1 = await _make_dimension(test_session, "hook_strength", 0.35)
        dim2 = await _make_dimension(test_session, "conversion_power", 0.30)
        await _make_rubrics(test_session, dim1.id)
        await _make_rubrics(test_session, dim2.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)
        job = await _make_job(test_session, run, tc)

        gen_calls = []
        score_calls = []

        async def mock_generate(*, messages):
            gen_calls.append(messages)
            return "generated-output-1"

        async def mock_score(*, messages):
            score_calls.append(messages)
            return _ok_score_json(7)

        await execute_case(
            test_session, job.id, generate_fn=mock_generate, score_fn=mock_score
        )

        case_results = (
            (
                await test_session.execute(
                    select(EvalCaseResult).where(EvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(case_results) == 1
        cr = case_results[0]
        assert cr.generated_output == "generated-output-1"
        assert cr.output_payload == {"text": "generated-output-1"}
        assert cr.test_case_id == tc.id
        # 输入快照固化（被测输入留痕）
        assert cr.input_snapshot == tc.input_payload
        assert cr.input_snapshot["product_info"] == "粉底液"

        scores = (
            (
                await test_session.execute(
                    select(EvalScore).where(EvalScore.case_result_id == cr.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(scores) == 2  # 1 case × 2 dim
        for s in scores:
            assert float(s.ai_score) == 7.0
            assert s.ai_reasoning == "score=7"
            assert s.ai_strengths == ["a"]
            assert s.ai_weaknesses == ["b"]
            assert s.weight_used is not None

        assert len(gen_calls) == 1    # 1 case → 1 次生成
        assert len(score_calls) == 2  # 1 case × 2 dim


# ---------------------------------------------------------------------------
# 权重三级覆盖
# ---------------------------------------------------------------------------


class TestWeightThreeLevelOverride:
    """权重三级覆盖：strategy > version > dimension.default。"""

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
        job = await _make_job(test_session, run, tc)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_case(
            test_session, job.id, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (await test_session.execute(select(EvalScore))).scalars().first()
        )
        assert score is not None
        assert float(score.weight_used) == pytest.approx(0.5)

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
        job = await _make_job(test_session, run, tc)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_case(
            test_session, job.id, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (await test_session.execute(select(EvalScore))).scalars().first()
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
        job = await _make_job(test_session, run, tc)

        async def noop_gen(*, messages):
            return "x"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_case(
            test_session, job.id, generate_fn=noop_gen, score_fn=noop_score
        )

        score = (
            (await test_session.execute(select(EvalScore))).scalars().first()
        )
        assert score is not None
        assert float(score.weight_used) == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# case 级失败隔离
# ---------------------------------------------------------------------------


class TestCaseLevelFailureIsolation:
    """generate/score 抛错 → execute_case 抛错，不落任何半成品（无 case_result/score）。"""

    async def test_generate_raises_nothing_written(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)
        job = await _make_job(test_session, run, tc)

        async def boom_gen(*, messages):
            raise RuntimeError("generate failed")

        async def noop_score(*, messages):
            return _ok_score_json()

        with pytest.raises(RuntimeError, match="generate failed"):
            await execute_case(
                test_session, job.id, generate_fn=boom_gen, score_fn=noop_score
            )

        # 不落任何半成品
        crs = (
            (await test_session.execute(select(EvalCaseResult))).scalars().all()
        )
        assert len(crs) == 0
        scs = (
            (await test_session.execute(select(EvalScore))).scalars().all()
        )
        assert len(scs) == 0

    async def test_score_raises_nothing_written(self, test_session: AsyncSession):
        """第 2 维 score 抛错 → 整个 execute_case 抛错，连第 1 维都不落库（无半成品）。"""
        dim1 = await _make_dimension(test_session, "hook_strength", 0.35)
        dim2 = await _make_dimension(test_session, "conversion_power", 0.30)
        await _make_rubrics(test_session, dim1.id)
        await _make_rubrics(test_session, dim2.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)
        job = await _make_job(test_session, run, tc)

        calls = {"n": 0}

        async def noop_gen(*, messages):
            return "x"

        async def flaky_score(*, messages):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("dim2 score failed")
            return _ok_score_json()

        with pytest.raises(RuntimeError, match="dim2 score failed"):
            await execute_case(
                test_session, job.id, generate_fn=noop_gen, score_fn=flaky_score
            )

        # 无半成品落库（db.add 在 score 循环之后，抛错时未执行）
        crs = (
            (await test_session.execute(select(EvalCaseResult))).scalars().all()
        )
        assert len(crs) == 0
        scs = (
            (await test_session.execute(select(EvalScore))).scalars().all()
        )
        assert len(scs) == 0


# ---------------------------------------------------------------------------
# job 绑定正确 test_case
# ---------------------------------------------------------------------------


class TestJobBindsCorrectTestCase:
    """job.test_case_id 决定唯一 tc，不串 case。"""

    async def test_job_resolves_its_own_test_case(self, test_session: AsyncSession):
        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc1 = await _make_test_case(test_session, "case1")
        tc2 = await _make_test_case(test_session, "case2")
        run = await _make_run(test_session, version, strategy)
        job = await _make_job(test_session, run, tc2)  # job 绑 tc2

        async def noop_gen(*, messages):
            return "for-tc2"

        async def noop_score(*, messages):
            return _ok_score_json()

        await execute_case(
            test_session, job.id, generate_fn=noop_gen, score_fn=noop_score
        )

        cr = (
            (await test_session.execute(select(EvalCaseResult))).scalars().one()
        )
        assert cr.test_case_id == tc2.id  # 绑的是 tc2，不是 tc1
        assert cr.generated_output == "for-tc2"


# ---------------------------------------------------------------------------
# default rubric 变体选择
# ---------------------------------------------------------------------------


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
        job = await _make_job(test_session, run, tc)

        captured_score_msgs = []

        async def noop_gen(*, messages):
            return "x"

        async def capture_score(*, messages):
            captured_score_msgs.append(messages[0]["content"])
            return _ok_score_json()

        await execute_case(
            test_session, job.id, generate_fn=noop_gen, score_fn=capture_score
        )

        # 评分 prompt 应包含 default 变体 criteria，不含 scenario 变体
        assert len(captured_score_msgs) == 1
        prompt = captured_score_msgs[0]
        assert "level-10-criteria" in prompt  # default 变体文本
        assert "skincare-only" not in prompt  # scenario 变体未选


# ---------------------------------------------------------------------------
# adapter 绑定（生产路径）
# ---------------------------------------------------------------------------


class TestProductionAdapterBinding:
    """generate_fn/score_fn=None 时走 adapter_registry 绑定。"""

    async def test_none_fns_use_adapter_registry(self, test_session: AsyncSession):
        from app.evaluation.services import runner as runner_mod

        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(test_session)
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)
        job = await _make_job(test_session, run, tc)

        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = _ok_score_json(9)

        def fake_get_adapter(name):
            assert name == DEFAULT_ADAPTER
            return mock_adapter

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(runner_mod, "get_adapter", fake_get_adapter)

            await execute_case(test_session, job.id)  # 不传 fn

        # mock_adapter.chat 被调用：generate（1）+ score（1 dim）= 2 次
        assert mock_adapter.chat.await_count == 2
        # 产物落库
        cr = (
            (await test_session.execute(select(EvalCaseResult))).scalars().one()
        )
        assert cr is not None

    async def test_score_uses_frozen_resolved_scoring_and_binds_params(
        self, test_session: AsyncSession
    ):
        """B-C2：execute_case 评分用 run.metadata 冻结的 resolved_scoring（不是当前 config），
        且验证 partial 绑定的 model_id 参数（spec §7.1-5）。

        场景：version.config 的 scoring_model_id='config-judge'，但 run.metadata 冻结
        快照是 'frozen-judge'（模拟 trigger 时写入、之后 config 被改）。execute_case 评分
        应该用 frozen-judge，保证「冻结值 = 实际使用」。
        """
        from unittest.mock import AsyncMock
        from app.evaluation.services import runner as runner_mod

        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(
            test_session, scoring_model_id="config-judge"
        )
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)
        # 覆盖 metadata 为冻结快照（值与 config 不同）
        run.metadata_ = {
            "resolved_scoring": {
                "model_id": "frozen-judge",
                "provider": "yunwu",
                "adapter": "yunwu",
            }
        }
        await test_session.commit()
        await test_session.refresh(run)
        job = await _make_job(test_session, run, tc)

        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = _ok_score_json(9)

        def fake_get_adapter(name):
            return mock_adapter

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(runner_mod, "get_adapter", fake_get_adapter)
            await execute_case(test_session, job.id)

        # 2 次 adapter.chat：[0]=generate（用 config 的 model_id）, [1]=score（用冻结快照）
        assert mock_adapter.chat.await_count == 2
        calls = mock_adapter.chat.call_args_list
        assert calls[0].kwargs["model_id"] == "gen-model"  # generate 绑 version config
        # score 绑冻结快照的 model_id（不是 config 的 'config-judge'）→ B-C2 冻结生效
        assert calls[1].kwargs["model_id"] == "frozen-judge"

    async def test_falls_back_to_compute_when_metadata_missing(
        self, test_session: AsyncSession
    ):
        """run.metadata 无 resolved_scoring（测试直建 run / 迁移期旧 run）→ 回退现算 config。"""
        from unittest.mock import AsyncMock
        from app.evaluation.services import runner as runner_mod

        dim = await _make_dimension(test_session, "copy_quality", 0.4)
        await _make_rubrics(test_session, dim.id)

        version = await _make_version(
            test_session, scoring_model_id="config-judge"
        )
        strategy = await _make_strategy(test_session)
        tc = await _make_test_case(test_session, "case1")
        run = await _make_run(test_session, version, strategy)  # metadata_={}
        job = await _make_job(test_session, run, tc)

        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = _ok_score_json(9)

        def fake_get_adapter(name):
            return mock_adapter

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(runner_mod, "get_adapter", fake_get_adapter)
            await execute_case(test_session, job.id)

        # 无冻结快照 → score 用 config 的 scoring_model_id
        calls = mock_adapter.chat.call_args_list
        assert calls[1].kwargs["model_id"] == "config-judge"


# ---------------------------------------------------------------------------
# resolve_test_cases（selector 解析；从旧 execute_run 端到端测试迁为直接单测）
# ---------------------------------------------------------------------------


class TestResolveTestCases:
    """strategy.test_case_selector 解析：{"all"}/{"tags"}/{"ids"}。"""

    async def test_all_selector(self, test_session: AsyncSession):
        await _make_test_case(test_session, "case1")
        await _make_test_case(test_session, "case2")
        cases = await resolve_test_cases(
            test_session, EVAL_TOOL_QIANCHUAN_WRITER, {"all": True}
        )
        assert len(cases) >= 2

    async def test_filter_by_tags(self, test_session: AsyncSession):
        await _make_test_case(test_session, "a", tags=["skincare"])
        await _make_test_case(test_session, "b", tags=["diet"])
        c3 = await _make_test_case(test_session, "c", tags=["skincare", "lite"])
        cases = await resolve_test_cases(
            test_session, EVAL_TOOL_QIANCHUAN_WRITER, {"tags": ["skincare"]}
        )
        ids = {c.id for c in cases}
        assert c3.id in ids
        assert all(
            "skincare" in (c.tags or []) for c in cases
        )  # 命中的都含 skincare

    async def test_filter_by_ids(self, test_session: AsyncSession):
        c1 = await _make_test_case(test_session, "case1")
        await _make_test_case(test_session, "case2")
        c3 = await _make_test_case(test_session, "case3")
        cases = await resolve_test_cases(
            test_session,
            EVAL_TOOL_QIANCHUAN_WRITER,
            {"ids": [c1.id, c3.id]},
        )
        ids = {c.id for c in cases}
        assert ids == {c1.id, c3.id}
