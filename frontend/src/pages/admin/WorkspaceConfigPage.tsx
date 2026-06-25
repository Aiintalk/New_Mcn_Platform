import { useEffect, useState, useCallback } from 'react';
import { Modal, Form, Input, Select, Popconfirm, Tabs, message } from 'antd';
import { adminGetTools, adminUpdateTool } from '../../api/workspace';
import AdminIntakePage from './AdminIntakePage';
import BenchmarkConfigTab from './BenchmarkConfigTab';
import SellingPointConfigTab from './SellingPointConfigTab';
import TiktokWriterConfigTab from './TiktokWriterConfigTab';
import QianchuanReviewConfigTab from './QianchuanReviewConfigTab';
import QianchuanEditReviewConfigTab from './QianchuanEditReviewConfigTab';
import LivestreamWriterConfigTab from './LivestreamWriterConfigTab';
import LivestreamReviewConfigTab from './LivestreamReviewConfigTab';
import PersonaReviewConfigTab from './PersonaReviewConfigTab';
import QianchuanPreviewConfigTab from './QianchuanPreviewConfigTab';
import TiktokReviewConfigTab from './TiktokReviewConfigTab';
import QianchuanWriterConfigTab from './QianchuanWriterConfigTab';
import PersonaWriterConfigTab from './PersonaWriterConfigTab';
import SeedingWriterConfigTab from './SeedingWriterConfigTab';
import ValuesWriterConfigTab from './ValuesWriterConfigTab';
import type { WorkspaceTool } from '../../types/workspace';
export default function WorkspaceConfigPage() {
  const [tools, setTools] = useState<WorkspaceTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [editTool, setEditTool] = useState<WorkspaceTool|null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [form] = Form.useForm<Partial<WorkspaceTool>>();
  const load = useCallback(() => {
    setLoading(true);
    adminGetTools().then(setTools).catch(() => message.error('加载工具配置失败')).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  async function handleUpdate(values: Partial<WorkspaceTool>) {
    if (!editTool) return;
    setFormLoading(true);
    try { await adminUpdateTool(editTool.tool_code, values); message.success('更新成功'); setEditTool(null); load(); }
    catch (err: unknown) { message.error(err instanceof Error ? err.message : '更新失败'); }
    finally { setFormLoading(false); }
  }
  async function handleToggle(t: WorkspaceTool) {
    try { await adminUpdateTool(t.tool_code, { status: t.status==='online'?'disabled':'online' }); message.success('操作成功'); load(); }
    catch { message.error('操作失败'); }
  }
  const sClass = (s: string) => ({online:'badge-success',dev:'badge-warning',offline:'badge-danger',disabled:'badge-gray'})[s]??'badge-gray';
  const sLabel = (s: string) => ({online:'在线',dev:'开发中',offline:'下线',disabled:'停用'})[s]??s;
  const toolsTab = (
    <>
      <div className="card">
        <div className="filter-bar"><span className="filter-count">共 {tools.length} 个工具</span></div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : tools.length===0 ? <div className="empty-state"><div className="empty-state-text">暂无工具配置</div></div>
        : <table className="ant-table"><thead><tr><th>工具代码</th><th>工具名称</th><th>分类</th><th>状态</th><th>描述</th><th className="col-actions">操作</th></tr></thead>
          <tbody>{tools.map(t => (
            <tr key={t.tool_code}>
              <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{t.tool_code}</td>
              <td style={{fontWeight:600}}>{t.tool_name}</td>
              <td><span className="badge badge-brand">{t.category}</span></td>
              <td><span className={`badge ${sClass(t.status)}`}>{sLabel(t.status)}</span></td>
              <td style={{color:'var(--gray-500)',fontSize:12,maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.description}</td>
              <td className="col-actions">
                <button className="btn btn-ghost btn-sm" onClick={() => { setEditTool(t); form.setFieldsValue({ tool_name:t.tool_name, description:t.description, category:t.category, status:t.status, sort_order:t.sort_order }); }}>编辑</button>
                <Popconfirm title={t.status==='online'?'确认停用？':'确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(t)}>
                  <button className="btn btn-ghost btn-sm">{t.status==='online'?'停用':'启用'}</button>
                </Popconfirm>
              </td>
            </tr>
          ))}</tbody></table>}
      </div>
      <Modal title={`编辑：${editTool?.tool_name??''}`} open={!!editTool} onCancel={() => setEditTool(null)} onOk={() => form.submit()} okText="保存" confirmLoading={formLoading}>
        <Form form={form} layout="vertical" onFinish={handleUpdate} style={{marginTop:16}}>
          <Form.Item label="工具名称" name="tool_name" rules={[{required:true}]}><Input /></Form.Item>
          <Form.Item label="分类" name="category" rules={[{required:true}]}><Input /></Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item label="状态" name="status"><Select><Select.Option value="online">在线</Select.Option><Select.Option value="dev">开发中</Select.Option><Select.Option value="offline">下线</Select.Option><Select.Option value="disabled">停用</Select.Option></Select></Form.Item>
          <Form.Item label="排序" name="sort_order"><Input type="number" /></Form.Item>
        </Form>
      </Modal>
    </>
  );

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">工具配置</h1>
          <p className="page-desc">管理内容工作台工具及 AI 功能配置</p>
        </div>
      </div>
      <Tabs
        defaultActiveKey="tools"
        items={[
          { key: 'tools',  label: '工具列表',        children: toolsTab },
          { key: 'intake', label: '红人信息采集助手', children: <AdminIntakePage embedded /> },
          { key: 'benchmark', label: '对标分析助手', children: <BenchmarkConfigTab /> },
          { key: 'selling-point', label: '产品卖点提取器', children: <SellingPointConfigTab /> },
          { key: 'tiktok-writer', label: 'TikTok 脚本仿写', children: <TiktokWriterConfigTab /> },
          { key: 'qianchuan-review', label: '千川脚本复盘', children: <QianchuanReviewConfigTab /> },
          { key: 'qianchuan-edit-review', label: '千川剪辑预审', children: <QianchuanEditReviewConfigTab /> },
          { key: 'livestream-writer', label: '直播脚本仿写', children: <LivestreamWriterConfigTab /> },
          { key: 'livestream-review', label: '直播间脚本复盘', children: <LivestreamReviewConfigTab /> },
          { key: 'persona-review', label: '人设脚本复盘', children: <PersonaReviewConfigTab /> },
          { key: 'qianchuan-preview', label: '千川文案预审', children: <QianchuanPreviewConfigTab /> },
          { key: 'tiktok-review', label: 'TT内容复盘', children: <TiktokReviewConfigTab /> },
          { key: 'qianchuan-writer', label: '千川文案写作', children: <QianchuanWriterConfigTab /> },
          { key: 'persona-writer', label: '人设脚本仿写', children: <PersonaWriterConfigTab /> },
          { key: 'seeding-writer', label: '种草内容仿写', children: <SeedingWriterConfigTab /> },
          { key: 'values-writer', label: '价值观仿写', children: <ValuesWriterConfigTab /> },
        ]}
      />
    </>
  );
}
