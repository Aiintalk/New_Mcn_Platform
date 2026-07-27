"""
app/evaluation/adapters/base.py

LLMAdapter 接口（Protocol）：评测模块对 LLM 调用方的抽象。

一期仅 YunwuAdapter 实现；二期加 GeminiAdapter/KimiAdapter 时只需新增 adapter 文件 +
在 registry 注册，不动 generator/scorer/runner 调用代码（spec §2.9.3）。

关键：adapter.chat 由 runner（持 db）调用，db 作为参数注入；adapter 模块本身不 import
AsyncSessionLocal，因此无需注册到 conftest 的 _SESSION_LOCAL_PATCH_TARGETS。
"""
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM 适配器接口：把 model_id/provider/credentials 等差异收口到一层。"""

    async def chat(
        self,
        *,
        messages: list[dict],
        model_id: str,
        db: AsyncSession,
        provider: str = "yunwu",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_body: dict | None = None,
    ) -> str:
        """非流式对话，返回 assistant 回复文本。"""
        ...
