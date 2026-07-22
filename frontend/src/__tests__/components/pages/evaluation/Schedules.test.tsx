/**
 * Schedules 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListSchedulePolicies = vi.fn();
const mockListVersionsAdmin = vi.fn();
const mockCreateSchedulePolicy = vi.fn();
const mockUpdateSchedulePolicy = vi.fn();
const mockDeleteSchedulePolicy = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listSchedulePolicies: (...args: unknown[]) => mockListSchedulePolicies(...args),
  listVersionsAdmin: (...args: unknown[]) => mockListVersionsAdmin(...args),
  createSchedulePolicy: (...args: unknown[]) => mockCreateSchedulePolicy(...args),
  updateSchedulePolicy: (...args: unknown[]) => mockUpdateSchedulePolicy(...args),
  deleteSchedulePolicy: (...args: unknown[]) => mockDeleteSchedulePolicy(...args),
}));

import SchedulesPage from '../../../../evaluation/pages/Schedules';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const samplePolicies = [
  {
    id: 1,
    name: '夜间全量回归',
    cron: '0 2 * * *',
    version_id: null,
    filter_tags: ['核心集'],
    is_active: true,
    created_by: 1,
    created_at: '2026-07-16T02:00:00Z',
    updated_at: null,
    deleted_at: null,
  },
  {
    id: 2,
    name: '每周一核心集回归',
    cron: '0 9 * * 1',
    version_id: 13,
    filter_tags: [],
    is_active: false,
    created_by: 1,
    created_at: '2026-07-15T09:00:00Z',
    updated_at: null,
    deleted_at: null,
  },
];

describe('SchedulesPage', () => {
  beforeEach(() => {
    mockListSchedulePolicies.mockReset();
    mockListVersionsAdmin.mockReset();
  });

  it('渲染策略列表', async () => {
    mockListSchedulePolicies.mockResolvedValue(samplePolicies);
    mockListVersionsAdmin.mockResolvedValue([]);
    renderWithProviders(<SchedulesPage />);
    expect(screen.getByText('定时策略')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('夜间全量回归')).toBeInTheDocument();
      expect(screen.getByText('每周一核心集回归')).toBeInTheDocument();
    });
    expect(screen.getByText(/共 2 条策略/)).toBeInTheDocument();
  });

  it('加载失败时显示错误', async () => {
    mockListSchedulePolicies.mockRejectedValue(new Error('权限拒绝'));
    mockListVersionsAdmin.mockResolvedValue([]);
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => {
      expect(screen.getByText('权限拒绝')).toBeInTheDocument();
    });
  });

  it('空列表显示空状态', async () => {
    mockListSchedulePolicies.mockResolvedValue([]);
    mockListVersionsAdmin.mockResolvedValue([]);
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无定时策略，点击右上角「新建策略」开始配置 cron 回归')).toBeInTheDocument();
    });
  });
});
