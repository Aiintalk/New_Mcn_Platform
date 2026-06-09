# 前端任务单 · kol-intake 运营直发对话页面

> 目标：
> 1. 运营点击创作中心「红人信息采集助手」→ 直接进入对话页面（用 JWT 登录态，无需 token）
> 2. 对话页面右上角有「+ 创建分享链接」按钮，给远程场景使用
> 3. 历史分享链接从 OperatorIntakePage 移到产出中心
>
> 涉及文件：
> - 新建 `src/pages/operator/OperatorIntakeChatPage.tsx`
> - 新建 `src/api/intakeDirect.ts`
> - 修改 `src/pages/operator/OperatorIntakePage.tsx`（整体替换为跳转逻辑）
> - 修改 `src/pages/operator/OutputsPage.tsx`（加「分享链接」Tab）
> - 修改 `src/App.tsx`（新增路由）

---

## 改动 1 — 新增 API 函数

**文件**：`src/api/intakeDirect.ts`（新建）

```ts
import { get, post } from './request';
import type { ChatMessage } from '../types/intake';

export const startDirectSession = (data: { kol_name?: string }) =>
  post<{ session_id: number; kol_name: string | null }>(
    '/api/operator/intake/direct/start', data
  );

export const chatDirect = (sessionId: number, messages: ChatMessage[]) =>
  post<{ reply: string }>(
    `/api/operator/intake/direct/${sessionId}/chat`, { messages }
  );

export const submitDirect = (sessionId: number) =>
  post<{ report_status: string }>(
    `/api/operator/intake/direct/${sessionId}/submit`, {}
  );

export const getDirectStatus = (sessionId: number) =>
  get<{ report_status: 'pending' | 'generating' | 'ready' | 'failed' }>(
    `/api/operator/intake/direct/${sessionId}/status`
  );

export const getDirectDownloadUrl = (sessionId: number, format: 'docx' | 'pdf') => {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  return `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}`;
};
```

---

## 改动 2 — 新建运营对话页面

**文件**：`src/pages/operator/OperatorIntakeChatPage.tsx`（新建）

UI 与 `IntakePage.tsx` 完全一致（旧架构风格：紫色渐变头像、不对称气泡、三点动画），差异点：
- 用 `startDirectSession` 初始化会话（页面挂载时自动调用）
- 用 `chatDirect` / `submitDirect` / `getDirectStatus` 替换对应接口
- header 右侧额外显示「+ 创建分享链接」按钮

```tsx
import { useEffect, useRef, useState } from 'react';
import { Modal, Form, Input, InputNumber, message } from 'antd';
import {
  startDirectSession, chatDirect, submitDirect,
  getDirectStatus, getDirectDownloadUrl,
} from '../../api/intakeDirect';
import { createIntakeLink } from '../../api/intake';
import type { ChatMessage } from '../../types/intake';

const FRONTEND_BASE = import.meta.env.VITE_APP_BASE_URL ?? window.location.origin;
const MAX_POLL = 75;

type Phase = 'loading' | 'error' | 'chat' | 'submitted' | 'ready';

export default function OperatorIntakeChatPage() {
  const [phase, setPhase] = useState<Phase>('loading');
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [kolName, setKolName] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reportStatus, setReportStatus] = useState<string>('pending');
  const [pollCount, setPollCount] = useState(0);

  // 创建分享链接弹窗
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [shareForm] = Form.useForm();
  const [shareLoading, setShareLoading] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 页面挂载：自动开始会话
  useEffect(() => {
    startDirectSession({})
      .then(res => {
        setSessionId(res.session_id);
        setKolName(res.kol_name);
        setPhase('chat');
        sendFirstMessage(res.session_id, []);
      })
      .catch(() => setPhase('error'));

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  async function sendFirstMessage(sid: number, msgs: ChatMessage[]) {
    setSending(true);
    try {
      const res = await chatDirect(sid, msgs);
      if (res.reply) {
        setMessages([{ role: 'assistant', content: res.reply, ts: new Date().toISOString() }]);
      }
    } catch {
      // ignore first-message error silently
    } finally {
      setSending(false);
    }
  }

  async function handleSend() {
    if (!input.trim() || !sessionId || sending) return;
    const userMsg: ChatMessage = { role: 'user', content: input.trim(), ts: new Date().toISOString() };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setSending(true);
    try {
      const res = await chatDirect(sessionId, nextMessages);
      if (res.reply) {
        setMessages(prev => [...prev, { role: 'assistant', content: res.reply, ts: new Date().toISOString() }]);
      }
    } catch (err: unknown) {
      message.error((err as Error).message || '发送失败，请重试');
    } finally {
      setSending(false);
    }
  }

  async function handleSubmit() {
    if (!sessionId || messages.length === 0) return;
    if (messages.filter(m => m.role === 'user').length < 3) {
      message.warning('请先完成与 AI 的对话，至少回答 3 个问题');
      return;
    }
    setSubmitting(true);
    try {
      await submitDirect(sessionId);
      setPhase('submitted');
      pollStatus(sessionId);
    } catch (err: unknown) {
      message.error((err as Error).message || '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  function pollStatus(sid: number) {
    let count = 0;
    pollRef.current = setInterval(async () => {
      count += 1;
      try {
        const res = await getDirectStatus(sid);
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

  async function handleCreateShareLink(values: { kol_name?: string; expire_hours: number }) {
    setShareLoading(true);
    try {
      const res = await createIntakeLink({
        kol_name: values.kol_name || undefined,
        expire_hours: values.expire_hours,
      });
      const url = `${FRONTEND_BASE}/intake/${res.token}`;
      setShareLink(url);
      shareForm.resetFields();
    } catch (err: unknown) {
      message.error((err as Error).message || '创建失败');
    } finally {
      setShareLoading(false);
    }
  }

  function handleDownload(format: 'docx' | 'pdf') {
    if (!sessionId) return;
    window.open(getDirectDownloadUrl(sessionId, format), '_blank');
  }

  // ── 状态页 ──────────────────────────────────────────────────
  if (phase === 'loading') return <Shell><Loading /></Shell>;
  if (phase === 'error') return <Shell><StatusCard icon="❌" title="加载失败" desc="请刷新页面重试" /></Shell>;

  if (phase === 'ready') return (
    <Shell>
      <StatusCard icon="✅" title="入驻报告已生成" desc="报告已生成，可下载留存。">
        <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={() => handleDownload('docx')}>下载 Word 版</button>
          <button className="btn btn-ghost" onClick={() => handleDownload('pdf')}>下载 PDF 版</button>
        </div>
      </StatusCard>
    </Shell>
  );

  if (phase === 'submitted') return (
    <Shell>
      <StatusCard
        icon={reportStatus === 'failed' ? '❌' : '⏳'}
        title={reportStatus === 'failed' ? '报告生成失败' : '正在生成入驻报告…'}
        desc={
          reportStatus === 'failed'
            ? '报告生成出错，请联系管理员。'
            : `AI 正在分析，请稍候（已等待 ${pollCount * 4} 秒）`
        }
      />
    </Shell>
  );

  // ── 对话页 ──────────────────────────────────────────────────
  return (
    <Shell>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

        {/* Header */}
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 12,
          background: 'var(--bg-card)', flexShrink: 0,
          position: 'sticky', top: 0, zIndex: 10,
        }}>
          <div style={{
            width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
            background: 'linear-gradient(135deg, #7c3aed, #db2777)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 700, fontSize: 14,
          }}>AI</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)' }}>
              红人信息采集助手
            </div>
            <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
              {sending ? '正在输入…' : kolName ? `当前红人：${kolName}` : '请如实回答，越详细越好'}
            </div>
          </div>
          {/* 进度条 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <div style={{ width: 72, height: 4, background: 'var(--gray-100)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                background: 'linear-gradient(90deg, #7c3aed, #db2777)',
                borderRadius: 2,
                width: `${Math.min(100, messages.filter(m => m.role === 'user').length * 8)}%`,
                transition: 'width 0.5s ease',
              }} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>
              {messages.filter(m => m.role === 'user').length} 条
            </span>
          </div>
          {/* 创建分享链接按钮 */}
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setShareLink(null); setShowShareModal(true); }}
            style={{ flexShrink: 0 }}
          >
            + 创建分享链接
          </button>
        </div>

        {/* Messages */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '20px 16px',
          display: 'flex', flexDirection: 'column', gap: 14,
          background: 'var(--bg-page)',
        }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              gap: 10, alignItems: 'flex-start',
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                background: msg.role === 'user'
                  ? 'var(--gray-200)'
                  : 'linear-gradient(135deg, #7c3aed, #db2777)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
                color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
              }}>
                {msg.role === 'user' ? '我' : 'AI'}
              </div>
              <div style={{ maxWidth: '75%' }}>
                <div style={{
                  background: msg.role === 'user' ? '#7c3aed' : 'var(--bg-card)',
                  color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                  padding: '10px 14px',
                  borderRadius: msg.role === 'user' ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
                  fontSize: 14, lineHeight: 1.65,
                  boxShadow: msg.role === 'user' ? 'none' : 'var(--shadow-sm)',
                  border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
                <div style={{
                  fontSize: 11, color: 'var(--gray-400)', marginTop: 4,
                  textAlign: msg.role === 'user' ? 'right' : 'left',
                }}>
                  {new Date(msg.ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            </div>
          ))}
          {sending && (
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: 'linear-gradient(135deg, #7c3aed, #db2777)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontWeight: 700, fontSize: 12, flexShrink: 0,
              }}>AI</div>
              <div style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: '4px 14px 14px 14px', padding: '10px 16px',
                boxShadow: 'var(--shadow-sm)',
                display: 'flex', gap: 4, alignItems: 'center',
              }}>
                {[0, 150, 300].map(delay => (
                  <span key={delay} style={{
                    width: 6, height: 6, borderRadius: '50%', background: '#7c3aed',
                    display: 'inline-block',
                    animation: 'bounce 1.2s ease-in-out infinite',
                    animationDelay: `${delay}ms`,
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: '12px 16px 16px', borderTop: '1px solid var(--border)',
          background: 'var(--bg-card)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="输入回答（Enter 发送，Shift+Enter 换行）"
              disabled={sending}
              rows={2}
              style={{
                flex: 1, resize: 'none', border: '1px solid var(--border)',
                borderRadius: 12, padding: '10px 14px',
                fontFamily: 'var(--font-sans)', fontSize: 14, outline: 'none',
                background: 'var(--bg-page)', color: 'var(--gray-800)',
                transition: 'border-color 0.2s',
              }}
              onFocus={e => (e.target.style.borderColor = '#7c3aed')}
              onBlur={e => (e.target.style.borderColor = 'var(--border)')}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              style={{
                width: 44, height: 44, flexShrink: 0,
                background: '#7c3aed', border: 'none', borderRadius: 12,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', opacity: (sending || !input.trim()) ? 0.35 : 1,
                transition: 'opacity 0.2s',
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            </button>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>
              已回答 {messages.filter(m => m.role === 'user').length} 条（至少 3 条才能提交）
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleSubmit}
              disabled={submitting || sending || messages.filter(m => m.role === 'user').length < 3}
              style={{ color: '#7c3aed', borderColor: '#7c3aed' }}
            >
              {submitting ? '提交中…' : '完成并生成报告 →'}
            </button>
          </div>
        </div>
      </div>

      {/* 创建分享链接 Modal */}
      <Modal
        title="创建分享链接"
        open={showShareModal}
        onCancel={() => { setShowShareModal(false); setShareLink(null); shareForm.resetFields(); }}
        footer={null}
        destroyOnClose
      >
        {shareLink ? (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 8 }}>链接已创建，复制后发给红人：</div>
            <div style={{
              background: 'var(--bg-page)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px',
              fontFamily: 'var(--font-mono)', fontSize: 13,
              wordBreak: 'break-all', marginBottom: 16,
            }}>
              {shareLink}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost btn-sm"
                onClick={() => { setShareLink(null); shareForm.resetFields(); }}>
                再创建一个
              </button>
              <button className="btn btn-primary btn-sm"
                onClick={() => {
                  navigator.clipboard.writeText(shareLink).then(() => message.success('链接已复制'));
                }}>
                复制链接
              </button>
            </div>
          </div>
        ) : (
          <Form form={shareForm} layout="vertical" onFinish={handleCreateShareLink} style={{ marginTop: 16 }}>
            <Form.Item label="红人姓名（可选）" name="kol_name">
              <Input placeholder="预填写，方便识别" />
            </Form.Item>
            <Form.Item label="有效期（小时）" name="expire_hours" initialValue={168} rules={[{ required: true }]}>
              <InputNumber min={1} max={720} style={{ width: '100%' }} addonAfter="小时" />
            </Form.Item>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm"
                onClick={() => setShowShareModal(false)}>取消</button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={shareLoading}>
                {shareLoading ? '创建中…' : '创建链接'}
              </button>
            </div>
          </Form>
        )}
      </Modal>
    </Shell>
  );
}

// ── Shell / Loading / StatusCard（与 IntakePage 相同） ─────────────────────────

const bounceStyle = `
  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-6px); }
  }
`;

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <style>{bounceStyle}</style>
      <div style={{ width: '100%', maxWidth: 700, flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', minHeight: '100vh', boxShadow: 'var(--shadow-lg)' }}>
        {children}
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 28, color: '#7c3aed' }}>⏳</div>
      <div style={{ fontSize: 14, color: 'var(--gray-500)' }}>正在初始化…</div>
    </div>
  );
}

function StatusCard({ icon, title, desc, children }: { icon: string; title: string; desc: string; children?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16, padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 48 }}>{icon}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--gray-800)' }}>{title}</div>
      <div style={{ fontSize: 14, color: 'var(--gray-500)', maxWidth: 320 }}>{desc}</div>
      {children}
    </div>
  );
}
```

---

## 改动 3 — OperatorIntakePage 整体替换

**文件**：`src/pages/operator/OperatorIntakePage.tsx`

整个组件替换为进入即跳转：

```tsx
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function OperatorIntakePage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate('/workspace/kol-intake/chat', { replace: true });
  }, [navigate]);
  return null;
}
```

---

## 改动 4 — App.tsx 新增路由

**文件**：`src/App.tsx`

```tsx
// import 新增
import OperatorIntakeChatPage from './pages/operator/OperatorIntakeChatPage';

// 路由新增（在 /workspace/kol-intake 之后）
<Route path="/workspace/kol-intake/chat" element={<OperatorIntakeChatPage />} />
```

---

## 改动 5 — OutputsPage：加「分享链接」Tab

**文件**：`src/pages/operator/OutputsPage.tsx`

### 5.1 import 补充

```tsx
import { Tabs } from 'antd';
import { getIntakeLinks } from '../../api/intake';
import type { IntakeLink } from '../../types/intake';
```

### 5.2 新增 state

```tsx
const [links, setLinks] = useState<IntakeLink[]>([]);
const [linksLoading, setLinksLoading] = useState(false);
const [activeTab, setActiveTab] = useState('outputs');

const FRONTEND_BASE = import.meta.env.VITE_APP_BASE_URL ?? window.location.origin;

function fmtLinkTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function isExpired(iso: string) {
  return new Date(iso) < new Date();
}

const loadLinks = useCallback(async () => {
  setLinksLoading(true);
  try { setLinks(await getIntakeLinks()); }
  catch { message.error('加载链接失败'); }
  finally { setLinksLoading(false); }
}, []);

function handleTabChange(key: string) {
  setActiveTab(key);
  if (key === 'links' && links.length === 0) loadLinks();
}
```

### 5.3 return 改为 Tabs 布局

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">产出中心</h1>
        <p className="page-desc">查看 AI 工具生成的内容和采集分享链接</p>
      </div>
    </div>

    <Tabs activeKey={activeTab} onChange={handleTabChange} items={[
      {
        key: 'outputs',
        label: 'AI 产出',
        children: (
          <>
            {/* 原有 card + 分页，原样保留，去掉 page-header */}
          </>
        ),
      },
      {
        key: 'links',
        label: '分享链接',
        children: (
          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {linksLoading
                ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
                : links.length === 0
                ? <div className="empty-state"><div className="empty-state-text">暂无分享链接</div></div>
                : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>红人姓名</th>
                        <th>状态</th>
                        <th>到期时间</th>
                        <th>访问时间</th>
                        <th>提交时间</th>
                        <th style={{ textAlign: 'right' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {links.map(lnk => {
                        const expired = isExpired(lnk.expires_at);
                        return (
                          <tr key={lnk.id}>
                            <td>{lnk.kol_name || <span style={{ color: 'var(--gray-400)' }}>未填写</span>}</td>
                            <td>
                              <span className={`badge ${expired ? 'badge-gray' : lnk.is_active ? 'badge-success' : 'badge-danger'}`}>
                                {expired ? '已过期' : lnk.is_active ? '有效' : '停用'}
                              </span>
                            </td>
                            <td style={{ fontSize: 12, color: expired ? 'var(--danger)' : 'var(--gray-700)' }}>
                              {fmtLinkTime(lnk.expires_at)}
                            </td>
                            <td style={{ fontSize: 12 }}>{fmtLinkTime(lnk.used_at)}</td>
                            <td style={{ fontSize: 12 }}>{fmtLinkTime(lnk.submitted_at)}</td>
                            <td>
                              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                <button className="btn btn-ghost btn-sm"
                                  onClick={() => navigator.clipboard.writeText(`${FRONTEND_BASE}/intake/${lnk.token}`).then(() => message.success('链接已复制'))}>
                                  复制链接
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )
              }
            </div>
          </div>
        ),
      },
    ]} />
  </>
);
```

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `api/intakeDirect.ts` | 新建，5 个 API 函数 |
| 2 | `pages/operator/OperatorIntakeChatPage.tsx` | 新建，运营对话页面 |
| 3 | `pages/operator/OperatorIntakePage.tsx` | 替换为跳转逻辑 |
| 4 | `App.tsx` | 新增 `/workspace/kol-intake/chat` 路由 |
| 5 | `pages/operator/OutputsPage.tsx` | 加「分享链接」Tab |

**改动量**：约 250 行净增，TypeScript 零新 `any`，零新依赖。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| 点击创作中心「红人信息采集助手」| 直接跳转对话页面，AI 发出第一条消息 |
| 对话页 header 右上角 | 有「+ 创建分享链接」按钮 |
| 点击「+ 创建分享链接」| 弹窗，填写姓名和有效期，创建后显示链接可复制 |
| 完成对话提交 | 跳转生成中页面，轮询后变为可下载 |
| 产出中心 `/outputs` | 有「AI 产出」和「分享链接」两个 Tab |
| 切换到「分享链接」Tab | 显示历史分享链接列表，可复制 |
