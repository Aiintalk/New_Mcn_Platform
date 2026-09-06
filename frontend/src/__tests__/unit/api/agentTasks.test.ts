import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGet, mockPost, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  post: mockPost,
  put: mockPut,
}));

import {
  createAgentTaskTestRun,
  getAgentTaskOverview,
  getAgentTaskProjectInput,
  getAgentTaskProjects,
  getAgentTaskRun,
  getAgentTaskRuns,
  getAgentTaskWeeklyAccounts,
  retryAgentTaskRun,
  saveAgentTaskConfig,
} from '../../../api/agentTasks';
import type { AgentTaskProjectSummary } from '../../../types/agentTask';

const prefix = '/api/admin/agent-tasks/content-analysis';
const projectWithoutAccountName: AgentTaskProjectSummary = {
  id: 7,
  name: '已入驻项目',
  kol_name: '达人甲',
  account_name: null,
};

describe('内容分析智能体任务 API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('项目摘要允许后端返回空账号名', () => {
    expect(projectWithoutAccountName.account_name).toBeNull();
  });

  it('读取总览时使用内容分析总览路径', async () => {
    const overview = { agent_code: 'content-analysis', selected_project_count: 2 };
    mockGet.mockResolvedValue(overview);

    await expect(getAgentTaskOverview()).resolves.toEqual(overview);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/overview`);
  });

  it('读取项目范围时保留 snake_case 分页和范围参数', async () => {
    const projects = { items: [], pagination: { page: 2, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(projects);

    await expect(getAgentTaskProjects({
      page: 2,
      page_size: 20,
      keyword: '达人甲',
      scope_status: 'selected_missing',
    })).resolves.toEqual(projects);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/projects`, {
      page: 2,
      page_size: 20,
      keyword: '达人甲',
      scope_status: 'selected_missing',
    });
  });

  it('读取单项目输入时把项目编号放入路径', async () => {
    const input = { project_id: 7, modules: [] };
    mockGet.mockResolvedValue(input);

    await expect(getAgentTaskProjectInput(7)).resolves.toEqual(input);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/projects/7/input`);
  });

  it('保存项目范围与共享报告根目录时通过 PUT 提交完整配置', async () => {
    const config = { selected_project_ids: [7, 9], report_root_ref: 'folder-ref' };
    mockPut.mockResolvedValue(config);

    await expect(saveAgentTaskConfig({ selected_project_ids: [7, 9], report_root_ref: 'folder-ref' })).resolves.toEqual(config);
    expect(mockPut).toHaveBeenCalledWith(`${prefix}/config`, { selected_project_ids: [7, 9], report_root_ref: 'folder-ref' });
  });

  it('读取周账号候选时保留分页、关键词与项目参数', async () => {
    const accounts = { items: [], pagination: { page: 2, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(accounts);

    await expect(getAgentTaskWeeklyAccounts({
      page: 2,
      page_size: 20,
      keyword: '达人甲',
      project_id: 7,
    })).resolves.toEqual(accounts);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/weekly-accounts`, {
      page: 2,
      page_size: 20,
      keyword: '达人甲',
      project_id: 7,
    });
  });

  it('读取运行列表时保留 snake_case 运行筛选参数', async () => {
    const runs = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(runs);

    await expect(getAgentTaskRuns({
      page: 3,
      page_size: 50,
      task_code: 'daily',
      status: 'not_run',
      project_id: 7,
      account_key: 'sec-account',
      run_type: 'test',
      started_from: '2026-09-01T00:00:00+08:00',
      started_to: '2026-09-03T23:59:59+08:00',
    })).resolves.toEqual(runs);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/runs`, {
      page: 3,
      page_size: 50,
      task_code: 'daily',
      status: 'not_run',
      project_id: 7,
      account_key: 'sec-account',
      run_type: 'test',
      started_from: '2026-09-01T00:00:00+08:00',
      started_to: '2026-09-03T23:59:59+08:00',
    });
  });

  it('读取单条运行时把运行编号放入路径', async () => {
    const run = { id: 31, status: 'not_run' };
    mockGet.mockResolvedValue(run);

    await expect(getAgentTaskRun(31)).resolves.toEqual(run);
    expect(mockGet).toHaveBeenCalledWith(`${prefix}/runs/31`);
  });

  it('创建日受控测试时 POST 项目与请求号', async () => {
    const run = { id: 31, status: 'success', controlled_test: true };
    mockPost.mockResolvedValue(run);

    await expect(createAgentTaskTestRun({ task_code: 'daily', project_id: 7, request_id: 'daily-uuid' })).resolves.toEqual(run);
    expect(mockPost).toHaveBeenCalledWith(`${prefix}/test-runs`, { task_code: 'daily', project_id: 7, request_id: 'daily-uuid' });
  });

  it('创建周受控测试时只 POST 账号与请求号，不发送项目列表', async () => {
    const run = { id: 33, status: 'success', controlled_test: true };
    mockPost.mockResolvedValue(run);

    await expect(createAgentTaskTestRun({ task_code: 'weekly', account_key: 'sec-account', request_id: 'weekly-uuid' })).resolves.toEqual(run);
    expect(mockPost).toHaveBeenCalledWith(`${prefix}/test-runs`, {
      task_code: 'weekly',
      account_key: 'sec-account',
      request_id: 'weekly-uuid',
    });
  });

  it('重试失败运行时 POST 请求号到单运行重试路径', async () => {
    const run = { id: 32, retry_of_task_id: 31, status: 'queued' };
    mockPost.mockResolvedValue(run);

    await expect(retryAgentTaskRun(31, { request_id: 'retry-uuid' })).resolves.toEqual(run);
    expect(mockPost).toHaveBeenCalledWith(`${prefix}/runs/31/retry`, { request_id: 'retry-uuid' });
  });
});
