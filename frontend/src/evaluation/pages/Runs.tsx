/**
 * 运行列表（设计稿 runs.html）
 *
 * 列表 + 子 tab 过滤 + 触发抽屉。
 * 数据接口：GET /api/operator/evaluation/runs（Phase 4 起接入，替代早期 localStorage 兜底）。
 * 拉最近 50 条（后端 _PAGE_SIZE_ALLOWED 最大值，不被 clamp）；tab 过滤 + 状态卡基于当前列表客户端计算。
 * 待决：run 历史超 50 条时改服务端分页（见 spec §1）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Button, Drawer, Form, Input, Radio, Select, Skeleton, Table, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import { listRuns, listVersionsOperator, triggerRun } from '../api';
import type { EvalRun, EvalRunStatus, EvalTriggerType, EvalVersion } from '../types';
import {
  Callout,
  PageHeader,
  ProgressBar,
  RunStatusBadge,
  TriggerBadge,
  formatDuration,
  formatShortTime,
} from '../components/primitives';

interface FilterTab {
  key: EvalRunStatus | 'all' | 'in_progress';
  label: string;
}

const FILTER_TABS: FilterTab[] = [
  { key: 'all', label: '全部' },
  // 进行中 = pending（排队）+ running（执行中）：新触发的 run 先进 arq 队列（pending），
  // 只筛 running 会让刚建的 run "消失"，误导用户以为创建失败
  { key: 'in_progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
];

export default function RunsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [activeTab, setActiveTab] = useState<EvalRunStatus | 'all' | 'in_progress'>('all');
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [versions, setVersions] = useState<EvalVersion[]>([]);

  const [form] = Form.useForm<{
    name: string;
    version_id: number;
    scope: 'all' | 'tags';
    tags: string[];
  }>();

  const [total, setTotal] = useState(0);

  // 从后端 GET /runs 拉列表（Phase 4：替代 localStorage 兜底，跨设备可见）
  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRuns({ page: 1, page_size: 50 });
      setRuns(data.items);
      setTotal(data.pagination.total);
    } catch {
      setRuns([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  // 加载版本列表（抽屉用）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listVersionsOperator();
        if (!cancelled) setVersions(data);
      } catch {
        // 静默
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredRuns = useMemo(() => {
    if (activeTab === 'all') return runs;
    // 进行中 = 排队中（pending）+ 执行中（running）
    if (activeTab === 'in_progress') return runs.filter((r) => r.status === 'pending' || r.status === 'running');
    return runs.filter((r) => r.status === activeTab);
  }, [runs, activeTab]);

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: runs.length, running: 0, completed: 0, failed: 0, pending: 0, partial: 0 };
    runs.forEach((r) => {
      map[r.status] = (map[r.status] ?? 0) + 1;
    });
    return map;
  }, [runs]);

  const handleTrigger = async () => {
    try {
      const values = await form!.validateFields();
      setSaving(true);
      const run = await triggerRun({
        version_id: values.version_id,
        name: values.name,
        filter_tags: values.scope === 'tags' ? values.tags : [],
        trigger_type: 'manual',
      });
      message.success('运行已启动，可到详情页查看进度');
      setTriggerOpen(false);
      void loadRuns();   // 刷新列表（不阻塞跳详情）
      navigate(`/evaluation/runs/${run.id}`);
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<EvalRun> = [
    {
      title: '运行名',
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r) => (
        <a
          onClick={() => navigate(`/evaluation/runs/${r.id}`)}
          style={{ color: 'var(--gray-900)', fontWeight: 500 }}
        >
          {v || `Run #${r.id}`}
        </a>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version_id',
      key: 'version_id',
      width: 80,
      render: (v) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>v#{v}</span>,
    },
    {
      title: '策略',
      key: 'strategy',
      width: 100,
      render: () => <Tag color="default">default</Tag>,
    },
    {
      title: '触发',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      width: 80,
      render: (v: EvalTriggerType) => <TriggerBadge trigger={v} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (v: EvalRunStatus) => <RunStatusBadge status={v} />,
    },
    {
      title: '进度',
      key: 'progress',
      width: 180,
      render: (_, r) => {
        const variant = r.status === 'completed' ? 'success' : r.status === 'failed' ? 'danger' : r.status === 'running' ? 'warn' : 'brand';
        return <ProgressBar completed={r.completed_cases} total={r.total_cases} variant={variant} />;
      },
    },
    {
      title: '耗时',
      key: 'duration',
      width: 80,
      render: (_, r) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatDuration(r.started_at, r.finished_at)}</span>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 130,
      render: (v) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatShortTime(v)}</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      align: 'right',
      render: (_, r) => (
        <Button size="small" type="link" onClick={() => navigate(`/evaluation/runs/${r.id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div className="eval-page">
      <PageHeader
        title="运行管理"
        description="用某个版本跑一批测试样本，产出仿写结果与多维评分。状态机：pending → running → completed / failed。"
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void loadRuns()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setTriggerOpen(true)}>
              新建运行
            </Button>
          </>
        }
      />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">运行总数</div>
          <div className="stat-value">{total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">已完成</div>
          <div className="stat-value">{counts.completed}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">进行中</div>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {counts.pending + counts.running}
          </div>
        </div>
        <div className="stat-card accent">
          <div className="stat-label">失败</div>
          <div className="stat-value" style={{ color: counts.failed > 0 ? 'var(--danger)' : undefined }}>
            {counts.failed}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-body flush">
          <div style={{ padding: 'var(--sp-4) var(--sp-5) 0' }}>
            <div className="sub-tabs">
              {FILTER_TABS.map((t) => (
                <button
                  key={t.key}
                  className={`sub-tab ${activeTab === t.key ? 'active' : ''}`}
                  onClick={() => setActiveTab(t.key)}
                  type="button"
                >
                  {t.label} <span className="count">{counts[t.key] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div style={{ padding: 'var(--sp-5)' }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : (
            <Table<EvalRun>
              rowKey="id"
              columns={columns}
              dataSource={filteredRuns}
              size="middle"
              pagination={{ pageSize: 20 }}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '暂无运行记录，点击右上角「新建运行」触发一次回归' }}
            />
          )}
        </div>
      </div>

      <Drawer
        title="触发运行"
        placement="right"
        width={520}
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleTrigger()}>
            开始运行
          </Button>
        }
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ name: '', scope: 'all', tags: [] }}
        >
          <Form.Item
            name="name"
            label="运行名"
            rules={[{ required: true, message: '请输入运行名' }]}
          >
            <Input placeholder="例：v1.3 核心集手动回归" />
          </Form.Item>

          <Form.Item
            name="version_id"
            label="被测版本"
            rules={[{ required: true, message: '请选择版本' }]}
          >
            <Select
              placeholder="选择一个 active 版本"
              options={versions.map((v) => ({
                label: `${v.name}${v.is_active ? '（启用）' : ''}`,
                value: v.id,
              }))}
              notFoundContent="暂无 active 版本，请先在管理端创建"
            />
          </Form.Item>

          <Form.Item label="评测策略">
            <Input
              readOnly
              value="default（一期自动绑定，无需传 strategy_id）"
              style={{ background: 'var(--gray-50)', fontFamily: 'var(--font-mono)' }}
            />
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              eval_runs.strategy_id 恒指向 default 策略；per-KOL / 业务策略二期开放。
            </div>
          </Form.Item>

          <Form.Item name="scope" label="样本范围">
            <Radio.Group>
              <Radio value="all">全部启用样本</Radio>
              <Radio value="tags">按标签筛选</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prev, next) => prev.scope !== next.scope}
          >
            {({ getFieldValue }) =>
              getFieldValue('scope') === 'tags' ? (
                <Form.Item name="tags" label="标签筛选">
                  <Select
                    mode="tags"
                    placeholder="输入标签后回车，多个标签为交集"
                    tokenSeparators={[',']}
                  />
                </Form.Item>
              ) : null
            }
          </Form.Item>

          <Callout variant="warn" icon="!">
            一期后台任务使用 BackgroundTask，进程重启会丢失未完成运行，中断后需重新触发。
          </Callout>
        </Form>
      </Drawer>
    </div>
  );
}
