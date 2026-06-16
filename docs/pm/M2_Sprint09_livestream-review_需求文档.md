# 直播间脚本复盘 · 迁移需求文档

> 工具标识：`livestream-review`  
> 来源：`Ai_Toolbox/livestream-review-web`  
> 目标路由：`/workspace/livestream-review`  
> 文档状态：✅ 已确认，可进入任务拆解

---

## 一、业务逻辑还原

### 1.1 工作流步骤（共 3 步）

| 步骤 | 用户操作 | 系统行为 |
|------|----------|----------|
| Step 1：上传脚本 | 上传文件（.txt/.md/.docx/.pages，可多选批量）；或展开折叠区手动粘贴（多条用 `===` 分隔） | 逐文件调用后端 `/parse-file` 接口解析文本；粘贴内容按 `\n===\n` 或 `\n---\n` 分隔符切分；每条脚本提取标题（首行非空，最多 60 字）；展示已添加列表（序号、标题、来源、字数、删除按钮） |
| Step 2：上传直播数据 | 上传直播后台导出的 Excel（.xlsx/.xls/.csv）；**可直接跳过** | **前端**用 XLSX.js 解析 Excel，支持标准格式（首行为列头）和转置格式（首列为指标名）两种布局；识别 14 个字段；展示解析预览表格（8列）；「跳过」按钮清空 Excel 数据并直接进入 Step 3 |
| Step 3：复盘报告 | 点击「生成复盘报告」或「跳过直接生成报告」 | 前端将脚本与 Excel 数据按标题模糊匹配合并，按 GMV 降序排列，动态构建 System Prompt，调用后端 `/generate` 接口流式生成，前端实时展示；完成后可「保存到产出中心」/「导出下载 .md」/「复制报告」 |

### 1.2 AI 调用参数

| 参数 | 值 |
|------|----|
| 模型 | `claude-sonnet-4-20250514`（yunwu.ts 默认值） |
| stream | true（SSE 流式输出） |
| System Prompt | 动态构建（见 1.4 节，分有/无 Excel 数据两个版本） |
| User Message | `以下是本期直播间脚本（共N场）：\n\n{场次描述}`（单条脚本截断至 3000 字） |
| max_tokens | 未显式设置 |
| temperature | 未显式设置（库默认） |

**User Message 构建规则（每场格式）：**
```
### 场次 {i+1}：{title}
{metaParts（有值才追加，用 | 分隔）：日期/时长/GMV/GPM/成交单数/峰值在线/平均在线/总UV/平均停留/点赞/评论/涨粉/投放金额}

【完整直播脚本】
{content（超过 3000 字截断并注明"...(已截断)"）}
```

### 1.3 文件解析支持格式

| 格式 | 处理逻辑 |
|------|----------|
| `.txt` / `.md` | 前端直接 `file.text()` 读取，不调后端接口 |
| `.docx` | 调后端 `/parse-file`，后端用 `mammoth.extractRawText` |
| `.pdf` | 不支持，返回固定提示 `"[暂不支持 PDF 格式，请转为 .docx 或 .txt 后上传]"` |
| `.pages` | 调后端 `/parse-file`：JSZip 打开 → 读 `Index/Document.iwa` → snappyjs 解压（`data.slice(4)` 跳过4字节头，失败则裸读）→ 正则提取中文段落（≥10字，≥5个汉字，过滤日期/季度噪声字符串） |
| 其他格式 | 尝试 UTF-8 读取 |

### 1.4 Excel 解析逻辑（前端 XLSX.js）

支持 **14 个字段**，每个字段有多个别名匹配：

| 字段 | 别名列表 |
|------|---------|
| liveTheme（直播主题） | 直播主题、场次、场次名称、直播名称、主题 |
| liveDate（直播日期） | 直播日期、日期、开播日期、开播时间 |
| duration（时长） | 直播时长、时长、开播时长 |
| peakViewers（峰值在线） | 峰值在线、最高在线、峰值人数、在线峰值 |
| avgViewers（平均在线） | 平均在线、在线均值、人均在线 |
| totalUV（总UV） | 总UV、UV、观看人数、观看用户数、观看人数(UV) |
| avgStayTime（平均停留） | 平均停留时长、停留时长、人均停留、平均观看时长 |
| likes（点赞） | 点赞、点赞数、点赞数量 |
| comments（评论） | 评论、评论数、评论数量 |
| followsGained（涨粉） | 新增粉丝、涨粉、粉丝增量、关注数、新增关注 |
| conversions（成交单数） | 成交单数、订单数、成交数、订单量 |
| gmv | GMV、销售额、成交金额、直播间GMV |
| gpm | GPM、千次曝光价值、千次观看价值 |
| adSpend（投放金额） | 投放金额、消耗、广告消耗、投放消耗 |

**格式识别策略（两次 Pass）：**
- **转置格式**（指标名在首列，每列一场直播）：首列扫行匹配 → 识别到 ≥3 个不同字段时使用转置格式，读每列为一场数据
- **标准格式**（首行为列头，每行一场直播）：Pass1 精确匹配，Pass2 endsWith 匹配 → 识别到 ≥2 列时使用标准格式
- 有效行条件：至少有 `liveTheme` 或 `liveDate` 字段

### 1.5 脚本与 Excel 合并逻辑

```
对每条脚本，在 Excel 数据中查找匹配行：
  - 比较字段：liveTheme 和 liveDate（两者中有值的都参与比较）
  - 清洗规则：去除 [，。！？、#@\s]，取前12个字符
  - 匹配规则：双向 include 检查，取前6字符（ft.includes(st.slice(0,6)) || st.includes(ft.slice(0,6))）

排序：按 GMV 降序（parseFloat，无值排末）

追加未匹配行：Excel 中没有匹配到脚本的行也追加到末尾（content 为空字符串）
```

### 1.6 数据存储结构（旧系统）

旧系统将报告保存为本地 JSON 文件（`/opt/livestream-review/reports/{timestamp}-{random}.json`）：

```json
{
  "id": "1734567890123-abc123",
  "report": "完整 Markdown 报告文本",
  "scripts": [{"title": "...", "content": "..."}],
  "excelData": [{"liveTheme": "...", "gmv": "...", ...}],
  "createdAt": "2026-06-11T10:00:00.000Z"
}
```

### 1.7 前端 State 列表

| State | 类型 | 用途 |
|-------|------|------|
| step | 1｜2｜3 | 当前步骤 |
| error | string | 全局错误提示 |
| scripts | ScriptEntry[] | 已添加的脚本列表 |
| pasteInput | string | 手动粘贴输入框内容 |
| excelData | ExcelRow[] | 解析后的 Excel 数据 |
| excelFileName | string | 上传的 Excel 文件名 |
| merged | MergedItem[] | 合并后的场次列表（Step 3 展示） |
| report | string | SSE 流式接收的报告文本（累积） |
| reportLoading | boolean | 生成中状态 |
| savedId | string｜null | 保存成功后返回的 ID |
| saving | boolean | 保存中状态 |

### 1.8 跨应用依赖

**无跨应用依赖**。此工具不调用任何其他工具的 API，也不依赖 TikHub / OSS / ASR。

---

## 二、System Prompt 完整原文（禁止任何修改）

### 版本 A（有直播数据时，hasExcel = true）

```
你是直播间运营复盘专家。你研究过头部主播的直播脚本逻辑，深谙什么样的开场能快速聚人、什么样的互动能提升留存、什么样的转化话术能成交。你对直播间的"人货场"配合有极深的实战理解。

你现在要帮直播运营团队做一期直播复盘分析。

用户会给你本期所有直播间的**完整脚本文案**以及直播数据（GMV、峰值在线、平均停留时长、成交单数、互动数据等）。你需要从「话术效果 + 留人转化」视角做深度复盘。

请输出以下模块（**不是每个都必须写，根据数据情况判断哪些有必要**）：

1. **开场留人分析**（峰值在线 = 开场吸引力）
   - 哪几场峰值在线人数最高？开场前3分钟的脚本做了什么
   - 从脚本层面拆解：开场用了什么钩子、福利预告、话题选择
   - 峰值高的场次开场有什么共性
   - 这套规律怎么复用到下次直播

2. **留存诊断**（平均停留时长 = 内容吸引力）
   - 平均停留时长 Top/Bottom 场次对照脚本分析
   - 停留长的场次脚本节奏怎么样？讲解-互动-逼单的配比
   - 停留短的场次哪里出了问题？是节奏太慢？还是话术单调？
   - 给出下次直播的脚本节奏建议

3. **互动设计拆解**（点赞、评论、扣1）
   - 互动数据 Top 场次的脚本里互动话术怎么设计的
   - 哪些"扣1"、"扣想要"、"姐妹们点赞"等话术最有效
   - 互动密度多少合适，过密或过疏的问题

4. **转化话术效率**（GMV/GPM/成交单数）
   - GMV 最高的场次脚本里转化部分怎么讲的
   - 逼单话术（机制、紧迫感、稀缺感）的设计是否到位
   - GPM 高低对比，找出转化效率最高的脚本段落
   - 哪些场次"流量好但 GMV 差" = 讲解和逼单没接住流量

5. **亏损场次诊断**（投放金额高但 GMV 差）
   - 哪些场次花了钱但没产出？
   - 是开场没接住流量？还是讲解段太弱？还是逼单太软？
   - 直接说该改就改，给理由

6. **人设一致性**
   - 各场次脚本的人设表现是否一致
   - 有没有跑偏的话术（比如人设是"温柔姐姐"但讲解很硬销）
   - 哪些场次最贴合人设

7. **下场优化建议**
   - 基于整体数据，下次直播脚本应该怎么调
   - 开场、互动、讲解、逼单四个段落分别的优化方向
   - 具体到话术示例

要求：
- 你有完整脚本，分析必须引用具体话术原文，不是只看标题
- 所有判断必须有数据支撑，不说"感觉"
- 语言直接，像一个跟主播一起复盘的操盘手在开会
- 每条建议都能直接执行，主播下次就能改
- 如果某个模块没有足够数据支撑，跳过，不凑字数
```

### 版本 B（无直播数据时，hasExcel = false）

```
你是直播间运营复盘专家。你研究过头部主播的直播脚本逻辑，深谙什么样的开场能快速聚人、什么样的互动能提升留存、什么样的转化话术能成交。你对直播间的"人货场"配合有极深的实战理解。

你现在要帮直播运营团队做一期直播复盘分析。

用户会给你本期所有直播间的**完整脚本文案**。你需要从「话术效果 + 留人转化」视角做深度复盘。

请输出以下模块（**不是每个都必须写，根据数据情况判断哪些有必要**）：

1. **最好的脚本段落**：哪场脚本写得最好？
   - 开场怎么抓人的（前3分钟做了什么）
   - 互动设计、转化话术、节奏控制
   - 跑量潜力判断

2. **建议重写的段落**：哪些脚本质量不行？
   - 开场没吸引力？讲解段太散？逼单太软？
   - 直接说哪段砍掉哪段重写，给理由

3. **互动话术分析**
   - 各场次脚本里的互动话术密度和类型
   - 哪种互动设计更有效
   - 推荐的互动节奏

4. **转化逻辑分析**
   - 转化段的铺垫-逼单-解决异议结构是否完整
   - 推荐的逼单话术结构

5. **新脚本方向**：基于好脚本的共性规律，推荐改进方向
   - 具体到什么开场、什么节奏、什么逼单话术

要求：
- 你有完整脚本，分析必须引用具体话术原文，不是只看标题
- 分析要深入到具体的话术句子和段落
- 语言直接，像一个跟主播一起复盘的操盘手在开会
- 每条建议都能直接执行，主播下次就能改
- 如果某个模块没有足够内容支撑，跳过，不凑字数
```

---

## 三、变与不变（迁移映射表）

| 业务点 | 原实现 | 新实现 | 变与不变 | 风险点 |
|--------|--------|--------|----------|--------|
| 工作流三步 | Next.js 前端 state 管理 | React/Vite 前端 state 管理 | **不变**：三步流程、每步交互逻辑完全相同 | — |
| 文件解析（.txt/.md） | 前端 `file.text()` 直读 | 前端直读（不走后端） | **不变** | — |
| 文件解析（.docx/.pdf/.pages） | Next.js API Route `/parse-file` | FastAPI `POST /api/workspace/livestream-review/parse-file` | **逻辑不变**：mammoth→python-docx，snappyjs→python-snappy，pdf提示不变 | python-snappy 需安装 |
| Excel 解析 | 前端 XLSX.js，支持转置/标准两种格式，14字段 | **前端保留**：XLSX.js 解析逻辑 100% copy（迁移到新前端项目） | **不变**：复杂匹配逻辑保留在前端 | 新系统需安装 xlsx 包 |
| 脚本与Excel合并逻辑 | 前端 `handleGenerate()` 中执行 | **后端**：`service.merge_scripts_excel()` | **逻辑不变**，迁移到后端执行（Python等价实现）。**未匹配的 Excel 行不追加到 mergedList，只把有脚本内容的场次发给 AI（已确认）** | — |
| GMV 降序排列 | 前端排序 | 后端排序 | **逻辑不变** | — |
| System Prompt 构建 | 前端动态拼接（依赖 hasExcel 标志） | **后端**：`service.build_system_prompt(has_excel)` | **Prompt 原文零改动**，构建逻辑移至后端。**hasExcel 判断逻辑：后端在合并完成后检查 `merged_list` 中是否存在任意一条含有 gmv/peak_viewers/conversions 的项，而不是简单判断 excel_data 是否非空（已确认）** | — |
| User Message 构建 | 前端拼接场次描述（含截断至3000字） | **后端**：`service.build_user_message(merged)` | **不变**：格式、截断规则、metaParts 排列顺序均不变 | — |
| AI 调用（流式） | Next.js `/chat` → yunwu.ts chatStream | FastAPI `/generate` → `adapters.ai.stream_chat()` | **Prompt 不变**，调用机制迁移到 FastAPI SSE | ai.py 当前无 stream_chat，需新增 |
| 报告保存 | 本地 JSON 文件 `/opt/livestream-review/reports/` | `outputs` 表（PostgreSQL） | **变**：持久化方式改为数据库；字段映射见下方 | — |
| 报告历史 | `GET /api/reports` 读本地文件列表 | `GET /api/workspace/livestream-review/outputs`（查 outputs 表） | **变**：改为查数据库。**权限规则（已确认）：admin 和 operator 在工具页历史列表里均只看自己创建的报告；admin 查看全部用户报告走后台管理的「产出记录」页（`/api/admin/outputs`）** | — |
| 鉴权 | 无鉴权 | JWT Bearer token | **变**：所有接口需 `Depends(require_password_changed)` | — |
| 任务记录 | 无 | `task_jobs` 表（五态状态机） | **新增** | — |
| 操作审计 | 无 | `operation_logs` 表 | **新增** | — |
| 外部调用日志 | 无 | `external_service_logs` 表 | **新增** | — |

### outputs 表字段映射

| 旧 JSON 字段 | 新 outputs 表字段 |
|-------------|------------------|
| report（完整 Markdown 文本） | content |
| scripts.length（场次数） | 存入 title，格式：`直播间脚本复盘_{N}场_{有/仅脚本}` |
| excelData.length > 0 | 存入 title |
| createdAt | created_at（自动） |
| — | tool_code = "livestream-review" |
| — | tool_name = "直播间脚本复盘" |
| — | task_id（关联 task_jobs） |
| — | created_by = current_user.id |

---

## 四、新系统接口设计

路由前缀：`/api/workspace/livestream-review`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/parse-file` | 解析上传的脚本文件（.docx/.pages），返回文本 | JWT |
| POST | `/generate` | 流式生成复盘报告（StreamingResponse） | JWT |
| POST | `/save` | 保存报告到 outputs 表 | JWT |
| GET | `/outputs` | 查询当前用户历史报告（分页） | JWT |

### `/parse-file` 请求/响应
```
Request: multipart/form-data，file 字段
Response: { text: string, filename: string }
```

### `/generate` 请求/响应
```
Request JSON:
{
  "scripts": [{"title": "...", "content": "..."}],
  "excel_data": [{"live_theme": "...", "gmv": "...", ...}]  // snake_case，可为空数组
}
Response: StreamingResponse，text/plain，逐 chunk 输出报告文本
同时写 task_jobs（processing → success/failed）
```

### `/save` 请求/响应
```
Request JSON:
{
  "task_id": 123,
  "report": "完整报告 Markdown 文本",
  "script_count": 5,
  "has_excel": true
}
Response: { output_id: 456 }
写 outputs 表，写 operation_logs（action="save_review"）
```

### `/outputs` 请求/响应
```
Query: ?page=1&size=20
Response: { items: [...], total: N }
每条：{ id, title, created_at, task_id }（不返回全文，节省带宽）
```

---

## 五、前置基础设施依赖

| 依赖项 | 现状 | 需要的动作 |
|--------|------|-----------|
| `adapters/ai.py` 流式支持 | ❌ 只有 `chat()` 返回 str | 新增 `stream_chat()` 异步生成器 |
| `utils/file_parser.py` | ❌ 不存在 | 新建，Python 等价实现 .docx/.pages 解析 |
| python-snappy | ❌ 未安装 | `pip install python-snappy`，写入 requirements.txt |
| python-docx | ✅ 已安装（1.2.0） | 直接使用 |
| 前端 xlsx 包 | 需确认 | `npm install xlsx`（若未安装） |

---

## 六、覆盖率目标（待任务拆解时声明）

| 模块 | 目标 |
|------|------|
| `services/livestream_review_service.py` | ≥ 80% |
| `routers/workspace_livestream_review.py` | ≥ 70% |
| `utils/file_parser.py` | ≥ 90% |
| 整体模块 | ≥ 75% |

---

## 七、brainstorming 澄清结论（2026-06-11 已确认）

| # | 问题 | 决策 | 决策方 |
|---|------|------|--------|
| Q1 | 流式断开时日志怎么写 | `finally` 块写日志：正常完成=success，中途断开=error | 技术决策 |
| Q2 | hasExcel 判断位置 | 后端合并后检查 `merged_list` 中是否有任意一条含 gmv/peak_viewers/conversions，不是简单判断 excel_data 非空 | PM 确认（选 B） |
| Q3 | Python 模糊匹配等价性 | `re.sub(r'[，。！？、#@\s　]', '', s)` 额外覆盖全角空格 | 技术决策 |
| Q4 | Excel 解析代码位置 | 提取为 `utils/excelParser.ts`，组件导入使用 | 技术决策 |
| Q5 | 截断字符数 vs token 数 | 保持字符数（3000字），与原系统一致 | 技术决策 |
| Q6 | 流式测试验收标准 | 最终文本长度 > 0、含"复盘"关键词、task_jobs 状态为 success | 技术决策 |
| Q7 | Prompt 精确比对方式 | 单元测试对两版 Prompt 字符串精确比对 | 技术决策 |
| Q8 | Excel 格式冲突时用哪种 | 转置格式优先（与原 JS 逻辑一致） | 技术决策 |
| Q9 | 未匹配 Excel 行是否发给 AI | **不发给 AI，只把有脚本内容的场次加入 mergedList** | PM 确认（选 B） |
| Q10 | Windows 安装 python-snappy | PyPI 有预编译 wheel，直接 pip install | 技术决策 |
| Q11 | outputs 表字段类型 | PostgreSQL TEXT 无限制，部署前确认字段类型 | 技术决策 |
| Q12 | Admin 历史列表权限 | **工具页历史列表 admin 也只看自己的报告；全量查看走后台管理「产出记录」** | PM 确认（选 B） |
| Q13 | 多用户并发更新风险 | 每请求独立 db session，无竞争风险 | 技术决策 |

