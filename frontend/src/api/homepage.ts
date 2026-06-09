import { get } from './request';

export interface HomepageStats {
  today_outputs: number;
  today_outputs_change: string | null;
  week_outputs: number;
  week_outputs_change: string | null;
  in_progress_tasks: number;
  week_token_usage: number | null;
  week_tool_count: number;
  tool_usage_breakdown: {
    tool_name: string;
    tool_code: string | null;
    count: number;
    percentage: number;
  }[];
  recent_tools: {
    tool_name: string;
    tool_code: string;
    last_used_at: string;
  }[];
  last_login_at: string | null;
}

export interface HomepageTrend {
  trend: { date: string; count: number }[];
}

export function getHomepageStats(): Promise<HomepageStats> {
  return get<HomepageStats>('/api/operator/homepage/stats');
}

export function getHomepageTrend(): Promise<HomepageTrend> {
  return get<HomepageTrend>('/api/operator/homepage/trend');
}
