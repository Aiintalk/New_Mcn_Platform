/**
 * AIGC 评测系统 — 类型定义
 *
 * 对齐后端 backend/app/evaluation/routers/{admin,operator}_evaluation.py 的响应结构。
 * 字段命名与后端 _xxx_to_dict 输出保持一致（snake_case，由 request.ts 透传）。
 */

/** 工具标识（一期只有千川仿写） */
export type EvalToolCode = 'qianchuan-writer';

/** 触发方式 */
export type EvalTriggerType = 'manual' | 'auto' | 'schedule';

/** 运行状态机 */
export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'cancelled';

/** 通用分页结构 */
export interface EvalPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** 通用分页列表响应 */
export interface EvalPaged<T> {
  items: T[];
  pagination: EvalPagination;
}

// ---------------------------------------------------------------------------
// 测试样本（EvalTestCase）
// ---------------------------------------------------------------------------

export interface EvalTestCase {
  id: number;
  tool_code: EvalToolCode;
  name: string;
  description: string | null;
  /** 输入负载 JSONB：达人 / 卖点卡 / 参考脚本 / 对话上下文 */
  input_payload: Record<string, unknown>;
  tags: string[];
  is_active: boolean;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface EvalTestCaseListParams {
  page?: number;
  page_size?: number;
  tool_code?: EvalToolCode;
  tag?: string;
}

export interface EvalTestCaseCreate {
  tool_code: EvalToolCode;
  name: string;
  description?: string | null;
  input_payload: Record<string, unknown>;
  tags?: string[];
  is_active?: boolean;
}

export interface EvalTestCaseUpdate {
  tool_code?: EvalToolCode;
  name?: string;
  description?: string | null;
  input_payload?: Record<string, unknown>;
  tags?: string[];
  is_active?: boolean;
}

// ---------------------------------------------------------------------------
// 评分维度 + Rubric
// ---------------------------------------------------------------------------

export interface EvalDimension {
  id: number;
  tool_code: EvalToolCode;
  name: string;
  display_name: string;
  description: string | null;
  /** 0–1 浮点 */
  default_weight: number;
  score_min: number;
  score_max: number;
  /** 评分 Prompt 模板，支持 {{generated_output}} / {{rubric_text}} / {{persona}} */
  prompt_template: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface EvalDimensionCreate {
  tool_code: EvalToolCode;
  name: string;
  display_name: string;
  description?: string | null;
  default_weight: number;
  score_min?: number;
  score_max?: number;
  prompt_template: string;
  is_active?: boolean;
}

export interface EvalDimensionUpdate {
  tool_code?: EvalToolCode;
  name?: string;
  display_name?: string;
  description?: string | null;
  default_weight?: number;
  score_min?: number;
  score_max?: number;
  prompt_template?: string;
  is_active?: boolean;
}

export interface EvalRubric {
  id: number;
  dimension_id: number;
  /** 分数等级：10 / 8 / 6 / 4 / 2 */
  level: number;
  criteria: string;
  /** 场景变体 tag：default / skincare / diet … */
  scenario_tag: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface EvalRubricItemInput {
  level: number;
  criteria: string;
  scenario_tag?: string;
  is_active?: boolean;
}

export interface EvalRubricBatchUpdate {
  rubrics: EvalRubricItemInput[];
}

// ---------------------------------------------------------------------------
// 版本快照（不可编辑，只能 create / clone / 软删）
// ---------------------------------------------------------------------------

export interface EvalVersion {
  id: number;
  tool_code: EvalToolCode;
  name: string;
  description: string | null;
  /** 配置 payload：system_prompt_template / scoring_model_id / dimension_weights … */
  config_payload: Record<string, unknown>;
  parent_version_id: number | null;
  /** 关联维护：来源红人 id（spec §4.4 三步） */
  source_kol_id: number | null;
  auto_run_on_create: boolean;
  auto_run_tags: string[];
  is_active: boolean;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface EvalVersionCreate {
  tool_code: EvalToolCode;
  name: string;
  description?: string | null;
  /** 当不传 source_kol_id 时，admin 直接填 config_payload */
  config_payload?: Record<string, unknown>;
  parent_version_id?: number | null;
  /** 关联维护三步：选红人 → 抠 system_prompt_template → 校验 kol 存在 */
  source_kol_id?: number | null;
  /** 顶层 scoring 三件套（合并入 config_payload） */
  scoring_model_id?: string | null;
  scoring_provider?: string | null;
  scoring_adapter?: string | null;
  auto_run_on_create?: boolean;
  auto_run_tags?: string[];
  is_active?: boolean;
}

export interface EvalVersionClone {
  name: string;
  description?: string | null;
  /** 部分覆盖父版本 config_payload */
  config_payload_overrides?: Record<string, unknown>;
  auto_run_on_create?: boolean;
  auto_run_tags?: string[];
  is_active?: boolean;
}

// ---------------------------------------------------------------------------
// 运行 + 评分
// ---------------------------------------------------------------------------

export interface EvalRun {
  id: number;
  version_id: number;
  /** 一期恒为 default 策略 id */
  strategy_id: number | null;
  name: string;
  trigger_type: EvalTriggerType;
  status: EvalRunStatus;
  filter_tags: string[];
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  metadata: Record<string, unknown>;
  created_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface EvalTriggerRunRequest {
  version_id: number;
  filter_tags?: string[];
  name?: string;
  trigger_type?: EvalTriggerType;
}

/** GET /runs 列表查询参数 */
export interface EvalRunListParams {
  page?: number;
  page_size?: number;
  status?: EvalRunStatus;
  version_id?: number;
}

export interface EvalScore {
  id: number;
  case_result_id: number;
  dimension_id: number;
  weight_used: number;
  ai_score: number | null;
  ai_reasoning: string | null;
  ai_strengths: string[];
  ai_weaknesses: string[];
  human_score: number | null;
  human_feedback: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** GET /runs/{id}/case-results — 单 case 生成结果（含 generated_output，供「查看输出」） */
export interface EvalCaseResult {
  id: number;
  test_case_id: number;
  test_case_name: string;
  generated_output: string | null;
  output_payload: Record<string, unknown> | null;
  input_snapshot: Record<string, unknown> | null;
  created_at: string | null;
}

/** GET /admin/evaluation/queue-stats — 队列健康度 */
export interface EvalQueueStats {
  pending: number;
  running: number;
  failed_dead_letter: number;
  done: number;
  cancelled: number;
  oldest_pending_secs: number | null;
  runs_active: number;
}

/** GET /admin/evaluation/runs/{id}/jobs — 单 run 的 job 明细 */
export interface EvalRunJob {
  id: number;
  test_case_id: number;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  enqueued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface EvalHumanLabelRequest {
  human_score: number;
  human_feedback?: string | null;
}

// ---------------------------------------------------------------------------
// 版本对比报告（comparator.compare_runs）
// ---------------------------------------------------------------------------

export interface EvalDimensionDelta {
  dimension_id: number;
  dimension_name: string;
  avg_a: number | null;
  avg_b: number | null;
  /** b - a */
  delta: number | null;
}

export type EvalCaseDirection = 'improve' | 'worsen' | 'flat';

export interface EvalCaseDelta {
  test_case_id: number;
  test_case_name: string;
  avg_a: number | null;
  avg_b: number | null;
  delta: number | null;
  direction: EvalCaseDirection;
}

export interface EvalComparisonReport {
  run_a_id: number;
  run_b_id: number;
  overall_avg_a: number | null;
  overall_avg_b: number | null;
  overall_delta: number | null;
  dimension_deltas: EvalDimensionDelta[];
  case_deltas: EvalCaseDelta[];
  /** { improve, worsen, flat } */
  summary: Record<string, number>;
}

// ---------------------------------------------------------------------------
// 定时策略（admin）
// ---------------------------------------------------------------------------

export interface EvalSchedulePolicy {
  id: number;
  name: string;
  /** 5 字段 cron：分 时 日 月 周 */
  cron: string;
  /** null 表示使用最新 active 版本 */
  version_id: number | null;
  filter_tags: string[];
  is_active: boolean;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface EvalSchedulePolicyCreate {
  name: string;
  cron: string;
  version_id?: number | null;
  filter_tags?: string[];
  is_active?: boolean;
}

export interface EvalSchedulePolicyUpdate {
  name?: string;
  cron?: string;
  version_id?: number | null;
  filter_tags?: string[];
  is_active?: boolean;
}
