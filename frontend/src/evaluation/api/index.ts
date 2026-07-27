/**
 * AIGC 评测系统 — API 封装
 *
 * 端点对齐：
 *   - admin:  /api/admin/evaluation/*      （admin only，backend/app/evaluation/routers/admin_evaluation.py）
 *   - operator: /api/operator/evaluation/* （operator + admin，backend/app/evaluation/routers/operator_evaluation.py）
 *
 * 所有 JSON 调用走 @/api/request（红线 #3），不裸 fetch。
 */
import { get, post, put, del } from '../../api/request';
import type {
  EvalCaseDelta,
  EvalCaseResult,
  EvalComparisonReport,
  EvalDimension,
  EvalDimensionCreate,
  EvalDimensionUpdate,
  EvalHumanLabelRequest,
  EvalPaged,
  EvalRubric,
  EvalRubricBatchUpdate,
  EvalRun,
  EvalRunListParams,
  EvalSchedulePolicy,
  EvalSchedulePolicyCreate,
  EvalSchedulePolicyUpdate,
  EvalScore,
  EvalTestCase,
  EvalTestCaseCreate,
  EvalTestCaseListParams,
  EvalTestCaseUpdate,
  EvalTriggerRunRequest,
  EvalVersion,
  EvalVersionClone,
  EvalVersionCreate,
} from '../types';

// ---------------------------------------------------------------------------
// 测试样本（operator）
// ---------------------------------------------------------------------------

export async function listTestCases(params: EvalTestCaseListParams = {}) {
  return get<EvalPaged<EvalTestCase>>(
    '/api/operator/evaluation/test-cases',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export async function createTestCase(body: EvalTestCaseCreate) {
  return post<EvalTestCase>('/api/operator/evaluation/test-cases', body);
}

export async function updateTestCase(id: number, body: EvalTestCaseUpdate) {
  return put<EvalTestCase>(`/api/operator/evaluation/test-cases/${id}`, body);
}

export async function deleteTestCase(id: number) {
  return del<{ id: number; deleted_at: string }>(`/api/operator/evaluation/test-cases/${id}`);
}

// ---------------------------------------------------------------------------
// 版本（admin 全量 CRUD / operator 只读 active）
// ---------------------------------------------------------------------------

export async function listVersionsAdmin(toolCode?: string) {
  return get<EvalVersion[]>('/api/admin/evaluation/versions', toolCode ? { tool_code: toolCode } : undefined);
}

export async function listVersionsOperator(toolCode?: string) {
  return get<EvalVersion[]>('/api/operator/evaluation/versions', toolCode ? { tool_code: toolCode } : undefined);
}

export async function getVersion(id: number) {
  return get<EvalVersion>(`/api/admin/evaluation/versions/${id}`);
}

export async function createVersion(body: EvalVersionCreate) {
  return post<EvalVersion>('/api/admin/evaluation/versions', body);
}

export async function deleteVersion(id: number) {
  return del<{ id: number; deleted_at: string }>(`/api/admin/evaluation/versions/${id}`);
}

export async function cloneVersion(id: number, body: EvalVersionClone) {
  return post<EvalVersion>(`/api/admin/evaluation/versions/${id}/clone`, body);
}

// ---------------------------------------------------------------------------
// 运行 + 评分（operator）
// ---------------------------------------------------------------------------

export async function triggerRun(body: EvalTriggerRunRequest) {
  return post<EvalRun>('/api/operator/evaluation/runs', body);
}

export async function listRuns(params: EvalRunListParams = {}) {
  return get<EvalPaged<EvalRun>>(
    '/api/operator/evaluation/runs',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export async function getRun(id: number) {
  return get<EvalRun>(`/api/operator/evaluation/runs/${id}`);
}

export async function listRunScores(id: number) {
  return get<EvalScore[]>(`/api/operator/evaluation/runs/${id}/scores`);
}

export async function listCaseResults(runId: number) {
  return get<EvalCaseResult[]>(`/api/operator/evaluation/runs/${runId}/case-results`);
}

export async function cancelRun(id: number) {
  return post<EvalRun>(`/api/operator/evaluation/runs/${id}/cancel`);
}

export async function submitHumanLabel(scoreId: number, body: EvalHumanLabelRequest) {
  return put<EvalScore>(`/api/operator/evaluation/scores/${scoreId}/human-label`, body);
}

export async function compareRuns(runA: number, runB: number) {
  return get<EvalComparisonReport>('/api/operator/evaluation/compare', {
    run_a: runA,
    run_b: runB,
  });
}

// ---------------------------------------------------------------------------
// 维度 + Rubric（admin）
// ---------------------------------------------------------------------------

export async function listDimensions(toolCode?: string) {
  return get<EvalDimension[]>('/api/admin/evaluation/dimensions', toolCode ? { tool_code: toolCode } : undefined);
}

export async function createDimension(body: EvalDimensionCreate) {
  return post<EvalDimension>('/api/admin/evaluation/dimensions', body);
}

export async function updateDimension(id: number, body: EvalDimensionUpdate) {
  return put<EvalDimension>(`/api/admin/evaluation/dimensions/${id}`, body);
}

export async function deleteDimension(id: number) {
  return del<{ id: number; deleted_at: string }>(`/api/admin/evaluation/dimensions/${id}`);
}

export async function listRubrics(dimensionId: number) {
  return get<EvalRubric[]>(`/api/admin/evaluation/dimensions/${dimensionId}/rubrics`);
}

export async function replaceRubrics(dimensionId: number, body: EvalRubricBatchUpdate) {
  return put<EvalRubric[]>(`/api/admin/evaluation/dimensions/${dimensionId}/rubrics`, body);
}

// ---------------------------------------------------------------------------
// 定时策略（admin）
// ---------------------------------------------------------------------------

export async function listSchedulePolicies() {
  return get<EvalSchedulePolicy[]>('/api/admin/evaluation/schedule-policies');
}

export async function createSchedulePolicy(body: EvalSchedulePolicyCreate) {
  return post<EvalSchedulePolicy>('/api/admin/evaluation/schedule-policies', body);
}

export async function updateSchedulePolicy(id: number, body: EvalSchedulePolicyUpdate) {
  return put<EvalSchedulePolicy>(`/api/admin/evaluation/schedule-policies/${id}`, body);
}

export async function deleteSchedulePolicy(id: number) {
  return del<{ id: number; deleted_at: string }>(`/api/admin/evaluation/schedule-policies/${id}`);
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/** 用于 UI 显示用的样例 diff 方向计算（UI 自身也保留这份逻辑，避免冗余请求） */
export function deriveDirection(a: number | null, b: number | null): EvalCaseDelta['direction'] {
  if (a === null || b === null) return 'flat';
  const delta = b - a;
  if (delta > 0.05) return 'improve';
  if (delta < -0.05) return 'worsen';
  return 'flat';
}
