// frontend/src/pages/admin/SeedingWriterConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select, Switch } from 'antd';
import { App } from 'antd';
import { getConfigs, updateConfig } from '../../api/seedingWriter';
import { getAiModels } from '../../api/ai';
import type { SeedingWriterConfig } from '../../types/seedingWriter';
import type { AiModelItem } from '../../api/ai';

const { TextArea } = Input;

export default function SeedingWriterConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<SeedingWriterConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<SeedingWriterConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mdResp] = await Promise.all([
        getConfigs(),
        getAiModels().catch(() => ({ items: [] as AiModelItem[], total: 0 })),
      ]);
      setConfigs(Array.isArray(cfgResp) ? cfgResp : []);
      setModels(mdResp.items ?? []);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function openEdit(cfg: SeedingWriterConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({
      sp_system_prompt: cfg.sp_system_prompt,
      parse_product_prompt: cfg.parse_product_prompt,
      structure_analysis_prompt: cfg.structure_analysis_prompt,
      ai_recommend_prompt: cfg.ai_recommend_prompt,
      writing_prompt: cfg.writing_prompt,
      iteration_prompt: cfg.iteration_prompt,
      light_model_id: cfg.light_model_id,
      heavy_model_id: cfg.heavy_model_id,
      is_active: cfg.is_active,
    });
  }

  async function saveConfig(values: {
    sp_system_prompt: string | null;
    parse_product_prompt: string | null;
    structure_analysis_prompt: string | null;
    ai_recommend_prompt: string | null;
    writing_prompt: string | null;
    iteration_prompt: string | null;
    light_model_id: number | null;
    heavy_model_id: number | null;
    is_active: boolean;
  }) {
    if (!editingConfig) return;
    try {
      await updateConfig(editingConfig.config_key, {
        sp_system_prompt: values.sp_system_prompt ?? null,
        parse_product_prompt: values.parse_product_prompt ?? null,
        structure_analysis_prompt: values.structure_analysis_prompt ?? null,
        ai_recommend_prompt: values.ai_recommend_prompt ?? null,
        writing_prompt: values.writing_prompt ?? null,
        iteration_prompt: values.iteration_prompt ?? null,
        light_model_id: values.light_model_id ?? null,
        heavy_model_id: values.heavy_model_id ?? null,
        is_active: values.is_active,
      });
      message.success('配置已保存');
      setEditingConfig(null);
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">加载中...</div>
      </div>
    );
  }

  const activeModels = models.filter((m) => m.status === 'active');

  /** 统计配置显示状态 */
  function promptStatus(val: string | null): { text: string; color: string } {
    return val
      ? { text: `已设置（${val.length} 字）`, color: 'var(--success)' }
      : { text: '未设置', color: 'var(--warning)' };
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-text">暂无配置</div>
          </div>
        )}
        {configs.map((cfg) => {
          const sp = promptStatus(cfg.sp_system_prompt);
          const pp = promptStatus(cfg.parse_product_prompt);
          const sa = promptStatus(cfg.structure_analysis_prompt);
          const ar = promptStatus(cfg.ai_recommend_prompt);
          const wp = promptStatus(cfg.writing_prompt);
          const ip = promptStatus(cfg.iteration_prompt);
          return (
            <div key={cfg.config_key} className="card">
              <div className="card-body">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: 12,
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>
                      {cfg.config_key === 'default' ? '默认配置' : cfg.config_key}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>
                      config_key: {cfg.config_key}
                    </div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={() => openEdit(cfg)}>
                    编辑
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 20, fontSize: 13, flexWrap: 'wrap' }}>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>轻量模型：</span>
                    <span
                      style={{ color: cfg.light_model_id ? 'var(--gray-800)' : 'var(--warning)' }}
                    >
                      {cfg.light_model_id
                        ? activeModels.find((m) => m.id === cfg.light_model_id)?.name ??
                          `ID:${cfg.light_model_id}`
                        : '使用默认（claude-haiku-4-5）'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>重型模型：</span>
                    <span
                      style={{ color: cfg.heavy_model_id ? 'var(--gray-800)' : 'var(--warning)' }}
                    >
                      {cfg.heavy_model_id
                        ? activeModels.find((m) => m.id === cfg.heavy_model_id)?.name ??
                          `ID:${cfg.heavy_model_id}`
                        : '使用默认（claude-opus-4-6）'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>卖点提取 Prompt：</span>
                    <span style={{ color: sp.color }}>{sp.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>文档解析 Prompt：</span>
                    <span style={{ color: pp.color }}>{pp.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>结构拆解 Prompt：</span>
                    <span style={{ color: sa.color }}>{sa.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>AI 推荐 Prompt：</span>
                    <span style={{ color: ar.color }}>{ar.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>写作 Prompt：</span>
                    <span style={{ color: wp.color }}>{wp.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>迭代 Prompt：</span>
                    <span style={{ color: ip.color }}>{ip.text}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>状态：</span>
                    <span
                      className={`badge ${cfg.is_active ? 'badge-success' : 'badge-gray'}`}
                    >
                      {cfg.is_active ? '启用' : '停用'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <Modal
        title={editingConfig ? `编辑配置：${editingConfig.config_key}` : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={820}
        destroyOnHidden
      >
        <Form form={configForm} layout="vertical" onFinish={saveConfig} style={{ marginTop: 16 }}>
          <Form.Item label="卖点提取系统 Prompt（heavy 模型）" name="sp_system_prompt">
            <TextArea
              rows={10}
              placeholder="输入卖点提取系统 Prompt，支持 {{raw_text}} 占位符..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="文档解析 Prompt（heavy 模型，固定 JSON 输出）" name="parse_product_prompt">
            <TextArea
              rows={8}
              placeholder="输入文档解析 Prompt..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="结构拆解 Prompt（light 模型）" name="structure_analysis_prompt">
            <TextArea
              rows={8}
              placeholder="输入结构拆解 Prompt，支持 {{transcript}} 占位符..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="AI 推荐角度 Prompt（light 模型）" name="ai_recommend_prompt">
            <TextArea
              rows={8}
              placeholder="输入 AI 推荐角度 Prompt..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="写作 Prompt（heavy 模型，支持 {{name}}...{{/name}} 等占位符）" name="writing_prompt">
            <TextArea
              rows={16}
              placeholder="输入写作 Prompt，支持全部 14 个占位符..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="迭代 Prompt（heavy 模型）" name="iteration_prompt">
            <TextArea
              rows={12}
              placeholder="输入多轮迭代 Prompt..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item label="轻量 AI 模型（结构拆解/AI 推荐）" name="light_model_id">
            <Select
              placeholder="选择 AI 模型（留空使用默认 claude-haiku-4-5）"
              options={activeModels.map((m) => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="重型 AI 模型（卖点/写作/迭代）" name="heavy_model_id">
            <Select
              placeholder="选择 AI 模型（留空使用默认 claude-opus-4-6）"
              options={activeModels.map((m) => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="启用状态" name="is_active" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
