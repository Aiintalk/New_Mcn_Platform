import { useEffect, useState, useCallback } from 'react';
import { Form, Input, Select, Switch, Button, message, Spin } from 'antd';
import { getMaterialLibraryConfigs, updateMaterialLibraryConfig } from '../../api/materialLibrary';
import type { MaterialLibraryConfig } from '../../api/materialLibrary';
import { getAiModels } from '../../api/ai';

export default function MaterialLibraryConfigTab() {
  const [config, setConfig] = useState<MaterialLibraryConfig | null>(null);
  const [models, setModels] = useState<{ id: number; name: string; model_id: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [configs, modelList] = await Promise.all([getMaterialLibraryConfigs(), getAiModels()]);
      if (configs.length > 0) {
        const cfg = configs[0];
        setConfig(cfg);
        form.setFieldsValue({
          ai_model_id: cfg.ai_model_id,
          system_prompt: cfg.system_prompt,
          is_active: cfg.is_active,
        });
      }
      setModels(modelList);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => { load(); }, [load]);

  async function handleSave() {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const updated = await updateMaterialLibraryConfig(values);
      setConfig(updated);
      message.success('保存成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spin />;
  if (!config) return <div className="empty-state"><div className="empty-state-text">配置项不存在</div></div>;

  return (
    <div style={{ maxWidth: 800, padding: '0 16px' }}>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 8 }}>
          <strong>配置项：</strong>soul_generator（从入驻问卷数据生成人格档案初稿）
        </div>
        <div>
          <strong>状态：</strong>
          <span className={`badge ${config.is_active ? 'badge-success' : 'badge-gray'}`}>
            {config.is_active ? '启用' : '停用'}
          </span>
        </div>
      </div>

      <Form form={form} layout="vertical">
        <Form.Item label="AI 模型" name="ai_model_id">
          <Select allowClear placeholder="选择 AI 模型">
            {models.map(m => (
              <Select.Option key={m.id} value={m.id}>{m.name} ({m.model_id})</Select.Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item label="系统提示词（soul_generator Prompt）" name="system_prompt">
          <Input.TextArea rows={16} placeholder="输入用于生成人格档案的系统提示词。占位符：{{kol_name}} {{intake_answers}} {{intake_report}}" />
        </Form.Item>

        <Form.Item label="启用" name="is_active" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Button type="primary" onClick={handleSave} loading={saving}>保存</Button>
      </Form>
    </div>
  );
}
