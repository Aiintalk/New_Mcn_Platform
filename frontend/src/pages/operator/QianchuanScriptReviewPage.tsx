import { useState, useEffect, useRef } from 'react';
import { Select, Spin, App, Tag, Typography } from 'antd';
import { submitReview, saveOutput } from '../../api/scriptReview';
import { getQianchuanProducts } from '../../api/qianchuanProducts';
import type { ScriptType, ReviewResult, ReviewResponse, ReviewRating } from '../../types/scriptReview';
import type { QianchuanProduct } from '../../types/kolWorkspace';
import type { Output } from '../../types/output';
import OutputHistoryDrawer from '../../components/OutputHistoryDrawer';

const { Text, Paragraph } = Typography;

const RATING_CONFIG: Record<ReviewRating, { bg: string; color: string; label: string }> = {
  pass:  { bg: 'var(--success-bg)', color: 'var(--success)', label: '✅ 通过，可以上线' },
  minor: { bg: 'var(--warning-bg)', color: 'var(--warning)', label: '⚠️ 小改可上线' },
  fail:  { bg: 'var(--danger-bg)',  color: 'var(--danger)',  label: '❌ 需要大改' },
};

function isReviewResponse(value: unknown): value is ReviewResponse {
  if (!value || typeof value !== 'object') return false;
  const result = value as Record<string, unknown>;
  if (!Number.isInteger(result.task_id) || !['pass', 'minor', 'fail'].includes(String(result.rating))) return false;
  if (!Array.isArray(result.must_fix) || !Array.isArray(result.suggestions) || !Array.isArray(result.passed)) return false;
  if (!result.suggestions.every(item => typeof item === 'string') || !result.passed.every(item => typeof item === 'string')) return false;
  return result.must_fix.every(item => {
    if (!item || typeof item !== 'object') return false;
    const detail = item as Record<string, unknown>;
    return ['type', 'quote', 'fix'].every(key => typeof detail[key] === 'string' && String(detail[key]).trim().length > 0);
  });
}

export function QianchuanScriptReviewModule() {
  const { message } = App.useApp();
  const [scriptType, setScriptType] = useState<ScriptType>('direct');
  const [originalScript, setOriginalScript] = useState('');
  const [adaptedScript, setAdaptedScript] = useState('');
  const [products, setProducts] = useState<QianchuanProduct[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<QianchuanProduct | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [reviewError, setReviewError] = useState('');

  // History drawer + save
  const [saving, setSaving] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const inputRevisionRef = useRef(0);

  function invalidateReviewResult() {
    inputRevisionRef.current += 1;
    setResult(null);
    setReviewError('');
  }

  useEffect(() => {
    if (scriptType === 'direct') {
      getQianchuanProducts({ page_size: 100 })
        .then((resp) => setProducts(resp.items ?? []))
        .catch(() => {});
    }
  }, [scriptType]);

  async function handleReview() {
    if (!originalScript.trim() || !adaptedScript.trim()) return;
    setReviewing(true);
    setResult(null);
    setReviewError('');
    const inputRevision = inputRevisionRef.current;
    try {
      const product =
        scriptType === 'direct' && selectedProduct
          ? {
              nickname: selectedProduct.nickname,
              mechanism: selectedProduct.mechanism ?? undefined,
              core_selling_point: selectedProduct.core_selling_point ?? undefined,
            }
          : null;
      const res = await submitReview({
        script_type: scriptType,
        original_script: originalScript,
        adapted_script: adaptedScript,
        product,
      });
      if (!isReviewResponse(res)) throw new Error('审核结果结构异常，请重新审核');
      if (inputRevision !== inputRevisionRef.current) return;
      setResult(res);
    } catch (err: unknown) {
      if (inputRevision !== inputRevisionRef.current) return;
      const errorMessage = err instanceof Error ? err.message : '审核请求失败';
      setReviewError(errorMessage);
      message.error(errorMessage);
    } finally {
      setReviewing(false);
    }
  }

  async function handleSave() {
    if (!result || !adaptedScript.trim()) {
      message.warning('请先完成预审再保存');
      return;
    }
    setSaving(true);
    try {
      const titlePreview = adaptedScript.slice(0, 20).replace(/\n/g, ' ');
      const { task_id, ...contentJson } = result;
      await saveOutput({
        task_id,
        content: adaptedScript,
        content_json: contentJson,
        title: `脚本预审 [${result.rating}] · ${titlePreview}...`,
      });
      message.success('已保存到历史');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  /** 历史抽屉自定义渲染：展示评分 + 必须修改数 */
  function renderHistoryItem(item: Output) {
    const review = item.content_json as ReviewResult | undefined;
    const ratingLabel = review?.rating ? RATING_CONFIG[review.rating].label : '';
    return (
      <div style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <Text strong>{item.title || `#${item.id}`}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(item.created_at).toLocaleString('zh-CN')}
          </Text>
        </div>
        {ratingLabel && (
          <Tag
            color={
              review?.rating === 'pass' ? 'success' :
              review?.rating === 'minor' ? 'warning' : 'error'
            }
            style={{ marginBottom: 6 }}
          >
            {ratingLabel}
          </Tag>
        )}
        {review?.must_fix && review.must_fix.length > 0 && (
          <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>
            必须修改 {review.must_fix.length} 条
          </div>
        )}
        <Paragraph
          type="secondary"
          ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
          style={{ marginBottom: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}
        >
          {item.content ?? ''}
        </Paragraph>
      </div>
    );
  }

  const canSubmit = originalScript.trim().length > 0 && adaptedScript.trim().length > 0;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川脚本预审</h1>
          <p className="page-desc">AI 对比审核原版与仿写脚本，输出结构化改进意见</p>
        </div>
      </div>

      {/* 脚本类型切换 */}
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: 'var(--gray-600)', marginRight: 'var(--sp-2)' }}>脚本类型：</span>
            <button
              className={`btn btn-sm ${scriptType === 'direct' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => { setScriptType('direct'); invalidateReviewResult(); }}
            >
              千川直销
            </button>
            <button
              className={`btn btn-sm ${scriptType === 'value' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => { setScriptType('value'); setSelectedProduct(null); invalidateReviewResult(); }}
            >
              价值观内容
            </button>
          </div>
        </div>
      </div>

      {/* 产品选择（仅 direct 模式） */}
      {scriptType === 'direct' && (
        <div className="card">
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
              <span style={{ fontSize: 13, color: 'var(--gray-600)', flexShrink: 0 }}>关联产品（可选）：</span>
              <Select
                style={{ width: 320 }}
                placeholder="从千川产品库选择，用于校验卖点"
                allowClear
                value={selectedProduct?.id ?? null}
                onChange={(val) => {
                  const p = products.find((x) => x.id === val) ?? null;
                  setSelectedProduct(p);
                  invalidateReviewResult();
                }}
                options={products.map((p) => ({
                  value: p.id,
                  label: p.nickname,
                }))}
              />
              {selectedProduct && (
                <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>
                  {selectedProduct.core_selling_point
                    ? `核心卖点：${selectedProduct.core_selling_point.slice(0, 30)}...`
                    : '暂无卖点信息'}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 双栏脚本输入 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <h2 className="card-title">原版脚本</h2>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{originalScript.length} 字</span>
          </div>
          <div className="card-body">
            <textarea
              value={originalScript}
              onChange={(e) => { setOriginalScript(e.target.value); invalidateReviewResult(); }}
              rows={14}
              placeholder="粘贴原版千川脚本..."
              style={{
                width: '100%',
                resize: 'vertical',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                lineHeight: 1.7,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--sp-3)',
                outline: 'none',
                color: 'var(--gray-800)',
                background: 'var(--bg-surface)',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <h2 className="card-title">仿写脚本</h2>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{adaptedScript.length} 字</span>
          </div>
          <div className="card-body">
            <textarea
              value={adaptedScript}
              onChange={(e) => { setAdaptedScript(e.target.value); invalidateReviewResult(); }}
              rows={14}
              placeholder="粘贴待审核的仿写脚本..."
              style={{
                width: '100%',
                resize: 'vertical',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                lineHeight: 1.7,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--sp-3)',
                outline: 'none',
                color: 'var(--gray-800)',
                background: 'var(--bg-surface)',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>
      </div>

      {/* 提交按钮 */}
      <div style={{ textAlign: 'center', marginBottom: 'var(--sp-6)' }}>
        <button
          className="btn btn-primary"
          disabled={!canSubmit || reviewing}
          onClick={handleReview}
          style={{ minWidth: 160 }}
        >
          {reviewing ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Spin size="small" />
              AI 审核中...
            </span>
          ) : '🔍 开始预审'}
        </button>
      </div>

      {reviewError && (
        <div role="alert" style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', borderRadius: 'var(--radius-md)', padding: '12px 14px', color: 'var(--danger)', marginBottom: 'var(--sp-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{reviewError}</span>
          <button className="btn btn-ghost btn-sm" onClick={handleReview} disabled={!canSubmit || reviewing}>重新审核</button>
        </div>
      )}

      {/* 审核结果 */}
      {result && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">审核结果</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setHistoryOpen(true)}
              >
                历史记录
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? '保存中...' : '保存到历史'}
              </button>
            </div>
          </div>
          <div className="card-body">
            {/* 评级 Banner */}
            <div
              style={{
                background: RATING_CONFIG[result.rating].bg,
                borderRadius: 'var(--radius-md)',
                padding: 'var(--sp-4) var(--sp-5)',
                marginBottom: 'var(--sp-5)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--sp-3)',
              }}
            >
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: RATING_CONFIG[result.rating].color,
                }}
              >
                {RATING_CONFIG[result.rating].label}
              </span>
            </div>

            {/* 必须修改 */}
            {result.must_fix.length > 0 && (
              <div style={{ marginBottom: 'var(--sp-5)' }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--danger)',
                    marginBottom: 'var(--sp-3)',
                  }}
                >
                  ❌ 必须修改（{result.must_fix.length} 条）
                </div>
                {result.must_fix.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      background: 'var(--danger-bg)',
                      border: '1px solid rgba(220,38,38,0.2)',
                      borderRadius: 'var(--radius-sm)',
                      padding: 'var(--sp-3) var(--sp-4)',
                      marginBottom: 'var(--sp-2)',
                      fontSize: 13,
                      lineHeight: 1.7,
                    }}
                  >
                    <span style={{ fontWeight: 600, color: 'var(--danger)' }}>[{item.type}]</span>
                    {' '}「{item.quote}」
                    <span style={{ color: 'var(--gray-500)', margin: '0 6px' }}>→</span>
                    <span style={{ color: 'var(--gray-800)' }}>{item.fix}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 建议优化 */}
            {result.suggestions.length > 0 && (
              <div style={{ marginBottom: 'var(--sp-5)' }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--warning)',
                    marginBottom: 'var(--sp-3)',
                  }}
                >
                  ⚠️ 建议优化
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 'var(--sp-5)',
                    fontSize: 13,
                    lineHeight: 1.8,
                    color: 'var(--gray-700)',
                  }}
                >
                  {result.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* 已通过 */}
            {result.passed.length > 0 && (
              <div>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--success)',
                    marginBottom: 'var(--sp-3)',
                  }}
                >
                  ✅ 已通过
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
                  {result.passed.map((p, i) => (
                    <span key={i} className="badge badge-success">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <OutputHistoryDrawer
        toolCode="qianchuan-script-review"
        toolName="千川脚本预审"
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        renderItem={renderHistoryItem}
      />
    </div>
  );
}

export default function QianchuanScriptReviewPage() {
  return <QianchuanScriptReviewModule />;
}
