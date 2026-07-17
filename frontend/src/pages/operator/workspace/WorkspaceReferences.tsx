import { useCallback, useEffect, useRef, useState } from 'react';
import { App, Popconfirm } from 'antd';
import { UploadOutlined, VideoCameraOutlined } from '@ant-design/icons';
import {
  createKolReference,
  deleteKolReference,
  flattenKolReferences,
  getKolReferenceVideoPlayback,
  getMaterialLibraryKolDetail,
  parseKolReferenceDocument,
  updateKolReference,
  uploadKolReferenceVideo,
} from '../../../api/materialLibrary';
import type { KolReference } from '../../../api/materialLibrary';

interface WorkspaceReferencesProps {
  kolId: number;
}

const MAX_VIDEO_UPLOAD_BYTES = 500 * 1024 * 1024;
const STORAGE_TYPE = '千川爆款文案';
const DISPLAY_TYPE = '千川爆款素材';

type FormState = {
  title: string;
  dataDescription: string;
  content: string;
  documentName: string;
  documentType: string;
  documentSize?: number;
  video?: File;
};

const emptyForm = (): FormState => ({
  title: '', dataDescription: '', content: '', documentName: '', documentType: '', documentSize: undefined,
});

function referenceForm(reference: KolReference): FormState {
  return {
    title: reference.title,
    dataDescription: reference.data_description ?? '',
    content: reference.content,
    documentName: reference.document_name ?? '',
    documentType: reference.document_type ?? '',
    documentSize: reference.document_size ?? undefined,
  };
}

function readableSize(size?: number | null): string {
  if (!size) return '';
  return size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function contentSummary(content: string): string {
  const normalized = content.replace(/\s+/g, ' ').trim();
  return normalized.length > 80 ? `${normalized.slice(0, 80)}…` : normalized;
}

export default function WorkspaceReferences({ kolId }: WorkspaceReferencesProps) {
  const { message } = App.useApp();
  const [references, setReferences] = useState<KolReference[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [playbackUrls, setPlaybackUrls] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formVisible, setFormVisible] = useState(true);
  const [editing, setEditing] = useState<KolReference | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [documentParsing, setDocumentParsing] = useState(false);
  const documentInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);

  const loadReferences = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await getMaterialLibraryKolDetail(kolId);
      setReferences(flattenKolReferences(detail.references));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载素材库失败');
    } finally {
      setLoading(false);
    }
  }, [kolId, message]);

  useEffect(() => { void loadReferences(); }, [loadReferences]);

  const visibleReferences = references.filter((reference) => reference.type === STORAGE_TYPE);

  function resetForm() {
    setEditing(null);
    setForm(emptyForm());
    setFormVisible(true);
  }

  function openCreate() {
    setEditing(null);
    setForm(emptyForm());
    setFormVisible(true);
  }

  function openEdit(reference: KolReference) {
    setEditing(reference);
    setForm(referenceForm(reference));
    setFormVisible(true);
  }

  async function parseDocument(file?: File) {
    if (!file) return;
    setDocumentParsing(true);
    try {
      const parsed = await parseKolReferenceDocument(kolId, file);
      setForm((previous) => ({
        ...previous,
        content: parsed.text,
        documentName: parsed.document_name,
        documentType: parsed.document_type ?? '',
        documentSize: parsed.document_size,
      }));
      message.success('文档已解析，可在保存前修改正文');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文档解析失败');
    } finally {
      setDocumentParsing(false);
    }
  }

  function selectVideo(file?: File) {
    if (file && file.size > MAX_VIDEO_UPLOAD_BYTES) {
      message.error('视频文件不能超过 500MB');
      setForm((previous) => ({ ...previous, video: undefined }));
      return;
    }
    setForm((previous) => ({ ...previous, video: file }));
  }

  async function saveReference() {
    if (!form.title.trim() || !form.content.trim()) {
      message.warning('请填写标题和脚本正文');
      return;
    }
    setSaving(true);
    try {
      const metadata = {
        title: form.title.trim(),
        data_description: form.dataDescription.trim() || undefined,
        content: form.content.trim(),
        document_name: form.documentName || undefined,
        document_type: form.documentType || undefined,
        document_size: form.documentSize,
      };
      const saved = editing
        ? await updateKolReference(kolId, editing.id, metadata)
        : await createKolReference(kolId, { ...metadata, type: STORAGE_TYPE });
      const withVideo = form.video
        ? await uploadKolReferenceVideo(kolId, saved.id, form.video)
        : saved;
      setReferences((previous) => editing
        ? previous.map((reference) => reference.id === withVideo.id ? withVideo : reference)
        : [withVideo, ...previous]);
      message.success(editing ? '素材已更新，原视频保持不变' : '素材已添加');
      resetForm();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存素材失败');
    } finally {
      setSaving(false);
    }
  }

  async function toggleExpanded(reference: KolReference) {
    const isExpanded = expanded.has(reference.id);
    setExpanded((previous) => {
      const next = new Set(previous);
      isExpanded ? next.delete(reference.id) : next.add(reference.id);
      return next;
    });
    if (!isExpanded && reference.has_video && !playbackUrls[reference.id]) {
      try {
        const playback = await getKolReferenceVideoPlayback(kolId, reference.id);
        setPlaybackUrls((previous) => ({ ...previous, [reference.id]: playback.url }));
      } catch (error) {
        message.error(error instanceof Error ? error.message : '视频播放地址获取失败');
      }
    }
  }

  async function removeReference(reference: KolReference) {
    try {
      await deleteKolReference(kolId, reference.id);
      setReferences((previous) => previous.filter((item) => item.id !== reference.id));
      setPlaybackUrls((previous) => {
        const next = { ...previous };
        delete next[reference.id];
        return next;
      });
      message.success('素材已删除');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除素材失败');
    }
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">素材库</h1>
          <p className="page-desc">管理当前红人的千川爆款文案和视频原片</p>
        </div>
        {!formVisible && <button className="btn btn-primary btn-sm" onClick={openCreate}>上传千川爆款素材</button>}
      </div>

      {formVisible && <section className="card" style={{ marginBottom: 'var(--sp-5)' }}><div className="card-body">
        <h2 className="card-title">{editing ? '编辑千川爆款素材' : '上传千川爆款素材'}</h2>
        <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
          <label>标题 *<input aria-label="素材标题" style={{ width: '100%', boxSizing: 'border-box', marginTop: 6 }} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>数据说明（如点赞数、完播率）<input aria-label="数据说明" style={{ width: '100%', boxSizing: 'border-box', marginTop: 6 }} value={form.dataDescription} onChange={(event) => setForm({ ...form, dataDescription: event.target.value })} /></label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <div role="button" tabIndex={0} className="workspace-upload-tile" onClick={() => documentInput.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter') documentInput.current?.click(); }}>
              <UploadOutlined /><strong>{documentParsing ? '脚本文档解析中…' : '上传脚本文档'}</strong><span>{form.documentName ? `已解析：${form.documentName} ${readableSize(form.documentSize)}` : 'docx / doc / txt / md（可选 pdf）'}</span>
              <input ref={documentInput} aria-label="上传脚本文档" type="file" accept=".txt,.md,.doc,.docx,.pdf" style={{ display: 'none' }} onChange={(event) => void parseDocument(event.target.files?.[0])} />
            </div>
            <div role="button" tabIndex={0} className="workspace-upload-tile" onClick={() => videoInput.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter') videoInput.current?.click(); }}>
              <VideoCameraOutlined /><strong>{editing?.has_video ? '替换视频（可选）' : '上传视频原片（可选）'}</strong><span>{form.video ? `${form.video.name} ${readableSize(form.video.size)}` : 'mp4 / mov，最大 500MB'}</span>
              <input ref={videoInput} aria-label="视频原片" type="file" accept="video/*" style={{ display: 'none' }} onChange={(event) => selectVideo(event.target.files?.[0])} />
            </div>
          </div>
          <label>脚本内容 *<textarea aria-label="脚本正文" rows={14} style={{ width: '100%', boxSizing: 'border-box', marginTop: 6 }} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
          <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>正文 {form.content.replace(/\s/g, '').length} 字，解析后可继续修改。</span>
          {editing?.has_video && <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>当前视频：{editing.video_name}</span>}
          <div style={{ display: 'flex', gap: 8 }}><button className="btn btn-primary" style={{ width: '100%' }} disabled={saving} onClick={() => void saveReference()}>{saving ? '保存中...' : editing ? '保存修改' : '保存素材'}</button>{editing && <button className="btn btn-ghost btn-sm" disabled={saving} onClick={resetForm}>取消编辑</button>}</div>
        </div>
      </div></section>}

      <section><h2 className="card-title" style={{ marginBottom: 'var(--sp-3)' }}>已有素材</h2>
      {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : visibleReferences.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无千川爆款素材</div></div> : (
        <div>{visibleReferences.map((reference) => {
          const isExpanded = expanded.has(reference.id);
          return <article key={reference.id} className="card" style={{ marginBottom: 'var(--sp-3)' }}><div className="card-body">
            <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
              <div style={{ minWidth: 0 }}><strong>{reference.title}</strong><div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>{reference.data_description || (reference.likes !== null ? `${reference.likes} 赞` : '未填写数据说明')}</div><div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>分类：{DISPLAY_TYPE} · {reference.has_video ? '有视频' : '无视频'}{reference.document_name ? ` · ${reference.document_name}` : ''}</div><div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>摘要：{contentSummary(reference.content)}</div></div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}><button className="btn btn-ghost btn-sm" onClick={() => void toggleExpanded(reference)}>{isExpanded ? '收起' : '展开'}</button><button className="btn btn-ghost btn-sm" onClick={() => openEdit(reference)}>编辑</button><Popconfirm title="确认删除这条素材？" onConfirm={() => void removeReference(reference)} okText="删除" cancelText="取消" okButtonProps={{ danger: true }}><button className="btn btn-danger-ghost btn-sm">删除</button></Popconfirm></div>
            </div>
            {isExpanded && <div style={{ marginTop: 12 }}>{reference.has_video && <div style={{ marginBottom: 12 }}><div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>{reference.video_name} {readableSize(reference.video_size)}</div>{playbackUrls[reference.id] ? <video controls src={playbackUrls[reference.id]} style={{ width: '100%', maxWidth: 560 }} /> : <span style={{ fontSize: 12 }}>正在获取播放地址...</span>}</div>}<div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, background: 'var(--bg-muted)', padding: 'var(--sp-3)', borderRadius: 'var(--radius-md)' }}>{reference.content}</div></div>}
          </div></article>;
        })}</div>
      )}</section>
    </div>
  );
}
