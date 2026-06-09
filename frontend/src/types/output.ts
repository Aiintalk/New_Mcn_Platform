export interface Output {
  id: number;
  title: string;
  tool_code: string;
  tool_name: string;
  task_id: number | null;
  word_count: number | null;
  file_id: number | null;
  content?: string;
  content_json?: unknown;
  created_by: number;
  created_by_name?: string;
  created_at: string;
}

export interface OutputListParams {
  page?: number;
  page_size?: number;
  tool_code?: string;
}

export interface AdminOutputListParams extends OutputListParams {
  user_id?: number;
}
