import { useEffect, useState, useCallback } from 'react';
import { message } from 'antd';
import { getOperationLogs } from '../../api/logs';
import type { OperationLog } from '../../types/log';
import type { PagedData } from '../../types/api';
export default function OperationLogsPage() {
  const [data, setData] = useState<PagedData<OperationLog>|null>(null);
  const [kw, setKw] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const load = useCallback(() => {
    setLoading(true);
    getOperationLogs({ page, page_size:30, action:kw||undefined }).then(setData).catch(() => message.error('加载失败')).finally(() => setLoading(false));
  }, [page, kw]);
  useEffect(() => { load(); }, [load]);
  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">操作日志</h1><p className="page-desc">平台用户的所有操作记录</p></div></div>
      <div className="card">
        <div className="filter-bar">
          <input className="filter-input" placeholder="搜索操作..." value={kw} onChange={e=>{setKw(e.target.value);setPage(1);}} style={{width:200}} />
          <button className="btn btn-ghost btn-sm" onClick={()=>{setKw('');setPage(1);}}>重置</button>
          <span className="filter-count">共 {total} 条</span>
        </div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无操作日志</div></div>
        : <table className="ant-table"><thead><tr><th>操作人</th><th>角色</th><th>操作</th><th>目标类型</th><th>IP</th><th>时间</th></tr></thead>
          <tbody>{data.items.map(l => <tr key={l.id}>
            <td style={{fontWeight:600}}>{l.user_name??'—'}</td>
            <td>{l.role?<span className={`badge ${l.role==='admin'?'badge-brand':'badge-info'}`}>{l.role==='admin'?'管理员':'运营'}</span>:'—'}</td>
            <td style={{color:'var(--gray-600)'}}>{l.action}</td>
            <td style={{color:'var(--gray-400)',fontSize:12}}>{l.target_type??'—'}</td>
            <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{l.ip_address??'—'}</td>
            <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(l.created_at).toLocaleString('zh-CN')}</td>
          </tr>)}</tbody></table>}
        {totalPages>1 && <div className="pagination"><span>共 {total} 条</span><div className="pages">
          <div className="page-btn" onClick={()=>setPage(p=>Math.max(1,p-1))}>‹</div>
          {Array.from({length:Math.min(totalPages,5)},(_,i)=>i+1).map(p=><div key={p} className={`page-btn ${page===p?'active':''}`} onClick={()=>setPage(p)}>{p}</div>)}
          <div className="page-btn" onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>›</div>
        </div></div>}
      </div>
    </>
  );
}
