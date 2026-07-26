/**
 * 测试样本编辑（设计稿 test-case-edit.html）
 *
 * 路由：
 *   /evaluation/test-cases/new         → 创建
 *   /evaluation/test-cases/:id/edit    → 更新
 *
 * 表单字段：基础信息 / 卖点卡(JSON 文本) / 参考脚本 / 对话上下文(JSON) / 标签
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Form, Input, Skeleton, Space, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import '../../styles/variables.css';
import '../styles/eval.css';
import { Callout } from '../components/primitives';
import { createTestCase, listTestCases, updateTestCase } from '../api';
import type { EvalTestCaseCreate, EvalTestCaseUpdate } from '../types';

const { TextArea } = Input;

interface FormValues {
  name: string;
  description?: string;
  kol_id?: number | null;
  kol_name?: string;
  selling_points?: string;
  reference_script?: string;
  messages?: string; // JSON 字符串
  is_active: boolean;
}

const DEFAULT_MESSAGES = JSON.stringify(
  [
    { role: 'user', content: '帮我仿写一条抖音千川投放文案，要符合我的人设，3 秒内抓住痛点。' },
  ],
  null,
  2,
);

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

  // 加载已有样本（编辑模式）
  useEffect(() => {
    if (!isEdit || !testCaseId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        // 后端无 GET /test-cases/:id 单条接口，从 list 中查找
        const page = await listTestCases({ page: 1, page_size: 50 });
        const found = page.items.find((it) => it.id === testCaseId);
        if (cancelled) return;
        if (!found) {
          message.error('样本不存在或已被删除');
          navigate('/evaluation/test-cases');
          return;
        }
        const ip = found.input_payload ?? {};
        form.setFieldsValue({
          name: found.name,
          description: found.description ?? '',
          kol_id: (ip.kol_id as number | undefined) ?? null,
          kol_name: (ip.kol_name as string | undefined) ?? '',
          selling_points: (ip.selling_points as string | undefined) ?? '',
          reference_script: (ip.reference_script as string | undefined) ?? '',
          messages: ip.messages ? JSON.stringify(ip.messages, null, 2) : DEFAULT_MESSAGES,
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
  }, [isEdit, testCaseId, form, message, navigate]);

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
      message.error('至少一个标签，便于按场景筛选');
      return;
    }
    // 校验 messages JSON
    let messagesJson: unknown = null;
    if (values.messages) {
      try {
        messagesJson = JSON.parse(values.messages);
      } catch {
        message.error('对话上下文 messages 不是合法 JSON');
        return;
      }
    }

    const input_payload: Record<string, unknown> = {
      kol_id: values.kol_id ?? null,
      kol_name: values.kol_name ?? '',
      selling_points: values.selling_points ?? '',
      reference_script: values.reference_script ?? '',
      messages: messagesJson,
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
        message.success('已创建样本');
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
    if (!isEdit) return '新建一条覆盖特定场景的固定输入样本。input_payload 以 JSONB 存储，generator 运行时按 key 渲染占位符。';
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
          kol_id: null,
          kol_name: '',
          selling_points: '',
          reference_script: '',
          messages: DEFAULT_MESSAGES,
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
            <Input placeholder="例：焦虑型 · 美妆精华开屏" />
          </Form.Item>
          <Form.Item name="description" label="样本描述">
            <Input placeholder="一句话场景描述，便于筛选与回顾" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="middle">
            <Form.Item name="kol_name" label="关联达人（名称，便于追溯）" style={{ flex: 1, minWidth: 240, marginBottom: 0 }}>
              <Input placeholder="例：林小美" />
            </Form.Item>
            <Form.Item name="kol_id" label="达人 ID（可选）" style={{ width: 160, marginBottom: 0 }}>
              <Input type="number" placeholder="kol_id" />
            </Form.Item>
          </Space>
        </Card>

        <Card title="产品卖点卡" className="mb-5" styles={{ body: { padding: 24 } }}>
          <Form.Item name="selling_points" label="或直接填写卖点文本" tooltip="一期以文本录入，文件上传二期开放">
            <TextArea
              autoSize={{ minRows: 4, maxRows: 12 }}
              placeholder="核心成分：5% 烟酰胺 + 玻尿酸；价格：198 元买一送一；定位：熬夜脸黄提亮；目标人群：25-35 女性白领…"
            />
          </Form.Item>
          <Callout variant="warn" icon="!">
            文件拖拽上传（图片 / PDF / DOC）将在二期开放。当前请将卖点内容直接粘贴到上方文本框。
          </Callout>
        </Card>

        <Card title="参考脚本 / 原版" className="mb-5" styles={{ body: { padding: 24 } }}>
          <Form.Item name="reference_script" label="被仿写的参考文案">
            <TextArea
              autoSize={{ minRows: 4, maxRows: 12 }}
              placeholder="粘贴原版脚本，generator 会基于此生成仿写候选"
            />
          </Form.Item>
        </Card>

        <Card title="对话上下文 messages" className="mb-5" styles={{ body: { padding: 24 } }}>
          <Form.Item
            name="messages"
            label="JSON 或多行文本"
            tooltip='generator 会结合 persona 渲染 {{name}}/{{soul}}/{{content_plan}}，再用通用占位符渲染 {{product_info}}/{{original_script}}/{{messages}}'
          >
            <TextArea
              className="code-area"
              autoSize={{ minRows: 6, maxRows: 20 }}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5 }}
            />
          </Form.Item>
        </Card>

        <Card title="标签" styles={{ body: { padding: 24 } }}>
          <Form.Item label="标签 tags" required>
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
              <input
                data-testid="tag-input"
                placeholder="+ 添加标签（回车确认）"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddTag();
                  }
                }}
                style={{
                  border: 'none',
                  outline: 'none',
                  flex: 1,
                  minWidth: 160,
                  fontSize: 13,
                  padding: 2,
                  background: 'transparent',
                }}
              />
            </div>
          </Form.Item>
          <div className="text-xs text-muted" style={{ marginTop: -8, marginBottom: 16 }}>
            最多 5 个标签。按回车添加。
          </div>

          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <Form.Item name="is_active" noStyle valuePropName="checked">
                <input type="checkbox" style={{ width: 18, height: 18 }} />
              </Form.Item>
              <span>参与回归运行</span>
            </label>
          </Form.Item>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
          <Button onClick={() => navigate('/evaluation/test-cases')}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            保存
          </Button>
        </div>
      </Form>
    </div>
  );
}

// 文件结束
