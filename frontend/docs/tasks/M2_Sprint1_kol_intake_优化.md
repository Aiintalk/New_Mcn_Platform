# 前端任务单 · M2 Sprint 1 kol-intake 优化

> 本次为 kol-intake 功能上线前的集中修缮，共 7 项改动。
> 涉及文件：`types/intake.ts` / `pages/intake/IntakePage.tsx` / `pages/operator/OperatorIntakePage.tsx` / `pages/admin/AdminIntakePage.tsx`。
> 新增 API 调用：`GET /api/admin/intake/submissions/{id}` + `POST /api/admin/intake/submissions/{id}/regenerate`（已有后端实现）。

---

## 改动 1 — 补全 IntakeSubmission 类型

**文件**：`src/types/intake.ts`

`IntakeSubmission` 缺少 `operator_downloaded_at` 字段，导致 AdminIntakePage 用了类型强转。直接补上：

```ts
export interface IntakeSubmission {
  id: number;
  link_id: number;
  kol_name: string | null;
  report_status: 'pending' | 'generating' | 'ready' | 'failed';
  created_at: string;
  report_generated_at: string | null;
  kol_downloaded_at: string | null;
  operator_downloaded_at: string | null;   // ← 补上
  messages?: ChatMessage[];
  ai_report?: string | null;
  operator_id?: number | null;             // ← 补上（admin 接口返回）
}
```

---

## 改动 2 — 新增 Admin 详情 API 函数

**文件**：`src/api/intake.ts`

补充两个 admin 接口调用：

```ts
// 已有 getAdminSubmissions，在其后面补：

export const getAdminSubmissionDetail = (id: number) =>
  get<IntakeSubmission>(`/api/admin/intake/submissions/${id}`);

export const regenerateReport = (id: number) =>
  post<null>(`/api/admin/intake/submissions/${id}/regenerate`, {});
```

---

## 改动 3 — IntakePage：轮询加超时保护

**文件**：`src/pages/intake/IntakePage.tsx`

当前 `pollStatus()` 无上限，报告卡住会无限请求。加最大等待 5 分钟（75 次 × 4 秒）：

**改前：**
```tsx
function pollStatus() {
  if (!token) return;
  pollRef.current = setInterval(async () => {
    try {
      const res = await getIntakeStatus(token!);
      setReportStatus(res.report_status);
      setPollCount(c => c + 1);
      if (res.report_status === 'ready' || res.report_status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        if (res.report_status === 'ready') setPhase('ready');
      }
    } catch {
      // ignore poll errors
    }
  }, 4000);
}
```

**改后：**
```tsx
const MAX_POLL = 75; // 75 × 4s = 5 分钟

function pollStatus() {
  if (!token) return;
  let count = 0;
  pollRef.current = setInterval(async () => {
    count += 1;
    try {
      const res = await getIntakeStatus(token!);
      setReportStatus(res.report_status);
      setPollCount(count);
      if (res.report_status === 'ready' || res.report_status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        if (res.report_status === 'ready') setPhase('ready');
        return;
      }
    } catch {
      // ignore poll errors
    }
    if (count >= MAX_POLL) {
      if (pollRef.current) clearInterval(pollRef.current);
      setReportStatus('failed');
    }
  }, 4000);
}
```

---

## 改动 4 — OperatorIntakePage：详情弹窗扩展为「对话 / 报告」双 Tab

**文件**：`src/pages/operator/OperatorIntakePage.tsx`

### 4.1 弹窗加 Tab 切换

当前弹窗只展示 `messages` 对话历史。改为：
- **Tab 1「对话记录」**：原有对话气泡（不改）
- **Tab 2「入驻报告」**：展示 `ai_report`（Markdown 文本），底部放下载按钮

`ai_report` 是 Markdown 格式，用 `<pre>` 或简单 whitespace 渲染即可（不需要引入 markdown 库，`white-space: pre-wrap` 足够）。

### 4.2 弹窗底部加下载按钮

报告 Tab 底部固定两个按钮：「下载 Word」「下载 PDF」，仅 `report_status === 'ready'` 时显示。

### 4.3 替换实现

**Modal 部分改为：**

```tsx
{/* Submission detail modal */}
<Modal
  title={`${selectedSub?.kol_name || '未知'} · 提交详情`}
  open={!!selectedSub}
  onCancel={() => { setSelectedSub(null); setDetailTab('messages'); }}
  footer={null}
  width={680}
  destroyOnClose
>
  {selectedSub && (
    <>
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {(['messages', 'report'] as const).map(t => (
          <button
            key={t}
            onClick={() => setDetailTab(t)}
            className={detailTab === t ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
          >
            {t === 'messages' ? '对话记录' : '入驻报告'}
          </button>
        ))}
      </div>

      {detailTab === 'messages' && (
        <div style={{ maxHeight: 420, overflowY: 'auto', padding: '4px 0' }}>
          {(selectedSub.messages ?? []).map((msg, i) => (
            <div key={i} style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              gap: 8, marginBottom: 12, alignItems: 'flex-start',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: msg.role === 'user' ? 'var(--gray-200)' : 'var(--brand)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
                color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
              }}>
                {msg.role === 'user' ? '红' : 'AI'}
              </div>
              <div style={{
                maxWidth: '80%',
                background: msg.role === 'user' ? 'var(--brand)' : 'var(--bg-page)',
                color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                padding: '8px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.6,
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {detailTab === 'report' && (
        <div>
          {selectedSub.report_status !== 'ready'
            ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  {selectedSub.report_status === 'failed' ? '❌' : '⏳'}
                </div>
                <div className="empty-state-text">
                  {selectedSub.report_status === 'failed' ? '报告生成失败' : '报告尚未生成完成'}
                </div>
              </div>
            )
            : (
              <>
                <div style={{
                  maxHeight: 380, overflowY: 'auto',
                  background: 'var(--bg-page)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', padding: '16px 20px',
                  fontSize: 13, lineHeight: 1.8, color: 'var(--gray-800)',
                  whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)',
                }}>
                  {selectedSub.ai_report || '报告内容为空'}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                  <button className="btn btn-ghost btn-sm"
                    onClick={() => window.open(getOperatorDownloadUrl(selectedSub.id, 'pdf'), '_blank')}>
                    下载 PDF
                  </button>
                  <button className="btn btn-primary btn-sm"
                    onClick={() => window.open(getOperatorDownloadUrl(selectedSub.id, 'docx'), '_blank')}>
                    下载 Word
                  </button>
                </div>
              </>
            )
          }
        </div>
      )}
    </>
  )}
</Modal>
```

### 4.4 同步修改 state

在组件顶部加一个 Tab 状态：

```tsx
const [detailTab, setDetailTab] = useState<'messages' | 'report'>('messages');
```

`openDetail` 函数打开弹窗时重置 Tab：

```tsx
async function openDetail(id: number) {
  try {
    const detail = await getOperatorSubmissionDetail(id);
    setSelectedSub(detail);
    setDetailTab('messages');   // ← 每次打开默认回对话记录
  } catch (err: unknown) {
    message.error((err as Error).message || '加载详情失败');
  }
}
```

---

## 改动 5 — AdminIntakePage：修复题目表格列头

**文件**：`src/pages/admin/AdminIntakePage.tsx`

当前 `<thead>` 列顺序与 `<tbody>` 渲染顺序不符（分类用了 rowSpan 顶在最前，但列头写的是「序号 → 分类」）。

**改前：**
```tsx
<tr>
  <th style={{ width: 40 }}>序号</th>
  <th>分类</th>
  <th>题目</th>
  ...
</tr>
```

**改后：**
```tsx
<tr>
  <th style={{ width: 80 }}>分类</th>
  <th style={{ width: 48 }}>序号</th>
  <th>题目</th>
  ...
</tr>
```

---

## 改动 6 — AdminIntakePage：修复提交记录「运营 ID」列

**文件**：`src/pages/admin/AdminIntakePage.tsx`

提交记录表格第三列显示 `sub.link_id`，与列头「运营 ID」不符。

**改为显示 `operator_id`**（`IntakeSubmission` 已在改动 1 中补上此字段）：

```tsx
// 改前
<th>运营 ID</th>
<td style={{ fontSize: 12 }}>{sub.link_id}</td>

// 改后
<th>运营</th>
<td style={{ fontSize: 12, color: 'var(--gray-500)' }}>
  {sub.operator_id ? `#${sub.operator_id}` : '—'}
</td>
```

> 注：如果后端 admin 提交列表接口返回了 operator 用户名，可直接显示用户名；如果只有 id，显示 `#id` 即可，不需要额外请求。

---

## 改动 7 — AdminIntakePage：补全量提交「查看详情」和「重新生成」

**文件**：`src/pages/admin/AdminIntakePage.tsx`

### 7.1 import 新增

```ts
import { getAdminSubmissions, getAdminSubmissionDetail, regenerateReport } from '../../api/intake';
```

### 7.2 state 新增

```tsx
const [selectedAdminSub, setSelectedAdminSub] = useState<IntakeSubmission | null>(null);
const [adminDetailTab, setAdminDetailTab] = useState<'messages' | 'report'>('messages');
```

### 7.3 提交记录表格加操作列

在提交记录表格最后加一列「操作」：

```tsx
<th style={{ textAlign: 'right' }}>操作</th>

// tbody 对应行：
<td>
  <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
    <button className="btn btn-ghost btn-sm" onClick={() => openAdminDetail(sub.id)}>
      查看
    </button>
    {sub.report_status === 'failed' && (
      <Popconfirm
        title="重新触发报告生成？"
        okText="确认"
        cancelText="取消"
        onConfirm={() => handleRegenerate(sub.id)}
      >
        <button className="btn btn-ghost btn-sm">重新生成</button>
      </Popconfirm>
    )}
  </div>
</td>
```

### 7.4 函数实现

```tsx
async function openAdminDetail(id: number) {
  try {
    const detail = await getAdminSubmissionDetail(id);
    setSelectedAdminSub(detail);
    setAdminDetailTab('messages');
  } catch (err: unknown) {
    message.error((err as Error).message || '加载详情失败');
  }
}

async function handleRegenerate(id: number) {
  try {
    await regenerateReport(id);
    message.success('已触发重新生成，请稍后刷新查看');
    getAdminSubmissions().then(setSubmissions).catch(() => {});
  } catch (err: unknown) {
    message.error((err as Error).message || '操作失败');
  }
}
```

### 7.5 Admin 详情弹窗

在页面底部加，结构与 OperatorIntakePage 的弹窗相同，下载按钮调 admin 接口（无运营下载限制）：

```tsx
<Modal
  title={`${selectedAdminSub?.kol_name || '未知'} · 提交详情`}
  open={!!selectedAdminSub}
  onCancel={() => setSelectedAdminSub(null)}
  footer={null}
  width={680}
  destroyOnClose
>
  {selectedAdminSub && (
    <>
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {(['messages', 'report'] as const).map(t => (
          <button
            key={t}
            onClick={() => setAdminDetailTab(t)}
            className={adminDetailTab === t ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
          >
            {t === 'messages' ? '对话记录' : '入驻报告'}
          </button>
        ))}
      </div>

      {adminDetailTab === 'messages' && (
        <div style={{ maxHeight: 420, overflowY: 'auto', padding: '4px 0' }}>
          {(selectedAdminSub.messages ?? []).map((msg, i) => (
            <div key={i} style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              gap: 8, marginBottom: 12, alignItems: 'flex-start',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: msg.role === 'user' ? 'var(--gray-200)' : 'var(--brand)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
                color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
              }}>
                {msg.role === 'user' ? '红' : 'AI'}
              </div>
              <div style={{
                maxWidth: '80%',
                background: msg.role === 'user' ? 'var(--brand)' : 'var(--bg-page)',
                color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                padding: '8px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.6,
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {adminDetailTab === 'report' && (
        <div>
          {selectedAdminSub.report_status !== 'ready'
            ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  {selectedAdminSub.report_status === 'failed' ? '❌' : '⏳'}
                </div>
                <div className="empty-state-text">
                  {selectedAdminSub.report_status === 'failed' ? '报告生成失败' : '报告尚未生成完成'}
                </div>
              </div>
            )
            : (
              <>
                <div style={{
                  maxHeight: 380, overflowY: 'auto',
                  background: 'var(--bg-page)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', padding: '16px 20px',
                  fontSize: 13, lineHeight: 1.8, color: 'var(--gray-800)',
                  whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)',
                }}>
                  {selectedAdminSub.ai_report || '报告内容为空'}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                  <button className="btn btn-ghost btn-sm"
                    onClick={() => window.open(`/api/admin/intake/submissions/${selectedAdminSub.id}/download?format=pdf`, '_blank')}>
                    下载 PDF
                  </button>
                  <button className="btn btn-primary btn-sm"
                    onClick={() => window.open(`/api/admin/intake/submissions/${selectedAdminSub.id}/download?format=docx`, '_blank')}>
                    下载 Word
                  </button>
                </div>
              </>
            )
          }
        </div>
      )}
    </>
  )}
</Modal>
```

---

## 改动汇总

| # | 文件 | 类型 | 说明 |
|---|------|------|------|
| 1 | `types/intake.ts` | Bug 修复 | 补 `operator_downloaded_at` + `operator_id` 字段 |
| 2 | `api/intake.ts` | 功能补全 | 新增 `getAdminSubmissionDetail` / `regenerateReport` |
| 3 | `pages/intake/IntakePage.tsx` | 可靠性 | 轮询加最大 75 次（5 分钟）超时保护 |
| 4 | `pages/operator/OperatorIntakePage.tsx` | 功能增强 | 详情弹窗改为对话/报告双 Tab，报告 Tab 含下载按钮 |
| 5 | `pages/admin/AdminIntakePage.tsx` | Bug 修复 | 题目表格列头顺序修正 |
| 6 | `pages/admin/AdminIntakePage.tsx` | Bug 修复 | 提交记录「运营」列改显示 `operator_id` |
| 7 | `pages/admin/AdminIntakePage.tsx` | 功能补全 | 全量提交加「查看详情」弹窗 + `failed` 状态加「重新生成」按钮 |

**改动量**：约 120 行净增/改，无新依赖引入，TypeScript 零新 `any`。
