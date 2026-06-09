import { useEffect, useState, useCallback } from 'react';
import { Modal, message } from 'antd';
import { adminGetTasks, adminGetTask } from '../../api/tasks';
import type { TaskJob, TaskDetail, TaskStatus } from '../../types/task';
import type { PagedData } from '../../types/api';
function statusBadge(s: TaskStatus) {
  const m: Record<TaskStatus,string> = {pending:'badge-gray',processing:'badge-warning',success:'badge-success',failed:'badge-danger',cancelled:'badge-gray'};
  const l: Record<TaskStatus,string> = {pending:'待处理',processing:'处理中',success:'成功',failed:'失败',cancelled:'已取消'};
  return <span className={`badge ${m[s]}`}>{l[s]}</span>;
}
export default function AdminTasksPage() {
  const [data, setData] = useState<PagedData<TaskJob>|null>(null);
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<TaskDetail|null>(null);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => {
    setLoading(true);
    adminGetTasks({ page, page_size:20, status:status||undefined }).then(setData).catch(() => message.error('加载失败')).finally(() => setLoading(false));
  }, [page, status]);
  useEffect(() => { load(); }, [load]);
  async function handleDetail(id: number) {
    setOpen(true);
    try { setDetail(await adminGetTask(id)); } catch { message.error('加载详情失败'); setOpen(false); }
  }
  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">任务记录</h1><p className="page-desc">所有用户的任务执行记录</p></div></div>
      <div className="card">
        <div className="filter-bar">
          <select className="filter-select" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
            <option value="">全部状态</option><option value="pending">待处理</option><option value="processing">处理中</option><option value="success">成功</option><option value="failed">失败</option>
          </select>
          <span className="filter-count">共 {total} 条</span>
        </div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无任务记录</div></div>
        : <table className="ant-table"><thead><tr><th>任务编号</th><th>工具</th><th>操作人</th><th>状态</th><th>时间</th><th>耗时</th><th className="col-actions">操作</th></tr></thead>
          <tbody>{data.items.map(t => <tr key={t.id}>
            <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{t.task_no}</td>
            <td style={{fontWeight:600}}>{t.tool_name}</td>
            <td style={{color:'var(--gray-500)'}}>{t.created_by_name??t.created_by}</td>
            <td>{statusBadge(t.status)}</td>
            <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(t.created_at).toLocaleString('zh-CN')}</td>
            <td style={{color:'var(--gray-500)',fontSize:12}}>{t.duration_ms!=null?`${(t.duration_ms/1000).toFixed(1)}s`:'—'}</td>
            <td className="col-actions"><button className="btn btn-ghost btn-sm" onClick={() => handleDetail(t.id)}>详情</button></td>
          </tr>)}</tbody></table>}
        {totalPages>1 && <div className="pagination"><span>共 {total} 条</span><div className="pages">
          <div className="page-btn" onClick={()=>setPage(p=>Math.max(1,p-1))}>‹</div>
          {Array.from({length:Math.min(totalPages,5)},(_,i)=>i+1).map(p=><div key={p} className={`page-btn ${page===p?'active':''}`} onClick={()=>setPage(p)}>{p}</div>)}
          <div className="page-btn" onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>›</div>
        </div></div>}
      </div>
      <Modal title="任务详情" open={open} onCancel={() => setOpen(false)} footer={null} width={600}>
        {detail && <div style={{marginTop:16}}>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--sp-3)',marginBottom:'var(--sp-4)'}}>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>任务编号</div><div style={{fontFamily:'var(--font-mono)',fontSize:12}}>{detail.task_no}</div></div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>工具</div><div style={{fontWeight:600}}>{detail.tool_name}</div></div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>状态</div>{statusBadge(detail.status)}</div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>操作人</div><div>{detail.created_by_name}</div></div>
          </div>
          {detail.error_message && <div style={{background:'var(--danger-bg)',padding:'var(--sp-3)',borderRadius:'var(--radius-sm)',marginBottom:'var(--sp-4)',fontSize:13,color:'var(--danger)'}}>{detail.error_message}</div>}
          <div className="log-panel">
            {detail.task_logs.map(log => <div key={log.id} className="log-step">
              <div className={`step-dot ${log.status==='success'?'success':log.status==='failed'?'failed':log.status==='processing'?'processing':'pending'}`} />
              <div><div className="step-name">{log.step_name}</div>{log.message&&<div className="step-msg">{log.message}</div>}</div>
              <div />
              <div className="step-time">{new Date(log.created_at).toLocaleTimeString('zh-CN')}</div>
            </div>)}
          </div>
        </div>}
      </Modal>
    </>
  );
}
