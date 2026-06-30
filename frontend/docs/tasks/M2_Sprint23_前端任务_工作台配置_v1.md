# M2 Sprint23 前端任务 — 红人工作台配置（KOL Workspace Config）v1

> 编写时间：2026-06-30
> 分支：`feature/kol-workspace`
> 需求文档：`docs/pm/M2_Sprint23_红人工作台配置_需求文档.md`
> 后端任务：`backend/docs/tasks/M2_Sprint23_后端任务_工作台配置_v1.md`

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | 类型定义 | `src/types/kolWorkspaceConfig.ts` |
| 2 | API 层 | `src/api/kolWorkspaceConfig.ts` |
| 3 | 管理端配置页 | `src/pages/admin/KolWorkspaceConfigPage.tsx` |
| 4 | 管理端路由注册 | `App.tsx` |
| 5 | 管理端红人列表入口 | `src/pages/admin/KolsPage.tsx` |
| 6 | 运营端工作台 tab 过滤 | `src/pages/operator/KolWorkspacePage.tsx` |
| 7 | 8 个 AI 模块传 kol_id | 各 Module 组件 |
| 8 | 组件测试 | `KolWorkspaceConfigPage.test.tsx` |

---

## 二、类型定义

文件：`src/types/kolWorkspaceConfig.ts`

```typescript
export type WorkspaceTabCode =
  | 'dashboard' | 'persona' | 'references' | 'products'
  | 'qianchuan-writer' | 'seeding-writer' | 'persona-writer'
  | 'livestream-writer' | 'livestream-review' | 'values-writer'
  | 'script-review' | 'retrospective';

export type ToolCode =
  | 'qianchuan-writer' | 'persona-writer' | 'seeding-writer'
  | 'livestream-writer' | 'livestream-review' | 'values-writer'
  | 'script-review' | 'retrospective';

// 各模块的 prompt_key 结构
export interface ToolPrompts {
  'qianchuan-writer': { system_prompt?: string };
  'persona-writer': { evaluation_prompt?: string; analysis_prompt?: string; writing_prompt?: string; iteration_prompt?: string };
  'seeding-writer': { sp_system?: string; parse_product?: string; structure_analysis?: string; ai_recommend?: string; writing?: string; iteration?: string };
  'livestream-writer': { system_prompt?: string };
  'livestream-review': { with_excel_prompt?: string; without_excel_prompt?: string };
  'values-writer': { extract_values_prompt?: string; emotion_direction_prompt?: string; writing_prompt?: string; iteration_prompt?: string };
  'script-review': { direct_prompt?: string; value_prompt?: string };
  'retrospective': { system_prompt?: string };
}

export interface KolWorkspaceConfig {
  kol_id: number;
  enabled_tabs: WorkspaceTabCode[];
  prompt_overrides: Partial<{ [K in ToolCode]: Partial<ToolPrompts[K]> }>;
  global_prompts: { [K in ToolCode]: ToolPrompts[K] };
}
```

---

## 三、API 层

文件：`src/api/kolWorkspaceConfig.ts`

```typescript
import { get, put } from './request';
import type { KolWorkspaceConfig, WorkspaceTabCode, ToolCode, ToolPrompts } from '../types/kolWorkspaceConfig';

export const getKolWorkspaceConfig = (kolId: number) =>
  get<KolWorkspaceConfig>(`/api/admin/kols/${kolId}/workspace-config`);

export const updateKolWorkspaceConfig = (
  kolId: number,
  data: {
    enabled_tabs: WorkspaceTabCode[];
    prompt_overrides: Partial<{ [K in ToolCode]: Partial<ToolPrompts[K]> }>;
  }
) => put<KolWorkspaceConfig>(`/api/admin/kols/${kolId}/workspace-config`, data);
```

---

## 四、管理端配置页

文件：`src/pages/admin/KolWorkspaceConfigPage.tsx`
路由：`/admin/kols/:kolId/workspace-config`

### 4.1 布局结构

```
顶部 Header
  ← 返回红人列表      红人头像 + 姓名 + 「工作台配置」标题
────────────────────────────────────────────────────
左侧区块（宽 320px）               右侧区块（flex: 1）
┌─ Section 1: 模块开关 ──────┐   ┌─ Section 2: AI Prompt 覆盖 ──┐
│ 全选 / 全不选              │   │ 折叠面板（8 个 AI 模块）       │
│ ─────────────────────────  │   │  ▶ 千川仿写  Badge:已覆盖 1 项 │
│ ✅ 工作台首页               │   │  ▶ 人设仿写  Badge:全局默认    │
│ ✅ 人物档案                 │   │  ▶ 种草仿写  ...              │
│ ✅ 素材库                   │   └────────────────────────────┘
│ ...（全 12 个）             │
└────────────────────────────┘       底部：保存 Button（loading）
```

### 4.2 模块开关（Section 1）

- 12 个 tab 逐一显示，对应 `NAV_ITEMS` 中的 label + icon
- `film-review` 固定 disabled（Sprint 23 暂不可用）
- 选中状态用 `enabled_tabs` 数组控制
- 「全选/全不选」快捷按钮

### 4.3 AI Prompt 覆盖（Section 2）

8 个 AI 模块，每个用 AntD `Collapse.Panel`：

- **标题**：模块名 + AntD `Badge`（有覆盖值的字段数 / 全局默认）
- **展开内容**：
  - 各 prompt_key 对应一个 `Form.Item`
  - `Input.TextArea`（rows=5）
  - `extra` 下方展示全局默认值（`global_prompts[tool][key]` 截取前 100 字符 + "..."）
  - 留空 = 不覆盖

各模块 prompt 字段的中文 label：

| tool_code | prompt_key | label |
|-----------|-----------|-------|
| qianchuan-writer | system_prompt | System Prompt |
| persona-writer | evaluation_prompt | 开头评估 Prompt |
| persona-writer | analysis_prompt | 结构拆解 Prompt |
| persona-writer | writing_prompt | 写作 Prompt |
| persona-writer | iteration_prompt | 迭代 Prompt |
| seeding-writer | sp_system | System Prompt |
| seeding-writer | parse_product | 产品解析 Prompt |
| seeding-writer | structure_analysis | 结构拆解 Prompt |
| seeding-writer | ai_recommend | AI 推荐 Prompt |
| seeding-writer | writing | 写作 Prompt |
| seeding-writer | iteration | 迭代 Prompt |
| livestream-writer | system_prompt | System Prompt |
| livestream-review | with_excel_prompt | 含投放数据 Prompt |
| livestream-review | without_excel_prompt | 无投放数据 Prompt |
| values-writer | extract_values_prompt | 提炼价值观 Prompt |
| values-writer | emotion_direction_prompt | 情绪方向 Prompt |
| values-writer | writing_prompt | 写作 Prompt |
| values-writer | iteration_prompt | 迭代 Prompt |
| script-review | direct_prompt | 千川直销 Prompt |
| script-review | value_prompt | 价值观 Prompt |
| retrospective | system_prompt | System Prompt |

### 4.4 保存逻辑

- 全页只有一个「保存」按钮
- 提交时合并 `enabled_tabs` + `prompt_overrides`（空字符串转为 null/不传）
- 成功后 `message.success('配置已保存')`

---

## 五、管理端路由注册

`App.tsx` 新增：
```tsx
const KolWorkspaceConfigPage = lazy(() => import('./pages/admin/KolWorkspaceConfigPage'));

// 在 admin routes 内：
<Route path="/admin/kols/:kolId/workspace-config" element={<KolWorkspaceConfigPage />} />
```

---

## 六、管理端红人列表入口

文件：`src/pages/admin/KolsPage.tsx`

每行操作列加「工作台配置」按钮（紧邻现有「编辑」按钮），点击：
```tsx
navigate(`/admin/kols/${kol.id}/workspace-config`)
```

---

## 七、运营端工作台 tab 过滤

文件：`src/pages/operator/KolWorkspacePage.tsx`

```typescript
// 新增 state
const [enabledTabs, setEnabledTabs] = useState<WorkspaceTabCode[] | null>(null);

// 加载时读取配置
useEffect(() => {
  getKolWorkspaceConfig(kolId)
    .then(config => setEnabledTabs(config.enabled_tabs))
    .catch(() => setEnabledTabs(null)); // 失败时降级显示全部
}, [kolId]);

// 过滤 NAV_ITEMS
const visibleNavItems = NAV_ITEMS.filter(item =>
  !enabledTabs || enabledTabs.includes(item.tab as WorkspaceTabCode)
);
```

---

## 八、8 个 AI 模块传 kol_id

各 Module 组件已接收 `kolId` prop，调用 API 时带上：

| 模块组件 | 需改动的 API 调用 | 新增字段 |
|---------|----------------|---------|
| `QianchuanWriterModule` | `chatStream` | `kol_id: kolId` |
| `PersonaWriterModule` | `evaluateOpening`、`analyzeStructure`、`chatStream` | `kol_id: kolId` |
| `SeedingWriterModule` | `extractSellingPoints`、`analyzeStructure`、`aiRecommend`、`chatStream` | `kol_id: kolId` |
| `LivestreamWriterModule` | `chatStream` | `kol_id: kolId` |
| `LivestreamReviewModule` | `generate` | `kol_id: kolId` |
| `ValuesWriterModule` | 已有 `kol_id`（无需改动） | — |
| `QianchuanScriptReviewModule` | `reviewScript` | `kol_id: kolId`（可 undefined） |
| `WorkspaceRetrospective` | `analyzeStream` | kol_id 在 path 中（无需改动） |

**注意**：`QianchuanScriptReviewModule` 在工作台内接收 `kolId?: number`，从独立页面访问时不传。

---

## 九、组件测试

文件：`src/__tests__/components/pages/KolWorkspaceConfigPage.test.tsx`

| # | 测试用例 |
|---|---------|
| 1 | 渲染模块开关列表（12 个 tab，film-review disabled） |
| 2 | 全选/全不选快捷操作 |
| 3 | 点击 tab 开关改变选中状态 |
| 4 | 展开 AI Prompt 面板，显示 global_prompts 默认值 |
| 5 | 填写 Prompt 后保存，调用 updateKolWorkspaceConfig |
| 6 | global_prompts 截断展示（超 100 字符显示 ...） |

---

## 十、验收口径

1. 管理端红人列表有「工作台配置」按钮，跳转正确
2. 配置页加载时显示当前 enabled_tabs + prompt_overrides + global_prompts
3. 模块开关保存后工作台左侧导航生效
4. Prompt 覆盖保存后 AI 调用使用覆盖值（可在 ai_call_logs 验证）
5. 留空字段不覆盖全局（fallback 行为正确）
6. 前端全量测试通过
