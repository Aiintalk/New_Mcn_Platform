# M2 Sprint20 前端任务 — 价值观仿写（values-writer）v1

> 编写时间：2026-06-26
> 分支：`feature/kol-workspace`

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | API 层 | `src/api/valuesWriter.ts`（新建） |
| 2 | 管理端 ConfigTab | `src/pages/admin/ValuesWriterConfigTab.tsx`（新建） |
| 3 | 运营端 ValuesWriterModule | `src/pages/operator/ValuesWriterPage.tsx`（新建，同时导出 Module） |
| 4 | 工作台接入 | `src/pages/operator/KolWorkspacePage.tsx`（改造） |
| 5 | 管理端接入 | `src/pages/admin/WorkspaceConfigPage.tsx` 或 `ServiceConfigPage.tsx`（确认后接入） |
| 6 | 单元测试 | `src/__tests__/components/pages/ValuesWriterPage.test.tsx`（新建） |

---

## 二、API 层（valuesWriter.ts）

```typescript
// src/api/valuesWriter.ts
import { get, put, postSSE } from './request';

export const getConfig = () =>
  get<ValuesWriterConfig>('/api/admin/values-writer/config');

export const updateConfig = (body: Partial<ValuesWriterConfig>) =>
  put('/api/admin/values-writer/config', body);

export const extractValues = (kolId: number, extraContext?: string) =>
  post<{ values: string[] }>('/api/operator/values-writer/extract-values', {
    kol_id: kolId,
    extra_context: extraContext,
  });

// SSE 流式接口（参考 seedingWriter.ts chatStream 模式）
export const emotionDirectionStream = (
  body: { kol_id: number; selected_values: string[]; tone?: string },
  onDelta: (delta: string) => void,
) => postSSE('/api/operator/values-writer/emotion-direction', body, onDelta);

export const writeStream = (
  body: { kol_id: number; selected_values: string[]; emotion_direction: string; product_context?: string },
  onDelta: (delta: string) => void,
) => postSSE('/api/operator/values-writer/write', body, onDelta);

export const iterateStream = (
  body: { kol_id: number; content: string; instruction: string },
  onDelta: (delta: string) => void,
) => postSSE('/api/operator/values-writer/iterate', body, onDelta);
```

类型定义加进 `src/types/valuesWriter.ts`：
```typescript
export interface ValuesWriterConfig {
  id: number;
  config_key: string;
  extract_values_prompt: string | null;
  emotion_direction_prompt: string | null;
  writing_prompt: string | null;
  iteration_prompt: string | null;
  model_id: number | null;
  is_active: boolean;
}
```

---

## 三、运营端 ValuesWriterPage（同时导出 Module）

### 3.1 4 步向导流程

```
Step 1: 选达人（独立页面模式）/ 跳过（Module 模式，kolId 由父组件传入）
Step 2: 选价值观（extractValues → 展示清单，用户勾选 1-3 个）
Step 3: 情绪方向（emotionDirectionStream → 流式输出）
Step 4: 生成内容（writeStream → 流式输出）+ 迭代（iterateStream）
```

### 3.2 交互细节

**Step 2（选价值观）：**
- 调 extractValues，loading 期间显示 Spin
- 返回 values 数组，每个 value 显示为 Tag/Badge，可点击选中（高亮）
- 限制最多选 3 个，超出提示
- 「下一步」按钮，至少选 1 个才可点

**Step 3（情绪方向）：**
- 显示已选价值观摘要
- tone 可选输入（情感基调，placeholder="轻松、真实、有温度..."）
- 「生成情绪方向」按钮 → emotionDirectionStream 流式输出到文本框
- 文本框可手动编辑（流式完成后变为 editable）
- 「下一步」按钮

**Step 4（生成内容）：**
- 可选填 product_context（产品关联，如"本期推广XX产品"）
- 「开始生成」→ writeStream 流式输出到内容区
- 内容区下方：对话框 + 「迭代优化」按钮 → iterateStream
- 工具栏：「导出 TXT」「复制」

### 3.3 Props

```typescript
// Module 模式（工作台内嵌）
export function ValuesWriterModule({ kolId }: { kolId: number }) { ... }

// 独立页面（保留选达人 Step 1）
export default function ValuesWriterPage() { ... }
```

---

## 四、管理端 ConfigTab（ValuesWriterConfigTab.tsx）

参考 `SeedingWriterConfigTab.tsx` 结构：
- 4 个 Prompt 的 TextArea（extract_values / emotion_direction / writing / iteration）
- 模型选择下拉（接口：GET /api/admin/ai/models）
- 启用开关
- 保存按钮 → PUT config → 成功 toast

---

## 五、工作台接入

`KolWorkspacePage.tsx`：
- `values-writer` 导航项移除 `disabled: true`
- 主内容区新增 `{activeTab === 'values-writer' && <ValuesWriterModule kolId={kolId} />}`

---

## 六、管理端接入

找到现有工具配置页（`WorkspaceConfigPage.tsx` 或 `ServiceConfigPage.tsx`），参照 `SeedingWriterConfigTab` 的接入方式，添加「价值观仿写」Tab。

---

## 七、单元测试要点

- `test_config_tab_loads`：GET config mock → 渲染 4 个 TextArea
- `test_extract_values`：mock extractValues → 渲染 Tag 列表
- `test_step_navigation`：选价值观 → 下一步 → Step 3 显示
- `test_streaming_write`：mock writeStream → onDelta 回调触发 → 内容区更新

---

## 八、验收口径

1. 从工作台左侧点击「价值观仿写」→ 直接进入 Step 2（选价值观，达人已锁定）
2. 从运营端直接访问路由 `/workspace/values-writer` → 显示 Step 1（选达人）
3. 管理端「价值观仿写」Tab 可保存 Prompt 配置
4. `npx tsc --noEmit` 无报错
5. `npx vitest run` ≥ 198 passed
