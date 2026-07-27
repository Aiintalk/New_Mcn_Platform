"""
app/evaluation/services/runner.py

评测 case 执行器（spec §6.1/§6.5 + plan Phase 3 异步架构）。

【异步模型】一个 run 拆成 N 个 case-job（worker.eval_case_job 消费）；
本模块提供**单 case** 执行：

- execute_case(db, job_id)：generate（LLM）→ 多维 score（LLM）→ 写 case_result+scores。
  由 worker.run_case_job_logic 经 execute= 注入；异常不捕获，由其收尾（job→failed +
  aggregate 原子累加 run 计数）。三条硬约束：generate/score 在事务外（yunwu.chat 内部
  commit）、每 case 一次 commit、run 计数走 aggregate。
- compute_resolved_scoring(strategy, config)：resolve 评委身份（strategy override >
  version.config_payload），trigger_run 写入 run.metadata['resolved_scoring']（B-C2 可复现）
  + execute_case 据此绑 score_fn adapter。
- resolve_test_cases：strategy.test_case_selector → test_cases 列表（trigger_run 用）。

权重三级 resolve：strategy > version > dimension.default（spec §2.4）。
generator/scorer 是纯函数不持 db（spec §6.1 服务职责分层）。
测试注入 mock generate_fn/score_fn 绕过 adapter/credentials（B-I1）。
"""
from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# AsyncSessionLocal 在模块顶部 import（满足 conftest patch 注册，红线 #7）。
# execute_case 接受外部 db 参数（测试注入 test_session / 生产路径由 worker 自开 session 传入）。
from app.core.database import AsyncSessionLocal  # noqa: F401
from app.evaluation.adapters.registry import get_adapter
from app.evaluation.constants import DEFAULT_ADAPTER
from app.evaluation.models import (
    EvalCaseJob,
    EvalCaseResult,
    EvalDimension,
    EvalRubric,
    EvalRun,
    EvalScore,
    EvalStrategy,
    EvalTestCase,
    EvalVersion,
)
from app.evaluation.services.generator import generate
from app.evaluation.services.scorer import score

__all__ = ["execute_case", "resolve_test_cases", "compute_resolved_scoring"]


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------


def _resolve_with_strategy_override(
    strategy_value: Any,
    config_value: Any,
    fallback: Any = None,
) -> Any:
    """strategy override 优先，其次 version.config_payload，最后 fallback。"""
    if strategy_value is not None:
        return strategy_value
    if config_value is not None:
        return config_value
    return fallback


def _resolve_weight(
    strategy: EvalStrategy,
    config: dict[str, Any],
    dimension: EvalDimension,
) -> float:
    """权重三级 resolve（spec §2.4）：strategy > version > dimension.default。

    key 为 dimension_id 字符串（spec §2.8.2 防 dimension 改名失效）。
    """
    dim_key = str(dimension.id)
    overrides = strategy.dimension_weight_overrides or {}
    if dim_key in overrides:
        return float(overrides[dim_key])
    version_weights = config.get("dimension_weights") or {}
    if dim_key in version_weights:
        return float(version_weights[dim_key])
    return float(dimension.default_weight)


def compute_resolved_scoring(
    strategy: EvalStrategy, config: dict[str, Any]
) -> dict[str, Any]:
    """resolve 评委身份（spec §2.9.2/§2.9.4 B-C2）：strategy override > version.config_payload。

    返回 {model_id, provider, adapter}：
    - trigger_run 写入 run.metadata['resolved_scoring']（run 创建即固化，可复现）
    - execute_case 据此绑定 score_fn adapter

    两者共用同一来源，避免分散 resolve 逻辑漂移。
    """
    return {
        "model_id": _resolve_with_strategy_override(
            getattr(strategy, "scoring_model_override", None),
            config.get("scoring_model_id"),
        ),
        "provider": _resolve_with_strategy_override(
            getattr(strategy, "scoring_provider_override", None),
            config.get("scoring_provider"),
        ),
        "adapter": _resolve_with_strategy_override(
            getattr(strategy, "scoring_adapter_override", None),
            config.get("scoring_adapter"),
            fallback=DEFAULT_ADAPTER,
        ),
    }


async def resolve_test_cases(
    db: AsyncSession,
    tool_code: str,
    selector: dict[str, Any] | None,
) -> list[EvalTestCase]:
    """解析 strategy.test_case_selector → 实际 test_cases 列表。

    一期格式：
      - {"all": True}（或无匹配 key）→ 全部 active test_cases
      - {"tags": [...]} → tags overlap 过滤
      - {"ids": [...]} → 按 id 过滤
    """
    selector = selector or {}
    stmt = select(EvalTestCase).where(
        EvalTestCase.tool_code == tool_code,
        EvalTestCase.is_active.is_(True),
        EvalTestCase.deleted_at.is_(None),
    )

    if selector.get("all"):
        pass  # 取全部
    elif "tags" in selector and selector["tags"]:
        tags = list(selector["tags"])
        # tags overlap：test_case.tags 与 selector.tags 有交集即命中
        stmt = stmt.where(or_(*[EvalTestCase.tags.contains([t]) for t in tags]))
    elif "ids" in selector:
        ids = list(selector["ids"] or [])
        if not ids:
            return []
        stmt = stmt.where(EvalTestCase.id.in_(ids))
    # 其它未识别格式 → 退化为全部（一期向后兼容）

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_default_rubrics(
    db: AsyncSession, dimension_id: int
) -> list[EvalRubric]:
    """一期 default 变体：scenario_tag IS NULL 的 active rubrics（按 level 降序）。

    spec §2.4 阶段边界：scenario_tag 结构预留、匹配不启用（全用 default 变体）。
    """
    stmt = (
        select(EvalRubric)
        .where(
            EvalRubric.dimension_id == dimension_id,
            EvalRubric.is_active.is_(True),
            EvalRubric.scenario_tag.is_(None),
        )
        .order_by(EvalRubric.level.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_active_dimensions(
    db: AsyncSession, tool_code: str
) -> list[EvalDimension]:
    """取该工具所有 active 维度。"""
    stmt = select(EvalDimension).where(
        EvalDimension.tool_code == tool_code,
        EvalDimension.is_active.is_(True),
        EvalDimension.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 单 case 执行（Phase 3：worker.run_case_job_logic 经 execute= 注入）
# ---------------------------------------------------------------------------


async def execute_case(
    db: AsyncSession,
    job_id: int,
    *,
    generate_fn: Callable[..., Awaitable[str]] | None = None,
    score_fn: Callable[..., Awaitable[str]] | None = None,
) -> None:
    """单个 case-job 的真实执行（Phase 3：generate → 多维 score → 写 case_result+scores）。

    异常**不捕获**，向上抛给 worker.run_case_job_logic（它负责 job→failed 收尾 +
    aggregate_run_progress 原子累加 run 计数）。

    三条硬约束（沿用已验证的原同步 case body 行为）：
    - generate/score 经 yunwu.chat，其内部 commit（写 AiCallLog）→ **必须在事务/savepoint
      之外**调，否则 commit 破坏外层事务（InvalidRequestError）。
    - 结果写入单次 commit（case 级隔离：失败不落半成品）。
    - run 计数不走这里，由 run_case_job_logic + aggregate_run_progress（原子 UPDATE）负责。

    Args:
        db: AsyncSession（worker 自开 session；测试注入 test_session）
        job_id: eval_case_jobs.id（绑唯一 test_case，无循环）
        generate_fn: 被测生成 callable（None 时经 adapter_registry 绑定）
        score_fn: 评委评分 callable（None 时经 adapter_registry 绑定）
    """
    job = await db.get(EvalCaseJob, job_id)
    if job is None:
        raise ValueError(f"EvalCaseJob not found: id={job_id}")

    run = await db.get(EvalRun, job.run_id)
    if run is None:
        raise ValueError(f"EvalRun not found: id={job.run_id} (job={job_id})")

    version = await db.get(EvalVersion, run.version_id)
    if version is None:
        raise ValueError(
            f"EvalVersion not found: id={run.version_id} (run={run.id}, job={job_id})"
        )

    strategy = await db.get(EvalStrategy, run.strategy_id)
    if strategy is None:
        raise ValueError(
            f"EvalStrategy not found: id={run.strategy_id} (run={run.id}, job={job_id})"
        )

    tc = await db.get(EvalTestCase, job.test_case_id)
    if tc is None:
        raise ValueError(
            f"EvalTestCase not found: id={job.test_case_id} (job={job_id})"
        )

    config = dict(version.config_payload or {})

    # --- resolve 评委身份：优先用 run.metadata 里 trigger_run 冻结的快照（B-C2 可复现：
    # 保证「冻结值 = 实际使用」，不受 run 进行中改 version/strategy 配置影响；也保证同 run
    # 各 job 用同一评委身份）。缺失（测试直建 run / 迁移期旧 run 无此字段）则回退现算。 ---
    resolved_scoring = (run.metadata_ or {}).get("resolved_scoring") or compute_resolved_scoring(
        strategy, config
    )
    if generate_fn is None or score_fn is None:
        adapter = get_adapter(resolved_scoring["adapter"])
        if generate_fn is None:
            generate_fn = functools.partial(
                adapter.chat,
                db=db,
                model_id=config.get("model_id"),
                provider=config.get("provider", DEFAULT_ADAPTER),
            )
        if score_fn is None:
            score_fn = functools.partial(
                adapter.chat,
                db=db,
                model_id=resolved_scoring["model_id"],
                provider=resolved_scoring["provider"],
            )

    dimensions = await _get_active_dimensions(db, version.tool_code)

    # --- generate + 每维 score（事务外 LLM：yunwu.chat 内部 commit）---
    generated_output = await generate(generate_fn, version, tc)
    input_context = dict(tc.input_payload or {})
    scored: list[tuple] = []
    for dim in dimensions:
        rubrics = await _get_default_rubrics(db, dim.id)
        weight = _resolve_weight(strategy, config, dim)
        parsed = await score(score_fn, dim, rubrics, generated_output, input_context)
        scored.append((dim, weight, parsed))

    # --- 结果写入（单 case 一次 commit；失败由调用方 rollback，不落半成品）---
    case_result = EvalCaseResult(
        run_id=run.id,
        test_case_id=tc.id,
        generated_output=generated_output,
        input_snapshot=tc.input_payload,
        output_payload={"text": generated_output},
    )
    db.add(case_result)
    await db.flush()  # 拿 case_result.id
    for dim, weight, parsed in scored:
        db.add(
            EvalScore(
                case_result_id=case_result.id,
                dimension_id=dim.id,
                ai_score=parsed.score,
                ai_reasoning=parsed.reasoning,
                ai_strengths=parsed.strengths,
                ai_weaknesses=parsed.weaknesses,
                weight_used=weight,
            )
        )
    await db.commit()

