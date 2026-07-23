/**
 * TestCaseEdit 页面测试（新建模式）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
// useNavigate 必须返回稳定引用：TestCaseEdit 的加载 effect 依赖 navigate，
// 每次渲染返回新 fn 会触发 effect 反复取消（cancelled=true），导致 setLoading(false) 被跳过
const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
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

describe('TestCaseEditPage — 表单提交与标签交互', () => {
  beforeEach(() => {
    mockListTestCases.mockReset();
    mockCreateTestCase.mockReset();
    mockUpdateTestCase.mockReset();
    mockUseParams.mockReset();
    mockUseParams.mockReturnValue({ id: 'new' }); // 新建模式
  });

  // 点击「保存」（AntD 2 字按钮 autoInsertSpace → "保 存"；页面顶部+底部各一个）
  function clickSave() {
    fireEvent.click(screen.getAllByText(/保\s*存/)[0]);
  }

  // 填齐必填项：名称 + 至少一个标签
  function fillRequired(name = '测试样本A', tag = '焦虑型') {
    fireEvent.change(screen.getByPlaceholderText(/美妆精华开屏/), { target: { value: name } });
    const tagInput = screen.getByTestId('tag-input');
    fireEvent.change(tagInput, { target: { value: tag } });
    fireEvent.keyDown(tagInput, { key: 'Enter' });
  }

  it('新建：填名称+标签后保存，调用 createTestCase 并提示成功', async () => {
    mockCreateTestCase.mockResolvedValue({ id: 9 });
    renderWithProviders(<TestCaseEditPage />);
    fillRequired();
    clickSave();
    await waitFor(() => {
      expect(mockCreateTestCase).toHaveBeenCalledWith(
        expect.objectContaining({
          tool_code: 'qianchuan-writer',
          name: '测试样本A',
          tags: ['焦虑型'],
          input_payload: expect.objectContaining({ messages: expect.any(Array) }),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/已创建样本/)).toBeInTheDocument();
    });
  });

  it('messages 非法 JSON 时阻止提交并提示', async () => {
    renderWithProviders(<TestCaseEditPage />);
    fillRequired();
    fireEvent.change(screen.getByLabelText('JSON 或多行文本'), { target: { value: '{not json' } });
    clickSave();
    await waitFor(() => {
      expect(screen.getByText(/messages 不是合法 JSON/)).toBeInTheDocument();
    });
    expect(mockCreateTestCase).not.toHaveBeenCalled();
  });

  it('expected_output 非法 JSON 时阻止提交并提示', async () => {
    renderWithProviders(<TestCaseEditPage />);
    fillRequired();
    fireEvent.change(screen.getByLabelText('期望输出（可选，JSON）'), { target: { value: '{bad' } });
    clickSave();
    await waitFor(() => {
      expect(screen.getByText(/期望输出不是合法 JSON/)).toBeInTheDocument();
    });
    expect(mockCreateTestCase).not.toHaveBeenCalled();
  });

  it('保存失败显示错误提示', async () => {
    mockCreateTestCase.mockRejectedValue(new Error('服务器错误'));
    renderWithProviders(<TestCaseEditPage />);
    fillRequired();
    clickSave();
    await waitFor(() => {
      expect(screen.getByText(/服务器错误/)).toBeInTheDocument();
    });
  });

  it('编辑模式：加载后保存调用 updateTestCase', async () => {
    mockUseParams.mockReturnValue({ id: '5' });
    mockListTestCases.mockResolvedValue({
      items: [
        {
          id: 5,
          tool_code: 'qianchuan-writer',
          name: '原样本',
          description: 'desc',
          input_payload: { kol_name: '林小美', messages: [{ role: 'user', content: 'x' }] },
          expected_output: null,
          tags: ['美妆'],
          is_active: true,
          created_by: 1,
          updated_by: 1,
          created_at: '2026-07-16T14:22:00Z',
          updated_at: '2026-07-16T14:22:00Z',
          deleted_at: null,
        },
      ],
      pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 },
    });
    mockUpdateTestCase.mockResolvedValue({ id: 5 });
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/5/edit']);
    // 等待表单回填（异步加载）
    const nameInput = await screen.findByDisplayValue('原样本');
    expect(nameInput).toBeInTheDocument();
    clickSave();
    await waitFor(() => {
      expect(mockUpdateTestCase).toHaveBeenCalledWith(5, expect.objectContaining({ name: '原样本' }));
    });
  });

  it('标签边界：空输入不添加', () => {
    renderWithProviders(<TestCaseEditPage />);
    const tagInput = screen.getByTestId('tag-input');
    fireEvent.change(tagInput, { target: { value: '   ' } });
    fireEvent.keyDown(tagInput, { key: 'Enter' });
    expect(screen.queryByText(/焦虑型/)).not.toBeInTheDocument();
  });

  it('标签边界：重复标签只保留一个', async () => {
    renderWithProviders(<TestCaseEditPage />);
    const tagInput = screen.getByTestId('tag-input');
    fireEvent.change(tagInput, { target: { value: '焦虑型' } });
    fireEvent.keyDown(tagInput, { key: 'Enter' });
    fireEvent.change(tagInput, { target: { value: '焦虑型' } });
    fireEvent.keyDown(tagInput, { key: 'Enter' });
    // Tag closable 带关闭图标，用正则匹配
    await waitFor(() => {
      expect(screen.getAllByText(/焦虑型/).length).toBe(1);
    });
  });

  it('标签边界：超过 5 个提示警告且不加第 6 个', async () => {
    renderWithProviders(<TestCaseEditPage />);
    const tagInput = screen.getByTestId('tag-input');
    ['一', '二', '三', '四', '五'].forEach((t) => {
      fireEvent.change(tagInput, { target: { value: t } });
      fireEvent.keyDown(tagInput, { key: 'Enter' });
    });
    fireEvent.change(tagInput, { target: { value: '六' } });
    fireEvent.keyDown(tagInput, { key: 'Enter' });
    await waitFor(() => {
      expect(screen.getByText(/标签最多 5 个/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/六/)).not.toBeInTheDocument();
  });
});
