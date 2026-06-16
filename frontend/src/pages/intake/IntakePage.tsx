import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { message } from 'antd';
import {
  getIntakeQuestions,
  getIntakeInfo, submitIntake, getIntakeStatus, getIntakeDownloadUrl,
} from '../../api/intake';
import type { ChatMessage, IntakeQuestion } from '../../types/intake';

type Phase = 'loading' | 'error' | 'expired' | 'chat' | 'submitted' | 'ready';

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

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

export default function IntakePage() {
  const { token } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<Phase>('loading');
  const [errMsg, setErrMsg] = useState('');
  const [kolName, setKolName] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reportStatus, setReportStatus] = useState<string>('pending');
  const [pollCount, setPollCount] = useState(0);

  // 前端驱动题目流程
  const [questions, setQuestions] = useState<IntakeQuestion[]>([]);
  const [currentQIdx, setCurrentQIdx] = useState(-1);   // -1 = 未开始
  const [collectCount, setCollectCount] = useState(0);
  const [done, setDone] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!token) { setPhase('error'); setErrMsg('无效链接'); return; }

    Promise.all([
      getIntakeQuestions(),
      getIntakeInfo(token),
    ]).then(([qs, info]) => {
      const activeQs = qs.filter(q => q.is_active !== false);
      setQuestions(activeQs);
      setKolName(info.kol_name);

      if (info.already_submitted) {
        if (info.existing_messages?.length) setMessages(info.existing_messages);
        setPhase('submitted');
        pollStatus();
      } else {
        const existing = info.existing_messages ?? [];
        setMessages(existing);
        setPhase('chat');
        if (existing.length === 0) showWelcome();
        // 如果有历史消息，currentQIdx 保持 -1（无法精确恢复进度，允许用户继续）
      }
    }).catch(err => {
      const code = (err as { code?: string }).code;
      if (code === 'LINK_EXPIRED') { setPhase('expired'); return; }
      setPhase('error');
      setErrMsg((err as Error).message || '链接无效');
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // ── 开场白（固定文案，不调 AI）─────────────────────────────────
  function showWelcome() {
    const welcomeMsg: ChatMessage = {
      role: 'assistant',
      content: '你好呀！我是团队里专门负责了解新伙伴的，接下来我们就轻松聊聊，我想听听你的故事和想法，这样团队才能更懂你，帮你找到最适合你的内容方向。\n\n不用紧张，就当跟朋友聊天就好，大概十来分钟。有些问题如果不想答可以跳过。准备好了就点下面的按钮～',
      ts: new Date().toISOString(),
    };
    setMessages([welcomeMsg]);
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
    const qMsg: ChatMessage = {
      role: 'assistant',
      content: `${q.question_text}${reqNote ? ' ' + reqNote : ''}`,
      ts: new Date().toISOString(),
    };
    setMessages(prev => [...prev, qMsg]);
  }

  // ── 用户发送 ─────────────────────────────────────────────────────
  function handleSend() {
    if (!input.trim() || !token || sending || currentQIdx < 0) return;
    const val = input.trim();
    const q = questions[currentQIdx];
    const isSkip = val === '跳过' || val === '跳';

    // 必填题不允许跳过
    if (q.is_required && isSkip) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: '这道题挺重要的，尽量填一下吧～', ts: new Date().toISOString(),
      }]);
      return;
    }

    setMessages(prev => [...prev, { role: 'user', content: val, ts: new Date().toISOString() }]);
    setInput('');

    if (q.question_type === 'multi_collect' && !isSkip) {
      handleMultiCollect(val, q);
    } else {
      handleNormalAnswer(val, q, isSkip);
    }
  }

  // ── 普通题目 ─────────────────────────────────────────────────────
  function handleNormalAnswer(_val: string, _q: IntakeQuestion, _isSkip: boolean) {
    const nextIdx = currentQIdx + 1;
    const isLast = nextIdx >= questions.length;

    if (isLast) {
      setDone(true);
      return;
    }

    showQuestion(nextIdx);
  }

  // ── multi_collect 题目 ──────────────────────────────────────────
  function handleMultiCollect(val: string, q: IntakeQuestion) {
    const isDone = isDoneKeyword(val);

    // 第一条就说没了，必填题不允许
    if (isDone && collectCount === 0 && q.is_required) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: '这道题挺重要的，至少说一个吧～', ts: new Date().toISOString(),
      }]);
      return;
    }

    if (isDone || collectCount + 1 >= (q.max_items ?? 3)) {
      // 收集结束，进入下一题
      setCollectCount(0);
      handleNormalAnswer(val, q, false);
      return;
    }

    const newCount = collectCount + 1;
    setCollectCount(newCount);

    setMessages(prev => [...prev, {
      role: 'assistant', content: '还有没有其他的？没有的话输入"没了"就行。', ts: new Date().toISOString(),
    }]);
  }

  // ── 提交 ──────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!token || !done) return;
    setSubmitting(true);
    try {
      await submitIntake(token, messages);
      setPhase('submitted');
      pollStatus();
    } catch (err: unknown) {
      message.error((err as Error).message || '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  const MAX_POLL = 75;

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

  function handleDownload(format: 'docx' | 'pdf') {
    if (!token) return;
    window.open(getIntakeDownloadUrl(token, format), '_blank');
  }

  // ── 状态页 ──────────────────────────────────────────────────────
  if (phase === 'loading') return <Shell><Loading /></Shell>;
  if (phase === 'expired') return <Shell><StatusCard icon="⏰" title="链接已过期" desc="该入驻链接已过期，请联系运营人员重新生成。" /></Shell>;
  if (phase === 'error') return <Shell><StatusCard icon="🔗" title="链接无效" desc={errMsg || '该链接不存在或已被停用。'} /></Shell>;

  if (phase === 'ready') return (
    <Shell>
      <StatusCard icon="✅" title="入驻报告已生成" desc="感谢您的配合！您的专属报告已生成，请下载留存。">
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
            ? '报告生成出错，请联系运营人员。'
            : `AI 正在分析您的信息，请稍候（已等待 ${pollCount * 4} 秒）`
        }
      />
    </Shell>
  );

  // ── chat phase ──────────────────────────────────────────────────
  return (
    <Shell>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

        {/* Header */}
        <div style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--border)',
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
              {sending ? '正在输入…' : kolName ? `欢迎 ${kolName}` : '请如实回答，越详细越好'}
            </div>
          </div>

          {/* 进度条：按题目数计算 */}
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
                  {fmtTime(msg.ts)}
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
                    width: 6, height: 6, borderRadius: '50%',
                    background: '#7c3aed', display: 'inline-block',
                    animation: 'bounce 1.2s ease-in-out infinite',
                    animationDelay: `${delay}ms`,
                  }} />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input 区：根据状态显示不同内容 */}
        <div style={{
          padding: '12px 16px 16px',
          borderTop: '1px solid var(--border)',
          background: 'var(--bg-card)', flexShrink: 0,
        }}>
          {currentQIdx === -1 && !done ? (
            /* 开始按钮 */
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px', fontSize: 15 }}
              onClick={handleStart}
              disabled={questions.length === 0}
            >
              开始聊吧 →
            </button>
          ) : done ? (
            /* 提交按钮 */
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px', fontSize: 15 }}
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? '提交中…' : '提交并生成报告 →'}
            </button>
          ) : (
            /* 正常输入框 */
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder="输入你的回答（Enter 发送，Shift+Enter 换行）"
                disabled={sending}
                rows={2}
                style={{
                  flex: 1, resize: 'none',
                  border: '1px solid var(--border)',
                  borderRadius: 12, padding: '10px 14px',
                  fontFamily: 'var(--font-sans)', fontSize: 14,
                  outline: 'none',
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
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100dvh', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column', alignItems: 'center', overflow: 'hidden' }}>
      <style>{bounceStyle}</style>
      <div style={{
        width: '100%', maxWidth: 700, height: '100%',
        display: 'flex', flexDirection: 'column',
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-lg)',
      }}>
        {children}
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 28, color: 'var(--brand)' }}>⏳</div>
      <div style={{ fontSize: 14, color: 'var(--gray-500)' }}>正在加载…</div>
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
