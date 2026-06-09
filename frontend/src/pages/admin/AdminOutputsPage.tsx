import { useEffect, useState, useCallback } from 'react';
import { Modal, Popconfirm, message } from 'antd';
import { adminGetOutputs, adminDeleteOutput } from '../../api/outputs';
import type { Output } from '../../types/output';
import type { PagedData } from '../../types/api';
export default function AdminOutputsPage() {
  const [data, setData] = useState<PagedData<Output>|null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Output|null>(null);
  const load = useCallback(() => {
    setLoading(true);
    adminGetOutputs({ page, page_size:20 }).then(setData).catch(() => message.error('加载失败')).finally(() => setLoading(false));
  }, [page]);
  useEffect(() => { load(); }, [load]);
  async function handleDelete(id: number) {
    try { await adminDeleteOutput(id); message.success('删除成功'); load(); } catch { message.error('删除失败'); }
  }
  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">产出记录</h1><p className="page-desc">所有用户的内容产出记录</p></div></div>
      <div className="card">
        <div className="filter-bar"><span className="filter-count">共 {total} 条</span></div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无产出记录</div></div>
        : <table className="ant-table"><thead><tr><th>标题</th><th>工具</th><th>创建人</th><th>字数</th><th>时间</th><th className="col-actions">操作</th></tr></thead>
          <tbody>{data.items.map(o => <tr key={o.id}>
            <td style={{fontWeight:600,maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{o.title}</td>
            <td><span className="badge badge-brand">{o.tool_name}</span></td>
            <td style={{color:'var(--gray-500)'}}>{o.created_by_name??o.created_by}</td>
            <td style={{color:'var(--gray-500)',fontSize:12}}>{o.word_count??'—'}</td>
            <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(o.created_at).toLocaleString('zh-CN')}</td>
            <td className="col-actions">
              <button className="btn btn-ghost btn-sm" onClick={() => setPreview(o)}>预览</button>
              <Popconfirm title="确认删除？" okText="删除" cancelText="取消" okButtonProps={{danger:true}} onConfirm={() => handleDelete(o.id)}>
                <button className="btn btn-danger-ghost btn-sm">删除</button>
              </Popconfirm>
            </td>
          </tr>)}</tbody></table>}
        {totalPages>1 && <div className="pagination"><span>共 {total} 条</span><div className="pages">
          <div className="page-btn" onClick={()=>setPage(p=>Math.max(1,p-1))}>‹</div>
          {Array.from({length:Math.min(totalPages,5)},(_,i)=>i+1).map(p=><div key={p} className={`page-btn ${page===p?'active':''}`} onClick={()=>setPage(p)}>{p}</div>)}
          <div className="page-btn" onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>›</div>
        </div></div>}
      </div>
      <Modal title={preview?.title??'产出预览'} open={!!preview} onCancel={()=>setPreview(null)} footer={null} width={700}>
        {preview && <div style={{maxHeight:'60vh',overflowY:'auto',marginTop:16}}>
          {preview.content ? <pre style={{fontFamily:'var(--font-sans)',fontSize:13,lineHeight:1.8,whiteSpace:'pre-wrap',wordBreak:'break-word'}}>{preview.content}</pre>
          : <div className="empty-state"><div className="empty-state-text">暂无内容预览</div></div>}
        </div>}
      </Modal>
    </>
  );
}
