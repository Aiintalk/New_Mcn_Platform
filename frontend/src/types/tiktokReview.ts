export interface VideoSide {
  file: File | null;
  transcript: string;
  likes: string;
}

export interface TiktokReviewOutput {
  id: number;
  title: string;
  created_at: string | null;
  preview: string;
  word_count: number | null;
}

export interface TiktokReviewConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
  updated_at: string | null;
}

export interface GenerateRequest {
  original_transcript: string;
  original_likes: string;
  copycat_transcript: string;
  copycat_likes: string;
}

export interface SaveRequest {
  content: string;
  title?: string;
  task_id?: number | null;
}

export interface OutputsResponse {
  items: TiktokReviewOutput[];
  total: number;
}
