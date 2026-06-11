import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { getTools } from '../../api/workspace';
import type { WorkspaceTool } from '../../types/workspace';
function statusBadge(s: string) {
  const m: Record<string,string> = {online:'badge-success',dev:'badge-warning',offline:'badge-danger',disabled:'badge-gray'};
  const l: Record<string,string> = {online:'在线',dev:'开发中',offline:'下线',disabled:'停用'};
  return <span className={`badge ${m[s] ?? 'badge-gray'}`}>{l[s] ?? s}</span>;
}
export default function WorkspacePage() {
  const navigate = useNavigate();
  const [tools, setTools] = useState<WorkspaceTool[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { getTools().then(setTools).catch(() => message.error('加载工具列表失败')).finally(() => setLoading(false)); }, []);
  const sorted = [...tools].sort((a, b) => {
    if (a.status === 'online' && b.status !== 'online') return -1;
    if (a.status !== 'online' && b.status === 'online') return 1;
    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });
  const grouped = sorted.reduce<Record<string,WorkspaceTool[]>>((acc,t) => { const k = t.category||'其他'; if(!acc[k])acc[k]=[]; acc[k].push(t); return acc; }, {});
  function handleToolClick(t: WorkspaceTool) {
    if (t.status !== 'online') { message.info('该工具暂不可用'); return; }
    if (t.tool_code === 'kol-intake') navigate('/workspace/kol-intake/chat');
    else if (t.tool_code === 'persona-writer') navigate('/workspace/persona-writer');
    else if (t.tool_code === 'persona-positioning') navigate('/workspace/persona-positioning');
    else navigate(`/workspace/${t.tool_code}`);
  }
  return (
    <>
      <div className="page-header"><div><h1 className="page-title">内容工作台</h1><p className="page-desc">选择 AI 工具开始内容创作</p></div></div>
      {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
      : Object.keys(grouped).length === 0 ? <div className="empty-state"><div className="empty-state-text">暂无可用工具</div></div>
      : Object.entries(grouped).map(([cat, items]) => (
        <div key={cat} style={{marginBottom:'var(--sp-6)'}}>
          <div className="section-title">{cat}</div>
          <div className="tool-grid">
            {items.map(t => (
              <div key={t.tool_code} className="tool-card" onClick={() => handleToolClick(t)}>
                <div className="tc-category">{t.category}</div>
                <div className="tc-name">{t.tool_name}</div>
                <div className="tc-desc">{t.description}</div>
                <div className="tc-footer">{statusBadge(t.status)}<span className="tc-arrow">→</span></div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
