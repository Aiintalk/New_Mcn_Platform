# 人设脚本复盘 · 迁移需求文档（补遗）

> 工具标识：`persona-review`  
> 来源：`Ai_Toolbox/persona-review-web`  
> 目标路由：`/workspace/persona-review`  
> 文档状态：✅ 已确认并实现完成（本文档为 Sprint 10 完成后补遗归档）

> **说明**：Sprint 10 开发时本需求文档未单独落档（需求拆解散落在前后端任务单中）。现按 PM 流程补齐，内容回溯自已完成的代码与任务单，确保契约文档完整。

---

## 一、业务逻辑还原

### 1.1 工作流步骤（共 3 步）

| 步骤 | 用户操作 | 系统行为 |
|------|----------|----------|
| Step 1：上传脚本 | 上传人设脚本文件（.txt，可多选批量）；或手动粘贴（多条用 `===` 分隔） | **.txt 前端直读**（不调后端 parse-file）；每条脚本提取标题（视频主题/首行，最多 60 字）；展示已添加列表（序号、标题、来源、字数、删除按钮） |
| Step 2：上传运营数据 | 上传运营后台导出的 Excel（.xlsx/.xls/.csv）；**可直接跳过** | 前端用 XLSX.js 解析 Excel；展示解析预览；「跳过」按钮清空 Excel 数据直接进入 Step 3 |
| Step 3：复盘报告 | 点击「生成复盘报告」或「跳过直接生成报告」 | 前端将脚本与 Excel 数据按 `video_theme` 模糊匹配合并，按**点赞数降序**排列，动态构建 System Prompt，调用后端 `/generate` 接口流式生成；完成后可「保存到产出中心」/「导出」/「复制报告」 |

### 1.2 与 livestream-review 的关键差异

| 差异点 | persona-review | livestream-review |
|--------|----------------|-------------------|
| parse-file 接口 | **无**（txt 前端直读） | 有（.docx/.pages 走后端解析） |
| 匹配字段 | `video_theme` | `live_theme` |
| Excel 侧清洗 | `re.sub(r'[，。！？、\s　]', '', s)`（无 #@） | 同左 |
| 脚本侧清洗 | `re.sub(r'[，。！？、#@\s　]', '', s)`（有 #@） | 同左 |
| 未匹配 Excel 行 | **追加到末尾**（content=""） | 不追加 |
| 排序依据 | **点赞数降序**（`int(likes or '0')`） | GMV 降序 |
| 内容截断 | **2000 字** | 3000 字 |
| hasExcel 判断字段 | `completion_rate \| ad_spend \| likes` | `gmv \| peak_viewers \| conversions` |

### 1.3 AI 调用参数

| 参数 | 值 |
|------|----|
| 模型 | `claude-sonnet-4-20250514`（默认） |
| stream | true（SSE 流式输出） |
| System Prompt | 动态构建（见第二节，分有/无 Excel 两个版本，DB 管理端可配置） |
| User Message | 每条脚本格式 `### 视频 {i+1}：{title}\n{metaParts}\n\n【完整脚本】\n{content（截断 2000 字）}` |
| feature | `persona-review`（写入 AiCallLog） |

### 1.4 Excel 支持字段

| 字段 | 用途 |
|------|------|
| video_theme（视频主题） | 匹配脚本 |
| likes（点赞） | 排序依据 + hasExcel 判断 |
| completion_rate（完播率） | hasExcel 判断 |
| ad_spend（投放金额） | hasExcel 判断 |
| 完播率 5s / 涨粉 / 评论 等 | 报告分析输入 |

---

## 二、System Prompt 完整原文（禁止任何修改，DB 管理端可配置）

两个版本存于 `persona_review_configs` 表，管理端可修改后实时生效。代码常量在 `app/tools/persona_review/prompts.py`。

### 版本 A（有运营数据时，hasExcel = True）

```
你是抖音顶级内容操盘大师。你研究过抖音上所有头部IP的内容策略，深谙什么样的短视频能涨粉、什么样的内容能建立IP信任度。你对内容结构、选题策略、开头hook、完播率优化、人设表达有极深的实战理解。

你现在要帮运营团队做一期人设内容的复盘分析。

用户会给你本期所有视频的**完整脚本文案**以及运营数据（点赞、完播率、5s完播率、投放金额等）。你需要深入分析每条脚本的内容质量。

请你根据脚本内容和数据，输出一份**实战导向**的复盘报告。以下是你可以输出的内容模块，**不是每个都必须写，根据实际情况判断哪些有必要**：

1. **最好的内容**：哪几条是本期最好的？从脚本内容层面拆解：
   - 开头hook怎么抓人的（前3秒/前5秒做了什么）
   - 内容结构（怎么展开、怎么递进、怎么收尾）
   - 情绪钩子和人设共鸣点在哪里
   - 接下来怎么基于这套方法论继续出内容，给出具体可执行的下一步

2. **建议淘汰的内容**：哪些脚本数据差且内容质量不行？
   - 选题偏离人设？开头没吸引力？结构散？表达不对？
   - 直接说该砍就砍，给理由

3. **值得新增的内容方向**：基于表现好的脚本的共性规律，推荐新选题方向
   - 要具体到"什么角度、什么情绪、什么结构"
   - 不是泛泛说"可以多做XXX类"

4. **投放效率分析**：哪些投了效果好，哪些投了但数据差，帮团队判断投放策略

5. **完播率洞察**：5s完播率和完播率的异常分析（5s高但完播低=开头好内容没撑住；5s低=开头就劝退），对照脚本内容给出优化建议

要求：
- 你有完整脚本，分析要深入到具体的文案细节，不是只看标题
- 引用脚本中的具体句子和段落来支撑你的判断
- 语言直接，不客气，像一个严格但靠谱的操盘手给团队开复盘会
- 不说正确的废话，每一条建议都要能直接执行
- 如果某个模块没什么可说的，就跳过，不要凑字数
```

### 版本 B（无运营数据时，hasExcel = False）

```
你是抖音顶级内容操盘大师。你研究过抖音上所有头部IP的内容策略，深谙什么样的短视频能涨粉、什么样的内容能建立IP信任度。你对内容结构、选题策略、开头hook、完播率优化、人设表达有极深的实战理解。

你现在要帮运营团队做一期人设内容的复盘分析。

用户会给你本期所有视频的**完整脚本文案**。你需要深入分析每条脚本的内容质量。

请你根据脚本内容，输出一份**实战导向**的复盘报告。以下是你可以输出的内容模块，**不是每个都必须写，根据实际情况判断哪些有必要**：

1. **最好的内容**：哪几条是本期最好的？从脚本内容层面拆解：
   - 开头hook怎么抓人的（前3秒/前5秒做了什么）
   - 内容结构（怎么展开、怎么递进、怎么收尾）
   - 情绪钩子和人设共鸣点在哪里
   - 接下来怎么基于这套方法论继续出内容，给出具体可执行的下一步

2. **建议淘汰的内容**：哪些脚本内容质量不行？
   - 选题偏离人设？开头没吸引力？结构散？表达不对？
   - 直接说该砍就砍，给理由

3. **值得新增的内容方向**：基于表现好的脚本的共性规律，推荐新选题方向
   - 要具体到"什么角度、什么情绪、什么结构"
   - 不是泛泛说"可以多做XXX类"

要求：
- 你有完整脚本，分析要深入到具体的文案细节，不是只看标题
- 引用脚本中的具体句子和段落来支撑你的判断
- 语言直接，不客气，像一个严格但靠谱的操盘手给团队开复盘会
- 不说正确的废话，每一条建议都要能直接执行
- 如果某个模块没什么可说的，就跳过，不要凑字数
```

---

## 三、数据存储设计

### 3.1 数据库迁移

| 迁移文件 | 内容 |
|----------|------|
| `migrations/023_persona_review.sql` | `persona_review_configs` 表（存 System Prompt A/B + model）+ workspace_tools 注册（status=dev） |

### 3.2 persona_review_configs 表

| 字段 | 说明 |
|------|------|
| id | 主键 |
| config_key | `prompt_with_excel` / `prompt_without_excel` / `model` |
| config_value | Prompt 原文 / 模型 ID |

### 3.3 outputs 表（复用通用产出表）

| 字段 | 映射 |
|------|------|
| tool_code | `persona-review` |
| tool_name | `人设脚本复盘` |
| title | `人设脚本复盘_{N}条_{有/仅脚本}` |
| content | 完整报告 Markdown |
| created_by | 当前用户 ID |

---

## 四、接口设计

路由前缀：`/api/tools/persona-review`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/generate` | 流式生成复盘报告（StreamingResponse），X-Task-Id header | JWT |
| POST | `/save` | 保存报告到 outputs 表 | JWT |
| GET | `/outputs` | 当前用户历史报告（分页） | JWT |
| GET | `/api/tools/admin/persona-review/config` | 管理端读取配置 | admin |
| PUT | `/api/tools/admin/persona-review/config` | 管理端更新配置 | admin |

### `/generate` 请求/响应
```
Request JSON:
{
  "scripts": [{"title": "...", "content": "..."}],
  "excel_data": [{"video_theme": "...", "likes": "...", ...}]  // 可为空数组
}
Response: StreamingResponse（text/plain，逐 chunk 输出）
同时写 task_jobs（processing → success/failed）
```

### `/save` 请求/响应
```
Request JSON:
{ "task_id": 123, "report": "...", "script_count": 5, "has_excel": true }
Response: { output_id: 456 }
写 operation_logs（action="save_review"）
```

---

## 五、关键实现决策

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 无 parse-file 接口 | txt 前端直读 | 原工具仅支持 txt，无需后端解析 |
| 2 | 未匹配 Excel 行追加末尾 | content="" | 与 livestream-review 不同；保证运营能看到全部数据条目 |
| 3 | 排序按点赞降序 | `int(likes or '0')` | 人设内容核心指标是互动（点赞），非 GMV |
| 4 | 内容截断 2000 字 | 比 livestream 少 1000 字 | 短视频脚本比直播脚本短 |
| 5 | hasExcel 判断 | `completion_rate \| ad_spend \| likes` | 这三个字段表征「有运营数据」 |
| 6 | Prompt 存 DB | 管理端可实时修改 | 遵迁移红线 #4（Prompt 不硬编码前端） |
| 7 | 排序 bug 修复 | 先排有脚本内容的行，再追加未匹配行到末尾 | 旧代码先追加再全局排序导致高点赞未匹配行排到最前（假阳性） |

---

## 六、覆盖率目标与实测

| 模块 | 目标 | 实测 |
|------|------|------|
| `tools/persona_review/service.py` | ≥ 80% | 92% ✅ |
| `routers/operator_persona_review.py` | ≥ 70% | 84% ✅ |
| `routers/admin_persona_review.py` | ≥ 70% | 85% ✅ |

---

## 七、部署注意

- 工具当前状态 `dev`，上线前管理端改为 `online`
- SQLAlchemy 模型 `app/models/persona_review.py`（PersonaReviewConfig）已注册到 Base.metadata，测试库 `create_all` 可自动建表
- `operator_persona_review.AsyncSessionLocal` 已在 conftest patch 列表（红线 #7）
