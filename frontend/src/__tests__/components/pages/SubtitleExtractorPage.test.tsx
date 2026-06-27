/**
 * SubtitleExtractorPage 单元测试
 *
 * 覆盖：
 * - 初始渲染（两个 Card：单条提取 / 批量提取）
 * - 单条提取异步流程（mock extractSubtitle 返回 job_code → 轮询 getBatchByJobCode → 完成后显示）
 * - 字幕↔思维导图切换（mock generateMindmap + 同容器切换）
 * - 批量提交（mock createBatch + parseBatchItems 计数）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// ── Mock API ──────────────────────────────────────────────────────────
const mockExtract = vi.fn();
const mockGenerateMindmap = vi.fn();
const mockCreateBatch = vi.fn();
const mockGetBatch = vi.fn();
const mockListHistory = vi.fn();
const mockDeleteHistory = vi.fn();
const mockSaveOutput = vi.fn();

vi.mock('../../../api/subtitle', () => ({
  extractSubtitle: (...args: unknown[]) => mockExtract(...args),
  generateMindmap: (...args: unknown[]) => mockGenerateMindmap(...args),
  createBatch: (...args: unknown[]) => mockCreateBatch(...args),
  getBatchByJobCode: (...args: unknown[]) => mockGetBatch(...args),
  listHistory: (...args: unknown[]) => mockListHistory(...args),
  listMyBatches: (...args: unknown[]) => mockListHistory(...args), // 兼容别名
  deleteHistory: (...args: unknown[]) => mockDeleteHistory(...args),
  saveOutput: (...args: unknown[]) => mockSaveOutput(...args),
}));

// react-dropzone 在 jsdom 下不支持 DataTransfer，mock 掉避免拖拽测试踩坑
vi.mock('react-dropzone', () => ({
  useDropzone: () => ({
    getRootProps: () => ({ onClick: vi.fn() }),
    getInputProps: () => ({}),
    isDragActive: false,
  }),
}));

import SubtitleExtractorPage from '../../../pages/operator/SubtitleExtractorPage';

// extract 现在只返回 { job_code, status: 'processing' }
const sampleExtractResp = {
  job_code: 'sub_single_001',
  status: 'processing' as const,
};

// 完成后的 SubtitleJob（单条）：items[0] 含视频元信息 + transcript
const sampleCompletedJob = {
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
  items: [
    {
      id: 10,
      row_number: 1,
      original_url: 'https://v.douyin.com/xxx/',
      title: '测试视频标题',
      transcript: '这是字幕内容',
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

const sampleMindmap = {
  rootTitle: '核心主题',
  summary: '总结内容',
  branches: [
    { title: '分支一', children: ['要点 1', '要点 2'] },
    { title: '分支二', children: ['要点 3'] },
  ],
};

function renderWithApp(ui: React.ReactElement) {
  return render(<App>{ui}</App>);
}

describe('SubtitleExtractorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockExtract.mockResolvedValue(sampleExtractResp);
    mockGenerateMindmap.mockResolvedValue(sampleMindmap);
    mockCreateBatch.mockResolvedValue({ job_code: 'sub_test', total: 2 });
    // 默认 getBatchByJobCode 直接返回完成状态（模拟轮询第一次就命中）
    mockGetBatch.mockResolvedValue(sampleCompletedJob);
    mockListHistory.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    });
    mockDeleteHistory.mockResolvedValue({ job_code: 'sub_single_001', deleted: true });
    mockSaveOutput.mockResolvedValue({
      id: 1,
      title: '',
      tool_code: 'subtitle',
      word_count: 0,
      created_at: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders single-page layout with two sections', () => {
    renderWithApp(<SubtitleExtractorPage />);
    expect(screen.getByText('字幕提取')).toBeInTheDocument();
    expect(screen.getByText('单条视频 ASR 转换')).toBeInTheDocument();
    expect(screen.getByText('批量提取')).toBeInTheDocument();
  });

  it('extracts subtitle via async polling and displays video info + cover', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithApp(<SubtitleExtractorPage />);

    const input = screen.getByPlaceholderText(/粘贴抖音视频分享链接/);
    await user.type(input, 'https://v.douyin.com/xxx/');

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /提取视频内容/ }));
    });

    // extract 应被调用，返回 job_code
    await waitFor(() => expect(mockExtract).toHaveBeenCalled());

    // 轮询若干次后应触发 getBatchByJobCode
    await waitFor(() => expect(mockGetBatch).toHaveBeenCalledWith('sub_single_001'));

    // 视频信息卡显示（轮询完成后）
    await waitFor(() => {
      expect(screen.getByText('测试作者')).toBeInTheDocument();
      expect(screen.getByText('5.0万')).toBeInTheDocument(); // formatCount(50000) → 5.0万
      expect(screen.getByText('7012345')).toBeInTheDocument();
    });

    // 字幕内容显示
    expect(screen.getByText('这是字幕内容')).toBeInTheDocument();
  });

  it('shows error message when single extract fails', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockGetBatch.mockResolvedValueOnce({
      ...sampleCompletedJob,
      status: 'failed',
      success: 0,
      failed: 1,
      items: [
        {
          ...sampleCompletedJob.items[0],
          status: 'failed',
          transcript: '',
          error: 'ASR 转写失败',
        },
      ],
    });

    renderWithApp(<SubtitleExtractorPage />);

    const input = screen.getByPlaceholderText(/粘贴抖音视频分享链接/);
    await user.type(input, 'https://v.douyin.com/xxx/');

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /提取视频内容/ }));
    });

    await waitFor(() => expect(mockGetBatch).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByText(/ASR 转写失败/)).toBeInTheDocument();
    });
  });

  it('switches to mindmap view and shows root title', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithApp(<SubtitleExtractorPage />);

    // 先提取（轮询完成后会有数据）
    const input = screen.getByPlaceholderText(/粘贴抖音视频分享链接/);
    await user.type(input, 'https://v.douyin.com/xxx/');
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /提取视频内容/ }));
    });

    await waitFor(() => expect(mockGetBatch).toHaveBeenCalled());

    // 等结果出来
    await waitFor(() => {
      expect(screen.getByText('这是字幕内容')).toBeInTheDocument();
    });

    // 点「思维导图」按钮
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /思维导图/ }));
    });

    await waitFor(() => expect(mockGenerateMindmap).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByText('核心主题')).toBeInTheDocument();
      expect(screen.getByText('分支一')).toBeInTheDocument();
      expect(screen.getByText('分支二')).toBeInTheDocument();
    });
  });

  it('counts pending batch items in textarea', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithApp(<SubtitleExtractorPage />);

    const textarea = screen.getByPlaceholderText(/每行一条抖音分享文本/);
    await user.type(textarea, 'https://v.douyin.com/a/\nhttps://v.douyin.com/b/');

    await waitFor(() => {
      expect(screen.getByText(/2 条待提交/)).toBeInTheDocument();
    });
  });
});
