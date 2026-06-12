import { useEffect, useState, useCallback } from 'react';
import { Modal, Tabs, message } from 'antd';
import { getTasks, getTask } from '../../api/tasks';
import { getOperatorSubmissions, getOperatorSubmissionDetail, getOperatorDownloadUrl } from '../../api/intake';
import type { TaskJob, TaskDetail, TaskStatus } from '../../types/task';
import type { PagedData } from '../../types/api';
import type { IntakeSubmission } from '../../types/intake';

function statusBadge(s: TaskStatus) {
  const m: Record<TaskStatus,string> = {pending:'badge-gray',processing:'badge-warning',success:'badge-success',failed:'badge-danger',cancelled:'badge-gray'};
  const l: Record<TaskStatus,string> = {pending:'待处理',processing:'处理中',success:'成功',failed:'失败',cancelled:'已取消'};
  return <span className={`badge ${m[s]}`}>{l[s]}</span>;
}
function dotClass(s: string) { return s==='success'?'success':s==='failed'?'failed':s==='processing'?'processing':'pending'; }

function fmtIntakeTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const SUB_STATUS_LABEL: Record<string, string> = {
  pending: '待生成', generating: '生成中', ready: '已就绪', failed: '生成失败',
};
const SUB_STATUS_CLS: Record<string, string> = {
  pending: 'badge-gray', generating: 'badge-warning', ready: 'badge-success', failed: 'badge-danger',
};

export default function TasksPage() {
  const [data, setData] = useState<PagedData<TaskJob>|null>(null);
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<TaskDetail|null>(null);
  const [open, setOpen] = useState(false);

  // 采集记录
  const [submissions, setSubmissions] = useState<IntakeSubmission[]>([]);
  const [subLoading, setSubLoading] = useState(false);
  const [selectedSub, setSelectedSub] = useState<IntakeSubmission | null>(null);
  const [detailTab, setDetailTab] = useState<'messages' | 'report'>('messages');
  const [activeMainTab, setActiveMainTab] = useState('tasks');

  const load = useCallback(() => {
    setLoading(true);
    getTasks({ page, page_size:20, status: status||undefined })
      .then(setData).catch(() => message.error('加载任务列表失败')).finally(() => setLoading(false));
  }, [page, status]);
  useEffect(() => { load(); }, [load]);

  const loadSubmissions = useCallback(async () => {
    setSubLoading(true);
    try { setSubmissions(await getOperatorSubmissions()); }
    catch { message.error('加载采集记录失败'); }
    finally { setSubLoading(false); }
  }, []);

  async function handleDetail(id: number) {
    setOpen(true);
    try { setDetail(await getTask(id)); } catch { message.error('加载详情失败'); setOpen(false); }
  }

  async function openSubDetail(id: number) {
    try {
      const d = await getOperatorSubmissionDetail(id);
      setSelectedSub(d);
      setDetailTab('messages');
    } catch (err: unknown) {
      message.error((err as Error).message || '加载详情失败');
    }
  }

  function handleTabChange(key: string) {
    setActiveMainTab(key);
    if (key === 'intake' && submissions.length === 0) loadSubmissions();
  }

  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">任务中心</h1>
          <p className="page-desc">查看 AI 工具处理任务的状态和采集记录</p>
        </div>
      </div>

      <Tabs
        activeKey={activeMainTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'tasks',
            label: 'AI 任务',
            children: (
              <div className="card">
                <div className="filter-bar">
                  <select className="filter-select" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
                    <option value="">全部状态</option>
                    <option value="pending">待处理</option>
                    <option value="processing">处理中</option>
                    <option value="success">成功</option>
                    <option value="failed">失败</option>
                  </select>
                  <span className="filter-count">共 {total} 条</span>
                </div>
                {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
                : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无任务</div></div>
                : <table className="ant-table"><thead><tr><th>任务编号</th><th>工具</th><th>状态</th><th>时间</th><th>耗时</th><th className="col-actions">操作</th></tr></thead>
                  <tbody>{data.items.map(t => <tr key={t.id}>
                    <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{t.task_no}</td>
                    <td style={{fontWeight:600}}>{t.tool_name}</td>
                    <td>{statusBadge(t.status)}</td>
                    <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(t.created_at).toLocaleString('zh-CN')}</td>
                    <td style={{color:'var(--gray-500)',fontSize:12}}>{t.duration_ms!=null?`${(t.duration_ms/1000).toFixed(1)}s`:'—'}</td>
                    <td className="col-actions"><button className="btn btn-ghost btn-sm" onClick={() => handleDetail(t.id)}>详情</button></td>
                  </tr>)}</tbody></table>}
                {totalPages>1 && <div className="pagination"><span>共 {total} 条</span><div className="pages">
                  <div className="page-btn" onClick={() => setPage(p => Math.max(1,p-1))}>‹</div>
                  {Array.from({length:Math.min(totalPages,5)},(_,i)=>i+1).map(p=><div key={p} className={`page-btn ${page===p?'active':''}`} onClick={()=>setPage(p)}>{p}</div>)}
                  <div className="page-btn" onClick={() => setPage(p => Math.min(totalPages,p+1))}>›</div>
                </div></div>}
              </div>
            ),
          },
          {
            key: 'intake',
            label: '采集记录',
            children: (
              <div className="card">
                <div className="card-body" style={{ padding: 0 }}>
                  {subLoading
                    ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
                    : submissions.length === 0
                    ? <div className="empty-state"><div className="empty-state-text">暂无采集记录</div></div>
                    : (
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>红人姓名</th>
                            <th>报告状态</th>
                            <th>提交时间</th>
                            <th>报告生成时间</th>
                            <th>红人下载</th>
                            <th style={{ textAlign: 'right' }}>操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {submissions.map(sub => (
                            <tr key={sub.id}>
                              <td>{sub.kol_name || <span style={{ color: 'var(--gray-400)' }}>未知</span>}</td>
                              <td>
                                <span className={`badge ${SUB_STATUS_CLS[sub.report_status] ?? 'badge-gray'}`}>
                                  {SUB_STATUS_LABEL[sub.report_status] ?? sub.report_status}
                                </span>
                              </td>
                              <td style={{ fontSize: 12 }}>{fmtIntakeTime(sub.created_at)}</td>
                              <td style={{ fontSize: 12 }}>{fmtIntakeTime(sub.report_generated_at)}</td>
                              <td style={{ fontSize: 12 }}>
                                {sub.kol_downloaded_at
                                  ? <span style={{ color: 'var(--success)' }}>✓ {fmtIntakeTime(sub.kol_downloaded_at)}</span>
                                  : <span style={{ color: 'var(--gray-400)' }}>未下载</span>}
                              </td>
                              <td>
                                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                  <button className="btn btn-ghost btn-sm"
                                    onClick={() => openSubDetail(sub.id)}>查看</button>
                                  {sub.report_status === 'ready' && (
                                    <>
                                      <button className="btn btn-ghost btn-sm"
                                        onClick={() => window.open(getOperatorDownloadUrl(sub.id, 'docx'), '_blank')}>
                                        Word
                                      </button>
                                      <button className="btn btn-ghost btn-sm"
                                        onClick={() => window.open(getOperatorDownloadUrl(sub.id, 'pdf'), '_blank')}>
                                        PDF
                                      </button>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )
                  }
                </div>
              </div>
            ),
          },
        ]}
      />

      {/* AI 任务详情 Modal */}
      <Modal title="任务详情" open={open} onCancel={() => setOpen(false)} footer={null} width={600}>
        {detail && <div style={{marginTop:16}}>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--sp-3)',marginBottom:'var(--sp-4)'}}>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>任务编号</div><div style={{fontFamily:'var(--font-mono)',fontSize:12}}>{detail.task_no}</div></div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>工具</div><div style={{fontWeight:600}}>{detail.tool_name}</div></div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>状态</div>{statusBadge(detail.status)}</div>
            <div><div style={{fontSize:11,color:'var(--gray-400)',marginBottom:4}}>耗时</div><div>{detail.duration_ms!=null?`${(detail.duration_ms/1000).toFixed(1)}s`:'—'}</div></div>
          </div>
          {detail.error_message && <div style={{background:'var(--danger-bg)',padding:'var(--sp-3)',borderRadius:'var(--radius-sm)',marginBottom:'var(--sp-4)',fontSize:13,color:'var(--danger)'}}>{detail.error_message}</div>}
          <div style={{fontSize:11,fontWeight:600,color:'var(--gray-500)',textTransform:'uppercase',letterSpacing:'0.5px',marginBottom:'var(--sp-3)'}}>执行日志</div>
          <div className="log-panel">
            {detail.task_logs.length===0 ? <div style={{color:'var(--gray-400)',fontSize:12}}>暂无日志</div>
            : detail.task_logs.map(log => <div key={log.id} className="log-step">
              <div className={`step-dot ${dotClass(log.status)}`} />
              <div><div className="step-name">{log.step_name}</div>{log.message&&<div className="step-msg">{log.message}</div>}</div>
              <div />
              <div className="step-time">{new Date(log.created_at).toLocaleTimeString('zh-CN')}</div>
            </div>)}
          </div>
        </div>}
      </Modal>

      {/* 采集记录详情 Modal */}
      <Modal
        title={`${selectedSub?.kol_name || '未知'} · 提交详情`}
        open={!!selectedSub}
        onCancel={() => { setSelectedSub(null); setDetailTab('messages'); }}
        footer={null}
        width={680}
        destroyOnHidden
      >
        {selectedSub && (
          <>
            <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
              {(['messages', 'report'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className={detailTab === t ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
                >
                  {t === 'messages' ? '对话记录' : '入驻报告'}
                </button>
              ))}
            </div>

            {detailTab === 'messages' && (
              <div style={{ maxHeight: 420, overflowY: 'auto', padding: '4px 0' }}>
                {(selectedSub.messages ?? []).map((msg, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                    gap: 8, marginBottom: 12, alignItems: 'flex-start',
                  }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                      background: msg.role === 'user' ? 'var(--gray-200)' : 'var(--brand)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 12, fontWeight: 700,
                      color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
                    }}>
                      {msg.role === 'user' ? '红' : 'AI'}
                    </div>
                    <div style={{
                      maxWidth: '80%',
                      background: msg.role === 'user' ? 'var(--brand)' : 'var(--bg-page)',
                      color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                      padding: '8px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.6,
                      border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                      whiteSpace: 'pre-wrap',
                    }}>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {detailTab === 'report' && (
              <div>
                {selectedSub.report_status !== 'ready'
                  ? (
                    <div className="empty-state">
                      <div className="empty-state-icon">
                        {selectedSub.report_status === 'failed' ? '❌' : '⏳'}
                      </div>
                      <div className="empty-state-text">
                        {selectedSub.report_status === 'failed' ? '报告生成失败' : '报告尚未生成完成'}
                      </div>
                    </div>
                  )
                  : (
                    <>
                      <div style={{
                        maxHeight: 380, overflowY: 'auto',
                        background: 'var(--bg-page)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)', padding: '16px 20px',
                        fontSize: 13, lineHeight: 1.8, color: 'var(--gray-800)',
                        whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)',
                      }}>
                        {selectedSub.ai_report || '报告内容为空'}
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                        <button className="btn btn-ghost btn-sm"
                          onClick={() => window.open(getOperatorDownloadUrl(selectedSub.id, 'pdf'), '_blank')}>
                          下载 PDF
                        </button>
                        <button className="btn btn-primary btn-sm"
                          onClick={() => window.open(getOperatorDownloadUrl(selectedSub.id, 'docx'), '_blank')}>
                          下载 Word
                        </button>
                      </div>
                    </>
                  )
                }
              </div>
            )}
          </>
        )}
      </Modal>
    </>
  );
}
