/** 抖音拉取结果 */
export interface FetchResult {
  sec_user_id: string;
  nickname: string;
  total_videos: number;
  top10_count: number;
  recent30_count: number;
  top10_text: string;
  recent30_text: string;
}

/** 分析记录 */
export interface BenchmarkAnalysis {
  id: number;
  account_name: string;
  sec_user_id: string;
  top10_content: string;
  recent30_content: string;
  profile_result: string;
  plan_result: string;
  model_used: string;
  tokens_used: number;
  duration_ms: number;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  created_by?: number;
  created_at: string;
  updated_at: string;
}

/** 管理员配置 */
export interface BenchmarkConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string;
  is_active: boolean;
  updated_at: string;
}
