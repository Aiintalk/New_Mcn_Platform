import { useEffect, useState, useCallback } from 'react';
import { message } from 'antd';
import { getExternalLogs } from '../../api/logs';
import type { ExternalServiceLog } from '../../types/log';
import type { PagedData } from '../../types/api';
export default function ExternalLogsPage() {
  const [data, setData] = useState<PagedData<ExternalServiceLog>|null>(null);
  const [svc, setSvc] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const load = useCallback(() => {
    setLoading(true);
    getExternalLogs({ page, page_size:30, service:svc||undefined, status:status||undefined })
      .then(setData).catch(() => message.error('加载失败')).finally(() => setLoading(false));
  }, [page, svc, status]);
  useEffect(() => { load(); }, [load]);
  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">调用日志</h1><p className="page-desc">外部服务（AI / TikHub / ASR）的调用记录</p></div></div>
      <div className="card">
        <div className="filter-bar">
          <select className="filter-select" value={svc} onChange={e=>{setSvc(e.target.value);setPage(1);}}>
            <option value="">全部服务</option><option value="ai">AI</option><option value="tikhub">TikHub</option><option value="asr">ASR</option>
          </select>
          <select className="filter-select" value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}>
            <option value="">全部状态</option><option value="success">成功</option><option value="error">失败</option>
          </select>
          <span className="filter-count">共 {total} 条</span>
        </div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无调用日志</div></div>
        : <table className="ant-table"><thead><tr><th>服务</th><th>接口</th><th>状态</th><th>耗时</th><th>Token入</th><th>Token出</th><th>时间</th></tr></thead>
          <tbody>{data.items.map(l => (
            <tr key={l.id}>
              <td><span className={`badge ${l.service==='ai'?'badge-purple':l.service==='tikhub'?'badge-cyan':'badge-brand'}`}>{l.service.toUpperCase()}</span></td>
              <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-500)',maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{l.endpoint}</td>
              <td><span className={`badge ${l.status==='success'?'badge-success':'badge-danger'}`}>{l.status==='success'?'成功':'失败'}</span></td>
              <td style={{color:'var(--gray-500)',fontSize:12}}>{l.duration_ms!=null?`${l.duration_ms}ms`:'—'}</td>
              <td style={{color:'var(--gray-500)',fontSize:12}}>{l.tokens_in??'—'}</td>
              <td style={{color:'var(--gray-500)',fontSize:12}}>{l.tokens_out??'—'}</td>
              <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(l.created_at).toLocaleString('zh-CN')}</td>
            </tr>
          ))}</tbody></table>}
        {totalPages>1 && <div className="pagination"><span>共 {total} 条</span><div className="pages">
          <div className="page-btn" onClick={()=>setPage(p=>Math.max(1,p-1))}>‹</div>
          {Array.from({length:Math.min(totalPages,5)},(_,i)=>i+1).map(p=><div key={p} className={`page-btn ${page===p?'active':''}`} onClick={()=>setPage(p)}>{p}</div>)}
          <div className="page-btn" onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>›</div>
        </div></div>}
      </div>
    </>
  );
}
