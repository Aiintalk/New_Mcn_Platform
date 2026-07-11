/**
 * 人设脚本仿写页面（persona-writer）
 *
 * 3 步工作流：
 *   Step 1 · 加载风格   — 下拉选达人 + 预览 content_plan 前 8 行
 *   Step 2 · 对标验证   — 抖音链接解析 + 点赞门槛 + 文案粘贴 + AI 评估 + 用户同意
 *   Step 3 · 仿写创作   — 结构拆解 + 双选题 + 写作 + 多轮追问 + 终稿编辑 + 导出
 *
 * 业务铁律：3 步业务逻辑 100% 忠实旧版（决策 #1 全保留）。
 * 点赞门槛 digg_count >= 100000 硬编码（决策 #5）。
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Input, Select, Steps, Radio, App } from 'antd';
import {
  SaveOutlined,
  FileTextOutlined,
  FileWordOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  getPersonas,
  fetchVideo,
  evaluateOpeningStream,
  analyzeStructureStream,
  chatStream,
  saveOutput,
  exportWord,
} from '../../api/personaWriter';
import type {
  PersonaWriterPersona,
  PersonaChatMessage,
} from '../../types/personaWriter';

const { TextArea } = Input;

/** 点赞门槛（业务铁律，硬编码） */
const LIKES_THRESHOLD = 100000;

/** 对标原文展示前 N 句（用于终稿编辑提示） */
const TRANSCRIPT_PREVIEW_SENTENCES = 3;

interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

function charCount(text: string): number {
  return text.replace(/\s/g, '').length;
}

/** 把 content_plan 字符串按换行切，取前 8 行 */
function previewContentPlan(plan: string): string {
  const lines = plan.split(/\r?\n/).slice(0, 8).join('\n');
  return lines;
}

/** 取对标原文前 N 句（用于终稿编辑提示） */
function firstSentences(text: string, n: number): string {
  const parts = text
    .split(/[。！？!?\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, n);
  return parts.join('。') + (parts.length > 0 ? '。' : '');
}

function downloadBlob(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── 内部实现（共享逻辑）──────────────────────────────────────────────────────
function PersonaWriterInner({ initKolId }: { initKolId?: number }) {
  const { message } = App.useApp();
  const isModule = initKolId !== undefined;
  const [currentStep, setCurrentStep] = useState(isModule ? 2 : 1);

  // Step 1
  const [personas, setPersonas] = useState<PersonaWriterPersona[]>([]);
  const [personasLoading, setPersonasLoading] = useState(false);
  const [selectedPersona, setSelectedPersona] = useState<PersonaWriterPersona | null>(null);
  /** content_plan 预览（达人选中后从 soul_preview 近似推导，实际靠后端返回的 soul） */
  const [contentPlanPreview, setContentPlanPreview] = useState('');

  // Step 2
  const [shareUrl, setShareUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState<{
    title: string;
    digg_count: number;
    aweme_id: string;
    play_url: string;
    likes_pass: boolean;
  } | null>(null);
  const [fetchingVideo, setFetchingVideo] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [evaluationResult, setEvaluationResult] = useState('');
  const [evaluating, setEvaluating] = useState(false);
  const [userAgreeEvaluation, setUserAgreeEvaluation] = useState<boolean | null>(null);

  // Step 3
  const [structureAnalysis, setStructureAnalysis] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [topicMode, setTopicMode] = useState<'custom' | 'default'>('custom');
  const [topic, setTopic] = useState('');
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamDisplay, setStreamDisplay] = useState('');
  const [finalScript, setFinalScript] = useState('');
  const [pendingImageUrl, setPendingImageUrl] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Step 1: 加载达人列表
  const loadPersonas = useCallback(async () => {
    setPersonasLoading(true);
    try {
      const data = await getPersonas();
      setPersonas(data);
      // Module 模式：从列表中找到当前达人
      if (isModule && initKolId) {
        const found = data.find((p) => p.id === initKolId) ?? null;
        if (found) {
          setSelectedPersona(found);
          setContentPlanPreview(previewContentPlan(found.soul_preview));
        }
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载达人列表失败');
    } finally {
      setPersonasLoading(false);
    }
  }, [message, isModule, initKolId]);

  useEffect(() => {
    loadPersonas();
  }, [loadPersonas]);

  // 自动滚动到聊天底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatTurns, streamDisplay]);

  // Step 2: 抖音链接解析
  async function handleFetchVideo(): Promise<void> {
    if (!shareUrl.trim()) return;
    setFetchingVideo(true);
    setVideoInfo(null);
    setUserAgreeEvaluation(null);
    try {
      const result = await fetchVideo(shareUrl.trim());
      setVideoInfo(result);
      if (!result.likes_pass) {
        message.warning(`点赞 ${result.digg_count} 未达 ${LIKES_THRESHOLD.toLocaleString()} 门槛，请换点赞更高的对标`);
      } else {
        message.success(`解析成功：${result.title}（${result.digg_count.toLocaleString()} 赞）`);
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '抖音链接解析失败');
    } finally {
      setFetchingVideo(false);
    }
  }

  // Step 2.4: AI 开头评估
  async function handleEvaluate(): Promise<void> {
    if (!transcript.trim()) return;
    setEvaluating(true);
    setEvaluationResult('');
    try {
      const full = await evaluateOpeningStream(transcript, (text) => {
        setEvaluationResult(text);
      });
      setEvaluationResult(full);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'AI 评估失败');
    } finally {
      setEvaluating(false);
    }
  }

  // 质量门判定：点赞✅ + 评估✅（含"通过"且不含"不通过"） + 用户同意
  const likesOk = videoInfo?.likes_pass === true;
  const evaluationPassed: boolean =
    evaluationResult.length > 0 &&
    evaluationResult.includes('通过') &&
    !evaluationResult.includes('不通过');
  const qualityGateOk: boolean =
    likesOk && evaluationPassed && userAgreeEvaluation === true;

  // Step 3.1: AI 结构拆解
  async function handleAnalyze(): Promise<void> {
    if (!transcript.trim()) return;
    setAnalyzing(true);
    setStructureAnalysis('');
    try {
      const full = await analyzeStructureStream(transcript, (text) => {
        setStructureAnalysis(text);
      });
      setStructureAnalysis(full);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '结构拆解失败');
    } finally {
      setAnalyzing(false);
    }
  }

  // Step 3.3: AI 写作
  async function handleWriting(): Promise<void> {
    if (!selectedPersona) return;
    if (topicMode === 'custom' && !topic.trim()) {
      message.warning('请输入选题想法');
      return;
    }
    if (!structureAnalysis.trim()) {
      message.warning('请先完成结构拆解');
      return;
    }
    setStreaming(true);
    setStreamDisplay('');

    const userMsg = '请按照规则生成人设脚本。';
    const newTurns: ChatTurn[] = [{ role: 'user', content: userMsg }];
    setChatTurns(newTurns);

    try {
      const apiMessages: PersonaChatMessage[] = [{ role: 'user', content: userMsg }];
      const full = await chatStream(
        {
          scene: 'writing',
          topic_mode: topicMode,
          persona_id: selectedPersona.id,
          transcript,
          structure_analysis: structureAnalysis,
          topic: topicMode === 'custom' ? topic.trim() : '',
          messages: apiMessages,
          create_job: true,
        },
        (text) => setStreamDisplay(text),
      );
      setChatTurns([...newTurns, { role: 'assistant', content: full }]);
      setFinalScript(full);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `写作失败：${err.message}` : '写作失败');
    } finally {
      setStreaming(false);
    }
  }

  // Step 3.4: 多轮追问
  async function handleSendChat(): Promise<void> {
    if (!chatInput.trim() || !selectedPersona || streaming) return;
    const userText = chatInput.trim();
    const userMsg: ChatTurn = { role: 'user', content: userText };
    const newTurns = [...chatTurns, userMsg];
    setChatTurns(newTurns);
    setChatInput('');
    setStreaming(true);
    setStreamDisplay('');

    try {
      // 构造 messages（含可能的图片）
      const apiMessages: PersonaChatMessage[] = newTurns.map((t) => {
        if (t.role === 'user' && pendingImageUrl) {
          return {
            role: 'user',
            content: [
              { type: 'text', text: t.content },
              { type: 'image_url', image_url: { url: pendingImageUrl } },
            ],
          };
        }
        return { role: t.role, content: t.content };
      });
      setPendingImageUrl(null);

      const full = await chatStream(
        {
          scene: 'iteration',
          persona_id: selectedPersona.id,
          transcript,
          structure_analysis: structureAnalysis,
          topic: topicMode === 'custom' ? topic : '',
          messages: apiMessages,
        },
        (text) => setStreamDisplay(text),
      );
      setChatTurns([...newTurns, { role: 'assistant', content: full }]);
      setFinalScript(full);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `追问失败：${err.message}` : '追问失败');
    } finally {
      setStreaming(false);
    }
  }

  // Step 3.4: 图片上传（复用通用 /api/files）
  async function handleImageUpload(file: File): Promise<void> {
    try {
      const { useAuthStore } = await import('../../store/authStore');
      const token = useAuthStore.getState().token;
      const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch(`${BASE_URL}/api/files`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      });
      if (!resp.ok) throw new Error(`上传失败: ${resp.status}`);
      const body = await resp.json();
      if (!body.success) throw new Error(body.message ?? '上传失败');
      const url: string = body.data?.url ?? body.data ?? '';
      setPendingImageUrl(url);
      message.success('图片已上传，发送追问时将附带');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '图片上传失败');
    }
  }

  // Step 3.5: 保存历史
  async function handleSave(): Promise<void> {
    if (!finalScript || !selectedPersona) return;
    try {
      const title = `人设脚本_${selectedPersona.name}_${topic || '终稿'}`;
      await saveOutput({
        title,
        content: finalScript,
        topic: topic || null,
        transcript_digest: firstSentences(transcript, TRANSCRIPT_PREVIEW_SENTENCES),
      });
      message.success('已保存到历史记录');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  // Step 3.6a: 导出 .txt
  function handleExportTxt(): void {
    if (!finalScript || !selectedPersona) return;
    const filename = `人设脚本_${selectedPersona.name}_${topic || '终稿'}.txt`;
    downloadBlob(finalScript, filename, 'text/plain;charset=utf-8');
    message.success('终稿 .txt 已下载');
  }

  // Step 3.6b: 导出 .docx
  async function handleExportDocx(): Promise<void> {
    if (!finalScript || !selectedPersona) return;
    try {
      const filename = `人设脚本_${selectedPersona.name}_${topic || '终稿'}`;
      const blob = await exportWord({ content: finalScript, filename });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${filename}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('终稿 .docx 已下载');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '导出失败');
    }
  }

  const step1Ok = selectedPersona !== null;
  const step2VideoFetched = videoInfo !== null;
  const step2TranscriptOk = transcript.trim().length > 0;
  const step2EvaluationOk = evaluationResult.length > 0;
  const hasResult = chatTurns.some((m) => m.role === 'assistant');
  const referenceOpening = firstSentences(transcript, TRANSCRIPT_PREVIEW_SENTENCES);

  return (
    <div
      className={isModule ? 'workspace-tool-module' : undefined}
      style={isModule ? undefined : { maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}
    >
      <div className="page-header">
        <div>
          <h1 className="page-title">人设脚本仿写</h1>
          <p className="page-desc">{isModule ? '对标验证 · 仿写创作' : '加载风格 · 对标验证 · 仿写创作'}</p>
        </div>
      </div>

      <Steps
        current={isModule ? currentStep - 2 : currentStep - 1}
        items={isModule
          ? [{ title: '对标验证' }, { title: '仿写创作' }]
          : [{ title: '加载风格' }, { title: '对标验证' }, { title: '仿写创作' }]
        }
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 1 · 加载风格（仅独立页面模式） */}
      {!isModule && currentStep >= 1 && (
        <div className="card workspace-step-card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 1 · 选择达人</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>达人人设</label>
            <Select
              style={{ width: '100%' }}
              placeholder="请选择达人..."
              loading={personasLoading}
              value={selectedPersona?.id || undefined}
              onChange={(val) => {
                const p = personas.find((p) => p.id === val) ?? null;
                setSelectedPersona(p);
                // soul_preview 实际上是 persona 字段的前 400 字，这里近似作为 content_plan 预览
                // 真实 content_plan 从后端 chat 接口在后端读取，前端仅做展示预览
                if (p) {
                  setContentPlanPreview(previewContentPlan(p.soul_preview));
                } else {
                  setContentPlanPreview('');
                }
              }}
              options={personas.map((p) => ({
                value: p.id,
                label: `${p.name}（${p.creator_name}）`,
              }))}
            />
          </div>
          {selectedPersona && (
            <div
              style={{
                background: 'var(--gray-50)',
                padding: 'var(--sp-3)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--sp-2)' }}>
                人物档案预览（前 8 行）
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--gray-700)',
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                  maxHeight: 160,
                  overflow: 'hidden',
                }}
              >
                {contentPlanPreview || selectedPersona.soul_preview.slice(0, 400)}
              </div>
            </div>
          )}
          {currentStep === 1 && (
            <Button type="primary" disabled={!step1Ok} onClick={() => setCurrentStep(2)}>
              下一步：对标验证 →
            </Button>
          )}
        </div>
      )}

      {/* Step 2 · 对标验证 */}
      {currentStep >= 2 && (
        <div className="card workspace-step-card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · 对标验证</h3>

          {/* 2.1 粘贴抖音链接 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              2.1 抖音分享链接
            </label>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Input
                placeholder="粘贴抖音分享链接（含短链和分享文本）..."
                value={shareUrl}
                onChange={(e) => setShareUrl(e.target.value)}
                onPressEnter={handleFetchVideo}
              />
              <Button
                onClick={handleFetchVideo}
                loading={fetchingVideo}
                disabled={!shareUrl.trim()}
              >
                解析
              </Button>
            </div>
          </div>

          {/* 2.2 点赞门槛 */}
          {videoInfo && (
            <div
              style={{
                background: 'var(--gray-50)',
                padding: 'var(--sp-3)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              <div style={{ fontSize: 13, marginBottom: 'var(--sp-1)' }}>
                <strong>视频标题：</strong>{videoInfo.title}
              </div>
              <div style={{ fontSize: 13 }}>
                <strong>点赞数：</strong>
                <span style={{ fontWeight: 600, color: likesOk ? 'var(--success)' : 'var(--danger)' }}>
                  {videoInfo.digg_count.toLocaleString()}
                </span>
                <span style={{ marginLeft: 'var(--sp-2)' }}>
                  {likesOk ? '✅ 达标（≥100,000）' : `❌ 未达 ${LIKES_THRESHOLD.toLocaleString()} 门槛`}
                </span>
              </div>
            </div>
          )}

          {/* 2.3 粘贴文案 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              2.3 对标视频口播文案
            </label>
            <TextArea
              rows={6}
              placeholder="粘贴对标视频的口播文案（外部工具如 AI 好记转好）..."
              value={transcript}
              onChange={(e) => {
                setTranscript(e.target.value);
                setEvaluationResult('');
                setUserAgreeEvaluation(null);
              }}
            />
            {transcript.trim() && (
              <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--gray-400)', marginTop: 'var(--sp-1)' }}>
                {charCount(transcript)} 字
              </div>
            )}
          </div>

          {/* 2.4 AI 开头评估 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <label style={{ fontWeight: 500 }}>2.4 AI 开头评估</label>
              <Button
                size="small"
                onClick={handleEvaluate}
                loading={evaluating}
                disabled={!step2TranscriptOk}
              >
                开始评估
              </Button>
            </div>
            {evaluationResult && (
              <div
                style={{
                  background: 'var(--gray-50)',
                  padding: 'var(--sp-3)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                  maxHeight: 200,
                  overflowY: 'auto',
                }}
              >
                {evaluationResult}
              </div>
            )}
          </div>

          {/* 2.5 用户同意判定 */}
          {step2EvaluationOk && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                2.5 您是否同意此评估结论？
              </label>
              <Radio.Group
                value={userAgreeEvaluation}
                onChange={(e) => setUserAgreeEvaluation(e.target.value)}
              >
                <Radio.Button value={true}>同意，进入仿写</Radio.Button>
                <Radio.Button value={false}>不同意，留在本步</Radio.Button>
              </Radio.Group>
            </div>
          )}

          {/* 质量门状态 */}
          {step2VideoFetched && step2EvaluationOk && userAgreeEvaluation !== null && (
            <div
              style={{
                fontSize: 13,
                padding: 'var(--sp-2) var(--sp-3)',
                borderRadius: 'var(--radius-md)',
                background: qualityGateOk ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                color: qualityGateOk ? 'var(--success)' : 'var(--danger)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              质量门：点赞{likesOk ? '✅' : '❌'} · 评估{evaluationPassed ? '✅' : '❌'} ·
              同意{userAgreeEvaluation === true ? '✅' : '❌'}
              {qualityGateOk ? ' → 可进入仿写' : ' → 请解决后继续'}
            </div>
          )}

          {currentStep === 2 && (
            <Button
              type="primary"
              disabled={!qualityGateOk}
              onClick={() => setCurrentStep(3)}
            >
              下一步：仿写创作 →
            </Button>
          )}
        </div>
      )}

      {/* Step 3 · 仿写创作 */}
      {currentStep >= 3 && (
        <div className="card workspace-step-card">
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · 仿写创作</h3>

          {/* 3.1 AI 结构拆解 */}
          <div style={{ marginBottom: 'var(--sp-4)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
              <label style={{ fontWeight: 500 }}>3.1 AI 对标结构拆解</label>
              <Button
                size="small"
                onClick={handleAnalyze}
                loading={analyzing}
              >
                {structureAnalysis ? '重新拆解' : '开始拆解'}
              </Button>
            </div>
            {structureAnalysis && (
              <div
                style={{
                  background: 'var(--gray-50)',
                  padding: 'var(--sp-3)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                  maxHeight: 240,
                  overflowY: 'auto',
                }}
              >
                {structureAnalysis}
              </div>
            )}
          </div>

          {/* 3.2 双选题 */}
          <div style={{ marginBottom: 'var(--sp-4)' }}>
            <label style={{ display: 'block', marginBottom: 'var(--sp-2)', fontWeight: 500 }}>
              3.2 选题方向
            </label>
            <Radio.Group
              value={topicMode}
              onChange={(e) => setTopicMode(e.target.value)}
              style={{ marginBottom: 'var(--sp-2)' }}
            >
              <Radio.Button value="custom">💡 我有想法</Radio.Button>
              <Radio.Button value="default">🤖 我没想法</Radio.Button>
            </Radio.Group>
            {topicMode === 'custom' && (
              <TextArea
                rows={3}
                placeholder="请输入您的选题想法（必填）..."
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            )}
            {topicMode === 'default' && (
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--gray-500)',
                  background: 'var(--gray-50)',
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                系统将基于对标原文结构 + 人格档案自动生成默认选题
              </div>
            )}
          </div>

          {/* 3.3 写作按钮 */}
          <div style={{ marginBottom: 'var(--sp-4)' }}>
            <Button
              type="primary"
              onClick={handleWriting}
              loading={streaming && chatTurns.length === 0}
              disabled={
                streaming ||
                !structureAnalysis.trim() ||
                (topicMode === 'custom' && !topic.trim())
              }
            >
              {hasResult ? '重新生成脚本' : '3.3 生成人设脚本'}
            </Button>
          </div>

          {/* 3.3/3.4 消息列表 + 追问 */}
          {(hasResult || (streaming && streamDisplay)) && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <div
                style={{
                  maxHeight: '50vh',
                  overflowY: 'auto',
                  padding: 'var(--sp-3)',
                  background: 'var(--gray-50)',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: 'var(--sp-3)',
                }}
              >
                {chatTurns.map((msg, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                      marginBottom: 'var(--sp-2)',
                    }}
                  >
                    <div
                      style={{
                        maxWidth: '90%',
                        padding: 'var(--sp-2) var(--sp-3)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 13,
                        whiteSpace: 'pre-wrap',
                        lineHeight: 1.6,
                        background: msg.role === 'user' ? 'var(--brand)' : 'var(--bg-card)',
                        color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                        border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
                {streaming && streamDisplay && (
                  <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 'var(--sp-2)' }}>
                    <div
                      style={{
                        maxWidth: '90%',
                        padding: 'var(--sp-2) var(--sp-3)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 13,
                        whiteSpace: 'pre-wrap',
                        lineHeight: 1.6,
                        background: 'var(--bg-card)',
                        color: 'var(--gray-800)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {streamDisplay}
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* 3.4 多轮追问 */}
              {hasResult && !streaming && (
                <div style={{ marginBottom: 'var(--sp-2)' }}>
                  <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)' }}>
                    <Input
                      placeholder="告诉 AI 哪里需要调整（可上传图片）..."
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onPressEnter={handleSendChat}
                    />
                    <label className="btn btn-ghost" style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
                      <UploadOutlined />
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: 'none' }}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) handleImageUpload(f);
                        }}
                      />
                    </label>
                    <Button onClick={handleSendChat} disabled={!chatInput.trim()}>
                      发送
                    </Button>
                  </div>
                  {pendingImageUrl && (
                    <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 'var(--sp-1)' }}>
                      ✅ 已附图，发送追问时将携带
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 3.5 终稿编辑 */}
          {hasResult && !streaming && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                3.5 终稿编辑
              </label>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--gray-500)',
                  background: 'rgba(250,204,21,0.1)',
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                💡 提示：建议手动复制对标原文前 2-3 句，粘贴替换本脚本开头，确保吸引力对齐。
              </div>
              {referenceOpening && (
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--gray-400)',
                    background: 'var(--gray-50)',
                    padding: 'var(--sp-2)',
                    borderRadius: 'var(--radius-sm)',
                    marginBottom: 'var(--sp-2)',
                    fontStyle: 'italic',
                  }}
                >
                  对标原文开头（可复制）：{referenceOpening}
                </div>
              )}
              <TextArea
                rows={12}
                value={finalScript}
                onChange={(e) => setFinalScript(e.target.value)}
              />
              {finalScript.trim() && (
                <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--gray-400)', marginTop: 'var(--sp-1)' }}>
                  {charCount(finalScript)} 字
                </div>
              )}
            </div>
          )}

          {/* 3.6 动作按钮 */}
          {hasResult && !streaming && (
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Button icon={<SaveOutlined />} onClick={handleSave}>
                保存到历史
              </Button>
              <Button icon={<FileTextOutlined />} onClick={handleExportTxt}>
                导出 .txt
              </Button>
              <Button type="primary" icon={<FileWordOutlined />} onClick={handleExportDocx}>
                导出 .docx
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 核心 Module（接受外部 kolId，跳过 Step 1 选达人）───────────────────────
export function PersonaWriterModule({ kolId }: { kolId: number }) {
  return <PersonaWriterInner initKolId={kolId} />;
}

// ── 独立页面（保留完整 Step 1 选达人流程）────────────────────────────────────
export default function PersonaWriterPage() {
  return <PersonaWriterInner />;
}
