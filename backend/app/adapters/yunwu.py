"""
app/adapters/yunwu.py

多服务商 AI Key 池适配器：
- 按 provider 筛选对应的 Key 池（yunwu / siliconflow / glm 等）
- 原子操作选取并发未满的 Key（active_requests < max_concurrent）
- 请求前 active_requests +1，结束后 -1（成功或失败均执行）
- 无槽位时进入 asyncio.Queue 排队等待，超过 30 秒抛 TimeoutError
- _release 时自动唤醒队列中的下一个等待者
- 每次调用写入 ai_call_logs
- 暴露 chat() 供路由和业务层调用
- 暴露 chat_stream() 供 SSE 流式场景调用
- 暴露 get_queue_length() 供 stats 接口读取
"""
import asyncio
import json
import os
import time
from collections.abc import AsyncGenerator

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import AiCallLog

_DEFAULT_BASE_URLS = {
    "yunwu":       os.getenv("YUNWU_BASE_URL",       "https://yunwu.ai/v1"),
    "siliconflow": os.getenv("SILICONFLOW_BASE_URL",  "https://api.siliconflow.cn/v1"),
    "glm":         os.getenv("GLM_BASE_URL",          "https://open.bigmodel.cn/api/paas/v4"),
}
_HTTP_TIMEOUT  = 60
_STREAM_TIMEOUT = 300  # 流式生成超时（秒），人格定位等长输出场景
_QUEUE_TIMEOUT = 30   # 排队等待上限（秒）
_STALE_LOCK_SECS = 360  # 僵尸锁超时（秒）：active_requests > 0 但 updated_at 超过此时间的视为泄漏

# 全局等待队列：存放 Future，每个代表一个等待槽位的请求
_wait_queue: asyncio.Queue = asyncio.Queue()


def get_queue_length() -> int:
    """返回当前排队等待槽位的请求数（供 stats 接口读取）。"""
    return _wait_queue.qsize()


async def _pick_and_lock(db: AsyncSession, provider: str) -> tuple[int, str, str] | None:
    """
    原子操作：按 provider 选取 active_requests < max_concurrent 的 Key 并将其 +1。
    使用子查询 + FOR UPDATE SKIP LOCKED 防止并发竞争。
    自动清理僵尸锁：active_requests > 0 但 updated_at 超过 _STALE_LOCK_SECS 的凭证重置为 0。
    返回 (credential_id, api_key, base_url)，无可用 Key 时返回 None。
    """
    # 先清理僵尸锁：超时未释放的凭证视为泄漏，重置 active_requests
    await db.execute(text("""
        UPDATE credentials
        SET active_requests = 0,
            updated_at      = NOW()
        WHERE provider        = :provider
          AND active_requests > 0
          AND updated_at      < NOW() - INTERVAL '%s seconds'
    """ % _STALE_LOCK_SECS), {"provider": provider})

    fallback = _DEFAULT_BASE_URLS.get(provider, _DEFAULT_BASE_URLS["yunwu"])
    row = (await db.execute(text("""
        UPDATE credentials
        SET active_requests = active_requests + 1,
            updated_at      = NOW()
        WHERE id = (
            SELECT id FROM credentials
            WHERE  provider        = :provider
              AND  status          = 'active'
              AND  active_requests < max_concurrent
            ORDER BY active_requests ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, api_key, COALESCE(base_url, :fallback)
    """), {"provider": provider, "fallback": fallback})).fetchone()
    return (row[0], row[1], row[2]) if row else None


async def _release(credential_id: int, db: AsyncSession) -> None:
    """
    请求结束后将 active_requests -1。
    释放后唤醒队列中的第一个等待者，让它重新尝试获取槽位。
    """
    await db.execute(text("""
        UPDATE credentials
        SET active_requests = GREATEST(active_requests - 1, 0),
            updated_at      = NOW()
        WHERE id = :id
    """), {"id": credential_id})

    # 唤醒下一个排队请求（跳过已取消的 future）
    while not _wait_queue.empty():
        try:
            fut = _wait_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if not fut.done():
            fut.set_result(True)
            break


async def chat(
    messages: list[dict],
    db: AsyncSession,
    model_id: str,
    provider: str = "yunwu",
    user_id: int | None = None,
    feature: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    extra_body: dict | None = None,
) -> str:
    """
    调用指定服务商的 AI 完成对话，返回 assistant 回复文本。
    按 provider 从对应 Key 池选取可用 Key。

    extra_body: 合并到请求 JSON body（如 extended thinking 参数）。
    无槽位时最多等待 30 秒（_QUEUE_TIMEOUT）。

    Raises:
        RuntimeError: 无可用 Key、排队超时或请求失败
    """
    picked = await _pick_and_lock(db, provider)

    if picked is None:
        # 无可用槽位 → 入队等待
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        await _wait_queue.put(fut)
        try:
            await asyncio.wait_for(fut, timeout=_QUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            fut.cancel()
            raise RuntimeError(
                f"No available AI key for provider '{provider}': "
                f"queue timeout after {_QUEUE_TIMEOUT}s"
            )
        # 被唤醒后重试
        picked = await _pick_and_lock(db, provider)
        if picked is None:
            raise RuntimeError(
                f"No available AI key for provider '{provider}' after queue wait"
            )

    credential_id, api_key, base_url = picked
    # 提交 +1，让其他协程可见
    await db.commit()

    start = time.monotonic()
    input_tokens: int | None  = None
    output_tokens: int | None = None
    status        = "success"
    error_message: str | None = None

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            payload: dict = {
                "model":       model_id,
                "messages":    messages,
                "temperature": temperature,
                "max_tokens":  max_tokens,
            }
            if extra_body:
                payload.update(extra_body)
            response = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage         = data.get("usage") or {}
        input_tokens  = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        return content

    except Exception as e:
        status        = "error"
        error_message = str(e)[:500]
        raise RuntimeError(f"chat failed [{provider}]: {e}") from e

    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        await _release(credential_id, db)
        db.add(AiCallLog(
            user_id=user_id,
            feature=feature,
            model_id=model_id,
            credential_id=credential_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        ))
        await db.commit()


async def chat_stream(
    messages: list[dict],
    db: AsyncSession,
    model_id: str,
    provider: str = "yunwu",
    user_id: int | None = None,
    feature: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    extra_body: dict | None = None,
) -> AsyncGenerator[str, None]:
    """
    SSE 流式调用 AI，逐 chunk yield content 文本。
    复用 _pick_and_lock / _release 凭证池逻辑。
    流完成后写 AiCallLog。

    用法:
        async for chunk in chat_stream(messages, db, model_id, ...):
            yield chunk  # 传入 StreamingResponse
    """
    picked = await _pick_and_lock(db, provider)

    if picked is None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        await _wait_queue.put(fut)
        try:
            await asyncio.wait_for(fut, timeout=_QUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            fut.cancel()
            raise RuntimeError(
                f"No available AI key for provider '{provider}': "
                f"queue timeout after {_QUEUE_TIMEOUT}s"
            )
        picked = await _pick_and_lock(db, provider)
        if picked is None:
            raise RuntimeError(
                f"No available AI key for provider '{provider}' after queue wait"
            )

    credential_id, api_key, base_url = picked
    await db.commit()

    start = time.monotonic()
    input_tokens: int | None = None
    output_tokens: int | None = None
    status = "success"
    error_message: str | None = None

    try:
        payload: dict = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if extra_body:
            payload.update(extra_body)

        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens")
                        output_tokens = usage.get("completion_tokens")
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
    except Exception as e:
        status = "error"
        error_message = str(e)[:500]
        raise RuntimeError(f"chat_stream failed [{provider}]: {e}") from e

    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        await _release(credential_id, db)
        db.add(AiCallLog(
            user_id=user_id,
            feature=feature,
            model_id=model_id,
            credential_id=credential_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        ))
        await db.commit()
