/**
 * 评分维度 + Rubric 管理（设计稿 dimensions.html）
 *
 * 左侧：维度列表
 * 右侧：当前编辑维度的配置 form + RubricEditor（level × criteria）
 *
 * 数据接口：admin /api/admin/evaluation/dimensions + /rubrics
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Form, Input, InputNumber, Modal, Select, Skeleton, Switch, Table, Tag } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import '../../styles/variables.css';
import '../styles/eval.css';
import {
  createDimension,
  deleteDimension,
  listDimensions,
  listRubrics,
  replaceRubrics,
  updateDimension,
} from '../api';
import type {
  EvalDimension,
  EvalDimensionCreate,
  EvalDimensionUpdate,
  EvalRubricItemInput,
} from '../types';
import { Callout, PageHeader, WeightBar } from '../components/primitives';

const { TextArea } = Input;

interface RubricRow extends EvalRubricItemInput {
  key: string;
}

const DEFAULT_LEVELS = [10, 8, 6, 4, 2];

export default function DimensionsPage() {
  const { message, modal } = App.useApp();

  const [loading, setLoading] = useState(false);
  const [dimensions, setDimensions] = useState<EvalDimension[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [rubricLoading, setRubricLoading] = useState(false);
  const [rubricScenario, setRubricScenario] = useState<string>('default');
  const [savingRubric, setSavingRubric] = useState(false);

  const [editForm] = Form.useForm<EvalDimensionUpdate>();
  const [createForm] = Form.useForm<EvalDimensionCreate>();
  const [createOpen, setCreateOpen] = useState(false);
  const [savingDimension, setSavingDimension] = useState(false);

  // 本地编辑中的 rubrics（按 scenario 过滤显示，但整批替换）
  const [draftRubrics, setDraftRubrics] = useState<RubricRow[]>([]);

  const loadDimensions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDimensions();
      setDimensions(data);
      if (data.length > 0 && selectedId === null) {
        setSelectedId(data[0].id);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [message, selectedId]);

  useEffect(() => {
    void loadDimensions();
  }, [loadDimensions]);

  // 当前选中的维度对象
  const selected = useMemo(
    () => dimensions.find((d) => d.id === selectedId) ?? null,
    [dimensions, selectedId],
  );

  // 切换维度时同步 form + 加载 rubrics
  useEffect(() => {
    if (!selected) return;
    editForm.setFieldsValue({
      name: selected.name,
      display_name: selected.display_name,
      description: selected.description ?? '',
      default_weight: selected.default_weight,
      score_min: selected.score_min,
      score_max: selected.score_max,
      prompt_template: selected.prompt_template,
      is_active: selected.is_active,
    });
    let cancelled = false;
    (async () => {
      setRubricLoading(true);
      try {
        const data = await listRubrics(selected.id);
        if (cancelled) return;

        setDraftRubrics(
          data.map((r) => ({
            key: `${r.level}-${r.scenario_tag}-${r.id}`,
            level: r.level,
            criteria: r.criteria,
            scenario_tag: r.scenario_tag,
            is_active: r.is_active,
          })),
        );
        // 默认显示 default 场景，若 default 无则取第一个
        const scenarios = Array.from(new Set(data.map((r) => r.scenario_tag)));
        if (!scenarios.includes('default') && scenarios.length > 0) {
          setRubricScenario(scenarios[0]);
        } else {
          setRubricScenario('default');
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : 'Rubric 加载失败';
          message.error(msg);
        }
      } finally {
        if (!cancelled) setRubricLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, editForm, message]);

  const filteredDraft = useMemo(
    () => draftRubrics.filter((r) => r.scenario_tag === rubricScenario),
    [draftRubrics, rubricScenario],
  );

  const handleSaveDimension = async () => {
    if (!selected) return;
    try {
      const values = await editForm.validateFields();
      setSavingDimension(true);
      await updateDimension(selected.id, values);
      message.success('维度配置已保存');
      void loadDimensions();
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSavingDimension(false);
    }
  };

  const handleSaveRubrics = async () => {
    if (!selected) return;
    try {
      setSavingRubric(true);
      // 整批替换：发送所有 draft（不只是当前 scenario 过滤的）
      const items: EvalRubricItemInput[] = draftRubrics.map((r) => ({
        level: r.level,
        criteria: r.criteria,
        scenario_tag: r.scenario_tag || 'default',
        is_active: r.is_active ?? true,
      }));
      await replaceRubrics(selected.id, { rubrics: items });
      message.success(`Rubric 已保存（共 ${items.length} 条）`);
      // 重新加载
      const fresh = await listRubrics(selected.id);

      setDraftRubrics(
        fresh.map((r) => ({
          key: `${r.level}-${r.scenario_tag}-${r.id}`,
          level: r.level,
          criteria: r.criteria,
          scenario_tag: r.scenario_tag,
          is_active: r.is_active,
        })),
      );
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSavingRubric(false);
    }
  };

  const handleAddRubricLevel = () => {
    const newLevel = Math.min(...DEFAULT_LEVELS.filter((l) => !filteredDraft.some((r) => r.level === l)), 1);
    setDraftRubrics((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}`,
        level: newLevel,
        criteria: '',
        scenario_tag: rubricScenario,
        is_active: true,
      },
    ]);
  };

  const handleUpdateDraft = (key: string, patch: Partial<RubricRow>) => {
    setDraftRubrics((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  const handleRemoveDraft = (key: string) => {
    setDraftRubrics((prev) => prev.filter((r) => r.key !== key));
  };

  const handleCreateDimension = async () => {
    try {
      const values = await createForm.validateFields();
      setSavingDimension(true);
      await createDimension(values);
      message.success('维度已创建');
      setCreateOpen(false);
      createForm.resetFields();
      void loadDimensions();
    } catch (err) {
      if (err instanceof Error && err.message) {
        message.error(err.message);
      }
    } finally {
      setSavingDimension(false);
    }
  };

  const handleDeleteDimension = (d: EvalDimension) => {
    modal.confirm({
      title: `软删维度 ${d.display_name}?`,
      content: '维度下的 rubric 仍保留，可通过数据恢复。',
      okText: '软删',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDimension(d.id);
          message.success('已软删（可恢复）');
          if (selectedId === d.id) setSelectedId(null);
          void loadDimensions();
        } catch (err) {
          const msg = err instanceof Error ? err.message : '删除失败';
          message.error(msg);
        }
      },
    });
  };

  const dimColumns: ColumnsType<EvalDimension> = [
    {
      title: '维度（中 / 英）',
      key: 'name',
      render: (_, d) => (
        <a
          onClick={() => setSelectedId(d.id)}
          style={{ color: d.id === selectedId ? 'var(--brand)' : 'var(--gray-900)', fontWeight: 500 }}
        >
          {d.display_name}
          <div style={{ fontSize: 11, color: 'var(--gray-500)', fontFamily: 'var(--font-mono)' }}>{d.name}</div>
        </a>
      ),
    },
    {
      title: '默认权重',
      dataIndex: 'default_weight',
      key: 'default_weight',
      width: 160,
      render: (v: number) => <WeightBar weight={v} />,
    },
    {
      title: '分数区间',
      key: 'range',
      width: 100,
      render: (_, d) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {d.score_min}–{d.score_max}
        </span>
      ),
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
      render: (_, d) => (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => setSelectedId(d.id)}>
            编辑
          </Button>
          <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteDimension(d)}>
            删除
          </Button>
        </div>
      ),
    },
  ];

  const rubricColumns: ColumnsType<RubricRow> = [
    {
      title: '分数等级',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (v: number, r) => (
        <InputNumber
          value={v}
          min={1}
          max={10}
          onChange={(nv) => nv !== null && handleUpdateDraft(r.key, { level: nv })}
          style={{ width: 80 }}
        />
      ),
    },
    {
      title: '标准描述 criteria',
      dataIndex: 'criteria',
      key: 'criteria',
      render: (v: string, r) => (
        <TextArea
          value={v}
          onChange={(e) => handleUpdateDraft(r.key, { criteria: e.target.value })}
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder="例：开头 3 秒钩子极强，叙事流畅，卖点密度高不生硬，强代入感"
        />
      ),
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (v: boolean, r) => <Switch checked={v} onChange={(c) => handleUpdateDraft(r.key, { is_active: c })} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      align: 'right',
      render: (_, r) => (
        <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => handleRemoveDraft(r.key)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <div className="eval-page">
      <PageHeader
        title="维度与评分标准"
        titleTag="v2 · 权重 TBD 安雅"
        description="Dimension → Rubric → Prompt Template 三层结构。权重独立配置不硬编码：策略层 > 版本快照 > 维度默认三级覆盖。"
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void loadDimensions()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建维度
            </Button>
          </>
        }
      />

      <div style={{ marginBottom: 'var(--sp-4)' }}>
        <Callout variant="info" icon="i">
          权重三级覆盖（优先级从高到低）：策略层 <code>dimension_weight_overrides</code> &gt; 版本快照{' '}
          <code>config_payload.dimension_weights</code> &gt; 维度默认 <code>default_weight</code>。
          runner 取最 specific 的命中值；一期三级都只落在「维度默认」。
        </Callout>
      </div>

      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : (
        <div className="card mb-5">
          <div className="card-header">
            <h3>评分维度</h3>
            <span className="ch-sub">{dimensions.length} 个维度 · 权重为占位值，TBD 安雅确认（周会决议）</span>
          </div>
          <div className="card-body flush">
            <Table<EvalDimension>
              rowKey="id"
              columns={dimColumns}
              dataSource={dimensions}
              size="middle"
              pagination={false}
              style={{ padding: '0 var(--sp-5)' }}
              locale={{ emptyText: '暂无维度，点击右上角「新建维度」开始' }}
            />
          </div>
        </div>
      )}

      {selected ? (
        <>
          <Card
            title={`${selected.display_name} · ${selected.name}`}
            extra={
              <Button type="primary" icon={<SaveOutlined />} loading={savingDimension} onClick={() => void handleSaveDimension()}>
                保存配置
              </Button>
            }
            className="mb-5"
            styles={{ body: { padding: 24 } }}
          >
            <Form form={editForm} layout="vertical">
              <div className="form-grid-2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <Form.Item name="name" label="英文名 name">
                  <Input style={{ fontFamily: 'var(--font-mono)' }} />
                </Form.Item>
                <Form.Item name="display_name" label="展示名 display_name">
                  <Input />
                </Form.Item>
                <Form.Item name="default_weight" label="默认权重（0–1）" tooltip="占位值 · 三级覆盖：策略层 > 版本快照 > 维度默认">
                  <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="分数区间">
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <Form.Item name="score_min" noStyle>
                      <InputNumber style={{ width: 'calc(50% - 8px)' }} min={0} />
                    </Form.Item>
                    <span style={{ display: 'inline-block', padding: '0 8px', color: 'var(--gray-400)' }}>—</span>
                    <Form.Item name="score_max" noStyle>
                      <InputNumber style={{ width: 'calc(50% - 8px)' }} min={1} />
                    </Form.Item>
                  </div>
                </Form.Item>
                <Form.Item name="description" label="说明" style={{ gridColumn: '1 / -1' }}>
                  <Input />
                </Form.Item>
                <Form.Item name="is_active" label="启用" valuePropName="checked" style={{ gridColumn: '1 / -1' }}>
                  <Switch />
                </Form.Item>
              </div>
              <Form.Item
                name="prompt_template"
                label="评分 Prompt 模板"
                tooltip="支持占位符：{{generated_output}} / {{rubric_text}} / {{persona}}"
              >
                <TextArea
                  className="code-area"
                  autoSize={{ minRows: 6, maxRows: 16 }}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5 }}
                />
              </Form.Item>
            </Form>
          </Card>

          <Card
            title={
              <span>
                Rubric 评分标准
              </span>
            }
            extra={
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size="small" icon={<PlusOutlined />} onClick={handleAddRubricLevel}>
                  添加等级
                </Button>
                <Button type="primary" icon={<SaveOutlined />} loading={savingRubric} onClick={() => void handleSaveRubrics()}>
                  保存全部修改
                </Button>
              </div>
            }
            styles={{ body: { padding: 0 } }}
          >

            {rubricLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} style={{ padding: 'var(--sp-5)' }} />
            ) : (
              <Table<RubricRow>
                rowKey="key"
                columns={rubricColumns}
                dataSource={filteredDraft}
                size="middle"
                pagination={false}
                style={{ padding: '0 var(--sp-5)' }}
                locale={{ emptyText: `暂无 ${rubricScenario} 场景变体的 rubric，点击右上角添加等级` }}
              />
            )}

            <div style={{ padding: '12px var(--sp-5)', borderTop: '1px solid var(--border)', color: 'var(--gray-500)', fontSize: 12 }}>
              完整 5 档量化表由安雅模板（scoring-alignment-anya.md）产出后录入；细则在池子里、策略负责选，不是加 tag。
            </div>
          </Card>
        </>
      ) : (
        <Callout variant="info" icon="i">
          选择上方某个维度，或新建一个维度来配置评分 Prompt 与 Rubric 等级标准。
        </Callout>
      )}

      <Modal
        title="新建维度"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void handleCreateDimension()}
        confirmLoading={savingDimension}
        okText="创建"
        cancelText="取消"
        destroyOnHidden
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{
            tool_code: 'qianchuan-writer',
            name: '',
            display_name: '',
            description: '',
            default_weight: 0.33,
            score_min: 1,
            score_max: 10,
            prompt_template:
              '你是千川脚本文案评审专家。请对以下脚本在【{{dimension_name}}】维度打分。\n评分标准：{{rubric_text}}\n\n输出格式（严格 JSON）：{score, reasoning, strengths, weaknesses}\n\n被评脚本：{{generated_output}}',
            is_active: true,
          }}
        >
          <Form.Item name="tool_code" label="tool_code" rules={[{ required: true }]}>
            <Select options={[{ label: 'qianchuan-writer', value: 'qianchuan-writer' }]} />
          </Form.Item>
          <Form.Item name="name" label="英文名 name" rules={[{ required: true }]}>
            <Input style={{ fontFamily: 'var(--font-mono)' }} placeholder="例：copy_quality" />
          </Form.Item>
          <Form.Item name="display_name" label="展示名 display_name" rules={[{ required: true }]}>
            <Input placeholder="例：文案质量" />
          </Form.Item>
          <Form.Item name="default_weight" label="默认权重（0–1）" rules={[{ required: true }]}>
            <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
