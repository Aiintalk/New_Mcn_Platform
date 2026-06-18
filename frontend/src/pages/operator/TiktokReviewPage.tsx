// frontend/src/pages/operator/TiktokReviewPage.tsx
import { useState, useRef, useCallback } from 'react';
import { App } from 'antd';
import { useAuthStore } from '../../store/authStore';
import { generateStream, saveReport, exportWord } from '../../api/tiktokReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/* ── Markdown 渲染 ── */
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

interface VideoSide {
  file: File | null;
  transcript: string;
  likes: string;
}

const EMPTY_SIDE: VideoSide = { file: null, transcript: '', likes: '' };

/* ── 单侧输入面板 ── */
function SidePanel({
  side,
  data,
  onChange,
  transcribing,
  onTranscribe,
}: {
  side: 'original' | 'copycat';
  data: VideoSide;
  onChange: (patch: Partial<VideoSide>) => void;
  transcribing: boolean;
  onTranscribe: () => void;
}) {
  const label = side === 'original' ? '原版爆款' : '仿写版';
  const borderColor = side === 'original' ? '#d1fae5' : '#bfdbfe';
  const dotColor = side === 'original' ? '#10b981' : '#3b82f6';
  const titleColor = side === 'original' ? '#065f46' : '#1e40af';

  function handleFileDrop(file: File | null) {
    onChange({ file });
  }

  return (
    <div style={{
      flex: 1, border: `2px solid ${borderColor}`, borderRadius: 12,
      padding: 20, background: '#fff', minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 16, color: titleColor }}>{label}</span>
      </div>

      {/* 视频上传 */}
      <div
        style={{
          border: '2px dashed #e5e7eb', borderRadius: 8, padding: 16,
          textAlign: 'center', cursor: 'pointer', marginBottom: 8,
          background: '#fafafa',
        }}
        onClick={() => document.getElementById(`file-${side}`)?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault();
          const f = e.dataTransfer.files[0];
          if (f && f.type.startsWith('video/')) handleFileDrop(f);
        }}
      >
        <input
          id={`file-${side}`}
          type="file"
          accept="video/*"
          style={{ display: 'none' }}
          onChange={e => handleFileDrop(e.target.files?.[0] || null)}
        />
        {data.file ? (
          <div style={{ fontSize: 13, color: '#374151' }}>
            {data.file.name}
            <span style={{ color: '#9ca3af', marginLeft: 6 }}>
              ({(data.file.size / 1024 / 1024).toFixed(1)}MB)
            </span>
            <button
              style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#f87171' }}
              onClick={e => { e.stopPropagation(); handleFileDrop(null); }}
            >✕</button>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#9ca3af' }}>上传视频自动转文案（最大25MB）</div>
        )}
      </div>

      {data.file && (
        <button
          disabled={transcribing}
          onClick={onTranscribe}
          style={{
            width: '100%', padding: '8px 0', borderRadius: 8, border: 'none',
            background: transcribing ? '#9ca3af' : '#7c3aed', color: '#fff',
            fontSize: 13, fontWeight: 600, cursor: transcribing ? 'not-allowed' : 'pointer',
            marginBottom: 8,
          }}
        >
          {transcribing ? '转录中...' : '转文案'}
        </button>
      )}

      {/* 文案文本框 */}
      <textarea
        style={{
          width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb',
          borderRadius: 8, fontSize: 13, height: 112, resize: 'vertical',
          outline: 'none', boxSizing: 'border-box', marginBottom: 8,
        }}
        placeholder="上传视频自动转录，或直接粘贴文案..."
        value={data.transcript}
        onChange={e => onChange({ transcript: e.target.value })}
      />

      {/* 点赞数 */}
      <input
        type="text"
        style={{
          width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb',
          borderRadius: 8, fontSize: 13, outline: 'none', boxSizing: 'border-box',
        }}
        placeholder="点赞数（如 16万）"
        value={data.likes}
        onChange={e => onChange({ likes: e.target.value })}
      />
    </div>
  );
}

/* ── 主页面 ── */
export default function TiktokReviewPage() {
  const { message } = App.useApp();
  const [original, setOriginal] = useState<VideoSide>({ ...EMPTY_SIDE });
  const [copycat, setCopycat] = useState<VideoSide>({ ...EMPTY_SIDE });
  const [transcribing, setTranscribing] = useState<'original' | 'copycat' | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState('');
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  async function handleTranscribe(side: 'original' | 'copycat') {
    const data = side === 'original' ? original : copycat;
    if (!data.file) return;
    setTranscribing(side);
    try {
      const token = useAuthStore.getState().token;
      const form = new FormData();
      form.append('file', data.file);
      form.append('language', 'ko');
      const resp = await fetch(`${BASE_URL}/api/tools/transcribe`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json?.detail?.message ?? '转录失败');
      const text = json?.data?.text ?? '';
      if (side === 'original') setOriginal(prev => ({ ...prev, transcript: text }));
      else setCopycat(prev => ({ ...prev, transcript: text }));
    } catch (e) {
      message.error(e instanceof Error ? e.message : '转录出错');
    } finally {
      setTranscribing(null);
    }
  }

  const handleAnalyze = useCallback(async () => {
    if (!original.transcript.trim() && !copycat.transcript.trim()) {
      message.warning('至少需要一侧有文案内容才能分析');
      return;
    }
    setAnalyzing(true);
    setReport('');
    setTaskId(null);
    try {
      const resp = await generateStream({
        original_transcript: original.transcript,
        original_likes: original.likes,
        copycat_transcript: copycat.transcript,
        copycat_likes: copycat.likes,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.detail?.message ?? `分析请求失败: ${resp.status}`);
      }

      const tid = resp.headers.get('x-task-id');
      if (tid) setTaskId(Number(tid));

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');
      const decoder = new TextDecoder();
      let fullText = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
        setReport(fullText);
      }
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '分析出错');
    } finally {
      setAnalyzing(false);
    }
  }, [original, copycat, message]);

  async function handleSave() {
    if (!report) return;
    setSaving(true);
    try {
      const date = new Date().toISOString().slice(0, 10);
      await saveReport({
        content: report,
        title: `TT复盘报告_${date}`,
        task_id: taskId,
      });
      message.success('报告已保存到产出中心');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    if (!report) return;
    setExporting(true);
    try {
      const date = new Date().toISOString().slice(0, 10);
      const blob = await exportWord(report, `TT复盘报告_${date}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `TT复盘报告_${date}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '32px 16px' }}>
      {/* 标题 */}
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1f2937', margin: 0 }}>TT内容复盘</h1>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 6 }}>
          上传/粘贴两条视频文案，AI找出差距
        </p>
      </div>

      {/* 两栏输入 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <SidePanel
            side="original"
            data={original}
            onChange={patch => setOriginal(prev => ({ ...prev, ...patch }))}
            transcribing={transcribing === 'original'}
            onTranscribe={() => handleTranscribe('original')}
          />
          <SidePanel
            side="copycat"
            data={copycat}
            onChange={patch => setCopycat(prev => ({ ...prev, ...patch }))}
            transcribing={transcribing === 'copycat'}
            onTranscribe={() => handleTranscribe('copycat')}
          />
        </div>
      </div>

      {/* 开始复盘按钮 */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <button
          disabled={analyzing}
          onClick={handleAnalyze}
          style={{
            padding: '12px 32px', borderRadius: 12, border: 'none',
            background: analyzing
              ? '#9ca3af'
              : 'linear-gradient(to right, #7c3aed, #2563eb)',
            color: '#fff', fontSize: 15, fontWeight: 700,
            cursor: analyzing ? 'not-allowed' : 'pointer',
            boxShadow: analyzing ? 'none' : '0 4px 12px rgba(124,58,237,0.3)',
          }}
        >
          {analyzing ? '正在分析...' : '开始复盘'}
        </button>
      </div>

      {/* 复盘报告 */}
      {report && (
        <div
          ref={reportRef}
          style={{
            background: '#fff', border: '1px solid #e5e7eb',
            borderRadius: 12, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1f2937', margin: 0 }}>复盘报告</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                disabled={saving}
                onClick={handleSave}
                style={{
                  padding: '6px 16px', borderRadius: 8, border: 'none',
                  background: saving ? '#9ca3af' : '#2563eb', color: '#fff',
                  fontSize: 13, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? '保存中...' : '保存'}
              </button>
              <button
                disabled={exporting}
                onClick={handleExport}
                style={{
                  padding: '6px 16px', borderRadius: 8, border: 'none',
                  background: exporting ? '#9ca3af' : '#059669', color: '#fff',
                  fontSize: 13, fontWeight: 600, cursor: exporting ? 'not-allowed' : 'pointer',
                }}
              >
                {exporting ? '导出中...' : '导出 Word'}
              </button>
            </div>
          </div>
          <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 16 }}>
            <SimpleMarkdown text={report} />
          </div>
        </div>
      )}
    </div>
  );
}
