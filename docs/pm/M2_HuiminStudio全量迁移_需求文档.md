# Huimin-Studio 全量迁移需求文档

> 编写时间：2026-06-24
> 文档定位：旧代码 `Ai_Toolbox_new/huimin-studio-web/app/page.tsx`（2571 行单文件）中尚未迁移到新平台的 6 个模块，逐一拆解需求、技术方案和决策点。
> 状态：**待确认** — 所有带 ❓ 的决策点需用户拍板后方可开工。

---

## 一、迁移全景

### 已迁移（不在本文档范围）

| 旧模块 | 新平台对应 | Sprint |
|--------|-----------|--------|
| 千川仿写（adapter） | QianchuanWriterPage | Sprint 14 |
| 直播间脚本仿写（livestream-writer） | LivestreamWriterPage | Sprint 8 |
| 直播间脚本复盘（livestream-review） | LivestreamReviewPage | Sprint 9 |
| TikTok 工具（tiktok） | TiktokWriterPage | Sprint 4 |
| 种草内容仿写（seeding-writer） | SeedingWriterPage | Sprint 16 |

### 本文档范围：未迁移 6 个模块

| # | 旧模块 | 功能摘要 | 优先级建议 |
|---|--------|---------|-----------|
| A | 价值观仿写（values） | 爆款原文→产品→AI推情绪方向→生成脚本+情绪报告 | 🔴 高 |
| B | 千川脚本预审（review-script） | 原版+仿写双栏对比，输出 pass/minor/fail 评级 | 🔴 高 |
| C | 人物档案编辑器（personas） | 达人5分区结构化档案（基本身份/经历/关系网/独家/其他） | 🟡 中 |
| D | 产品库——千川场景（products） | 千川专属9字段产品 CRUD（含"只有我有"机制字段） | 🟡 中 |
| E | 复盘（retrospective） | 上传5类直播材料→AI生成复盘报告→历史记录管理 | 🟡 中 |
| F | 千川成片预审（review-film） | 上传原片+成片视频，AI分镜分析+三维评分 | 🟠 低（技术风险高） |

---

## 二、模块 A — 价值观仿写

### 2.1 业务逻辑（完整 4 步）

```
Step 1 · 输入爆款原文
  ├── 锁定开头（第一句，AI 改写时一字不动）
  └── 粘贴全文（AI 从此处分析段落结构和字数）

Step 2 · 选关联产品
  └── 从产品库下拉选择（只用于方向推导，脚本中绝不出现产品名）

Step 3 · AI 推导情绪方向（轻模型，3 次重试）
  ├── 输出 2-3 个方向，每个含：type(焦虑型/诱惑型)、title(5字)、description、anchor(情绪锚点)
  └── 用户点选一个方向进入 Step 4

Step 4 · 生成脚本 + 情绪报告（重模型，流式）
  ├── 先输出 <analysis>（原文结构：总字数/段落数/各段字数）
  ├── 再输出 <rewrite>（改写后的脚本）
  └── 再输出 <report>（情绪检测报告：触发句/恐惧强度/诱惑强度/产品联想/开头核查/优化建议）

后处理
  ├── bigram 相似度计算：与原文相似度 < 35% 绿色 / 35-50% 黄色 / >50% 红色
  ├── 多轮迭代对话（保留 system prompt + 历史消息）
  └── 导出 .txt（脚本 + 情绪报告合并）
```

### 2.2 人设来源

旧版读取固定"慧敏"档案（background/experience/relationships/extra 4 个字段）。
新平台应改为：**从达人列表下拉选择，读取对应 kol 的人设档案**（对接模块 C 的新字段）。

### 2.3 产品来源

❓ **决策点 A-1**：价值观仿写关联的产品，从哪里读取？
- **方案 α**：从模块 D（千川场景产品库）读取，字段包含 `core_selling_point`（最主推卖点）
- **方案 β**：从 seeding-writer 现有产品库（`seeding_writer_products`）读取
- **方案 γ**：价值观模块自带独立产品选择，不与其他模块共享

> 旧代码：读的是专属"慧敏产品库"，即模块 D 的前身。**推荐方案 α**（与模块 D 一起实现，统一千川产品库）。

### 2.4 数据库

新增：`values_writer_configs` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| config_key | VARCHAR(64) UNIQUE | 'default' |
| direction_prompt | TEXT | Step 3 方向推导 prompt |
| writing_prompt | TEXT | Step 4 写作 prompt |
| light_model_id | BIGINT FK ai_models | 方向推导用轻模型 |
| heavy_model_id | BIGINT FK ai_models | 写作用重模型 |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

产出记录复用现有 `outputs` 表（tool_code = 'values-writer'），不新建表。

### 2.5 API

| 端 | 接口 | 说明 |
|----|------|------|
| 运营 POST | `/api/tools/values-writer/derive-directions` | 推导情绪方向（非流式，返回 JSON 数组） |
| 运营 POST stream | `/api/tools/values-writer/chat` | 生成脚本+报告（流式）；也处理后续迭代轮次 |
| 运营 POST | `/api/tools/values-writer/save-output` | 保存产出到 outputs |
| 管理 GET/PUT | `/api/admin/values-writer/config` | 配置管理 |

### 2.6 前端页面

- 运营端：`ValuesWriterPage.tsx`（4步向导，参照 `SeedingWriterPage` 结构）
- 管理端：`ValuesWriterConfigTab.tsx`（ServiceConfigPage 新增 Tab）

---

## 三、模块 B — 千川脚本预审

### 3.1 业务逻辑

```
输入
  ├── 脚本类型切换：千川直销 / 价值观内容
  ├── 如选千川直销：从产品库下拉选产品（可选，用于校验卖点）
  ├── 左栏：原版脚本（字数实时统计）
  └── 右栏：仿写脚本（字数实时统计）

AI 审核（非流式，返回结构化 JSON）
  └── { rating: 'pass'|'minor'|'fail', must_fix: [...], suggestions: [...], passed: [...] }

结果展示
  ├── 评级 Banner（绿/黄/红）
  ├── 必须修改（type + 原文引用 + 修改建议）
  ├── 建议优化（列表）
  └── 已通过（标签云）
```

### 3.2 与现有 qianchuan-review 的区别

| 维度 | 现有 qianchuan-review（Sprint 6/9/10） | 本模块 review-script |
|------|---------------------------------------|---------------------|
| 定位 | 事后复盘：上线后的脚本效果复盘 | 事前预审：上线前的仿写质量把关 |
| 输入 | 单一脚本 + 数据反馈 | 原版脚本 + 仿写脚本双栏对比 |
| 输出 | 复盘分析（文字流式） | 结构化评级（pass/minor/fail + 分类问题） |

**两者独立，不共用配置表。**

### 3.3 数据库

新增：`qianchuan_script_review_configs` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| config_key | VARCHAR(64) UNIQUE | |
| direct_prompt | TEXT | 千川直销模式 prompt |
| value_prompt | TEXT | 价值观模式 prompt |
| ai_model_id | BIGINT FK ai_models | |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

审核记录不入库（纯工具，不保存历史）。

### 3.4 API

| 端 | 接口 | 说明 |
|----|------|------|
| 运营 POST | `/api/tools/qianchuan-script-review/review` | 提交审核（非流式，返回 JSON） |
| 管理 GET/PUT | `/api/admin/qianchuan-script-review/config` | 配置管理 |

### 3.5 前端页面

- 运营端：`QianchuanScriptReviewPage.tsx`
- 管理端：`QianchuanScriptReviewConfigTab.tsx`（ServiceConfigPage 新增 Tab）

---

## 四、模块 C — 人物档案编辑器

### 4.1 业务逻辑

旧版是固定的"慧敏"单人档案编辑器，5 个分区可各自独立编辑：

| 分区 | 说明 | 典型内容 |
|------|------|---------|
| 基本身份 | 年龄、职业、背景、性格 | 用于 AI 定位人物基调 |
| 真实经历 | 可替换对标脚本人物经历的素材 | 越具体越好 |
| 关系网 | 朋友/闺蜜/家人名单 | 替换脚本中其他人名 |
| 独家经历 | 只有该达人有的人生故事 | 差异化素材 |
| 其他补充 | 习惯、口头禅、禁区 | 风格约束 |

新平台需改为**多达人模式**：按达人下拉选择，每个达人有自己的 5 分区档案。

### 4.2 与现有 kols 表的关系

❓ **决策点 C-1**：人物档案 5 分区存在哪里？

| 方案 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| **方案 α（推荐）** | 新建 `kol_persona_details` 表（一对一 kols） | 不污染 kols 表；字段独立可扩展 | 需要 migration + JOIN |
| 方案 β | 在 kols 表加 5 列 | 简单 | kols 表字段过多；与现有 `persona`（单字段）语义冲突 |

> 推荐方案 α。kols 表已有 `persona`（人设全文）字段，但那是非结构化文本。新建独立表可以支持分区存储，且便于 AI 工具按需读取某一分区。

### 4.3 数据库（方案 α）

新增：`kol_persona_details` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| kol_id | BIGINT FK kols(id) UNIQUE | 一达人一条 |
| background | TEXT | 基本身份 |
| experience | TEXT | 真实经历 |
| relationships | TEXT | 关系网 |
| unique_story | TEXT | 独家经历 |
| extra | TEXT | 其他补充 |
| updated_at | TIMESTAMPTZ | |

### 4.4 API

| 端 | 接口 | 说明 |
|----|------|------|
| 运营 GET | `/api/operator/kols/{kol_id}/persona-details` | 读档案（无则返回空） |
| 运营 PUT | `/api/operator/kols/{kol_id}/persona-details` | 保存档案（upsert） |

### 4.5 前端页面

- 运营端：`PersonaDetailsPage.tsx`，放在工作台（WorkspacePage），非工具列表
- 交互：选达人下拉 → 5 分区卡片（每个分区有「编辑/保存/取消」inline 编辑）

---

## 五、模块 D — 产品库（千川场景）

### 5.1 业务逻辑

千川场景的产品字段与种草场景（seeding-writer 现有的 `seeding_writer_products`）语义不同：

| 字段 | 千川场景（本模块） | 种草场景（已有） |
|------|-----------------|----------------|
| 名称 | nickname（产品昵称，脚本中怎么叫） | name |
| 核心卖点 | core_selling_point（几个字，如"美白"） | selling_points（多行文本） |
| **主推机制** | mechanism（价格钩子/促销力度） | — |
| **只有我有** | mechanism_exclusive（布尔，脚本必须写出） | — |
| 可视化 | visualization（拍摄演示点） | — |
| 背书 | endorsement（明星同款/渠道） | — |
| 用户反馈 | user_feedback | — |
| 独家卖点 | unique_selling | — |
| 获奖荣誉 | awards | — |
| 功效承诺 | efficacy_proof | — |
| 品类/价格/人群 | — | category / price / target_audience |

❓ **决策点 D-1**：千川产品库与种草产品库**合并还是分开**？

| 方案 | 实现 | 适用场景 |
|------|------|---------|
| **方案 α（推荐）** | 新建 `qianchuan_products` 表，与 `seeding_writer_products` 并立 | 两套场景字段差异大，分开管理语义清晰 |
| 方案 β | 合并为通用 `products` 表，用 category_type 区分 | 字段太杂，空字段多，且"只有我有"等字段对种草无意义 |

> 推荐方案 α。两套字段差异明显（7 个字段完全不重叠），强行合并会让表结构混乱。

### 5.2 数据库（方案 α）

新增：`qianchuan_products` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| created_by | BIGINT FK users(id) | 创建者 |
| nickname | VARCHAR(100) NOT NULL | 产品昵称 |
| core_selling_point | VARCHAR(200) | 最主推卖点（几个字） |
| visualization | TEXT | 可视化演示点 |
| mechanism | TEXT | 主推机制/价格钩子 |
| mechanism_exclusive | BOOLEAN DEFAULT FALSE | "只有我有"标记 |
| endorsement | TEXT | 推荐来源/背书 |
| user_feedback | TEXT | 用户反馈 |
| unique_selling | TEXT | 独家卖点 |
| awards | VARCHAR(500) | 获奖荣誉 |
| efficacy_proof | TEXT | 功效承诺 |
| deleted_at | TIMESTAMPTZ | 软删除 |
| created_at / updated_at | TIMESTAMPTZ | |

### 5.3 API

| 端 | 接口 | 说明 |
|----|------|------|
| 运营 GET | `/api/tools/qianchuan-products` | 列表（分页） |
| 运营 POST | `/api/tools/qianchuan-products` | 新建 |
| 运营 PUT | `/api/tools/qianchuan-products/{id}` | 编辑 |
| 运营 DELETE | `/api/tools/qianchuan-products/{id}` | 软删除 |

### 5.4 前端页面

- 运营端：`QianchuanProductsPage.tsx`（独立管理页，卡片列表 + 弹窗表单）
- 不进 ServiceConfigPage，放工作台工具列表

---

## 六、模块 E — 复盘

### 6.1 业务逻辑

```
场次管理（历史列表）
  ├── 状态：草稿 / 已完成
  ├── 按最近更新排序
  ├── 点击进入详情或重新复盘
  └── 删除

新建/编辑复盘
  ├── 场次标题（必填，如"0608 Biodance 直播"）
  ├── 上传材料（5 类）
  │   ├── 直播汇总数据（xlsx/csv，AI 解析后传文本）
  │   ├── 素材明细数据（xlsx/csv）
  │   ├── 团队复盘文字（docx/txt，可选）
  │   ├── 直播间脚本（docx/txt，可选）
  │   └── 千川素材脚本（多文件，docx/txt，可选）
  ├── 保存草稿（不跑 AI）
  └── 开始复盘分析（流式）→ 保存结果

详情页
  ├── 展示复盘结果（Markdown 渲染）
  ├── 导出 Word
  ├── 复制全文
  └── 重新复盘（回到编辑态）
```

### 6.2 数据归属

❓ **决策点 E-1**：复盘历史记录是否关联到达人（per-kol），还是全团队共享？

| 方案 | 说明 |
|------|------|
| **方案 α（推荐）** | 全团队共享（不绑定达人），按创建者可筛选 |
| 方案 β | 每场复盘关联一个达人（对应某场直播的主播） |

> 旧版是全团队共享的。推荐保持原逻辑（方案 α），复盘是按场次（日期+活动名）组织的，不一定对应单个达人。

### 6.3 文件处理

上传的 Excel/CSV 调用现有 `document_parser.py` 中的 Excel 解析（已有 `parse-excel` 能力）。docx/txt 调用现有文档解析。**不新增解析服务**。

### 6.4 数据库

新增：`retrospective_sessions` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| created_by | BIGINT FK users(id) | 创建者 |
| title | VARCHAR(200) NOT NULL | 场次标题 |
| status | VARCHAR(20) | 'draft' / 'done' |
| live_data | TEXT | 直播汇总数据（文本化） |
| material_data | TEXT | 素材明细数据（文本化） |
| review_text | TEXT | 团队复盘文字 |
| live_script | TEXT | 直播间脚本 |
| material_scripts | JSONB | 千川素材脚本列表 [{name, text}] |
| result | TEXT | AI 复盘报告 |
| created_at / updated_at | TIMESTAMPTZ | |

新增：`retrospective_configs` 表（AI Prompt + 模型配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | |
| config_key | VARCHAR(64) UNIQUE | 'default' |
| system_prompt | TEXT | 复盘 AI Prompt |
| ai_model_id | BIGINT FK ai_models | |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMPTZ | |

### 6.5 API

| 端 | 接口 | 说明 |
|----|------|------|
| 运营 GET | `/api/tools/retrospective` | 历史列表（分页） |
| 运营 POST | `/api/tools/retrospective` | 新建/更新场次（upsert by id） |
| 运营 DELETE | `/api/tools/retrospective/{id}` | 删除 |
| 运营 POST | `/api/tools/retrospective/parse-files` | 上传文件解析（multipart） |
| 运营 POST stream | `/api/tools/retrospective/{id}/analyze` | 流式生成复盘报告 |
| 运营 GET | `/api/tools/retrospective/{id}/export-word` | 导出 Word（blob 响应） |
| 管理 GET/PUT | `/api/admin/retrospective/config` | 配置管理 |

### 6.6 前端页面

- 运营端：`RetrospectivePage.tsx`（列表+详情+编辑，三视图切换）
- 管理端：`RetrospectiveConfigTab.tsx`（ServiceConfigPage 新增 Tab）

---

## 七、模块 F — 千川成片预审

### 7.1 旧版实现

旧版调用 `/api/gemini-video`，上传两个视频（原片+成片）后，Gemini 多模态直接分析整段视频，返回流式分镜报告。

### 7.2 新平台现有能力（Sprint 7 后端）

`qianchuan_edit_review_configs` 表（Sprint 7）已存在，后端已实现截帧+转录+Claude 分析流程（API 路由在 `/api/tools/` 下有截帧/转录/流式/Word导出/保存报告 5 个端点）。

❓ **决策点 F-1**：是否沿用 Sprint 7 后端逻辑，还是保留 Gemini 视频直传方案？

| 方案 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| **方案 α（推荐）** | 沿用 Sprint 7（截帧+ASR+Claude），补建前端页面 | 与平台统一；无需引入 Gemini 依赖 | 分析质量依赖截帧覆盖率，不如 Gemini 直接看视频连贯 |
| 方案 β | 引入 Gemini API，维持旧版视频直传 | 质量更高（Gemini 真正理解视频时序） | 需新增 Gemini 凭证管理；增加平台外部依赖；成本更高 |

> **强烈推荐方案 α**。Sprint 7 后端已经实现，只需补前端即可上线。Gemini 方案会引入平台外的 API 依赖，增加维护成本。如果后期用户有强烈需求，可作为独立 Sprint 再评估。

### 7.3 前端页面（方案 α）

- 运营端：`QianchuanFilmReviewPage.tsx`（两个视频上传卡片 + 分析按钮 + Markdown 报告展示）
- 复用 Sprint 7 已有后端 API，**后端不需要新开发**

### 7.4 工作量评估

方案 α 前端工作量约 0.5 个 Sprint（复用现有后端，UI 参考旧版两栏上传卡片）。

---

## 八、数据库变更汇总

| 新增表 | 对应模块 | Migration 编号 |
|--------|---------|---------------|
| `values_writer_configs` | A-价值观仿写 | 034 |
| `qianchuan_script_review_configs` | B-脚本预审 | 035 |
| `kol_persona_details` | C-人物档案 | 036 |
| `qianchuan_products` | D-千川产品库 | 037 |
| `retrospective_sessions` | E-复盘 | 038 |
| `retrospective_configs` | E-复盘 | 038（同文件） |

> 模块 F（成片预审）后端无新增表，复用 Sprint 7 的 `qianchuan_edit_review_configs`。

---

## 九、workspace_tools 注册

以下工具需注册到 `workspace_tools` 表（status 由 'dev' 逐步改为 'online'）：

| tool_code | tool_name | category |
|-----------|-----------|---------|
| values-writer | 价值观仿写 | 脚本创作 |
| qianchuan-script-review | 千川脚本预审 | 质量把关 |
| qianchuan-film-review | 千川成片预审 | 质量把关 |
| retrospective | 复盘 | 数据复盘 |

> 人物档案编辑器和千川产品库属于「工作台工具」，不进工具列表，直接挂在工作台页面。

---

## 十、决策点汇总（需用户确认）

| # | 决策点 | 推荐方案 | 影响范围 |
|---|--------|---------|---------|
| A-1 | 价值观仿写的产品从哪读 | 方案 α：从千川产品库（模块 D）读 | 影响 A、D 两模块的开发顺序（D 先 A 后） |
| C-1 | 人物档案存哪 | 方案 α：新建 `kol_persona_details` 表 | 影响 migration 设计 |
| D-1 | 千川产品库与种草产品库合并还是分开 | 方案 α：分开，新建 `qianchuan_products` | 影响 seeding-writer 后续是否可共享 |
| E-1 | 复盘是否关联达人 | 方案 α：全团队共享，不绑定达人 | 影响表结构设计 |
| F-1 | 成片预审用 Gemini 还是沿用 Sprint 7 | 方案 α：沿用 Sprint 7（只补前端） | 影响是否引入 Gemini 依赖 |

---

## 十一、Sprint 拆分建议

> 优先完成高价值、依赖少的模块，把有依赖关系的排在一起。

| Sprint | 内容 | 估算 | 前置依赖 |
|--------|------|------|---------|
| Sprint 18 | 模块 C（人物档案编辑器）+ 模块 D（千川产品库） | 1.5 Sprint | 无 |
| Sprint 19 | 模块 B（千川脚本预审） | 0.5 Sprint | 无（独立） |
| Sprint 20 | 模块 A（价值观仿写） | 1 Sprint | 依赖 C（人设）和 D（产品） |
| Sprint 21 | 模块 E（复盘） | 1 Sprint | 无 |
| Sprint 22 | 模块 F（成片预审前端） | 0.5 Sprint | 依赖 Sprint 7 后端已就绪 |

---

## 十二、备注

1. **相似度算法**：旧版用 bigram Jaccard 相似度（代码 ~15 行，纯前端计算）。新平台沿用，逻辑写在前端，不走后端。
2. **情绪报告 + 结构分析**：价值观仿写的 AI 输出用 `<analysis>` / `<rewrite>` / `<report>` XML 标签分割，前端 regex 解析，与旧版保持一致。
3. **千川产品"只有我有"**：`mechanism_exclusive = true` 时，AI 写作 prompt 必须加约束"脚本必须写出「只有我有」"，这是旧版的硬规则，迁移时要带进 Prompt 模板。
4. **复盘 Excel 解析**：调用现有 `document_parser.py`，已支持 xlsx/csv/docx/txt，无需新增解析能力。
5. **成片预审 Sprint 7 后端状态**：已有 `qianchuan_edit_review_configs` 表和 5 个 API，但需要确认 Router 是否已注册到 `app/main.py`，以及测试覆盖情况。
