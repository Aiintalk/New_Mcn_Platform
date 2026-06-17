// frontend/src/pages/operator/PersonaReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import * as XLSX from 'xlsx';
import { generateStream, saveReport, getOutputs } from '../../api/personaReview';
import type { OutputItem } from '../../api/personaReview';

/* ── Types ── */
interface ScriptEntry { id: string; title: string; content: string; source: string }

interface ExcelRow {
  date: string;
  liveTheme: string;
  videoTheme: string;
  videoType: string;
  totalPlays: string;
  completionRate: string;
  fiveSecRate: string;
  likes: string;
  comments: string;
  adSpend: string;
}

/* ── Excel 解析（100% copy 旧 page.tsx parseTransposedExcel，仅转置格式）── */
function parseTransposedExcel(wb: XLSX.WorkBook): ExcelRow[] {
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) return [];
  const raw: unknown[][] = XLSX.utils.sheet_to_json(ws, { header: 1 });
  if (raw.length < 2) return [];

  const knownLabels: [string[], keyof ExcelRow][] = [
    [['发布时间'], 'date'],
    [['直播主题'], 'liveTheme'],
    [['视频主题'], 'videoTheme'],
    [['视频类型'], 'videoType'],
    [['总播放量', '播放量'], 'totalPlays'],
    [['完播率'], 'completionRate'],
    [['5s完播率', '5秒完播率'], 'fiveSecRate'],
    [['点赞'], 'likes'],
    [['评论'], 'comments'],
    [['投放金额', '投放'], 'adSpend'],
  ];

  const rowMapping: { rowIdx: number; key: keyof ExcelRow }[] = [];
  for (let r = 0; r < raw.length; r++) {
    const cellVal = String((raw[r] as unknown[])?.[0] ?? '').trim();
    for (const [aliases, key] of knownLabels) {
      if (aliases.some(a => cellVal.includes(a))) {
        rowMapping.push({ rowIdx: r, key });
        break;
      }
    }
  }
  if (rowMapping.length === 0) return [];

  const numCols = Math.max(...raw.map(r => (r as unknown[])?.length ?? 0));
  const results: ExcelRow[] = [];
  for (let c = 1; c < numCols; c++) {
    const entry: Partial<ExcelRow> = {};
    let hasData = false;
    for (const { rowIdx, key } of rowMapping) {
      const val = (raw[rowIdx] as unknown[])?.[c];
      if (val !== undefined && val !== null && val !== '') {
        entry[key] = String(val).trim();
        hasData = true;
      }
    }
    if (hasData && (entry.videoTheme || entry.date)) results.push(entry as ExcelRow);
  }
  return results;
}

function extractTitle(text: string): string {
  const firstLine = text.split('\n').map(l => l.trim()).find(l => l.length > 0);
  if (!firstLine) return '(无标题)';
  return firstLine.length > 60 ? firstLine.slice(0, 60) + '...' : firstLine;
}

let _nextId = 0;
function genId() { return `script-${++_nextId}`; }

/* ── Main Component ── */
export default function PersonaReviewPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [error, setError] = useState('');

  const [scripts, setScripts] = useState<ScriptEntry[]>([]);
  const [pasteInput, setPasteInput] = useState('');
  const scriptFileRef = useRef<HTMLInputElement>(null);

  const [excelData, setExcelData] = useState<ExcelRow[]>([]);
  const [excelFileName, setExcelFileName] = useState('');
  const excelFileRef = useRef<HTMLInputElement>(null);

  const [report, setReport] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<OutputItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);

  /* ── Step 1: 添加脚本 ── */
  function handleAddPaste() {
    const text = pasteInput.trim();
    if (!text) { setError('请先粘贴脚本内容'); return; }

    const separator = /\n(?:={3,}|-{3,})\n/;
    const segments = separator.test(text)
      ? text.split(separator).map(s => s.trim()).filter(s => s.length > 0)
      : [text];

    const newEntries: ScriptEntry[] = segments.map(s => ({
      id: genId(),
      title: extractTitle(s),
      content: s,
      source: 'paste',
    }));
    setScripts(prev => [...prev, ...newEntries]);
    setPasteInput('');
    setError('');
  }

  async function handleScriptFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const text = await file.text();
      if (text.trim()) {
        setScripts(prev => [...prev, {
          id: genId(),
          title: extractTitle(text),
          content: text.trim(),
          source: file.name,
        }]);
      }
    }
    e.target.value = '';
  }

  function removeScript(id: string) {
    setScripts(prev => prev.filter(s => s.id !== id));
  }

  /* ── Step 2: 解析 Excel ── */
  const handleExcelUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExcelFileName(file.name);
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = new Uint8Array(evt.target?.result as ArrayBuffer);
        const wb = XLSX.read(data, { type: 'array' });
        const parsed = parseTransposedExcel(wb);
        if (parsed.length === 0) { setError('未能解析Excel数据，请检查格式（仅支持转置格式）'); return; }
        setExcelData(parsed);
        setError('');
      } catch { setError('Excel解析失败'); }
    };
    reader.readAsArrayBuffer(file);
  }, []);

  /* ── Step 3: 生成报告 ── */
  async function handleGenerate(skipExcel = false) {
    if (scripts.length === 0) { setError('请先上传脚本'); return; }

    const excelPayload = skipExcel ? [] : excelData.map(row => ({
      date: row.date || '',
      live_theme: row.liveTheme || '',
      video_theme: row.videoTheme || '',
      video_type: row.videoType || '',
      total_plays: row.totalPlays || '',
      completion_rate: row.completionRate || '',
      five_sec_rate: row.fiveSecRate || '',
      likes: row.likes || '',
      comments: row.comments || '',
      ad_spend: row.adSpend || '',
    }));

    const scriptsPayload = scripts.map(s => ({ title: s.title, content: s.content }));

    setStep(3);
    setReportLoading(true);
    setReport('');
    setSavedId(null);
    setTaskId(null);
    setError('');

    try {
      const resp = await generateStream({ scripts: scriptsPayload, excel_data: excelPayload });
      if (!resp.ok) throw new Error(`生成失败: ${resp.status}`);

      const tid = resp.headers.get('x-task-id');
      if (tid) setTaskId(parseInt(tid));

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无响应流');
      const decoder = new TextDecoder();
      let text = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        setReport(text);
        if (reportRef.current) reportRef.current.scrollTop = reportRef.current.scrollHeight;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成报告失败');
    } finally {
      setReportLoading(false);
    }
  }

  async function handleSave() {
    if (!report.trim() || taskId === null) return;
    setSaving(true);
    try {
      const hasExcel = excelData.length > 0;
      const res = await saveReport({
        task_id: taskId,
        report,
        script_count: scripts.length,
        has_excel: hasExcel,
      });
      setSavedId(res.output_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  function handleExport() {
    const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const dateStr = new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `人设脚本复盘_${dateStr}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function loadHistory(page = 1) {
    setHistoryLoading(true);
    try {
      const res = await getOutputs(page, 20);
      setHistoryItems(res.items);
      setHistoryTotal(res.total);
      setHistoryPage(page);
    } catch {
      setError('加载历史记录失败');
    } finally {
      setHistoryLoading(false);
    }
  }

  const STEPS = [
    { n: 1, label: '上传脚本' },
    { n: 2, label: '上传复盘表' },
    { n: 3, label: '复盘报告' },
  ];

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 className="page-title">人设脚本复盘</h1>
          <p className="page-desc">上传脚本 → 上传复盘表 → AI 生成复盘报告</p>
        </div>
        <button
          className="btn btn-ghost"
          style={{ marginTop: 4 }}
          onClick={() => { setShowHistory(true); loadHistory(1); }}
        >
          历史报告
        </button>
      </div>

      {/* Step Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {STEPS.map(({ n, label }) => (
          <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600, flexShrink: 0,
              background: step >= n ? 'var(--brand)' : 'var(--neutral-200)',
              color: step >= n ? '#fff' : 'var(--neutral-500)',
            }}>
              {step > n ? '✓' : n}
            </div>
            <span style={{
              fontSize: 14,
              fontWeight: step >= n ? 500 : 400,
              color: step >= n ? 'var(--neutral-900)' : 'var(--neutral-400)',
            }}>{label}</span>
            {n < 3 && <div style={{ width: 40, height: 2, background: step > n ? 'var(--brand)' : 'var(--neutral-200)' }} />}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          marginBottom: 16, padding: '10px 14px', borderRadius: 8,
          background: '#fff5f5', border: '1px solid #ffcdd2', color: '#c62828',
          fontSize: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {error}
          <button onClick={() => setError('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#e57373', marginLeft: 12 }}>✕</button>
        </div>
      )}

      {/* ── Step 1: 上传脚本 ── */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {scripts.length > 0 && (
            <div className="card">
              <div className="card-body">
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--neutral-700)', marginBottom: 12 }}>
                  已添加 {scripts.length} 条脚本
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {scripts.map((s, i) => (
                    <div key={s.id} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 12px',
                      background: 'var(--neutral-50)', borderRadius: 8,
                    }}>
                      <span style={{ fontSize: 12, color: 'var(--neutral-400)', marginTop: 2, minWidth: 20 }}>{i + 1}.</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 14, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--neutral-400)', marginTop: 2 }}>
                          {s.source === 'paste' ? '手动粘贴' : s.source} · {s.content.length} 字
                        </div>
                      </div>
                      <button
                        onClick={() => removeScript(s.id)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--neutral-300)', fontSize: 14, flexShrink: 0 }}
                      >✕</button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-body">
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>粘贴脚本文案</h2>
              <p style={{ fontSize: 13, color: 'var(--neutral-400)', marginBottom: 16 }}>
                粘贴一条视频的完整脚本。多条脚本可以用 <code style={{ background: 'var(--neutral-100)', padding: '1px 6px', borderRadius: 4, fontSize: 12 }}>===</code> 或 <code style={{ background: 'var(--neutral-100)', padding: '1px 6px', borderRadius: 4, fontSize: 12 }}>---</code> 分隔。
              </p>
              <textarea
                style={{
                  width: '100%', height: 180, padding: 14, border: '1px solid var(--neutral-200)',
                  borderRadius: 8, fontSize: 14, resize: 'none', outline: 'none',
                  fontFamily: 'inherit', boxSizing: 'border-box',
                }}
                placeholder={'粘贴视频脚本文案...\n\n如果有多条脚本，可以用 === 分隔：\n\n第一条脚本内容...\n===\n第二条脚本内容...'}
                value={pasteInput}
                onChange={e => setPasteInput(e.target.value)}
              />
              <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button className="btn btn-ghost" onClick={() => scriptFileRef.current?.click()}>
                    上传 .txt 文件
                  </button>
                  <input ref={scriptFileRef} type="file" accept=".txt,.text" multiple onChange={handleScriptFiles} style={{ display: 'none' }} />
                  <span style={{ fontSize: 12, color: 'var(--neutral-400)' }}>支持多选</span>
                </div>
                <button className="btn btn-primary" onClick={handleAddPaste} disabled={!pasteInput.trim()}>
                  添加脚本
                </button>
              </div>
            </div>
          </div>

          {scripts.length > 0 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setStep(2)}>
                下一步：上传复盘表
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Step 2: 上传复盘表 ── */}
      {step === 2 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button className="btn btn-ghost" onClick={() => setStep(1)}>← 返回编辑脚本</button>
            <span style={{ fontSize: 13, color: 'var(--neutral-500)' }}>已添加 {scripts.length} 条脚本</span>
          </div>

          <div className="card">
            <div className="card-body">
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>上传运营复盘表</h2>
              <p style={{ fontSize: 13, color: 'var(--neutral-400)', marginBottom: 16 }}>
                上传 Excel 复盘表，提取播放量、完播率、投放金额等运营数据。<strong>可选步骤</strong>，跳过也能基于脚本内容生成报告。
              </p>

              <div
                onClick={() => excelFileRef.current?.click()}
                style={{
                  border: '2px dashed var(--neutral-200)', borderRadius: 12, padding: '32px 24px',
                  textAlign: 'center', cursor: 'pointer', transition: 'border-color 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--brand)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--neutral-200)')}
              >
                <input ref={excelFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleExcelUpload} style={{ display: 'none' }} />
                {excelFileName ? (
                  <>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{excelFileName}</div>
                    <div style={{ fontSize: 12, color: 'var(--success)', marginTop: 4 }}>已解析 {excelData.length} 条数据</div>
                    <div style={{ fontSize: 12, color: 'var(--neutral-400)', marginTop: 8 }}>点击更换文件</div>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                    <div style={{ fontSize: 13, color: 'var(--neutral-500)' }}>点击上传 Excel 复盘表</div>
                    <div style={{ fontSize: 12, color: 'var(--neutral-400)', marginTop: 4 }}>支持 .xlsx / .xls / .csv（仅转置格式）</div>
                  </>
                )}
              </div>

              {excelData.length > 0 && (
                <div style={{ marginTop: 16, overflowX: 'auto' }}>
                  <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>解析预览</div>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--neutral-50)', color: 'var(--neutral-500)' }}>
                        {['日期', '视频主题', '类型', '播放量', '完播率', '5s完播率', '点赞', '投放金额'].map(h => (
                          <th key={h} style={{ padding: '6px 12px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {excelData.map((row, i) => (
                        <tr key={i} style={{ borderTop: '1px solid var(--neutral-100)' }}>
                          <td style={{ padding: '6px 12px', color: 'var(--neutral-500)' }}>{row.date || '—'}</td>
                          <td style={{ padding: '6px 12px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.videoTheme || '—'}</td>
                          <td style={{ padding: '6px 12px', color: 'var(--neutral-500)' }}>{row.videoType || '—'}</td>
                          <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.totalPlays ? row.totalPlays + '万' : '—'}</td>
                          <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.completionRate || '—'}</td>
                          <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.fiveSecRate || '—'}</td>
                          <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.likes || '—'}</td>
                          <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.adSpend || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
                <button
                  className="btn btn-ghost"
                  onClick={() => { setExcelData([]); setExcelFileName(''); handleGenerate(true); }}
                >
                  跳过，直接生成报告
                </button>
                {excelData.length > 0 && (
                  <button className="btn btn-primary" onClick={() => handleGenerate(false)}>
                    生成复盘报告
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Step 3: 复盘报告 ── */}
      {step === 3 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button className="btn btn-ghost" onClick={() => setStep(2)}>← 返回</button>
            <span style={{ fontSize: 13, color: 'var(--neutral-500)' }}>
              {scripts.length} 条脚本{excelData.length > 0 ? ' · 含运营数据' : ''}
            </span>
          </div>

          <div
            ref={reportRef}
            className="card"
            style={{ minHeight: 400, maxHeight: '70vh', overflowY: 'auto' }}
          >
            <div className="card-body">
              {reportLoading && !report && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--neutral-400)' }}>
                  <span style={{ display: 'inline-block', width: 16, height: 16, border: '2px solid var(--neutral-300)', borderTopColor: 'var(--brand)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                  操盘大师正在深度分析脚本内容...
                </div>
              )}
              {report && (
                <div style={{ fontSize: 14, lineHeight: 1.8, color: 'var(--neutral-800)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {report}
                </div>
              )}
              {reportLoading && report && (
                <span style={{ display: 'inline-block', width: 8, height: 18, background: 'var(--brand)', animation: 'pulse 1s infinite', marginLeft: 4, verticalAlign: 'middle' }} />
              )}
            </div>
          </div>

          {!reportLoading && report && (
            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              {savedId ? (
                <span style={{ fontSize: 14, color: 'var(--success)', padding: '8px 16px' }}>✓ 已保存</span>
              ) : (
                <button className="btn btn-ghost" onClick={handleSave} disabled={saving}>
                  {saving ? '保存中...' : '保存在线'}
                </button>
              )}
              <button className="btn btn-ghost" onClick={handleExport}>导出下载</button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  navigator.clipboard.writeText(report);
                }}
              >
                复制报告
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── 历史记录抽屉 ── */}
      {showHistory && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) setShowHistory(false); }}
        >
          <div style={{ width: 420, height: '100%', background: '#fff', display: 'flex', flexDirection: 'column', boxShadow: '-4px 0 20px rgba(0,0,0,0.12)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px 24px', borderBottom: '1px solid var(--neutral-100)' }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>历史报告</span>
              <button style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--neutral-400)' }} onClick={() => setShowHistory(false)}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {historyLoading ? (
                <div style={{ textAlign: 'center', color: 'var(--neutral-400)', padding: 32 }}>加载中...</div>
              ) : historyItems.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--neutral-400)', padding: 32 }}>暂无历史记录</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {historyItems.map(item => (
                    <div key={item.id} style={{ padding: '12px 14px', border: '1px solid var(--neutral-100)', borderRadius: 8 }}>
                      <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>{item.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--neutral-400)' }}>
                        {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {historyTotal > 20 && (
              <div style={{ padding: '12px 16px', borderTop: '1px solid var(--neutral-100)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <button className="btn btn-ghost" disabled={historyPage <= 1} onClick={() => loadHistory(historyPage - 1)}>上一页</button>
                <span style={{ fontSize: 13, color: 'var(--neutral-500)' }}>{historyPage} / {Math.ceil(historyTotal / 20)}</span>
                <button className="btn btn-ghost" disabled={historyPage >= Math.ceil(historyTotal / 20)} onClick={() => loadHistory(historyPage + 1)}>下一页</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
