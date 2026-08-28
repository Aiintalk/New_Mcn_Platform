/**
 * 测试样本 新建/编辑（方案 A 架构：纯业务数据四字段）
 *
 * input_payload 契约（与 seed_eval_testcases_real.py / generator 渲染对齐）：
 *   name            达人名（渲染 {{name}}）
 *   persona         达人人设（渲染 {{soul}}）
 *   product_info    产品信息（渲染 {{product_info}}）
 *   original_script 参考原版脚本（渲染 {{original_script}}）
 * 不含改写指令——指令归版本提示词模板（rubric/version 管理）。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Form, Input, Skeleton, Space, Switch, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import '../../styles/variables.css';
import '../styles/eval.css';
import { createTestCase, getTestCase, updateTestCase } from '../api';
import type { EvalTestCaseCreate, EvalTestCaseUpdate } from '../types';
import { Callout } from '../components/primitives';

const { TextArea } = Input;

interface FormValues {
  name: string;            // 样本名（管理）
  description?: string;    // 样本描述（管理）
  kol_name: string;        // 达人名（input_payload.name）
  persona: string;         // 达人人设（input_payload.persona）
  product_info: string;    // 产品信息（input_payload.product_info）
  original_script: string; // 参考原版脚本（input_payload.original_script）
  is_active: boolean;
}

export default function TestCaseEditPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id && id !== 'new');
  const testCaseId = isEdit ? Number(id) : null;

  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  // 加载已有样本（编辑模式）——按方案 A 字段契约回填
  useEffect(() => {
    if (!isEdit || !testCaseId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const found = await getTestCase(testCaseId);
        if (cancelled) return;
        const ip = found.input_payload ?? {};
        form.setFieldsValue({
          name: found.name,
          description: found.description ?? '',
          kol_name: (ip.name as string | undefined) ?? '',
          persona: (ip.persona as string | undefined) ?? '',
          product_info: (ip.product_info as string | undefined) ?? '',
          original_script: (ip.original_script as string | undefined) ?? '',
          is_active: found.is_active,
        });
        setTags(found.tags ?? []);
      } catch (err) {
        const msg = err instanceof Error ? err.message : '加载失败';
        message.error(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isEdit, testCaseId, form, message]);

  const handleAddTag = () => {
    const v = tagInput.trim();
    if (!v) return;
    if (tags.includes(v)) {
      setTagInput('');
      return;
    }
    if (tags.length >= 5) {
      message.warning('标签最多 5 个');
      return;
    }
    setTags([...tags, v]);
    setTagInput('');
  };

  const handleSave = async (values: FormValues) => {
    if (tags.length === 0) {
      message.error('至少一个标签，便于按场景筛选（如：真实数据）');
      return;
    }
    if (!values.kol_name.trim() || !values.persona.trim()
        || !values.product_info.trim() || !values.original_script.trim()) {
      message.error('四个业务输入字段（达人/人设/产品信息/参考脚本）均必填');
      return;
    }

    // 方案 A 纯业务数据：四输入字段（无 messages——指令归版本提示词）
    const input_payload: Record<string, unknown> = {
      name: values.kol_name.trim(),
      persona: values.persona.trim(),
      product_info: values.product_info,
      original_script: values.original_script,
    };

    setSaving(true);
    try {
      if (isEdit && testCaseId) {
        const body: EvalTestCaseUpdate = {
          name: values.name,
          description: values.description ?? null,
          input_payload,
          tags,
          is_active: values.is_active,
        };
        await updateTestCase(testCaseId, body);
        message.success('已保存');
      } else {
        const body: EvalTestCaseCreate = {
          tool_code: 'qianchuan-writer',
          name: values.name,
          description: values.description ?? null,
          input_payload,
          tags,
          is_active: values.is_active,
        };
        await createTestCase(body);
        message.success('已创建');
      }
      navigate('/evaluation/test-cases');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败';
      message.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const subtitle = useMemo(() => {
    if (!isEdit) return '纯业务数据样本：四输入字段由版本提示词模板渲染（{{name}}/{{soul}}/{{product_info}}/{{original_script}}）。';
    return `样本 #${testCaseId} · 编辑模式。修改后立即生效，下一次回归运行将采用最新版本。`;
  }, [isEdit, testCaseId]);

  if (loading) {
    return (
      <div className="eval-page" style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    );
  }

  return (
    <div className="eval-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">{isEdit ? '编辑测试样本' : '新建测试样本'}</h1>
          <p className="page-desc">{subtitle}</p>
        </div>
        <div className="page-actions">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/evaluation/test-cases')}>
            取消
          </Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            保存
          </Button>
        </div>
      </div>

      <Form<FormValues>
        form={form}
        layout="vertical"
        initialValues={{
          name: '',
          description: '',
          kol_name: '',
          persona: '',
          product_info: '',
          original_script: '',
          is_active: true,
        }}
        onFinish={handleSave}
      >
        <Card title="基础信息" className="mb-5" styles={{ body: { padding: 24 } }}>
          <Form.Item
            name="name"
            label="样本名称"
            rules={[{ required: true, message: '请输入样本名称' }]}
          >
            <Input placeholder="例：产品稀缺性 · 羊羊 · 美迪惠尔面膜" />
          </Form.Item>
          <Form.Item name="description" label="样本描述">
            <Input placeholder="一句话场景描述，便于筛选与回顾" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Card title="业务输入（驱动评测的四个字段）" className="mb-5" styles={{ body: { padding: 24 } }}>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item
              name="kol_name"
              label="达人"
              style={{ flex: 1, minWidth: 200, marginBottom: 0 }}
              rules={[{ required: true, message: '达人名必填' }]}
            >
              <Input placeholder="例：羊羊" />
            </Form.Item>
          </Space>
          <Form.Item
            name="persona"
            label="达人人设"
            rules={[{ required: true, message: '人设必填' }]}
            style={{ marginTop: 16 }}
          >
            <TextArea
              autoSize={{ minRows: 2, maxRows: 6 }}
              placeholder="例：羊羊：自带亲和力节奏快、干脆利落人设，坦诚，营造信任感"
            />
          </Form.Item>
          <Form.Item
            name="product_info"
            label="产品信息"
            rules={[{ required: true, message: '产品信息必填' }]}
          >
            <TextArea
              autoSize={{ minRows: 4, maxRows: 12 }}
              placeholder="成分/机制/价格/卖点/合规红线等，粘贴张翀表格的「产品信息[输入]」列"
            />
          </Form.Item>
          <Form.Item
            name="original_script"
            label="参考原版脚本"
            rules={[{ required: true, message: '参考脚本必填' }]}
          >
            <TextArea
              autoSize={{ minRows: 6, maxRows: 20 }}
              placeholder="被仿写的原版千川脚本，粘贴张翀表格的「参考原版脚本[输入]」列"
            />
          </Form.Item>
          <Callout variant="info" icon="i">
            改写指令不在样本里——由「版本提示词模板」统一管理（版本管理页），
            运行时以 {'{{name}}'} / {'{{soul}}'} / {'{{product_info}}'} / {'{{original_script}}'} 占位符渲染本页四字段。
          </Callout>
        </Card>

        <Card title="标签" styles={{ body: { padding: 24 } }}>
          <Form.Item label="标签 tags" required tooltip="溯源/场景标签，如：真实数据；最多 5 个">
            <div className="tag-input" style={{ minHeight: 40 }}>
              {tags.map((t: string) => (
                <Tag
                  key={t}
                  closable
                  onClose={(e) => {
                    e.preventDefault();
                    setTags(tags.filter((x: string) => x !== t));
                  }}
                  style={{ margin: 2 }}
                >
                  {t}
                </Tag>
              ))}
              <Input
                size="small"
                style={{ width: 160, margin: 2 }}
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onPressEnter={handleAddTag}
                onBlur={handleAddTag}
                placeholder="输入后回车"
              />
            </div>
          </Form.Item>
        </Card>
      </Form>
    </div>
  );
}
