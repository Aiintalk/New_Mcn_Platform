# M2 Sprint 21 · 前端开发验收 · subtitle v1（字幕提取异步任务化 + 统一历史 + 软删除）

> 验收日期：2026-06-27
> 验收人：MCN_PM_Agent
> 对应任务单：`M2_Sprint21_前端任务_subtitle_v1.md`
> 对应需求：`docs/pm/M2_Sprint21_subtitle_需求文档.md`
> 对应测试报告：`backend/docs/tests/M2_Sprint21_测试报告_subtitle_v1.md`

---

## 一、文件落地核查

| 文件 | 状态 |
|------|------|
| `frontend/src/api/subtitle.ts`（类型重命名 + listHistory/deleteHistory） | ✅ 已修改 |
| `frontend/src/pages/operator/SubtitleExtractorPage.tsx`（异步轮询 + 删除批量列表 state） | ✅ 已修改 |
| `frontend/src/pages/operator/subtitle/HistoryList.tsx`（新建统一历史组件） | ✅ 已创建 |
| `frontend/src/__tests__/components/pages/SubtitleExtractorPage.test.tsx`（重写 5 个用例） | ✅ 已修改 |
| `frontend/src/__tests__/components/pages/HistoryList.test.tsx`（新建 6 个用例） | ✅ 已创建 |
| `frontend/docs/README.md` | ✅ 已更新 |

---

## 二、路由注册验证

SubtitleExtractorPage 路由在 Sprint 19 已注册，Sprint 21 沿用未改动：

```
App.tsx：<Route path="/workspace/subtitle-extractor" element={<SubtitleExtractorPage />} />
```

HistoryList 是 SubtitleExtractorPage 的子组件，无需独立路由。

---

## 三、前端守卫测试

`conventionGuard.test.ts` 扫描所有 `src/api/*.ts` 裸 fetch 调用：

- `api/subtitle.ts` 所有 JSON 调用均走 `request.ts` 的 `get` / `post` / `del`
- 无新增裸 fetch（思维导图 POST 走 `post()`，删除走 `del()`）
- 守卫测试中无 subtitle.ts 违规条目 ✅

---

## 四、TypeScript 编译

`npx tsc --noEmit`：**0 错误** ✅

关键类型变更已落地：
- `ExtractResponse`（新增）：`{ job_code: string; status: 'processing' }`
- `VideoMeta`（新增）：`{ play_url?, audio_url?, cover_url?, nickname?, digg_count?, aweme_id? }`
- `SubtitleItem extends VideoMeta`：扁平化字段已在类型层确认
- `SubtitleJob`：加 `kind: 'single' | 'batch'`
- `result` state 类型：`ExtractResult | null` → `SubtitleItem | null`
- `result.text` / `result?.text` → `result.transcript` / `result?.transcript`（全量替换，含可选链版本）

---

## 五、功能验证（vitest）

| 测试文件 | 用例 | 通过 |
|---------|------|------|
| `SubtitleExtractorPage.test.tsx`（重写） | 5 | 5/5 ✅ |
| `HistoryList.test.tsx`（新建） | 6 | 6/6 ✅ |
| **合计** | **11** | **11/11 ✅** |

### SubtitleExtractorPage.test.tsx（5 个）

| 用例 | 覆盖点 |
|------|--------|
| renders single-page layout with two sections | 初始渲染（两个 Card + HistoryList） |
| extracts subtitle via async polling and displays video info + cover | extract → 轮询 → 完成后显示封面 + 3 列元信息 + 字幕 |
| shows error message when single extract fails | 任务 failed 时显示 error 文本 |
| switches to mindmap view and shows root title | 切换思维导图视图，SVG 渲染分支 |
| counts pending batch items in textarea | 批量 TextArea 计数 |

### HistoryList.test.tsx（6 个）

| 用例 | 覆盖点 |
|------|--------|
| shows empty state when no history | 空列表 Empty 组件 |
| renders unified list of single + batch jobs | 单条 + 批量混合渲染 |
| expands single job to show full transcript and operations | 展开 → 懒加载详情 → 显示 transcript + 复制/思维导图按钮 |
| deletes a job and refreshes list | 删除 → mock deleteHistory 调用 → 列表刷新为空 |
| generates mindmap for a single job | 点生成思维导图 → mock generateMindmap 调用 → MindmapView 渲染 |
| expands batch job to show items list | 批量任务展开 → items list（含 status tag + error） |

### 关键测试技巧

- `vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` —— 让 setInterval 异步轮询在 fake timers 下能触发
- mock `MindmapView` 组件避免 jsdom 下 SVG layout 报错
- mock `extractSubtitle` 返回值改为 `{job_code, status:'processing'}`（不再返回完整结果）
- mock `getBatchByJobCode` 默认返回 completed 状态 + items[0] 含完整字段

---

## 六、红线合规核查

| 红线 | 核查项 | 状态 |
|------|--------|------|
| #3 JSON 调用走 request.ts | extractSubtitle / listHistory / deleteHistory / getBatchByJobCode / generateMindmap 全部走 `api/subtitle.ts` 封装 | ✅ |
| #3 例外（流式/FormData/Blob） | 本次无新增例外，所有调用都是 JSON | ✅ |
| #4 改接口同步契约 | 后端 Base_API §25 已同步更新（前端契约来源） | ✅ |
| #5 README 已更新 | `frontend/docs/README.md` 加注 Sprint 21 字幕异步任务化 + HistoryList 新建 | ✅ |

---

## 七、全量回归

```
npx vitest run
```

- **新增**：5 + 6 = 11 个字幕相关用例
- **全量结果**：233 passed / 7 pre-existing failed ✅
- **7 个 pre-existing failures 与字幕无关**：
  - `src/__tests__/unit/api/request.test.ts` × 7：测试硬编码 `http://localhost:8000`，但 `.env.local` 设为 8001（与字幕模块完全无关）

---

## 八、踩坑与修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | 批量 replace_all 漏可选链版本：`replace_all('result.text' → 'result.transcript')` 漏掉 5 处 `result?.text` | 单独再做一次 `replace_all('result?.text' → 'result?.transcript')` |
| 2 | fake timers + userEvent 异步轮询不触发（测试卡死） | `vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` |
| 3 | 后端旧代码 + 新前端联调陷阱：旧 /extract 返回 200 + 旧版响应，前端把 `resp.job_code` 当 undefined 启动轮询 `/batch/undefined` 永远 404 | 必须前后端同步部署/重启；前端刷新清 state |
| 4 | Windows watchfiles 不触发 uvicorn reload，改完代码后端仍是旧逻辑 | 手动 kill 3 个 python 进程（父 reload 监视器 / worker / multiprocessing 子）后重启 |

---

## 九、待用户人工验收（8 项）

代码与自动化测试已通过，**功能正确性需用户在浏览器验证**：

| # | 验收项 | 操作 |
|---|--------|------|
| 1 | 单条异步提取 | 刷新页面（Ctrl+Shift+R）→ 粘贴抖音链接 → 点提取 → 按钮变"解析中… Ns" |
| 2 | 历史记录实时显示 | 提交后历史记录区立刻出现 `single` 标签的 processing 任务 |
| 3 | 切换页面回来 | 切到其他功能页 → 1-3 分钟后回来 → 历史记录里任务变为 completed |
| 4 | 展开查看完整字幕 | 点"详情" → 显示完整 transcript + 复制/思维导图按钮 |
| 5 | 重新生成思维导图 | 点"生成思维导图" → 内联显示 SVG 思维导图 |
| 6 | 软删除 | 点"删除" → 列表移除 → DB 里 deleted_at 非 null（不物理删除） |
| 7 | 批量任务 | TextArea 输入或 Excel 拖拽 → 提交 → 历史记录里出现 `batch` 任务 |
| 8 | 跨用户隔离 | 切换账号后看不到他人的字幕历史 |

---

## 十、结论

- **代码与文件**：全部按任务单落地，无遗漏
- **类型**：tsc clean，0 错误
- **测试**：字幕模块 11/11 全过；全量 233 passed，pre-existing 7 与字幕无关不阻塞
- **红线**：4 项全部合规
- **守卫**：subtitle.ts 无违规条目

**准予通过开发验收**，转入用户浏览器人工验收环节（8 项清单见第九节）。
