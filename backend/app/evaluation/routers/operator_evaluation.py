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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.user import User

from app.evaluation.constants import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    TRIGGER_TYPE_MANUAL,
)
from app.evaluation.models import (
    EvalCaseJob,
    EvalCaseResult,
    EvalDimension,
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
from app.evaluation.worker import retry_failed_job
from app.evaluation.services.comparator import compare_runs

router = APIRouter(
    prefix="/operator/evaluation",
    tags=["operator-evaluation"],
    lifespan=None,
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


def _num(v):
    """Numeric 列（Decimal）→ float。不转的话 FastAPI 会把 Decimal 序列化成 JSON 字符串，
    前端按 number 消费（如 ai_score.toFixed）直接崩（RunDetail 白屏的根因）。"""
    return float(v) if v is not None else None


def _score_to_dict(s: EvalScore) -> dict:
    return {
        "id": s.id,
        "case_result_id": s.case_result_id,
        "dimension_id": s.dimension_id,
        "weight_used": _num(s.weight_used),
        "ai_score": _num(s.ai_score),
        "ai_reasoning": s.ai_reasoning,
        "ai_strengths": list(s.ai_strengths or []),
        "ai_weaknesses": list(s.ai_weaknesses or []),
        "human_score": _num(s.human_score),
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


@router.get("/test-cases/{test_case_id}")
async def get_test_case(
    test_case_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """测试样本单条（编辑模式用，替代早期 list+find，样本超 50 也能取到）。"""
    tc = await db.get(EvalTestCase, test_case_id)
    if tc is None or tc.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "测试样本不存在"},
        )
    return success_response(data=_test_case_to_dict(tc))


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


@router.get("/runs")
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    version_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运行分页列表（status / version_id 过滤，id 倒序）。

    响应：{items:[_run_to_dict], pagination:{page,page_size,total,total_pages}}。
    """
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    stmt = select(EvalRun)
    if status:
        stmt = stmt.where(EvalRun.status == status)
    if version_id:
        stmt = stmt.where(EvalRun.version_id == version_id)

    from sqlalchemy import func as sa_func
    count_stmt = select(sa_func.count()).select_from(EvalRun)
    if status:
        count_stmt = count_stmt.where(EvalRun.status == status)
    if version_id:
        count_stmt = count_stmt.where(EvalRun.version_id == version_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(EvalRun.id.desc()).limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(stmt)).scalars().all()

    items = [_run_to_dict(r) for r in rows]
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


@router.post("/runs")
async def trigger_run(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """触发评测运行（一期自动绑定 default 策略，不传 strategy_id）。

    body 含 version_id / filter_tags / name / trigger_type。
    调 scheduler.trigger_run（异步：建 run(pending)+N case-job+入队，立即返回 run_id；
    实际执行由独立 worker 进程异步消费 case-job）。
    """
    version_id = body.get("version_id")
    if not version_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "version_id 必填"},
        )

    filter_tags = list(body.get("filter_tags") or [])
    trigger_type = body.get("trigger_type") or TRIGGER_TYPE_MANUAL
    run_name = (str(body.get("name") or "").strip()) or None  # 用户自定义运行名（空则后端默认生成）

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

    # 调 scheduler.trigger_run（异步：建 run(pending)+N case-job+入队，立即返回）
    run_id = await scheduler.trigger_run(
        version_id=int(version_id),
        filter_tags=filter_tags,
        trigger_type=trigger_type,
        user_id=current_user.id,
        db=db,
        name=run_name,
    )
    # run 现为 pending；执行由 worker 异步推进（不在此 await）
    run = await db.get(EvalRun, run_id)
    return success_response(data=_run_to_dict(run) if run else {"id": run_id})


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运行状态查询（含 ETA：avg_case_duration_secs + eta_secs）。"""
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )
    # ETA：用本 run 已完成 job 的平均耗时估算剩余（无 done job 则 null）
    dur = (await db.execute(
        text(
            "SELECT AVG(EXTRACT(EPOCH FROM (finished_at - started_at))), "
            "COUNT(*) FILTER (WHERE status = 'done'), "
            "COUNT(*) FILTER (WHERE status = 'pending') "
            "FROM eval_case_jobs WHERE run_id = :rid"
        ),
        {"rid": run_id},
    )).fetchone()
    avg_dur = dur[0] if dur else None
    pending_n = (dur[2] if dur else 0) or 0
    data = _run_to_dict(run)
    data["avg_case_duration_secs"] = int(avg_dur) if avg_dur is not None else None
    data["eta_secs"] = int(avg_dur * pending_n) if (avg_dur is not None and pending_n > 0) else None
    return success_response(data=data)


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

    # 维度 id → 显示名（徽章直接显示「开头钩子力」而非 d4；前端不再自行拉维度）
    dim_ids = {s.dimension_id for s in rows}
    dim_names: dict[int, str | None] = {}
    if dim_ids:
        dim_rows = (await db.execute(
            select(EvalDimension).where(EvalDimension.id.in_(dim_ids))
        )).scalars().all()
        dim_names = {d.id: d.display_name or d.name for d in dim_rows}

    data = []
    for s in rows:
        d = _score_to_dict(s)
        d["dimension_name"] = dim_names.get(s.dimension_id)
        data.append(d)
    return success_response(data=data)


@router.get("/runs/{run_id}/case-results")
async def list_run_case_results(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """运行的所有 case 生成结果（含 generated_output，供前端「查看输出」）。

    join eval_test_cases 拿真实样本名；按 test_case_id 排序。
    """
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )
    from sqlalchemy import and_
    stmt = (
        select(EvalCaseResult, EvalTestCase.name, EvalCaseJob.id, EvalCaseJob.status, EvalCaseJob.last_error)
        .outerjoin(EvalTestCase, EvalTestCase.id == EvalCaseResult.test_case_id)
        # job 按 (run, test_case) 匹配且仅取最新一条（同 case 重跑会产生多 job 时以 id 最大为准）
        .outerjoin(EvalCaseJob, and_(
            EvalCaseJob.run_id == EvalCaseResult.run_id,
            EvalCaseJob.test_case_id == EvalCaseResult.test_case_id,
        ))
        .where(EvalCaseResult.run_id == run_id)
        .order_by(EvalCaseResult.test_case_id.asc(), EvalCaseJob.id.desc())
    )
    # 同 (case_result) 可能 join 出多条 job（历史重跑）——按 case_result 去重取第一条（最新 job）
    seen: set[int] = set()
    items = []
    for cr, name, job_id, job_status, job_error in (await db.execute(stmt)).all():
        if cr.id in seen:
            continue
        seen.add(cr.id)
        items.append({
            "id": cr.id,
            "test_case_id": cr.test_case_id,
            "test_case_name": name or f"样本 #{cr.test_case_id}",
            "generated_output": cr.generated_output,
            "output_payload": cr.output_payload,
            "input_snapshot": cr.input_snapshot,
            "created_at": _ts(cr.created_at),
            # job 状态（P2 重跑按钮依据）
            "job_id": job_id,
            "job_status": job_status,
            "job_error": job_error,
        })
    return success_response(data=items)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """取消运行：pending job 标 cancelled + run 直接收尾 cancelled（写 OperationLog）。

    worker 无需改动——已入队的 pending job 被 arq 投递时，run_case_job_logic 的幂等守卫
    （status ∈ terminal → skip）自动跳过；在跑的 job 自然跑完（结果落库，run 仍 cancelled）。
    """
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )
    if run.status not in (RUN_STATUS_PENDING, RUN_STATUS_RUNNING):
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": f"运行已终态（{run.status}），无法取消"},
        )

    prev_status = run.status
    # pending job → cancelled（在跑的 job 不动，自然跑完）
    await db.execute(
        text(
            "UPDATE eval_case_jobs SET status = 'cancelled', finished_at = NOW() "
            "WHERE run_id = :rid AND status = 'pending'"
        ),
        {"rid": run_id},
    )
    run.status = RUN_STATUS_CANCELLED
    run.finished_at = datetime.now(timezone.utc)

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_run_cancel",
        target_type="eval_run",
        target_id=run.id,
        detail={"prev_status": prev_status},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(run)
    return success_response(data=_run_to_dict(run))


@router.get("/runs/{run_id}/jobs")
async def list_run_jobs(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """单 run 的逐 job 明细（失败 case 重跑入口：无 case_result 的 failed job 只在此可见）。"""
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
        )
    rows = (await db.execute(
        select(EvalCaseJob).where(EvalCaseJob.run_id == run_id).order_by(EvalCaseJob.id)
    )).scalars().all()
    return success_response(data=[
        {
            "id": j.id,
            "test_case_id": j.test_case_id,
            "status": j.status,
            "attempts": j.attempts,
            "last_error": j.last_error,
            "started_at": _ts(j.started_at),
            "finished_at": _ts(j.finished_at),
        }
        for j in rows
    ])


@router.post("/runs/{run_id}/jobs/{job_id}/retry")
async def retry_job(
    run_id: int,
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """重跑单个失败 case-job（run 详情页"重跑"按钮）。

    - job 必须属于该 run 且状态 failed（否则 409）
    - 重置 pending + failed_cases-1 + run 终态回 running + 重新入队
    - redis 不可用时 503（trigger 同款降级：队列故障不应把 job 状态卡在半途——
      先入队后 commit 的顺序由 retry_failed_job 保证，此处仅转发其错误）
    """
    # 归属校验
    row = (
        await db.execute(
            text("SELECT run_id, status FROM eval_case_jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).fetchone()
    if row is None or row[0] != run_id:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "job 不存在或不属于该运行"},
        )

    try:
        result = await retry_failed_job(db, job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": str(e)},
        )
    except Exception as e:  # redis/arq 入队失败
        raise HTTPException(
            status_code=503,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": f"队列暂不可用，稍后重试: {str(e)[:120]}"},
        )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_job_retry",
        target_type="eval_case_job",
        target_id=job_id,
        detail={"run_id": run_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data=result, message="已重新入队，稍后刷新查看结果")


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
