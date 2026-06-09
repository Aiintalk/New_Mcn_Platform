import { useEffect, useState } from 'react';
import { message } from 'antd';
import { getHealth, testAIConnection, testTikHubConnection } from '../../api/system';
import type { HealthData, AITestResult, ServiceTestResult } from '../../types/system';
export default function ServiceStatusPage() {
  const [health, setHealth] = useState<HealthData|null>(null);
  const [aiResult, setAiResult] = useState<AITestResult|null>(null);
  const [tikResult, setTikResult] = useState<ServiceTestResult|null>(null);
  const [aiTesting, setAiTesting] = useState(false);
  const [tikTesting, setTikTesting] = useState(false);
  useEffect(() => { getHealth().then(setHealth).catch(() => message.error('获取系统状态失败')); }, []);
  async function handleTestAI() {
    setAiTesting(true);
    try {
      const r = await testAIConnection();
      setAiResult(r);
      if (r.status==='ok') message.success(`AI 正常，延迟 ${r.latency_ms}ms`);
      else message.error(`AI 失败：${r.error??'未知'}`);
    } catch { message.error('AI 连接测试失败'); } finally { setAiTesting(false); }
  }
  async function handleTestTikHub() {
    setTikTesting(true);
    try {
      const r = await testTikHubConnection();
      setTikResult(r);
      if (r.status==='ok') message.success(`TikHub 正常，延迟 ${r.latency_ms}ms`);
      else message.error(`TikHub 失败：${r.error??'未知'}`);
    } catch { message.error('TikHub 连接测试失败'); } finally { setTikTesting(false); }
  }
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">服务状态</h1><p className="page-desc">检查各外部服务的连接状态</p></div></div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="s-label">系统状态</div>
          <div className="s-value" style={{fontSize:18}}>
            {health ? <span className={`badge ${health.status==='ok'?'badge-success':'badge-danger'}`}>{health.status==='ok'?'正常':'异常'}</span> : '—'}
          </div>
          <div className="s-sub">{health?.service??'加载中...'}</div>
        </div>
        <div className="stat-card">
          <div className="s-label">数据库</div>
          <div className="s-value" style={{fontSize:18}}>
            {health ? <span className={`badge ${health.database==='ok'?'badge-success':'badge-danger'}`}>{health.database==='ok'?'正常':'异常'}</span> : '—'}
          </div>
          <div className="s-sub">PostgreSQL</div>
        </div>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--sp-4)'}}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">AI 服务</h3>
            <button className="btn btn-ghost btn-sm" onClick={handleTestAI} disabled={aiTesting}>{aiTesting?'测试中...':'连通测试'}</button>
          </div>
          <div className="card-body">
            {aiResult ? (
              <div>
                <div style={{display:'flex',alignItems:'center',gap:'var(--sp-2)',marginBottom:'var(--sp-3)'}}>
                  <span className={`badge ${aiResult.status==='ok'?'badge-success':'badge-danger'}`}>{aiResult.status==='ok'?'正常':'失败'}</span>
                  <span style={{fontSize:12,color:'var(--gray-400)'}}>延迟 {aiResult.latency_ms}ms</span>
                </div>
                {aiResult.model && <div style={{fontSize:12,color:'var(--gray-500)',marginBottom:'var(--sp-2)'}}>模型：{aiResult.model}</div>}
                {aiResult.reply && <div style={{fontSize:12,background:'var(--gray-50)',padding:'var(--sp-3)',borderRadius:'var(--radius-sm)'}}>{aiResult.reply}</div>}
                {aiResult.error && <div style={{fontSize:12,color:'var(--danger)'}}>{aiResult.error}</div>}
              </div>
            ) : <div className="empty-state"><div className="empty-state-text">点击"连通测试"检查服务状态</div></div>}
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">TikHub 服务</h3>
            <button className="btn btn-ghost btn-sm" onClick={handleTestTikHub} disabled={tikTesting}>{tikTesting?'测试中...':'连通测试'}</button>
          </div>
          <div className="card-body">
            {tikResult ? (
              <div>
                <div style={{display:'flex',alignItems:'center',gap:'var(--sp-2)'}}>
                  <span className={`badge ${tikResult.status==='ok'?'badge-success':'badge-danger'}`}>{tikResult.status==='ok'?'正常':'失败'}</span>
                  <span style={{fontSize:12,color:'var(--gray-400)'}}>延迟 {tikResult.latency_ms}ms</span>
                </div>
                {tikResult.error && <div style={{fontSize:12,color:'var(--danger)',marginTop:'var(--sp-2)'}}>{tikResult.error}</div>}
              </div>
            ) : <div className="empty-state"><div className="empty-state-text">点击"连通测试"检查服务状态</div></div>}
          </div>
        </div>
      </div>
    </>
  );
}
