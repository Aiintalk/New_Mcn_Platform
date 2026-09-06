import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockOverview = vi.fn();
const mockProjects = vi.fn();
const mockProjectInput = vi.fn();
const mockWeeklyAccounts = vi.fn();
const mockSaveConfig = vi.fn();
const mockRuns = vi.fn();
const mockRun = vi.fn();
const mockTestRun = vi.fn();
const mockRetry = vi.fn();

vi.mock('../../../api/agentTasks', () => ({
  getAgentTaskOverview: (...args: unknown[]) => mockOverview(...args),
  getAgentTaskProjects: (...args: unknown[]) => mockProjects(...args),
  getAgentTaskProjectInput: (...args: unknown[]) => mockProjectInput(...args),
  getAgentTaskWeeklyAccounts: (...args: unknown[]) => mockWeeklyAccounts(...args),
  saveAgentTaskConfig: (...args: unknown[]) => mockSaveConfig(...args),
  getAgentTaskRuns: (...args: unknown[]) => mockRuns(...args),
  getAgentTaskRun: (...args: unknown[]) => mockRun(...args),
  createAgentTaskTestRun: (...args: unknown[]) => mockTestRun(...args),
  retryAgentTaskRun: (...args: unknown[]) => mockRetry(...args),
}));

import AgentTaskConfigPage from '../../../pages/admin/AgentTaskConfigPage';
import { getShanghaiDate } from '../../../pages/admin/agentTaskDate';

const pagination = { page: 1, page_size: 20, total: 2, total_pages: 1 };
const projectReady = {
  project_id: 7, project_name: '职场成长项目',
  project: { id: 7, name: '职场成长项目', kol_name: '达人甲', account_name: '达人甲内容号' },
  selected: true, scope_status: 'selected_ready' as const, missing_required: [],
  optional_context_missing: ['近期优先级'], content_benchmark_total: 2,
  content_benchmark_valid_count: 2, content_benchmark_relation_status: 'ready' as const,
  content_data_status: 'ready' as const, project_context_status: 'partial_missing' as const,
  updated_at: '2026-09-03T10:00:00+08:00',
};
const projectMissing = {
  ...projectReady, project_id: 8, project_name: '生活方式项目',
  project: { id: 8, name: '生活方式项目', kol_name: '达人乙', account_name: null },
  selected: true, scope_status: 'selected_missing' as const,
  missing_required: ['缺少可识别内容对标账号'], optional_context_missing: [],
  content_benchmark_total: 1, content_benchmark_valid_count: 0,
  content_benchmark_relation_status: 'missing' as const,
};
const projectUnselected = { ...projectReady, project_id: 9, project_name: '未选择项目', selected: false, scope_status: 'unselected' as const };
const runFailed = {
  id: 31, task_no: 'CA-31', agent_code: 'content-analysis' as const, task_code: 'daily' as const,
  task: { code: 'daily' as const, name: '每日项目对标内容分析' }, project_id: 7,
  project: projectReady.project, run_type: 'test' as const, business_date: '2026-09-03',
  window_start: '2026-08-31T00:00:00+08:00', window_end: '2026-09-02T23:59:59+08:00',
  status: 'failed' as const, triggered_at: '2026-09-03T10:00:00+08:00', deadline_at: '2026-09-03T22:00:00+08:00',
  started_at: '2026-09-03T10:01:00+08:00', finished_at: '2026-09-03T10:02:00+08:00',
  duration_ms: 60000, elapsed_ms: 60000, error_code: 'TIMEOUT', error_message: '运行超过 12 小时',
  reason_code: 'TIMEOUT', required_missing_reasons: [], input_limited: true, controlled_test: true,
  input_limited_reasons: ['近期优先级缺失'], delivery_target: 'feishu_document' as const,
  delivery_status: 'skipped' as const, result_status: 'skipped' as const,
  execution: { object_type: 'project' as const, project_id: 7 }, failure_stage: 'analysis' as const,
  database_precheck: { status: 'ready' as const }, feishu_relation: { status: 'ready' as const, content_read_status: 'ready' as const },
  internal_result: { status: 'failed' as const, reason_code: 'ANALYSIS_FAILED' }, delivery: { status: 'skipped' as const },
  retry_of_task_id: null, retried_by_task_ids: [32],
};
const runQueued = { ...runFailed, id: 32, task_no: 'CA-32', status: 'queued' as const, run_type: 'retry' as const, controlled_test: false, error_code: null, error_message: null, reason_code: null, retried_by_task_ids: [] };
const runInternalRetry = { ...runQueued, id: 39, task_no: 'CA-39', run_type: 'internal_retry' as const };
const runTimeout = { ...runFailed, id: 40, task_no: 'CA-40', failure_stage: 'timeout' as const };
const runWithoutResult = {
  ...runQueued,
  database_precheck: null,
  feishu_relation: null,
  internal_result: null,
  delivery: null,
};
const runSuccess = { ...runFailed, id: 33, task_no: 'CA-33', status: 'success' as const, error_code: null, error_message: null, reason_code: null, controlled_test: false };
const runRunning = { ...runFailed, id: 34, task_no: 'CA-34', status: 'running' as const, duration_ms: null, elapsed_ms: 90000, error_code: null, error_message: null, reason_code: null, controlled_test: false };
const runAccountSuccess = {
  ...runSuccess,
  id: 35,
  task_no: 'CA-35',
  task_code: 'weekly' as const,
  task: { code: 'weekly' as const, name: '账号人设内容基准更新' },
  project_id: null,
  project: null,
  run_type: 'auto' as const,
  execution: {
    object_type: 'account' as const,
    account_key_hash: 'abc123hash',
    project_ids: [7, 9],
    weekly_batch_id: 'weekly-1',
    batch_size: 2,
    batch_position: 1,
  },
  failure_stage: null,
  database_precheck: { status: 'ready' as const },
  feishu_relation: { status: 'ready' as const, content_read_status: 'ready' as const },
  internal_result: { status: 'success' as const, outcome: 'no_content' as const, internal_result_id: 'internal-35' },
  delivery: { status: 'success' as const, delivery_identity: 'doc-35', document_url: 'https://example.com/document/35' },
};
const runTestSuccess = {
  ...runAccountSuccess,
  id: 37,
  task_no: 'CA-37',
  run_type: 'test' as const,
  controlled_test: true,
  internal_result: { status: 'success' as const, outcome: 'content' as const, internal_result_id: 'internal-test-37' },
  controlled_result_summary: {
    execution: { account_key: 'sec-sensitive-plain-text' },
    delivery_target: { report_root_ref: 'sensitive-report-root-ref' },
  },
};
const runWeeklyFinalize = {
  ...runAccountSuccess,
  id: 38,
  task_no: 'CA-38',
  task: { code: 'weekly' as const, name: '周批次收尾' },
  execution: {
    object_type: 'weekly_batch_finalize' as const,
    weekly_batch_id: 'content-analysis:weekly:2026-09-06',
    batch_size: 3,
    project_ids: [7, 9],
    finalize_version: 'state-v1',
  },
  feishu_relation: { status: 'skipped' as const },
  internal_result: { status: 'success' as const, outcome: 'content' as const, internal_result_id: 'weekly-summary-v1' },
  delivery: { status: 'success' as const, delivery_identity: 'weekly-document', document_url: 'https://example.com/document/weekly' },
};
const runDeliveryFailed = {
  ...runFailed,
  id: 36,
  task_no: 'CA-36',
  failure_stage: 'delivery' as const,
  error_message: '文档投递失败',
  internal_result: { status: 'success' as const, outcome: 'content' as const, internal_result_id: 'internal-36' },
  delivery: { status: 'failed' as const, reason_code: 'DELIVERY_FAILED', delivery_identity: 'doc-36' },
};
const runDeliveryTimedOut = {
  ...runDeliveryFailed,
  id: 39,
  task_no: 'CA-39',
  failure_stage: 'timeout' as const,
  error_message: '文档投递超时',
  delivery: { status: 'failed' as const, reason_code: 'DEADLINE_EXCEEDED', delivery_identity: 'doc-39' },
};

function renderPage() {
  return render(<App><AgentTaskConfigPage /></App>);
}

describe('AgentTaskConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOverview.mockResolvedValue({
      agent_code: 'content-analysis', agent_name: '内容分析', selected_project_count: 2,
      scope_counts: { selected_ready: 1, selected_missing: 1, unselected: 1 },
      status_summary: { today_completed: 3, current_running: 1, failed_last_7_days: 2 },
      config_updated_by: 1, config_updated_by_name: '管理员甲', config_updated_at: '2026-09-03T10:00:00+08:00',
      report_root_ref: 'folder-old', report_root_ref_configured: true,
      tasks: [
        { task_code: 'daily', name: '每日项目对标内容分析', schedule: '每日 00:00', window_days: 3, latest_formal_run: null, next_fixed_run: '2026-09-04T00:00:00+08:00' },
        { task_code: 'weekly', name: '账号人设内容基准更新', schedule: '每周一 01:00', window_days: 30, latest_formal_run: null, next_fixed_run: '2026-09-07T01:00:00+08:00' },
      ], delivery_target: 'feishu_document',
    });
    mockProjects.mockResolvedValue({ items: [projectReady, projectMissing, projectUnselected], pagination });
    mockWeeklyAccounts.mockResolvedValue({
      items: [
        { account_key: 'sec-shared', account_name: '共享账号', project_ids: [7, 9] },
        { account_key: 'sec-second', account_name: null, project_ids: [7] },
      ],
      pagination: { ...pagination, total: 2 },
    });
    mockRuns.mockResolvedValue({ items: [runFailed], pagination: { ...pagination, total: 1 } });
    mockProjectInput.mockResolvedValue({
      project_id: 7, project_name: '职场成长项目', delivery_target: 'feishu_document',
      modules: [
        { key: 'persona', label: '人格', required: true, status: 'ready', source: '项目资料', updated_at: '2026-09-03T10:00:00+08:00', value: '真实克制', missing_reason: null, missing_reasons: [] },
        { key: 'priority', label: '近期优先级', required: false, status: 'missing', source: '项目业务上下文', updated_at: null, value: null, missing_reason: '暂未维护', missing_reasons: ['近期优先级'] },
      ],
    });
    mockRun.mockResolvedValue({ ...runFailed, logs: [{ id: 1, step_code: 'timeout', step_name: '超时收敛', status: 'failed', message: '运行超过 12 小时', created_at: '2026-09-03T22:00:00+08:00' }] });
    mockSaveConfig.mockResolvedValue({ selected_project_ids: [7, 8], report_root_ref: 'folder-new', agent_code: 'content-analysis', updated_by: 1, updated_by_name: '管理员甲', updated_at: '2026-09-03T10:20:00+08:00' });
    mockTestRun.mockResolvedValue({ ...runFailed, id: 40, status: 'success', error_message: null });
    mockRetry.mockResolvedValue({ ...runFailed, id: 32, status: 'queued', retry_of_task_id: 31 });
  });

  it('只展示内容分析身份、两个页签、两个固定任务，并排除未确认智能体和旧结果文案', async () => {
    renderPage();
    expect(await screen.findByText('内容分析（首期）')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '任务与输入' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '运行监控' })).toBeInTheDocument();
    expect(await screen.findByText('每日项目对标内容分析')).toBeInTheDocument();
    expect(screen.getByText('账号人设内容基准更新')).toBeInTheDocument();
    expect(screen.queryByText('直播复盘')).not.toBeInTheDocument();
    expect(screen.queryByText('内容规划缺失但可运行')).not.toBeInTheDocument();
    expect(screen.queryByText('日报已写入')).not.toBeInTheDocument();
    expect(screen.queryByText(/本分支|合同已具备|阶段二单模块验证|部署授权/)).not.toBeInTheDocument();
    expect(screen.getAllByText('自动任务尚未启用；启用后将按固定北京时间和已保存范围运行。').length).toBeGreaterThan(0);
  });

  it('回显并随项目范围保存共享报告根目录，不提供两张飞书输入表配置', async () => {
    const user = userEvent.setup();
    renderPage();

    const reportRoot = await screen.findByRole('textbox', { name: '内容分析飞书报告根目录' });
    await waitFor(() => expect(reportRoot).toHaveValue('folder-old'));
    expect(screen.getAllByText(/共享.*持续生效.*不按项目/).length).toBeGreaterThan(0);
    expect(screen.queryByText('项目清单飞书表')).not.toBeInTheDocument();
    expect(screen.queryByText('内容明细飞书表')).not.toBeInTheDocument();

    await user.clear(reportRoot);
    await user.type(reportRoot, 'folder-new');
    await user.click(screen.getByRole('button', { name: '保存项目范围与报告根目录' }));
    await waitFor(() => expect(mockSaveConfig).toHaveBeenCalledWith({
      selected_project_ids: [7, 8],
      report_root_ref: 'folder-new',
    }));
  });

  it('报告根目录未配置时明确说明自动和测试任务只记录为未运行', async () => {
    const user = userEvent.setup();
    mockOverview.mockResolvedValue({
      agent_code: 'content-analysis', agent_name: '内容分析', selected_project_count: 2,
      scope_counts: { selected_ready: 1, selected_missing: 1, unselected: 1 },
      status_summary: { today_completed: 0, current_running: 0, failed_last_7_days: 0 },
      config_updated_by: 1, config_updated_by_name: '管理员甲', config_updated_at: '2026-09-03T10:00:00+08:00',
      report_root_ref: null, report_root_ref_configured: false, tasks: [],
      delivery_target: 'feishu_document',
    });
    renderPage();

    expect(await screen.findByText('报告根目录未配置：自动和测试任务只记录为未运行，不调用内容分析执行器。')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    const dialog = screen.getByRole('dialog', { name: '发起受控测试' });
    expect(within(dialog).getByText('请先保存内容分析飞书报告根目录；未配置时本次测试只会记录为未运行。')).toBeInTheDocument();
  });

  it('非上海时区仍按北京时间展示两项固定任务的触发、窗口和下次运行', async () => {
    const originalTimezone = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      renderPage();
      const fixedTaskCard = (await screen.findByRole('heading', { name: '固定任务' })).closest('.agent-task-card');
      expect(fixedTaskCard).not.toBeNull();
      const taskContract = within(fixedTaskCard as HTMLElement);
      expect(await taskContract.findByText('每日项目对标内容分析')).toBeInTheDocument();
      expect(taskContract.getByText('每日 00:00（北京时间）')).toBeInTheDocument();
      expect(taskContract.getByText('最近 3 个完整自然日')).toBeInTheDocument();
      expect(taskContract.getByText('09/04 00:00')).toBeInTheDocument();
      expect(taskContract.getByText('账号人设内容基准更新')).toBeInTheDocument();
      expect(taskContract.getByText('每周一 01:00（北京时间）')).toBeInTheDocument();
      expect(taskContract.getByText('最近 30 个完整自然日')).toBeInTheDocument();
      expect(taskContract.getByText('09/07 01:00')).toBeInTheDocument();
    } finally {
      process.env.TZ = originalTimezone;
    }
  });

  it('展示三种范围状态、保存勾选结果，并标出输入受限而非内容规划缺失', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('职场成长项目');
    expect(screen.getAllByText('已选可运行').length).toBeGreaterThan(1);
    expect(screen.getAllByText('已选配置缺失').length).toBeGreaterThan(1);
    expect(screen.getAllByText('未选择').length).toBeGreaterThan(1);
    expect(screen.getAllByText('输入受限：近期优先级').length).toBeGreaterThan(0);
    expect(screen.getAllByText('飞书内容表在运行时完整校验').length).toBeGreaterThan(0);
    expect(screen.getByText('必要配置缺失')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '选择未选择项目' }));
    await user.click(screen.getByRole('button', { name: '保存项目范围与报告根目录' }));
    await waitFor(() => expect(mockSaveConfig).toHaveBeenCalledWith({ selected_project_ids: [7, 8, 9], report_root_ref: 'folder-old' }));
  });

  it('可查看只读输入，展示来源、更新时间和具体缺失原因', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '查看职场成长项目输入' }));
    const drawer = await screen.findByRole('dialog', { name: '职场成长项目 · 输入上下文' });
    expect(within(drawer).getByText('项目资料')).toBeInTheDocument();
    expect(within(drawer).getByText('真实克制')).toBeInTheDocument();
    expect(within(drawer).getByText(/暂未维护/)).toBeInTheDocument();
    expect(within(drawer).getByText('近期优先级')).toBeInTheDocument();
    expect(within(drawer).getByText('只读')).toBeInTheDocument();
  });

  it('监控支持筛选、详情、受控测试与失败重试，并显示真实结果位置', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await screen.findByText(/CA-31/);
    expect(screen.getByText('同时展示项目、账号与周批收尾实例；内部结果和飞书投递按四层状态追踪。')).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: '运行状态' }), 'failed');
    await waitFor(() => expect(mockRuns).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'failed' })));
    await user.click(screen.getByRole('button', { name: '查看 CA-31 详情' }));
    expect(await screen.findByText('超时收敛')).toBeInTheDocument();
    expect(screen.getByText('12 小时截止')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '完整重试 CA-31' }));
    await waitFor(() => expect(screen.getAllByText('确认重试').length).toBeGreaterThan(0));
    const retryDialog = screen.getAllByRole('dialog').at(-1)!;
    await user.click(within(retryDialog).getByRole('button', { name: '确认完整重试' }));
    await waitFor(() => expect(mockRetry).toHaveBeenCalledWith(31, { request_id: expect.any(String) }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    await waitFor(() => expect(screen.getAllByText('发起受控测试').length).toBeGreaterThan(1));
    const testDialog = screen.getAllByRole('dialog').at(-1)!;
    await user.selectOptions(within(testDialog).getByRole('combobox', { name: '选择项目' }), '7');
    await user.click(within(testDialog).getByRole('button', { name: '开始受控测试' }));
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledWith({ task_code: 'daily', project_id: 7, request_id: expect.any(String) }));
    expect((await screen.findAllByText(/可保存带测试隔离标识的平台结构化结果.*不写正式业务投影或正式目录/)).length).toBeGreaterThan(0);
  });

  it('运行监控把周批次收尾与账号实例明确区分', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runWeeklyFinalize], pagination: { ...pagination, total: 1 } });
    mockRun.mockResolvedValue({ ...runWeeklyFinalize, logs: [] });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    expect((await screen.findAllByText('周批次收尾')).length).toBeGreaterThan(0);
    expect(screen.getByText('批次 content-analysis:weekly:2026-09-06 · 3 个账号')).toBeInTheDocument();
    const finalizeRow = screen.getByText(/CA-38/).closest('tr');
    expect(finalizeRow).not.toBeNull();
    expect(within(finalizeRow as HTMLElement).queryByText(/账号实例/)).not.toBeInTheDocument();
    expect(screen.getByText('内部结果编号：weekly-summary-v1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '查看 CA-38 详情' }));
    const drawer = await screen.findByRole('dialog', { name: 'CA-38 · 执行详情' });
    expect(within(drawer).getByText('批次 content-analysis:weekly:2026-09-06 · 3 个账号')).toBeInTheDocument();
  });

  it('运行监控明确展示系统内部重试类型', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runInternalRetry], pagination: { ...pagination, total: 1 } });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));

    const row = (await screen.findByText(/CA-39/)).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('系统内部重试')).toBeInTheDocument();
  });

  it('运行监控把执行器主动截止失败展示为超时阶段', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runTimeout], pagination: { ...pagination, total: 1 } });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));

    const row = (await screen.findByText(/CA-40/)).closest('tr');
    expect(row).not.toBeNull();
    expect(row).toHaveTextContent('失败阶段：超时');
  });

  it('未开始的任务只显示暂无结果，不再暴露待联调占位状态', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runWithoutResult], pagination: { ...pagination, total: 1 } });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));

    expect(await screen.findByText('暂无结果')).toBeInTheDocument();
    expect(screen.queryByText(/待联调/)).not.toBeInTheDocument();
  });

  it('日测试允许未选择但必要配置通过的项目且不改变持续项目范围', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('职场成长项目');
    await user.click(screen.getByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    await waitFor(() => expect(screen.getAllByText('发起受控测试').length).toBeGreaterThan(1));
    const dialog = screen.getAllByRole('dialog').at(-1)!;
    expect(within(dialog).getByRole('option', { name: /未选择项目/ })).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择项目' }), '9');
    await user.click(within(dialog).getByRole('button', { name: '开始受控测试' }));
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledWith({ task_code: 'daily', project_id: 9, request_id: expect.any(String) }));
    await user.click(screen.getByRole('tab', { name: '任务与输入' }));
    expect(screen.getByRole('checkbox', { name: '选择未选择项目' })).not.toBeChecked();
  });

  it('取消选择后切换筛选并保存，不会被旧的服务端选择重新加入草稿', async () => {
    const user = userEvent.setup();
    mockProjects.mockImplementation((params?: { scope_status?: string }) => {
      if (params?.scope_status === 'selected_missing') return Promise.resolve({ items: [], pagination: { ...pagination, total: 0 } });
      return Promise.resolve({ items: [projectReady], pagination: { ...pagination, total: 1 } });
    });
    renderPage();
    const checkbox = await screen.findByRole('checkbox', { name: '选择职场成长项目' });
    await waitFor(() => expect(checkbox).toBeChecked());
    await user.click(checkbox);
    await user.selectOptions(screen.getByRole('combobox', { name: '项目范围状态' }), 'selected_ready');
    await waitFor(() => expect(mockProjects).toHaveBeenLastCalledWith(expect.objectContaining({ scope_status: 'selected_ready' })));
    await user.click(screen.getByRole('button', { name: '保存项目范围与报告根目录' }));
    await waitFor(() => expect(mockSaveConfig).toHaveBeenCalledWith({ selected_project_ids: [], report_root_ref: 'folder-old' }));
  });

  it('失败重试后清空失败筛选并加载新的排队记录', async () => {
    const user = userEvent.setup();
    mockRuns.mockImplementation((params?: { status?: string }) => Promise.resolve({
      items: params?.status === 'failed' ? [runFailed] : [runQueued], pagination: { ...pagination, total: 1 },
    }));
    renderPage();
    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '运行状态' }), 'failed');
    await screen.findByText(/CA-31/);
    await user.click(screen.getByRole('button', { name: '完整重试 CA-31' }));
    await waitFor(() => expect(screen.getAllByText('确认重试').length).toBeGreaterThan(0));
    const retryDialog = screen.getAllByRole('dialog').at(-1)!;
    await user.click(within(retryDialog).getByRole('button', { name: '确认完整重试' }));
    await waitFor(() => expect(mockRuns).toHaveBeenLastCalledWith(expect.objectContaining({ status: undefined, page: 1 })));
    expect(await screen.findByText(/CA-32/)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '运行状态' })).toHaveValue('');
  });

  it('快速切换运行状态时，旧响应不能覆盖最新筛选结果', async () => {
    const user = userEvent.setup();
    let resolveFailed: ((value: unknown) => void) | undefined;
    const failedResponse = new Promise(resolve => { resolveFailed = resolve; });
    mockRuns.mockImplementation((params?: { status?: string }) => {
      if (params?.status === 'failed') return failedResponse;
      if (params?.status === 'success') return Promise.resolve({ items: [runSuccess], pagination: { ...pagination, total: 1 } });
      return Promise.resolve({ items: [runFailed], pagination: { ...pagination, total: 1 } });
    });
    renderPage();
    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '运行状态' }), 'failed');
    await user.selectOptions(screen.getByRole('combobox', { name: '运行状态' }), 'success');
    await waitFor(() => expect(mockRuns).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'success' })));
    expect(await screen.findByText(/CA-33/)).toBeInTheDocument();
    resolveFailed?.({ items: [runFailed], pagination: { ...pagination, total: 1 } });
    await new Promise(resolve => window.setTimeout(resolve));
    expect(screen.getByText(/CA-33/)).toBeInTheDocument();
    expect(screen.queryByText(/CA-31/)).not.toBeInTheDocument();
  });

  it('初始概览旧响应不能覆盖保存后的保存人和时间', async () => {
    const user = userEvent.setup();
    let resolveInitialOverview: ((value: unknown) => void) | undefined;
    const initialOverview = new Promise(resolve => { resolveInitialOverview = resolve; });
    mockOverview.mockImplementationOnce(() => initialOverview).mockResolvedValue({
      agent_code: 'content-analysis', agent_name: '内容分析', selected_project_count: 1,
      scope_counts: { selected_ready: 1, selected_missing: 0, unselected: 0 }, status_summary: { today_completed: 0, current_running: 0, failed_last_7_days: 0 },
      config_updated_by: 1, config_updated_by_name: '管理员甲', config_updated_at: '2026-09-03T10:20:00+08:00', tasks: [], delivery_target: 'feishu_document',
    });
    renderPage();
    const saveButton = await screen.findByRole('button', { name: '保存项目范围与报告根目录' });
    await user.click(saveButton);
    await waitFor(() => expect(mockSaveConfig).toHaveBeenCalled());
    resolveInitialOverview?.({
      agent_code: 'content-analysis', agent_name: '内容分析', selected_project_count: 99,
      scope_counts: { selected_ready: 99, selected_missing: 0, unselected: 0 }, status_summary: { today_completed: 0, current_running: 0, failed_last_7_days: 0 },
      config_updated_by: 2, config_updated_by_name: '旧管理员', config_updated_at: '2026-08-01T10:00:00+08:00', tasks: [], delivery_target: 'feishu_document',
    });
    await new Promise(resolve => window.setTimeout(resolve));
    await waitFor(() => expect(screen.getByText(/最近保存：管理员甲/)).toBeInTheDocument());
    expect(screen.queryByText(/旧管理员/)).not.toBeInTheDocument();
  });

  it('延迟概览响应不能覆盖管理员未保存的报告根目录草稿', async () => {
    const user = userEvent.setup();
    let resolveOverview: ((value: unknown) => void) | undefined;
    mockOverview.mockImplementationOnce(() => new Promise(resolve => { resolveOverview = resolve; }));
    renderPage();

    const reportRoot = screen.getByRole('textbox', { name: '内容分析飞书报告根目录' });
    await user.type(reportRoot, 'folder-draft');
    resolveOverview?.({
      agent_code: 'content-analysis', agent_name: '内容分析', selected_project_count: 2,
      scope_counts: { selected_ready: 1, selected_missing: 1, unselected: 1 },
      status_summary: { today_completed: 3, current_running: 1, failed_last_7_days: 2 },
      config_updated_by: 1, config_updated_by_name: '管理员甲', config_updated_at: '2026-09-03T10:00:00+08:00',
      report_root_ref: 'folder-server-old', report_root_ref_configured: true, tasks: [],
      delivery_target: 'feishu_document',
    });

    await waitFor(() => expect(mockOverview).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(reportRoot).toHaveValue('folder-draft'));
  });

  it('上海日期在时区边界按 Asia/Shanghai 计算，运行中耗时显示 elapsed_ms，项目筛选可识别红人和账号', async () => {
    expect(getShanghaiDate(new Date('2026-09-02T20:30:00Z'))).toBe('2026-09-03');
    mockRuns.mockResolvedValue({ items: [runRunning], pagination: { ...pagination, total: 1 } });
    renderPage();
    await userEvent.setup().click(await screen.findByRole('tab', { name: '运行监控' }));
    expect(await screen.findByText('1 分 30 秒')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /达人甲.*职场成长项目.*达人甲内容号/ })).toBeInTheDocument();
  });

  it('周测试从账号候选选择并显示关联项目，失败后再次确认复用 request_id', async () => {
    const user = userEvent.setup();
    mockTestRun.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValueOnce(runAccountSuccess);
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    const dialog = screen.getAllByRole('dialog').at(-1)!;
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择固定任务' }), 'weekly');
    await waitFor(() => expect(mockWeeklyAccounts).toHaveBeenCalledWith({ page: 1, page_size: 20 }));
    expect(within(dialog).getByRole('option', { name: '请选择可测试账号' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('option', { name: /当前范围内/ })).not.toBeInTheDocument();
    expect(within(dialog).getByRole('option', { name: /共享账号.*项目 #7、#9/ })).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择周账号' }), 'sec-shared');

    const confirm = within(dialog).getByRole('button', { name: '开始受控测试' });
    await user.click(confirm);
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledTimes(1));
    await user.click(confirm);
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledTimes(2));

    const firstBody = mockTestRun.mock.calls[0][0];
    const secondBody = mockTestRun.mock.calls[1][0];
    expect(firstBody).toEqual({ task_code: 'weekly', account_key: 'sec-shared', request_id: expect.any(String) });
    expect(firstBody).not.toHaveProperty('project_ids');
    expect(secondBody.request_id).toBe(firstBody.request_id);
  });

  it('周账号搜索后清空旧选择和请求号，必须重新选择新候选才能提交', async () => {
    const user = userEvent.setup();
    mockTestRun.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValueOnce(runAccountSuccess);
    mockWeeklyAccounts.mockImplementation((params?: { keyword?: string }) => Promise.resolve({
      items: params?.keyword
        ? [{ account_key: 'sec-new-account', account_name: '新账号', project_ids: [9] }]
        : [{ account_key: 'sec-shared', account_name: '共享账号', project_ids: [7] }],
      pagination: { ...pagination, total: 1 },
    }));
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    const dialog = screen.getAllByRole('dialog').at(-1)!;
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择固定任务' }), 'weekly');
    const accountSelect = within(dialog).getByRole('combobox', { name: '选择周账号' });
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /共享账号/ })).toBeInTheDocument());
    await user.selectOptions(accountSelect, 'sec-shared');
    const confirm = within(dialog).getByRole('button', { name: '开始受控测试' });
    await user.click(confirm);
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledTimes(1));
    const firstRequestId = mockTestRun.mock.calls[0][0].request_id;

    await user.type(within(dialog).getByRole('textbox', { name: '搜索周账号' }), '新');
    await waitFor(() => expect(mockWeeklyAccounts).toHaveBeenLastCalledWith({ page: 1, page_size: 20, keyword: '新' }));
    await waitFor(() => expect(accountSelect).toHaveValue(''));
    await user.click(confirm);
    expect(mockTestRun).toHaveBeenCalledTimes(1);

    await user.selectOptions(accountSelect, 'sec-new-account');
    await user.click(confirm);
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledTimes(2));
    expect(mockTestRun.mock.calls[1][0].request_id).not.toBe(firstRequestId);
  });

  it('周账号翻页后清空已消失的旧选择，未重新选择时禁止提交', async () => {
    const user = userEvent.setup();
    mockWeeklyAccounts.mockImplementation((params?: { page?: number }) => Promise.resolve({
      items: params?.page === 2
        ? [{ account_key: 'sec-page-two', account_name: '第二页账号', project_ids: [9] }]
        : [{ account_key: 'sec-page-one', account_name: '第一页账号', project_ids: [7] }],
      pagination: { page: params?.page || 1, page_size: 20, total: 2, total_pages: 2 },
    }));
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    const dialog = screen.getAllByRole('dialog').at(-1)!;
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择固定任务' }), 'weekly');
    const accountSelect = within(dialog).getByRole('combobox', { name: '选择周账号' });
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /第一页账号/ })).toBeInTheDocument());
    await user.selectOptions(accountSelect, 'sec-page-one');
    await user.click(within(dialog).getByRole('button', { name: '2' }));
    await waitFor(() => expect(mockWeeklyAccounts).toHaveBeenLastCalledWith({ page: 2, page_size: 20 }));
    await waitFor(() => expect(accountSelect).toHaveValue(''));

    await user.click(within(dialog).getByRole('button', { name: '开始受控测试' }));
    expect(mockTestRun).not.toHaveBeenCalled();
  });

  it('无账号名称的周候选只显示稳定掩码但仍用完整账号键提交', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.click(screen.getByRole('button', { name: '发起受控测试' }));
    const dialog = screen.getAllByRole('dialog').at(-1)!;
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择固定任务' }), 'weekly');
    const maskedOption = await within(dialog).findByRole('option', { name: /未命名账号 \*\*\*\*cond.*项目 #7/ });
    expect(maskedOption).not.toHaveTextContent('sec-second');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择周账号' }), 'sec-second');
    await user.click(within(dialog).getByRole('button', { name: '开始受控测试' }));
    await waitFor(() => expect(mockTestRun).toHaveBeenCalledWith({ task_code: 'weekly', account_key: 'sec-second', request_id: expect.any(String) }));
  });

  it('运行监控展示正式与测试内部结果编号、四层状态和安全文档链接，不泄露账号或根目录引用', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runAccountSuccess, runTestSuccess, runFailed], pagination: { ...pagination, total: 3 } });
    mockRun.mockResolvedValue({ ...runTestSuccess, logs: [] });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    expect((await screen.findAllByText('账号实例 #abc123hash')).length).toBe(2);
    expect(screen.getAllByText('关联项目 #7、#9')).toHaveLength(2);
    expect(screen.getByText(/项目实例.*职场成长项目/)).toBeInTheDocument();
    expect(screen.getAllByText('数据库预检：已就绪').length).toBeGreaterThan(0);
    expect(screen.getAllByText('飞书关系：已就绪').length).toBeGreaterThan(0);
    expect(screen.getAllByText('内部结果：成功').length).toBeGreaterThan(0);
    expect(screen.getByText('内部结果编号：internal-35')).toBeInTheDocument();
    expect(screen.getByText('内部结果编号：internal-test-37')).toBeInTheDocument();
    expect(screen.getAllByText('投递：成功').length).toBeGreaterThan(0);
    expect(screen.getByText('无内容（空日报）')).toBeInTheDocument();
    const [link] = screen.getAllByRole('link', { name: '打开结果文档' });
    expect(link).toHaveAttribute('href', 'https://example.com/document/35');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByText('sec-sensitive-plain-text')).not.toBeInTheDocument();
    expect(screen.queryByText('sensitive-report-root-ref')).not.toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: '账号筛选' }), 'sec-shared');
    await waitFor(() => expect(mockRuns).toHaveBeenLastCalledWith(expect.objectContaining({ account_key: 'sec-shared' })));
    await user.click(screen.getByRole('button', { name: '查看 CA-37 详情' }));
    const detail = await screen.findByRole('dialog', { name: 'CA-37 · 执行详情' });
    expect(within(detail).getByText('账号实例 #abc123hash')).toBeInTheDocument();
    expect(within(detail).getByText('失败阶段：无')).toBeInTheDocument();
    expect(within(detail).getByText('内部结果编号：internal-test-37')).toBeInTheDocument();
    expect(within(detail).queryByText('sec-sensitive-plain-text')).not.toBeInTheDocument();
    expect(within(detail).queryByText('sensitive-report-root-ref')).not.toBeInTheDocument();
  });

  it('投递失败明确仅重试投递且失败后复用 request_id，其他失败明确完整重试', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runDeliveryFailed, runFailed], pagination: { ...pagination, total: 2 } });
    mockRetry.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValueOnce(runQueued);
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await screen.findByText(/CA-36/);
    await user.click(screen.getByRole('button', { name: '仅重试投递 CA-36' }));
    let dialog = screen.getAllByRole('dialog').at(-1)!;
    expect(within(dialog).getByText(/仅重试投递，不重复分析/)).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: '确认仅重试投递' });
    await user.click(confirm);
    await waitFor(() => expect(mockRetry).toHaveBeenCalledTimes(1));
    await user.click(confirm);
    await waitFor(() => expect(mockRetry).toHaveBeenCalledTimes(2));
    expect(mockRetry.mock.calls[0][0]).toBe(36);
    expect(mockRetry.mock.calls[1][1].request_id).toBe(mockRetry.mock.calls[0][1].request_id);

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '确认重试' })).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '完整重试 CA-31' }));
    dialog = screen.getAllByRole('dialog').at(-1)!;
    expect(within(dialog).getByText(/将执行完整重试/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '确认完整重试' })).toBeInTheDocument();
  });

  it('已有内部结果的投递超时只重试投递', async () => {
    const user = userEvent.setup();
    mockRuns.mockResolvedValue({ items: [runDeliveryTimedOut], pagination: { ...pagination, total: 1 } });
    renderPage();

    await user.click(await screen.findByRole('tab', { name: '运行监控' }));
    await user.click(await screen.findByRole('button', { name: '仅重试投递 CA-39' }));

    const dialog = screen.getAllByRole('dialog').at(-1)!;
    expect(within(dialog).getByText(/仅重试投递，不重复分析/)).toBeInTheDocument();
  });

  it('全量项目范围加载失败时，保存和勾选继续保持禁用', async () => {
    mockProjects.mockRejectedValue(new Error('项目范围加载失败'));
    renderPage();
    const saveButton = await screen.findByRole('button', { name: '正在加载已保存范围…' });
    expect(saveButton).toBeDisabled();
  });
});
