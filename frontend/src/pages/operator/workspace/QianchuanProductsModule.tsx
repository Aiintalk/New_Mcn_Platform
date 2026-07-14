import { useState, useEffect, useCallback } from 'react';
import { Popconfirm, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { QianchuanProduct } from '../../../types/kolWorkspace';
import ProductFormModal, { type ProductFormValues } from '../../../components/qianchuan/ProductFormModal';
import {
  getQianchuanProducts,
  createQianchuanProduct,
  updateQianchuanProduct,
  deleteQianchuanProduct,
} from '../../../api/qianchuanProducts';

const PAGE_SIZE = 20;

const PRODUCT_FIELDS: { key: keyof QianchuanProduct; label: string; tone: string }[] = [
  { key: 'core_selling_point', label: '最主推卖点', tone: 'var(--pink)' },
  { key: 'visualization', label: '可视化', tone: 'var(--info)' },
  { key: 'mechanism', label: '主推机制', tone: 'var(--warning)' },
  { key: 'endorsement', label: '推荐来源', tone: 'var(--brand)' },
  { key: 'user_feedback', label: '用户反馈', tone: 'var(--success)' },
  { key: 'unique_selling', label: '独家卖点', tone: 'var(--danger)' },
  { key: 'awards', label: '获奖荣誉', tone: 'var(--purple)' },
  { key: 'efficacy_proof', label: '功效承诺', tone: 'var(--info)' },
];

function ProductDetail({ label, value, tone }: { label: string; value: string | null; tone: string }) {
  if (!value) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, lineHeight: 1.65 }}>
      <span style={{ flexShrink: 0, color: tone, background: `color-mix(in srgb, ${tone} 10%, white)`, borderRadius: 4, padding: '1px 6px', fontSize: 12, fontWeight: 600 }}>{label}</span>
      <span style={{ color: 'var(--gray-700)', whiteSpace: 'pre-wrap' }}>{value}</span>
    </div>
  );
}

function ProductScanCard({ product, onEdit, onDelete }: {
  product: QianchuanProduct;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="card" style={{ marginBottom: 'var(--sp-4)' }} data-testid={`product-card-${product.id}`}>
      <div className="card-header" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2 className="card-title" style={{ marginBottom: 6 }}>{product.nickname}</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {product.core_selling_point && <span className="badge badge-brand">{product.core_selling_point}</span>}
            {product.mechanism_exclusive && <span className="badge badge-danger">只有我有</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button className="btn btn-ghost btn-sm" onClick={onEdit}>编辑</button>
          <Popconfirm
            title={`确认删除产品「${product.nickname}」？`}
            description="删除后不可恢复。"
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={onDelete}
          >
            <button className="btn btn-danger-ghost btn-sm">删除</button>
          </Popconfirm>
        </div>
      </div>
      <div className="card-body" style={{ display: 'grid', gap: 8 }}>
        {PRODUCT_FIELDS.map((field) => <ProductDetail key={field.key} label={field.label} value={product[field.key] as string | null} tone={field.tone} />)}
      </div>
    </div>
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
          <h1 className="page-title">产品库</h1>
          <p className="page-desc">所有脚本工具都会从这里读取产品信息</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={openCreate}>
            <PlusOutlined /> 新建产品
          </button>
        </div>
      </div>

      <div>
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
            <div style={{ marginTop: 'var(--sp-4)' }}>
              {items.map((product) => (
                <ProductScanCard
                  key={product.id}
                  product={product}
                  onEdit={() => openEdit(product)}
                  onDelete={() => handleDelete(product.id)}
                />
              ))}
            </div>

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
        title={editing ? `编辑产品：${editing.nickname}` : '新建产品'}
        submitText={editing ? '保存' : '创建'}
        initialProduct={editing}
        loading={saveLoading}
        onCancel={closeModal}
        onSubmit={handleSave}
      />
    </>
  );
}
