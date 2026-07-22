"""
app/evaluation/adapters/registry.py

adapter_registry：runner（Phase 3）经 get(adapter_name) 取适配器，
分别用被测 model_id 绑 generate_fn、评委 model_id 绑 score_fn，注入 generator/scorer
（generator/scorer 仍是纯函数，不经 registry）。

一期只注册 yunwu 一个实现；二期加 Gemini/Kimi 时只需 _REGISTRY 表加一行 + 新 adapter 文件。
"""
from app.evaluation.adapters.base import LLMAdapter
from app.evaluation.adapters.yunwu import YunwuAdapter

# 一期唯一适配器；二期扩展时在此登记
_REGISTRY: dict[str, type] = {
    "yunwu": YunwuAdapter,
}


def get_adapter(adapter_name: str) -> LLMAdapter:
    """按名取适配器实例。一期恒返回 YunwuAdapter。

    归 runner 用（spec §2.9.3）：runner 取适配器 → 用被测 model_id 绑 generate_fn、
    用评委 model_id 绑 score_fn → 注入 generator/scorer（G/S 不经此 registry）。
    """
    cls = _REGISTRY.get(adapter_name)
    if cls is None:
        raise KeyError(
            f"Unknown adapter: {adapter_name!r}. Registered: {sorted(_REGISTRY)}"
        )
    return cls()
