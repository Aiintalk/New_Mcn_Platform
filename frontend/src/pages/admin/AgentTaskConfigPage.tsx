import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Drawer, Modal, Tabs, message } from 'antd';
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
} from '../../api/agentTasks';
import type {
  AgentTaskCode,
  AgentTaskOverview,
  AgentTaskProject,
  AgentTaskProjectInput,
  AgentTaskRun,
  AgentTaskRunStatus,
  AgentTaskRunType,
  AgentTaskScopeStatus,
  AgentTaskWeeklyAccount,
} from '../../types/agentTask';
import { getShanghaiDate } from './agentTaskDate';

const PAGE_SIZE = 20;
const STATUS_LABELS: Record<AgentTaskRunStatus, string> = {
  not_run: '未运行', queued: '排队中', running: '运行中', success: '成功', failed: '失败', cancelled: '已取消',
};
const STATUS_CLASS: Record<AgentTaskRunStatus, string> = {
  not_run: 'badge-gray', queued: 'badge-gray', running: 'badge-warning', success: 'badge-success', failed: 'badge-danger', cancelled: 'badge-gray',
};
const SCOPE_LABELS: Record<AgentTaskScopeStatus, string> = {
  selected_ready: '已选可运行', selected_missing: '已选配置缺失', unselected: '未选择',
};
const SCOPE_CLASS: Record<AgentTaskScopeStatus, string> = {
  selected_ready: 'badge-success', selected_missing: 'badge-warning', unselected: 'badge-gray',
};
const RUN_TYPE_LABELS: Record<AgentTaskRunType, string> = { auto: '自动运行', test: '受控测试', retry: '阶段一重试', manual_retry: '手动重试', internal_retry: '系统内部重试' };
const LAYER_STATUS_LABELS = {
  ready: '已就绪', missing: '缺失', skipped: '已跳过', failed: '失败', success: '成功',
} as const;
const FAILURE_STAGE_LABELS = {
  data_source: '数据源', analysis: '分析', internal_result: '内部结果', delivery: '投递', timeout: '超时',
} as const;
const MISSING_REASON_LABELS: Record<string, string> = {
  CONTENT_BENCHMARK_SEC_UID_MISSING: '缺少可识别的内容对标账号',
  REPORT_ROOT_REF_MISSING: '内容分析飞书报告根目录未配置',
  optional_context_missing: '其他非必需上下文尚未补齐，不阻断运行',
  BACKGROUND_MISSING: '背景资料缺失', EXPERIENCE_MISSING: '经历资料缺失', RELATIONSHIPS_MISSING: '关系资料缺失',
  UNIQUE_STORY_MISSING: '个人故事缺失', EXTRA_NOTES_MISSING: '补充说明缺失', STYLE_NOTES_MISSING: '表达偏好缺失',
};

function formatTime(value: string | null | undefined, compact = false) {
  if (!value) return '—';
  const date = new Date(value);
  return compact
    ? date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hourCycle: 'h23', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hourCycle: 'h23' });
}

function formatDuration(ms: number | null) {
  if (ms == null) return '—';
  if (ms < 60000) return `${Math.round(ms / 1000)} 秒`;
  return `${Math.floor(ms / 60000)} 分 ${Math.round((ms % 60000) / 1000)} 秒`;
}

function formatMissingReason(value: string) { return MISSING_REASON_LABELS[value] || value; }

function formatInputValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  try { return JSON.stringify(value, null, 2); } catch { return '无法展示的只读数据'; }
}

function StatusBadge({ status }: { status: AgentTaskRunStatus }) {
  return <span className={`badge ${STATUS_CLASS[status]}`}>{STATUS_LABELS[status]}</span>;
}

function createRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    try { return globalThis.crypto.randomUUID(); } catch { /* 测试环境可能不支持原生 UUID。 */ }
  }
  return `agent-task-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function executionLabel(run: AgentTaskRun) {
  if (run.execution.object_type === 'account') return `账号实例 #${run.execution.account_key_hash}`;
  if (run.execution.object_type === 'weekly_batch_finalize') {
    return `批次 ${run.execution.weekly_batch_id} · ${run.execution.batch_size} 个账号`;
  }
  return `项目实例：${run.project?.name || `项目 #${run.execution.project_id}`}`;
}

function isDeliveryOnlyRetry(run: AgentTaskRun | null | undefined) {
  return Boolean(
    run
    && (run.failure_stage === 'delivery' || run.failure_stage === 'timeout')
    && run.internal_result?.internal_result_id
    && run.delivery?.delivery_identity,
  );
}

function safeDocumentUrl(value: string | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : null;
  } catch { return null; }
}

function weeklyAccountLabel(account: AgentTaskWeeklyAccount) {
  if (account.account_name) return account.account_name;
  const tail = account.account_key.length > 4 ? account.account_key.slice(-4) : '';
  return `未命名账号 ${tail ? `****${tail}` : '****'}`;
}

function ResultSummary({ run, includeFailureStage = false }: { run: AgentTaskRun; includeFailureStage?: boolean }) {
  const hasLayers = Boolean(run.database_precheck || run.feishu_relation || run.internal_result || run.delivery);
  const documentUrl = safeDocumentUrl(run.delivery?.document_url);
  if (!hasLayers) return <span className="agent-task-secondary">暂无结果</span>;
  return <div className="agent-task-secondary">
    {includeFailureStage && <div>失败阶段：{run.failure_stage ? FAILURE_STAGE_LABELS[run.failure_stage] : '无'}</div>}
    <div>数据库预检：{run.database_precheck ? LAYER_STATUS_LABELS[run.database_precheck.status] : '暂无结果'}</div>
    <div>飞书关系：{run.feishu_relation ? LAYER_STATUS_LABELS[run.feishu_relation.status] : '暂无结果'}</div>
    <div>内部结果：{run.internal_result ? LAYER_STATUS_LABELS[run.internal_result.status] : '暂无结果'}</div>
    {run.internal_result?.internal_result_id && <div>内部结果编号：{run.internal_result.internal_result_id}</div>}
    {run.internal_result?.outcome === 'no_content' && <div>无内容（空日报）</div>}
    <div>投递：{run.delivery ? LAYER_STATUS_LABELS[run.delivery.status] : '暂无结果'}</div>
    {documentUrl && <div><a href={documentUrl} target="_blank" rel="noopener noreferrer">打开结果文档</a></div>}
  </div>;
}

function Pagination({ page, total, totalPages, onChange }: { page: number; total: number; totalPages: number; onChange: (value: number) => void }) {
  if (totalPages <= 1) return null;
  return <div className="pagination"><span>共 {total} 条</span><div className="pages">
    <button className="page-btn" aria-label="上一页" disabled={page === 1} onClick={() => onChange(page - 1)}>‹</button>
    {Array.from({ length: Math.min(totalPages, 5) }, (_, index) => index + 1).map(item => <button key={item} className={`page-btn ${page === item ? 'active' : ''}`} onClick={() => onChange(item)}>{item}</button>)}
    <button className="page-btn" aria-label="下一页" disabled={page === totalPages} onClick={() => onChange(page + 1)}>›</button>
  </div></div>;
}

export default function AgentTaskConfigPage() {
  const [activeTab, setActiveTab] = useState('input');
  const [overview, setOverview] = useState<AgentTaskOverview | null>(null);
  const [projects, setProjects] = useState<AgentTaskProject[]>([]);
  const [projectPage, setProjectPage] = useState(1);
  const [projectTotal, setProjectTotal] = useState(0);
  const [projectTotalPages, setProjectTotalPages] = useState(1);
  const [projectKeyword, setProjectKeyword] = useState('');
  const [projectScope, setProjectScope] = useState<AgentTaskScopeStatus | ''>('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [reportRootRef, setReportRootRef] = useState('');
  const [allProjects, setAllProjects] = useState<AgentTaskProject[]>([]);
  const [selectionReady, setSelectionReady] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [inputOpen, setInputOpen] = useState(false);
  const [inputData, setInputData] = useState<AgentTaskProjectInput | null>(null);
  const [inputLoading, setInputLoading] = useState(false);
  const [runs, setRuns] = useState<AgentTaskRun[]>([]);
  const [runsPage, setRunsPage] = useState(1);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsTotalPages, setRunsTotalPages] = useState(1);
  const [runLoading, setRunLoading] = useState(false);
  const [runTask, setRunTask] = useState<AgentTaskCode | ''>('');
  const [runProject, setRunProject] = useState<number | ''>('');
  const [runAccount, setRunAccount] = useState('');
  const [runStatus, setRunStatus] = useState<AgentTaskRunStatus | ''>('');
  const [runType, setRunType] = useState<AgentTaskRunType | ''>('');
  const [startedFrom, setStartedFrom] = useState('');
  const [startedTo, setStartedTo] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [runDetail, setRunDetail] = useState<AgentTaskRun | null>(null);
  const [retryTarget, setRetryTarget] = useState<AgentTaskRun | null>(null);
  const [retryRequestId, setRetryRequestId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testProjectId, setTestProjectId] = useState<number | ''>('');
  const [testAccountKey, setTestAccountKey] = useState('');
  const [testTaskCode, setTestTaskCode] = useState<AgentTaskCode>('daily');
  const [testRequestId, setTestRequestId] = useState<string | null>(null);
  const [weeklyAccounts, setWeeklyAccounts] = useState<AgentTaskWeeklyAccount[]>([]);
  const [weeklyAccountsLoading, setWeeklyAccountsLoading] = useState(false);
  const [weeklyPage, setWeeklyPage] = useState(1);
  const [weeklyTotal, setWeeklyTotal] = useState(0);
  const [weeklyTotalPages, setWeeklyTotalPages] = useState(1);
  const [weeklyKeyword, setWeeklyKeyword] = useState('');
  const [testing, setTesting] = useState(false);
  const [controlledNotice, setControlledNotice] = useState(false);
  const projectRequestVersion = useRef(0);
  const overviewRequestVersion = useRef(0);
  const runRequestVersion = useRef(0);
  const inputRequestVersion = useRef(0);
  const runDetailRequestVersion = useRef(0);
  const weeklyRequestVersion = useRef(0);
  const selectionInitialized = useRef(false);
  const reportRootInitialized = useRef(false);
  const reportRootDirty = useRef(false);
  const [runReload, setRunReload] = useState(0);

  const loadOverview = useCallback(async () => {
    const requestVersion = ++overviewRequestVersion.current;
    try {
      const data = await getAgentTaskOverview();
      if (requestVersion === overviewRequestVersion.current) {
        setOverview(data);
        if (!reportRootInitialized.current) {
          reportRootInitialized.current = true;
          if (!reportRootDirty.current) setReportRootRef(data.report_root_ref ?? '');
        }
      }
    } catch (error) { if (requestVersion === overviewRequestVersion.current) message.error((error as Error).message || '加载任务概览失败'); }
  }, []);
  const loadProjects = useCallback(async () => {
    const requestVersion = ++projectRequestVersion.current;
    setProjectsLoading(true);
    try {
      const data = await getAgentTaskProjects({ page: projectPage, page_size: PAGE_SIZE, keyword: projectKeyword || undefined, scope_status: projectScope || undefined });
      if (requestVersion !== projectRequestVersion.current) return;
      setProjects(data.items); setProjectTotal(data.pagination.total); setProjectTotalPages(data.pagination.total_pages);
    } catch (error) { if (requestVersion === projectRequestVersion.current) message.error((error as Error).message || '加载项目范围失败'); }
    finally { if (requestVersion === projectRequestVersion.current) setProjectsLoading(false); }
  }, [projectKeyword, projectPage, projectScope]);
  const loadRuns = useCallback(async () => {
    const requestVersion = ++runRequestVersion.current;
    setRunLoading(true);
    try {
      const data = await getAgentTaskRuns({
        page: runsPage, page_size: PAGE_SIZE, task_code: runTask || undefined, status: runStatus || undefined,
        project_id: runProject || undefined, account_key: runAccount || undefined, run_type: runType || undefined,
        started_from: startedFrom ? `${startedFrom}T00:00:00+08:00` : undefined,
        started_to: startedTo ? `${startedTo}T23:59:59+08:00` : undefined,
      });
      if (requestVersion !== runRequestVersion.current) return;
      setRuns(data.items); setRunsTotal(data.pagination.total); setRunsTotalPages(data.pagination.total_pages);
    } catch (error) { if (requestVersion === runRequestVersion.current) message.error((error as Error).message || '加载运行监控失败'); }
    finally { if (requestVersion === runRequestVersion.current) setRunLoading(false); }
  }, [runAccount, runProject, runStatus, runTask, runType, runsPage, startedFrom, startedTo]);
  const loadAllProjects = useCallback(async () => {
    async function collectAll() {
      const first = await getAgentTaskProjects({ page: 1, page_size: 100 });
      const pages = [first];
      for (let page = 2; page <= first.pagination.total_pages; page += 1) pages.push(await getAgentTaskProjects({ page, page_size: 100 }));
      return pages.flatMap(page => page.items);
    }
    try {
      const all = await collectAll();
      setAllProjects(all);
      if (!selectionInitialized.current) {
        selectionInitialized.current = true;
        setSelectedIds(all.filter(project => project.selected).map(project => project.project_id));
        setSelectionReady(true);
      }
    } catch (error) { message.error((error as Error).message || '加载已保存项目范围失败'); }
  }, []);
  const loadWeeklyAccounts = useCallback(async () => {
    const requestVersion = ++weeklyRequestVersion.current;
    setWeeklyAccountsLoading(true);
    try {
      const data = await getAgentTaskWeeklyAccounts({
        page: weeklyPage,
        page_size: PAGE_SIZE,
        keyword: weeklyKeyword || undefined,
      });
      if (requestVersion !== weeklyRequestVersion.current) return;
      setWeeklyAccounts(data.items);
      setWeeklyTotal(data.pagination.total);
      setWeeklyTotalPages(data.pagination.total_pages);
      setTestAccountKey(current => data.items.some(account => account.account_key === current) ? current : '');
      setTestRequestId(null);
    } catch (error) {
      if (requestVersion === weeklyRequestVersion.current) message.error((error as Error).message || '加载周账号候选失败');
    } finally {
      if (requestVersion === weeklyRequestVersion.current) setWeeklyAccountsLoading(false);
    }
  }, [weeklyKeyword, weeklyPage]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadOverview(); });
    return () => window.clearTimeout(timer);
  }, [loadOverview]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadProjects(); });
    return () => window.clearTimeout(timer);
  }, [loadProjects]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadAllProjects(); });
    return () => window.clearTimeout(timer);
  }, [loadAllProjects]);
  useEffect(() => {
    if (activeTab !== 'monitor') return undefined;
    const timer = window.setTimeout(() => { void loadRuns(); });
    return () => window.clearTimeout(timer);
  }, [activeTab, loadRuns, runReload]);
  useEffect(() => {
    if (!testOpen || testTaskCode !== 'weekly') return undefined;
    const timer = window.setTimeout(() => { void loadWeeklyAccounts(); });
    return () => window.clearTimeout(timer);
  }, [loadWeeklyAccounts, testOpen, testTaskCode]);

  const projectOptions = useMemo(() => allProjects.filter(project => project.missing_required.length === 0).map(project => ({ value: project.project_id, label: [project.project.kol_name, project.project_name, project.project.account_name].filter(Boolean).join(' · ') })), [allProjects]);
  const runProjectOptions = useMemo(() => allProjects.map(project => ({ value: project.project_id, label: [project.project.kol_name, project.project_name, project.project.account_name].filter(Boolean).join(' · ') })), [allProjects]);

  function changeProjectFilter(action: () => void) { action(); setProjectPage(1); }
  function changeRunFilter(action: () => void) { action(); setRunsPage(1); }
  function showTodayCompleted() {
    const today = getShanghaiDate();
    setRunStatus('success'); setStartedFrom(today); setStartedTo(today); setRunsPage(1); setActiveTab('monitor');
  }
  function toggleProject(projectId: number, checked: boolean) {
    setSelectedIds(current => checked ? Array.from(new Set([...current, projectId])) : current.filter(value => value !== projectId));
  }
  async function handleSave() {
    if (!selectionReady) return;
    setSaving(true);
    try {
      const result = await saveAgentTaskConfig({ selected_project_ids: selectedIds, report_root_ref: reportRootRef.trim() || null });
      setSelectedIds(result.selected_project_ids);
      setReportRootRef(result.report_root_ref ?? '');
      reportRootInitialized.current = true;
      reportRootDirty.current = false;
      setOverview(current => current ? { ...current, selected_project_count: result.selected_project_ids.length, report_root_ref: result.report_root_ref, report_root_ref_configured: Boolean(result.report_root_ref), config_updated_by: result.updated_by, config_updated_by_name: result.updated_by_name, config_updated_at: result.updated_at } : current);
      message.success('项目范围与报告根目录已保存，将从下一次固定触发开始生效');
      await Promise.all([loadProjects(), loadOverview()]);
    } catch (error) { message.error((error as Error).message || '保存项目范围失败'); }
    finally { setSaving(false); }
  }
  async function showInput(project: AgentTaskProject) {
    const requestVersion = ++inputRequestVersion.current;
    setInputOpen(true); setInputLoading(true); setInputData(null);
    try {
      const data = await getAgentTaskProjectInput(project.project_id);
      if (requestVersion === inputRequestVersion.current) setInputData(data);
    } catch (error) { if (requestVersion === inputRequestVersion.current) message.error((error as Error).message || '加载项目输入失败'); }
    finally { if (requestVersion === inputRequestVersion.current) setInputLoading(false); }
  }
  async function showRunDetail(run: AgentTaskRun) {
    const requestVersion = ++runDetailRequestVersion.current;
    setDetailOpen(true); setRunDetail(null);
    try {
      const data = await getAgentTaskRun(run.id);
      if (requestVersion === runDetailRequestVersion.current) setRunDetail(data);
    } catch (error) { if (requestVersion === runDetailRequestVersion.current) { message.error((error as Error).message || '加载运行详情失败'); setDetailOpen(false); } }
  }
  async function handleRetry() {
    if (!retryTarget) return;
    const requestId = retryRequestId ?? createRequestId();
    if (!retryRequestId) setRetryRequestId(requestId);
    setRetrying(true);
    try {
      await retryAgentTaskRun(retryTarget.id, { request_id: requestId });
      message.success(isDeliveryOnlyRetry(retryTarget) ? '已创建仅投递重试记录' : '已创建完整重试记录');
      setRetryTarget(null); setRetryRequestId(null);
      setRunStatus(''); setRunsPage(1); setRunReload(value => value + 1);
    }
    catch (error) { message.error((error as Error).message || '重试失败'); }
    finally { setRetrying(false); }
  }
  function openRetry(run: AgentTaskRun) {
    setRetryTarget(run);
    setRetryRequestId(null);
  }
  function closeRetry() {
    setRetryTarget(null);
    setRetryRequestId(null);
  }
  function openControlledTest() {
    setTestOpen(true);
    setTestTaskCode('daily');
    setTestProjectId('');
    setTestAccountKey('');
    setTestRequestId(null);
    setWeeklyPage(1);
    setWeeklyKeyword('');
  }
  function closeControlledTest() {
    setTestOpen(false);
    setTestRequestId(null);
  }
  function changeTestTask(taskCode: AgentTaskCode) {
    setTestTaskCode(taskCode);
    setTestProjectId('');
    setTestAccountKey('');
    setTestRequestId(null);
    setWeeklyPage(1);
    setWeeklyKeyword('');
  }
  async function handleControlledTest() {
    if (testTaskCode === 'daily' && !testProjectId) { message.error('请选择一个必要配置已通过的项目'); return; }
    if (testTaskCode === 'weekly' && !testAccountKey) { message.error('请选择一个周账号候选'); return; }
    const requestId = testRequestId ?? createRequestId();
    if (!testRequestId) setTestRequestId(requestId);
    setTesting(true);
    try {
      await createAgentTaskTestRun(testTaskCode === 'daily'
        ? { task_code: 'daily', project_id: testProjectId as number, request_id: requestId }
        : { task_code: 'weekly', account_key: testAccountKey, request_id: requestId });
      closeControlledTest(); setControlledNotice(true); message.success('已创建隔离受控测试记录');
      setActiveTab('monitor'); setRunsPage(1); setRunReload(value => value + 1);
    } catch (error) { message.error((error as Error).message || '发起受控测试失败'); }
    finally { setTesting(false); }
  }

  const taskAndInput = <>
    <div className="agent-task-card">
      <div className="agent-task-card-head"><div><h2 className="card-title">固定任务</h2><p>自动任务尚未启用；启用后将按固定北京时间和已保存范围运行。</p></div></div>
      <div className="agent-task-definition-grid">
        {overview?.tasks.map(task => <div className="agent-task-definition" key={task.task_code}>
          <div className="agent-task-definition-kicker">内容分析 · 固定任务</div>
          <h3>{task.name}</h3>
          <dl><div><dt>固定触发</dt><dd>{task.schedule}（北京时间）</dd></div><div><dt>分析窗口</dt><dd>最近 {task.window_days} 个完整自然日</dd></div><div><dt>最近正式运行</dt><dd>{formatTime(task.latest_formal_run?.triggered_at, true)}</dd></div><div><dt>下次预计运行</dt><dd>{formatTime(task.next_fixed_run, true)}</dd></div></dl>
        </div>)}
      </div>
    </div>
    <div className="card agent-task-project-card">
      <div className="card-header"><div><h2 className="card-title">持续项目范围与报告位置</h2><p className="agent-task-muted">项目范围与内容分析飞书报告根目录一起保存；根目录为智能体级共享配置，持续生效，不按项目配置。</p></div><button className="btn btn-primary" onClick={() => void handleSave()} disabled={saving || !selectionReady}>{saving ? '保存中…' : selectionReady ? '保存项目范围与报告根目录' : '正在加载已保存范围…'}</button></div>
      <div className="filter-bar">
        <label className="agent-task-field">内容分析飞书报告根目录<input className="filter-input" aria-label="内容分析飞书报告根目录" value={reportRootRef} onChange={event => { reportRootDirty.current = true; setReportRootRef(event.target.value); }} placeholder="请填写并保存报告根目录" /></label>
        <span className={overview && !overview.report_root_ref_configured ? 'agent-task-reason' : 'agent-task-muted'}>{!overview ? '正在读取已保存配置…' : overview.report_root_ref_configured ? '已配置：共享、持续生效、不按项目配置；受控测试不可临时覆盖。' : '报告根目录未配置：自动和测试任务只记录为未运行，不调用内容分析执行器。'}</span>
      </div>
      <div className="filter-bar">
        <input className="filter-input" aria-label="搜索项目" placeholder="搜索项目或红人" value={projectKeyword} onChange={event => changeProjectFilter(() => setProjectKeyword(event.target.value))} />
        <select className="filter-select" aria-label="项目范围状态" value={projectScope} onChange={event => changeProjectFilter(() => setProjectScope(event.target.value as AgentTaskScopeStatus | ''))}>
          <option value="">全部范围状态</option><option value="selected_ready">已选可运行</option><option value="selected_missing">已选配置缺失</option><option value="unselected">未选择</option>
        </select><span className="filter-count">已选择 {selectedIds.length} 个 · 共 {projectTotal} 个</span>
      </div>
      <div className="agent-task-table-scroll">{projectsLoading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : projects.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无入驻成功项目</div></div> : <table className="ant-table"><thead><tr><th>选择</th><th>项目</th><th>对标账号</th><th>内容数据</th><th>项目上下文</th><th>生效状态</th><th className="col-actions">操作</th></tr></thead><tbody>
        {projects.map(project => <tr key={project.project_id}><td><input aria-label={`选择${project.project_name}`} type="checkbox" disabled={!selectionReady} checked={selectedIds.includes(project.project_id)} onChange={event => toggleProject(project.project_id, event.target.checked)} /></td><td><strong>{project.project_name}</strong><div className="agent-task-secondary">{project.project.kol_name}{project.project.account_name ? ` · ${project.project.account_name}` : ''}</div></td><td><div>{project.content_benchmark_valid_count}/{project.content_benchmark_total} 可识别</div><div className="agent-task-secondary">{project.content_benchmark_relation_status === 'ready' ? '关联已就绪' : '关联待补齐'}</div></td><td><span className="badge badge-success">已接入</span><div className="agent-task-secondary">飞书内容表在运行时完整校验</div></td><td>{project.missing_required.length > 0 ? <><span className="badge badge-danger">必要配置缺失</span><div className="agent-task-reason">{project.missing_required.map(formatMissingReason).join('、')}</div></> : project.project_context_status === 'complete' ? <span className="badge badge-success">完整</span> : <><span className="badge badge-warning">部分缺失</span>{project.optional_context_missing.length > 0 && <div className="agent-task-secondary">输入受限：{project.optional_context_missing.map(formatMissingReason).join('、')}</div>}</>}</td><td><span className={`badge ${SCOPE_CLASS[project.scope_status]}`}>{SCOPE_LABELS[project.scope_status]}</span>{project.missing_required.map(reason => <div className="agent-task-reason" key={reason}>{formatMissingReason(reason)}</div>)}</td><td className="col-actions"><button className="btn btn-ghost btn-sm" aria-label={`查看${project.project_name}输入`} onClick={() => void showInput(project)}>查看输入</button></td></tr>)}
      </tbody></table>}</div>
      <Pagination page={projectPage} total={projectTotal} totalPages={projectTotalPages} onChange={setProjectPage} />
      <div className="agent-task-save-meta">最近保存：{overview?.config_updated_by_name || '尚未保存'} · {formatTime(overview?.config_updated_at)}</div>
    </div>
  </>;

  const monitor = <div className="card agent-task-monitor-card">
    <div className="card-header"><div><h2 className="card-title">内容分析运行监控</h2><p className="agent-task-muted">同时展示项目、账号与周批收尾实例；内部结果和飞书投递按四层状态追踪。</p></div><button className="btn btn-primary" onClick={openControlledTest}>发起受控测试</button></div>
    {controlledNotice && <div className="agent-task-controlled-notice">受控测试可保存带测试隔离标识的平台结构化结果，并写入测试子目录；不写正式业务投影或正式目录。</div>}
    <div className="filter-bar agent-task-run-filters">
      <select className="filter-select" aria-label="任务类型" value={runTask} onChange={event => changeRunFilter(() => setRunTask(event.target.value as AgentTaskCode | ''))}><option value="">全部任务</option><option value="daily">每日项目对标内容分析</option><option value="weekly">账号人设内容基准更新</option></select>
      <select className="filter-select" aria-label="项目筛选" value={runProject} onChange={event => changeRunFilter(() => setRunProject(event.target.value ? Number(event.target.value) : ''))}><option value="">全部项目</option>{runProjectOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
      <input className="filter-input" aria-label="账号筛选" placeholder="输入完整账号标识" value={runAccount} onChange={event => changeRunFilter(() => setRunAccount(event.target.value))} />
      <select className="filter-select" aria-label="运行状态" value={runStatus} onChange={event => changeRunFilter(() => setRunStatus(event.target.value as AgentTaskRunStatus | ''))}><option value="">全部状态</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <select className="filter-select" aria-label="运行类型" value={runType} onChange={event => changeRunFilter(() => setRunType(event.target.value as AgentTaskRunType | ''))}><option value="">全部类型</option>{Object.entries(RUN_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <label className="agent-task-date">开始<input aria-label="开始日期" type="date" value={startedFrom} onChange={event => changeRunFilter(() => setStartedFrom(event.target.value))} /></label><label className="agent-task-date">结束<input aria-label="结束日期" type="date" value={startedTo} onChange={event => changeRunFilter(() => setStartedTo(event.target.value))} /></label>
    </div>
    <div className="agent-task-table-scroll">{runLoading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : runs.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无内容分析运行记录</div></div> : <table className="ant-table"><thead><tr><th>任务 / 执行对象</th><th>业务日期 / 窗口</th><th>类型</th><th>触发 / 12 小时截止</th><th>状态</th><th>耗时</th><th>四层结果 / 说明</th><th className="col-actions">操作</th></tr></thead><tbody>{runs.map(run => <tr key={run.id}><td><strong>{run.task.name}</strong><div className="agent-task-secondary">{executionLabel(run)}</div>{run.execution.object_type === 'account' && <div className="agent-task-secondary">关联项目 {run.execution.project_ids.map(value => `#${value}`).join('、')}</div>}<div className="agent-task-secondary">{run.task_no}</div></td><td>{run.business_date}<div className="agent-task-secondary">{formatTime(run.window_start, true)} 至 {formatTime(run.window_end, true)}</div></td><td><span className="badge badge-info">{RUN_TYPE_LABELS[run.run_type]}</span>{run.controlled_test && <div className="agent-task-secondary">隔离测试</div>}</td><td>{formatTime(run.triggered_at, true)}<div className="agent-task-secondary">截止：{formatTime(run.deadline_at, true)}</div></td><td><StatusBadge status={run.status} />{run.failure_stage && <div className="agent-task-reason">失败阶段：{FAILURE_STAGE_LABELS[run.failure_stage]}</div>}</td><td>{formatDuration(run.status === 'running' ? run.elapsed_ms : run.duration_ms)}</td><td><ResultSummary run={run} />{run.input_limited && <div className="agent-task-secondary">输入受限：{run.input_limited_reasons.map(formatMissingReason).join('、')}</div>}{(run.error_message || run.required_missing_reasons.length > 0) && <div className="agent-task-reason">{run.error_message || run.required_missing_reasons.map(formatMissingReason).join('、')}</div>}</td><td className="col-actions"><button className="btn btn-ghost btn-sm" aria-label={`查看 ${run.task_no} 详情`} onClick={() => void showRunDetail(run)}>详情</button>{run.status === 'failed' && <button className="btn btn-danger-ghost btn-sm" aria-label={`${isDeliveryOnlyRetry(run) ? '仅重试投递' : '完整重试'} ${run.task_no}`} onClick={() => openRetry(run)}>{isDeliveryOnlyRetry(run) ? '仅重试投递' : '完整重试'}</button>}</td></tr>)}</tbody></table>}</div>
    <Pagination page={runsPage} total={runsTotal} totalPages={runsTotalPages} onChange={setRunsPage} />
  </div>;

  return <>
    <div className="page-header"><div><h1 className="page-title">智能体任务配置</h1><p className="page-desc">管理员配置内容分析项目范围，查看隔离的输入与执行状态。</p></div></div>
    <section className="agent-task-identity" aria-label="当前智能体"><span>当前智能体</span><strong>内容分析（首期）</strong><small>各智能体独立保存范围与运行记录</small></section>
    <div className="agent-task-stage-note">自动任务由部署开关控制，启用后按固定北京时间和已保存范围运行。</div>
    <div className="agent-task-summary-grid">
      <div className="stat-card"><div className="s-label">已选项目</div><div className="s-value">{overview?.selected_project_count ?? '—'}</div><div className="s-sub">持续生效的内容分析范围</div></div>
      <button className="stat-card agent-task-summary-action" onClick={showTodayCompleted}><div className="s-label">今日已完成</div><div className="s-value">{overview?.status_summary.today_completed ?? '—'}</div><div className="s-sub">点击查看运行记录</div></button>
      <button className="stat-card agent-task-summary-action" onClick={() => { setActiveTab('monitor'); changeRunFilter(() => setRunStatus('running')); }}><div className="s-label">当前运行中</div><div className="s-value">{overview?.status_summary.current_running ?? '—'}</div><div className="s-sub">项目或账号隔离执行</div></button>
      <button className="stat-card agent-task-summary-action" onClick={() => { setActiveTab('monitor'); changeRunFilter(() => setRunStatus('failed')); }}><div className="s-label">近 7 日失败</div><div className="s-value">{overview?.status_summary.failed_last_7_days ?? '—'}</div><div className="s-sub">含 12 小时超时收敛</div></button>
    </div>
    <Tabs activeKey={activeTab} onChange={setActiveTab} items={[{ key: 'input', label: '任务与输入', children: taskAndInput }, { key: 'monitor', label: '运行监控', children: monitor }]} />

    <Drawer title={`${inputData?.project_name || '项目'} · 输入上下文`} open={inputOpen} onClose={() => setInputOpen(false)} width={680} destroyOnClose>
      {inputLoading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : inputData && <><div className="agent-task-drawer-note"><span className="badge badge-gray">只读</span> 数据只用于当前项目的内容分析隔离运行，不可在此编辑。</div>{inputData.modules.map(module => <div className="agent-task-input-module" key={module.key}><div><strong>{module.label}</strong><span className={`badge ${module.status === 'ready' ? 'badge-success' : 'badge-warning'}`}>{module.status === 'ready' ? '已就绪' : '缺失'}</span></div><dl><div><dt>来源</dt><dd>{module.source}</dd></div><div><dt>更新时间</dt><dd>{formatTime(module.updated_at, true)}</dd></div><div><dt>只读内容</dt><dd><pre className="agent-task-input-value">{formatInputValue(module.value)}</pre></dd></div>{module.missing_reason && <div><dt>缺失原因</dt><dd>{formatMissingReason(module.missing_reason)}{module.missing_reasons.length ? `：${module.missing_reasons.map(formatMissingReason).join('、')}` : ''}</dd></div>}</dl></div>)}<div className="agent-task-drawer-result">正式结果位置：平台结构化结果与飞书文档</div></>}
    </Drawer>
    <Drawer title={`${runDetail?.task_no || '运行'} · 执行详情`} open={detailOpen} onClose={() => setDetailOpen(false)} width={680} destroyOnClose>
      {!runDetail ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div> : <><div className="agent-task-detail-grid"><div><span>任务</span><strong>{runDetail.task.name}</strong></div><div><span>执行对象</span><strong>{executionLabel(runDetail)}</strong>{runDetail.execution.object_type === 'account' && <small>关联项目 {runDetail.execution.project_ids.map(value => `#${value}`).join('、')}</small>}</div><div><span>状态</span><StatusBadge status={runDetail.status} /></div><div><span>12 小时截止</span><strong>{formatTime(runDetail.deadline_at, true)}</strong></div><div><span>前序重试</span><strong>{runDetail.retry_of_task_id ? `#${runDetail.retry_of_task_id}` : '无'}</strong></div><div><span>后续重试</span><strong>{runDetail.retried_by_task_ids.length ? runDetail.retried_by_task_ids.map(value => `#${value}`).join('、') : '无'}</strong></div></div><div className="agent-task-drawer-result"><ResultSummary run={runDetail} includeFailureStage /></div>{runDetail.controlled_test && <div className="agent-task-controlled-notice">受控测试可保存带测试隔离标识的平台结构化结果，并写入测试子目录；不写正式业务投影或正式目录。</div>}<div className="log-panel">{runDetail.logs?.length ? runDetail.logs.map(log => <div className="log-step" key={log.id}><div className={`step-dot ${log.status === 'success' ? 'success' : log.status === 'failed' ? 'failed' : log.status === 'running' ? 'processing' : 'pending'}`} /><div><div className="step-name">{log.step_name}</div>{log.message && <div className="step-msg">{log.message}</div>}</div><div className="step-time">{formatTime(log.created_at, true)}</div></div>) : <div className="empty-state"><div className="empty-state-text">暂无日志</div></div>}</div></>}
    </Drawer>
    <Modal title="确认重试" open={Boolean(retryTarget)} onCancel={closeRetry} onOk={() => void handleRetry()} okText={isDeliveryOnlyRetry(retryTarget) ? '确认仅重试投递' : '确认完整重试'} cancelText="取消" confirmLoading={retrying}><p>{isDeliveryOnlyRetry(retryTarget) ? '本次仅重试投递，不重复分析；继续复用已有内部结果。' : '本次将执行完整重试，继承原业务日期和分析窗口，并重新计算 12 小时截止时间。'}</p></Modal>
    <Modal title="发起受控测试" open={testOpen} onCancel={closeControlledTest} onOk={() => void handleControlledTest()} okText="开始受控测试" cancelText="取消" confirmLoading={testing}>
      <p className="agent-task-controlled-notice">测试可保存带测试隔离标识的平台结构化结果，并写入测试子目录；不写正式业务投影或正式目录。</p>
      {!overview?.report_root_ref_configured && <p className="agent-task-reason">请先保存内容分析飞书报告根目录；未配置时本次测试只会记录为未运行。</p>}
      <label className="agent-task-field">固定任务<select aria-label="选择固定任务" value={testTaskCode} onChange={event => changeTestTask(event.target.value as AgentTaskCode)}><option value="daily">每日项目对标内容分析</option><option value="weekly">账号人设内容基准更新</option></select></label>
      {testTaskCode === 'daily' ? <label className="agent-task-field">选择项目<select aria-label="选择项目" value={testProjectId} onChange={event => { setTestProjectId(event.target.value ? Number(event.target.value) : ''); setTestRequestId(null); }}><option value="">请选择必要配置通过的项目</option>{projectOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label> : <>
        <label className="agent-task-field">搜索周账号<input className="filter-input" aria-label="搜索周账号" value={weeklyKeyword} onChange={event => { setWeeklyKeyword(event.target.value); setWeeklyPage(1); setTestAccountKey(''); setTestRequestId(null); }} /></label>
        <label className="agent-task-field">选择周账号<select aria-label="选择周账号" value={testAccountKey} disabled={weeklyAccountsLoading} onChange={event => { setTestAccountKey(event.target.value); setTestRequestId(null); }}><option value="">{weeklyAccountsLoading ? '加载中...' : '请选择可测试账号'}</option>{weeklyAccounts.map(account => <option key={account.account_key} value={account.account_key}>{weeklyAccountLabel(account)} · 项目 {account.project_ids.map(value => `#${value}`).join('、')}</option>)}</select></label>
        <Pagination page={weeklyPage} total={weeklyTotal} totalPages={weeklyTotalPages} onChange={value => { setWeeklyPage(value); setTestAccountKey(''); setTestRequestId(null); }} />
      </>}
    </Modal>
  </>;
}
