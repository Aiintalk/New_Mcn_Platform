/**
 * 版本快照（设计稿 versions.html + version-create.html）
 *
 * 列表 + 创建抽屉（关联维护 source_kol_id）+ clone + 软删。
 * 数据接口：admin /api/admin/evaluation/versions（CRUD）。
 *
 * 注：本页放在 admin 路由下（/admin/evaluation/versions），admin only。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Drawer, Form, Input, InputNumber, Select, Skeleton, Switch, Table, Tag } from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import {
  cloneVersion,
  createVersion,
  deleteVersion,
  listDimensions,
  listVersionsAdmin,
} from '../api';
import type { EvalDimension, EvalVersion, EvalVersionClone, EvalVersionCreate } from '../types';
import { Callout, PageHeader, formatShortTime } from '../components/primitives';

const { TextArea } = Input;

export default function VersionsPage() {
  const { message, modal } = App.useApp();

  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<EvalVersion[]>([]);
  const [dimensions, setDimensions] = useState<EvalDimension[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cloneTarget, setCloneTarget] = useState<EvalVersion | null>(null);

  const [createForm] = Form.useForm<EvalVersionCreate & { dimensionWeights: Record<number, number> }>();
  const [cloneForm] = Form.useForm<EvalVersionClone>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [vs, ds] = await Promise.all([listVersionsAdmin(), listDimensions()]);
      setVersions(vs);
      setDimensions(ds);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredVersions = useMemo(() => {
    let list = versions;
    if (search.trim()) {
      const kw = search.trim().toLowerCase();
      list = list.filter(
        (v) =>
          v.name.toLowerCase().includes(kw) ||
          (v.description ?? '').toLowerCase().includes(kw),
      );
    }
    if (statusFilter === 'active') list = list.filter((v) => v.is_active);
    if (statusFilter === 'inactive') list = list.filter((v) => !v.is_active);
    return list;
  }, [versions, search, statusFilter]);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setSaving(true);
      const weights = values.dimensionWeights ?? {};
      const configPayload: Record<string, unknown> = {
        ...(values.config_payload ?? {}),
        dimension_weights: weights,
      };
      const body: EvalVersionCreate = {
        tool_code: 'qianchuan-writer',
        name: values.name,
        description: values.description ?? null,
        config_payload: configPayload,
        parent_version_id: values.parent_version_id ?? null,
        source_kol_id: values.source_kol_id ?? null,
        scoring_model_id: values.scoring_model_id ?? null,
        scoring_provider: values.scoring_provider ?? null,
        scoring_adapter: values.scoring_adapter ?? null,
        auto_run_on_create: values.auto_run_on_create ?? false,
        auto_run_tags: values.auto_run_tags ?? [],
        is_active: values.is_active ?? true,
      };
      const created = await createVersion(body);
      message.success(`版本 ${created.name} 已创建${body.auto_run_on_create ? '，已自动触发回归' : ''}`);
      setCreateOpen(false);
      createForm.resetFields();
      void load();
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleClone = async () => {
    if (!cloneTarget) return;
    try {
      const values = await cloneForm.validateFields();
      setSaving(true);
      const body: EvalVersionClone = {
        name: values.name,
        description: values.description ?? null,
        config_payload_overrides: values.config_payload_overrides ?? undefined,
        auto_run_on_create: values.auto_run_on_create ?? false,
        auto_run_tags: values.auto_run_tags ?? [],
        is_active: values.is_active ?? true,
      };
      const cloned = await cloneVersion(cloneTarget.id, body);
      message.success(`已复制为新版本：${cloned.name}`);
      setCloneTarget(null);
      cloneForm.resetFields();
      void load();
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (v: EvalVersion) => {
    modal.confirm({
      title: `软删版本 ${v.name}?`,
      content: '版本快照删除后可恢复，但历史运行引用不受影响。',
      okText: '软删',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteVersion(v.id);
          message.success('已软删（可恢复）');
          void load();
        } catch (err) {
          const msg = err instanceof Error ? err.message : '删除失败';
          message.error(msg);
        }
      },
    });
  };

  const columns: ColumnsType<EvalVersion> = [
    {
      title: '版本名',
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r) => (
        <span style={{ color: 'var(--gray-900)', fontWeight: 500 }}>
          {v}
          {r.is_active ? (
            <Tag color="success" style={{ marginLeft: 8, marginInlineEnd: 0 }}>
              最新
            </Tag>
          ) : null}
        </span>
      ),
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
      render: (v) => <span className="text-muted">{v ?? '—'}</span>,
    },
    {
      title: '派生自',
      dataIndex: 'parent_version_id',
      key: 'parent_version_id',
      width: 80,
      render: (v) => (v ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>v#{v}</span> : '—'),
    },
    {
      title: '来源红人',
      dataIndex: 'source_kol_id',
      key: 'source_kol_id',
      width: 100,
      render: (v) => (v ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>kol#{v}</span> : '全局默认'),
    },
    {
      title: '自动触发',
      key: 'auto_run',
      width: 100,
      render: (_, r) =>
        r.auto_run_on_create ? (
          <Tag color="brand" style={{ margin: 0 }}>
            {r.auto_run_tags.length > 0 ? r.auto_run_tags.join(',') : 'all'}
          </Tag>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 130,
      render: (v) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatShortTime(v)}</span>,
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (v: boolean) =>
        v ? (
          <Tag color="success" style={{ margin: 0 }}>
            启用
          </Tag>
        ) : (
          <Tag color="default" style={{ margin: 0 }}>
            停用
          </Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      align: 'right',
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
          <Button
            size="small"
            type="link"
            icon={<CopyOutlined />}
            onClick={() => {
              setCloneTarget(r);
              cloneForm.setFieldsValue({
                name: `${r.name}-copy`,
                description: r.description ?? '',
                auto_run_on_create: false,
                auto_run_tags: r.auto_run_tags,
                is_active: false,
              });
            }}
          >
            复制为新版本
          </Button>
          <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>
            删除
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="eval-page">
      <PageHeader
        title="版本快照"
        description="固化一版 Prompt + 模型 + 参数 + 维度权重的不可编辑存档，保证历史运行可复现。"
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建版本
            </Button>
          </>
        }
      />

      <div style={{ marginBottom: 'var(--sp-4)' }}>
        <Callout variant="warn" icon="!">
          版本快照不可编辑。要调整配置必须「复制为新版本」派生。删除一律走软删（deleted_at），可恢复。
          v2 关联维护：config_payload 由系统只读抠现有千川仿写配置（resolve_prompt + kol_context）固化，来源红人记录在 source_kol_id。
        </Callout>
      </div>

      <div className="card">
        <div className="card-body flush">
          <div style={{ padding: 'var(--sp-4) var(--sp-5) 0' }}>
            <div className="filter-bar">
              <Input
                className="filter-input"
                placeholder="🔍 搜索版本名 / 说明"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                allowClear
                style={{ minWidth: 240 }}
              />
              <Select
                className="filter-select"
                style={{ width: 140 }}
                value={statusFilter}
                onChange={setStatusFilter}
                options={[
                  { label: '全部状态', value: 'all' },
                  { label: '启用', value: 'active' },
                  { label: '已停用', value: 'inactive' },
                ]}
              />
              <span className="filter-count">共 {versions.length} 个版本</span>
              <span className="grow" />
            </div>
          </div>

          {loading ? (
            <div style={{ padding: 'var(--sp-5)' }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : (
            <Table<EvalVersion>
              rowKey="id"
              columns={columns}
              dataSource={filteredVersions}
              size="middle"
              pagination={{ pageSize: 20 }}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '暂无版本快照' }}
            />
          )}
        </div>
      </div>

      {/* 创建版本抽屉 */}
      <Drawer
        title="新建版本快照"
        placement="right"
        width={640}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleCreate()}>
            创建版本
          </Button>
        }
        destroyOnClose
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{
            tool_code: 'qianchuan-writer',
            name: '',
            description: '',
            source_kol_id: null,
            scoring_model_id: 'glm-5.2',
            scoring_provider: 'yunwu',
            scoring_adapter: 'yunwu',
            auto_run_on_create: false,
            auto_run_tags: [],
            is_active: true,
            dimensionWeights: Object.fromEntries(dimensions.map((d) => [d.id, d.default_weight])),
          }}
        >
          <Card size="small" title="基础信息" style={{ marginBottom: 16 }}>
            <Form.Item name="name" label="版本名" rules={[{ required: true, message: '请输入版本名' }]}>
              <Input placeholder="例：v1.3-行动引导" />
            </Form.Item>
            <Form.Item name="description" label="说明">
              <Input placeholder="本次变更的一句话描述" />
            </Form.Item>
            <Form.Item name="source_kol_id" label="来源红人 source_kol_id（关联维护三步）" tooltip="选填：触发 resolve_prompt + kol_context 抠 system_prompt_template">
              <InputNumber style={{ width: '100%' }} placeholder="留空 → 由管理员直接填 config_payload" min={1} />
            </Form.Item>
          </Card>

          <Card size="small" title="评分模型（评委，v2）" style={{ marginBottom: 16 }}>
            <Form.Item name="scoring_model_id" label="评委模型 model_id">
              <Select
                options={[
                  { label: 'glm-5.2（当前默认）', value: 'glm-5.2' },
                  { label: 'glm-4.7', value: 'glm-4.7' },
                ]}
              />
            </Form.Item>
            <Form.Item name="scoring_provider" label="provider">
              <Select options={[{ label: 'yunwu', value: 'yunwu' }]} />
            </Form.Item>
            <Form.Item name="scoring_adapter" label="adapter（一期唯一 yunwu）">
              <Select options={[{ label: 'yunwu', value: 'yunwu' }]} />
            </Form.Item>
          </Card>

          {dimensions.length > 0 ? (
            <Card size="small" title="维度权重覆盖（默认填入维度默认值）" style={{ marginBottom: 16 }}>
              {dimensions.map((d) => (
                <Form.Item
                  key={d.id}
                  name={['dimensionWeights', d.id]}
                  label={d.display_name}
                  tooltip={`默认权重 ${d.default_weight}`}
                >
                  <InputNumber min={0} max={1} step={0.05} style={{ width: 120 }} />
                </Form.Item>
              ))}
              <div className="text-xs text-muted">
                权重之和应为 1.0；当前值：默认填入维度默认值（请人工核对）
              </div>
            </Card>
          ) : null}

          <Card size="small" title="创建后行为">
            <Form.Item name="auto_run_on_create" label="创建后自动触发回归运行" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="auto_run_tags" label="自动触发覆盖的样本标签集">
              <Select mode="tags" placeholder="留空表示全部启用样本" tokenSeparators={[',']} />
            </Form.Item>
            <Form.Item name="is_active" label="立即启用为 active 版本" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Card>

          <Callout variant="info" icon="i">
            创建后版本将写入 eval_versions，同时插入 OperationLog。
          </Callout>
        </Form>
      </Drawer>

      {/* clone 抽屉 */}
      <Drawer
        title={`复制为新版本（基于 ${cloneTarget?.name ?? ''}）`}
        placement="right"
        width={520}
        open={cloneTarget !== null}
        onClose={() => setCloneTarget(null)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleClone()}>
            创建副本
          </Button>
        }
        destroyOnClose
      >
        {cloneTarget ? (
          <Form form={cloneForm} layout="vertical">
            <Form.Item name="name" label="新版本名" rules={[{ required: true, message: '请输入版本名' }]}>
              <Input />
            </Form.Item>
            <Form.Item name="description" label="说明">
              <TextArea rows={3} />
            </Form.Item>
            <Form.Item name="config_payload_overrides" label="config_payload 覆盖（JSON，可选）" tooltip="部分覆盖父版本 config_payload">
              <TextArea
                rows={6}
                className="code-area"
                placeholder='{ "system_prompt_template": "..." }'
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5 }}
              />
            </Form.Item>
            <Form.Item name="auto_run_on_create" label="创建后自动触发回归" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="auto_run_tags" label="自动触发覆盖的样本标签集">
              <Select mode="tags" placeholder="留空表示全部启用样本" tokenSeparators={[',']} />
            </Form.Item>
            <Form.Item name="is_active" label="立即启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Callout variant="warn" icon="!">
              克隆会拷贝父版本 ({cloneTarget.name}) 的 config_payload + parent_version_id。
            </Callout>
          </Form>
        ) : null}
      </Drawer>
    </div>
  );
}
