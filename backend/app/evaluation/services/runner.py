"""
app/evaluation/services/runner.py

评测运行编排器（spec §6.1/§6.2/§6.5 + plan Phase 3）。

职责：
- 串起一次完整 run：生成→写 case_result→评分→写 score→更新 run 状态
- run 启动时 resolve 评委身份（strategy 三件套 override > version.config_payload）
  并写入 `eval_runs.metadata['resolved_scoring']`（B-C2，可复现）
- 经 `adapter_registry.get_adapter` 取适配器，分别用被测 model_id 绑 generate_fn、
  评委 model_id 绑 score_fn，注入 generator/scorer（方案 B，spec §2.9.3）
- case 级错误隔离：单 case 异常不中断其他 case（spec §6.5）
- 权重三级 resolve：strategy > version > dimension.default（spec §2.4）

异步执行一期用 BackgroundTask + DB 状态机；runner 持 session 写库，
generator/scorer 是纯函数不持 db（spec §6.1 服务职责分层）。

测试注入 mock generate_fn/score_fn 绕过 adapter/credentials（B-I1）。
"""
from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# AsyncSessionLocal 在模块顶部 import（满足 conftest patch 注册，spec §6.7）。
# execute_run 接受外部 db 参数（测试注入 test_session / 生产路径由 scheduler 传入），
# AsyncSessionLocal 留作未来 BackgroundTask 自开 session 路径扩展使用。
from app.core.database import AsyncSessionLocal  # noqa: F401
from app.evaluation.adapters.registry import get_adapter
from app.evaluation.constants import (
    DEFAULT_ADAPTER,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
)
from app.evaluation.models import (
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

__all__ = ["execute_run"]


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


async def _resolve_test_cases(
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
# 主入口
# ---------------------------------------------------------------------------


async def execute_run(
    run_id: int,
    db: AsyncSession,
    *,
    generate_fn: Callable[..., Awaitable[str]] | None = None,
    score_fn: Callable[..., Awaitable[str]] | None = None,
) -> None:
    """编排一次评测 run（spec §6.1）。

    Args:
        run_id: eval_runs.id
        db: AsyncSession（测试传 test_session；生产路径由 scheduler 传入）
        generate_fn: 被测生成 callable（None 时 runner 经 adapter_registry 绑定）
        score_fn: 评委评分 callable（None 时 runner 经 adapter_registry 绑定）

    副作用：
        - 写 eval_case_results / eval_scores
        - 更新 eval_runs.status / completed_cases / failed_cases / metadata
        - run.metadata['resolved_scoring']（B-C2）+ metadata['errors']（失败 case 汇总）
    """
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise ValueError(f"EvalRun not found: id={run_id}")

    version = await db.get(EvalVersion, run.version_id)
    if version is None:
        raise ValueError(
            f"EvalVersion not found: id={run.version_id} (run={run_id})"
        )

    strategy = await db.get(EvalStrategy, run.strategy_id)
    if strategy is None:
        raise ValueError(
            f"EvalStrategy not found: id={run.strategy_id} (run={run_id})"
        )

    config = dict(version.config_payload or {})

    # --- run 启动阶段：resolve 评委身份（spec §2.9.2/§2.9.4 B-C2）---
    resolved_scoring = {
        "model_id": _resolve_with_strategy_override(
            strategy.scoring_model_override,
            config.get("scoring_model_id"),
        ),
        "provider": _resolve_with_strategy_override(
            strategy.scoring_provider_override,
            config.get("scoring_provider"),
        ),
        "adapter": _resolve_with_strategy_override(
            strategy.scoring_adapter_override,
            config.get("scoring_adapter"),
            fallback=DEFAULT_ADAPTER,
        ),
    }

    run_meta = dict(run.metadata_ or {})
    run_meta["resolved_scoring"] = resolved_scoring

    # --- 绑定 callable（方案 B，spec §2.9.3）---
    # 测试路径直接用注入的 mock；生产路径（None）经 adapter_registry 绑定。
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

    # --- 选 test_cases + 维度（在循环前一次性查好）---
    test_cases = await _resolve_test_cases(
        db, version.tool_code, strategy.test_case_selector
    )
    dimensions = await _get_active_dimensions(db, version.tool_code)

    run.metadata_ = run_meta
    run.status = RUN_STATUS_RUNNING
    run.total_cases = len(test_cases)
    run.completed_cases = 0
    run.failed_cases = 0
    run.started_at = datetime.now(timezone.utc)
    await db.commit()

    # --- case 循环（spec §6.5 case 级错误隔离）---
    errors: list[str] = list(run_meta.get("errors", []))

    for tc in test_cases:
        try:
            # savepoint：case 内任一步骤失败 → 回滚该 case 的所有写入，不影响其他 case
            async with db.begin_nested():
                # 1. 被测生成
                generated_output = await generate(generate_fn, version, tc)

                # 2. 写 case_result（含输入快照 + 输出 payload）
                case_result = EvalCaseResult(
                    run_id=run.id,
                    test_case_id=tc.id,
                    generated_output=generated_output,
                    input_snapshot=tc.input_payload,
                    output_payload={"text": generated_output},
                )
                db.add(case_result)
                await db.flush()  # 拿 case_result.id

                # 3. 每维度评分
                input_context = dict(tc.input_payload or {})
                for dim in dimensions:
                    rubrics = await _get_default_rubrics(db, dim.id)
                    weight = _resolve_weight(strategy, config, dim)
                    parsed = await score(
                        score_fn, dim, rubrics, generated_output, input_context
                    )
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
            # savepoint 正常退出 → case 成功
            run.completed_cases += 1
        except Exception as exc:  # noqa: BLE001 —— case 级隔离需捕获所有异常
            # savepoint 已自动回滚该 case 的所有写入
            run.failed_cases += 1
            tc_name = getattr(tc, "name", "?")
            errors.append(
                f"case {tc.id} ({tc_name}): {type(exc).__name__}: {exc}"
            )

    # --- 收尾 ---
    final_meta = dict(run.metadata_ or {})
    final_meta["resolved_scoring"] = resolved_scoring
    final_meta["errors"] = errors
    run.metadata_ = final_meta
    run.finished_at = datetime.now(timezone.utc)

    # 全部 case 失败 → run failed；否则 completed（部分失败仍 completed，spec §6.5）
    if run.total_cases > 0 and run.completed_cases == 0:
        run.status = RUN_STATUS_FAILED
    else:
        run.status = RUN_STATUS_COMPLETED

    await db.commit()
