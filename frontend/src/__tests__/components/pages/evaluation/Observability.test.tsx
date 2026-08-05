/**
 * Observability 页面测试（Phase 5 可观测仪表盘）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockGetQueueStats = vi.fn();
const mockGetRunJobs = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  getQueueStats: (...args: unknown[]) => mockGetQueueStats(...args),
  getRunJobs: (...args: unknown[]) => mockGetRunJobs(...args),
}));

import ObservabilityPage from '../../../../evaluation/pages/Observability';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const SAMPLE_STATS = {
  pending: 3, running: 2, failed_dead_letter: 1, done: 10, cancelled: 0,
  oldest_pending_secs: 120, runs_active: 2,
};

describe('ObservabilityPage', () => {
  beforeEach(() => {
    mockGetQueueStats.mockReset();
    mockGetRunJobs.mockReset();
    mockGetQueueStats.mockResolvedValue(SAMPLE_STATS);
  });

  it('渲染队列健康度卡片', async () => {
    renderWithProviders(<ObservabilityPage />);
    expect(screen.getByText('评测监控')).toBeInTheDocument();
    await waitFor(() => expect(mockGetQueueStats).toHaveBeenCalled());
    // oldest_pending_secs=120 → "120s"（唯一值，证明 stats 落到卡片）
    await waitFor(() => expect(screen.getByText('120s')).toBeInTheDocument());
  });

  it('输入 run id 查 jobs 明细（含 last_error 失败原因）', async () => {
    mockGetRunJobs.mockResolvedValue([
      {
        id: 31, test_case_id: 7, status: 'failed', attempts: 3, max_attempts: 3,
        last_error: 'chat failed [glm]: ReadTimeout',
        enqueued_at: 't', started_at: 't', finished_at: 't',
      },
    ]);
    renderWithProviders(<ObservabilityPage />);
    await waitFor(() => expect(mockGetQueueStats).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText('run id，如 16'), { target: { value: '16' } });
    fireEvent.click(screen.getByRole('button', { name: /查\s*看\s*jobs/ }));

    await waitFor(() => expect(mockGetRunJobs).toHaveBeenCalledWith(16));
    await waitFor(() => expect(screen.getByText(/ReadTimeout/)).toBeInTheDocument());
  });

  it('queue-stats 加载失败提示错误', async () => {
    mockGetQueueStats.mockRejectedValue(new Error('无权限'));
    renderWithProviders(<ObservabilityPage />);
    await waitFor(() => expect(screen.getByText(/无权限/)).toBeInTheDocument());
  });

  it('空 run id 点查看 → 警告不调 getRunJobs', async () => {
    renderWithProviders(<ObservabilityPage />);
    await waitFor(() => expect(mockGetQueueStats).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /查\s*看\s*jobs/ }));
    await waitFor(() => expect(screen.getByText(/请输入 run id/)).toBeInTheDocument());
    expect(mockGetRunJobs).not.toHaveBeenCalled();
  });
});
