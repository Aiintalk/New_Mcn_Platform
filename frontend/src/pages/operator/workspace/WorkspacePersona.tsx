/**
 * WorkspacePersona — 人物档案编辑器（5 分区）
 *
 * 5 分区：基本身份 / 真实经历 / 关系网 / 独家经历 / 其他补充
 * 交互：悬停显示编辑按钮 → 点击展开 TextArea → 保存/取消
 * API：GET/PUT /api/operator/kols/{kolId}/persona-details
 */
import { useState, useEffect, useCallback } from 'react';
import { App } from 'antd';
import { getPersonaDetails, updatePersonaDetails } from '../../../api/kolWorkspace';
import type { PersonaDetails } from '../../../types/kolWorkspace';

interface WorkspacePersonaProps {
  kolId: number;
}

interface SectionConfig {
  key: keyof Omit<PersonaDetails, 'kol_id' | 'updated_at'>;
  title: string;
  hint: string;
}

const SECTIONS: SectionConfig[] = [
  { key: 'background',    title: '基本身份',   hint: '年龄、职业、背景、性格' },
  { key: 'experience',    title: '真实经历',   hint: '可替换脚本人物经历的素材' },
  { key: 'relationships', title: '关系网',     hint: '朋友/闺蜜/家人名单，替换脚本人名' },
  { key: 'unique_story',  title: '独家经历',   hint: '只有该达人有的人生故事，越细越好' },
  { key: 'extra_notes',   title: '其他补充',   hint: '习惯、口头禅、禁区' },
];

export default function WorkspacePersona({ kolId }: WorkspacePersonaProps) {
  const { message } = App.useApp();
  const [details, setDetails] = useState<PersonaDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 每个分区的编辑状态
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);

  // 鼠标悬停的分区
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getPersonaDetails(kolId);
      setDetails(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载人物档案失败';
      setError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [kolId, message]);

  useEffect(() => {
    load();
  }, [load]);

  function handleEdit(key: string, currentValue: string | null) {
    setEditingKey(key);
    setEditValue(currentValue ?? '');
  }

  function handleCancel() {
    setEditingKey(null);
    setEditValue('');
  }

  async function handleSave(key: keyof Omit<PersonaDetails, 'kol_id' | 'updated_at'>) {
    setSaving(true);
    try {
      const updated = await updatePersonaDetails(kolId, { [key]: editValue });
      setDetails(updated);
      setEditingKey(null);
      setEditValue('');
      message.success('保存成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">加载中...</div>
      </div>
    );
  }

  if (error && !details) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">{error}</div>
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ marginTop: 'var(--sp-3)' }}>
          重试
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">人物档案</h1>
          <p className="page-desc">记录达人的真实背景、经历与关系网，用于脚本仿写替换</p>
        </div>
      </div>

      {SECTIONS.map((section) => {
        const value = details?.[section.key] ?? null;
        const isEditing = editingKey === section.key;
        const isHovered = hoveredKey === section.key;

        return (
          <div
            key={section.key}
            className="card"
            style={{ marginBottom: 'var(--sp-4)', position: 'relative' }}
            onMouseEnter={() => setHoveredKey(section.key)}
            onMouseLeave={() => setHoveredKey(null)}
          >
            <div className="card-body">
              {/* 分区标题 + hint */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
                <div>
                  <div className="card-title" style={{ marginBottom: 2 }}>{section.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>{section.hint}</div>
                </div>
                {/* 编辑按钮：悬停且非编辑状态时显示 */}
                {(isHovered || isEditing) && !isEditing && (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleEdit(section.key, value)}
                    style={{ flexShrink: 0, marginLeft: 'var(--sp-2)' }}
                  >
                    编辑
                  </button>
                )}
              </div>

              {/* 内容区 */}
              {isEditing ? (
                <div>
                  <textarea
                    rows={6}
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    style={{
                      width: '100%',
                      padding: 'var(--sp-3)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border)',
                      fontSize: 14,
                      lineHeight: 1.6,
                      fontFamily: 'var(--font-sans)',
                      resize: 'vertical',
                      outline: 'none',
                      boxSizing: 'border-box',
                      color: 'var(--gray-800)',
                      background: 'var(--bg-card)',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--brand)'; }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; }}
                  />
                  <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSave(section.key)}
                      disabled={saving}
                    >
                      {saving ? '保存中...' : '保存'}
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={handleCancel} disabled={saving}>
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    fontSize: 14,
                    lineHeight: 1.8,
                    color: value ? 'var(--gray-700)' : 'var(--gray-400)',
                    whiteSpace: 'pre-wrap',
                    minHeight: 40,
                    padding: 'var(--sp-2) 0',
                    cursor: 'text',
                  }}
                  onClick={() => handleEdit(section.key, value)}
                >
                  {value || '暂未填写，点击编辑'}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* 底部更新时间 */}
      {details?.updated_at && (
        <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 'var(--sp-2)' }}>
          上次更新：{new Date(details.updated_at).toLocaleString('zh-CN')}
        </div>
      )}
    </div>
  );
}
