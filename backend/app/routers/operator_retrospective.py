"""
app/routers/operator_retrospective.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  GET    /api/operator/workspace/{kol_id}/retrospective              — 分页列表
  POST   /api/operator/workspace/{kol_id}/retrospective              — 新建/更新（upsert by id）
  DELETE /api/operator/workspace/{kol_id}/retrospective/{id}         — 物理删除
  POST   /api/operator/workspace/{kol_id}/retrospective/parse-files  — 文件解析
  POST   /api/operator/workspace/{kol_id}/retrospective/{id}/analyze — 流式生成复盘报告
  GET    /api/operator/workspace/{kol_id}/retrospective/{id}/export-word — 导出 Word
"""
import json
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.retrospective import RetrospectiveConfig, RetrospectiveSession
from app.models.user import User
from app.services import document_parser
from app.services.word_export import markdown_to_docx_bytes

router = APIRouter(prefix="/operator/workspace", tags=["operator-retrospective"])

_PAGE_SIZE_ALLOWED = {10, 20, 50}

_DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的 MCN 复盘分析师。"
    "请根据以下达人的材料（直播数据、素材数据、评价文字、直播脚本、素材脚本），"
    "生成一份详尽的复盘报告，包含数据分析、问题归因、改进建议三部分。"
)


# ---------------------------------------------------------------------------
# 鉴权
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


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _session_to_dict(s: RetrospectiveSession) -> dict:
    return {
        "id": s.id,
        "kol_id": s.kol_id,
        "created_by": s.created_by,
        "title": s.title,
        "status": s.status,
        "live_data": s.live_data,
        "material_data": s.material_data,
        "review_text": s.review_text,
        "live_script": s.live_script,
        "material_scripts": s.material_scripts,
        "result": s.result,
        "created_at": _ts(s.created_at),
        "updated_at": _ts(s.updated_at),
    }


async def _resolve_model_id(config: RetrospectiveConfig | None, db: AsyncSession) -> str:
    default_model = "claude-sonnet-4-6"
    if config is None or config.ai_model_id is None:
        return default_model
    from sqlalchemy import text as sa_text
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else default_model


def _sse_chunk(delta: str) -> str:
    return f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return f"data: {json.dumps({'done': True})}\n\n"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionUpsertRequest(BaseModel):
    id: Optional[int] = None
    title: str = "新建复盘"
    status: Optional[str] = "draft"
    live_data: Optional[str] = None
    material_data: Optional[str] = None
    review_text: Optional[str] = None
    live_script: Optional[str] = None
    material_scripts: Optional[dict] = None
    result: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /{kol_id}/retrospective — 分页列表
# ---------------------------------------------------------------------------

@router.get("/{kol_id}/retrospective")
async def list_sessions(
    kol_id: int,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    total_result = await db.execute(
        select(RetrospectiveSession)
        .where(RetrospectiveSession.kol_id == kol_id)
    )
    total = len(total_result.scalars().all())

    sessions = (await db.execute(
        select(RetrospectiveSession)
        .where(RetrospectiveSession.kol_id == kol_id)
        .order_by(RetrospectiveSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return success_response(data={
        "items": [_session_to_dict(s) for s in sessions],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total > 0 else 0,
        },
    })


# ---------------------------------------------------------------------------
# POST /{kol_id}/retrospective — 新建/更新（upsert by id）
# ---------------------------------------------------------------------------

@router.post("/{kol_id}/retrospective")
async def upsert_session(
    kol_id: int,
    body: SessionUpsertRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if body.id:
        # 更新已有 session
        result = await db.execute(
            update(RetrospectiveSession)
            .where(
                RetrospectiveSession.id == body.id,
                RetrospectiveSession.kol_id == kol_id,
            )
            .values(
                title=body.title,
                status=body.status,
                live_data=body.live_data,
                material_data=body.material_data,
                review_text=body.review_text,
                live_script=body.live_script,
                material_scripts=body.material_scripts,
                result=body.result,
                updated_at=datetime.now(timezone.utc),
            )
            .returning(RetrospectiveSession.id)
        )
        session_id = result.scalar_one_or_none()
        if session_id is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘记录不存在"},
            )
        session = (await db.execute(
            select(RetrospectiveSession).where(RetrospectiveSession.id == session_id)
        )).scalar_one()
        action = "update_retrospective_session"
    else:
        # 新建 session
        session = RetrospectiveSession(
            kol_id=kol_id,
            created_by=current_user.id,
            title=body.title,
            status=body.status or "draft",
            live_data=body.live_data,
            material_data=body.material_data,
            review_text=body.review_text,
            live_script=body.live_script,
            material_scripts=body.material_scripts,
            result=body.result,
        )
        db.add(session)
        await db.flush()
        action = "create_retrospective_session"

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action=action,
        target_type="retrospective_session",
        target_id=session.id,
        detail={"kol_id": kol_id, "title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(session)
    return success_response(data=_session_to_dict(session))


# ---------------------------------------------------------------------------
# DELETE /{kol_id}/retrospective/{id} — 物理删除
# ---------------------------------------------------------------------------

@router.delete("/{kol_id}/retrospective/{session_id}")
async def delete_session(
    kol_id: int,
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    result = await db.execute(
        delete(RetrospectiveSession)
        .where(
            RetrospectiveSession.id == session_id,
            RetrospectiveSession.kol_id == kol_id,
        )
        .returning(RetrospectiveSession.id)
    )
    deleted_id = result.scalar_one_or_none()
    if deleted_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘记录不存在"},
        )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="delete_retrospective_session",
        target_type="retrospective_session",
        target_id=session_id,
        detail={"kol_id": kol_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": session_id})


# ---------------------------------------------------------------------------
# POST /{kol_id}/retrospective/parse-files — 文件解析（multipart）
# ---------------------------------------------------------------------------

@router.post("/{kol_id}/retrospective/parse-files")
async def parse_files(
    kol_id: int,
    files: List[UploadFile] = File(...),
    _: User = Depends(require_operator),
):
    try:
        text = await document_parser.parse_files_to_text(files)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": str(e)},
        )
    return success_response(data={"text": text})


# ---------------------------------------------------------------------------
# POST /{kol_id}/retrospective/{id}/analyze — 流式生成复盘报告（SSE）
# ---------------------------------------------------------------------------

@router.post("/{kol_id}/retrospective/{session_id}/analyze")
async def analyze_stream(
    kol_id: int,
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    # 读取 session
    session = (await db.execute(
        select(RetrospectiveSession).where(
            RetrospectiveSession.id == session_id,
            RetrospectiveSession.kol_id == kol_id,
        )
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘记录不存在"},
        )

    # 读取 kol extra_notes
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    extra_notes = kol.extra_notes if kol and kol.extra_notes else ""

    # 读取 retrospective_configs default
    config = (await db.execute(
        select(RetrospectiveConfig).where(RetrospectiveConfig.config_key == "default")
    )).scalar_one_or_none()

    system_prompt = (
        config.system_prompt if config and config.system_prompt else _DEFAULT_SYSTEM_PROMPT
    )
    model_id = await _resolve_model_id(config, db)

    # 拼 prompt
    material_parts = []
    if session.live_data:
        material_parts.append(f"【直播数据】\n{session.live_data}")
    if session.material_data:
        material_parts.append(f"【素材数据】\n{session.material_data}")
    if session.review_text:
        material_parts.append(f"【评价文字】\n{session.review_text}")
    if session.live_script:
        material_parts.append(f"【直播脚本】\n{session.live_script}")
    if session.material_scripts:
        scripts_text = json.dumps(session.material_scripts, ensure_ascii=False)
        material_parts.append(f"【素材脚本】\n{scripts_text}")

    user_content = f"复盘标题：{session.title}\n\n"
    if material_parts:
        user_content += "\n\n".join(material_parts)
    else:
        user_content += "（暂无材料）"
    if extra_notes:
        user_content += f"\n\n【达人风格约束】\n{extra_notes}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    user_id = current_user.id
    state: dict = {"full_text": ""}

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    user_id=user_id,
                    feature="retrospective_analyze",
                ):
                    state["full_text"] += chunk
                    yield _sse_chunk(chunk)
            except Exception as e:
                yield _sse_chunk(f"[ERROR] {e}")
        yield _sse_done()

        # 完成后更新 session.result + status='done'
        async with AsyncSessionLocal() as save_db:
            await save_db.execute(
                update(RetrospectiveSession)
                .where(RetrospectiveSession.id == session_id)
                .values(
                    result=state["full_text"],
                    status="done",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            save_db.add(OperationLog(
                user_id=user_id,
                action="retrospective_analyze",
                target_type="retrospective_session",
                target_id=session_id,
                detail={"kol_id": kol_id, "model_id": model_id},
            ))
            await save_db.commit()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /{kol_id}/retrospective/{id}/export-word — 导出 Word
# ---------------------------------------------------------------------------

@router.get("/{kol_id}/retrospective/{session_id}/export-word")
async def export_word(
    kol_id: int,
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    session = (await db.execute(
        select(RetrospectiveSession).where(
            RetrospectiveSession.id == session_id,
            RetrospectiveSession.kol_id == kol_id,
        )
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "复盘记录不存在"},
        )

    result_text = session.result or ""
    docx_bytes = markdown_to_docx_bytes(
        title=session.title,
        metadata_lines=[f"KOL ID: {kol_id}", f"导出时间: {datetime.now().strftime('%Y-%m-%d')}"],
        content=result_text,
    )

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="retrospective.docx"'},
    )
