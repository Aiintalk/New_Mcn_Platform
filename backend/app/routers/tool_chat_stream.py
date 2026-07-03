"""
app/routers/tool_chat_stream.py

POST /api/tools/chat-stream
通用多模态流式接口，透传 messages + system_prompt 给 yunwu.chat_stream()。

支持 ai_model_id：调用方传则查 ai_models 表解析 (model_id, provider)，
不传则用 body.model + 默认 provider=yunwu（向后兼容）。
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_RETRY_DELAYS = [2, 4, 6]  # 429 重试间隔（秒）

DEFAULT_MODEL = "gpt-4o"
DEFAULT_PROVIDER = "yunwu"


async def _resolve_model(ai_model_id: int | None, db: AsyncSession) -> tuple[str, str]:
    """解析 ai_model_id → (model_id, provider)；无值或失效则返回默认。"""
    if not ai_model_id:
        return DEFAULT_MODEL, DEFAULT_PROVIDER
    row = (await db.execute(
        text(
            "SELECT model_id, COALESCE(provider, :default_p) "
            "FROM ai_models WHERE id = :id AND status = 'active'"
        ),
        {"id": ai_model_id, "default_p": DEFAULT_PROVIDER},
    )).fetchone()
    return (row[0], row[1]) if row else (DEFAULT_MODEL, DEFAULT_PROVIDER)


class ChatStreamRequest(BaseModel):
    messages: list[dict]
    system_prompt: str
    model: str = "gpt-4o"
    max_tokens: int = 8000
    ai_model_id: int | None = None  # 有值则覆盖 model 并解析 provider


@router.post("/chat-stream")
async def chat_stream(
    body: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_password_changed),
):
    """多模态流式接口：拼 system_prompt → 调 yunwu.chat_stream → StreamingResponse。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if not body.system_prompt.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "system_prompt 不能为空"},
        )

    model_id, provider = await _resolve_model(body.ai_model_id, db)

    messages = [{"role": "system", "content": body.system_prompt}] + body.messages
    user_id = current_user.id
    max_tokens = body.max_tokens

    async def generate():
        delays = [0] + _RETRY_DELAYS
        for i, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with AsyncSessionLocal() as stream_db:
                    async for chunk in yunwu_adapter.chat_stream(
                        messages=messages,
                        db=stream_db,
                        model_id=model_id,
                        provider=provider,
                        user_id=user_id,
                        feature="qianchuan_edit_review_chat",
                        max_tokens=max_tokens,
                    ):
                        yield chunk
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(delays) - 1:
                    continue
                yield f"\n\n[ERROR] {str(e)}"
                return

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )
