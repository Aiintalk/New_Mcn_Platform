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
        <Form.Item label="产品昵称" name="nickname" rules={[{ required: true, message: '请输入产品昵称' }]} extra="脚本里统一怎么称呼它（如：大红瓶、番茄精华、小棕瓶）">
          <Input placeholder="请输入产品昵称" />
        </Form.Item>
        <Form.Item label="最主推卖点" name="core_selling_point" extra="几个字即可，如：美白 / 舒缓 / 缩小毛孔（价值观创作会自动读取这里）"><Input /></Form.Item>
        <Form.Item label="可视化" name="visualization" extra="员工实测中可拍摄的产品演示点，如：涂上去湿润，一会就干了；用一用皮肤变化肉眼可见"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item label="主推机制" name="mechanism" extra="这次主推的价格钩子或促销力度（如：买一送一、破价、限时赠品）"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="mechanism_exclusive" valuePropName="checked"><Checkbox>只有我有（脚本必须写出「只有我有」）</Checkbox></Form.Item>
        <Form.Item label="推荐来源" name="endorsement" extra="如：明星同款、头部达人推荐、知名线下连锁渠道入驻"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item label="用户反馈" name="user_feedback" extra="如：小红书素人测评、多年老用户真实反馈、复购率数据"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item label="独家卖点" name="unique_selling" extra="这个产品为什么有效果？和同类产品相比最与众不同的是什么？（如：独家专利成分、特殊工艺、临床验证数据）"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item label="获奖荣誉" name="awards" extra="如：xxx 大奖、xxx 榜单第一（没有可留空）"><Input /></Form.Item>
        <Form.Item label="功效承诺" name="efficacy_proof" extra="有功效测试报告时填写，如：28 天实测亮度提升 30%、SGS 检测报告显示…（没有可留空）"><Input.TextArea rows={3} /></Form.Item>
      </Form>
    </Modal>
  );
}
