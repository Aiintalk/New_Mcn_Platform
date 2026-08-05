/**
 * 评测监控（admin，Phase 5 可观测仪表盘）
 *
 * 路由：/evaluation/observability（admin-only）
 * 数据：
 *   GET /api/admin/evaluation/queue-stats   → 队列健康度（堵没堵一眼可见）
 *   GET /api/admin/evaluation/runs/{id}/jobs → 单 run 的 job 明细（排查卡住/失败）
 */
import { useCallback, useEffect, useState } from 'react';
import { App, Button, Input, Skeleton, Table, Tag } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import { getQueueStats, getRunJobs } from '../api';
import type { EvalQueueStats, EvalRunJob } from '../types';
import { PageHeader } from '../components/primitives';

const JOB_TAG: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  failed: 'error',
  cancelled: 'warning',
};

export default function ObservabilityPage() {
  const { message } = App.useApp();
  const [stats, setStats] = useState<EvalQueueStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [runIdInput, setRunIdInput] = useState('');
  const [jobs, setJobs] = useState<EvalRunJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await getQueueStats());
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const loadJobs = async () => {
    const rid = Number(runIdInput);
    if (!rid) {
      message.warning('请输入 run id');
      return;
    }
    setJobsLoading(true);
    try {
      setJobs(await getRunJobs(rid));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载失败');
      setJobs([]);
    } finally {
      setJobsLoading(false);
    }
  };

  const jobColumns: ColumnsType<EvalRunJob> = [
    {
      title: 'job id', dataIndex: 'id', width: 80,
      render: (v) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{v}</span>,
    },
    { title: 'test_case', dataIndex: 'test_case_id', width: 100 },
    {
      title: '状态', dataIndex: 'status', width: 110,
      render: (v: string) => <Tag color={JOB_TAG[v] ?? 'default'}>{v}</Tag>,
    },
    {
      title: 'attempts', width: 100,
      render: (_, r) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.attempts}/{r.max_attempts}</span>,
    },
    {
      title: 'last_error', dataIndex: 'last_error',
      render: (v: string | null) =>
        v ? <span style={{ color: 'var(--danger)', fontSize: 12 }}>{v}</span> : <span className="text-muted">—</span>,
    },
  ];

  const oldestLabel =
    stats?.oldest_pending_secs !== null && stats?.oldest_pending_secs !== undefined
      ? `${stats.oldest_pending_secs}s`
      : '—';

  return (
    <div className="eval-page">
      <PageHeader
        title="评测监控"
        description="异步运行队列健康度 + 单 run job 明细排查（admin）。pending 堆积 + 最老等待大 = 队列堵塞信号。"
        actions={
          <Button icon={<ReloadOutlined />} onClick={() => void loadStats()}>
            刷新
          </Button>
        }
      />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">待消费 pending</div>
          <div className="stat-value" style={{ color: stats && stats.pending > 0 ? 'var(--warning)' : undefined }}>
            {loading && !stats ? '…' : stats?.pending ?? '—'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">在跑 running</div>
          <div className="stat-value">{stats?.running ?? '—'}</div>
        </div>
        <div className="stat-card accent">
          <div className="stat-label">失败死信</div>
          <div className="stat-value" style={{ color: stats && stats.failed_dead_letter > 0 ? 'var(--danger)' : undefined }}>
            {stats?.failed_dead_letter ?? '—'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">已完成 done</div>
          <div className="stat-value">{stats?.done ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">已取消</div>
          <div className="stat-value">{stats?.cancelled ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">活跃 run</div>
          <div className="stat-value">{stats?.runs_active ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">最老 pending 等待</div>
          <div className="stat-value" style={{ fontSize: 20 }}>{oldestLabel}</div>
        </div>
      </div>

      <div className="card mb-5">
        <div className="card-header">
          <h3>排查单 run 的 job 明细</h3>
          <span className="ch-sub">输入 run id，看每个 case-job 的状态 / 重试次数 / 失败原因</span>
        </div>
        <div className="card-body flush">
          <div style={{ display: 'flex', gap: 8, padding: 'var(--sp-4) var(--sp-5)' }}>
            <Input
              placeholder="run id，如 16"
              value={runIdInput}
              onChange={(e) => setRunIdInput(e.target.value)}
              style={{ width: 200 }}
              onPressEnter={() => void loadJobs()}
            />
            <Button type="primary" icon={<SearchOutlined />} loading={jobsLoading} onClick={() => void loadJobs()}>
              查看 jobs
            </Button>
          </div>
          {jobsLoading ? (
            <div style={{ padding: 'var(--sp-5)' }}>
              <Skeleton active paragraph={{ rows: 4 }} />
            </div>
          ) : (
            <Table<EvalRunJob>
              rowKey="id"
              columns={jobColumns}
              dataSource={jobs}
              size="middle"
              pagination={{ pageSize: 20 }}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '输入 run id 后点「查看 jobs」' }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
