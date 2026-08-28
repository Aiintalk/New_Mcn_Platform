/**
 * 版本对比报告（设计稿 compare.html）
 *
 * 数据：GET /api/operator/evaluation/compare?run_a=&run_b=
 * 展示：总体 / 维度 / 样本级 diff，标 ▲▼→
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Select, Skeleton, Table, Tag } from 'antd';
import { SwapOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import { compareRuns, listRuns } from '../api';
import type { EvalCaseDelta, EvalComparisonReport, EvalDimensionDelta, EvalRun } from '../types';
import { Callout, DiffIndicator, PageHeader, ScoreChip } from '../components/primitives';

const SAMPLE_A = 'A';
const SAMPLE_B = 'B';
const MAX_SCORE = 10;

/** run 下拉选项文案：#id 名称（状态 · 日期）——用户凭印象选，信息给足 */
function runOptionLabel(r: EvalRun): string {
  const name = r.name || `Run #${r.id}`;
  const date = (r.created_at || '').slice(5, 10).replace('-', '/');
  const statusText: Record<string, string> = {
    completed: '已完成',
    running: '进行中',
    pending: '排队中',
    failed: '失败',
    partial: '部分完成',
    cancelled: '已取消',
  };
  return `#${r.id} ${name}（${statusText[r.status] ?? r.status} · ${date}）`;
}

export default function ComparePage() {
  const { message } = App.useApp();
  const [runA, setRunA] = useState<number | null>(null);
  const [runB, setRunB] = useState<number | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<EvalComparisonReport | null>(null);
  const [filterDir, setFilterDir] = useState<'all' | EvalCaseDelta['direction']>('all');

  const handleCompare = useCallback(async () => {
    if (runA === null || runB === null) {
      message.warning('请选择两个运行');
      return;
    }
    if (runA === runB) {
      message.warning('请选择不同的运行');
      return;
    }
    setLoading(true);
    try {
      const data = await compareRuns(runA, runB);
      setReport(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [runA, runB, message]);

  // 加载可选 run 列表（下拉选择，替代手输数字 id）；默认选最近两次完成的 run
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listRuns({ page: 1, page_size: 50 });
        if (cancelled) return;
        setRuns(data.items);
        // 默认预选：最近两个 completed（对比最常见的"旧基线 vs 新版"场景）
        const done = data.items.filter((r) => r.status === 'completed');
        const [newer, older] = done;
        if (newer && older) {
          setRunB(newer.id);
          setRunA(older.id);
        }
      } catch {
        // 静默：列表加载失败不阻塞页面，用户仍可手动输入（Select 支持搜索）
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 后端 comparator 的 direction 是 up/down/same，页面语义是 improve/worsen/flat——
  // 数据入口归一化（顺带把 only_a/only_b 归为 flat，样本交集模式下不出现）
  const normalizedCases = useMemo(() => {
    if (!report) return [];
    const map: Record<string, EvalCaseDelta['direction']> = {
      up: 'improve', down: 'worsen', same: 'flat', only_a: 'flat', only_b: 'flat',
    };
    return report.case_deltas.map((c) => ({
      ...c,
      direction: map[c.direction] ?? 'flat',
    }));
  }, [report]);

  const filteredCases = useMemo(() => {
    if (filterDir === 'all') return normalizedCases;
    return normalizedCases.filter((c) => c.direction === filterDir);
  }, [normalizedCases, filterDir]);

  const counts = useMemo(() => {
    return {
      all: normalizedCases.length,
      improve: normalizedCases.filter((c) => c.direction === 'improve').length,
      worsen: normalizedCases.filter((c) => c.direction === 'worsen').length,
      flat: normalizedCases.filter((c) => c.direction === 'flat').length,
    };
  }, [normalizedCases]);

  const columns: ColumnsType<EvalCaseDelta> = [
    {
      title: '样本',
      dataIndex: 'test_case_name',
      key: 'test_case_name',
      render: (v) => <span style={{ color: 'var(--gray-900)', fontWeight: 500 }}>{v}</span>,
    },
    {
      title: 'A 分',
      dataIndex: 'avg_a',
      key: 'avg_a',
      width: 110,
      render: (v: number | null) => <ScoreChip score={v} />,
    },
    {
      title: 'B 分',
      dataIndex: 'avg_b',
      key: 'avg_b',
      width: 110,
      render: (v: number | null) => <ScoreChip score={v} />,
    },
    {
      title: '变化',
      dataIndex: 'delta',
      key: 'delta',
      width: 110,
      render: (v: number | null, r) => {
        const dir = r.direction;
        const arrow = dir === 'improve' ? '▲' : dir === 'worsen' ? '▼' : '→';
        const cls = dir === 'improve' ? 'diff-up' : dir === 'worsen' ? 'diff-down' : 'diff-flat';
        return (
          <span className={cls}>
            {arrow} {v !== null ? Math.abs(v).toFixed(1) : '0.0'}
          </span>
        );
      },
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      width: 100,
      render: (dir: EvalCaseDelta['direction']) => {
        const meta = {
          improve: { color: 'success', text: '改善' },
          worsen: { color: 'error', text: '恶化' },
          flat: { color: 'default', text: '持平' },
        }[dir];
        return (
          <Tag color={meta.color} style={{ margin: 0 }}>
            {meta.text}
          </Tag>
        );
      },
    },
  ];

  return (
    <div className="eval-page">
      <PageHeader
        title="版本对比报告"
        description='comparator.py 取两个 run 的 scores，计算总体 / 维度 / 样本级 diff，回答"新版到底变好还是变差"。'
        actions={
          <Button icon={<SwapOutlined />} disabled={!report} onClick={() => {
            if (runA !== null && runB !== null) {
              setRunA(runB);
              setRunB(runA);
            }
          }}>
            交换 A / B
          </Button>
        }
      />

      <Card className="mb-5" styles={{ body: { padding: 24 } }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 16, alignItems: 'end' }}>
          <div>
            <label className="text-sm" style={{ display: 'block', marginBottom: 6, color: 'var(--gray-700)', fontWeight: 500 }}>
              A 基线运行
            </label>
            <Select
              style={{ width: '100%' }}
              placeholder="选择旧版本运行"
              value={runA ?? undefined}
              onChange={(v) => setRunA(typeof v === 'number' ? v : null)}
              allowClear
              showSearch
              optionFilterProp="label"
              options={runs.map((r) => ({ label: runOptionLabel(r), value: r.id }))}
            />
          </div>
          <div>
            <label className="text-sm" style={{ display: 'block', marginBottom: 6, color: 'var(--gray-700)', fontWeight: 500 }}>
              B 新版运行
            </label>
            <Select
              style={{ width: '100%' }}
              placeholder="选择新版本运行"
              value={runB ?? undefined}
              onChange={(v) => setRunB(typeof v === 'number' ? v : null)}
              allowClear
              showSearch
              optionFilterProp="label"
              options={runs.map((r) => ({ label: runOptionLabel(r), value: r.id }))}
            />
          </div>
          <div>
            <label className="text-sm" style={{ display: 'block', marginBottom: 6, color: 'var(--gray-700)', fontWeight: 500 }}>
              对比范围
            </label>
            <Select
              style={{ width: '100%' }}
              defaultValue="intersection"
              options={[{ label: '相同样本交集', value: 'intersection' }]}
            />
          </div>
          <Button type="primary" loading={loading} onClick={() => void handleCompare()}>
            对比
          </Button>
        </div>
      </Card>

      {loading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : report ? (
        <>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">A 基线平均分 (run #{report.run_a_id})</div>
              <div className="stat-value">{report.overall_avg_a !== null ? report.overall_avg_a.toFixed(2) : '—'}</div>
            </div>
            <div className="stat-card accent">
              <div className="stat-label">B 新版平均分 (run #{report.run_b_id})</div>
              <div className="stat-value">{report.overall_avg_b !== null ? report.overall_avg_b.toFixed(2) : '—'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">整体变化</div>
              <div
                className="stat-value"
                style={{
                  color:
                    (report.overall_delta ?? 0) > 0
                      ? 'var(--success)'
                      : (report.overall_delta ?? 0) < 0
                        ? 'var(--danger)'
                        : 'var(--gray-500)',
                }}
              >
                {report.overall_delta !== null
                  ? `${report.overall_delta > 0 ? '+' : ''}${report.overall_delta.toFixed(2)}`
                  : '—'}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">改善 / 恶化 / 持平</div>
              <div className="stat-value" style={{ fontSize: 20, lineHeight: 1.4 }}>
                <span style={{ color: 'var(--success)' }}>{counts.improve}</span>{' '}
                <span className="text-muted">/</span>{' '}
                <span style={{ color: 'var(--danger)' }}>{counts.worsen}</span>{' '}
                <span className="text-muted">/</span>{' '}
                <span style={{ color: 'var(--gray-500)' }}>{counts.flat}</span>
              </div>
            </div>
          </div>

          <div className="card mb-5">
            <div className="card-header">
              <h3>维度差异</h3>
              <span className="ch-sub">每个维度两个 run 的平均分对比</span>
            </div>
            <div className="card-body">
              {report.dimension_deltas.length === 0 ? (
                <div className="empty-state">
                  <div className="es-text">暂无维度数据</div>
                </div>
              ) : (
                <DimensionBars deltas={report.dimension_deltas} />
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>样本级差异</h3>
              <span className="ch-sub">共 {counts.all} 条样本</span>
            </div>
            <div className="card-body flush">
              <div className="sub-tabs" style={{ padding: '0 var(--sp-5)', marginBottom: 0 }}>
                {(
                  [
                    { key: 'all', label: '全部' },
                    { key: 'improve', label: '改善' },
                    { key: 'worsen', label: '恶化' },
                    { key: 'flat', label: '持平' },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    className={`sub-tab ${filterDir === t.key ? 'active' : ''}`}
                    onClick={() => setFilterDir(t.key)}
                  >
                    {t.label} <span className="count">{counts[t.key]}</span>
                  </button>
                ))}
              </div>
              <Table<EvalCaseDelta>
                rowKey="test_case_id"
                columns={columns}
                dataSource={filteredCases}
                size="middle"
                pagination={{ pageSize: 20 }}
                style={{ padding: '0 var(--sp-5)' }}
              />
            </div>
          </div>
        </>
      ) : (
        <Callout variant="info" icon="i">
          下拉选择两个运行后点击「对比」（支持按名称/编号搜索）。A 应为旧版本基线运行，B 为新版本对照运行；样本交集为两次运行都包含的样本。默认预选最近两次已完成的运行。
        </Callout>
      )}
    </div>
  );
}

/** 维度 diff 双向条形图 */
function DimensionBars({ deltas }: { deltas: EvalDimensionDelta[] }) {
  return (
    <div>
      {deltas.map((d) => {
        const aW = ((d.avg_a ?? 0) / MAX_SCORE) * 100;
        const bW = ((d.avg_b ?? 0) / MAX_SCORE) * 100;
        return (
          <div className="compare-row" key={d.dimension_id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="fw-600">{d.dimension_name}</span>
              <DiffIndicator delta={d.delta} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="compare-line">
                <span className="compare-label">{SAMPLE_A}</span>
                <div className="compare-track">
                  <div
                    className="compare-fill"
                    style={{ width: `${aW}%`, background: 'var(--gray-400)' }}
                  />
                </div>
                <span className="compare-val">{d.avg_a !== null ? d.avg_a.toFixed(1) : '—'}</span>
              </div>
              <div className="compare-line">
                <span className="compare-label">{SAMPLE_B}</span>
                <div className="compare-track">
                  <div
                    className="compare-fill"
                    style={{ width: `${bW}%`, background: 'var(--brand)' }}
                  />
                </div>
                <span className="compare-val">{d.avg_b !== null ? d.avg_b.toFixed(1) : '—'}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
