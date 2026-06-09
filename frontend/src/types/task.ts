export type TaskStatus = 'pending' | 'processing' | 'success' | 'failed' | 'cancelled';

export interface TaskJob {
  id: number;
  task_no: string;
  tool_code: string;
  tool_name: string;
  status: TaskStatus;
  created_by: number;
  created_by_name?: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  output_id: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface TaskLog {
  id: number;
  step_code: string;
  step_name: string;
  status: string;
  message: string | null;
  created_at: string;
}

export interface TaskDetail extends TaskJob {
  task_logs: TaskLog[];
}

export interface TaskListParams {
  page?: number;
  page_size?: number;
  status?: string;
  tool_code?: string;
}

export interface AdminTaskListParams extends TaskListParams {
  user_id?: number;
}
