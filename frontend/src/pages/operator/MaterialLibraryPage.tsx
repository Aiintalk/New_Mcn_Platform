import { useEffect, useState, useCallback, useMemo } from 'react';
import { Input, Tabs, Button, Modal, Form, Select, message, Spin, Popconfirm } from 'antd';
import {
  getMaterialLibraryKols,
  getMaterialLibraryKolDetail,
  updateKolProfile,
  createKolReference,
  deleteKolReference,
  getKolIntake,
  generateSoul,
} from '../../api/materialLibrary';
import type { KolListItem, KolDetail, KolReference, IntakeData } from '../../api/materialLibrary';

const REFERENCE_TYPES = [
  { label: '红人爆款文案', group: '人设仿写素材' },
  { label: '红人喜欢的内容', group: '人设仿写素材' },
  { label: '风格参考', group: '人设仿写素材' },
  { label: '千川爆款文案', group: '千川仿写素材' },
  { label: '千川喜欢的内容', group: '千川仿写素材' },
  { label: '千川风格参考', group: '千川仿写素材' },
];

export default function MaterialLibraryPage() {
  const [kols, setKols] = useState<KolListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedKolId, setSelectedKolId] = useState<number | null>(null);
  const [detail, setDetail] = useState<KolDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('persona');

  // persona / content_plan editing
  const [personaText, setPersonaText] = useState('');
  const [contentPlanText, setContentPlanText] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [generating, setGenerating] = useState(false);

  // reference modal
  const [refModalOpen, setRefModalOpen] = useState(false);
  const [refForm] = Form.useForm();
  const [addingRef, setAddingRef] = useState(false);

  // intake data
  const [intake, setIntake] = useState<IntakeData | null>(null);

  // ---- list ----
  const loadKols = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMaterialLibraryKols(search);
      setKols(data);
      if (data.length > 0 && selectedKolId === null) {
        setSelectedKolId(data[0].id);
      }
    } catch {
      message.error('加载红人列表失败');
    } finally {
      setLoading(false);
    }
  }, [search, selectedKolId]);

  useEffect(() => { loadKols(); }, [loadKols]);

  // ---- detail ----
  const loadDetail = useCallback(async (kolId: number) => {
    setDetailLoading(true);
    try {
      const d = await getMaterialLibraryKolDetail(kolId);
      setDetail(d);
      setPersonaText(d.persona);
      setContentPlanText(d.content_plan);
    } catch {
      message.error('加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedKolId !== null) {
      loadDetail(selectedKolId);
      setIntake(null);
    }
  }, [selectedKolId, loadDetail]);

  // ---- profile save ----
  async function handleSavePersona() {
    if (!selectedKolId) return;
    setSavingProfile(true);
    try {
      await updateKolProfile(selectedKolId, { persona: personaText });
      message.success('人格档案已保存');
      loadKols();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleSaveContentPlan() {
    if (!selectedKolId) return;
    setSavingProfile(true);
    try {
      await updateKolProfile(selectedKolId, { content_plan: contentPlanText });
      message.success('内容规划已保存');
      loadKols();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSavingProfile(false);
    }
  }

  // ---- generate soul ----
  async function handleGenerateSoul() {
    if (!selectedKolId) return;
    if (personaText.trim()) {
      Modal.confirm({
        title: '确认覆盖',
        content: '当前已有人格档案内容，AI 生成的初稿将覆盖编辑器中的内容（不会自动保存，仍需手动点保存）。是否继续？',
        onOk: doGenerate,
      });
    } else {
      doGenerate();
    }
  }

  async function doGenerate() {
    if (!selectedKolId) return;
    setGenerating(true);
    try {
      const result = await generateSoul(selectedKolId);
      setPersonaText(result.soul_md);
      setActiveTab('persona');
      message.success('人格档案初稿已生成，请检查后保存');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
    }
  }

  // ---- reference CRUD ----
  async function handleAddReference() {
    const values = await refForm.validateFields();
    if (!selectedKolId) return;
    setAddingRef(true);
    try {
      await createKolReference(selectedKolId, values);
      message.success('素材已添加');
      setRefModalOpen(false);
      refForm.resetFields();
      loadDetail(selectedKolId);
      loadKols();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '添加失败');
    } finally {
      setAddingRef(false);
    }
  }

  async function handleDeleteReference(refId: number) {
    if (!selectedKolId) return;
    try {
      await deleteKolReference(selectedKolId, refId);
      message.success('已删除');
      loadDetail(selectedKolId);
      loadKols();
    } catch {
      message.error('删除失败');
    }
  }

  // ---- intake ----
  async function loadIntake() {
    if (!selectedKolId || intake !== null) return;
    try {
      const data = await getKolIntake(selectedKolId);
      setIntake(data);
    } catch {
      message.error('加载入驻问卷失败');
    }
  }

  const groupedRefs = useMemo(() => {
    const groups: Record<string, KolReference[]> = {};
    for (const t of REFERENCE_TYPES) {
      const refs = detail?.references?.[t.label] || [];
      if (refs.length > 0) groups[t.label] = refs;
    }
    return groups;
  }, [detail]);

  // ---- render ----
  const kolListTab = (
    <div style={{ width: 280, borderRight: '1px solid var(--gray-200)', overflowY: 'auto', height: '100%' }}>
      <div style={{ padding: '12px' }}>
        <Input.Search
          placeholder="搜索红人名"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onSearch={loadKols}
          allowClear
          style={{ marginBottom: 12 }}
        />
        {loading ? <Spin size="small" /> : kols.length === 0 ? (
          <div className="empty-state"><div className="empty-state-text">暂无红人</div></div>
        ) : (
          kols.map(kol => (
            <div
              key={kol.id}
              onClick={() => setSelectedKolId(kol.id)}
              style={{
                padding: '10px 12px',
                cursor: 'pointer',
                borderRadius: 6,
                marginBottom: 4,
                background: selectedKolId === kol.id ? 'var(--brand-50)' : 'transparent',
                border: selectedKolId === kol.id ? '1px solid var(--brand-200)' : '1px solid transparent',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 14 }}>{kol.name}</div>
              <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {kol.has_persona && <span style={{ color: 'var(--brand-500)' }}>档案●</span>}
                {kol.has_content_plan && <span style={{ color: 'var(--brand-500)' }}>规划●</span>}
                <span>素材 {kol.reference_count}</span>
                {kol.has_intake && <span style={{ color: 'var(--success)' }}>问卷●</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  const personaTab = (
    <div style={{ padding: '16px' }}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600 }}>人格档案（soul.md）</span>
        <div>
          <Button
            onClick={handleGenerateSoul}
            loading={generating}
            style={{ marginRight: 8 }}
            disabled={!detail?.name}
          >
            从入驻问卷生成
          </Button>
          <Button type="primary" onClick={handleSavePersona} loading={savingProfile}>
            保存
          </Button>
        </div>
      </div>
      <Input.TextArea
        value={personaText}
        onChange={e => setPersonaText(e.target.value)}
        rows={24}
        placeholder="暂无人格档案。可手动编辑，或点击「从入驻问卷生成」使用 AI 生成初稿。"
        style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
      />
    </div>
  );

  const contentPlanTab = (
    <div style={{ padding: '16px' }}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600 }}>内容规划（content-plan.md）</span>
        <Button type="primary" onClick={handleSaveContentPlan} loading={savingProfile}>保存</Button>
      </div>
      <Input.TextArea
        value={contentPlanText}
        onChange={e => setContentPlanText(e.target.value)}
        rows={24}
        placeholder="暂无内容规划"
        style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
      />
    </div>
  );

  const referencesTab = (
    <div style={{ padding: '16px' }}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600 }}>参考素材</span>
        <Button type="primary" onClick={() => setRefModalOpen(true)}>添加素材</Button>
      </div>
      {Object.keys(groupedRefs).length === 0 ? (
        <div className="empty-state"><div className="empty-state-text">暂无素材</div></div>
      ) : (
        Object.entries(groupedRefs).map(([type, refs]) => (
          <div key={type} style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--gray-700)' }}>
              {type}（{refs.length}）
            </div>
            {refs.map(ref => (
              <div key={ref.id} className="card" style={{ marginBottom: 8, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{ref.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>
                      {ref.likes != null && `点赞 ${ref.likes} · `}来源 {ref.source}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, color: 'var(--gray-600)', whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto' }}>
                      {ref.content}
                    </div>
                  </div>
                  <Popconfirm title="确认删除？" onConfirm={() => handleDeleteReference(ref.id)}>
                    <Button type="text" danger size="small">删除</Button>
                  </Popconfirm>
                </div>
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );

  const intakeTab = (
    <div style={{ padding: '16px' }}>
      <div style={{ marginBottom: 12, fontWeight: 600 }}>入驻问卷数据</div>
      {intake === null ? (
        <Button onClick={loadIntake} loading={false}>加载入驻问卷</Button>
      ) : intake === null ? (
        <div className="empty-state"><div className="empty-state-text">该红人暂无入驻问卷数据</div></div>
      ) : (
        <div>
          <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--gray-500)' }}>
            来源：{intake.source === 'submission' ? '分享链接提交' : '运营直发会话'} ·
            状态：{intake.report_status}
          </div>
          {intake.ai_report && (
            <div className="card" style={{ marginBottom: 16, padding: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>AI 分析报告</div>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: 'var(--gray-700)' }}>
                {intake.ai_report}
              </div>
            </div>
          )}
          <div className="card" style={{ padding: 16 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>问卷对话记录</div>
            <div style={{ maxHeight: 400, overflow: 'auto', fontSize: 13 }}>
              {Array.isArray(intake.messages) && intake.messages.map((msg: any, i: number) => (
                <div key={i} style={{ marginBottom: 8 }}>
                  <strong>{msg.role === 'assistant' ? 'AI' : msg.role === 'user' ? '红人' : msg.role}：</strong>
                  <span style={{ color: 'var(--gray-600)' }}>{typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">素材库</h1>
          <p className="page-desc">红人素材中枢：人格档案 + 内容规划 + 参考素材管理</p>
        </div>
      </div>
      <div style={{ display: 'flex', height: 'calc(100vh - 200px)', minHeight: 500 }}>
        {kolListTab}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {detailLoading ? (
            <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
          ) : detail ? (
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              style={{ height: '100%' }}
              items={[
                { key: 'persona', label: '人格档案', children: personaTab },
                { key: 'content-plan', label: '内容规划', children: contentPlanTab },
                { key: 'references', label: `参考素材 (${detail ? Object.values(detail.references).reduce((a, b) => a + b.length, 0) : 0})`, children: referencesTab },
                { key: 'intake', label: '入驻信息', children: intakeTab },
              ]}
            />
          ) : (
            <div className="empty-state" style={{ height: '100%' }}>
              <div className="empty-state-text">请从左侧选择红人</div>
            </div>
          )}
        </div>
      </div>

      <Modal
        title="添加参考素材"
        open={refModalOpen}
        onCancel={() => setRefModalOpen(false)}
        onOk={handleAddReference}
        confirmLoading={addingRef}
        okText="添加"
      >
        <Form form={refForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="类型" name="type" rules={[{ required: true }]}>
            <Select placeholder="选择素材类型">
              {REFERENCE_TYPES.map(t => (
                <Select.Option key={t.label} value={t.label}>
                  {t.group} — {t.label}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="标题" name="title" rules={[{ required: true }]}>
            <Input placeholder="视频/文案标题" />
          </Form.Item>
          <Form.Item label="点赞数" name="likes">
            <Input type="number" placeholder="选填" />
          </Form.Item>
          <Form.Item label="正文内容" name="content" rules={[{ required: true }]}>
            <Input.TextArea rows={8} placeholder="粘贴文案正文" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
