export interface OperationLog {
  id: number;
  user_id: number | null;
  user_name: string | null;
  role: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: unknown;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface ExternalServiceLog {
  id: number;
  service: string;
  endpoint: string;
  model: string | null;
  tool_code: string | null;
  task_id: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  credits: number | null;
  audio_seconds: number | null;
  duration_ms: number | null;
  status: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface LogListParams {
  page?: number;
  page_size?: number;
  user_id?: number;
  action?: string;
  service?: string;
  status?: string;
}
