import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import type { PersonaStep, PersonaTab, UploadedFile, FetchDouyinResult, KolSubmission, PersonaReport, PersonaReportDetail } from '../../types/persona';
import {
  fetchDouyin, parseFile, downloadQuestionnaireTemplate,
  generatePersona, optimizePersona, exportPersonaWord,
  getKolSubmissions, getPersonaReports, getPersonaReportDetail, deletePersonaReport,
} from '../../api/persona';

export default function PersonaPage() {
  // ── 步骤 ──
  const [step, setStep] = useState<PersonaStep>(1);

  // ── Step 1 状态 ──
  const [douyinId, setDouyinId] = useState('');
  const [fetchingDy, setFetchingDy] = useState(false);
  const [fetchDyError, setFetchDyError] = useState('');
  const [top10Content, setTop10Content] = useState('');
  const [recent30Content, setRecent30Content] = useState('');
  const [fetchDyResult, setFetchDyResult] = useState<FetchDouyinResult | null>(null);
  const [influencerFiles, setInfluencerFiles] = useState<UploadedFile[]>([]);
  const [supplementNotes, setSupplementNotes] = useState('');
  const [supplementFiles, setSupplementFiles] = useState<UploadedFile[]>([]);
  // KOL 导入
  const [kolSubmissions, setKolSubmissions] = useState<KolSubmission[]>([]);
  const [selectedKolId, setSelectedKolId] = useState<number | null>(null);

  // ── Step 2 状态 ──
  const [benchmarkProfileFiles, setBenchmarkProfileFiles] = useState<UploadedFile[]>([]);
  const [benchmarkPlanFiles, setBenchmarkPlanFiles] = useState<UploadedFile[]>([]);

  // ── Step 3 状态 ──
  const [activeTab, setActiveTab] = useState<PersonaTab>('profile');
  const [profileResult, setProfileResult] = useState('');
  const [planResult, setPlanResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [reportId, setReportId] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── 优化对话状态 ──
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [optimizeTarget, setOptimizeTarget] = useState<PersonaTab>('profile');
  const [optimizeMsgs, setOptimizeMsgs] = useState<Array<{ role: string; content: string }>>([]);
  const [optimizeInput, setOptimizeInput] = useState('');
  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const optimizeAbortRef = useRef<AbortController | null>(null);

  // ── 历史状态 ──
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyList, setHistoryList] = useState<PersonaReport[]>([]);

  // ── 加载 KOL 列表 ──
  useEffect(() => {
    getKolSubmissions().then(setKolSubmissions).catch(() => {});
  }, []);

  // ── 组件卸载时中止进行中的请求 ──
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      optimizeAbortRef.current?.abort();
    };
  }, []);

  // ── 数据汇总函数 ──
  const buildInfluencerInfo = useCallback(() => {
    return influencerFiles
      .filter(f => f.status === 'done' && f.text)
      .map(f => `=== ${f.name} ===\n${f.text}`)
      .join('\n\n');
  }, [influencerFiles]);

  const buildSupplementText = useCallback(() => {
    const parts: string[] = [];
    if (supplementNotes.trim()) parts.push(`=== 运营补充说明 ===\n${supplementNotes.trim()}`);
    const fileText = supplementFiles
      .filter(f => f.status === 'done' && f.text)
      .map(f => `=== ${f.name} ===\n${f.text}`)
      .join('\n\n');
    if (fileText) parts.push(fileText);
    return parts.join('\n\n');
  }, [supplementNotes, supplementFiles]);

  const buildBenchmarkText = useCallback(() => {
    const parts: string[] = [];
    const profileText = benchmarkProfileFiles
      .filter(f => f.status === 'done' && f.text)
      .map(f => `=== 对标人格档案：${f.name} ===\n${f.text}`)
      .join('\n\n');
    const planText = benchmarkPlanFiles
      .filter(f => f.status === 'done' && f.text)
      .map(f => `=== 对标内容规划：${f.name} ===\n${f.text}`)
      .join('\n\n');
    if (profileText) parts.push(profileText);
    if (planText) parts.push(planText);
    return parts.join('\n\n');
  }, [benchmarkProfileFiles, benchmarkPlanFiles]);

  // ── 文件上传处理 ──
  async function handleFileUpload(
    file: File,
    setter: React.Dispatch<React.SetStateAction<UploadedFile[]>>,
  ) {
    setter(prev => [...prev, { name: file.name, text: '', status: 'uploading' }]);
    try {
      const { text } = await parseFile(file);
      setter(prev => prev.map(f => f.name === file.name ? { ...f, text, status: 'done' as const } : f));
    } catch {
      setter(prev => prev.map(f => f.name === file.name ? { ...f, status: 'error' as const } : f));
      message.error(`${file.name} 解析失败`);
    }
  }

  function removeFile(name: string, setter: React.Dispatch<React.SetStateAction<UploadedFile[]>>) {
    setter(prev => prev.filter(f => f.name !== name));
  }

  // ── KOL 导入 ──
  function handleImportKol() {
    const kol = kolSubmissions.find(k => k.id === selectedKolId);
    if (!kol) return;
    const virtualFile: UploadedFile = {
      name: `KOL入驻_${kol.nickname}`,
      text: kol.formatted_answers + (kol.report ? `\n\n=== AI 入驻报告 ===\n${kol.report}` : ''),
      status: 'done',
    };
    setInfluencerFiles(prev => [...prev, virtualFile]);
    message.success(`已导入 ${kol.nickname} 的入驻数据`);
  }

  // ── 抖音号解析 ──
  async function handleFetchDouyin() {
    if (!douyinId.trim()) return;
    setFetchingDy(true);
    setFetchDyError('');
    try {
      const result = await fetchDouyin(douyinId.trim());
      setFetchDyResult(result);
      setTop10Content(result.top10_text);
      setRecent30Content(result.recent30_text);
    } catch (e) {
      setFetchDyError(e instanceof Error ? e.message : '解析失败');
    } finally {
      setFetchingDy(false);
    }
  }

  // ── 生成 ──
  async function handleGenerate() {
    const influencerInfo = buildInfluencerInfo();
    if (!influencerInfo.trim()) {
      message.error('请上传达人资料文档或从 KOL 入驻导入');
      return;
    }
    setLoading(true);
    setProfileResult('');
    setPlanResult('');
    setStep(3);
    setActiveTab('profile');
    abortRef.current = new AbortController();

    try {
      const { reader, reportId: rid } = await generatePersona({
        influencer_info: influencerInfo,
        top10_content: top10Content || undefined,
        supplement_text: buildSupplementText() || undefined,
        benchmark_text: buildBenchmarkText() || undefined,
        douyin_id: douyinId || undefined,
        douyin_nickname: fetchDyResult?.nickname || undefined,
        recent30_text: recent30Content || undefined,
        questionnaire_files: influencerFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
        supplement_files: supplementFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
        benchmark_profile_files: benchmarkProfileFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
        benchmark_plan_files: benchmarkPlanFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
      }, abortRef.current.signal);
      setReportId(rid);

      const decoder = new TextDecoder();
      let fullText = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
        const parts = fullText.split('===SPLIT===');
        setProfileResult(parts[0].trim());
        if (parts.length > 1) setPlanResult(parts[1].trim());
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        message.error('生成出错，请重试');
      }
    } finally {
      setLoading(false);
    }
  }

  // ── 导出 Word ──
  async function handleExportWord(type: 'profile' | 'plan') {
    if (!reportId) { message.error('请等待生成完成'); return; }
    setExporting(true);
    try {
      await exportPersonaWord({ report_id: reportId, type });
    } catch { message.error('导出失败'); }
    finally { setExporting(false); }
  }

  // ── 优化对话 ──
  async function handleOptimizeSend() {
    if (!optimizeInput.trim()) return;
    const newMsgs = [...optimizeMsgs, { role: 'user' as const, content: optimizeInput }];
    setOptimizeMsgs(newMsgs);
    setOptimizeInput('');
    setOptimizeLoading(true);
    optimizeAbortRef.current = new AbortController();

    try {
      const reader = await optimizePersona({
        messages: newMsgs.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })),
        current_content: optimizeTarget === 'profile' ? profileResult : planResult,
        content_type: optimizeTarget,
        influencer_info: buildInfluencerInfo(),
        benchmark_text: buildBenchmarkText() || undefined,
      }, optimizeAbortRef.current.signal);

      const decoder = new TextDecoder();
      let aiContent = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        aiContent += decoder.decode(value, { stream: true });
      }
      setOptimizeMsgs(prev => [...prev, { role: 'assistant', content: aiContent }]);
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        message.error('优化请求失败');
      }
    } finally {
      setOptimizeLoading(false);
    }
  }

  function handleAdoptOptimize(aiContent: string) {
    if (optimizeTarget === 'profile') setProfileResult(aiContent);
    else setPlanResult(aiContent);
    setOptimizeOpen(false);
    message.success('已采纳优化版本');
  }

  // ── 历史管理 ──
  async function loadHistory() {
    setHistoryOpen(true);
    try {
      const list = await getPersonaReports();
      setHistoryList(list);
    } catch { message.error('加载历史失败'); }
  }

  async function loadHistoryDetail(id: number) {
    try {
      const detail: PersonaReportDetail = await getPersonaReportDetail(id);
      if (detail.profile_result) setProfileResult(detail.profile_result);
      if (detail.plan_result) setPlanResult(detail.plan_result);
      setReportId(id);
      setHistoryOpen(false);
      setStep(3);
      message.success('已加载历史报告');
    } catch { message.error('加载详情失败'); }
  }

  async function handleDeleteHistory(id: number) {
    try {
      await deletePersonaReport(id);
      setHistoryList(prev => prev.filter(r => r.id !== id));
      message.success('已删除');
    } catch { message.error('删除失败'); }
  }

  // ── 重置 ──
  function handleReset() {
    abortRef.current?.abort();
    optimizeAbortRef.current?.abort();
    setStep(1);
    setDouyinId(''); setFetchDyResult(null); setFetchDyError('');
    setTop10Content(''); setRecent30Content('');
    setInfluencerFiles([]); setSupplementNotes(''); setSupplementFiles([]);
    setSelectedKolId(null);
    setBenchmarkProfileFiles([]); setBenchmarkPlanFiles([]);
    setProfileResult(''); setPlanResult('');
    setReportId(null); setLoading(false);
    setOptimizeOpen(false); setOptimizeMsgs([]);
  }

  // ── 验证条件 ──
  const hasInfluencerData = influencerFiles.some(f => f.status === 'done') || !!selectedKolId;
  const hasParsedDouyin = !douyinId.trim() || !!fetchDyResult;
  const canGoStep2 = hasInfluencerData && hasParsedDouyin;
  const hasBenchmarkData = benchmarkProfileFiles.some(f => f.status === 'done') || benchmarkPlanFiles.some(f => f.status === 'done');

  // ── 文件上传区组件 ──
  function FileUploadArea({ files, setter, accept = '.docx,.pdf,.txt,.md' }: {
    files: UploadedFile[]; setter: React.Dispatch<React.SetStateAction<UploadedFile[]>>; accept?: string;
  }) {
    return (
      <div>
        <input type="file" multiple accept={accept} style={{ display: 'none' }}
          id={`file-upload-${Math.random().toString(36).slice(2)}`}
          onChange={e => { const files = e.target.files; if (files) Array.from(files).forEach(f => handleFileUpload(f, setter)); }} />
        <div className="upload-zone" onClick={e => { const input = e.currentTarget.previousElementSibling as HTMLInputElement; input?.click(); }}
          style={{ border: '2px dashed var(--border)', borderRadius: 8, padding: '20px', textAlign: 'center', cursor: 'pointer', background: 'var(--bg-page)' }}>
          点击或拖拽上传文件（支持 .docx .pdf .txt .md）
        </div>
        {files.map(f => (
          <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, padding: '4px 8px', background: 'var(--bg-card)', borderRadius: 4 }}>
            <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
            <span className={`badge ${f.status === 'done' ? 'badge-success' : f.status === 'error' ? 'badge-danger' : 'badge-warning'}`}>
              {f.status === 'uploading' ? '解析中...' : f.status === 'done' ? '完成' : '失败'}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={() => removeFile(f.name, setter)}>删除</button>
          </div>
        ))}
      </div>
    );
  }

  // ── 渲染 ──
  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">人格定位</h1>
          <p className="page-desc">输入达人资料，AI 生成专属人格档案 + 内容规划</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={loadHistory}>历史记录</button>
      </div>

      {/* 步骤指示器 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0, margin: '24px 0 32px' }}>
        {(['填写达人资料', '选择对标达人', '生成结果'] as const).map((label, i) => {
          const s = (i + 1) as PersonaStep;
          const done = step > s;
          const active = step === s;
          return (
            <div key={s} style={{ display: 'flex', alignItems: 'center' }}>
              <div onClick={() => { if (done) setStep(s); }}
                style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: done ? 'pointer' : 'default' }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 600, color: active || done ? '#fff' : 'var(--text-secondary)',
                  background: active ? 'var(--brand)' : done ? 'var(--brand-dark)' : 'var(--bg-page)',
                  border: active || done ? 'none' : '1px solid var(--border)',
                }}>{done ? '✓' : s}</div>
                <span style={{ fontSize: 13, color: active ? 'var(--brand)' : done ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: active ? 600 : 400 }}>{label}</span>
              </div>
              {i < 2 && <div style={{ width: 60, height: 1, background: 'var(--border)', margin: '0 12px' }} />}
            </div>
          );
        })}
      </div>

      {/* Step 1: 填写达人资料 */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* 抖音号 */}
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8 }}>
            <div className="section-title">抖音号解析（选填）</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input value={douyinId} onChange={e => setDouyinId(e.target.value)} placeholder="输入抖音号或主页链接"
                style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }} />
              <button className="btn btn-primary" onClick={handleFetchDouyin} disabled={fetchingDy || !douyinId.trim()}>
                {fetchingDy ? '解析中...' : '解析'}
              </button>
            </div>
            {fetchDyError && <div style={{ color: 'var(--danger)', fontSize: 12, marginTop: 6 }}>{fetchDyError}</div>}
            {fetchDyResult && <div style={{ color: 'var(--success)', fontSize: 12, marginTop: 6 }}>已解析：{fetchDyResult.nickname}，共 {fetchDyResult.total_videos} 个视频，抓取 TOP{fetchDyResult.top10_count} 条</div>}
          </div>

          {/* 达人资料 */}
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8 }}>
            <div className="section-title">达人资料（必填）</div>
            {/* KOL 导入 */}
            {kolSubmissions.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>从 KOL 入驻导入：</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <select value={selectedKolId ?? ''} onChange={e => setSelectedKolId(e.target.value ? Number(e.target.value) : null)}
                    style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }}>
                    <option value="">选择已完成的 KOL 入驻...</option>
                    {kolSubmissions.map(k => <option key={k.id} value={k.id}>{k.nickname}</option>)}
                  </select>
                  <button className="btn btn-ghost" disabled={!selectedKolId} onClick={handleImportKol}>导入</button>
                </div>
              </div>
            )}
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>或上传文件：</div>
            <button className="btn btn-ghost btn-sm" style={{ marginBottom: 8 }} onClick={() => downloadQuestionnaireTemplate()}>下载问卷模板</button>
            <FileUploadArea files={influencerFiles} setter={setInfluencerFiles} />
          </div>

          {/* 补充信息 */}
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8 }}>
            <div className="section-title">补充信息（选填）</div>
            <textarea value={supplementNotes} onChange={e => setSupplementNotes(e.target.value)}
              placeholder="输入补充说明..."
              style={{ width: '100%', minHeight: 80, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, resize: 'vertical', marginBottom: 12, boxSizing: 'border-box' }} />
            <FileUploadArea files={supplementFiles} setter={setSupplementFiles} />
          </div>

          <div style={{ textAlign: 'right' }}>
            <button className="btn btn-primary" disabled={!canGoStep2} onClick={() => setStep(2)}>下一步</button>
          </div>
        </div>
      )}

      {/* Step 2: 对标资料 */}
      {step === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8 }}>
            <div className="section-title">对标人格档案（选填）</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>上传同赛道已验证成功的达人方案，AI 会参照对标风格为目标达人定制方案。</div>
            <FileUploadArea files={benchmarkProfileFiles} setter={setBenchmarkProfileFiles} />
          </div>
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8 }}>
            <div className="section-title">对标内容规划（选填）</div>
            <FileUploadArea files={benchmarkPlanFiles} setter={setBenchmarkPlanFiles} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button className="btn btn-ghost" onClick={() => setStep(1)}>上一步</button>
            <div style={{ display: 'flex', gap: 8 }}>
              {!hasBenchmarkData && <button className="btn btn-ghost" onClick={handleGenerate}>跳过，直接生成</button>}
              <button className="btn btn-primary" onClick={handleGenerate}>开始生成</button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: 生成结果 */}
      {step === 3 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 顶部操作栏 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost btn-sm" disabled={loading || !reportId} onClick={() => handleExportWord('profile')}>导出人格档案</button>
              <button className="btn btn-ghost btn-sm" disabled={loading || !reportId} onClick={() => handleExportWord('plan')}>导出内容规划</button>
              {exporting && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>导出中...</span>}
            </div>
            <button className="btn btn-ghost btn-sm" onClick={handleReset}>重新开始</button>
          </div>

          {/* Tab 切换 */}
          <div style={{ display: 'flex', borderBottom: '2px solid var(--border)' }}>
            {(['profile', 'plan'] as const).map(tab => (
              <div key={tab} onClick={() => setActiveTab(tab)}
                style={{ padding: '10px 24px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
                  color: activeTab === tab ? 'var(--brand)' : 'var(--text-secondary)',
                  borderBottom: activeTab === tab ? '2px solid var(--brand)' : 'none', marginBottom: -2 }}>
                {tab === 'profile' ? '人格档案' : '内容规划'}
              </div>
            ))}
          </div>

          {/* 内容展示 */}
          <div style={{ background: 'var(--bg-card)', padding: 20, borderRadius: 8, minHeight: 300 }}>
            {loading && !(profileResult || planResult) ? (
              <div className="empty-state"><div className="empty-state-text">AI 正在生成中...</div></div>
            ) : (
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13, lineHeight: 1.8, margin: 0 }}>
                {activeTab === 'profile' ? profileResult || '等待生成...' : planResult || '等待生成...'}
              </pre>
            )}
            {loading && (profileResult || planResult) && (
              <div style={{ textAlign: 'center', padding: 8, color: 'var(--text-secondary)', fontSize: 12 }}>生成中...</div>
            )}
          </div>

          {/* 操作按钮 */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost btn-sm" disabled={loading}
              onClick={() => navigator.clipboard.writeText(activeTab === 'profile' ? profileResult : planResult).then(() => message.success('已复制'))}>复制</button>
            <button className="btn btn-ghost btn-sm" disabled={loading}
              onClick={() => { setOptimizeTarget(activeTab); setOptimizeMsgs([]); setOptimizeInput(''); setOptimizeOpen(true); }}>
              优化{activeTab === 'profile' ? '人格档案' : '内容规划'}
            </button>
          </div>
        </div>
      )}

      {/* 优化对话 Overlay — 全局，不绑定 Step */}
      {optimizeOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--bg-card)', borderRadius: 12, width: '90%', maxWidth: 800, maxHeight: '80vh', display: 'flex', flexDirection: 'column', padding: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>优化{optimizeTarget === 'profile' ? '人格档案' : '内容规划'}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setOptimizeOpen(false); optimizeAbortRef.current?.abort(); }}>关闭</button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {optimizeMsgs.map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div style={{ maxWidth: '80%', padding: '10px 14px', borderRadius: 8, fontSize: 13, lineHeight: 1.6,
                    background: m.role === 'user' ? 'var(--brand)' : 'var(--bg-page)', color: m.role === 'user' ? '#fff' : 'var(--text-primary)' }}>
                    <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{m.content}</pre>
                    {m.role === 'assistant' && (
                      <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}
                        onClick={() => handleAdoptOptimize(m.content)}>采纳此版本</button>
                    )}
                  </div>
                </div>
              ))}
              {optimizeLoading && <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>AI 思考中...</div>}
            </div>
            <div style={{ display: 'flex', gap: 8, padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
              <input value={optimizeInput} onChange={e => setOptimizeInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleOptimizeSend(); } }}
                placeholder="输入优化意见..."
                style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }} />
              <button className="btn btn-primary" onClick={handleOptimizeSend} disabled={optimizeLoading || !optimizeInput.trim()}>发送</button>
            </div>
          </div>
        </div>
      )}

      {/* 历史记录抽屉 — 全局，不绑定 Step */}
      {historyOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}
          onClick={() => setHistoryOpen(false)}>
          <div style={{ width: 380, background: 'var(--bg-card)', height: '100%', padding: 20, overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>历史报告</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setHistoryOpen(false)}>关闭</button>
            </div>
            {historyList.length === 0 ? <div className="empty-state-text">暂无历史记录</div> : historyList.map(r => (
              <div key={r.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ cursor: 'pointer', flex: 1 }} onClick={() => loadHistoryDetail(r.id)}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{r.influencer_name || r.douyin_nickname || '未命名'}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{r.created_at?.slice(0, 16).replace('T', ' ')}</div>
                </div>
                <button className="btn btn-danger-ghost btn-sm" onClick={() => handleDeleteHistory(r.id)}>删除</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
