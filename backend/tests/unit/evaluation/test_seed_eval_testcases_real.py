"""
test_seed_eval_testcases_real.py — 张翀真实测试集 seed 脚本的数据契约测试。

不连库（数据契约静态校验），放 tests/unit/evaluation/：
- REAL_CASES 结构：10 条、name 唯一、4 输入字段非空、无 messages
- tags：含 '真实数据' 溯源 tag；前 3 条含钩子标签
- 源文件一致性锚点：抽关键行的字段与源 .et 转换内容对齐（防手改脚本时误伤数据）
- 迁移 057 存在且含剥离/停用语句
"""
from collections import Counter
from pathlib import Path

# seed 脚本不在包内，按路径加载；只执行到 REAL_CASES 定义为止
# （脚本尾部 import app.* 依赖后端运行环境，单测环境不引入）
_SEED = Path(__file__).resolve().parents[3] / "scripts" / "seed_eval_testcases_real.py"


def _load_cases():
    assert _SEED.exists(), f"seed 脚本不存在: {_SEED}"
    src = _SEED.read_text(encoding="utf-8")
    ns: dict = {"__file__": str(_SEED)}
    compiled = compile(src.split("async def main")[0], str(_SEED), "exec")
    exec(compiled, ns)  # noqa: S102 - 只执行常量定义段，无外部输入
    return ns["REAL_CASES"]


class TestRealCasesContract:
    def test_ten_cases_unique_names(self):
        cases = _load_cases()
        assert len(cases) == 10
        names = [c["name"] for c in cases]
        assert len(set(names)) == 10

    def test_input_fields_present(self):
        for c in _load_cases():
            for k in ("kol", "persona", "product_info", "original_script"):
                assert isinstance(c[k], str) and c[k].strip(), f"{c['name']} 缺 {k}"

    def test_source_traceability_tags(self):
        for c in _load_cases():
            assert "真实数据" in c["tags"], f"{c['name']} 缺溯源 tag"
            assert "demo" not in c["tags"]

    def test_no_messages_anywhere(self):
        # 方案 A：数据结构本身不含指令字段
        for c in _load_cases():
            assert "messages" not in c

    def test_hook_tags_first_three(self):
        cases = _load_cases()
        # R1 羊羊面膜：标签拆分数组（含"直白接地气的口语化表达"等）
        assert "直白接地气的口语化表达" in cases[0]["tags"]
        # R5 姜周周：含"强情绪价值"
        assert any("强情绪价值" in t for t in cases[4]["tags"])

    def test_kol_distribution(self):
        kols = Counter(c["kol"] for c in _load_cases())
        assert kols == {"羊羊": 3, "暖暖": 3, "姜周周": 2, "可可": 2}

    def test_content_anchor_rows(self):
        """源文件一致性锚点：关键行内容与 .et 转换结果逐字对齐（防误改）。"""
        cases = _load_cases()
        r1 = cases[0]
        assert r1["kol"] == "羊羊"
        assert r1["product_info"].startswith("韩国 OLIVE YOUNG 热销的美迪惠尔")
        assert r1["original_script"].startswith("我把美迪惠尔面膜砍到一盒18块钱")
        r5 = cases[4]
        assert r5["kol"] == "姜周周"
        assert "PMPM" in r5["product_info"] or "pmpm" in r5["product_info"]
        r10 = cases[9]
        assert r10["kol"] == "可可"
        assert "绿豆" in r10["product_info"]

    def test_migration_057_exists(self):
        mig = _SEED.parents[1] / "migrations" / "057_eval_testcases_real_data.sql"
        assert mig.exists()
        sql = mig.read_text(encoding="utf-8")
        assert "input_payload - 'messages'" in sql
        assert "'demo' = ANY(tags)" in sql
