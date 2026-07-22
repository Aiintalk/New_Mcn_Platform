/**
 * Runs 页面测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListVersionsOperator = vi.fn();
const mockTriggerRun = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listVersionsOperator: (...args: unknown[]) => mockListVersionsOperator(...args),
  triggerRun: (...args: unknown[]) => mockTriggerRun(...args),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

import RunsPage from '../../../../evaluation/pages/Runs';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // 重置 localStorage（jsdom 有时不存在 clear，做防御）
  try {
    window.localStorage?.clear?.();
  } catch {
    // 静默
  }
});

describe('RunsPage', () => {
  beforeEach(() => {
    mockListVersionsOperator.mockReset();
    mockTriggerRun.mockReset();
    mockListVersionsOperator.mockResolvedValue([
      {
        id: 10,
        tool_code: 'qianchuan-writer',
        name: 'v1.3',
        description: null,
        config_payload: {},
        parent_version_id: null,
        source_kol_id: null,
        auto_run_on_create: false,
        auto_run_tags: [],
        is_active: true,
        created_by: 1,
        created_at: null,
        updated_at: null,
        deleted_at: null,
      },
    ]);
  });

  it('渲染空状态与统计', async () => {
    renderWithProviders(<RunsPage />);
    expect(screen.getByText('运行管理')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('暂无运行记录，点击右上角「新建运行」触发一次回归')).toBeInTheDocument();
    });
    // 统计 4 张卡 都显示 0
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(4);
  });

  it('从 localStorage 恢复历史运行', async () => {
    localStorage.setItem(
      'eval_runs_cache',
      JSON.stringify([
        {
          id: 1,
          version_id: 10,
          strategy_id: 1,
          name: 'v1.3 创建自动回归',
          trigger_type: 'manual',
          status: 'completed',
          filter_tags: [],
          total_cases: 28,
          completed_cases: 28,
          failed_cases: 0,
          metadata: {},
          created_by: 1,
          started_at: '2026-07-16T10:21:00Z',
          finished_at: '2026-07-16T10:27:00Z',
          created_at: '2026-07-16T10:21:00Z',
        },
      ]),
    );
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('v1.3 创建自动回归')).toBeInTheDocument();
    });
  });

  it('点击子 tab 过滤运行', async () => {
    localStorage.setItem(
      'eval_runs_cache',
      JSON.stringify([
        {
          id: 1,
          version_id: 10,
          strategy_id: 1,
          name: '运行A',
          trigger_type: 'manual',
          status: 'completed',
          filter_tags: [],
          total_cases: 28,
          completed_cases: 28,
          failed_cases: 0,
          metadata: {},
          created_by: 1,
          started_at: null,
          finished_at: null,
          created_at: '2026-07-16T10:21:00Z',
        },
        {
          id: 2,
          version_id: 10,
          strategy_id: 1,
          name: '运行B',
          trigger_type: 'manual',
          status: 'running',
          filter_tags: [],
          total_cases: 28,
          completed_cases: 7,
          failed_cases: 0,
          metadata: {},
          created_by: 1,
          started_at: null,
          finished_at: null,
          created_at: '2026-07-16T10:21:00Z',
        },
      ]),
    );
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('运行A')).toBeInTheDocument();
      expect(screen.getByText('运行B')).toBeInTheDocument();
    });
    // 切到「进行中」（sub-tab 按钮，区别于 stat-card 标签）
    const subTabs = screen.getAllByText('进行中');
    // 选择 sub-tab（按钮元素）那一个
    const tabBtn = subTabs.find((el) => el.closest('.sub-tab') !== null) ?? subTabs[0];
    fireEvent.click(tabBtn);
    expect(screen.getByText('运行B')).toBeInTheDocument();
    expect(screen.queryByText('运行A')).not.toBeInTheDocument();
  });
});
