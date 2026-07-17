import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock API — 必须在 import 组件之前
const mockGetCredentials = vi.fn();
const mockCreateCredential = vi.fn();
const mockTestOssCredential = vi.fn();
vi.mock('../../../api/credentials', () => ({
  getCredentials: (...args: unknown[]) => mockGetCredentials(...args),
  createCredential: (...args: unknown[]) => mockCreateCredential(...args),
  testOssCredential: (...args: unknown[]) => mockTestOssCredential(...args),
  updateCredential: vi.fn(),
  deleteCredential: vi.fn(),
  enableCredential: vi.fn(),
  disableCredential: vi.fn(),
}));

// Mock OSS stats API（对齐 TikHub 统计的 4 卡 + 2 图 + 3 子 Tab）
const mockGetOssStats = vi.fn();
const mockGetOssOperations = vi.fn();
const mockGetOssUsers = vi.fn();
vi.mock('../../../api/oss', () => ({
  getOssStats: (...args: unknown[]) => mockGetOssStats(...args),
  getOssOperations: (...args: unknown[]) => mockGetOssOperations(...args),
  getOssUsers: (...args: unknown[]) => mockGetOssUsers(...args),
}));

// Mock antd message
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn() },
  };
});

import { OssConfigTab } from '../../../pages/admin/ServiceConfigPage';

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
  provider: 'oss',
  label: '杭州生产',
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
    access_key_id: 'LTAIABCD1234',
    bucket: 'test-bucket',
    endpoint: 'oss-cn-hangzhou.aliyuncs.com',
    region: 'cn-hangzhou',
  },
};

describe('OssConfigTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCredentials.mockResolvedValue(emptyPage);
    mockGetOssStats.mockResolvedValue(emptyStats);
    mockGetOssOperations.mockResolvedValue([]);
    mockGetOssUsers.mockResolvedValue({ items: [], total: 0 });
  });

  it('renders empty state when no credentials', async () => {
    render(<OssConfigTab />);
    await waitFor(() => {
      expect(screen.getByText(/暂无 OSS 凭证/)).toBeInTheDocument();
    });
  });

  it('renders 4 stat cards with zeros when stats empty', async () => {
    render(<OssConfigTab />);
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
    mockGetOssStats.mockResolvedValue({
      overview: {
        total_calls: 1234,
        today_calls: 56,
        avg_latency_ms: 120,
        active_keys: 2,
        total_keys: 3,
      },
      operations: [
        { operation: 'upload', calls: 1000, percentage: 81.0 },
        { operation: 'download', calls: 200, percentage: 16.2 },
        { operation: 'delete', calls: 34, percentage: 2.8 },
      ],
      users: [],
      trend: [
        { date: '06-15', calls: 10 },
        { date: '06-16', calls: 20 },
      ],
    });

    render(<OssConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('1,234')).toBeInTheDocument(); // total_calls
      expect(screen.getByText('56')).toBeInTheDocument();     // today_calls
      expect(screen.getByText('120ms')).toBeInTheDocument();  // avg_latency
      expect(screen.getByText('2 / 3')).toBeInTheDocument();  // active_keys
    });
  });

  it('renders donut chart when operations data exists', async () => {
    mockGetOssStats.mockResolvedValue({
      overview: emptyStats.overview,
      operations: [
        { operation: 'upload', calls: 10, percentage: 100 },
      ],
      users: [],
      trend: [],
    });
    render(<OssConfigTab />);
    await waitFor(() => {
      // 饼图中心 "操作" 标签 + 操作名
      expect(screen.getByText('操作')).toBeInTheDocument();
      expect(screen.getByText('upload')).toBeInTheDocument();
    });
  });

  it('renders line chart when trend has >= 2 data points', async () => {
    mockGetOssStats.mockResolvedValue({
      overview: emptyStats.overview,
      operations: [],
      users: [],
      trend: [
        { date: '06-15', calls: 5 },
        { date: '06-16', calls: 10 },
        { date: '06-17', calls: 8 },
      ],
    });
    render(<OssConfigTab />);
    await waitFor(() => {
      // 趋势图日期标签可见（在 SVG 内部）
      expect(screen.getByText('06-15')).toBeInTheDocument();
      expect(screen.getByText('06-16')).toBeInTheDocument();
      expect(screen.getByText('06-17')).toBeInTheDocument();
    });
  });

  it('renders 3 sub-tab labels', async () => {
    render(<OssConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('凭证管理')).toBeInTheDocument();
      expect(screen.getByText('操作统计')).toBeInTheDocument();
      expect(screen.getByText('用户排行')).toBeInTheDocument();
    });
  });

  it('switches to operations sub-tab and loads operation details on click', async () => {
    const user = userEvent.setup();
    mockGetOssOperations.mockResolvedValue([
      { operation: 'upload', calls: 80, percentage: 80.0, avg_latency_ms: 120, success_rate: 0.99 },
      { operation: 'download', calls: 20, percentage: 20.0, avg_latency_ms: 80, success_rate: 1.0 },
    ]);

    render(<OssConfigTab />);
    await waitFor(() => expect(screen.getByText('操作统计')).toBeInTheDocument());
    await user.click(screen.getByText('操作统计'));

    await waitFor(() => {
      expect(mockGetOssOperations).toHaveBeenCalled();
      expect(screen.getByText('upload')).toBeInTheDocument();
      expect(screen.getByText('download')).toBeInTheDocument();
      expect(screen.getByText('80%')).toBeInTheDocument();
      expect(screen.getByText('99.0%')).toBeInTheDocument();
    });
  });

  it('switches to users sub-tab and loads user ranking on click', async () => {
    const user = userEvent.setup();
    mockGetOssUsers.mockResolvedValue({
      items: [
        { user_id: 1, username: '张三', role: 'operator', calls: 50, last_called_at: '2024-06-20T10:00:00Z' },
      ],
      total: 1,
    });

    render(<OssConfigTab />);
    await waitFor(() => expect(screen.getByText('用户排行')).toBeInTheDocument());
    await user.click(screen.getByText('用户排行'));

    await waitFor(() => {
      expect(mockGetOssUsers).toHaveBeenCalled();
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.getByText('operator')).toBeInTheDocument();
      expect(screen.getByText('50')).toBeInTheDocument();
    });
  });

  it('renders credential rows with bucket and endpoint when data exists', async () => {
    mockGetCredentials.mockResolvedValue({
      items: [sampleCred],
      pagination: { total: 1, page: 1, page_size: 20, total_pages: 1 },
    });
    render(<OssConfigTab />);
    await waitFor(() => {
      expect(screen.getByText('杭州生产')).toBeInTheDocument();
      expect(screen.getByText('test-bucket')).toBeInTheDocument();
      expect(screen.getByText(/oss-cn-hangzhou/)).toBeInTheDocument();
    });
  });

  it('opens add modal and shows all OSS-specific fields', async () => {
    const user = userEvent.setup();
    render(<OssConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 新增/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 新增/));

    // 验证 OSS 必备字段都在表单里
    expect(await screen.findByText(/AccessKey ID/i)).toBeInTheDocument();
    expect(screen.getByText(/AccessKey Secret/i)).toBeInTheDocument();
    expect(screen.getByText(/Bucket/i)).toBeInTheDocument();
    expect(screen.getByText(/Endpoint/i)).toBeInTheDocument();
  });

  it('submits new credential with config field correctly assembled', async () => {
    mockCreateCredential.mockResolvedValue({ ...sampleCred, id: 99 });
    const user = userEvent.setup();
    render(<OssConfigTab />);
    await waitFor(() => expect(screen.getByText(/\+ 新增/)).toBeInTheDocument());
    await user.click(screen.getByText(/\+ 新增/));

    // 等表单挂载
    await screen.findByText(/AccessKey ID/i);

    // 填表（用 placeholder 定位 input）
    await user.type(screen.getByPlaceholderText(/如 杭州生产环境/), '测试凭证');
    await user.type(screen.getByPlaceholderText(/LTAI/), 'LTAI1234');
    await user.type(screen.getByPlaceholderText(/test-secret/), 'test-secret-5678');
    await user.type(screen.getByPlaceholderText(/如 oss-cn-hangzhou/), 'oss-cn-hangzhou.aliyuncs.com');
    await user.type(screen.getByPlaceholderText(/如 mcn-production/), 'test-bucket');

    // 通过 DOM 选择 Antd Modal 的 OK 按钮（文字在 jsdom 下可能为空）
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement;
    expect(okBtn).toBeTruthy();
    await user.click(okBtn);

    await waitFor(() => {
      expect(mockCreateCredential).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'oss',
          label: '测试凭证',
          api_key: 'test-secret-5678',
          config: expect.objectContaining({
            access_key_id: 'LTAI1234',
            bucket: 'test-bucket',
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
      latency_ms: 100,
      bucket: 'test-bucket',
    });

    const user = userEvent.setup();
    render(<OssConfigTab />);
    await waitFor(() => expect(screen.getByText('杭州生产')).toBeInTheDocument());

    const testButtons = screen.getAllByRole('button', { name: /测试/ });
    expect(testButtons.length).toBeGreaterThan(0);
    await user.click(testButtons[0]);

    await waitFor(() => {
      expect(mockTestOssCredential).toHaveBeenCalledWith(1);
    });
  });
});
