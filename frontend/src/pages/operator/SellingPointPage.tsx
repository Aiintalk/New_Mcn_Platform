// frontend/src/pages/operator/SellingPointPage.tsx
import { useState, useRef } from 'react';
import type { UploadedFile, HistoryItem, HistoryRecord } from '../../types/sellingPoint';
import {
  chatStream,
  parseFile,
  getHistoryList,
  getHistoryRecord,
  saveHistory,
  deleteHistoryRecord,
} from '../../api/sellingPoint';

interface ChatMsg { role: string; content: string }

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.*)/g, '<h3 class="text-xl font-bold mt-8 mb-3 text-gray-800">$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p class="mb-3">')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return (
    <div
      className="prose max-w-none text-[15px] leading-relaxed text-gray-700"
      dangerouslySetInnerHTML={{ __html: `<p class="mb-3">${html}</p>` }}
    />
  );
}

function extractProductName(result: string): string {
  const m = result.match(/资料概览[\s\S]*?\n([\s\S]*?)(?:\n---|\n###)/);
  if (m) {
    const t = m[1].replace(/<[^>]+>/g, '').trim();
    if (t.length > 0) return t.slice(0, 20) + (t.length > 20 ? '...' : '');
  }
  return '未命名产品';
}

function trimMessages(msgs: ChatMsg[]): ChatMsg[] {
  if (msgs.length <= 10) return msgs;
  const first = msgs[0];
  const last8 = msgs.slice(-8);
  if (last8.includes(first)) return last8;
  return [first, ...last8];
}

export default function SellingPointPage() {
  const [step, setStep] = useState(1);
  const [briefFiles, setBriefFiles] = useState<UploadedFile[]>([]);
  const [scriptFiles, setScriptFiles] = useState<UploadedFile[]>([]);
  const [briefExtra, setBriefExtra] = useState('');
  const [scriptExtra, setScriptExtra] = useState('');
  const [uploadingBrief, setUploadingBrief] = useState(false);
  const [uploadingScript, setUploadingScript] = useState(false);
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([]);
  const [followUpResult, setFollowUpResult] = useState('');
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const briefRef = useRef<HTMLInputElement>(null);
  const scriptRef = useRef<HTMLInputElement>(null);
  const [briefDragOver, setBriefDragOver] = useState(false);
  const [scriptDragOver, setScriptDragOver] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const data = await getHistoryList();
      setHistoryList(data.records || []);
    } catch { setHistoryList([]); }
    finally { setHistoryLoading(false); }
  }

  async function loadHistoryRecord(id: string) {
    try {
      const data = await getHistoryRecord(id);
      if (data.record) {
        const rec: HistoryRecord = data.record;
        setResult(rec.result);
        setChatHistory(rec.chatHistory || []);
        setBriefFiles(rec.briefFiles || []);
        setScriptFiles(rec.scriptFiles || []);
        setFollowUpResult(''); setFollowUp('');
        setShowHistory(false); setStep(3);
      }
    } catch { setError('加载历史记录失败'); }
  }

  async function handleDeleteHistory(id: string) {
    try {
      await deleteHistoryRecord(id);
      setHistoryList(prev => prev.filter(h => h.id !== id));
    } catch { setError('删除失败'); }
  }

  async function handleSaveHistory(analysisResult: string, history: ChatMsg[]) {
    try {
      const productName = extractProductName(analysisResult);
      await saveHistory({ productName, result: analysisResult, chatHistory: history, briefFiles, scriptFiles });
    } catch { console.error('Failed to save history'); }
  }

  async function handleFilesUpload(files: FileList, type: 'brief' | 'script') {
    const setter = type === 'brief' ? setBriefFiles : setScriptFiles;
    const setUploading = type === 'brief' ? setUploadingBrief : setUploadingScript;
    setUploading(true); setError('');
    for (const file of Array.from(files)) {
      try {
        const data = await parseFile(file);
        setter(prev => [...prev, { name: data.filename, text: data.text }]);
      } catch { setError(`文件 ${file.name} 上传失败`); }
    }
    setUploading(false);
    if (type === 'brief' && briefRef.current) briefRef.current.value = '';
    if (type === 'script' && scriptRef.current) scriptRef.current.value = '';
  }

  function removeFile(type: 'brief' | 'script', index: number) {
    if (type === 'brief') setBriefFiles(prev => prev.filter((_, i) => i !== index));
    else setScriptFiles(prev => prev.filter((_, i) => i !== index));
  }

  const hasBrief = briefFiles.length > 0 || briefExtra.trim();
  const hasScript = scriptFiles.length > 0 || scriptExtra.trim();

  async function handleAnalyze() {
    setLoading(true); setError(''); setResult(''); setFollowUpResult(''); setChatHistory([]); setStep(3);

    let userMsg = '';
    if (hasBrief) {
      const parts: string[] = [];
      briefFiles.forEach((f, i) => parts.push(`【文档${i + 1}：${f.name}】\n${f.text}`));
      if (briefExtra.trim()) parts.push(`【补充内容】\n${briefExtra.trim()}`);
      userMsg += `## 产品Brief（共${briefFiles.length}份文档${briefExtra.trim() ? ' + 补充内容' : ''}）\n\n${parts.join('\n\n---\n\n')}\n\n`;
    }
    if (hasScript) {
      const parts: string[] = [];
      scriptFiles.forEach((f, i) => parts.push(`【文案${i + 1}：${f.name}】\n${f.text}`));
      if (scriptExtra.trim()) parts.push(`【补充内容】\n${scriptExtra.trim()}`);
      userMsg += `## 达人文案脚本（共${scriptFiles.length}份文案${scriptExtra.trim() ? ' + 补充内容' : ''}）\n\n${parts.join('\n\n---\n\n')}\n\n`;
    }
    userMsg += '请综合以上所有资料，严格按照 机制→背书→可视化→种草 的顺序逐维度分析，提炼卖点并排序。';

    try {
      const res = await chatStream([{ role: 'user', content: userMsg }]);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setResult(full);
      }
      const finalHistory: ChatMsg[] = [{ role: 'user', content: userMsg }, { role: 'assistant', content: full }];
      setChatHistory(finalHistory);
      await handleSaveHistory(full, finalHistory);
    } catch { setError('分析失败，请重试'); }
    finally { setLoading(false); }
  }

  async function handleFollowUp() {
    if (!followUp.trim() || !chatHistory.length) return;
    setFollowUpLoading(true); setFollowUpResult('');
    const allMessages: ChatMsg[] = [...chatHistory, { role: 'user', content: followUp }];
    const messages = trimMessages(allMessages);
    try {
      const res = await chatStream(messages);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setFollowUpResult(full);
      }
      setChatHistory([...allMessages, { role: 'assistant', content: full }]);
      setFollowUp('');
    } catch { setError('追问失败，请重试'); }
    finally { setFollowUpLoading(false); }
  }

  function handleReset() {
    setStep(1); setBriefFiles([]); setScriptFiles([]);
    setBriefExtra(''); setScriptExtra(''); setResult('');
    setError(''); setFollowUp(''); setFollowUpResult(''); setChatHistory([]);
  }

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header">
        <div>
          <h1 className="page-title">产品卖点提取器</h1>
          <p className="page-desc">上传产品Brief + 达人文案，AI提炼机制/背书/口碑/产品力卖点卡</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => { setShowHistory(true); loadHistory(); }}>
          📋 历史记录
        </button>
      </div>

      {/* Step Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 24 }}>
        {['上传Brief', '达人文案', '卖点分析'].map((label, i) => {
          const num = i + 1;
          const isActive = step === num;
          const isDone = step > num;
          return (
            <div key={num} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600,
                  background: (isActive || isDone) ? 'var(--brand)' : 'var(--gray-200)',
                  color: (isActive || isDone) ? '#fff' : 'var(--gray-400)',
                }}>
                  {isDone ? '✓' : num}
                </div>
                <span style={{ marginTop: 4, fontSize: 12, color: isActive ? 'var(--brand)' : isDone ? 'var(--gray-500)' : 'var(--gray-400)' }}>
                  {label}
                </span>
              </div>
              {i < 2 && <div style={{ flex: 1, height: 2, background: step > num ? 'var(--brand)' : 'var(--gray-200)', marginBottom: 18 }} />}
            </div>
          );
        })}
      </div>

      {/* 错误提示 */}
      {error && (
        <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', borderRadius: 'var(--radius-md)', padding: '12px 16px', fontSize: 13, color: 'var(--danger)', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* 历史记录弹窗 */}
      {showHistory && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
          onClick={() => setShowHistory(false)}>
          <div className="card" style={{ width: '100%', maxWidth: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>📋 历史记录</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowHistory(false)}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
              {historyLoading
                ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
                : historyList.length === 0
                ? <div className="empty-state"><div className="empty-state-text">暂无历史记录</div></div>
                : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {historyList.map(item => (
                      <div key={item.id} className="card" style={{ cursor: 'pointer' }}>
                        <div className="card-body" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                          <div style={{ flex: 1, minWidth: 0 }} onClick={() => loadHistoryRecord(item.id)}>
                            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-800)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.productName}</div>
                            <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>{new Date(item.createdAt).toLocaleString('zh-CN')}</div>
                            <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{item.summary}</div>
                          </div>
                          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)', flexShrink: 0 }}
                            onClick={e => { e.stopPropagation(); handleDeleteHistory(item.id); }}>删除</button>
                        </div>
                      </div>
                    ))}
                  </div>
              }
            </div>
          </div>
        </div>
      )}

      {/* Step 1: 上传Brief */}
      {step === 1 && (
        <div className="card">
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <span style={{ fontSize: 24 }}>📄</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--gray-800)' }}>上传产品Brief</div>
                <div style={{ fontSize: 13, color: 'var(--gray-400)', marginTop: 2 }}>支持 PDF、Word、TXT 格式，可上传多个文件</div>
              </div>
            </div>

            <input ref={briefRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple style={{ display: 'none' }}
              onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'brief'); }} />

            {briefFiles.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
                {briefFiles.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--success-bg)', border: '1px solid var(--success)', borderRadius: 'var(--radius-sm)', padding: '8px 12px' }}>
                    <span style={{ color: 'var(--success)' }}>✅</span>
                    <span style={{ flex: 1, fontSize: 13, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => removeFile('brief', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}

            <div
              onClick={() => !uploadingBrief && briefRef.current?.click()}
              onDragOver={e => { e.preventDefault(); if (!uploadingBrief) setBriefDragOver(true); }}
              onDragLeave={() => setBriefDragOver(false)}
              onDrop={e => {
                e.preventDefault();
                setBriefDragOver(false);
                if (!uploadingBrief && e.dataTransfer.files.length) handleFilesUpload(e.dataTransfer.files, 'brief');
              }}
              style={{
                width: '100%', border: `2px dashed ${briefDragOver ? 'var(--brand)' : 'var(--brand-border)'}`,
                borderRadius: 'var(--radius-md)', padding: '24px 0', fontSize: 14,
                color: 'var(--brand)', background: briefDragOver ? 'rgba(245,154,35,0.12)' : 'var(--brand-light)',
                cursor: uploadingBrief ? 'not-allowed' : 'pointer', marginBottom: 16,
                opacity: uploadingBrief ? 0.5 : 1, textAlign: 'center',
                transition: 'border-color 0.15s, background 0.15s',
              }}
            >
              {uploadingBrief ? '正在解析文件...' : briefDragOver ? '松开即可上传' : briefFiles.length > 0 ? '点击或拖拽继续添加文件' : '点击或拖拽文件到此处上传（可多选）'}
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, color: 'var(--gray-500)', marginBottom: 6 }}>也可以直接粘贴补充内容</label>
              <textarea
                style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 14px', fontSize: 14, resize: 'none', outline: 'none', lineHeight: 1.6, boxSizing: 'border-box', fontFamily: 'var(--font-sans)' }}
                rows={5} placeholder="粘贴产品Brief内容..." value={briefExtra} onChange={e => setBriefExtra(e.target.value)} />
            </div>

            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => setStep(2)}>
              {hasBrief ? '下一步：上传达人文案 →' : '跳过，直接上传达人文案'}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: 上传达人文案 */}
      {step === 2 && (
        <div className="card">
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <span style={{ fontSize: 24 }}>🎬</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--gray-800)' }}>上传达人文案脚本</div>
                <div style={{ fontSize: 13, color: 'var(--gray-400)', marginTop: 2 }}>头部达人的讲解文案，可上传多个文件</div>
              </div>
            </div>

            {hasBrief && (
              <div style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 12 }}>
                ✓ Brief已就绪（{briefFiles.length}份{briefExtra.trim() ? ' + 补充' : ''}）
              </div>
            )}

            <input ref={scriptRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple style={{ display: 'none' }}
              onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'script'); }} />

            {scriptFiles.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
                {scriptFiles.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--success-bg)', border: '1px solid var(--success)', borderRadius: 'var(--radius-sm)', padding: '8px 12px' }}>
                    <span style={{ color: 'var(--success)' }}>✅</span>
                    <span style={{ flex: 1, fontSize: 13, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => removeFile('script', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}

            <div
              onClick={() => !uploadingScript && scriptRef.current?.click()}
              onDragOver={e => { e.preventDefault(); if (!uploadingScript) setScriptDragOver(true); }}
              onDragLeave={() => setScriptDragOver(false)}
              onDrop={e => {
                e.preventDefault();
                setScriptDragOver(false);
                if (!uploadingScript && e.dataTransfer.files.length) handleFilesUpload(e.dataTransfer.files, 'script');
              }}
              style={{
                width: '100%', border: `2px dashed ${scriptDragOver ? 'var(--brand)' : 'var(--brand-border)'}`,
                borderRadius: 'var(--radius-md)', padding: '24px 0', fontSize: 14,
                color: 'var(--brand)', background: scriptDragOver ? 'rgba(245,154,35,0.12)' : 'var(--brand-light)',
                cursor: uploadingScript ? 'not-allowed' : 'pointer', marginBottom: 16,
                opacity: uploadingScript ? 0.5 : 1, textAlign: 'center',
                transition: 'border-color 0.15s, background 0.15s',
              }}
            >
              {uploadingScript ? '正在解析文件...' : scriptDragOver ? '松开即可上传' : scriptFiles.length > 0 ? '点击或拖拽继续添加文件' : '📎 点击或拖拽达人文案到此处（可多选）'}
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, color: 'var(--gray-500)', marginBottom: 6 }}>也可以直接粘贴补充内容</label>
              <textarea
                style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px 14px', fontSize: 14, resize: 'none', outline: 'none', lineHeight: 1.6, boxSizing: 'border-box', fontFamily: 'var(--font-sans)' }}
                rows={5} placeholder="粘贴达人文案脚本..." value={scriptExtra} onChange={e => setScriptExtra(e.target.value)} />
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-ghost" onClick={() => setStep(1)}>← 上一步</button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={handleAnalyze}
                disabled={loading || (!hasBrief && !hasScript)}
              >
                {hasScript ? '开始提取卖点' : '请先上传达人文案 ↑'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: 结果 */}
      {step === 3 && (
        <div>
          {/* 加载中 */}
          {loading && !result && (
            <div className="card">
              <div className="card-body" style={{ textAlign: 'center', padding: '48px 24px' }}>
                <div className="spinner" style={{ marginBottom: 12 }} />
                <p style={{ color: 'var(--gray-500)', fontSize: 14 }}>AI 正在分析你的产品资料...</p>
                <p style={{ color: 'var(--gray-300)', fontSize: 13, marginTop: 4 }}>共 {briefFiles.length + scriptFiles.length} 份文档，请稍候</p>
              </div>
            </div>
          )}

          {/* 文件徽章 */}
          {(result || loading) && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              {briefFiles.length > 0 && (
                <span className="badge badge-brand">📄 {briefFiles.length} 份Brief</span>
              )}
              {scriptFiles.length > 0 && (
                <span className="badge badge-brand">🎬 {scriptFiles.length} 份文案</span>
              )}
            </div>
          )}

          {/* 分析报告 */}
          {result && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-body">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <span style={{ fontWeight: 600, fontSize: 15 }}>📊 卖点分析报告</span>
                  <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(result)}>复制全文</button>
                </div>
                <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14, lineHeight: 1.8, color: 'var(--gray-800)', margin: 0 }}>{result}</pre>
              </div>
            </div>
          )}

          {/* 追问回复 */}
          {followUpResult && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-body">
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>💬 追问回复</div>
                <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14, lineHeight: 1.8, color: 'var(--gray-800)', margin: 0 }}>{followUpResult}</pre>
              </div>
            </div>
          )}

          {/* 追问输入框 */}
          {result && !loading && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-body">
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-600)', marginBottom: 4 }}>和 AI 聊聊</div>
                <div style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 12 }}>对卖点分析有疑问？和 AI 讨论调整</div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    type="text"
                    style={{ flex: 1, border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '10px 14px', fontSize: 14, outline: 'none', fontFamily: 'var(--font-sans)' }}
                    placeholder="比如：帮我把卖点一的话术再优化一下..."
                    value={followUp}
                    onChange={e => setFollowUp(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); } }}
                  />
                  <button className="btn btn-primary" onClick={handleFollowUp} disabled={followUpLoading || !followUp.trim()}>
                    {followUpLoading ? '思考中...' : '发送'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 最终卖点卡 */}
          {result && !loading && (() => {
            const source = followUpResult || result;
            const cardMatch = source.match(/(?:##\s*)?🔥\s*极致卖点卡([\s\S]*?)(?=(?:##\s*)?💡\s*AI|$)/);
            const aiMatch = source.match(/(?:##\s*)?💡\s*AI补充建议[\s\S]*$/);
            const cardContent = cardMatch ? ('## 🔥 极致卖点卡' + cardMatch[1]).trim() : '';
            const fullCard = cardContent + (aiMatch ? '\n\n' + aiMatch[0] : '');
            if (!fullCard) return null;
            return (
              <div className="card" style={{ marginBottom: 16, border: '2px solid var(--brand-border)', background: 'var(--brand-light)' }}>
                <div className="card-body">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--brand)' }}>🔥 最终卖点卡</span>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(fullCard)}>复制卖点卡</button>
                      <button className="btn btn-primary btn-sm" onClick={() => {
                        const blob = new Blob([fullCard], { type: 'text/markdown;charset=utf-8' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url; a.download = '极致卖点卡.md'; a.click();
                        URL.revokeObjectURL(url);
                      }}>保存到电脑</button>
                    </div>
                  </div>
                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14, lineHeight: 1.8, color: 'var(--gray-800)', margin: 0 }}>{fullCard}</pre>
                </div>
              </div>
            );
          })()}

          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={handleReset}>重新开始分析新产品</button>
          </div>
        </div>
      )}
    </div>
  );
}
