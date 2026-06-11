import { useEffect, useState, useCallback } from 'react';
import { Modal, Popconfirm, Tabs, message } from 'antd';
import { getOutputs, getOutput, deleteOutput } from '../../api/outputs';
import { getIntakeLinks } from '../../api/intake';
import { getDirectSessions } from '../../api/intakeDirect';
import type { DirectSession } from '../../api/intakeDirect';
import { useAuthStore } from '../../store/authStore';
import type { Output } from '../../types/output';
import type { PagedData } from '../../types/api';
import type { IntakeLink } from '../../types/intake';

const FRONTEND_BASE = import.meta.env.VITE_APP_BASE_URL ?? window.location.origin;

function fmtLinkTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function isExpired(iso: string) {
  return new Date(iso) < new Date();
}

export default function OutputsPage() {
  const [data, setData] = useState<PagedData<Output>|null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Output|null>(null);

  // 分享链接 Tab
  const [links, setLinks] = useState<IntakeLink[]>([]);
  const [linksLoading, setLinksLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('outputs');

  // 入驻报告 Tab
  const [sessions, setSessions] = useState<DirectSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [reportPreview, setReportPreview] = useState<DirectSession | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getOutputs({ page, page_size:20 }).then(setData).catch(() => message.error('加载产出列表失败')).finally(() => setLoading(false));
  }, [page]);
  useEffect(() => { load(); }, [load]);

  const loadLinks = useCallback(async () => {
    setLinksLoading(true);
    try { setLinks(await getIntakeLinks()); }
    catch { message.error('加载链接失败'); }
    finally { setLinksLoading(false); }
  }, []);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try { setSessions(await getDirectSessions()); }
    catch { message.error('加载报告列表失败'); }
    finally { setSessionsLoading(false); }
  }, []);

  function handleTabChange(key: string) {
    setActiveTab(key);
    if (key === 'links' && links.length === 0) loadLinks();
    if (key === 'reports' && sessions.length === 0) loadSessions();
  }

  async function handleSessionDownload(sessionId: number, format: 'docx' | 'pdf') {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
    const token = useAuthStore.getState().token;
    if (!token) { message.error('请重新登录后再试'); return; }
    try {
      const res = await fetch(
        `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ message: '下载失败' }));
        message.error(body.message || '下载失败');
        return;
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `入驻报告.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      message.error('下载失败，请重试');
    }
  }

  async function handleDelete(id: number) {
    try { await deleteOutput(id); message.success('删除成功'); load(); } catch { message.error('删除失败'); }
  }
  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? 1;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">产出中心</h1>
          <p className="page-desc">查看 AI 工具生成的内容和采集分享链接</p>
        </div>
      </div>

      <Tabs activeKey={activeTab} onChange={handleTabChange} items={[
        {
          key: 'outputs',
          label: 'AI 产出',
          children: (
            <div className="card">
              <div className="filter-bar"><span className="filter-count">共 {total} 条</span></div>
              {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
              : !data||data.items.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无产出记录</div></div>
              : <table className="ant-table"><thead><tr><th>标题</th><th>工具</th><th>字数</th><th>时间</th><th className="col-actions">操作</th></tr></thead>
                <tbody>{data.items.map(o => <tr key={o.id}>
                  <td style={{fontWeight:600,maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{o.title}</td>
                  <td><span className="badge badge-brand">{o.tool_name}</span></td>
                  <td style={{color:'var(--gray-500)',fontSize:12}}>{o.word_count??'—'}</td>
                  <td style={{color:'var(--gray-400)',fontSize:12}}>{new Date(o.created_at).toLocaleString('zh-CN')}</td>
                  <td className="col-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => { setPreview(o); getOutput(o.id).then(detail => setPreview(detail)).catch(() => {}); }}>预览</button>
                    <Popconfirm title="确认删除该产出？" okText="删除" cancelText="取消" okButtonProps={{danger:true}} onConfirm={() => handleDelete(o.id)}>
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
          ),
        },
        {
          key: 'links',
          label: '分享链接',
          children: (
            <div className="card">
              <div className="card-body" style={{ padding: 0 }}>
                {linksLoading
                  ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
                  : links.length === 0
                  ? <div className="empty-state"><div className="empty-state-text">暂无分享链接</div></div>
                  : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>红人姓名</th>
                          <th>状态</th>
                          <th>到期时间</th>
                          <th>访问时间</th>
                          <th>提交时间</th>
                          <th style={{ textAlign: 'right' }}>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {links.map(lnk => {
                          const expired = isExpired(lnk.expires_at);
                          return (
                            <tr key={lnk.id}>
                              <td>{lnk.kol_name || <span style={{ color: 'var(--gray-400)' }}>未填写</span>}</td>
                              <td>
                                <span className={`badge ${expired ? 'badge-gray' : lnk.is_active ? 'badge-success' : 'badge-danger'}`}>
                                  {expired ? '已过期' : lnk.is_active ? '有效' : '停用'}
                                </span>
                              </td>
                              <td style={{ fontSize: 12, color: expired ? 'var(--danger)' : 'var(--gray-700)' }}>
                                {fmtLinkTime(lnk.expires_at)}
                              </td>
                              <td style={{ fontSize: 12 }}>{fmtLinkTime(lnk.used_at)}</td>
                              <td style={{ fontSize: 12 }}>{fmtLinkTime(lnk.submitted_at)}</td>
                              <td>
                                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                  <button className="btn btn-ghost btn-sm"
                                    onClick={() => navigator.clipboard.writeText(`${FRONTEND_BASE}/intake/${lnk.token}`).then(() => message.success('链接已复制'))}>
                                    复制链接
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )
                }
              </div>
            </div>
          ),
        },
        {
          key: 'reports',
          label: '入驻报告',
          children: (
            <div className="card">
              {sessionsLoading
                ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
                : sessions.length === 0
                ? <div className="empty-state"><div className="empty-state-text">暂无入驻报告</div></div>
                : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>红人姓名</th>
                        <th>状态</th>
                        <th>生成时间</th>
                        <th style={{ textAlign: 'right' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.map(s => (
                        <tr key={s.id}>
                          <td style={{ fontWeight: 600 }}>{s.kol_name || <span style={{ color: 'var(--gray-400)' }}>未命名</span>}</td>
                          <td>
                            <span className={`badge ${
                              s.report_status === 'ready' ? 'badge-success' :
                              s.report_status === 'failed' ? 'badge-danger' : 'badge-gray'
                            }`}>
                              {s.report_status === 'ready' ? '已生成' :
                               s.report_status === 'generating' ? '生成中' :
                               s.report_status === 'failed' ? '失败' : '待生成'}
                            </span>
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--gray-400)' }}>
                            {s.report_generated_at ? new Date(s.report_generated_at).toLocaleString('zh-CN') : '—'}
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                              {s.report_status === 'ready' && (
                                <>
                                  <button className="btn btn-ghost btn-sm" onClick={() => setReportPreview(s)}>查看报告</button>
                                  <button className="btn btn-ghost btn-sm" onClick={() => handleSessionDownload(s.id, 'pdf')}>下载 PDF</button>
                                  <button className="btn btn-primary btn-sm" onClick={() => handleSessionDownload(s.id, 'docx')}>下载 Word</button>
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
          ),
        },
      ]} />

      <Modal
        title={reportPreview?.kol_name ? `${reportPreview.kol_name} · 入驻报告` : '入驻报告'}
        open={!!reportPreview}
        onCancel={() => setReportPreview(null)}
        footer={null}
        width={800}
      >
        {reportPreview?.ai_report && (
          <div style={{ maxHeight: '65vh', overflowY: 'auto', marginTop: 16 }}>
            <pre style={{
              fontFamily: 'var(--font-sans)', fontSize: 13,
              lineHeight: 1.8, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {reportPreview.ai_report}
            </pre>
          </div>
        )}
      </Modal>

      <Modal title={preview?.title??'产出预览'} open={!!preview} onCancel={()=>setPreview(null)} footer={null} width={700}>
        {preview && <div style={{maxHeight:'60vh',overflowY:'auto',marginTop:16}}>
          {preview.content ? <pre style={{fontFamily:'var(--font-sans)',fontSize:13,lineHeight:1.8,whiteSpace:'pre-wrap',wordBreak:'break-word'}}>{preview.content}</pre>
          : <div className="empty-state"><div className="empty-state-text">暂无内容预览</div></div>}
        </div>}
      </Modal>
    </>
  );
}
