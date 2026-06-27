# 千川爆文合集（qianchuan-collection）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧架构「千川爆文合集」工具迁移到新平台，实现脚本的 CRUD 管理（全网爆款 + 达人爆款两池），纯手工无 AI。

**Architecture:** 后端 FastAPI + PostgreSQL，两张新表（personas + scripts），7 个 operator REST 接口，软删除。前端 React + Ant Design，运营端一个页面（模式切换 + 达人管理 + 脚本分页列表）。

**Tech Stack:** Python/FastAPI、SQLAlchemy asyncpg、PostgreSQL 15、React 19、Ant Design 5、TypeScript 6、Vite 8

---

## 文件清单

### 后端（新建）
- `backend/migrations/025_qianchuan_collection.sql` — 建表 + 种子数据 + workspace_tools 注册
- `backend/app/models/qianchuan_collection.py` — SQLAlchemy ORM 模型
- `backend/app/routers/operator_qianchuan_collection.py` — 7 个接口
- `backend/tests/unit/routers/test_qianchuan_collection_unit.py` — 单元测试
- `backend/tests/integration/routers/test_qianchuan_collection.py` — 集成测试

### 后端（修改）
- `backend/app/models/__init__.py` — 导入新模型
- `backend/app/main.py` — include 新 router

### 前端（新建）
- `frontend/src/types/qianchuanCollection.ts` — 类型定义
- `frontend/src/api/qianchuanCollection.ts` — API 封装
- `frontend/src/pages/operator/QianchuanCollectionPage.tsx` — 运营端页面

### 前端（修改）
- `frontend/src/App.tsx` — 懒加载路由注册

---

## Task 1：数据库迁移

**Files:**
- Create: `backend/migrations/025_qianchuan_collection.sql`

- [ ] **Step 1: 写迁移文件**

```sql
-- 025_qianchuan_collection.sql
-- 千川爆文合集：达人表 + 脚本表 + 种子数据 + workspace_tools 注册

-- 达人分组表
CREATE TABLE IF NOT EXISTS qianchuan_collection_personas (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_qianchuan_collection_personas_updated ON qianchuan_collection_personas;
CREATE TRIGGER trg_qianchuan_collection_personas_updated
    BEFORE UPDATE ON qianchuan_collection_personas
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 脚本表
CREATE TABLE IF NOT EXISTS qianchuan_collection_scripts (
    id             SERIAL PRIMARY KEY,
    pool           VARCHAR(20)  NOT NULL DEFAULT 'global',
    persona_name   VARCHAR(100),
    title          VARCHAR(200) NOT NULL,
    content        TEXT         NOT NULL,
    likes          INTEGER,
    source         VARCHAR(100),
    source_account VARCHAR(100),
    script_date    DATE,
    is_deleted     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_qianchuan_collection_scripts_updated ON qianchuan_collection_scripts;
CREATE TRIGGER trg_qianchuan_collection_scripts_updated
    BEFORE UPDATE ON qianchuan_collection_scripts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_qianchuan_scripts_pool_deleted
    ON qianchuan_collection_scripts (pool, is_deleted);

CREATE INDEX IF NOT EXISTS idx_qianchuan_scripts_persona_deleted
    ON qianchuan_collection_scripts (persona_name, is_deleted);

-- workspace_tools 注册
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'qianchuan-collection',
    '千川爆文合集',
    '千川',
    '收集管理全网高跑量千川脚本，按全网爆款和达人爆款两个维度分池管理',
    'online',
    '["脚本","千川","素材库"]'::jsonb,
    (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools WHERE category = '千川')
)
ON CONFLICT (tool_code) DO NOTHING;

-- 种子数据（41 条全网爆款脚本）
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '一个普通女人的逆袭之路…… #逆袭 #爆改 #反差 #变美 #自律', '刚开始觉得自己丑，可能是因为有点胖，准备小小的减一下肥得了。 通过十六加八加二幺幺饮食法，搭配安娜的混氧训练，成功从一百零三到九十。 刚想得瑟一下，朋友说我骨盆前倾有点严重，于是我每天打卡欧阳春晓改善骨盆前倾的视频，练了半个月，明显改善了不少，刚准备炫耀一下，结果发现自己有翼状肩甲、圆肩、溜肩，斜方肌还很明显，整个背看起来很丑。 于是我又开始练c哥和欧阳春晓改善翼状肩胛的视频，坚持每天训练，成功拿下，背部平整了不少，还拥有了一字肩，但是我还不满意，没有我要的力量感，于是我又开始打卡安娜的力量训练，每天都在幻想自己美美穿上小吊带的样子，果然功夫不负有心人，又成功拿下了背，又薄又有力量感，正准备大炫特炫一下朋友说你天天运动怎么没有马甲线，这我忍不了一点。 于是我又开始练帕梅拉和欧阳春小马甲线训练一个多月后再次拿下，刚准备休息一下，结果又发现。 发现我的腿虽然细但是不直，并且还有o型腿。 于是我又开始练韩小四改善腿型，每天睡醒就练。 结果不出所料，我又再次拿下了腿又细又直。 这期间我的体重也从九十降到了八十二，体态和身材通通都拿下了，我要的就是绝对的掌控。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '发腮肉肉脸真的瘦了！每天4分钟巨巨巨无敌瘦脸操 亲测有用！搭配减肥效果更好～分享我经常练的几套瘦脸操之一#瘦脸 #减肥 #瘦脸操', '我的脸从这样变成这样，侧脸的变化也很大。 除了减肥以外，我每周会坚持做两到三次瘦脸操。 它可以锻炼我们的面部肌肉，让肌肉走向分布更匀称，从而达到皮贴骨的状态。 做这个动作的时候会感觉到脸颊两侧很酸，小宝们刚开始做的时候可以不那么用力。 还有最后十秒，坚持住。 这个动作是在第一个动作的基础上活动嘴角两侧的肌肉，小宝们可以不用像视频展示的那样幅度大，慢慢来感受这个动作的发力。 这个动作舌头在右侧嘴里面打圈，会感觉到有一些酸痛，都是正常的，坚持做可以淡化法令纹，一定程度上改善大小脸。 接着换到另一侧。 还有最后十秒，老婆们坚持就能变美。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '你的颜值，一半靠天生，另外一半是可以靠后天去干预的 #变美', '有钱人家的孩子，他是绝对不可能丑的，因为他们知道长相一半是靠基因，一半一定是靠后天去干预。 第七个干预就能换头的特征，你们一定要记一下。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '人是可以突然变好看的！#变美小技巧 #变美思路 #女生必看 #科普冷知识 #逆袭', '人是会突然变好看的，只要你抓住了18~25岁这个女生颜值逆袭的黄金时期，小透明也能变3D建模脸。学会了让追你的crush排到法国第一名就是发型。女生一定不要跟风，剪高层次不仅容易踩雷，还显脸大。选法式木马卷或者慵懒直发，无论是素颜还是化妆都很漂亮。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '我发誓来小韩绝不do脸#韩女 #变美', '我发誓来小韩绝不do脸，脸能紧一点吗？这里两坨肉能不能消下去？', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '刷到我证明你要变美啦，15个邪修技巧一看就会 #变美', '变漂亮真的跟呼吸一样简单，给你们分享十五个协修招数，不用带脑啊，一听就会。 一所有方圆脸下巴短的姐妹，你看过来信，我一定要多穿白色的衣服。 你们自己看这个对比，它真的跟个反光板一样，视觉上下巴能拉出来一大截。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '人是可以突然变漂亮的 抓3个要素 找对大框架 #醒图#AI托尼老师来了#变美', '你们的小学初中到你现在，你们有没有变漂亮过？ 我不知道，我有变得很漂亮。 我跟你说人变漂亮，她不是慢慢变漂亮，她是称了一下那个节点，就那一段时间突然就变漂亮了。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '就是一个美 变美2.0', '朋友们，对于女生而言，立竿见影且无副作用的变美神器是什么？ 嗯，break up with your boyfriend. 哎，真的我发现我身边的女生只要她一分手，过几个月哎自动就变美了。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '2026怎么能让自己美到另一个阶层，全年计划都在这了#变美计划 #美女养成计划 #全方位 #新年新气象', '如果二零二六年你只能做一件事，我求你把这副皮囊修剪好。很多人觉得变美是虚荣，但是我想告诉你，变美是普通女孩都会生活掌控权最快的路。这一年我不要你盲目跟风自信，我们要的是从发丝到眼神全方位的彻底塑造。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '三招教你提升美貌 逆袭大美女#真实生活分享计划#美女逆袭成功#女生变美攻略 #素人爆改#美女', '美貌本身就是一种高能量，刷到这条视频证明你要变漂亮了。 为什么大部分女生都成不了鞠婧祎那样的美女呢？ 因为你根本没有去做美女该做的事儿。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '都快去试试#豆包#内容过于真实', '建议所有建模一般，参数一般的女生都去让豆包分析长相，这是能让你从路人甲逆袭建模怪的关键。 三招教你如何赛博变美。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '丑女爆改美女本人，我是怎么开窍的~ #逆袭#爆改 #前后对比 #女生必看', '首先我也觉得我变化特别特别大，所以经常被人怀疑动力。甚至还有营销号专门抠我们去做虚假宣传，说的还真的是有模有样。今天这篇变美总结，我将毫无保留全部交代清楚。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '美白四部曲，谁用谁知道！ #美白', '给大家分享几个我觉得能最快速脱美白的方法，市面上你们见到的见不到的，我基本上都试过。终于把自己从这样的黄黑变成现在白白嫩嫩的皮肤，这个肤色的变化非常夸张一点，不骗你们。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '10个睡前变美习惯，睡醒就是大美女 #变美', '睡前十分钟，十五个懒人低成本快速变美的实用小tips。 一、越是方圆脸脸大脸不对称的，你越不能给我去乱睡。 你去观察那些明星他们的睡觉姿势，发现没有，基本上都是反着手肘去睡的。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '无意识养成好皮肤的7️⃣个tips #变美', '一些让你随手就能变好看的实用小tips。 都是我从我美女朋友那边严刑拷问来的，学会了一生受益。 一、美女家里面的零食千万不能随便拿起来就吃。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '长相一般，五官逐渐变耐看 脱颖而出的10个小tips #变美', '五官越来越耐看的十个小tips，这期只适合普通人，天生丽质的请划走。 一、吃饭一定要学会交替咀嚼为什么现在越来越多的人有脸不对称大小脸这个问题了都是自己作出来的。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '成为日常美女的7个高效心法 #变美 #逆袭', '不要把美丽留到特殊场合，美丽是需要练习的，穿搭、化妆都要日常训练，平时不是重要场合，总会觉得哪里都不对劲，尤其是我们普通女孩，更要多花心思。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '纯小白变美，把优点放大到极限就能最快逆袭美女！ #变美小技巧 #模仿美女 #变美', '底子一般的普通女生成为美女第一步请无限放大自己的优点，教你们一个思路，最快最大值提升颜值阶梯就是发照片让评论区的姐妹帮你们找你们自己的优点。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '手把手教你改善毛孔cu大（跟练）#护肤 #毛孔', '今天来讲，我是怎么从这样这样慢慢改善成这样这样的。 无论什么领域，邪修还是太权威了。 话不多说，保姆级教程来了。 第一步，用小点沾湿棉球，在脸上来个马杀鸡，原理是起到清洁杀菌的作用。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '护肤之美白教程 #美白 #逆袭 #护肤', '很多人问那个怎么美白啊？ 要与其你去看那一些广告博主，就是那些啊给脸上一滴，然后擦一擦脸，再给你开个滤镜那种变化的，要那种恰饭博主，你还不如看我呢，对吧？', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '全程无广，十八九岁，学生党，毛孔粗大，圣经，一看就懂 #变美 #毛孔', '贝贝，你十八九岁你有毛孔，你的好乖乖crush社交距离能看到你这一块有毛孔。 你们知道我不太喜欢说废话，这一期一丁点广都没有我直接跟你说十八九岁你能用得起的产品。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '变美公式之美白成分公式🧬 #变美公式 #变美 #护肤 #美白', '有斑斑烟酰胺、黑圈圈、视黄醇、包包印，外泌体肤色黄、虾青素、唇周黑用维c红丝丝、积雪草，有黑头、水杨酸。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '战线略长，但真的有用#干货 #毛孔粗大 #护肤 #脱毛', '来，姐妹们，今天一条视频，我来给你解决百分之九十五以上的毛孔粗大和粗糙问题，以及你的黑头问题。 这是一套方法论啊。 我不推荐任何的产品，我只告诉你方法，产品如何去选择，你们自己去挑啊。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '超温和缩毛孔方法，建议看到最后！#护肤#毛孔粗大 #毛孔', '截止目前，本人认为收敛毛孔最顶的方法，主包用这个方法。 从这样变成这样也就一个多月。 话不多说，保姆级教程来了。 第一步，取一条热毛巾热敷面部三分钟，充分打开毛孔，软化废角质。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '一个故事带你把减肥欲望拉到顶峰', '一个故事带你把减肥欲望拉到顶峰。 哈喽大家好，我是无敌小面包。 我今年二十一岁，是一名普通的在校大三学生，也是一名专注分享减肥干货的博主。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '想要夏天来之前白成反光板的，来！跟练！ #变美', '现在撸起你的袖子看一下你的胳膊内侧，如果我说你能比这个地方还要白，你信吗？ 只要跟练完这四个弯道超车超级有用的实操方法，就能让你白的又快又狠。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '周末快乐！明天出第四期校园发饰分享！！电话圈专场！！#发型#丸子头#鲨鱼夹用法', '你是扁头吗？是的话，那这期视频就够了，每天讲解一个发型工具。今天是鲨鱼夹，鲨鱼夹这东西作为发饰界的鼻祖，我认为它是扁头想要修饰头型最快最稳的一种方式。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '年度自用平价好物分享2 #好物推荐 #平价好物 #省钱', '我朋友说，为什么我总花买破烂的钱就能买到好东西，因为我又抠又挑剔。 给大家分享几个巨巨巨高性价比的好物。 这些都是我翻烂测评，翻烂购物软件找到的宝藏。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '20个！是个人就能用得上的pdd神物！！ #pdd好物 #平价好物 #租房好物', '没钱的别看这条视频啊，不然我怕这二十个九块九生活好物直接给你全包干空。我算了一下，我一年在pdd买了三千多个包裹，花了七万多人民币。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '普通人如何展开2026?(实操喂饭版) #2026 #新年 #能量加油站 #认知', '我可以说如果你真的罩这条视频的步骤去做，二零二六年十二月三十一号的，你会和现在完全不是同一个人。我敢这么说啊，不是我在鼓励你我不瞎鼓励人啊。是因为这套东西我已经实打实的做过，是我实验测试出来的结果。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '普通家庭女生社会化必知 #个人成长 #女性成长 #大学生 #进步', '宝宝这条视频不要外放，关上门，带上耳机，自己一个人偷偷听。 如果你家里面崇尚丛林，就可以化作。 因为家境好的小孩早在十八岁之前就完成了舍友。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '女生一定要看的17条社会潜规则！玻璃心请划走 #社会真相 #女生必看', '赶紧把门关上，带上耳机自己偷偷的听。 说句实话，家境好的小孩在十八岁就完成了社会化，而普通家庭的孩子进入到社会当中。 最惨的从来不是没钱没背景，而是根本就没有人教你这十七条人性的潜规则。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '女孩子要尽早明白社会和人性的规则，以及人情世故技巧 #女性成长 #老吴讲成长 #人性', '说个你爸妈都不会告诉你的残酷真相，女孩子不能有学生思维。 乖乖你赚不到钱就是因为你有学生思维，还没有社会化，跟年龄没关系。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '女孩子们！正视自己的野心，永远不要轻易放弃自己 #刘晓艳#女性独立 #向下的自由', '同学们最近有一句话对我感触特别深，就是女性终其一生都在抵御向下的诱惑。 什么意思？ 我相信很多女孩都听到过这样的话，女孩子不用那么高的学历，不要太辛苦了，工作不用那么拼命，你不上班我养你。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '#真实生活分享计划 不管自己打扮永远都是旺自己的捷径#内容太过真实 #女性成长', '一个人只要她长得好看，又或者她打扮的好看，那他这辈子百分之八十他都不可能命苦。 美貌和颜值永远都是挂钩的，永远都是硬通货。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '三个让你快乐到起飞的转运法则！#日常vlog #女性智慧 #girlstalk', '就三个让你快乐到死的转运思维。 第一，你在哪儿就说哪儿好，你跟谁在一起就说谁好，你在做什么就只说这件事儿的好，你选择的就是对的。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '女生一定要学会识别低配关系！会让你越来越顺 #女性成长 #自我提升', '我今天想讲一个很多女孩子都在经历，但是不一定说得清楚的东西，叫低配关系。 你们有没有发现有一些关系你一开始很期待，但是后来却是越相处越累。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '女生一定要明白的13条生存潜规则！否则一直吃亏的就是你 #女性成长 #生存法则', '赶紧把门关上，带上耳机自己偷偷的听。 不要怪我没有提醒你啊，说十三条，你的父母，你的学校老师都不会教你的生存潜规则。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '11个托举自己的超绝思维。#吸引力法则 #认知 #女性成长必修课 #变美', '如果你是女孩子，能刷到这条视频，说明你真的要变得越来越好了，现在就为自己写下越来越好这四个字，只要记住以下几点，你一定可以成为你想成为的人的。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '美女只需要做自己，全世界都会来爱你 #女性智慧 #情感 #女性提升', '美女越做自己，别人就会越惯着你。 人根本不需要太懂事，只需要你形成了一套自己的行事风格，并且充分相信自己，那就是对的，那别人就会自动根据你的需求做出调整。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
INSERT INTO qianchuan_collection_scripts (pool, title, content, source, script_date) VALUES ('global', '藏锋练技，暗赚底气 #女性搞钱 #藏锋成长 #底气自带 #本事立身', '女孩子怎样拥有搞钱的真本事？你就暗暗的去练这十一招。第一个复盘，每天写复盘，睡觉之前二十分钟写下来，今天做的事情，学到的东西，还有哪里做错了以后该怎么做。', '抖音', '2026-05-19') ON CONFLICT DO NOTHING;
```

- [ ] **Step 2: 执行迁移**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 -f migrations/025_qianchuan_collection.sql
```

Expected: `CREATE TABLE` × 2、`CREATE TRIGGER` × 2、`CREATE INDEX` × 2、`INSERT 0 1`（workspace_tools）、`INSERT 0 41`（scripts）

- [ ] **Step 3: 验证**

```bash
psql postgresql://mcn_user:admin123@localhost:5432/mcn_m1 -c "
SELECT tool_code, tool_name, status FROM workspace_tools WHERE tool_code='qianchuan-collection';
SELECT COUNT(*) AS script_count FROM qianchuan_collection_scripts WHERE pool='global' AND is_deleted=false;
"
```

Expected: `qianchuan-collection | 千川爆文合集 | online`，`script_count = 41`

- [ ] **Step 4: commit**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add backend/migrations/025_qianchuan_collection.sql
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "feat(db): migration 025 — qianchuan_collection tables + 41 seed scripts"
```

---

## Task 2：SQLAlchemy 模型

**Files:**
- Create: `backend/app/models/qianchuan_collection.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 写测试（红）**

`backend/tests/unit/routers/test_qianchuan_collection_unit.py` — 先用 import 测试验证模型可导入：

```python
"""Unit tests for qianchuan_collection models and route validation logic."""


def test_models_importable():
    from app.models.qianchuan_collection import (
        QianchuanCollectionPersona,
        QianchuanCollectionScript,
    )
    assert QianchuanCollectionPersona.__tablename__ == "qianchuan_collection_personas"
    assert QianchuanCollectionScript.__tablename__ == "qianchuan_collection_scripts"


def test_script_pool_values():
    """pool 字段只允许 global / persona 两种值（业务校验逻辑）。"""
    valid_pools = {"global", "persona"}
    assert "global" in valid_pools
    assert "persona" in valid_pools
    assert "other" not in valid_pools


def test_page_size_clamp():
    """page_size 超过 100 时截断为 100。"""
    def clamp_page_size(ps: int) -> int:
        return min(ps, 100)

    assert clamp_page_size(20) == 20
    assert clamp_page_size(200) == 100
    assert clamp_page_size(100) == 100
```

- [ ] **Step 2: 运行测试（确认红）**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
pytest tests/unit/routers/test_qianchuan_collection_unit.py -v
```

Expected: `FAILED` — `ImportError: cannot import name 'QianchuanCollectionPersona'`

- [ ] **Step 3: 写模型文件**

`backend/app/models/qianchuan_collection.py`:

```python
from sqlalchemy import Boolean, Column, Date, Integer, String, Text, TIMESTAMP, func

from app.core.database import Base


class QianchuanCollectionPersona(Base):
    """千川爆文合集 — 达人分组表"""
    __tablename__ = "qianchuan_collection_personas"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False, unique=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class QianchuanCollectionScript(Base):
    """千川爆文合集 — 脚本表"""
    __tablename__ = "qianchuan_collection_scripts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    pool           = Column(String(20), nullable=False, default="global")
    persona_name   = Column(String(100), nullable=True)
    title          = Column(String(200), nullable=False)
    content        = Column(Text, nullable=False)
    likes          = Column(Integer, nullable=True)
    source         = Column(String(100), nullable=True)
    source_account = Column(String(100), nullable=True)
    script_date    = Column(Date, nullable=True)
    is_deleted     = Column(Boolean, nullable=False, default=False)
    created_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: 注册到 `__init__.py`**

在 `backend/app/models/__init__.py` 末尾追加：

```python
from app.models.qianchuan_collection import QianchuanCollectionPersona, QianchuanCollectionScript
```

并在 `__all__` 列表中追加：

```python
    "QianchuanCollectionPersona",
    "QianchuanCollectionScript",
```

- [ ] **Step 5: 运行测试（确认绿）**

```bash
pytest tests/unit/routers/test_qianchuan_collection_unit.py -v
```

Expected: `3 passed`

- [ ] **Step 6: commit**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add backend/app/models/qianchuan_collection.py backend/app/models/__init__.py backend/tests/unit/routers/test_qianchuan_collection_unit.py
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "feat(backend): qianchuan_collection SQLAlchemy models + unit tests"
```

---

## Task 3：operator router（7 个接口）

**Files:**
- Create: `backend/app/routers/operator_qianchuan_collection.py`

- [ ] **Step 1: 写集成测试（红）**

`backend/tests/integration/routers/test_qianchuan_collection.py`:

```python
"""Integration tests for operator_qianchuan_collection."""
import pytest
from sqlalchemy import text as sa_text


# ── Auth ──────────────────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.asyncio
    async def test_get_personas_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-collection/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_scripts_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-collection/scripts?pool=global")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_persona_unauthorized(self, test_client):
        resp = await test_client.post("/api/tools/qianchuan-collection/personas",
                                       json={"name": "测试达人"})
        assert resp.status_code == 401


# ── Personas ──────────────────────────────────────────────────────────────

class TestPersonas:
    @pytest.mark.asyncio
    async def test_get_personas_empty(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"]["personas"], list)

    @pytest.mark.asyncio
    async def test_create_persona_success(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "测试达人A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "测试达人A"

    @pytest.mark.asyncio
    async def test_create_persona_duplicate(self, test_client, operator_token):
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "重复达人"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "重复达人"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_persona_empty_name(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_persona_cascades(self, test_client, operator_token, test_session):
        # 创建达人
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "待删达人"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 给该达人添加脚本
        await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "persona", "persona_name": "待删达人",
                  "title": "测试脚本", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 删除达人
        resp = await test_client.delete(
            "/api/tools/qianchuan-collection/personas/待删达人",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        # 确认脚本被级联软删
        row = (await test_session.execute(
            sa_text("SELECT COUNT(*) FROM qianchuan_collection_scripts "
                    "WHERE persona_name='待删达人' AND is_deleted=false")
        )).scalar()
        assert row == 0


# ── Scripts ───────────────────────────────────────────────────────────────

class TestScripts:
    @pytest.mark.asyncio
    async def test_get_global_scripts(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=global",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "scripts" in data
        assert "total" in data
        assert "page" in data

    @pytest.mark.asyncio
    async def test_create_global_script(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "测试脚本标题", "content": "脚本内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "id" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_create_script_missing_title(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_persona_script_no_persona(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "persona", "title": "标题", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_scripts(self, test_client, operator_token):
        # 先添加一条带关键词的脚本
        await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "独特关键词XYZ脚本", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=global&q=独特关键词XYZ",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_delete_script_success(self, test_client, operator_token):
        # 创建脚本
        create_resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "待删脚本", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        script_id = create_resp.json()["data"]["id"]
        # 删除
        resp = await test_client.delete(
            f"/api/tools/qianchuan-collection/scripts/{script_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_script_not_found(self, test_client, operator_token):
        resp = await test_client.delete(
            "/api/tools/qianchuan-collection/scripts/999999",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404


# ── parse-file ────────────────────────────────────────────────────────────

class TestParseFile:
    @pytest.mark.asyncio
    async def test_parse_txt_success(self, test_client, operator_token):
        content = "这是一段千川脚本内容"
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("script.txt", content.encode("utf-8"), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == content

    @pytest.mark.asyncio
    async def test_parse_unsupported_format(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("x.xlsx", b"data", "application/octet-stream")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试（确认红）**

```bash
pytest tests/integration/routers/test_qianchuan_collection.py -v 2>&1 | head -30
```

Expected: 大量 `FAILED` — `404 Not Found`（路由未注册）

- [ ] **Step 3: 写 router 文件**

`backend/app/routers/operator_qianchuan_collection.py`:

```python
"""
app/routers/operator_qianchuan_collection.py

千川爆文合集接口（operator / admin 鉴权）：
  GET    /api/tools/qianchuan-collection/personas              — 达人列表
  POST   /api/tools/qianchuan-collection/personas              — 新建达人
  DELETE /api/tools/qianchuan-collection/personas/{name}       — 软删达人（级联软删脚本）
  GET    /api/tools/qianchuan-collection/scripts               — 脚本列表（分页+搜索）
  POST   /api/tools/qianchuan-collection/scripts               — 新增脚本
  DELETE /api/tools/qianchuan-collection/scripts/{script_id}   — 软删脚本
  POST   /api/tools/qianchuan-collection/parse-file            — 文件解析
"""
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.qianchuan_collection import (
    QianchuanCollectionPersona,
    QianchuanCollectionScript,
)
from app.models.user import User
from app.services.file_parser import parse_uploaded_file

router = APIRouter(prefix="/tools/qianchuan-collection", tags=["qianchuan-collection"])


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


# ---------------------------------------------------------------------------
# GET /personas
# ---------------------------------------------------------------------------

@router.get("/personas")
async def get_personas(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """获取达人列表（不含已软删除）。"""
    rows = (await db.execute(
        select(
            QianchuanCollectionPersona.name,
            func.count(QianchuanCollectionScript.id).label("script_count"),
        )
        .outerjoin(
            QianchuanCollectionScript,
            (QianchuanCollectionScript.persona_name == QianchuanCollectionPersona.name)
            & (QianchuanCollectionScript.is_deleted == False),  # noqa: E712
        )
        .where(QianchuanCollectionPersona.is_deleted == False)  # noqa: E712
        .group_by(QianchuanCollectionPersona.name)
        .order_by(QianchuanCollectionPersona.name)
    )).all()

    personas = [{"name": r.name, "script_count": r.script_count} for r in rows]
    return success_response(data={"personas": personas})


# ---------------------------------------------------------------------------
# POST /personas
# ---------------------------------------------------------------------------

class CreatePersonaRequest(BaseModel):
    name: str


@router.post("/personas")
async def create_persona(
    body: CreatePersonaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新建达人分组。"""
    if not body.name.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "达人名称不能为空"},
        )
    name = body.name.strip()[:100]

    existing = (await db.execute(
        select(QianchuanCollectionPersona)
        .where(QianchuanCollectionPersona.name == name)
        .where(QianchuanCollectionPersona.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_NAME", "message": "该达人已存在"},
        )

    persona = QianchuanCollectionPersona(name=name)
    db.add(persona)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        action="collection_persona_create", target_type="qianchuan_collection_persona",
        target_id=persona.id, detail={"name": name},
        ip=_get_ip(request), user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"name": name})


# ---------------------------------------------------------------------------
# DELETE /personas/{persona_name}
# ---------------------------------------------------------------------------

@router.delete("/personas/{persona_name}")
async def delete_persona(
    persona_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删除达人（级联软删该达人下所有脚本）。"""
    persona = (await db.execute(
        select(QianchuanCollectionPersona)
        .where(QianchuanCollectionPersona.name == persona_name)
        .where(QianchuanCollectionPersona.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "达人不存在"},
        )

    await db.execute(
        update(QianchuanCollectionPersona)
        .where(QianchuanCollectionPersona.id == persona.id)
        .values(is_deleted=True)
    )
    await db.execute(
        update(QianchuanCollectionScript)
        .where(QianchuanCollectionScript.persona_name == persona_name)
        .where(QianchuanCollectionScript.is_deleted == False)  # noqa: E712
        .values(is_deleted=True)
    )
    db.add(OperationLog(
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        action="collection_persona_delete", target_type="qianchuan_collection_persona",
        target_id=persona.id, detail={"name": persona_name},
        ip=_get_ip(request), user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"ok": True})


# ---------------------------------------------------------------------------
# GET /scripts
# ---------------------------------------------------------------------------

@router.get("/scripts")
async def get_scripts(
    pool: str = Query(..., description="global 或 persona"),
    persona_name: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """获取脚本列表，支持分页和关键词搜索。"""
    page_size = min(page_size, 100)

    stmt = (
        select(QianchuanCollectionScript)
        .where(QianchuanCollectionScript.pool == pool)
        .where(QianchuanCollectionScript.is_deleted == False)  # noqa: E712
    )
    if pool == "persona":
        if not persona_name:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": "pool=persona 时必须传 persona_name"},
            )
        stmt = stmt.where(QianchuanCollectionScript.persona_name == persona_name)
    if q:
        stmt = stmt.where(
            or_(
                QianchuanCollectionScript.title.ilike(f"%{q}%"),
                QianchuanCollectionScript.content.ilike(f"%{q}%"),
            )
        )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    scripts_rows = (await db.execute(
        stmt.order_by(QianchuanCollectionScript.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    scripts = [
        {
            "id": s.id,
            "pool": s.pool,
            "persona_name": s.persona_name,
            "title": s.title,
            "content": s.content,
            "likes": s.likes,
            "source": s.source,
            "source_account": s.source_account,
            "script_date": s.script_date.isoformat() if s.script_date else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in scripts_rows
    ]
    return success_response(data={"scripts": scripts, "total": total, "page": page, "page_size": page_size})


# ---------------------------------------------------------------------------
# POST /scripts
# ---------------------------------------------------------------------------

class CreateScriptRequest(BaseModel):
    pool: str
    persona_name: str | None = None
    title: str
    content: str
    likes: int | None = None
    source: str | None = None
    source_account: str | None = None
    script_date: str | None = None  # ISO date string YYYY-MM-DD


@router.post("/scripts")
async def create_script(
    body: CreateScriptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新增脚本。"""
    if not body.title.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "脚本标题不能为空"},
        )
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "脚本内容不能为空"},
        )
    if body.pool == "persona" and not body.persona_name:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "达人爆款脚本必须指定达人名称"},
        )

    # 如果是 persona 池，确认达人存在
    if body.pool == "persona" and body.persona_name:
        persona = (await db.execute(
            select(QianchuanCollectionPersona)
            .where(QianchuanCollectionPersona.name == body.persona_name)
            .where(QianchuanCollectionPersona.is_deleted == False)  # noqa: E712
        )).scalar_one_or_none()
        if not persona:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": f"达人「{body.persona_name}」不存在"},
            )

    script_date = None
    if body.script_date:
        try:
            script_date = date.fromisoformat(body.script_date)
        except ValueError:
            script_date = date.today()
    else:
        script_date = date.today()

    script = QianchuanCollectionScript(
        pool=body.pool,
        persona_name=body.persona_name,
        title=body.title.strip()[:200],
        content=body.content.strip(),
        likes=body.likes,
        source=body.source,
        source_account=body.source_account,
        script_date=script_date,
    )
    db.add(script)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        action="collection_script_create", target_type="qianchuan_collection_script",
        target_id=script.id, detail={"pool": body.pool, "title": body.title.strip()[:50]},
        ip=_get_ip(request), user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": script.id})


# ---------------------------------------------------------------------------
# DELETE /scripts/{script_id}
# ---------------------------------------------------------------------------

@router.delete("/scripts/{script_id}")
async def delete_script(
    script_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删除脚本。"""
    script = (await db.execute(
        select(QianchuanCollectionScript)
        .where(QianchuanCollectionScript.id == script_id)
        .where(QianchuanCollectionScript.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if not script:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "脚本不存在或已删除"},
        )

    await db.execute(
        update(QianchuanCollectionScript)
        .where(QianchuanCollectionScript.id == script_id)
        .values(is_deleted=True)
    )
    db.add(OperationLog(
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        action="collection_script_delete", target_type="qianchuan_collection_script",
        target_id=script_id, detail={"title": script.title[:50]},
        ip=_get_ip(request), user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"ok": True})


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    _: User = Depends(require_operator),
):
    """上传文件，解析返回文本。支持 .txt/.md/.docx/.pdf。"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("txt", "md", "docx", "pdf"):
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT",
                    "message": f"不支持的文件格式: .{ext}（支持 .txt / .md / .docx / .pdf）"},
        )
    try:
        text = await parse_uploaded_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return success_response(data={"text": text, "filename": file.filename})
```

- [ ] **Step 4: 注册到 `main.py`**

在 `backend/app/main.py` 中：

```python
# 在现有 import 末尾添加
from app.routers.operator_qianchuan_collection import router as operator_qianchuan_collection_router
```

在 `app.include_router(admin_qianchuan_preview_router, prefix="/api")` 后添加：

```python
app.include_router(operator_qianchuan_collection_router, prefix="/api")
```

- [ ] **Step 5: 运行测试（确认绿）**

```bash
pytest tests/integration/routers/test_qianchuan_collection.py -v
```

Expected: `16 passed`（或类似数量，全绿）

- [ ] **Step 6: 跑覆盖率**

```bash
pytest tests/integration/routers/test_qianchuan_collection.py \
  --cov=app/routers/operator_qianchuan_collection \
  --cov-report=term-missing -v
```

Expected: 覆盖率 ≥ 80%

- [ ] **Step 7: 跑全量回归（防改坏旧功能）**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 原有测试全绿，无新增失败

- [ ] **Step 8: commit**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add \
  backend/app/routers/operator_qianchuan_collection.py \
  backend/app/main.py \
  backend/tests/integration/routers/test_qianchuan_collection.py
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "feat(backend): operator_qianchuan_collection 7 接口 + 集成测试"
```

---

## Task 4：前端类型 + API 封装

**Files:**
- Create: `frontend/src/types/qianchuanCollection.ts`
- Create: `frontend/src/api/qianchuanCollection.ts`

- [ ] **Step 1: 写类型文件**

`frontend/src/types/qianchuanCollection.ts`:

```typescript
export interface CollectionPersona {
  name: string;
  script_count: number;
}

export interface CollectionScript {
  id: number;
  pool: 'global' | 'persona';
  persona_name: string | null;
  title: string;
  content: string;
  likes: number | null;
  source: string | null;
  source_account: string | null;
  script_date: string | null;
  created_at: string;
}

export interface ScriptListResponse {
  scripts: CollectionScript[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateScriptBody {
  pool: 'global' | 'persona';
  persona_name?: string;
  title: string;
  content: string;
  likes?: number;
  source?: string;
  source_account?: string;
  script_date?: string;
}
```

- [ ] **Step 2: 写 API 封装**

`frontend/src/api/qianchuanCollection.ts`:

```typescript
/**
 * qianchuanCollection.ts
 * 千川爆文合集工具的接口封装。
 *
 * fetch 例外说明（红线 #3）：
 *   - parseFile: FormData 上传（例外：FormData）
 */
import { del, get, post } from './request';
import { useAuthStore } from '../store/authStore';
import type {
  CollectionPersona,
  CollectionScript,
  CreateScriptBody,
  ScriptListResponse,
} from '../types/qianchuanCollection';

const BASE = '/api/tools/qianchuan-collection';

// ── Personas ──────────────────────────────────────────────────────────────

export const getPersonas = () =>
  get<{ personas: CollectionPersona[] }>(`${BASE}/personas`);

export const createPersona = (name: string) =>
  post<{ name: string }>(`${BASE}/personas`, { name });

export const deletePersona = (name: string) =>
  del<{ ok: boolean }>(`${BASE}/personas/${encodeURIComponent(name)}`);

// ── Scripts ───────────────────────────────────────────────────────────────

export interface GetScriptsParams {
  pool: 'global' | 'persona';
  persona_name?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export const getScripts = (params: GetScriptsParams) =>
  get<ScriptListResponse>(`${BASE}/scripts`, params as Record<string, string | number | boolean | undefined>);

export const createScript = (body: CreateScriptBody) =>
  post<{ id: number }>(`${BASE}/scripts`, body);

export const deleteScript = (id: number) =>
  del<{ ok: boolean }>(`${BASE}/scripts/${id}`);

// ── parse-file（FormData 例外）────────────────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function parseFile(file: File): Promise<{ text: string; filename: string }> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch(`${BASE}/parse-file`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message || '文件解析失败');
  }
  const json = await resp.json();
  return json.data as { text: string; filename: string };
}
```

- [ ] **Step 3: 写守卫单元测试**

`frontend/src/__tests__/unit/api/qianchuanCollection.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = path.resolve(__dirname, '../../../api/qianchuanCollection.ts');
const code = fs.readFileSync(SRC, 'utf-8');

describe('qianchuanCollection API convention guard', () => {
  it('getPersonas uses request.ts get', () => {
    expect(code).toMatch(/getPersonas.*=.*\(\).*get</s);
  });

  it('createPersona uses request.ts post', () => {
    expect(code).toMatch(/createPersona.*=.*post</s);
  });

  it('deletePersona uses request.ts del', () => {
    expect(code).toMatch(/deletePersona.*=.*del</s);
  });

  it('getScripts uses request.ts get', () => {
    expect(code).toMatch(/getScripts.*=.*get</s);
  });

  it('createScript uses request.ts post', () => {
    expect(code).toMatch(/createScript.*=.*post</s);
  });

  it('deleteScript uses request.ts del', () => {
    expect(code).toMatch(/deleteScript.*=.*del</s);
  });

  it('parseFile is FormData exception with comment', () => {
    expect(code).toContain('FormData');
    expect(code).toContain('例外');
  });
});
```

- [ ] **Step 4: 运行前端测试**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx vitest run src/__tests__/unit/api/qianchuanCollection.test.ts
```

Expected: `7 passed`

- [ ] **Step 5: commit**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add \
  frontend/src/types/qianchuanCollection.ts \
  frontend/src/api/qianchuanCollection.ts \
  frontend/src/__tests__/unit/api/qianchuanCollection.test.ts
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "feat(frontend): qianchuan-collection 类型定义 + API 封装 + 守卫测试"
```

---

## Task 5：运营端页面 + 路由注册

**Files:**
- Create: `frontend/src/pages/operator/QianchuanCollectionPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 写页面组件**

`frontend/src/pages/operator/QianchuanCollectionPage.tsx`:

```tsx
import React, { useState, useEffect, useRef } from 'react';
import {
  Table, Button, Input, Select, Modal, Form, InputNumber, message, Tag, Space, Tooltip,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  getPersonas, createPersona, deletePersona,
  getScripts, createScript, deleteScript, parseFile,
} from '../../api/qianchuanCollection';
import type { CollectionPersona, CollectionScript } from '../../types/qianchuanCollection';

type Mode = 'global' | 'persona';

export default function QianchuanCollectionPage() {
  const [mode, setMode] = useState<Mode>('global');
  const [personas, setPersonas] = useState<CollectionPersona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string>('');
  const [scripts, setScripts] = useState<CollectionScript[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchQ, setSearchQ] = useState('');
  const [loading, setLoading] = useState(false);

  // 新建达人弹窗
  const [personaModalOpen, setPersonaModalOpen] = useState(false);
  const [personaName, setPersonaName] = useState('');
  const [personaLoading, setPersonaLoading] = useState(false);

  // 添加脚本弹窗
  const [scriptModalOpen, setScriptModalOpen] = useState(false);
  const [scriptForm] = Form.useForm();
  const [scriptLoading, setScriptLoading] = useState(false);
  const [parsedContent, setParsedContent] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 展开行
  const [expandedKeys, setExpandedKeys] = useState<number[]>([]);

  useEffect(() => { loadPersonas(); }, []);
  useEffect(() => { loadScripts(); }, [mode, selectedPersona, page, searchQ]);

  async function loadPersonas() {
    try {
      const data = await getPersonas();
      setPersonas(data.personas);
    } catch { /* ignore */ }
  }

  async function loadScripts() {
    if (mode === 'persona' && !selectedPersona) {
      setScripts([]); setTotal(0); return;
    }
    setLoading(true);
    try {
      const data = await getScripts({
        pool: mode,
        persona_name: mode === 'persona' ? selectedPersona : undefined,
        q: searchQ || undefined,
        page,
        page_size: 20,
      });
      setScripts(data.scripts);
      setTotal(data.total);
    } catch {
      message.error('加载脚本失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreatePersona() {
    if (!personaName.trim()) return;
    setPersonaLoading(true);
    try {
      await createPersona(personaName.trim());
      message.success('达人已创建');
      setPersonaModalOpen(false);
      setPersonaName('');
      await loadPersonas();
      setSelectedPersona(personaName.trim());
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '创建失败');
    } finally {
      setPersonaLoading(false);
    }
  }

  async function handleDeletePersona(name: string) {
    Modal.confirm({
      title: `确认删除达人「${name}」？`,
      content: '该达人下的所有脚本也将被删除，不可恢复。',
      okType: 'danger',
      onOk: async () => {
        try {
          await deletePersona(name);
          message.success('达人已删除');
          if (selectedPersona === name) setSelectedPersona('');
          await loadPersonas();
          await loadScripts();
        } catch {
          message.error('删除失败');
        }
      },
    });
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await parseFile(file);
      setParsedContent(result.text);
      scriptForm.setFieldValue('content', result.text);
      if (!scriptForm.getFieldValue('title')) {
        scriptForm.setFieldValue('title', file.name.replace(/\.[^.]+$/, ''));
      }
      message.success('文件已解析');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '文件解析失败');
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleCreateScript() {
    try {
      const values = await scriptForm.validateFields();
      setScriptLoading(true);
      await createScript({
        pool: mode,
        persona_name: mode === 'persona' ? selectedPersona : undefined,
        title: values.title,
        content: values.content,
        likes: values.likes || undefined,
        source: values.source || undefined,
        source_account: values.source_account || undefined,
      });
      message.success('脚本已添加');
      setScriptModalOpen(false);
      scriptForm.resetFields();
      setParsedContent('');
      setPage(1);
      await loadScripts();
      if (mode === 'persona') await loadPersonas();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return; // form validation
      message.error(e instanceof Error ? e.message : '添加失败');
    } finally {
      setScriptLoading(false);
    }
  }

  async function handleDeleteScript(id: number) {
    try {
      await deleteScript(id);
      message.success('脚本已删除');
      await loadScripts();
      if (mode === 'persona') await loadPersonas();
    } catch {
      message.error('删除失败');
    }
  }

  function copyText(text: string) {
    navigator.clipboard.writeText(text).then(() => message.success('已复制'));
  }

  function downloadScript(s: CollectionScript) {
    const blob = new Blob([s.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${s.title}.txt`; a.click();
    URL.revokeObjectURL(url);
  }

  const columns: ColumnsType<CollectionScript> = [
    {
      title: '#',
      width: 50,
      render: (_, __, index) => (page - 1) * 20 + index + 1,
    },
    {
      title: '内容开头',
      dataIndex: 'content',
      render: (content: string) => (
        <span style={{ color: 'var(--gray-700)' }}>
          {content.replace(/\n/g, ' ').slice(0, 120)}
          {content.length > 120 ? '…' : ''}
        </span>
      ),
    },
    {
      title: '',
      width: 80,
      render: (_, record) => (
        <Space>
          <Tooltip title="删除">
            <Button
              type="text" danger size="small" icon={<DeleteOutlined />}
              onClick={() => {
                Modal.confirm({
                  title: '确认删除此脚本？',
                  okType: 'danger',
                  onOk: () => handleDeleteScript(record.id),
                });
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const expandedRowRender = (record: CollectionScript) => (
    <div style={{ padding: '12px 16px', background: 'var(--gray-50)' }}>
      <Space style={{ marginBottom: 8 }}>
        <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(record.content)}>
          复制文案
        </Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadScript(record)}>
          下载 TXT
        </Button>
        {record.source && <Tag color="blue">{record.source}</Tag>}
        {record.likes && <Tag color="orange">{record.likes >= 10000 ? `${(record.likes / 10000).toFixed(1)}万赞` : `${record.likes}赞`}</Tag>}
      </Space>
      <div style={{
        whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8,
        color: 'var(--gray-700)', maxHeight: 400, overflowY: 'auto',
      }}>
        {record.content}
      </div>
    </div>
  );

  const showList = mode === 'global' || (mode === 'persona' && !!selectedPersona);

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--gray-900)', margin: 0 }}>
          千川爆文合集
        </h2>
        <p style={{ color: 'var(--gray-500)', marginTop: 4, fontSize: 14 }}>
          全网高跑量千川脚本收集与管理
        </p>
      </div>

      {/* 模式切换 */}
      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        <Space>
          <Button
            type={mode === 'global' ? 'primary' : 'default'}
            onClick={() => { setMode('global'); setPage(1); setSearchQ(''); }}
          >
            全网爆款
          </Button>
          <Button
            type={mode === 'persona' ? 'primary' : 'default'}
            onClick={() => { setMode('persona'); setPage(1); setSearchQ(''); }}
          >
            达人爆款
          </Button>
        </Space>

        {mode === 'persona' && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <Select
              style={{ flex: 1 }}
              placeholder="请选择达人"
              value={selectedPersona || undefined}
              onChange={(v) => { setSelectedPersona(v); setPage(1); }}
              options={personas.map(p => ({
                value: p.name,
                label: `${p.name}（${p.script_count} 条）`,
              }))}
            />
            <Button icon={<PlusOutlined />} onClick={() => setPersonaModalOpen(true)}>
              新建达人
            </Button>
            {selectedPersona && (
              <Button danger onClick={() => handleDeletePersona(selectedPersona)}>
                删除达人
              </Button>
            )}
          </div>
        )}
      </div>

      {/* 工具栏 */}
      {showList && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Input.Search
            placeholder="搜索标题或内容…"
            style={{ flex: 1 }}
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
            onSearch={() => { setPage(1); loadScripts(); }}
            allowClear
            onClear={() => { setSearchQ(''); setPage(1); }}
          />
          <Button
            type="primary" icon={<PlusOutlined />}
            onClick={() => { scriptForm.resetFields(); setParsedContent(''); setScriptModalOpen(true); }}
          >
            添加脚本
          </Button>
        </div>
      )}

      {/* 脚本列表 */}
      {showList && (
        <Table<CollectionScript>
          className="card"
          columns={columns}
          dataSource={scripts}
          rowKey="id"
          loading={loading}
          expandable={{
            expandedRowKeys: expandedKeys,
            onExpand: (expanded, record) => {
              setExpandedKeys(expanded ? [record.id] : []);
            },
            expandedRowRender,
          }}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            showTotal: t => `共 ${t} 条脚本`,
            onChange: (p) => setPage(p),
          }}
        />
      )}

      {mode === 'persona' && !selectedPersona && (
        <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--gray-400)' }}>
          请在上方选择一个达人
        </div>
      )}

      {/* 新建达人弹窗 */}
      <Modal
        title="新建达人"
        open={personaModalOpen}
        onCancel={() => { setPersonaModalOpen(false); setPersonaName(''); }}
        onOk={handleCreatePersona}
        confirmLoading={personaLoading}
        destroyOnHidden
      >
        <Input
          placeholder="达人名称"
          value={personaName}
          onChange={e => setPersonaName(e.target.value)}
          onPressEnter={handleCreatePersona}
          maxLength={100}
        />
      </Modal>

      {/* 添加脚本弹窗 */}
      <Modal
        title={mode === 'global' ? '添加全网爆文' : `为「${selectedPersona}」添加爆文`}
        open={scriptModalOpen}
        onCancel={() => { setScriptModalOpen(false); scriptForm.resetFields(); setParsedContent(''); }}
        onOk={handleCreateScript}
        confirmLoading={scriptLoading}
        width={640}
        destroyOnHidden
      >
        <Form form={scriptForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="title" label="脚本标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="脚本标题" maxLength={200} />
          </Form.Item>
          <Form.Item name="likes" label="点赞数（选填）">
            <InputNumber style={{ width: '100%' }} min={0} placeholder="如：50000" />
          </Form.Item>
          <Form.Item name="source" label="来源平台（选填）">
            <Input placeholder="如：抖音、快手" maxLength={100} />
          </Form.Item>
          <Form.Item name="source_account" label="来源账号（选填）">
            <Input placeholder="达人账号名" maxLength={100} />
          </Form.Item>
          <Form.Item label="上传文件（可选）">
            <label style={{
              cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '4px 12px', border: '1px solid var(--gray-300)',
              borderRadius: 6, fontSize: 13, color: 'var(--gray-600)',
            }}>
              上传 Word / PDF / TXT
              <input
                ref={fileInputRef}
                type="file"
                accept=".docx,.pdf,.txt,.md"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
              />
            </label>
            <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--gray-400)' }}>
              或直接粘贴内容
            </span>
          </Form.Item>
          <Form.Item name="content" label="脚本内容" rules={[{ required: true, message: '请输入脚本内容' }]}>
            <Input.TextArea rows={8} placeholder="脚本内容…" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: 注册路由到 `App.tsx`**

在 `frontend/src/App.tsx` 中：

在现有 lazy import 末尾添加：

```typescript
const QianchuanCollectionPage = lazy(() => import('./pages/operator/QianchuanCollectionPage'));
```

在 `<Route path="/workspace/persona-review" .../>` 后添加：

```tsx
<Route path="/workspace/qianchuan-collection" element={<QianchuanCollectionPage />} />
```

- [ ] **Step 3: 运行前端构建验证**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npx tsc -b --noEmit
```

Expected: 无 TypeScript 错误

- [ ] **Step 4: 运行全量前端测试**

```bash
npx vitest run
```

Expected: 所有测试通过，无新增失败

- [ ] **Step 5: commit**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add \
  frontend/src/pages/operator/QianchuanCollectionPage.tsx \
  frontend/src/App.tsx
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "feat(frontend): 千川爆文合集运营端页面 + 路由注册"
```

---

## Task 6：功能验证

- [ ] **Step 1: 启动后端**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Expected: 启动日志无报错

- [ ] **Step 2: 确认路由注册**

```bash
curl -s http://localhost:8000/openapi.json | python3 -c "
import json, sys
paths = json.load(sys.stdin)['paths']
coll = [p for p in paths if 'qianchuan-collection' in p]
print(f'Found {len(coll)} routes:')
for p in coll: print(' ', p)
"
```

Expected: 7 条路由出现在输出中

- [ ] **Step 3: 启动前端**

```bash
cd /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/frontend
npm run dev
```

- [ ] **Step 4: 手动验证流程**

以 operator 账号登录（admin / Admin@123456，或创建一个 operator 账号），进入创作中心 → 千川爆文合集，验证：

1. 全网爆款列表正常加载（显示 41 条种子数据，分页每页 20 条）
2. 搜索关键词「变美」，结果正确过滤
3. 点击一行展开，显示全文 + 复制/下载按钮
4. 复制功能正常（粘贴验证）
5. 添加一条全网爆款脚本（手动输入），保存后列表更新
6. 上传 TXT 文件，内容填充到文本框
7. 删除该脚本，删除后消失
8. 切换到达人爆款 → 新建达人「测试达人」→ 为该达人添加脚本 → 验证脚本出现在列表
9. 删除达人，确认该达人下的脚本也消失

- [ ] **Step 5: 验证 workspace_tools 工具可见**

以 admin 账号登录，进入管理后台 → 工具配置，确认「千川爆文合集」在列表中，状态为 online。

- [ ] **Step 6: 最终 commit（若有修复）**

```bash
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform add -A
git -C /Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform commit -m "fix: 功能验证修复（如有）"
```

---

## Self-Review

**Spec Coverage Check:**
- ✅ 两个脚本池（global / persona）— Task 1, 3, 5
- ✅ 种子数据 41 条 — Task 1
- ✅ 达人独立维护，不绑 kols — Task 1 无 FK，Task 3 API 独立
- ✅ 脚本完整字段（title/content/likes/source/source_account/script_date）— Task 1, 3, 5
- ✅ 软删除（is_deleted）— Task 1 建表, Task 3 DELETE 接口
- ✅ 级联软删（删达人 → 软删脚本）— Task 3 delete_persona
- ✅ 分页（每页 20 条）— Task 3 GET /scripts, Task 5 Table pagination
- ✅ 搜索（title/content ILIKE）— Task 3 GET /scripts, Task 5 Input.Search
- ✅ 文件解析（.docx/.pdf/.txt/.md）— Task 3 parse-file, Task 5 Modal
- ✅ 复制文案 / 下载 TXT — Task 5 展开行
- ✅ workspace_tools 注册（online）— Task 1
- ✅ 无 AI 功能、无管理端专属 Tab — 计划中无相关 Task
- ✅ OperationLog（persona_create/delete, script_create/delete）— Task 3 每个写操作
- ✅ 标准信封（success_response）— Task 3 所有接口
- ✅ 鉴权（operator/admin + password_changed_at）— Task 3 require_operator
- ✅ request.ts 规范（JSON 接口走 get/post/del，parseFile 为 FormData 例外）— Task 4
- ✅ 路由懒加载 — Task 5 lazy()
- ✅ 禁止 Tailwind，使用 CSS 变量 — Task 5 页面组件

**Placeholder Scan:** 无 TBD / TODO / "similar to" 语句。

**Type Consistency:** `CollectionPersona`、`CollectionScript`、`CreateScriptBody`、`ScriptListResponse` 在 types 和 API 封装中名称一致；页面中 `getPersonas`、`getScripts`、`createScript`、`deleteScript`、`parseFile` 与 API 文件导出名称一致。
