import { useEffect, useState } from 'react';
import { message } from 'antd';
import { getAiStats, getAiModels } from '../../api/ai';
import type { AiStats, AiModel } from '../../api/ai';
function roleBadge(r: AiModel['role']) {
  const m = { primary:'badge-success', fallback:'badge-warning', inactive:'badge-gray' } as const;
  const l = { primary:'主力', fallback:'备用', inactive:'停用' };
  return <span className={`badge ${m[r]}`}>{l[r]}</span>;
}
export default function AiManagementPage() {
  const [stats, setStats] = useState<AiStats|null>(null);
  const [models, setModels] = useState<AiModel[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    Promise.all([getAiStats(), getAiModels()])
      .then(([s,m]) => { setStats(s); setModels(m); })
      .catch(() => message.error('加载 AI 服务数据失败'))
      .finally(() => setLoading(false));
  }, []);
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">AI 服务管理</h1><p className="page-desc">监控 AI 模型调用情况与 Key 池状态</p></div></div>
      <div className="stats-grid">
        {[
          ['今日 Tokens', (stats?.today_tokens??0).toLocaleString(), '累计消耗'],
          ['活跃模型', stats?.active_model_count??0, '可用模型数'],
          ['可用 Keys', stats?.available_key_count??0, '健康 Key 数'],
          ['平均延迟', `${stats?.avg_latency_ms??0}ms`, '近 24 小时'],
        ].map(([label,val,sub]) => (
          <div key={String(label)} className="stat-card">
            <div className="s-label">{label}</div>
            <div className="s-value">{loading?'—':String(val)}</div>
            <div className="s-sub">{sub}</div>
          </div>
        ))}
      </div>
      <div className="section-title">模型概览</div>
      {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
      : <div className="model-grid">
        {models.map(m => (
          <div key={m.id} className="model-card">
            <div className="model-card-header">
              <div><div className="model-name">{m.name}</div><div className="model-provider">{m.provider_id}</div></div>
              {roleBadge(m.role)}
            </div>
            <div className="model-card-body">
              <div className="model-stats">
                {[['调用',m.call_count.toLocaleString()],['延迟',`${m.avg_latency}ms`],['成功率',`${m.success_rate}%`],['Keys',m.key_count]].map(([k,v])=>(
                  <div key={String(k)} className="model-stat"><div className="ms-label">{k}</div><div className="ms-value">{v}</div></div>
                ))}
              </div>
              <div className="model-bar-label"><span>调用占比</span><span>{m.usage_pct}%</span></div>
              <div className="bar-track"><div className="bar-fill" style={{width:`${m.usage_pct}%`}} /></div>
            </div>
          </div>
        ))}
      </div>}
    </>
  );
}
