// Types for 千川文案写作（qianchuan-writer）

/** Step 1 达人列表项 */
export interface QianchuanWriterPersona {
  id: number;
  name: string;
  soul_preview: string;
  soul_full: string;
  content_plan: string;
  creator_name: string;
}

/** 管理端配置项 */
export interface QianchuanWriterConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}

/** 历史记录项 */
export interface QianchuanOutput {
  id: number;
  title: string;
  content: string;
  word_count: number;
  task_id: number | null;
  created_at: string | null;
}

/** 历史记录分页响应 */
export interface QianchuanOutputsPage {
  items: QianchuanOutput[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** chat 请求中的单条消息 */
export interface QianchuanChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/** POST /chat 请求体 */
export interface QianchuanChatRequest {
  messages: QianchuanChatMessage[];
  persona_id: number;
  kol_id?: number;
  create_job?: boolean;
  job_context?: {
    product_name?: string;
    original_script_length?: number;
  };
}

/** POST /save-output 请求体 */
export interface QianchuanSaveOutputRequest {
  task_id?: number | null;
  title: string;
  content: string;
  product_name?: string | null;
}

/** POST /export-word 请求体 */
export interface QianchuanExportWordRequest {
  content: string;
  filename: string;
}

/** parse-file 返回 */
export interface QianchuanParseFileResult {
  text: string;
  word_count: number;
}
