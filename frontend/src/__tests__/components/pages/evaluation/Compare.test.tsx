/**
 * Compare 页面测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockCompareRuns = vi.fn();
const mockListRuns = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  compareRuns: (...args: unknown[]) => mockCompareRuns(...args),
  listRuns: (...args: unknown[]) => mockListRuns(...args),
}));

// 下拉数据源：两条已完成 run（页面会默认预选 #2 → #1）
const sampleRuns = {
  items: [
    { id: 2, version_id: 6, strategy_id: 2, name: '新版回归', trigger_type: 'manual', status: 'completed', filter_tags: [], total_cases: 3, completed_cases: 3, failed_cases: 0, metadata: {}, created_by: 1, started_at: null, finished_at: null, created_at: '2026-08-20T10:00:00Z' },
    { id: 1, version_id: 6, strategy_id: 2, name: '基线回归', trigger_type: 'manual', status: 'completed', filter_tags: [], total_cases: 3, completed_cases: 3, failed_cases: 0, metadata: {}, created_by: 1, started_at: null, finished_at: null, created_at: '2026-08-19T10:00:00Z' },
  ],
  pagination: { page: 1, page_size: 50, total: 2, total_pages: 1 },
};

import ComparePage from '../../../../evaluation/pages/Compare';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const sampleReport = {
  run_a_id: 1,
  run_b_id: 2,
  overall_avg_a: 7.1,
  overall_avg_b: 7.6,
  overall_delta: 0.5,
  dimension_deltas: [
    { dimension_id: 1, dimension_name: '文案质量', avg_a: 7.1, avg_b: 7.8, delta: 0.7 },
    { dimension_id: 2, dimension_name: '种草力', avg_a: 7.4, avg_b: 7.5, delta: 0.1 },
    { dimension_id: 3, dimension_name: '人设一致性', avg_a: 8.0, avg_b: 8.1, delta: 0.1 },
  ],
  case_deltas: [
    { test_case_id: 1, test_case_name: '焦虑型 · 美妆精华开屏', avg_a: 7.2, avg_b: 8.4, delta: 1.2, direction: 'improve' as const },
    { test_case_id: 2, test_case_name: '诱惑型 · 护肤套装促销量', avg_a: 7.6, avg_b: 6.8, delta: -0.8, direction: 'worsen' as const },
    { test_case_id: 3, test_case_name: '痛点共鸣 · 口红显白话术', avg_a: 8.1, avg_b: 8.1, delta: 0, direction: 'flat' as const },
  ],
  summary: { improve: 1, worsen: 1, flat: 1 },
};


/** 在第 idx 个 run Select 里选中 value（antd Select：mouseDown 打开 + 点选项） */
async function pickRun(container: HTMLElement, idx: number, value: number) {
  const selectors = container.querySelectorAll('.ant-select-selector');
  fireEvent.mouseDown(selectors[idx]);
  await waitFor(() => {
    expect(container.ownerDocument.querySelectorAll('.ant-select-item-option').length).toBeGreaterThan(0);
  });
  // 选项 title 形如 "#1 基线回归（已完成 · 08/19）"——按 title 前缀 `#id ` 精确定位
  const opt = Array.from(container.ownerDocument.querySelectorAll('.ant-select-item-option'))
    .find((el) => (el.textContent ?? '').startsWith(`#${value} `));
  fireEvent.click(opt!);
}

/** 清空第 idx 个 run Select（allowClear 叉） */
async function clearRun(container: HTMLElement, idx: number) {
  // allowClear 的叉默认隐藏（hover 才显示）——用 mouseEnter 模拟悬停使其挂载
  const selectors = container.querySelectorAll('.ant-select');
  fireEvent.mouseEnter(selectors[idx]);
  await waitFor(() => {
    expect(container.querySelectorAll('.ant-select-clear').length).toBeGreaterThan(idx);
  });
  const clears = container.querySelectorAll('.ant-select-clear');
  fireEvent.mouseDown(clears[idx]);
  fireEvent.click(clears[idx]);
}

describe('ComparePage', () => {
  beforeEach(() => {
  mockListRuns.mockReset();
  mockListRuns.mockResolvedValue(sampleRuns);
    mockCompareRuns.mockReset();
  });

  it('初始状态显示提示，未发起对比', () => {
    renderWithProviders(<ComparePage />);
    expect(screen.getByText('版本对比报告')).toBeInTheDocument();
    expect(screen.getByText(/下拉选择两个运行后点击「对比」/)).toBeInTheDocument();
    expect(mockCompareRuns).not.toHaveBeenCalled();
  });

  /** 找到页面上「对比」按钮（AntD 会自动在中文字符间插入空格） */
  function findCompareButton(container: HTMLElement): HTMLElement {
    const buttons = container.querySelectorAll('button');
    const texts: string[] = [];
    for (const b of Array.from(buttons)) {
      const txt = (b.textContent ?? '').replace(/\s+/g, '').trim();
      texts.push(txt);
      if (txt === '对比') return b as HTMLElement;
    }
    throw new Error(`未找到「对比」按钮。现有按钮文本：${texts.join(' | ')}`);
  }

  it('点击对比后渲染统计卡 + 维度差异 + 样本表', async () => {
    mockCompareRuns.mockResolvedValue(sampleReport);
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));   // 等 run 列表加载 + 默认预选(A=1,B=2)
    const btn = findCompareButton(container);
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByText('维度差异')).toBeInTheDocument();
      expect(screen.getByText('样本级差异')).toBeInTheDocument();
    });
    expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument();
    // 改善/恶化/持平
    expect(screen.getByText('文案质量')).toBeInTheDocument();
  });

  it('相同 run id 提交时给出警告', async () => {
    const { container } = renderWithProviders(<ComparePage />);
    // 等 run 列表加载并默认预选（A=1, B=2），把 B 改成 1 与 A 相同
    await waitFor(() => screen.getByText(/基线回归/));
    await pickRun(container, 1, 1);   // B 下拉选 #1
    const btn = findCompareButton(container);
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockCompareRuns).not.toHaveBeenCalled();
    });
  });
});

describe('ComparePage — 交互与边界', () => {
  beforeEach(() => {
    mockCompareRuns.mockReset();
  });

  function findCompareButton(container: HTMLElement): HTMLElement {
    for (const b of Array.from(container.querySelectorAll('button'))) {
      if ((b.textContent ?? '').replace(/\s+/g, '').trim() === '对比') return b as HTMLElement;
    }
    throw new Error('未找到「对比」按钮');
  }

  it('对比失败时提示错误', async () => {
    mockCompareRuns.mockRejectedValue(new Error('对比接口失败'));
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));
    fireEvent.click(findCompareButton(container));
    await waitFor(() => {
      expect(screen.getByText(/对比接口失败/)).toBeInTheDocument();
    });
  });

  it('交换 A/B 后再次对比用交换后的 id', async () => {
    mockCompareRuns.mockResolvedValue(sampleReport);
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));
    fireEvent.click(findCompareButton(container));
    await waitFor(() => expect(screen.getByText('维度差异')).toBeInTheDocument());
    // 点「交换 A / B」
    fireEvent.click(screen.getByText(/交换/));
    fireEvent.click(findCompareButton(container));
    await waitFor(() => {
      expect(mockCompareRuns).toHaveBeenLastCalledWith(2, 1);
    });
  });

  it('维度差异为空时显示空状态', async () => {
    mockCompareRuns.mockResolvedValue({ ...sampleReport, dimension_deltas: [] });
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));
    fireEvent.click(findCompareButton(container));
    await waitFor(() => {
      expect(screen.getByText('暂无维度数据')).toBeInTheDocument();
    });
  });

  it('总体下降（overall_delta < 0）渲染恶化色', async () => {
    mockCompareRuns.mockResolvedValue({ ...sampleReport, overall_delta: -0.6 });
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));
    fireEvent.click(findCompareButton(container));
    await waitFor(() => {
      expect(screen.getByText(/-0\.60/)).toBeInTheDocument();
    });
  });

  it('清空 run 时阻止并提示（覆盖 null 分支）', async () => {
    mockCompareRuns.mockResolvedValue(sampleReport);
    const { container } = renderWithProviders(<ComparePage />);
    await waitFor(() => screen.getByText(/基线回归/));
    await clearRun(container, 0);     // 清空 A
    fireEvent.click(findCompareButton(container));
    await waitFor(() => {
      expect(mockCompareRuns).not.toHaveBeenCalled();
    });
  });
});
