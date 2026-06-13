"""
app/routers/operator_intake.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/operator/intake/links                        — 生成分享链接
  GET  /api/operator/intake/links                        — 自己的链接列表
  GET  /api/operator/intake/submissions                  — 自己链接下的提交列表
  GET  /api/operator/intake/submissions/{id}             — 提交详情（含 messages + ai_report）
  GET  /api/operator/intake/submissions/{id}/download    — 运营下载报告
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.kol_intake import KolIntakeLink, KolIntakeSubmission
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter(prefix="/operator/intake", tags=["operator-intake"])


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """Require operator or admin role with changed password."""
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


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# POST /operator/intake/links
# ---------------------------------------------------------------------------

class CreateLinkRequest(BaseModel):
    kol_name: str | None = None
    expire_hours: int = 168  # 默认 7 天


@router.post("/links")
async def create_link(
    body: CreateLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成一次性分享链接。"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expire_hours)
    link = KolIntakeLink(
        token=token,
        operator_id=current_user.id,
        kol_name=body.kol_name,
        expires_at=expires_at,
    )
    db.add(link)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="create_intake_link",
        target_type="link",
        target_id=link.id,
        detail={"kol_name": body.kol_name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(link)

    return success_response(data={
        "id":         link.id,
        "token":      link.token,
        "kol_name":   link.kol_name,
        "expires_at": _ts(link.expires_at),
        "created_at": _ts(link.created_at),
    })


# ---------------------------------------------------------------------------
# GET /operator/intake/links
# ---------------------------------------------------------------------------

@router.get("/links")
async def list_links(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """自己的链接列表。"""
    links = (await db.execute(
        select(KolIntakeLink)
        .where(KolIntakeLink.operator_id == current_user.id)
        .order_by(KolIntakeLink.created_at.desc())
    )).scalars().all()

    return success_response(data=[
        {
            "id":           lnk.id,
            "token":        lnk.token,
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
# GET /operator/intake/submissions
# ---------------------------------------------------------------------------

@router.get("/submissions")
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """自己链接下的提交列表（摘要，不含 messages）。"""
    rows = (await db.execute(
        select(KolIntakeSubmission, KolIntakeLink)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeLink.operator_id == current_user.id)
        .order_by(KolIntakeSubmission.created_at.desc())
    )).all()

    return success_response(data=[
        {
            "id":                  sub.id,
            "link_id":             sub.link_id,
            "kol_name":            lnk.kol_name,
            "report_status":       sub.report_status,
            "report_generated_at": _ts(sub.report_generated_at),
            "kol_downloaded_at":   _ts(sub.kol_downloaded_at),
            "created_at":          _ts(sub.created_at),
        }
        for sub, lnk in rows
    ])


# ---------------------------------------------------------------------------
# GET /operator/intake/submissions/{id}
# ---------------------------------------------------------------------------

@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提交详情（含 messages + ai_report）。"""
    row = (await db.execute(
        select(KolIntakeSubmission, KolIntakeLink)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeSubmission.id == submission_id)
        .where(KolIntakeLink.operator_id == current_user.id)
    )).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "提交记录不存在"},
        )

    sub, lnk = row
    return success_response(data={
        "id":                  sub.id,
        "link_id":             sub.link_id,
        "kol_name":            lnk.kol_name,
        "messages":            sub.messages,
        "ai_report":           sub.ai_report,
        "report_status":       sub.report_status,
        "report_generated_at": _ts(sub.report_generated_at),
        "kol_downloaded_at":   _ts(sub.kol_downloaded_at),
        "created_at":          _ts(sub.created_at),
    })


# ---------------------------------------------------------------------------
# GET /operator/intake/submissions/{id}/download
# ---------------------------------------------------------------------------

@router.get("/submissions/{submission_id}/download")
async def operator_download(
    submission_id: int,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    运营下载报告。
    前置条件：链接已过期 OR 博主已下载，否则返回 403。
    """
    row = (await db.execute(
        select(KolIntakeSubmission, KolIntakeLink)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeSubmission.id == submission_id)
        .where(KolIntakeLink.operator_id == current_user.id)
    )).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "提交记录不存在"},
        )

    sub, lnk = row

    if sub.report_status != "ready":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告尚未生成"},
        )

    # 运营下载条件：链接已过期 OR 博主已下载
    now = datetime.now(timezone.utc)
    if not (lnk.expires_at < now or sub.kol_downloaded_at is not None):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "博主尚未下载报告且链接未过期，暂不可下载"},
        )

    file_path = sub.docx_path if format == "docx" else sub.pdf_path
    abs_path = os.path.abspath(file_path) if file_path else None
    if not abs_path or not os.path.exists(abs_path):
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告文件不存在"},
        )

    # 写入首次运营下载时间
    if sub.operator_downloaded_at is None:
        await db.execute(
            update(KolIntakeSubmission)
            .where(KolIntakeSubmission.id == sub.id)
            .values(operator_downloaded_at=datetime.now(timezone.utc))
        )
        await db.commit()

    suffix = "docx" if format == "docx" else "pdf"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if format == "docx"
        else "application/pdf"
    )
    return FileResponse(
        path=abs_path,
        media_type=media_type,
        filename=f"MCN红人入驻评估报告.{suffix}",
    )
