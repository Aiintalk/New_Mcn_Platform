import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockAdminGetTasks = vi.fn();
const mockAdminGetTask = vi.fn();
const mockGetTasks = vi.fn();
const mockGetTask = vi.fn();

vi.mock('../../../api/tasks', () => ({
  adminGetTasks: (...args: unknown[]) => mockAdminGetTasks(...args),
  adminGetTask: (...args: unknown[]) => mockAdminGetTask(...args),
  getTasks: (...args: unknown[]) => mockGetTasks(...args),
  getTask: (...args: unknown[]) => mockGetTask(...args),
}));

vi.mock('../../../api/intake', () => ({
  getOperatorSubmissions: vi.fn(),
  getOperatorSubmissionDetail: vi.fn(),
  getOperatorDownloadUrl: vi.fn(),
}));

import AdminTasksPage from '../../../pages/admin/AdminTasksPage';
import TasksPage from '../../../pages/operator/TasksPage';

const baseTask = {
  id: 91,
  task_no: 'CA-status-91',
  tool_code: 'content-analysis-daily',
  tool_name: '每日项目对标内容分析',
  created_by: 1,
  started_at: null,
  finished_at: null,
  duration_ms: null,
  output_id: null,
  error_code: null,
  error_message: null,
  created_at: '2026-09-03T08:00:00+08:00',
};

const statusCases = [
  ['pending', '待处理'],
  ['processing', '处理中'],
  ['success', '成功'],
  ['failed', '失败'],
  ['cancelled', '已取消'],
  ['not_run', '未运行'],
] as const;

const pageCases = [
  {
    pageName: '管理员',
    renderPage: () => render(<App><AdminTasksPage /></App>),
    listMock: mockAdminGetTasks,
  },
  {
    pageName: '运营',
    renderPage: () => render(<App><TasksPage /></App>),
    listMock: mockGetTasks,
  },
] as const;

describe.each(pageCases)('$pageName任务页的六种状态兼容', ({ renderPage, listMock }) => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(statusCases)('把 %s 显示为“%s”并使用原状态值筛选', async (status, label) => {
    const user = userEvent.setup();
    const taskList = {
      items: [{ ...baseTask, status }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    };
    listMock.mockResolvedValue(taskList);
    renderPage();

    await waitFor(() => {
      const matchingLabels = screen.getAllByText(label);
      expect(matchingLabels.some(element => element.classList.contains('badge'))).toBe(true);
    });
    expect(screen.getByRole('option', { name: label })).toHaveValue(status);
    await user.selectOptions(screen.getByRole('combobox'), status);
    await waitFor(() => expect(listMock).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      status,
    }));
  });
});
