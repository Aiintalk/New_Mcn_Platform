import { useCallback, useEffect, useState } from 'react';
import { Modal, Form, Input, Select, Tabs, Popconfirm, message } from 'antd';
import {
  getIntakeConfigs, updateIntakeConfig, getAdminQuestions,
  createQuestion, updateQuestion, deleteQuestion, getAdminSubmissions,
  getAdminSubmissionDetail, regenerateReport,
} from '../../api/intake';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';
import type { IntakeQuestion, IntakeSubmission, IntakeConfigForm, QuestionForm } from '../../types/intake';

const STATUS_LABEL: Record<string, string> = {
  pending: '待生成', generating: '生成中', ready: '已就绪', failed: '生成失败',
};
const STATUS_CLS: Record<string, string> = {
  pending: 'badge-gray', generating: 'badge-warning', ready: 'badge-success', failed: 'badge-danger',
};
const TYPE_LABEL: Record<string, string> = { text: '单条', multi_collect: '多条收集' };

function fmtTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

interface IntakeConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string | null;
  is_active: boolean;
}

const CONFIG_LABELS: Record<string, string> = {
  conversation_bridge: 'AI 面试官（对话模型）',
  report_generation: '报告生成模型',
};

const PROMPT_PLACEHOLDER: Record<string, string> = {
  conversation_bridge: `你是"达人说"MCN的专业面试官，负责通过自然对话收集红人入驻信息。

要求：
- 语气温和亲切，像朋友一样聊天，不像填表格
- 按题目提纲依次引导，每次只问一个问题
- 对于 multi_collect 类型题目，要追问"还有吗？最多X条"
- 所有必填题(★)必须覆盖，选填题在对话自然时可以提及
- 当必填题全部收集完毕后，主动提示用户可以提交了`,
  report_generation: `你是MCN专业分析师，根据以下红人入驻对话记录，生成一份详细的入驻评估报告。

报告结构：
## 一、基本信息
## 二、野心与执行力评估
## 三、人品与稳定性评估
## 四、内容方向与差异化
## 五、综合评分与建议

对话记录：
{qa_content}

请用专业但平实的语言，重点分析这位红人是否适合签约、优势在哪、风险点是什么。`,
};

export default function AdminIntakePage({ embedded = false }: { embedded?: boolean }) {
  const [configs, setConfigs] = useState<IntakeConfig[]>([]);
  const [questions, setQuestions] = useState<IntakeQuestion[]>([]);
  const [submissions, setSubmissions] = useState<IntakeSubmission[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [activeTab, setActiveTab] = useState('config');

  // Config editing
  const [editingConfig, setEditingConfig] = useState<IntakeConfig | null>(null);
  const [configForm] = Form.useForm();

  // Admin submission detail
  const [selectedAdminSub, setSelectedAdminSub] = useState<IntakeSubmission | null>(null);
  const [adminDetailTab, setAdminDetailTab] = useState<'messages' | 'report'>('messages');

  // Question editing
  const [questionModal, setQuestionModal] = useState<{ mode: 'create' | 'edit'; data?: IntakeQuestion } | null>(null);
  const [qForm] = Form.useForm();

  const loadAll = useCallback(async () => {
    const [cfgs, qs, mds] = await Promise.all([
      getIntakeConfigs().catch(() => [] as IntakeConfig[]),
      getAdminQuestions().catch(() => [] as IntakeQuestion[]),
      getAiModels().then(r => r.items ?? r).catch(() => [] as AiModelItem[]),
    ]);
    setConfigs(cfgs);
    setQuestions(qs);
    setModels(mds as AiModelItem[]);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    if (activeTab === 'submissions') {
      getAdminSubmissions().then(setSubmissions).catch(() => message.error('加载提交失败'));
    }
  }, [activeTab]);

  // Save config
  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    const body: IntakeConfigForm = { ai_model_id: values.ai_model_id ?? null, system_prompt: values.system_prompt ?? null };
    try {
      await updateIntakeConfig(editingConfig.config_key, body);
      message.success('配置已保存');
      setEditingConfig(null);
      loadAll();
    } catch (err: unknown) {
      message.error((err as Error).message || '保存失败');
    }
  }

  function openConfigEdit(cfg: IntakeConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  // Question CRUD
  async function saveQuestion(values: QuestionForm & { is_active: boolean }) {
    try {
      if (questionModal?.mode === 'edit' && questionModal.data) {
        await updateQuestion(questionModal.data.id, values);
        message.success('题目已更新');
      } else {
        await createQuestion(values);
        message.success('题目已添加');
      }
      setQuestionModal(null);
      qForm.resetFields();
      getAdminQuestions().then(setQuestions);
    } catch (err: unknown) {
      message.error((err as Error).message || '操作失败');
    }
  }

  async function handleDeleteQuestion(id: number) {
    try {
      await deleteQuestion(id);
      message.success('已删除');
      setQuestions(qs => qs.filter(q => q.id !== id));
    } catch (err: unknown) {
      message.error((err as Error).message || '删除失败');
    }
  }

  async function openAdminDetail(id: number) {
    try {
      const detail = await getAdminSubmissionDetail(id);
      setSelectedAdminSub(detail);
      setAdminDetailTab('messages');
    } catch (err: unknown) {
      message.error((err as Error).message || '加载详情失败');
    }
  }

  async function handleRegenerate(id: number) {
    try {
      await regenerateReport(id);
      message.success('已触发重新生成，请稍后刷新查看');
      getAdminSubmissions().then(setSubmissions).catch(() => {});
    } catch (err: unknown) {
      message.error((err as Error).message || '操作失败');
    }
  }

  function openQuestionEdit(q: IntakeQuestion) {
    setQuestionModal({ mode: 'edit', data: q });
    qForm.setFieldsValue({
      order_num: q.order_num, category: q.category, question_text: q.question_text,
      question_type: q.question_type, max_items: q.max_items, is_required: q.is_required, is_active: q.is_active,
    });
  }

  const categories = [...new Set(questions.map(q => q.category))];

  return (
    <>
      {!embedded && (
        <div className="page-header">
          <div>
            <h1 className="page-title">红人信息采集助手 · 配置</h1>
            <p className="page-desc">管理 AI 对话模型、系统提示词和题目提纲</p>
          </div>
        </div>
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: 'config', label: 'AI 配置' },
        { key: 'questions', label: `题目管理（${questions.length}）` },
        { key: 'submissions', label: '全量提交' },
      ]} />

      {activeTab === 'config' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
          {configs.length === 0 && <div className="empty-state"><div className="empty-state-text">加载中…</div></div>}
          {configs.map(cfg => (
            <div key={cfg.config_key} className="card">
              <div className="card-body">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{CONFIG_LABELS[cfg.config_key] ?? cfg.config_key}</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 2 }}>config_key: {cfg.config_key}</div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={() => openConfigEdit(cfg)}>编辑</button>
                </div>
                <div style={{ display: 'flex', gap: 20, fontSize: 13 }}>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>模型：</span>
                    <span style={{ color: cfg.ai_model_id ? 'var(--gray-800)' : 'var(--danger)' }}>
                      {cfg.ai_model_id
                        ? (models.find(m => m.id === cfg.ai_model_id)?.name ?? `ID:${cfg.ai_model_id}`)
                        : '⚠ 未配置'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--gray-400)' }}>Prompt：</span>
                    <span style={{ color: cfg.system_prompt ? 'var(--success)' : 'var(--warning)' }}>
                      {cfg.system_prompt ? `已设置（${cfg.system_prompt.length} 字）` : '未设置'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'questions' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16, marginBottom: 12 }}>
            <button className="btn btn-primary btn-sm" onClick={() => { setQuestionModal({ mode: 'create' }); qForm.resetFields(); }}>
              + 添加题目
            </button>
          </div>
          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {questions.length === 0
                ? <div className="empty-state"><div className="empty-state-text">暂无题目</div></div>
                : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th style={{ width: 80 }}>分类</th>
                        <th style={{ width: 48 }}>序号</th>
                        <th>题目</th>
                        <th style={{ width: 70 }}>类型</th>
                        <th style={{ width: 60 }}>必填</th>
                        <th style={{ width: 60 }}>状态</th>
                        <th style={{ textAlign: 'right' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {categories.map(cat => {
                        const catQs = questions.filter(q => q.category === cat);
                        return catQs.map((q, i) => (
                          <tr key={q.id} style={{ opacity: q.is_active ? 1 : 0.5 }}>
                            {i === 0 && (
                              <td rowSpan={catQs.length} style={{ background: 'var(--bg-muted)', verticalAlign: 'middle', textAlign: 'center', fontSize: 12, color: 'var(--gray-500)', fontWeight: 600 }}>
                                {cat}
                              </td>
                            )}
                            <td>{q.order_num}</td>
                            <td style={{ maxWidth: 300, fontSize: 13 }}>{q.question_text}</td>
                            <td><span className="badge badge-gray">{TYPE_LABEL[q.question_type]}</span></td>
                            <td><span className={`badge ${q.is_required ? 'badge-warning' : 'badge-gray'}`}>{q.is_required ? '必填' : '选填'}</span></td>
                            <td><span className={`badge ${q.is_active ? 'badge-success' : 'badge-gray'}`}>{q.is_active ? '启用' : '停用'}</span></td>
                            <td>
                              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                                <button className="btn btn-ghost btn-sm" onClick={() => openQuestionEdit(q)}>编辑</button>
                                <Popconfirm title="确认删除？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDeleteQuestion(q.id)}>
                                  <button className="btn btn-danger-ghost btn-sm">删除</button>
                                </Popconfirm>
                              </div>
                            </td>
                          </tr>
                        ));
                      })}
                    </tbody>
                  </table>
                )}
            </div>
          </div>
        </>
      )}

      {activeTab === 'submissions' && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-body" style={{ padding: 0 }}>
            {submissions.length === 0
              ? <div className="empty-state"><div className="empty-state-text">暂无提交记录</div></div>
              : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>红人姓名</th>
                      <th>运营</th>
                      <th>报告状态</th>
                      <th>提交时间</th>
                      <th>报告生成</th>
                      <th>红人下载</th>
                      <th>运营下载</th>
                      <th style={{ textAlign: 'right' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {submissions.map(sub => (
                      <tr key={sub.id}>
                        <td style={{ fontSize: 12, color: 'var(--gray-400)' }}>{sub.id}</td>
                        <td>{sub.kol_name || <span style={{ color: 'var(--gray-400)' }}>未知</span>}</td>
                        <td style={{ fontSize: 12, color: 'var(--gray-500)' }}>
                          {sub.operator_id ? `#${sub.operator_id}` : '—'}
                        </td>
                        <td>
                          <span className={`badge ${STATUS_CLS[sub.report_status] ?? 'badge-gray'}`}>
                            {STATUS_LABEL[sub.report_status] ?? sub.report_status}
                          </span>
                        </td>
                        <td style={{ fontSize: 12 }}>{fmtTime(sub.created_at)}</td>
                        <td style={{ fontSize: 12 }}>{fmtTime(sub.report_generated_at)}</td>
                        <td style={{ fontSize: 12 }}>{fmtTime(sub.kol_downloaded_at)}</td>
                        <td style={{ fontSize: 12 }}>{fmtTime(sub.operator_downloaded_at)}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                            <button className="btn btn-ghost btn-sm" onClick={() => openAdminDetail(sub.id)}>
                              查看
                            </button>
                            {sub.report_status === 'failed' && (
                              <Popconfirm
                                title="重新触发报告生成？"
                                okText="确认" cancelText="取消"
                                onConfirm={() => handleRegenerate(sub.id)}
                              >
                                <button className="btn btn-ghost btn-sm">重新生成</button>
                              </Popconfirm>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
          </div>
        </div>
      )}

      {/* Config edit modal */}
      <Modal
        title={editingConfig ? (CONFIG_LABELS[editingConfig.config_key] ?? editingConfig.config_key) : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnClose
      >
        <Form form={configForm} layout="vertical" onFinish={saveConfig} style={{ marginTop: 16 }}>
          <Form.Item label="AI 模型" name="ai_model_id" rules={[{ required: true, message: '请选择模型' }]}>
            <Select
              placeholder="选择已配置的 AI 模型"
              options={models.filter(m => m.status === 'active').map(m => ({
                value: m.id,
                label: `${m.name} (${m.provider} · ${m.model_id})`,
              }))}
              allowClear
            />
          </Form.Item>
          <Form.Item
            label="系统 Prompt"
            name="system_prompt"
            help={editingConfig ? `参考模板：${PROMPT_PLACEHOLDER[editingConfig.config_key] ? '见下方' : '无'}` : ''}
          >
            <Input.TextArea
              rows={12}
              placeholder={editingConfig ? PROMPT_PLACEHOLDER[editingConfig.config_key] : ''}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </Form.Item>
          {editingConfig && PROMPT_PLACEHOLDER[editingConfig.config_key] && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => configForm.setFieldValue('system_prompt', PROMPT_PLACEHOLDER[editingConfig.config_key])}
            >
              使用参考模板
            </button>
          )}
        </Form>
      </Modal>

      {/* Question modal */}
      <Modal
        title={questionModal?.mode === 'edit' ? '编辑题目' : '添加题目'}
        open={!!questionModal}
        onCancel={() => { setQuestionModal(null); qForm.resetFields(); }}
        onOk={() => qForm.submit()}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={qForm} layout="vertical" onFinish={saveQuestion} style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item label="序号" name="order_num" rules={[{ required: true }]} style={{ width: 90 }}>
              <input type="number" className="ant-input" />
            </Form.Item>
            <Form.Item label="分类" name="category" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select
                showSearch allowClear
                options={categories.map(c => ({ value: c, label: c }))}
                placeholder="选择或输入分类名"
              />
            </Form.Item>
          </div>
          <Form.Item label="题目内容" name="question_text" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item label="题目类型" name="question_type" initialValue="text" style={{ flex: 1 }}>
              <Select options={[{ value: 'text', label: '单条回答' }, { value: 'multi_collect', label: '多条收集' }]} />
            </Form.Item>
            <Form.Item label="最多条数" name="max_items" style={{ width: 100 }}>
              <input type="number" className="ant-input" placeholder="仅多条" />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item label="必填" name="is_required" initialValue={true} style={{ flex: 1 }}>
              <Select options={[{ value: true, label: '必填 (★)' }, { value: false, label: '选填' }]} />
            </Form.Item>
            <Form.Item label="状态" name="is_active" initialValue={true} style={{ flex: 1 }}>
              <Select options={[{ value: true, label: '启用' }, { value: false, label: '停用' }]} />
            </Form.Item>
          </div>
        </Form>
      </Modal>

      {/* Admin submission detail modal */}
      <Modal
        title={`${selectedAdminSub?.kol_name || '未知'} · 提交详情`}
        open={!!selectedAdminSub}
        onCancel={() => setSelectedAdminSub(null)}
        footer={null}
        width={680}
        destroyOnClose
      >
        {selectedAdminSub && (
          <>
            <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
              {(['messages', 'report'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setAdminDetailTab(t)}
                  className={adminDetailTab === t ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
                >
                  {t === 'messages' ? '对话记录' : '入驻报告'}
                </button>
              ))}
            </div>

            {adminDetailTab === 'messages' && (
              <div style={{ maxHeight: 420, overflowY: 'auto', padding: '4px 0' }}>
                {(selectedAdminSub.messages ?? []).map((msg, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                    gap: 8, marginBottom: 12, alignItems: 'flex-start',
                  }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                      background: msg.role === 'user' ? 'var(--gray-200)' : 'var(--brand)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 12, fontWeight: 700,
                      color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
                    }}>
                      {msg.role === 'user' ? '红' : 'AI'}
                    </div>
                    <div style={{
                      maxWidth: '80%',
                      background: msg.role === 'user' ? 'var(--brand)' : 'var(--bg-page)',
                      color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                      padding: '8px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.6,
                      border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                      whiteSpace: 'pre-wrap',
                    }}>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {adminDetailTab === 'report' && (
              <div>
                {selectedAdminSub.report_status !== 'ready'
                  ? (
                    <div className="empty-state">
                      <div className="empty-state-icon">
                        {selectedAdminSub.report_status === 'failed' ? '❌' : '⏳'}
                      </div>
                      <div className="empty-state-text">
                        {selectedAdminSub.report_status === 'failed' ? '报告生成失败' : '报告尚未生成完成'}
                      </div>
                    </div>
                  )
                  : (
                    <>
                      <div style={{
                        maxHeight: 380, overflowY: 'auto',
                        background: 'var(--bg-page)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)', padding: '16px 20px',
                        fontSize: 13, lineHeight: 1.8, color: 'var(--gray-800)',
                        whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)',
                      }}>
                        {selectedAdminSub.ai_report || '报告内容为空'}
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                        <button className="btn btn-ghost btn-sm"
                          onClick={() => window.open(`/api/admin/intake/submissions/${selectedAdminSub.id}/download?format=pdf`, '_blank')}>
                          下载 PDF
                        </button>
                        <button className="btn btn-primary btn-sm"
                          onClick={() => window.open(`/api/admin/intake/submissions/${selectedAdminSub.id}/download?format=docx`, '_blank')}>
                          下载 Word
                        </button>
                      </div>
                    </>
                  )
                }
              </div>
            )}
          </>
        )}
      </Modal>
    </>
  );
}
