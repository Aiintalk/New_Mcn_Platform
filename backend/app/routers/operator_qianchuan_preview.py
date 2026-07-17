"""
app/routers/operator_qianchuan_preview.py

千川文案预审接口（operator / admin 鉴权）：
  POST /api/tools/qianchuan-preview/parse-file  — 上传文案文件，返回文本
  POST /api/tools/qianchuan-preview/generate    — SSE 流式生成预审报告
  POST /api/tools/qianchuan-preview/export-word — 导出 Word 文件
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import gemini_video
from app.adapters import oss as oss_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.kol import Kol
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services import word_export
from app.services.file_parser import parse_qianchuan_review_file
from app.tools.qianchuan_preview.prompts import PROMPT_DEFAULT

router = APIRouter(prefix="/tools/qianchuan-preview", tags=["qianchuan-preview"])

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_PROVIDER = "yunwu"
VIDEO_MAX_BYTES = 500 * 1024 * 1024
VIDEO_CHUNK_BYTES = 1024 * 1024
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
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
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    _: User = Depends(require_operator),
):
    """上传文案文件，解析返回文本。支持 .txt/.docx。"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("txt", "md", "docx", "pages"):
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": f"不支持的文件格式: .{ext}（支持 .txt / .md / .docx / .pages）"},
        )
    try:
        text = await parse_qianchuan_review_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return success_response(data={"text": text, "filename": file.filename})


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    script_a: str
    script_b: str


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """SSE 流式生成预审报告。"""
    if not body.script_a.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "文案A不能为空"},
        )
    if not body.script_b.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "文案B不能为空"},
        )

    # 从 DB 读取 Prompt + 模型
    config_row = (await db.execute(sa_text(
        "SELECT system_prompt, ai_model_id FROM qianchuan_preview_configs "
        "WHERE config_key = 'default' AND is_active = true LIMIT 1"
    ))).fetchone()

    system_prompt = (config_row[0] if config_row and config_row[0] else PROMPT_DEFAULT)

    model_id = DEFAULT_MODEL
    provider = DEFAULT_PROVIDER
    if config_row and config_row[1]:
        model_row = (await db.execute(sa_text(
            "SELECT model_id, COALESCE(provider, :default_p) FROM ai_models WHERE id = :id AND status = 'active'"
        ), {"id": config_row[1], "default_p": DEFAULT_PROVIDER})).fetchone()
        if model_row:
            model_id = model_row[0]
            provider = model_row[1]

    user_content = f"## 文案A\n{body.script_a}\n\n---\n\n## 文案B\n{body.script_b}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    async def stream_generator():
        try:
            async for chunk in yunwu_adapter.chat_stream(
                messages=messages,
                db=db,
                model_id=model_id,
                provider=provider,
                user_id=current_user.id,
                feature="qianchuan_preview_generate",
            ):
                yield chunk
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    title: str = "千川文案预审报告"


@router.post("/export-word")
async def export_word_endpoint(
    body: ExportWordRequest,
    _: User = Depends(require_operator),
):
    """导出预审报告为 Word 文件。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "报告内容不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    docx_bytes = word_export.markdown_to_docx_bytes(
        title=body.title,
        metadata_lines=[f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
        content=body.content,
    )

    filename = f"千川预审报告_{date_str}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


# ---------------------------------------------------------------------------
# POST /analyze-video — 工作台完整视频成片预审（不使用关键帧）
# ---------------------------------------------------------------------------

def _validate_video(file: UploadFile, label: str) -> None:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    expected_type = VIDEO_TYPES.get(suffix)
    if not expected_type:
        raise HTTPException(status_code=400, detail={"code": ErrorCode.VALIDATION_ERROR, "message": f"{label}只支持 mp4 或 mov 视频"})
    if file.content_type and file.content_type not in VIDEO_TYPES.values():
        raise HTTPException(status_code=400, detail={"code": ErrorCode.VALIDATION_ERROR, "message": f"{label}只支持 mp4 或 mov 视频"})


async def _write_video_to_temp(file: UploadFile, directory: Path, slot: str) -> tuple[Path, int]:
    """限制内分块落盘；文件本身不会长期保存在应用服务器。"""
    suffix = Path(file.filename or "").suffix.lower()
    target = directory / f"{slot}{suffix}"
    size = 0
    try:
        with target.open("wb") as destination:
            while chunk := await file.read(VIDEO_CHUNK_BYTES):
                size += len(chunk)
                if size > VIDEO_MAX_BYTES:
                    target.unlink(missing_ok=True)
                    raise ValueError(f"视频文件大小不能超过 {VIDEO_MAX_BYTES // 1024 // 1024}MB")
                destination.write(chunk)
    except OSError:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise ValueError("视频文件不能为空")
    return target, size


async def _resolve_full_video_config(db: AsyncSession) -> tuple[str, str]:
    """必须由管理端绑定 active Gemini 模型，不能回退到默认文字模型。"""
    row = (await db.execute(sa_text(
        "SELECT system_prompt, ai_model_id FROM qianchuan_preview_configs "
        "WHERE config_key='full_video' AND is_active=true LIMIT 1"
    ))).fetchone()
    if not row or not row[1] or not (row[0] or "").strip():
        raise RuntimeError("请先在管理端为千川成片预审配置 Gemini 模型和提示词")
    model = (await db.execute(sa_text(
        "SELECT model_id, provider FROM ai_models WHERE id=:id AND status='active'"
    ), {"id": row[1]})).fetchone()
    if not model or model[1] != "gemini":
        raise RuntimeError("千川成片预审必须绑定启用中的 Gemini 模型")
    return model[0], row[0]


def _temporary_video_key(task_id: int, slot: str, filename: str) -> str:
    return f"qianchuan-preview/temp/{task_id}/{slot}-{uuid4().hex}{Path(filename).suffix.lower()}"


def _remove_local_video_temp(directory: Path | None, temp_paths: list[Path]) -> None:
    for path in temp_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if directory is None:
        return
    try:
        for path in directory.iterdir():
            path.unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        pass


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _set_video_task_error(task_id: int, message: str, error_code: str = ErrorCode.EXTERNAL_SERVICE_ERROR) -> None:
    async with AsyncSessionLocal() as task_db:
        task = await task_db.get(TaskJob, task_id)
        if task:
            task.status = "failed"
            task.error_code = error_code
            task.error_message = message[:500]
            task.finished_at = datetime.now(timezone.utc)
            task.duration_ms = max(task.duration_ms or 0, 0)
            await task_db.commit()


@router.post("/analyze-video")
async def analyze_video(
    kol_id: int = Form(...),
    original: UploadFile = File(...),
    edited: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Gemini 读取两条完整视频；任何配置/服务问题均明确失败，绝不关键帧降级。"""
    for file, label in ((original, "原片"), (edited, "剪辑成片")):
        _validate_video(file, label)
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not kol:
        raise HTTPException(status_code=404, detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "红人不存在"})

    try:
        model_id, system_prompt = await _resolve_full_video_config(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"code": ErrorCode.EXTERNAL_SERVICE_ERROR, "message": str(exc)}) from exc

    task = TaskJob(
        task_no=f"QVP-{time.time_ns()}-{current_user.id}",
        tool_code="qianchuan-preview",
        tool_name="千川成片预审",
        status="processing",
        input_payload={"mode": "full_video", "kol_id": kol_id},
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    directory: Path | None = None
    temp_paths: list[Path] = []
    oss_keys: list[str] = []
    try:
        directory = Path(mkdtemp(prefix=f"qianchuan-preview-{task.id}-"))
        original_path, original_size = await _write_video_to_temp(original, directory, "original")
        temp_paths.append(original_path)
        edited_path, edited_size = await _write_video_to_temp(edited, directory, "edited")
        temp_paths.append(edited_path)
        original_key = _temporary_video_key(task.id, "original", original.filename or "original.mp4")
        edited_key = _temporary_video_key(task.id, "edited", edited.filename or "edited.mp4")
        oss_keys.extend((original_key, edited_key))
        task.input_payload = {
            "mode": "full_video",
            "kol_id": kol_id,
            "original": {"oss_key": original_key, "filename": original.filename, "content_type": original.content_type or VIDEO_TYPES[original_path.suffix], "size": original_size},
            "edited": {"oss_key": edited_key, "filename": edited.filename, "content_type": edited.content_type or VIDEO_TYPES[edited_path.suffix], "size": edited_size},
        }
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="qianchuan_preview_full_video_start",
            target_type="task_job",
            target_id=task.id,
            detail={"mode": "full_video", "kol_id": kol_id, "original_size": original_size, "edited_size": edited_size},
        ))
        await db.commit()
        await oss_adapter.upload_file_from_path(original_key, original_path, original.content_type or VIDEO_TYPES[original_path.suffix], db, current_user.id)
        await oss_adapter.upload_file_from_path(edited_key, edited_path, edited.content_type or VIDEO_TYPES[edited_path.suffix], db, current_user.id)
    except ValueError as exc:
        await _set_video_task_error(task.id, str(exc))
        _remove_local_video_temp(directory, temp_paths)
        raise HTTPException(status_code=400, detail={"code": ErrorCode.VALIDATION_ERROR, "message": str(exc)}) from exc
    except OSError as exc:
        await _set_video_task_error(task.id, "本地临时视频写入失败", ErrorCode.INTERNAL_ERROR)
        _remove_local_video_temp(directory, temp_paths)
        raise HTTPException(status_code=500, detail={"code": ErrorCode.INTERNAL_ERROR, "message": "本地临时视频写入失败"}) from exc
    except (KeyError, RuntimeError) as exc:
        await _set_video_task_error(task.id, "临时视频上传失败，请检查对象存储配置后重试")
        for oss_key in oss_keys:
            try:
                await oss_adapter.delete_file(oss_key, db, current_user.id)
            except (KeyError, RuntimeError):
                pass
        _remove_local_video_temp(directory, temp_paths)
        raise HTTPException(status_code=502, detail={"code": ErrorCode.EXTERNAL_SERVICE_ERROR, "message": "临时视频上传失败，请检查对象存储配置后重试"}) from exc

    async def stream_report():
        finished = False
        error_message: str | None = None
        started = time.monotonic()
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in gemini_video.stream_full_video_analysis(
                    original_path=original_path,
                    edited_path=edited_path,
                    original_content_type=original.content_type or VIDEO_TYPES[original_path.suffix],
                    edited_content_type=edited.content_type or VIDEO_TYPES[edited_path.suffix],
                    system_prompt=system_prompt,
                    model_id=model_id,
                    db=stream_db,
                    user_id=current_user.id,
                    task_id=task.id,
                ):
                    if chunk.startswith("__STATUS__"):
                        yield _sse("status", {"message": chunk[len("__STATUS__"):].strip()})
                    else:
                        yield _sse("report", {"text": chunk})
            finished = True
        except GeneratorExit:
            error_message = "客户端中断了完整视频分析"
            raise
        except Exception as exc:
            error_message = str(exc)
            yield _sse("error", {"message": f"分析失败：{error_message}"})
            yield _sse("failed", {"task_id": task.id})
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                for oss_key in oss_keys:
                    try:
                        await oss_adapter.delete_file(oss_key, cleanup_db, current_user.id)
                    except (KeyError, RuntimeError):
                        cleanup_db.add(OperationLog(
                            user_id=current_user.id,
                            username=current_user.username,
                            role=current_user.role,
                            action="qianchuan_preview_full_video_oss_cleanup_failed",
                            target_type="task_job",
                            target_id=task.id,
                            detail={"oss_key": oss_key},
                        ))
                current = await cleanup_db.get(TaskJob, task.id)
                if current:
                    current.finished_at = datetime.now(timezone.utc)
                    current.duration_ms = int((time.monotonic() - started) * 1000)
                    if finished:
                        current.status = "success"
                    else:
                        current.status = "failed"
                        current.error_code = ErrorCode.EXTERNAL_SERVICE_ERROR
                        current.error_message = (error_message or "完整视频分析未完成")[:500]
                await cleanup_db.commit()
            _remove_local_video_temp(directory, temp_paths)

    return StreamingResponse(
        stream_report(),
        media_type="text/event-stream",
        headers={"X-Task-Id": str(task.id)},
    )


class SaveVideoReportRequest(BaseModel):
    task_id: int
    report: str
    original_filename: str
    edited_filename: str


@router.post("/save-video-report")
async def save_video_report(
    body: SaveVideoReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.report.strip():
        return error_response(ErrorCode.VALIDATION_ERROR, "报告内容不能为空")
    task = await db.get(TaskJob, body.task_id)
    payload = task.input_payload if task else None
    kol_id = payload.get("kol_id") if isinstance(payload, dict) else None
    if not task or task.tool_code != "qianchuan-preview" or not isinstance(payload, dict) or payload.get("mode") != "full_video" or not isinstance(kol_id, int):
        return error_response(ErrorCode.TASK_NOT_FOUND, "成片预审任务不存在")
    if task.status != "success":
        return error_response(ErrorCode.VALIDATION_ERROR, "完整视频分析尚未成功完成，不能保存报告")
    if current_user.role != "admin" and task.created_by != current_user.id:
        return error_response(ErrorCode.PERMISSION_DENIED, "只能保存自己的成片预审报告")
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not kol:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")
    output = Output(
        title=f"千川成片预审_{body.edited_filename}",
        tool_code="qianchuan-preview",
        tool_name="千川成片预审",
        task_id=task.id,
        content=body.report,
        content_json={
            "mode": "full_video",
            "kol_id": kol_id,
            "task_no": task.task_no,
            "original_filename": body.original_filename,
            "edited_filename": body.edited_filename,
        },
        word_count=len(body.report),
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()
    task.output_id = output.id
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_preview_full_video_save",
        target_type="output",
        target_id=output.id,
        detail={"task_id": task.id, "kol_id": kol_id, "mode": "full_video"},
    ))
    await db.commit()
    return success_response(data={"output_id": output.id})
