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

## 6. Coverage 工具未安装（项目级）

**现象**：项目 `package.json` 有 `test:coverage` 脚本（`vitest run --coverage`），但 `@vitest/coverage-v8` 未安装。

**Phase 5 应对**：
- 仅运行了不带 `--coverage` 的测试套件
- 评测模块共 8 个页面 + 1 个 API 封装 + 1 个 primitives 组件 + 1 个 types 文件
- 组件测试 9 个文件、25 个用例全通过；convention guard 通过

**建议修复**：项目级 `npm i -D @vitest/coverage-v8`，再补全部门禁覆盖率目标。

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
