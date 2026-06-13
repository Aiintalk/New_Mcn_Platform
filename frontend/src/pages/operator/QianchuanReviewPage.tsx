// frontend/src/pages/operator/QianchuanReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import * as XLSX from 'xlsx';
import type { ScriptEntry, ExcelRow, OutputItem } from '../../types/qianchuanReview';
import { parseFile, generateReport, saveReport, getOutputs } from '../../api/qianchuanReview';

/* ── Markdown 渲染 ── */
function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 class="text-base font-bold mt-4 mb-2">$1</h3>')
    .replace(/## (.+)/g, '<h2 class="text-lg font-bold mt-5 mb-2">$1</h2>')
    .replace(/# (.+)/g, '<h1 class="text-xl font-bold mt-6 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
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
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">千川脚本复盘助手</h1>
        <p className="text-gray-500 mt-1">上传脚本 → 上传投放数据 → AI复盘报告</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map(({ n, label }) => (
          <div key={n} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium shrink-0 ${
              step >= n ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500'
            }`}>
              {step > n ? '✓' : n}
            </div>
            <span className={`text-sm ${step >= n ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>{label}</span>
            {n < 3 && <div className={`w-10 h-0.5 ${step > n ? 'bg-blue-500' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex justify-between">
          {error}
          <button onClick={() => setError('')} className="ml-4 text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      {/* Step 1 */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-1">上传千川脚本</h2>
            <p className="text-gray-400 text-sm mb-4">每个文件 = 一条脚本，支持批量上传</p>
            <div
              className="border-2 border-dashed rounded-xl p-10 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
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
              <input ref={scriptFileRef} type="file" accept=".txt,.md,.docx,.pages" multiple onChange={handleScriptFiles} className="hidden" />
              <div className="text-4xl mb-3">📄</div>
              <p className="text-sm font-medium text-gray-700">点击选择文件 或 拖拽到这里</p>
              <p className="text-xs text-gray-400 mt-1">支持 .txt / .md / .docx / .pages，可多选</p>
            </div>
            <details className="mt-4">
              <summary className="text-sm text-blue-500 cursor-pointer hover:text-blue-600">或者手动粘贴文案</summary>
              <div className="mt-3">
                <textarea
                  className="w-full h-36 p-4 border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder={"粘贴千川脚本文案...\n多条脚本用 === 分隔"}
                  value={pasteInput}
                  onChange={e => setPasteInput(e.target.value)}
                />
                <div className="mt-2 flex justify-end">
                  <button onClick={handleAddPaste} disabled={!pasteInput.trim()} className="px-5 py-2 bg-blue-500 text-white rounded-lg text-sm disabled:opacity-50">添加脚本</button>
                </div>
              </div>
            </details>
          </div>

          {scripts.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="text-sm font-medium text-gray-700 mb-3">已添加 {scripts.length} 条脚本</div>
              <div className="space-y-2">
                {scripts.map((s, i) => (
                  <div key={s.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                    <span className="text-xs text-gray-400 w-5 shrink-0">{i + 1}.</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">{s.title}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{s.source === 'paste' ? '手动粘贴' : s.source} · {s.content.length} 字</div>
                    </div>
                    <button onClick={() => setScripts(prev => prev.filter(x => x.id !== s.id))} className="text-gray-300 hover:text-red-400 text-sm">✕</button>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex justify-end">
                <button onClick={() => setStep(2)} className="px-6 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors">
                  下一步：上传投放数据
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <button onClick={() => setStep(1)} className="text-sm text-blue-500 hover:text-blue-600">← 返回</button>
            <span className="text-sm text-gray-500">已添加 {scripts.length} 条脚本</span>
          </div>
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-1">上传千川投放数据</h2>
            <p className="text-gray-400 text-sm mb-4">可选步骤，跳过也能基于脚本内容生成复盘报告</p>
            <div onClick={() => excelFileRef.current?.click()} className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/30 transition-colors">
              <input ref={excelFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleExcelUpload} className="hidden" />
              {excelFileName ? (
                <div>
                  <div className="text-3xl mb-2">📊</div>
                  <div className="text-sm font-medium">{excelFileName}</div>
                  <div className="text-xs text-green-600 mt-1">已解析 {excelData.length} 条数据</div>
                  <div className="text-xs text-gray-400 mt-1">点击更换文件</div>
                </div>
              ) : (
                <div>
                  <div className="text-3xl mb-2">📄</div>
                  <div className="text-sm text-gray-500">点击上传千川投放数据 Excel</div>
                  <div className="text-xs text-gray-400 mt-1">支持 .xlsx / .xls / .csv</div>
                </div>
              )}
            </div>
            {excelData.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <div className="text-sm font-medium text-gray-700 mb-2">解析预览</div>
                <table className="text-xs w-full">
                  <thead>
                    <tr className="bg-gray-50 text-gray-500">
                      <th className="px-3 py-2 text-left">素材名称</th>
                      <th className="px-3 py-2 text-right">消耗</th>
                      <th className="px-3 py-2 text-right">ROI</th>
                      <th className="px-3 py-2 text-right">转化数</th>
                      <th className="px-3 py-2 text-right">3s完播率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {excelData.slice(0, 10).map((row, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-3 py-1.5 text-gray-900 max-w-[200px] truncate">{row.video_theme || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.spend ? row.spend + '元' : '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.roi || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.conversions || '—'}</td>
                        <td className="px-3 py-1.5 text-right">{row.three_sec_rate || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => { setExcelData([]); setExcelFileName(''); handleGenerate(false); }}
                className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              >
                跳过，直接生成报告
              </button>
              {excelData.length > 0 && (
                <button onClick={() => handleGenerate(true)} className="px-6 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors">
                  生成复盘报告
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <button onClick={() => setStep(2)} className="text-sm text-blue-500 hover:text-blue-600">← 返回</button>
            <span className="text-sm text-gray-500">{scripts.length} 条素材{excelData.length > 0 ? ' · 含投放数据' : ''}</span>
          </div>
          <div
            ref={reportRef}
            className="bg-white rounded-xl shadow-sm border p-6 min-h-[400px] max-h-[70vh] overflow-y-auto"
          >
            {reportLoading && !report && (
              <div className="flex items-center gap-2 text-gray-400">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                千川复盘专家正在深度分析素材数据...
              </div>
            )}
            {report && (
              <div className="prose prose-sm max-w-none text-gray-800 leading-relaxed">
                <SimpleMarkdown text={report} />
              </div>
            )}
            {reportLoading && report && <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-1" />}
          </div>

          {!reportLoading && report && (
            <div className="mt-4 flex justify-end gap-3">
              {savedOutputId ? (
                <span className="px-5 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">已保存</span>
              ) : (
                <button
                  onClick={handleSave}
                  disabled={saving || taskId === null}
                  className="px-5 py-2 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50 transition-colors"
                >
                  {saving ? '保存中...' : '保存到产出中心'}
                </button>
              )}
              <button onClick={handleExport} className="px-5 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors">导出下载</button>
              <button onClick={() => navigator.clipboard.writeText(report)} className="px-5 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors">复制报告</button>
            </div>
          )}
        </div>
      )}

      {/* 底部历史 */}
      <div className="mt-12 border-t pt-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-700">最近复盘记录</h3>
          <button onClick={loadHistory} disabled={historyLoading} className="text-sm text-blue-500 hover:text-blue-600 disabled:opacity-50">
            {historyLoading ? '加载中...' : '刷新'}
          </button>
        </div>
        {history.length === 0 && !historyLoading && (
          <p className="text-sm text-gray-400">暂无记录，点击刷新加载</p>
        )}
        {history.length > 0 && (
          <div className="space-y-2">
            {history.map(item => (
              <div key={item.id} className="flex items-start justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">{item.title}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
                    {item.word_count ? ` · ${item.word_count} 字` : ''}
                  </div>
                  {item.preview && <div className="text-xs text-gray-500 mt-1 truncate">{item.preview}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
