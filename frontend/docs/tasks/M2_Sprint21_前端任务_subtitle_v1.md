# M2 Sprint 21 — 前端任务：单条轮询 + 统一历史记录组件

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-27
> **依赖需求**：`docs/pm/M2_Sprint21_subtitle_需求文档.md`
> **基线**：Sprint 19 字幕提取 + Sprint 20 单页面布局（封面图/思维导图/XMind 导出/Excel 拖拽）

---

## 一、任务范围

| # | 任务 | 文件 |
|---|------|------|
| 1 | API 类型 + 函数重命名 | `src/api/subtitle.ts` |
| 2 | SubtitleExtractorPage 改轮询模式 | `src/pages/operator/SubtitleExtractorPage.tsx` |
| 3 | 新建 HistoryList 组件 | `src/pages/operator/subtitle/HistoryList.tsx` |
| 4 | 重写 SubtitleExtractorPage 测试 | `src/__tests__/components/pages/SubtitleExtractorPage.test.tsx` |
| 5 | 新建 HistoryList 测试 | `src/__tests__/components/pages/HistoryList.test.tsx` |
| 6 | 前端 README 更新 | `frontend/docs/README.md` |

---

## 二、API 层变更（`src/api/subtitle.ts`）

### 类型变更

```typescript
// 新增：异步 extract 响应
export interface ExtractResponse {
  job_code: string;
  status: 'processing';
}

// 新增：视频元信息（SubtitleItem 继承）
export interface VideoMeta {
  play_url?: string;
  audio_url?: string;
  cover_url?: string | null;
  nickname?: string;
  digg_count?: number;
  aweme_id?: string;
}

// SubtitleItem 继承 VideoMeta（API 响应里 meta_json 已扁平化到顶层）
export interface SubtitleItem extends VideoMeta {
  id: number;
  row_number: number;
  original_url: string;
  title: string;
  transcript: string;
  status: 'pending' | 'processing' | 'success' | 'failed';
  error: string;
}

// SubtitleJob 加 kind
export interface SubtitleJob {
  // ...原有字段
  kind: 'single' | 'batch';  // 新增
}
```

### 函数变更

| 原函数 | 新函数 | 行为 |
|--------|--------|------|
| `extractSubtitle` | `extractSubtitle`（同名） | 返回类型改 `ExtractResponse`（只含 job_code） |
| `listMyBatches` | `listHistory` | 重命名；保留 `listMyBatches` 别名（兼容） |
| — | `deleteHistory`（**新增**） | `del<{job_code, deleted}>(/api/tools/subtitle/batch/{jobCode})` |

---

## 三、SubtitleExtractorPage 改造

### 单条提取：同步 → 轮询

**原**：`await extractSubtitle()` → 直接拿结果展示
**新**：

```typescript
const singleJobCodeRef = useRef<string | null>(null);
const singlePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

const doExtract = async () => {
  // ...validation...
  const resp = await extractSubtitle({ share_text: text });
  singleJobCodeRef.current = resp.job_code;
  startSinglePolling(resp.job_code);
};

const pollSingle = async (jobCode: string) => {
  const job = await getBatchByJobCode(jobCode);
  if (job.status === 'completed' || job.status === 'failed') {
    stopSinglePolling(); stopExtractTimer(); setExtracting(false);
    const item = job.items?.[0];
    if (job.status === 'completed' && item?.status === 'success') {
      setResult(item);  // SubtitleItem 直接作为 result
    } else {
      message.error(item?.error || '字幕提取失败');
    }
  }
};

const startSinglePolling = (jobCode: string) => {
  pollSingle(jobCode);  // 立即拉一次
  singlePollRef.current = setInterval(() => pollSingle(jobCode), 3000);  // 3s 轮询
};
```

### result 类型：ExtractResult → SubtitleItem

所有引用从 `result.text` 改为 `result.transcript`（含可选链版本 `result?.transcript`）。

### 删除批量列表（由 HistoryList 替代）

删除的 JSX/state：
- `<List>「我的批量任务」`（原 lines 780-814）
- `batchJob Card`（原 lines 816-871）
- state：`batchList`、`batchJob`、`pollRef`
- 函数：`loadBatchList`、`pollBatch`、`startPolling`、`selectJob`、`batchProgress`

新增：
- state：`historyRefreshSignal`（递增触发 HistoryList 刷新）
- JSX：`<HistoryList refreshSignal={historyRefreshSignal} />`

`doCreateBatch` 简化：成功后 `setHistoryRefreshSignal((s) => s + 1)`，由 HistoryList 自动轮询。

---

## 四、HistoryList 组件（新建）

**位置**：`src/pages/operator/subtitle/HistoryList.tsx`（~360 行）

**Props**：
```typescript
interface HistoryListProps {
  refreshSignal?: number;  // 递增触发刷新
}
```

**功能**：
1. 挂载 + refreshSignal 变化时调 `listHistory(1, 20)` 加载列表
2. 列表里只要有 processing 状态的任务，每 5s 自动刷新
3. 每行展开/收起：懒加载 `getBatchByJobCode` 拿详情
4. **单条任务（kind='single'）展开后**：
   - 显示完整 transcript
   - 复制按钮（clipboard API）
   - 生成/重新生成思维导图（调 `generateMindmap(transcript)`，结果缓存到 `mindmapCache[jobCode]`）
   - 思维导图内联展示（MindmapView 组件）+ 缩放控件
5. **批量任务（kind='batch'）展开后**：
   - Progress 进度条
   - items 列表（status tag + title + original_url + transcript 预览 + error）
6. 删除按钮（调 `deleteHistory`，成功后刷新列表）

**关键陷阱**：
- 用 `useCallback` 包 `loadList` 避免 useEffect 无限触发
- 自动轮询 useEffect 依赖 `jobs.some(j => j.status === 'processing')`，无 active 任务时停轮询
- mindmap 缓存按 jobCode key，避免同一任务多次调 AI

---

## 五、测试

### `SubtitleExtractorPage.test.tsx`（重写）

**关键改动**：
- mock `listMyBatches` → `listHistory`（同时保留 `listMyBatches` 别名 mock）
- mock `extractSubtitle` 返回值改为 `{job_code, status:'processing'}`（不再返回完整结果）
- mock `getBatchByJobCode` 默认返回 completed 状态 + items[0] 含完整字段
- 用 `vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` 让 setInterval 触发

**用例**（5 个）：
1. renders single-page layout with two sections
2. extracts subtitle via async polling and displays video info + cover
3. shows error message when single extract fails
4. switches to mindmap view and shows root title
5. counts pending batch items in textarea

### `HistoryList.test.tsx`（新建）

**用例**（6 个）：
1. shows empty state when no history
2. renders unified list of single + batch jobs
3. expands single job to show full transcript and operations
4. deletes a job and refreshes list
5. generates mindmap for a single job
6. expands batch job to show items list

**Mock 策略**：
- `vi.mock('../../../api/subtitle', ...)` mock 4 个函数
- `vi.mock('../../../pages/operator/subtitle/MindmapView', ...)` 避免 SVG layout 在 jsdom 下报错

---

## 六、README 更新

`frontend/docs/README.md` 两行加注：
- `api/subtitle.ts`：Sprint 19 迁移；Sprint 21 异步任务化（extract 返回 job_code，前端轮询；listHistory 统一历史 + deleteHistory 软删除）
- `SubtitleExtractorPage.tsx`：Sprint 21 异步任务化 + HistoryList.tsx 新建

---

## 七、回归验证

```bash
cd frontend
npx tsc --noEmit                                                    # 类型检查
npx vitest run src/__tests__/components/pages/SubtitleExtractorPage.test.tsx
npx vitest run src/__tests__/components/pages/HistoryList.test.tsx
npx vitest run                                                      # 全量（pre-existing 7 个 port-mismatch 失败与字幕无关）
```

**通过标准**：5+6 字幕测试全过，tsc clean，全量 233 passed。
