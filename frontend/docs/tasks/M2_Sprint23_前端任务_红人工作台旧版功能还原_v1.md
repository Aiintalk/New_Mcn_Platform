# M2 Sprint 23 — 前端任务：红人工作台旧版功能还原 v1（PR #28 补归档）

> **归档性质说明（2026-07-17）：** 本任务是 PR #28 `feature/kol-core-workflow`（merge `ba376ce9`，2026-07-17 合入 main）的**回顾性任务单归档**。开发期实际未单独建任务单，PR 合并后由 PM 审计发现缺口并补齐，便于后续追溯。
> **开发期时间：** 2026-07-14（需求 v1 落档）至 2026-07-17（合并 main）
> **需求来源：** `docs/pm/M2_红人工作台旧版功能还原_需求文档_v1.md` + `docs/pm/M2_红人工作台旧版功能还原_页面与交互一致性修正需求_v2.md`
> **联合验收：** `docs/pm/M2_红人工作台旧版功能还原_最终联合验收报告.md`（功能验收通过）
> **测试报告：** `docs/tests/M2_红人工作台页面与交互一致性修正_v2_测试报告.md`

---

## 一、背景

红人工作台已迁入人物档案 / 产品库 / 千川仿写 / 价值观仿写 / 直播脚本仿写 / 成片预审 / 复盘 / 素材库等模块，但部分模块只完成页面入口或基础能力，与旧版 `huimin-studio` 的实际功能存在差异。

本轮不是重做工作台，而是"功能还原补齐"：保留新平台视觉与额外工具，恢复旧版八个页签的核心业务步骤、输入输出和人工确认点。TikTok 工具不进入本轮范围。

---

## 二、范围

### 模块覆盖

| 模块 | 本轮还原目标 |
|---|---|
| 人物档案 | 统一人物上下文读取，供所有脚本工具复用（不漏读独家经历等分区） |
| 产品库 + 当前商品 | 完整商品卡 + 单一当前商品约束 + 工具真实读取 |
| 千川仿写 | 还原"初稿 → 运营修改 → 自动预审 → 自动重写 → 最好版本"闭环 |
| 价值观仿写 | 旧版四步流程（输入原文 → 选产品 → 推导情绪方向 → 生成脚本和报告） |
| 直播脚本仿写 | 自动绑定红人和当前商品 + 读取完整人物上下文 |
| 素材库 | 文档解析 + 私有视频上传/播放/编辑/软删除 + 红人路径隔离 |
| 复盘 | 多脚本逐份解析（不合并到第一条）+ 红人维度隔离 |
| 千川成片预审 | 启用工作台页签 + 恢复完整视频分析（不退化关键帧） |

### 实际改动文件清单（36 个前端文件）

**新增页面与 API：**

| 文件 | 用途 |
|---|---|
| `pages/operator/FilmReviewPage.tsx` | 千川成片预审独立页（工作台内由 film-review tab 激活同源 Module） |
| `api/filmReview.ts` | 成片预审 API：双视频上传 + 流式报告 + 保存到产出中心 + Word 导出 |
| `types/filmReview.ts` | 成片预审类型定义 |
| `pages/admin/QianchuanPreviewConfigTab.tsx` | 管理端：完整视频 Gemini 配置 Tab（Prompt + ai_model_id + 凭证绑定） |

**新增 / 改造工作台子模块：**

| 文件 | 改动 |
|---|---|
| `pages/operator/KolWorkspacePage.tsx` | 加 `film-review` tab（13 个导航项），成片预审入口 |
| `pages/operator/workspace/WorkspaceDashboard.tsx` | "在售商品" → "当前商品"，单选 |
| `pages/operator/workspace/WorkspacePersona.tsx` | 统一人物上下文（5 分区 + 独家经历） |
| `pages/operator/workspace/WorkspaceReferences.tsx` | 加文档解析 + 私有视频上传/播放/替换/软删除 |
| `pages/operator/workspace/WorkspaceRetrospective.tsx` | 修复多脚本逐份解析（不合并） |
| `pages/operator/workspace/QianchuanProductsModule.tsx` | 加单一当前商品约束 |

**改造独立页 / Module：**

| 文件 | 改动 |
|---|---|
| `pages/operator/LivestreamWriterPage.tsx` | 自动绑定红人 + 读取当前商品和完整人物上下文 |
| `pages/operator/MaterialLibraryPage.tsx` | OSS 私有桶短时签名 + 视频路径隔离 |
| `pages/operator/QianchuanWriterPage.tsx` | 自动预审闭环 + 商品卖点真实进入 AI 输入 |
| `pages/operator/ValuesWriterPage.tsx` | 旧版四步流程 + 双字组合相似度算法 |
| `components/qianchuan/ProductFormModal.tsx` | 商品卡完整字段编辑 |
| `pages/admin/ServiceConfigPage.tsx` | 注册 QianchuanPreviewConfigTab |
| `styles/admin.css` | 新增成片预审 / 视频上传等样式 |

**类型定义更新：**

- `types/kolWorkspaceConfig.ts`（加 `film-review` WorkspaceTabCode）
- `types/livestreamWriter.ts` / `qianchuanWriter.ts` / `scriptReview.ts`

**测试（11 个测试文件）：**

- `__tests__/components/pages/`：FilmReviewModule / KolWorkspacePage / LivestreamWriterPage / MaterialLibraryPage / QianchuanPreviewConfigTab / QianchuanProductsModule / QianchuanWriterPage / ValuesWriterPage / WorkspacePersona / WorkspaceReferences / WorkspaceRetrospective
- `__tests__/unit/api/filmReview.test.ts`

---

## 三、不做

- 不开发、不接入 TikTok 工具
- 不接入 `dysync.net` / `douyin-live-platform` 自动采集
- 不接入云视频
- 不做每日 1-3 条文案排产和统计
- 不删除既有种草仿写 / 人设仿写 / 直播复盘 / 千川脚本预审等额外模块
- 不做与功能还原无关的页面重构或公共组件重写
- 不复制旧版粉色主题、表情符号和旧布局

---

## 四、验收口径

### 4.1 主流程端到端

运营登录 → 进入红人工作台 → 编辑人物档案 → 新建并选中当前商品 → 千川仿写生成初稿 → 运营修改 → 自动预审至通过或轮次用尽 → 保存最终稿 → 用同一商品生成价值观脚本和直播方案 → 上传脚本文档和视频到素材库 → 上传五类复盘材料 → 上传原片和成片完成完整视频预审 → 管理端查看调用日志。

### 4.2 关键不变量

- 当前商品唯一：一个红人最多一条有效关联
- 红人隔离：甲红人不可访问乙红人的素材/复盘/视频
- 完整视频不降级：缺凭证 / 文件过大 / 服务失败均明确报错，不静默退化为关键帧
- OSS 私有桶：上传 / 15 分钟短时读取 / 替换 / 删除均走签名地址，不存长期公开 URL
- 操作日志：3 处 values_writer POST 接口在 PM 接手修复后已补 OperationLog（derive_directions / generate_value_script / iterate_structured_value_script）

### 4.3 视觉与交互

- 1440×900 普通视口检查通过，无文字截断 / 遮挡 / 不可点击
- 工作台 13 个导航项可直接访问
- 独立工具路由（千川仿写 / 直播 / 千川脚本预审 / 千川剪辑预审）保持可用

---

## 五、验收结果

**功能验收：通过**（详见 `docs/pm/M2_红人工作台旧版功能还原_最终联合验收报告.md`）

**测试通过情况（合并 main 时）：**

- 后端：8 模块定向回归 227 通过 + qianchuan-preview 完整视频 30 通过
- 前端 vitest：35 文件 295 通过（1 条 SeedingWriterPage 既有失败为预存基线债务，与本轮无关）
- 前端 `tsc -b`：合并后 PR #30 hotfix 补 `film-review` TAB_LABELS key 后通过

**已知遗留：**

- 5 份真实复盘源文件待补齐（联合验收前置条件，非代码阻断）
- migration 049-052 需在生产 psql 手动执行（项目无 schema_migrations 表，详见 `db_migration_gap.md`）
- migration 049 要求 `kol_active_products` 无重复 kol_id，**生产环境跑前需先排查**

---

## 六、契约影响

- 接口：`backend/docs/base/MCN_M2_Base_API.md` §30（qianchuan-preview 完整视频成片预审）
- 数据库：`backend/docs/base/MCN_M2_Base_Database.md`（migration 051 + 完整视频数据边界说明）
- 不新增前端独立契约文档，沿用现有 `frontend/docs/前端规范.md`

---

## 七、参考

- 开发分支：`feature/kol-core-workflow`（已合并）
- 需求 v1：`docs/pm/M2_红人工作台旧版功能还原_需求文档_v1.md`
- 需求 v2（页面与交互一致性修正）：`docs/pm/M2_红人工作台旧版功能还原_页面与交互一致性修正需求_v2.md`
- 设计审查与规范：`docs/pm/M2_红人工作台视觉优化_设计审查与规范_v1.md`
- 联合验收入口：`docs/pm/M2_红人工作台页面与交互一致性修正_v2_联合验收入口.md`
- 视觉复审清单：`docs/pm/M2_红人工作台页面与交互一致性修正_v2_视觉复审清单.md`
- 开发验收清单：`docs/pm/M2_红人工作台旧版功能还原_开发验收清单.md`
- 最终联合验收报告：`docs/pm/M2_红人工作台旧版功能还原_最终联合验收报告.md`
- 测试报告：`docs/tests/M2_红人工作台页面与交互一致性修正_v2_测试报告.md` + `backend/docs/tests/M2_红人工作台旧版功能还原_测试报告.md`
