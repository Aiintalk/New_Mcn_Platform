// frontend/src/pages/operator/QianchuanReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import * as XLSX from 'xlsx';
import type { ScriptEntry, ExcelRow, OutputItem } from '../../types/qianchuanReview';
import { parseFile, generateReport, saveReport, getOutputs } from '../../api/qianchuanReview';

/* ── Markdown 渲染 ── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 style="font-size:14px;font-weight:600;margin:16px 0 8px">$1</h3>')
    .replace(/## (.+)/g, '<h2 style="font-size:16px;font-weight:600;margin:20px 0 8px">$1</h2>')
    .replace(/# (.+)/g, '<h1 style="font-size:18px;font-weight:700;margin:24px 0 10px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--gray-800)' }} dangerouslySetInnerHTML={{ __html: html }} />;
}

/* ── Excel 解析（前端本地，与旧代码等价） ── */
function matchHeader(header: string, aliases: string[]): boolean {
  const h = header.trim();
  if (aliases.some(a => a === h)) return true;
  if (aliases.some(a => h.endsWith(a))) return true;
  return false;
}

function parseExcelWorkbook(wb: XLSX.WorkBook): ExcelRow[] {
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) return [];
  const raw: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 });
  if (raw.length < 2) return [];

  const knownLabels: [string[], keyof ExcelRow][] = [
    [['素材名称', '视频主题', '素材标题', '视频名称'], 'video_theme'],
    [['整体消耗', '消耗', '花费', '总消耗'], 'spend'],
    [['展示次数', '展示', '曝光', '曝光次数'], 'impressions'],
    [['点击率', 'CTR', 'ctr', '整体点击率'], 'ctr'],
    [['3s完播率', '3秒完播率', '3s完播', '3秒播放率'], 'three_sec_rate'],
    [['转化数', '成交数', '订单数'], 'conversions'],
    [['转化成本', '成交成本', '单次转化成本'], 'cost_per_conversion'],
    [['ROI', 'roi', '投产比', '投产', '整体支付ROI', '支付ROI'], 'roi'],
    [['千次展示成本', 'CPM', 'cpm', '千展成本', '千次展现费用', '整体千次展现费用'], 'cpm'],
    [['投放时段', '时段', '投放时间'], 'time_range'],
  ];

  // 尝试转置格式
  const rowMapping: { rowIdx: number; key: keyof ExcelRow }[] = [];
  for (let r = 0; r < raw.length; r++) {
    const cellVal = String(raw[r]?.[0] ?? '').trim();
    for (const [aliases, key] of knownLabels) {
      if (matchHeader(cellVal, aliases)) { rowMapping.push({ rowIdx: r, key }); break; }
    }
  }
  const distinctKeys = new Set(rowMapping.map(m => m.key));
  if (distinctKeys.size >= 3 && rowMapping.length >= 3) {
    const numCols = Math.max(...raw.map(r => r?.length ?? 0));
    const results: ExcelRow[] = [];
    for (let c = 1; c < numCols; c++) {
      const entry: any = {};
      let hasData = false;
      for (const { rowIdx, key } of rowMapping) {
        const val = raw[rowIdx]?.[c];
        if (val !== undefined && val !== null && val !== '') { entry[key] = String(val).trim(); hasData = true; }
      }
      if (hasData && entry.video_theme) results.push(entry as ExcelRow);
    }
    if (results.length > 0) return results;
  }

  // 标准格式
  const headers = raw[0]?.map((h: any) => String(h ?? '').trim()) || [];
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
      const entry: any = {}; let hasData = false;
      for (const { colIdx, key } of colMapping) {
        const val = raw[r]?.[colIdx];
        if (val !== undefined && val !== null && val !== '') { entry[key] = String(val).trim(); hasData = true; }
      }
      if (hasData && entry.video_theme) results.push(entry as ExcelRow);
    }
    return results;
  }
  return [];
}

function extractTitle(text: string): string {
  const firstLine = text.split('\n').map(l => l.trim()).find(l => l.length > 0);
  if (!firstLine) return '(无标题)';
  return firstLine.length > 60 ? firstLine.slice(0, 60) + '...' : firstLine;
}

let _nextId = 0;
function genId() { return `s-${++_nextId}`; }

/* ── 主组件 ── */
export default function QianchuanReviewPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [error, setError] = useState('');

  // Step 1
  const [scripts, setScripts] = useState<ScriptEntry[]>([]);
  const [pasteInput, setPasteInput] = useState('');
  const scriptFileRef = useRef<HTMLInputElement>(null);

  // Step 2
  const [excelData, setExcelData] = useState<ExcelRow[]>([]);
  const [excelFileName, setExcelFileName] = useState('');
  const excelFileRef = useRef<HTMLInputElement>(null);

  // Step 3
  const [report, setReport] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOutputId, setSavedOutputId] = useState<number | null>(null);
  const reportRef = useRef<HTMLDivElement>(null);

  // 历史
  const [history, setHistory] = useState<OutputItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  /* ── Step 1 ── */
  async function handleParseFile(file: File): Promise<string> {
    const name = file.name.toLowerCase();
    if (name.endsWith('.txt') || name.endsWith('.md')) return file.text();
    const result = await parseFile(file);
    return result.text;
  }

  async function handleScriptFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const text = await handleParseFile(file);
        if (text.trim()) setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: file.name }]);
      } catch { setError(`文件 ${file.name} 解析失败`); }
    }
    e.target.value = '';
  }

  function handleAddPaste() {
    const text = pasteInput.trim();
    if (!text) { setError('请先粘贴脚本内容'); return; }
    const separator = /\n(?:={3,}|-{3,})\n/;
    const segments = separator.test(text)
      ? text.split(separator).map(s => s.trim()).filter(s => s.length > 0)
      : [text];
    setScripts(prev => [...prev, ...segments.map(s => ({ id: genId(), title: extractTitle(s), content: s, source: 'paste' }))]);
    setPasteInput('');
    setError('');
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
        const parsed = parseExcelWorkbook(wb);
        if (parsed.length === 0) { setError('未能解析Excel数据，请检查格式'); return; }
        setExcelData(parsed);
        setError('');
      } catch { setError('Excel解析失败'); }
    };
    reader.readAsArrayBuffer(file);
  }, []);

  /* ── Step 3: 生成报告 ── */
  async function handleGenerate(withExcel: boolean) {
    if (scripts.length === 0) { setError('请先上传脚本'); return; }
    if (scripts.length > 30) { setError('脚本条数超过上限（30条），请分批复盘'); return; }

    setStep(3);
    setReportLoading(true);
    setReport('');
    setTaskId(null);
    setSavedOutputId(null);

    try {
      const resp = await generateReport({
        scripts: scripts.map(s => ({ title: s.title, content: s.content })),
        excel_data: withExcel ? excelData : [],
      });
      if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);

      const tid = resp.headers.get('X-Task-Id');
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
    if (!report || taskId === null) return;
    setSaving(true);
    try {
      const result = await saveReport({
        task_id: taskId,
        report,
        script_count: scripts.length,
        has_excel: excelData.length > 0,
      });
      setSavedOutputId(result.output_id);
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
    a.href = url;
    a.download = `千川脚本复盘_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const data = await getOutputs(1, 10);
      setHistory(data.items);
    } catch { /* 历史加载失败不影响主流程 */ }
    finally { setHistoryLoading(false); }
  }

  const STEPS = [
    { n: 1, label: '上传脚本' },
    { n: 2, label: '上传投放数据' },
    { n: 3, label: '复盘报告' },
  ];

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">千川脚本复盘助手</h1>
        <p className="page-desc">上传脚本 → 上传投放数据 → AI复盘报告</p>
      </div>

      {/* Step Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 24 }}>
        {STEPS.map(({ n, label }) => {
          const isActive = step === n;
          const isDone = step > n;
          return (
            <div key={n} style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%',
                  background: (isActive || isDone) ? 'var(--brand)' : 'var(--gray-200)',
                  color: (isActive || isDone) ? '#fff' : 'var(--gray-400)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 13, fontWeight: 600,
                }}>
                  {isDone ? '✓' : n}
                </div>
                <span style={{ fontSize: 12, color: isActive ? 'var(--brand)' : isDone ? 'var(--gray-500)' : 'var(--gray-400)', whiteSpace: 'nowrap' }}>{label}</span>
              </div>
              {n < 3 && <div style={{ width: 48, height: 2, background: isDone ? 'var(--brand)' : 'var(--gray-200)', margin: '0 4px', marginBottom: 18 }} />}
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', borderRadius: 'var(--radius-md)', padding: '10px 14px', fontSize: 13, color: 'var(--danger)', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {error}
          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => setError('')}>✕</button>
        </div>
      )}

      {/* Step 1 */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-body">
              <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--gray-800)', marginBottom: 4 }}>上传千川脚本</div>
              <div style={{ fontSize: 13, color: 'var(--gray-400)', marginBottom: 16 }}>每个文件 = 一条脚本，支持批量上传</div>
              <div
                style={{
                  border: '2px dashed var(--brand-border)', borderRadius: 'var(--radius-md)',
                  padding: '40px 0', textAlign: 'center', cursor: 'pointer',
                  background: 'var(--brand-light)',
                }}
                onClick={() => scriptFileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={async e => {
                  e.preventDefault();
                  const files = e.dataTransfer.files;
                  for (let i = 0; i < files.length; i++) {
                    try {
                      const text = await handleParseFile(files[i]);
                      if (text.trim()) setScripts(prev => [...prev, { id: genId(), title: extractTitle(text), content: text.trim(), source: files[i].name }]);
                    } catch { setError(`文件 ${files[i].name} 解析失败`); }
                  }
                }}
              >
                <input ref={scriptFileRef} type="file" accept=".txt,.md,.docx,.pages" multiple onChange={handleScriptFiles} style={{ display: 'none' }} />
                <div style={{ fontSize: 32, marginBottom: 10 }}>📄</div>
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--gray-700)' }}>点击选择文件 或 拖拽到这里</div>
                <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>支持 .txt / .md / .docx / .pages，可多选</div>
              </div>
              <details style={{ marginTop: 12 }}>
                <summary style={{ fontSize: 13, color: 'var(--brand)', cursor: 'pointer' }}>或者手动粘贴文案</summary>
                <div style={{ marginTop: 10 }}>
                  <textarea
                    style={{ width: '100%', height: 120, padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 13, resize: 'none', outline: 'none', boxSizing: 'border-box', fontFamily: 'var(--font-sans)' }}
                    placeholder={"粘贴千川脚本文案...\n多条脚本用 === 分隔"}
                    value={pasteInput}
                    onChange={e => setPasteInput(e.target.value)}
                  />
                  <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
                    <button className="btn btn-primary btn-sm" onClick={handleAddPaste} disabled={!pasteInput.trim()}>添加脚本</button>
                  </div>
                </div>
              </details>
            </div>
          </div>

          {scripts.length > 0 && (
            <div className="card">
              <div className="card-body">
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 10 }}>已添加 {scripts.length} 条脚本</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {scripts.map((s, i) => (
                    <div key={s.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px', background: 'var(--gray-50)', borderRadius: 'var(--radius-sm)' }}>
                      <span style={{ fontSize: 12, color: 'var(--gray-400)', minWidth: 20, flexShrink: 0 }}>{i + 1}.</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-800)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>{s.source === 'paste' ? '手动粘贴' : s.source} · {s.content.length} 字</div>
                      </div>
                      <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)', flexShrink: 0 }} onClick={() => setScripts(prev => prev.filter(x => x.id !== s.id))}>✕</button>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
                  <button className="btn btn-primary" onClick={() => setStep(2)}>下一步：上传投放数据</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)}>← 返回</button>
            <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>已添加 {scripts.length} 条脚本</span>
          </div>
          <div className="card">
            <div className="card-body">
              <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--gray-800)', marginBottom: 4 }}>上传千川投放数据</div>
              <div style={{ fontSize: 13, color: 'var(--gray-400)', marginBottom: 16 }}>可选步骤，跳过也能基于脚本内容生成复盘报告</div>
              <div
                onClick={() => excelFileRef.current?.click()}
                style={{
                  border: '2px dashed var(--brand-border)', borderRadius: 'var(--radius-md)',
                  padding: '32px 0', textAlign: 'center', cursor: 'pointer',
                  background: 'var(--brand-light)',
                }}
              >
                <input ref={excelFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleExcelUpload} style={{ display: 'none' }} />
                {excelFileName ? (
                  <div>
                    <div style={{ fontSize: 28, marginBottom: 6 }}>📊</div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-700)' }}>{excelFileName}</div>
                    <div style={{ fontSize: 12, color: 'var(--success)', marginTop: 4 }}>已解析 {excelData.length} 条数据</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>点击更换文件</div>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 28, marginBottom: 6 }}>📄</div>
                    <div style={{ fontSize: 13, color: 'var(--gray-500)' }}>点击上传千川投放数据 Excel</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>支持 .xlsx / .xls / .csv</div>
                  </div>
                )}
              </div>
              {excelData.length > 0 && (
                <div style={{ marginTop: 16, overflowX: 'auto' }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-700)', marginBottom: 8 }}>解析预览</div>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--gray-50)', color: 'var(--gray-500)' }}>
                        <th style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 500 }}>素材名称</th>
                        <th style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 500 }}>消耗</th>
                        <th style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 500 }}>ROI</th>
                        <th style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 500 }}>转化数</th>
                        <th style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 500 }}>3s完播率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {excelData.slice(0, 10).map((row, i) => (
                        <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: '6px 10px', color: 'var(--gray-800)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.video_theme || '—'}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--gray-600)' }}>{row.spend ? row.spend + '元' : '—'}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--gray-600)' }}>{row.roi || '—'}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--gray-600)' }}>{row.conversions || '—'}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: 'var(--gray-600)' }}>{row.three_sec_rate || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  className="btn btn-ghost"
                  onClick={() => { setExcelData([]); setExcelFileName(''); handleGenerate(false); }}
                >
                  跳过，直接生成报告
                </button>
                {excelData.length > 0 && (
                  <button className="btn btn-primary" onClick={() => handleGenerate(true)}>生成复盘报告</button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setStep(2)}>← 返回</button>
            <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>{scripts.length} 条素材{excelData.length > 0 ? ' · 含投放数据' : ''}</span>
          </div>
          <div
            ref={reportRef}
            className="card"
            style={{ minHeight: 400, maxHeight: '70vh', overflowY: 'auto' }}
          >
            <div className="card-body">
              {reportLoading && !report && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--gray-400)', fontSize: 14 }}>
                  <svg style={{ width: 20, height: 20, animation: 'spin 1s linear infinite' }} viewBox="0 0 24 24">
                    <circle style={{ opacity: 0.25 }} cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path style={{ opacity: 0.75 }} fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  千川复盘专家正在深度分析素材数据...
                </div>
              )}
              {report && <SimpleMarkdown text={report} />}
              {reportLoading && report && (
                <span style={{ display: 'inline-block', width: 8, height: 16, background: 'var(--brand)', animation: 'pulse 1s infinite', marginLeft: 4 }} />
              )}
            </div>
          </div>

          {!reportLoading && report && (
            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              {savedOutputId ? (
                <span style={{ padding: '6px 16px', background: 'var(--success-bg)', border: '1px solid var(--success)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--success)' }}>已保存</span>
              ) : (
                <button
                  className="btn btn-ghost"
                  onClick={handleSave}
                  disabled={saving || taskId === null}
                >
                  {saving ? '保存中...' : '保存到产出中心'}
                </button>
              )}
              <button className="btn btn-ghost" onClick={handleExport}>导出下载</button>
              <button className="btn btn-ghost" onClick={() => navigator.clipboard.writeText(report)}>复制报告</button>
            </div>
          )}
        </div>
      )}

      {/* 底部历史 */}
      <div style={{ marginTop: 48, paddingTop: 24, borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-700)' }}>最近复盘记录</span>
          <button className="btn btn-ghost btn-sm" onClick={loadHistory} disabled={historyLoading}>
            {historyLoading ? '加载中...' : '刷新'}
          </button>
        </div>
        {history.length === 0 && !historyLoading && (
          <p style={{ fontSize: 13, color: 'var(--gray-400)' }}>暂无记录，点击刷新加载</p>
        )}
        {history.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {history.map(item => (
              <div key={item.id} className="card" style={{ cursor: 'default' }}>
                <div className="card-body" style={{ padding: '10px 14px' }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-800)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 3 }}>
                    {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
                    {item.word_count ? ` · ${item.word_count} 字` : ''}
                  </div>
                  {item.preview && <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.preview}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } } @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0; } }`}</style>
    </div>
  );
}
