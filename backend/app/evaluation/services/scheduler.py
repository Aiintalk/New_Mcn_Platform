"""
app/evaluation/services/scheduler.py

评测调度入口（异步，方案 C：arq+Redis，Phase 2；plan 2026-07-26-async-run-architecture）。

职责：
- 统一封装 run 触发：手动触发 / 版本创建后自动触发 / 定时触发（一期占位）
- 建 eval_runs 记录（pending）+ 绑 default 策略 + 解析 test_cases + 建 N 条 eval_case_jobs
- 调 worker.enqueue_case_job 把 case-job 入队（arq 异步消费）→ 立即返回 run_id（不阻塞、不执行）
- 空 test_cases 守卫：无匹配则 run 直接 failed 返回（不卡 pending）

实际执行由独立 worker 进程（worker.eval_case_job）异步消费 case-job。

一期定时触发占位——不消费 eval_schedule_policies 表（该表一期仅建表 + admin CRUD）。

AsyncSessionLocal 在模块顶部 import（满足 conftest patch 注册）。
trigger_run 接受外部 db 参数（测试注入 test_session）；生产路径由 router 传入请求 session。
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
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
)
from app.evaluation.models import EvalCaseJob, EvalRun, EvalStrategy, EvalVersion
from app.evaluation.services import runner
from app.evaluation.worker import enqueue_case_job

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
    enqueue=None,
    name: str | None = None,
) -> int:
    """触发一次评测 run（异步，方案 C：arq+Redis，Phase 2）。

    建 run(pending) + N 条 case-job → 逐条入队 arq → 立即返回 run_id（不阻塞、不执行）。
    实际执行由独立 worker 进程异步消费 case-job（见 worker.eval_case_job）。

    Args:
        version_id: 被测版本 id
        filter_tags: 一期写入 run 记录，不参与 test_case 选择（由 strategy.test_case_selector 决定）
        trigger_type: manual / auto_on_version_create / scheduled
        user_id: 触发者 id（可空，定时触发无）
        db: AsyncSession
        enqueue: 入队 callable（job_id → awaitable），默认 arq enqueue_case_job；
                 测试可注入 mock 避免依赖 redis。

    Returns:
        run_id（触发即返回，run 为 pending，worker 异步推进到 completed/failed）
    """
    version = await db.get(EvalVersion, version_id)
    if version is None:
        raise ValueError(f"EvalVersion not found: id={version_id}")

    strategy = await _resolve_default_strategy(db, version.tool_code)

    # 解析本次 run 的 test_cases（按 strategy.test_case_selector）
    test_cases = await runner.resolve_test_cases(
        db, version.tool_code, strategy.test_case_selector
    )

    # 空 case 守卫：无 case 则直接收尾 run（failed），不建 job/入队，避免 run 永远 pending
    if not test_cases:
        run = EvalRun(
            version_id=version.id,
            strategy_id=strategy.id,
            name=(name or "").strip() or f"run-{version.name}-{trigger_type}",
            trigger_type=trigger_type,
            status=RUN_STATUS_FAILED,
            filter_tags=list(filter_tags or []),
            total_cases=0,
            completed_cases=0,
            failed_cases=0,
            metadata_={"error": "no test_cases matched selector"},
            created_by=user_id,
        )
        db.add(run)
        await db.commit()
        return run.id

    run = EvalRun(
        version_id=version.id,
        strategy_id=strategy.id,
        name=(name or "").strip() or f"run-{version.name}-{trigger_type}",
        trigger_type=trigger_type,
        status=RUN_STATUS_PENDING,
        filter_tags=list(filter_tags or []),
        total_cases=len(test_cases),
        completed_cases=0,
        failed_cases=0,
        metadata_={"resolved_scoring": runner.compute_resolved_scoring(
            strategy, dict(version.config_payload or {})
        )},
        created_by=user_id,
    )
    db.add(run)
    await db.flush()  # 拿 run.id

    # 每个 test_case 建一条 case-job（按 case 拆任务，Phase 2）
    jobs = [EvalCaseJob(run_id=run.id, test_case_id=tc.id) for tc in test_cases]
    db.add_all(jobs)
    await db.flush()  # 拿 job.id
    await db.commit()

    # 入队（默认 arq；测试可注入 mock）
    enq = enqueue or enqueue_case_job
    for job in jobs:
        await enq(job.id)

    return run.id
