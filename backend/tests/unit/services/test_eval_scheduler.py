"""
Unit tests for scheduler.trigger_run（异步版，方案 C：arq+Redis，Phase 2）。

Validates：
- 触发即返回 run_id（不阻塞、不执行）；run 为 pending
- 建 run(total_cases=N) + N 条 eval_case_jobs(pending)
- 逐条 enqueue（用注入的 mock enqueue，不依赖 redis）
- strategy 解析（一期恒 default）、trigger_type/filter_tags 写入
- version 不存在 → ValueError

使用 test_session fixture（real PostgreSQL test DB）。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.constants import (
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
    JOB_STATUS_PENDING,
    RUN_STATUS_PENDING,
    TRIGGER_TYPE_AUTO_ON_VERSION_CREATE,
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
from app.evaluation.services import scheduler as scheduler_mod


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture(autouse=True)
async def _isolate_eval_tables(test_session: AsyncSession):
    """每个测试前清理 eval_* 数据（含 eval_case_jobs），避免跨测试累积。"""
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


async def _make_version(test_session, *, scoring_model_id=None, scoring_provider=None, scoring_adapter=None):
    config_payload = {"model_id": "gen-model", "provider": "yunwu"}
    if scoring_model_id is not None:
        config_payload["scoring_model_id"] = scoring_model_id
    if scoring_provider is not None:
        config_payload["scoring_provider"] = scoring_provider
    if scoring_adapter is not None:
        config_payload["scoring_adapter"] = scoring_adapter
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


async def _make_default_strategy(
    test_session,
    *,
    scoring_model_override=None,
    scoring_provider_override=None,
    scoring_adapter_override=None,
):
    s = EvalStrategy(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=DEFAULT_STRATEGY_NAME,
        test_case_selector={"all": True},
        dimension_weight_overrides={},
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


async def _make_test_cases(test_session, n: int):
    cases = []
    for _ in range(n):
        tc = EvalTestCase(
            tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
            name=_uid("tc"),
            input_payload={"messages": []},
            tags=[],
            is_active=True,
        )
        test_session.add(tc)
        cases.append(tc)
    await test_session.commit()
    for tc in cases:
        await test_session.refresh(tc)
    return cases


def _recording_enqueue():
    """返回 (mock enqueue, 已入队 job_id 列表)。"""
    enqueued: list[int] = []

    async def _enq(job_id: int) -> None:
        enqueued.append(job_id)

    return _enq, enqueued


class TestTriggerRunAsync:
    """异步触发：建 run(pending) + N job + 入队 + 立即返回。"""

    async def test_creates_pending_run_with_jobs_and_enqueues(self, test_session):
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 3)

        enq, enqueued = _recording_enqueue()
        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=["skincare"],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=enq,
        )

        assert run_id > 0
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        assert run.status == RUN_STATUS_PENDING        # 未执行，仍 pending
        assert run.total_cases == 3
        assert run.completed_cases == 0
        assert run.filter_tags == ["skincare"]

        jobs = (await test_session.execute(select(EvalCaseJob).where(EvalCaseJob.run_id == run_id).order_by(EvalCaseJob.id))).scalars().all()
        assert len(jobs) == 3
        assert all(j.status == JOB_STATUS_PENDING for j in jobs)   # 全 pending
        assert len({j.test_case_id for j in jobs}) == 3            # 各指向不同 case
        assert enqueued == [j.id for j in jobs]                    # 每条 job 入队一次

    async def test_trigger_returns_fast_without_executing(self, test_session):
        """触发不调 runner.execute_case（异步：执行由 worker）；且 enqueue 被调用。"""
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 1)

        enq, enqueued = _recording_enqueue()
        from unittest.mock import patch, AsyncMock
        with patch("app.evaluation.services.scheduler.runner.execute_case", new_callable=AsyncMock) as mock_exec:
            await scheduler_mod.trigger_run(
                version_id=version.id,
                filter_tags=[],
                trigger_type=TRIGGER_TYPE_MANUAL,
                user_id=None,
                db=test_session,
                enqueue=enq,
            )
        mock_exec.assert_not_awaited()   # 异步触发不执行 case
        assert len(enqueued) == 1        # 且 enqueue 被调用（非恒真）

    async def test_empty_test_cases_finalizes_run_failed(self, test_session):
        """无 test_case 匹配 → run 直接 failed（不建 job、不入队），不卡 pending。"""
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)
        # 不 seed 任何 test_case → selector {"all":True} 命中 0 条
        enq, enqueued = _recording_enqueue()
        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=enq,
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        assert run.status == "failed"
        assert run.total_cases == 0
        assert enqueued == []                                  # 没入队
        from app.evaluation.models import EvalCaseJob
        jobs = (await test_session.execute(select(EvalCaseJob).where(EvalCaseJob.run_id == run_id))).scalars().all()
        assert len(jobs) == 0                                  # 没建 job

    async def test_auto_trigger_on_version_create(self, test_session):
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 2)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_AUTO_ON_VERSION_CREATE,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        assert run.trigger_type == TRIGGER_TYPE_AUTO_ON_VERSION_CREATE
        assert run.total_cases == 2

    async def test_filter_tags_default_empty(self, test_session):
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 1)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=None,
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        assert run.filter_tags == []

    async def test_version_not_found_raises(self, test_session):
        await _make_default_strategy(test_session)
        with pytest.raises(ValueError):
            await scheduler_mod.trigger_run(
                version_id=999999,
                filter_tags=[],
                trigger_type=TRIGGER_TYPE_MANUAL,
                user_id=None,
                db=test_session,
                enqueue=_recording_enqueue()[0],
            )


class TestTriggerRunStrategyResolution:
    async def test_resolves_default_strategy_by_name(self, test_session):
        version = await _make_version(test_session)
        other = EvalStrategy(
            tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
            name="skincare-biz",
            test_case_selector={"tags": ["skincare"]},
            dimension_weight_overrides={},
            rubric_selector={},
            is_active=True,
        )
        test_session.add(other)
        await test_session.commit()
        default_s = await _make_default_strategy(test_session)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        assert run.strategy_id == default_s.id  # 不是 other.id


class TestResolvedScoringMetadata:
    """run.metadata['resolved_scoring'] 在建 run 时固化（B-C2 可复现；Phase 3 从 execute_run 迁来）。"""

    async def test_metadata_contains_three_keys(self, test_session):
        version = await _make_version(
            test_session,
            scoring_model_id="glm-5.2",
            scoring_provider="yunwu",
            scoring_adapter="yunwu",
        )
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 1)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        meta = run.metadata_ or {}
        assert "resolved_scoring" in meta
        rs = meta["resolved_scoring"]
        assert set(rs.keys()) >= {"model_id", "provider", "adapter"}
        assert rs["model_id"] == "glm-5.2"
        assert rs["provider"] == "yunwu"
        assert rs["adapter"] == "yunwu"

    async def test_strategy_override_takes_priority(self, test_session):
        """strategy.scoring_*_override 覆盖 version.config_payload.scoring_*。"""
        version = await _make_version(
            test_session,
            scoring_model_id="version-judge",
            scoring_provider="yunwu",
            scoring_adapter="yunwu",
        )
        await _make_default_strategy(
            test_session,
            scoring_model_override="strategy-judge",
            scoring_provider_override="strategy-provider",
        )
        await _make_test_cases(test_session, 1)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        rs = run.metadata_["resolved_scoring"]
        assert rs["model_id"] == "strategy-judge"
        assert rs["provider"] == "strategy-provider"
        assert rs["adapter"] == "yunwu"  # 无 override → fallback DEFAULT_ADAPTER

    async def test_adapter_falls_back_to_default(self, test_session):
        """version/strategy 都没给 scoring_adapter → fallback DEFAULT_ADAPTER(yunwu)。"""
        version = await _make_version(test_session)  # 无 scoring 配置
        await _make_default_strategy(test_session)
        await _make_test_cases(test_session, 1)

        run_id = await scheduler_mod.trigger_run(
            version_id=version.id,
            filter_tags=[],
            trigger_type=TRIGGER_TYPE_MANUAL,
            user_id=None,
            db=test_session,
            enqueue=_recording_enqueue()[0],
        )
        run = (await test_session.execute(select(EvalRun).where(EvalRun.id == run_id))).scalars().one()
        rs = run.metadata_["resolved_scoring"]
        assert rs["adapter"] == "yunwu"  # DEFAULT_ADAPTER
        assert rs["model_id"] is None    # 无来源 → None
