/**
 * 评测模块 — 共享 UI 原语（移植自 eval.css 视觉系统）
 *
 * 不重复造 Ant Design 已有的组件；这里只封装带业务语义的复合展示组件，
 * 保持视觉与设计稿一致（score-chip / weight-bar / status-badge / 等）。
 */
import type { CSSProperties, ReactNode } from 'react';
import type { EvalRunStatus, EvalTriggerType } from '../types';

/** 评分色阶 chip（hi ≥ 8 / mid ≥ 5 / lo < 5） */
export function ScoreChip({ score, max = 10 }: { score: number | null; max?: number }) {
  if (score === null || score === undefined) {
    return <span className="score-chip score-na">—</span>;
  }
  const cls = score >= 8 ? 'score-hi' : score >= 5 ? 'score-mid' : 'score-lo';
  return (
    <span className={`score-chip ${cls}`}>
      {score.toFixed(1)}
      <span style={{ opacity: 0.55, fontSize: 11, fontWeight: 400 }}>/{max}</span>
    </span>
  );
}

/** diff 指示器（▲/▼/→） */
export function DiffIndicator({ delta }: { delta: number | null }) {
  if (delta === null || Math.abs(delta) < 0.05) {
    return <span className="diff-flat">→ 0.0</span>;
  }
  if (delta > 0) {
    return (
      <span className="diff-up">
        ▲ +{delta.toFixed(1)}
      </span>
    );
  }
  return (
    <span className="diff-down">
      ▼ {delta.toFixed(1)}
    </span>
  );
}

/** 权重条（0–1 浮点显示） */
export function WeightBar({ weight }: { weight: number }) {
  const pct = Math.round(weight * 100);
  return (
    <div className="weight-bar">
      <div className="wb-track">
        <div className="wb-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="wb-pct">{pct}%</span>
    </div>
  );
}

/** 运行状态徽标（dot 风格） */
const RUN_STATUS_META: Record<EvalRunStatus, { text: string; cls: string }> = {
  pending: { text: 'pending', cls: 'badge-gray' },
  running: { text: 'running', cls: 'badge-warning' },
  completed: { text: 'completed', cls: 'badge-success' },
  failed: { text: 'failed', cls: 'badge-danger' },
  partial: { text: 'partial', cls: 'badge-warning' },
  cancelled: { text: 'cancelled', cls: 'badge-gray' },
};

export function RunStatusBadge({ status }: { status: EvalRunStatus }) {
  const meta = RUN_STATUS_META[status] ?? RUN_STATUS_META.pending;
  return (
    <span className={`badge dot ${meta.cls}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
      {meta.text}
    </span>
  );
}

/** 触发方式徽标 */
const TRIGGER_META: Record<EvalTriggerType, { text: string; cls: string }> = {
  manual: { text: '手动', cls: 'badge-gray' },
  auto: { text: '自动', cls: 'badge-info' },
  schedule: { text: '定时', cls: 'badge-brand' },
};

export function TriggerBadge({ trigger }: { trigger: EvalTriggerType }) {
  const meta = TRIGGER_META[trigger] ?? TRIGGER_META.manual;
  return (
    <span className={`badge ${meta.cls}`} style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 500, border: '1px solid transparent' }}>
      {meta.text}
    </span>
  );
}

/** 进度条（运行 / 完成 / 失败） */
export function ProgressBar({
  completed,
  total,
  variant = 'brand',
}: {
  completed: number;
  total: number;
  variant?: 'brand' | 'success' | 'warn' | 'danger';
}) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="cell-progress">
      <div className="bar-track">
        <div className={`bar-fill ${variant}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="pct">
        {completed}/{total}
      </span>
    </div>
  );
}

/** callout 提示框 */
export function Callout({
  variant = 'brand',
  icon = '!',
  children,
  style,
}: {
  variant?: 'brand' | 'info' | 'warn';
  icon?: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div className={`callout ${variant === 'brand' ? '' : variant}`} style={style}>
      <span className="callout-icon">{icon}</span>
      <div>{children}</div>
    </div>
  );
}

/** 标签徽标（彩色，按标签哈希挑色） */
const TAG_COLORS = ['badge-pink', 'badge-purple', 'badge-cyan', 'badge-info', 'badge-success', 'badge-warning', 'badge-danger', 'badge-brand'];
function hashTag(tag: string): string {
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) | 0;
  return TAG_COLORS[Math.abs(h) % TAG_COLORS.length];
}

export function TagBadge({ tag }: { tag: string }) {
  return (
    <span
      className={`badge ${hashTag(tag)}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        border: '1px solid transparent',
      }}
    >
      {tag}
    </span>
  );
}

/** ISO 时间字符串 → "MM-DD HH:mm" 简短显示 */
export function formatShortTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${mi}`;
}

/** 耗时（started_at → finished_at），格式 "MM:SS" */
export function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt || !finishedAt) return '—';
  const start = new Date(startedAt).getTime();
  const end = new Date(finishedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '—';
  const sec = Math.round((end - start) / 1000);
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

/** 通用页头（标题 + 描述 + 操作） */
export function PageHeader({
  title,
  titleTag,
  description,
  actions,
}: {
  title: string;
  titleTag?: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">
          {title}
          {titleTag ? <span className="title-tag">{titleTag}</span> : null}
        </h1>
        {description ? <p className="page-desc">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  );
}
