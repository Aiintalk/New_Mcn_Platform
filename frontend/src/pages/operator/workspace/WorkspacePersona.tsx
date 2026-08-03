/**
 * WorkspacePersona — 七字段达人档案唯一编辑入口
 *
 * 定位信息在前：人格档案 / 内容规划
 * 人物事实在后：基本身份 / 真实经历 / 关系网 / 独家经历 / 其他补充
 */
import { useCallback, useEffect, useState } from 'react';
import { App } from 'antd';
import {
  fillEmptyPersonaFacts,
  getPersonaDetails,
  updatePersonaDetails,
} from '../../../api/kolWorkspace';
import type { PersonaDetails, PersonaDetailsUpdate, PersonaField } from '../../../types/kolWorkspace';

interface WorkspacePersonaProps {
  kolId: number;
  kolName?: string;
}

interface FieldConfig {
  key: PersonaField;
  title: string;
  hint: string;
  rows: number;
}

const POSITIONING_FIELDS: FieldConfig[] = [
  { key: 'persona', title: '人格档案', hint: '人设定位、人物形象与表达原则', rows: 7 },
  { key: 'content_plan', title: '内容规划', hint: '选题方向、内容结构与创作策略', rows: 7 },
];

const FACT_FIELDS: FieldConfig[] = [
  { key: 'background', title: '基本身份', hint: '年龄、职业、背景、性格', rows: 5 },
  { key: 'experience', title: '真实经历', hint: '可以替换脚本人物经历的素材', rows: 7 },
  { key: 'relationships', title: '关系网', hint: '家人、朋友和长期关系线索', rows: 5 },
  { key: 'unique_story', title: '独家经历', hint: '只有这个红人拥有的人生故事', rows: 7 },
  { key: 'extra_notes', title: '其他补充', hint: '习惯、口头禅、禁区和表达约束', rows: 4 },
];

const FIELD_LABELS: Record<PersonaField, string> = Object.fromEntries(
  [...POSITIONING_FIELDS, ...FACT_FIELDS].map((field) => [field.key, field.title]),
) as Record<PersonaField, string>;

function fieldNames(fields: PersonaField[]) {
  return fields.map((field) => FIELD_LABELS[field]).join('、');
}

export default function WorkspacePersona({ kolId, kolName = '当前红人' }: WorkspacePersonaProps) {
  const { message } = App.useApp();
  const [details, setDetails] = useState<PersonaDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editingKey, setEditingKey] = useState<PersonaField | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [filling, setFilling] = useState(false);
  const [fillFeedback, setFillFeedback] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setDetails(await getPersonaDetails(kolId));
    } catch (err: unknown) {
      const text = err instanceof Error ? err.message : '加载人物档案失败';
      setError(text);
      message.error(text);
    } finally {
      setLoading(false);
    }
  }, [kolId, message]);

  useEffect(() => {
    load();
  }, [load]);

  function handleEdit(field: PersonaField) {
    setEditingKey(field);
    setEditValue(details?.[field] ?? '');
  }

  function handleCancel() {
    setEditingKey(null);
    setEditValue('');
  }

  async function handleSave(field: PersonaField) {
    setSaving(true);
    try {
      const update = { [field]: editValue } as unknown as PersonaDetailsUpdate;
      setDetails(await updatePersonaDetails(kolId, update));
      handleCancel();
      message.success(`${FIELD_LABELS[field]}已保存`);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleFillEmpty() {
    setFilling(true);
    setFillFeedback('');
    try {
      const result = await fillEmptyPersonaFacts(kolId);
      const filled = result.filled_fields.length > 0
        ? `已补全：${fieldNames(result.filled_fields)}`
        : '本次没有可补全字段';
      setFillFeedback(`${filled}；其他字段未改动`);
      await load();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '补全失败');
    } finally {
      setFilling(false);
    }
  }

  function renderField(field: FieldConfig) {
    const value = details?.[field.key] ?? '';
    const isEditing = editingKey === field.key;
    const isFilled = Boolean(value.trim());

    return (
      <article
        key={field.key}
        data-testid={`persona-field-${field.key}`}
        style={{
          width: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
          padding: 'var(--sp-5) 0',
          borderTop: '1px solid var(--border-light)',
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-4)', alignItems: 'flex-start', minWidth: 0 }}>
          <div style={{ flex: '1 1 30%', minWidth: 0 }}>
            <div className="card-title">{field.title}</div>
            <div className="page-desc">{field.hint}</div>
            <span className={`badge ${isFilled ? 'badge-success' : 'badge-gray'}`} style={{ marginTop: 'var(--sp-2)' }}>
              {isFilled ? '已填写' : '待补充'}
            </span>
          </div>

          <div style={{ flex: '2 1 60%', minWidth: 0 }}>
            {isEditing ? (
              <>
                <textarea
                  aria-label={`编辑${field.title}`}
                  rows={field.rows}
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  style={{
                    width: '100%',
                    minWidth: 0,
                    boxSizing: 'border-box',
                    padding: 'var(--sp-3)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)',
                    color: 'var(--gray-800)',
                    background: 'var(--bg-card)',
                    fontFamily: 'var(--font-sans)',
                    resize: 'vertical',
                  }}
                />
                <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)', flexWrap: 'wrap' }}>
                  <button className="btn btn-primary btn-sm" onClick={() => handleSave(field.key)} disabled={saving}>
                    {saving ? '保存中...' : '保存'}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={handleCancel} disabled={saving}>取消</button>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'flex-start', minWidth: 0 }}>
                <div style={{ flex: 1, minWidth: 0, whiteSpace: 'pre-wrap', color: isFilled ? 'var(--gray-700)' : 'var(--gray-400)' }}>
                  {isFilled ? value : '暂未填写'}
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => handleEdit(field.key)} disabled={saving} style={{ flexShrink: 0 }}>
                  编辑
                </button>
              </div>
            )}
          </div>
        </div>
      </article>
    );
  }

  if (loading && !details) {
    return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;
  }

  if (error && !details) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">{error}</div>
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ marginTop: 'var(--sp-3)' }}>重试</button>
      </div>
    );
  }

  const completion = details?.total_count
    ? `${details.filled_count}/${details.total_count}`
    : '0/7';
  const completionPercent = details?.total_count
    ? `${Math.round((details.filled_count / details.total_count) * 100)}%`
    : '0%';

  return (
    <div
      data-testid="workspace-persona-document"
      className="workspace-persona-document"
      style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box' }}
    >
      <header className="page-header" style={{ flexWrap: 'wrap', gap: 'var(--sp-4)' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h1 className="page-title">{kolName}人物档案</h1>
          <p className="page-desc">
            统一维护定位策略和脚本可用人物事实
            {details?.updated_at ? ` · 上次更新 ${new Date(details.updated_at).toLocaleString('zh-CN')}` : ''}
          </p>
        </div>
        <div style={{ minWidth: 0, flex: '0 1 30%' }}>
          <div className="card-title">档案完整度 {completion}</div>
          <div style={{ width: '100%', height: 'var(--sp-1)', marginTop: 'var(--sp-2)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', background: 'var(--gray-200)' }}>
            <span style={{ display: 'block', width: completionPercent, height: '100%', background: 'var(--brand)' }} />
          </div>
        </div>
      </header>

      <section className="card" style={{ width: '100%', minWidth: 0 }}>
        <div className="card-header" style={{ display: 'block' }}>
          <div className="card-title">定位与规划</div>
          <div className="page-desc">决定红人的人物形象、表达方向和内容策略。</div>
        </div>
        <div className="card-body">{POSITIONING_FIELDS.map(renderField)}</div>
      </section>

      <section className="card" style={{ width: '100%', minWidth: 0 }}>
        <div className="card-header" style={{ flexWrap: 'wrap', gap: 'var(--sp-3)' }}>
          <div style={{ minWidth: 0 }}>
            <div className="card-title">人物事实素材</div>
            <div className="page-desc">人工维护内容不会被最新人格报告覆盖。</div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={handleFillEmpty} disabled={filling}>
            {filling ? '补全中...' : '从最新人格报告补全空字段'}
          </button>
        </div>
        {fillFeedback && (
          <div style={{ margin: 'var(--sp-4) var(--sp-5) 0', padding: 'var(--sp-3)', border: '1px solid var(--brand-border)', borderRadius: 'var(--radius-sm)', background: 'var(--brand-light)', color: 'var(--gray-700)' }}>
            {fillFeedback}
          </div>
        )}
        <div className="card-body">{FACT_FIELDS.map(renderField)}</div>
      </section>
    </div>
  );
}
