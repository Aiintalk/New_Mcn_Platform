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

## 8. 页面交互处理函数覆盖率偏低（独立迭代项）

**现象（2026-07-22 PM 覆盖率核实）**：页面层语句/分支覆盖合理（64–99%），但**函数覆盖**集中在渲染/加载/错误路径，核心交互处理函数（表单提交、抽屉开关、批量替换、cron 校验）多为单测未触达。这些路径的正确性目前由 E2E smoke（#9）+ 人工 QA 兜底。

**待补交互测试（按缺口大小排序）**：
| 页面 | Funcs 覆盖 | 待覆盖核心交互 |
|------|-----------|---------------|
| `TestCaseEdit.tsx` | 10% | `handleSave`（新建/编辑提交 + JSON 校验）、`handleAddTag` |
| `Dimensions.tsx` | 33% | RubricEditor 增/删/整批替换、`handleSaveDimension` |
| `RunDetail.tsx` | 41% | `handleSaveCalibration`（人工校准提交，对应一期 C 能力）、`openCalibrate` |
| `Versions.tsx` | 43% | 创建抽屉提交、clone、`handleToggleActive` |
| `Schedules.tsx` | 50% | `handleSavePolicy`、croniter 客户端预校验分支 |

**建议**：按上表逐页补 `userEvent` 交互测试（参考 `src/__tests__/unit/api/*.test.ts` 的 mock 模式）。优先 RunDetail（人工校准 = 一期 C 能力核心）与 TestCaseEdit（CRUD 主流程）。

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

