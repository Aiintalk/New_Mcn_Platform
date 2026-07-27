# Phase 5 前端 — 已知问题与遗留事项

> 本文档记录 Phase 5（AIGC 评测前端）实施过程中识别但未在本次迭代解决的问题。
> 按升级规则（spec §Phase 5）记录后继续推进其他工作，避免阻塞主线。

## 1. 运行列表后端接口缺失（中等优先级）

**现象**：`backend/app/evaluation/routers/operator_evaluation.py` 提供了 `POST /runs`（触发）+ `GET /runs/{id}`（单条）+ `GET /runs/{id}/scores`（评分明细），但**未提供 `GET /runs` 列表接口**。

**前端当前应对**：
- `Runs.tsx` 通过浏览器 `localStorage`（key: `eval_runs_cache`）保存每次 `triggerRun` 返回的 run 对象
- 最多缓存 20 条，按时间倒序展示
- 切换浏览器 / 清理缓存后列表重置，但 run id 仍可从「详情」直接访问（URL `/evaluation/runs/:id`）

**影响**：
- 一期能用（单用户 / 单浏览器）
- 多用户 / 多设备不可见对方触发的 run

**建议修复**：
- 后端补 `GET /api/operator/evaluation/runs?page=&page_size=&status=&version_id=` 分页列表接口（对齐 spec §9）
- 前端 `listRuns` API 封装已预留位置（在 `evaluation/api/index.ts` 注释中），接入后即可移除 localStorage 兜底

---

## 2. 测试集单条 GET 接口缺失（低优先级）

**现象**：后端 `operator_evaluation.py` 未提供 `GET /test-cases/{id}` 单条接口，只有分页 `GET /test-cases`。

**前端当前应对**：
- `TestCaseEdit.tsx` 编辑模式通过 `listTestCases({ page: 1, page_size: 50 })` 拉前 50 条再前端 `.find()` 目标 id
- 样本超过 50 条时编辑模式可能找不到目标

**建议修复**：
- 后端补 `GET /api/operator/evaluation/test-cases/{id}` 单条接口
- 前端 `getTestCase(id)` API 封装修改后单行替换

---

## 3. 测试集统计聚合接口缺失（低优先级）

**现象**：`TestCases.tsx` 顶部 4 张统计卡（样本总数 / 启用 / 标签数 / 最近运行平均分）目前基于当前页 + 全量 total 计算，「最近一次运行平均分」恒为 `—`。

**建议修复**：
- 后端补 `GET /api/operator/evaluation/stats` 聚合接口（或作为 `/test-cases` 的响应 meta 字段）

---

## 4. 运行详情「人工校准」UI 简化（低优先级）

**现象**：设计稿 `run-detail.html` 中「样本明细」每行展开后有「输出对比」「人工校准」两个独立操作。Phase 5 实施：
- 每条 score 一个「校准 dN」按钮（N=dimension_id）
- 暂未实现「查看输出」modal（生成输出文本对齐设计稿 msg.assistant 气泡）

**影响**：人工校准功能完整可用，但缺少「快速浏览生成结果」入口。

**建议修复**：
- 后端 `EvalCaseResult` 表已存储 `generated_output`，新增 `GET /api/operator/evaluation/case-results/{id}` 接口
- 前端补「查看输出」Drawer/Modal

---

## 5. 版本创建「关联维护」UI 简化（中等优先级）

**现象**：设计稿 `version-create.html` 的关联维护流程：
- 选来源红人 → 自动触发 `resolve_prompt(kol_id, "qianchuan-writer", "system_prompt", db)` + `get_kol_context(db, kol_id)`
- 显示「关联抠取（只读调用，自动完成）」success badges
- 自动填入 system_prompt 模板到 `code-area` 文本框

**前端当前应对**：
- `Versions.tsx` 创建抽屉只暴露 `source_kol_id` 数值输入
- 缺少红人下拉选择 + 抠取预览 + system_prompt 模板展示

**影响**：管理员需手动查询 kol_id 后填入，无法可视化预览抠取结果。

**建议修复**：
- 接入 `/api/admin/kols`（已有）做红人下拉
- 后端补 `POST /api/admin/evaluation/versions/preview-config`（dry-run 关联维护三步）接口
- 前端创建抽屉补「预览抠取」按钮

---

## 6. ✅ 已解决 — Coverage 工具已安装 + 评测模块覆盖率达标（API 层 100%）

**处理结果（2026-07-22 PM 验证补完）**：
- `npm install` 补齐了已声明但未落地的 `@playwright/test`（package.json 声明，node_modules 缺失）
- 新增 `@vitest/coverage-v8@3.2.7`（对齐已安装的 `vitest@3.2.7`，避免 v4 peer 冲突）到 devDependencies
- 新增 API 契约层单测 `src/__tests__/unit/api/evaluation.test.ts`（32 用例，覆盖 26 个 API 函数的 method/URL/params 契约 + `deriveDirection` 工具函数）

**评测模块覆盖率（`src/evaluation/**`，10 测试文件 / 57 用例全通过）**：

| 区域 | Stmts | Branch | Funcs | Lines |
|------|-------|--------|-------|-------|
| **评测模块整体** | **79.0%** | **77.3%** | **57.0%** | **79.0%** |
| `api/index.ts` | 100% | 97.4% | 100% | 100% |
| `components/primitives.tsx` | 95.5% | 71.1% | 100% | 95.5% |
| `pages/TestCases.tsx` | 98.7% | 77.8% | 64.3% | 98.7% |
| `pages/Compare.tsx` | 93.8% | 71.4% | 75.0% | 93.8% |
| `pages/Runs.tsx` | 86.3% | 75.0% | 55.0% | 86.3% |
| `pages/Dimensions.tsx` | 79.2% | 83.7% | 33.3% | 79.2% |
| `pages/Schedules.tsx` | 74.5% | 80.6% | 50.0% | 74.5% |
| `pages/TestCaseEdit.tsx` | 68.1% | 72.2% | 10.0% | 68.1% |
| `pages/Versions.tsx` | 66.9% | 66.7% | 42.9% | 66.9% |
| `pages/RunDetail.tsx` | 64.9% | 76.9% | 41.2% | 64.9% |
| `types/index.ts` | 0% | 0% | 0% | 0%（纯类型声明，无运行时，非真实缺口）|

**判定**：API 契约层（类比后端 Services ≥80% 门禁）已达 100%，是最关键缺口（此前因页面测试整体 mock 掉 API 模块导致 0%）。页面层语句/分支覆盖属一期合理水平；**函数覆盖偏低集中在交互处理函数**，见下方 #8 作为独立迭代项。

**复现命令**：
```bash
cd frontend
npx vitest run src/__tests__/components/pages/evaluation/ src/__tests__/unit/api/conventionGuard.test.ts src/__tests__/unit/api/evaluation.test.ts --coverage --coverage.include='src/evaluation/**'
```

---

## 7. UI 视觉细节与设计稿对齐（低优先级）

**已对齐**：
- 设计 token（Stone 暖灰 + #f59a23）直接复用 `variables.css`，无重复定义
- 页面骨架（page-header + stats-grid + card + table + drawer）
- 状态徽标 / 分数 chip / 进度条 / 权重条 / callout

**未对齐**：
- 雷达图仅渲染单系列（当前运行），设计稿是双系列（baseline vs current overlay）— 需要后端在 `GET /runs/{id}` 响应中带 baseline run id 才能渲染对比
- Dimensions Rubric 编辑表格的「场景变体 tag」用 input + scenario_tag 字段，未实现设计稿的彩色 pill 风格（用 AntD Tag 替代）
- Versions 列表的「实验 / 最新」徽标只渲染「最新」（active），未保留设计稿的「实验」分支标记

---

## 8. ✅ 已解决 — 页面交互覆盖率补齐到高位（语句 79% → 97.5%，函数 57% → 85%）

**处理结果（2026-07-23 两轮测试加固）**：逐页补齐 happy / error / boundary 交互测试 + 共享原语单测，覆盖率达高位。**测试中发现并修复 1 个 P0 缺陷**（见 #10）。

**评测模块覆盖率（`src/evaluation/**`，11 测试文件 / 146 用例全通过）**：

| 区域 | Stmts | Branch | Funcs | Lines |
|------|-------|--------|-------|-------|
| **评测模块整体** | **97.5%** | **85.6%** | **85.2%** | **97.5%** |
| `api/index.ts` | 100% | 100% | 100% | 100% |
| `components/primitives.tsx` | 100% | 96.2% | 100% | 100% |
| `pages/Compare.tsx` | 99.0% | 78.3% | 91.7% | 99.0% |
| `pages/Dimensions.tsx` | 100% | 90.1% | 76.5% | 100% |
| `pages/Runs.tsx` | 98.7% | 85.5% | 80.0% | 98.7% |
| `pages/Schedules.tsx` | 97.2% | 85.7% | 90.5% | 97.2% |
| `pages/TestCaseEdit.tsx` | 100% | 79.4% | 70.0% | 100% |
| `pages/TestCases.tsx` | 100% | 88.4% | 85.7% | 100% |
| `pages/Versions.tsx` | 100% | 74.3% | 86.4% | 100% |
| `pages/RunDetail.tsx` | 86.4% | 86.8% | 70.6% | 86.4% |

**全量回归**：`tsc --noEmit` 0 错误；前端全量 48 文件 / 455 用例全通过，0 回归。

**交互覆盖提升（funcs，两轮合计）**：Runs 55%→80% · TestCaseEdit 10%→70% · Dimensions 33%→76% · TestCases 64%→86% · Versions 43%→86% · Schedules 50%→90% · Compare 75%→92%。

**剩余低优先级（不阻塞，边际收益低）**：
- `RunDetail.tsx` funcs 70% — 未覆盖部分是 `RadarChart` SVG 绘制（459-521），测试价值低。
- `Versions.tsx` branch 74% / `TestCaseEdit.tsx` branch 79% — 剩余为 `handleCreate`/`handleClone` 体内防御性 `?? null`/`?? false` 兜底分支（表单值恒存在，分支不可达）。
- `Dimensions.tsx` funcs 76% — 剩余为内联箭头函数渲染回调。

---

## 9. E2E smoke 已编写 + 类型校验通过，本地未执行（环境约束）

**已完成**：
- `tests/e2e/evaluation-smoke.spec.ts` — 3 条用例：进入测试集页 / 打开运行触发抽屉 / 进入对比页
- 全程 `page.route()` mock 评测接口（`/api/operator/evaluation/test-cases`、`/versions`），不依赖真实 PG 数据
- `@playwright/test` 已随 `npm install` 落地，`npx tsc --noEmit` 对该 spec 0 错误
- Chromium 浏览器二进制已就绪（chromium-1217 等）

**未执行原因**：`loginAsAdmin` 走**真实 UI 登录**（`POST /api/auth/login` → `GET /api/me`），需后端 `uvicorn :8000` + PG + admin 种子用户在线。当前环境三者均未运行（:8000 / :5175 / PG 均 down）。此约束与项目既有 E2E（`smoke.spec.ts`、`seeding-writer.spec.ts`）完全一致——并非评测模块引入。

**执行方式（用户本地或 CI）**：
```bash
# 1. 起后端
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
# 2. 跑评测 smoke（webServer 会自动起前端 dev :5175）
cd frontend && npx playwright test evaluation-smoke.spec.ts
```

**建议**：在 Phase 6 集成回归或 CI 中纳入评测 smoke，与既有 E2E 一同执行。

---

## 附：Deprecation 清理（2026-07-22 已完成）

- `destroyOnClose` → `destroyOnHidden`（6 处，antd 5.29.3 支持）
- `Input.Group compact` → flex `div`（Dimensions.tsx 分数区间，保留原行内布局）
- 清理后 `tsc --noEmit` 0 错误，5 个受影响页面测试 15/15 通过，控制台 deprecation 警告清零

---

## 10. 🔴 已修复 P0 — TestCaseEdit 标签提交发送字符串而非数组（2026-07-23 测试发现）

**现象**：测试「填名称+标签后保存」时断言失败，`createTestCase` 收到 `tags: "焦虑型"`（**字符串**），期望 `tags: ["焦虑型"]`（数组）。

**根因**：标签输入控件用了三层嵌套的同名 `Form.Item name="tags"`（外层校验 / 中层 / 内层 `shouldUpdate` 渲染）。AntD 把中层 Form.Item 的子节点——一个原生 `<input data-testid="tag-input">`——绑定成了 `tags` 字段控件：键入文本直接把表单 `tags` 置为字符串；`handleAddTag` 读 `getFieldValue('tags')` 得到字符串后 `.includes()` 短路，永远不追加成数组。

**影响（生产）**：后端 `EvalTestCaseCreate.tags: list[str]`，前端若发字符串 → FastAPI 422，**测试样本创建/编辑接口会失败**。属 P0。

**修复**（`frontend/src/evaluation/pages/TestCaseEdit.tsx`，最小改动）：
- 标签改为独立 React state `tags: string[]`（脱离表单绑定）
- `handleAddTag` / Tag 关闭 / 编辑回填 / `handleSave` body 全部改用 state
- 渲染块改为单一无 `name` 的 `Form.Item`（仅 label，不绑字段）+ state 驱动
- 移除 `FormValues.tags` 与 `initialValues.tags`（孤儿清理）
- 新增空标签校验（`handleSave` 入口）

**验证**：`TestCaseEdit.test.tsx` 11/11 通过；全量 390/391（唯一失败为既有 SeedingWriter flake，隔离重跑 23/23 通过，与本次无关）。`tsc --noEmit` 0 错误。

**教训**：交互测试触达真实提交路径，才暴露了这个"渲染正常但提交数据结构错"的缺陷——单测只验渲染覆盖不到。这正是「测试质量 > 数量」要拦的案例。

