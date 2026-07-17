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

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// Mock scrollIntoView（jsdom 不支持）
Element.prototype.scrollIntoView = vi.fn();

import QianchuanWriterPage from '../../../pages/operator/QianchuanWriterPage';
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

/** 完整 4 步向导流程：选达人 → 粘贴产品 → 输入脚本 → 点生成 */
async function runFullWorkflow(user: UserInstance, chatResponse: string): Promise<void> {
  const mockResponse = {
    ok: true,
    body: createReadableStream([chatResponse]),
  } as unknown as Response;
  mockChatStream.mockResolvedValue(mockResponse);

  // 选达人
  await openSelectAndPick(user, /孙知羽/);
  await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

  // Step 2: 粘贴模式
  await waitFor(() => screen.getByText('直接粘贴文本'));
  await user.click(screen.getByText('直接粘贴文本'));
  await user.type(screen.getByPlaceholderText(/把产品卖点卡粘贴到这里/), '卖点');
  // 等确认按钮启用
  await waitFor(() => {
    const btn = screen.getByRole('button', { name: /确\s*认/ });
    expect(btn).not.toBeDisabled();
  });
  await user.click(screen.getByRole('button', { name: /确\s*认/ }));

  // Step 2 → Step 3: 点击"下一步"
  await waitFor(() => screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));
  await user.click(screen.getByRole('button', { name: '下一步：输入原版脚本 →' }));

  // Step 3: 输入脚本
  await waitFor(() => screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/));
  await user.type(screen.getByPlaceholderText(/把原版千川脚本粘贴到这里/), '脚本');

  // 生成
  await user.click(screen.getByRole('button', { name: '生成仿写脚本 →' }));
  await waitFor(() => expect(mockChatStream).toHaveBeenCalled());
}

describe('QianchuanWriterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPersonas.mockResolvedValue(samplePersonas);
    mockParseFile.mockResolvedValue({ text: '解析后的产品卖点', word_count: 10 });
    mockSaveOutput.mockResolvedValue({ output_id: 1 });
    mockExportWord.mockResolvedValue(new Blob(['docx'], { type: 'application/octet-stream' }));
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

  // Test 3: Step 2 文件上传区域 + 粘贴切换
  it('shows file upload area and paste mode toggle in Step 2', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 · 加载产品卖点')).toBeInTheDocument();
      expect(screen.getByText('点击上传或拖拽卖点卡')).toBeInTheDocument();
      expect(screen.getByText('直接粘贴文本')).toBeInTheDocument();
    });
  });

  // Test 4: Step 3 字数实时显示
  it('displays character count when script is entered', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    await waitFor(() => screen.getByText('直接粘贴文本'));
    await user.click(screen.getByText('直接粘贴文本'));
    await user.type(screen.getByPlaceholderText(/把产品卖点卡粘贴到这里/), '卖点内容');
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /确\s*认/ });
      expect(btn).not.toBeDisabled();
    });
    await user.click(screen.getByRole('button', { name: /确\s*认/ }));

    // Step 2 → Step 3
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

  // Test 7: 保存历史按钮调用 saveOutput
  it('calls saveOutput when save button is clicked', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);
    await runFullWorkflow(user, '仿写内容');

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

    await waitFor(() => screen.getByText('导出 .docx'));
    await user.click(screen.getByText('导出 .docx'));

    await waitFor(() => {
      expect(mockExportWord).toHaveBeenCalledWith(
        expect.objectContaining({ content: '仿写内容' }),
      );
    });
  });

  // Test 10 (PR #18 Bug #15): 长 Brief（>400 字）完整展示，不截断
  it('displays full product text without truncation when Brief exceeds 400 chars', async () => {
    const user = userEvent.setup();
    renderWithApp(<QianchuanWriterPage />);

    await openSelectAndPick(user, /孙知羽/);
    await user.click(screen.getByRole('button', { name: '确认，去加载产品 →' }));

    // 切换到粘贴模式
    await waitFor(() => screen.getByText('直接粘贴文本'));
    await user.click(screen.getByText('直接粘贴文本'));

    // 构造 500 字 Brief，含唯一的尾部标记（旧逻辑会截断到 400 字从而丢失此标记）
    const longBrief = '产品卖点'.repeat(20) + 'TAIL_MARKER_UNIQUE_XYZ';
    const textarea = await waitFor(() =>
      screen.getByPlaceholderText(/把产品卖点卡粘贴到这里/),
    );
    // 用 fireEvent.change 一次性灌入长文本，避开 user.type 逐字符 500 次的慢路径
    fireEvent.change(textarea, { target: { value: longBrief } });

    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /确\s*认/ });
      expect(btn).not.toBeDisabled();
    });
    await user.click(screen.getByRole('button', { name: /确\s*认/ }));

    // 断言：尾部标记完整出现在展示区，证明未走旧的 slice(0, 400) 截断
    await waitFor(() => {
      expect(screen.getByText(/TAIL_MARKER_UNIQUE_XYZ/)).toBeInTheDocument();
    });
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
