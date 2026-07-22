"""
app/evaluation/routers/operator_evaluation.py

AIGC 评测 — 运营/管理员接口（spec §9 + plan Phase 4 Task 3）。

权限：operator / admin 角色共用。require_operator 在本文件内复制
（手术刀原则，参照 operator_qianchuan_writer.py 风格，不抽公共）。

接口列表：
  测试集 CRUD
    GET    /operator/evaluation/test-cases                分页列表（账号隔离）
    POST   /operator/evaluation/test-cases                创建样本
    PUT    /operator/evaluation/test-cases/{id}           更新
    DELETE /operator/evaluation/test-cases/{id}           软删
  版本只读
    GET    /operator/evaluation/versions                  版本列表（只读）
  运行
    POST   /operator/evaluation/runs                      触发运行（调 scheduler.trigger_run）
    GET    /operator/evaluation/runs/{id}                 运行状态
    GET    /operator/evaluation/runs/{id}/scores          评分明细
  评分
    PUT    /operator/evaluation/scores/{id}/human-label   人工校准（单事务原子）
  对比
    GET    /operator/evaluation/compare                   版本对比（调 comparator.compare_runs）

所有写操作写 OperationLog（action 前缀 evaluation_）。
"""
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.user import User

from app.evaluation.constants import TRIGGER_TYPE_MANUAL
from app.evaluation.models import (
    EvalCaseResult,
    EvalHumanLabel,
    EvalRun,
    EvalScore,
    EvalTestCase,
    EvalVersion,
)
from app.evaluation.schemas import (
    HumanLabelRequest,
    TestCaseCreate,
    TestCaseUpdate,
)
from app.evaluation.services import scheduler
from app.evaluation.services.comparator import compare_runs

router = APIRouter(
    prefix="/operator/evaluation",
    tags=["operator-evaluation"],
)


_PAGE_SIZE_ALLOWED = {10, 20, 50}


# ---------------------------------------------------------------------------
# 内部 helpers（参照 operator_qianchuan_writer.py 风格，手术刀原则不抽公共）
# ---------------------------------------------------------------------------


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """operator / admin 角色校验 + 已改密。"""
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _test_case_to_dict(tc: EvalTestCase) -> dict:
    return {
        "id": tc.id,
        "tool_code": tc.tool_code,
        "name": tc.name,
        "description": tc.description,
        "input_payload": tc.input_payload,
        "expected_output": tc.expected_output,
        "tags": list(tc.tags or []),
        "is_active": tc.is_active,
        "created_by": tc.created_by,
        "updated_by": tc.updated_by,
        "created_at": _ts(tc.created_at),
        "updated_at": _ts(tc.updated_at),
        "deleted_at": _ts(tc.deleted_at),
    }


def _version_to_dict(v: EvalVersion) -> dict:
    return {
        "id": v.id,
        "tool_code": v.tool_code,
        "name": v.name,
        "description": v.description,
        "config_payload": v.config_payload,
        "parent_version_id": v.parent_version_id,
        "source_kol_id": v.source_kol_id,
        "auto_run_on_create": v.auto_run_on_create,
        "auto_run_tags": list(v.auto_run_tags or []),
        "is_active": v.is_active,
        "created_by": v.created_by,
        "created_at": _ts(v.created_at),
        "updated_at": _ts(v.updated_at),
        "deleted_at": _ts(v.deleted_at),
    }


def _run_to_dict(r: EvalRun) -> dict:
    return {
        "id": r.id,
        "version_id": r.version_id,
        "strategy_id": r.strategy_id,
        "name": r.name,
        "trigger_type": r.trigger_type,
        "status": r.status,
        "filter_tags": list(r.filter_tags or []),
        "total_cases": r.total_cases,
        "completed_cases": r.completed_cases,
        "failed_cases": r.failed_cases,
        "metadata": r.metadata_ or {},
        "created_by": r.created_by,
        "started_at": _ts(r.started_at),
        "finished_at": _ts(r.finished_at),
        "created_at": _ts(r.created_at),
    }


def _score_to_dict(s: EvalScore) -> dict:
    return {
        "id": s.id,
        "case_result_id": s.case_result_id,
        "dimension_id": s.dimension_id,
        "weight_used": s.weight_used,
        "ai_score": s.ai_score,
        "ai_reasoning": s.ai_reasoning,
        "ai_strengths": list(s.ai_strengths or []),
        "ai_weaknesses": list(s.ai_weaknesses or []),
        "human_score": s.human_score,
        "human_feedback": s.human_feedback,
        "created_at": _ts(s.created_at),
        "updated_at": _ts(s.updated_at),
    }


# ---------------------------------------------------------------------------
# 测试集 CRUD
# ---------------------------------------------------------------------------


@router.get("/test-cases")
async def list_test_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tool_code: str | None = None,
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """测试集分页列表（一期不按账号隔离，全量只读；标签/工具过滤）。"""
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    stmt = select(EvalTestCase).where(EvalTestCase.deleted_at.is_(None))
    if tool_code:
        stmt = stmt.where(EvalTestCase.tool_code == tool_code)
    if tag:
        stmt = stmt.where(EvalTestCase.tags.contains([tag]))

    # 总数（独立 count 查询）
    from sqlalchemy import func as sa_func
    count_stmt = select(sa_func.count()).select_from(EvalTestCase).where(
        EvalTestCase.deleted_at.is_(None)
    )
    if tool_code:
        count_stmt = count_stmt.where(EvalTestCase.tool_code == tool_code)
    if tag:
        count_stmt = count_stmt.where(EvalTestCase.tags.contains([tag]))
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页
    stmt = stmt.order_by(EvalTestCase.id.desc()).limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(stmt)).scalars().all()

    items = [_test_case_to_dict(tc) for tc in rows]
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return success_response(data={
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    })


@router.post("/test-cases")
async def create_test_case(
    body: TestCaseCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """创建测试样本，写 OperationLog。"""
    tc = EvalTestCase(
        tool_code=body.tool_code,
        name=body.name,
        description=body.description,
        input_payload=body.input_payload,
        expected_output=body.expected_output,
        tags=list(body.tags or []),
        is_active=body.is_active,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(tc)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_test_case_create",
        target_type="eval_test_case",
        target_id=tc.id,
        detail={"name": tc.name, "tool_code": tc.tool_code, "tags": list(tc.tags or [])},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(tc)
    return success_response(data=_test_case_to_dict(tc))


@router.put("/test-cases/{test_case_id}")
async def update_test_case(
    test_case_id: int,
    body: TestCaseUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """更新测试样本（部分字段），写 OperationLog。"""
    tc = await db.get(EvalTestCase, test_case_id)
    if tc is None or tc.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "测试样本不存在"},
        )

    payload = body.model_dump(exclude_unset=True, mode="json")
    for key, value in payload.items():
        setattr(tc, key, value)
    tc.updated_by = current_user.id
    tc.updated_at = datetime.now(timezone.utc)

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_test_case_update",
        target_type="eval_test_case",
        target_id=tc.id,
        detail=payload,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(tc)
    return success_response(data=_test_case_to_dict(tc))


@router.delete("/test-cases/{test_case_id}")
async def delete_test_case(
    test_case_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删测试样本（置 deleted_at），写 OperationLog。"""
    tc = await db.get(EvalTestCase, test_case_id)
    if tc is None or tc.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "测试样本不存在"},
        )
    tc.deleted_at = datetime.now(timezone.utc)
    tc.updated_at = datetime.now(timezone.utc)
    tc.updated_by = current_user.id
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_test_case_delete",
        target_type="eval_test_case",
        target_id=tc.id,
        detail={"name": tc.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": tc.id, "deleted_at": _ts(tc.deleted_at)})


# ---------------------------------------------------------------------------
# 版本只读
# ---------------------------------------------------------------------------


@router.get("/versions")
async def list_versions(
    tool_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运营端只读版本列表（不暴露 config_payload 敏感字段也可，一期保持完整只读）。"""
    stmt = select(EvalVersion).where(
        EvalVersion.deleted_at.is_(None),
        EvalVersion.is_active.is_(True),
    )
    if tool_code:
        stmt = stmt.where(EvalVersion.tool_code == tool_code)
    stmt = stmt.order_by(EvalVersion.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_version_to_dict(v) for v in rows])


# ---------------------------------------------------------------------------
# 运行触发 + 查询
# ---------------------------------------------------------------------------


@router.post("/runs")
async def trigger_run(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """触发评测运行（一期自动绑定 default 策略，不传 strategy_id）。

    body 含 version_id / filter_tags / name / trigger_type。
    调 scheduler.trigger_run（一期同步 await，二期改 BackgroundTask）。
    """
    version_id = body.get("version_id")
    if not version_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "version_id 必填"},
        )

    filter_tags = list(body.get("filter_tags") or [])
    trigger_type = body.get("trigger_type") or TRIGGER_TYPE_MANUAL

    # OperationLog（run_id 在 trigger_run 内部生成，这里先记录触发意图）
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_run_trigger",
        target_type="eval_version",
        target_id=int(version_id),
        detail={
            "filter_tags": filter_tags,
            "trigger_type": trigger_type,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    # 调 scheduler.trigger_run（建 run + 调 runner.execute_run）
    run_id = await scheduler.trigger_run(
        version_id=int(version_id),
        filter_tags=filter_tags,
        trigger_type=trigger_type,
        user_id=current_user.id,
        db=db,
    )
    # 刷新 run 实体（trigger_run 内部已 commit + execute_run 写完）
    run = await db.get(EvalRun, run_id)
    return success_response(data=_run_to_dict(run) if run else {"id": run_id})


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运行状态查询。"""
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )
    return success_response(data=_run_to_dict(run))


@router.get("/runs/{run_id}/scores")
async def list_run_scores(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运行的所有评分明细（join case_results → scores）。"""
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )

    stmt = (
        select(EvalScore)
        .join(EvalCaseResult, EvalScore.case_result_id == EvalCaseResult.id)
        .where(EvalCaseResult.run_id == run_id)
        .order_by(EvalCaseResult.test_case_id.asc(), EvalScore.dimension_id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_score_to_dict(s) for s in rows])


# ---------------------------------------------------------------------------
# 人工校准 — 单事务原子性
# ---------------------------------------------------------------------------


@router.put("/scores/{score_id}/human-label")
async def submit_human_label(
    score_id: int,
    body: HumanLabelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """人工校准评分（spec §5.4 单事务原子性）。

    在同一 db.commit 前完成（AtomicWrite）：
      ① 更新 eval_scores.human_score / human_feedback
      ② 插入 eval_human_labels 历史记录（old/new/feedback）
      ③ 写 OperationLog

    事务保证三者要么全成要么全败。
    """
    score = await db.get(EvalScore, score_id)
    if score is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "评分不存在"},
        )

    old_score = score.human_score
    # ① 更新 score
    score.human_score = body.human_score
    score.human_feedback = body.human_feedback
    score.updated_at = datetime.now(timezone.utc)

    # ② 插入历史记录
    db.add(EvalHumanLabel(
        score_id=score.id,
        old_score=old_score,
        new_score=body.human_score,
        feedback=body.human_feedback,
        labeled_by=current_user.id,
    ))

    # ③ 写 OperationLog
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_human_label_submit",
        target_type="eval_score",
        target_id=score.id,
        detail={
            "old_score": str(old_score) if old_score is not None else None,
            "new_score": str(body.human_score),
            "dimension_id": score.dimension_id,
            "case_result_id": score.case_result_id,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))

    await db.commit()
    await db.refresh(score)
    return success_response(data=_score_to_dict(score))


# ---------------------------------------------------------------------------
# 版本对比
# ---------------------------------------------------------------------------


@router.get("/compare")
async def compare_runs_endpoint(
    run_a: int = Query(..., description="基准 run id（旧版本）"),
    run_b: int = Query(..., description="对比 run id（新版本）"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """版本对比（调 comparator.compare_runs，返回 ComparisonReport 结构）。"""
    # 校验 run 存在
    for rid in (run_a, run_b):
        run = await db.get(EvalRun, rid)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": f"run {rid} 不存在"},
            )

    report = await compare_runs(run_a, run_b, db)
    return success_response(data={
        "run_a_id": report.run_a_id,
        "run_b_id": report.run_b_id,
        "overall_avg_a": report.overall_avg_a,
        "overall_avg_b": report.overall_avg_b,
        "overall_delta": report.overall_delta,
        "dimension_deltas": [
            {
                "dimension_id": d.dimension_id,
                "dimension_name": d.dimension_name,
                "avg_a": d.avg_a,
                "avg_b": d.avg_b,
                "delta": d.delta,
            }
            for d in report.dimension_deltas
        ],
        "case_deltas": [
            {
                "test_case_id": c.test_case_id,
                "test_case_name": c.test_case_name,
                "avg_a": c.avg_a,
                "avg_b": c.avg_b,
                "delta": c.delta,
                "direction": c.direction,
            }
            for c in report.case_deltas
        ],
        "summary": dict(report.summary),
    })
