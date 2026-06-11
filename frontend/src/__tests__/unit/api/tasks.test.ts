import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  post: vi.fn(),
}));

import { getTasks, getTask, adminGetTasks, adminGetTask } from '../../../api/tasks';

describe('tasks API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getTasks calls GET /api/tasks with params', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);
    const result = await getTasks({ page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith('/api/tasks', { page: 1, page_size: 20 });
    expect(result).toEqual(pagedData);
  });

  it('getTask calls GET /api/tasks/:id', async () => {
    const task = { id: 1, task_no: 'T001', status: 'pending' };
    mockGet.mockResolvedValue(task);
    const result = await getTask(1);
    expect(mockGet).toHaveBeenCalledWith('/api/tasks/1');
    expect(result.id).toBe(1);
  });

  it('adminGetTasks calls GET /api/admin/tasks with params', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);
    const result = await adminGetTasks({ page: 1, page_size: 20, user_id: 1 });
    expect(mockGet).toHaveBeenCalledWith('/api/admin/tasks', { page: 1, page_size: 20, user_id: 1 });
    expect(result).toEqual(pagedData);
  });

  it('adminGetTask calls GET /api/admin/tasks/:id', async () => {
    const task = { id: 1, task_no: 'T001', status: 'success' };
    mockGet.mockResolvedValue(task);
    const result = await adminGetTask(1);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/tasks/1');
    expect(result.id).toBe(1);
  });
});
