/**
 * Versions 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
