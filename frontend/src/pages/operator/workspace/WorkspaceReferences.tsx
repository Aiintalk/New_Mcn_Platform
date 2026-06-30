/**
 * WorkspaceReferences — 6 类素材库管理
 *
 * 两视图切换：
 *   - 分类首页：2 组 × 3 块卡片（人设仿写 / 千川仿写）
 *   - 类型视图：添加表单 + 列表（可折叠/展开，可删除）
 *
 * API：GET/POST /api/tools/seeding-writer/references
 *      DELETE  /api/tools/seeding-writer/references/{id}
 */
import { useState, useEffect, useCallback } from 'react';
import { Popconfirm, App } from 'antd';
import {
  FileTextOutlined,
  HeartOutlined,
  StarOutlined,
  ThunderboltOutlined,
  FireOutlined,
  CrownOutlined,
} from '@ant-design/icons';
import { get, post, del } from '../../../api/request';

interface WorkspaceReferencesProps {
  kolId: number;
}

interface Reference {
  id: number;
  kol_id: number | null;
  title: string;
  content: string;
  type: string | null;
  likes: number | null;
  created_at: string | null;
}

interface TypeGroup {
  group: string;
  types: { type: string; icon: React.ReactNode; color: string }[];
}

const TYPE_GROUPS: TypeGroup[] = [
  {
    group: '人设仿写素材',
    types: [
      { type: '红人爆款文案',   icon: <FireOutlined />,       color: 'var(--danger)' },
      { type: '红人喜欢的内容', icon: <HeartOutlined />,      color: 'var(--pink)' },
      { type: '风格参考',       icon: <StarOutlined />,       color: 'var(--brand)' },
    ],
  },
  {
    group: '千川仿写素材',
    types: [
      { type: '千川爆款文案',   icon: <ThunderboltOutlined />, color: 'var(--warning)' },
      { type: '千川喜欢的内容', icon: <CrownOutlined />,       color: 'var(--purple)' },
      { type: '千川风格参考',   icon: <FileTextOutlined />,    color: 'var(--info)' },
    ],
  },
];

// 所有类型的图标和颜色（用于类型视图顶部）
const TYPE_META: Record<string, { icon: React.ReactNode; color: string }> = {};
TYPE_GROUPS.forEach((g) => {
  g.types.forEach((t) => {
    TYPE_META[t.type] = { icon: t.icon, color: t.color };
  });
});

function getTypeColor(type: string): string {
  return TYPE_META[type]?.color ?? 'var(--brand)';
}

export default function WorkspaceReferences({ kolId }: WorkspaceReferencesProps) {
  const { message } = App.useApp();
  const [activeType, setActiveType] = useState<string | null>(null);
  const [references, setReferences] = useState<Reference[]>([]);
  const [loading, setLoading] = useState(false);

  // 添加表单
  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState('');
  const [formContent, setFormContent] = useState('');
  const [formLikes, setFormLikes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 折叠状态（存每条 ref 的 id）
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const loadReferences = useCallback(async () => {
    setLoading(true);
    try {
      const data = await get<Reference[]>('/api/tools/seeding-writer/references', { kol_id: kolId });
      setReferences(data);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载素材库失败');
    } finally {
      setLoading(false);
    }
  }, [kolId, message]);

  useEffect(() => {
    loadReferences();
  }, [loadReferences]);

  // 按类型过滤
  const filteredRefs = activeType
    ? references.filter((r) => r.type === activeType)
    : [];

  // 每种类型的数量（分类首页用）
  function countByType(type: string): number {
    return references.filter((r) => r.type === type).length;
  }

  // 重置表单
  function resetForm() {
    setFormTitle('');
    setFormContent('');
    setFormLikes('');
    setShowForm(false);
  }

  // 添加素材
  async function handleAdd() {
    if (!formTitle.trim()) { message.warning('请填写标题'); return; }
    if (!formContent.trim()) { message.warning('请填写正文'); return; }
    if (!activeType) return;
    setSubmitting(true);
    try {
      await post('/api/tools/seeding-writer/references', {
        kol_id: kolId,
        title: formTitle.trim(),
        content: formContent.trim(),
        type: activeType,
        likes: formLikes ? parseInt(formLikes, 10) : undefined,
      });
      message.success('素材已添加');
      resetForm();
      await loadReferences();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '添加失败');
    } finally {
      setSubmitting(false);
    }
  }

  // 删除素材
  async function handleDelete(id: number) {
    try {
      await del(`/api/tools/seeding-writer/references/${id}`);
      message.success('已删除');
      setReferences((prev) => prev.filter((r) => r.id !== id));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }

  // 折叠/展开
  function toggleExpand(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }

  // ── 类型视图 ──────────────────────────────────────────────────────────────
  if (activeType !== null) {
    const meta = TYPE_META[activeType];
    return (
      <div style={{ maxWidth: 800 }}>
        <div className="page-header">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 4 }}>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => { setActiveType(null); resetForm(); }}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                ← 返回
              </button>
            </div>
            <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <span style={{ color: getTypeColor(activeType) }}>{meta?.icon}</span>
              {activeType}
            </h1>
            <p className="page-desc">{filteredRefs.length} 条素材</p>
          </div>
          <div className="page-actions">
            {!showForm && (
              <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>
                + 添加
              </button>
            )}
          </div>
        </div>

        {/* 添加表单 */}
        {showForm && (
          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <div className="card-body">
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 'var(--sp-3)' }}>添加素材</div>
              <div style={{ marginBottom: 'var(--sp-2)' }}>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>
                  标题 <span style={{ color: 'var(--danger)' }}>*</span>
                </label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder="请输入标题"
                  style={{
                    width: '100%',
                    padding: 'var(--sp-2) var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    fontSize: 14,
                    fontFamily: 'var(--font-sans)',
                    boxSizing: 'border-box',
                    color: 'var(--gray-800)',
                  }}
                />
              </div>
              <div style={{ marginBottom: 'var(--sp-2)' }}>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>
                  点赞数（选填）
                </label>
                <input
                  type="number"
                  value={formLikes}
                  onChange={(e) => setFormLikes(e.target.value)}
                  placeholder="如 120000"
                  style={{
                    width: '100%',
                    padding: 'var(--sp-2) var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    fontSize: 14,
                    fontFamily: 'var(--font-sans)',
                    boxSizing: 'border-box',
                    color: 'var(--gray-800)',
                  }}
                />
              </div>
              <div style={{ marginBottom: 'var(--sp-3)' }}>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>
                  正文 <span style={{ color: 'var(--danger)' }}>*</span>
                </label>
                <textarea
                  rows={6}
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  placeholder="粘贴内容到这里..."
                  style={{
                    width: '100%',
                    padding: 'var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    fontSize: 14,
                    lineHeight: 1.6,
                    fontFamily: 'var(--font-sans)',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                    color: 'var(--gray-800)',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button className="btn btn-primary btn-sm" onClick={handleAdd} disabled={submitting}>
                  {submitting ? '保存中...' : '保存'}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={resetForm} disabled={submitting}>
                  取消
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 素材列表 */}
        {loading ? (
          <div className="empty-state">
            <div className="empty-state-text">加载中...</div>
          </div>
        ) : filteredRefs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📄</div>
            <div className="empty-state-text">暂无素材，点击「+ 添加」开始录入</div>
          </div>
        ) : (
          <div>
            {filteredRefs.map((ref) => {
              const isExpanded = expandedIds.has(ref.id);
              return (
                <div key={ref.id} className="card" style={{ marginBottom: 'var(--sp-3)' }}>
                  <div className="card-body">
                    {/* 标题行 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flex: 1, minWidth: 0 }}>
                        <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {ref.title}
                        </span>
                        {ref.likes != null && (
                          <span style={{ fontSize: 12, color: 'var(--gray-400)', flexShrink: 0 }}>
                            {ref.likes >= 10000 ? `${(ref.likes / 10000).toFixed(1)}万赞` : `${ref.likes}赞`}
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 'var(--sp-2)', flexShrink: 0, marginLeft: 'var(--sp-2)' }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => toggleExpand(ref.id)}
                          style={{ fontSize: 12 }}
                        >
                          {isExpanded ? '收起' : '展开'}
                        </button>
                        <Popconfirm
                          title="确认删除这条素材？"
                          onConfirm={() => handleDelete(ref.id)}
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                        >
                          <button className="btn btn-danger-ghost btn-sm">删除</button>
                        </Popconfirm>
                      </div>
                    </div>
                    {/* 内容（折叠/展开） */}
                    {isExpanded && (
                      <div
                        style={{
                          fontSize: 13,
                          lineHeight: 1.8,
                          color: 'var(--gray-700)',
                          whiteSpace: 'pre-wrap',
                          background: 'var(--bg-muted)',
                          borderRadius: 'var(--radius-md)',
                          padding: 'var(--sp-3)',
                          marginTop: 'var(--sp-2)',
                        }}
                      >
                        {ref.content}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // ── 分类首页 ──────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 800 }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">素材库</h1>
          <p className="page-desc">管理人设仿写与千川仿写的参考素材，点击分类进入</p>
        </div>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="empty-state-text">加载中...</div>
        </div>
      ) : (
        <div>
          {TYPE_GROUPS.map((group) => (
            <div key={group.group} style={{ marginBottom: 'var(--sp-6)' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 'var(--sp-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {group.group}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--sp-3)' }}>
                {group.types.map((t) => {
                  const count = countByType(t.type);
                  return (
                    <div
                      key={t.type}
                      className="card"
                      onClick={() => setActiveType(t.type)}
                      style={{
                        cursor: 'pointer',
                        transition: 'transform 0.15s, box-shadow 0.15s',
                        marginBottom: 0,
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.transform = 'translateY(-2px)';
                        (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-md)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.transform = '';
                        (e.currentTarget as HTMLElement).style.boxShadow = '';
                      }}
                    >
                      <div className="card-body" style={{ textAlign: 'center', padding: 'var(--sp-5)' }}>
                        <div style={{ fontSize: 28, color: t.color, marginBottom: 'var(--sp-2)' }}>
                          {t.icon}
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-800)', marginBottom: 'var(--sp-1)' }}>
                          {t.type}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
                          已有 {count} 条
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
