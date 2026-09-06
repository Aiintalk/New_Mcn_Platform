"""内容分析智能体的管理员配置与受控运行接口。"""
from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import DateTime, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.agent_task_config import AgentTaskConfig
from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.log import OperationLog
from app.models.task import TaskJob, TaskLog
from app.models.user import User
from app.services.agent_task_config_service import (
    AGENT_CODE,
    TOOL_CODE_DAILY,
    TOOL_CODE_WEEKLY,
    converge_overdue_tasks,
    get_project_input_status,
    is_project_eligible,
    validate_selected_project_ids,
)
from app.services.agent_task_execution_contract import (
    ContentAnalysisExecutor,
    get_registered_content_analysis_executor,
    is_valid_content_analysis_executor,
)
from app.services.agent_task_execution_service import (
    _is_delivery_only_retry,
    list_weekly_account_candidates,
    normalize_report_root_ref,
    retry_failed_execution,
    run_test_execution,
)


router = APIRouter(prefix="/admin/agent-tasks/content-analysis", tags=["admin-agent-tasks"])
_TOOL_CODES = {"daily": TOOL_CODE_DAILY, "weekly": TOOL_CODE_WEEKLY}
_TASK_NAMES = {
    "daily": "每日项目对标内容分析",
    "weekly": "账号人设内容基准更新",
}
_DELIVERY_TARGET = "feishu_document"
_SHANGHAI = timezone(timedelta(hours=8))


class ConfigRequest(BaseModel):
    selected_project_ids: list[int] = Field(default_factory=list)
    report_root_ref: str | None = None

    @field_validator("report_root_ref")
    @classmethod
    def normalize_report_root(cls, value: str | None) -> str | None:
        return normalize_report_root_ref(value)


class TestRunRequest(BaseModel):
    task_code: str
    project_id: int | None = None
    account_key: str | None = None
    request_id: str = Field(default_factory=lambda: uuid4().hex)

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("request_id 必须为 1 至 128 个非空字符")
        return normalized

    @model_validator(mode="after")
    def validate_execution_object(self):
        daily = self.task_code == "daily" and isinstance(self.project_id, int) and self.account_key is None
        weekly = self.task_code == "weekly" and self.project_id is None and bool(self.account_key and self.account_key.strip())
        if not (daily or weekly):
            raise ValueError("测试执行对象必须与任务类型匹配")
        return self


class RetryRunRequest(BaseModel):
    request_id: str

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("request_id 必须为 1 至 128 个非空字符")
        return normalized


def get_content_analysis_executor() -> ContentAnalysisExecutor | None:
    return get_registered_content_analysis_executor()


def _executor_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "code": "SERVICE_UNAVAILABLE",
            "message": "内容分析执行器尚未注册或不符合合同",
            "data": None,
        },
    )


def _ts(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _public_status(status: str) -> str:
    return {"pending": "queued", "processing": "running"}.get(status, status)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _project_data(project: Kol | None) -> dict | None:
    if project is None:
        return None
    return {
        "id": project.id,
        "name": project.name,
        "kol_name": project.name,
        "account_name": project.account_name,
    }


def _next_fixed_runs() -> dict[str, str]:
    now = datetime.now(timezone.utc).astimezone(_SHANGHAI)
    daily = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    days_to_monday = (7 - now.weekday()) % 7
    weekly = (now + timedelta(days=days_to_monday)).replace(hour=1, minute=0, second=0, microsecond=0)
    if weekly <= now:
        weekly += timedelta(days=7)
    return {"daily": daily.isoformat(), "weekly": weekly.isoformat()}


async def _selection(db: AsyncSession) -> list[int]:
    config = (await db.execute(
        select(AgentTaskConfig).where(AgentTaskConfig.agent_code == AGENT_CODE)
    )).scalar_one_or_none()
    return list(config.selected_project_ids or []) if config else []


async def _eligible_projects_with_benchmarks(db: AsyncSession) -> tuple[list[Kol], dict[int, list[KolBenchmark]]]:
    projects = (await db.execute(select(Kol).where(Kol.deleted_at.is_(None)))).scalars().all()
    eligible = [project for project in projects if is_project_eligible(project)]
    if not eligible:
        return [], {}
    ids = [project.id for project in eligible]
    benchmarks = (await db.execute(
        select(KolBenchmark).where(KolBenchmark.kol_id.in_(ids))
    )).scalars().all()
    by_project = {project.id: [] for project in eligible}
    for benchmark in benchmarks:
        by_project[benchmark.kol_id].append(benchmark)
    return eligible, by_project


def _project_scope(project: Kol, benchmarks: list[KolBenchmark], selected: bool) -> dict:
    input_status = get_project_input_status(project, benchmarks)
    content_benchmarks = [item for item in benchmarks if item.account_type == "content"]
    valid_count = sum(bool(item.sec_uid and item.sec_uid.strip()) for item in content_benchmarks)
    if not content_benchmarks:
        relation_status = "missing"
    elif valid_count == len(content_benchmarks):
        relation_status = "ready"
    else:
        relation_status = "partial_missing"
    if not selected:
        scope_status = "unselected"
    elif input_status["ready"]:
        scope_status = "selected_ready"
    else:
        scope_status = "selected_missing"
    return {
        "project_id": project.id,
        "project_name": project.name,
        "project": _project_data(project),
        "selected": selected,
        "scope_status": scope_status,
        "missing_required": input_status["required_missing_reasons"],
        "optional_context_missing": input_status["input_limited_reasons"],
        "content_benchmark_total": len(content_benchmarks),
        "content_benchmark_valid_count": valid_count,
        "content_benchmark_relation_status": relation_status,
        "content_data_status": "ready",
        "project_context_status": "complete" if not input_status["input_limited"] else "partial_missing",
        "updated_at": _ts(project.updated_at),
    }


def _module(
    key: str,
    label: str,
    *,
    required: bool,
    status: str,
    source: str,
    updated_at: datetime | None,
    value,
    missing_reason: str | None = None,
    missing_reasons: list[str] | None = None,
) -> dict:
    return {
        "key": key,
        "label": label,
        "required": required,
        "status": status,
        "source": source,
        "updated_at": _ts(updated_at),
        "value": value,
        "missing_reason": missing_reason,
        "missing_reasons": missing_reasons or [],
    }


def _input_modules(project: Kol, benchmarks: list[KolBenchmark]) -> list[dict]:
    input_status = get_project_input_status(project, benchmarks)
    content_benchmarks = [
        {"id": item.id, "account_name": item.account_name, "sec_uid": item.sec_uid}
        for item in benchmarks if item.account_type == "content"
    ]
    benchmark_updated = max((item.updated_at for item in benchmarks if item.account_type == "content"), default=None)
    optional_values = {
        key: getattr(project, key)
        for key in ("background", "experience", "relationships", "unique_story", "extra_notes", "style_notes")
        if getattr(project, key, None)
    }
    optional_reason = (
        "optional_context_missing" if input_status["input_limited"] else None
    )
    return [
        _module("project", "项目基础信息", required=True, status="ready", source="kols", updated_at=project.updated_at,
                value={"id": project.id, "name": project.name, "account_name": project.account_name}),
        _module("persona", "人格", required=True, status="ready", source="kols.persona", updated_at=project.updated_at,
                value=project.persona),
        _module("content_plan", "内容规划", required=True, status="ready", source="kols.content_plan", updated_at=project.updated_at,
                value=project.content_plan),
        _module("content_benchmarks", "内容对标账号", required=True,
                status="ready" if input_status["ready"] else "missing", source="kol_benchmarks", updated_at=benchmark_updated,
                value=content_benchmarks,
                missing_reason=None if input_status["ready"] else "CONTENT_BENCHMARK_SEC_UID_MISSING"),
        _module("optional_context", "其他非必需上下文", required=False,
                status="missing" if input_status["input_limited"] else "ready", source="kols", updated_at=project.updated_at,
                value=optional_values, missing_reason=optional_reason,
                missing_reasons=input_status["input_limited_reasons"]),
        _module("content_data", "内容数据", required=False, status="ready", source="feishu_bitable_runtime", updated_at=None,
                value={"validation": "runtime_required"}),
        _module("historical_analysis", "历史分析", required=False, status="ready", source="content_analysis_results/outputs", updated_at=None,
                value=None),
        _module("formal_result_target", "正式结果位置", required=False, status="ready", source="feishu_document", updated_at=None,
                value={"internal": "content_analysis_results/outputs", "delivery": "feishu_document"}),
    ]


def _task_code(task: TaskJob) -> str | None:
    return (task.input_payload or {}).get("task_code") or next(
        (code for code, tool_code in _TOOL_CODES.items() if task.tool_code == tool_code), None
    )


def _task_data(
    task: TaskJob,
    *,
    include_logs: list[TaskLog] | None = None,
    project: Kol | None = None,
    retried_by_task_ids: list[int] | None = None,
) -> dict:
    payload = task.input_payload or {}
    summary = task.result_summary or {}
    execution = deepcopy(payload.get("execution") or {})
    if not execution and isinstance(payload.get("project_id"), int):
        execution = {"object_type": "project", "project_id": payload["project_id"]}
    public_execution = _public_execution(execution)
    public_summary = deepcopy(summary)
    if isinstance(public_summary.get("execution"), dict):
        public_summary["execution"] = _public_execution(public_summary["execution"])
    running = task.status == "processing"
    elapsed_ms = None
    if running and task.started_at is not None:
        elapsed_ms = max(0, int((datetime.now(timezone.utc) - _utc(task.started_at)).total_seconds() * 1000))
    task_name = (
        "周批次收尾"
        if execution.get("object_type") == "weekly_batch_finalize"
        else _TASK_NAMES.get(_task_code(task), "内容分析")
    )
    data = {
        "id": task.id,
        "task_no": task.task_no,
        "agent_code": payload.get("agent_code", AGENT_CODE),
        "task_code": _task_code(task),
        "task": {"code": _task_code(task), "name": task_name},
        "project_id": payload.get("project_id") or execution.get("project_id"),
        "project": _project_data(project),
        "execution": public_execution,
        "run_type": payload.get("run_type"),
        "business_date": payload.get("business_date"),
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "status": _public_status(task.status),
        "triggered_at": payload.get("triggered_at"),
        "deadline_at": payload.get("deadline_at"),
        "started_at": _ts(task.started_at),
        "finished_at": _ts(task.finished_at),
        "duration_ms": task.duration_ms,
        "elapsed_ms": elapsed_ms,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "reason_code": summary.get("reason_code") or task.error_code,
        "required_missing_reasons": summary.get("required_missing_reasons", []),
        "input_limited": bool(summary.get("input_limited")),
        "controlled_test": bool(summary.get("controlled_test")),
        "input_limited_reasons": summary.get("input_limited_reasons", []),
        "delivery_target": summary.get("delivery_target", _DELIVERY_TARGET),
        "delivery_status": (summary.get("delivery") or {}).get("status", "skipped"),
        "result_status": (summary.get("internal_result") or {}).get("status", "skipped"),
        "retry_of_task_id": payload.get("retry_of_task_id") or (payload.get("retry") or {}).get("retry_of_task_id"),
        "retried_by_task_ids": retried_by_task_ids or [],
        "failure_stage": summary.get("failure_stage"),
        "database_precheck": summary.get("database_precheck"),
        "feishu_relation": summary.get("feishu_relation"),
        "internal_result": summary.get("internal_result"),
        "delivery": summary.get("delivery"),
    }
    if include_logs is not None:
        input_snapshot = deepcopy(payload)
        delivery_target = input_snapshot.get("delivery_target")
        if isinstance(delivery_target, dict):
            delivery_target["report_root_ref_configured"] = bool(delivery_target.pop("report_root_ref", None))
        snapshot_execution = input_snapshot.get("execution")
        if isinstance(snapshot_execution, dict) and isinstance(snapshot_execution.get("account_key"), str):
            snapshot_execution["account_key_hash"] = hashlib.sha256(
                snapshot_execution.pop("account_key").encode("utf-8")
            ).hexdigest()[:16]
        if isinstance(input_snapshot.get("account_key"), str):
            input_snapshot["account_key_hash"] = hashlib.sha256(
                input_snapshot.pop("account_key").encode("utf-8")
            ).hexdigest()[:16]
        data.update({
            "input_snapshot": input_snapshot,
            "controlled_result_summary": public_summary,
            "logs": [{
                "id": log.id, "step_code": log.step_code, "step_name": log.step_name,
                "status": _public_status(log.status), "message": log.message,
                "created_at": _ts(log.created_at),
            } for log in include_logs],
        })
    return data


def _public_execution(execution: dict) -> dict:
    public = deepcopy(execution)
    account_key = public.pop("account_key", None)
    if isinstance(account_key, str):
        public["account_key_hash"] = hashlib.sha256(account_key.encode("utf-8")).hexdigest()[:16]
    return public


def _pagination(items: list, page: int, page_size: int) -> tuple[list, dict]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = len(items)
    return items[(page - 1) * page_size: page * page_size], {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    projects, benchmarks = await _eligible_projects_with_benchmarks(db)
    selected_ids = set(await _selection(db))
    scopes = [_project_scope(project, benchmarks[project.id], project.id in selected_ids) for project in projects]
    counts = {status: sum(item["scope_status"] == status for item in scopes) for status in (
        "selected_ready", "selected_missing", "unselected"
    )}
    config = (await db.execute(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == AGENT_CODE
    ))).scalar_one_or_none()
    updated_by_name = None
    if config and config.updated_by:
        updated_by_name = (await db.execute(select(User.username).where(User.id == config.updated_by))).scalar_one_or_none()
    payload = TaskJob.input_payload
    base_conditions = [
        TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())),
        payload["agent_code"].astext == AGENT_CODE,
    ]
    next_runs = _next_fixed_runs()
    task_items = []
    for task_code, tool_code in _TOOL_CODES.items():
        latest = (await db.execute(
            select(TaskJob).where(*base_conditions, TaskJob.tool_code == tool_code,
                                  payload["run_type"].astext == "auto")
            .order_by(TaskJob.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        task_items.append({
            "task_code": task_code,
            "name": _TASK_NAMES[task_code],
            "schedule": "每日 00:00" if task_code == "daily" else "每周一 01:00",
            "window_days": 3 if task_code == "daily" else 30,
            "latest_formal_run": _task_data(latest) if latest else None,
            "next_fixed_run": next_runs[task_code],
        })
    today = datetime.now(timezone.utc).astimezone(_SHANGHAI).date().isoformat()
    recent_failed = datetime.now(timezone.utc) - timedelta(days=7)
    status_summary = {
        "today_completed": (await db.execute(select(func.count()).select_from(TaskJob).where(
            *base_conditions, TaskJob.status == "success", payload["business_date"].astext == today
        ))).scalar_one(),
        "current_running": (await db.execute(select(func.count()).select_from(TaskJob).where(
            *base_conditions, TaskJob.status == "processing"
        ))).scalar_one(),
        "failed_last_7_days": (await db.execute(select(func.count()).select_from(TaskJob).where(
            *base_conditions, TaskJob.status == "failed", TaskJob.finished_at >= recent_failed
        ))).scalar_one(),
    }
    report_root_ref = normalize_report_root_ref(config.report_root_ref if config else None)
    return success_response(data={
        "agent_code": AGENT_CODE,
        "agent_name": "内容分析",
        "selected_project_count": sum(project.id in selected_ids for project in projects),
        "scope_counts": counts,
        "tasks": task_items,
        "config_updated_by": config.updated_by if config else None,
        "config_updated_by_name": updated_by_name,
        "config_updated_at": _ts(config.updated_at) if config else None,
        "report_root_ref": report_root_ref,
        "report_root_ref_configured": report_root_ref is not None,
        "status_summary": status_summary,
        "delivery_target": _DELIVERY_TARGET,
    })


@router.get("/projects")
async def list_projects(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    scope_status: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    projects, benchmarks = await _eligible_projects_with_benchmarks(db)
    selected_ids = set(await _selection(db))
    items = [_project_scope(project, benchmarks[project.id], project.id in selected_ids) for project in projects]
    if keyword:
        lowered = keyword.lower()
        items = [item for item in items if lowered in item["project_name"].lower()]
    if scope_status in {"selected_ready", "selected_missing", "unselected"}:
        items = [item for item in items if item["scope_status"] == scope_status]
    items.sort(key=lambda item: item["project_id"])
    rows, pagination = _pagination(items, page, page_size)
    return success_response(data={"items": rows, "pagination": pagination})


@router.get("/projects/{project_id}/input")
async def get_project_input(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    project = (await db.execute(select(Kol).where(Kol.id == project_id))).scalar_one_or_none()
    if project is None or not is_project_eligible(project):
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在或未完成入驻")
    benchmarks = (await db.execute(
        select(KolBenchmark).where(KolBenchmark.kol_id == project_id)
    )).scalars().all()
    return success_response(data={
        "project_id": project.id,
        "project_name": project.name,
        "modules": _input_modules(project, benchmarks),
        "delivery_target": _DELIVERY_TARGET,
    })


@router.get("/weekly-accounts")
async def list_weekly_accounts(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    candidate_project_ids = [project_id] if project_id is not None else None
    items = await list_weekly_account_candidates(db, project_ids=candidate_project_ids)
    if keyword:
        lowered = keyword.lower()
        items = [item for item in items if (
            lowered in item["account_key"].lower()
            or lowered in (item.get("account_name") or "").lower()
        )]
    rows, pagination = _pagination(items, page, page_size)
    return success_response(data={"items": rows, "pagination": pagination})


@router.put("/config")
async def update_config(
    body: ConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        project_ids = await validate_selected_project_ids(db, body.selected_project_ids)
    except ValueError:
        return error_response(ErrorCode.VALIDATION_ERROR, "项目不存在、已删除或未完成入驻")
    existing = await db.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == AGENT_CODE,
    ))
    report_root_ref = normalize_report_root_ref(
        body.report_root_ref
        if "report_root_ref" in body.model_fields_set
        else (existing.report_root_ref if existing else None)
    )
    updated_at = datetime.now(timezone.utc)
    result = await db.execute(
        pg_insert(AgentTaskConfig)
        .values(
            agent_code=AGENT_CODE,
            selected_project_ids=project_ids,
            report_root_ref=report_root_ref,
            updated_by=current_user.id,
            updated_at=updated_at,
        )
        .on_conflict_do_update(
            index_elements=[AgentTaskConfig.agent_code],
            set_={
                "selected_project_ids": project_ids,
                "report_root_ref": report_root_ref,
                "updated_by": current_user.id,
                "updated_at": updated_at,
            },
        )
        .returning(AgentTaskConfig)
    )
    config = result.scalar_one()
    db.add(OperationLog(
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        action="update_agent_task_config", target_type="agent_task_config", target_id=None,
        detail={
            "agent_code": AGENT_CODE,
            "project_ids": project_ids,
            "report_root_ref_configured": bool(report_root_ref),
        }, ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(config)
    return success_response(data={
        "agent_code": AGENT_CODE,
        "selected_project_ids": project_ids,
        "report_root_ref": config.report_root_ref,
        "updated_by": config.updated_by,
        "updated_by_name": current_user.username,
        "updated_at": _ts(config.updated_at),
    })


@router.get("/runs")
async def list_runs(
    page: int = 1,
    page_size: int = 20,
    task_code: str = "",
    status: str = "",
    project_id: int | None = None,
    account_key: str = "",
    run_type: str = "",
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if await converge_overdue_tasks(db):
        await db.commit()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    payload = TaskJob.input_payload
    conditions = [TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())), payload["agent_code"].astext == AGENT_CODE]
    if task_code in _TOOL_CODES:
        conditions.append(payload["task_code"].astext == task_code)
    if status:
        conditions.append(TaskJob.status == {"queued": "pending", "running": "processing"}.get(status, status))
    if project_id is not None:
        conditions.append(or_(
            payload["project_id"].astext == str(project_id),
            payload["execution"]["project_id"].astext == str(project_id),
            payload["execution"]["project_ids"].contains([project_id]),
        ))
    if account_key:
        conditions.append(payload["execution"]["account_key"].astext == account_key.strip())
    if run_type:
        conditions.append(payload["run_type"].astext == run_type)
    triggered_at = cast(payload["triggered_at"].astext, DateTime(timezone=True))
    if started_from is not None:
        conditions.append(triggered_at >= _utc(started_from))
    if started_to is not None:
        conditions.append(triggered_at <= _utc(started_to))
    total = (await db.execute(select(func.count()).select_from(TaskJob).where(*conditions))).scalar_one()
    tasks = (await db.execute(
        select(TaskJob).where(*conditions).order_by(TaskJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    project_ids = {
        (task.input_payload or {}).get("project_id")
        or ((task.input_payload or {}).get("execution") or {}).get("project_id")
        for task in tasks
        if isinstance(task.input_payload, dict)
    }
    project_ids.discard(None)
    projects = (await db.execute(select(Kol).where(Kol.id.in_(project_ids)))).scalars().all() if project_ids else []
    projects_by_id = {project.id: project for project in projects}
    return success_response(data={
        "items": [_task_data(task, project=projects_by_id.get((task.input_payload or {}).get("project_id"))) for task in tasks],
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": math.ceil(total / page_size) if total else 0},
    })


@router.get("/runs/{run_id}")
async def get_run_detail(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if await converge_overdue_tasks(db):
        await db.commit()
    task = (await db.execute(
        select(TaskJob).where(TaskJob.id == run_id, TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())),
                              TaskJob.input_payload["agent_code"].astext == AGENT_CODE)
    )).scalar_one_or_none()
    if task is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "内容分析运行记录不存在")
    project_id = (task.input_payload or {}).get("project_id") or ((task.input_payload or {}).get("execution") or {}).get("project_id")
    project = (await db.execute(select(Kol).where(Kol.id == project_id))).scalar_one_or_none() if isinstance(project_id, int) else None
    logs = (await db.execute(
        select(TaskLog).where(TaskLog.task_id == task.id).order_by(TaskLog.created_at.asc(), TaskLog.id.asc())
    )).scalars().all()
    retried_by_task_ids = (await db.execute(select(TaskJob.id).where(
        TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())),
        TaskJob.input_payload["agent_code"].astext == AGENT_CODE,
        or_(
            TaskJob.input_payload["retry_of_task_id"].astext == str(task.id),
            TaskJob.input_payload["retry"]["retry_of_task_id"].astext == str(task.id),
        ),
    ).order_by(TaskJob.id.asc()))).scalars().all()
    return success_response(data=_task_data(task, include_logs=logs, project=project, retried_by_task_ids=retried_by_task_ids))


@router.post("/test-runs")
async def create_controlled_test_run(
    body: TestRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    executor: ContentAnalysisExecutor | None = Depends(get_content_analysis_executor),
):
    if body.task_code not in _TOOL_CODES:
        return error_response(ErrorCode.VALIDATION_ERROR, "task_code 仅支持 daily 或 weekly")
    if not is_valid_content_analysis_executor(executor):
        return _executor_unavailable_response()
    operation_log = OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="create_agent_task_test_run",
        target_type="task_job",
        target_id=None,
        detail={
            "agent_code": AGENT_CODE,
            "project_id": body.project_id,
            "task_code": body.task_code,
            "execution_type": "project" if body.task_code == "daily" else "account",
            "request_id_present": True,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    try:
        task = await run_test_execution(
            db,
            executor=executor,
            task_code=body.task_code,
            project_id=body.project_id,
            account_key=body.account_key,
            created_by=current_user.id,
            request_id=body.request_id,
            triggered_at=datetime.now(timezone.utc),
            operation_log=operation_log,
        )
    except ValueError as exc:
        return error_response(ErrorCode.VALIDATION_ERROR, str(exc))
    project = (await db.execute(select(Kol).where(Kol.id == body.project_id))).scalar_one_or_none() if isinstance(body.project_id, int) else None
    return success_response(data=_task_data(task, project=project))


@router.post("/runs/{run_id}/retry")
async def retry_run(
    run_id: int,
    request: Request,
    body: RetryRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    executor: ContentAnalysisExecutor | None = Depends(get_content_analysis_executor),
):
    original = (await db.execute(select(TaskJob).where(TaskJob.id == run_id))).scalar_one_or_none()
    if (original is None or original.tool_code not in _TOOL_CODES.values()
            or (original.input_payload or {}).get("agent_code") != AGENT_CODE):
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "内容分析运行记录不存在")
    try:
        if not is_valid_content_analysis_executor(executor):
            return _executor_unavailable_response()
        if body is None:
            return error_response(ErrorCode.VALIDATION_ERROR, "request_id 必填")
        operation_log = OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="retry_agent_task_run",
            target_type="task_job",
            target_id=None,
            detail={
                "agent_code": AGENT_CODE,
                "execution_type": ((original.input_payload or {}).get("execution") or {}).get("object_type", "project"),
                "retry_of_task_id": run_id,
                "retry_mode": "delivery_only"
                if _is_delivery_only_retry(original.result_summary)
                else "full",
                "request_id_present": True,
            },
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        task = await retry_failed_execution(
            db,
            executor=executor,
            task_id=run_id,
            created_by=current_user.id,
            request_id=body.request_id,
            triggered_at=datetime.now(timezone.utc),
            operation_log=operation_log,
        )
    except ValueError as exc:
        return error_response(ErrorCode.VALIDATION_ERROR, str(exc))
    project_id = (task.input_payload or {}).get("project_id") or ((task.input_payload or {}).get("execution") or {}).get("project_id")
    project = (await db.execute(select(Kol).where(Kol.id == project_id))).scalar_one_or_none() if isinstance(project_id, int) else None
    return success_response(data=_task_data(task, project=project))
