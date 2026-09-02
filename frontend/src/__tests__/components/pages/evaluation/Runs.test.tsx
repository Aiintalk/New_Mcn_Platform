/**
 * Runs 页面测试（Phase 4：数据源改为 GET /runs API，不再用 localStorage）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListRuns = vi.fn();
const mockListVersionsOperator = vi.fn();
const mockTriggerRun = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listRuns: (...args: unknown[]) => mockListRuns(...args),
  listVersionsOperator: (...args: unknown[]) => mockListVersionsOperator(...args),
  triggerRun: (...args: unknown[]) => mockTriggerRun(...args),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import RunsPage from '../../../../evaluation/pages/Runs';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const EMPTY_PAGED = { items: [], pagination: { page: 1, page_size: 50, total: 0, total_pages: 0 } };

function paged(items: unknown[], total = items.length) {
  return { items, pagination: { page: 1, page_size: 50, total, total_pages: total > 0 ? 1 : 0 } };
}

function makeRun(overrides: Partial<Record<string, unknown>> = {}) {
  return {
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
    ...overrides,
  };
}

describe('RunsPage', () => {
  beforeEach(() => {
    mockListRuns.mockReset();
    mockListVersionsOperator.mockReset();
    mockTriggerRun.mockReset();
    mockListRuns.mockResolvedValue(EMPTY_PAGED);
    mockListVersionsOperator.mockResolvedValue([sampleVersion]);
  });

  it('渲染空状态与统计（API 返回空）', async () => {
    renderWithProviders(<RunsPage />);
    expect(screen.getByText('运行管理')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('暂无运行记录，点击右上角「新建运行」触发一次回归')).toBeInTheDocument();
    });
    // listRuns 被调用（page_size=100）
    expect(mockListRuns).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 50 }));
    // 运行总数 = 0
    expect(screen.getByText('运行总数').parentElement?.querySelector('.stat-value')?.textContent).toBe('0');
  });

  it('从 API 加载运行列表', async () => {
    mockListRuns.mockResolvedValue(paged([makeRun({ id: 1, name: 'v1.3 创建自动回归' })], 1));
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('v1.3 创建自动回归')).toBeInTheDocument();
    });
    // 运行总数 = total（1）
    expect(screen.getByText('运行总数').parentElement?.querySelector('.stat-value')?.textContent).toBe('1');
  });

  it('点击子 tab 过滤运行（客户端）', async () => {
    mockListRuns.mockResolvedValue(
      paged([
        makeRun({ id: 1, name: '运行A', status: 'completed' }),
        makeRun({ id: 2, name: '运行B', status: 'running', completed_cases: 7 }),
      ], 2),
    );
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('运行A')).toBeInTheDocument();
      expect(screen.getByText('运行B')).toBeInTheDocument();
    });
    // 切到「进行中」（sub-tab 按钮，区别于 stat-card 标签）
    const subTabs = screen.getAllByText('进行中');
    const tabBtn = subTabs.find((el) => el.closest('.sub-tab') !== null) ?? subTabs[0];
    fireEvent.click(tabBtn);
    expect(screen.getByText('运行B')).toBeInTheDocument();
    expect(screen.queryByText('运行A')).not.toBeInTheDocument();
  });

  it('「进行中」含排队中的 pending run（回归：新触发的 run 曾在"进行中"里消失）', async () => {
    mockListRuns.mockResolvedValue(
      paged([
        makeRun({ id: 1, name: '已完成的运行', status: 'completed' }),
        makeRun({ id: 2, name: '排队中的运行', status: 'pending', total_cases: 10, completed_cases: 0 }),
        makeRun({ id: 3, name: '执行中的运行', status: 'running', completed_cases: 3 }),
      ], 3),
    );
    renderWithProviders(<RunsPage />);
    await waitFor(() => expect(screen.getByText('排队中的运行')).toBeInTheDocument());

    // 「进行中」统计卡 = pending(1) + running(1) = 2（stat-card 里的标签，区别于 sub-tab）
    const statLabel = screen.getAllByText('进行中').find((el) => el.closest('.stat-card') !== null);
    expect(statLabel?.closest('.stat-card')?.querySelector('.stat-value')?.textContent).toBe('2');

    // 切到「进行中」tab：pending 和 running 都可见，completed 不可见
    const subTabs = screen.getAllByText('进行中');
    const tabBtn = subTabs.find((el) => el.closest('.sub-tab') !== null) ?? subTabs[0];
    fireEvent.click(tabBtn);
    expect(screen.getByText('排队中的运行')).toBeInTheDocument();
    expect(screen.getByText('执行中的运行')).toBeInTheDocument();
    expect(screen.queryByText('已完成的运行')).not.toBeInTheDocument();
  });

  it('listRuns 失败降级为空列表（不崩溃）', async () => {
    mockListRuns.mockRejectedValue(new Error('网络错误'));
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无运行记录，点击右上角「新建运行」触发一次回归')).toBeInTheDocument();
    });
  });

  it('版本列表加载失败不影响页面渲染（静默）', async () => {
    mockListVersionsOperator.mockRejectedValue(new Error('网络错误'));
    renderWithProviders(<RunsPage />);
    await waitFor(() => {
      expect(screen.getByText('运行管理')).toBeInTheDocument();
    });
  });
});

const sampleVersion = {
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
};

// AntD Select 选项选择辅助
async function pickSelectOption(placeholder: string, optionText: string) {
  const selector = screen.getByText(placeholder).closest('.ant-select-selector')!;
  fireEvent.mouseDown(selector);
  const opt = await screen.findByText(optionText);
  fireEvent.click(opt);
}

describe('RunsPage — 触发运行交互', () => {
  beforeEach(() => {
    mockListRuns.mockReset();
    mockListVersionsOperator.mockReset();
    mockTriggerRun.mockReset();
    mockNavigate.mockReset();
    mockListRuns.mockResolvedValue(EMPTY_PAGED);
    mockListVersionsOperator.mockResolvedValue([sampleVersion]);
  });

  async function openTriggerDrawer() {
    renderWithProviders(<RunsPage />);
    await waitFor(() => expect(screen.getByText('运行管理')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新建运行'));
    await screen.findByText('开始运行');
  }

  it('触发全量样本运行：调用 triggerRun + 跳转详情 + 刷新列表', async () => {
    await openTriggerDrawer();
    fireEvent.change(screen.getByPlaceholderText('例：v1.3 核心集手动回归'), {
      target: { value: '手动回归A' },
    });
    await pickSelectOption('选择一个 active 版本', 'v1.3（启用）');
    mockTriggerRun.mockResolvedValue(makeRun({ id: 55, name: '手动回归A', status: 'pending', total_cases: 0 }));
    fireEvent.click(screen.getByText('开始运行'));
    await waitFor(() => {
      expect(mockTriggerRun).toHaveBeenCalledWith(
        expect.objectContaining({
          version_id: 10, name: '手动回归A', filter_tags: [], trigger_type: 'manual',
        }),
      );
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/evaluation/runs/55');
    });
    // 触发后刷新列表（listRuns 至少 2 次：初始 + 触发后）
    await waitFor(() => {
      expect(mockListRuns.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('按标签筛选：scope=tags 展示标签 Select（覆盖条件渲染）', async () => {
    await openTriggerDrawer();
    fireEvent.change(screen.getByPlaceholderText('例：v1.3 核心集手动回归'), {
      target: { value: '标签回归' },
    });
    await pickSelectOption('选择一个 active 版本', 'v1.3（启用）');
    fireEvent.click(screen.getByText('按标签筛选'));
    expect(await screen.findByText('输入标签后回车，多个标签为交集')).toBeInTheDocument();
    mockTriggerRun.mockResolvedValue(makeRun({ id: 56, name: '标签回归', status: 'pending' }));
    fireEvent.click(screen.getByText('开始运行'));
    await waitFor(() => {
      expect(mockTriggerRun).toHaveBeenCalledWith(expect.objectContaining({ name: '标签回归' }));
    });
  });

  it('触发失败显示错误且不跳转', async () => {
    await openTriggerDrawer();
    fireEvent.change(screen.getByPlaceholderText('例：v1.3 核心集手动回归'), {
      target: { value: '失败回归' },
    });
    await pickSelectOption('选择一个 active 版本', 'v1.3（启用）');
    mockTriggerRun.mockRejectedValue(new Error('版本未启用'));
    fireEvent.click(screen.getByText('开始运行'));
    await waitFor(() => {
      expect(screen.getByText(/版本未启用/)).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
