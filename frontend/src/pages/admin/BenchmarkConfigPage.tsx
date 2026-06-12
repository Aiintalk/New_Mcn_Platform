import { useState, useEffect } from 'react';
import { message, Modal } from 'antd';
import { getAdminConfigs, updateAdminConfig, getAdminAnalyses, getAdminAnalysisDetail, regenerateAnalysis } from '../../api/benchmark';
import type { BenchmarkConfig, BenchmarkAnalysis } from '../../types/benchmark';

export default function BenchmarkConfigPage() {
  const [configs, setConfigs] = useState<BenchmarkConfig[]>([]);
  const [analyses, setAnalyses] = useState<BenchmarkAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Config form state
  const [systemPrompt, setSystemPrompt] = useState('');
  const [aiModelId, setAiModelId] = useState<number | null>(null);
  const [isActive, setIsActive] = useState(true);

  // Detail drawer
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailData, setDetailData] = useState<BenchmarkAnalysis | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [cfg, ana] = await Promise.all([getAdminConfigs(), getAdminAnalyses()]);
      setConfigs(cfg);
      setAnalyses(ana);
      if (cfg.length > 0) {
        const c = cfg[0];
        setSystemPrompt(c.system_prompt || '');
        setAiModelId(c.ai_model_id);
        setIsActive(c.is_active);
      }
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateAdminConfig('analyze', {
        ai_model_id: aiModelId ?? undefined,
        system_prompt: systemPrompt,
        is_active: isActive,
      });
      message.success('配置已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

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
      title: '确认重新生成',
      content: '将清空已有结果，运营需重新触发分析。',
      onOk: async () => {
        try {
          await regenerateAnalysis(id);
          message.success('已重置，请运营重新触发分析');
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
    return (
      <span style={{ fontSize: 12, color: s.color, background: `${s.color}11`, padding: '2px 8px', borderRadius: 4 }}>
        {s.label}
      </span>
    );
  };

  if (loading) {
    return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>;
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">对标分析配置</h1>
          <p className="page-desc">管理对标分析助手的 AI Prompt 和模型</p>
        </div>
      </div>

      {/* Config Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>AI 配置</h3>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, display: 'block' }}>功能开关</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            启用对标分析功能
          </label>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, display: 'block' }}>System Prompt</label>
          <textarea
            className="input"
            style={{ width: '100%', minHeight: 400, fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6 }}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="输入 System Prompt..."
          />
        </div>

        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存配置'}
        </button>
      </div>

      {/* Analyses Table */}
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>分析记录</h3>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>账号名</th>
              <th>模型</th>
              <th>状态</th>
              <th>Token</th>
              <th>耗时</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {analyses.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--gray-400)', padding: 24 }}>暂无记录</td></tr>
            ) : (
              analyses.map((a) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Detail Drawer */}
      {detailVisible && detailData && (
        <div style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: 720,
          background: 'white', boxShadow: '-4px 0 24px rgba(0,0,0,0.1)',
          zIndex: 1000, display: 'flex', flexDirection: 'column',
        }}>
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
