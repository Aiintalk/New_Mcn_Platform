// frontend/src/pages/admin/TiktokReviewConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { App } from 'antd';
import { getAdminConfigs, updateAdminConfig } from '../../api/tiktokReview';
import { getAiModels } from '../../api/ai';
import type { TiktokReviewConfig } from '../../types/tiktokReview';
import type { AiModelItem } from '../../api/ai';

export default function TiktokReviewConfigTab() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<TiktokReviewConfig[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<TiktokReviewConfig | null>(null);
  const [configForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgResp, mdResp] = await Promise.all([
        getAdminConfigs(),
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

  useEffect(() => { loadData(); }, [loadData]);

  function openEdit(cfg: TiktokReviewConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await updateAdminConfig(editingConfig.config_key, {
        ai_model_id: values.ai_model_id ?? null,
        system_prompt: values.system_prompt ?? null,
        is_active: true,
      });
      message.success('配置已保存');
      setEditingConfig(null);
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  if (loading) return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && (
          <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>
        )}
        {configs.map(cfg => (
          <div key={cfg.config_key} className="card">
            <div className="card-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>TT内容复盘 · {cfg.config_key}</div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>
                    config_key: {cfg.config_key}
                  </div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => openEdit(cfg)}>编辑</button>
              </div>
              <div style={{ display: 'flex', gap: 20, fontSize: 13 }}>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>模型：</span>
                  <span style={{ color: cfg.ai_model_id ? 'var(--gray-800)' : 'var(--danger)' }}>
                    {cfg.ai_model_id
                      ? (models.find(m => m.id === cfg.ai_model_id)?.name ?? `ID:${cfg.ai_model_id}`)
                      : '⚠ 未配置（使用默认）'}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--gray-400)' }}>Prompt：</span>
                  <span style={{ color: cfg.system_prompt ? 'var(--success)' : 'var(--warning)' }}>
                    {cfg.system_prompt ? `已设置（${cfg.system_prompt.length} 字）` : '未设置'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal
        title={editingConfig ? `TT内容复盘 · ${editingConfig.config_key}` : ''}
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
              options={models.filter(m => m.status === 'active').map(m => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item label="系统 Prompt" name="system_prompt">
            <Input.TextArea
              rows={14}
              placeholder="输入系统 Prompt..."
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
