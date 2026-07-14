import { useEffect } from 'react';
import { Checkbox, Form, Input, Modal } from 'antd';
import type { QianchuanProduct } from '../../types/kolWorkspace';

export type ProductFormValues = Omit<QianchuanProduct, 'id' | 'created_by' | 'created_at' | 'updated_at'>;

interface ProductFormModalProps {
  open: boolean;
  title: string;
  submitText: string;
  initialProduct?: QianchuanProduct | null;
  loading?: boolean;
  onCancel: () => void;
  onSubmit: (values: ProductFormValues) => void | Promise<void>;
}

export default function ProductFormModal({
  open, title, submitText, initialProduct = null, loading = false, onCancel, onSubmit,
}: ProductFormModalProps) {
  const [form] = Form.useForm<ProductFormValues>();

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    form.setFieldsValue(initialProduct ? {
      nickname: initialProduct.nickname,
      core_selling_point: initialProduct.core_selling_point ?? '',
      visualization: initialProduct.visualization ?? '',
      mechanism: initialProduct.mechanism ?? '',
      mechanism_exclusive: initialProduct.mechanism_exclusive,
      endorsement: initialProduct.endorsement ?? '',
      user_feedback: initialProduct.user_feedback ?? '',
      unique_selling: initialProduct.unique_selling ?? '',
      awards: initialProduct.awards ?? '',
      efficacy_proof: initialProduct.efficacy_proof ?? '',
    } : { mechanism_exclusive: false });
  }, [form, initialProduct, open]);

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText={submitText}
      cancelText="取消"
      confirmLoading={loading}
      width={640}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={onSubmit} style={{ marginTop: 16 }}>
        <Form.Item label="产品昵称" name="nickname" rules={[{ required: true, message: '请输入产品昵称' }]}>
          <Input placeholder="请输入产品名称（用于区分识别）" />
        </Form.Item>
        <Form.Item label="最主推卖点" name="core_selling_point"><Input placeholder="例：控油持妆 12 小时" /></Form.Item>
        <Form.Item label="可视化演示点" name="visualization"><Input.TextArea rows={3} placeholder="填写可直观展示的卖点" /></Form.Item>
        <Form.Item label="主推机制" name="mechanism"><Input.TextArea rows={3} placeholder="填写价格钩子、买赠、破价、限时赠品等促销机制" /></Form.Item>
        <Form.Item name="mechanism_exclusive" valuePropName="checked"><Checkbox>只有我有（独家机制）</Checkbox></Form.Item>
        <Form.Item label="推荐来源 / 背书" name="endorsement"><Input.TextArea rows={3} placeholder="明星、权威机构、媒体背书等" /></Form.Item>
        <Form.Item label="用户反馈" name="user_feedback"><Input.TextArea rows={3} placeholder="真实用户口碑/评价" /></Form.Item>
        <Form.Item label="独家卖点" name="unique_selling"><Input.TextArea rows={3} placeholder="区别于竞品的独特优势" /></Form.Item>
        <Form.Item label="获奖荣誉" name="awards"><Input placeholder="获奖/认证/上榜信息" /></Form.Item>
        <Form.Item label="功效承诺" name="efficacy_proof"><Input.TextArea rows={3} placeholder="可量化的功效数据/承诺" /></Form.Item>
      </Form>
    </Modal>
  );
}
