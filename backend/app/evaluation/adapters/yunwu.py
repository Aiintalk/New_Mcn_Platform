"""
app/evaluation/adapters/yunwu.py

YunwuAdapter —— 一期唯一启用的 LLM 适配器实现。

委托现有 app.adapters.yunwu.chat（模块级 async 函数），db 作参数传入，不自开 session，
不 import AsyncSessionLocal（spec §2.9.3）。AiCallLog 由现有 yunwu.chat 的 finally 写，
本 adapter 不重复写。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu


class YunwuAdapter:
    """LLMAdapter 实现：转发到 app.adapters.yunwu.chat。"""

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
        """委托给 app.adapters.yunwu.chat 模块级 async 函数。

        现有 yunwu.chat 签名：
            chat(messages, db, model_id, provider="yunwu", user_id=None, feature=None,
                 temperature=0.7, max_tokens=4096, extra_body=None) -> str
        """
        return await yunwu.chat(
            messages,
            db,
            model_id,
            provider,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
