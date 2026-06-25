import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Checkbox, Popconfirm, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { QianchuanProduct } from '../../../types/kolWorkspace';
import {
  getQianchuanProducts,
  createQianchuanProduct,
  updateQianchuanProduct,
  deleteQianchuanProduct,
} from '../../../api/qianchuanProducts';

const PAGE_SIZE = 20;

type ProductFormValues = Omit<QianchuanProduct, 'id' | 'created_by' | 'created_at' | 'updated_at'>;

interface ProductFormModalProps {
  open: boolean;
  editing: QianchuanProduct | null;
  loading: boolean;
  onCancel: () => void;
  onFinish: (values: ProductFormValues) => void;
}

function ProductFormModal({ open, editing, loading, onCancel, onFinish }: ProductFormModalProps) {
  const [form] = Form.useForm<ProductFormValues>();

  useEffect(() => {
    if (open) {
      if (editing) {
        form.setFieldsValue({
          nickname:           editing.nickname,
          core_selling_point: editing.core_selling_point ?? '',
          visualization:      editing.visualization ?? '',
          mechanism:          editing.mechanism ?? '',
          mechanism_exclusive: editing.mechanism_exclusive,
          endorsement:        editing.endorsement ?? '',
          user_feedback:      editing.user_feedback ?? '',
          unique_selling:     editing.unique_selling ?? '',
          awards:             editing.awards ?? '',
          efficacy_proof:     editing.efficacy_proof ?? '',
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ mechanism_exclusive: false });
      }
    }
  }, [open, editing, form]);

  return (
    <Modal
      title={editing ? `编辑产品：${editing.nickname}` : '新建产品'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText={editing ? '保存' : '创建'}
      cancelText="取消"
      confirmLoading={loading}
      width={640}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        style={{ marginTop: 16 }}
      >
        <Form.Item
          label="产品昵称"
          name="nickname"
          rules={[{ required: true, message: '请输入产品昵称' }]}
        >
          <Input placeholder="请输入产品名称（用于区分识别）" />
        </Form.Item>
        <Form.Item label="最主推卖点" name="core_selling_point">
          <Input placeholder="例：控油持妆 12 小时" />
        </Form.Item>
        <Form.Item label="可视化演示点" name="visualization">
          <Input.TextArea rows={3} placeholder="填写可直观展示的卖点" />
        </Form.Item>
        <Form.Item label="主推机制" name="mechanism">
          <Input.TextArea rows={3} placeholder="填写核心成分/技术/机制" />
        </Form.Item>
        <Form.Item name="mechanism_exclusive" valuePropName="checked">
          <Checkbox>只有我有（独家机制）</Checkbox>
        </Form.Item>
        <Form.Item label="推荐来源 / 背书" name="endorsement">
          <Input.TextArea rows={3} placeholder="明星、权威机构、媒体背书等" />
        </Form.Item>
        <Form.Item label="用户反馈" name="user_feedback">
          <Input.TextArea rows={3} placeholder="真实用户口碑/评价" />
        </Form.Item>
        <Form.Item label="独家卖点" name="unique_selling">
          <Input.TextArea rows={3} placeholder="区别于竞品的独特优势" />
        </Form.Item>
        <Form.Item label="获奖荣誉" name="awards">
          <Input placeholder="获奖/认证/上榜信息" />
        </Form.Item>
        <Form.Item label="功效承诺" name="efficacy_proof">
          <Input.TextArea rows={3} placeholder="可量化的功效数据/承诺" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function QianchuanProductsModule() {
  const [items, setItems]           = useState<QianchuanProduct[]>([]);
  const [total, setTotal]           = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage]             = useState(1);
  const [query, setQuery]           = useState('');
  const [loading, setLoading]       = useState(false);

  const [modalOpen, setModalOpen]   = useState(false);
  const [editing, setEditing]       = useState<QianchuanProduct | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    getQianchuanProducts({ page, page_size: PAGE_SIZE, q: query || undefined })
      .then((res) => {
        setItems(res.items);
        setTotal(res.pagination.total);
        setTotalPages(res.pagination.total_pages);
      })
      .catch(() => message.error('加载产品列表失败'))
      .finally(() => setLoading(false));
  }, [page, query]);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(product: QianchuanProduct) {
    setEditing(product);
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditing(null);
  }

  async function handleSave(values: ProductFormValues) {
    setSaveLoading(true);
    try {
      if (editing) {
        await updateQianchuanProduct(editing.id, values);
        message.success('产品已更新');
      } else {
        await createQianchuanProduct(values);
        message.success('产品已创建');
      }
      closeModal();
      load();
    } catch (e: unknown) {
      message.error((e instanceof Error ? e.message : null) || '操作失败');
    } finally {
      setSaveLoading(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteQianchuanProduct(id);
      message.success('已删除');
      load();
    } catch {
      message.error('删除失败');
    }
  }

  return (
    <>
      {/* 页面标题区 */}
      <div className="page-header">
        <div>
          <h1 className="page-title">千川产品库</h1>
          <p className="page-desc">管理全局千川产品信息，可在工作台首页设置在售商品</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={openCreate}>
            <PlusOutlined /> 新建产品
          </button>
        </div>
      </div>

      <div className="card">
        {/* 搜索栏 */}
        <div className="filter-bar">
          <input
            className="filter-input"
            placeholder="搜索产品名称"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            style={{ width: 220 }}
          />
          <span className="filter-count">共 {total} 个产品</span>
        </div>

        {/* 列表 */}
        {loading ? (
          <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <div className="empty-state-text">暂无产品，点击「新建产品」添加</div>
          </div>
        ) : (
          <>
            <table className="ant-table">
              <thead>
                <tr>
                  <th style={{ width: 160 }}>产品昵称</th>
                  <th style={{ width: 180 }}>最主推卖点</th>
                  <th>主推机制</th>
                  <th style={{ width: 90, textAlign: 'center' }}>只有我有</th>
                  <th className="col-actions" style={{ width: 120 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 600, color: 'var(--gray-800)', fontSize: 14 }}>
                      {p.nickname}
                    </td>
                    <td style={{ fontSize: 13, color: 'var(--gray-600)' }}>
                      {p.core_selling_point ?? '—'}
                    </td>
                    <td style={{ fontSize: 13, color: 'var(--gray-600)' }}>
                      {p.mechanism
                        ? p.mechanism.length > 50 ? `${p.mechanism.slice(0, 50)}…` : p.mechanism
                        : '—'}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {p.mechanism_exclusive
                        ? <span className="badge badge-danger">是</span>
                        : <span className="badge badge-gray">否</span>}
                    </td>
                    <td className="col-actions">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(p)}
                      >
                        编辑
                      </button>
                      <Popconfirm
                        title={`确认删除产品「${p.nickname}」？`}
                        description="删除后不可恢复。"
                        okText="确认删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => handleDelete(p.id)}
                      >
                        <button className="btn btn-danger-ghost btn-sm">删除</button>
                      </Popconfirm>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="pagination">
                <span>共 {total} 个产品</span>
                <div className="pages">
                  <div
                    className="page-btn"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >‹</div>
                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map((p) => (
                    <div
                      key={p}
                      className={`page-btn${page === p ? ' active' : ''}`}
                      onClick={() => setPage(p)}
                    >{p}</div>
                  ))}
                  <div
                    className="page-btn"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  >›</div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <ProductFormModal
        open={modalOpen}
        editing={editing}
        loading={saveLoading}
        onCancel={closeModal}
        onFinish={handleSave}
      />
    </>
  );
}
