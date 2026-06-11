# 前端任务单 · kol-intake 报告展示与下载修复

> 问题：
> 1. 点击「下载 Word/PDF」报错 AUTH_TOKEN_MISSING（window.open 无法携带 Authorization header）
> 2. 报告生成后只有下载按钮，没有在页面直接展示报告内容
>
> 涉及文件：
> - `src/api/intakeDirect.ts`
> - `src/pages/operator/OperatorIntakeChatPage.tsx`
> - `src/store/authStore.ts`（只读，获取 token）

---

## 前置条件

后端已完成：
- `GET /status` 返回新增 `ai_report` 字段
- `GET /download` 支持 `?token=xxx` query 参数鉴权

---

## 改动 1 — getDirectDownloadUrl 携带 token

**文件**：`src/api/intakeDirect.ts`

```ts
// 修改前
export const getDirectDownloadUrl = (sessionId: number, format: 'docx' | 'pdf') => {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  return `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}`;
};

// 修改后（从 authStore 读取 token 拼入 URL）
import { useAuthStore } from '../store/authStore';

export const getDirectDownloadUrl = (sessionId: number, format: 'docx' | 'pdf') => {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  const token = useAuthStore.getState().token;  // Zustand 支持在非组件中读取 getState()
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
  return `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}${tokenParam}`;
};
```

---

## 改动 2 — status 接口类型新增 ai_report

**文件**：`src/api/intakeDirect.ts`

```ts
// 修改前
export const getDirectStatus = (sessionId: number) =>
  get<{ report_status: 'pending' | 'generating' | 'ready' | 'failed' }>(
    `/api/operator/intake/direct/${sessionId}/status`
  );

// 修改后
export const getDirectStatus = (sessionId: number) =>
  get<{
    report_status: 'pending' | 'generating' | 'ready' | 'failed';
    ai_report: string | null;
  }>(`/api/operator/intake/direct/${sessionId}/status`);
```

---

## 改动 3 — OperatorIntakeChatPage 新增报告展示

**文件**：`src/pages/operator/OperatorIntakeChatPage.tsx`

### 3.1 新增 state

```tsx
const [aiReport, setAiReport] = useState<string | null>(null);
```

### 3.2 pollStatus 中保存 ai_report

```tsx
function pollStatus(sid: number) {
  let count = 0;
  pollRef.current = setInterval(async () => {
    count += 1;
    try {
      const res = await getDirectStatus(sid);
      setReportStatus(res.report_status);
      setPollCount(count);
      if (res.ai_report) setAiReport(res.ai_report);   // ← 新增
      if (res.report_status === 'ready' || res.report_status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        if (res.report_status === 'ready') setPhase('ready');
        return;
      }
    } catch { /* ignore */ }
    if (count >= MAX_POLL) {
      if (pollRef.current) clearInterval(pollRef.current);
      setReportStatus('failed');
    }
  }, 4000);
}
```

### 3.3 ready 状态页展示报告内容

将当前的 `phase === 'ready'` 返回内容改为：

```tsx
if (phase === 'ready') return (
  <Shell>
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
        background: 'var(--bg-card)', flexShrink: 0,
      }}>
        <div style={{
          width: 38, height: 38, borderRadius: '50%',
          background: 'linear-gradient(135deg, #7c3aed, #db2777)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 14,
        }}>AI</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)' }}>入驻报告已生成</div>
          <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
            {kolName ? `红人：${kolName}` : '报告生成完毕'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => handleDownload('pdf')}>
            下载 PDF
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => handleDownload('docx')}>
            下载 Word
          </button>
        </div>
      </div>

      {/* 报告内容 */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '24px 20px',
        background: 'var(--bg-page)',
      }}>
        {aiReport ? (
          <div style={{
            background: 'var(--bg-card)', borderRadius: 12,
            border: '1px solid var(--border)', padding: '24px',
            fontSize: 14, lineHeight: 1.8, color: 'var(--gray-800)',
            whiteSpace: 'pre-wrap',
          }}>
            {aiReport}
          </div>
        ) : (
          <div style={{ textAlign: 'center', color: 'var(--gray-400)', paddingTop: 40 }}>
            报告内容加载中…
          </div>
        )}
      </div>
    </div>
  </Shell>
);
```

---

## 验证

| 验证点 | 预期 |
|--------|------|
| 点击「下载 Word 版」 | 直接下载文件，不报 AUTH_TOKEN_MISSING |
| 点击「下载 PDF 版」 | 直接下载文件，不报错 |
| 报告生成完成后 | 页面直接展示报告全文（纯文本，保留换行） |
| Header 有下载按钮 | 「下载 PDF」+ 「下载 Word」两个按钮在右上角 |
