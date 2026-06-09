import { get, post } from './request';
import type { PagedData } from '../types/api';
import type { TaskJob, TaskDetail, TaskListParams, AdminTaskListParams } from '../types/task';

export async function getTasks(params?: TaskListParams): Promise<PagedData<TaskJob>> {
  return get<PagedData<TaskJob>>('/api/tasks', params as Record<string, string | number | boolean | undefined>);
}

export async function getTask(task_id: number): Promise<TaskDetail> {
  return get<TaskDetail>(`/api/tasks/${task_id}`);
}

export async function adminGetTasks(params?: AdminTaskListParams): Promise<PagedData<TaskJob>> {
  return get<PagedData<TaskJob>>('/api/admin/tasks', params as Record<string, string | number | boolean | undefined>);
}

export async function adminGetTask(task_id: number): Promise<TaskDetail> {
  return get<TaskDetail>(`/api/admin/tasks/${task_id}`);
}

// Re-export for compatibility
export { post };
