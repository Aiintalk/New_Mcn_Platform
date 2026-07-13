import { useState } from 'react';
import { App, Button, Tag } from 'antd';
import { DownloadOutlined, SaveOutlined, VideoCameraOutlined } from '@ant-design/icons';
import {
  analyzeFilm,
  exportFilmReport,
  saveFilmReport,
} from '../../api/filmReview';
import type { FilmVideoRole, FilmVideoStatus } from '../../types/filmReview';

interface VideoCardState {
  file: File | null;
  status: FilmVideoStatus;
  error: string | null;
}

const EMPTY_VIDEO: VideoCardState = { file: null, status: 'selected', error: null };
const ACCEPTED_VIDEO_TYPES = ['video/mp4', 'video/quicktime'];
const ACCEPTED_VIDEO_EXTENSIONS = ['.mp4', '.mov'];

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isSupportedVideo(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_VIDEO_TYPES.includes(file.type) || ACCEPTED_VIDEO_EXTENSIONS.some((extension) => name.endsWith(extension));
}

function statusLabel(status: FilmVideoStatus): string {
  if (status === 'uploading') return '上传中';
  if (status === 'analyzing') return '完整视频分析中';
  if (status === 'completed') return '分析完成，临时文件已清理';
  if (status === 'failed') return '分析失败，可重试';
  return '已选择，等待上传';
}

export function FilmReviewModule({ kolId: _kolId }: { kolId: number }) {
  const { message } = App.useApp();
  const [original, setOriginal] = useState<VideoCardState>({ ...EMPTY_VIDEO });
  const [edited, setEdited] = useState<VideoCardState>({ ...EMPTY_VIDEO });
  const [analysisStatus, setAnalysisStatus] = useState('等待上传两条完整视频');
  const [analysisSteps, setAnalysisSteps] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState('');
  const [taskId, setTaskId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  function stateFor(role: FilmVideoRole): VideoCardState {
    return role === 'original' ? original : edited;
  }

  function updateState(role: FilmVideoRole, next: VideoCardState | ((previous: VideoCardState) => VideoCardState)) {
    const update = role === 'original' ? setOriginal : setEdited;
    update(next);
  }

  function selectFile(role: FilmVideoRole, file: File | null) {
    if (!file) return;
    if (!isSupportedVideo(file)) {
      updateState(role, (previous) => ({ ...previous, error: '仅支持 mp4 或 mov 视频文件' }));
      return;
    }
    updateState(role, { file, status: 'selected', error: null });
    setReport('');
    setTaskId(null);
    setAnalysisStatus('视频已选择，等待上传');
    setAnalysisSteps([]);
  }

  async function startAnalysis() {
    if (!original.file || !edited.file) {
      message.warning('请先选择原片和已剪辑成片');
      return;
    }
    setAnalyzing(true);
    setReport('');
    setTaskId(null);
    setOriginal((current) => ({ ...current, status: 'uploading', error: null }));
    setEdited((current) => ({ ...current, status: 'uploading', error: null }));
    setAnalysisStatus('正在上传两条完整视频');
    setAnalysisSteps(['正在上传两条完整视频']);
    try {
      const response = await analyzeFilm(original.file, edited.file);
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { message?: string; detail?: string } | null;
        throw new Error(body?.message || body?.detail || '完整视频分析请求失败');
      }
      const returnedTaskId = Number(response.headers.get('X-Task-Id'));
      if (Number.isInteger(returnedTaskId) && returnedTaskId > 0) setTaskId(returnedTaskId);
      setOriginal((current) => ({ ...current, status: 'analyzing' }));
      setEdited((current) => ({ ...current, status: 'analyzing' }));
      setAnalysisStatus('正在读取两条完整视频');
      setAnalysisSteps((steps) => [...steps, '正在读取两条完整视频']);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('无法读取流式分析报告');
      const decoder = new TextDecoder();
      let buffer = '';
      let streamedReport = '';
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const statusMarker = '__STATUS__';
        const markerIndex = buffer.lastIndexOf(statusMarker);
        if (markerIndex >= 0) {
          const statusEnd = buffer.indexOf('\n', markerIndex);
          if (statusEnd >= 0) {
            const status = buffer.slice(markerIndex + statusMarker.length, statusEnd).trim();
            setAnalysisStatus(status);
            if (status) setAnalysisSteps((steps) => [...steps, status]);
            buffer = buffer.slice(0, markerIndex) + buffer.slice(statusEnd + 1);
          }
        }
        if (buffer) {
          streamedReport += buffer;
          setReport(streamedReport);
          buffer = '';
        }
        if (done) break;
      }
      setOriginal((current) => ({ ...current, status: 'completed' }));
      setEdited((current) => ({ ...current, status: 'completed' }));
      setAnalysisStatus('完整视频分析完成');
      setAnalysisSteps((steps) => [...steps, '完整视频分析完成']);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '完整视频分析失败';
      setAnalysisStatus(`分析失败：${errorMessage}`);
      setAnalysisSteps((steps) => [...steps, `分析失败：${errorMessage}`]);
      setOriginal((current) => ({ ...current, status: 'failed', error: errorMessage }));
      setEdited((current) => ({ ...current, status: 'failed', error: errorMessage }));
      message.error(errorMessage);
    } finally {
      setAnalyzing(false);
    }
  }

  async function saveReport() {
    if (!report.trim()) return;
    setSaving(true);
    try {
      if (!taskId || !original.file || !edited.file) return;
      await saveFilmReport({
        task_id: taskId,
        report,
        original_filename: original.file.name,
        edited_filename: edited.file.name,
      });
      message.success('报告已保存到产出中心');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存报告失败');
    } finally {
      setSaving(false);
    }
  }

  async function exportReport() {
    if (!report.trim()) return;
    setExporting(true);
    try {
      const blob = await exportFilmReport(report);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = '千川成片预审报告.docx';
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出报告失败');
    } finally {
      setExporting(false);
    }
  }

  function renderVideoCard(role: FilmVideoRole, title: string) {
    const current = stateFor(role);
    return (
      <div className="card" style={{ marginBottom: 0 }} data-testid={`film-card-${role}`}>
        <div className="card-header">
          <h2 className="card-title">{title}</h2>
          <Tag color={current.status === 'completed' ? 'success' : current.status === 'failed' ? 'error' : 'default'}>
            {statusLabel(current.status)}
          </Tag>
        </div>
        <div className="card-body">
          <input
            data-testid={`film-file-${role}`}
            type="file"
            accept=".mp4,.mov,video/mp4,video/quicktime"
            onChange={(event) => selectFile(role, event.target.files?.[0] || null)}
          />
          {current.file && (
            <div style={{ marginTop: 'var(--sp-3)', fontSize: 13, color: 'var(--gray-700)' }}>
              <div>{current.file.name}</div>
              <div style={{ color: 'var(--gray-500)', marginTop: 4 }}>{formatSize(current.file.size)}</div>
            </div>
          )}
          {current.error && <div role="alert" style={{ marginTop: 'var(--sp-2)', color: 'var(--danger)', fontSize: 13 }}>{current.error}</div>}
          <div style={{ marginTop: 'var(--sp-3)', color: 'var(--gray-500)', fontSize: 12 }}>
            两条视频会在点击“开始完整视频预审”后一起上传并分析。
          </div>
        </div>
      </div>
    );
  }

  const canAnalyze = Boolean(original.file && edited.file) && !analyzing;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川成片预审</h1>
          <p className="page-desc">后端将原片和已剪辑成片作为两条完整视频提交分析，不使用关键帧替代。</p>
        </div>
      </div>

      <div className="card">
        <div className="card-body" style={{ color: 'var(--gray-600)', fontSize: 13 }}>
          支持 mp4、mov。建议 500MB 以内，实际服务端限制为 500MB。
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
        {renderVideoCard('original', '原片')}
        {renderVideoCard('edited', '已剪辑成片')}
      </div>

      <div className="card">
        <div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
          <Button type="primary" icon={<VideoCameraOutlined />} loading={analyzing} disabled={!canAnalyze} onClick={startAnalysis}>
            开始完整视频预审
          </Button>
          <span aria-live="polite" style={{ fontSize: 13, color: 'var(--gray-600)' }}>{analysisStatus}</span>
        </div>
      </div>

      {analysisSteps.length > 0 && (
        <div className="card">
          <div className="card-body" aria-live="polite" style={{ fontSize: 13, color: 'var(--gray-600)' }}>
            {analysisSteps.map((step, index) => <div key={`${index}-${step}`}>{step}</div>)}
          </div>
        </div>
      )}

      {report && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">预审报告</h2>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Button size="small" icon={<SaveOutlined />} loading={saving} disabled={!taskId} onClick={saveReport}>保存报告</Button>
              <Button size="small" icon={<DownloadOutlined />} loading={exporting} onClick={exportReport}>导出办公文档</Button>
            </div>
          </div>
          <div className="card-body">
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)', lineHeight: 1.7 }}>{report}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
