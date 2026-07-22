"""
app/evaluation/services/scheduler.py

评测调度入口（spec §3.4 + plan Phase 3）。

职责：
- 统一封装 run 触发：手动触发 / 版本创建后自动触发 / 定时触发（一期占位）
- 建 eval_runs 记录：绑 default 策略（一期恒 default）+ trigger_type + filter_tags
- 调 runner.execute_run 执行

一期定时触发占位——不消费 eval_schedule_policies 表（该表一期仅建表 + admin CRUD，
scheduler 二期才读它做定时触发，B-I4）。

AsyncSessionLocal 在模块顶部 import（满足 conftest patch 注册，spec §6.7）。
trigger_run 接受外部 db 参数（测试注入 test_session）；生产路径由 router 传入请求 session
或 BackgroundTask 自开 session。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# AsyncSessionLocal 在模块顶部 import（满足 conftest patch 注册，spec §6.7）。
from app.core.database import AsyncSessionLocal  # noqa: F401
from app.evaluation.constants import (
    DEFAULT_STRATEGY_NAME,
    EVAL_TOOL_QIANCHUAN_WRITER,
    RUN_STATUS_PENDING,
)
from app.evaluation.models import EvalRun, EvalStrategy, EvalVersion
from app.evaluation.services import runner

__all__ = ["trigger_run"]


async def _resolve_default_strategy(
    db: AsyncSession, tool_code: str
) -> EvalStrategy:
    """查 default 策略（一期所有 run 绑定它）。

    按 name='default' + tool_code 查 active 策略。若不存在则抛错（一期 seed 必须先建）。
    """
    stmt = select(EvalStrategy).where(
        EvalStrategy.tool_code == tool_code,
        EvalStrategy.name == DEFAULT_STRATEGY_NAME,
        EvalStrategy.is_active.is_(True),
        EvalStrategy.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    strategy = result.scalars().first()
    if strategy is None:
        raise ValueError(
            f"default strategy not found for tool_code={tool_code!r} "
            f"(seed required)"
        )
    return strategy


async def trigger_run(
    *,
    version_id: int,
    filter_tags: list[str] | None,
    trigger_type: str,
    user_id: int | None,
    db: AsyncSession,
) -> int:
    """触发一次评测 run（spec §3.4）。

    Args:
        version_id: 被测版本 id
        filter_tags: 过滤标签（一期写入 run 记录，不参与 test_case 选择；选择由 strategy.test_case_selector 决定）
        trigger_type: manual / auto_on_version_create / scheduled
        user_id: 触发者 id（可空，定时触发无）
        db: AsyncSession

    Returns:
        run_id

    副作用：
        - 创建 eval_runs 记录（pending）
        - 调 runner.execute_run 执行（run 进入 running → completed/failed）
    """
    version = await db.get(EvalVersion, version_id)
    if version is None:
        raise ValueError(f"EvalVersion not found: id={version_id}")

    strategy = await _resolve_default_strategy(db, version.tool_code)

    run = EvalRun(
        version_id=version.id,
        strategy_id=strategy.id,
        name=f"run-{version.name}-{trigger_type}",
        trigger_type=trigger_type,
        status=RUN_STATUS_PENDING,
        filter_tags=list(filter_tags or []),
        total_cases=0,
        completed_cases=0,
        failed_cases=0,
        metadata_={},
        created_by=user_id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # 调 runner 执行（一期同步 await；二期可改为 BackgroundTask 入队）
    # 不传 generate_fn/score_fn → 生产路径由 runner 经 adapter_registry 绑定
    await runner.execute_run(run.id, db)

    return run.id
