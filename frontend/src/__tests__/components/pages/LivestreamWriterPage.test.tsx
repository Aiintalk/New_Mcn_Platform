import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

const mockGetKolPersonas = vi.fn();
const mockChatStream = vi.fn();
const mockGetActiveProducts = vi.fn();
const mockGetWorkspaceDashboard = vi.fn();

vi.mock('../../../api/livestreamWriter', () => ({
  getKolPersonas: (...args: unknown[]) => mockGetKolPersonas(...args),
  parseFile: vi.fn(),
  chatStream: (...args: unknown[]) => mockChatStream(...args),
}));

vi.mock('../../../api/kolWorkspace', () => ({
  getActiveProducts: (...args: unknown[]) => mockGetActiveProducts(...args),
  getWorkspaceDashboard: (...args: unknown[]) => mockGetWorkspaceDashboard(...args),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

Element.prototype.scrollIntoView = vi.fn();

import { LivestreamWriterModule } from '../../../pages/operator/LivestreamWriterPage';

function streamResponse(content: string): Response {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(content));
        controller.close();
      },
    }),
  } as Response;
}

describe('LivestreamWriterModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetKolPersonas.mockResolvedValue({
      personas: [{ id: 7, name: '孙知羽', soul: '美妆达人', contentPlan: '护肤内容' }],
    });
    mockGetWorkspaceDashboard.mockResolvedValue({
      kol: { id: 7, name: '孙知羽', avatar_url: null, category: '美妆' },
    });
    mockGetActiveProducts.mockResolvedValue([{
      id: 31,
      nickname: '当前精华',
      core_selling_point: '熬夜也能稳住肤况',
      visualization: null,
      mechanism: '限时买一送一',
      mechanism_exclusive: true,
      endorsement: null,
      user_feedback: null,
      unique_selling: null,
      awards: null,
      efficacy_proof: null,
    }]);
  });

  it('工作台内嵌模式展示当前商品并只提交标识和已确认对标文案', async () => {
    const user = userEvent.setup();
    mockChatStream.mockResolvedValue(streamResponse('### 四、直播讲解脚本\n完整脚本'));

    render(<App><LivestreamWriterModule kolId={7} /></App>);

    await waitFor(() => expect(screen.getByText('当前精华')).toBeInTheDocument());
    expect(screen.queryByText('上传产品卖点卡')).not.toBeInTheDocument();
    expect(screen.getByText('熬夜也能稳住肤况')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.type(screen.getByPlaceholderText('粘贴对标直播间文案...'), '对标直播文案');
    await user.click(screen.getByRole('button', { name: '确认锁定对标' }));
    await user.click(screen.getByRole('button', { name: '开始仿写' }));
    await user.click(screen.getByRole('button', { name: '生成开播方案' }));

    await waitFor(() => expect(mockChatStream).toHaveBeenCalledTimes(1));
    expect(mockChatStream).toHaveBeenCalledWith(expect.objectContaining({
      kol_id: 7,
      reference_script: '对标直播文案',
      reference_confirmed: true,
      sp_order: '背书→机制→种草',
      systemPrompt: '',
      createJob: true,
    }));
    expect(mockChatStream.mock.calls[0][0].systemPrompt).not.toContain('熬夜也能稳住肤况');
  });

  it('内嵌模式按红人 ID 选择人设，空档案也不阻断生成', async () => {
    const user = userEvent.setup();
    mockGetKolPersonas.mockResolvedValue({
      personas: [{ id: 8, name: '同名但不是当前红人', soul: '错误人设', contentPlan: '错误规划' }],
    });
    mockGetWorkspaceDashboard.mockResolvedValue({
      kol: { id: 7, name: '空档案红人', avatar_url: null, category: '美妆' },
    });
    mockChatStream.mockResolvedValue(streamResponse('### 四、直播讲解脚本\n完整脚本'));

    render(<App><LivestreamWriterModule kolId={7} /></App>);

    await waitFor(() => expect(screen.getByText('当前精华')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.type(screen.getByPlaceholderText('粘贴对标直播间文案...'), '对标直播文案');
    await user.click(screen.getByRole('button', { name: '确认锁定对标' }));
    await user.click(screen.getByRole('button', { name: '开始仿写' }));
    await user.click(screen.getByRole('button', { name: '生成开播方案' }));

    await waitFor(() => expect(mockChatStream).toHaveBeenCalledTimes(1));
    expect(mockChatStream).toHaveBeenCalledWith(expect.objectContaining({
      workspace_mode: true,
      kol_id: 7,
      systemPrompt: '',
    }));
  });

  it('没有当前商品时明确提示，且不能进入生成', async () => {
    const user = userEvent.setup();
    mockGetActiveProducts.mockResolvedValue([]);

    render(<App><LivestreamWriterModule kolId={7} /></App>);

    await waitFor(() => expect(screen.getByText('还没有当前商品')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    expect(screen.getByRole('link', { name: '前往产品库选择或新建商品' })).toHaveAttribute('href', '/workspace/7?tab=products');
    expect(mockGetActiveProducts).toHaveBeenCalledWith(7);
    await user.click(screen.getByRole('button', { name: '下一步' }));
  });
});
