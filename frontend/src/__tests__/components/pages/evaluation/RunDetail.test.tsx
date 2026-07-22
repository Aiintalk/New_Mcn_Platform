/**
 * RunDetail 页面测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
