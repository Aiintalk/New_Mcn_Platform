"""
Unit tests for scheduler.trigger_run (Phase 3 运行编排层).

Validates（spec §3.4 + plan Phase 3）:
- 手动触发：建 run 记录（pending → runner 执行）+ strategy_id 绑定 default 策略
- trigger_type / filter_tags 正确写入
- 调 runner.execute_run（mock runner 绕过 AI）

使用 test_session fixture（metadata.create_all + real PostgreSQL test DB）。
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.constants import (
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
    RUN_STATUS_PENDING,
    TRIGGER_TYPE_AUTO_ON_VERSION_CREATE,
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
from app.evaluation.services import scheduler as scheduler_mod


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 跨测试数据隔离
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _isolate_eval_tables(test_session: AsyncSession):
    """每个测试前清理 eval_* 数据，避免跨测试累积干扰 default 策略查询。"""
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


async def _make_version(test_session):
    v = EvalVersion(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=_uid("v"),
        config_payload={
            "model_id": "gen-model",
            "provider": "yunwu",
            "system_prompt_template": "tpl",
            "scoring_model_id": "judge",
            "scoring_provider": "yunwu",
            "scoring_adapter": "yunwu",
        },
        is_active=True,
    )
    test_session.add(v)
    await test_session.commit()
    await test_session.refresh(v)
    return v


async def _make_default_strategy(test_session):
    """一期所有 run 绑定的 default 策略。"""
    s = EvalStrategy(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=DEFAULT_STRATEGY_NAME,
        test_case_selector={"all": True},
        dimension_weight_overrides={},
        rubric_selector={},
        is_active=True,
    )
    test_session.add(s)
    await test_session.commit()
    await test_session.refresh(s)
    return s


class TestTriggerRunManual:
    """手动触发：建 run + 调 runner + 绑定 default 策略。"""

    async def test_creates_run_with_default_strategy(
        self, test_session: AsyncSession
    ):
        version = await _make_version(test_session)
        strategy = await _make_default_strategy(test_session)

        # mock runner.execute_run，避免真实 AI 调用
        with patch.object(
            scheduler_mod, "runner", create=True
        ) if False else patch(
            "app.evaluation.services.scheduler.runner.execute_run",
            new_callable=AsyncMock,
        ) as mock_exec:
            run_id = await scheduler_mod.trigger_run(
                version_id=version.id,
                filter_tags=["skincare"],
                trigger_type=TRIGGER_TYPE_MANUAL,
                user_id=None,
                db=test_session,
            )

        assert run_id > 0

        run = (
            (
                await test_session.execute(
                    select(EvalRun).where(EvalRun.id == run_id)
                )
            )
            .scalars()
            .one()
        )
        assert run.version_id == version.id
        assert run.strategy_id == strategy.id  # 绑定 default 策略
        assert run.trigger_type == TRIGGER_TYPE_MANUAL
        assert run.filter_tags == ["skincare"]
        # execute_run 被调用一次，run_id 匹配
        mock_exec.assert_awaited_once()
        args, _ = mock_exec.call_args
        assert args[0] == run_id

    async def test_auto_trigger_on_version_create(
        self, test_session: AsyncSession
    ):
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)

        with patch(
            "app.evaluation.services.scheduler.runner.execute_run",
            new_callable=AsyncMock,
        ) as mock_exec:
            run_id = await scheduler_mod.trigger_run(
                version_id=version.id,
                filter_tags=[],
                trigger_type=TRIGGER_TYPE_AUTO_ON_VERSION_CREATE,
                user_id=None,
                db=test_session,
            )

        run = (
            (
                await test_session.execute(
                    select(EvalRun).where(EvalRun.id == run_id)
                )
            )
            .scalars()
            .one()
        )
        assert run.trigger_type == TRIGGER_TYPE_AUTO_ON_VERSION_CREATE
        mock_exec.assert_awaited_once()

    async def test_filter_tags_default_empty(self, test_session: AsyncSession):
        version = await _make_version(test_session)
        await _make_default_strategy(test_session)

        with patch(
            "app.evaluation.services.scheduler.runner.execute_run",
            new_callable=AsyncMock,
        ):
            run_id = await scheduler_mod.trigger_run(
                version_id=version.id,
                filter_tags=None,
                trigger_type=TRIGGER_TYPE_MANUAL,
                user_id=None,
                db=test_session,
            )

        run = (
            (
                await test_session.execute(
                    select(EvalRun).where(EvalRun.id == run_id)
                )
            )
            .scalars()
            .one()
        )
        assert run.filter_tags == []


class TestTriggerRunStrategyResolution:
    """trigger_run 解析 default 策略 id（一期恒 default）。"""

    async def test_resolves_default_strategy_by_name(
        self, test_session: AsyncSession
    ):
        """库里有多条策略（其他业务策略），trigger_run 仍选 name='default' 那条。"""
        version = await _make_version(test_session)

        # 另一条非 default 业务策略（二期场景）
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
        await test_session.refresh(other)

        default_s = await _make_default_strategy(test_session)

        with patch(
            "app.evaluation.services.scheduler.runner.execute_run",
            new_callable=AsyncMock,
        ):
            run_id = await scheduler_mod.trigger_run(
                version_id=version.id,
                filter_tags=[],
                trigger_type=TRIGGER_TYPE_MANUAL,
                user_id=None,
                db=test_session,
            )

        run = (
            (
                await test_session.execute(
                    select(EvalRun).where(EvalRun.id == run_id)
                )
            )
            .scalars()
            .one()
        )
        assert run.strategy_id == default_s.id  # 不是 other.id
