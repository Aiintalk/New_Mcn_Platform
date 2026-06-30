// frontend/src/pages/admin/ValuesWriterConfigTab.tsx
import { useState, useEffect, useCallback } from 'react';
import { Form, Input, Select, Switch, App } from 'antd';
import { getConfig, updateConfig } from '../../api/valuesWriter';
import { getAiModels } from '../../api/ai';
import type { ValuesWriterConfig } from '../../types/valuesWriter';
import type { AiModelItem } from '../../api/ai';

const { TextArea } = Input;

type FormValues = {
  extract_values_prompt: string | null;
  emotion_direction_prompt: string | null;
  writing_prompt: string | null;
  iteration_prompt: string | null;
  model_id: number | null;
  is_active: boolean;
};

export default function ValuesWriterConfigTab() {
  const { message } = App.useApp();
  const [config, setConfig] = useState<ValuesWriterConfig | null>(null);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FormValues>();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, mdResp] = await Promise.all([
        getConfig(),
        getAiModels().catch(() => ({ items: [] as AiModelItem[], total: 0 })),
      ]);
      setConfig(cfg);
      setModels(mdResp.items ?? []);
      form.setFieldsValue({
        extract_values_prompt: cfg.extract_values_prompt,
        emotion_direction_prompt: cfg.emotion_direction_prompt,
        writing_prompt: cfg.writing_prompt,
        iteration_prompt: cfg.iteration_prompt,
        model_id: cfg.model_id,
        is_active: cfg.is_active,
      });
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [message, form]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleSave(values: FormValues) {
    setSaving(true);
    try {
      await updateConfig({
        extract_values_prompt: values.extract_values_prompt ?? null,
        emotion_direction_prompt: values.emotion_direction_prompt ?? null,
        writing_prompt: values.writing_prompt ?? null,
        iteration_prompt: values.iteration_prompt ?? null,
        model_id: values.model_id ?? null,
        is_active: values.is_active,
      });
      message.success('配置已保存');
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">加载中...</div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">暂无配置</div>
      </div>
    );
  }

  const activeModels = models.filter((m) => m.status === 'active');

  return (
    <div style={{ maxWidth: 860 }}>
      <div className="card" style={{ marginBottom: 0 }}>
        <div className="card-header">
          <h2 className="card-title">价值观仿写配置</h2>
          <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
            config_key: {config.config_key}
            {config.updated_at && (
              <span style={{ marginLeft: 12 }}>
                最后更新：{new Date(config.updated_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>
        <div className="card-body">
          <Form form={form} layout="vertical" onFinish={handleSave}>
            <Form.Item label="价值观提炼 Prompt" name="extract_values_prompt">
              <TextArea
                rows={8}
                placeholder="输入价值观提炼 Prompt，支持 {{kol_name}}、{{persona}} 等占位符..."
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              />
            </Form.Item>
            <Form.Item label="情绪方向生成 Prompt" name="emotion_direction_prompt">
              <TextArea
                rows={8}
                placeholder="输入情绪方向生成 Prompt，支持 {{selected_values}}、{{tone}} 等占位符..."
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              />
            </Form.Item>
            <Form.Item label="内容写作 Prompt" name="writing_prompt">
              <TextArea
                rows={12}
                placeholder="输入写作 Prompt，支持 {{selected_values}}、{{emotion_direction}}、{{product_context}} 等占位符..."
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              />
            </Form.Item>
            <Form.Item label="迭代优化 Prompt" name="iteration_prompt">
              <TextArea
                rows={8}
                placeholder="输入迭代优化 Prompt，支持 {{content}}、{{instruction}} 等占位符..."
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              />
            </Form.Item>
            <Form.Item label="AI 模型" name="model_id">
              <Select
                placeholder="选择 AI 模型（留空使用默认模型）"
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
            <Form.Item>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving}
              >
                {saving ? '保存中...' : '保存配置'}
              </button>
            </Form.Item>
          </Form>
        </div>
      </div>
    </div>
  );
}
