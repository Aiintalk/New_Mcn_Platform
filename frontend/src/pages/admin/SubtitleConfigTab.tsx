import { useEffect, useState, useCallback } from 'react';
import { Form, Input, Select, Switch, Button, App, Spin } from 'antd';
import { getSubtitleConfigs, updateSubtitleConfig } from '../../api/subtitle';
import type { SubtitleConfig } from '../../api/subtitle';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';

export default function SubtitleConfigTab() {
  const { message } = App.useApp();
  const [config, setConfig] = useState<SubtitleConfig | null>(null);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [configs, modelPaged] = await Promise.all([getSubtitleConfigs(), getAiModels()]);
      const defaultCfg = configs.find((c) => c.config_key === 'default') ?? configs[0];
      if (defaultCfg) {
        setConfig(defaultCfg);
        form.setFieldsValue({
          mindmap_model_id: defaultCfg.mindmap_model_id,
          mindmap_prompt: defaultCfg.mindmap_prompt,
          is_active: defaultCfg.is_active,
        });
      }
      setModels(modelPaged.items);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [form, message]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const updated = await updateSubtitleConfig(values);
      setConfig(updated);
      message.success('保存成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spin />;
  if (!config) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">配置项不存在</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, padding: '0 16px' }}>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 8 }}>
          <strong>配置项：</strong>default（字幕 → 思维导图 Prompt + 模型）
        </div>
        <div>
          <strong>状态：</strong>
          <span className={`badge ${config.is_active ? 'badge-success' : 'badge-gray'}`}>
            {config.is_active ? '启用' : '停用'}
          </span>
        </div>
      </div>

      <Form form={form} layout="vertical">
        <Form.Item label="AI 模型（思维导图生成）" name="mindmap_model_id">
          <Select allowClear placeholder="选择 AI 模型（默认 claude-haiku-4-5）">
            {models.map((m) => (
              <Select.Option key={m.id} value={m.id}>
                {m.name} ({m.model_id})
              </Select.Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="思维导图系统提示词（mindmap_prompt）"
          name="mindmap_prompt"
        >
          <Input.TextArea
            rows={16}
            placeholder="输入用于生成思维导图的系统提示词。占位符：{{transcript}}"
          />
        </Form.Item>

        <Form.Item label="启用" name="is_active" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Button type="primary" onClick={handleSave} loading={saving}>
          保存
        </Button>
      </Form>
    </div>
  );
}
