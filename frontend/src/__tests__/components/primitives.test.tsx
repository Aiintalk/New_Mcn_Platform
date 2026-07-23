/**
 * 评测共享原语 primitives.tsx — 分支覆盖测试
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  ScoreChip,
  DiffIndicator,
  WeightBar,
  RunStatusBadge,
  TriggerBadge,
  ProgressBar,
  Callout,
  TagBadge,
  formatShortTime,
  formatDuration,
  PageHeader,
} from '../../evaluation/components/primitives';

function cls(html: HTMLElement, suffix: string) {
  return html.querySelector(`[class*="${suffix}"]`) !== null;
}

describe('ScoreChip', () => {
  it('null/undefined → score-na 占位', () => {
    const { container } = render(<ScoreChip score={null} />);
    expect(container.querySelector('.score-na')).toBeTruthy();
  });
  it('score ≥ 8 → score-hi', () => {
    const { container } = render(<ScoreChip score={9} />);
    expect(container.querySelector('.score-hi')).toBeTruthy();
  });
  it('5 ≤ score < 8 → score-mid', () => {
    const { container } = render(<ScoreChip score={6} />);
    expect(container.querySelector('.score-mid')).toBeTruthy();
  });
  it('score < 5 → score-lo', () => {
    const { container } = render(<ScoreChip score={3} />);
    expect(container.querySelector('.score-lo')).toBeTruthy();
  });
});

describe('DiffIndicator', () => {
  it('null 或 |delta|<0.05 → diff-flat', () => {
    const a = render(<DiffIndicator delta={null} />).container;
    expect(a.querySelector('.diff-flat')).toBeTruthy();
    const b = render(<DiffIndicator delta={0.01} />).container;
    expect(b.querySelector('.diff-flat')).toBeTruthy();
  });
  it('delta > 0 → diff-up', () => {
    const { container } = render(<DiffIndicator delta={0.5} />);
    expect(container.querySelector('.diff-up')).toBeTruthy();
  });
  it('delta < 0 → diff-down', () => {
    const { container } = render(<DiffIndicator delta={-0.5} />);
    expect(container.querySelector('.diff-down')).toBeTruthy();
  });
});

describe('WeightBar', () => {
  it('weight → 百分比', () => {
    const { container } = render(<WeightBar weight={0.4} />);
    expect(container.querySelector('.wb-pct')?.textContent).toBe('40%');
    expect(container.querySelector('.wb-fill')?.getAttribute('style')).toContain('width: 40%');
  });
});

describe('RunStatusBadge', () => {
  it.each(['pending', 'running', 'completed', 'failed', 'partial'] as const)('状态 %s 渲染对应徽标', (status) => {
    const { container } = render(<RunStatusBadge status={status} />);
    expect(container.querySelector('.badge')).toBeTruthy();
  });
});

describe('TriggerBadge', () => {
  it.each(['manual', 'auto', 'schedule'] as const)('触发 %s 渲染徽标', (trigger) => {
    const { container } = render(<TriggerBadge trigger={trigger} />);
    expect(container.querySelector('.badge')).toBeTruthy();
  });
});

describe('ProgressBar', () => {
  it('total>0 按比例渲染', () => {
    const { container } = render(<ProgressBar completed={7} total={10} variant="success" />);
    expect(container.querySelector('.bar-fill.success')).toBeTruthy();
    expect(container.querySelector('.pct')?.textContent).toBe('7/10');
  });
  it('total=0 兜底 0%', () => {
    const { container } = render(<ProgressBar completed={0} total={0} />);
    expect(container.querySelector('.bar-fill')?.getAttribute('style')).toContain('width: 0%');
  });
});

describe('Callout', () => {
  it('brand 变体默认', () => {
    const { container } = render(<Callout>hi</Callout>);
    expect(container.querySelector('.callout')).toBeTruthy();
    expect(container.textContent).toContain('hi');
  });
  it('warn / info 变体带 class', () => {
    const w = render(<Callout variant="warn" icon="!">w</Callout>).container;
    expect(w.querySelector('.callout.warn')).toBeTruthy();
    const i = render(<Callout variant="info" icon="i">i</Callout>).container;
    expect(i.querySelector('.callout.info')).toBeTruthy();
  });
});

describe('TagBadge', () => {
  it('渲染标签文本', () => {
    const { container } = render(<TagBadge tag="美妆" />);
    expect(container.textContent).toContain('美妆');
    expect(container.querySelector('.badge')).toBeTruthy();
  });
});

describe('formatShortTime', () => {
  it('null/undefined/非法 → 占位 —', () => {
    expect(formatShortTime(null)).toBe('—');
    expect(formatShortTime(undefined)).toBe('—');
    expect(formatShortTime('not-a-date')).toBe('—');
  });
  it('合法 ISO → 非 — 的 MM-DD HH:mm', () => {
    const s = formatShortTime('2026-07-16T10:21:00Z');
    expect(s).not.toBe('—');
    expect(s).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/);
  });
});

describe('formatDuration', () => {
  it('缺起止 → —', () => {
    expect(formatDuration(null, null)).toBe('—');
    expect(formatDuration('2026-07-16T10:00:00Z', null)).toBe('—');
  });
  it('end < start → —', () => {
    expect(formatDuration('2026-07-16T10:30:00Z', '2026-07-16T10:00:00Z')).toBe('—');
  });
  it('非法日期 → —', () => {
    expect(formatDuration('bad', 'alsobad')).toBe('—');
  });
  it('合法区间 → MM:SS', () => {
    const s = formatDuration('2026-07-16T10:00:00Z', '2026-07-16T10:02:30Z');
    expect(s).toMatch(/^\d{2}:\d{2}$/);
    expect(s).not.toBe('—');
  });
});

describe('PageHeader', () => {
  it('仅标题', () => {
    const { container } = render(<PageHeader title="标题" />);
    expect(container.querySelector('.page-title')?.textContent).toBe('标题');
    expect(container.querySelector('.title-tag')).toBeNull();
    expect(container.querySelector('.page-desc')).toBeNull();
  });
  it('titleTag + description + actions 全有', () => {
    const { container } = render(
      <PageHeader title="标题" titleTag="v2" description="说明" actions={<button>操作</button>} />,
    );
    expect(container.querySelector('.title-tag')?.textContent).toBe('v2');
    expect(container.querySelector('.page-desc')?.textContent).toBe('说明');
    expect(container.querySelector('.page-actions')).toBeTruthy();
  });
});

void cls; // 保留辅助（如需）
