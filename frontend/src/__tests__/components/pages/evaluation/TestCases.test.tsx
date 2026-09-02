/**
 * 测试集页面测试（TestCases.tsx）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListTestCases = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listTestCases: (...args: unknown[]) => mockListTestCases(...args),
  createTestCase: vi.fn(),
  updateTestCase: vi.fn(),
  deleteTestCase: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
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

describe('TestCasesPage — 交互与边界渲染', () => {
  beforeEach(() => {
    mockListTestCases.mockReset();
    mockNavigate.mockReset();
  });

  // 含一个无描述 + 无标签的样本（覆盖 113 / 124 渲染分支）
  const pageWithEmpty = {
    items: [
      ...samplePage.items,
      {
        id: 3,
        tool_code: 'qianchuan-writer',
        name: '裸样本无描述无标签',
        description: null,
        input_payload: {},
        expected_output: null,
        tags: [],
        is_active: true,
        created_by: 1,
        updated_by: 1,
        created_at: '2026-07-16T14:22:00Z',
        updated_at: '2026-07-16T14:22:00Z',
        deleted_at: null,
      },
    ],
    pagination: { page: 1, page_size: 20, total: 3, total_pages: 1 },
  };

  it('无描述 / 无标签样本正常渲染（覆盖分支）', async () => {
    mockListTestCases.mockResolvedValue(pageWithEmpty);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => {
      expect(screen.getByText('裸样本无描述无标签')).toBeInTheDocument();
    });
  });

  it('点击「新建样本」跳转新建页', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新建样本'));
    expect(mockNavigate).toHaveBeenCalledWith('/evaluation/test-cases/new');
  });

  it('点击「编辑」跳转编辑页', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('编辑')[0]);
    expect(mockNavigate).toHaveBeenCalledWith('/evaluation/test-cases/1/edit');
  });

  it('状态过滤：仅启用 / 仅停用', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());
    // 选「已停用」→ 只剩诱惑型（is_active=false）
    const statusSelect = screen.getAllByText('全部状态')[0].closest('.ant-select-selector')!;
    fireEvent.mouseDown(statusSelect);
    fireEvent.click(await screen.findByText('已停用'));
    await waitFor(() => {
      expect(screen.queryByText('焦虑型 · 美妆精华开屏')).not.toBeInTheDocument();
      expect(screen.getByText('诱惑型 · 护肤套装促销量')).toBeInTheDocument();
    });
  });

  it('分页切换触发重新加载（覆盖 pagination onChange）', async () => {
    mockListTestCases.mockResolvedValue({
      items: samplePage.items,
      pagination: { page: 1, page_size: 20, total: 25, total_pages: 2 },
    });
    const { container } = renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());
    // 点下一页（AntD pagination next 按钮）
    const nextBtn = container.querySelector('.ant-pagination-next') as HTMLElement;
    expect(nextBtn).toBeTruthy();
    fireEvent.click(nextBtn);
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }));
    });
  });

  /** 打开标签下拉并点选指定标签（"美妆"同时出现在行内徽章与下拉选项，需精确点选项层） */
  async function pickTag(tag: string) {
    const tagSelector = screen.getAllByText('全部标签')[0].closest('.ant-select-selector')!;
    fireEvent.mouseDown(tagSelector);
    const matches = await screen.findAllByText(tag);
    const option = matches.find((el) => el.closest('.ant-select-item-option'));
    expect(option).toBeTruthy();
    fireEvent.click(option!);
  }

  it('选择标签筛选：请求带 tag 参数并重置回第 1 页（回归：筛选曾不生效）', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());
    expect(mockListTestCases).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 }),
    );

    await pickTag('美妆');

    // 回归断言：请求参数带上 tag（此前 tagFilter 从未进请求 → 筛选无效）
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, tag: '美妆' }),
      );
    });
  });

  it('清空标签筛选：请求不带 tag 参数', async () => {
    mockListTestCases.mockResolvedValue(samplePage);
    const { container } = renderWithProviders(<TestCasesPage />);
    await waitFor(() => expect(screen.getByText('焦虑型 · 美妆精华开屏')).toBeInTheDocument());

    await pickTag('美妆');
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenLastCalledWith(expect.objectContaining({ tag: '美妆' }));
    });

    // allowClear：点 Select 上的清除叉
    const clearBtn = container.querySelector('.filter-bar .ant-select-clear');
    expect(clearBtn).toBeTruthy();
    fireEvent.mouseDown(clearBtn as HTMLElement);
    fireEvent.click(clearBtn as HTMLElement);
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ tag: expect.anything() }),
      );
    });
  });
});
