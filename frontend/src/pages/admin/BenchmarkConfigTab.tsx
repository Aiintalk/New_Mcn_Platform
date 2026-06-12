import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select, message } from 'antd';
import { getAdminConfigs, updateAdminConfig, getAdminAnalyses, getAdminAnalysisDetail, regenerateAnalysis } from '../../api/benchmark';
import { getAiModels } from '../../api/ai';
import type { AiModelItem } from '../../api/ai';
import type { BenchmarkConfig, BenchmarkAnalysis } from '../../types/benchmark';

const CONFIG_LABELS: Record<string, string> = {
  analyze: '对标分析配置',
};

const PROMPT_PLACEHOLDER: Record<string, string> = {
  analyze: `你是一个专业的抖音账号对标分析师。用户会提供一个抖音账号的内容数据，你需要根据这些数据生成两份分析文档。

用户会提供两组数据：
1. 全账号点赞TOP10的视频文案（代表这个账号历史上最能打的内容）
2. 最近30天的全部视频文案（代表当前内容策略和方向）

你需要输出两份文档，用 ===SPLIT=== 分隔符分开：

第一份：【人格档案】
严格按照以下模板结构输出。每个板块都要填，数据不足的标注"待补充"。

# {账号名} · 人格档案 v1.0

> 用于以{账号名}第一人称口吻创作内容时加载。

---

## 一、一句话定位
...（完整模板见数据库初始配置）`,
};

export default function BenchmarkConfigTab() {
  const [configs, setConfigs] = useState<BenchmarkConfig[]>([]);
  const [analyses, setAnalyses] = useState<BenchmarkAnalysis[]>([]);
  const [models, setModels] = useState<AiModelItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [editingConfig, setEditingConfig] = useState<BenchmarkConfig | null>(null);
  const [configForm] = Form.useForm();

  const [detailVisible, setDetailVisible] = useState(false);
  const [detailData, setDetailData] = useState<BenchmarkAnalysis | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, ana, mds] = await Promise.all([
        getAdminConfigs(),
        getAdminAnalyses(),
        getAiModels().then(r => r.items ?? r).catch(() => [] as AiModelItem[]),
      ]);
      setConfigs(cfg);
      setAnalyses(ana);
      setModels(mds as AiModelItem[]);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  function openConfigEdit(cfg: BenchmarkConfig) {
    setEditingConfig(cfg);
    configForm.setFieldsValue({ ai_model_id: cfg.ai_model_id, system_prompt: cfg.system_prompt });
  }

  async function saveConfig(values: { ai_model_id: number | null; system_prompt: string | null }) {
    if (!editingConfig) return;
    try {
      await updateAdminConfig(editingConfig.config_key, { ai_model_id: values.ai_model_id ?? undefined, system_prompt: values.system_prompt ?? undefined });
      message.success('配置已保存');
      setEditingConfig(null);
      loadData();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  const handleViewDetail = async (id: number) => {
    try {
      const data = await getAdminAnalysisDetail(id);
      setDetailData(data);
      setDetailVisible(true);
    } catch {
      message.error('加载详情失败');
    }
  };

  const handleRegenerate = (id: number) => {
    Modal.confirm({
      title: '确认重置',
      content: '将清空已有结果，运营需重新触发分析。',
      onOk: async () => {
        try {
          await regenerateAnalysis(id);
          message.success('已重置');
          loadData();
        } catch {
          message.error('操作失败');
        }
      },
    });
  };

  const statusTag = (status: string) => {
    const map: Record<string, { color: string; label: string }> = {
      completed: { color: 'var(--success-600)', label: '已完成' },
      generating: { color: 'var(--primary-600)', label: '生成中' },
      pending: { color: 'var(--gray-500)', label: '待处理' },
      failed: { color: 'var(--danger-600)', label: '失败' },
    };
    const s = map[status] || { color: 'var(--gray-500)', label: status };
    return <span style={{ fontSize: 12, color: s.color, background: `${s.color}11`, padding: '2px 8px', borderRadius: 4 }}>{s.label}</span>;
  };

  if (loading) return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;

  return (
    <>
      {/* Config Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
        {configs.length === 0 && <div className="empty-state"><div className="empty-state-text">暂无配置</div></div>}
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

      {/* Analyses Table */}
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>分析记录</h3>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th><th>账号名</th><th>模型</th><th>状态</th><th>Token</th><th>耗时</th><th>时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {analyses.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--gray-400)', padding: 24 }}>暂无记录</td></tr>
            ) : analyses.map((a) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{a.account_name || '-'}</td>
                <td style={{ fontSize: 12 }}>{a.model_used || '-'}</td>
                <td>{statusTag(a.status)}</td>
                <td>{a.tokens_used || '-'}</td>
                <td>{a.duration_ms ? `${(a.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                <td style={{ fontSize: 12 }}>{new Date(a.created_at).toLocaleString('zh-CN')}</td>
                <td>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => handleViewDetail(a.id)}>详情</button>
                    <button className="btn btn-ghost" style={{ fontSize: 12, color: 'var(--danger-600)' }} onClick={() => handleRegenerate(a.id)}>重置</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Config Edit Modal */}
      <Modal
        title={editingConfig ? (CONFIG_LABELS[editingConfig.config_key] ?? editingConfig.config_key) : ''}
        open={!!editingConfig}
        onCancel={() => setEditingConfig(null)}
        onOk={() => configForm.submit()}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnHidden
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

      {/* Detail Drawer */}
      {detailVisible && detailData && (
        <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 720, background: 'white', boxShadow: '-4px 0 24px rgba(0,0,0,0.1)', zIndex: 1000, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--gray-200)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ fontSize: 15, fontWeight: 600 }}>{detailData.account_name || '分析详情'}</h3>
            <button className="btn btn-ghost" onClick={() => setDetailVisible(false)}>✕</button>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
            <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>人格档案</h4>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7, background: 'var(--gray-50)', padding: 16, borderRadius: 8, marginBottom: 24 }}>
              {detailData.profile_result || '暂无'}
            </pre>
            <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>内容规划</h4>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7, background: 'var(--gray-50)', padding: 16, borderRadius: 8 }}>
              {detailData.plan_result || '暂无'}
            </pre>
          </div>
        </div>
      )}
    </>
  );
}
