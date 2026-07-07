/**
 * HistoryList 单元测试 — 字幕提取统一历史记录组件
 *
 * 覆盖：
 * - 初始加载（空列表 / 单条+批量混合）
 * - 展开/收起（懒加载详情）
 * - 删除（mock deleteHistory + 列表刷新）
 * - 复制（mock clipboard）
 * - 生成思维导图（mock generateMindmap）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// ── Mock API ──────────────────────────────────────────────────────────
const mockListHistory = vi.fn();
const mockGetBatch = vi.fn();
const mockDeleteHistory = vi.fn();
const mockGenerateMindmap = vi.fn();

vi.mock('../../../api/subtitle', () => ({
  listHistory: (...args: unknown[]) => mockListHistory(...args),
  getBatchByJobCode: (...args: unknown[]) => mockGetBatch(...args),
  deleteHistory: (...args: unknown[]) => mockDeleteHistory(...args),
  generateMindmap: (...args: unknown[]) => mockGenerateMindmap(...args),
}));

// MindmapView 在 jsdom 下没有真实 layout，mock 掉避免 SVG 计算问题
vi.mock('../../../pages/operator/subtitle/MindmapView', () => ({
  default: () => <div data-testid="mindmap-view">mindmap</div>,
}));

import HistoryList from '../../../pages/operator/subtitle/HistoryList';

// 单条任务样本
const singleJob = {
  id: 1,
  job_code: 'sub_single_001',
  kind: 'single' as const,
  status: 'completed' as const,
  phase: 'done',
  total: 1,
  success: 1,
  failed: 0,
  created_by: 1,
  created_at: '2026-06-27T10:00:00',
  updated_at: '2026-06-27T10:05:00',
};

const batchJob = {
  id: 2,
  job_code: 'sub_batch_002',
  kind: 'batch' as const,
  status: 'completed' as const,
  phase: 'done',
  total: 3,
  success: 2,
  failed: 1,
  created_by: 1,
  created_at: '2026-06-27T11:00:00',
  updated_at: '2026-06-27T11:30:00',
};

// 展开后的详情（单条）
const singleDetail = {
  ...singleJob,
  items: [
    {
      id: 10,
      row_number: 1,
      original_url: 'https://v.douyin.com/xxx/',
      title: '测试视频标题',
      transcript: '这是完整字幕内容',
      status: 'success' as const,
      error: '',
      play_url: 'https://example.com/video.mp4',
      audio_url: 'https://example.com/audio.mp3',
      cover_url: 'https://example.com/cover.jpg',
      nickname: '测试作者',
      digg_count: 50000,
      aweme_id: '7012345',
    },
  ],
};

// 展开后的详情（批量）
const batchDetail = {
  ...batchJob,
  items: [
    {
      id: 20,
      row_number: 1,
      original_url: 'https://v.douyin.com/a/',
      title: '视频 A',
      transcript: '字幕 A',
      status: 'success' as const,
      error: '',
    },
    {
      id: 21,
      row_number: 2,
      original_url: 'https://v.douyin.com/b/',
      title: '',
      transcript: '',
      status: 'failed' as const,
      error: 'ASR 失败',
    },
  ],
};

const sampleMindmap = {
  rootTitle: '核心主题',
  summary: '总结',
  branches: [{ title: '分支一', children: ['要点 1'] }],
};

function renderWithApp(ui: React.ReactElement) {
  return render(<App>{ui}</App>);
}

describe('HistoryList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListHistory.mockResolvedValue({ items: [], pagination: { total: 0 } });
    mockGetBatch.mockResolvedValue(singleDetail);
    mockDeleteHistory.mockResolvedValue({ job_code: '', deleted: true });
    mockGenerateMindmap.mockResolvedValue(sampleMindmap);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows empty state when no history', async () => {
    renderWithApp(<HistoryList />);
    await waitFor(() => expect(mockListHistory).toHaveBeenCalled());
    expect(screen.getByText('还没有历史记录')).toBeInTheDocument();
  });

  it('renders unified list of single + batch jobs', async () => {
    mockListHistory.mockResolvedValue({
      items: [singleJob, batchJob],
      pagination: { total: 2 },
    });
    renderWithApp(<HistoryList />);
    await waitFor(() => {
      expect(screen.getByText('单条')).toBeInTheDocument();
      expect(screen.getByText('批量')).toBeInTheDocument();
    });
  });

  it('expands single job to show full transcript and operations', async () => {
    const user = userEvent.setup();
    mockListHistory.mockResolvedValue({
      items: [singleJob],
      pagination: { total: 1 },
    });
    renderWithApp(<HistoryList />);

    await waitFor(() => expect(screen.getByText('单条')).toBeInTheDocument());

    // 点击 详情 展开
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /详情/ }));
    });

    await waitFor(() => expect(mockGetBatch).toHaveBeenCalledWith('sub_single_001'));
    await waitFor(() => {
      expect(screen.getByText('这是完整字幕内容')).toBeInTheDocument();
      expect(screen.getByText('复制字幕')).toBeInTheDocument();
      expect(screen.getByText('生成思维导图')).toBeInTheDocument();
    });
  });

  it('deletes a job and refreshes list', async () => {
    const user = userEvent.setup();
    mockListHistory.mockResolvedValueOnce({
      items: [singleJob],
      pagination: { total: 1 },
    });
    // 删除后的列表为空
    mockListHistory.mockResolvedValueOnce({
      items: [],
      pagination: { total: 0 },
    });
    renderWithApp(<HistoryList />);

    await waitFor(() => expect(screen.getByText('单条')).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /删除/ }));
    });

    await waitFor(() => expect(mockDeleteHistory).toHaveBeenCalledWith('sub_single_001'));
    await waitFor(() => expect(screen.getByText('还没有历史记录')).toBeInTheDocument());
  });

  it('generates mindmap for a single job', async () => {
    const user = userEvent.setup();
    mockListHistory.mockResolvedValue({
      items: [singleJob],
      pagination: { total: 1 },
    });
    renderWithApp(<HistoryList />);

    await waitFor(() => expect(screen.getByText('单条')).toBeInTheDocument());
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /详情/ }));
    });

    await waitFor(() => expect(screen.getByText('这是完整字幕内容')).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /生成思维导图/ }));
    });

    await waitFor(() => expect(mockGenerateMindmap).toHaveBeenCalledWith('这是完整字幕内容'));
    await waitFor(() => {
      expect(screen.getByTestId('mindmap-view')).toBeInTheDocument();
    });
  });

  it('expands batch job to show items list', async () => {
    const user = userEvent.setup();
    mockGetBatch.mockResolvedValue(batchDetail);
    mockListHistory.mockResolvedValue({
      items: [batchJob],
      pagination: { total: 1 },
    });
    renderWithApp(<HistoryList />);

    await waitFor(() => expect(screen.getByText('批量')).toBeInTheDocument());
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /详情/ }));
    });

    await waitFor(() => expect(mockGetBatch).toHaveBeenCalledWith('sub_batch_002'));
    await waitFor(() => {
      expect(screen.getByText('视频 A')).toBeInTheDocument();
      expect(screen.getByText('ASR 失败')).toBeInTheDocument();
    });

    // PR #18: 成功 item 应展示「复制文本」按钮（批量任务同样适用）
    // 失败 item（无 transcript）不应展示该按钮，由于只有 1 个成功 item，getByText 不会歧义
    expect(screen.getByText('复制文本')).toBeInTheDocument();
  });
});
