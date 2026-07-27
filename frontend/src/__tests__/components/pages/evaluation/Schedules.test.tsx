/**
 * Schedules 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
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

describe('SchedulesPage — 策略 CRUD + cron 校验', () => {
  beforeEach(() => {
    mockListSchedulePolicies.mockReset();
    mockListVersionsAdmin.mockReset();
    mockCreateSchedulePolicy.mockReset();
    mockUpdateSchedulePolicy.mockReset();
    mockDeleteSchedulePolicy.mockReset();
  });

  async function renderLoaded() {
    mockListSchedulePolicies.mockResolvedValue(samplePolicies);
    mockListVersionsAdmin.mockResolvedValue([]);
    renderWithProviders(<SchedulesPage />);
    await waitFor(() => expect(screen.getByText('夜间全量回归')).toBeInTheDocument());
  }

  it('新建策略：填名称后保存调用 createSchedulePolicy', async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText('新建策略'));
    const nameInput = await screen.findByPlaceholderText('例：夜间全量回归');
    fireEvent.change(nameInput, { target: { value: '每日早班回归' } });
    mockCreateSchedulePolicy.mockResolvedValue({ id: 9 });
    // Modal okText="保存"（2 字 → "保 存"）
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
    await waitFor(() => {
      expect(mockCreateSchedulePolicy).toHaveBeenCalledWith(
        expect.objectContaining({ name: '每日早班回归', cron: '0 2 * * *' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/策略已创建/)).toBeInTheDocument();
    });
  });

  it('编辑策略：加载后保存调用 updateSchedulePolicy', async () => {
    await renderLoaded();
    const row = screen.getByText('夜间全量回归').closest('tr')!;
    fireEvent.click(within(row).getByText(/编\s*辑/));
    // 表单回填策略名
    const nameInput = await screen.findByDisplayValue('夜间全量回归');
    expect(nameInput).toBeInTheDocument();
    mockUpdateSchedulePolicy.mockResolvedValue({});
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
    await waitFor(() => {
      expect(mockUpdateSchedulePolicy).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: '夜间全量回归', cron: '0 2 * * *' }),
      );
    });
  });

  it('删除策略：确认后调用 deleteSchedulePolicy', async () => {
    await renderLoaded();
    mockDeleteSchedulePolicy.mockResolvedValue({});
    const row = screen.getByText('夜间全量回归').closest('tr')!;
    fireEvent.click(within(row).getByText(/删\s*除/));
    const confirmBtn = await screen.findByRole('button', { name: /软\s*删/ });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockDeleteSchedulePolicy).toHaveBeenCalledWith(1);
    });
  });

  it('cron 客户端预校验：非法→「需 5 字段」，合法→「看起来合法」', async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText('新建策略'));
    const cronInput = await screen.findByPlaceholderText('0 2 * * *');
    // 初始 '0 2 * * *' → 合法
    expect(screen.getByText(/看起来合法/)).toBeInTheDocument();
    // 改为非法
    fireEvent.change(cronInput, { target: { value: 'bad' } });
    await waitFor(() => {
      expect(screen.getByText('需 5 字段')).toBeInTheDocument();
    });
    // 改回合法
    fireEvent.change(cronInput, { target: { value: '0 9 * * *' } });
    await waitFor(() => {
      expect(screen.getByText(/看起来合法/)).toBeInTheDocument();
    });
  });
});
