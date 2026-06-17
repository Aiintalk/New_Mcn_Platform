// frontend/src/pages/operator/LivestreamReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import * as XLSX from 'xlsx';
import { parseFile, generateStream, saveReport, getOutputs } from '../../api/livestreamReview';
import type { OutputItem } from '../../api/livestreamReview';

/* ── Types ── */
interface ScriptEntry { id: string; title: string; content: string; source: string }

interface ExcelRow {
  liveTheme: string; liveDate: string; duration: string; peakViewers: string;
  avgViewers: string; totalUV: string; avgStayTime: string; likes: string;
  comments: string; followsGained: string; conversions: string;
  gmv: string; gpm: string; adSpend: string;
}

/* ── Excel 解析（前端，100% copy 旧逻辑）── */
function matchHeader(header: string, aliases: string[]): boolean {
  const h = header.trim();
  return aliases.some(a => a === h) || aliases.some(a => h.endsWith(a));
}

function parseTransposedExcel(wb: XLSX.WorkBook): ExcelRow[] {
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) return [];
  const raw: unknown[][] = XLSX.utils.sheet_to_json(ws, { header: 1 });
  if (raw.length < 2) return [];

  const knownLabels: [string[], keyof ExcelRow][] = [
    [['直播主题', '场次', '场次名称', '直播名称', '主题'], 'liveTheme'],
    [['直播日期', '日期', '开播日期', '开播时间'], 'liveDate'],
    [['直播时长', '时长', '开播时长'], 'duration'],
    [['峰值在线', '最高在线', '峰值人数', '在线峰值'], 'peakViewers'],
    [['平均在线', '在线均值', '人均在线'], 'avgViewers'],
    [['总UV', 'UV', '观看人数', '观看用户数', '观看人数(UV)'], 'totalUV'],
    [['平均停留时长', '停留时长', '人均停留', '平均观看时长'], 'avgStayTime'],
    [['点赞', '点赞数', '点赞数量'], 'likes'],
    [['评论', '评论数', '评论数量'], 'comments'],
    [['新增粉丝', '涨粉', '粉丝增量', '关注数', '新增关注'], 'followsGained'],
    [['成交单数', '订单数', '成交数', '订单量'], 'conversions'],
    [['GMV', '销售额', '成交金额', '直播间GMV'], 'gmv'],
    [['GPM', '千次曝光价值', '千次观看价值'], 'gpm'],
    [['投放金额', '消耗', '广告消耗', '投放消耗'], 'adSpend'],
  ];

  // 转置格式优先
  const rowMapping: { rowIdx: number; key: keyof ExcelRow }[] = [];
  for (let r = 0; r < raw.length; r++) {
    const cellVal = String((raw[r] as unknown[])?.[0] ?? '').trim();
    for (const [aliases, key] of knownLabels) {
      if (matchHeader(cellVal, aliases)) { rowMapping.push({ rowIdx: r, key }); break; }
    }
  }
  const distinctKeys = new Set(rowMapping.map(m => m.key));
  if (distinctKeys.size >= 3 && rowMapping.length >= 3) {
    const numCols = Math.max(...raw.map(r => (r as unknown[])?.length ?? 0));
    const results: ExcelRow[] = [];
    for (let c = 1; c < numCols; c++) {
      const entry: Partial<ExcelRow> = {};
      let hasData = false;
      for (const { rowIdx, key } of rowMapping) {
        const val = (raw[rowIdx] as unknown[])?.[c];
        if (val !== undefined && val !== null && val !== '') { entry[key] = String(val).trim(); hasData = true; }
      }
      if (hasData && (entry.liveTheme || entry.liveDate)) results.push(entry as ExcelRow);
    }
    if (results.length > 0) return results;
  }

  // 标准格式
  const headers = ((raw[0] as unknown[]) ?? []).map((h) => String(h ?? '').trim());
  const usedKeys = new Set<string>(); const usedCols = new Set<number>();
  const colMapping: { colIdx: number; key: keyof ExcelRow }[] = [];
  for (let c = 0; c < headers.length; c++) {
    for (const [aliases, key] of knownLabels) {
      if (usedKeys.has(key) || usedCols.has(c)) continue;
      if (aliases.some(a => a === headers[c])) { colMapping.push({ colIdx: c, key }); usedKeys.add(key); usedCols.add(c); break; }
    }
  }
  for (let c = 0; c < headers.length; c++) {
    if (usedCols.has(c)) continue;
    for (const [aliases, key] of knownLabels) {
      if (usedKeys.has(key)) continue;
      if (aliases.some(a => headers[c].endsWith(a))) { colMapping.push({ colIdx: c, key }); usedKeys.add(key); usedCols.add(c); break; }
    }
  }
  if (colMapping.length >= 2) {
    const results: ExcelRow[] = [];
    for (let r = 1; r < raw.length; r++) {
      const entry: Partial<ExcelRow> = {};
      let hasData = false;
      for (const { colIdx, key } of colMapping) {
        const val = (raw[r] as unknown[])?.[colIdx];
        if (val !== undefined && val !== null && val !== '') { entry[key] = String(val).trim(); hasData = true; }
      }
      if (hasData && (entry.liveTheme || entry.liveDate)) results.push(entry as ExcelRow);
    }
    return results;
  }
  return [];
}

function extractTitle(text: string): string {
  const first = text.split('\n').map(l => l.trim()).find(l => l.length > 0);
  if (!first) return '(无标题)';
  return first.length > 60 ? first.slice(0, 60) + '...' : first;
}

let nextId = 0;
function genId() { return `script-${++nextId}`; }

/* ── Markdown 渲染 ── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 style="font-size:15px;font-weight:700;margin:20px 0 8px">$1</h3>')
    .replace(/## (.+)/g, '<h2 style="font-size:17px;font-weight:700;margin:24px 0 10px">$1</h2>')
    .replace(/# (.+)/g, '<h1 style="font-size:19px;font-weight:800;margin:28px 0 12px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n\d+\. /g, m => '<br/>' + m.trim() + ' ')
    .replace(/\n/g, '<br/>');
  return <div style={{ fontSize: 14, lineHeight: 1.8, color: 'var(--gray-800)' }} dangerouslySetInnerHTML={{ __html: html }} />;
}

/* ── 颜色常量 ── */
const GREEN = '#10b981';
const GREEN_BG = '#f0fdf4';

/* ── 主组件 ── */
export default function LivestreamReviewPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [error, setError] = useState('');
  const [scripts, setScripts] = useState<ScriptEntry[]>([]);
  const [pasteInput, setPasteInput] = useState('');
  const [excelData, setExcelData] = useState<ExcelRow[]>([]);
  const [excelFileName, setExcelFileName] = useState('');
  const [report, setReport] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<OutputItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const scriptFileRef = useRef<HTMLInputElement>(null);
  const excelFileRef = useRef<HTMLInputElement>(null);
  const reportRef = useRef<HTMLDivElement>(null);

  /* ── Step 1 ── */
  function handleAddPaste() {
    const text = pasteInput.trim();
    if (!text) { setError('请先粘贴脚本内容'); return; }
    const sep = /\n(?:={3,}|-{3,})\n/;
    const segments = sep.test(text)
      ? text.split(sep).map(s => s.trim()).filter(s => s.length > 0)
      : [text];
    setScripts(prev => [...prev, ...segments.map(s => ({ id: genId(), title: extractTitle(s), content: s, source: 'paste' }))]);
    setPasteInput('');
    setError('');
  }

  async function parseFileToText(file: File): Promise<string> {
    const name = file.name.toLowerCase();
    if (name.endsWith('.txt') || name.endsWith('.md') || !name.includes('.')) return file.text();
    const result = await parseFile(file);
    return result.text || '';
  }

  async function handleScriptFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      try {
        const text = await parseFileToText(files[i]);
        if (text.trim()) setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: files[i].name }]);
      } catch { setError(`文件 ${files[i].name} 解析失败`); }
    }
    e.target.value = '';
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const files = e.dataTransfer.files;
    for (let i = 0; i < files.length; i++) {
      try {
        const text = await parseFileToText(files[i]);
        if (text.trim()) setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: files[i].name }]);
      } catch { setError(`文件 ${files[i].name} 解析失败`); }
    }
  }

  /* ── Step 2 ── */
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
        if (parsed.length === 0) { setError('未能解析Excel数据，请检查格式'); return; }
        setExcelData(parsed);
        setError('');
      } catch { setError('Excel解析失败'); }
    };
    reader.readAsArrayBuffer(file);
  }, []);

  /* ── Step 3：生成报告 ── */
  async function handleGenerate() {
    if (scripts.length === 0) { setError('请先上传脚本'); return; }
    setStep(3);
    setReportLoading(true);
    setReport('');
    setSavedId(null);

    const excelPayload = excelData.map(e => ({
      live_theme: e.liveTheme || '',
      live_date: e.liveDate || '',
      duration: e.duration || '',
      peak_viewers: e.peakViewers || '',
      avg_viewers: e.avgViewers || '',
      total_uv: e.totalUV || '',
      avg_stay_time: e.avgStayTime || '',
      likes: e.likes || '',
      comments: e.comments || '',
      follows_gained: e.followsGained || '',
      conversions: e.conversions || '',
      gmv: e.gmv || '',
      gpm: e.gpm || '',
      ad_spend: e.adSpend || '',
    }));

    try {
      const resp = await generateStream({
        scripts: scripts.map(s => ({ title: s.title, content: s.content })),
        excel_data: excelPayload,
      });
      if (!resp.ok) throw new Error(`生成失败: ${resp.status}`);

      const tid = resp.headers.get('x-task-id');
      if (tid) setTaskId(Number(tid));

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
    if (!report.trim() || !taskId) return;
    setSaving(true);
    try {
      const hasExcel = excelData.length > 0;
      const result = await saveReport({ task_id: taskId, report, script_count: scripts.length, has_excel: hasExcel });
      setSavedId(result.output_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
    setSaving(false);
  }

  async function handleExport() {
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `直播复盘报告_${scripts.length}场.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function loadHistory() {
    try {
      const data = await getOutputs();
      setHistory(data.items);
      setShowHistory(true);
    } catch { setError('加载历史失败'); }
  }

  const STEPS = [
    { n: 1, label: '上传脚本' },
    { n: 2, label: '上传直播数据' },
    { n: 3, label: '复盘报告' },
  ];

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '32px 24px' }}>

      {/* Header */}
      <div style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--gray-900)', margin: 0 }}>直播间脚本复盘助手</h1>
          <p style={{ color: 'var(--gray-500)', marginTop: 4, fontSize: 13 }}>上传脚本 → 上传直播数据 → AI 复盘报告</p>
        </div>
        <button
          onClick={loadHistory}
          style={{ fontSize: 13, color: GREEN, background: GREEN_BG, border: 'none', cursor: 'pointer', padding: '6px 12px', borderRadius: 8 }}
        >
          历史报告
        </button>
      </div>

      {/* Step Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 32, flexWrap: 'wrap' }}>
        {STEPS.map(({ n, label }) => (
          <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 13, fontWeight: 600, flexShrink: 0,
              background: step >= n ? GREEN : 'var(--gray-200)',
              color: step >= n ? 'white' : 'var(--gray-500)',
            }}>
              {step > n ? '✓' : n}
            </div>
            <span style={{ fontSize: 13, fontWeight: step >= n ? 600 : 400, color: step >= n ? 'var(--gray-900)' : 'var(--gray-400)' }}>{label}</span>
            {n < 3 && <div style={{ width: 40, height: 2, background: step > n ? GREEN : 'var(--gray-200)' }} />}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--danger-bg)', border: '1px solid #fca5a5', borderRadius: 10, color: 'var(--danger)', fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {error}
          <button onClick={() => setError('')} style={{ color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', marginLeft: 16 }}>✕</button>
        </div>
      )}

      {/* ── Step 1 ── */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: 'white', borderRadius: 14, border: '1px solid var(--border)', padding: 24, boxShadow: 'var(--shadow-sm)' }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 4px', color: 'var(--gray-900)' }}>上传直播脚本</h2>
            <p style={{ color: 'var(--gray-400)', fontSize: 13, margin: '0 0 16px' }}>每个文件 = 一场直播的脚本，支持批量上传</p>

            <div
              onClick={() => scriptFileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              style={{
                border: `2px dashed ${dragOver ? GREEN : 'var(--border)'}`,
                borderRadius: 14, padding: '40px 24px', textAlign: 'center', cursor: 'pointer',
                background: dragOver ? GREEN_BG : 'transparent',
                transition: 'border-color 0.15s, background 0.15s',
              }}
            >
              <input ref={scriptFileRef} type="file" accept=".txt,.md,.docx,.pages" multiple onChange={handleScriptFiles} style={{ display: 'none' }} />
              <div style={{ fontSize: 36, marginBottom: 12 }}>🎙️</div>
              <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--gray-700)', margin: '0 0 4px' }}>点击选择文件 或 拖拽文件到这里</p>
              <p style={{ fontSize: 12, color: 'var(--gray-400)', margin: 0 }}>支持 .txt / .md / .docx / .pages，可多选</p>
            </div>

            <details style={{ marginTop: 16 }}>
              <summary style={{ fontSize: 13, color: GREEN, cursor: 'pointer' }}>或者手动粘贴文案</summary>
              <div style={{ marginTop: 12 }}>
                <textarea
                  style={{ width: '100%', height: 140, padding: 16, border: '1px solid var(--border)', borderRadius: 10, fontSize: 13, resize: 'none', outline: 'none', boxSizing: 'border-box' }}
                  placeholder={'粘贴直播间脚本文案...\n多场脚本用 === 分隔'}
                  value={pasteInput}
                  onChange={e => setPasteInput(e.target.value)}
                />
                <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    onClick={handleAddPaste}
                    disabled={!pasteInput.trim()}
                    style={{ padding: '8px 20px', background: GREEN, color: 'white', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: pasteInput.trim() ? 'pointer' : 'not-allowed', opacity: pasteInput.trim() ? 1 : 0.5 }}
                  >添加脚本</button>
                </div>
              </div>
            </details>
          </div>

          {scripts.length > 0 && (
            <div style={{ background: 'white', borderRadius: 14, border: '1px solid var(--border)', padding: 16, boxShadow: 'var(--shadow-sm)' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 12 }}>已添加 {scripts.length} 场脚本</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {scripts.map((s, i) => (
                  <div key={s.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 12px', background: 'var(--bg-muted)', borderRadius: 10 }}>
                    <span style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2, flexShrink: 0, width: 20 }}>{i + 1}.</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-900)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>
                        {s.source === 'paste' ? '手动粘贴' : s.source} · {s.content.length} 字
                      </div>
                    </div>
                    <button onClick={() => setScripts(prev => prev.filter(x => x.id !== s.id))} style={{ color: 'var(--gray-300)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, flexShrink: 0 }}>✕</button>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setStep(2)}
                  style={{ padding: '10px 24px', background: GREEN, color: 'white', border: 'none', borderRadius: 10, fontWeight: 600, fontSize: 14, cursor: 'pointer' }}
                >下一步：上传直播数据 →</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 2 ── */}
      {step === 2 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button onClick={() => setStep(1)} style={{ fontSize: 13, color: GREEN, background: 'none', border: 'none', cursor: 'pointer' }}>← 返回编辑脚本</button>
            <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>已添加 {scripts.length} 场脚本</span>
          </div>

          <div style={{ background: 'white', borderRadius: 14, border: '1px solid var(--border)', padding: 24, boxShadow: 'var(--shadow-sm)' }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 4px', color: 'var(--gray-900)' }}>上传直播数据</h2>
            <p style={{ color: 'var(--gray-400)', fontSize: 13, margin: '0 0 16px' }}>
              上传直播后台导出的数据 Excel（GMV、在线、停留、互动等）。
              <strong style={{ color: 'var(--gray-600)' }}> 可选</strong>，跳过也能基于脚本生成复盘报告。
            </p>

            <div
              onClick={() => excelFileRef.current?.click()}
              style={{ border: '2px dashed var(--border)', borderRadius: 14, padding: 32, textAlign: 'center', cursor: 'pointer' }}
            >
              <input ref={excelFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleExcelUpload} style={{ display: 'none' }} />
              {excelFileName ? (
                <div>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-900)' }}>{excelFileName}</div>
                  <div style={{ fontSize: 12, color: GREEN, marginTop: 4 }}>已解析 {excelData.length} 场数据</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 8 }}>点击更换文件</div>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                  <div style={{ fontSize: 13, color: 'var(--gray-500)' }}>点击上传直播数据 Excel</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>支持 .xlsx / .xls / .csv</div>
                </div>
              )}
            </div>

            {excelData.length > 0 && (
              <div style={{ marginTop: 16, overflowX: 'auto' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 8 }}>解析预览</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-muted)', color: 'var(--gray-500)' }}>
                      {['场次', 'GMV', 'GPM', '峰值在线', '平均停留', '成交单数', '点赞', '涨粉'].map(h => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: h === '场次' ? 'left' : 'right', fontWeight: 500 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {excelData.map((row, i) => (
                      <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: '6px 12px', color: 'var(--gray-900)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.liveTheme || row.liveDate || '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right', fontWeight: 500 }}>{row.gmv ? row.gmv + '元' : '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.gpm || '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.peakViewers || '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.avgStayTime ? row.avgStayTime + '秒' : '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.conversions || '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.likes || '—'}</td>
                        <td style={{ padding: '6px 12px', textAlign: 'right' }}>{row.followsGained || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ marginTop: 20, display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button
                onClick={() => { setExcelData([]); setExcelFileName(''); handleGenerate(); }}
                style={{ padding: '10px 20px', background: 'none', border: '1px solid var(--border)', borderRadius: 10, fontSize: 13, color: 'var(--gray-600)', cursor: 'pointer' }}
              >跳过，直接生成报告</button>
              <button
                onClick={handleGenerate}
                style={{ padding: '10px 24px', background: GREEN, color: 'white', border: 'none', borderRadius: 10, fontWeight: 600, fontSize: 14, cursor: 'pointer' }}
              >生成复盘报告 →</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Step 3 ── */}
      {step === 3 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button onClick={() => { setStep(2); setReport(''); }} style={{ fontSize: 13, color: GREEN, background: 'none', border: 'none', cursor: 'pointer' }}>← 返回</button>
            {!reportLoading && report && (
              <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
                {savedId ? (
                  <span style={{ fontSize: 13, color: GREEN, background: GREEN_BG, padding: '6px 12px', borderRadius: 8 }}>✓ 已保存到产出中心</span>
                ) : (
                  <button onClick={handleSave} disabled={saving || !taskId} style={{ padding: '8px 16px', background: GREEN, color: 'white', border: 'none', borderRadius: 8, fontSize: 13, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>
                    {saving ? '保存中...' : '保存到产出中心'}
                  </button>
                )}
                <button
                  onClick={() => navigator.clipboard.writeText(report)}
                  style={{ padding: '8px 16px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, fontSize: 13, cursor: 'pointer', color: 'var(--gray-600)' }}
                >复制报告</button>
                <button
                  onClick={handleExport}
                  style={{ padding: '8px 16px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, fontSize: 13, cursor: 'pointer', color: 'var(--gray-600)' }}
                >导出 .md</button>
              </div>
            )}
          </div>

          <div style={{ background: 'white', borderRadius: 14, border: '1px solid var(--border)', padding: 24, boxShadow: 'var(--shadow-sm)', minHeight: 400 }}>
            {reportLoading && !report && (
              <div style={{ textAlign: 'center', padding: '96px 0', color: 'var(--gray-400)', fontSize: 14 }}>
                <div style={{ fontSize: 32, marginBottom: 16 }}>🤔</div>
                AI 正在分析脚本，请稍候...
              </div>
            )}
            <div ref={reportRef} style={{ maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
              {report && <SimpleMarkdown text={report} />}
              {reportLoading && report && (
                <span style={{ display: 'inline-block', width: 8, height: 16, background: GREEN, borderRadius: 2, animation: 'blink 0.8s step-end infinite', verticalAlign: 'middle' }} />
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 历史报告弹层 ── */}
      {showHistory && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)', padding: 16 }}>
          <div style={{ background: 'white', borderRadius: 16, width: '100%', maxWidth: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-lg)' }}>
            <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>历史复盘报告</span>
              <button onClick={() => setShowHistory(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', fontSize: 20 }}>✕</button>
            </div>
            <div style={{ overflowY: 'auto', padding: '12px 24px', flex: 1 }}>
              {history.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--gray-400)', fontSize: 13 }}>暂无历史报告</div>
              ) : (
                history.map(item => (
                  <div key={item.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-900)' }}>{item.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>{item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }`}</style>
    </div>
  );
}
