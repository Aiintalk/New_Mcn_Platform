import { useState, useEffect, useRef } from 'react';
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, Tabs, Popconfirm, message, Space, Tag
} from 'antd';
import { PlusOutlined, DeleteOutlined, CopyOutlined, DownloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  getPersonas, createPersona, deletePersona,
  getScripts, createScript, deleteScript, parseFile,
} from '../../api/qianchuanCollection';
import type { CollectionPersona, CollectionScript, CreateScriptBody } from '../../types/qianchuanCollection';

const PAGE_SIZE = 20;

export default function QianchuanCollectionPage() {
  const [mode, setMode] = useState<'global' | 'persona'>('global');
  const [personas, setPersonas] = useState<CollectionPersona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string | undefined>(undefined);
  const [scripts, setScripts] = useState<CollectionScript[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(false);

  // 新建达人弹窗
  const [personaModalOpen, setPersonaModalOpen] = useState(false);
  const [personaForm] = Form.useForm();
  const [personaSubmitting, setPersonaSubmitting] = useState(false);

  // 新建脚本弹窗
  const [scriptModalOpen, setScriptModalOpen] = useState(false);
  const [scriptForm] = Form.useForm();
  const [scriptSubmitting, setScriptSubmitting] = useState(false);
  const [parsedText, setParsedText] = useState('');
  const [parsingFile, setParsingFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 展开行：存储已展开的 key
  const [expandedRows, setExpandedRows] = useState<number[]>([]);

  const [messageApi, contextHolder] = message.useMessage();

  // ── 加载达人列表 ──────────────────────────────────────────────

  async function loadPersonas() {
    try {
      const data = await getPersonas();
      setPersonas(data.personas);
    } catch {
      messageApi.error('加载达人列表失败');
    }
  }

  useEffect(() => {
    loadPersonas();
  }, []);

  // ── 加载脚本列表 ──────────────────────────────────────────────

  async function loadScripts(p: number, q: string) {
    if (mode === 'persona' && !selectedPersona) {
      setScripts([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    try {
      const data = await getScripts({
        pool: mode,
        persona_name: mode === 'persona' ? selectedPersona : undefined,
        q: q || undefined,
        page: p,
        page_size: PAGE_SIZE,
      });
      setScripts(data.scripts);
      setTotal(data.total);
    } catch {
      messageApi.error('加载脚本列表失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setPage(1);
    setSearch('');
    setSearchInput('');
    loadScripts(1, '');
  }, [mode, selectedPersona]);

  // ── 达人操作 ──────────────────────────────────────────────────

  async function handleCreatePersona() {
    try {
      const values = await personaForm.validateFields();
      setPersonaSubmitting(true);
      await createPersona(values.name);
      messageApi.success(`达人「${values.name}」创建成功`);
      setPersonaModalOpen(false);
      personaForm.resetFields();
      await loadPersonas();
    } catch (e: unknown) {
      if (e instanceof Error) messageApi.error(e.message);
    } finally {
      setPersonaSubmitting(false);
    }
  }

  async function handleDeletePersona(name: string) {
    try {
      await deletePersona(name);
      messageApi.success(`达人「${name}」已删除`);
      if (selectedPersona === name) setSelectedPersona(undefined);
      await loadPersonas();
    } catch (e: unknown) {
      if (e instanceof Error) messageApi.error(e.message);
    }
  }

  // ── 脚本操作 ──────────────────────────────────────────────────

  async function handleCreateScript() {
    try {
      const values = await scriptForm.validateFields();
      setScriptSubmitting(true);
      const body: CreateScriptBody = {
        pool: mode,
        persona_name: mode === 'persona' ? selectedPersona : undefined,
        title: values.title,
        content: values.content,
        likes: values.likes || undefined,
        source: values.source || undefined,
        source_account: values.source_account || undefined,
      };
      await createScript(body);
      messageApi.success('脚本添加成功');
      setScriptModalOpen(false);
      scriptForm.resetFields();
      setParsedText('');
      loadScripts(page, search);
    } catch (e: unknown) {
      if (e instanceof Error) messageApi.error(e.message);
    } finally {
      setScriptSubmitting(false);
    }
  }

  async function handleDeleteScript(id: number) {
    try {
      await deleteScript(id);
      messageApi.success('脚本已删除');
      loadScripts(page, search);
    } catch (e: unknown) {
      if (e instanceof Error) messageApi.error(e.message);
    }
  }

  async function handleParseFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsingFile(true);
    try {
      const result = await parseFile(file);
      setParsedText(result.text);
      scriptForm.setFieldsValue({
        content: result.text,
        title: scriptForm.getFieldValue('title') || file.name.replace(/\.[^.]+$/, ''),
      });
      messageApi.success('文件解析成功');
    } catch (err: unknown) {
      if (err instanceof Error) messageApi.error(err.message);
    } finally {
      setParsingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  // ── 复制和下载 ─────────────────────────────────────────────────

  function copyContent(content: string) {
    navigator.clipboard.writeText(content).then(() => {
      messageApi.success('已复制到剪贴板');
    });
  }

  function downloadTxt(script: CollectionScript) {
    const blob = new Blob([script.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${script.title}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── 搜索 ───────────────────────────────────────────────────────

  function handleSearch() {
    setPage(1);
    setSearch(searchInput);
    loadScripts(1, searchInput);
  }

  // ── 表格列定义 ─────────────────────────────────────────────────

  const columns: ColumnsType<CollectionScript> = [
    {
      title: '序号',
      key: 'index',
      width: 60,
      render: (_: unknown, __: unknown, index: number) => (page - 1) * PAGE_SIZE + index + 1,
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 220,
      ellipsis: true,
    },
    {
      title: '内容预览',
      dataIndex: 'content',
      key: 'content',
      render: (text: string) => (
        <span style={{ color: 'var(--gray-600)', fontSize: 13 }}>
          {text.slice(0, 120)}{text.length > 120 ? '...' : ''}
        </span>
      ),
    },
    {
      title: '点赞数',
      dataIndex: 'likes',
      key: 'likes',
      width: 90,
      render: (val: number | null) => val ? val.toLocaleString() : '—',
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 80,
      render: (val: string | null) => val ? <Tag>{val}</Tag> : '—',
    },
    {
      title: '日期',
      dataIndex: 'script_date',
      key: 'script_date',
      width: 110,
      render: (val: string | null) => val || '—',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: CollectionScript) => (
        <Popconfirm
          title="确认删除这条脚本？"
          onConfirm={() => handleDeleteScript(record.id)}
          okText="删除"
          cancelText="取消"
        >
          <Button type="link" danger size="small" icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  // ── 展开行渲染 ────────────────────────────────────────────────

  function expandedRowRender(record: CollectionScript) {
    return (
      <div style={{ padding: '12px 16px', background: 'var(--gray-50)', borderRadius: 8 }}>
        <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8, color: 'var(--gray-800)', marginBottom: 12 }}>
          {record.content}
        </div>
        <Space>
          <Button size="small" icon={<CopyOutlined />} onClick={() => copyContent(record.content)}>
            复制全文
          </Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadTxt(record)}>
            下载 .txt
          </Button>
          {record.source_account && (
            <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>来源账号：{record.source_account}</span>
          )}
        </Space>
      </div>
    );
  }

  // ── 渲染 ───────────────────────────────────────────────────────

  const canAddScript = mode === 'global' || (mode === 'persona' && !!selectedPersona);

  return (
    <div className="page-container">
      {contextHolder}

      {/* 页头 */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--gray-900)', marginBottom: 4 }}>千川爆文合集</h2>
        <p style={{ color: 'var(--gray-500)', fontSize: 13 }}>收集管理全网高跑量千川脚本，按全网爆款和达人爆款两个维度分池管理</p>
      </div>

      {/* 模式切换 */}
      <Tabs
        activeKey={mode}
        onChange={(k) => { setMode(k as 'global' | 'persona'); setSelectedPersona(undefined); }}
        style={{ marginBottom: 16 }}
        items={[
          { key: 'global', label: '全网爆款' },
          { key: 'persona', label: '达人爆款' },
        ]}
      />

      {/* 达人选择区（persona 模式） */}
      {mode === 'persona' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <Select
            placeholder="选择达人"
            style={{ width: 200 }}
            value={selectedPersona}
            onChange={setSelectedPersona}
            allowClear
            options={personas.map(p => ({
              value: p.name,
              label: `${p.name}（${p.script_count} 条）`,
            }))}
          />
          <Button icon={<PlusOutlined />} onClick={() => setPersonaModalOpen(true)}>
            新建达人
          </Button>
          {selectedPersona && (
            <Popconfirm
              title={`删除达人「${selectedPersona}」及其所有脚本？`}
              onConfirm={() => handleDeletePersona(selectedPersona)}
              okText="删除"
              cancelText="取消"
            >
              <Button danger icon={<DeleteOutlined />}>
                删除达人
              </Button>
            </Popconfirm>
          )}
        </div>
      )}

      {/* 工具栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12 }}>
        <Space>
          <Input
            placeholder="搜索标题或内容..."
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 260 }}
            suffix={<SearchOutlined style={{ cursor: 'pointer', color: 'var(--brand)' }} onClick={handleSearch} />}
          />
          <Button onClick={handleSearch}>搜索</Button>
          {search && (
            <Button onClick={() => { setSearchInput(''); setSearch(''); loadScripts(1, ''); }}>
              清除
            </Button>
          )}
        </Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!canAddScript}
          onClick={() => {
            scriptForm.resetFields();
            setParsedText('');
            setScriptModalOpen(true);
          }}
        >
          添加脚本
        </Button>
      </div>

      {/* 脚本列表 */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <Table
          dataSource={scripts}
          columns={columns}
          rowKey="id"
          loading={loading}
          expandable={{
            expandedRowRender,
            expandedRowKeys: expandedRows,
            onExpand: (expanded, record) => {
              setExpandedRows(expanded
                ? [...expandedRows, record.id]
                : expandedRows.filter(k => k !== record.id)
              );
            },
          }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p) => {
              setPage(p);
              loadScripts(p, search);
            },
          }}
          size="middle"
          locale={{ emptyText: mode === 'persona' && !selectedPersona ? '请先选择达人' : '暂无脚本' }}
        />
      </div>

      {/* 新建达人弹窗 */}
      <Modal
        title="新建达人"
        open={personaModalOpen}
        onOk={handleCreatePersona}
        onCancel={() => { setPersonaModalOpen(false); personaForm.resetFields(); }}
        confirmLoading={personaSubmitting}
        okText="创建"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={personaForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="达人名称"
            rules={[{ required: true, message: '请输入达人名称' }, { max: 100, message: '最多 100 个字符' }]}
          >
            <Input placeholder="输入达人名称，例如：张三" maxLength={100} showCount />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加脚本弹窗 */}
      <Modal
        title="添加脚本"
        open={scriptModalOpen}
        onOk={handleCreateScript}
        onCancel={() => { setScriptModalOpen(false); scriptForm.resetFields(); setParsedText(''); }}
        confirmLoading={scriptSubmitting}
        okText="添加"
        cancelText="取消"
        destroyOnHidden
        width={680}
      >
        <Form form={scriptForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="title"
            label="脚本标题"
            rules={[{ required: true, message: '请输入脚本标题' }]}
          >
            <Input placeholder="输入脚本标题" maxLength={200} showCount />
          </Form.Item>

          <Form.Item label="上传文件（可选）">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.docx,.pdf"
                style={{ display: 'none' }}
                onChange={handleParseFile}
              />
              <Button
                loading={parsingFile}
                onClick={() => fileInputRef.current?.click()}
              >
                上传文件（.txt / .md / .docx / .pdf）
              </Button>
              <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--gray-500)' }}>
                文件内容将自动填入下方输入框
              </span>
            </div>
          </Form.Item>

          <Form.Item
            name="content"
            label="脚本内容"
            rules={[{ required: true, message: '请输入脚本内容' }]}
          >
            <Input.TextArea
              rows={8}
              placeholder="粘贴或上传脚本正文..."
              style={{ resize: 'vertical' }}
            />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item name="likes" label="点赞数（选填）">
              <InputNumber min={0} style={{ width: '100%' }} placeholder="例如：50000" />
            </Form.Item>
            <Form.Item name="source" label="来源平台（选填）">
              <Input placeholder="例如：抖音" maxLength={100} />
            </Form.Item>
          </div>

          <Form.Item name="source_account" label="来源账号（选填）">
            <Input placeholder="来源达人账号名" maxLength={100} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
