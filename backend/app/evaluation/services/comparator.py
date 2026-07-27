"""
app/evaluation/services/comparator.py

两次 run 的评分对比：计算总体/维度/样本级 diff，分类改善/恶化/持平。

设计要点（spec §7.2/plan Phase 2）：
- 按 test_case_id 跨 run 对齐（不是 case_result_id，跨 run 主键不同）
- 计算：总体平均分 diff、每维度平均分 diff、样本级 ↑↓→ 分类
- comparator 自管 DB 读（唯一调用方是 operator router GET /compare，只有 run id）
- 唯一带 db 的 service（async，接收 AsyncSession 参数）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.models import EvalCaseResult, EvalDimension, EvalScore, EvalTestCase

__all__ = ["DimensionDelta", "CaseDelta", "ComparisonReport", "compare_runs"]


@dataclass
class DimensionDelta:
    """单维度的两次 run 平均分 diff。"""

    dimension_id: int
    dimension_name: str | None
    avg_a: float
    avg_b: float
    delta: float  # b - a（正=改善，负=恶化）


@dataclass
class CaseDelta:
    """单样本的两次 run 平均分 diff + 方向分类。"""

    test_case_id: int
    test_case_name: str | None
    avg_a: float
    avg_b: float
    delta: float  # b - a
    direction: str  # "up"(↑) | "down"(↓) | "same"(→) | "only_a" | "only_b"


@dataclass
class ComparisonReport:
    """两次 run 的完整对比报告。"""

    run_a_id: int
    run_b_id: int
    overall_avg_a: float
    overall_avg_b: float
    overall_delta: float  # b - a
    dimension_deltas: list[DimensionDelta] = field(default_factory=list)
    case_deltas: list[CaseDelta] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=lambda: {"up": 0, "down": 0, "same": 0})


async def _fetch_run_scores(db: AsyncSession, run_id: int) -> list[Any]:
    """
    查询单次 run 的所有评分行（跨 case_result + score + test_case + dimension join）。

    返回 Row 列表，每行含：
    test_case_id, test_case_name, dimension_id, dimension_name, ai_score
    """
    stmt = (
        select(
            EvalCaseResult.test_case_id,
            EvalTestCase.name.label("test_case_name"),
            EvalScore.dimension_id,
            EvalDimension.name.label("dimension_name"),
            EvalScore.ai_score,
        )
        .join(EvalScore, EvalCaseResult.id == EvalScore.case_result_id)
        .join(EvalTestCase, EvalCaseResult.test_case_id == EvalTestCase.id)
        .join(EvalDimension, EvalScore.dimension_id == EvalDimension.id)
        .where(EvalCaseResult.run_id == run_id)
    )
    result = await db.execute(stmt)
    return list(result.all())


def _avg(values: list[float]) -> float:
    """安全平均值，空列表返回 0.0。"""
    return sum(values) / len(values) if values else 0.0


def _classify(delta: float) -> str:
    """根据 delta 分类方向：>0 → up，<0 → down，==0 → same。"""
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "same"


async def compare_runs(
    run_a_id: int, run_b_id: int, db: AsyncSession
) -> ComparisonReport:
    """
    对比两次 run 的评分结果。

    按 test_case_id 跨 run 对齐（不是 case_result_id，跨 run 主键不同）。
    计算：总体平均分 diff、每维度平均分 diff、样本级 ↑↓→ 分类。

    Args:
        run_a_id: 基准 run（通常是旧版本）
        run_b_id: 对比 run（通常是新版本）
        db: AsyncSession（由 router 的 Depends(get_db) 传入）

    Returns:
        ComparisonReport
    """
    rows_a = await _fetch_run_scores(db, run_a_id)
    rows_b = await _fetch_run_scores(db, run_b_id)

    # --- 总体平均分 ---
    all_scores_a = [float(r.ai_score) for r in rows_a if r.ai_score is not None]
    all_scores_b = [float(r.ai_score) for r in rows_b if r.ai_score is not None]
    overall_avg_a = _avg(all_scores_a)
    overall_avg_b = _avg(all_scores_b)

    # --- 每维度平均分 ---
    dim_scores_a: dict[int, list[float]] = {}
    dim_scores_b: dict[int, list[float]] = {}
    dim_names: dict[int, str | None] = {}
    for r in rows_a:
        if r.ai_score is None:
            continue
        dim_scores_a.setdefault(r.dimension_id, []).append(float(r.ai_score))
        dim_names[r.dimension_id] = r.dimension_name
    for r in rows_b:
        if r.ai_score is None:
            continue
        dim_scores_b.setdefault(r.dimension_id, []).append(float(r.ai_score))
        dim_names[r.dimension_id] = r.dimension_name

    dimension_deltas: list[DimensionDelta] = []
    for dim_id in sorted(set(dim_scores_a) | set(dim_scores_b)):
        avg_a = _avg(dim_scores_a.get(dim_id, []))
        avg_b = _avg(dim_scores_b.get(dim_id, []))
        dimension_deltas.append(
            DimensionDelta(
                dimension_id=dim_id,
                dimension_name=dim_names.get(dim_id),
                avg_a=avg_a,
                avg_b=avg_b,
                delta=avg_b - avg_a,
            )
        )

    # --- 样本级（按 test_case_id 对齐）---
    case_scores_a: dict[int, list[float]] = {}
    case_scores_b: dict[int, list[float]] = {}
    case_names: dict[int, str | None] = {}
    for r in rows_a:
        if r.ai_score is None:
            continue
        case_scores_a.setdefault(r.test_case_id, []).append(float(r.ai_score))
        case_names[r.test_case_id] = r.test_case_name
    for r in rows_b:
        if r.ai_score is None:
            continue
        case_scores_b.setdefault(r.test_case_id, []).append(float(r.ai_score))
        case_names[r.test_case_id] = r.test_case_name

    case_deltas: list[CaseDelta] = []
    summary = {"up": 0, "down": 0, "same": 0}
    for tc_id in sorted(set(case_scores_a) | set(case_scores_b)):
        in_a = tc_id in case_scores_a
        in_b = tc_id in case_scores_b
        avg_a = _avg(case_scores_a.get(tc_id, []))
        avg_b = _avg(case_scores_b.get(tc_id, []))

        if in_a and in_b:
            delta = avg_b - avg_a
            direction = _classify(delta)
            summary[direction] += 1
        elif in_a:
            delta = 0.0  # 仅在 run_a，无对比基准
            direction = "only_a"
        else:
            delta = 0.0  # 仅在 run_b，无对比基准
            direction = "only_b"

        case_deltas.append(
            CaseDelta(
                test_case_id=tc_id,
                test_case_name=case_names.get(tc_id),
                avg_a=avg_a,
                avg_b=avg_b,
                delta=delta,
                direction=direction,
            )
        )

    return ComparisonReport(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        overall_avg_a=overall_avg_a,
        overall_avg_b=overall_avg_b,
        overall_delta=overall_avg_b - overall_avg_a,
        dimension_deltas=dimension_deltas,
        case_deltas=case_deltas,
        summary=summary,
    )
