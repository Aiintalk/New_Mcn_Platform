import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Radio, Popconfirm, Skeleton, Checkbox, message } from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import type { KolBenchmark, QianchuanProduct, WorkspaceDashboardData } from '../../../types/kolWorkspace';
import {
  getWorkspaceDashboard,
  createBenchmark,
  updateBenchmark,
  deleteBenchmark,
  updateActiveProducts,
} from '../../../api/kolWorkspace';
import { getQianchuanProducts } from '../../../api/qianchuanProducts';

interface WorkspaceDashboardProps {
  kolId: number;
  onKolLoaded?: (kol: { name: string; avatar_url: string | null }) => void;
}

// ─── 对标账号弹窗 ────────────────────────────────────────────────────────────
interface BenchmarkFormValues {
  account_name: string;
  account_type: 'content' | 'livestream';
  description: string;
}

function BenchmarkCard({
  benchmark,
  onEdit,
  onDelete,
}: {
  benchmark: KolBenchmark;
  onEdit: (b: KolBenchmark) => void;
  onDelete: (b: KolBenchmark) => void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onEdit(benchmark)}
      style={{
        position: 'relative',
        padding: 'var(--sp-3) var(--sp-4)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-card)',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s',
        boxShadow: hovered ? 'var(--shadow-md)' : 'var(--shadow-sm)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 4 }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-800)' }}>
          {benchmark.account_name}
        </span>
        <span
          className={benchmark.account_type === 'content' ? 'badge badge-info' : 'badge badge-purple'}
          style={{ fontSize: 11 }}
        >
          {benchmark.account_type === 'content' ? '内容' : '直播'}
        </span>
      </div>
      {benchmark.description && (
        <div style={{ fontSize: 12, color: 'var(--gray-500)', lineHeight: 1.5 }}>
          {benchmark.description}
        </div>
      )}
      {hovered && (
        <Popconfirm
          title="确认删除此对标账号？"
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={(e) => {
            e?.stopPropagation();
            onDelete(benchmark);
          }}
          onOpenChange={(open, e) => { if (open) e?.stopPropagation(); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              top: 6,
              right: 6,
              width: 20,
              height: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'var(--danger-bg)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
            }}
          >
            <CloseOutlined style={{ fontSize: 10, color: 'var(--danger)' }} />
          </div>
        </Popconfirm>
      )}
    </div>
  );
}

// ─── 在售商品卡片 ─────────────────────────────────────────────────────────────
function ProductCard({
  product,
  onRemove,
}: {
  product: QianchuanProduct;
  onRemove?: (p: QianchuanProduct) => void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        padding: 'var(--sp-3) var(--sp-4)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-card)',
        transition: 'box-shadow 0.15s',
        boxShadow: hovered ? 'var(--shadow-md)' : 'var(--shadow-sm)',
        minWidth: 160,
        maxWidth: 200,
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--gray-800)', marginBottom: 4 }}>
        {product.nickname}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
        {product.core_selling_point && (
          <span className="badge badge-brand" style={{ fontSize: 11 }}>{product.core_selling_point}</span>
        )}
        {product.mechanism_exclusive && (
          <span className="badge badge-danger" style={{ fontSize: 11 }}>只有我有</span>
        )}
      </div>
      {product.mechanism && (
        <div style={{ fontSize: 12, color: 'var(--gray-500)', lineHeight: 1.5 }}>
          {product.mechanism.length > 40 ? `${product.mechanism.slice(0, 40)}…` : product.mechanism}
        </div>
      )}
      {hovered && onRemove && (
        <button
          className="btn btn-danger-ghost btn-sm"
          onClick={() => onRemove(product)}
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            fontSize: 11,
            padding: '2px 8px',
          }}
        >
          移除
        </button>
      )}
    </div>
  );
}

export default function WorkspaceDashboard({ kolId, onKolLoaded }: WorkspaceDashboardProps) {
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<WorkspaceDashboardData | null>(null);

  // 对标账号弹窗
  const [bmModalOpen, setBmModalOpen]     = useState(false);
  const [bmEditing, setBmEditing]         = useState<KolBenchmark | null>(null);
  const [bmLoading, setBmLoading]         = useState(false);
  const [bmForm] = Form.useForm<BenchmarkFormValues>();

  // 管理商品弹窗
  const [manageOpen, setManageOpen]       = useState(false);
  const [allProducts, setAllProducts]     = useState<QianchuanProduct[]>([]);
  const [allProductsLoading, setAllProductsLoading] = useState(false);
  const [selectedIds, setSelectedIds]     = useState<number[]>([]);
  const [productPage, setProductPage]     = useState(1);
  const [productTotal, setProductTotal]   = useState(0);
  const [productTotalPages, setProductTotalPages] = useState(1);
  const [productQuery, setProductQuery]   = useState('');
  const [manageLoading, setManageLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getWorkspaceDashboard(kolId)
      .then((data) => {
        setDashboard(data);
        onKolLoaded?.({ name: data.kol.name, avatar_url: data.kol.avatar_url });
      })
      .catch(() => setError('加载工作台数据失败'))
      .finally(() => setLoading(false));
  }, [kolId, onKolLoaded]);

  useEffect(() => { load(); }, [load]);

  // ── 对标账号操作 ──────────────────────────────────────────────────────────
  function openCreateBenchmark() {
    setBmEditing(null);
    bmForm.resetFields();
    bmForm.setFieldsValue({ account_type: 'content' });
    setBmModalOpen(true);
  }

  function openEditBenchmark(bm: KolBenchmark) {
    setBmEditing(bm);
    bmForm.setFieldsValue({
      account_name: bm.account_name,
      account_type: bm.account_type,
      description:  bm.description ?? '',
    });
    setBmModalOpen(true);
  }

  async function handleBmSubmit(values: BenchmarkFormValues) {
    setBmLoading(true);
    try {
      if (bmEditing) {
        await updateBenchmark(kolId, bmEditing.id, values);
        message.success('对标账号已更新');
      } else {
        await createBenchmark(kolId, { ...values, sort_order: 0 });
        message.success('对标账号已添加');
      }
      setBmModalOpen(false);
      load();
    } catch (e: unknown) {
      message.error((e instanceof Error ? e.message : null) || '操作失败');
    } finally {
      setBmLoading(false);
    }
  }

  async function handleDeleteBenchmark(bm: KolBenchmark) {
    try {
      await deleteBenchmark(kolId, bm.id);
      message.success('已删除');
      load();
    } catch {
      message.error('删除失败');
    }
  }

  // ── 管理在售商品 ──────────────────────────────────────────────────────────
  async function openManageProducts() {
    setManageOpen(true);
    setSelectedIds((dashboard?.active_products ?? []).map((p) => p.id));
    setProductPage(1);
    setProductQuery('');
    await loadAllProducts(1, '');
  }

  async function loadAllProducts(page: number, q: string) {
    setAllProductsLoading(true);
    try {
      const res = await getQianchuanProducts({ page, page_size: 20, q: q || undefined });
      setAllProducts(res.items);
      setProductTotal(res.pagination.total);
      setProductTotalPages(res.pagination.total_pages);
    } catch {
      message.error('加载产品列表失败');
    } finally {
      setAllProductsLoading(false);
    }
  }

  async function handleManageConfirm() {
    setManageLoading(true);
    try {
      await updateActiveProducts(kolId, selectedIds);
      message.success('在售商品已更新');
      setManageOpen(false);
      load();
    } catch {
      message.error('保存失败');
    } finally {
      setManageLoading(false);
    }
  }

  function handleRemoveActiveProduct(product: QianchuanProduct) {
    const newIds = (dashboard?.active_products ?? [])
      .filter((p) => p.id !== product.id)
      .map((p) => p.id);
    updateActiveProducts(kolId, newIds)
      .then(() => {
        message.success('已移除');
        load();
      })
      .catch(() => message.error('移除失败'));
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="card" style={{ padding: 'var(--sp-6)' }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">{error}</div>
        <button className="btn btn-ghost btn-sm" style={{ marginTop: 'var(--sp-3)' }} onClick={load}>
          重试
        </button>
      </div>
    );
  }

  if (!dashboard) return null;

  const { benchmarks, active_products } = dashboard;

  return (
    <>
      {/* ── 对标账号区 ─────────────────────────────────────────────── */}
      <div className="card">
        <div className="card-header" style={{ padding: 'var(--sp-4) var(--sp-5)' }}>
          <span className="card-title">对标账号</span>
          <button className="btn btn-primary btn-sm" onClick={openCreateBenchmark}>
            <PlusOutlined /> 添加对标账号
          </button>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-5)' }}>
            {/* 内容对标 */}
            <div>
              <div className="section-title" style={{ marginBottom: 'var(--sp-3)', fontSize: 13, color: 'var(--gray-500)', fontWeight: 600 }}>
                内容对标（{benchmarks.content.length}）
              </div>
              {benchmarks.content.length === 0 ? (
                <div className="empty-state" style={{ padding: 'var(--sp-5)' }}>
                  <div className="empty-state-text">暂无内容对标账号</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                  {benchmarks.content.map((bm) => (
                    <BenchmarkCard
                      key={bm.id}
                      benchmark={bm}
                      onEdit={openEditBenchmark}
                      onDelete={handleDeleteBenchmark}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* 直播对标 */}
            <div>
              <div className="section-title" style={{ marginBottom: 'var(--sp-3)', fontSize: 13, color: 'var(--gray-500)', fontWeight: 600 }}>
                直播对标（{benchmarks.livestream.length}）
              </div>
              {benchmarks.livestream.length === 0 ? (
                <div className="empty-state" style={{ padding: 'var(--sp-5)' }}>
                  <div className="empty-state-text">暂无直播对标账号</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                  {benchmarks.livestream.map((bm) => (
                    <BenchmarkCard
                      key={bm.id}
                      benchmark={bm}
                      onEdit={openEditBenchmark}
                      onDelete={handleDeleteBenchmark}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 在售商品区 ─────────────────────────────────────────────── */}
      <div className="card">
        <div className="card-header" style={{ padding: 'var(--sp-4) var(--sp-5)' }}>
          <span className="card-title">目前在售商品</span>
          <button className="btn btn-ghost btn-sm" onClick={openManageProducts}>
            管理商品
          </button>
        </div>
        <div className="card-body">
          {active_products.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-text">暂无在售商品，点击「管理商品」添加</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-3)' }}>
              {active_products.map((p) => (
                <ProductCard key={p.id} product={p} onRemove={handleRemoveActiveProduct} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── 对标账号 Modal ──────────────────────────────────────────── */}
      <Modal
        title={bmEditing ? '编辑对标账号' : '添加对标账号'}
        open={bmModalOpen}
        onCancel={() => { setBmModalOpen(false); bmForm.resetFields(); }}
        onOk={() => bmForm.submit()}
        okText={bmEditing ? '保存' : '添加'}
        cancelText="取消"
        confirmLoading={bmLoading}
        destroyOnClose
      >
        <Form
          form={bmForm}
          layout="vertical"
          onFinish={handleBmSubmit}
          style={{ marginTop: 16 }}
          initialValues={{ account_type: 'content' }}
        >
          <Form.Item
            label="账号名"
            name="account_name"
            rules={[{ required: true, message: '请输入账号名' }]}
          >
            <Input placeholder="请输入对标账号名称" />
          </Form.Item>
          <Form.Item label="类型" name="account_type">
            <Radio.Group>
              <Radio value="content">内容对标</Radio>
              <Radio value="livestream">直播对标</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item label="简介" name="description">
            <Input.TextArea rows={3} placeholder="简单描述该账号的特点（选填）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 管理在售商品 Modal ──────────────────────────────────────── */}
      <Modal
        title="管理在售商品"
        open={manageOpen}
        onCancel={() => setManageOpen(false)}
        onOk={handleManageConfirm}
        okText="保存"
        cancelText="取消"
        confirmLoading={manageLoading}
        width={760}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-5)', minHeight: 340 }}>
          {/* 左：全量产品列表 */}
          <div>
            <div style={{ marginBottom: 'var(--sp-3)', display: 'flex', gap: 'var(--sp-2)' }}>
              <Input
                placeholder="搜索产品名称"
                value={productQuery}
                onChange={(e) => {
                  setProductQuery(e.target.value);
                  setProductPage(1);
                  loadAllProducts(1, e.target.value);
                }}
                style={{ flex: 1 }}
              />
            </div>
            {allProductsLoading ? (
              <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
            ) : allProducts.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">暂无产品</div></div>
            ) : (
              <>
                <div style={{ maxHeight: 280, overflowY: 'auto', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                  {allProducts.map((p) => (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 'var(--sp-2)',
                        padding: '8px var(--sp-3)',
                        borderBottom: '1px solid var(--gray-100)',
                        cursor: 'pointer',
                      }}
                      onClick={() => {
                        setSelectedIds((prev) =>
                          prev.includes(p.id) ? prev.filter((id) => id !== p.id) : [...prev, p.id]
                        );
                      }}
                    >
                      <Checkbox checked={selectedIds.includes(p.id)} onChange={() => {}} />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-800)' }}>{p.nickname}</div>
                        {p.core_selling_point && (
                          <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>{p.core_selling_point}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {productTotalPages > 1 && (
                  <div className="pagination" style={{ marginTop: 'var(--sp-2)' }}>
                    <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>共 {productTotal} 个</span>
                    <div className="pages">
                      <div
                        className="page-btn"
                        onClick={() => { const p = Math.max(1, productPage - 1); setProductPage(p); loadAllProducts(p, productQuery); }}
                      >‹</div>
                      <div className="page-btn active">{productPage}</div>
                      <div
                        className="page-btn"
                        onClick={() => { const p = Math.min(productTotalPages, productPage + 1); setProductPage(p); loadAllProducts(p, productQuery); }}
                      >›</div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* 右：已选预览 */}
          <div>
            <div style={{ marginBottom: 'var(--sp-2)', fontSize: 13, fontWeight: 600, color: 'var(--gray-700)' }}>
              已选（{selectedIds.length}）
            </div>
            <div
              style={{
                maxHeight: 320,
                overflowY: 'auto',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
              }}
            >
              {selectedIds.length === 0 ? (
                <div className="empty-state" style={{ padding: 'var(--sp-5)' }}>
                  <div className="empty-state-text">未选择任何商品</div>
                </div>
              ) : (
                allProducts
                  .filter((p) => selectedIds.includes(p.id))
                  .map((p) => (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px var(--sp-3)',
                        borderBottom: '1px solid var(--gray-100)',
                        fontSize: 13,
                      }}
                    >
                      <span style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{p.nickname}</span>
                      <CloseOutlined
                        style={{ fontSize: 12, color: 'var(--gray-400)', cursor: 'pointer' }}
                        onClick={() => setSelectedIds((prev) => prev.filter((id) => id !== p.id))}
                      />
                    </div>
                  ))
              )}
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
}
