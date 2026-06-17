import { useState, useRef } from 'react';
import { parseFile, chatStream, exportWord } from '../../api/qianchuanPreview';

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.+)/g, '<h3 style="font-size:14px;font-weight:600;margin:16px 0 8px">$1</h3>')
    .replace(/## (.+)/g, '<h2 style="font-size:16px;font-weight:600;margin:20px 0 8px">$1</h2>')
    .replace(/# (.+)/g, '<h1 style="font-size:18px;font-weight:700;margin:24px 0 10px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n/g, '<br/>');
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--gray-800)' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

type Side = 'a' | 'b';

export default function QianchuanPreviewPage() {
  const [scriptA, setScriptA] = useState('');
  const [scriptB, setScriptB] = useState('');
  const [fileNameA, setFileNameA] = useState('');
  const [fileNameB, setFileNameB] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState('');
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const reportRef = useRef<HTMLDivElement>(null);

  async function handleFile(side: Side, file: File) {
    setError('');
    try {
      const result = await parseFile(file);
      if (side === 'a') { setScriptA(result.text); setFileNameA(result.filename); }
      else { setScriptB(result.text); setFileNameB(result.filename); }
    } catch (e) {
      setError(e instanceof Error ? e.message : '文件解析失败');
    }
  }

  async function analyze() {
    if (!scriptA.trim() || !scriptB.trim()) {
      setError('两边都需要有文案才能预审');
      return;
    }
    setAnalyzing(true);
    setReport('');
    setError('');
    try {
      const resp = await chatStream(scriptA, scriptB);
      if (!resp.ok) throw new Error('AI 分析请求失败');
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setReport(full);
      }
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (e) {
      setError(e instanceof Error ? e.message : '分析出错');
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleExportWord() {
    if (!report) return;
    setExporting(true);
    try {
      const blob = await exportWord(report, '千川文案预审报告');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `千川预审报告_${new Date().toISOString().slice(0, 10)}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(report);
    } catch {
      setError('复制失败，请手动复制');
    }
  }

  function renderSide(side: Side) {
    const isA = side === 'a';
    const text = isA ? scriptA : scriptB;
    const setText = isA ? setScriptA : setScriptB;
    const fileName = isA ? fileNameA : fileNameB;
    const setFileName = isA ? setFileNameA : setFileNameB;
    const label = isA ? '原版爆款文案' : '我方文案';
    const placeholder = isA ? '上传文档或直接粘贴原版爆款文案...' : '上传文档或直接粘贴我方文案脚本...';
    const accentColor = isA ? 'var(--success)' : 'var(--brand)';
    const inputId = `file-${side}`;

    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-body">
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 12, color: accentColor }}>
            {label}
          </div>
          <div
            style={{
              border: '2px dashed var(--gray-200)',
              borderRadius: 8,
              padding: '12px 16px',
              textAlign: 'center',
              cursor: 'pointer',
              marginBottom: 12,
              background: 'var(--gray-50)',
            }}
            onClick={() => document.getElementById(inputId)?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) handleFile(side, f);
            }}
          >
            <input
              id={inputId}
              type="file"
              accept=".txt,.docx,.doc"
              style={{ display: 'none' }}
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) handleFile(side, f);
                e.target.value = '';
              }}
            />
            {fileName ? (
              <div style={{ fontSize: 13, color: 'var(--gray-700)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <span>{fileName}</span>
                <button
                  style={{ color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                  onClick={e => { e.stopPropagation(); setText(''); setFileName(''); }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--gray-400)' }}>
                上传文案文档（.docx / .txt），或直接粘贴下方
              </div>
            )}
          </div>
          <textarea
            className="form-control"
            style={{ width: '100%', height: 200, resize: 'vertical', fontSize: 13 }}
            placeholder={placeholder}
            value={text}
            onChange={e => setText(e.target.value)}
          />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川文案预审</h1>
          <p className="page-desc">拍摄前对比原版文案，AI找出问题给出修改建议</p>
        </div>
      </div>

      {error && (
        <div style={{
          marginBottom: 16, padding: '10px 16px',
          background: 'var(--danger-bg)', border: '1px solid var(--danger)',
          borderRadius: 8, fontSize: 13, color: 'var(--danger)',
          display: 'flex', justifyContent: 'space-between',
        }}>
          <span>{error}</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}
            onClick={() => setError('')}>✕</button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        {renderSide('a')}
        {renderSide('b')}
      </div>

      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <button
          className={`btn ${analyzing ? 'btn-disabled' : 'btn-primary'}`}
          style={{ minWidth: 140, fontSize: 15, padding: '10px 32px' }}
          disabled={analyzing || (!scriptA.trim() && !scriptB.trim())}
          onClick={analyze}
        >
          {analyzing ? '正在预审...' : '开始预审'}
        </button>
      </div>

      {report && (
        <div ref={reportRef} className="card">
          <div className="card-body">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 16 }}>预审报告</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-ghost btn-sm" onClick={handleCopy}>复制</button>
                <button
                  className={`btn btn-sm ${exporting ? 'btn-disabled' : 'btn-secondary'}`}
                  disabled={exporting}
                  onClick={handleExportWord}
                >
                  {exporting ? '导出中...' : '导出 Word'}
                </button>
              </div>
            </div>
            <div style={{ borderTop: '1px solid var(--gray-100)', paddingTop: 16 }}>
              <SimpleMarkdown text={report} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
