/**
 * TestCaseEdit 页面测试（新建模式）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListTestCases = vi.fn();
const mockCreateTestCase = vi.fn();
const mockUpdateTestCase = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listTestCases: (...args: unknown[]) => mockListTestCases(...args),
  createTestCase: (...args: unknown[]) => mockCreateTestCase(...args),
  updateTestCase: (...args: unknown[]) => mockUpdateTestCase(...args),
}));

const mockUseParams = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => mockUseParams(),
  };
});

import TestCaseEditPage from '../../../../evaluation/pages/TestCaseEdit';

function renderWithProviders(ui: React.ReactElement, initialEntries: string[] = ['/evaluation/test-cases/new']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

describe('TestCaseEditPage (新建模式)', () => {
  beforeEach(() => {
    mockListTestCases.mockReset();
    mockCreateTestCase.mockReset();
    mockUpdateTestCase.mockReset();
    mockUseParams.mockReset();
    mockUseParams.mockReturnValue({ id: 'new' });
  });

  it('新建模式渲染空表单', async () => {
    renderWithProviders(<TestCaseEditPage />);
    expect(screen.getByText('新建测试样本')).toBeInTheDocument();
    // 至少能看到几个 card 标题
    expect(screen.getByText('基础信息')).toBeInTheDocument();
    expect(screen.getByText('产品卖点卡')).toBeInTheDocument();
    expect(screen.getByText('参考脚本 / 原版')).toBeInTheDocument();
    expect(screen.getByText('对话上下文 messages')).toBeInTheDocument();
    expect(screen.getByText('标签 & 期望输出')).toBeInTheDocument();
    // 新建模式不调用 list
    expect(mockListTestCases).not.toHaveBeenCalled();
  });

  it('编辑模式加载已有样本', async () => {
    mockUseParams.mockReturnValue({ id: '5' });
    const sample = {
      id: 5,
      tool_code: 'qianchuan-writer',
      name: '焦虑型 · 美妆精华开屏',
      description: '3 秒痛点钩子前置',
      input_payload: {
        kol_name: '林小美',
        selling_points: '5% 烟酰胺',
        reference_script: '原版脚本...',
        messages: [{ role: 'user', content: '帮我仿写...' }],
      },
      expected_output: null,
      tags: ['焦虑型', '美妆'],
      is_active: true,
      created_by: 1,
      updated_by: 1,
      created_at: '2026-07-16T14:22:00Z',
      updated_at: '2026-07-16T14:22:00Z',
      deleted_at: null,
    };
    mockListTestCases.mockResolvedValue({
      items: [sample],
      pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 },
    });
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/5/edit']);
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenCalled();
    });
  });

  it('加载失败时通过 message.error 提示（验证 API 调用）', async () => {
    mockUseParams.mockReturnValue({ id: '99' });
    mockListTestCases.mockRejectedValue(new Error('网络错误'));
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/99/edit']);
    // 编辑模式下应触发加载（不渲染错误文案到 DOM，而是通过 antd 通知）
    await waitFor(() => {
      expect(mockListTestCases).toHaveBeenCalled();
    });
  });
});
