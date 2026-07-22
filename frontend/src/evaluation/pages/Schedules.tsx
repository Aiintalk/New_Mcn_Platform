/**
 * 定时策略（设计稿 schedules.html）
 *
 * 数据接口：admin /api/admin/evaluation/schedule-policies（CRUD）
 * cron 写入前由后端 croniter 校验；本地编辑器提供 5 字段输入 + 下次执行预览。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Form, Input, Modal, Select, Skeleton, Switch, Table, Tag } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import {
  createSchedulePolicy,
  deleteSchedulePolicy,
  listSchedulePolicies,
  listVersionsAdmin,
  updateSchedulePolicy,
} from '../api';
import type {
  EvalSchedulePolicy,
  EvalSchedulePolicyCreate,
  EvalSchedulePolicyUpdate,
  EvalVersion,
} from '../types';
import { Callout, PageHeader, formatShortTime } from '../components/primitives';

// 简单的 cron 预览：仅识别 5 字段，给出"看起来合法"的提示（最终以后端 croniter 校验为准）
function looksLikeCron(expr: string): boolean {
  return expr.trim().split(/\s+/).length === 5;
}

// 粗略计算下次执行时间（仅供 UI 提示，最终以后端为准）
function previewNextRun(expr: string): string {
  if (!looksLikeCron(expr)) return 'cron 表达式需 5 个字段';
  // 简单预览：取分钟 + 小时字段，组合今日 / 明日
  const parts = expr.trim().split(/\s+/);
  const [min, hour] = parts;
  if (min === '*' || hour === '*') return '每分钟/每小时触发（按 cron 实际解析）';
  return `下次执行预览仅参考，实际以 croniter 解析为准（min=${min} hour=${hour}）`;
}

export default function SchedulesPage() {
  const { message, modal } = App.useApp();

  const [loading, setLoading] = useState(false);
  const [policies, setPolicies] = useState<EvalSchedulePolicy[]>([]);
  const [versions, setVersions] = useState<EvalVersion[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [cronInput, setCronInput] = useState('0 2 * * *');

  const [form] = Form.useForm<EvalSchedulePolicyCreate & EvalSchedulePolicyUpdate>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ps, vs] = await Promise.all([listSchedulePolicies(), listVersionsAdmin()]);
      setPolicies(ps);
      setVersions(vs);
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

  const openCreate = () => {
    setEditingId(null);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      cron: '0 2 * * *',
      version_id: null,
      filter_tags: [],
      is_active: true,
    });
    setCronInput('0 2 * * *');
    setEditOpen(true);
  };

  const openEdit = (p: EvalSchedulePolicy) => {
    setEditingId(p.id);
    form.setFieldsValue({
      name: p.name,
      cron: p.cron,
      version_id: p.version_id,
      filter_tags: p.filter_tags,
      is_active: p.is_active,
    });
    setCronInput(p.cron);
    setEditOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const body: EvalSchedulePolicyCreate & EvalSchedulePolicyUpdate = {
        name: values.name,
        cron: values.cron,
        version_id: values.version_id ?? null,
        filter_tags: values.filter_tags ?? [],
        is_active: values.is_active ?? true,
      };
      if (editingId !== null) {
        await updateSchedulePolicy(editingId, body);
        message.success('策略已保存');
      } else {
        await createSchedulePolicy(body);
        message.success('策略已创建');
      }
      setEditOpen(false);
      void load();
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (p: EvalSchedulePolicy) => {
    modal.confirm({
      title: `软删策略 ${p.name}?`,
      content: '策略删除后可恢复，正在运行的执行不受影响。',
      okText: '软删',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteSchedulePolicy(p.id);
          message.success('已软删（可恢复）');
          void load();
        } catch (err) {
          const msg = err instanceof Error ? err.message : '删除失败';
          message.error(msg);
        }
      },
    });
  };

  const columns: ColumnsType<EvalSchedulePolicy> = [
    {
      title: '策略名',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <span style={{ color: 'var(--gray-900)', fontWeight: 500 }}>{v}</span>,
    },
    {
      title: 'cron 表达式',
      dataIndex: 'cron',
      key: 'cron',
      width: 160,
      render: (v: string) => (
        <Tag color="default" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, margin: 0 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version_id',
      key: 'version_id',
      width: 160,
      render: (v: number | null) =>
        v === null ? <span className="text-muted">最新启用版本</span> : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>v#{v}</span>,
    },
    {
      title: '样本标签',
      dataIndex: 'filter_tags',
      key: 'filter_tags',
      render: (tags: string[]) =>
        tags.length === 0 ? (
          <span className="text-muted">—</span>
        ) : (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {tags.map((t) => (
              <Tag key={t} color="brand" style={{ margin: 0 }}>
                {t}
              </Tag>
            ))}
          </div>
        ),
    },
    {
      title: '下次执行',
      key: 'next',
      width: 140,
      render: (_, p) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatShortTime(p.cron ? undefined : null)}</span>,
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (v: boolean) =>
        v ? (
          <Tag color="success" style={{ margin: 0 }}>
            on
          </Tag>
        ) : (
          <Tag color="default" style={{ margin: 0 }}>
            off
          </Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'right',
      render: (_, p) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(p)}>
            编辑
          </Button>
          <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(p)}>
            删除
          </Button>
        </div>
      ),
    },
  ];

  const cronValid = useMemo(() => looksLikeCron(cronInput), [cronInput]);
  const preview = useMemo(() => previewNextRun(cronInput), [cronInput]);

  return (
    <div className="eval-page">
      <PageHeader
        title="定时策略"
        description="配置 cron 定时触发批量回归（如夜间全量）。写入前用 croniter 校验合法性，非法 cron 不允许保存。"
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建策略
            </Button>
          </>
        }
      />

      <div style={{ marginBottom: 'var(--sp-4)' }}>
        <Callout variant="info" icon="i">
          一期建议先实现手动 + 版本创建自动触发；定时触发作为补充，可先用简单 cron endpoint。version_id 留空表示使用最新 active 版本。
        </Callout>
      </div>

      <div className="card">
        <div className="card-body flush">
          {loading ? (
            <div style={{ padding: 'var(--sp-5)' }}>
              <Skeleton active paragraph={{ rows: 4 }} />
            </div>
          ) : (
            <Table<EvalSchedulePolicy>
              rowKey="id"
              columns={columns}
              dataSource={policies}
              size="middle"
              pagination={false}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '暂无定时策略，点击右上角「新建策略」开始配置 cron 回归' }}
            />
          )}
          <div style={{ padding: 'var(--sp-4) var(--sp-5)', color: 'var(--gray-500)', fontSize: 12 }}>
            共 {policies.length} 条策略
          </div>
        </div>
      </div>

      <Modal
        title={editingId !== null ? '编辑定时策略' : '新建定时策略'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => void handleSave()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        width={520}
      >
        <Form form={form} layout="vertical" initialValues={{ is_active: true, cron: '0 2 * * *' }}>
          <Form.Item name="name" label="策略名" rules={[{ required: true, message: '请输入策略名' }]}>
            <Input placeholder="例：夜间全量回归" />
          </Form.Item>

          <Form.Item
            name="cron"
            label={
              <span>
                cron 表达式{' '}
                {cronValid ? (
                  <Tag color="success" style={{ marginInlineStart: 4 }}>
                    ✓ 看起来合法
                  </Tag>
                ) : (
                  <Tag color="error" style={{ marginInlineStart: 4 }}>
                    需 5 字段
                  </Tag>
                )}
              </span>
            }
            rules={[{ required: true, message: '请输入 cron 表达式' }]}
            extra="写入前用 croniter 校验；5 字段：分 时 日 月 周"
          >
            <Input
              style={{ fontFamily: 'var(--font-mono)' }}
              placeholder="0 2 * * *"
              onChange={(e) => setCronInput(e.target.value)}
            />
          </Form.Item>

          <Form.Item name="version_id" label="被测版本" tooltip="留空表示使用最新 active 版本">
            <Select
              allowClear
              placeholder="最新启用版本（latest_active）"
              options={versions.map((v) => ({
                label: `${v.name}${v.is_active ? '（启用）' : ''}`,
                value: v.id,
              }))}
            />
          </Form.Item>

          <Form.Item name="filter_tags" label="样本标签集">
            <Select mode="tags" placeholder="+ 添加标签" tokenSeparators={[',']} />
          </Form.Item>

          <Form.Item name="is_active" label="立即启用" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Callout variant="info" icon="⏰">
            下次执行：{preview}
          </Callout>
        </Form>
      </Modal>
    </div>
  );
}
