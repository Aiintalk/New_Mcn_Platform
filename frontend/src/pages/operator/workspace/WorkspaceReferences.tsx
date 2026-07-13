import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Popconfirm } from 'antd';
import {
  CrownOutlined,
  FileTextOutlined,
  FireOutlined,
  HeartOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
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

interface TypeMeta {
  icon: React.ReactNode;
  color: string;
}

const TYPE_GROUPS = [
  {
    group: '人设仿写素材',
    types: [
      { type: '红人爆款文案', icon: <FireOutlined />, color: 'var(--danger)' },
      { type: '红人喜欢的内容', icon: <HeartOutlined />, color: 'var(--pink)' },
      { type: '风格参考', icon: <StarOutlined />, color: 'var(--brand)' },
    ],
  },
  {
    group: '千川仿写素材',
    types: [
      { type: '千川爆款文案', icon: <ThunderboltOutlined />, color: 'var(--warning)' },
      { type: '千川喜欢的内容', icon: <CrownOutlined />, color: 'var(--purple)' },
      { type: '千川风格参考', icon: <FileTextOutlined />, color: 'var(--info)' },
    ],
  },
] as const;

const TYPE_META: Record<string, TypeMeta> = Object.fromEntries(
  TYPE_GROUPS.flatMap(({ types }) => types.map(({ type, icon, color }) => [type, { icon, color }])),
);

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

export default function WorkspaceReferences({ kolId }: WorkspaceReferencesProps) {
  const { message } = App.useApp();
  const [references, setReferences] = useState<KolReference[]>([]);
  const [activeType, setActiveType] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [playbackUrls, setPlaybackUrls] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formVisible, setFormVisible] = useState(false);
  const [editing, setEditing] = useState<KolReference | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

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

  const visibleReferences = useMemo(
    () => references.filter((reference) => reference.type === activeType),
    [activeType, references],
  );

  function resetForm() {
    setEditing(null);
    setForm(emptyForm());
    setFormVisible(false);
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
    }
  }

  async function saveReference() {
    if (!activeType || !form.title.trim() || !form.content.trim()) {
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
        : await createKolReference(kolId, { ...metadata, type: activeType });
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

  if (activeType === null) {
    return (
      <div style={{ maxWidth: 900 }}>
        <div className="page-header">
          <div><h1 className="page-title">素材库</h1><p className="page-desc">管理当前红人的六类脚本文档和视频原片</p></div>
        </div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : TYPE_GROUPS.map((group) => (
          <section key={group.group} style={{ marginBottom: 'var(--sp-6)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 'var(--sp-3)' }}>{group.group}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 'var(--sp-3)' }}>
              {group.types.map((item) => {
                const count = references.filter((reference) => reference.type === item.type).length;
                return <button key={item.type} type="button" className="card" onClick={() => setActiveType(item.type)} style={{ cursor: 'pointer', textAlign: 'left' }}>
                  <div className="card-body"><div style={{ color: item.color, fontSize: 24 }}>{item.icon}</div><strong>{item.type}</strong><div style={{ color: 'var(--gray-400)', fontSize: 12, marginTop: 6 }}>已有 {count} 条</div></div>
                </button>;
              })}
            </div>
          </section>
        ))}
      </div>
    );
  }

  const meta = TYPE_META[activeType];
  return (
    <div style={{ maxWidth: 900 }}>
      <div className="page-header">
        <div>
          <button className="btn btn-ghost btn-sm" onClick={() => { setActiveType(null); resetForm(); }}>← 返回</button>
          <h1 className="page-title" style={{ marginTop: 8, color: meta?.color }}>{meta?.icon} {activeType}</h1>
          <p className="page-desc">{visibleReferences.length} 条素材</p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={openCreate}>添加素材</button>
      </div>

      {formVisible && <div className="card" style={{ marginBottom: 'var(--sp-4)' }}><div className="card-body">
        <strong>{editing ? '编辑素材' : '添加素材'}</strong>
        <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
          <label>标题 *<input aria-label="素材标题" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>数据说明（如点赞数、完播率）<input aria-label="数据说明" value={form.dataDescription} onChange={(event) => setForm({ ...form, dataDescription: event.target.value })} /></label>
          <label>上传脚本文档（自动解析后仍可修改）<input aria-label="上传脚本文档" type="file" accept=".txt,.doc,.docx,.pdf" onChange={(event) => void parseDocument(event.target.files?.[0])} /></label>
          {form.documentName && <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>已解析：{form.documentName} {readableSize(form.documentSize)}</span>}
          <label>脚本正文 *<textarea aria-label="脚本正文" rows={7} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
          <label>{editing?.has_video ? '替换视频（不选则保留现有视频）' : '视频原片（可选）'}<input aria-label="视频原片" type="file" accept="video/*" onChange={(event) => setForm({ ...form, video: event.target.files?.[0] })} /></label>
          {editing?.has_video && <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>当前视频：{editing.video_name}</span>}
          <div style={{ display: 'flex', gap: 8 }}><button className="btn btn-primary btn-sm" disabled={saving} onClick={() => void saveReference()}>{saving ? '保存中...' : '保存'}</button><button className="btn btn-ghost btn-sm" disabled={saving} onClick={resetForm}>取消</button></div>
        </div>
      </div></div>}

      {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : visibleReferences.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无素材，点击「添加素材」开始录入</div></div> : (
        <div>{visibleReferences.map((reference) => {
          const isExpanded = expanded.has(reference.id);
          return <article key={reference.id} className="card" style={{ marginBottom: 'var(--sp-3)' }}><div className="card-body">
            <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
              <div style={{ minWidth: 0 }}><strong>{reference.title}</strong><div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>{reference.data_description || (reference.likes !== null ? `${reference.likes} 赞` : '未填写数据说明')}</div><div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>{reference.has_video ? '有视频' : '无视频'}{reference.document_name ? ` · ${reference.document_name}` : ''}</div></div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}><button className="btn btn-ghost btn-sm" onClick={() => void toggleExpanded(reference)}>{isExpanded ? '收起' : '展开'}</button><button className="btn btn-ghost btn-sm" onClick={() => openEdit(reference)}>编辑</button><Popconfirm title="确认删除这条素材？" onConfirm={() => void removeReference(reference)} okText="删除" cancelText="取消" okButtonProps={{ danger: true }}><button className="btn btn-danger-ghost btn-sm">删除</button></Popconfirm></div>
            </div>
            {isExpanded && <div style={{ marginTop: 12 }}><div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, background: 'var(--bg-muted)', padding: 'var(--sp-3)', borderRadius: 'var(--radius-md)' }}>{reference.content}</div>{reference.has_video && <div style={{ marginTop: 12 }}><div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>{reference.video_name} {readableSize(reference.video_size)}</div>{playbackUrls[reference.id] ? <video controls src={playbackUrls[reference.id]} style={{ width: '100%', maxWidth: 560 }} /> : <span style={{ fontSize: 12 }}>正在获取播放地址...</span>}</div>}</div>}
          </div></article>;
        })}</div>
      )}
    </div>
  );
}
