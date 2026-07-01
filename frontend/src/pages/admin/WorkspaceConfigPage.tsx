import { useEffect, useState, useCallback, useMemo } from 'react';
import { Modal, Form, Input, Select, Popconfirm, Tabs, Pagination, message } from 'antd';
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
import MaterialLibraryConfigTab from './MaterialLibraryConfigTab';
import SubtitleConfigTab from './SubtitleConfigTab';
import ValuesWriterConfigTab from './ValuesWriterConfigTab';
import ScriptReviewConfigTab from './ScriptReviewConfigTab';
import RetrospectiveConfigTab from './RetrospectiveConfigTab';
import type { WorkspaceTool } from '../../types/workspace';

// 所有配置 Tab 的 key 集合（不含 'tools'，因为 'tools' 是列表本身）
// 其中后 4 个为预留占位（分组锚点 / 配置页待开发），点进去显示 PlaceholderConfigTab
const CONFIG_TAB_KEYS = new Set<string>([
  'intake', 'benchmark', 'selling-point', 'tiktok-writer', 'qianchuan-review',
  'qianchuan-edit-review', 'livestream-writer', 'livestream-review', 'persona-review',
  'qianchuan-preview', 'tiktok-review', 'qianchuan-writer', 'persona-writer',
  'seeding-writer', 'material-library', 'subtitle', 'values-writer',
  'script-review', 'retrospective',
  // 预留占位：分组锚点 + 配置页待开发
  'qianchuan', 'review', 'persona-positioning', 'qianchuan-collection',
]);

// tool_code → Tab key 的例外映射（绝大多数两者相同，只有以下三个不同）
const TOOL_CODE_TO_TAB_KEY: Record<string, string> = {
  'kol-intake': 'intake',
  'qianchuan-script-review': 'script-review',
  'selling-point-extractor': 'selling-point',
};

// 预留配置页占位组件（分组工具 / 配置页待开发时使用）
function PlaceholderConfigTab({ toolName }: { toolName: string }) {
  return (
    <div className="card">
      <div className="empty-state">
        <div className="empty-state-text">
          「{toolName}」暂未提供独立配置项
        </div>
      </div>
    </div>
  );
}

export default function WorkspaceConfigPage() {
  const [tools, setTools] = useState<WorkspaceTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [editTool, setEditTool] = useState<WorkspaceTool|null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [form] = Form.useForm<Partial<WorkspaceTool>>();

  // 筛选 + 分页状态
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 15;

  // 当前激活的 Tab（受控，用于从工具列表跳转到对应配置 Tab）
  const [activeKey, setActiveKey] = useState<string>('tools');

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

  // 筛选 + 分页计算
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return tools.filter((t) => {
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (!kw) return true;
      return (
        t.tool_code.toLowerCase().includes(kw) ||
        t.tool_name.toLowerCase().includes(kw) ||
        (t.category ?? '').toLowerCase().includes(kw)
      );
    });
  }, [tools, keyword, statusFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const safePage = totalPages === 0 ? 1 : Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // 筛选条件变化时回第 1 页
  function handleKeywordChange(val: string) {
    setKeyword(val);
    setPage(1);
  }
  function handleStatusChange(val: string) {
    setStatusFilter(val);
    setPage(1);
  }

  const toolsTab = (
    <>
      <div className="card">
        <div className="filter-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="filter-count">
            共 {filtered.length} 个工具{filtered.length !== tools.length ? `（总计 ${tools.length}）` : ''}
          </span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Input.Search
              placeholder="搜索工具名 / 代码 / 分类"
              allowClear
              value={keyword}
              onChange={(e) => handleKeywordChange(e.target.value)}
              onSearch={handleKeywordChange}
              style={{ width: 240 }}
            />
            <Select
              value={statusFilter}
              onChange={handleStatusChange}
              style={{ width: 120 }}
              options={[
                { value: 'all', label: '全部状态' },
                { value: 'online', label: '在线' },
                { value: 'dev', label: '开发中' },
                { value: 'offline', label: '下线' },
                { value: 'disabled', label: '停用' },
              ]}
            />
          </div>
        </div>
        {loading ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        : filtered.length===0 ? <div className="empty-state"><div className="empty-state-text">{tools.length===0 ? '暂无工具配置' : '没有匹配的工具'}</div></div>
        : <table className="ant-table"><thead><tr><th>工具代码</th><th>工具名称</th><th>分类</th><th>状态</th><th>描述</th><th className="col-actions">操作</th></tr></thead>
          <tbody>{paged.map(t => (
            <tr key={t.tool_code}>
              <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--gray-400)'}}>{t.tool_code}</td>
              <td style={{fontWeight:600}}>{t.tool_name}</td>
              <td><span className="badge badge-brand">{t.category}</span></td>
              <td><span className={`badge ${sClass(t.status)}`}>{sLabel(t.status)}</span></td>
              <td style={{color:'var(--gray-500)',fontSize:12,maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.description}</td>
              <td className="col-actions">
                {CONFIG_TAB_KEYS.has(TOOL_CODE_TO_TAB_KEY[t.tool_code] ?? t.tool_code) && (
                  <button className="btn btn-ghost btn-sm" onClick={() => setActiveKey(TOOL_CODE_TO_TAB_KEY[t.tool_code] ?? t.tool_code)}>配置</button>
                )}
                <button className="btn btn-ghost btn-sm" onClick={() => { setEditTool(t); form.setFieldsValue({ tool_name:t.tool_name, description:t.description, category:t.category, status:t.status, sort_order:t.sort_order }); }}>编辑</button>
                <Popconfirm title={t.status==='online'?'确认停用？':'确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(t)}>
                  <button className="btn btn-ghost btn-sm">{t.status==='online'?'停用':'启用'}</button>
                </Popconfirm>
              </td>
            </tr>
          ))}</tbody></table>}
        {filtered.length > PAGE_SIZE && (
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <Pagination
              current={safePage}
              pageSize={PAGE_SIZE}
              total={filtered.length}
              onChange={setPage}
              showSizeChanger={false}
              size="small"
            />
          </div>
        )}
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
        activeKey={activeKey}
        onChange={setActiveKey}
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
          { key: 'material-library', label: '素材库', children: <MaterialLibraryConfigTab /> },
          { key: 'subtitle', label: '字幕提取', children: <SubtitleConfigTab /> },
          { key: 'values-writer', label: '价值观仿写', children: <ValuesWriterConfigTab /> },
          { key: 'script-review', label: '千川脚本预审', children: <ScriptReviewConfigTab /> },
          { key: 'retrospective', label: '复盘', children: <RetrospectiveConfigTab /> },
          { key: 'persona-positioning', label: '人格定位（预留）', children: <PlaceholderConfigTab toolName="人格定位" /> },
          { key: 'qianchuan-collection', label: '千川文案库（预留）', children: <PlaceholderConfigTab toolName="千川文案库" /> },
          { key: 'qianchuan', label: '千川工具组（预留）', children: <PlaceholderConfigTab toolName="千川工具组" /> },
          { key: 'review', label: '复盘工具组（预留）', children: <PlaceholderConfigTab toolName="复盘工具组" /> },
        ]}
      />
    </>
  );
}
