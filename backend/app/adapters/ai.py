"""
app/adapters/ai.py

AI 服务适配器：
- 使用 Key 池选取 Credential（provider="ai"）
- 直接 httpx POST，不依赖 OpenAI SDK
- 并发限制 Semaphore(3)（全局）
- 超时 120s
- 成功/失败后回报 CredentialSelector，并写入 external_service_logs
"""
import asyncio
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import ExternalServiceLog
from app.services.credential_selector import pick_credential, report_failure, report_success

# 全局并发限制
_semaphore = asyncio.Semaphore(3)


async def chat(
    messages: list[dict],
    db: AsyncSession,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    task_id: int | None = None,
) -> str:
    """
    调用 AI 接口，返回 assistant 消息内容。

    Args:
        messages: OpenAI 格式的消息列表，如 [{"role": "user", "content": "..."}]
        db: AsyncSession（用于 Key 池和日志）
        model: 可选，默认从 Key 的 config 中读取
        temperature: 采样温度
        max_tokens: 最大 token 数
        task_id: 关联任务 ID（可选）

    Returns:
        str: AI 返回的文本内容

    Raises:
        RuntimeError: 无可用 Key 或调用失败
    """
    credential = await pick_credential(provider="ai", db=db, model=model)

    config = credential.config or {}
    actual_model = model or config.get("model", "claude-haiku-4-5-20251001")
    base_url = config.get("base_url", "https://yunwu.ai/v1")
    api_key = credential.secret_enc  # Sprint 3: secret_enc 存储明文 API Key

    payload = {
        "model": actual_model,
        "messages": messages,
        "temperature": config.get("temperature", temperature),
        "max_tokens": config.get("max_tokens", max_tokens),
    }

    start = time.monotonic()
    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                tokens_used = usage.get("total_tokens")
                duration_ms = int((time.monotonic() - start) * 1000)

                await report_success(credential.id, db)

                db.add(ExternalServiceLog(
                    service="ai",
                    action="chat",
                    task_id=task_id,
                    credential_id=credential.id,
                    tokens_used=tokens_used,
                    duration_ms=duration_ms,
                    status="success",
                ))
                await db.commit()

                return content
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            await report_failure(credential.id, db)

            db.add(ExternalServiceLog(
                service="ai",
                action="chat",
                task_id=task_id,
                credential_id=credential.id,
                tokens_used=None,
                duration_ms=duration_ms,
                status="error",
                error_message=str(e)[:500],
            ))
            await db.commit()

            raise RuntimeError(f"AI call failed: {e}") from e


async def test_connection(db: AsyncSession) -> dict:
    """
    测试 AI 连通性。

    Returns:
        {"status": "ok", "model": "...", "latency_ms": 123, "reply": "..."}
        或
        {"status": "error", "latency_ms": 123, "error": "..."}
    """
    start = time.monotonic()
    try:
        credential = await pick_credential(provider="ai", db=db)
        config = credential.config or {}
        actual_model = config.get("model", "claude-haiku-4-5-20251001")

        reply = await chat(
            messages=[{"role": "user", "content": "Say 'hello' in one word."}],
            db=db,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "ok",
            "model": actual_model,
            "latency_ms": latency_ms,
            "reply": reply,
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e),
        }
