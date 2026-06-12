# M2 Sprint 04 · 前端任务 · tiktok-writer · v1

> 创建时间：2026-06-12
> 执行者：superpowers subagent-driven-development
> 状态：✅ 完成，TypeScript 编译零错误

---

## 一、任务范围

| 新建文件 | 说明 |
|---------|------|
| `frontend/src/types/tiktokWriter.ts` | TS 类型定义（Persona、StepState、ChatRequest、ExportWordRequest 等） |
| `frontend/src/api/tiktokWriter.ts` | API 调用（getPersonas、chatStream、exportWord） |
| `frontend/src/pages/operator/TiktokWriterPage.tsx` | 5 步仿写页面 |
| `frontend/src/__tests__/unit/api/tiktokWriter.test.ts` | API 单元测试（4 个） |

| 修改文件 | 说明 |
|---------|------|
| `frontend/src/App.tsx` | 新增路由 `/workspace/tiktok-writer` |
| `frontend/src/pages/operator/WorkspacePage.tsx` | 新增 tiktok-writer 导航分支 |

---

## 二、页面说明（TiktokWriterPage）

**5 步工作流：**

| 步骤 | 功能 |
|------|------|
| Step 1 · Source | 输入 TikTok 链接、文案、点赞数（≥10万校验） |
| Step 2 · Validate | AI 评估 Opening Hook（PASS/FAIL），选择创作者人设（可跳过） |
| Step 3 · Structure | AI 分析结构，前端解析 `===OPENING_START===` 标签锁定 Opening |
| Step 4 · Rewrite | AI 直写 / 用户提供方向两种模式，多轮迭代修改 |
| Step 5 · Export | 可编辑 finalBody，导出 Word 文档，提示已保存至产出中心 |

**System Prompt 构建：** 全部由前端动态构建后传给后端（含词数变量注入），后端不存储不修改。

---

## 三、API 层

| 函数 | 说明 |
|------|------|
| `getPersonas()` | GET /api/tools/tiktok-writer/kols/personas |
| `chatStream(body)` | fetch POST /api/tools/tiktok-writer/chat，返回 Response（调用方读 stream） |
| `exportWord(body)` | fetch POST /api/tools/tiktok-writer/export-word，返回 Blob |

---

## 四、测试结果

| 测试集 | 通过 |
|--------|------|
| unit/api/tiktokWriter.test.ts | 4/4 ✅ |
| 全量前端测试（vitest） | 69/69 ✅（2 个预存失败文件与本次改动无关） |
| TypeScript 编译 | 零错误 ✅ |

---

## 五、Commits

| Hash | 说明 |
|------|------|
| b212919 | feat: add tiktok-writer TypeScript types and API layer |
| 8ebb278 | feat: add TiktokWriterPage 5-step rewrite flow |
| efbd564 | feat: wire tiktok-writer route and workspace navigation |
