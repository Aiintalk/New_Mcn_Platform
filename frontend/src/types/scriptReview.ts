export type ScriptType = 'direct' | 'value';
export type ReviewRating = 'pass' | 'minor' | 'fail';

export interface MustFixItem {
  type: string;
  quote: string;
  fix: string;
}

export interface ReviewResult {
  rating: ReviewRating;
  must_fix: MustFixItem[];
  suggestions: string[];
  passed: string[];
}

export interface ScriptReviewConfig {
  id: number;
  config_key: string;
  direct_prompt: string | null;
  value_prompt: string | null;
  ai_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}

export interface ReviewRequest {
  script_type: ScriptType;
  original_script: string;
  adapted_script: string;
  product?: {
    nickname?: string;
    mechanism?: string;
    core_selling_point?: string;
  } | null;
}

/** POST /operator/qianchuan-script-review/save-output 请求体 */
export interface ScriptReviewSaveOutputRequest {
  content: string; // 仿写脚本原文
  content_json: ReviewResult; // 结构化评分
  title?: string;
}
