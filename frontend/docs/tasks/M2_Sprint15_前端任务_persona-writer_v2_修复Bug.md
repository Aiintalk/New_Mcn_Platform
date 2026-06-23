# M2 Sprint 15 — 前端任务：人设脚本仿写 v2 修复 Bug（persona-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-23
> 对应需求文档：`docs/pm/M2_Sprint15_persona-writer_需求文档.md`
> 上一份：`frontend/docs/tasks/M2_Sprint15_前端任务_persona-writer_v1.md`
> 对应分支：`migrate/persona-writer`
> 本次迭代类型：修复Bug（v2）

---

## 一、范围（本次前端 v2 迭代）

v1 已完成 persona-writer 前端主体。本次 v2 聚焦 **E2E 验收期发现的前端 bug + 配套完善**，共 3 项前端改动：

1. ConfigTab 描述文案清理（移除开发风格占位符语法说明）
2. KolsPage 内容规划（content_plan）编辑 UI 补全
3. KolsPage 新建红人表单 status 默认值

## 二、BUG 清单

| BUG ID | 严重度 | 问题 | 根因 | 修复文件 |
|--------|-------|------|------|---------|
| BUG-030 | P2 | 管理端 PersonaWriter/ QianchuanWriter ConfigTab 显示开发风格描述（"4 条 Prompt（含占位符 `{{name}}` / `{{soul}}` ...）和轻重双 AI 模型配置"）| v1 实现时把开发者注释风格文案误当成用户可见描述 | `PersonaWriterConfigTab.tsx` + `QianchuanWriterConfigTab.tsx`（删除描述 div）|
| BUG-031 | P2 | 管理端红人管理详情抽屉无「内容规划」编辑区；新建红人表单也无 content_plan 输入框 | 后端 `kols.content_plan` 字段早已存在，CreateKolRequest 也支持，但前端 UI 从未补上 | `KolsPage.tsx`（详情抽屉加内容规划编辑卡片 + 新建表单加 Form.Item）+ `types/kol.ts`（CreateKolRequest/UpdateKolRequest/Kol 补 content_plan）|
| BUG-027（前端侧）| P1 | 用户新建红人不选状态时，后端默认 `'active'`，导致新建后下拉看不到 | 新建表单的 status `<Select>` 无 `initialValue`，用户不选就空 | `KolsPage.tsx:508` Form.Item 加 `initialValue="signed"` |

## 三、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | PersonaWriterConfigTab 移除开发风格描述 | `frontend/src/pages/admin/PersonaWriterConfigTab.tsx` | ✅ |
| F2 | QianchuanWriterConfigTab 移除开发风格描述 | `frontend/src/pages/admin/QianchuanWriterConfigTab.tsx` | ✅ |
| F3 | types/kol.ts 补 content_plan 字段 | `frontend/src/types/kol.ts` | ✅ |
| F4 | KolsPage 详情抽屉加内容规划编辑卡片 | `frontend/src/pages/admin/KolsPage.tsx` | ✅ |
| F5 | KolsPage 新建表单加内容规划 Form.Item | `frontend/src/pages/admin/KolsPage.tsx` | ✅ |
| F6 | KolsPage 新建表单 status 加 initialValue="signed" | `frontend/src/pages/admin/KolsPage.tsx:508` | ✅ |
| F7 | 任务文档（本文件）| 本文件 | ✅ |

## 四、实现要点

### 4.1 ConfigTab 描述移除

删除原描述 div：
```tsx
// 删除前
<div className="text-xs text-gray-500">
  4 条 Prompt（含占位符 `{{name}}` / `{{soul}}` / ...）和轻重双 AI 模型配置
</div>

// 删除后：直接去掉整个 div，ConfigTab 标题自描述
```

理由：占位符语法是开发者视角的实现细节，不应在管理端 UI 暴露给运营/管理员。管理员只需知道"在这里配置 4 条 Prompt 和 2 个 AI 模型"。

### 4.2 KolsPage 内容规划编辑

**详情抽屉**（在"人格档案"下方加新卡片）：
```tsx
<Card title="内容规划" bordered={false}>
  <Input.TextArea
    rows={6}
    value={contentPlanValue}
    onChange={e => setContentPlanValue(e.target.value)}
    placeholder="请输入内容规划"
  />
  <Button loading={contentPlanSaving} onClick={handleSaveContentPlan}>
    保存内容规划
  </Button>
</Card>
```

**新建表单**（在"人格档案"和"风格备注"之间）：
```tsx
<Form.Item label="内容规划" name="content_plan">
  <Input.TextArea rows={3} placeholder="请输入内容规划" />
</Form.Item>
```

`handleSaveContentPlan` 调用 `updateKol(detailId, { content_plan: contentPlanValue })`，保存后刷新详情。

### 4.3 新建表单 status 默认值

```tsx
// 修改前
<Form.Item label="状态" name="status">
  <Select>...</Select>
</Form.Item>

// 修改后
<Form.Item label="状态" name="status" initialValue="signed">
  <Select>...</Select>
</Form.Item>
```

与后端 ORM default `'signed'` 形成双保险：前端默认选中「签约中」，后端兜底（即使前端忘传或传 null 也用 'signed'）。

## 五、types/kol.ts 字段补全

```typescript
export interface Kol {
  // ... 原有字段
  persona?: string;
  content_plan?: string;  // 新增
}

export interface CreateKolRequest {
  // ... 原有字段
  persona?: string;
  content_plan?: string;  // 新增
}

export interface UpdateKolRequest {
  // ... 原有字段
  content_plan?: string;  // 新增
}
```

## 六、测试

本次 v2 改动以 UI 微调为主，暂未新增前端单测。全量回归 `vitest run` 通过，`tsc --noEmit` exit 0。

> 后续若 KolsPage 抽取为独立组件或新增交互（如 content_plan 富文本编辑），补对应组件测试。

## 七、契约与文档同步

| 文档 | 章节 | 改动 |
|------|------|------|
| `frontend/docs/README.md` | 目录结构 | 无需改（仅列文件名，功能描述未变）|
| 其他契约文档 | — | 本次仅前端 UI 完善，不改 API 契约 |

## 八、不在本次范围

- 红人列表筛选/排序增强（独立任务）
- 红人导入（批量 Excel 上传，独立任务）
- content_plan 富文本/Markdown 编辑（当前 TextArea 够用，按需迭代）
- 运营端添加红人权限（当前仅 admin，运营走 kol-intake 问卷流程，独立任务）
