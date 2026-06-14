"""
app/routers/tool_transcribe.py

POST /api/tools/transcribe
接收视频文件，调云雾 Whisper 转录，返回文字。
"""
import asyncio
import os

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.response import success_response
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_MAX_SIZE = 25 * 1024 * 1024  # 25MB
_RETRY_DELAYS = [3, 6]         # 429 重试间隔（秒），共3次尝试（1首次+2重试）
_TIMEOUT = 120                  # httpx 超时


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    current_user: User = Depends(require_password_changed),
):
    """转录接口：接收视频，调云雾 Whisper，返回文字。"""
    content = await file.read()

    if len(content) > _MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": "文件不能超过 25MB"},
        )

    api_key = os.environ.get("YUNWU_API_KEY", "")
    base_url = os.environ.get("YUNWU_BASE_URL", "https://yunwu.ai/v1")
    url = f"{base_url}/audio/transcriptions"

    last_resp = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)

            form_data = {
                "model": (None, "gpt-4o-transcribe"),
                "language": (None, language),
                "file": (file.filename or "audio.mp4", content, "application/octet-stream"),
            }
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files=form_data,
            )
            last_resp = resp

            if resp.status_code == 429:
                if attempt < len(_RETRY_DELAYS):
                    continue
            break

    if last_resp is None or last_resp.status_code != 200:
        status_code = last_resp.status_code if last_resp else 0
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_ERROR", "message": f"转录失败（{status_code}），请稍后重试"},
        )

    result = last_resp.json()
    return success_response(data={"text": result.get("text", "")})
