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

  const stepLabels = ['上传Brief', '达人文案', '卖点分析'];

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-amber-50">
      <div className="bg-gradient-to-r from-orange-500 to-amber-500 text-white">
        <div className="max-w-3xl mx-auto px-6 py-10">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-4xl">🎯</span>
            <h1 className="text-3xl font-bold tracking-tight">产品卖点提取器</h1>
          </div>
          <p className="text-orange-100 text-base">上传产品Brief + 达人文案，AI帮你提炼最炸裂的卖点</p>
        </div>
      </div>
      <div className="max-w-3xl mx-auto px-6 pt-8 pb-2">
        <div className="flex items-center justify-between mb-8">
          {stepLabels.map((label, i) => {
            const num = i + 1; const isActive = step === num; const isDone = step > num;
            return (
              <div key={num} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all ${isActive ? 'bg-orange-500 text-white shadow-lg shadow-orange-200' : isDone ? 'bg-orange-500 text-white' : 'bg-gray-200 text-gray-400'}`}>
                    {isDone ? '✓' : num}
                  </div>
                  <span className={`mt-2 text-xs font-medium ${isActive ? 'text-orange-600' : isDone ? 'text-orange-400' : 'text-gray-400'}`}>{label}</span>
                </div>
                {i < stepLabels.length - 1 && <div className={`h-[2px] w-full mx-2 mt-[-18px] ${step > num ? 'bg-orange-400' : 'bg-gray-200'}`} />}
              </div>
            );
          })}
        </div>
      </div>
      <div className="max-w-3xl mx-auto px-6 pb-16">
        {error && <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4 text-sm text-red-600 mb-6">{error}</div>}

        {showHistory && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowHistory(false)}>
            <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
                <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2"><span>📋</span> 历史记录</h2>
                <button onClick={() => setShowHistory(false)} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {historyLoading ? <div className="text-center py-12 text-gray-400">加载中...</div>
                : historyList.length === 0 ? <div className="text-center py-12 text-gray-400">暂无历史记录</div>
                : <div className="space-y-3">
                    {historyList.map(item => (
                      <div key={item.id} className="border border-orange-100 rounded-xl p-4 hover:bg-orange-50/50 transition group">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0 cursor-pointer" onClick={() => loadHistoryRecord(item.id)}>
                            <h3 className="font-semibold text-gray-800 text-sm truncate">{item.productName}</h3>
                            <p className="text-xs text-gray-400 mt-1">{new Date(item.createdAt).toLocaleString('zh-CN')}</p>
                            <p className="text-xs text-gray-500 mt-2 line-clamp-2">{item.summary}</p>
                          </div>
                          <button onClick={e => { e.stopPropagation(); handleDeleteHistory(item.id); }} className="text-gray-300 hover:text-red-500 transition text-sm shrink-0 opacity-0 group-hover:opacity-100">删除</button>
                        </div>
                      </div>
                    ))}
                  </div>}
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="w-12 h-12 rounded-xl bg-orange-100 flex items-center justify-center text-2xl">📄</span>
                <div><h2 className="text-xl font-bold text-gray-800">上传产品Brief</h2><p className="text-sm text-gray-400 mt-0.5">支持 PDF、Word、TXT 格式，可上传多个文件</p></div>
              </div>
              <button onClick={() => { setShowHistory(true); loadHistory(); }} className="text-sm text-orange-500 hover:text-orange-600 border border-orange-200 rounded-lg px-4 py-2 hover:bg-orange-50 transition flex items-center gap-1.5"><span>📋</span> 历史记录</button>
            </div>
            <input ref={briefRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple className="hidden" onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'brief'); }} />
            {briefFiles.length > 0 && (
              <div className="mb-4 space-y-2">
                {briefFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 bg-green-50 border border-green-100 rounded-xl px-4 py-3">
                    <span className="text-green-500 text-lg">✅</span>
                    <span className="text-sm text-green-700 truncate flex-1">{f.name}</span>
                    <button className="text-gray-400 hover:text-red-500 transition text-lg" onClick={() => removeFile('brief', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => briefRef.current?.click()} disabled={uploadingBrief} className="w-full border-2 border-dashed border-orange-200 rounded-xl py-8 text-base text-orange-400 hover:border-orange-400 hover:text-orange-500 hover:bg-orange-50/50 transition disabled:opacity-50 mb-5">
              {uploadingBrief ? '正在解析文件...' : briefFiles.length > 0 ? '+ 继续添加文件' : '点击上传文件（可多选）'}
            </button>
            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">也可以直接粘贴补充内容</label>
              <textarea className="w-full border border-gray-200 rounded-xl px-5 py-4 text-[15px] resize-none focus:outline-none focus:ring-2 focus:ring-orange-300 leading-relaxed" rows={6} placeholder="粘贴产品Brief内容..." value={briefExtra} onChange={e => setBriefExtra(e.target.value)} />
            </div>
            <button onClick={() => setStep(2)} className="w-full bg-gradient-to-r from-orange-500 to-amber-500 text-white font-semibold py-4 rounded-xl text-base hover:from-orange-600 hover:to-amber-600 transition shadow-lg shadow-orange-200">
              {hasBrief ? '下一步：上传达人文案' : '跳过，直接上传达人文案'}
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <span className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center text-2xl">🎬</span>
              <div><h2 className="text-xl font-bold text-gray-800">上传达人文案脚本</h2><p className="text-sm text-gray-400 mt-0.5">头部达人的讲解文案，可上传多个文件</p></div>
            </div>
            {hasBrief && <div className="flex items-center gap-1.5 mb-4 text-xs text-gray-400"><span>✓</span><span>Brief已就绪（{briefFiles.length}份{briefExtra.trim() ? ' + 补充' : ''}）</span></div>}
            <input ref={scriptRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.pages" multiple className="hidden" onChange={e => { if (e.target.files?.length) handleFilesUpload(e.target.files, 'script'); }} />
            {scriptFiles.length > 0 && (
              <div className="mb-4 space-y-2">
                {scriptFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 bg-green-50 border border-green-100 rounded-xl px-4 py-3">
                    <span className="text-green-500 text-lg">✅</span>
                    <span className="text-sm text-green-700 truncate flex-1">{f.name}</span>
                    <button className="text-gray-400 hover:text-red-500 transition text-lg" onClick={() => removeFile('script', i)}>✕</button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => scriptRef.current?.click()} disabled={uploadingScript} className={`w-full border-2 border-dashed rounded-xl py-8 text-base transition disabled:opacity-50 mb-5 ${hasScript ? 'border-amber-200 text-amber-400 hover:border-amber-400' : 'border-amber-300 text-amber-500 bg-amber-50/30 hover:border-amber-400'}`}>
              {uploadingScript ? '正在解析文件...' : scriptFiles.length > 0 ? '+ 继续添加文件' : '📎 点击上传达人文案（可多选）'}
            </button>
            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">也可以直接粘贴补充内容</label>
              <textarea className="w-full border border-gray-200 rounded-xl px-5 py-4 text-[15px] resize-none focus:outline-none focus:ring-2 focus:ring-amber-300 leading-relaxed" rows={6} placeholder="粘贴达人文案脚本..." value={scriptExtra} onChange={e => setScriptExtra(e.target.value)} />
            </div>
            <div className="flex items-center gap-4">
              <button onClick={() => setStep(1)} className="px-6 py-4 border border-gray-200 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition">上一步</button>
              <button onClick={handleAnalyze} disabled={loading || (!hasBrief && !hasScript)} className="flex-1 bg-gradient-to-r from-orange-500 to-amber-500 text-white font-semibold py-4 rounded-xl text-base hover:from-orange-600 hover:to-amber-600 transition disabled:opacity-50 shadow-lg shadow-orange-200">
                {hasScript ? '开始提取卖点' : '请先上传达人文案 ↑'}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            {loading && !result && (
              <div className="bg-white rounded-2xl border border-orange-100 p-12 shadow-sm text-center">
                <svg className="animate-spin h-10 w-10 mx-auto mb-4 text-orange-500" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                <p className="text-gray-500 text-base">AI 正在分析你的产品资料...</p>
                <p className="text-gray-300 text-sm mt-2">共 {briefFiles.length + scriptFiles.length} 份文档，请稍候</p>
              </div>
            )}
            {result && (
              <div className="bg-white rounded-2xl border border-orange-100 p-8 shadow-sm mb-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2"><span>📊</span> 卖点分析报告</h2>
                  <button onClick={() => navigator.clipboard.writeText(result)} className="text-sm text-orange-500 hover:text-orange-600 border border-orange-200 rounded-lg px-4 py-2 hover:bg-orange-50 transition">复制全文</button>
                </div>
                <SimpleMarkdown text={result} />
              </div>
            )}
            {followUpResult && (
              <div className="bg-white rounded-2xl border border-amber-100 p-8 shadow-sm mb-6">
                <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2 mb-6"><span>💬</span> 追问回复</h2>
                <SimpleMarkdown text={followUpResult} />
              </div>
            )}
            {result && !loading && (
              <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm mb-6">
                <h3 className="text-sm font-semibold text-gray-600 mb-1">和 AI 聊聊</h3>
                <div className="flex gap-3">
                  <input type="text" className="flex-1 border border-gray-200 rounded-xl px-5 py-3.5 text-[15px] focus:outline-none focus:ring-2 focus:ring-orange-300" placeholder="比如：帮我把卖点一的话术再优化一下..." value={followUp} onChange={e => setFollowUp(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); } }} />
                  <button onClick={handleFollowUp} disabled={followUpLoading || !followUp.trim()} className="bg-orange-500 text-white px-6 py-3.5 rounded-xl text-sm font-semibold hover:bg-orange-600 transition disabled:opacity-50">
                    {followUpLoading ? '思考中...' : '发送'}
                  </button>
                </div>
              </div>
            )}
            {result && !loading && (() => {
              const source = followUpResult || result;
              const cardMatch = source.match(/(?:##\s*)?🔥\s*极致卖点卡([\s\S]*?)(?=(?:##\s*)?💡\s*AI|$)/);
              const aiMatch = source.match(/(?:##\s*)?💡\s*AI补充建议[\s\S]*$/);
              const cardContent = cardMatch ? ('## 🔥 极致卖点卡' + cardMatch[1]).trim() : '';
              const fullCard = cardContent + (aiMatch ? '\n\n' + aiMatch[0] : '');
              if (!fullCard) return null;
              return (
                <div className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl border-2 border-orange-200 p-8 shadow-sm">
                  <div className="flex items-center justify-between mb-5">
                    <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2"><span>🔥</span> 最终卖点卡</h2>
                    <div className="flex gap-2">
                      <button onClick={() => navigator.clipboard.writeText(fullCard)} className="text-sm text-orange-600 hover:text-orange-700 border border-orange-300 rounded-lg px-4 py-2 hover:bg-orange-100 transition font-medium">复制卖点卡</button>
                      <button onClick={() => { const blob = new Blob([fullCard], { type: 'text/markdown;charset=utf-8' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = '极致卖点卡.md'; a.click(); URL.revokeObjectURL(url); }} className="text-sm text-white bg-orange-500 hover:bg-orange-600 rounded-lg px-4 py-2 transition font-medium shadow-sm">保存到电脑</button>
                    </div>
                  </div>
                  <SimpleMarkdown text={fullCard} />
                </div>
              );
            })()}
            <div className="text-center mt-6"><button onClick={handleReset} className="text-sm text-gray-400 hover:text-orange-500 transition">重新开始分析新产品</button></div>
          </div>
        )}
      </div>
    </div>
  );
}
