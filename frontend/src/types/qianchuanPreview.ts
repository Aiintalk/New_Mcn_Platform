export interface GenerateRequest {
  script_a: string;
  script_b: string;
}

export interface ParseFileResponse {
  text: string;
  filename: string;
}

export interface QianchuanPreviewConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}
