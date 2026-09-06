import type { PagedData } from './api';

export type AgentTaskCode = 'daily' | 'weekly';
export type AgentTaskRunStatus = 'not_run' | 'queued' | 'running' | 'success' | 'failed' | 'cancelled';
export type AgentTaskScopeStatus = 'selected_ready' | 'selected_missing' | 'unselected';
export type AgentTaskRunType = 'test' | 'retry' | 'manual_retry' | 'internal_retry' | 'auto';
export type AgentTaskFailureStage = 'data_source' | 'analysis' | 'internal_result' | 'delivery' | 'timeout';
export type AgentTaskLayerStatus = 'ready' | 'missing' | 'skipped' | 'failed' | 'success';

export interface AgentTaskProjectSummary {
  id: number;
  name: string;
  kol_name: string;
  account_name: string | null;
}

export interface AgentTaskDefinition {
  task_code: AgentTaskCode;
  name: '每日项目对标内容分析' | '账号人设内容基准更新';
  schedule: string;
  window_days: number;
  latest_formal_run: AgentTaskRun | null;
  next_fixed_run: string;
}

export interface AgentTaskOverview {
  agent_code: 'content-analysis';
  agent_name: '内容分析';
  selected_project_count: number;
  scope_counts: Record<AgentTaskScopeStatus, number>;
  status_summary: {
    today_completed: number;
    current_running: number;
    failed_last_7_days: number;
  };
  config_updated_by: number | null;
  config_updated_by_name: string | null;
  config_updated_at: string | null;
  report_root_ref: string | null;
  report_root_ref_configured: boolean;
  tasks: AgentTaskDefinition[];
  delivery_target: 'feishu_document';
}

export interface AgentTaskProject {
  project_id: number;
  project_name: string;
  project: AgentTaskProjectSummary;
  selected: boolean;
  scope_status: AgentTaskScopeStatus;
  missing_required: string[];
  optional_context_missing: string[];
  content_benchmark_total: number;
  content_benchmark_valid_count: number;
  content_benchmark_relation_status: 'missing' | 'partial_missing' | 'ready';
  content_data_status: 'ready';
  project_context_status: 'complete' | 'partial_missing';
  updated_at: string | null;
}

export interface AgentTaskInputModule {
  key: string;
  label: string;
  required: boolean;
  status: 'ready' | 'missing';
  source: string;
  updated_at: string | null;
  value: unknown;
  missing_reason: string | null;
  missing_reasons: string[];
}

export interface AgentTaskProjectInput {
  project_id: number;
  project_name: string;
  modules: AgentTaskInputModule[];
  delivery_target: 'feishu_document';
}

export interface AgentTaskRun {
  id: number;
  task_no: string;
  agent_code: 'content-analysis';
  task_code: AgentTaskCode;
  task: { code: AgentTaskCode; name: string };
  project_id: number | null;
  project: AgentTaskProjectSummary | null;
  execution: AgentTaskExecution;
  run_type: AgentTaskRunType;
  business_date: string;
  window_start: string;
  window_end: string;
  status: AgentTaskRunStatus;
  triggered_at: string;
  deadline_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  elapsed_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  reason_code: string | null;
  required_missing_reasons: string[];
  input_limited: boolean;
  controlled_test: boolean;
  input_limited_reasons: string[];
  delivery_target: 'feishu_document';
  delivery_status: AgentTaskLayerStatus;
  result_status: AgentTaskLayerStatus;
  failure_stage: AgentTaskFailureStage | null;
  database_precheck: AgentTaskResultLayer | null;
  feishu_relation: AgentTaskResultLayer | null;
  internal_result: AgentTaskInternalResult | null;
  delivery: AgentTaskDeliveryResult | null;
  retry_of_task_id: number | null;
  retried_by_task_ids: number[];
  input_snapshot?: Record<string, unknown>;
  controlled_result_summary?: Record<string, unknown>;
  logs?: AgentTaskRunLog[];
}

export interface AgentTaskRunLog {
  id: number;
  step_code: string;
  step_name: string;
  status: AgentTaskRunStatus;
  message: string | null;
  created_at: string;
}

export interface AgentTaskProjectListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  scope_status?: AgentTaskScopeStatus;
}

export interface AgentTaskRunListParams {
  page?: number;
  page_size?: number;
  task_code?: AgentTaskCode;
  status?: AgentTaskRunStatus;
  project_id?: number;
  account_key?: string;
  run_type?: AgentTaskRunType;
  started_from?: string;
  started_to?: string;
}

export interface AgentTaskConfigRequest {
  selected_project_ids: number[];
  report_root_ref: string | null;
}

export interface AgentTaskConfigResponse extends AgentTaskConfigRequest {
  agent_code: 'content-analysis';
  updated_by: number;
  updated_by_name: string;
  updated_at: string;
}

export interface AgentTaskWeeklyAccount {
  account_key: string;
  account_name: string | null;
  project_ids: number[];
}

export interface AgentTaskWeeklyAccountListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  project_id?: number;
}

export type AgentTaskExecution =
  | { object_type: 'project'; project_id: number }
  | {
      object_type: 'account';
      account_key_hash: string;
      project_ids: number[];
      weekly_batch_id: string;
      batch_size: number;
      batch_position: number;
    }
  | {
      object_type: 'weekly_batch_finalize';
      weekly_batch_id: string;
      batch_size: number;
      project_ids: number[];
      finalize_version: string;
    };

export interface AgentTaskResultLayer {
  status: AgentTaskLayerStatus;
  reason_code?: string | null;
  content_read_status?: AgentTaskLayerStatus;
}

export interface AgentTaskInternalResult extends AgentTaskResultLayer {
  outcome?: 'content' | 'no_content';
  internal_result_id?: string;
}

export interface AgentTaskDeliveryResult extends AgentTaskResultLayer {
  delivery_identity?: string;
  document_url?: string;
}

export type AgentTaskControlledRunRequest =
  | { task_code: 'daily'; project_id: number; request_id: string }
  | { task_code: 'weekly'; account_key: string; request_id: string };

export interface AgentTaskRetryRequest {
  request_id: string;
}

export type AgentTaskProjectPage = PagedData<AgentTaskProject>;
export type AgentTaskWeeklyAccountPage = PagedData<AgentTaskWeeklyAccount>;
export type AgentTaskRunPage = PagedData<AgentTaskRun>;
