/**
 * 种草内容仿写页面（seeding-writer）
 *
 * 4 步工作流：
 *   Step 1 · 选达人 + 素材库   — 下拉选达人 + 素材库管理（粘贴文本 / 抖音链接导入 / 删除）
 *   Step 2 · 产品信息          — 产品库选择/新建 + 文档上传 AI 解析 + AI 卖点讨论 + 6 字段表单
 *   Step 3 · 对标验证          — 抖音链接解析 + ASR submit/poll 轮询 + 文案确认 + 结构拆解流式
 *   Step 4 · 种草仿写          — 3 种选题 + AI 写作流式 + 字数校验 + 多轮迭代 + 保存 + 导出
 *
 * 业务铁律：4 步业务逻辑 100% 忠实旧版。
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
  getReferences,
  createReference,
  importReferenceFromDouyin,
  deleteReference,
  getProducts,
  createProduct,
  parseProductDocument,
  extractSellingPointsStream,
  fetchVideo,
  submitTranscribe,
  pollTranscribe,
  analyzeStructureStream,
  aiRecommendStream,
  chatStream,
  saveOutput,
  exportWord,
} from '../../api/seedingWriter';
import type {
  PersonaOption,
  Reference,
  Product,
  ProductInfo,
  ChatMsg,
} from '../../types/seedingWriter';

const { TextArea } = Input;

/** ASR 轮询参数 */
const ASR_MAX_ATTEMPTS = 60;
const ASR_POLL_INTERVAL = 5000;

/** 空产品信息 */
const emptyProduct: ProductInfo = {
  name: '',
  category: '',
  price: '',
  targetAudience: '',
  sellingPoints: '',
  scenario: '',
  medicalAestheticAnchor: '',
};

/** 把 content_plan 字符串按换行切，取前 8 行 */
function previewContentPlan(plan: string): string {
  return plan.split(/\r?\n/).slice(0, 8).join('\n');
}

function charCount(text: string): number {
  return text.replace(/\s/g, '').length;
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

export default function SeedingWriterPage() {
  const { message } = App.useApp();
  const [step, setStep] = useState(1);

  // Step 1
  const [personas, setPersonas] = useState<PersonaOption[]>([]);
  const [personasLoading, setPersonasLoading] = useState(false);
  const [selectedPersonaId, setSelectedPersonaId] = useState<number | null>(null);
  const [selectedPersona, setSelectedPersona] = useState<PersonaOption | null>(null);
  const [references, setReferences] = useState<Reference[]>([]);
  const [showRefForm, setShowRefForm] = useState(false);
  const [refType, setRefType] = useState('种草爆款');
  const [refTitle, setRefTitle] = useState('');
  const [refContent, setRefContent] = useState('');
  const [refLikes, setRefLikes] = useState('');
  const [showImportDouyin, setShowImportDouyin] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [importType, setImportType] = useState('种草爆款');

  // Step 2
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [product, setProduct] = useState<ProductInfo>(emptyProduct);
  const [spChat, setSpChat] = useState<ChatMsg[]>([]);
  const [spInput, setSpInput] = useState('');
  const [spApplied, setSpApplied] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [spStreaming, setSpStreaming] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 3
  const [shareUrl, setShareUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState<{
    title: string;
    digg_count: number;
    aweme_id: string;
    play_url: string;
  } | null>(null);
  const [transcript, setTranscript] = useState('');
  const [transcriptConfirmed, setTranscriptConfirmed] = useState(false);
  const [asrTaskId, setAsrTaskId] = useState('');
  const [asrPolling, setAsrPolling] = useState(false);
  const [structureAnalysis, setStructureAnalysis] = useState('');
  const [analyzing, setAnalyzing] = useState(false);

  // Step 4
  const [topicMode, setTopicMode] = useState<'same' | 'custom' | 'ai' | null>(null);
  const [customTopic, setCustomTopic] = useState('');
  const [aiTopics, setAiTopics] = useState('');
  const [chosenTopic, setChosenTopic] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamDisplay, setStreamDisplay] = useState('');
  const [finalScript, setFinalScript] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Common
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');

  // ── Step 1: 加载达人列表 ──────────────────────────────────────────────────
  const loadPersonas = useCallback(async () => {
    setPersonasLoading(true);
    try {
      const data = await getPersonas();
      setPersonas(data);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载达人列表失败');
    } finally {
      setPersonasLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadPersonas();
  }, [loadPersonas]);

  // 加载素材库
  const loadReferences = useCallback(
    async (kolId: number) => {
      try {
        const data = await getReferences(kolId);
        setReferences(data);
      } catch (err: unknown) {
        message.error(err instanceof Error ? err.message : '加载素材库失败');
      }
    },
    [message],
  );

  // 达人选中后加载素材库
  useEffect(() => {
    if (selectedPersonaId) {
      loadReferences(selectedPersonaId);
    } else {
      setReferences([]);
    }
  }, [selectedPersonaId, loadReferences]);

  // 自动滚动到聊天底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, streamDisplay]);

  // ── Step 1: 素材库操作 ───────────────────────────────────────────────────
  async function handleAddReference(): Promise<void> {
    if (!selectedPersonaId || !refTitle.trim() || !refContent.trim()) {
      message.warning('请填写标题和正文');
      return;
    }
    try {
      await createReference({
        kol_id: selectedPersonaId,
        title: refTitle.trim(),
        content: refContent.trim(),
        type: refType,
        likes: refLikes ? parseInt(refLikes, 10) : undefined,
      });
      message.success('素材已保存');
      setRefTitle('');
      setRefContent('');
      setRefLikes('');
      setShowRefForm(false);
      loadReferences(selectedPersonaId);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存素材失败');
    }
  }

  async function handleImportDouyin(): Promise<void> {
    if (!selectedPersonaId || !importUrl.trim()) {
      message.warning('请粘贴抖音链接');
      return;
    }
    setLoading('正在从抖音导入，可能需要 5-10 分钟...');
    try {
      await importReferenceFromDouyin({
        kol_id: selectedPersonaId,
        share_url: importUrl.trim(),
        type: importType,
      });
      message.success('导入成功');
      setImportUrl('');
      setShowImportDouyin(false);
      loadReferences(selectedPersonaId);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '抖音导入失败');
    } finally {
      setLoading('');
    }
  }

  async function handleDeleteReference(id: number): Promise<void> {
    try {
      await deleteReference(id);
      message.success('已删除');
      if (selectedPersonaId) loadReferences(selectedPersonaId);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }

  // ── Step 2: 产品库操作 ───────────────────────────────────────────────────
  const loadProducts = useCallback(async () => {
    try {
      const data = await getProducts(1, 50);
      setProducts(data.items);
    } catch {
      // 静默失败，产品库可选
    }
  }, []);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  function handleSelectProduct(prodId: number): void {
    const p = products.find((p) => p.id === prodId);
    if (p) {
      setSelectedProductId(prodId);
      setProduct({
        name: p.name || '',
        category: p.category || '',
        price: p.price || '',
        targetAudience: p.target_audience || '',
        sellingPoints: p.selling_points || '',
        scenario: p.scenario || '',
        medicalAestheticAnchor: p.medical_aesthetic_anchor || '',
      });
      setSpApplied(true);
    }
  }

  // ── Step 2: 文档上传 AI 解析 ─────────────────────────────────────────────
  async function handleUploadProductDoc(
    e: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const fileArr = Array.from(files);
    setUploadingDoc(true);
    try {
      const parsed = await parseProductDocument(fileArr);
      setProduct({
        name: parsed.name || '',
        category: parsed.category || '',
        price: parsed.price || '',
        targetAudience: parsed.targetAudience || '',
        sellingPoints: parsed.sellingPoints || '',
        scenario: parsed.scenario || '',
        medicalAestheticAnchor: parsed.medicalAestheticAnchor || '',
      });
      message.success('文档解析完成');
      // 自动触发 AI 卖点讨论
      if (parsed._rawText) {
        startSellingPointsChat(parsed._rawText, {
          name: parsed.name || '',
          category: parsed.category || '',
          price: parsed.price || '',
          targetAudience: parsed.targetAudience || '',
          sellingPoints: parsed.sellingPoints || '',
          scenario: parsed.scenario || '',
          medicalAestheticAnchor: parsed.medicalAestheticAnchor || '',
        });
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '文档解析失败');
    } finally {
      setUploadingDoc(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  // ── Step 2: AI 卖点讨论（流式） ──────────────────────────────────────────
  async function startSellingPointsChat(rawText: string, info: ProductInfo): Promise<void> {
    const userContent = `以下是产品资料原文：\n\n${rawText.slice(0, 4000)}\n\nAI 初步提取的产品信息：\n产品名：${info.name}\n品类：${info.category}\n价格：${info.price}\n目标人群：${info.targetAudience}\n\n请站在消费者角度，帮我找出最能打动人购买的3个核心卖点。`;
    const msgs: ChatMsg[] = [{ role: 'user', content: userContent }];
    setSpChat(msgs);
    setSpApplied(false);
    setSpStreaming(true);

    try {
      await extractSellingPointsStream(
        { raw_text: rawText.slice(0, 4000), preliminary_info: info },
        (full: string) => {
          setSpChat([...msgs, { role: 'assistant', content: full }]);
        },
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '卖点讨论失败');
    } finally {
      setSpStreaming(false);
    }
  }

  async function handleSpSendChat(): Promise<void> {
    if (!spInput.trim() || spStreaming) return;
    const userMsg: ChatMsg = { role: 'user', content: spInput.trim() };
    const newMsgs = [...spChat, userMsg];
    setSpChat(newMsgs);
    setSpInput('');
    setSpStreaming(true);

    try {
      // 对于后续讨论，我们只需要把新消息追加上去
      const lastAssistant = [...spChat].reverse().find((m) => m.role === 'assistant');
      const rawText = lastAssistant?.content ?? '';
      await extractSellingPointsStream(
        { raw_text: rawText.slice(0, 4000), preliminary_info: product },
        (full: string) => {
          setSpChat([...newMsgs, { role: 'assistant', content: full }]);
        },
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '讨论失败');
    } finally {
      setSpStreaming(false);
    }
  }

  function handleApplySellingPoints(): void {
    const lastAssistant = [...spChat].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant) return;
    // 正则提取【最终卖点】
    const finalMatch = lastAssistant.content.match(/【最终卖点】([\s\S]*?)$/m);
    if (finalMatch) {
      setProduct((prev) => ({ ...prev, sellingPoints: finalMatch[1].trim() }));
    } else {
      // fallback：提取数字列表
      const lines = lastAssistant.content
        .split('\n')
        .filter((l) => /^\d+[\.\、]/.test(l.trim()));
      if (lines.length > 0) {
        setProduct((prev) => ({ ...prev, sellingPoints: lines.join('\n') }));
      }
    }
    setSpApplied(true);
    message.success('卖点已应用到表单');
  }

  // Step 2 校验：name + sellingPoints 非空 + (无 spChat 或 spApplied) 才能下一步
  const productValid =
    product.name.trim().length > 0 && product.sellingPoints.trim().length > 0;
  const spGatePassed = spChat.length === 0 || spApplied;

  // ── Step 3: 抖音链接解析 + ASR ───────────────────────────────────────────
  async function handleFetchVideoAndTranscribe(): Promise<void> {
    if (!shareUrl.trim()) return;
    setLoading('解析视频中...');
    setError('');
    try {
      const video = await fetchVideo(shareUrl.trim());
      setVideoInfo(video);

      setLoading('上传视频并提交转录...');
      const { task_id } = await submitTranscribe(video.play_url);
      setAsrTaskId(task_id);

      setAsrPolling(true);
      let attempts = 0;
      while (attempts < ASR_MAX_ATTEMPTS) {
        await new Promise((r) => setTimeout(r, ASR_POLL_INTERVAL));
        attempts++;
        setLoading(`转录中，请稍候...（已等待 ${attempts * 5} 秒）`);
        const result = await pollTranscribe(task_id);
        if (result.status === 'done' && result.text) {
          setTranscript(result.text);
          setLoading('');
          break;
        }
        if (result.status !== 'processing') {
          throw new Error('转录失败: ' + JSON.stringify(result));
        }
      }
      if (attempts >= ASR_MAX_ATTEMPTS) {
        throw new Error('转录超时（5 分钟），请重试或手动粘贴文案');
      }
      setAsrPolling(false);
      message.success('转录完成');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '解析/转录失败');
      message.error(err instanceof Error ? err.message : '解析/转录失败');
    } finally {
      setLoading('');
      setAsrPolling(false);
    }
  }

  // ── Step 3: 结构拆解 ─────────────────────────────────────────────────────
  async function handleAnalyzeStructure(): Promise<void> {
    if (!transcript.trim()) return;
    setAnalyzing(true);
    setStructureAnalysis('');
    try {
      const full = await analyzeStructureStream(
        { transcript },
        (text: string) => setStructureAnalysis(text),
      );
      setStructureAnalysis(full);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '结构拆解失败');
    } finally {
      setAnalyzing(false);
    }
  }

  // Step 3 → Step 4 过渡
  function handleEnterStep4(): void {
    setStep(4);
    // 自动触发结构拆解
    if (transcript.trim() && !structureAnalysis.trim()) {
      setTimeout(() => handleAnalyzeStructure(), 100);
    }
  }

  // ── Step 4: AI 推荐选题 ──────────────────────────────────────────────────
  async function handleAiRecommend(): Promise<void> {
    if (!selectedPersonaId) return;
    setStreaming(true);
    setStreamDisplay('');
    try {
      const refIds = references.map((r) => r.id);
      const full = await aiRecommendStream(
        {
          persona_id: selectedPersonaId,
          product_id: selectedProductId,
          reference_ids: refIds,
          transcript,
        },
        (text: string) => {
          setAiTopics(text);
          setStreamDisplay(text);
        },
      );
      setAiTopics(full);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'AI 推荐失败');
    } finally {
      setStreaming(false);
    }
  }

  // ── Step 4: AI 写作 ──────────────────────────────────────────────────────
  async function handleWriting(): Promise<void> {
    if (!selectedPersonaId) return;
    if (topicMode === 'custom' && !customTopic.trim()) {
      message.warning('请输入自定义选题');
      return;
    }
    if (topicMode === 'ai' && !chosenTopic.trim()) {
      message.warning('请从 AI 推荐中选择一个角度');
      return;
    }
    if (!structureAnalysis.trim()) {
      message.warning('请先完成结构拆解');
      return;
    }

    const topic =
      topicMode === 'same'
        ? ''
        : topicMode === 'custom'
          ? customTopic.trim()
          : chosenTopic.trim();

    setStreaming(true);
    setStreamDisplay('');

    const userMsg = '请按照规则生成种草脚本。';
    const newMessages: ChatMsg[] = [{ role: 'user', content: userMsg }];
    setChatMessages(newMessages);

    try {
      const refIds = references.map((r) => r.id);
      const full = await chatStream(
        {
          scene: 'writing',
          persona_id: selectedPersonaId,
          product_id: selectedProductId,
          reference_ids: refIds,
          transcript,
          structure_analysis: structureAnalysis,
          topic,
          messages: newMessages,
          create_job: true,
        },
        (text: string) => setStreamDisplay(text),
      );
      setChatMessages([...newMessages, { role: 'assistant', content: full }]);
      setFinalScript(full);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `写作失败：${err.message}` : '写作失败');
    } finally {
      setStreaming(false);
    }
  }

  // ── Step 4: 多轮迭代 ─────────────────────────────────────────────────────
  async function handleSendChat(): Promise<void> {
    if (!chatInput.trim() || streaming || !selectedPersonaId) return;
    const userText = chatInput.trim();
    const userMsg: ChatMsg = { role: 'user', content: userText };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput('');
    setStreaming(true);
    setStreamDisplay('');

    try {
      const refIds = references.map((r) => r.id);
      const full = await chatStream(
        {
          scene: 'iteration',
          persona_id: selectedPersonaId,
          product_id: selectedProductId,
          reference_ids: refIds,
          transcript,
          structure_analysis: structureAnalysis,
          topic: chosenTopic || customTopic,
          messages: newMessages,
        },
        (text: string) => setStreamDisplay(text),
      );
      setChatMessages([...newMessages, { role: 'assistant', content: full }]);
      setFinalScript(full);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `迭代失败：${err.message}` : '迭代失败');
    } finally {
      setStreaming(false);
    }
  }

  // ── Step 4: 保存 + 导出 ──────────────────────────────────────────────────
  async function handleSave(): Promise<void> {
    if (!finalScript || !selectedPersona) return;
    try {
      const title = `种草脚本_${selectedPersona.name}_${product.name}_${chosenTopic || customTopic || '终稿'}`;
      await saveOutput({
        content: finalScript,
        title,
        topic: chosenTopic || customTopic || null,
      });
      message.success('已保存到历史记录');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  function handleExportTxt(): void {
    if (!finalScript || !selectedPersona) return;
    const filename = `种草脚本_${selectedPersona.name}_${product.name}_${chosenTopic || customTopic || '终稿'}.txt`;
    downloadBlob(finalScript, filename, 'text/plain;charset=utf-8');
    message.success('终稿 .txt 已下载');
  }

  async function handleExportDocx(): Promise<void> {
    if (!finalScript || !selectedPersona) return;
    try {
      const filename = `种草脚本_${selectedPersona.name}_${product.name}_${chosenTopic || customTopic || '终稿'}`;
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

  const step1Ok = selectedPersonaId !== null;
  const hasResult = chatMessages.some((m) => m.role === 'assistant');

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">种草内容仿写</h1>
          <p className="page-desc">选达人 · 产品信息 · 对标验证 · 种草仿写</p>
        </div>
      </div>

      <Steps
        current={step - 1}
        items={[
          { title: '选达人' },
          { title: '产品信息' },
          { title: '对标验证' },
          { title: '种草仿写' },
        ]}
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 1 · 选达人 + 素材库 */}
      {step >= 1 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 1 · 选择达人</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>达人人设</label>
            <Select
              style={{ width: '100%' }}
              placeholder="请选择达人..."
              loading={personasLoading}
              value={selectedPersonaId ?? undefined}
              onChange={(val: number) => {
                const p = personas.find((p) => p.id === val) ?? null;
                setSelectedPersona(p);
                setSelectedPersonaId(val);
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
                {previewContentPlan(selectedPersona.soul_preview)}
              </div>
            </div>
          )}

          {/* 素材库面板 */}
          {selectedPersonaId && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--sp-3)' }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--sp-2)' }}>
                日常素材库维护（{references.length} 条）
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap', marginBottom: 'var(--sp-3)' }}>
                <Button
                  size="small"
                  onClick={() => {
                    setRefType('种草爆款');
                    setShowRefForm(true);
                  }}
                >
                  上传种草爆款文案
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    setRefType('对标种草');
                    setShowRefForm(true);
                  }}
                >
                  上传对标种草内容
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    setRefType('风格参考');
                    setShowRefForm(true);
                  }}
                >
                  上传风格参考
                </Button>
                <Button size="small" onClick={() => setShowImportDouyin(true)}>
                  从抖音链接导入
                </Button>
              </div>

              {showRefForm && (
                <div
                  style={{
                    background: 'var(--gray-50)',
                    padding: 'var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: 'var(--sp-3)',
                  }}
                >
                  <div style={{ marginBottom: 'var(--sp-2)', fontSize: 12, color: 'var(--gray-500)' }}>
                    类型：{refType}
                  </div>
                  <Input
                    placeholder="标题（必填）"
                    value={refTitle}
                    onChange={(e) => setRefTitle(e.target.value)}
                    style={{ marginBottom: 'var(--sp-2)' }}
                  />
                  <Input
                    placeholder="点赞数（选填，如 120000）"
                    value={refLikes}
                    onChange={(e) => setRefLikes(e.target.value)}
                    style={{ marginBottom: 'var(--sp-2)' }}
                  />
                  <TextArea
                    rows={6}
                    placeholder="正文（必填）"
                    value={refContent}
                    onChange={(e) => setRefContent(e.target.value)}
                    style={{ marginBottom: 'var(--sp-2)' }}
                  />
                  <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                    <Button size="small" type="primary" onClick={handleAddReference}>
                      保存
                    </Button>
                    <Button size="small" onClick={() => setShowRefForm(false)}>
                      取消
                    </Button>
                  </div>
                </div>
              )}

              {references.length > 0 && (
                <div>
                  {references.map((ref) => (
                    <div
                      key={ref.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: 'var(--sp-2) var(--sp-3)',
                        background: 'var(--gray-50)',
                        borderRadius: 'var(--radius-sm)',
                        marginBottom: 'var(--sp-1)',
                      }}
                    >
                      <div>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{ref.title}</span>
                        <span style={{ fontSize: 12, color: 'var(--gray-400)', marginLeft: 'var(--sp-2)' }}>
                          {ref.type || ''}
                          {ref.likes ? ` · ${(ref.likes / 10000).toFixed(1)}万赞` : ''}
                        </span>
                      </div>
                      <Button danger size="small" onClick={() => handleDeleteReference(ref.id)}>
                        删除
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {showImportDouyin && (
                <div
                  style={{
                    background: 'var(--gray-50)',
                    padding: 'var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: 'var(--sp-3)',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--sp-2)' }}>
                    从抖音链接导入素材（可能需要 5-10 分钟）
                  </div>
                  <Select
                    style={{ width: '100%', marginBottom: 'var(--sp-2)' }}
                    placeholder="选择类型"
                    value={importType}
                    onChange={setImportType}
                    options={[
                      { value: '种草爆款', label: '种草爆款' },
                      { value: '对标种草', label: '对标种草' },
                      { value: '风格参考', label: '风格参考' },
                    ]}
                  />
                  <Input
                    placeholder="粘贴抖音分享链接..."
                    value={importUrl}
                    onChange={(e) => setImportUrl(e.target.value)}
                    style={{ marginBottom: 'var(--sp-2)' }}
                  />
                  <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                    <Button size="small" type="primary" onClick={handleImportDouyin}>
                      开始导入
                    </Button>
                    <Button size="small" onClick={() => setShowImportDouyin(false)}>
                      取消
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 1 && (
            <Button type="primary" disabled={!step1Ok} onClick={() => setStep(2)}>
              下一步：产品信息 →
            </Button>
          )}
        </div>
      )}

      {/* Step 2 · 产品信息 */}
      {step >= 2 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · 产品信息</h3>

          {/* 产品库选择 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              从团队产品库选已有产品（公司共享）
            </label>
            <Select
              style={{ width: '100%' }}
              placeholder="选择已有产品..."
              value={selectedProductId ?? undefined}
              onChange={handleSelectProduct}
              showSearch
              optionFilterProp="label"
              options={products.map((p) => ({ label: p.name, value: p.id }))}
            />
          </div>

          {/* 文档上传 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <input
              type="file"
              ref={fileInputRef}
              multiple
              accept=".pdf,.docx,.xlsx,.pptx,.txt,.md"
              hidden
              onChange={handleUploadProductDoc}
            />
            <Button
              icon={<UploadOutlined />}
              loading={uploadingDoc}
              onClick={() => fileInputRef.current?.click()}
            >
              上传产品文档（AI 解析）
            </Button>
          </div>

          {/* 6 字段表单 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>产品名称 *</label>
              <Input
                value={product.name}
                onChange={(e) => setProduct({ ...product, name: e.target.value })}
                placeholder="必填"
              />
            </div>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>品类</label>
              <Input
                value={product.category}
                onChange={(e) => setProduct({ ...product, category: e.target.value })}
              />
            </div>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>价格区间</label>
              <Input
                value={product.price}
                onChange={(e) => setProduct({ ...product, price: e.target.value })}
              />
            </div>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>目标人群</label>
              <Input
                value={product.targetAudience}
                onChange={(e) => setProduct({ ...product, targetAudience: e.target.value })}
              />
            </div>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>核心卖点 *</label>
              <TextArea
                rows={4}
                value={product.sellingPoints}
                onChange={(e) => setProduct({ ...product, sellingPoints: e.target.value })}
                placeholder="必填"
              />
            </div>
            <div style={{ marginBottom: 'var(--sp-2)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>使用场景</label>
              <Input
                value={product.scenario}
                onChange={(e) => setProduct({ ...product, scenario: e.target.value })}
              />
            </div>
          </div>

          {/* AI 卖点讨论 */}
          {spChat.length > 0 && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 13 }}>AI 卖点讨论</span>
                <Button size="small" onClick={handleApplySellingPoints}>
                  采用卖点到表单
                </Button>
              </div>
              <div
                style={{
                  maxHeight: 300,
                  overflowY: 'auto',
                  padding: 'var(--sp-3)',
                  background: 'var(--gray-50)',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                {spChat.map((msg, i) => (
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
              </div>
              {!spStreaming && (
                <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                  <Input
                    placeholder={'输入讨论指令（如"第 2 个卖点换成 XX 方向"）...'}
                    value={spInput}
                    onChange={(e) => setSpInput(e.target.value)}
                    onPressEnter={handleSpSendChat}
                  />
                  <Button onClick={handleSpSendChat} disabled={!spInput.trim()}>
                    发送
                  </Button>
                </div>
              )}
            </div>
          )}

          {spChat.length > 0 && !spApplied && (
            <div style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 'var(--sp-3)' }}>
              请先点击「采用卖点到表单」确认最终卖点，才能进入下一步
            </div>
          )}

          {step === 2 && (
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Button onClick={() => setStep(1)}>← 上一步</Button>
              <Button
                type="primary"
                disabled={!productValid || !spGatePassed}
                onClick={() => setStep(3)}
              >
                下一步：对标验证 →
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Step 3 · 对标验证 */}
      {step >= 3 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · 对标验证</h3>

          {/* 3.1 抖音链接解析 */}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              3.1 粘贴抖音分享链接
            </label>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Input
                placeholder="粘贴抖音分享链接..."
                value={shareUrl}
                onChange={(e) => setShareUrl(e.target.value)}
                disabled={asrPolling || !!transcript}
              />
              <Button
                onClick={handleFetchVideoAndTranscribe}
                disabled={!shareUrl.trim() || asrPolling}
              >
                解析并转录
              </Button>
            </div>
          </div>

          {/* 视频信息 */}
          {videoInfo && (
            <div
              style={{
                background: 'var(--gray-50)',
                padding: 'var(--sp-3)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              <div style={{ fontSize: 13 }}>
                <strong>视频标题：</strong>
                {videoInfo.title}
              </div>
              <div style={{ fontSize: 13 }}>
                <strong>点赞数：</strong>
                {videoInfo.digg_count.toLocaleString()}
              </div>
            </div>
          )}

          {/* loading 提示 */}
          {loading && (
            <div
              style={{
                fontSize: 13,
                color: 'var(--brand)',
                padding: 'var(--sp-2) var(--sp-3)',
                background: 'var(--brand-light)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              {loading}
            </div>
          )}

          {/* error 提示 */}
          {error && (
            <div
              style={{
                fontSize: 13,
                color: 'var(--danger)',
                padding: 'var(--sp-2) var(--sp-3)',
                background: 'rgba(239,68,68,0.1)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--sp-3)',
              }}
            >
              {error}
            </div>
          )}

          {/* 3.3 文案确认 */}
          {transcript && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                3.3 对标视频口播文案（可修改）
              </label>
              <TextArea
                rows={8}
                value={transcript}
                onChange={(e) => {
                  setTranscript(e.target.value);
                  setTranscriptConfirmed(false);
                }}
              />
              <div style={{ marginTop: 'var(--sp-2)' }}>
                <Button
                  size="small"
                  type={transcriptConfirmed ? 'default' : 'primary'}
                  onClick={() => setTranscriptConfirmed(true)}
                >
                  {transcriptConfirmed ? '已确认' : '确认文案'}
                </Button>
                <span style={{ marginLeft: 'var(--sp-2)', fontSize: 12, color: 'var(--gray-400)' }}>
                  {charCount(transcript)} 字
                </span>
              </div>
            </div>
          )}

          {/* 3.4 结构拆解 */}
          {(transcriptConfirmed || structureAnalysis) && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                <label style={{ fontWeight: 500 }}>3.4 AI 对标结构拆解</label>
                <Button size="small" onClick={handleAnalyzeStructure} loading={analyzing}>
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
          )}

          {step === 3 && (
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <Button onClick={() => setStep(2)}>← 上一步</Button>
              <Button
                type="primary"
                disabled={!transcript.trim()}
                onClick={handleEnterStep4}
              >
                下一步：种草仿写 →
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Step 4 · 种草仿写 */}
      {step >= 4 && (
        <div className="card">
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 4 · 种草仿写</h3>

          {/* 4.1 选题模式 */}
          <div style={{ marginBottom: 'var(--sp-4)' }}>
            <label style={{ display: 'block', marginBottom: 'var(--sp-2)', fontWeight: 500 }}>
              4.1 选题方向
            </label>
            <Radio.Group
              value={topicMode}
              onChange={(e) => setTopicMode(e.target.value)}
              style={{ marginBottom: 'var(--sp-2)' }}
            >
              <Radio.Button value="same">沿用原文角度</Radio.Button>
              <Radio.Button value="custom">自定义角度</Radio.Button>
              <Radio.Button value="ai">AI 推荐角度</Radio.Button>
            </Radio.Group>

            {topicMode === 'same' && (
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--gray-500)',
                  background: 'var(--gray-50)',
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                系统将沿用对标原文的选题角度进行仿写
              </div>
            )}

            {topicMode === 'custom' && (
              <TextArea
                rows={3}
                placeholder="请输入您的选题想法（必填）..."
                value={customTopic}
                onChange={(e) => setCustomTopic(e.target.value)}
              />
            )}

            {topicMode === 'ai' && (
              <div>
                <Button onClick={handleAiRecommend} loading={streaming && !chatMessages.length}>
                  获取 AI 推荐角度
                </Button>
                {aiTopics && (
                  <div
                    style={{
                      background: 'var(--gray-50)',
                      padding: 'var(--sp-3)',
                      borderRadius: 'var(--radius-md)',
                      marginTop: 'var(--sp-2)',
                      fontSize: 13,
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.6,
                    }}
                  >
                    {aiTopics}
                  </div>
                )}
                {aiTopics && (
                  <TextArea
                    rows={2}
                    placeholder="从 AI 推荐中选择/修改一个角度..."
                    value={chosenTopic}
                    onChange={(e) => setChosenTopic(e.target.value)}
                    style={{ marginTop: 'var(--sp-2)' }}
                  />
                )}
              </div>
            )}
          </div>

          {/* 4.2 写作按钮 */}
          <div style={{ marginBottom: 'var(--sp-4)' }}>
            <Button
              type="primary"
              onClick={handleWriting}
              loading={streaming && chatMessages.length === 0}
              disabled={
                streaming ||
                !structureAnalysis.trim() ||
                topicMode === null ||
                (topicMode === 'custom' && !customTopic.trim()) ||
                (topicMode === 'ai' && !chosenTopic.trim())
              }
            >
              {hasResult ? '重新生成脚本' : '4.2 生成种草脚本'}
            </Button>
          </div>

          {/* 流式输出 + 消息列表 */}
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
                {chatMessages.map((msg, i) => (
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
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'flex-start',
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

              {/* 多轮迭代输入 */}
              {hasResult && !streaming && (
                <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)' }}>
                  <Input
                    placeholder="告诉 AI 哪里需要调整..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onPressEnter={handleSendChat}
                  />
                  <Button onClick={handleSendChat} disabled={!chatInput.trim()}>
                    发送
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* 终稿编辑 + 动作按钮 */}
          {hasResult && !streaming && (
            <>
              <div style={{ marginBottom: 'var(--sp-3)' }}>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                  终稿编辑
                </label>
                <TextArea
                  rows={12}
                  value={finalScript}
                  onChange={(e) => setFinalScript(e.target.value)}
                />
                <div
                  style={{
                    textAlign: 'right',
                    fontSize: 12,
                    color: 'var(--gray-400)',
                    marginTop: 'var(--sp-1)',
                  }}
                >
                  {charCount(finalScript)} 字
                </div>
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <Button onClick={() => setStep(3)}>← 上一步</Button>
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
            </>
          )}
        </div>
      )}
    </div>
  );
}
