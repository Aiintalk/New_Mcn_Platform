/**
 * 运行详情 + 人工校准（设计稿 run-detail.html）
 *
 * 路由：/evaluation/runs/:id
 *
 * 数据：
 *   GET /api/operator/evaluation/runs/{id}        → run 元信息
 *   GET /api/operator/evaluation/runs/{id}/scores → 所有评分（含 ai_reasoning）
 *   PUT /api/operator/evaluation/scores/{id}/human-label
 *
 * 评分按 test_case_id 分组渲染；维度雷达图用 SVG 绘制（与设计稿 eval.js renderRadar 一致）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { App, Button, Drawer, Input, Popconfirm, Skeleton, Slider, Table, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';

const { TextArea } = Input;
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import { cancelRun, getRun, listCaseResults, listRunScores, submitHumanLabel } from '../api';
import type { EvalCaseResult, EvalRun, EvalScore } from '../types';
import {
  Callout,
  PageHeader,
  ScoreChip,
  formatDuration,
} from '../components/primitives';

interface CaseRow {
  key: string;
  case_result_id: number;
  test_case_id: number;
  test_case_name: string;
  scores: EvalScore[];
  aiAvg: number | null;
  humanCalibrated: boolean;
  generated_output: string | null;
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = id ? Number(id) : null;
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [scores, setScores] = useState<EvalScore[]>([]);
  const [caseResults, setCaseResults] = useState<EvalCaseResult[]>([]);
  const [calibrating, setCalibrating] = useState<EvalScore | null>(null);
  const [humanScore, setHumanScore] = useState(7);
  const [humanFeedback, setHumanFeedback] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    try {
      const [runData, scoreData, crData] = await Promise.all([
        getRun(runId),
        listRunScores(runId),
        listCaseResults(runId),
      ]);
      setRun(runData);
      setScores(scoreData);
      setCaseResults(crData);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [runId, message]);

  useEffect(() => {
    void load();
  }, [load]);

  // 进度轮询（Phase 4）：run 处于 pending/running 时每 4s 拉 getRun；
  // 检测到终态（completed/failed）→ 重拉 listRunScores（挂载时 pending 期 scores 为空）+ 停轮询。
  // 依赖 run?.status：状态变化时 effect 重跑，自动清旧 timer。
  useEffect(() => {
    if (!run || run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') return;
    const runId = run.id;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const runData = await getRun(runId);
        if (cancelled) return;
        setRun(runData);
        if (runData.status === 'completed' || runData.status === 'failed') {
          const [scoreData, crData] = await Promise.all([
            listRunScores(runId),
            listCaseResults(runId),
          ]);
          if (!cancelled) {
            setScores(scoreData);
            setCaseResults(crData);
          }
        }
      } catch {
        // 静默：单次轮询失败不打断（下次重试）
      }
    };

    timer = setInterval(() => { void poll(); }, 4000);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [run?.id, run?.status]);

  // 按 case_result_id 聚合（scores ∪ caseResults：有输出但未评分的 case 也要显示）
  const rows: CaseRow[] = useMemo(() => {
    const byCase = new Map<number, EvalScore[]>();
    scores.forEach((s) => {
      const arr = byCase.get(s.case_result_id) ?? [];
      arr.push(s);
      byCase.set(s.case_result_id, arr);
    });
    const crMap = new Map<number, EvalCaseResult>();
    caseResults.forEach((cr) => crMap.set(cr.id, cr));
    const allIds = new Set<number>([...byCase.keys(), ...crMap.keys()]);
    return Array.from(allIds).sort((a, b) => a - b).map((caseResultId) => {
      const scoreList = byCase.get(caseResultId) ?? [];
      const cr = crMap.get(caseResultId);
      const aiScores = scoreList.map((s) => (s.ai_score === null ? null : Number(s.ai_score))).filter((v): v is number => v !== null);
      const aiAvg = aiScores.length > 0 ? aiScores.reduce((a, b) => a + b, 0) / aiScores.length : null;
      const anyHuman = scoreList.some((s) => s.human_score !== null);
      return {
        key: String(caseResultId),
        case_result_id: caseResultId,
        test_case_id: cr?.test_case_id ?? caseResultId,
        test_case_name: cr?.test_case_name ?? `样本 #${caseResultId}`,
        scores: scoreList,
        aiAvg,
        humanCalibrated: anyHuman,
        generated_output: cr?.generated_output ?? null,
      };
    });
  }, [scores, caseResults]);

  // 维度聚合（雷达图 + 列表）
  // 维度 id → 显示名（scores 端点附带；雷达图/徽章统一用，d{id} 兜底）
  const dimNameMap = useMemo(() => {
    const m = new Map<number, string>();
    scores.forEach((s) => {
      if (s.dimension_name) m.set(s.dimension_id, s.dimension_name);
    });
    return m;
  }, [scores]);

  const dimensionAgg = useMemo(() => {
    const byDim = new Map<number, { sum: number; count: number }>();
    scores.forEach((s) => {
      if (s.ai_score === null) return;
      const cur = byDim.get(s.dimension_id) ?? { sum: 0, count: 0 };
      cur.sum += s.ai_score;
      cur.count += 1;
      byDim.set(s.dimension_id, cur);
    });
    return Array.from(byDim.entries()).map(([dimId, v]) => ({
      dimension_id: dimId,
      name: dimNameMap.get(dimId) || `d${dimId}`,
      avg: v.count > 0 ? v.sum / v.count : null,
    }));
  }, [scores]);

  const overallAvg = useMemo(() => {
    // Number() 防御：后端 Decimal 曾序列化成字符串导致 a+b 拼接 + 雷达图 NaN
    const all = scores.map((s) => (s.ai_score === null ? null : Number(s.ai_score))).filter((v): v is number => v !== null);
    return all.length > 0 ? all.reduce((a, b) => a + b, 0) / all.length : null;
  }, [scores]);

  const handleCancel = async () => {
    if (!run) return;
    try {
      const updated = await cancelRun(run.id);
      setRun(updated);
      message.success('运行已取消');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '取消失败';
      message.error(msg);
    }
  };

  const openCalibrate = (score: EvalScore) => {
    setCalibrating(score);
    setHumanScore(score.human_score ?? score.ai_score ?? 7);
    setHumanFeedback(score.human_feedback ?? '');
  };

  const handleSaveCalibration = async () => {
    if (!calibrating) return;
    setSaving(true);
    try {
      const updated = await submitHumanLabel(calibrating.id, {
        human_score: humanScore,
        human_feedback: humanFeedback || null,
      });
      setScores((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      message.success(`人工校准已保存（${humanScore} 分）`);
      setCalibrating(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败';
      message.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<CaseRow> = [
    {
      title: '样本',
      dataIndex: 'test_case_name',
      key: 'test_case_name',
      render: (v) => <span style={{ color: 'var(--gray-900)', fontWeight: 500 }}>{v}</span>,
    },
    {
      title: 'AI 平均分',
      dataIndex: 'aiAvg',
      key: 'aiAvg',
      width: 120,
      render: (v: number | null) => <ScoreChip score={v} />,
    },
    {
      title: '维度评分',
      key: 'dim-scores',
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {r.scores.map((s) => (
            <Tag key={s.id} style={{ margin: 0, fontSize: 12 }}>
              {s.dimension_name || `d${s.dimension_id}`}: <b>{s.ai_score !== null ? Number(s.ai_score).toFixed(1) : '—'}</b>
              {s.human_score !== null ? (
                <span style={{ color: 'var(--success)', marginLeft: 4 }}>★{Number(s.human_score).toFixed(1)}</span>
              ) : null}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '人工校准',
      dataIndex: 'humanCalibrated',
      key: 'humanCalibrated',
      width: 110,
      render: (v: boolean) =>
        v ? (
          <Tag color="success" style={{ margin: 0 }}>
            已校准
          </Tag>
        ) : (
          <Tag color="default" style={{ margin: 0 }}>
            未校准
          </Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      align: 'right',
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          {r.scores.map((s) => (
            <Button
              key={s.id}
              size="small"
              type={s.human_score === null ? 'primary' : 'link'}
              onClick={() => openCalibrate(s)}
            >
              校准 {s.dimension_name || `d${s.dimension_id}`}
            </Button>
          ))}
        </div>
      ),
    },
  ];

  if (loading && !run) {
    return (
      <div className="eval-page" style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="eval-page">
        <Callout variant="warn" icon="!">
          运行不存在或加载失败。
        </Callout>
        <Button style={{ marginTop: 16 }} onClick={() => navigate('/evaluation/runs')}>
          ← 返回列表
        </Button>
      </div>
    );
  }

  return (
    <div className="eval-page">
      <PageHeader
        title={run.name || `Run #${run.id}`}
        titleTag={run.status}
        description={`版本 v#${run.version_id} · 策略 default · ${run.trigger_type} 触发 · ${run.completed_cases}/${run.total_cases} 完成 · 失败 ${run.failed_cases}${run.filter_tags.length > 0 ? ` · filter_tags: ${run.filter_tags.join(', ')}` : ''}`}
        actions={
          <>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/evaluation/runs')}>
              返回列表
            </Button>
            <Button type="primary" onClick={() => navigate('/evaluation/compare')}>
              与其它版本对比
            </Button>
            {(run.status === 'pending' || run.status === 'running') && (
              <Popconfirm
                title="确认取消此运行？"
                description="未开始的样本会被跳过；已在跑的样本会自然跑完。"
                okText="确认取消"
                cancelText="算了"
                onConfirm={() => void handleCancel()}
              >
                <Button danger>取消运行</Button>
              </Popconfirm>
            )}
          </>
        }
      />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">总样本</div>
          <div className="stat-value">{run.total_cases}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">完成</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {run.completed_cases}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">失败</div>
          <div className="stat-value" style={{ color: run.failed_cases > 0 ? 'var(--danger)' : undefined }}>
            {run.failed_cases}
          </div>
        </div>
        <div className="stat-card accent">
          <div className="stat-label">整体平均分</div>
          <div className="stat-value">
            {overallAvg !== null ? overallAvg.toFixed(2) : '—'}
            <span className="unit">/10</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">耗时</div>
          <div className="stat-value" style={{ fontSize: 22 }}>
            {formatDuration(run.started_at, run.finished_at)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">预计剩余</div>
          <div className="stat-value" style={{ fontSize: 22 }}>
            {run.eta_secs != null
              ? run.eta_secs >= 60
                ? `≈${Math.floor(run.eta_secs / 60)}m ${run.eta_secs % 60}s`
                : `≈${run.eta_secs}s`
              : '—'}
          </div>
        </div>
      </div>

      <div className="card mb-5">
        <div className="card-header">
          <h3>维度评分概览</h3>
          <span className="ch-sub">本次运行 AI 评分聚合（按维度均分）</span>
        </div>
        <div className="card-body">
          {dimensionAgg.length === 0 ? (
            <div className="empty-state">
              <div className="es-icon">△</div>
              <div className="es-text">暂无评分数据</div>
              <div className="es-hint">运行完成后会自动聚合</div>
            </div>
          ) : (
            <div className="radar-wrap">
              <RadarChart
                labels={dimensionAgg.map((d) => d.name)}
                values={dimensionAgg.map((d) => d.avg ?? 0)}
              />
              <div className="radar-legend">
                {dimensionAgg.map((d) => (
                  <div className="legend-row" key={d.dimension_id}>
                    <div>
                      <div className="fw-600">维度 #{d.dimension_id}</div>
                      <div className="text-xs text-muted">dimension_id: {d.dimension_id}</div>
                    </div>
                    <ScoreChip score={d.avg} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>样本明细</h3>
          <span className="ch-sub">每行一个 case 的生成输出与各维度评分</span>
        </div>
        <div className="card-body flush">
          <Table<CaseRow>
            rowKey="key"
            columns={columns}
            dataSource={rows}
            size="middle"
            pagination={{ pageSize: 20 }}
            style={{ padding: '0 var(--sp-5)' }}
            locale={{ emptyText: '暂无样本评分数据' }}
            expandable={{
              expandedRowRender: (r) =>
                r.generated_output ? (
                  <div
                    style={{
                      background: 'var(--gray-50)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      padding: 12,
                      fontSize: 13,
                      color: 'var(--gray-700)',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {r.generated_output}
                  </div>
                ) : (
                  <span className="text-muted">该 case 无生成输出</span>
                ),
              rowExpandable: () => true,
            }}
          />
        </div>
      </div>

      <Drawer
        title="人工校准"
        placement="right"
        width={640}
        open={calibrating !== null}
        onClose={() => setCalibrating(null)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleSaveCalibration()}>
            保存校准
          </Button>
        }
        destroyOnHidden
      >
        {calibrating ? (
          <div>
            <div className="text-xs text-muted" style={{ marginBottom: 12 }}>
              case_result #{calibrating.case_result_id} · 维度 #{calibrating.dimension_id} · 权重 {calibrating.weight_used}
            </div>

            <div style={{ marginBottom: 20 }}>
              <div className="text-sm fw-600" style={{ marginBottom: 8 }}>
                AI 初评
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <ScoreChip score={calibrating.ai_score} />
                <span className="text-xs text-muted">权重 {calibrating.weight_used}</span>
              </div>
              {calibrating.ai_reasoning ? (
                <div
                  style={{
                    background: 'var(--gray-50)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)',
                    padding: 12,
                    fontSize: 13,
                    color: 'var(--gray-700)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {calibrating.ai_reasoning}
                </div>
              ) : null}
              {(calibrating.ai_strengths.length > 0 || calibrating.ai_weaknesses.length > 0) && (
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {calibrating.ai_strengths.map((s, i) => (
                    <Tag key={`s${i}`} color="success" style={{ margin: 0 }}>
                      优点：{s}
                    </Tag>
                  ))}
                  {calibrating.ai_weaknesses.map((s, i) => (
                    <Tag key={`w${i}`} color="error" style={{ margin: 0 }}>
                      缺点：{s}
                    </Tag>
                  ))}
                </div>
              )}
            </div>

            <div style={{ marginBottom: 20 }}>
              <div className="text-sm fw-600" style={{ marginBottom: 8 }}>
                人工分数（覆盖 AI 初评）
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Slider
                  min={1}
                  max={10}
                  step={1}
                  value={humanScore}
                  onChange={setHumanScore}
                  style={{ flex: 1 }}
                />
                <ScoreChip score={humanScore} />
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div className="text-sm fw-600" style={{ marginBottom: 8 }}>
                反馈 feedback
              </div>
              <TextArea
                rows={4}
                value={humanFeedback}
                onChange={(e) => setHumanFeedback(e.target.value)}
                placeholder="说明本次校准的理由（可选，写入 eval_human_labels）"
              />
            </div>

            <Callout variant="info" icon="i">
              保存后将在同一事务更新 eval_scores.human_score 并插入 eval_human_labels 历史记录。
            </Callout>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

/** SVG 雷达图（移植自设计稿 eval.js renderRadar，单系列简化版） */
function RadarChart({ labels, values }: { labels: string[]; values: number[] }) {
  const cx = 110;
  const cy = 110;
  const R = 80;
  const n = labels.length;
  if (n < 3) {
    return (
      <div
        style={{
          width: 220,
          height: 220,
          display: 'grid',
          placeItems: 'center',
          color: 'var(--gray-500)',
          fontSize: 12,
        }}
      >
        至少需要 3 个维度才能渲染雷达图
      </div>
    );
  }

  const polyPoints = (vals: number[]) => {
    const pts: string[] = [];
    for (let i = 0; i < n; i++) {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
      const r = (vals[i] / 10) * R;
      pts.push(`${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`);
    }
    return pts.join(' ');
  };

  const lines = [];
  for (let g = 2; g <= 10; g += 2) {
    lines.push(
      <polygon
        key={`grid-${g}`}
        points={polyPoints(labels.map(() => g))}
        fill="none"
        stroke="var(--border)"
        strokeWidth={1}
      />,
    );
  }
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    lines.push(
      <line
        key={`axis-${i}`}
        x1={cx}
        y1={cy}
        x2={(cx + R * Math.cos(a)).toFixed(1)}
        y2={(cy + R * Math.sin(a)).toFixed(1)}
        stroke="var(--border)"
      />,
    );
    const tx = cx + (R + 16) * Math.cos(a);
    const ty = cy + (R + 16) * Math.sin(a) + 4;
    lines.push(
      <text
        key={`label-${i}`}
        x={tx.toFixed(1)}
        y={ty.toFixed(1)}
        textAnchor="middle"
        fontSize={10}
        fill="var(--gray-500)"
      >
        {labels[i]}
      </text>,
    );
  }

  return (
    <svg width={220} height={220} viewBox="0 0 220 220" data-testid="radar-chart">
      {lines}
      <polygon
        points={polyPoints(values)}
        fill="var(--brand)"
        fillOpacity={0.18}
        stroke="var(--brand)"
        strokeWidth={2}
      />
    </svg>
  );
}
