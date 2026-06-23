// Types for 人设脚本仿写（persona-writer）

/** Step 1 达人列表项（与 qianchuan-writer 共享同结构）*/
export interface PersonaWriterPersona {
  id: number;
  name: string;
  soul_preview: string;
  creator_name: string;
}

/** 管理端配置项（4 Prompt + 2 模型 + 启用）*/
export interface PersonaWriterConfig {
  id: number;
  config_key: string;
  evaluation_prompt: string | null;
  analysis_prompt: string | null;
  writing_prompt: string | null;
  iteration_prompt: string | null;
  light_model_id: number | null;
  heavy_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}

/** 历史记录项 */
export interface PersonaWriterOutput {
  id: number;
  title: string;
  content: string;
  word_count: number;
  task_id: number | null;
  created_at: string | null;
}

/** 历史记录分页响应 */
export interface PersonaWriterOutputsPage {
  items: PersonaWriterOutput[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** Step 2.1 fetch-video 返回 */
export interface FetchVideoResult {
  title: string;
  digg_count: number;
  aweme_id: string;
  play_url: string;
  likes_pass: boolean;
}

/** chat 请求中的单条消息（yunwu 格式，content 可为 string 或含 image_url 的数组）*/
export interface PersonaChatMessage {
  role: 'user' | 'assistant';
  content: string | Array<{ type: 'text'; text: string } | { type: 'image_url'; image_url: { url: string } }>;
}

/** POST /chat 请求体 */
export interface PersonaChatRequest {
  scene: 'writing' | 'iteration';
  topic_mode?: 'custom' | 'default';
  persona_id: number;
  transcript?: string;
  structure_analysis?: string;
  topic?: string;
  messages: PersonaChatMessage[];
  create_job?: boolean;
  job_context?: Record<string, unknown> | null;
}

/** POST /save-output 请求体 */
export interface PersonaSaveOutputRequest {
  content: string;
  title?: string;
  task_id?: number | null;
  topic?: string | null;
  transcript_digest?: string | null;
}

/** POST /export-word 请求体 */
export interface PersonaExportWordRequest {
  content: string;
  filename?: string;
}
