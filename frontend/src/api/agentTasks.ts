import { get, post, put } from './request';
import type {
  AgentTaskConfigRequest,
  AgentTaskConfigResponse,
  AgentTaskControlledRunRequest,
  AgentTaskOverview,
  AgentTaskProjectInput,
  AgentTaskProjectListParams,
  AgentTaskProjectPage,
  AgentTaskRun,
  AgentTaskRunListParams,
  AgentTaskRunPage,
  AgentTaskRetryRequest,
  AgentTaskWeeklyAccountListParams,
  AgentTaskWeeklyAccountPage,
} from '../types/agentTask';

const PREFIX = '/api/admin/agent-tasks/content-analysis';
type QueryParams = Record<string, string | number | boolean | undefined>;

export async function getAgentTaskOverview(): Promise<AgentTaskOverview> {
  return get<AgentTaskOverview>(`${PREFIX}/overview`);
}

export async function getAgentTaskProjects(params?: AgentTaskProjectListParams): Promise<AgentTaskProjectPage> {
  return get<AgentTaskProjectPage>(`${PREFIX}/projects`, params as QueryParams);
}

export async function getAgentTaskProjectInput(project_id: number): Promise<AgentTaskProjectInput> {
  return get<AgentTaskProjectInput>(`${PREFIX}/projects/${project_id}/input`);
}

export async function getAgentTaskWeeklyAccounts(params?: AgentTaskWeeklyAccountListParams): Promise<AgentTaskWeeklyAccountPage> {
  return get<AgentTaskWeeklyAccountPage>(`${PREFIX}/weekly-accounts`, params as QueryParams);
}

export async function saveAgentTaskConfig(body: AgentTaskConfigRequest): Promise<AgentTaskConfigResponse> {
  return put<AgentTaskConfigResponse>(`${PREFIX}/config`, body);
}

export async function getAgentTaskRuns(params?: AgentTaskRunListParams): Promise<AgentTaskRunPage> {
  return get<AgentTaskRunPage>(`${PREFIX}/runs`, params as QueryParams);
}

export async function getAgentTaskRun(run_id: number): Promise<AgentTaskRun> {
  return get<AgentTaskRun>(`${PREFIX}/runs/${run_id}`);
}

export async function createAgentTaskTestRun(body: AgentTaskControlledRunRequest): Promise<AgentTaskRun> {
  return post<AgentTaskRun>(`${PREFIX}/test-runs`, body);
}

export async function retryAgentTaskRun(run_id: number, body: AgentTaskRetryRequest): Promise<AgentTaskRun> {
  return post<AgentTaskRun>(`${PREFIX}/runs/${run_id}/retry`, body);
}
