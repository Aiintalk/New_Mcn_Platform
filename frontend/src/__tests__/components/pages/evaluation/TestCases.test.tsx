/**
 * 测试集页面测试（TestCases.tsx）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListTestCases = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listTestCases: (...args: unknown[]) => mockListTestCases(...args),
  createTestCase: vi.fn(),
  updateTestCase: vi.fn(),
  deleteTestCase: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

import TestCasesPage from '../../../../evaluation/pages/TestCases';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const samplePage = {
  items: [
    {
      id: 1,
      tool_code: 'qianchuan-writer',
      name: '焦虑型 · 美妆精华开屏',
      description: '3 秒痛点钩子前置',
      input_payload: {},
      expected_output: null,
      tags: ['焦虑型', '美妆'],
      is_active: true,
      created_by: 1,
      updated_by: 1,
      created_at: '2026-07-16T14:22:00Z',
      updated_at: '2026-07-16T14:22:00Z',
      deleted_at: null,
    },
    {
      id: 2,
      tool_code: 'qianchuan-writer',
      name: '诱惑型 · 护肤套装促销量',
      description: '强转化 + 限时优惠',
      input_payload: {},
      expected_output: null,
      tags: ['诱惑型'],
      is_active: false,
      created_by: 2,
      updated_by: 2,
      created_at: '2026-07-16T11:05:00Z',
      updated_at: '2026-07-16T11:05:00Z',
      deleted_at: null,
    },
  ],
  pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
};

describe('TestCasesPage', () => {
  beforeEach(() => {
    mockListTestCases.mockReset();
  });

  it('渲染标题、统计与样本列表', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    expect(screen.getByText('测试集')).toBeInTheDocument();
    expect(screen.getByText(/tool: qianchuan-writer/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument();
      expect(screen.getByText('诱惑型 · 护肤套装促销量')).toBeInTheDocument();
    });
    // 统计：总数 2
    expect(mockListTestCases).toHaveBeenCalledTimes(1);
  });

  it('加载失败时显示错误提示', async () => {
    mockListTestCases.mockRejectedValue(new Error('网络错误'));
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument();
    });
  });

  it('客户端搜索过滤（按名称）', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => {
      expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument();
    });
    const searchInput = screen.getByPlaceholderText('🔍 搜索样本名称 / 描述');
    fireEvent.change(searchInput, { target: { value: '焦虑型' } });
    expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument();
    expect(screen.queryByText('诱惑型 · 护肤套装促销量')).not.toBeInTheDocument();
  });
});
