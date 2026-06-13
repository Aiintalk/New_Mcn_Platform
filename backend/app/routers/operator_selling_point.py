"""
app/routers/operator_selling_point.py

运营端接口（JWT 鉴权，operator / admin）：
  POST   /api/tools/selling-point-extractor/chat        — AI 流式对话（从 DB 读取 Prompt+模型）
  POST   /api/tools/selling-point-extractor/parse-file  — 文件解析
  GET    /api/tools/selling-point-extractor/history     — 历史列表 / 单条（全员共享）
  POST   /api/tools/selling-point-extractor/history     — 保存（写 outputs 表）
  DELETE /api/tools/selling-point-extractor/history     — 软删除
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.middlewares.auth import get_current_user
from app.models.output import Output
from app.models.selling_point import SellingPointConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_selling_point_file

router = APIRouter(prefix="/tools/selling-point-extractor", tags=["selling-point-extractor"])

TOOL_CODE = "selling-point-extractor"
TOOL_NAME = "产品卖点提取器"
CONFIG_KEY = "extract"
DEFAULT_MODEL = "claude-sonnet-4-6"


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


async def _get_active_config(db: AsyncSession) -> SellingPointConfig:
    """从 DB 读取激活的配置，不存在则抛 503。"""
    config = (await db.execute(
        select(SellingPointConfig)
        .where(SellingPointConfig.config_key == CONFIG_KEY)
        .where(SellingPointConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": "卖点提取配置未激活，请联系管理员"},
        )
    return config


async def _resolve_model_id(config: SellingPointConfig, db: AsyncSession) -> str:
    """解析配置绑定的模型 ID，无绑定则返回默认值。"""
    if not config.ai_model_id:
        return DEFAULT_MODEL
    from sqlalchemy import text
    row = (await db.execute(
        text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 流式对话。Prompt 和模型从 selling_point_configs 表读取，不硬编码。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )

    config = await _get_active_config(db)
    model_id = await _resolve_model_id(config, db)
    system_prompt = config.system_prompt or ""
    messages = [{"role": "system", "content": system_prompt}] + body.messages
    user_id = current_user.id

    async def generate():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    user_id=user_id,
                    feature="selling_point_chat",
                    max_tokens=8192,
                ):
                    yield chunk
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def write_task_job():
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"SP-{int(time.time())}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "briefFileCount": sum(
                        1 for m in body.messages
                        if m.get("role") == "user" and "产品Brief" in m.get("content", "")
                    ),
                    "scriptFileCount": sum(
                        1 for m in body.messages
                        if m.get("role") == "user" and "达人文案脚本" in m.get("content", "")
                    ),
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    try:
        text = await parse_selling_point_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "PARSE_ERROR", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return {"text": text, "filename": file.filename}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class SaveHistoryRequest(BaseModel):
    productName: str = "未命名产品"
    result: str
    chatHistory: list[dict] = []
    briefFiles: list[dict] = []
    scriptFiles: list[dict] = []


@router.get("/history")
async def get_history(
    id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """历史记录查询。全员共享，不按用户隔离。"""
    if id is not None:
        row = await db.get(Output, id)
        if row is None or row.deleted_at is not None or row.tool_code != TOOL_CODE:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "记录不存在"},
            )
        cj = row.content_json or {}
        return {
            "record": {
                "id": str(row.id),
                "productName": row.title,
                "result": row.content or "",
                "chatHistory": cj.get("chatHistory", []),
                "briefFiles": cj.get("briefFiles", []),
                "scriptFiles": cj.get("scriptFiles", []),
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        }

    rows = (await db.execute(
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
        .order_by(Output.created_at.desc())
    )).scalars().all()

    return {
        "records": [
            {
                "id": str(r.id),
                "productName": r.title,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
                "summary": (r.content or "")[:100].replace("\n", " ") + "..."
                if r.content and len(r.content) > 100 else (r.content or ""),
            }
            for r in rows
        ]
    }


@router.post("/history")
async def save_history(
    body: SaveHistoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.result.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "result 不能为空"},
        )
    output = Output(
        title=body.productName or "未命名产品",
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.result,
        content_json={
            "chatHistory": body.chatHistory,
            "briefFiles": body.briefFiles,
            "scriptFiles": body.scriptFiles,
        },
        word_count=len(body.result),
        created_by=current_user.id,
    )
    db.add(output)
    await db.commit()
    await db.refresh(output)
    return {"success": True, "id": str(output.id)}


@router.delete("/history")
async def delete_history(
    id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    row = await db.get(Output, id)
    if row is None or row.deleted_at is not None or row.tool_code != TOOL_CODE:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "记录不存在"},
        )
    row.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}
