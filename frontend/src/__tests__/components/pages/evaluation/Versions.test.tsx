/**
 * Versions 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListVersionsAdmin = vi.fn();
const mockListDimensions = vi.fn();
const mockDeleteVersion = vi.fn();
const mockCreateVersion = vi.fn();
const mockCloneVersion = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listVersionsAdmin: (...args: unknown[]) => mockListVersionsAdmin(...args),
  listDimensions: (...args: unknown[]) => mockListDimensions(...args),
  deleteVersion: (...args: unknown[]) => mockDeleteVersion(...args),
  createVersion: (...args: unknown[]) => mockCreateVersion(...args),
  cloneVersion: (...args: unknown[]) => mockCloneVersion(...args),
}));

import VersionsPage from '../../../../evaluation/pages/Versions';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const sampleVersions = [
  {
    id: 13,
    tool_code: 'qianchuan-writer',
    name: 'v1.3-行动引导',
    description: '调整行动引导句式',
    config_payload: {},
    parent_version_id: 12,
    source_kol_id: 1024,
    auto_run_on_create: true,
    auto_run_tags: ['核心集'],
    is_active: true,
    created_by: 1,
    created_at: '2026-07-16T10:20:00Z',
    updated_at: null,
    deleted_at: null,
  },
  {
    id: 12,
    tool_code: 'qianchuan-writer',
    name: 'v1.2-痛点共鸣',
    description: '增加痛点共鸣要求',
    config_payload: {},
    parent_version_id: 11,
    source_kol_id: 1024,
    auto_run_on_create: false,
    auto_run_tags: [],
    is_active: false,
    created_by: 1,
    created_at: '2026-07-12T15:40:00Z',
    updated_at: null,
    deleted_at: null,
  },
];

describe('VersionsPage', () => {
  beforeEach(() => {
    mockListVersionsAdmin.mockReset();
    mockListDimensions.mockReset();
  });

  it('渲染版本列表与统计计数', async () => {
    mockListVersionsAdmin.mockResolvedValue(sampleVersions);
    mockListDimensions.mockResolvedValue([]);
    renderWithProviders(<VersionsPage />);
    expect(screen.getByText('版本快照')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('v1.3-行动引导')).toBeInTheDocument();
      expect(screen.getByText('v1.2-痛点共鸣')).toBeInTheDocument();
    });
    expect(screen.getByText(/共 2 个版本/)).toBeInTheDocument();
  });

  it('加载失败时显示错误', async () => {
    mockListVersionsAdmin.mockRejectedValue(new Error('网络错误'));
    mockListDimensions.mockResolvedValue([]);
    renderWithProviders(<VersionsPage />);
    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument();
    });
  });

  it('空列表显示空状态', async () => {
    mockListVersionsAdmin.mockResolvedValue([]);
    mockListDimensions.mockResolvedValue([]);
    renderWithProviders(<VersionsPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无版本快照')).toBeInTheDocument();
    });
  });
});

describe('VersionsPage — 创建 / 克隆 / 删除交互', () => {
  beforeEach(() => {
    mockListVersionsAdmin.mockReset();
    mockListDimensions.mockReset();
    mockDeleteVersion.mockReset();
    mockCreateVersion.mockReset();
    mockCloneVersion.mockReset();
  });

  async function renderLoaded() {
    mockListVersionsAdmin.mockResolvedValue(sampleVersions);
    mockListDimensions.mockResolvedValue([]);
    renderWithProviders(<VersionsPage />);
    await waitFor(() => expect(screen.getByText('v1.3-行动引导')).toBeInTheDocument());
  }

  it('新建版本：填版本名后创建调用 createVersion', async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText('新建版本'));
    const nameInput = await screen.findByPlaceholderText('例：v1.3-行动引导');
    fireEvent.change(nameInput, { target: { value: 'v1.4-人设强化' } });
    mockCreateVersion.mockResolvedValue({ id: 14, name: 'v1.4-人设强化' });
    fireEvent.click(screen.getByText('创建版本'));
    await waitFor(() => {
      expect(mockCreateVersion).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'v1.4-人设强化', tool_code: 'qianchuan-writer' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/已创建/)).toBeInTheDocument();
    });
  });

  it('复制为新版本：自动带出 -copy 名后调用 cloneVersion', async () => {
    await renderLoaded();
    mockCloneVersion.mockResolvedValue({ id: 14, name: 'v1.3-行动引导-copy' });
    // 第一行（id=13）的「复制为新版本」按钮
    fireEvent.click(screen.getAllByText('复制为新版本')[0]);
    // 抽屉打开，cloneForm 自动填 name = `${原name}-copy`
    const nameInput = await screen.findByDisplayValue('v1.3-行动引导-copy');
    expect(nameInput).toBeInTheDocument();
    fireEvent.click(screen.getByText('创建副本'));
    await waitFor(() => {
      expect(mockCloneVersion).toHaveBeenCalledWith(
        13,
        expect.objectContaining({ name: 'v1.3-行动引导-copy' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/已复制为新版本/)).toBeInTheDocument();
    });
  });

  it('删除版本：确认后调用 deleteVersion', async () => {
    await renderLoaded();
    mockDeleteVersion.mockResolvedValue({});
    // 用 within 限定到 id=13 版本行（「删除」按钮 2 字 → "删 除"）
    const row = screen.getByText('v1.3-行动引导').closest('tr')!;
    fireEvent.click(within(row).getByText(/删\s*除/));
    const confirmBtn = await screen.findByRole('button', { name: /软\s*删/ });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockDeleteVersion).toHaveBeenCalledWith(13);
    });
  });

  it('创建失败时提示错误', async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText('新建版本'));
    const nameInput = await screen.findByPlaceholderText('例：v1.3-行动引导');
    fireEvent.change(nameInput, { target: { value: 'v1.4' } });
    mockCreateVersion.mockRejectedValue(new Error('名字重复'));
    fireEvent.click(screen.getByText('创建版本'));
    await waitFor(() => {
      expect(screen.getByText(/名字重复/)).toBeInTheDocument();
    });
  });
});
