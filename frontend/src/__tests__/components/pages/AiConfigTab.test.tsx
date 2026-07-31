import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ---- Mock API（必须在 import 组件之前）----------------------------------------
const mockGetAiKeys    = vi.fn();
const mockGetAiModels  = vi.fn();
const mockGetAiStats   = vi.fn();
const mockCreateAiKey  = vi.fn();
const mockCreateAiModel = vi.fn();

vi.mock('../../../api/ai', () => ({
  getAiKeys:    (...args: unknown[]) => mockGetAiKeys(...args),
  getAiModels:  (...args: unknown[]) => mockGetAiModels(...args),
  getAiStats:   (...args: unknown[]) => mockGetAiStats(...args),
  createAiKey:  (...args: unknown[]) => mockCreateAiKey(...args),
  createAiModel:(...args: unknown[]) => mockCreateAiModel(...args),
  updateAiKey:    vi.fn(),
  deleteAiKey:    vi.fn(),
  updateAiModel:  vi.fn(),
  deleteAiModel:  vi.fn(),
  testAiKey:      vi.fn(),
  testAiModel:    vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn() } };
});

import { AiConfigTab } from '../../../pages/admin/ServiceConfigPage';

// ---- 固定数据 ----------------------------------------------------------------
const emptyStats = {
  summary: {
    total_keys: 0, healthy_keys: 0, model_count: 0, total_tokens: 0,
    avg_latency_ms: 0, service_status: 'unavailable' as const,
    current_active: 0, total_capacity: 0,
  },
  by_model: [],
  token_trend: [],
};

type UserInstance = ReturnType<typeof userEvent.setup>;

/** 在 antd Select 的下拉 portal 内查找匹配文本的选项（避开页面其他位置同名文本冲突） */
function findOptionInPortal(optionText: RegExp): HTMLElement {
  const opts = Array.from(document.querySelectorAll<HTMLElement>('.ant-select-item-option-content'));
  const hit = opts.find(o => optionText.test(o.textContent ?? ''));
  if (!hit) throw new Error(`选项 ${optionText} 不在 Select 下拉 portal 中。当前选项：${opts.map(o => o.textContent).join(', ')}`);
  return hit;
}

/** 打开 AntD Select 下拉并选指定选项。selectorIndex 用于多 Select 场景。 */
async function openSelectAndPick(user: UserInstance, optionText: RegExp, selectorIndex = 0): Promise<void> {
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-select-selector').length).toBeGreaterThan(selectorIndex);
  });
  const selectSelector = document.querySelectorAll('.ant-select-selector')[selectorIndex] as HTMLElement;
  await act(async () => {
    fireEvent.mouseDown(selectSelector);
  });
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-select-item-option-content').length).toBeGreaterThan(0);
  });
  await user.click(findOptionInPortal(optionText));
}

/** 仅打开 Select 下拉不点选项（用于验证选项是否存在于下拉列表） */
async function openSelectDropdown(selectorIndex = 0): Promise<void> {
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-select-selector').length).toBeGreaterThan(selectorIndex);
  });
  const selectSelector = document.querySelectorAll('.ant-select-selector')[selectorIndex] as HTMLElement;
  await act(async () => {
    fireEvent.mouseDown(selectSelector);
  });
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-select-item-option-content').length).toBeGreaterThan(0);
  });
}

/** 点 Modal 的 OK 按钮（AntD Modal footer 的 primary button） */
async function clickModalOk(): Promise<void> {
  const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement;
  expect(okBtn).toBeTruthy();
  await fireEvent.click(okBtn);
}

describe('AiConfigTab — 自定义厂商支持', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAiKeys.mockResolvedValue({ items: [] });
    mockGetAiModels.mockResolvedValue({ items: [] });
    mockGetAiStats.mockResolvedValue(emptyStats);
    mockCreateAiKey.mockResolvedValue({ id: 99 });
    mockCreateAiModel.mockResolvedValue({ id: 99 });
  });

  // ── 用例 1：加 Key 表单的"服务商"下拉含"自定义厂商"选项 ────────────────
  it('加 Key 表单的服务商下拉包含"自定义厂商"选项', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加 Key/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加 Key/));

    // 打开 Select 下拉（不点选项），验证下拉里含"自定义厂商"
    await openSelectDropdown();
    const optionTexts = Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(o => o.textContent);
    expect(optionTexts).toContain('自定义厂商');
    expect(optionTexts).toContain('云雾');
  });

  // ── 用例 2：选"自定义"后出现"厂商编码"输入框 ──────────────────────────
  it('选自定义厂商后显示"厂商编码"输入框', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加 Key/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加 Key/));

    await openSelectAndPick(user, /自定义厂商/);

    // 出现厂商编码字段
    await waitFor(() => {
      expect(screen.getByText(/厂商编码/)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/如 deepseek/)).toBeInTheDocument();
  });

  // ── 用例 3：选自定义 + 填编码 + 提交 → provider 为用户填的编码 ──────────
  it('选自定义厂商并填编码 deepseek 提交时，createAiKey 收到 provider=deepseek', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加 Key/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加 Key/));

    // 名称（label）
    await user.type(screen.getByPlaceholderText(/如 key-main/), '深度求索主 Key');
    // 服务商选自定义
    await openSelectAndPick(user, /自定义厂商/);
    // 厂商编码
    await user.type(screen.getByPlaceholderText(/如 deepseek/), 'deepseek');
    // base_url（选自定义时清空，必填）
    await user.type(screen.getByPlaceholderText(/https:\/\//), 'https://api.deepseek.com/v1');
    // api_key
    await user.type(document.querySelector('input[type="password"]') as HTMLElement, 'sk-test-123');

    await clickModalOk();

    await waitFor(() => {
      expect(mockCreateAiKey).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'deepseek',
          label: '深度求索主 Key',
          base_url: 'https://api.deepseek.com/v1',
        }),
      );
    });
  });

  // ── 用例 4：选预设厂商 yunwu 提交 → provider=yunwu（不破坏现状）────────
  it('选预设云雾提交时，createAiKey 收到 provider=yunwu（保持现有行为）', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加 Key/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加 Key/));

    await user.type(screen.getByPlaceholderText(/如 key-main/), '云雾主 Key');
    await openSelectAndPick(user, /云雾/);
    await user.type(document.querySelector('input[type="password"]') as HTMLElement, 'sk-yunwu-1');

    await clickModalOk();

    await waitFor(() => {
      expect(mockCreateAiKey).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'yunwu',
          label: '云雾主 Key',
        }),
      );
    });
  });

  // ── 用例 5：加模型表单也有"自定义厂商"选项 ────────────────────────────
  it('加模型表单的服务商下拉也包含"自定义厂商"选项', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加模型/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加模型/));

    await openSelectDropdown();
    const optionTexts = Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(o => o.textContent);
    expect(optionTexts).toContain('自定义厂商');
  });

  // ── 用例 6：自定义编码格式校验（大写字母非法）─────────────────────────
  it('厂商编码含大写字母时校验失败，不发起 API 调用', async () => {
    const user = userEvent.setup();
    render(<AiConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 添加 Key/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 添加 Key/));

    await user.type(screen.getByPlaceholderText(/如 key-main/), 'Test');
    await openSelectAndPick(user, /自定义厂商/);
    // 填非法编码（大写）
    await user.type(screen.getByPlaceholderText(/如 deepseek/), 'DeepSeek');
    await user.type(screen.getByPlaceholderText(/https:\/\//), 'https://api.deepseek.com/v1');
    await user.type(document.querySelector('input[type="password"]') as HTMLElement, 'sk-x');

    await clickModalOk();

    // 应该校验失败、不发 API（等错误消息出现）
    await waitFor(() => {
      expect(screen.getByText(/小写字母/)).toBeInTheDocument();
    });
    expect(mockCreateAiKey).not.toHaveBeenCalled();
  });
});
