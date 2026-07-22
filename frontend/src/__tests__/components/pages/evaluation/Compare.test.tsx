/**
 * Compare 页面测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockCompareRuns = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  compareRuns: (...args: unknown[]) => mockCompareRuns(...args),
}));

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

describe('ComparePage', () => {
  beforeEach(() => {
    mockCompareRuns.mockReset();
  });

  it('初始状态显示提示，未发起对比', () => {
    renderWithProviders(<ComparePage />);
    expect(screen.getByText('版本对比报告')).toBeInTheDocument();
    expect(screen.getByText(/填入两个 run id 后点击「对比」/)).toBeInTheDocument();
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
    // 把 runB 改成 1 与 runA 相同
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[1], { target: { value: '1' } });
    const btn = findCompareButton(container);
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockCompareRuns).not.toHaveBeenCalled();
    });
  });
});
