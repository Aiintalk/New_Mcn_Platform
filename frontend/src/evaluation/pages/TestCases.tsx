/**
 * 测试集列表（设计稿 test-cases.html）
 *
 * 表格 + 筛选 + 分页 + 新建/编辑抽屉。
 * 数据接口：GET /api/operator/evaluation/test-cases（分页）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Button, Input, Select, Skeleton, Table, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import { listTestCases } from '../api';
import type { EvalTestCase, EvalTestCaseListParams } from '../types';
import {
  Callout,
  PageHeader,
  ScoreChip,
  TagBadge,
  formatShortTime,
} from '../components/primitives';

const PAGE_SIZE_OPTIONS = ['10', '20', '50'];

// 占位统计（设计稿保留）：等后端 /stats 聚合接口落地后替换
interface TestCasesStats {
  total: number;
  active: number;
  tagCount: number;
  lastAvg: number | null;
}

export default function TestCasesPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<EvalTestCase[]>([]);
  const [params, setParams] = useState<EvalTestCaseListParams>({ page: 1, page_size: 20 });
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTestCases(params);
      setRows(data.items);
      setTotal(data.pagination.total);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  // 标签筛选走服务端（后端 /test-cases 原生支持 tag 参数）；切换时重置回第 1 页
  const handleTagFilterChange = useCallback(
    (tag: string | undefined) => {
      setTagFilter(tag);
      setParams((prev) => ({ ...prev, page: 1, tag }));
    },
    [],
  );

  // 客户端二次过滤（搜索 + 状态；标签已由服务端过滤）
  const filteredRows = useMemo(() => {
    let list = rows;
    if (search.trim()) {
      const kw = search.trim().toLowerCase();
      list = list.filter(
        (r) =>
          r.name.toLowerCase().includes(kw) ||
          (r.description ?? '').toLowerCase().includes(kw),
      );
    }
    if (statusFilter === 'active') list = list.filter((r) => r.is_active);
    if (statusFilter === 'inactive') list = list.filter((r) => !r.is_active);
    return list;
  }, [rows, search, statusFilter]);

  // 提取标签选项（用于筛选下拉）。
  // 筛选中冻结选项（否则按 tag 过滤后当前页只剩该 tag，其他选项会消失），清空后重算
  const allTagOptions = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((r) => r.tags.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [rows]);
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  useEffect(() => {
    if (!tagFilter) setTagOptions(allTagOptions);
  }, [allTagOptions, tagFilter]);

  // 占位统计（来自当前页 + 全量 total）
  const stats: TestCasesStats = useMemo(() => {
    const activeCount = rows.filter((r) => r.is_active).length;
    return {
      total,
      active: activeCount,
      tagCount: tagOptions.length,
      lastAvg: null, // 等聚合接口
    };
  }, [rows, total, tagOptions]);

  const columns: ColumnsType<EvalTestCase> = [
    {
      title: '样本名称',
      dataIndex: 'name',
      key: 'name',
      render: (_, r) => (
        <a
          onClick={() => navigate(`/evaluation/test-cases/${r.id}/edit`)}
          style={{ color: 'var(--gray-900)', fontWeight: 500 }}
        >
          {r.name}
          {r.description ? (
            <div style={{ fontSize: 11, color: 'var(--gray-500)', marginTop: 2 }}>
              {r.description}
            </div>
          ) : null}
        </a>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {tags.length === 0 ? (
            <span style={{ color: 'var(--gray-400)', fontSize: 12 }}>—</span>
          ) : (
            tags.map((t) => <TagBadge key={t} tag={t} />)
          )}
        </div>
      ),
    },
    {
      title: '最近评分',
      key: 'score',
      render: () => <ScoreChip score={null} />,
      width: 110,
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      key: 'created_by',
      width: 90,
      render: (v) => (v ? `#${v}` : '—'),
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (v: boolean) =>
        v ? (
          <Tag color="success" style={{ margin: 0 }}>
            启用
          </Tag>
        ) : (
          <Tag color="default" style={{ margin: 0 }}>
            停用
          </Tag>
        ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 130,
      render: (v) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatShortTime(v)}</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'right',
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
          <Button size="small" type="link" onClick={() => navigate(`/evaluation/test-cases/${r.id}/edit`)}>
            编辑
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="eval-page">
      <PageHeader
        title="测试集"
        titleTag="tool: qianchuan-writer"
        description="持续维护的固定输入样本资产。每个样本带标签分类，便于按场景筛选与运行；样本退役用软删，参与回归由开关控制。"
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/evaluation/test-cases/new')}>
              新建样本
            </Button>
          </>
        }
      />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">样本总数</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">当前页启用</div>
          <div className="stat-value">
            {stats.active}
            <span className="unit">/{rows.length}</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">标签分类</div>
          <div className="stat-value">{stats.tagCount}</div>
        </div>
        <div className="stat-card accent">
          <div className="stat-label">最近一次运行平均分</div>
          <div className="stat-value">{stats.lastAvg !== null ? stats.lastAvg.toFixed(1) : '—'}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-body flush">
          <div style={{ padding: 'var(--sp-4) var(--sp-5) 0' }}>
            <div className="filter-bar">
              <Input
                className="filter-input"
                style={{ minWidth: 220 }}
                placeholder="🔍 搜索样本名称 / 描述"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                prefix={<SearchOutlined style={{ color: 'var(--gray-400)' }} />}
                allowClear
              />
              <Select
                className="filter-select"
                style={{ minWidth: 160 }}
                placeholder="全部标签"
                allowClear
                value={tagFilter}
                onChange={handleTagFilterChange}
                options={tagOptions.map((t) => ({ label: t, value: t }))}
              />
              <Select
                className="filter-select"
                style={{ minWidth: 140 }}
                value={statusFilter}
                onChange={setStatusFilter}
                options={[
                  { label: '全部状态', value: 'all' },
                  { label: '启用', value: 'active' },
                  { label: '已停用', value: 'inactive' },
                ]}
              />
              <span className="filter-count">共 {total} 条</span>
              <span className="grow" />
            </div>
          </div>

          {loading ? (
            <div style={{ padding: 'var(--sp-5)' }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : (
            <Table<EvalTestCase>
              rowKey="id"
              columns={columns}
              dataSource={filteredRows}
              size="middle"
              pagination={{
                current: params.page,
                pageSize: params.page_size,
                total,
                showSizeChanger: true,
                pageSizeOptions: PAGE_SIZE_OPTIONS,
                onChange: (page, pageSize) =>
                  setParams((p) => ({ ...p, page, page_size: pageSize })),
              }}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '暂无样本，点击右上角「新建样本」开始录入' }}
            />
          )}
        </div>
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <Callout variant="info" icon="i">
          测试样本的 <code>input_payload</code> 以 JSONB 存储，generator 运行时按 key 渲染占位符（
          <code>{'{{product_info}}'}</code> / <code>{'{{original_script}}'}</code> / <code>{'{{messages}}'}</code>）。
        </Callout>
      </div>
    </div>
  );
}
