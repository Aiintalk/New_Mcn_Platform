import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

const mockGet = vi.fn();
const mockGetAiModels = vi.fn();

vi.mock('../../../api/request', () => ({
  get: (...args: unknown[]) => mockGet(...args),
  put: vi.fn(),
}));

vi.mock('../../../api/ai', () => ({
  getAiModels: (...args: unknown[]) => mockGetAiModels(...args),
}));

import QianchuanPreviewConfigTab from '../../../pages/admin/QianchuanPreviewConfigTab';

describe('QianchuanPreviewConfigTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue([{ id: 1, config_key: 'full_video', ai_model_id: null, system_prompt: null, is_active: true, updated_at: null }]);
    mockGetAiModels.mockResolvedValue({
      items: [
        { id: 1, name: 'Gemini 视频模型', provider: 'gemini', model_id: 'gemini-2.5-pro', status: 'active' },
        { id: 2, name: '其他模型', provider: 'yunwu', model_id: 'other-model', status: 'active' },
      ],
      total: 2,
    });
  });

  it('labels full-video config clearly and only offers active Gemini models', async () => {
    const user = userEvent.setup();
    render(<App><QianchuanPreviewConfigTab /></App>);

    expect(await screen.findByText('千川成片预审')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '编辑' }));
    await user.click(screen.getByRole('combobox'));

    expect(await screen.findByText(/Gemini 视频模型/)).toBeInTheDocument();
    expect(screen.queryByText(/其他模型/)).not.toBeInTheDocument();
  });
});
