export interface ChatMessage {
  role: 'assistant' | 'user';
  content: string;
  ts: string; // ISO8601
}

export interface IntakeQuestion {
  id: number;
  order_num: number;
  category: string;
  question_text: string;
  question_type: 'text' | 'multi_collect';
  max_items: number | null;
  is_required: boolean;
  is_active: boolean;
}

export interface IntakeLink {
  id: number;
  token: string;
  kol_name: string | null;
  expires_at: string;
  is_active: boolean;
  created_at: string;
  used_at: string | null;
  submitted_at: string | null;
  report_status: 'pending' | 'generating' | 'ready' | 'failed' | null;
}

export interface IntakeSubmission {
  id: number;
  link_id: number;
  kol_name: string | null;
  report_status: 'pending' | 'generating' | 'ready' | 'failed';
  created_at: string;
  report_generated_at: string | null;
  kol_downloaded_at: string | null;
  operator_downloaded_at: string | null;
  operator_id?: number | null;
  messages?: ChatMessage[];
  ai_report?: string | null;
}

export interface IntakeConfigForm {
  ai_model_id: number | null;
  system_prompt: string | null;
}

export interface QuestionForm {
  order_num: number;
  category: string;
  question_text: string;
  question_type: 'text' | 'multi_collect';
  max_items: number | null;
  is_required: boolean;
}
