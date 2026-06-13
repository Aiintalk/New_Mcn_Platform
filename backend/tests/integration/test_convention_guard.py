"""
规范防御测试 — 自动扫描所有 router 文件，验证开发红线遵守情况。

本测试是静态代码分析（AST + 文本模式匹配），不依赖数据库连接，
可以单独运行：pytest tests/integration/test_convention_guard.py -v

拦截的红线（对应 CLAUDE.md 第十二节）：
  #1 非流式接口必须返回标准信封（success_response / error_response）
  #2 鉴权接口的写操作（POST/PUT/PATCH/DELETE + db.commit）必须有 OperationLog
  #6 AiCallLog 由 adapter 层负责，router 中不应直接写 AiCallLog
  #7 导入 AsyncSessionLocal 的 router 必须注册到 conftest.py 的 patch 列表

豁免规则：
  - 流式接口（StreamingResponse）、文件下载（FileResponse / Response）豁免信封检查
  - 公开接口（无 current_user / require_admin 等鉴权依赖）豁免 OperationLog 检查
  - GET 查询不触发 OperationLog 检查（只检查写操作）
  - helper 函数（如 _write_op_log）中的 OperationLog 可被调用方继承识别
"""
import ast
import re
from pathlib import Path

import pytest

# Router 源码目录（backend/app/routers/）
ROUTERS_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "routers"

# conftest.py 路径（用于红线 #7 交叉检查）
CONFTEST_PATH = Path(__file__).resolve().parent.parent / "conftest.py"

# 写操作的 HTTP 方法（需要 OperationLog）
_WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})

# 所有需要识别的 HTTP 方法（用于发现路由函数）
_ALL_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

# 鉴权指示器 — 出现任意一个表示该函数需要登录（因此写操作需要 OperationLog）
_AUTH_INDICATORS = (
    "current_user",
    "get_current_user",
    "require_admin",
    "require_operator",
    "require_password_changed",
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _router_files() -> list[Path]:
    """返回所有需要检查的 router 源文件（排除 __init__.py）"""
    return sorted(p for p in ROUTERS_DIR.glob("*.py") if p.name != "__init__.py")


def _get_http_method(func_node: ast.AsyncFunctionDef) -> str | None:
    """
    从 @router.xxx 装饰器中提取 HTTP 方法。
    返回 'get'/'post'/'put'/'patch'/'delete'；非路由函数返回 None。
    """
    for decorator in func_node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Attribute) and func.attr in _ALL_METHODS:
                return func.attr
    return None


def _find_op_log_writers(tree: ast.Module, source: str) -> set[str]:
    """
    扫描文件中所有函数定义（含嵌套），返回函数体内包含 OperationLog 写入的函数名集合。
    用于识别 _write_op_log 这类 helper —— 调用它们的路由函数也算合规。
    """
    writers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(source, node)
            if seg and "OperationLog(" in seg:
                writers.add(node.name)
    return writers


def _is_exempt_from_envelope(func_source: str) -> bool:
    """流式 / 文件下载接口豁免标准信封检查"""
    return (
        "StreamingResponse" in func_source
        or "FileResponse" in func_source
        or re.search(r"\breturn\s+Response\s*\(", func_source) is not None
    )


def _scan_routers() -> list[str]:
    """
    扫描所有 router 文件，返回违规描述列表。
    每条格式: "[文件名:行号] 函数名 (METHOD): 描述 (红线 #N)"

    覆盖红线: #1（标准信封）、#2（OperationLog）、#6（AiCallLog 不在 router）
    """
    violations: list[str] = []

    for filepath in _router_files():
        source = filepath.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            violations.append(f"[{filepath.name}:0] (parse-error): {exc} (红线 #0)")
            continue

        # --- 红线 #6: router 中不应直接写 AiCallLog（由 adapter 层负责） ---
        if "AiCallLog(" in source:
            for i, line in enumerate(source.split("\n"), 1):
                if "AiCallLog(" in line:
                    violations.append(
                        f"[{filepath.name}:{i}]: router 中不应直接写 AiCallLog"
                        f"（应由 adapter 层负责） (红线 #6)"
                    )
                    break  # 每个文件只报第一条

        op_log_writers = _find_op_log_writers(tree, source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            method = _get_http_method(node)
            if method is None:
                continue  # 普通函数（非路由）

            func_source = ast.get_source_segment(source, node) or ""
            location = f"[{filepath.name}:{node.lineno}] {node.name} ({method.upper()})"

            # --- 红线 #1: 非流式接口必须返回标准信封 ---
            if not _is_exempt_from_envelope(func_source):
                has_envelope = (
                    "success_response(" in func_source
                    or "error_response(" in func_source
                )
                if not has_envelope:
                    violations.append(
                        f"{location}: 缺少 success_response/error_response (红线 #1)"
                    )

            # --- 红线 #2: 鉴权写操作必须有 OperationLog ---
            if method in _WRITE_METHODS:
                has_auth = any(ind in func_source for ind in _AUTH_INDICATORS)
                has_commit = ".commit()" in func_source
                has_op_log = "OperationLog(" in func_source or any(
                    f"{name}(" in func_source for name in op_log_writers
                )
                if has_auth and has_commit and not has_op_log:
                    violations.append(
                        f"{location}: 鉴权写操作缺少 OperationLog (红线 #2)"
                    )

    return violations


def _scan_session_local_targets() -> list[str]:
    """
    红线 #7: 导入 AsyncSessionLocal 的 router 必须注册到 conftest.py 的
    _SESSION_LOCAL_PATCH_TARGETS 列表，否则测试时该 router 会连到生产数据库。

    扫描逻辑:
    1. 从 conftest.py 提取已注册的模块路径集合
    2. 遍历 router 文件，检查是否包含 AsyncSessionLocal
    3. 若包含但未注册 → 违规
    """
    if not CONFTEST_PATH.exists():
        return [f"[conftest.py:0]: conftest.py 不存在 ({CONFTEST_PATH}) (红线 #7)"]

    conftest_source = CONFTEST_PATH.read_text(encoding="utf-8")
    registered: set[str] = set(re.findall(
        r'"(app\.[^"]+\.AsyncSessionLocal)"', conftest_source
    ))

    violations: list[str] = []
    for filepath in _router_files():
        source = filepath.read_text(encoding="utf-8")
        if "AsyncSessionLocal" not in source:
            continue
        module_path = f"app.routers.{filepath.stem}.AsyncSessionLocal"
        if module_path not in registered:
            violations.append(
                f"[{filepath.name}:0]: 导入了 AsyncSessionLocal 但未注册到 "
                f"tests/conftest.py 的 _SESSION_LOCAL_PATCH_TARGETS "
                f"（缺 '{module_path}'） (红线 #7)"
            )
    return violations


# ---------------------------------------------------------------------------
# Session-scoped fixture：全量扫描只执行一次
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def convention_violations() -> list[str]:
    """扫描所有 router 文件 + conftest.py，返回违规列表（session 级缓存）"""
    return _scan_routers() + _scan_session_local_targets()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestConventionGuard:
    """开发红线自动化守卫 — 对应 CLAUDE.md 第十二节 §12 #1 #2"""

    def test_routers_directory_has_files(self):
        """前置检查: router 目录存在且包含源文件"""
        assert ROUTERS_DIR.exists(), f"Router 目录不存在: {ROUTERS_DIR}"
        files = _router_files()
        assert len(files) >= 10, f"Router 目录文件过少（{len(files)} 个），可能路径错误"

    def test_no_bare_dict_returns(self, convention_violations: list[str]):
        """红线 #1: 所有非流式/非文件路由必须返回标准信封 success_response/error_response"""
        bare = [v for v in convention_violations if "红线 #1" in v]
        if bare:
            report = "\n".join(f"  - {v}" for v in bare)
            pytest.fail(
                f"发现 {len(bare)} 处响应格式违规。\n"
                f"非流式接口必须用 success_response(data=...) 或 error_response(...) 返回，"
                f"不得返回裸 dict。(见 CLAUDE.md §12 #1)\n\n{report}"
            )

    def test_write_ops_have_operation_log(self, convention_violations: list[str]):
        """红线 #2: 所有鉴权写操作（POST/PUT/PATCH/DELETE + commit）必须有 OperationLog"""
        missing = [v for v in convention_violations if "红线 #2" in v]
        if missing:
            report = "\n".join(f"  - {v}" for v in missing)
            pytest.fail(
                f"发现 {len(missing)} 处缺少 OperationLog。\n"
                f"鉴权接口的写操作必须记录 OperationLog（直接 db.add 或通过 helper）。"
                f"(见 CLAUDE.md §12 #2)\n\n{report}"
            )

    def test_no_aicalllog_in_routers(self, convention_violations: list[str]):
        """红线 #6: AiCallLog 由 adapter 层负责，router 中不应直接写"""
        aicl = [v for v in convention_violations if "红线 #6" in v]
        if aicl:
            report = "\n".join(f"  - {v}" for v in aicl)
            pytest.fail(
                f"发现 {len(aicl)} 处 AiCallLog 违规。\n"
                f"router 中不应直接写 AiCallLog（由 adapter 层在 finally 中自动写入）。"
                f"(见 CLAUDE.md §12 #6)\n\n{report}"
            )

    def test_session_local_registered(self, convention_violations: list[str]):
        """红线 #7: 导入 AsyncSessionLocal 的 router 必须注册到 conftest.py"""
        unreg = [v for v in convention_violations if "红线 #7" in v]
        if unreg:
            report = "\n".join(f"  - {v}" for v in unreg)
            pytest.fail(
                f"发现 {len(unreg)} 处未注册的 AsyncSessionLocal 导入。\n"
                f"router 内部直接导入 AsyncSessionLocal 的，必须在 tests/conftest.py 的 "
                f"_SESSION_LOCAL_PATCH_TARGETS 中注册，否则测试时会连到生产数据库。"
                f"(见 CLAUDE.md §12 #7)\n\n{report}"
            )

    def test_scan_summary(self, convention_violations: list[str]):
        """汇总: 当前违规总数应为 0（用于快速定位回归）"""
        if convention_violations:
            by_rule = {}
            for v in convention_violations:
                if "红线 #1" in v:
                    tag = "红线 #1"
                elif "红线 #2" in v:
                    tag = "红线 #2"
                elif "红线 #6" in v:
                    tag = "红线 #6"
                elif "红线 #7" in v:
                    tag = "红线 #7"
                else:
                    tag = "其他"
                by_rule[tag] = by_rule.get(tag, 0) + 1
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_rule.items()))
            pytest.fail(f"规范违规汇总（{summary}），详见上方测试的详细输出")
