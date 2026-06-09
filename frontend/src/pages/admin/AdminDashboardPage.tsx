import { useEffect, useState } from 'react';
import { message } from 'antd';
import { getUsers } from '../../api/users';
import { adminGetTasks } from '../../api/tasks';
import { adminGetOutputs } from '../../api/outputs';
import { getOperationLogs } from '../../api/logs';
import type { OperationLog } from '../../types/log';
export default function AdminDashboardPage() {
  const [stats, setStats] = useState({userCount:0,taskCount:0,outputCount:0,logCount:0});
  const [logs, setLogs] = useState<OperationLog[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    Promise.all([
      getUsers({page:1,page_size:1}),
      adminGetTasks({page:1,page_size:1}),
      adminGetOutputs({page:1,page_size:1}),
      getOperationLogs({page:1,page_size:5}),
    ]).then(([u,t,o,l]) => {
      setStats({userCount:u.pagination.total,taskCount:t.pagination.total,outputCount:o.pagination.total,logCount:l.pagination.total});
      setLogs(l.items);
    }).catch(() => message.error('加载看板数据失败')).finally(() => setLoading(false));
  }, []);
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">数据看板</h1><p className="page-desc">平台整体数据概览</p></div></div>
      <div className="stats-grid">
        {[['注册用户',stats.userCount,'管理员 + 运营'],['任务总数',stats.taskCount,'历史累计'],['产出总数',stats.outputCount,'历史累计'],['操作日志',stats.logCount,'历史累计']].map(([label,val,sub])=>(
          <div key={String(label)} className="stat-card">
            <div className="s-label">{label}</div>
            <div className="s-value">{loading?'—':Number(val).toLocaleString()}</div>
            <div className="s-sub">{sub}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="card-header"><h3 className="card-title">最新操作日志</h3></div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : logs.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无操作日志</div></div>
        : <table className="ant-table"><thead><tr><th>操作人</th><th>角色</th><th>操作</th><th>IP</th><th>时间</th></tr></thead>
          <tbody>{logs.map(l => <tr key={l.id}>
            <td style={{fontWeight:600}}>{l.user_name??'—'}</td>
            <td>{l.role?<span className={`badge ${l.role==='admin'?'badge-brand':'badge-info'}`}>{l.role==='admin'?'管理员':'运营'}</span>:'—'}</td>
            <td style={{color:'var(--gray-600)'}}>{l.action}</td>
            <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{l.ip_address??'—'}</td>
            <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(l.created_at).toLocaleString('zh-CN')}</td>
          </tr>)}</tbody></table>}
      </div>
    </>
  );
}
