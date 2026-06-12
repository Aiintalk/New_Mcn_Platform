import { useState, useRef, useEffect } from 'react';
import { App } from 'antd';
import { fetchAccount, analyzeStream, getMyHistory, getHistoryDetail } from '../../api/benchmark';
import type { BenchmarkAnalysis } from '../../types/benchmark';

type Step = 'input' | 'result';
type Tab = 'profile' | 'plan';

export default function BenchmarkPage() {
  const { message } = App.useApp();
  // Input state
  const [accountUrl, setAccountUrl] = useState('');
  const [top10Content, setTop10Content] = useState('');
  const [recent30Content, setRecent30Content] = useState('');
  const [accountName, setAccountName] = useState('');

  // Fetch state
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<{ total: number; top10: number; recent30: number } | null>(null);

  // Analysis state
  const [step, setStep] = useState<Step>('input');
  const [activeTab, setActiveTab] = useState<Tab>('profile');
  const [profileResult, setProfileResult] = useState('');
  const [planResult, setPlanResult] = useState('');
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const [currentAnalysisId, setCurrentAnalysisId] = useState<number | null>(null);

  // History
  const [history, setHistory] = useState<BenchmarkAnalysis[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const data = await getMyHistory();
      setHistory(data);
    } catch {
      // silent
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleFetch = async () => {
    if (!accountUrl.trim()) return;
    setFetching(true);
    setFetchResult(null);
    try {
      const data = await fetchAccount(accountUrl);
      setTop10Content(data.top10_text);
      setRecent30Content(data.recent30_text);
      if (data.nickname) setAccountName(data.nickname);
      setFetchResult({ total: data.total_videos, top10: data.top10_count, recent30: data.recent30_count });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '抓取失败';
      message.error(msg);
    } finally {
      setFetching(false);
    }
  };

  const handleAnalyze = async () => {
    if (!top10Content.trim() && !recent30Content.trim()) {
      message.warning('请至少填写一组内容数据');
      return;
    }

    setLoading(true);
    setProfileResult('');
    setPlanResult('');
    setStep('result');
    setActiveTab('profile');
    abortRef.current = new AbortController();

    try {
      const res = await analyzeStream({
        account_name: accountName,
        top10_content: top10Content,
        recent30_content: recent30Content,
      });

      const analysisId = res.headers.get('X-Analysis-Id');
      if (analysisId) setCurrentAnalysisId(Number(analysisId));

      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
        const parts = fullText.split('===SPLIT===');
        setProfileResult(parts[0].trim());
        if (parts.length > 1) {
          setPlanResult(parts[1].trim());
        }
      }

      loadHistory();
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        message.error('分析出错，请重试');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLoadHistory = async (id: number) => {
    try {
      const data = await getHistoryDetail(id);
      setAccountName(data.account_name || '');
      setTop10Content(data.top10_content || '');
      setRecent30Content(data.recent30_content || '');
      setProfileResult(data.profile_result || '');
      setPlanResult(data.plan_result || '');
      setCurrentAnalysisId(data.id);
      setStep('result');
      setActiveTab('profile');
    } catch {
      message.error('加载失败');
    }
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setStep('input');
    setProfileResult('');
    setPlanResult('');
    setLoading(false);
    setCurrentAnalysisId(null);
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制');
  };

  const handleExportWord = async (type: 'profile' | 'plan') => {
    if (!currentAnalysisId) return;
    try {
      const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
      const token = (await import('../../store/authStore')).useAuthStore.getState().token;
      const res = await fetch(`${BASE_URL}/api/operator/benchmark/export-word`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ analysis_id: currentAnalysisId, type }),
      });
      if (!res.ok) {
        message.error('导出失败');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const label = type === 'profile' ? '人格档案' : '内容规划';
      a.download = `${label}_${accountName || '账号'}_${new Date().toISOString().slice(0, 10)}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      message.error('导出失败');
    }
  };

  const formatDate = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  if (step === 'result') {
    return (
      <>
        <div className="page-header">
          <div>
            <h1 className="page-title">对标分析助手</h1>
            <p className="page-desc">{accountName || '分析结果'}</p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-primary"
              onClick={() => handleExportWord('profile')}
              disabled={!profileResult || loading}
            >
              导出人格档案
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleExportWord('plan')}
              disabled={!planResult || loading}
            >
              导出内容规划
            </button>
            <button className="btn btn-ghost" onClick={handleReset}>← 返回</button>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', borderBottom: '1px solid var(--gray-200)' }}>
            <button
              style={{
                flex: 1, padding: '12px 0', fontSize: 14, fontWeight: 500,
                background: activeTab === 'profile' ? 'var(--primary-50)' : 'transparent',
                color: activeTab === 'profile' ? 'var(--primary-600)' : 'var(--gray-500)',
                borderTop: 'none', borderLeft: 'none', borderRight: 'none',
                borderBottom: activeTab === 'profile' ? '2px solid var(--primary-600)' : '2px solid transparent',
                cursor: 'pointer',
              }}
              onClick={() => setActiveTab('profile')}
            >
              人格档案
            </button>
            <button
              style={{
                flex: 1, padding: '12px 0', fontSize: 14, fontWeight: 500,
                background: activeTab === 'plan' ? 'var(--primary-50)' : 'transparent',
                color: activeTab === 'plan' ? 'var(--primary-600)' : 'var(--gray-500)',
                borderTop: 'none', borderLeft: 'none', borderRight: 'none',
                borderBottom: activeTab === 'plan' ? '2px solid var(--primary-600)' : '2px solid transparent',
                cursor: 'pointer',
              }}
              onClick={() => setActiveTab('plan')}
            >
              内容规划
            </button>
          </div>

          <div style={{ padding: 24, position: 'relative' }}>
            {loading && !profileResult && !planResult ? (
              <div style={{ textAlign: 'center', padding: '64px 0' }}>
                <div className="spinner" style={{ marginBottom: 12 }} />
                <p style={{ color: 'var(--gray-500)', fontSize: 14 }}>正在分析账号内容，预计 1-2 分钟...</p>
              </div>
            ) : (
              <>
                <pre style={{
                  whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14,
                  lineHeight: 1.8, color: 'var(--gray-800)', margin: 0,
                }}>
                  {activeTab === 'profile'
                    ? (profileResult || '等待生成...')
                    : (planResult || (loading ? '人格档案生成中，内容规划稍后输出...' : '等待生成...'))
                  }
                </pre>
                {((activeTab === 'profile' && profileResult) || (activeTab === 'plan' && planResult)) && (
                  <button
                    style={{
                      position: 'absolute', top: 12, right: 12, fontSize: 12,
                      color: 'var(--primary-600)', background: 'var(--primary-50)', border: '1px solid var(--primary-200)',
                      borderRadius: 4, padding: '2px 8px', cursor: 'pointer',
                    }}
                    onClick={() => handleCopy(activeTab === 'profile' ? profileResult : planResult)}
                  >
                    复制
                  </button>
                )}
              </>
            )}
            {loading && (profileResult || planResult) && (
              <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--primary-500)' }}>
                <div className="spinner-sm" />
                生成中...
              </div>
            )}
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">对标分析助手</h1>
          <p className="page-desc">系统化拆解对标账号，输出人格档案与内容规划</p>
        </div>
      </div>

      {/* History */}
      {history.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>已分析的对标账号</span>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>共 {history.length} 个</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
            {history.map((item) => (
              <div
                key={item.id}
                className="card"
                style={{ padding: 12, cursor: 'pointer', border: '1px solid var(--gray-200)' }}
                onClick={() => handleLoadHistory(item.id)}
              >
                <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.account_name || '未命名'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 4 }}>
                  {item.status === 'completed' ? '已完成' : item.status === 'failed' ? '失败' : item.status}
                </div>
                <div style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 2 }}>
                  {formatDate(item.created_at)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {historyLoading && history.length === 0 && (
        <div style={{ textAlign: 'center', padding: 16, fontSize: 12, color: 'var(--gray-400)' }}>加载历史记录...</div>
      )}

      {/* Fetch Section */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>获取对标账号数据</h3>
        <p style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 12 }}>输入抖音号或主页链接，自动抓取全部作品</p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            value={accountUrl}
            onChange={(e) => setAccountUrl(e.target.value)}
            placeholder="输入抖音号（如 DNX833）或粘贴主页链接..."
            onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
          />
          <button className="btn btn-primary" onClick={handleFetch} disabled={fetching || !accountUrl.trim()}>
            {fetching ? '抓取中...' : '解析'}
          </button>
        </div>
        {fetchResult && (
          <div style={{ marginTop: 12, padding: '8px 12px', background: 'var(--success-50)', border: '1px solid var(--success-200)', borderRadius: 6, fontSize: 12, color: 'var(--success-700)' }}>
            抓取成功！共 {fetchResult.total} 条作品，TOP10 已选出 {fetchResult.top10} 条，最近30天 {fetchResult.recent30} 条
          </div>
        )}
      </div>

      {/* Account Name */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>账号名称（可选）</h3>
        <input
          className="input"
          style={{ width: '100%' }}
          value={accountName}
          onChange={(e) => setAccountName(e.target.value)}
          placeholder="输入对标账号名称"
        />
      </div>

      {/* TOP10 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 600 }}>数据一：全账号点赞 TOP10</h3>
            <p style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 2 }}>整个账号按点赞量排序最高的10条视频文案</p>
          </div>
          {top10Content && <span style={{ fontSize: 11, color: 'var(--success-600)', background: 'var(--success-50)', padding: '2px 8px', borderRadius: 4 }}>已填充</span>}
        </div>
        <textarea
          className="input"
          style={{ width: '100%', minHeight: 160, resize: 'vertical' }}
          value={top10Content}
          onChange={(e) => setTop10Content(e.target.value)}
          placeholder="自动抓取后会自动填充，也可以手动粘贴..."
        />
        {top10Content && <p style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 4 }}>已输入 {top10Content.length} 字</p>}
      </div>

      {/* Recent 30 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 600 }}>数据二：最近30天全部内容</h3>
            <p style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 2 }}>最近一个月内发布的所有视频文案</p>
          </div>
          {recent30Content && <span style={{ fontSize: 11, color: 'var(--success-600)', background: 'var(--success-50)', padding: '2px 8px', borderRadius: 4 }}>已填充</span>}
        </div>
        <textarea
          className="input"
          style={{ width: '100%', minHeight: 160, resize: 'vertical' }}
          value={recent30Content}
          onChange={(e) => setRecent30Content(e.target.value)}
          placeholder="自动抓取后会自动填充，也可以手动粘贴..."
        />
        {recent30Content && <p style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 4 }}>已输入 {recent30Content.length} 字</p>}
      </div>

      {/* Analyze Button */}
      <button
        className="btn btn-primary"
        style={{ width: '100%', padding: '12px 0', fontSize: 14 }}
        onClick={handleAnalyze}
        disabled={!top10Content.trim() && !recent30Content.trim()}
      >
        开始分析
      </button>
    </>
  );
}
