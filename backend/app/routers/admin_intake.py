"""
app/routers/admin_intake.py

管理员接口：
  GET    /api/admin/intake/questions              — 题目列表
  POST   /api/admin/intake/questions              — 新增题目
  PATCH  /api/admin/intake/questions/{id}         — 编辑题目
  DELETE /api/admin/intake/questions/{id}         — 删除题目
  PUT    /api/admin/intake/questions/reorder      — 批量更新排序
  GET    /api/admin/intake/configs                — AI 配置列表
  PUT    /api/admin/intake/configs/{key}          — 更新 AI 配置
  GET    /api/admin/intake/links                  — 全部链接（含运营信息）
  GET    /api/admin/intake/submissions            — 全部提交
  GET    /api/admin/intake/submissions/{id}       — 提交详情
  POST   /api/admin/intake/submissions/{id}/regenerate — 重新生成报告
"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeLink, KolIntakeQuestion, KolIntakeSubmission,
)
from app.models.user import User

router = APIRouter(prefix="/admin/intake", tags=["admin-intake"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# Questions CRUD
# ---------------------------------------------------------------------------

class QuestionIn(BaseModel):
    order_num: int
    category: str
    question_text: str
    question_type: str = "text"
    max_items: int | None = None
    is_required: bool = True
    is_active: bool = True


@router.get("/questions")
async def list_questions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    questions = (await db.execute(
        select(KolIntakeQuestion).order_by(KolIntakeQuestion.order_num)
    )).scalars().all()

    return success_response(data=[
        {
            "id":            q.id,
            "order_num":     q.order_num,
            "category":      q.category,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "max_items":     q.max_items,
            "is_required":   q.is_required,
            "is_active":     q.is_active,
            "created_at":    _ts(q.created_at),
            "updated_at":    _ts(q.updated_at),
        }
        for q in questions
    ])


@router.post("/questions")
async def create_question(
    body: QuestionIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = KolIntakeQuestion(**body.model_dump())
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return success_response(data={"id": q.id})


class ReorderItem(BaseModel):
    id: int
    order_num: int


@router.put("/questions/reorder")
async def reorder_questions(
    body: list[ReorderItem],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """批量更新题目排序。"""
    now = datetime.now(timezone.utc)
    for item in body:
        await db.execute(
            update(KolIntakeQuestion)
            .where(KolIntakeQuestion.id == item.id)
            .values(order_num=item.order_num, updated_at=now)
        )
    await db.commit()
    return success_response(data=None)


@router.patch("/questions/{question_id}")
async def update_question(
    question_id: int,
    body: QuestionIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        update(KolIntakeQuestion)
        .where(KolIntakeQuestion.id == question_id)
        .values(**body.model_dump(), updated_at=datetime.now(timezone.utc))
        .returning(KolIntakeQuestion.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "题目不存在"},
        )
    await db.commit()
    return success_response(data={"id": question_id})


@router.delete("/questions/{question_id}")
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        delete(KolIntakeQuestion)
        .where(KolIntakeQuestion.id == question_id)
        .returning(KolIntakeQuestion.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "题目不存在"},
        )
    await db.commit()
    return success_response(data=None)


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------

class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(KolIntakeConfig))).scalars().all()
    return success_response(data=[
        {
            "id":            c.id,
            "config_key":    c.config_key,
            "ai_model_id":   c.ai_model_id,
            "system_prompt": c.system_prompt,
            "is_active":     c.is_active,
            "updated_at":    _ts(c.updated_at),
        }
        for c in configs
    ])


@router.put("/configs/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        update(KolIntakeConfig)
        .where(KolIntakeConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(KolIntakeConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    await db.commit()
    return success_response(data={"config_key": config_key})


# ---------------------------------------------------------------------------
# All links
# ---------------------------------------------------------------------------

@router.get("/links")
async def list_all_links(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """全部链接（含运营信息）。"""
    links = (await db.execute(
        select(KolIntakeLink).order_by(KolIntakeLink.created_at.desc())
    )).scalars().all()

    return success_response(data=[
        {
            "id":           lnk.id,
            "token":        lnk.token,
            "operator_id":  lnk.operator_id,
            "kol_name":     lnk.kol_name,
            "expires_at":   _ts(lnk.expires_at),
            "used_at":      _ts(lnk.used_at),
            "submitted_at": _ts(lnk.submitted_at),
            "is_active":    lnk.is_active,
            "created_at":   _ts(lnk.created_at),
        }
        for lnk in links
    ])


# ---------------------------------------------------------------------------
# All submissions
# ---------------------------------------------------------------------------

@router.get("/submissions")
async def list_all_submissions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = (await db.execute(
        select(KolIntakeSubmission, KolIntakeLink)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .order_by(KolIntakeSubmission.created_at.desc())
    )).all()

    return success_response(data=[
        {
            "id":                     sub.id,
            "link_id":                sub.link_id,
            "operator_id":            lnk.operator_id,
            "kol_name":               lnk.kol_name,
            "report_status":          sub.report_status,
            "report_generated_at":    _ts(sub.report_generated_at),
            "kol_downloaded_at":      _ts(sub.kol_downloaded_at),
            "operator_downloaded_at": _ts(sub.operator_downloaded_at),
            "created_at":             _ts(sub.created_at),
        }
        for sub, lnk in rows
    ])


@router.get("/submissions/{submission_id}")
async def get_submission_detail(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = (await db.execute(
        select(KolIntakeSubmission, KolIntakeLink)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeSubmission.id == submission_id)
    )).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "提交记录不存在"},
        )

    sub, lnk = row
    return success_response(data={
        "id":                     sub.id,
        "link_id":                sub.link_id,
        "operator_id":            lnk.operator_id,
        "kol_name":               lnk.kol_name,
        "messages":               sub.messages,
        "ai_report":              sub.ai_report,
        "ai_report_raw":          sub.ai_report_raw,
        "report_status":          sub.report_status,
        "report_generated_at":    _ts(sub.report_generated_at),
        "kol_downloaded_at":      _ts(sub.kol_downloaded_at),
        "operator_downloaded_at": _ts(sub.operator_downloaded_at),
        "created_at":             _ts(sub.created_at),
    })


# ---------------------------------------------------------------------------
# Regenerate report
# ---------------------------------------------------------------------------

@router.post("/submissions/{submission_id}/regenerate")
async def regenerate_report(
    submission_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """重新生成报告：重置状态为 pending，异步触发生成。"""
    from app.routers.intake_public import generate_intake_report

    sub = (await db.execute(
        select(KolIntakeSubmission).where(KolIntakeSubmission.id == submission_id)
    )).scalar_one_or_none()

    if sub is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "提交记录不存在"},
        )

    await db.execute(
        update(KolIntakeSubmission)
        .where(KolIntakeSubmission.id == submission_id)
        .values(report_status="pending", ai_report=None, ai_report_raw=None)
    )
    await db.commit()

    background_tasks.add_task(generate_intake_report, submission_id)
    return success_response(data={"report_status": "generating"})
