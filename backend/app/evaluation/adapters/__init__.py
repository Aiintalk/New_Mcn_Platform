"""
app/evaluation/adapters/__init__.py

LLM 适配器抽象层（v2）：
- base.LLMAdapter：Protocol 接口（chat / chat_stream）
- yunwu.YunwuAdapter：一期唯一实现，委托现有 app.adapters.yunwu
- registry.get(adapter_name) -> LLMAdapter：归 runner 用（一期恒返回 YunwuAdapter）

generator/scorer 仍是纯函数，不经 registry（spec §2.9.3）。
"""
from app.evaluation.adapters.base import LLMAdapter
from app.evaluation.adapters.registry import get_adapter
from app.evaluation.adapters.yunwu import YunwuAdapter

__all__ = ["LLMAdapter", "YunwuAdapter", "get_adapter"]
