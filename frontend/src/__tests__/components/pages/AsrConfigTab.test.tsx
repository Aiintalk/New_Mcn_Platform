import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock API — 必须在 import 组件之前
const mockGetCredentials = vi.fn();
const mockCreateCredential = vi.fn();
const mockTestOssCredential = vi.fn(); // AsrConfigTab 通过通用 testOssCredential 端点测试
vi.mock('../../../api/credentials', () => ({
  getCredentials: (...args: unknown[]) => mockGetCredentials(...args),
  createCredential: (...args: unknown[]) => mockCreateCredential(...args),
  testOssCredential: (...args: unknown[]) => mockTestOssCredential(...args),
  updateCredential: vi.fn(),
  deleteCredential: vi.fn(),
  enableCredential: vi.fn(),
  disableCredential: vi.fn(),
}));

// Mock ASR stats API（4 卡 + 2 图 + 3 子 Tab）
const mockGetAsrStats = vi.fn();
const mockGetAsrOperations = vi.fn();
const mockGetAsrUsers = vi.fn();
vi.mock('../../../api/asr', () => ({
  getAsrStats: (...args: unknown[]) => mockGetAsrStats(...args),
  getAsrOperations: (...args: unknown[]) => mockGetAsrOperations(...args),
  getAsrUsers: (...args: unknown[]) => mockGetAsrUsers(...args),
}));

// Mock antd message
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  };
});

import { AsrConfigTab } from '../../../pages/admin/ServiceConfigPage';

const emptyPage = { items: [], pagination: { total: 0, page: 1, page_size: 20, total_pages: 0 } };

const emptyStats = {
  overview: {
    total_calls: 0,
    today_calls: 0,
    avg_latency_ms: null,
    active_keys: 0,
    total_keys: 0,
  },
  operations: [],
  users: [],
  trend: [],
};

const sampleCred = {
  id: 1,
  provider: 'asr',
  label: '上海生产环境',
  secret_tail: '1234',
  status: 'enabled' as const,
  weight: 10,
  quota_limit: null,
  quota_used: 0,
  fail_count: 0,
  cooldown_until: null,
  last_tested_at: null,
  last_latency_ms: null,
  created_at: '2024-01-01T00:00:00Z',
  config: {
    app_key: 'fvY8kxR6abcd',
    region: 'cn-shanghai',
  },
};

describe('AsrConfigTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCredentials.mockResolvedValue(emptyPage);
    mockGetAsrStats.mockResolvedValue(emptyStats);
    mockGetAsrOperations.mockResolvedValue([]);
    mockGetAsrUsers.mockResolvedValue({ items: [], total: 0 });
  });

  it('renders empty state when no credentials', async () => {
    render(<AsrConfigTab />);
    await waitFor(() => {
      expect(screen.getByText(/暂无 ASR 凭证/)).toBeInTheDocument();
    });
  });

  it('renders 4 stat cards with zeros when stats empty', async () => {
    render(<AsrConfigTab />);
    await waitFor(() => {
      // 4 张卡的 label 都在
      expect(screen.getByText('总调用')).toBeInTheDocument();
      expect(screen.getByText('今日调用')).toBeInTheDocument();
      expect(screen.getByText('平均延迟')).toBeInTheDocument();
      expect(screen.getByText('活跃凭证')).toBeInTheDocument();
    });
    // 默认值（多个 0，用 getAllByText）
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(2); // total_calls + today_calls
  });

  it('renders stat cards with real values from stats API', async () => {
    mockGetAsrStats.mockResolvedValue({
      overview: {
        total_calls: 2345,
        today_calls: 78,
        avg_latency_ms: 210,
        active_keys: 2,
        total_keys: 4,
      },
      operations: [
        { operation: 'submit', calls: 1800, percentage: 76.8 },
        { operation: 'query', calls: 545, percentage: 23.2 },
      ],
      users: [],
      trend: [
        { date: '06-15', calls: 10 },
        { date: '06-16', calls: 20 },
      ],
    });

    render(<AsrConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('2,345')).toBeInTheDocument(); // total_calls
      expect(screen.getByText('78')).toBeInTheDocument();     // today_calls
      expect(screen.getByText('210ms')).toBeInTheDocument();  // avg_latency
      expect(screen.getByText('2 / 4')).toBeInTheDocument();  // active_keys
    });
  });

  it('renders donut chart when operations data exists', async () => {
    mockGetAsrStats.mockResolvedValue({
      overview: emptyStats.overview,
      operations: [
        { operation: 'submit', calls: 10, percentage: 100 },
      ],
      users: [],
      trend: [],
    });
    render(<AsrConfigTab />);
    await waitFor(() => {
      // 饼图中心 "操作" 标签 + 操作名
      expect(screen.getByText('操作')).toBeInTheDocument();
      expect(screen.getByText('submit')).toBeInTheDocument();
    });
  });

  it('renders line chart when trend has >= 2 data points', async () => {
    mockGetAsrStats.mockResolvedValue({
      overview: emptyStats.overview,
      operations: [],
      users: [],
      trend: [
        { date: '06-15', calls: 5 },
        { date: '06-16', calls: 10 },
        { date: '06-17', calls: 8 },
      ],
    });
    render(<AsrConfigTab />);
    await waitFor(() => {
      // 趋势图日期标签可见（在 SVG 内部）
      expect(screen.getByText('06-15')).toBeInTheDocument();
      expect(screen.getByText('06-16')).toBeInTheDocument();
      expect(screen.getByText('06-17')).toBeInTheDocument();
    });
  });

  it('renders 3 sub-tab labels', async () => {
    render(<AsrConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('凭证管理')).toBeInTheDocument();
      expect(screen.getByText('操作统计')).toBeInTheDocument();
      expect(screen.getByText('用户排行')).toBeInTheDocument();
    });
  });

  it('switches to operations sub-tab and loads operation details on click', async () => {
    const user = userEvent.setup();
    mockGetAsrOperations.mockResolvedValue([
      { operation: 'submit', calls: 80, percentage: 80.0, avg_latency_ms: 220, success_rate: 0.95 },
      { operation: 'query', calls: 20, percentage: 20.0, avg_latency_ms: 80, success_rate: 1.0 },
    ]);

    render(<AsrConfigTab />);
    await waitFor(() => expect(screen.getByText('操作统计')).toBeInTheDocument());
    await user.click(screen.getByText('操作统计'));

    await waitFor(() => {
      expect(mockGetAsrOperations).toHaveBeenCalled();
      expect(screen.getByText('submit')).toBeInTheDocument();
      expect(screen.getByText('query')).toBeInTheDocument();
      expect(screen.getByText('80%')).toBeInTheDocument();
      expect(screen.getByText('95.0%')).toBeInTheDocument();
    });
  });

  it('switches to users sub-tab and loads user ranking on click', async () => {
    const user = userEvent.setup();
    mockGetAsrUsers.mockResolvedValue({
      items: [
        { user_id: 1, username: '李四', role: 'operator', calls: 30, last_called_at: '2024-06-20T10:00:00Z' },
      ],
      total: 1,
    });

    render(<AsrConfigTab />);
    await waitFor(() => expect(screen.getByText('用户排行')).toBeInTheDocument());
    await user.click(screen.getByText('用户排行'));

    await waitFor(() => {
      expect(mockGetAsrUsers).toHaveBeenCalled();
      expect(screen.getByText('李四')).toBeInTheDocument();
      expect(screen.getByText('operator')).toBeInTheDocument();
      expect(screen.getByText('30')).toBeInTheDocument();
    });
  });

  it('renders credential rows with masked AppKey and region when data exists', async () => {
    mockGetCredentials.mockResolvedValue({
      items: [sampleCred],
      pagination: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });
    render(<AsrConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('上海生产环境')).toBeInTheDocument();
      // AppKey 前 8 位 + ****（fvY8kxR6****）
      expect(screen.getByText(/fvY8kxR6/)).toBeInTheDocument();
      expect(screen.getByText('cn-shanghai')).toBeInTheDocument();
    });
  });

  it('opens add modal and shows all ASR-specific fields', async () => {
    const user = userEvent.setup();
    render(<AsrConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 新增 ASR 凭证/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 新增 ASR 凭证/));

    // 验证 ASR 必备字段都在表单里
    expect(await screen.findByText(/AppKey/i)).toBeInTheDocument();
    expect(screen.getByText(/AccessKey ID/i)).toBeInTheDocument();
    expect(screen.getByText(/AccessKey Secret/i)).toBeInTheDocument();
    expect(screen.getByText(/Region/i)).toBeInTheDocument();
  });

  it('submits new credential with api_key assembled as id\\nsecret', async () => {
    mockCreateCredential.mockResolvedValue({ ...sampleCred, id: 99 });
    const user = userEvent.setup();
    render(<AsrConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 新增 ASR 凭证/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 新增 ASR 凭证/));

    // 等表单挂载
    await screen.findByText(/AppKey/i);

    // 填表（用 placeholder 定位 input）
    await user.type(screen.getByPlaceholderText(/如 上海生产环境/), '测试凭证');
    await user.type(screen.getByPlaceholderText(/阿里云 ISI 项目 AppKey/), 'testAppKey123');
    await user.type(screen.getByPlaceholderText(/LTAI/), 'LTAI1234');
    await user.type(screen.getByPlaceholderText(/AccessKey Secret/), 'secret5678');
    // Region 已在打开 modal 时预设为 'cn-shanghai'，无需交互

    // 通过 DOM 选择 Antd Modal 的 OK 按钮
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement;
    expect(okBtn).toBeTruthy();
    await user.click(okBtn);

    await waitFor(() => {
      expect(mockCreateCredential).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'asr',
          label: '测试凭证',
          api_key: 'LTAI1234\nsecret5678', // secret_enc 格式
          config: expect.objectContaining({
            app_key: 'testAppKey123',
            region: 'cn-shanghai',
          }),
        })
      );
    });
  });

  it('invokes testOssCredential when test button clicked', async () => {
    mockGetCredentials.mockResolvedValue({
      items: [sampleCred],
      pagination: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });
    mockTestOssCredential.mockResolvedValue({
      status: 'ok',
      latency_ms: 150,
      status_text: 'FILE_TRANS_TASK_EXPIRED',
    });

    const user = userEvent.setup();
    render(<AsrConfigTab />);
    await waitFor(() => expect(screen.getByText('上海生产环境')).toBeInTheDocument());

    const testButtons = screen.getAllByRole('button', { name: /测试/ });
    expect(testButtons.length).toBeGreaterThan(0);
    await user.click(testButtons[0]);

    await waitFor(() => {
      expect(mockTestOssCredential).toHaveBeenCalledWith(1);
    });
  });
});
