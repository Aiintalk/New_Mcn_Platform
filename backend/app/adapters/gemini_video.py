"""Gemini Files API 完整视频适配器。

凭证只从统一 ``credentials`` 表选择（provider=gemini）。这里刻意只接收
完整视频文件路径，不能传关键帧、转录文本或任何降级模式。
"""
import asyncio
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as credential_pool
from app.models.log import AiCallLog, ExternalServiceLog

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_POLL_SECONDS = 2


async def _file_bytes(path: Path) -> AsyncGenerator[bytes, None]:
    """按块读取，避免 500MB 视频被一次性放进应用内存。"""
    with path.open("rb") as source:
        while chunk := await asyncio.to_thread(source.read, _UPLOAD_CHUNK_BYTES):
            yield chunk


def _file_name(file_data: dict) -> str:
    name = file_data.get("name") or ""
    if not name and file_data.get("uri"):
        name = str(file_data["uri"]).split("/")[-1]
    return str(name).removeprefix("v1beta/")


async def _upload_complete_video(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    path: Path,
    content_type: str,
    display_name: str,
) -> dict:
    size = path.stat().st_size
    init = await client.post(
        f"{base_url}/upload/v1beta/files",
        params={"key": api_key},
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": content_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": display_name}},
    )
    init.raise_for_status()
    upload_url = init.headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError("Gemini Files API 未返回视频上传地址")

    uploaded = await client.post(
        upload_url,
        headers={
            "Content-Length": str(size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        content=_file_bytes(path),
    )
    uploaded.raise_for_status()
    file_data = (uploaded.json() or {}).get("file")
    if not isinstance(file_data, dict) or not file_data.get("uri"):
        raise RuntimeError("Gemini Files API 未返回完整视频引用")
    return file_data


async def _wait_until_active(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    file_data: dict,
    timeout_seconds: int,
) -> dict:
    name = _file_name(file_data)
    if not name:
        raise RuntimeError("Gemini 视频文件标识缺失")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = await client.get(f"{base_url}/v1beta/{name}", params={"key": api_key})
        response.raise_for_status()
        current = (response.json() or {}).get("file") or response.json()
        state = str(current.get("state") or "").upper()
        if state == "ACTIVE":
            return current
        if state == "FAILED":
            raise RuntimeError("Gemini 完整视频处理失败")
        await asyncio.sleep(_POLL_SECONDS)
    raise TimeoutError("Gemini 完整视频处理超时")


async def _delete_file(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    file_data: dict,
) -> None:
    name = _file_name(file_data)
    if not name:
        return
    response = await client.delete(f"{base_url}/v1beta/{name}", params={"key": api_key})
    response.raise_for_status()


def _stream_text(line: str) -> str:
    if not line.startswith("data: "):
        return ""
    data = line[6:].strip()
    if data == "[DONE]":
        return ""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return ""
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    return "".join(str(part.get("text") or "") for part in parts)


async def stream_full_video_analysis(
    *,
    original_path: Path,
    edited_path: Path,
    original_content_type: str,
    edited_content_type: str,
    system_prompt: str,
    model_id: str,
    db: AsyncSession,
    user_id: int,
    task_id: int,
    timeout_seconds: int = 600,
) -> AsyncGenerator[str, None]:
    """上传两条完整视频，轮询 Gemini 后流式返回报告；无降级分支。"""
    picked = await credential_pool._pick_and_lock(db, "gemini")
    if picked is None:
        raise RuntimeError("未配置可用的 Gemini 统一凭证")
    credential_id, api_key, configured_base_url = picked
    await db.commit()

    base_url = configured_base_url.rstrip("/")
    uploaded: list[dict] = []
    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    try:
        timeout = httpx.Timeout(timeout_seconds, connect=30)
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield "__STATUS__正在上传原片到 Gemini Files...\n"
            original_file = await _upload_complete_video(
                client,
                base_url=base_url,
                api_key=api_key,
                path=original_path,
                content_type=original_content_type,
                display_name="原片",
            )
            uploaded.append(original_file)

            yield "__STATUS__正在上传剪辑成片到 Gemini Files...\n"
            edited_file = await _upload_complete_video(
                client,
                base_url=base_url,
                api_key=api_key,
                path=edited_path,
                content_type=edited_content_type,
                display_name="剪辑成片",
            )
            uploaded.append(edited_file)

            yield "__STATUS__正在等待两条完整视频处理完成...\n"
            original_file, edited_file = await asyncio.gather(
                _wait_until_active(client, base_url=base_url, api_key=api_key, file_data=original_file, timeout_seconds=timeout_seconds),
                _wait_until_active(client, base_url=base_url, api_key=api_key, file_data=edited_file, timeout_seconds=timeout_seconds),
            )

            yield "__STATUS__Gemini 正在分析两条完整视频...\n"
            request_body = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": "第一条是原片，请完整读取。"},
                        {"file_data": {"mime_type": original_content_type, "file_uri": original_file["uri"]}},
                        {"text": "第二条是剪辑成片，请完整读取。"},
                        {"file_data": {"mime_type": edited_content_type, "file_uri": edited_file["uri"]}},
                        {"text": "请输出分镜分析、三维评分、对比结论和可执行剪辑优化建议。"},
                    ],
                }],
                "generationConfig": {"maxOutputTokens": 8192},
            }
            async with client.stream(
                "POST",
                f"{base_url}/v1beta/models/{model_id}:streamGenerateContent",
                params={"key": api_key, "alt": "sse"},
                json=request_body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if content := _stream_text(line):
                        yield content
    except Exception as exc:
        status = "error"
        error_message = str(exc)[:500]
        raise
    finally:
        try:
            async with httpx.AsyncClient(timeout=30) as cleanup_client:
                for file_data in uploaded:
                    try:
                        await _delete_file(cleanup_client, base_url=base_url, api_key=api_key, file_data=file_data)
                    except Exception as cleanup_error:
                        db.add(ExternalServiceLog(
                            service="gemini",
                            action="qianchuan_preview_full_video_cleanup",
                            task_id=task_id,
                            credential_id=None,
                            request_body={"gemini_file": _file_name(file_data)},
                            status="error",
                            error_message=str(cleanup_error)[:500],
                        ))
        finally:
            await credential_pool._release(credential_id, db)
            latency_ms = int((time.monotonic() - start) * 1000)
            db.add(AiCallLog(
                user_id=user_id,
                feature="qianchuan_preview_full_video",
                model_id=model_id,
                credential_id=credential_id,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
            ))
            db.add(ExternalServiceLog(
                service="gemini",
                action="qianchuan_preview_full_video",
                task_id=task_id,
                credential_id=None,
                request_body={"mode": "full_video", "file_count": 2},
                duration_ms=latency_ms,
                status=status,
                error_message=error_message,
            ))
            await db.commit()
