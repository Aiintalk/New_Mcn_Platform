/**
 * RunDetail 页面测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockGetRun = vi.fn();
const mockListRunScores = vi.fn();
const mockSubmitHumanLabel = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  listRunScores: (...args: unknown[]) => mockListRunScores(...args),
  submitHumanLabel: (...args: unknown[]) => mockSubmitHumanLabel(...args),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ id: '42' }),
  };
});

import RunDetailPage from '../../../../evaluation/pages/RunDetail';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={['/evaluation/runs/42']}>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const sampleRun = {
  id: 42,
  version_id: 13,
  strategy_id: 1,
  name: '核心集全量回归',
  trigger_type: 'manual',
  status: 'completed',
  filter_tags: ['核心集'],
  total_cases: 28,
  completed_cases: 28,
  failed_cases: 0,
  metadata: {},
  created_by: 1,
  started_at: '2026-07-16T10:21:00Z',
  finished_at: '2026-07-16T10:27:22Z',
  created_at: '2026-07-16T10:21:00Z',
};

const sampleScores = [
  {
    id: 100,
    case_result_id: 1,
    dimension_id: 1,
    weight_used: 0.4,
    ai_score: 8.4,
    ai_reasoning: '钩子强，叙事流畅',
    ai_strengths: ['钩子强'],
    ai_weaknesses: [],
    human_score: null,
    human_feedback: null,
    created_at: '2026-07-16T10:25:00Z',
    updated_at: '2026-07-16T10:25:00Z',
  },
  {
    id: 101,
    case_result_id: 1,
    dimension_id: 2,
    weight_used: 0.35,
    ai_score: 7.9,
    ai_reasoning: '转化引导到位',
    ai_strengths: [],
    ai_weaknesses: [],
    human_score: 8.0,
    human_feedback: '人工校准到 8.0',
    created_at: '2026-07-16T10:25:00Z',
    updated_at: '2026-07-16T10:25:00Z',
  },
  {
    id: 102,
    case_result_id: 2,
    dimension_id: 1,
    weight_used: 0.4,
    ai_score: 6.8,
    ai_reasoning: null,
    ai_strengths: [],
    ai_weaknesses: [],
    human_score: null,
    human_feedback: null,
    created_at: '2026-07-16T10:25:00Z',
    updated_at: '2026-07-16T10:25:00Z',
  },
];

describe('RunDetailPage', () => {
  beforeEach(() => {
    mockGetRun.mockReset();
    mockListRunScores.mockReset();
    mockSubmitHumanLabel.mockReset();
  });

  it('渲染运行概览 + 维度概览 + 样本明细', async () => {
    mockGetRun.mockResolvedValue(sampleRun);
    mockListRunScores.mockResolvedValue(sampleScores);
    renderWithProviders(<RunDetailPage />);
    await waitFor(() => {
      expect(screen.getByText('核心集全量回归')).toBeInTheDocument();
    });
    // 整体平均分（8.4 + 7.9 + 6.8）/3 = 7.7
    await waitFor(() => {
      expect(screen.getByText(/7\.7/)).toBeInTheDocument();
    });
    // 维度概览：3 个维度
    expect(mockGetRun).toHaveBeenCalledWith(42);
    expect(mockListRunScores).toHaveBeenCalledWith(42);
  });

  it('加载失败时通过 message.error 提示（验证 API 调用）', async () => {
    mockGetRun.mockRejectedValue(new Error('运行不存在'));
    mockListRunScores.mockResolvedValue([]);
    renderWithProviders(<RunDetailPage />);
    await waitFor(() => {
      expect(mockGetRun).toHaveBeenCalledWith(42);
    });
  });

  it('维度不足 3 个时不渲染雷达图，显示提示', async () => {
    mockGetRun.mockResolvedValue(sampleRun);
    // 同一 dimension_id，雷达图至少需要 3 个不同维度
    mockListRunScores.mockResolvedValue([
      { ...sampleScores[0], dimension_id: 1, case_result_id: 1, id: 200 },
      { ...sampleScores[0], dimension_id: 1, case_result_id: 2, id: 201 },
    ]);
    renderWithProviders(<RunDetailPage />);
    // 等待标题渲染（说明数据已加载）
    await waitFor(() => {
      expect(screen.getByText('核心集全量回归')).toBeInTheDocument();
    });
    // 雷达图提示应在维度数 < 3 时出现
    await waitFor(() => {
      expect(screen.getByText('至少需要 3 个维度才能渲染雷达图')).toBeInTheDocument();
    }, { timeout: 2000 });
  });
});

describe('RunDetailPage — 人工校准交互', () => {
  beforeEach(() => {
    mockGetRun.mockReset();
    mockListRunScores.mockReset();
    mockSubmitHumanLabel.mockReset();
  });

  async function renderLoaded() {
    mockGetRun.mockResolvedValue(sampleRun);
    mockListRunScores.mockResolvedValue(sampleScores);
    renderWithProviders(<RunDetailPage />);
    await waitFor(() => expect(screen.getByText('核心集全量回归')).toBeInTheDocument());
  }

  it('点击校准 → 抽屉打开 → 保存成功调用 submitHumanLabel 并提示', async () => {
    await renderLoaded();
    // score id=100：human_score=null、ai_score=8.4 → openCalibrate 初始化 humanScore=8.4
    const updated = { ...sampleScores[0], human_score: 8.4, human_feedback: '钩子强，认可' };
    mockSubmitHumanLabel.mockResolvedValue(updated);

    // 点击第一个「校准 d1」（score 100，primary 按钮）
    fireEvent.click(screen.getAllByText(/校准 d1/)[0]);

    // 抽屉打开：反馈 textarea 可见，输入反馈
    const feedback = await screen.findByPlaceholderText(/说明本次校准的理由/);
    fireEvent.change(feedback, { target: { value: '钩子强，认可' } });

    // 点击 Drawer extra 的「保存校准」
    const saveBtn = await screen.findByRole('button', { name: '保存校准' });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockSubmitHumanLabel).toHaveBeenCalledWith(100, {
        human_score: 8.4,
        human_feedback: '钩子强，认可',
      });
    });
    // 成功提示
    await waitFor(() => {
      expect(screen.getByText(/人工校准已保存/)).toBeInTheDocument();
    });
  });

  it('保存校准失败时显示错误提示且不关闭抽屉', async () => {
    await renderLoaded();
    mockSubmitHumanLabel.mockRejectedValue(new Error('网络错误'));

    fireEvent.click(screen.getAllByText(/校准 d1/)[0]);
    const saveBtn = await screen.findByRole('button', { name: '保存校准' });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockSubmitHumanLabel).toHaveBeenCalledWith(
        100,
        expect.objectContaining({ human_score: expect.any(Number) }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/网络错误/)).toBeInTheDocument();
    });
  });

  it('打开已有校准时预填人工分数与反馈', async () => {
    await renderLoaded();
    // score id=101：human_score=8.0、human_feedback='人工校准到 8.0'，按钮「校准 d2」
    fireEvent.click(screen.getByText(/校准 d2/));
    const feedback = await screen.findByPlaceholderText(/说明本次校准的理由/);
    expect(feedback).toHaveValue('人工校准到 8.0');
  });

  it('校准成功后本地 scores 更新（行变为已校准）', async () => {
    await renderLoaded();
    // 初始：case_result 1（含 score 101 human_score=8.0）已校准，case_result 2 未校准
    expect(screen.getAllByText('已校准').length).toBe(1);
    expect(screen.getByText('未校准')).toBeInTheDocument();
    // score id=102（case_result 2，第二个「校准 d1」按钮）
    const updated = { ...sampleScores[2], human_score: 9, human_feedback: '很好' };
    mockSubmitHumanLabel.mockResolvedValue(updated);

    fireEvent.click(screen.getAllByText(/校准 d1/)[1]);
    const saveBtn = await screen.findByRole('button', { name: '保存校准' });
    fireEvent.click(saveBtn);

    // 保存后 case_result 2 的 score 102 写入 human_score → 该行变为「已校准」
    await waitFor(() => {
      expect(screen.getAllByText('已校准').length).toBe(2);
    });
  });
});

describe('RunDetailPage — 边界渲染', () => {
  beforeEach(() => {
    mockGetRun.mockReset();
    mockListRunScores.mockReset();
    mockSubmitHumanLabel.mockReset();
  });

  it('无 AI 评分数据时维度概览显示空状态（覆盖 dimensionAgg 空）', async () => {
    mockGetRun.mockResolvedValue(sampleRun);
    mockListRunScores.mockResolvedValue([
      { ...sampleScores[0], ai_score: null },
    ]);
    renderWithProviders(<RunDetailPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无评分数据')).toBeInTheDocument();
    });
  });

  it('校准抽屉展示 AI 优缺点（覆盖 strengths/weaknesses 渲染）', async () => {
    mockGetRun.mockResolvedValue(sampleRun);
    mockListRunScores.mockResolvedValue([
      {
        ...sampleScores[0],
        ai_strengths: ['钩子强'],
        ai_weaknesses: ['结尾弱'],
      },
    ]);
    renderWithProviders(<RunDetailPage />);
    await waitFor(() => expect(screen.getByText('核心集全量回归')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText(/校准 d1/)[0]);
    expect(await screen.findByText(/优点：钩子强/)).toBeInTheDocument();
    expect(screen.getByText(/缺点：结尾弱/)).toBeInTheDocument();
  });
});

describe('RunDetailPage — 进度轮询（Phase 4）', () => {
  beforeEach(() => {
    mockGetRun.mockReset();
    mockListRunScores.mockReset();
    mockSubmitHumanLabel.mockReset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('pending 时轮询 getRun；转 completed 后重拉 scores 且停轮询', async () => {
    // 初始 getRun → pending；第一次轮询 getRun → completed
    mockGetRun.mockResolvedValueOnce({ ...sampleRun, status: 'pending', completed_cases: 0 });
    mockGetRun.mockResolvedValueOnce({ ...sampleRun, status: 'completed', completed_cases: 28 });
    mockListRunScores.mockResolvedValue(sampleScores);

    renderWithProviders(<RunDetailPage />);

    // 初始 mount：getRun(pending) + listRunScores 各 1 次（flush microtasks）
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(mockGetRun).toHaveBeenCalledTimes(1);
    expect(mockListRunScores).toHaveBeenCalledTimes(1);

    // 推进 4s → 第一次轮询：getRun(completed) + 终态重拉 scores
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(mockGetRun).toHaveBeenCalledTimes(2);
    expect(mockListRunScores).toHaveBeenCalledTimes(2);  // 完成时重拉

    // 再推进 8s → 终态不再轮询
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(mockGetRun).toHaveBeenCalledTimes(2);
    expect(mockListRunScores).toHaveBeenCalledTimes(2);
  });

  it('终态(completed)不轮询', async () => {
    mockGetRun.mockResolvedValue(sampleRun);  // completed
    mockListRunScores.mockResolvedValue(sampleScores);
    renderWithProviders(<RunDetailPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(mockGetRun).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(12000); });
    expect(mockGetRun).toHaveBeenCalledTimes(1);  // 12s 后仍只 1 次（没轮询）
    expect(mockListRunScores).toHaveBeenCalledTimes(1);
  });

  it('轮询中 getRun 单次失败不中断（下次继续）', async () => {
    mockGetRun.mockResolvedValueOnce({ ...sampleRun, status: 'pending', completed_cases: 0 });
    mockGetRun.mockRejectedValueOnce(new Error('瞬时网络抖动'));
    mockGetRun.mockResolvedValueOnce({ ...sampleRun, status: 'completed', completed_cases: 28 });
    mockListRunScores.mockResolvedValue(sampleScores);

    renderWithProviders(<RunDetailPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    // 第一次轮询失败（4s）
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    // 第二次轮询成功完成（8s）
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(mockGetRun).toHaveBeenCalledTimes(3);  // 初始 + 失败那次 + 完成那次
  });
});
