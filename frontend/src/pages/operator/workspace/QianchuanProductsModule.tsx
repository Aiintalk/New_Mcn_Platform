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

function ProductDetail({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--gray-700)', whiteSpace: 'pre-wrap' }}>{value}</div>
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
      <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 'var(--sp-4)' }}>
        <ProductDetail label="可视化演示点" value={product.visualization} />
        <ProductDetail label="主推机制（价格钩子、买赠、破价、限时赠品）" value={product.mechanism} />
        <ProductDetail label="推荐来源 / 背书" value={product.endorsement} />
        <ProductDetail label="用户反馈" value={product.user_feedback} />
        <ProductDetail label="独家卖点" value={product.unique_selling} />
        <ProductDetail label="获奖荣誉" value={product.awards} />
        <ProductDetail label="功效承诺" value={product.efficacy_proof} />
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
