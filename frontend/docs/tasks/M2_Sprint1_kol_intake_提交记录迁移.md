# 前端任务单 · kol-intake 提交记录迁移至任务中心

> 目标：
> 1. 运营端「红人信息采集助手」页面只保留「创建链接」功能，不再显示提交记录
> 2. 提交记录迁移至「任务中心」，作为独立 Tab「采集记录」
>
> 涉及文件：
> - `src/pages/operator/OperatorIntakePage.tsx`
> - `src/pages/operator/TasksPage.tsx`
>
> 不涉及：API、类型、路由均不改动

---

## 改动 1 — OperatorIntakePage：精简为纯链接管理

**文件**：`src/pages/operator/OperatorIntakePage.tsx`

移除所有「提交记录」相关代码，只保留链接管理。

### 1.1 删除的 import

```tsx
// 删除这两行（submissions 相关）
import { getOperatorSubmissions, getOperatorSubmissionDetail, getOperatorDownloadUrl } from '../../api/intake';
// getOperatorDownloadUrl 也一并删除（detail modal 里用到的）
```

改后 import 只保留：
```tsx
import { createIntakeLink, getIntakeLinks } from '../../api/intake';
import type { IntakeLink } from '../../types/intake';
```

### 1.2 删除的 state

删除以下 state 声明：
```tsx
// 全部删除
const [tab, setTab] = useState<'links' | 'submissions'>('links');
const [submissions, setSubmissions] = useState<IntakeSubmission[]>([]);
const [selectedSub, setSelectedSub] = useState<IntakeSubmission | null>(null);
const [detailTab, setDetailTab] = useState<'messages' | 'report'>('messages');
```

### 1.3 删除的函数和 useEffect

```tsx
// 删除 loadSubs
const loadSubs = useCallback(async () => { ... }, []);

// 删除 submissions tab 触发的 useEffect
useEffect(() => { if (tab === 'submissions') loadSubs(); }, [tab, loadSubs]);

// 删除 openDetail
async function openDetail(id: number) { ... }
```

### 1.4 return 简化

去掉 Tab 切换 UI 和提交记录内容，只保留链接管理部分：

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">红人信息采集助手</h1>
        <p className="page-desc">生成专属链接，邀请红人完成 AI 对话采集</p>
      </div>
      <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ 创建链接</button>
    </div>

    {/* 链接列表 card（原样保留，去掉外层 tab 判断） */}
    <div className="card">
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
          : links.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无链接，点击「创建链接」开始</div></div>
          : (
            <table className="data-table">
              {/* 原有表格，原样保留 */}
            </table>
          )}
      </div>
    </div>

    {/* 创建链接 Modal（原样保留） */}
    <Modal ... />

    {/* 删除：提交记录 Tab 内容 */}
    {/* 删除：Submission detail Modal */}
  </>
);
```

---

## 改动 2 — TasksPage：新增「采集记录」Tab

**文件**：`src/pages/operator/TasksPage.tsx`

### 2.1 import 补充

```tsx
import { Tabs } from 'antd';
import {
  getOperatorSubmissions,
  getOperatorSubmissionDetail,
  getOperatorDownloadUrl,
} from '../../api/intake';
import type { IntakeSubmission } from '../../types/intake';
```

### 2.2 新增 state

在组件顶部补充：

```tsx
// 采集记录相关
const [submissions, setSubmissions] = useState<IntakeSubmission[]>([]);
const [subLoading, setSubLoading] = useState(false);
const [selectedSub, setSelectedSub] = useState<IntakeSubmission | null>(null);
const [detailTab, setDetailTab] = useState<'messages' | 'report'>('messages');
const [activeMainTab, setActiveMainTab] = useState('tasks');

// 复用 OperatorIntakePage 的常量
const SUB_STATUS_LABEL: Record<string, string> = {
  pending: '待生成', generating: '生成中', ready: '已就绪', failed: '生成失败',
};
const SUB_STATUS_CLS: Record<string, string> = {
  pending: 'badge-gray', generating: 'badge-warning', ready: 'badge-success', failed: 'badge-danger',
};
```

### 2.3 新增加载函数

```tsx
const loadSubmissions = useCallback(async () => {
  setSubLoading(true);
  try { setSubmissions(await getOperatorSubmissions()); }
  catch { message.error('加载采集记录失败'); }
  finally { setSubLoading(false); }
}, []);

async function openSubDetail(id: number) {
  try {
    const detail = await getOperatorSubmissionDetail(id);
    setSelectedSub(detail);
    setDetailTab('messages');
  } catch (err: unknown) {
    message.error((err as Error).message || '加载详情失败');
  }
}
```

切换到「采集记录」Tab 时加载：
```tsx
function handleTabChange(key: string) {
  setActiveMainTab(key);
  if (key === 'intake' && submissions.length === 0) loadSubmissions();
}
```

### 2.4 return 改为 Tabs 布局

原来 return 里的全部内容（`page-header` + `card` + `Modal`）用 Tabs 包裹：

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">任务中心</h1>
        <p className="page-desc">查看 AI 工具处理任务的状态和采集记录</p>
      </div>
    </div>

    <Tabs
      activeKey={activeMainTab}
      onChange={handleTabChange}
      items={[
        {
          key: 'tasks',
          label: 'AI 任务',
          children: (
            <>
              {/* 原有 card + 分页，原样保留，去掉 page-header（已移到外层） */}
              <div className="card">
                <div className="filter-bar">
                  <select className="filter-select" value={status}
                    onChange={e => { setStatus(e.target.value); setPage(1); }}>
                    <option value="">全部状态</option>
                    <option value="pending">待处理</option>
                    <option value="processing">处理中</option>
                    <option value="success">成功</option>
                    <option value="failed">失败</option>
                  </select>
                  <span className="filter-count">共 {total} 条</span>
                </div>
                {/* 原有表格和分页，原样保留 */}
              </div>
            </>
          ),
        },
        {
          key: 'intake',
          label: '采集记录',
          children: (
            <div className="card">
              <div className="card-body" style={{ padding: 0 }}>
                {subLoading
                  ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
                  : submissions.length === 0
                  ? <div className="empty-state"><div className="empty-state-text">暂无采集记录</div></div>
                  : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>红人姓名</th>
                          <th>报告状态</th>
                          <th>提交时间</th>
                          <th>报告生成时间</th>
                          <th>红人下载</th>
                          <th style={{ textAlign: 'right' }}>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {submissions.map(sub => (
                          <tr key={sub.id}>
                            <td>{sub.kol_name || <span style={{ color: 'var(--gray-400)' }}>未知</span>}</td>
                            <td>
                              <span className={`badge ${SUB_STATUS_CLS[sub.report_status] ?? 'badge-gray'}`}>
                                {SUB_STATUS_LABEL[sub.report_status] ?? sub.report_status}
                              </span>
                            </td>
                            <td style={{ fontSize: 12 }}>{fmtTime(sub.created_at)}</td>
                            <td style={{ fontSize: 12 }}>{fmtTime(sub.report_generated_at)}</td>
                            <td style={{ fontSize: 12 }}>
                              {sub.kol_downloaded_at
                                ? <span style={{ color: 'var(--success)' }}>✓ {fmtTime(sub.kol_downloaded_at)}</span>
                                : <span style={{ color: 'var(--gray-400)' }}>未下载</span>}
                            </td>
                            <td>
                              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                <button className="btn btn-ghost btn-sm"
                                  onClick={() => openSubDetail(sub.id)}>查看</button>
                                {sub.report_status === 'ready' && (
                                  <>
                                    <button className="btn btn-ghost btn-sm"
                                      onClick={() => window.open(getOperatorDownloadUrl(sub.id, 'docx'), '_blank')}>
                                      Word
                                    </button>
                                    <button className="btn btn-ghost btn-sm"
                                      onClick={() => window.open(getOperatorDownloadUrl(sub.id, 'pdf'), '_blank')}>
                                      PDF
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )
                }
              </div>
            </div>
          ),
        },
      ]}
    />

    {/* 原有 AI 任务详情 Modal，原样保留 */}
    <Modal title="任务详情" open={open} onCancel={() => setOpen(false)} footer={null} width={600}>
      {/* ... */}
    </Modal>

    {/* 新增：采集记录详情 Modal（从 OperatorIntakePage 迁移） */}
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
  </>
);
```

> **注意**：`fmtTime` 函数已在 TasksPage 中存在（格式不同），需统一或新增一个适配 intake 的格式：
> ```tsx
> function fmtIntakeTime(iso: string | null) {
>   if (!iso) return '—';
>   return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
> }
> ```

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `OperatorIntakePage.tsx` | 删除提交记录 Tab、相关 state、函数、Modal，页面变为纯链接管理 |
| 2 | `TasksPage.tsx` | 加 Tabs，原内容进「AI 任务」Tab，新增「采集记录」Tab |

**改动量**：OperatorIntakePage 净减约 80 行，TasksPage 净增约 100 行，TypeScript 零新 `any`。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| `/workspace/kol-intake` | 只显示「链接管理」，无 Tab 切换，无提交记录 |
| 点击「+ 创建链接」| 弹窗正常 |
| `/tasks` | 有「AI 任务」和「采集记录」两个 Tab |
| 切换到「采集记录」Tab | 触发加载，显示提交记录列表 |
| 点击「查看」| 弹出对话/报告双 Tab 详情 |
| 报告 ready 时 | 显示下载 Word / PDF 按钮 |
