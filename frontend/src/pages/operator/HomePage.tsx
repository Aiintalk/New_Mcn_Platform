import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { getTasks } from '../../api/tasks';
import { getOutputs } from '../../api/outputs';
import { getHomepageStats, getHomepageTrend } from '../../api/homepage';
import { useAuthStore } from '../../store/authStore';
import type { HomepageStats } from '../../api/homepage';
import type { TaskJob } from '../../types/task';
import type { Output } from '../../types/output';

// ── helpers ───────────────────────────────────────────────────────────────
function formatToken(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function statusBadge(s: string) {
  const cls: Record<string, string> = {
    pending: 'badge-gray', processing: 'badge-warning',
    success: 'badge-success', failed: 'badge-danger', cancelled: 'badge-gray',
  };
  const lbl: Record<string, string> = {
    pending: '待处理', processing: '处理中',
    success: '成功', failed: '失败', cancelled: '已取消',
  };
  return <span className={`badge ${cls[s] ?? 'badge-gray'}`}>{lbl[s] ?? s}</span>;
}

// ── StatCard ──────────────────────────────────────────────────────────────
function StatCard({ label, value, unit, sub, change, loading }: {
  label: string;
  value: string | number;
  unit?: string;
  sub?: string;
  change?: string | null;
  loading?: boolean;
}) {
  const changeColor = change?.startsWith('+') ? '#52c41a' : '#ff4d4f';
  return (
    <div className="card" style={{ padding: 'var(--sp-4)', marginBottom: 0 }}>
      <div style={{ color: 'var(--gray-500)', fontSize: 13, marginBottom: 8 }}>{label}</div>
      {loading
        ? <div style={{ height: 32, background: 'var(--gray-100)', borderRadius: 4 }} />
        : <>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--gray-900)', lineHeight: 1.2 }}>
              {value}
              <span style={{ fontSize: 13, color: 'var(--gray-500)', marginLeft: 4 }}>{unit}</span>
            </div>
            {change != null
              ? <div style={{ fontSize: 12, color: changeColor, marginTop: 4 }}>{change} 较{sub ?? '昨日'}</div>
              : sub && <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>{sub}</div>
            }
          </>
      }
    </div>
  );
}

// ── ToolUsageChart ────────────────────────────────────────────────────────
const DONUT_COLORS = ['#4F6EF7', '#36CFC9', '#FFA940', '#FF7875', '#D9D9D9'];

function ToolUsageChart({ data, total, loading }: {
  data: HomepageStats['tool_usage_breakdown'];
  total: number;
  loading: boolean;
}) {
  if (loading) {
    return <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">加载中...</div></div>;
  }
  if (!data.length) {
    return <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">本周暂无工具使用记录</div></div>;
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
      <div style={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
        <ResponsiveContainer width={140} height={140}>
          <PieChart>
            <Pie data={data} cx={65} cy={65} innerRadius={45} outerRadius={65}
                 dataKey="percentage" paddingAngle={2}>
              {data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
          </PieChart>
        </ResponsiveContainer>
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--gray-900)' }}>{total}</div>
          <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>次</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 0 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: DONUT_COLORS[i % DONUT_COLORS.length], flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: 'var(--gray-600)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.tool_name}
              </span>
            </div>
            <span style={{ fontSize: 12, color: 'var(--gray-500)', flexShrink: 0, marginLeft: 4 }}>
              {item.percentage.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── HomePage ──────────────────────────────────────────────────────────────
export default function HomePage() {
  const navigate = useNavigate();
  const user = useAuthStore(s => s.user);

  const [stats, setStats]               = useState<HomepageStats | null>(null);
  const [trend, setTrend]               = useState<{ date: string; count: number }[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);

  const [tasks, setTasks]   = useState<TaskJob[]>([]);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getHomepageStats(), getHomepageTrend()])
      .then(([s, t]) => { setStats(s); setTrend(t.trend); })
      .catch(() => message.error('加载统计数据失败'))
      .finally(() => setStatsLoading(false));

    Promise.all([getTasks({ page: 1, page_size: 5 }), getOutputs({ page: 1, page_size: 5 })])
      .then(([t, o]) => { setTasks(t.items); setOutputs(o.items); })
      .catch(() => message.error('加载首页数据失败'))
      .finally(() => setLoading(false));
  }, []);

  const h = new Date().getHours();
  const greeting = h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好';

  return (
    <>
      {/* 1. 顶部欢迎区 */}
      <div className="page-header">
        <div>
          <h1 className="page-title">{greeting}，{user?.real_name ?? user?.username}</h1>
          <p className="page-desc">欢迎回到达人说 AI 内容运营平台</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={() => navigate('/workspace')}>开始创作</button>
        </div>
      </div>

      {/* 2. 工作概览 — 4 卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
        <StatCard
          label="今日产出"
          value={stats?.today_outputs ?? 0}
          unit="篇"
          change={stats?.today_outputs_change ?? null}
          sub="昨日"
          loading={statsLoading}
        />
        <StatCard
          label="本周产出"
          value={stats?.week_outputs ?? 0}
          unit="篇"
          change={stats?.week_outputs_change ?? null}
          sub="上周"
          loading={statsLoading}
        />
        <StatCard
          label="进行中任务"
          value={stats?.in_progress_tasks ?? 0}
          unit="个"
          sub="实时"
          loading={statsLoading}
        />
        <StatCard
          label="Token 消耗"
          value={stats?.week_token_usage != null ? formatToken(stats.week_token_usage) : '—'}
          sub="本周"
          loading={statsLoading}
        />
      </div>

      {/* 3. 内容趋势（左）+ 工具使用占比（右） */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <h3 className="card-title">内容生成趋势</h3>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>最近7天</span>
          </div>
          <div className="card-body">
            {statsLoading
              ? <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">加载中...</div></div>
              : trend.length < 2
                ? <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">暂无趋势数据</div></div>
                : <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--gray-400)' }} tickLine={false} axisLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--gray-400)' }} tickLine={false} axisLine={false} width={28} />
                      <Tooltip contentStyle={{ fontSize: 12 }} />
                      <Line
                        type="monotone" dataKey="count" name="产出数"
                        stroke="var(--accent)" strokeWidth={2}
                        dot={{ r: 3, fill: 'var(--accent)' }} activeDot={{ r: 5 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
            }
          </div>
        </div>

        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <h3 className="card-title">工具使用占比</h3>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>本周</span>
          </div>
          <div className="card-body">
            <ToolUsageChart
              data={stats?.tool_usage_breakdown ?? []}
              total={stats?.week_tool_count ?? 0}
              loading={statsLoading}
            />
          </div>
        </div>
      </div>

      {/* 4. 常用工具快捷入口 */}
      {!statsLoading && stats?.recent_tools && stats.recent_tools.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <div className="card-header">
            <h3 className="card-title">常用工具</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/workspace')}>更多工具</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--sp-3)', padding: '0 20px 16px' }}>
            {stats.recent_tools.slice(0, 6).map(tool => (
              <button
                key={tool.tool_code}
                className="btn btn-ghost"
                style={{
                  justifyContent: 'flex-start', padding: 'var(--sp-3)',
                  height: 'auto', textAlign: 'left',
                  border: '1px solid var(--gray-200)', borderRadius: 'var(--radius-md)',
                }}
                onClick={() => {
                  if (tool.tool_code === 'persona-writer') navigate('/workspace/persona-writer');
                  else navigate(`/workspace/${tool.tool_code}`);
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-800)', marginBottom: 2 }}>
                  {tool.tool_name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>
                  {new Date(tool.last_used_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 5. 最近任务 + 最近产出 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-4)' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">最近任务</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/tasks')}>查看全部</button>
          </div>
          {loading
            ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
            : tasks.length === 0
              ? <div className="empty-state"><div className="empty-state-text">暂无任务记录</div></div>
              : <table className="ant-table">
                  <thead><tr><th>工具</th><th>状态</th><th>时间</th></tr></thead>
                  <tbody>
                    {tasks.map(t => (
                      <tr key={t.id}>
                        <td style={{ fontWeight: 600 }}>{t.tool_name}</td>
                        <td>{statusBadge(t.status)}</td>
                        <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>
                          {new Date(t.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
          }
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">最近产出</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/outputs')}>查看全部</button>
          </div>
          {loading
            ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
            : outputs.length === 0
              ? <div className="empty-state"><div className="empty-state-text">暂无产出记录</div></div>
              : <table className="ant-table">
                  <thead><tr><th>标题</th><th>工具</th><th>字数</th></tr></thead>
                  <tbody>
                    {outputs.map(o => (
                      <tr key={o.id}>
                        <td style={{ fontWeight: 600, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.title}</td>
                        <td><span className="badge badge-brand">{o.tool_name}</span></td>
                        <td style={{ color: 'var(--gray-500)', fontSize: 12 }}>{o.word_count ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
          }
        </div>
      </div>
    </>
  );
}
