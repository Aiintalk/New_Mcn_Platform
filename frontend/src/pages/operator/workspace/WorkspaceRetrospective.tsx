// src/pages/operator/workspace/WorkspaceRetrospective.tsx
import { useState, useEffect, useCallback, useRef } from 'react';
import { App, Popconfirm } from 'antd';
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  DownloadOutlined,
  CopyOutlined,
  RedoOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import {
  getSessions,
  saveSession,
  deleteSession,
  parseFiles,
  analyzeStream,
  exportWord,
} from '../../../api/retrospective';
import type { RetrospectiveSession } from '../../../types/retrospective';

interface WorkspaceRetrospectiveProps {
  kolId: number;
}

type View = 'list' | 'edit' | 'detail';

// 5 类材料定义
const MATERIAL_FIELDS = [
  { key: 'live_data',         label: '直播汇总数据', accept: '.xlsx,.csv',       multiple: false },
  { key: 'material_data',     label: '素材明细数据', accept: '.xlsx,.csv',       multiple: false },
  { key: 'review_text',       label: '团队复盘文字', accept: '.docx,.txt',       multiple: false },
  { key: 'live_script',       label: '直播间脚本',   accept: '.docx,.txt',       multiple: false },
  { key: 'material_scripts',  label: '千川素材脚本', accept: '.docx,.txt',       multiple: true  },
] as const;

type MaterialKey = typeof MATERIAL_FIELDS[number]['key'];

// ---------------------------------------------------------------------------
// 简易 Markdown 渲染（不引入重量级库）
// ---------------------------------------------------------------------------
function SimpleMarkdown({ content }: { content: string }) {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={key++} style={{ fontSize: 15, fontWeight: 700, color: 'var(--gray-800)', margin: '20px 0 6px' }}>
          {line.slice(4)}
        </h3>,
      );
    } else if (line.startsWith('## ')) {
      elements.push(
        <h2 key={key++} style={{ fontSize: 17, fontWeight: 700, color: 'var(--gray-900)', margin: '24px 0 8px', borderBottom: '2px solid var(--brand)', paddingBottom: 4 }}>
          {line.slice(3)}
        </h2>,
      );
    } else if (line.startsWith('# ')) {
      elements.push(
        <h1 key={key++} style={{ fontSize: 20, fontWeight: 800, color: 'var(--gray-900)', margin: '0 0 16px' }}>
          {line.slice(2)}
        </h1>,
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <div key={key++} style={{ paddingLeft: 16, lineHeight: 1.8, color: 'var(--gray-700)' }}>
          <span style={{ color: 'var(--brand)', marginRight: 6 }}>•</span>
          {line.slice(2)}
        </div>,
      );
    } else if (line.trim() === '') {
      elements.push(<div key={key++} style={{ height: 8 }} />);
    } else {
      elements.push(
        <p key={key++} style={{ lineHeight: 1.8, color: 'var(--gray-700)', margin: '4px 0' }}>
          {line}
        </p>,
      );
    }
  }

  return <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14 }}>{elements}</div>;
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------
export default function WorkspaceRetrospective({ kolId }: WorkspaceRetrospectiveProps) {
  const { message } = App.useApp();

  // ── 视图状态机 ──────────────────────────────────────────────────────────────
  const [view, setView] = useState<View>('list');
  const [currentSession, setCurrentSession] = useState<RetrospectiveSession | null>(null);

  // ── 列表视图 ────────────────────────────────────────────────────────────────
  const [sessions, setSessions] = useState<RetrospectiveSession[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // ── 编辑视图 ────────────────────────────────────────────────────────────────
  const [title, setTitle] = useState('');
  const [parsedFields, setParsedFields] = useState<Partial<Record<MaterialKey, string>>>({});
  const [materialScripts, setMaterialScripts] = useState<{ name: string; text: string }[]>([]);
  const [uploading, setUploading] = useState<Partial<Record<MaterialKey, boolean>>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [streamResult, setStreamResult] = useState('');
  const [saving, setSaving] = useState(false);
  const fileInputRefs = useRef<Partial<Record<MaterialKey, HTMLInputElement | null>>>({});

  // ── 详情视图 ────────────────────────────────────────────────────────────────
  const [copying, setCopying] = useState(false);
  const [exporting, setExporting] = useState(false);

  // ── 加载列表 ────────────────────────────────────────────────────────────────
  const loadSessions = useCallback(async (p: number) => {
    setListLoading(true);
    try {
      const resp = await getSessions(kolId, p);
      setSessions(resp.items);
      setTotalPages(resp.pagination.total_pages);
    } catch (err: unknown) {
      message.error((err as Error).message || '加载列表失败');
    } finally {
      setListLoading(false);
    }
  }, [kolId, message]);

  useEffect(() => {
    if (view === 'list') {
      loadSessions(page);
    }
  }, [view, page, loadSessions]);

  // ── 打开编辑视图（新建） ─────────────────────────────────────────────────────
  function handleNew() {
    setCurrentSession(null);
    setTitle('');
    setParsedFields({});
    setMaterialScripts([]);
    setStreamResult('');
    setView('edit');
  }

  // ── 打开编辑视图（已有草稿） ──────────────────────────────────────────────────
  function handleOpenEdit(session: RetrospectiveSession) {
    setCurrentSession(session);
    setTitle(session.title);
    setParsedFields({
      live_data: session.live_data ?? undefined,
      material_data: session.material_data ?? undefined,
      review_text: session.review_text ?? undefined,
      live_script: session.live_script ?? undefined,
    });
    setMaterialScripts(session.material_scripts ?? []);
    setStreamResult('');
    setView('edit');
  }

  // ── 打开详情视图 ─────────────────────────────────────────────────────────────
  function handleOpenDetail(session: RetrospectiveSession) {
    setCurrentSession(session);
    setView('detail');
  }

  // ── 卡片点击 ─────────────────────────────────────────────────────────────────
  function handleCardClick(session: RetrospectiveSession) {
    if (session.result) {
      handleOpenDetail(session);
    } else {
      handleOpenEdit(session);
    }
  }

  // ── 删除会话 ─────────────────────────────────────────────────────────────────
  async function handleDelete(id: number) {
    try {
      await deleteSession(kolId, id);
      message.success('已删除');
      loadSessions(page);
    } catch (err: unknown) {
      message.error((err as Error).message || '删除失败');
    }
  }

  // ── 文件上传 + 解析 ──────────────────────────────────────────────────────────
  async function handleFileChange(field: MaterialKey, files: FileList | null) {
    if (!files || files.length === 0) return;
    const fileArr = Array.from(files);
    setUploading((prev) => ({ ...prev, [field]: true }));
    try {
      const { text } = await parseFiles(kolId, fileArr);
      if (field === 'material_scripts') {
        const newScripts = fileArr.map((f, i) => ({
          name: f.name,
          text: i === 0 ? text : '',
        }));
        setMaterialScripts((prev) => [...prev, ...newScripts]);
      } else {
        setParsedFields((prev) => ({ ...prev, [field]: text }));
      }
      message.success(`${MATERIAL_FIELDS.find((f) => f.key === field)?.label ?? ''} 解析成功`);
    } catch (err: unknown) {
      message.error((err as Error).message || '文件解析失败');
    } finally {
      setUploading((prev) => ({ ...prev, [field]: false }));
    }
  }

  // ── 保存草稿 ─────────────────────────────────────────────────────────────────
  async function handleSaveDraft() {
    if (!title.trim()) {
      message.warning('请输入场次标题');
      return;
    }
    setSaving(true);
    try {
      const data = buildSessionData('draft');
      const saved = await saveSession(kolId, data);
      setCurrentSession(saved);
      message.success('草稿已保存');
    } catch (err: unknown) {
      message.error((err as Error).message || '保存失败');
    } finally {
      setSaving(false);
    }
  }

  // ── 构建 session 数据 ─────────────────────────────────────────────────────────
  function buildSessionData(status: 'draft' | 'done', result?: string): Partial<RetrospectiveSession> {
    return {
      ...(currentSession?.id ? { id: currentSession.id } : {}),
      title: title.trim(),
      status,
      live_data: parsedFields.live_data ?? null,
      material_data: parsedFields.material_data ?? null,
      review_text: parsedFields.review_text ?? null,
      live_script: parsedFields.live_script ?? null,
      material_scripts: materialScripts.length > 0 ? materialScripts : null,
      ...(result !== undefined ? { result } : {}),
    };
  }

  // ── 开始复盘分析 ─────────────────────────────────────────────────────────────
  async function handleAnalyze() {
    if (!title.trim()) {
      message.warning('请输入场次标题');
      return;
    }
    setAnalyzing(true);
    setStreamResult('');
    try {
      // 1. 保存草稿，获取 sessionId
      const draftData = buildSessionData('draft');
      const saved = await saveSession(kolId, draftData);
      setCurrentSession(saved);

      // 2. 流式分析
      let fullResult = '';
      await analyzeStream(kolId, saved.id, (text) => {
        fullResult = text;
        setStreamResult(text);
      });

      // 3. 保存最终结果
      const finalData = buildSessionData('done', fullResult);
      const finalSaved = await saveSession(kolId, { ...finalData, id: saved.id });
      setCurrentSession(finalSaved);

      // 4. 切换到详情视图
      setView('detail');
      message.success('复盘分析完成');
    } catch (err: unknown) {
      message.error((err as Error).message || '分析失败，请重试');
    } finally {
      setAnalyzing(false);
    }
  }

  // ── 导出 Word ─────────────────────────────────────────────────────────────────
  async function handleExportWord() {
    if (!currentSession) return;
    setExporting(true);
    try {
      const blob = await exportWord(kolId, currentSession.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${currentSession.title || '复盘'}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      message.error((err as Error).message || '导出失败');
    } finally {
      setExporting(false);
    }
  }

  // ── 复制全文 ─────────────────────────────────────────────────────────────────
  async function handleCopy() {
    if (!currentSession?.result) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(currentSession.result);
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败，请手动复制');
    } finally {
      setCopying(false);
    }
  }

  // ── 重新复盘 ─────────────────────────────────────────────────────────────────
  function handleReanalyze() {
    if (!currentSession) return;
    handleOpenEdit(currentSession);
  }

  // ── 时间格式化 ───────────────────────────────────────────────────────────────
  function formatTime(iso: string | null) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  // ===========================================================================
  // 视图 1 — 历史列表
  // ===========================================================================
  if (view === 'list') {
    return (
      <div>
        <div className="page-header">
          <div>
            <h1 className="page-title">复盘记录</h1>
            <p className="page-desc">管理达人直播复盘分析记录</p>
          </div>
          <div className="page-actions">
            <button className="btn btn-primary" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 4 }} />
              新建复盘
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            {listLoading ? (
              <div className="empty-state">
                <div className="empty-state-text">加载中...</div>
              </div>
            ) : sessions.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <InboxOutlined />
                </div>
                <div className="empty-state-text">暂无复盘记录，点击「新建复盘」开始</div>
              </div>
            ) : (
              <>
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    data-testid={`session-card-${s.id}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: 'var(--sp-4) var(--sp-5)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border)',
                      marginBottom: 'var(--sp-3)',
                      background: 'var(--bg-surface)',
                      cursor: 'pointer',
                      transition: 'box-shadow 0.15s',
                    }}
                    onClick={() => handleCardClick(s)}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.boxShadow = 'none';
                    }}
                  >
                    {/* 状态 badge */}
                    <span
                      className={`badge ${s.status === 'done' ? 'badge-success' : 'badge-warning'}`}
                      style={{ marginRight: 'var(--sp-4)', flexShrink: 0 }}
                    >
                      {s.status === 'done' ? '已完成' : '草稿'}
                    </span>

                    {/* 标题 */}
                    <span
                      style={{
                        flex: 1,
                        fontWeight: 600,
                        fontSize: 14,
                        color: 'var(--gray-800)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {s.title || '（未命名）'}
                    </span>

                    {/* 时间 */}
                    <span style={{ fontSize: 12, color: 'var(--gray-400)', marginRight: 'var(--sp-5)', flexShrink: 0 }}>
                      {formatTime(s.updated_at ?? s.created_at)}
                    </span>

                    {/* 删除按钮 */}
                    <Popconfirm
                      title="确认删除这条复盘记录？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDelete(s.id);
                      }}
                      onPopupClick={(e) => e.stopPropagation()}
                    >
                      <button
                        data-testid={`delete-btn-${s.id}`}
                        className="btn btn-danger-ghost btn-sm"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <DeleteOutlined />
                      </button>
                    </Popconfirm>
                  </div>
                ))}

                {/* 分页 */}
                {totalPages > 1 && (
                  <div className="pagination">
                    <button
                      className={`page-btn${page <= 1 ? ' disabled' : ''}`}
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      上一页
                    </button>
                    <span style={{ padding: '0 var(--sp-4)', color: 'var(--gray-500)', fontSize: 13 }}>
                      {page} / {totalPages}
                    </span>
                    <button
                      className={`page-btn${page >= totalPages ? ' disabled' : ''}`}
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      下一页
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // 视图 2 — 编辑/分析
  // ===========================================================================
  if (view === 'edit') {
    return (
      <div>
        {/* 返回 */}
        <div style={{ marginBottom: 'var(--sp-5)' }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setView('list');
              loadSessions(page);
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <ArrowLeftOutlined />
            复盘记录
          </button>
        </div>

        <div className="card">
          <div className="card-header">
            <h2 className="card-title">{currentSession ? '编辑复盘' : '新建复盘'}</h2>
          </div>
          <div className="card-body">
            {/* 场次标题 */}
            <div style={{ marginBottom: 'var(--sp-5)' }}>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, color: 'var(--gray-700)', marginBottom: 'var(--sp-2)' }}>
                场次标题 <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                data-testid="title-input"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例：0608 Biodance 直播"
                style={{
                  width: '100%',
                  padding: '8px var(--sp-3)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 14,
                  fontFamily: 'var(--font-sans)',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* 上传材料 */}
            <div style={{ marginBottom: 'var(--sp-6)' }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-700)', marginBottom: 'var(--sp-3)' }}>
                上传材料
              </div>
              <div
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                }}
              >
                {MATERIAL_FIELDS.map((field, idx) => {
                  const isParsed =
                    field.key === 'material_scripts'
                      ? materialScripts.length > 0
                      : !!parsedFields[field.key];
                  const isUploading = uploading[field.key];
                  return (
                    <div
                      key={field.key}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        padding: 'var(--sp-4) var(--sp-5)',
                        background: idx % 2 === 0 ? 'var(--bg-muted)' : 'var(--bg-surface)',
                        borderBottom: idx < MATERIAL_FIELDS.length - 1 ? '1px solid var(--border)' : 'none',
                        gap: 'var(--sp-4)',
                      }}
                    >
                      {/* 状态点 */}
                      <span
                        className={`step-dot ${isParsed ? 'success' : 'pending'}`}
                        style={{ flexShrink: 0 }}
                      />

                      {/* 标签 */}
                      <span style={{ flex: 1, fontSize: 13, color: 'var(--gray-700)', fontWeight: 500 }}>
                        {field.label}
                        <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--gray-400)' }}>
                          {field.accept.replace(/\./g, '').toUpperCase()}
                          {field.multiple ? '（多文件）' : ''}
                        </span>
                      </span>

                      {/* 已解析信息 */}
                      {isParsed && (
                        <span
                          className="badge badge-success"
                          style={{ fontSize: 11 }}
                        >
                          {field.key === 'material_scripts'
                            ? `已上传 ${materialScripts.length} 份`
                            : '已解析'}
                        </span>
                      )}

                      {/* 上传按钮 */}
                      <input
                        data-testid={`file-input-${field.key}`}
                        ref={(el) => { fileInputRefs.current[field.key] = el; }}
                        type="file"
                        accept={field.accept}
                        multiple={field.multiple}
                        style={{ display: 'none' }}
                        onChange={(e) => handleFileChange(field.key, e.target.files)}
                      />
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={isUploading}
                        onClick={() => fileInputRefs.current[field.key]?.click()}
                      >
                        {isUploading ? '解析中...' : isParsed ? '重新上传' : '上传文件'}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 流式分析进度 */}
            {(analyzing || streamResult) && (
              <div
                data-testid="stream-result"
                style={{
                  background: 'var(--bg-muted)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--sp-5)',
                  marginBottom: 'var(--sp-5)',
                  maxHeight: 400,
                  overflowY: 'auto',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-600)', marginBottom: 'var(--sp-3)' }}>
                  {analyzing ? '正在生成复盘分析...' : '分析完成'}
                </div>
                <pre
                  style={{
                    fontFamily: 'var(--font-sans)',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.8,
                    fontSize: 13,
                    color: 'var(--gray-700)',
                    margin: 0,
                  }}
                >
                  {streamResult}
                  {analyzing && (
                    <span style={{ display: 'inline-block', width: 8, height: 14, background: 'var(--brand)', animation: 'blink 1s step-end infinite', verticalAlign: 'text-bottom' }} />
                  )}
                </pre>
              </div>
            )}

            {/* 操作按钮 */}
            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button
                data-testid="save-draft-btn"
                className="btn btn-ghost"
                disabled={saving || analyzing}
                onClick={handleSaveDraft}
              >
                {saving ? '保存中...' : '保存草稿'}
              </button>
              <button
                data-testid="analyze-btn"
                className="btn btn-primary"
                disabled={analyzing || saving}
                onClick={handleAnalyze}
              >
                {analyzing ? '分析中...' : '开始复盘分析 →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // 视图 3 — 详情
  // ===========================================================================
  if (view === 'detail' && currentSession) {
    return (
      <div>
        {/* 返回面包屑 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-5)' }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setView('list');
              loadSessions(page);
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <ArrowLeftOutlined />
            复盘记录
          </button>
          <span style={{ color: 'var(--gray-400)', fontSize: 13 }}>/</span>
          <span style={{ fontSize: 13, color: 'var(--gray-600)', fontWeight: 500 }}>
            {currentSession.title}
          </span>
        </div>

        <div className="card">
          <div className="card-header">
            <h2 className="card-title">{currentSession.title}</h2>
            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button
                data-testid="reanalyze-btn"
                className="btn btn-ghost btn-sm"
                onClick={handleReanalyze}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                <RedoOutlined />
                重新复盘
              </button>
              <button
                data-testid="export-word-btn"
                className="btn btn-ghost btn-sm"
                disabled={exporting}
                onClick={handleExportWord}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                <DownloadOutlined />
                {exporting ? '导出中...' : '导出 Word'}
              </button>
              <button
                data-testid="copy-btn"
                className="btn btn-ghost btn-sm"
                disabled={copying}
                onClick={handleCopy}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                <CopyOutlined />
                {copying ? '复制中...' : '复制全文'}
              </button>
            </div>
          </div>
          <div className="card-body">
            {currentSession.result ? (
              <SimpleMarkdown content={currentSession.result} />
            ) : (
              <div className="empty-state">
                <div className="empty-state-text">暂无复盘结果</div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
