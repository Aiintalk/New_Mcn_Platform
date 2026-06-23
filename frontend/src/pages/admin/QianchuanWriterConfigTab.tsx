// frontend/src/pages/admin/QianchuanWriterConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select, Switch } from 'antd';
import { App } from 'antd';
import { getConfigs, updateConfig } from '../../api/qianchuanWriter';
import { getAiModels } from '../../api/ai';
import type { QianchuanWriterConfig } from '../../types/qianchuanWriter';
import type { AiModelItem } from '../../api/ai';

export default function QianchuanWriterConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<QianchuanWriterConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<QianchuanWriterConfig | null>(null);
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

  function openEdit(cfg: QianchuanWriterConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({
      ai_model_id: cfg.ai_model_id,
      system_prompt: cfg.system_prompt,
      is_active: cfg.is_active,
    });
  }

  async function saveConfig(values: {
    ai_model_id: number | null;
    system_prompt: string | null;
    is_active: boolean;
  }) {
    if (!editingConfig) return;
    try {
      await updateConfig(editingConfig.config_key, {
        ai_model_id: values.ai_model_id ?? null,
        system_prompt: values.system_prompt ?? null,
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

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-text">暂无配置</div>
          </div>
        )}
        {configs.map((cfg) => (
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
                  <span style={{ color: 'var(--gray-400)' }}>模型：</span>
                  <span
                    style={{ color: cfg.ai_model_id ? 'var(--gray-800)' : 'var(--warning)' }}
                  >
                    {cfg.ai_model_id
                      ? models.find((m) => m.id === cfg.ai_model_id)?.name ??
                        `ID:${cfg.ai_model_id}`
                      : '使用默认（claude-opus-4-6-thinking）'}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>Prompt：</span>
                  <span
                    style={{ color: cfg.system_prompt ? 'var(--success)' : 'var(--warning)' }}
                  >
                    {cfg.system_prompt
                      ? `已设置（${cfg.system_prompt.length} 字）`
                      : '未设置'}
                  </span>
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
        ))}
      </div>
      <Modal
        title={editingConfig ? `编辑配置：${editingConfig.config_key}` : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnHidden
      >
        <Form form={configForm} layout="vertical" onFinish={saveConfig} style={{ marginTop: 16 }}>
          <Form.Item label="AI 模型" name="ai_model_id">
            <Select
              placeholder="选择已配置的 AI 模型（留空使用默认 claude-opus-4-6-thinking）"
              options={models
                .filter((m) => m.status === 'active')
                .map((m) => ({
                  value: m.id,
                  label: `${m.name} (${m.provider} · ${m.model_id})`,
                }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="系统 Prompt" name="system_prompt">
            <Input.TextArea
              rows={12}
              placeholder="输入系统 Prompt，支持 {{name}} / {{soul}} / {{content_plan}} 占位符..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
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
