"""
app/evaluation/routers/admin_evaluation.py

AIGC 评测 — 管理员接口（spec §9 + plan Phase 4 Task 2）。

权限：admin 角色专用（require_admin from app.middlewares.auth）。

接口列表：
  维度 CRUD
    GET    /admin/evaluation/dimensions
    POST   /admin/evaluation/dimensions
    PUT    /admin/evaluation/dimensions/{id}
    DELETE /admin/evaluation/dimensions/{id}              软删（置 deleted_at）
  Rubric
    GET    /admin/evaluation/dimensions/{id}/rubrics
    PUT    /admin/evaluation/dimensions/{id}/rubrics      整批替换
  版本快照（不可编辑）
    GET    /admin/evaluation/versions
    POST   /admin/evaluation/versions                     关联维护三步（spec §4.4）
    GET    /admin/evaluation/versions/{id}
    DELETE /admin/evaluation/versions/{id}                软删
    POST   /admin/evaluation/versions/{id}/clone          复制新版本
  调度策略
    GET    /admin/evaluation/schedule-policies
    POST   /admin/evaluation/schedule-policies            croniter 校验
    PUT    /admin/evaluation/schedule-policies/{id}       croniter 校验
    DELETE /admin/evaluation/schedule-policies/{id}       软删

所有写操作写 OperationLog（action 前缀 evaluation_）。
非流式响应统一标准信封 success_response/error_response（红线 #1）。
"""
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.qianchuan_writer import QianchuanWriterConfig
from app.models.user import User
from app.services import kol_context, workspace_prompt

from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER
from app.evaluation.models import (
    EvalDimension,
    EvalRubric,
    EvalSchedulePolicy,
    EvalVersion,
)
from app.evaluation.schemas import (
    DimensionCreate,
    DimensionResponse,
    DimensionUpdate,
    RubricBatchUpdate,
    RubricItemInput,
    RubricResponse,
    SchedulePolicyCreate,
    SchedulePolicyResponse,
    SchedulePolicyUpdate,
    VersionClone,
    VersionCreate,
    VersionResponse,
)

router = APIRouter(
    prefix="/admin/evaluation",
    tags=["admin-evaluation"],
)


# ---------------------------------------------------------------------------
# 内部 helpers（参照 admin_qianchuan_writer.py 风格，手术刀原则不抽公共）
# ---------------------------------------------------------------------------


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _dimension_to_dict(d: EvalDimension) -> dict:
    return {
        "id": d.id,
        "tool_code": d.tool_code,
        "name": d.name,
        "display_name": d.display_name,
        "description": d.description,
        "default_weight": d.default_weight,
        "score_min": d.score_min,
        "score_max": d.score_max,
        "prompt_template": d.prompt_template,
        "is_active": d.is_active,
        "created_at": _ts(d.created_at),
        "updated_at": _ts(d.updated_at),
        "deleted_at": _ts(d.deleted_at),
    }


def _rubric_to_dict(r: EvalRubric) -> dict:
    return {
        "id": r.id,
        "dimension_id": r.dimension_id,
        "level": r.level,
        "criteria": r.criteria,
        "scenario_tag": r.scenario_tag,
        "is_active": r.is_active,
        "created_at": _ts(r.created_at),
        "updated_at": _ts(r.updated_at),
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


def _schedule_policy_to_dict(p: EvalSchedulePolicy) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "cron": p.cron,
        "version_id": p.version_id,
        "filter_tags": list(p.filter_tags or []),
        "is_active": p.is_active,
        "created_by": p.created_by,
        "created_at": _ts(p.created_at),
        "updated_at": _ts(p.updated_at),
        "deleted_at": _ts(p.deleted_at),
    }


def _validate_cron(expr: str) -> None:
    """croniter 校验 cron 表达式，非法抛 400（spec §3.4）。"""
    try:
        croniter(expr)  # 不传 base_time，仅校验表达式语法
    except (ValueError, KeyError, AttributeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CRON",
                "message": f"非法 cron 表达式 {expr!r}: {exc}",
            },
        )


# ---------------------------------------------------------------------------
# 维度 CRUD
# ---------------------------------------------------------------------------


@router.get("/dimensions")
async def list_dimensions(
    tool_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出全部 active 维度（默认仅未软删的）。"""
    stmt = select(EvalDimension).where(EvalDimension.deleted_at.is_(None))
    if tool_code:
        stmt = stmt.where(EvalDimension.tool_code == tool_code)
    stmt = stmt.order_by(EvalDimension.id.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_dimension_to_dict(d) for d in rows])


@router.post("/dimensions")
async def create_dimension(
    body: DimensionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建维度，写 OperationLog。"""
    dim = EvalDimension(
        tool_code=body.tool_code,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        default_weight=body.default_weight,
        score_min=body.score_min,
        score_max=body.score_max,
        prompt_template=body.prompt_template,
        is_active=body.is_active,
    )
    db.add(dim)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_dimension_create",
        target_type="eval_dimension",
        target_id=dim.id,
        detail={"name": dim.name, "tool_code": dim.tool_code},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(dim)
    return success_response(data=_dimension_to_dict(dim))


@router.put("/dimensions/{dimension_id}")
async def update_dimension(
    dimension_id: int,
    body: DimensionUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新维度（部分字段），写 OperationLog。"""
    dim = await db.get(EvalDimension, dimension_id)
    if dim is None or dim.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "维度不存在"},
        )

    payload = body.model_dump(exclude_unset=True, mode="json")
    for key, value in payload.items():
        setattr(dim, key, value)
    dim.updated_at = datetime.now(timezone.utc)

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_dimension_update",
        target_type="eval_dimension",
        target_id=dim.id,
        detail=payload,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(dim)
    return success_response(data=_dimension_to_dict(dim))


@router.delete("/dimensions/{dimension_id}")
async def delete_dimension(
    dimension_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """软删维度（置 deleted_at），写 OperationLog。"""
    dim = await db.get(EvalDimension, dimension_id)
    if dim is None or dim.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "维度不存在"},
        )
    dim.deleted_at = datetime.now(timezone.utc)
    dim.updated_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_dimension_delete",
        target_type="eval_dimension",
        target_id=dim.id,
        detail={"name": dim.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": dim.id, "deleted_at": _ts(dim.deleted_at)})


# ---------------------------------------------------------------------------
# Rubric — GET + PUT 整批替换
# ---------------------------------------------------------------------------


@router.get("/dimensions/{dimension_id}/rubrics")
async def list_rubrics(
    dimension_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出该维度的全部 active rubrics（按 level 降序）。"""
    dim = await db.get(EvalDimension, dimension_id)
    if dim is None or dim.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "维度不存在"},
        )
    stmt = (
        select(EvalRubric)
        .where(
            EvalRubric.dimension_id == dimension_id,
            EvalRubric.is_active.is_(True),
        )
        .order_by(EvalRubric.level.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_rubric_to_dict(r) for r in rows])


@router.put("/dimensions/{dimension_id}/rubrics")
async def replace_rubrics(
    dimension_id: int,
    body: RubricBatchUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """整批替换该维度的 rubrics（旧 active 行置 is_active=False，插入新行）。

    spec §9 + plan Phase 4 Task 2：整批替换避免增量编辑的歧义。
    """
    dim = await db.get(EvalDimension, dimension_id)
    if dim is None or dim.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "维度不存在"},
        )

    # 1. 把现有 active 行置 is_active=False
    existing = (
        await db.execute(
            select(EvalRubric).where(
                EvalRubric.dimension_id == dimension_id,
                EvalRubric.is_active.is_(True),
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for r in existing:
        r.is_active = False
        r.updated_at = now

    # 2. 插入新行
    new_ids: list[int] = []
    for item in body.rubrics:
        rubric = EvalRubric(
            dimension_id=dimension_id,
            level=item.level,
            criteria=item.criteria,
            scenario_tag=item.scenario_tag,
            is_active=item.is_active,
        )
        db.add(rubric)
        await db.flush()
        new_ids.append(rubric.id)

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_rubric_update",
        target_type="eval_dimension",
        target_id=dimension_id,
        detail={
            "deactivated_count": len(existing),
            "inserted_count": len(new_ids),
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    # 重新查出新插入的行
    new_rows = (
        await db.execute(
            select(EvalRubric).where(EvalRubric.id.in_(new_ids))
        )
    ).scalars().all()
    return success_response(data=[_rubric_to_dict(r) for r in new_rows])


# ---------------------------------------------------------------------------
# 版本快照（不可编辑）— POST 关联维护三步 + clone + 软删
# ---------------------------------------------------------------------------


async def _resolve_version_config(
    body: VersionCreate, db: AsyncSession
) -> dict:
    """组装 config_payload（spec §4.4 关联维护三步）。

    - source_kol_id 非空：执行三步抠 system_prompt_template
      ① kol_override = resolve_prompt(kol_id, "qianchuan-writer", "system_prompt", db)
      ② None → 读 QianchuanWriterConfig.system_prompt 兜底
      ③ kol_ctx = get_kol_context(db, kol_id)（仅校验存在 + 可被运行时填充占位符）
    - source_kol_id 为空：跳过三步，admin 直接填 config_payload
    - 顶层 scoring_model_id/provider/adapter 合并入 config_payload
    """
    config = dict(body.config_payload or {})

    if body.source_kol_id is not None:
        # ① 关联维护：抠 system_prompt 模板（带占位符，非渲染后文本）
        kol_override = await workspace_prompt.resolve_prompt(
            body.source_kol_id,
            EVAL_TOOL_QIANCHUAN_WRITER,
            "system_prompt",
            db,
        )
        if kol_override:
            system_prompt_template = kol_override
        else:
            # ② cfg.system_prompt 兜底；cfg 不存在用空串
            cfg = (
                await db.execute(
                    select(QianchuanWriterConfig).where(
                        QianchuanWriterConfig.config_key == "default"
                    )
                )
            ).scalar_one_or_none()
            system_prompt_template = (cfg.system_prompt if cfg else "") or ""
        config["system_prompt_template"] = system_prompt_template

        # ③ 校验 kol 存在（不写入 config_payload；占位符运行时由 generator 填）
        # 若不存在会抛 404 HTTPException，由调用方自然返回
        await kol_context.get_kol_context(db, body.source_kol_id)

    # 合并顶层 scoring 三件套（请求体直接传，覆盖 config_payload 已有值）
    if body.scoring_model_id is not None:
        config["scoring_model_id"] = body.scoring_model_id
    if body.scoring_provider is not None:
        config["scoring_provider"] = body.scoring_provider
    if body.scoring_adapter is not None:
        config["scoring_adapter"] = body.scoring_adapter

    return config


@router.get("/versions")
async def list_versions(
    tool_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出全部 active 版本快照（只读 config_payload）。"""
    stmt = select(EvalVersion).where(EvalVersion.deleted_at.is_(None))
    if tool_code:
        stmt = stmt.where(EvalVersion.tool_code == tool_code)
    stmt = stmt.order_by(EvalVersion.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_version_to_dict(v) for v in rows])


@router.post("/versions")
async def create_version(
    body: VersionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建版本快照（spec §4.4 关联维护三步），写 OperationLog。

    版本快照一旦创建即不可编辑（无 PUT 接口），调整配置走 clone 新版本。
    """
    config_payload = await _resolve_version_config(body, db)

    version = EvalVersion(
        tool_code=body.tool_code,
        name=body.name,
        description=body.description,
        config_payload=config_payload,
        parent_version_id=body.parent_version_id,
        source_kol_id=body.source_kol_id,
        auto_run_on_create=body.auto_run_on_create,
        auto_run_tags=list(body.auto_run_tags or []),
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(version)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_version_create",
        target_type="eval_version",
        target_id=version.id,
        detail={
            "name": version.name,
            "tool_code": version.tool_code,
            "source_kol_id": version.source_kol_id,
            "parent_version_id": version.parent_version_id,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(version)
    return success_response(data=_version_to_dict(version))


@router.get("/versions/{version_id}")
async def get_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """版本详情（只读 config_payload）。"""
    version = await db.get(EvalVersion, version_id)
    if version is None or version.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "版本不存在"},
        )
    return success_response(data=_version_to_dict(version))


@router.delete("/versions/{version_id}")
async def delete_version(
    version_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """软删版本快照（置 deleted_at），写 OperationLog。"""
    version = await db.get(EvalVersion, version_id)
    if version is None or version.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "版本不存在"},
        )
    version.deleted_at = datetime.now(timezone.utc)
    version.updated_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_version_delete",
        target_type="eval_version",
        target_id=version.id,
        detail={"name": version.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": version.id, "deleted_at": _ts(version.deleted_at)})


@router.post("/versions/{version_id}/clone")
async def clone_version(
    version_id: int,
    body: VersionClone,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """复制版本（拷贝 config_payload + parent_version_id），写 OperationLog。

    版本快照不可编辑，修改必走 clone（spec §9）。
    config_payload_overrides 可覆盖部分字段（如 system_prompt_template）。
    """
    parent = await db.get(EvalVersion, version_id)
    if parent is None or parent.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "源版本不存在"},
        )

    # 拷贝 config_payload，再应用 overrides
    config_payload = dict(parent.config_payload or {})
    if body.config_payload_overrides:
        config_payload.update(body.config_payload_overrides)

    new_version = EvalVersion(
        tool_code=parent.tool_code,
        name=body.name,
        description=body.description or parent.description,
        config_payload=config_payload,
        parent_version_id=parent.id,
        source_kol_id=parent.source_kol_id,
        auto_run_on_create=body.auto_run_on_create,
        auto_run_tags=list(body.auto_run_tags or []),
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(new_version)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_version_clone",
        target_type="eval_version",
        target_id=new_version.id,
        detail={
            "name": new_version.name,
            "parent_version_id": parent.id,
            "parent_name": parent.name,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(new_version)
    return success_response(data=_version_to_dict(new_version))


# ---------------------------------------------------------------------------
# 调度策略 CRUD（croniter 校验）
# ---------------------------------------------------------------------------


@router.get("/schedule-policies")
async def list_schedule_policies(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出全部 active 调度策略。"""
    stmt = (
        select(EvalSchedulePolicy)
        .where(EvalSchedulePolicy.deleted_at.is_(None))
        .order_by(EvalSchedulePolicy.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return success_response(data=[_schedule_policy_to_dict(p) for p in rows])


@router.post("/schedule-policies")
async def create_schedule_policy(
    body: SchedulePolicyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建调度策略，croniter 校验 cron，写 OperationLog。"""
    _validate_cron(body.cron)

    policy = EvalSchedulePolicy(
        name=body.name,
        cron=body.cron,
        version_id=body.version_id,
        filter_tags=list(body.filter_tags or []),
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(policy)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_schedule_policy_create",
        target_type="eval_schedule_policy",
        target_id=policy.id,
        detail={"name": policy.name, "cron": policy.cron},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(policy)
    return success_response(data=_schedule_policy_to_dict(policy))


@router.put("/schedule-policies/{policy_id}")
async def update_schedule_policy(
    policy_id: int,
    body: SchedulePolicyUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新调度策略（部分字段），croniter 校验 cron，写 OperationLog。"""
    policy = await db.get(EvalSchedulePolicy, policy_id)
    if policy is None or policy.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "调度策略不存在"},
        )

    payload = body.model_dump(exclude_unset=True, mode="json")
    if "cron" in payload and payload["cron"] is not None:
        _validate_cron(payload["cron"])

    for key, value in payload.items():
        setattr(policy, key, value)
    policy.updated_at = datetime.now(timezone.utc)

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_schedule_policy_update",
        target_type="eval_schedule_policy",
        target_id=policy.id,
        detail=payload,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(policy)
    return success_response(data=_schedule_policy_to_dict(policy))


@router.delete("/schedule-policies/{policy_id}")
async def delete_schedule_policy(
    policy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """软删调度策略（置 deleted_at），写 OperationLog。"""
    policy = await db.get(EvalSchedulePolicy, policy_id)
    if policy is None or policy.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "调度策略不存在"},
        )
    policy.deleted_at = datetime.now(timezone.utc)
    policy.updated_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="evaluation_schedule_policy_delete",
        target_type="eval_schedule_policy",
        target_id=policy.id,
        detail={"name": policy.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": policy.id, "deleted_at": _ts(policy.deleted_at)})
