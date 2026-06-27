# 红人工作台（KOL Workspace）完整需求文档

> 编写时间：2026-06-25
> 文档定位：以慧敏为首个落地达人，建立通用「红人工作台」架构，后续所有达人复用同一套模板，Prompt 等可按达人配置。
> 状态：**待开工** — 所有决策点已确认，可直接进入 Sprint 拆分。

---

## 一、产品定位

### 1.1 是什么

**红人工作台**是一个以「达人」为中心的工作空间。运营人员进入某个达人的工作台后，所有操作——查档案、选产品、写脚本、做复盘——全部在该达人上下文里完成，不需要在每个工具页重复选达人。

### 1.2 和现有页面的关系

| 现有页面 | 关系 |
|---------|------|
| 红人管理（KolsPage） | 入口：在红人列表点击「进入工作台」 |
| 千川仿写、种草仿写等工具页 | 改造：拆出 `XxxModule({ kolId })` 组件，工作台直接渲染，运营全程不离开工作台（方案 D） |
| ServiceConfigPage（管理端配置） | 不变：Prompt/模型配置仍走管理端，工作台不涉及 |

### 1.3 设计原则

- **达人上下文贯穿全程**：进入工作台后，所有操作默认归属当前达人
- **先做慧敏，架构支持所有达人**：数据结构按 `kol_id` 隔离，每个达人独立
- **Prompt 可配置**：部分工具（如千川仿写、价值观仿写）的 Prompt 后期支持按达人覆盖，本期统一用全局配置，预留扩展字段

---

## 二、入口与导航

### 2.1 入口

**KolsPage（红人管理列表）** → 每个达人卡片/行增加「进入工作台」按钮 → 跳转至 `/workspace/:kol_id`

### 2.2 工作台路由结构

工作台整体是**单路由 + 内部 Tab 切换**，不为每个子模块单独设路由。所有内容在 `/workspace/:kol_id` 内部通过 `activeTab` 状态切换渲染，运营全程不离开该页面。

```
/workspace/:kol_id    → 工作台（内部 activeTab 控制显示哪个模块）

# 独立工具页保留原路由（从工具广场等其他入口进入时走此路径，支持不选达人独立使用）
/tools/qianchuan-writer
/tools/seeding-writer
/tools/persona-writer
/tools/livestream-writer
/tools/livestream-review
/tools/values-writer
/tools/qianchuan-script-review
/tools/qianchuan-film-review
```

### 2.3 左侧导航结构

```
△  工作台首页        → activeTab = 'dashboard'
👤 人物档案          → activeTab = 'persona'
📦 产品库            → activeTab = 'products'
✂️ 千川仿写          → activeTab = 'qianchuan-writer'   （内嵌 Module，达人自动锁定）
💎 价值观仿写        → activeTab = 'values-writer'      （内嵌 Module，达人自动锁定）
🔍 千川脚本预审      → activeTab = 'script-review'      （内嵌 Module，不依赖达人）
🎞️ 千川成片预审      → activeTab = 'film-review'        （内嵌 Module，不依赖达人）
📊 复盘              → activeTab = 'retrospective'
🗂️ 素材库            → activeTab = 'references'
```

顶部显示「当前红人：{kol.name}」，右侧「退出工作台」按钮返回红人列表。

### 2.4 技术方案 D：Shell + Module 改造

**核心思路**：旧代码（huimin-studio）的实现方式——一个页面 + `activeModule` 状态 + 条件渲染组件。新平台做干净版的同款架构。

```
WorkspacePage.tsx（Shell）
  ├── 读取 kol_id，加载达人信息
  ├── activeTab 状态
  ├── 左侧导航（切换 activeTab）
  └── 主区域条件渲染：
        {activeTab === 'dashboard'        && <WorkspaceDashboard kolId={kolId} />}
        {activeTab === 'persona'          && <WorkspacePersona kolId={kolId} />}
        {activeTab === 'products'         && <QianchuanProductsModule />}
        {activeTab === 'qianchuan-writer' && <QianchuanWriterModule kolId={kolId} />}
        {activeTab === 'values-writer'    && <ValuesWriterModule kolId={kolId} />}
        {activeTab === 'script-review'    && <QianchuanScriptReviewModule />}
        {activeTab === 'film-review'      && <QianchuanFilmReviewModule />}
        {activeTab === 'retrospective'    && <WorkspaceRetrospective kolId={kolId} />}
        {activeTab === 'references'       && <WorkspaceReferences kolId={kolId} />}
```

**各工具页改造方式**（以千川仿写为例）：

```tsx
// 改造前：只有独立页面
export default function QianchuanWriterPage() {
  // Step 1: 下拉选达人
}

// 改造后：拆出 Module 组件（去掉选达人 Step，接受外部 kolId）
export function QianchuanWriterModule({ kolId }: { kolId: number }) {
  // 直接用 kolId 加载达人数据，无选达人 Step
}

// 独立页面保留（从工具广场进入时用，有完整选达人流程）
export default function QianchuanWriterPage() {
  const [kolId, setKolId] = useState<number>();
  if (!kolId) return <KolSelector onSelect={setKolId} />;  // Step 1
  return <QianchuanWriterModule kolId={kolId} />;
}
```

**每个工具页改造量约 30-40 行**，无需重写业务逻辑，只是把「选达人」从 Step 内部抽到组件外部。

| 需改造的工具页 | 改造内容 | 工作量 |
|--------------|---------|--------|
| QianchuanWriterPage | 拆出 QianchuanWriterModule | ~30 行 |
| SeedingWriterPage | 拆出 SeedingWriterModule | ~30 行 |
| PersonaWriterPage | 拆出 PersonaWriterModule | ~30 行 |
| LivestreamWriterPage | 拆出 LivestreamWriterModule | ~30 行 |
| LivestreamReviewPage | 拆出 LivestreamReviewModule | ~30 行 |
| ValuesWriterPage（新建） | 直接按 Module 模式设计，无需改造 | — |
| QianchuanScriptReviewPage（新建） | 不依赖达人，无需改造 | — |
| QianchuanFilmReviewPage（新建） | 不依赖达人，无需改造 | — |

---

## 三、工作台首页（Dashboard）

### 3.1 页面布局

```
┌─────────────────────────────────────────────────────┐
│ 对标账号                                              │
│ ┌──────────────────┐  ┌──────────────────┐           │
│ │ 内容对标（N 个）  │  │ 直播对标（N 个）  │           │
│ │ · 账号名  [内容]  │  │ · 账号名  [直播]  │          │
│ │   简介一句话      │  │   简介一句话      │           │
│ └──────────────────┘  └──────────────────┘           │
│ [+ 添加对标账号]                                      │
├─────────────────────────────────────────────────────┤
│ 目前在售商品                                          │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│ │ 商品名    │ │ 商品名    │ │ + 选择   │              │
│ │ 品类 主推 │ │ 品类 主推 │ │ 商品     │              │
│ │ 核心卖点… │ │ 核心卖点… │ │          │              │
│ └──────────┘ └──────────┘ └──────────┘              │
└─────────────────────────────────────────────────────┘
```

### 3.2 对标账号

**数据来源**：新增 `kol_benchmarks` 表（详见 §七数据库设计）

**字段**：
- 账号名（必填）
- 类型：内容对标 / 直播对标
- 简介（一句话，可选，运营手动填写）
- 排序（拖拽或手动设置）

**交互**：
- 点「+ 添加对标账号」→ 弹窗填写（账号名 + 类型 + 简介）
- 点对标账号卡片 → 弹窗编辑
- 删除按钮（悬浮显示）

> ❗ 和现有 benchmark（对标分析，Sprint 3）的关系：`benchmark_analyses` 存的是「对某个账号做深度分析后的报告」，本处的 `kol_benchmarks` 存的是「这个达人应该参考哪些账号」，两者独立，后期可联动（如点对标账号直接跳到 benchmark 分析页），本期不联动。

### 3.3 目前在售商品

**数据来源**：`kol_active_products` 关联表（kol_id ↔ qianchuan_product_id，多对多）

**交互**：
- 商品卡片展示：昵称、品类 tag、主推 tag（若 mechanism_exclusive=true 显示「只有我有」）、核心卖点、主推机制（截断显示）
- 「+ 选择商品」按钮 → 弹窗：
  - 列出 `qianchuan_products` 表所有产品（可搜索）
  - 多选勾选 → 确认 → 更新关联表
  - 弹窗内提供「+ 新建产品」快捷入口（跳转或内嵌弹窗）
- 商品卡片右上角「取消在售」（从关联表删除，不删产品本身）

---

## 四、人物档案

### 4.1 功能描述

结构化编辑达人的 5 分区人设档案，供千川仿写、价值观仿写等 AI 工具自动读取。

### 4.2 5 个分区

| 分区 | 字段名 | 说明 | AI 用途 |
|------|--------|------|---------|
| 基本身份 | `background` | 年龄、职业、背景、性格 | 定位人物基调 |
| 真实经历 | `experience` | 可替换脚本人物经历的素材 | 替换原版人物经历 |
| 关系网 | `relationships` | 朋友/闺蜜/家人名单 | 替换脚本中其他人名 |
| 独家经历 | `unique_story` | 只有该达人有的人生故事 | 差异化素材 |
| 其他补充 | `extra_notes` | 习惯、口头禅、禁区 | 风格约束 |

### 4.3 交互

- 每个分区：标题 + hint 说明 + 查看态（富文本渲染）
- 鼠标悬浮分区显示「编辑」按钮 → 点击变为 textarea inline 编辑
- 「保存」按钮调后端 PUT 接口（upsert）
- 底部显示「上次更新时间」

### 4.4 数据库方案

**扩展 `kols` 表**（已确认），新增 5 列：

```sql
ALTER TABLE kols ADD COLUMN IF NOT EXISTS background     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS experience     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS relationships  TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS unique_story   TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS extra_notes    TEXT;
```

> kols 表已有 `persona`（人设全文）和 `content_plan`（内容规划），5 个新字段是更细粒度的结构化分区，与现有字段并存不冲突。

---

## 五、产品库（千川场景）

### 5.1 定位

千川专属产品库，与种草产品库（`seeding_writer_products`）独立。字段面向「千川直播带货」场景设计，强调价格钩子、背书、促销机制。

### 5.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| nickname | VARCHAR(100) | ✅ | 产品昵称（脚本中怎么叫，如"大红瓶"） |
| core_selling_point | VARCHAR(200) | | 最主推卖点（几个字，如"美白/舒缓"） |
| visualization | TEXT | | 可拍摄的产品演示点 |
| mechanism | TEXT | | 主推机制/价格钩子（如"买一送一/破价"） |
| mechanism_exclusive | BOOLEAN | | "只有我有"标记，true 时 AI prompt 必须写出该句 |
| endorsement | TEXT | | 推荐来源/背书（明星同款/渠道入驻） |
| user_feedback | TEXT | | 用户反馈（素人测评/复购数据） |
| unique_selling | TEXT | | 独家卖点（专利成分/临床数据） |
| awards | VARCHAR(500) | | 获奖荣誉 |
| efficacy_proof | TEXT | | 功效承诺（实测报告数据） |

### 5.3 功能

- **列表页**：卡片展示，每个字段用彩色 tag 区分，支持搜索
- **新建/编辑**：弹窗表单，9 个字段，mechanism 字段下方有「只有我有」checkbox
- **软删除**：`deleted_at` 软删，不支持物理删除
- **全局共享**：所有达人共用同一个产品库，通过「在售商品」关联表决定哪些产品在哪个达人的首页展示

### 5.4 入口

两个入口：
1. 工作台左侧导航「产品库」→ 全局产品 CRUD
2. 工作台首页「目前在售商品」→「+ 选择商品」弹窗内提供「新建产品」快捷入口

---

## 六、复盘

### 6.1 定位

**达人维度**的复盘：每场复盘关联到一个达人，AI 分析时可参考该达人的人物档案（风格/禁忌），输出更有针对性的建议。

### 6.2 功能流程

```
历史列表（默认当前达人的复盘记录）
  └── 按更新时间倒序，显示标题/状态/时间
  └── 点击 → 详情；删除按钮

新建/编辑复盘
  Step 1 · 填写场次标题（必填，如"0608 Biodance 直播"）
  Step 2 · 上传材料（5 类，均为可选，至少上传 1 类才能分析）
    ├── 直播汇总数据（xlsx/csv）
    ├── 素材明细数据（xlsx/csv）
    ├── 团队复盘文字（docx/txt）
    ├── 直播间脚本（docx/txt）
    └── 千川素材脚本（多文件，docx/txt）
  Step 3 · 开始复盘分析（流式）
    └── AI 读取材料 + 达人档案（background/experience/extra_notes）
    └── 生成复盘报告（Markdown）
  Step 4 · 保存 / 导出 Word / 复制全文

详情页
  └── 展示复盘结果 + 上传材料摘要
  └── 「重新复盘」按钮 → 回到编辑态
```

### 6.3 与达人档案的联动

AI 复盘 prompt 中注入达人档案（`extra_notes` 中的风格约束/禁区），使复盘建议能参考达人人设。例如：「本场话术出现了"大家快来抢"等催促性语言，与慧敏一贯的亲和叙事风格有偏差」。

### 6.4 数据库

**`retrospective_sessions` 表**（新增）：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| kol_id | BIGINT FK kols(id) | 关联达人（NOT NULL） |
| created_by | BIGINT FK users(id) | 创建者 |
| title | VARCHAR(200) NOT NULL | 场次标题 |
| status | VARCHAR(20) | 'draft' / 'done' |
| live_data | TEXT | 直播汇总数据（文本化后存储） |
| material_data | TEXT | 素材明细数据（文本化） |
| review_text | TEXT | 团队复盘文字 |
| live_script | TEXT | 直播间脚本 |
| material_scripts | JSONB | 千川素材脚本列表 [{name, text}] |
| result | TEXT | AI 复盘报告 |
| created_at / updated_at | TIMESTAMPTZ | |

**`retrospective_configs` 表**（新增，管理端可配置）：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| config_key | VARCHAR(64) UNIQUE | 'default' |
| system_prompt | TEXT | 复盘 AI Prompt |
| ai_model_id | BIGINT FK ai_models | |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

---

## 七、素材库

### 7.1 定位

**达人维度**的素材库：每条素材归属某个达人（`kol_id`），不同达人素材互不干扰。即复用现有 `seeding_writer_references` 表（已有 `kol_id` 字段）。

### 7.2 素材分类（沿用旧版）

| 分组 | 类型 |
|------|------|
| 人设仿写素材 | 红人爆款文案、红人喜欢的内容、风格参考 |
| 千川仿写素材 | 千川爆款文案、千川喜欢的内容、千川风格参考 |

### 7.3 功能

- 分类入口卡片（6 块），点击进入对应类型的添加/列表
- 素材列表：标题 + 数据/点赞数 + 内容预览（折叠/展开）+ 删除
- 添加：标题（必填）+ 数据说明（选填）+ 正文（必填）
- **本期不支持抖音链接导入**（该功能已在 seeding-writer 工具页里，工作台素材库只支持手动粘贴）

> 复用 `seeding_writer_references` 表，不新建表。

---

## 八、价值观仿写

### 8.1 4 步流程

```
Step 1 · 输入爆款原文
  ├── 锁定开头（第一句，改写时一字不动）
  └── 粘贴全文（AI 分析段落结构和字数）

Step 2 · 选关联产品（从千川产品库选，脚本中不出现产品名）

Step 3 · AI 推导情绪方向（轻模型，最多 3 次重试）
  └── 输出 2-3 个方向：type(焦虑型/诱惑型) + title + description + anchor

Step 4 · 生成脚本 + 情绪报告（重模型，流式）
  ├── <analysis> 原文结构（字数/段落/各段字数）
  ├── <rewrite>  改写后脚本
  └── <report>   情绪检测报告（触发句/恐惧强度/诱惑强度/产品联想/开头核查/优化建议）

后处理
  ├── bigram 相似度（前端计算）：<35% 绿 / 35-50% 黄 / >50% 红
  ├── 多轮迭代对话
  └── 导出 .txt（脚本 + 情绪报告）
```

### 8.2 与工作台联动

- 从工作台进入：`kol_id` 自动传入，跳过达人选择，直接读取该达人档案（background/experience/relationships/extra_notes）
- AI prompt 中注入达人档案 4 个字段

### 8.3 数据库

**`values_writer_configs` 表**（新增）：

| 字段 | 类型 | 说明 |
|------|------|------|
| config_key | VARCHAR(64) UNIQUE | 'default' |
| direction_prompt | TEXT | Step 3 情绪方向推导 prompt |
| writing_prompt | TEXT | Step 4 写作 prompt |
| light_model_id | BIGINT FK ai_models | 方向推导用（轻模型） |
| heavy_model_id | BIGINT FK ai_models | 写作用（重模型） |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

产出复用 `outputs` 表（`tool_code = 'values-writer'`）。

---

## 九、千川脚本预审

### 9.1 功能（独立工具，不依赖达人上下文）

```
输入
  ├── 脚本类型：千川直销 / 价值观内容
  ├── 千川直销时：从千川产品库选产品（可选，用于校验卖点）
  ├── 左栏：原版脚本（字数实时统计）
  └── 右栏：仿写脚本（字数实时统计）

AI 审核（非流式，结构化 JSON）
  └── { rating: 'pass'|'minor'|'fail', must_fix: [...], suggestions: [...], passed: [...] }

结果展示
  ├── 评级 Banner（绿/黄/红）
  ├── 必须修改（type + 原文引用 + 修改建议）
  ├── 建议优化（列表）
  └── 已通过（标签云）
```

### 9.2 数据库

**`qianchuan_script_review_configs` 表**（新增）：

| 字段 | 类型 | 说明 |
|------|------|------|
| config_key | VARCHAR(64) UNIQUE | 'default' |
| direct_prompt | TEXT | 千川直销模式 prompt |
| value_prompt | TEXT | 价值观模式 prompt |
| ai_model_id | BIGINT FK ai_models | |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

审核记录不入库。

---

## 十、千川成片预审（Gemini 方案）

### 10.1 功能（独立工具，不依赖达人上下文）

```
输入
  ├── 原片（素材视频，mp4/mov，建议 500MB 以内）
  └── 成片（已剪辑视频，mp4/mov）

处理流程（后端）
  ├── 接收两个视频文件
  ├── 调用 Gemini 多模态 API（直接传视频，非截帧）
  └── 流式返回分析报告（分镜分析 + 三维评分 + 优化建议）

结果展示
  └── 流式 Markdown 渲染
```

### 10.2 新增后端工作

| 工作项 | 说明 |
|--------|------|
| Gemini 凭证管理 | `service_credentials` 表新增 `service_type = 'gemini'`，管理端可配置 Key |
| `/api/tools/gemini-video` 接口 | 接收两视频，调 Gemini Multimodal API，流式返回 |
| 前端两视频上传卡片 | 参照旧版实现 |

### 10.3 数据库

复用现有 `service_credentials` 表（新增 Gemini Key 记录），不新建表。

---

## 十一、数据库变更汇总

| Migration | 内容 | 对应模块 |
|-----------|------|---------|
| 034 | `ALTER TABLE kols` 加 5 列（人物档案分区） | 人物档案 |
| 035 | 新建 `qianchuan_products` + 索引 | 产品库 |
| 036 | 新建 `kol_benchmarks`（对标账号） | 工作台首页 |
| 037 | 新建 `kol_active_products`（在售商品关联） | 工作台首页 |
| 038 | 新建 `retrospective_sessions` + `retrospective_configs` | 复盘 |
| 039 | 新建 `values_writer_configs` | 价值观仿写 |
| 040 | 新建 `qianchuan_script_review_configs` | 千川脚本预审 |

> 千川成片预审（Gemini）使用现有 `service_credentials` 表，不新增 Migration。
> 素材库复用 `seeding_writer_references` 表，不新增 Migration。

---

## 十二、API 汇总

### 工作台首页

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/operator/workspace/{kol_id}/dashboard` | 首页聚合数据（对标账号 + 在售商品） |
| GET | `/api/operator/workspace/{kol_id}/benchmarks` | 对标账号列表 |
| POST | `/api/operator/workspace/{kol_id}/benchmarks` | 新增对标账号 |
| PUT | `/api/operator/workspace/{kol_id}/benchmarks/{id}` | 编辑对标账号 |
| DELETE | `/api/operator/workspace/{kol_id}/benchmarks/{id}` | 删除对标账号 |
| GET | `/api/operator/workspace/{kol_id}/active-products` | 在售商品列表 |
| PUT | `/api/operator/workspace/{kol_id}/active-products` | 更新在售商品（传 product_id 数组） |

### 人物档案

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/operator/kols/{kol_id}/persona-details` | 读取 5 分区档案 |
| PUT | `/api/operator/kols/{kol_id}/persona-details` | 保存档案（upsert） |

### 千川产品库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/operator/qianchuan-products` | 列表（分页+搜索） |
| POST | `/api/operator/qianchuan-products` | 新建 |
| PUT | `/api/operator/qianchuan-products/{id}` | 编辑 |
| DELETE | `/api/operator/qianchuan-products/{id}` | 软删除 |

### 复盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/operator/workspace/{kol_id}/retrospective` | 列表（分页） |
| POST | `/api/operator/workspace/{kol_id}/retrospective` | 新建/更新（upsert by id） |
| DELETE | `/api/operator/workspace/{kol_id}/retrospective/{id}` | 删除 |
| POST | `/api/operator/workspace/{kol_id}/retrospective/parse-files` | 文件上传解析 |
| POST stream | `/api/operator/workspace/{kol_id}/retrospective/{id}/analyze` | 流式分析 |
| GET | `/api/operator/workspace/{kol_id}/retrospective/{id}/export-word` | 导出 Word |
| GET/PUT | `/api/admin/retrospective/config` | 管理端配置 |

### 素材库（复用 seeding-writer 接口）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tools/seeding-writer/references?kol_id=xx` | 按达人读素材 |
| POST | `/api/tools/seeding-writer/references` | 新增素材 |
| DELETE | `/api/tools/seeding-writer/references/{id}` | 删除素材 |

### 价值观仿写

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/values-writer/derive-directions` | 推导情绪方向（非流式） |
| POST stream | `/api/tools/values-writer/chat` | 生成脚本+报告（流式） |
| POST | `/api/tools/values-writer/save-output` | 保存产出 |
| GET/PUT | `/api/admin/values-writer/config` | 管理端配置 |

### 千川脚本预审

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/qianchuan-script-review/review` | 提交审核（非流式） |
| GET/PUT | `/api/admin/qianchuan-script-review/config` | 管理端配置 |

### 千川成片预审（Gemini）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST stream | `/api/tools/gemini-video` | 上传两视频，流式返回分析报告 |

---

## 十三、前端文件清单

### 工作台 Shell 与原生模块（新建）

| 文件路径 | 说明 |
|---------|------|
| `pages/operator/WorkspacePage.tsx` | Shell：左侧导航 + activeTab 状态 + 条件渲染主区域 |
| `pages/operator/workspace/WorkspaceDashboard.tsx` | 工作台首页（对标账号 + 在售商品） |
| `pages/operator/workspace/WorkspacePersona.tsx` | 人物档案（5 分区编辑） |
| `pages/operator/workspace/WorkspaceReferences.tsx` | 素材库 |
| `pages/operator/workspace/WorkspaceRetrospective.tsx` | 复盘（列表/编辑/详情三视图） |
| `pages/operator/workspace/QianchuanProductsModule.tsx` | 千川产品库（工作台内嵌版，全局共享） |

### 现有工具页改造（拆出 Module 组件）

| 原文件 | 新增导出 | 说明 |
|--------|---------|------|
| `QianchuanWriterPage.tsx` | `export function QianchuanWriterModule({ kolId })` | 去掉选达人 Step，接受外部 kolId |
| `SeedingWriterPage.tsx` | `export function SeedingWriterModule({ kolId })` | 同上 |
| `PersonaWriterPage.tsx` | `export function PersonaWriterModule({ kolId })` | 同上 |
| `LivestreamWriterPage.tsx` | `export function LivestreamWriterModule({ kolId })` | 同上 |
| `LivestreamReviewPage.tsx` | `export function LivestreamReviewModule({ kolId })` | 同上 |

> 原页面的 `export default` 保留，内部调用 Module 并在前面加 KolSelector Step，独立路由访问不受影响。

### 新工具页（新建）

| 文件路径 | 说明 |
|---------|------|
| `pages/operator/ValuesWriterPage.tsx` | 价值观仿写（直接按 Module 模式设计，支持 kolId prop） |
| `pages/operator/QianchuanScriptReviewPage.tsx` | 千川脚本预审（不依赖达人） |
| `pages/operator/QianchuanFilmReviewPage.tsx` | 千川成片预审（Gemini，不依赖达人） |

### 管理端配置 Tab（新建）

| 文件路径 | 说明 |
|---------|------|
| `pages/admin/ValuesWriterConfigTab.tsx` | 价值观仿写配置 |
| `pages/admin/QianchuanScriptReviewConfigTab.tsx` | 千川脚本预审配置 |
| `pages/admin/RetrospectiveConfigTab.tsx` | 复盘配置 |

---

## 十四、Sprint 拆分

| Sprint | 内容 | 估算 | 前置依赖 |
|--------|------|------|---------|
| **Sprint 18** | Migration 034-037 + WorkspacePage Shell + 工作台首页 Dashboard（对标账号+在售商品）+ 千川产品库 Module | 1.5 Sprint | 无 |
| **Sprint 19** | 人物档案 Module + 素材库 Module + **现有5个工具页拆 Module 改造**（千川仿写/种草仿写/人设仿写/直播仿写/直播复盘） | 1.5 Sprint | Sprint 18（Shell 就绪） |
| **Sprint 20** | 价值观仿写（后端+ValuesWriterPage+管理端配置）+ 接入工作台 | 1 Sprint | Sprint 18（产品库就绪）、Sprint 19（人物档案就绪） |
| **Sprint 21** | 千川脚本预审（后端+前端+管理端配置）+ 接入工作台 | 0.5 Sprint | 无 |
| **Sprint 22** | 复盘（后端+前端+管理端配置）+ 接入工作台 | 1 Sprint | Sprint 19（人物档案就绪，供 AI 注入） |
| **Sprint 23** | 千川成片预审：Gemini 凭证管理 + 后端接口 + 前端 + 接入工作台 | 1.5 Sprint | Sprint 18（凭证管理框架） |

**总估算：约 7 Sprint**（Sprint 19 因增加工具页 Module 改造，从 1 升至 1.5）

---

## 十五、本期暂不做（后续 Sprint）

| 功能 | 说明 |
|------|------|
| 千川拼接 | 需求待明确 |
| 达人维度 Prompt 覆盖 | 本期所有达人共用全局 Prompt 配置，后期可按 kol_id 覆盖 |
| 素材库抖音链接导入 | 已在 seeding-writer 工具页里，工作台素材库本期只支持手动粘贴 |
| 对标账号与 benchmark 分析联动 | 后期按需联动 |
| 权限隔离（哪个运营管哪个达人） | 早期不区分，后期再做 |
