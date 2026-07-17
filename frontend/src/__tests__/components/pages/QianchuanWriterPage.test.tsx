import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// Mock API
const mockGetPersonas = vi.fn();
const mockParseFile = vi.fn();
const mockChatStream = vi.fn();
const mockSaveOutput = vi.fn();
const mockExportWord = vi.fn();
const mockGetOutputs = vi.fn();
const mockGetConfigs = vi.fn();
const mockUpdateConfig = vi.fn();
const mockGetActiveProducts = vi.fn();
const mockUpdateActiveProducts = vi.fn();
const mockGetQianchuanProducts = vi.fn();
const mockCreateQianchuanProduct = vi.fn();
const mockSubmitReview = vi.fn();

vi.mock('../../../api/qianchuanWriter', () => ({
  getPersonas: (...args: unknown[]) => mockGetPersonas(...args),
  parseFile: (...args: unknown[]) => mockParseFile(...args),
  chatStream: (...args: unknown[]) => mockChatStream(...args),
  saveOutput: (...args: unknown[]) => mockSaveOutput(...args),
  exportWord: (...args: unknown[]) => mockExportWord(...args),
  getOutputs: (...args: unknown[]) => mockGetOutputs(...args),
  getConfigs: (...args: unknown[]) => mockGetConfigs(...args),
  updateConfig: (...args: unknown[]) => mockUpdateConfig(...args),
}));

vi.mock('../../../api/ai', () => ({
  getAiModels: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

vi.mock('../../../api/kolWorkspace', () => ({
  getActiveProducts: (...args: unknown[]) => mockGetActiveProducts(...args),
  updateActiveProducts: (...args: unknown[]) => mockUpdateActiveProducts(...args),
}));

vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts: (...args: unknown[]) => mockGetQianchuanProducts(...args),
  createQianchuanProduct: (...args: unknown[]) => mockCreateQianchuanProduct(...args),
}));

vi.mock('../../../api/scriptReview', () => ({
  submitReview: (...args: unknown[]) => mockSubmitReview(...args),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// Mock scrollIntoView（jsdom 不支持）
Element.prototype.scrollIntoView = vi.fn();

import QianchuanWriterPage, { QianchuanWriterModule, selectBestReviewCandidate } from '../../../pages/operator/QianchuanWriterPage';
import QianchuanWriterConfigTab from '../../../pages/admin/QianchuanWriterConfigTab';

const samplePersonas = [
  {
    id: 1,
    name: '孙知羽',
    soul_preview: '我是一个热爱分享的美妆博主，专注护肤品评测和教程...',
    creator_name: '系统预设',
  },
  {
    id: 2,
    name: '陶然',
    soul_preview: '科技达人，喜欢分享数码产品使用心得...',
    creator_name: '管理员',
  },
];

function createReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

function renderWithApp(ui: React.ReactElement) {
  return render(<App>{ui}</App>);
}

type UserInstance = ReturnType<typeof userEvent.setup>;

/** 打开 AntD Select 下拉并选择指定选项 */
async function openSelectAndPick(user: UserInstance, optionText: RegExp): Promise<void> {
  await waitFor(() => {
    expect(document.querySelector('.ant-select-selector')).toBeTruthy();
  });
  const selectSelector = document.querySelector('.ant-select-selector') as HTMLElement;
  await act(async () => {
    fireEvent.mouseDown(selectSelector);
  });
  await waitFor(() => screen.getByText(optionText));
  await user.click(screen.getByText(optionText));
}

/** 当前商品已加载的主流程：选达人 → 输入脚本 → 点生成。 */
async function runFullWorkflow(user: UserInstance, chatResponse: string): Promise<void> {
  const mockResponse = {
    ok: true,
    body: createReadableStream([chatResponse]),
  } as unknown as Response;
  mockChatStream.mockResolvedValue(mockResponse);

  // 选达人
  await openSelectAndPick(user, /孙知羽/);
  await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

  // Step 2 → Step 3
  await waitFor(() => screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));
  await user.click(screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));

  // Step 3: 输入脚本
  await waitFor(() => screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/));
  await user.type(screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/), '脚本');

  // 生成
  await user.click(screen.getByRole('button', { name: '生成仿写脚本 →' }));
  await waitFor(() => expect(mockChatStream).toHaveBeenCalled());
}

async function reviewAndConfirm(user: UserInstance): Promise<void> {
  await user.click(screen.getByRole('button', { name: '开始逐轮预审' }));
  await waitFor(() => screen.getByRole('button', { name: '运营确认最终稿' }));
  await user.click(screen.getByRole('button', { name: '运营确认最终稿' }));
}

describe('QianchuanWriterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPersonas.mockResolvedValue(samplePersonas);
    mockParseFile.mockResolvedValue({ text: '解析后的产品卖点', word_count: 10 });
    mockSaveOutput.mockResolvedValue({ output_id: 1 });
    mockExportWord.mockResolvedValue(new Blob(['docx'], { type: 'application/octet-stream' }));
    mockGetActiveProducts.mockResolvedValue([{ id: 101, nickname: '当前商品', core_selling_point: '当前卖点', mechanism: '买一送一', mechanism_exclusive: true }]);
    mockGetQianchuanProducts.mockResolvedValue({ items: [], pagination: { page: 1, page_size: 100, total: 0, total_pages: 0 } });
    mockUpdateActiveProducts.mockResolvedValue({ active_product_ids: [101] });
    mockSubmitReview.mockResolvedValue({ rating: 'pass', must_fix: [], suggestions: [], passed: [] });
  });

  // Test 1: 4 步向导渲染
  it('renders 4 step labels in the wizard', async () => {
    renderWithApp(<QianchuanWriterPage />);
    await waitFor(() => {
      expect(screen.getByText('选择达人')).toBeInTheDocument();
      expect(screen.getByText('加载产品')).toBeInTheDocument();
      expect(screen.getByText('输入脚本')).toBeInTheDocument();
      expect(screen.getByText('生成仿写')).toBeInTheDocument();
    });
  });

  // Test 2: Step 1 达人下拉 + 预览
  it('loads personas and shows preview when selected', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await waitFor(() => expect(mockGetPersonas).toHaveBeenCalled());

    await openSelectAndPick(user, /孙知羽/);

    await waitFor(() => {
      expect(screen.getByText('人格档案')).toBeInTheDocument();
      expect(screen.getByText(/美妆博主/)).toBeInTheDocument();
    });
  });

  it('loads the current product instead of asking for a product brief upload', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '选产品' })).toBeInTheDocument();
      expect(screen.getByText(/产品昵称：当前商品/)).toBeInTheDocument();
      expect(screen.queryByText('点击上传或拖拽卖点卡')).not.toBeInTheDocument();
    });
  });

  it('在没有当前商品时，新建并选中流程要求填写完整商品字段', async () => {
    mockGetActiveProducts.mockResolvedValue([]);
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterModule kolId={1} />);

    await screen.findByText('还没有当前商品，不能生成仿写');
    await user.click(screen.getByRole('button', { name: '新建商品' }));

    expect(await screen.findByLabelText('最主推卖点')).toBeInTheDocument();
    expect(screen.getByLabelText('主推机制')).toBeInTheDocument();
    expect(screen.getByText(/这次主推的价格钩子或促销力度/)).toBeInTheDocument();
  });

  // Test 4: Step 3 字数实时显示
  it('displays character count when script is entered', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    await waitFor(() => screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));
    await user.click(screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));

    await waitFor(() => screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/));
    await user.type(screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/), '这是测试脚本的文字内容');

    await waitFor(() => {
      expect(screen.getByText(/11 字/)).toBeInTheDocument();
    });
  });

  // Test 5: 流式输出 — chatStream 被调用
  it('calls chatStream when generate is clicked', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '这是仿写结果');
    expect(mockChatStream).toHaveBeenCalled();
  });

  // Test 6: 多轮追问输入框
  it('shows chat input after generation completes', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '仿写完成');

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/告诉 AI 哪里需要调整/)).toBeInTheDocument();
    });
  });

  it('runs fail fail pass through three review rounds and stops', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '初稿');
    mockChatStream
      .mockResolvedValueOnce({ ok: true, body: createReadableStream(['自动修改稿一']) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, body: createReadableStream(['自动修改稿二']) } as unknown as Response);
    mockSubmitReview
      .mockResolvedValueOnce({ rating: 'fail', must_fix: [{ type: '价格', quote: '99', fix: '改价' }], suggestions: [], passed: [] })
      .mockResolvedValueOnce({ rating: 'fail', must_fix: [{ type: '卖点', quote: '旧卖点', fix: '替换' }], suggestions: [], passed: [] })
      .mockResolvedValueOnce({ rating: 'pass', must_fix: [], suggestions: [], passed: [] });

    await user.click(screen.getByRole('button', { name: '开始逐轮预审' }));

    await waitFor(() => expect(mockSubmitReview).toHaveBeenCalledTimes(3));
    expect(screen.getByText(/第 3 轮预审：通过/)).toBeInTheDocument();
  });

  it('reviews one time again after a confirmed final draft is adjusted', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '初稿');
    await reviewAndConfirm(user);
    mockChatStream.mockResolvedValueOnce({ ok: true, body: createReadableStream(['人工微调稿']) } as unknown as Response);

    await user.type(screen.getByPlaceholderText(/告诉 AI 哪里需要调整/), '把开头改短');
    await user.click(screen.getByRole('button', { name: /发\s*送/ }));

    await waitFor(() => expect(mockSubmitReview).toHaveBeenCalledTimes(2));
    expect(mockChatStream.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({
      messages: [expect.objectContaining({ content: expect.stringContaining('初稿') })],
    }));
    expect(screen.getByLabelText('运营直接编辑当前最佳稿')).toHaveValue('人工微调稿');
    expect(screen.getByRole('button', { name: '运营确认最终稿' })).toBeInTheDocument();
  });

  it('reviews an operator edited best draft exactly once without regenerating it', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '初稿');
    await reviewAndConfirm(user);

    const editor = screen.getByLabelText('运营直接编辑当前最佳稿');
    await user.clear(editor);
    await user.type(editor, '运营编辑后的最佳稿');
    await user.click(screen.getByRole('button', { name: '编辑稿预审一次' }));

    await waitFor(() => expect(mockSubmitReview).toHaveBeenCalledTimes(2));
    expect(mockSubmitReview).toHaveBeenLastCalledWith(expect.objectContaining({
      adapted_script: '运营编辑后的最佳稿',
    }));
    expect(mockChatStream).toHaveBeenCalledTimes(1);
  });

  it('keeps the current draft when a review request fails', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '初稿');
    mockSubmitReview.mockRejectedValueOnce(new Error('预审服务异常'));

    await user.click(screen.getByRole('button', { name: '开始逐轮预审' }));

    await waitFor(() => expect(screen.getByLabelText('运营直接编辑当前最佳稿')).toHaveValue('初稿'));
    expect(screen.getByText(/轮次用尽或预审中断/)).toBeInTheDocument();
  });

  // Test 7: 保存历史按钮调用 saveOutput
  it('calls saveOutput when save button is clicked', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '仿写内容');
    await reviewAndConfirm(user);
    await waitFor(() => screen.getByText('保存到历史'));
    await user.click(screen.getByText('保存到历史'));

    await waitFor(() => {
      expect(mockSaveOutput).toHaveBeenCalledWith(
        expect.objectContaining({ content: '仿写内容' }),
      );
    });
  });

  // Test 8: 导出 .txt 触发下载
  it('triggers .txt download when export txt button is clicked', async () => {
    const user = userEvent.setup();

    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'mock-url');
    URL.revokeObjectURL = vi.fn();

    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '仿写内容');
    await reviewAndConfirm(user);

    // 在点击导出按钮前设置 DOM mock（避免影响渲染）
    const clickSpy = vi.fn();
    const appendChildSpy = vi
      .spyOn(document.body, 'appendChild')
      .mockImplementation((node) => {
        if (node instanceof HTMLAnchorElement) {
          node.click = clickSpy;
        }
        return node;
      });
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);

    await waitFor(() => screen.getByText('导出 .txt'));
    await user.click(screen.getByText('导出 .txt'));

    await waitFor(() => expect(clickSpy).toHaveBeenCalled());

    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    appendChildSpy.mockRestore();
  });

  // Test 9: 导出 .docx 调用 exportWord
  it('calls exportWord when export docx button is clicked', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '仿写内容');
    await reviewAndConfirm(user);

    await waitFor(() => screen.getByText('导出 .docx'));
    await user.click(screen.getByText('导出 .docx'));

    await waitFor(() => {
      expect(mockExportWord).toHaveBeenCalledWith(
        expect.objectContaining({ content: '仿写内容' }),
      );
    });
  });

  it('blocks generation and provides product actions when no current product exists', async () => {
    const user = userEvent.setup();
    mockGetActiveProducts.mockResolvedValue([]);
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    await waitFor(() => {
      expect(screen.getByText('还没有当前商品，不能生成仿写')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '选择已有商品' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '新建商品' })).toBeInTheDocument();
    });
  });
});

describe('selectBestReviewCandidate', () => {
  it('stops at the third review candidate when fail fail pass is returned', () => {
    const result = selectBestReviewCandidate([
      { text: '第一版', review: { rating: 'fail', must_fix: [{ type: '价格', quote: '', fix: '' }] } },
      { text: '第二版', review: { rating: 'fail', must_fix: [] } },
      { text: '第三版', review: { rating: 'pass', must_fix: [] } },
    ]);

    expect(result?.text).toBe('第三版');
  });

  it('prefers fewer must-fix items and then the newer draft for equal ratings', () => {
    const result = selectBestReviewCandidate([
      { text: '第二轮较好', review: { rating: 'minor', must_fix: [] } },
      { text: '第四轮较差', review: { rating: 'minor', must_fix: [{ type: '遗漏', quote: '', fix: '' }] } },
      { text: '同样好但更新', review: { rating: 'minor', must_fix: [] } },
    ]);

    expect(result?.text).toBe('同样好但更新');
  });

  it('keeps the better second round when the fourth round is worse', () => {
    const result = selectBestReviewCandidate([
      { text: '第一轮', review: { rating: 'fail', must_fix: [{ type: '价格', quote: '', fix: '' }] } },
      { text: '第二轮最佳', review: { rating: 'minor', must_fix: [] } },
      { text: '第三轮', review: { rating: 'minor', must_fix: [{ type: '卖点', quote: '', fix: '' }] } },
      { text: '第四轮较差', review: { rating: 'minor', must_fix: [{ type: '卖点', quote: '', fix: '' }, { type: '结构', quote: '', fix: '' }] } },
    ]);

    expect(result?.text).toBe('第二轮最佳');
  });

  it('selects the best candidate after four failed reviews', () => {
    const result = selectBestReviewCandidate([
      { text: '第一轮', review: { rating: 'fail', must_fix: [{ type: '价格', quote: '', fix: '' }, { type: '卖点', quote: '', fix: '' }] } },
      { text: '第二轮最佳', review: { rating: 'fail', must_fix: [] } },
      { text: '第三轮', review: { rating: 'fail', must_fix: [{ type: '结构', quote: '', fix: '' }] } },
      { text: '第四轮', review: { rating: 'fail', must_fix: [{ type: '价格', quote: '', fix: '' }] } },
    ]);

    expect(result?.text).toBe('第二轮最佳');
  });
});

// ---------------------------------------------------------------------------
// ConfigTab 测试
// ---------------------------------------------------------------------------
describe('QianchuanWriterConfigTab', () => {
  const sampleConfig = {
    id: 1,
    config_key: 'default',
    ai_model_id: null,
    system_prompt: '你是一个千川脚本仿写专家...',
    is_active: true,
    updated_at: '2026-06-22T10:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetConfigs.mockResolvedValue([sampleConfig]);
    mockUpdateConfig.mockResolvedValue({ config_key: 'default' });
  });

  it('renders configs after loading', async () => {
    render(
      <App>
        <QianchuanWriterConfigTab />
      </App>,
    );

    await waitFor(() => {
      expect(mockGetConfigs).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText('默认配置')).toBeInTheDocument();
      expect(screen.getByText('编辑')).toBeInTheDocument();
    });
  });

  it('opens edit modal when edit button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <App>
        <QianchuanWriterConfigTab />
      </App>,
    );

    await waitFor(() => screen.getByText('编辑'));
    await user.click(screen.getByText('编辑'));

    await waitFor(() => {
      expect(screen.getByText('编辑配置：default')).toBeInTheDocument();
      expect(screen.getByText('系统 Prompt')).toBeInTheDocument();
    });
  });
});
