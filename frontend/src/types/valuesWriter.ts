export interface ValuesWriterConfig {
  id: number;
  config_key: string;
  extract_values_prompt: string | null;
  emotion_direction_prompt: string | null;
  writing_prompt: string | null;
  iteration_prompt: string | null;
  model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}

/** POST /operator/values-writer/save-output 请求体 */
export interface ValuesWriterSaveOutputRequest {
  content: string;
  title?: string;
  topic?: string | null;
}
