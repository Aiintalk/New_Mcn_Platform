import { useEffect, useState, useCallback } from 'react';
import { Modal, Form, Input, Select, Tabs, Popconfirm, message } from 'antd';
import { EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { getCredentials, createCredential, updateCredential, deleteCredential, enableCredential, disableCredential, testOssCredential } from '../../api/credentials';
import { testAiKey, testAiModel, getAiStats, getAiKeys, createAiKey, updateAiKey, deleteAiKey, getAiModels, createAiModel, deleteAiModel, updateAiModel } from '../../api/ai';
import { getTikHubStats, getTikHubKeys, createTikHubKey, updateTikHubKey, deleteTikHubKey, testTikHubKey, enableTikHubKey, disableTikHubKey, getTikHubEndpoints, getTikHubUsers } from '../../api/tikhub';
import { getOssStats, getOssOperations, getOssUsers } from '../../api/oss';
import { getAsrStats, getAsrOperations, getAsrUsers } from '../../api/asr';
import type { AiStatsResponse, AiKeyRecord, AiModelItem, ByModelItem, TokenTrendItem, CreateAiModelRequest } from '../../api/ai';
import type { TikHubStatsResponse, TikHubKey, TikHubEndpointDetail, TikHubUserRank } from '../../api/tikhub';
import type { OssStatsResponse, OssOperationDetail, OssUserDetail } from '../../api/oss';
import type { AsrStatsResponse, AsrOperationDetail, AsrUserDetail } from '../../api/asr';
import type { ServiceCredential, CreateCredentialRequest, UpdateCredentialRequest } from '../../types/credential';
import type { PagedData } from '../../types/api';

// ── KeyRow — per-row component so revealed state is local and never reset ─────
interface KeyRowProps {
  k: AiKeyRecord;
  idx: number;
  testing: boolean;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function KeyRow({ k, idx, testing, onTest, onEdit, onDelete }: KeyRowProps) {
  const [revealed, setRevealed] = useState(false);
  const testTime = k.last_tested_at
    ? `${fmtTime(k.last_tested_at)}${k.last_latency_ms !== null ? ` · ${k.last_latency_ms}ms` : ''}`
    : '—';
  return (
    <tr>
      <td><span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{idx + 1}</span></td>
      <td><span style={{ fontSize: 12, color: 'var(--gray-700)' }}>{k.label}</span></td>
      <td><span style={{ fontSize: 12, color: 'var(--gray-700)' }}>{k.provider}</span></td>
      <td>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--gray-700)', letterSpacing: revealed ? 0 : 2 }}>
            {revealed ? k.api_key : '••••••••'}
          </span>
          <button
            onClick={() => setRevealed(v => !v)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--gray-400)', display: 'inline-flex', alignItems: 'center', lineHeight: 1 }}
          >
            {revealed ? <EyeInvisibleOutlined style={{ fontSize: 14 }} /> : <EyeOutlined style={{ fontSize: 14 }} />}
          </button>
        </span>
      </td>
      <td>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, display: 'inline-block', background: k.status === 'disabled' ? 'var(--danger)' : !k.last_tested_at ? 'var(--gray-300)' : 'var(--success)' }} />
          {k.status === 'disabled' ? '停用' : !k.last_tested_at ? '未测试' : '正常'}
        </span>
      </td>
      <td><span style={{ fontSize: 12, color: 'var(--gray-700)' }}>{k.concurrency}/{k.max_concurrent}</span></td>
      <td><span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{testTime}</span></td>
      <td><span style={{ fontSize: 13 }}>{k.today_calls.toLocaleString()}</span></td>
      <td><span style={{ fontSize: 13, fontWeight: 600 }}>{k.total_calls.toLocaleString()}</span></td>
      <td>
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost btn-sm" disabled={testing} onClick={onTest}>
            {testing ? '测试中...' : '测试'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onEdit}>编辑</button>
          <Popconfirm title="确认删除？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={onDelete}>
            <button className="btn btn-danger-ghost btn-sm">删除</button>
          </Popconfirm>
        </div>
      </td>
    </tr>
  );
}

// ── Date-range helper ─────────────────────────────────────────────────────────
function getDateRange(range: string): { start_date: string; end_date: string } {
  const today = new Date();
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  const shift = (n: number) => { const d = new Date(today); d.setDate(d.getDate() + n); return d; };
  if (range === '今日')   return { start_date: fmt(today),      end_date: fmt(today) };
  if (range === '近30天') return { start_date: fmt(shift(-29)), end_date: fmt(today) };
  return                         { start_date: fmt(shift(-6)),  end_date: fmt(today) }; // 近7天
}

const PROVIDERS = ['全部', '云雾', '硅基流动', 'GLM'];

const PROVIDER_BASE_URL: Record<string, string> = {
  yunwu:       'https://yunwu.ai/v1',
  siliconflow: 'https://api.siliconflow.cn/v1',
  glm:         'https://open.bigmodel.cn/api/paas/v4',
};
const CHART_COLORS = ['#4096FF', '#52C41A', '#FF7A45', '#FAAD14', '#9254DE'];

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtTokens(n: number | null | undefined): string {
  if (n == null || n === 0) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const mm  = String(d.getMonth() + 1).padStart(2, '0');
  const dd  = String(d.getDate()).padStart(2, '0');
  const hh  = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${min}`;
}

// ── DonutChart (SVG) ──────────────────────────────────────────────────────────
function DonutChart({ data }: { data: ByModelItem[] }) {
  const r = 48; const cx = 64; const cy = 64;
  const circ = 2 * Math.PI * r;
  let cum = 0;

  const segs = data.map((item, i) => {
    const dash = (item.pct / 100) * circ;
    const rot = (cum / 100) * 360 - 90;
    cum += item.pct;
    return { dash, rot, color: CHART_COLORS[i % CHART_COLORS.length], ...item };
  });

  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg width={128} height={128} viewBox="0 0 128 128" style={{ flexShrink: 0 }}>
        {segs.map((s, i) => (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={s.color}
            strokeWidth={16}
            strokeDasharray={`${s.dash} ${circ - s.dash}`}
            transform={`rotate(${s.rot} ${cx} ${cy})`}
          />
        ))}
        <circle cx={cx} cy={cy} r={r - 16} fill="white" />
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={20} fontWeight={700} fill="#1d1d1f">{data.length}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="#a8a29e">模型</text>
      </svg>
      <div style={{ flex: 1, minWidth: 0 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
            <span style={{ flex: 1, fontSize: 12, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--gray-800)', width: 38, textAlign: 'right' }}>{item.pct}%</span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', width: 44, textAlign: 'right' }}>{fmtTokens(item.tokens)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── LineChart (SVG) ───────────────────────────────────────────────────────────
function LineChart({ data }: { data: TokenTrendItem[] }) {
  if (data.length < 2) return null;
  const W = 360; const H = 130;
  const pL = 42; const pR = 8; const pT = 10; const pB = 26;
  const cW = W - pL - pR;
  const cH = H - pT - pB;
  const maxVal = Math.max(...data.flatMap(d => [d.input, d.output]));
  const n = data.length;

  const xP = (i: number) => pL + (i / (n - 1)) * cW;
  const yP = (v: number) => pT + cH - (v / maxVal) * cH;

  const inPts  = data.map((d, i) => `${xP(i)},${yP(d.input)}`).join(' ');
  const outPts = data.map((d, i) => `${xP(i)},${yP(d.output)}`).join(' ');

  const yTicks = [0, 0.5, 1].map(r => ({ v: maxVal * r, y: yP(maxVal * r) }));

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pL} y1={t.y} x2={W - pR} y2={t.y} stroke="#f5f5f4" strokeWidth={1} />
            <text x={pL - 4} y={t.y + 4} textAnchor="end" fontSize={9} fill="#a8a29e">{fmtTokens(t.v)}</text>
          </g>
        ))}
        <polyline points={inPts}  fill="none" stroke="#4096FF" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <polyline points={outPts} fill="none" stroke="#FF7A45" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((d, i) => (
          <g key={i}>
            <circle cx={xP(i)} cy={yP(d.input)}  r={3} fill="#4096FF" />
            <circle cx={xP(i)} cy={yP(d.output)} r={3} fill="#FF7A45" />
            <text x={xP(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="#a8a29e">{d.date}</text>
          </g>
        ))}
      </svg>
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 6 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--gray-600)' }}>
          <span style={{ width: 18, height: 2, background: '#4096FF', borderRadius: 1, display: 'inline-block' }} />输入 Token
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--gray-600)' }}>
          <span style={{ width: 18, height: 2, background: '#FF7A45', borderRadius: 1, display: 'inline-block' }} />输出 Token
        </span>
      </div>
    </div>
  );
}

// ── TikHub DonutChart (SVG) ──────────────────────────────────────────────────
function TikHubDonutChart({ data }: { data: { endpoint: string; percentage: number; calls: number }[] }) {
  const r = 48; const cx = 64; const cy = 64;
  const circ = 2 * Math.PI * r;
  let cum = 0;
  const segs = data.map((item, i) => {
    const dash = (item.percentage / 100) * circ;
    const rot = (cum / 100) * 360 - 90;
    cum += item.percentage;
    return { dash, rot, color: CHART_COLORS[i % CHART_COLORS.length], ...item };
  });
  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg width={128} height={128} viewBox="0 0 128 128" style={{ flexShrink: 0 }}>
        {segs.map((s, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={16}
            strokeDasharray={`${s.dash} ${circ - s.dash}`} transform={`rotate(${s.rot} ${cx} ${cy})`} />
        ))}
        <circle cx={cx} cy={cy} r={r - 16} fill="white" />
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={20} fontWeight={700} fill="#1d1d1f">{data.length}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="#a8a29e">接口</text>
      </svg>
      <div style={{ flex: 1, minWidth: 0 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
            <span style={{ flex: 1, fontSize: 12, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.endpoint}</span>
            <span style={{ fontSize: 12, fontWeight: 600, width: 38, textAlign: 'right' }}>{item.percentage}%</span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', width: 44, textAlign: 'right' }}>{item.calls}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── TikHub LineChart (SVG) ───────────────────────────────────────────────────
function TikHubLineChart({ data }: { data: { date: string; calls: number }[] }) {
  if (data.length < 2) return <div style={{ fontSize: 12, color: 'var(--gray-400)', textAlign: 'center', padding: 20 }}>数据不足，至少需要 2 天</div>;
  const W = 360; const H = 130; const pL = 42; const pR = 8; const pT = 10; const pB = 26;
  const cW = W - pL - pR; const cH = H - pT - pB;
  const maxVal = Math.max(...data.map(d => d.calls));
  const n = data.length;
  const xP = (i: number) => pL + (i / (n - 1)) * cW;
  const yP = (v: number) => pT + cH - (v / maxVal) * cH;
  const pts = data.map((d, i) => `${xP(i)},${yP(d.calls)}`).join(' ');
  const yTicks = [0, 0.5, 1].map(r => ({ v: maxVal * r, y: yP(maxVal * r) }));
  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pL} y1={t.y} x2={W - pR} y2={t.y} stroke="#f5f5f4" strokeWidth={1} />
            <text x={pL - 4} y={t.y + 4} textAnchor="end" fontSize={9} fill="#a8a29e">{Math.round(t.v)}</text>
          </g>
        ))}
        <polyline points={pts} fill="none" stroke="#52C41A" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((d, i) => (
          <g key={i}>
            <circle cx={xP(i)} cy={yP(d.calls)} r={3} fill="#52C41A" />
            <text x={xP(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="#a8a29e">{d.date}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

// ── OSS DonutChart (SVG) — operation distribution ────────────────────────────
function OssDonutChart({ data }: { data: { operation: string; percentage: number; calls: number }[] }) {
  const r = 48; const cx = 64; const cy = 64;
  const circ = 2 * Math.PI * r;
  let cum = 0;
  const segs = data.map((item, i) => {
    const dash = (item.percentage / 100) * circ;
    const rot = (cum / 100) * 360 - 90;
    cum += item.percentage;
    return { dash, rot, color: CHART_COLORS[i % CHART_COLORS.length], ...item };
  });
  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg width={128} height={128} viewBox="0 0 128 128" style={{ flexShrink: 0 }}>
        {segs.map((s, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={16}
            strokeDasharray={`${s.dash} ${circ - s.dash}`} transform={`rotate(${s.rot} ${cx} ${cy})`} />
        ))}
        <circle cx={cx} cy={cy} r={r - 16} fill="white" />
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={20} fontWeight={700} fill="#1d1d1f">{data.length}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="#a8a29e">操作</text>
      </svg>
      <div style={{ flex: 1, minWidth: 0 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
            <span style={{ flex: 1, fontSize: 12, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.operation}</span>
            <span style={{ fontSize: 12, fontWeight: 600, width: 38, textAlign: 'right' }}>{item.percentage}%</span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', width: 44, textAlign: 'right' }}>{item.calls}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── OSS LineChart (SVG) — calls trend ────────────────────────────────────────
function OssLineChart({ data }: { data: { date: string; calls: number }[] }) {
  if (data.length < 2) return <div style={{ fontSize: 12, color: 'var(--gray-400)', textAlign: 'center', padding: 20 }}>数据不足，至少需要 2 天</div>;
  const W = 360; const H = 130; const pL = 42; const pR = 8; const pT = 10; const pB = 26;
  const cW = W - pL - pR; const cH = H - pT - pB;
  const maxVal = Math.max(...data.map(d => d.calls));
  const n = data.length;
  const xP = (i: number) => pL + (i / (n - 1)) * cW;
  const yP = (v: number) => pT + cH - (v / maxVal) * cH;
  const pts = data.map((d, i) => `${xP(i)},${yP(d.calls)}`).join(' ');
  const yTicks = [0, 0.5, 1].map(r => ({ v: maxVal * r, y: yP(maxVal * r) }));
  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pL} y1={t.y} x2={W - pR} y2={t.y} stroke="#f5f5f4" strokeWidth={1} />
            <text x={pL - 4} y={t.y + 4} textAnchor="end" fontSize={9} fill="#a8a29e">{Math.round(t.v)}</text>
          </g>
        ))}
        <polyline points={pts} fill="none" stroke="#4096FF" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((d, i) => (
          <g key={i}>
            <circle cx={xP(i)} cy={yP(d.calls)} r={3} fill="#4096FF" />
            <text x={xP(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="#a8a29e">{d.date}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

// ── ASR DonutChart (SVG) — operation distribution（紫色色调） ─────────────────
function AsrDonutChart({ data }: { data: { operation: string; percentage: number; calls: number }[] }) {
  const ASR_COLORS = ['#722ED1', '#9254DE', '#B37FEB', '#D3ADF7', '#EFDBFF'];
  const r = 48; const cx = 64; const cy = 64;
  const circ = 2 * Math.PI * r;
  let cum = 0;
  const segs = data.map((item, i) => {
    const dash = (item.percentage / 100) * circ;
    const rot = (cum / 100) * 360 - 90;
    cum += item.percentage;
    return { dash, rot, color: ASR_COLORS[i % ASR_COLORS.length], ...item };
  });
  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg width={128} height={128} viewBox="0 0 128 128" style={{ flexShrink: 0 }}>
        {segs.map((s, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={16}
            strokeDasharray={`${s.dash} ${circ - s.dash}`} transform={`rotate(${s.rot} ${cx} ${cy})`} />
        ))}
        <circle cx={cx} cy={cy} r={r - 16} fill="white" />
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize={20} fontWeight={700} fill="#1d1d1f">{data.length}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="#a8a29e">操作</text>
      </svg>
      <div style={{ flex: 1, minWidth: 0 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: ASR_COLORS[i % ASR_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
            <span style={{ flex: 1, fontSize: 12, color: 'var(--gray-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.operation}</span>
            <span style={{ fontSize: 12, fontWeight: 600, width: 38, textAlign: 'right' }}>{item.percentage}%</span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)', width: 44, textAlign: 'right' }}>{item.calls}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── ASR LineChart (SVG) — calls trend（紫色） ─────────────────────────────────
function AsrLineChart({ data }: { data: { date: string; calls: number }[] }) {
  if (data.length < 2) return <div style={{ fontSize: 12, color: 'var(--gray-400)', textAlign: 'center', padding: 20 }}>数据不足，至少需要 2 天</div>;
  const W = 360; const H = 130; const pL = 42; const pR = 8; const pT = 10; const pB = 26;
  const cW = W - pL - pR; const cH = H - pT - pB;
  const maxVal = Math.max(...data.map(d => d.calls));
  const n = data.length;
  const xP = (i: number) => pL + (i / (n - 1)) * cW;
  const yP = (v: number) => pT + cH - (v / maxVal) * cH;
  const pts = data.map((d, i) => `${xP(i)},${yP(d.calls)}`).join(' ');
  const yTicks = [0, 0.5, 1].map(r => ({ v: maxVal * r, y: yP(maxVal * r) }));
  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pL} y1={t.y} x2={W - pR} y2={t.y} stroke="#f5f5f4" strokeWidth={1} />
            <text x={pL - 4} y={t.y + 4} textAnchor="end" fontSize={9} fill="#a8a29e">{Math.round(t.v)}</text>
          </g>
        ))}
        <polyline points={pts} fill="none" stroke="#722ED1" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((d, i) => (
          <g key={i}>
            <circle cx={xP(i)} cy={yP(d.calls)} r={3} fill="#722ED1" />
            <text x={xP(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="#a8a29e">{d.date}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

// ── TikHubConfigTab ──────────────────────────────────────────────────────────
function TikHubConfigTab() {
  const [stats, setStats] = useState<TikHubStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [keys, setKeys] = useState<TikHubKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm] = Form.useForm<{ label: string; api_key: string; base_url: string; max_concurrent: number; max_users: number }>();
  const [editKey, setEditKey] = useState<TikHubKey | null>(null);
  const [editForm] = Form.useForm<{ label: string; max_concurrent: number; max_users: number }>();
  const [activePanel, setActivePanel] = useState<'keys' | 'endpoints' | 'users'>('keys');
  const [endpoints, setEndpoints] = useState<TikHubEndpointDetail[]>([]);
  const [users, setUsers] = useState<TikHubUserRank[]>([]);

  function reloadStats() {
    setStatsLoading(true);
    getTikHubStats().then(setStats).catch(() => message.error('加载统计失败')).finally(() => setStatsLoading(false));
  }
  function reloadKeys() {
    setKeysLoading(true);
    getTikHubKeys().then(setKeys).catch(() => message.error('加载 Key 列表失败')).finally(() => setKeysLoading(false));
  }
  function reloadEndpoints() {
    getTikHubEndpoints().then(setEndpoints).catch(() => {});
  }
  function reloadUsers() {
    getTikHubUsers().then(setUsers).catch(() => {});
  }

  useEffect(() => { reloadStats(); reloadKeys(); }, []);

  useEffect(() => {
    if (activePanel === 'endpoints' && endpoints.length === 0) reloadEndpoints();
    if (activePanel === 'users' && users.length === 0) reloadUsers();
  }, [activePanel]);

  async function handleAdd(v: { label: string; api_key: string; base_url: string; max_concurrent: number; max_users: number }) {
    try { await createTikHubKey(v); message.success('Key 已添加'); setAddOpen(false); addForm.resetFields(); reloadKeys(); reloadStats(); }
    catch (e: unknown) { message.error(e instanceof Error ? e.message : '添加失败'); }
  }
  async function handleEdit(v: { label: string; max_concurrent: number; max_users: number }) {
    if (!editKey) return;
    try { await updateTikHubKey(editKey.id, v); message.success('更新成功'); setEditKey(null); editForm.resetFields(); reloadKeys(); }
    catch (e: unknown) { message.error(e instanceof Error ? e.message : '更新失败'); }
  }
  async function handleTest(id: number) {
    setTestingId(id);
    try {
      const r = await testTikHubKey(id);
      if (r.status === 'ok') { message.success(`连通正常 ${r.latency_ms}ms`); reloadKeys(); }
      else { message.error(`测试失败: ${r.error ?? '未知错误'}`); }
    } catch { message.error('测试请求失败'); }
    finally { setTestingId(null); }
  }
  async function handleDelete(id: number) {
    try { await deleteTikHubKey(id); message.success('已删除'); reloadKeys(); reloadStats(); }
    catch (e: unknown) { message.error(e instanceof Error ? e.message : '删除失败'); }
  }
  async function handleToggle(k: TikHubKey) {
    try {
      if (k.status === 'active') await disableTikHubKey(k.id);
      else await enableTikHubKey(k.id);
      message.success('操作成功'); reloadKeys(); reloadStats();
    } catch (e: unknown) { message.error(e instanceof Error ? e.message : '操作失败'); }
  }
  function openEdit(k: TikHubKey) {
    editForm.setFieldsValue({ label: k.label, max_concurrent: k.max_concurrent, max_users: k.max_users });
    setEditKey(k);
  }

  const ov = stats?.overview;
  const statCards = [
    { label: '总调用', value: ov?.total_calls?.toLocaleString() ?? '0', color: '#4096FF' },
    { label: '今日调用', value: ov?.today_calls?.toLocaleString() ?? '0', color: '#52C41A' },
    { label: '平均延迟', value: ov?.avg_latency_ms != null ? `${ov.avg_latency_ms}ms` : '—', color: '#FF7A45' },
    { label: '活跃 Key', value: ov ? `${ov.active_keys} / ${ov.total_keys}` : '—', color: '#9254DE' },
  ];

  return (
    <div>
      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        {statCards.map((c, i) => (
          <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '16px 20px' }}>
            <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color }}>{statsLoading ? '...' : c.value}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>接口分布</div>
          {(stats?.endpoints?.length ?? 0) > 0 ? <TikHubDonutChart data={stats!.endpoints} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>近 7 天趋势</div>
          {(stats?.trend?.length ?? 0) >= 2 ? <TikHubLineChart data={stats!.trend} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid var(--border)', marginBottom: 16 }}>
        {([
          { key: 'keys' as const, label: 'Key 管理' },
          { key: 'endpoints' as const, label: '接口统计' },
          { key: 'users' as const, label: '用户排行' },
        ]).map(tab => (
          <div key={tab.key} onClick={() => setActivePanel(tab.key)}
            style={{ padding: '10px 24px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
              color: activePanel === tab.key ? 'var(--brand)' : 'var(--text-secondary)',
              borderBottom: activePanel === tab.key ? '2px solid var(--brand)' : 'none', marginBottom: -2 }}>
            {tab.label}
          </div>
        ))}
        <div style={{ flex: 1 }} />
        {activePanel === 'keys' && (
          <button className="btn btn-primary btn-sm" style={{ alignSelf: 'center' }}
            onClick={() => { addForm.resetFields(); addForm.setFieldsValue({ base_url: 'https://api.tikhub.io', max_concurrent: 5, max_users: 10 }); setAddOpen(true); }}>+ 新增 Key</button>
        )}
      </div>

      {/* Key Management */}
      {activePanel === 'keys' && (
        keysLoading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : keys.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无 TikHub Key</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['#', '标签', 'API Key', '状态', '并发', '今日', '累计', '上次测试', '操作'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: h === '操作' ? 'right' : 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keys.map((k, idx) => (
                  <tr key={k.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{idx + 1}</td>
                    <td style={{ padding: '10px 12px' }}>{k.label || '—'}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k.api_key}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                        <span style={{ width: 7, height: 7, borderRadius: '50%', display: 'inline-block', background: k.status === 'active' ? 'var(--success)' : 'var(--gray-300)' }} />
                        {k.status === 'active' ? '启用' : '停用'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>{k.active_requests}/{k.max_concurrent}</td>
                    <td style={{ padding: '10px 12px' }}>{k.today_calls}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{k.total_calls}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>
                      {k.last_tested_at ? `${fmtTime(k.last_tested_at)}${k.last_latency_ms != null ? ` · ${k.last_latency_ms}ms` : ''}` : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-ghost btn-sm" disabled={testingId === k.id} onClick={() => handleTest(k.id)}>
                          {testingId === k.id ? '测试中...' : '测试'}
                        </button>
                        <button className="btn btn-ghost btn-sm" onClick={() => openEdit(k)}>编辑</button>
                        <Popconfirm title={k.status === 'active' ? '确认停用？' : '确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(k)}>
                          <button className="btn btn-ghost btn-sm">{k.status === 'active' ? '停用' : '启用'}</button>
                        </Popconfirm>
                        <Popconfirm title="确认删除？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDelete(k.id)}>
                          <button className="btn btn-danger-ghost btn-sm">删除</button>
                        </Popconfirm>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* Endpoint Stats */}
      {activePanel === 'endpoints' && (
        endpoints.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无接口统计数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['接口', '平台', '调用次数', '占比', '平均延迟', '成功率'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {endpoints.map((ep, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px' }}>{ep.endpoint}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-500)' }}>{ep.platform || '—'}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{ep.calls}</td>
                    <td style={{ padding: '10px 12px' }}>{ep.percentage}%</td>
                    <td style={{ padding: '10px 12px' }}>{ep.avg_latency_ms != null ? `${ep.avg_latency_ms}ms` : '—'}</td>
                    <td style={{ padding: '10px 12px' }}>{ep.success_rate != null ? `${(ep.success_rate * 100).toFixed(1)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* User Ranking */}
      {activePanel === 'users' && (
        users.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无用户调用数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['排名', '用户', '角色', '调用次数', '最近调用'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{i + 1}</td>
                    <td style={{ padding: '10px 12px' }}>{u.username || `user_${u.user_id}`}</td>
                    <td style={{ padding: '10px 12px' }}><span className="badge badge-gray">{u.role}</span></td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{u.calls}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{fmtTime(u.last_called_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* Add Key Modal */}
      <Modal title="新增 TikHub Key" open={addOpen} onCancel={() => { setAddOpen(false); addForm.resetFields(); }} onOk={() => addForm.submit()} okText="创建" cancelText="取消">
        <Form form={addForm} layout="vertical" onFinish={handleAdd} style={{ marginTop: 16 }}>
          <Form.Item label="标签" name="label"><Input placeholder="如 tikhub-main" /></Form.Item>
          <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: '请输入 API Key' }]}><Input.Password placeholder="sk-..." /></Form.Item>
          <Form.Item label="Base URL" name="base_url"><Input placeholder="https://api.tikhub.io" /></Form.Item>
          <Form.Item label="最大并发" name="max_concurrent"><Input type="number" min={1} max={50} /></Form.Item>
          <Form.Item label="最大用户数" name="max_users"><Input type="number" min={1} max={100} /></Form.Item>
        </Form>
      </Modal>

      {/* Edit Key Modal */}
      <Modal title="编辑 TikHub Key" open={!!editKey} onCancel={() => { setEditKey(null); editForm.resetFields(); }} onOk={() => editForm.submit()} okText="保存" cancelText="取消">
        <Form form={editForm} layout="vertical" onFinish={handleEdit} style={{ marginTop: 16 }}>
          <Form.Item label="标签" name="label"><Input /></Form.Item>
          <Form.Item label="最大并发" name="max_concurrent"><Input type="number" min={1} max={50} /></Form.Item>
          <Form.Item label="最大用户数" name="max_users"><Input type="number" min={1} max={100} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ── OssConfigTab ──────────────────────────────────────────────────────────────
interface OssConfig {
  access_key_id?: string;
  bucket?: string;
  endpoint?: string;
  region?: string;
}

interface OssCreateFormData {
  label: string;
  access_key_id: string;
  api_key: string; // AccessKey Secret
  endpoint: string;
  bucket: string;
  region?: string;
  weight?: number;
}

interface OssEditFormData {
  label: string;
  access_key_id: string;
  api_key?: string; // 留空 = 不修改
  endpoint: string;
  bucket: string;
  region?: string;
  weight?: number;
}

const OSS_ENDPOINTS = [
  { value: 'oss-cn-hangzhou.aliyuncs.com',   label: '华东1(杭州)' },
  { value: 'oss-cn-shanghai.aliyuncs.com',   label: '华东2(上海)' },
  { value: 'oss-cn-beijing.aliyuncs.com',    label: '华北2(北京)' },
  { value: 'oss-cn-zhangjiakou.aliyuncs.com', label: '华北3(张家口)' },
  { value: 'oss-cn-huhehaote.aliyuncs.com',  label: '华北5(呼和浩特)' },
  { value: 'oss-cn-qingdao.aliyuncs.com',    label: '华北1(青岛)' },
  { value: 'oss-cn-shenzhen.aliyuncs.com',   label: '华南1(深圳)' },
  { value: 'oss-cn-heyuan.aliyuncs.com',     label: '华南2(河源)' },
  { value: 'oss-cn-chengdu.aliyuncs.com',    label: '西南1(成都)' },
];

export function OssConfigTab() {
  const [data, setData] = useState<PagedData<ServiceCredential> | null>(null);
  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editCred, setEditCred] = useState<ServiceCredential | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [addForm] = Form.useForm<OssCreateFormData>();
  const [editForm] = Form.useForm<OssEditFormData>();

  // OSS 统计相关 state（对齐 TikHub Tab）
  const [stats, setStats] = useState<OssStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [activePanel, setActivePanel] = useState<'credentials' | 'operations' | 'users'>('credentials');
  const [operations, setOperations] = useState<OssOperationDetail[]>([]);
  const [users, setUsers] = useState<OssUserDetail[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    getCredentials('oss')
      .then(setData)
      .catch(() => message.error('加载 OSS 凭证失败'))
      .finally(() => setLoading(false));
  }, []);

  const reloadStats = useCallback(() => {
    setStatsLoading(true);
    getOssStats()
      .then(setStats)
      .catch(() => message.error('加载 OSS 统计失败'))
      .finally(() => setStatsLoading(false));
  }, []);

  useEffect(() => {
    load();
    reloadStats();
  }, [load, reloadStats]);

  const handlePanelSwitch = useCallback((tab: 'credentials' | 'operations' | 'users') => {
    setActivePanel(tab);
    if (tab === 'operations' && operations.length === 0) {
      getOssOperations().then(setOperations).catch(() => { /* error handled in api layer */ });
    }
    if (tab === 'users' && users.length === 0) {
      getOssUsers().then(res => setUsers(res.items ?? [])).catch(() => { /* 同上 */ });
    }
  }, [operations.length, users.length]);

  async function handleAdd(v: OssCreateFormData) {
    setFormLoading(true);
    try {
      await createCredential({
        provider: 'oss',
        label: v.label,
        api_key: v.api_key,
        weight: v.weight ?? 10,
        config: {
          access_key_id: v.access_key_id,
          bucket: v.bucket,
          endpoint: v.endpoint,
          ...(v.region ? { region: v.region } : {}),
        },
      });
      message.success('OSS 凭证已添加');
      setAddOpen(false);
      addForm.resetFields();
      load();
      reloadStats();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleEdit(v: OssEditFormData) {
    if (!editCred) return;
    setFormLoading(true);
    try {
      const payload: UpdateCredentialRequest = {
        label: v.label,
        weight: v.weight,
        config: {
          access_key_id: v.access_key_id,
          bucket: v.bucket,
          endpoint: v.endpoint,
          ...(v.region ? { region: v.region } : {}),
        },
      };
      if (v.api_key) {
        payload.api_key = v.api_key;
      }
      await updateCredential(editCred.id, payload);
      message.success('更新成功');
      setEditCred(null);
      load();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleTest(id: number) {
    setTestingId(id);
    try {
      const r = await testOssCredential(id);
      if (r.status === 'ok') {
        message.success(`连通正常 ${r.latency_ms}ms · ${r.bucket}`);
        load();
        reloadStats();
      } else {
        message.error(`失败：${r.error ?? '未知错误'}`);
      }
    } catch {
      message.error('测试请求失败');
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteCredential(id);
      message.success('已删除');
      load();
      reloadStats();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleToggle(c: ServiceCredential) {
    try {
      c.status === 'enabled' ? await disableCredential(c.id) : await enableCredential(c.id);
      message.success('操作成功');
      load();
      reloadStats();
    } catch {
      message.error('操作失败');
    }
  }

  function openEdit(c: ServiceCredential) {
    const cfg = (c.config ?? {}) as OssConfig;
    editForm.setFieldsValue({
      label: c.label,
      access_key_id: cfg.access_key_id ?? '',
      bucket: cfg.bucket ?? '',
      endpoint: cfg.endpoint ?? '',
      region: cfg.region ?? '',
      weight: c.weight,
      api_key: '',
    });
    setEditCred(c);
  }

  const total = data?.pagination.total ?? 0;
  const statusColor = (s: string) => s === 'enabled' ? 'var(--success)' : 'var(--gray-300)';
  const statusLabel = (s: string) => s === 'enabled' ? '启用' : s === 'cooldown' ? '冷却' : '停用';

  // 4 张统计卡（对齐 TikHub）
  const ov = stats?.overview;
  const statCards = [
    { label: '总调用',  value: ov?.total_calls?.toLocaleString() ?? '0', color: '#4096FF' },
    { label: '今日调用', value: ov?.today_calls?.toLocaleString() ?? '0', color: '#52C41A' },
    { label: '平均延迟', value: ov?.avg_latency_ms != null ? `${ov.avg_latency_ms}ms` : '—', color: '#FF7A45' },
    { label: '活跃凭证', value: ov ? `${ov.active_keys} / ${ov.total_keys}` : '—', color: '#9254DE' },
  ];

  return (
    <div>
      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        {statCards.map((c, i) => (
          <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '16px 20px' }}>
            <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color }}>{statsLoading ? '...' : c.value}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>操作分布</div>
          {(stats?.operations?.length ?? 0) > 0 ? <OssDonutChart data={stats!.operations} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>近 7 天趋势</div>
          {(stats?.trend?.length ?? 0) >= 2 ? <OssLineChart data={stats!.trend} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid var(--border)', marginBottom: 16 }}>
        {([
          { key: 'credentials' as const, label: '凭证管理' },
          { key: 'operations' as const, label: '操作统计' },
          { key: 'users' as const,       label: '用户排行' },
        ]).map(tab => (
          <div key={tab.key} onClick={() => handlePanelSwitch(tab.key)}
            style={{ padding: '10px 24px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
              color: activePanel === tab.key ? 'var(--brand)' : 'var(--text-secondary)',
              borderBottom: activePanel === tab.key ? '2px solid var(--brand)' : 'none', marginBottom: -2 }}>
            {tab.label}
          </div>
        ))}
        <div style={{ flex: 1 }} />
        {activePanel === 'credentials' && (
          <button className="btn btn-primary btn-sm" style={{ alignSelf: 'center' }}
            onClick={() => { addForm.resetFields(); addForm.setFieldsValue({ weight: 10 }); setAddOpen(true); }}>+ 新增 OSS 凭证</button>
        )}
      </div>

      {/* Credential Management (default sub-tab) */}
      {activePanel === 'credentials' && (
        <>
          <div style={{ marginBottom: 12 }}>
            <span className="filter-count">共 {total} 条</span>
          </div>
          {loading ? (
            <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
          ) : !data || data.items.length === 0 ? (
            <div className="empty-state"><div className="empty-state-text">暂无 OSS 凭证</div></div>
          ) : (
            <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['#', '备注', 'AccessKey ID', 'Bucket', 'Endpoint', '状态', '权重', '上次测试', '操作'].map(h => (
                      <th key={h} style={{ padding: '10px 12px', textAlign: h === '操作' ? 'right' : 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c, idx) => {
                    const cfg = (c.config ?? {}) as OssConfig;
                    const akId = cfg.access_key_id ?? '';
                    const maskedAk = akId.length > 8 ? `${akId.slice(0, 8)}****` : (akId || '—');
                    const testTime = c.last_tested_at
                      ? `${fmtTime(c.last_tested_at)}${c.last_latency_ms != null ? ` · ${c.last_latency_ms}ms` : ''}`
                      : '—';
                    return (
                      <tr key={c.id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{idx + 1}</td>
                        <td style={{ padding: '10px 12px' }}>{c.label || '—'}</td>
                        <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{maskedAk}</td>
                        <td style={{ padding: '10px 12px' }}>{cfg.bucket || '—'}</td>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{cfg.endpoint || '—'}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                            <span style={{ width: 7, height: 7, borderRadius: '50%', display: 'inline-block', background: statusColor(c.status) }} />
                            {statusLabel(c.status)}
                          </span>
                        </td>
                        <td style={{ padding: '10px 12px' }}>{c.weight}</td>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{testTime}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                            <button className="btn btn-ghost btn-sm" disabled={testingId === c.id} onClick={() => handleTest(c.id)}>
                              {testingId === c.id ? '测试中...' : '测试'}
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={() => openEdit(c)}>编辑</button>
                            <Popconfirm title={c.status === 'enabled' ? '确认停用？' : '确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(c)}>
                              <button className="btn btn-ghost btn-sm">{c.status === 'enabled' ? '停用' : '启用'}</button>
                            </Popconfirm>
                            <Popconfirm title="确认删除该凭证？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDelete(c.id)}>
                              <button className="btn btn-danger-ghost btn-sm">删除</button>
                            </Popconfirm>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Operation Stats sub-tab */}
      {activePanel === 'operations' && (
        operations.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无操作统计数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['操作类型', '调用次数', '占比', '平均延迟', '成功率'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {operations.map((op, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px' }}>{op.operation}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{op.calls}</td>
                    <td style={{ padding: '10px 12px' }}>{op.percentage}%</td>
                    <td style={{ padding: '10px 12px' }}>{op.avg_latency_ms != null ? `${op.avg_latency_ms}ms` : '—'}</td>
                    <td style={{ padding: '10px 12px' }}>{op.success_rate != null ? `${(op.success_rate * 100).toFixed(1)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* User Ranking sub-tab */}
      {activePanel === 'users' && (
        users.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无用户调用数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['排名', '用户', '角色', '调用次数', '最近调用'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{i + 1}</td>
                    <td style={{ padding: '10px 12px' }}>{u.username || `user_${u.user_id}`}</td>
                    <td style={{ padding: '10px 12px' }}><span className="badge badge-gray">{u.role}</span></td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{u.calls}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{fmtTime(u.last_called_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* Add Modal */}
      <Modal title="新增 OSS 凭证" open={addOpen} onCancel={() => { setAddOpen(false); addForm.resetFields(); }} onOk={() => addForm.submit()} okText="创建" cancelText="取消" confirmLoading={formLoading}>
        <Form form={addForm} layout="vertical" onFinish={handleAdd} style={{ marginTop: 16 }}>
          <Form.Item label="备注" name="label" rules={[{ required: true, message: '请输入备注' }]}>
            <Input placeholder="如 杭州生产环境" />
          </Form.Item>
          <Form.Item label="AccessKey ID" name="access_key_id" rules={[{ required: true, message: '请输入 AccessKey ID' }]}>
            <Input placeholder="LTAI..." />
          </Form.Item>
          <Form.Item label="AccessKey Secret" name="api_key" rules={[{ required: true, message: '请输入 AccessKey Secret' }]}>
            <Input.Password placeholder="test-secret-..." />
          </Form.Item>
          <Form.Item label="Endpoint" name="endpoint" rules={[{ required: true, message: '请选择或输入 Endpoint' }]}>
            <Input placeholder="如 oss-cn-hangzhou.aliyuncs.com" list="oss-endpoint-list" />
          </Form.Item>
          <datalist id="oss-endpoint-list">
            {OSS_ENDPOINTS.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}
          </datalist>
          <Form.Item label="Bucket" name="bucket" rules={[{ required: true, message: '请输入 Bucket' }]}>
            <Input placeholder="如 mcn-production" />
          </Form.Item>
          <Form.Item label="Region（选填）" name="region">
            <Input placeholder="如 cn-hangzhou（一般可从 endpoint 推断）" />
          </Form.Item>
          <Form.Item label="权重" name="weight" initialValue={10}>
            <Input type="number" min={1} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal title="编辑 OSS 凭证" open={!!editCred} onCancel={() => { setEditCred(null); editForm.resetFields(); }} onOk={() => editForm.submit()} okText="保存" cancelText="取消" confirmLoading={formLoading}>
        <Form form={editForm} layout="vertical" onFinish={handleEdit} style={{ marginTop: 16 }}>
          <Form.Item label="备注" name="label" rules={[{ required: true, message: '请输入备注' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="AccessKey ID" name="access_key_id" rules={[{ required: true, message: '请输入 AccessKey ID' }]}>
            <Input placeholder="LTAI..." />
          </Form.Item>
          <Form.Item label="AccessKey Secret（留空 = 不修改）" name="api_key">
            <Input.Password placeholder="输入新 Secret 以轮换密钥" />
          </Form.Item>
          <Form.Item label="Endpoint" name="endpoint" rules={[{ required: true, message: '请选择或输入 Endpoint' }]}>
            <Input placeholder="如 oss-cn-hangzhou.aliyuncs.com" list="oss-endpoint-list" />
          </Form.Item>
          <Form.Item label="Bucket" name="bucket" rules={[{ required: true, message: '请输入 Bucket' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Region（选填）" name="region">
            <Input placeholder="如 cn-hangzhou" />
          </Form.Item>
          <Form.Item label="权重" name="weight">
            <Input type="number" min={1} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ── AsrConfigTab ──────────────────────────────────────────────────────────────
interface AsrConfig {
  app_key?: string;
  region?: string;
}

interface AsrCreateFormData {
  label: string;
  app_key: string;
  access_key_id: string;
  access_key_secret: string;
  region: string;
  weight?: number;
}

interface AsrEditFormData {
  label: string;
  app_key: string;
  access_key_id?: string;
  access_key_secret?: string; // 留空 = 不修改
  region: string;
  weight?: number;
}

const ASR_REGIONS = [
  { value: 'cn-shanghai', label: '华东2(上海)' },
  { value: 'cn-beijing',  label: '华北2(北京)' },
  { value: 'cn-shenzhen', label: '华南1(深圳)' },
];

export function AsrConfigTab() {
  const [data, setData] = useState<PagedData<ServiceCredential> | null>(null);
  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editCred, setEditCred] = useState<ServiceCredential | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [addForm] = Form.useForm<AsrCreateFormData>();
  const [editForm] = Form.useForm<AsrEditFormData>();

  // ASR 统计相关 state（对齐 OSS Tab）
  const [stats, setStats] = useState<AsrStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [activePanel, setActivePanel] = useState<'credentials' | 'operations' | 'users'>('credentials');
  const [operations, setOperations] = useState<AsrOperationDetail[]>([]);
  const [users, setUsers] = useState<AsrUserDetail[]>([]);

  const load = useCallback(() => {
    setLoading(true);
    getCredentials('asr')
      .then(setData)
      .catch(() => message.error('加载 ASR 凭证失败'))
      .finally(() => setLoading(false));
  }, []);

  const reloadStats = useCallback(() => {
    setStatsLoading(true);
    getAsrStats()
      .then(setStats)
      .catch(() => message.error('加载 ASR 统计失败'))
      .finally(() => setStatsLoading(false));
  }, []);

  useEffect(() => {
    load();
    reloadStats();
  }, [load, reloadStats]);

  const handlePanelSwitch = useCallback((tab: 'credentials' | 'operations' | 'users') => {
    setActivePanel(tab);
    if (tab === 'operations' && operations.length === 0) {
      getAsrOperations().then(setOperations).catch(() => { /* error handled in api layer */ });
    }
    if (tab === 'users' && users.length === 0) {
      getAsrUsers().then(res => setUsers(res.items ?? [])).catch(() => { /* 同上 */ });
    }
  }, [operations.length, users.length]);

  async function handleAdd(v: AsrCreateFormData) {
    setFormLoading(true);
    try {
      await createCredential({
        provider: 'asr',
        label: v.label,
        api_key: `${v.access_key_id}\n${v.access_key_secret}`, // secret_enc 格式：id\nsecret
        weight: v.weight ?? 10,
        config: {
          app_key: v.app_key,
          region: v.region,
        },
      });
      message.success('ASR 凭证已添加');
      setAddOpen(false);
      addForm.resetFields();
      load();
      reloadStats();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleEdit(v: AsrEditFormData) {
    if (!editCred) return;
    setFormLoading(true);
    try {
      const payload: UpdateCredentialRequest = {
        label: v.label,
        weight: v.weight,
        config: {
          app_key: v.app_key,
          region: v.region,
        },
      };
      // 任一字段非空 = 轮换密钥（拼接为 id\nsecret）
      if (v.access_key_id && v.access_key_secret) {
        payload.api_key = `${v.access_key_id}\n${v.access_key_secret}`;
      } else if (v.access_key_id || v.access_key_secret) {
        message.warning('轮换密钥时 AccessKey ID 和 Secret 必须同时填写');
        setFormLoading(false);
        return;
      }
      await updateCredential(editCred.id, payload);
      message.success('更新成功');
      setEditCred(null);
      load();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleTest(id: number) {
    setTestingId(id);
    try {
      const { testOssCredential: testCred } = await import('../../api/credentials');
      const r = await testCred(id);
      if (r.status === 'ok') {
        message.success(`连通正常 ${r.latency_ms}ms`);
        load();
        reloadStats();
      } else {
        message.error(`失败：${r.error ?? '未知错误'}`);
      }
    } catch {
      message.error('测试请求失败');
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteCredential(id);
      message.success('已删除');
      load();
      reloadStats();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleToggle(c: ServiceCredential) {
    try {
      c.status === 'enabled' ? await disableCredential(c.id) : await enableCredential(c.id);
      message.success('操作成功');
      load();
      reloadStats();
    } catch {
      message.error('操作失败');
    }
  }

  function openEdit(c: ServiceCredential) {
    const cfg = (c.config ?? {}) as AsrConfig;
    editForm.setFieldsValue({
      label: c.label,
      app_key: cfg.app_key ?? '',
      region: cfg.region ?? 'cn-shanghai',
      weight: c.weight,
      access_key_id: '',
      access_key_secret: '',
    });
    setEditCred(c);
  }

  const total = data?.pagination.total ?? 0;
  const statusColor = (s: string) => s === 'enabled' ? 'var(--success)' : 'var(--gray-300)';
  const statusLabel = (s: string) => s === 'enabled' ? '启用' : s === 'cooldown' ? '冷却' : '停用';

  // 4 张统计卡（紫色色调）
  const ov = stats?.overview;
  const statCards = [
    { label: '总调用',  value: ov?.total_calls?.toLocaleString() ?? '0', color: '#722ED1' },
    { label: '今日调用', value: ov?.today_calls?.toLocaleString() ?? '0', color: '#9254DE' },
    { label: '平均延迟', value: ov?.avg_latency_ms != null ? `${ov.avg_latency_ms}ms` : '—', color: '#FF7A45' },
    { label: '活跃凭证', value: ov ? `${ov.active_keys} / ${ov.total_keys}` : '—', color: '#37C2C2' },
  ];

  return (
    <div>
      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        {statCards.map((c, i) => (
          <div key={i} style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '16px 20px' }}>
            <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color }}>{statsLoading ? '...' : c.value}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>操作分布</div>
          {(stats?.operations?.length ?? 0) > 0 ? <AsrDonutChart data={stats!.operations} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>近 7 天趋势</div>
          {(stats?.trend?.length ?? 0) >= 2 ? <AsrLineChart data={stats!.trend} /> : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>}
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid var(--border)', marginBottom: 16 }}>
        {([
          { key: 'credentials' as const, label: '凭证管理' },
          { key: 'operations' as const, label: '操作统计' },
          { key: 'users' as const,       label: '用户排行' },
        ]).map(tab => (
          <div key={tab.key} onClick={() => handlePanelSwitch(tab.key)}
            style={{ padding: '10px 24px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
              color: activePanel === tab.key ? 'var(--brand)' : 'var(--text-secondary)',
              borderBottom: activePanel === tab.key ? '2px solid var(--brand)' : 'none', marginBottom: -2 }}>
            {tab.label}
          </div>
        ))}
        <div style={{ flex: 1 }} />
        {activePanel === 'credentials' && (
          <button className="btn btn-primary btn-sm" style={{ alignSelf: 'center' }}
            onClick={() => { addForm.resetFields(); addForm.setFieldsValue({ weight: 10, region: 'cn-shanghai' }); setAddOpen(true); }}>+ 新增 ASR 凭证</button>
        )}
      </div>

      {/* Credential Management sub-tab */}
      {activePanel === 'credentials' && (
        <>
          <div style={{ marginBottom: 12 }}>
            <span className="filter-count">共 {total} 条</span>
          </div>
          {loading ? (
            <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
          ) : !data || data.items.length === 0 ? (
            <div className="empty-state"><div className="empty-state-text">暂无 ASR 凭证</div></div>
          ) : (
            <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['#', '备注', 'AppKey', 'Region', '状态', '权重', '上次测试', '操作'].map(h => (
                      <th key={h} style={{ padding: '10px 12px', textAlign: h === '操作' ? 'right' : 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c, idx) => {
                    const cfg = (c.config ?? {}) as AsrConfig;
                    const appKey = cfg.app_key ?? '';
                    const maskedAppKey = appKey.length > 8 ? `${appKey.slice(0, 8)}****` : (appKey || '—');
                    const testTime = c.last_tested_at
                      ? `${fmtTime(c.last_tested_at)}${c.last_latency_ms != null ? ` · ${c.last_latency_ms}ms` : ''}`
                      : '—';
                    return (
                      <tr key={c.id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{idx + 1}</td>
                        <td style={{ padding: '10px 12px' }}>{c.label || '—'}</td>
                        <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{maskedAppKey}</td>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{cfg.region || '—'}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                            <span style={{ width: 7, height: 7, borderRadius: '50%', display: 'inline-block', background: statusColor(c.status) }} />
                            {statusLabel(c.status)}
                          </span>
                        </td>
                        <td style={{ padding: '10px 12px' }}>{c.weight}</td>
                        <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{testTime}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                            <button className="btn btn-ghost btn-sm" disabled={testingId === c.id} onClick={() => handleTest(c.id)}>
                              {testingId === c.id ? '测试中...' : '测试'}
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={() => openEdit(c)}>编辑</button>
                            <Popconfirm title={c.status === 'enabled' ? '确认停用？' : '确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(c)}>
                              <button className="btn btn-ghost btn-sm">{c.status === 'enabled' ? '停用' : '启用'}</button>
                            </Popconfirm>
                            <Popconfirm title="确认删除该凭证？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDelete(c.id)}>
                              <button className="btn btn-danger-ghost btn-sm">删除</button>
                            </Popconfirm>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Operation Stats sub-tab */}
      {activePanel === 'operations' && (
        operations.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无操作统计数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['操作类型', '调用次数', '占比', '平均延迟', '成功率'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {operations.map((op, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px' }}>{op.operation}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{op.calls}</td>
                    <td style={{ padding: '10px 12px' }}>{op.percentage}%</td>
                    <td style={{ padding: '10px 12px' }}>{op.avg_latency_ms != null ? `${op.avg_latency_ms}ms` : '—'}</td>
                    <td style={{ padding: '10px 12px' }}>{op.success_rate != null ? `${(op.success_rate * 100).toFixed(1)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* User Ranking sub-tab */}
      {activePanel === 'users' && (
        users.length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无用户调用数据</div></div>
        : <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['排名', '用户', '角色', '调用次数', '最近调用'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--gray-500)', fontWeight: 500, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-400)' }}>{i + 1}</td>
                    <td style={{ padding: '10px 12px' }}>{u.username || `user_${u.user_id}`}</td>
                    <td style={{ padding: '10px 12px' }}><span className="badge badge-gray">{u.role}</span></td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{u.calls}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--gray-500)', fontSize: 12 }}>{fmtTime(u.last_called_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      )}

      {/* Add Modal */}
      <Modal title="新增 ASR 凭证" open={addOpen} onCancel={() => { setAddOpen(false); addForm.resetFields(); }} onOk={() => addForm.submit()} okText="创建" cancelText="取消" confirmLoading={formLoading}>
        <Form form={addForm} layout="vertical" onFinish={handleAdd} style={{ marginTop: 16 }}>
          <Form.Item label="备注" name="label" rules={[{ required: true, message: '请输入备注' }]}>
            <Input placeholder="如 上海生产环境" />
          </Form.Item>
          <Form.Item label="AppKey" name="app_key" rules={[{ required: true, message: '请输入 AppKey' }]}>
            <Input placeholder="阿里云 ISI 项目 AppKey" />
          </Form.Item>
          <Form.Item label="AccessKey ID" name="access_key_id" rules={[{ required: true, message: '请输入 AccessKey ID' }]}>
            <Input placeholder="LTAI..." />
          </Form.Item>
          <Form.Item label="AccessKey Secret" name="access_key_secret" rules={[{ required: true, message: '请输入 AccessKey Secret' }]}>
            <Input.Password placeholder="AccessKey Secret" />
          </Form.Item>
          <Form.Item label="Region" name="region" rules={[{ required: true, message: '请选择 Region' }]}>
            <Select options={ASR_REGIONS} placeholder="选择区域" />
          </Form.Item>
          <Form.Item label="权重" name="weight" initialValue={10}>
            <Input type="number" min={1} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal title="编辑 ASR 凭证" open={!!editCred} onCancel={() => { setEditCred(null); editForm.resetFields(); }} onOk={() => editForm.submit()} okText="保存" cancelText="取消" confirmLoading={formLoading}>
        <Form form={editForm} layout="vertical" onFinish={handleEdit} style={{ marginTop: 16 }}>
          <Form.Item label="备注" name="label" rules={[{ required: true, message: '请输入备注' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="AppKey" name="app_key" rules={[{ required: true, message: '请输入 AppKey' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="AccessKey ID（轮换密钥时填）" name="access_key_id">
            <Input placeholder="留空 = 不修改" />
          </Form.Item>
          <Form.Item label="AccessKey Secret（轮换密钥时填）" name="access_key_secret">
            <Input.Password placeholder="留空 = 不修改（需与 ID 同时填写）" />
          </Form.Item>
          <Form.Item label="Region" name="region" rules={[{ required: true, message: '请选择 Region' }]}>
            <Select options={ASR_REGIONS} />
          </Form.Item>
          <Form.Item label="权重" name="weight">
            <Input type="number" min={1} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ── AiConfigTab ───────────────────────────────────────────────────────────────
function AiConfigTab() {
  const [providerFilter, setProviderFilter] = useState('全部');
  const [statusFilter,   setStatusFilter]   = useState('全部');
  const [timeRange,      setTimeRange]       = useState('近7天');

  const [statsData,    setStatsData]    = useState<AiStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    setStatsLoading(true);
    const { start_date, end_date } = getDateRange(timeRange);
    const params = {
      ...(providerFilter !== '全部' ? { provider: providerFilter } : {}),
      start_date,
      end_date,
    };
    getAiStats(params)
      .then(setStatsData)
      .catch(() => message.error('加载统计数据失败'))
      .finally(() => setStatsLoading(false));
  }, [providerFilter, timeRange]);

  const [keys,         setKeys]         = useState<AiKeyRecord[]>([]);
  const [keysLoading,  setKeysLoading]  = useState(false);
  const [models,       setModels]       = useState<AiModelItem[]>([]);
  const [modelsLoading,setModelsLoading]= useState(false);

  useEffect(() => {
    setKeysLoading(true);
    getAiKeys()
      .then(data => setKeys(data.items ?? []))
      .catch(() => message.error('加载 Key 列表失败'))
      .finally(() => setKeysLoading(false));
  }, []);

  useEffect(() => {
    setModelsLoading(true);
    getAiModels()
      .then(data => setModels(data.items ?? []))
      .catch(() => message.error('加载模型列表失败'))
      .finally(() => setModelsLoading(false));
  }, []);

  const [addKeyOpen, setAddKeyOpen] = useState(false);
  const [addKeyForm] = Form.useForm<{ label: string; provider: string; api_key: string; base_url: string; max_concurrent: number; remark?: string }>();

  const [editKey, setEditKey] = useState<AiKeyRecord | null>(null);
  const [editKeyForm] = Form.useForm<{ label: string; provider: string; api_key: string; base_url: string; max_concurrent: number }>();

  const [testingKeyId, setTestingKeyId] = useState<number | null>(null);

  const [testingModelId, setTestingModelId] = useState<number | null>(null);

  const [addModelOpen, setAddModelOpen] = useState(false);
  const [addModelForm] = Form.useForm<{ name: string; model_id: string; provider: string }>();


  const filteredKeys = keys.filter(k => {
    if (providerFilter !== '全部' && k.provider !== providerFilter) return false;
    if (statusFilter === '正常'   && (k.status === 'disabled' || !k.last_tested_at))  return false;
    if (statusFilter === '未测试' && (k.status === 'disabled' || !!k.last_tested_at)) return false;
    if (statusFilter === '停用'   && k.status !== 'disabled')                          return false;
    return true;
  });

  const filteredModels = models.filter(m =>
    providerFilter === '全部' || m.provider === providerFilter,
  );

  function reloadKeys() {
    setKeysLoading(true);
    getAiKeys()
      .then(data => setKeys(data.items ?? []))
      .catch(() => message.error('刷新 Key 列表失败'))
      .finally(() => setKeysLoading(false));
  }

  function reloadModels() {
    setModelsLoading(true);
    getAiModels()
      .then(data => setModels(data.items ?? []))
      .catch(() => message.error('刷新模型列表失败'))
      .finally(() => setModelsLoading(false));
  }

  async function handleAddKey(v: { label: string; provider: string; api_key: string; base_url: string; max_concurrent: number; remark?: string }) {
    try {
      await createAiKey(v);
      message.success('Key 已添加');
      setAddKeyOpen(false);
      addKeyForm.resetFields();
      reloadKeys();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加失败');
    }
  }

  async function handleEditKey(v: { label: string; provider: string; api_key: string; base_url: string; max_concurrent: number }) {
    if (!editKey) return;
    try {
      await updateAiKey(editKey.id, v);
      message.success('更新成功');
      setEditKey(null);
      editKeyForm.resetFields();
      reloadKeys();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  }

  function openEditKey(k: AiKeyRecord) {
    editKeyForm.setFieldsValue({ label: k.label, provider: k.provider, api_key: k.api_key, base_url: k.base_url, max_concurrent: k.max_concurrent });
    setEditKey(k);
  }

  async function handleTestKey(id: number) {
    setTestingKeyId(id);
    try {
      const r = await testAiKey(id);
      if (r.status === 'ok') {
        message.success(`✅ 正常 ${r.latency_ms}ms`);
        reloadKeys();
      } else {
        message.error(`❌ ${r.error ?? r.message ?? '未知错误'}`);
      }
    } catch {
      message.error('❌ 请求失败');
    } finally {
      setTestingKeyId(null);
    }
  }

  async function handleTestModel(id: number) {
    setTestingModelId(id);
    try {
      const r = await testAiModel(id);
      if (r.status === 'ok') {
        message.success(`✅ 正常 ${r.latency_ms}ms`);
        reloadModels();
      } else {
        message.error(`❌ ${r.error ?? r.message ?? '未知错误'}`);
      }
    } catch {
      message.error('❌ 请求失败');
    } finally {
      setTestingModelId(null);
    }
  }

  async function handleDeleteKey(id: number) {
    try {
      await deleteAiKey(id);
      message.success('删除成功');
      reloadKeys();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleAddModel(v: CreateAiModelRequest) {
    try {
      await createAiModel(v);
      message.success('模型已添加');
      setAddModelOpen(false);
      addModelForm.resetFields();
      reloadModels();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加失败');
    }
  }

  async function handleDeleteModel(id: number) {
    try {
      await deleteAiModel(id);
      message.success('删除成功');
      reloadModels();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleToggleModel(id: number, currentStatus: 'active' | 'inactive') {
    try {
      await updateAiModel(id, { status: currentStatus === 'active' ? 'inactive' : 'active' });
      message.success('操作成功');
      reloadModels();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '操作失败');
    }
  }

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {PROVIDERS.map(p => (
            <button
              key={p}
              className={`btn btn-sm ${providerFilter === p ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setProviderFilter(p)}
            >{p}</button>
          ))}
        </div>
        <select
          className="filter-select"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={{ height: 30 }}
        >
          <option>全部</option>
          <option>正常</option>
          <option>未测试</option>
          <option>停用</option>
        </select>
        <select
          className="filter-select"
          value={timeRange}
          onChange={e => setTimeRange(e.target.value)}
          style={{ height: 30 }}
        >
          <option>今日</option>
          <option>近7天</option>
          <option>近30天</option>
        </select>
      </div>

      {/* Summary cards */}
      {(() => {
        const s = statsData?.summary;
        const svcStatus = s?.service_status ?? 'unavailable';
        const SVC_MAP = {
          healthy:     { color: 'var(--success)',          label: '正常'  },
          degraded:    { color: 'var(--warning, #FA8C16)', label: '较忙'  },
          overloaded:  { color: 'var(--danger)',           label: '超负载' },
          unavailable: { color: 'var(--gray-400)',         label: '不可用' },
        } as const;
        const { color: svcColor, label: svcLabel } = SVC_MAP[svcStatus] ?? SVC_MAP.unavailable;

        const cur = s?.current_active ?? 0;
        const cap = s?.total_capacity ?? 0;
        const loadPct = cap > 0 ? Math.round((cur / cap) * 100) : 0;
        const loadColor = loadPct <= 60 ? 'var(--success)' : loadPct <= 90 ? 'var(--warning, #FA8C16)' : 'var(--danger)';

        return (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20, opacity: statsLoading ? 0.5 : 1, transition: 'opacity .2s' }}>
            <div className="stat-card">
              <div className="s-label">Key 总数</div>
              <div className="s-value">{s?.total_keys ?? '--'}</div>
              <div className="s-sub">健康 {s?.healthy_keys ?? '--'} / {s?.total_keys ?? '--'}</div>
            </div>
            <div className="stat-card">
              <div className="s-label">负载率</div>
              <div className="s-value" style={{ fontSize: 22, color: loadColor }}>{cap > 0 ? `${loadPct}%` : '--'}</div>
              <div className="s-sub" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>当前并发 {cur} / 总上限 {cap}</span>
                <span style={{ color: svcColor, fontWeight: 500 }}>· {svcLabel}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="s-label">模型数量</div>
              <div className="s-value">{s?.model_count ?? '--'}</div>
              <div className="s-sub">已配置模型</div>
            </div>
            <div className="stat-card">
              <div className="s-label">Token 用量</div>
              <div className="s-value">{fmtTokens(s?.total_tokens)}</div>
              <div className="s-sub">本月用量</div>
            </div>
            <div className="stat-card">
              <div className="s-label">平均延迟</div>
              <div className="s-value" style={{ fontSize: 22 }}>
                {s?.avg_latency_ms ?? '--'}
                {s && <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--gray-400)' }}>ms</span>}
              </div>
              <div className="s-sub">过去 {timeRange}</div>
            </div>
          </div>
        );
      })()}

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header"><h2 className="card-title">模型使用占比</h2></div>
          <div className="card-body">
            {statsLoading
              ? <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">加载中...</div></div>
              : <DonutChart data={statsData?.by_model ?? []} />}
          </div>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header"><h2 className="card-title">Token 消耗趋势</h2></div>
          <div className="card-body">
            {statsLoading
              ? <div className="empty-state" style={{ padding: 24 }}><div className="empty-state-text">加载中...</div></div>
              : <LineChart data={statsData?.token_trend ?? []} />}
          </div>
        </div>
      </div>

      {/* Key list */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h2 className="card-title">Key 列表</h2>
          <button className="btn btn-primary btn-sm" onClick={() => { addKeyForm.resetFields(); setAddKeyOpen(true); }}>+ 添加 Key</button>
        </div>
        <div style={{ padding: '0 20px 16px' }}>
          {keysLoading ? (
            <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
          ) : filteredKeys.length === 0 ? null : (
            <table className="ant-table" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th style={{ width: 48 }}>序号</th>
                  <th>名称</th>
                  <th>服务商</th>
                  <th>Key 秘钥</th>
                  <th>Key 状态</th>
                  <th>并发</th>
                  <th>测试时间</th>
                  <th>今日调用</th>
                  <th>总调用</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredKeys.map((k, idx) => (
                  <KeyRow
                    key={k.id}
                    k={k}
                    idx={idx}
                    testing={testingKeyId === k.id}
                    onTest={() => handleTestKey(k.id)}
                    onEdit={() => openEditKey(k)}
                    onDelete={() => handleDeleteKey(k.id)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Model list */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">模型列表</h2>
          <button className="btn btn-primary btn-sm" onClick={() => { addModelForm.resetFields(); setAddModelOpen(true); }}>+ 添加模型</button>
        </div>
        <div style={{ padding: '0 20px 16px' }}>
          {modelsLoading ? (
            <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
          ) : filteredModels.length === 0 ? (
            <div className="empty-state"><div className="empty-state-text">暂无模型</div></div>
          ) : (
            <table className="ant-table" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>模型名称</th>
                  <th>model_id</th>
                  <th>服务商</th>
                  <th>状态</th>
                  <th>总调用</th>
                  <th>Token 用量</th>
                  <th>测试时间</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredModels.map(m => {
                  const modelTestTime = m.last_tested_at
                    ? `${fmtTime(m.last_tested_at)}${m.last_latency_ms !== null ? ` · ${m.last_latency_ms}ms` : ''}`
                    : '—';
                  return (
                  <tr key={m.id}>
                    <td><span style={{ fontWeight: 500, color: 'var(--gray-900)' }}>{m.name}</span></td>
                    <td><span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--gray-500)' }}>{m.model_id}</span></td>
                    <td><span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{m.provider}</span></td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                        <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, display: 'inline-block', background: m.status === 'active' ? 'var(--success)' : 'var(--gray-300)' }} />
                        {m.status === 'active' ? '启用' : '停用'}
                      </span>
                    </td>
                    <td><span style={{ fontSize: 13, fontWeight: 600 }}>{m.total_calls.toLocaleString()}</span></td>
                    <td><span style={{ fontSize: 13 }}>{fmtTokens(m.token_usage)}</span></td>
                    <td><span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{modelTestTime}</span></td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-ghost btn-sm" disabled={testingModelId === m.id} onClick={() => handleTestModel(m.id)}>
                          {testingModelId === m.id ? '测试中...' : '测试'}
                        </button>
                        <Popconfirm
                          title={m.status === 'active' ? '确认停用？' : '确认启用？'}
                          okText="确认" cancelText="取消"
                          onConfirm={() => handleToggleModel(m.id, m.status)}
                        >
                          <button className="btn btn-ghost btn-sm">{m.status === 'active' ? '停用' : '启用'}</button>
                        </Popconfirm>
                        <Popconfirm title="确认删除？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDeleteModel(m.id)}>
                          <button className="btn btn-danger-ghost btn-sm">删除</button>
                        </Popconfirm>
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Add Key Modal */}
      <Modal
        title="添加 Key"
        open={addKeyOpen}
        onCancel={() => { setAddKeyOpen(false); addKeyForm.resetFields(); }}
        onOk={() => addKeyForm.submit()}
        okText="添加" cancelText="取消"
      >
        <Form form={addKeyForm} layout="vertical" onFinish={handleAddKey} style={{ marginTop: 16 }}>
          <Form.Item label="名称" name="label" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 key-main" />
          </Form.Item>
          <Form.Item label="服务商" name="provider" rules={[{ required: true, message: '请选择服务商' }]}>
            <Select
              placeholder="请选择服务商"
              onChange={(val: string) => {
                addKeyForm.setFieldValue('base_url', PROVIDER_BASE_URL[val] ?? '');
              }}
            >
              <Select.Option value="yunwu">云雾</Select.Option>
              <Select.Option value="siliconflow">硅基流动</Select.Option>
              <Select.Option value="glm">GLM</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="Base URL" name="base_url" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: '请输入 API Key' }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item label="最大并发数" name="max_concurrent" initialValue={5}>
            <Input type="number" min={1} max={50} />
          </Form.Item>
          <Form.Item label="备注" name="remark"><Input placeholder="可选" /></Form.Item>
        </Form>
      </Modal>

      {/* Edit Key Modal */}
      <Modal
        title="编辑 Key"
        open={!!editKey}
        onCancel={() => { setEditKey(null); editKeyForm.resetFields(); }}
        onOk={() => editKeyForm.submit()}
        okText="保存" cancelText="取消"
      >
        <Form form={editKeyForm} layout="vertical" onFinish={handleEditKey} style={{ marginTop: 16 }}>
          <Form.Item label="名称" name="label" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="服务商" name="provider" rules={[{ required: true, message: '请选择服务商' }]}>
            <Select
              onChange={(val: string) => {
                editKeyForm.setFieldValue('base_url', PROVIDER_BASE_URL[val] ?? editKeyForm.getFieldValue('base_url'));
              }}
            >
              <Select.Option value="yunwu">云雾</Select.Option>
              <Select.Option value="siliconflow">硅基流动</Select.Option>
              <Select.Option value="glm">GLM</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="Base URL" name="base_url" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: '请输入 API Key' }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item label="最大并发数" name="max_concurrent">
            <Input type="number" min={1} max={50} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Add Model Modal */}
      <Modal
        title="添加模型"
        open={addModelOpen}
        onCancel={() => { setAddModelOpen(false); addModelForm.resetFields(); }}
        onOk={() => addModelForm.submit()}
        okText="添加" cancelText="取消"
      >
        <Form form={addModelForm} layout="vertical" onFinish={handleAddModel} style={{ marginTop: 16 }}>
          <Form.Item label="模型名称" name="name" rules={[{ required: true, message: '请输入模型名称' }]}>
            <Input placeholder="如 Claude Haiku 4.5" />
          </Form.Item>
          <Form.Item label="model_id" name="model_id" rules={[{ required: true, message: '请输入 model_id' }]}>
            <Input placeholder="如 claude-haiku-4-5-20251001" />
          </Form.Item>
          <Form.Item label="服务商" name="provider" rules={[{ required: true, message: '请选择服务商' }]}>
            <Select placeholder="请选择服务商">
              <Select.Option value="yunwu">云雾</Select.Option>
              <Select.Option value="siliconflow">硅基流动</Select.Option>
              <Select.Option value="glm">GLM</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ── Tab config ─────────────────────────────────────────────────────────────────
const PROVIDER_TABS = [
  { key: 'ai',     label: 'AI 配置' },
  { key: 'tikhub', label: 'TikHub 配置' },
  { key: 'oss',    label: 'OSS 配置' },
  { key: 'asr',    label: 'ASR 配置' },
];

// ── ServiceConfigPage ─────────────────────────────────────────────────────────
export default function ServiceConfigPage() {
  const [data, setData] = useState<PagedData<ServiceCredential> | null>(null);
  const [provider, setProvider] = useState('ai');
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editCred, setEditCred] = useState<ServiceCredential | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [createForm] = Form.useForm<CreateCredentialRequest>();
  const [editForm] = Form.useForm<UpdateCredentialRequest>();

  const load = useCallback(() => {
    if (provider === 'ai' || provider === 'tikhub' || provider === 'asr') return;
    setLoading(true);
    getCredentials(provider || undefined)
      .then(setData)
      .catch(() => message.error('加载配置失败'))
      .finally(() => setLoading(false));
  }, [provider]);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    createForm.resetFields();
    createForm.setFieldValue('provider', provider);
    setCreateOpen(true);
  }

  async function handleCreate(v: CreateCredentialRequest) {
    setFormLoading(true);
    try {
      await createCredential(v);
      message.success('创建成功');
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch (e: unknown) { message.error(e instanceof Error ? e.message : '创建失败'); }
    finally { setFormLoading(false); }
  }

  async function handleUpdate(v: UpdateCredentialRequest) {
    if (!editCred) return;
    setFormLoading(true);
    try {
      await updateCredential(editCred.id, v);
      message.success('更新成功');
      setEditCred(null);
      load();
    } catch (e: unknown) { message.error(e instanceof Error ? e.message : '更新失败'); }
    finally { setFormLoading(false); }
  }

  async function handleDelete(id: number) {
    try { await deleteCredential(id); message.success('删除成功'); load(); }
    catch { message.error('删除失败'); }
  }

  async function handleToggle(c: ServiceCredential) {
    try {
      c.status === 'enabled' ? await disableCredential(c.id) : await enableCredential(c.id);
      message.success('操作成功');
      load();
    } catch { message.error('操作失败'); }
  }

  async function handleTest(id: number) {
    setTestingId(id);
    try {
      const r = await testAiKey(id);
      r.status === 'ok'
        ? message.success(`正常，延迟 ${r.latency_ms}ms`)
        : message.error(`失败：${r.message ?? '未知'}`);
    } catch { message.error('测试失败'); }
    finally { setTestingId(null); }
  }

  const total = data?.pagination.total ?? 0;
  const statusClass = (s: string) => s === 'enabled' ? 'badge-success' : s === 'cooldown' ? 'badge-warning' : 'badge-gray';
  const statusLabel = (s: string) => s === 'enabled' ? '启用' : s === 'cooldown' ? '冷却' : '停用';

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">服务配置</h1>
          <p className="page-desc">管理 AI / TikHub / OSS / ASR 等外部服务的 API Key</p>
        </div>
        {provider !== 'ai' && provider !== 'tikhub' && provider !== 'oss' && provider !== 'asr' && (
          <div className="page-actions">
            <button className="btn btn-primary" onClick={openCreate}>+ 新增 Key</button>
          </div>
        )}
      </div>

      {/* Tabs card */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '4px 20px 0' }}>
          <Tabs
            activeKey={provider}
            onChange={key => setProvider(key)}
            items={PROVIDER_TABS.map(t => ({ key: t.key, label: t.label }))}
          />
        </div>

        {/* Non-AI/TikHub/OSS/ASR content stays inside the card (OSS/ASR have their own components) */}
        {provider !== 'ai' && provider !== 'tikhub' && provider !== 'oss' && provider !== 'asr' && (
          <>
            <div className="filter-bar" style={{ paddingTop: 0 }}>
              <span className="filter-count">共 {total} 条</span>
            </div>
            {loading ? (
              <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
            ) : !data || data.items.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>
            ) : data.items.map(c => (
              <div key={c.id} className="key-row">
                <div>
                  <div className="key-label">{c.label}</div>
                  <div className="key-tail">···· {c.secret_tail}</div>
                </div>
                <div style={{ color: 'var(--gray-500)', fontSize: 12 }}>{c.provider}</div>
                <div><span className={`badge ${statusClass(c.status)}`}>{statusLabel(c.status)}</span></div>
                <div style={{ color: 'var(--gray-400)', fontSize: 12 }}>W: {c.weight}</div>
                <div />
                <div className="key-actions">
                  <button className="btn btn-ghost btn-sm" disabled={testingId === c.id} onClick={() => handleTest(c.id)}>
                    {testingId === c.id ? '测试...' : '测试'}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => { setEditCred(c); editForm.setFieldsValue({ label: c.label, weight: c.weight }); }}>编辑</button>
                  <Popconfirm title={c.status === 'enabled' ? '确认停用？' : '确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(c)}>
                    <button className="btn btn-ghost btn-sm">{c.status === 'enabled' ? '停用' : '启用'}</button>
                  </Popconfirm>
                  <Popconfirm title="确认删除该 Key？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDelete(c.id)}>
                    <button className="btn btn-danger-ghost btn-sm">删除</button>
                  </Popconfirm>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* AI tab content rendered outside the tabs card */}
      {provider === 'ai' && <AiConfigTab />}

      {/* TikHub tab content */}
      {provider === 'tikhub' && <TikHubConfigTab />}

      {/* OSS tab content — 独立组件，含 OSS 专属字段表单和连通性测试 */}
      {provider === 'oss' && <OssConfigTab />}

      {/* ASR tab content — 独立组件，含 ASR 专属字段表单（AppKey + AK + Region）和连通性测试 */}
      {provider === 'asr' && <AsrConfigTab />}

      {/* Modals for non-AI providers */}
      <Modal title="新增 Key" open={createOpen} onCancel={() => { setCreateOpen(false); createForm.resetFields(); }} onOk={() => createForm.submit()} okText="创建" cancelText="取消" confirmLoading={formLoading}>
        <Form form={createForm} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item label="标签" name="label" rules={[{ required: true, message: '请输入标签' }]}><Input placeholder="如 ai-main" /></Form.Item>
          <Form.Item label="服务商" name="provider" rules={[{ required: true, message: '请选择服务商' }]}>
            <Select>
              <Select.Option value="ai">AI</Select.Option>
              <Select.Option value="tikhub">TikHub</Select.Option>
              {/* OSS / ASR 已有独立 Tab，不再在通用 Modal 创建 */}
            </Select>
          </Form.Item>
          <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: '请输入 API Key' }]}><Input.Password /></Form.Item>
          <Form.Item label="权重" name="weight" initialValue={10}><Input type="number" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑 Key" open={!!editCred} onCancel={() => setEditCred(null)} onOk={() => editForm.submit()} okText="保存" cancelText="取消" confirmLoading={formLoading}>
        <Form form={editForm} layout="vertical" onFinish={handleUpdate} style={{ marginTop: 16 }}>
          <Form.Item label="标签" name="label" rules={[{ required: true, message: '请输入标签' }]}><Input /></Form.Item>
          <Form.Item label="权重" name="weight"><Input type="number" /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
