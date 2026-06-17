"""
app/routers/operator_qianchuan_preview.py

千川文案预审接口（operator / admin 鉴权）：
  POST /api/tools/qianchuan-preview/parse-file  — 上传文案文件，返回文本
  POST /api/tools/qianchuan-preview/generate    — SSE 流式生成预审报告
  POST /api/tools/qianchuan-preview/export-word — 导出 Word 文件
"""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.user import User
from app.services import word_export
from app.services.file_parser import parse_qianchuan_review_file
from app.tools.qianchuan_preview.prompts import PROMPT_DEFAULT

router = APIRouter(prefix="/tools/qianchuan-preview", tags=["qianchuan-preview"])

DEFAULT_MODEL = "claude-sonnet-4-20250514"


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
    _: User = Depends(require_operator),
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
    if config_row and config_row[1]:
        model_row = (await db.execute(sa_text(
            "SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"
        ), {"id": config_row[1]})).fetchone()
        if model_row:
            model_id = model_row[0]

    user_content = f"## 文案A\n{body.script_a}\n\n---\n\n## 文案B\n{body.script_b}"
    messages = [{"role": "user", "content": user_content}]

    async def stream_generator():
        try:
            async for chunk in yunwu_adapter.chat_stream(
                messages=messages,
                system_prompt=system_prompt,
                model=model_id,
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
