import { useEffect, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { Modal, Drawer, Form, Input, Select, Tabs, Tag, Popconfirm, message } from 'antd';
import { getKols, createKol, getKol, updateKol, deleteKol, fetchTikhub } from '../../api/kols';
import type { Kol, KolDetail, KolListParams, CreateKolRequest, UpdateKolRequest, KolStatus, TikhubFansData } from '../../types/kol';
import type { PagedData } from '../../types/api';

const PAGE_SIZE = 20;

function formatFollowers(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`;
  return n.toLocaleString();
}

const STATUS_MAP: Record<KolStatus, { label: string; cls: string }> = {
  signed:          { label: '签约中', cls: 'badge-success' },
  pending_renewal: { label: '待续约', cls: 'badge-warning' },
  terminated:      { label: '已解约', cls: 'badge-gray' },
};

function statusBadge(status: KolStatus) {
  const { label, cls } = STATUS_MAP[status] ?? { label: status, cls: 'badge-gray' };
  return <span className={`badge ${cls}`}>{label}</span>;
}

function KolAvatar({ url, name }: { url?: string; name: string }) {
  return (
    <img
      src={url || '/default-avatar.svg'}
      alt={name}
      onError={(e) => {
        e.currentTarget.onerror = null;          // 防止 default-avatar 也失败时死循环
        e.currentTarget.src = '/default-avatar.svg';
      }}
      style={{ width: 36, height: 36, borderRadius: '50%', objectFit: 'cover', display: 'inline-block' }}
    />
  );
}

// 进度条行：标签 + 条 + 百分比
function BarRow({ label, pct, color, maxPct = 100 }: {
  label: string; pct: number; color: string; maxPct?: number;
}) {
  const width = maxPct > 0 ? Math.min((pct / maxPct) * 100, 100) : 0;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
        <span style={{ color: 'var(--gray-600)' }}>{label}</span>
        <span style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{Number(pct).toFixed(1)}%</span>
      </div>
      <div style={{ height: 6, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${width}%`,
          background: color, borderRadius: 3,
          transition: 'width .4s ease',
        }} />
      </div>
    </div>
  );
}

interface FansItem { name: string; value: number; }

// JSON.parse 兜底：解析失败返回空数组，不白屏
function parseFansField(raw: string | undefined): FansItem[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is FansItem =>
        item != null &&
        typeof item.name === 'string' &&
        typeof item.value === 'number' &&
        !isNaN(item.value),
    );
  } catch {
    return [];
  }
}

const genderLabel = (name: string) => name === 'female' ? '女性' : '男性';
const pct = (value: number) => (value * 100).toFixed(1) + '%';

function FansPanel({ data, onFetch, fetching, updatedAt }: {
  data?: TikhubFansData | null;
  onFetch: () => void;
  fetching?: boolean;
  updatedAt?: string;
}) {
  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 0' }}>
        <div style={{ fontSize: 13, color: 'var(--gray-400)', marginBottom: 16 }}>
          暂无粉丝画像数据，请点击立即抓取
        </div>
        <button className="btn btn-primary btn-sm" onClick={onFetch} disabled={fetching}>
          {fetching ? '抓取中...' : '立即抓取'}
        </button>
      </div>
    );
  }

  const genderList   = parseFansField(data.Gender);
  const ageList      = parseFansField(data.Age).sort((a, b) => b.value - a.value);
  const provinceList = parseFansField(data.Province).sort((a, b) => b.value - a.value).slice(0, 5);
  const tagList      = Array.isArray(data.FirstTag) ? data.FirstTag : [];

  const femaleItem  = genderList.find(g => g.name === 'female');
  const maleItem    = genderList.find(g => g.name === 'male');
  const provinceMax = (provinceList[0]?.value ?? 1) * 100;

  const block = (title: string, children: ReactNode) => (
    <div style={{
      marginBottom: 16, padding: '14px 16px',
      border: '1px solid var(--gray-100)', borderRadius: 10,
      background: '#fff',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 12 }}>
        {title}
      </div>
      {children}
    </div>
  );

  return (
    <div style={{ paddingTop: 4 }}>

      {/* 性别占比 */}
      {block('性别占比',
        genderList.length > 0 ? (
          <>
            <BarRow label="女" pct={femaleItem ? femaleItem.value * 100 : 0} color="#F59A23" />
            <BarRow label="男" pct={maleItem   ? maleItem.value   * 100 : 0} color="#4096FF" />
          </>
        ) : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>
      )}

      {/* 年龄分布（按占比从高到低） */}
      {block('年龄分布',
        ageList.length > 0 ? (
          ageList.map(a => (
            <BarRow key={a.name} label={a.name} pct={a.value * 100} color="#F59A23" />
          ))
        ) : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>
      )}

      {/* 省份 TOP 5 */}
      {block('省份 TOP 5',
        provinceList.length > 0 ? (
          provinceList.map(p => (
            <BarRow key={p.name} label={p.name} pct={p.value * 100} color="#7C6FCD" maxPct={provinceMax} />
          ))
        ) : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无数据</div>
      )}

      {/* 粉丝标签 */}
      {block('粉丝标签',
        tagList.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {tagList.map(t => (
              <Tag key={t} color="orange" style={{ margin: 0, borderRadius: 4 }}>{t}</Tag>
            ))}
          </div>
        ) : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>暂无标签</div>
      )}

      {/* 底部数据来源 */}
      <div style={{
        paddingTop: 8, fontSize: 11, color: 'var(--gray-400)',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>数据来源：TikHub</span>
        {updatedAt && (
          <span>最后更新：{new Date(updatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
        )}
      </div>
    </div>
  );
}

const PLATFORMS = ['抖音', '快手', '小红书', 'B站'];

export default function KolsPage() {
  const [data, setData] = useState<PagedData<Kol> | null>(null);
  const [filters, setFilters] = useState<KolListParams>({ page: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm] = Form.useForm<CreateKolRequest>();

  const [editKol, setEditKol] = useState<Kol | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editForm] = Form.useForm<UpdateKolRequest>();

  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<KolDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [personaSaving, setPersonaSaving] = useState(false);
  const [personaValue, setPersonaValue] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    getKols(filters)
      .then(setData)
      .catch(() => message.error('加载红人列表失败'))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  async function loadDetail(id: number) {
    setDetailId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getKol(id);
      setDetail(d);
      setPersonaValue(d.persona ?? '');
    } catch {
      message.error('加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleFetchTikhub() {
    if (!detailId) return;
    setFetchLoading(true);
    try {
      await fetchTikhub(detailId);
      const d = await getKol(detailId);
      setDetail(d);
      setPersonaValue(d.persona ?? '');
      message.success('抓取成功');
    } catch {
      message.error('抓取失败');
    } finally {
      setFetchLoading(false);
    }
  }

  async function handleSavePersona() {
    if (!detailId) return;
    setPersonaSaving(true);
    try {
      await updateKol(detailId, { persona: personaValue });
      message.success('人格档案已保存');
      if (detail) setDetail({ ...detail, persona: personaValue });
    } catch {
      message.error('保存失败');
    } finally {
      setPersonaSaving(false);
    }
  }

  async function handleCreate(values: CreateKolRequest) {
    if (!values.douyin_id && !values.sec_uid) {
      message.warning('抖音号与安全ID至少填一个');
      return;
    }
    setCreateLoading(true);
    try {
      await createKol(values);
      message.success('红人已添加');
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '创建失败');
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleUpdate(values: UpdateKolRequest) {
    if (!editKol) return;
    setEditLoading(true);
    try {
      await updateKol(editKol.id, values);
      message.success('更新成功');
      setEditKol(null);
      editForm.resetFields();
      load();
      if (detailId === editKol.id) loadDetail(editKol.id);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteKol(id);
      message.success('已删除');
      load();
    } catch {
      message.error('删除失败');
    }
  }

  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? Math.ceil(total / PAGE_SIZE);
  const page = filters.page ?? 1;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">红人管理</h1>
          <p className="page-desc">管理平台合作红人信息</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>+ 新增红人</button>
        </div>
      </div>

      <div className="card">
        <div className="filter-bar">
          <select
            className="filter-select"
            value={filters.platform ?? ''}
            onChange={e => setFilters(f => ({ ...f, platform: e.target.value || undefined, page: 1 }))}
          >
            <option value="">全部平台</option>
            {PLATFORMS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select
            className="filter-select"
            value={filters.status ?? ''}
            onChange={e => setFilters(f => ({ ...f, status: e.target.value || undefined, page: 1 }))}
          >
            <option value="">全部状态</option>
            <option value="signed">签约中</option>
            <option value="pending_renewal">待续约</option>
            <option value="terminated">已解约</option>
          </select>
          <input
            className="filter-input"
            placeholder="搜索姓名 / 账号"
            value={filters.keyword ?? ''}
            onChange={e => setFilters(f => ({ ...f, keyword: e.target.value || undefined, page: 1 }))}
            style={{ width: 180 }}
          />
          <span className="filter-count">共 {total} 位红人</span>
        </div>

        {loading ? (
          <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        ) : !data || data.items.length === 0 ? (
          <div className="empty-state"><div className="empty-state-text">暂无红人数据</div></div>
        ) : (
          <>
            <table className="ant-table">
              <thead>
                <tr>
                  <th style={{ width: 56, textAlign: 'center' }}>头像</th>
                  <th style={{ width: 110 }}>姓名</th>
                  <th style={{ width: 160 }}>账号ID</th>
                  <th style={{ width: 95 }}>粉丝数量</th>
                  <th style={{ width: 85 }}>作品数量</th>
                  <th style={{ width: 85 }}>状态</th>
                  <th style={{ width: 90 }}>负责人</th>
                  <th style={{ width: 100 }}>添加时间</th>
                  <th className="col-actions" style={{ width: 160 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(k => (
                  <tr key={k.id}>
                    <td style={{ textAlign: 'center', verticalAlign: 'middle' }}>
                      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                        <KolAvatar url={k.avatar_url} name={k.name} />
                      </div>
                    </td>
                    <td style={{ fontWeight: 600, color: 'var(--gray-800)', fontSize: 14 }}>{k.name}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--gray-700)' }}>{k.douyin_id ?? k.sec_uid ?? '—'}</td>
                    <td style={{ fontWeight: 600, color: 'var(--gray-800)', fontSize: 13 }}>{formatFollowers(k.followers_count)}</td>
                    <td style={{ color: 'var(--gray-700)', fontSize: 13 }}>{k.works_count?.toLocaleString() ?? '—'}</td>
                    <td>{statusBadge(k.status)}</td>
                    <td style={{ color: 'var(--gray-700)', fontSize: 13 }}>{k.owner ?? '—'}</td>
                    <td style={{ color: 'var(--gray-500)', fontSize: 12 }}>
                      {new Date(k.created_at).toLocaleDateString('zh-CN')}
                    </td>
                    <td className="col-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => loadDetail(k.id)}>详情</button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => {
                          setEditKol(k);
                          editForm.setFieldsValue({
                            name: k.name, platform: k.platform,
                            douyin_id: k.douyin_id, sec_uid: k.sec_uid,
                            owner: k.owner, status: k.status,
                            persona: k.persona, style_note: k.style_note,
                          });
                        }}
                      >
                        编辑
                      </button>
                      <Popconfirm
                        title={`确认删除红人「${k.name}」？`}
                        description="删除后数据不可恢复。"
                        okText="确认删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => handleDelete(k.id)}
                      >
                        <button className="btn btn-danger-ghost btn-sm">删除</button>
                      </Popconfirm>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {total > PAGE_SIZE && (
              <div className="pagination">
                <span>共 {total} 位红人</span>
                <div className="pages">
                  <div className="page-btn" onClick={() => setFilters(f => ({ ...f, page: Math.max(1, (f.page ?? 1) - 1) }))}>‹</div>
                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map(p => (
                    <div key={p} className={`page-btn${page === p ? ' active' : ''}`} onClick={() => setFilters(f => ({ ...f, page: p }))}>{p}</div>
                  ))}
                  <div className="page-btn" onClick={() => setFilters(f => ({ ...f, page: Math.min(totalPages, (f.page ?? 1) + 1) }))}>›</div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* 新增红人弹窗 */}
      <Modal
        title="新增红人"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        onOk={() => createForm.submit()}
        okText="添加"
        cancelText="取消"
        confirmLoading={createLoading}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="请输入红人姓名" />
          </Form.Item>
          <Form.Item label="平台" name="platform" initialValue="抖音" rules={[{ required: true }]}>
            <Select>
              {PLATFORMS.map(p => <Select.Option key={p} value={p}>{p}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item label="抖音号" name="douyin_id">
            <Input placeholder="请输入抖音号" />
          </Form.Item>
          <Form.Item label="安全ID (sec_uid)" name="sec_uid">
            <Input placeholder="请输入 sec_uid" />
          </Form.Item>
          <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: -8, marginBottom: 16 }}>
            抖音号与安全ID至少填一个
          </div>
          <Form.Item label="负责人" name="owner">
            <Input placeholder="请输入负责人姓名" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑红人弹窗 */}
      <Modal
        title={`编辑红人：${editKol?.name ?? ''}`}
        open={!!editKol}
        onCancel={() => { setEditKol(null); editForm.resetFields(); }}
        onOk={() => editForm.submit()}
        okText="保存"
        cancelText="取消"
        confirmLoading={editLoading}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate} style={{ marginTop: 16 }}>
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="平台" name="platform" rules={[{ required: true }]}>
            <Select>
              {PLATFORMS.map(p => <Select.Option key={p} value={p}>{p}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item label="抖音号" name="douyin_id"><Input /></Form.Item>
          <Form.Item label="安全ID (sec_uid)" name="sec_uid"><Input /></Form.Item>
          <Form.Item label="负责人" name="owner"><Input /></Form.Item>
          <Form.Item label="状态" name="status">
            <Select>
              <Select.Option value="signed">签约中</Select.Option>
              <Select.Option value="pending_renewal">待续约</Select.Option>
              <Select.Option value="terminated">已解约</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="人格档案" name="persona">
            <Input.TextArea rows={3} placeholder="请输入人格档案" />
          </Form.Item>
          <Form.Item label="风格备注" name="style_note">
            <Input.TextArea rows={2} placeholder="请输入风格备注" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情抽屉 */}
      <Drawer
        title={detail?.name ?? '红人详情'}
        open={detailId !== null}
        onClose={() => { setDetailId(null); setDetail(null); }}
        width={520}
        extra={
          <button
            className="btn btn-ghost btn-sm"
            disabled={fetchLoading || detailLoading}
            onClick={handleFetchTikhub}
          >
            {fetchLoading ? '抓取中...' : '重新抓取'}
          </button>
        }
      >
        {detailLoading ? (
          <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        ) : !detail ? null : (
          <Tabs
            items={[
              {
                key: 'info',
                label: '基本信息',
                children: (
                  <div style={{ paddingTop: 8 }}>
                    <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 24 }}>
                      <KolAvatar url={detail.avatar_url} name={detail.name} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--gray-800)' }}>{detail.name}</div>
                        <div style={{ fontSize: 13, color: 'var(--gray-500)', marginTop: 2 }}>{detail.account_name}</div>
                      </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
                      {([
                        ['平台', detail.platform],
                        ['粉丝数', formatFollowers(detail.followers_count)],
                        ['作品数', detail.works_count?.toLocaleString() ?? '—'],
                        ['状态', null],
                        ['负责人', detail.owner ?? '—'],
                      ] as [string, string | null][]).map(([label, value]) => (
                        <div key={label}>
                          <div style={{ fontSize: 11, color: 'var(--gray-400)', marginBottom: 4 }}>{label}</div>
                          <div style={{ fontWeight: 500, color: 'var(--gray-700)' }}>
                            {label === '状态' ? statusBadge(detail.status) : value}
                          </div>
                        </div>
                      ))}
                    </div>
                    {/* 签名/简介 */}
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)', marginBottom: 6 }}>个人简介</div>
                      <div style={{ fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                        {detail.signature || '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 8 }}>人格档案</div>
                      <Input.TextArea
                        rows={5}
                        value={personaValue}
                        onChange={e => setPersonaValue(e.target.value)}
                        placeholder="暂无人格档案，输入后点击保存"
                      />
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ marginTop: 8 }}
                        disabled={personaSaving}
                        onClick={handleSavePersona}
                      >
                        {personaSaving ? '保存中...' : '保存人格档案'}
                      </button>
                    </div>
                  </div>
                ),
              },
              {
                key: 'fans',
                label: '粉丝画像',
                children: (
                  <FansPanel
                    data={detail.tikhub_raw?.fans_info?.data}
                    onFetch={handleFetchTikhub}
                    fetching={fetchLoading}
                    updatedAt={detail.updated_at}
                  />
                ),
              },
            ]}
          />
        )}
      </Drawer>
    </>
  );
}
