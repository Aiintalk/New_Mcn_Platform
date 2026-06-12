import { useEffect, useRef, useState } from 'react';
import { Modal, Form, Input, InputNumber, message } from 'antd';
import {
  startDirectSession, submitDirect,
  getDirectStatus,
} from '../../api/intakeDirect';
import { createIntakeLink, getIntakeQuestions } from '../../api/intake';
import { useAuthStore } from '../../store/authStore';
import type { ChatMessage, IntakeQuestion } from '../../types/intake';

const FRONTEND_BASE = import.meta.env.VITE_APP_BASE_URL ?? window.location.origin;
const MAX_POLL = 75;

type Phase = 'loading' | 'error' | 'chat' | 'submitted' | 'ready';

const DONE_KEYWORDS = ['没了', '没有了', '就这些', '没有', '没', '无', '就这样', 'no', '算了'];
function isDoneKeyword(val: string) {
  return DONE_KEYWORDS.includes(val.trim().toLowerCase());
}

const bounceStyle = `
  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-6px); }
  }
`;

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
  const [aiReport, setAiReport] = useState<string | null>(null);

  // 前端驱动题目流程
  const [questions, setQuestions] = useState<IntakeQuestion[]>([]);
  const [currentQIdx, setCurrentQIdx] = useState(-1);
  const [collectCount, setCollectCount] = useState(0);
  const [done, setDone] = useState(false);

  // 创建分享链接弹窗
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [shareForm] = Form.useForm();
  const [shareLoading, setShareLoading] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 挂载时去掉 .main-body 的 padding 和 overflow，卸载时恢复
  useEffect(() => {
    const mainBody = document.querySelector('.main-body') as HTMLElement | null;
    if (mainBody) {
      mainBody.style.padding = '0';
      mainBody.style.overflow = 'hidden';
    }
    return () => {
      if (mainBody) {
        mainBody.style.padding = '';
        mainBody.style.overflow = '';
      }
    };
  }, []);

  // 页面挂载：并行加载会话 + 题目列表
  useEffect(() => {
    Promise.all([
      startDirectSession({}),
      getIntakeQuestions(),
    ]).then(([sessionRes, qs]) => {
      const activeQs = qs.filter(q => q.is_active !== false);
      setQuestions(activeQs);
      setSessionId(sessionRes.session_id);
      setKolName(sessionRes.kol_name);
      setPhase('chat');
      showWelcome();
    }).catch(() => setPhase('error'));

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // ── 开场白 ──────────────────────────────────────────────────────
  function showWelcome() {
    setMessages([{
      role: 'assistant',
      content: '你好呀！我是团队里专门负责了解新伙伴的，接下来我们就轻松聊聊，我想听听你的故事和想法，这样团队才能更懂你，帮你找到最适合你的内容方向。\n\n不用紧张，就当跟朋友聊天就好，大概十来分钟。有些问题如果不想答可以跳过。准备好了就点下面的按钮～',
      ts: new Date().toISOString(),
    }]);
  }

  // ── 开始 / 显示题目 ─────────────────────────────────────────────
  function handleStart() {
    if (questions.length === 0) return;
    showQuestion(0);
  }

  function showQuestion(idx: number) {
    const q = questions[idx];
    setCurrentQIdx(idx);
    setCollectCount(0);
    const reqNote = q.is_required ? '' : '（选填，可输入"跳过"）';
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: `${q.question_text}${reqNote ? ' ' + reqNote : ''}`,
      ts: new Date().toISOString(),
    }]);
  }

  // ── 用户发送 ─────────────────────────────────────────────────────
  async function handleSend() {
    if (!input.trim() || !sessionId || sending || currentQIdx < 0) return;
    const val = input.trim();
    const q = questions[currentQIdx];
    const isSkip = val === '跳过' || val === '跳';

    if (q.is_required && isSkip) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: '这道题挺重要的，尽量填一下吧～', ts: new Date().toISOString(),
      }]);
      return;
    }

    setMessages(prev => [...prev, { role: 'user', content: val, ts: new Date().toISOString() }]);
    setInput('');
    setSending(true);

    try {
      if (q.question_type === 'multi_collect' && !isSkip) {
        await handleMultiCollect(val, q, sessionId);
      } else {
        await handleNormalAnswer(val, q, isSkip, sessionId);
      }
    } finally {
      setSending(false);
    }
  }

  // ── 普通题目 ─────────────────────────────────────────────────────
  async function handleNormalAnswer(val: string, q: IntakeQuestion, isSkip: boolean, _sid: number) {
    const nextIdx = currentQIdx + 1;
    const isLast = nextIdx >= questions.length;

    if (isLast) {
      setDone(true);
      return;
    }

    showQuestion(nextIdx);
  }

  // ── multi_collect 题目 ──────────────────────────────────────────
  async function handleMultiCollect(val: string, q: IntakeQuestion, _sid: number) {
    const isDone = isDoneKeyword(val);

    if (isDone && collectCount === 0 && q.is_required) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: '这道题挺重要的，至少说一个吧～', ts: new Date().toISOString(),
      }]);
      return;
    }

    if (isDone || collectCount + 1 >= (q.max_items ?? 3)) {
      setCollectCount(0);
      await handleNormalAnswer(val, q, false, _sid);
      return;
    }

    const newCount = collectCount + 1;
    setCollectCount(newCount);
    setMessages(prev => [...prev, {
      role: 'assistant', content: '还有没有其他的？没有的话输入"没了"就行。', ts: new Date().toISOString(),
    }]);
  }

  // ── 提交 ─────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!sessionId || !done) return;
    setSubmitting(true);
    try {
      await submitDirect(sessionId, messages);
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
        if (res.ai_report) setAiReport(res.ai_report);
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

  async function handleDownload(format: 'docx' | 'pdf') {
    if (!sessionId) return;
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
    const token = useAuthStore.getState().token;
    if (!token) { message.error('请重新登录后再试'); return; }
    try {
      const res = await fetch(
        `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ message: '下载失败' }));
        message.error(body.message || '下载失败');
        return;
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `入驻报告.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      message.error('下载失败，请重试');
    }
  }

  // ── 状态页 ──────────────────────────────────────────────────────
  if (phase === 'loading') return <Shell><Loading /></Shell>;
  if (phase === 'error') return <Shell><StatusCard icon="❌" title="加载失败" desc="请刷新页面重试" /></Shell>;

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
            color: '#fff', fontWeight: 700, fontSize: 14, flexShrink: 0,
          }}>AI</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)' }}>入驻报告已生成</div>
            <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
              {kolName ? `红人：${kolName}` : '报告生成完毕'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
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

  // ── 对话页 ──────────────────────────────────────────────────────
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
          <div style={{ flex: 1, minWidth: 0 }}>
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
                width: questions.length > 0 && currentQIdx >= 0
                  ? `${Math.min(100, Math.round((currentQIdx / questions.length) * 100))}%`
                  : '0%',
                transition: 'width 0.5s ease',
              }} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>
              {currentQIdx >= 0 ? `${currentQIdx + 1}/${questions.length}` : '准备中'}
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
          {/* 三点跳动动画 */}
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

        {/* Input 区 */}
        <div style={{
          padding: '12px 16px 16px', borderTop: '1px solid var(--border)',
          background: 'var(--bg-card)', flexShrink: 0,
        }}>
          {currentQIdx === -1 && !done ? (
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px', fontSize: 15 }}
              onClick={handleStart}
              disabled={questions.length === 0}
            >
              开始聊吧 →
            </button>
          ) : done ? (
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px', fontSize: 15 }}
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? '提交中…' : '提交并生成报告 →'}
            </button>
          ) : (
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
          )}
        </div>
      </div>

      {/* 创建分享链接 Modal */}
      <Modal
        title="创建分享链接"
        open={showShareModal}
        onCancel={() => { setShowShareModal(false); setShareLink(null); shareForm.resetFields(); }}
        footer={null}
        destroyOnHidden
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

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100%', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <style>{bounceStyle}</style>
      <div style={{ width: '100%', maxWidth: 700, flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', height: '100%', boxShadow: 'var(--shadow-lg)' }}>
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
