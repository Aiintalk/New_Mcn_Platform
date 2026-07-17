import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// Mock API
const mockGetConfigs = vi.fn();
const mockUpdateConfig = vi.fn();
const mockGetAiModels = vi.fn();

vi.mock('../../../api/materialLibrary', () => ({
  getMaterialLibraryConfigs: (...args: unknown[]) => mockGetConfigs(...args),
  updateMaterialLibraryConfig: (...args: unknown[]) => mockUpdateConfig(...args),
}));

vi.mock('../../../api/ai', () => ({
  getAiModels: (...args: unknown[]) => mockGetAiModels(...args),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn() },
  };
});

import MaterialLibraryConfigTab from '../../../pages/admin/MaterialLibraryConfigTab';

const sampleConfig = {
  id: 1,
  config_key: 'soul_generator',
  ai_model_id: 3,
  system_prompt: '你是人格档案生成器，根据问卷数据生成 soul.md\n占位符：{{kol_name}} {{intake_answers}}',
  is_active: true,
  updated_at: '2026-06-25T10:00:00Z',
};

const sampleModels = {
  items: [
    { id: 3, name: 'Claude Sonnet', model_id: 'claude-sonnet-4-6' },
    { id: 4, name: 'GLM-4.6', model_id: 'glm-4.6' },
  ],
  pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
};

describe('MaterialLibraryConfigTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetConfigs.mockResolvedValue([sampleConfig]);
    mockGetAiModels.mockResolvedValue(sampleModels);
    mockUpdateConfig.mockResolvedValue(sampleConfig);
  });

  // Test 1: 渲染加载默认配置
  it('renders soul_generator config after loading', async () => {
    render(<App><MaterialLibraryConfigTab /></App>);

    await waitFor(() => {
      expect(mockGetConfigs).toHaveBeenCalled();
      expect(mockGetAiModels).toHaveBeenCalled();
    });

    await waitFor(() => {
      // 配置项说明文本 — soul_generator（从入驻问卷数据生成人格档案初稿）
      expect(screen.getByText(/从入驻问卷数据生成人格档案初稿/)).toBeInTheDocument();
    });
  });

  // Test 2: 启用状态显示
  it('shows enabled status badge', async () => {
    render(<App><MaterialLibraryConfigTab /></App>);

    await waitFor(() => {
      // 顶部状态卡 + 表单内 Switch label 都可能含 "启用"，至少有一个
      const badges = screen.getAllByText('启用');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  // Test 3: 系统提示词文本框显示现有内容
  it('renders system prompt textarea with existing value', async () => {
    render(<App><MaterialLibraryConfigTab /></App>);

    await waitFor(() => {
      const textarea = screen.getByDisplayValue(/你是人格档案生成器/) as HTMLTextAreaElement;
      expect(textarea).toBeInTheDocument();
    });
  });

  // Test 4: 保存按钮调用 updateMaterialLibraryConfig
  it('calls updateMaterialLibraryConfig when save clicked', async () => {
    const user = userEvent.setup();
    render(<App><MaterialLibraryConfigTab /></App>);

    // 等表单挂载好（system_prompt textarea 出现表示加载完成）
    await waitFor(() => screen.getByDisplayValue(/你是人格档案生成器/));

    // AntD 会给两个中文字之间自动插入空格（"保存"→"保 存"）
    const saveBtn = await waitFor(() => {
      const btn = screen.getAllByRole('button').find((b) => /^保\s*存$/.test(b.textContent || ''));
      if (!btn) throw new Error('save button not found');
      return btn;
    });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalled();
    });
  });

  // Test 5: AI 模型下拉显示选项
  it('renders AI model options in select', async () => {
    render(<App><MaterialLibraryConfigTab /></App>);

    await waitFor(() => {
      expect(screen.getByText(/Claude Sonnet/)).toBeInTheDocument();
    });
  });

  // Test 6: 配置不存在时显示空状态
  it('renders empty state when no config exists', async () => {
    mockGetConfigs.mockResolvedValue([]);
    render(<App><MaterialLibraryConfigTab /></App>);

    await waitFor(() => {
      expect(screen.getByText('配置项不存在')).toBeInTheDocument();
    });
  });
});
