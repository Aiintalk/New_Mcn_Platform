"""
app/routers/tool_chat_stream.py

POST /api/tools/chat-stream
通用多模态流式接口，透传 messages + system_prompt 给 yunwu.chat_stream()。
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_RETRY_DELAYS = [2, 4, 6]  # 429 重试间隔（秒）


class ChatStreamRequest(BaseModel):
    messages: list[dict]
    system_prompt: str
    model: str = "gpt-4o"
    max_tokens: int = 8000


@router.post("/chat-stream")
async def chat_stream(
    body: ChatStreamRequest,
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

    messages = [{"role": "system", "content": body.system_prompt}] + body.messages
    user_id = current_user.id
    model_id = body.model
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
