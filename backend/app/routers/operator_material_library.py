"""
app/routers/operator_material_library.py

素材库运营端 API（7 接口）：
  GET    /kols                          红人列表（含 profile 概况 + 素材数 + intake 状态）
  GET    /kols/{kol_id}                 红人详情（persona + content_plan + references 按类型分组）
  PUT    /kols/{kol_id}/profile         更新 kols.persona（soul.md）/ kols.content_plan
  POST   /kols/{kol_id}/references      添加素材
  DELETE /kols/{kol_id}/references/{id} 删除素材（软删除）
  GET    /kols/{kol_id}/intake          获取关联的入驻问卷数据（只读）
  POST   /kols/{kol_id}/generate-soul   AI 生成 soul.md 初稿
"""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user
from app.models.user import User
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.material_library import KolReference, MaterialLibraryConfig
from app.models.kol_intake import (
    KolIntakeSubmission,
    KolIntakeLink,
    KolIntakeOperatorSession,
)
from app.models.credential import AiModel
from app.adapters import yunwu as yunwu_adapter
from app.adapters import oss as oss_adapter
from app.services import document_parser
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/tools/material-library", tags=["material-library"])

VALID_TYPES = [
    "红人爆款文案", "红人喜欢的内容", "风格参考",
    "千川爆款文案", "千川喜欢的内容", "千川风格参考",
]


# ---------------------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------------------
class ProfileUpdate(BaseModel):
    persona: Optional[str] = None        # soul.md 全文
    content_plan: Optional[str] = None   # content-plan.md 全文


class ReferenceCreate(BaseModel):
    title: str
    likes: Optional[int] = None
    source: str = "抖音"
    type: str
    content: str
    data_description: Optional[str] = None
    document_name: Optional[str] = None
    document_type: Optional[str] = None
    document_size: Optional[int] = None


class ReferenceUpdate(BaseModel):
    title: Optional[str] = None
    data_description: Optional[str] = None
    content: Optional[str] = None
    document_name: Optional[str] = None
    document_type: Optional[str] = None
    document_size: Optional[int] = None


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _require_operator(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise ValueError("用户已停用")
    return current_user


def _get_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")


async def _get_active_kol(db: AsyncSession, kol_id: int) -> Kol | None:
    return (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()


async def _get_active_reference(
    db: AsyncSession, kol_id: int, ref_id: int
) -> KolReference | None:
    return (await db.execute(
        select(KolReference).where(
            KolReference.id == ref_id,
            KolReference.kol_id == kol_id,
            KolReference.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


def _reference_to_dict(ref: KolReference) -> dict:
    """返回安全的素材数据：私有对象键和签名地址不进入页面数据。"""
    return {
        "id": ref.id,
        "title": ref.title,
        "likes": ref.likes,
        "source": ref.source,
        "type": ref.type,
        "content": ref.content,
        "data_description": ref.data_description,
        "document_name": ref.document_name,
        "document_type": ref.document_type,
        "document_size": ref.document_size,
        "has_video": bool(ref.video_oss_key),
        "video_name": ref.video_name,
        "video_content_type": ref.video_content_type,
        "video_size": ref.video_size,
        "created_at": ref.created_at.isoformat() if ref.created_at else None,
    }


async def _get_latest_intake(db: AsyncSession, kol_name: str) -> dict | None:
    """通过 kol_name 弱匹配获取最新的入驻问卷数据（先查 submissions，再查 operator_sessions）。"""
    # 1. KolIntakeSubmission（通过 link 的 kol_name 关联）
    stmt = (
        select(KolIntakeSubmission, KolIntakeLink.kol_name)
        .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeLink.kol_name == kol_name)
        .order_by(KolIntakeSubmission.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row:
        sub = row[0]
        return {
            "source": "submission",
            "messages": sub.messages,
            "ai_report": sub.ai_report,
            "report_status": sub.report_status,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        }

    # 2. KolIntakeOperatorSession（通过 kol_name 直接关联）
    stmt2 = (
        select(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.kol_name == kol_name)
        .order_by(KolIntakeOperatorSession.created_at.desc())
        .limit(1)
    )
    session = (await db.execute(stmt2)).scalar_one_or_none()
    if session:
        return {
            "source": "operator_session",
            "messages": session.messages,
            "ai_report": session.ai_report,
            "report_status": session.report_status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        }

    return None


# ---------------------------------------------------------------------------
# 1. GET /kols — 红人列表
# ---------------------------------------------------------------------------
@router.get("/kols")
async def list_kols(
    search: str = Query(default="", description="按红人名搜索"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """红人列表，每行含：基本信息 + persona 有无 + content_plan 有无 + 素材数 + intake 状态。"""
    # 基础查询：未软删的红人
    base = select(Kol).where(Kol.deleted_at.is_(None))
    if search:
        base = base.where(Kol.name.ilike(f"%{search}%"))
    base = base.order_by(Kol.updated_at.desc())
    kols = (await db.execute(base)).scalars().all()
    if not kols:
        return success_response(data=[])

    kol_ids = [k.id for k in kols]

    # 批量统计每个红人的素材数
    ref_counts_stmt = (
        select(KolReference.kol_id, func.count(KolReference.id).label("cnt"))
        .where(and_(KolReference.kol_id.in_(kol_ids), KolReference.deleted_at.is_(None)))
        .group_by(KolReference.kol_id)
    )
    ref_counts = {row[0]: row[1] for row in (await db.execute(ref_counts_stmt)).all()}

    # 批量查 intake 状态（通过 kol_name）
    kol_names = [k.name for k in kols]
    intake_names_sub = (
        select(KolIntakeLink.kol_name)
        .join(KolIntakeSubmission, KolIntakeSubmission.link_id == KolIntakeLink.id)
        .where(KolIntakeLink.kol_name.in_(kol_names))
        .distinct()
    )
    intake_names_op = (
        select(KolIntakeOperatorSession.kol_name)
        .where(KolIntakeOperatorSession.kol_name.in_(kol_names))
        .distinct()
    )
    intake_names = set()
    for r in (await db.execute(intake_names_sub)).all():
        intake_names.add(r[0])
    for r in (await db.execute(intake_names_op)).all():
        intake_names.add(r[0])

    result = []
    for k in kols:
        result.append({
            "id": k.id,
            "name": k.name,
            "account_name": k.account_name,
            "category": k.category,
            "follower_count": k.follower_count,
            "has_persona": bool(k.persona),
            "has_content_plan": bool(k.content_plan),
            "reference_count": ref_counts.get(k.id, 0),
            "has_intake": k.name in intake_names,
            "updated_at": k.updated_at.isoformat() if k.updated_at else None,
        })

    return success_response(data=result)


# ---------------------------------------------------------------------------
# 2. GET /kols/{kol_id} — 红人详情
# ---------------------------------------------------------------------------
@router.get("/kols/{kol_id}")
async def get_kol_detail(
    kol_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """红人详情：persona + content_plan + references 按类型分组。"""
    kol = await _get_active_kol(db, kol_id)
    if not kol:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    # 素材按类型分组
    refs_stmt = (
        select(KolReference)
        .where(and_(KolReference.kol_id == kol_id, KolReference.deleted_at.is_(None)))
        .order_by(KolReference.created_at.desc())
    )
    refs = (await db.execute(refs_stmt)).scalars().all()

    grouped = {}
    for r in refs:
        grouped.setdefault(r.type, []).append(_reference_to_dict(r))

    return success_response(data={
        "id": kol.id,
        "name": kol.name,
        "account_name": kol.account_name,
        "category": kol.category,
        "follower_count": kol.follower_count,
        "persona": kol.persona or "",
        "content_plan": kol.content_plan or "",
        "references": grouped,
    })


# ---------------------------------------------------------------------------
# 3. PUT /kols/{kol_id}/profile — 更新 persona / content_plan
# ---------------------------------------------------------------------------
@router.put("/kols/{kol_id}/profile")
async def update_profile(
    kol_id: int,
    body: ProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新 kols.persona（soul.md）和/或 kols.content_plan。"""
    kol = await _get_active_kol(db, kol_id)
    if not kol:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    changes = []
    if body.persona is not None:
        kol.persona = body.persona
        changes.append("persona")
    if body.content_plan is not None:
        kol.content_plan = body.content_plan
        changes.append("content_plan")

    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_update_profile",
        target_type="kol",
        target_id=kol_id,
        detail={"updated_fields": changes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"kol_id": kol_id, "updated_fields": changes})


# ---------------------------------------------------------------------------
# 4. POST /kols/{kol_id}/references — 添加素材
# ---------------------------------------------------------------------------
@router.post("/kols/{kol_id}/references")
async def create_reference(
    kol_id: int,
    body: ReferenceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """添加一条参考素材（6 种类型之一）。"""
    kol = await _get_active_kol(db, kol_id)
    if not kol:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    if body.type not in VALID_TYPES:
        return error_response(ErrorCode.VALIDATION_ERROR, f"素材类型无效，可选: {', '.join(VALID_TYPES)}")

    ref = KolReference(
        kol_id=kol_id,
        title=body.title,
        likes=body.likes,
        source=body.source,
        type=body.type,
        content=body.content,
        data_description=body.data_description,
        document_name=body.document_name,
        document_type=body.document_type,
        document_size=body.document_size,
        created_by=user.id,
    )
    db.add(ref)
    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_create_reference",
        target_type="kol_reference",
        target_id=None,
        detail={"kol_id": kol_id, "title": body.title, "type": body.type},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(ref)
    return success_response(data={"kol_id": ref.kol_id, **_reference_to_dict(ref)})


# ---------------------------------------------------------------------------
# 5. PUT /kols/{kol_id}/references/{ref_id} — 编辑素材正文和元数据
# ---------------------------------------------------------------------------
@router.put("/kols/{kol_id}/references/{ref_id}")
async def update_reference(
    kol_id: int,
    ref_id: int,
    body: ReferenceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """编辑标题、数据说明、正文和解析来源元数据，不触碰现有视频。"""
    ref = await _get_active_reference(db, kol_id, ref_id)
    if not ref:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "素材不存在")

    changes = []
    for field in (
        "title", "data_description", "content", "document_name", "document_type", "document_size"
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(ref, field, value)
            changes.append(field)

    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_update_reference",
        target_type="kol_reference",
        target_id=ref_id,
        detail={"kol_id": kol_id, "updated_fields": changes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(ref)
    return success_response(data={"kol_id": ref.kol_id, **_reference_to_dict(ref)})


# ---------------------------------------------------------------------------
# 6. POST /kols/{kol_id}/references/parse-document — 上传后先解析，保存前可编辑
# ---------------------------------------------------------------------------
@router.post("/kols/{kol_id}/references/parse-document")
async def parse_reference_document(
    kol_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """解析一份脚本文档；只返回文本和元数据，不保存原文件路径或内容副本。"""
    if not await _get_active_kol(db, kol_id):
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    raw = await file.read()
    await file.seek(0)
    try:
        parsed = await document_parser.parse_files_to_items([file])
    except ValueError as exc:
        return error_response(ErrorCode.VALIDATION_ERROR, str(exc))

    item = parsed[0]
    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_parse_document",
        target_type="kol_reference_document",
        target_id=None,
        detail={"kol_id": kol_id, "filename": item["name"], "document_size": len(raw)},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={
        "text": item["text"],
        "document_name": item["name"],
        "document_type": file.content_type,
        "document_size": len(raw),
    })


def _video_oss_key(kol_id: int, ref_id: int, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"material-library/{kol_id}/{ref_id}/{uuid4().hex}{suffix}"


# ---------------------------------------------------------------------------
# 7. POST /kols/{kol_id}/references/{ref_id}/video — 上传或显式替换视频
# ---------------------------------------------------------------------------
@router.post("/kols/{kol_id}/references/{ref_id}/video")
async def upload_reference_video(
    kol_id: int,
    ref_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """视频先上传新对象，再替换元数据；私有对象键不返回给前端。"""
    ref = await _get_active_reference(db, kol_id, ref_id)
    if not ref:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "素材不存在")
    if not (file.content_type or "").startswith("video/"):
        return error_response(ErrorCode.VALIDATION_ERROR, "请上传视频文件")

    content = await file.read()
    if not content:
        return error_response(ErrorCode.VALIDATION_ERROR, "视频文件不能为空")

    filename = file.filename or "video"
    new_key = _video_oss_key(kol_id, ref_id, filename)
    try:
        await oss_adapter.upload_file(
            new_key, content, file.content_type or "application/octet-stream", db, user.id
        )
    except (KeyError, RuntimeError):
        return error_response(ErrorCode.EXTERNAL_SERVICE_ERROR, "视频上传失败，请检查对象存储配置后重试")

    old_key = ref.video_oss_key
    ref.video_oss_key = new_key
    ref.video_name = filename
    ref.video_content_type = file.content_type
    ref.video_size = len(content)
    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_replace_video" if old_key else "material_library_upload_video",
        target_type="kol_reference",
        target_id=ref_id,
        detail={"kol_id": kol_id, "filename": filename, "video_size": len(content)},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(ref)

    if old_key:
        try:
            await oss_adapter.delete_file(old_key, db, user.id)
        except (KeyError, RuntimeError):
            db.add(OperationLog(
                user_id=user.id,
                username=user.username,
                role=user.role,
                action="material_library_replace_video_cleanup_failed",
                target_type="kol_reference",
                target_id=ref_id,
                detail={"kol_id": kol_id},
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent"),
            ))
            await db.commit()

    return success_response(data={"kol_id": ref.kol_id, **_reference_to_dict(ref)})


# ---------------------------------------------------------------------------
# 8. GET /kols/{kol_id}/references/{ref_id}/video/playback — 短时签名播放地址
# ---------------------------------------------------------------------------
@router.get("/kols/{kol_id}/references/{ref_id}/video/playback")
async def get_reference_video_playback(
    kol_id: int,
    ref_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ref = await _get_active_reference(db, kol_id, ref_id)
    if not ref:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "素材不存在")
    if not ref.video_oss_key:
        return error_response(ErrorCode.FILE_NOT_FOUND, "素材未上传视频")
    try:
        url = await oss_adapter.get_download_url(ref.video_oss_key, db, expires=900, user_id=user.id)
    except (KeyError, RuntimeError):
        return error_response(ErrorCode.EXTERNAL_SERVICE_ERROR, "视频播放地址生成失败，请检查对象存储配置后重试")
    return success_response(data={"url": url, "expires_in": 900})


# ---------------------------------------------------------------------------
# 9. DELETE /kols/{kol_id}/references/{ref_id} — 删除素材（软删除）
# ---------------------------------------------------------------------------
@router.delete("/kols/{kol_id}/references/{ref_id}")
async def delete_reference(
    kol_id: int,
    ref_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """软删除一条参考素材。"""
    ref = await _get_active_reference(db, kol_id, ref_id)
    if not ref:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "素材不存在")

    video_oss_key = ref.video_oss_key
    ref.deleted_at = func.now()
    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_delete_reference",
        target_type="kol_reference",
        target_id=ref_id,
        detail={"kol_id": kol_id, "title": ref.title, "type": ref.type},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    if video_oss_key:
        try:
            await oss_adapter.delete_file(video_oss_key, db, user.id)
        except (KeyError, RuntimeError):
            db.add(OperationLog(
                user_id=user.id,
                username=user.username,
                role=user.role,
                action="material_library_delete_video_cleanup_failed",
                target_type="kol_reference",
                target_id=ref_id,
                detail={"kol_id": kol_id},
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent"),
            ))
            await db.commit()
            return success_response(message="素材已删除，视频对象清理失败已记录")

    return success_response(message="删除成功")


# ---------------------------------------------------------------------------
# 6. GET /kols/{kol_id}/intake — 获取关联的入驻问卷数据
# ---------------------------------------------------------------------------
@router.get("/kols/{kol_id}/intake")
async def get_intake(
    kol_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """只读展示该红人关联的入驻问卷数据（通过 kol_name 弱匹配）。"""
    kol = (await db.execute(select(Kol).where(Kol.id == kol_id))).scalar_one_or_none()
    if not kol or kol.deleted_at:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    intake = await _get_latest_intake(db, kol.name)
    if not intake:
        return success_response(data=None, message="该红人暂无入驻问卷数据")

    return success_response(data=intake)


# ---------------------------------------------------------------------------
# 7. POST /kols/{kol_id}/generate-soul — AI 生成 soul.md 初稿
# ---------------------------------------------------------------------------
@router.post("/kols/{kol_id}/generate-soul")
async def generate_soul(
    kol_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从入驻问卷数据 + AI 报告，用可配置 Prompt 生成 soul.md 初稿（不自动保存）。"""
    kol = (await db.execute(select(Kol).where(Kol.id == kol_id))).scalar_one_or_none()
    if not kol or kol.deleted_at:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    # 1. 获取 intake 数据
    intake = await _get_latest_intake(db, kol.name)
    if not intake:
        return error_response(ErrorCode.VALIDATION_ERROR, "该红人暂无入驻问卷数据，无法生成人格档案")

    # 2. 获取 soul_generator 配置
    config = (
        await db.execute(
            select(MaterialLibraryConfig).where(
                and_(
                    MaterialLibraryConfig.config_key == "soul_generator",
                    MaterialLibraryConfig.is_active.is_(True),
                )
            )
        )
    ).scalar_one_or_none()
    if not config or not config.system_prompt:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "素材库 AI 配置缺失，请联系管理员在「工具配置→素材库配置」中设置",
        )

    # 3. 获取 AI 模型标识
    model = None
    if config.ai_model_id:
        model = (
            await db.execute(select(AiModel).where(AiModel.id == config.ai_model_id))
        ).scalar_one_or_none()
    if not model:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "AI 模型未配置，请联系管理员在「工具配置→素材库配置」中选择模型",
        )

    # 4. 渲染 Prompt 占位符
    intake_answers = json.dumps(intake.get("messages", []), ensure_ascii=False, indent=2)
    intake_report = intake.get("ai_report") or "（暂无 AI 分析报告）"

    prompt = config.system_prompt
    prompt = prompt.replace("{{kol_name}}", kol.name or "")
    prompt = prompt.replace("{{intake_answers}}", intake_answers)
    prompt = prompt.replace("{{intake_report}}", intake_report)

    # 5. 调用 yunwu adapter（非流式）
    try:
        soul_draft = await yunwu_adapter.chat(
            messages=[{"role": "user", "content": "请根据以上信息生成人格档案。"}],
            db=db,
            model_id=model.model_id,
            user_id=user.id,
            feature="material_library_soul_generator",
            max_tokens=8192,
        )
    except Exception as e:
        return error_response(
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            f"AI 生成失败: {str(e)[:200]}",
        )

    # 6. 记录操作日志
    db.add(OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action="material_library_generate_soul",
        target_type="kol",
        target_id=kol_id,
        detail={"model": model.model_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"soul_md": soul_draft})
