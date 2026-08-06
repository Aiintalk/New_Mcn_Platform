"""
seed_eval_testcases_demo.py — 评测 demo 测试集（多元化占位数据）+ 维护机制。

【用途】
- 给评测系统灌一套**多元化的 demo 测试例**（覆盖不同达人/钩子类型/品类/合规场景），
  用来跑通系统 + 冒烟验证。**不是真实业务数据**——等张翀给真实测试例后替换。
- 所有 demo case 带 `'demo'` tag，便于识别 + 定向清理（真数据不会被误删）。

【维护（这就是"临时测试数据怎么管"的方案）】
- demo 测试例的**唯一来源 = 本脚本**（可重跑，幂等 upsert by name）。
- 新增/修改 demo case：编辑本脚本的 `DEMO_CASES` → 重跑 `python scripts/seed_eval_testcases_demo.py`。
- 重置（清掉所有 demo case 重灌）：
    DELETE FROM eval_case_jobs WHERE run_id IN (SELECT id FROM eval_runs);
    DELETE FROM eval_scores WHERE case_result_id IN (SELECT id FROM eval_case_results);
    DELETE FROM eval_case_results;
    DELETE FROM eval_test_cases WHERE 'demo' = ANY(tags);   -- 只删 demo，真数据保留
    python scripts/seed_eval_testcases_demo.py               -- 重灌
- 真实测试例（张翀的，不带 'demo' tag）**永不被本脚本或上面的清理影响**。

【多元化覆盖】（13 条：原 5 + 本脚本新增 8）
- 达人：慧敏（亲和种草）、桃园（直男测评/理性）、宝妈小雅（认证党）
- 钩子：焦虑/痛点/诱惑/效果/场景/对比/权威/故事/测评/恐吓/价格
- 品类：美妆/护肤/减肥/零食/家居/3C/母婴/食品/家纺/服装/教育/个护
- 合规：普通食品/婴幼儿国标/防晒特证/化妆品/医疗器械边界
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401  # 注册全部模型（User 等），让 eval FK 能解析
from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER
from app.evaluation.models import EvalTestCase

TOOL = EVAL_TOOL_QIANCHUAN_WRITER

# ---------------------------------------------------------------------------
# 新增 8 条多元化 demo case（原 5 条在 seed_eval_demo.sql，本脚本会给它们补 'demo' tag）
# ---------------------------------------------------------------------------

DEMO_CASES = [
    {
        "name": "对比型 · 降噪蓝牙耳机（3C 数码）",
        "description": "前后对比：旧耳机杂音 vs 主动降噪；参数党理性风",
        "persona_name": "桃园",
        "persona": "测评博主桃园：直男参数党、理性不夸张、擅长数据对比",
        "product_info": (
            "主动降噪蓝牙耳机（入耳式）\n"
            "降噪深度 -42dB（对标某牌 699 款）\n"
            "续航：单次 8h + 充电盒共 32h\n"
            "蓝牙 5.3，低延迟；IPX5 防汗\n"
            "价格：首发 199（对标款零头）"
        ),
        "original_script": (
            "【0-5s】这个降噪，我直接拿地铁测给你看。\n"
            "【5-25s】开启瞬间，地铁轰鸣没了。-42dB 主动降噪，对标某牌 699 的效果。\n"
            "【25-45s】续航 8 小时，充电盒再续 32 小时。蓝牙 5.3，打游戏不卡。\n"
            "【45-60s】首发 199，对标款零头，冲！"
        ),
        "messages": "仿写降噪蓝牙耳机千川文案，地铁实测降噪对比开头，主打 -42dB 降噪+续航+蓝牙 5.3，对标某牌 699 只要 199，60 秒。",
        "tags": ["对比型", "3C", "耳机", "降噪"],
    },
    {
        "name": "权威背书型 · 婴儿纸尿裤（母婴）",
        "description": "认证背书：SGS 0 荧光剂 + 国标；不贩卖焦虑、不承诺防红屁屁",
        "persona_name": "宝妈小雅",
        "persona": "理科妈妈宝妈小雅：看重认证、不贩卖焦虑、讲证据",
        "product_info": (
            "婴儿纸尿裤（NB/S/M/L）\n"
            "SGS 认证：0 荧光剂 0 甲醛\n"
            "日本住友高分子，吸得锁得住\n"
            "3D 立体防漏 + 透气底膜\n"
            "执行 GB/T 28004 婴幼儿国标\n"
            "合规红线：不承诺防红屁屁（因人而异，非医疗）\n"
            "价格：99/箱（56 片）"
        ),
        "original_script": (
            "【0-5s】给娃选纸尿裤，我只看两样。\n"
            "【5-25s】SGS 报告：0 荧光剂 0 甲醛。日本住友高分子，吸得锁得住。\n"
            "【25-45s】3D 立体防漏，透气底膜，娃不红屁屁。\n"
            "【45-60s】99 块一箱 56 片，执行婴幼儿国标，闭眼囤！"
        ),
        "messages": "仿写婴儿纸尿裤千川文案，选纸尿裤只看两样开头，主打 SGS 认证 0 荧光剂 + 婴幼儿国标，不能承诺防红屁屁（因人而异），60 秒。",
        "tags": ["权威型", "母婴", "纸尿裤", "认证"],
    },
    {
        "name": "故事型 · 冻干速溶咖啡（食品）",
        "description": "剧情代入：凌晨加班场景；普通食品不承诺提神功效",
        "persona_name": "慧敏",
        "persona": "韩国欧尼慧敏：亲和种草风、擅长场景代入",
        "product_info": (
            "冻干速溶咖啡（100g/瓶）\n"
            "-40℃ 冻干工艺，保留风味\n"
            "100% 阿拉比卡豆；冷热双溶\n"
            "咖啡因 ≥1.2%\n"
            "合规红线：普通食品，不承诺提神/减肥功效\n"
            "价格：79/瓶，两瓶 129"
        ),
        "original_script": (
            "【0-5s】凌晨两点改方案，全靠这一口。\n"
            "【5-25s】-40 度冻干，热水冷水都秒溶。阿拉比卡，喝起来像现磨。\n"
            "【25-45s】加班、赶 due、带娃熬夜，拧开就喝。\n"
            "【45-60s】79 一瓶，两瓶 129，打工人续命，冲！"
        ),
        "messages": "仿写冻干咖啡千川文案，凌晨加班故事场景开头，主打 -40℃ 冻干+冷热双溶，不能承诺提神功效（普通食品），60 秒。",
        "tags": ["故事型", "食品", "咖啡", "熬夜"],
    },
    {
        "name": "测评型 · 100 支贡缎四件套（家纺）",
        "description": "参数测评：支数/印染；极致性价比",
        "persona_name": "桃园",
        "persona": "测评博主桃园：直男参数党、理性不夸张、擅长数据对比",
        "product_info": (
            "100 支贡缎四件套（纯棉）\n"
            "含：床单 + 被套 + 2 枕套\n"
            "100 支贡缎（亲肤如丝）；活性印染不掉色\n"
            "1.8m/2.0m 床通用\n"
            "价格：199（专柜同品质 600+）"
        ),
        "original_script": (
            "【0-5s】100 支贡缎四件套，199 你敢信？\n"
            "【5-25s】纯棉 100 支，摸起来像真丝。活性印染，洗十次不掉色。\n"
            "【25-45s】1.8/2.0 床通用，一套含被套床单枕套。\n"
            "【45-60s】专柜 600 的品质 199 拿走，冲！"
        ),
        "messages": "仿写贡缎四件套千川文案，100 支 199 你敢信开头，主打 100 支纯棉+活性印染+性价比，60 秒。",
        "tags": ["测评型", "家纺", "床品", "性价比"],
    },
    {
        "name": "恐吓型 · 物理防晒霜（美妆）",
        "description": "风险切入：不防晒老十岁；持国妆特字，不承诺美白",
        "persona_name": "慧敏",
        "persona": "韩国欧尼慧敏：亲和种草风、擅长风险提醒式种草",
        "product_info": (
            "物理防晒霜 SPF50+ PA++++（50ml）\n"
            "氧化锌物理防晒，不含化学防晒剂\n"
            "敏感肌 / 孕妇可用\n"
            "持国妆特字\n"
            "合规红线：化妆品，不承诺美白/医疗功效\n"
            "价格：129/支"
        ),
        "original_script": (
            "【0-5s】不防晒，老十岁不是吓你。\n"
            "【5-25s】SPF50+ PA++++，氧化锌物理防晒，不刺激，敏感肌孕妇能用。\n"
            "【25-45s】持国妆特字，出门前涂一泵，脸脖子都够。\n"
            "【45-60s】129 一支，养儿不防老先防晒，冲！"
        ),
        "messages": "仿写物理防晒霜千川文案，不防晒老十岁风险开头，主打 SPF50+ 物理防晒+敏感肌可用+国妆特字，不能承诺美白功效，60 秒。",
        "tags": ["恐吓型", "美妆", "防晒", "特证"],
    },
    {
        "name": "价格型 · 法式茶歇连衣裙（服装）",
        "description": "极致性价比：专柜款十分之一价",
        "persona_name": "桃园",
        "persona": "测评博主桃园：理性省钱、擅长算账式种草",
        "product_info": (
            "法式茶歇连衣裙\n"
            "修身 V 领 + 收腰显腿长；雪纺垂顺不透\n"
            "尺码 S-XL\n"
            "价格：89（专柜同款 800+）"
        ),
        "original_script": (
            "【0-5s】专柜 800 的款，89 拿走。\n"
            "【5-25s】法式茶歇版型，腰线收得刚好，显腿长。雪纺垂顺不透。\n"
            "【25-45s】S 到 XL 都有，通勤约会都能穿。\n"
            "【45-60s】89 一件，专柜零头，冲！"
        ),
        "messages": "仿写法式连衣裙千川文案，专柜 800 的款 89 拿走价格开头，主打版型显瘦+雪纺不透+性价比，60 秒。",
        "tags": ["价格型", "服装", "连衣裙", "性价比"],
    },
    {
        "name": "场景型 · 儿童护眼学习桌（母婴/教育）",
        "description": "陪读场景；不承诺提升成绩/预防近视（医疗器械边界）",
        "persona_name": "宝妈小雅",
        "persona": "理科妈妈宝妈小雅：看重认证、不贩卖焦虑、讲证据",
        "product_info": (
            "儿童可升降学习桌（含椅）\n"
            "桌面 0-60° 倾斜；坐姿矫正椅背\n"
            "环保 E0 级板材\n"
            "合规红线：不能承诺提升成绩/预防近视（属医疗器械/医疗功效范畴）\n"
            "价格：599（连桌带椅）"
        ),
        "original_script": (
            "【0-5s】陪娃写作业，他趴桌我看不下去。\n"
            "【5-25s】这张学习桌能升降，桌面 0 到 60 度倾斜，娃坐得直了。\n"
            "【25-45s】E0 环保板，没味道。椅子带坐姿矫正。\n"
            "【45-60s】599 连桌带椅，娃坐得正，妈少操心！"
        ),
        "messages": "仿写儿童学习桌千川文案，陪娃写作业趴桌场景开头，主打可升降+坐姿矫正+E0 环保，不能承诺提升成绩或预防近视，60 秒。",
        "tags": ["场景型", "母婴", "学习桌", "护眼"],
    },
    {
        "name": "效果型 · 氨基酸洗发水（个护）",
        "description": "效果对比：毛躁→顺滑；化妆品不承诺生发",
        "persona_name": "慧敏",
        "persona": "韩国欧尼慧敏：亲和种草风、擅长视觉化效果演示",
        "product_info": (
            "氨基酸洗发水（300ml）\n"
            "氨基酸表活，温和不拔干；无硅油\n"
            "蓬松控油\n"
            "合规红线：化妆品，不承诺生发/治疗脱发\n"
            "价格：59 两瓶"
        ),
        "original_script": (
            "【0-5s】看我这毛躁炸毛的头发。\n"
            "【5-25s】换这个氨基酸洗发水，洗完顺滑蓬松。氨基酸表活，温和不拔干。\n"
            "【25-45s】无硅油，油头也能撑两天。\n"
            "【45-60s】59 两瓶，沙发炸毛星人冲！"
        ),
        "messages": "仿写氨基酸洗发水千川文案，毛躁炸毛效果对比开头，主打氨基酸温和+蓬松控油+无硅油，不能承诺生发功效，60 秒。",
        "tags": ["效果型", "个护", "洗发水", "蓬松"],
    },
]


async def main():
    async with AsyncSessionLocal() as db:
        # 1. 给现有 demo case（seed_eval_demo.sql 的 5 条）补 'demo' tag
        existing = (await db.execute(
            select(EvalTestCase).where(EvalTestCase.deleted_at.is_(None))
        )).scalars().all()
        tagged = 0
        for tc in existing:
            tags = list(tc.tags or [])
            if "demo" not in tags:
                tags.append("demo")
                tc.tags = tags
                tagged += 1

        # 2. upsert 新增 8 条（by name）
        inserted = updated = 0
        for c in DEMO_CASES:
            tags = list(c["tags"]) + ["demo"]
            found = (await db.execute(
                select(EvalTestCase).where(EvalTestCase.name == c["name"])
            )).scalar_one_or_none()
            payload = {
                "name": c["persona_name"],
                "persona": c["persona"],
                "product_info": c["product_info"],
                "original_script": c["original_script"],
                "messages": [{"role": "user", "content": c["messages"]}],
            }
            if found is None:
                db.add(EvalTestCase(
                    tool_code=TOOL, name=c["name"], description=c["description"],
                    input_payload=payload, tags=tags, is_active=True,
                ))
                inserted += 1
            else:
                found.description = c["description"]
                found.input_payload = payload
                found.tags = tags
                updated += 1
        await db.commit()

        # 3. 汇总
        all_cases = (await db.execute(
            select(EvalTestCase).where(EvalTestCase.deleted_at.is_(None))
        )).scalars().all()
        demo_n = sum(1 for t in all_cases if "demo" in (t.tags or []))
        print(f"✓ 现有 case 补 demo tag: {tagged} 条")
        print(f"✓ 新增 demo case: {inserted} 条 / 更新: {updated} 条")
        print(f"✓ 当前测试集: 共 {len(all_cases)} 条（其中 demo {demo_n} 条）")
        # 分类概览
        from collections import Counter
        hooks = Counter((t.tags or ["无"])[0] for t in all_cases)
        kols = Counter((t.input_payload or {}).get("name", "?") for t in all_cases)
        print(f"  钩子类型: {dict(hooks)}")
        print(f"  达人: {dict(kols)}")


if __name__ == "__main__":
    asyncio.run(main())
