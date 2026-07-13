/**
 * 千川文案写作页面（qianchuan-writer）
 *
 * 工作流：选择红人和当前商品，输入原版脚本，生成仿写并进行逐轮预审。
 */
import { useState, useEffect, useRef } from 'react';
import { Alert, Button, Input, Modal, Select, Steps, Upload, App } from 'antd';
import type { UploadProps } from 'antd';
import { UploadOutlined, SaveOutlined, FileTextOutlined, FileWordOutlined } from '@ant-design/icons';
import {
  getPersonas,
  parseFile,
  chatStream,
  saveOutput,
  exportWord,
} from '../../api/qianchuanWriter';
import type { QianchuanWriterPersona, QianchuanChatMessage } from '../../types/qianchuanWriter';
import { getActiveProducts, updateActiveProducts } from '../../api/kolWorkspace';
import { createQianchuanProduct, getQianchuanProducts } from '../../api/qianchuanProducts';
import { submitReview } from '../../api/scriptReview';
import type { QianchuanProduct } from '../../types/kolWorkspace';
import type { ReviewResult, ReviewRating } from '../../types/scriptReview';

const { TextArea } = Input;

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

export interface ReviewCandidate {
  text: string;
  review: Pick<ReviewResult, 'rating' | 'must_fix'>;
}

const REVIEW_RANK: Record<ReviewRating, number> = { pass: 2, minor: 1, fail: 0 };

export function selectBestReviewCandidate(candidates: ReviewCandidate[]): ReviewCandidate | undefined {
  return candidates.reduce<ReviewCandidate | undefined>((best, candidate) => {
    if (!best) return candidate;
    const candidateRank = REVIEW_RANK[candidate.review.rating];
    const bestRank = REVIEW_RANK[best.review.rating];
    if (candidateRank > bestRank) return candidate;
    if (candidateRank < bestRank) return best;
    return candidate.review.must_fix.length <= best.review.must_fix.length ? candidate : best;
  }, undefined);
}

function charCount(text: string): number {
  return text.replace(/\s/g, '').length;
}

async function readStream(resp: Response, onChunk: (full: string) => void): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onChunk(full);
  }
  return full;
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

// ── 核心 Module（接受外部 kolId，跳过 Step 1 选达人）───────────────────────
export function QianchuanWriterModule({ kolId }: { kolId: number }) {
  const { message } = App.useApp();
  const [currentStep, setCurrentStep] = useState(2);

  // 从接口加载达人信息
  const [selectedPersona, setSelectedPersona] = useState<QianchuanWriterPersona | null>(null);

  useEffect(() => {
    getPersonas().then((list) => {
      const found = list.find((p) => p.id === kolId) ?? null;
      setSelectedPersona(found);
    }).catch(() => {
      // 静默：达人名可能加载失败，不影响主流程
    });
  }, [kolId]);

  // 当前商品由工作台共享产品库提供，生成时后端会按 ID 重读数据库事实。
  const [currentProduct, setCurrentProduct] = useState<QianchuanProduct | null>(null);
  const [products, setProducts] = useState<QianchuanProduct[]>([]);
  const [switchProductId, setSwitchProductId] = useState<number | null>(null);
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [showCreateProduct, setShowCreateProduct] = useState(false);
  const [newProductName, setNewProductName] = useState('');
  const [switchingProduct, setSwitchingProduct] = useState(false);

  // 商品摘要只用于展示，不作为模型输入来源。
  const [productText, setProductText] = useState('');
  const [productName, setProductName] = useState('');

  // Step 3
  const [originalScript, setOriginalScript] = useState('');

  // Step 4
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamDisplay, setStreamDisplay] = useState('');
  const [reviewHistory, setReviewHistory] = useState<Array<{ round: number; review: ReviewResult }>>([]);
  const [finalDraft, setFinalDraft] = useState('');
  const [finalReview, setFinalReview] = useState<Pick<ReviewResult, 'rating' | 'must_fix'> | null>(null);
  const [needsManualReview, setNeedsManualReview] = useState(false);
  const [confirmedFinal, setConfirmedFinal] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  function productSummary(product: QianchuanProduct): string {
    return [
      `产品昵称：${product.nickname}`,
      product.core_selling_point && `最主推卖点：${product.core_selling_point}`,
      product.mechanism && `主推机制：${product.mechanism}`,
      product.unique_selling && `独家卖点：${product.unique_selling}`,
      product.mechanism_exclusive && '只有我有：是（必须强调独家权益）',
    ].filter(Boolean).join('\n');
  }

  async function loadCurrentProduct(): Promise<void> {
    const [activeProducts, page] = await Promise.all([
      getActiveProducts(kolId),
      getQianchuanProducts({ page: 1, page_size: 100 }),
    ]);
    const product = activeProducts[0] ?? null;
    setProducts(page.items);
    setCurrentProduct(product);
    setProductText(product ? productSummary(product) : '');
    setProductName(product?.nickname ?? '');
  }

  useEffect(() => {
    loadCurrentProduct().catch((err: unknown) => {
      message.error(err instanceof Error ? err.message : '当前商品加载失败');
    });
  // message is stable inside Ant Design App; kolId changes must reload facts.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kolId]);

  async function selectCurrentProduct(productId: number): Promise<void> {
    setSwitchingProduct(true);
    try {
      await updateActiveProducts(kolId, [productId]);
      await loadCurrentProduct();
      setShowProductPicker(false);
      message.success('当前商品已更新');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '切换当前商品失败');
    } finally {
      setSwitchingProduct(false);
    }
  }

  async function createAndSelectProduct(): Promise<void> {
    if (!newProductName.trim()) return;
    setSwitchingProduct(true);
    try {
      const product = await createQianchuanProduct({
        nickname: newProductName.trim(), core_selling_point: null, visualization: null,
        mechanism: null, mechanism_exclusive: false, endorsement: null, user_feedback: null,
        unique_selling: null, awards: null, efficacy_proof: null,
      });
      await updateActiveProducts(kolId, [product.id]);
      setNewProductName('');
      setShowCreateProduct(false);
      await loadCurrentProduct();
      message.success('商品已新建并设为当前商品');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '新建商品失败');
    } finally {
      setSwitchingProduct(false);
    }
  }

  // 自动滚动到聊天底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, streamDisplay]);

  // 原版脚本支持文件解析和直接粘贴。
  const originalScriptUploadProps: UploadProps = {
    accept: '.txt,.md,.docx,.pdf,.xlsx,.pptx',
    showUploadList: false,
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options;
      try {
        const result = await parseFile(file as File);
        setOriginalScript(result.text);
        onSuccess?.(result);
        message.success(`解析成功，${result.word_count} 字`);
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : '文件解析失败';
        message.error(errMsg);
        onError?.(new Error(errMsg));
      }
    },
  };

  // Step 4: 生成仿写
  async function handleGenerate(): Promise<void> {
    if (!selectedPersona || !currentProduct || !originalScript.trim()) return;
    setCurrentStep(4);
    setStreaming(true);
    setStreamDisplay('');
    setReviewHistory([]);
    setFinalDraft('');
    setFinalReview(null);
    setNeedsManualReview(false);
    setConfirmedFinal(false);

    const userMsg = `原版脚本如下，请按仿写规则输出${selectedPersona.name}版本：\n\n${originalScript}`;
    const newMessages: ChatMsg[] = [{ role: 'user', content: userMsg }];
    setChatMessages(newMessages);

    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: userMsg }],
        persona_id: selectedPersona.id,
        kol_id: kolId,
        product_id: currentProduct.id,
        create_job: true,
        job_context: {
          original_script_length: charCount(originalScript),
        },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, (text) => setStreamDisplay(text));
      setChatMessages([...newMessages, { role: 'assistant', content: full }]);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `生成失败：${err.message}` : '生成失败');
    } finally {
      setStreaming(false);
    }
  }

  // Step 4: 多轮追问
  async function handleSendChat(): Promise<void> {
    if (!chatInput.trim() || !selectedPersona || !currentProduct || streaming) return;
    const isFinalAdjustment = Boolean(finalDraft);
    const userMsg: ChatMsg = { role: 'user', content: chatInput };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput('');
    setStreaming(true);
    setStreamDisplay('');
    setConfirmedFinal(false);

    try {
      const apiMessages: QianchuanChatMessage[] = newMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const resp = await chatStream({
        messages: apiMessages,
        persona_id: selectedPersona.id,
        kol_id: kolId,
        product_id: currentProduct.id,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, (text) => setStreamDisplay(text));
      setChatMessages([...newMessages, { role: 'assistant', content: full }]);
      setStreamDisplay('');
      if (isFinalAdjustment) {
        try {
          const review = await submitReview({
            script_type: 'direct', original_script: originalScript, adapted_script: full,
            kol_id: kolId, product_id: currentProduct.id,
          });
          setReviewHistory((history) => [...history, { round: history.length + 1, review }]);
          setFinalDraft(full);
          setFinalReview(review);
          setNeedsManualReview(review.rating !== 'pass');
        } catch (reviewErr: unknown) {
          setFinalDraft(full);
          setFinalReview(null);
          setNeedsManualReview(true);
          message.error(reviewErr instanceof Error ? `微调后的预审失败，当前稿已保留：${reviewErr.message}` : '微调后的预审失败，当前稿已保留，请人工处理');
        }
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? `修改失败：${err.message}` : '修改失败');
    } finally {
      setStreaming(false);
    }
  }

  function latestDraft(): string | null {
    return [...chatMessages].reverse().find((item) => item.role === 'assistant')?.content ?? null;
  }

  function revisionInstruction(draft: string, review: ReviewResult): string {
    const fixes = review.must_fix.map((item, index) =>
      `${index + 1}. [${item.type}]${item.quote ? `「${item.quote}」` : ''}：${item.fix}`,
    ).join('\n');
    return `原版脚本：\n${originalScript}\n\n当前仿写稿：\n${draft}\n\n请只修改以下预审点名的问题，未点名且已合格的内容不要改动。必须保持原版结构、当前商品事实和红人设定。\n${fixes || '无必须修改项，仅按建议最小调整。'}`;
  }

  async function generateRevision(draft: string, review: ReviewResult): Promise<string> {
    if (!selectedPersona || !currentProduct) throw new Error('当前红人或商品未加载');
    const instruction = revisionInstruction(draft, review);
    const response = await chatStream({
      messages: [{ role: 'user', content: instruction }],
      persona_id: selectedPersona.id,
      kol_id: kolId,
      product_id: currentProduct.id,
      job_context: { original_script_length: charCount(originalScript) },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return readStream(response, (text) => setStreamDisplay(text));
  }

  async function handleStartReview(): Promise<void> {
    const initialDraft = latestDraft();
    if (!initialDraft || !currentProduct || streaming) return;
    setStreaming(true);
    setStreamDisplay('');
    setNeedsManualReview(false);
    setConfirmedFinal(false);
    const candidates: ReviewCandidate[] = [];
    let draft = initialDraft;
    try {
      for (let round = 1; round <= 4; round += 1) {
        const review = await submitReview({
          script_type: 'direct', original_script: originalScript, adapted_script: draft,
          kol_id: kolId, product_id: currentProduct.id,
        });
        candidates.push({ text: draft, review });
        setReviewHistory((history) => [...history, { round, review }]);
        if (review.rating === 'pass' || round === 4) break;
        draft = await generateRevision(draft, review);
        setChatMessages((messages) => [...messages, { role: 'assistant', content: draft }]);
        setStreamDisplay('');
      }
      const best = selectBestReviewCandidate(candidates);
      setFinalDraft(best?.text ?? draft);
      setFinalReview(best?.review ?? null);
      setNeedsManualReview(Boolean(best && best.review.rating !== 'pass'));
    } catch (err: unknown) {
      setFinalDraft(draft);
      setNeedsManualReview(true);
      message.error(err instanceof Error ? `预审已停止，当前稿已保留：${err.message}` : '预审已停止，当前稿已保留，请人工处理');
    } finally {
      setStreamDisplay('');
      setStreaming(false);
    }
  }

  // Step 4: 保存历史
  async function handleSave(): Promise<void> {
    if (!finalDraft || !selectedPersona || !confirmedFinal) return;
    try {
      const title = `千川仿写_${selectedPersona.name}_${productName || '终稿'}`;
      await saveOutput({
        title,
        content: finalDraft,
        product_name: productName || null,
      });
      message.success('已保存到历史记录');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  // Step 4: 导出 .txt
  function handleExportTxt(): void {
    if (!finalDraft || !selectedPersona || !confirmedFinal) return;
    const filename = `千川仿写_${selectedPersona.name}_${productName || '终稿'}.txt`;
    downloadBlob(finalDraft, filename, 'text/plain;charset=utf-8');
    message.success('终稿 .txt 已下载');
  }

  // Step 4: 导出 .docx
  async function handleExportDocx(): Promise<void> {
    if (!finalDraft || !selectedPersona || !confirmedFinal) return;
    try {
      const filename = `千川仿写_${selectedPersona.name}_${productName || '终稿'}`;
      const blob = await exportWord({
        content: finalDraft,
        filename,
      });
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

  const step3Ok = originalScript.trim().length > 0;
  const hasResult = chatMessages.some((m) => m.role === 'assistant');

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川文案写作</h1>
          <p className="page-desc">加载产品卖点 · 输入原版脚本 · AI 仿写</p>
        </div>
      </div>

      <Steps
        current={currentStep - 2}
        items={[
          { title: '加载产品' },
          { title: '输入脚本' },
          { title: '生成仿写' },
        ]}
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 2 · 当前商品 */}
      {currentStep >= 2 && (
        <div className="card workspace-step-card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · 当前商品</h3>
          {currentProduct ? (
            <>
              <div style={{ whiteSpace: 'pre-wrap', background: 'var(--gray-50)', padding: 'var(--sp-3)', borderRadius: 'var(--radius-md)', marginBottom: 'var(--sp-3)' }}>
                {productText}
              </div>
              <Button onClick={() => setShowProductPicker(true)}>切换商品</Button>
              {currentStep === 2 && <Button type="primary" style={{ marginLeft: 'var(--sp-2)' }} onClick={() => setCurrentStep(3)}>下一步：输入原版脚本 →</Button>}
            </>
          ) : (
            <Alert
              type="warning"
              showIcon
              message="还没有当前商品，不能生成仿写"
              description="请先选择已有商品，或直接新建一个商品并设为当前商品。"
              action={<><Button size="small" onClick={() => setShowProductPicker(true)}>选择已有商品</Button><Button size="small" style={{ marginLeft: 8 }} onClick={() => setShowCreateProduct(true)}>新建商品</Button></>}
            />
          )}
        </div>
      )}

      <Modal title="切换当前商品" open={showProductPicker} onCancel={() => setShowProductPicker(false)} onOk={() => switchProductId && selectCurrentProduct(switchProductId)} confirmLoading={switchingProduct} okButtonProps={{ disabled: !switchProductId }}>
        <Select style={{ width: '100%' }} placeholder="选择共享商品" value={switchProductId ?? undefined} onChange={setSwitchProductId} options={products.map((product) => ({ value: product.id, label: `${product.nickname}${product.core_selling_point ? ` · ${product.core_selling_point}` : ''}` }))} />
        <Button type="link" style={{ paddingLeft: 0, marginTop: 12 }} onClick={() => { setShowProductPicker(false); setShowCreateProduct(true); }}>没有合适的商品？直接新建</Button>
      </Modal>
      <Modal title="新建并设为当前商品" open={showCreateProduct} onCancel={() => setShowCreateProduct(false)} onOk={createAndSelectProduct} confirmLoading={switchingProduct} okButtonProps={{ disabled: !newProductName.trim() }}>
        <Input placeholder="商品昵称" value={newProductName} onChange={(event) => setNewProductName(event.target.value)} />
      </Modal>

      {/* Step 3 · 输入脚本 */}
      {currentStep >= 3 && (
        <div className="card workspace-step-card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · 输入原版脚本</h3>
          <Upload {...originalScriptUploadProps}>
            <Button icon={<UploadOutlined />}>上传原版脚本文件</Button>
          </Upload>
          <div style={{ fontSize: 12, color: 'var(--gray-400)', margin: 'var(--sp-2) 0' }}>或直接粘贴原版脚本</div>
          <TextArea
            rows={8}
            placeholder="把原版千川脚本粘贴到这里..."
            value={originalScript}
            onChange={(e) => setOriginalScript(e.target.value)}
          />
          {originalScript.trim() && (
            <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--gray-400)', marginTop: 'var(--sp-1)' }}>
              {charCount(originalScript)} 字
            </div>
          )}
          {currentStep === 3 && (
            <Button
              type="primary"
              disabled={!step3Ok || !currentProduct || streaming}
              onClick={handleGenerate}
              style={{ marginTop: 'var(--sp-3)' }}
            >
              生成仿写脚本 →
            </Button>
          )}
        </div>
      )}

      {/* Step 4 · 生成仿写 */}
      {currentStep >= 4 && (
        <div className="card workspace-step-card">
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 4 · 生成仿写</h3>

          {/* 消息列表 */}
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

          {reviewHistory.length > 0 && (
            <div style={{ marginBottom: 'var(--sp-3)' }}>
              {reviewHistory.map(({ round, review }) => (
                <div key={round} style={{ fontSize: 13, padding: 'var(--sp-2)', borderBottom: '1px solid var(--border)' }}>
                  第 {round} 轮预审：{review.rating === 'pass' ? '通过' : review.rating === 'minor' ? '小改' : '不通过'}；必须修改 {review.must_fix.length} 项
                </div>
              ))}
            </div>
          )}

          {finalDraft && !streaming && (
            <div style={{ padding: 'var(--sp-3)', background: 'var(--brand-light)', borderRadius: 'var(--radius-md)', marginBottom: 'var(--sp-3)' }}>
              <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>最好版本{finalReview ? `：${finalReview.rating === 'pass' ? '通过' : finalReview.rating === 'minor' ? '小改' : '不通过'}` : ''}</div>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{finalDraft}</div>
              {needsManualReview && <div style={{ marginTop: 'var(--sp-2)', fontSize: 12 }}>轮次用尽或预审中断，剩余问题需人工确认。</div>}
              <Button style={{ marginTop: 'var(--sp-2)' }} type={confirmedFinal ? 'default' : 'primary'} onClick={() => setConfirmedFinal(true)}>{confirmedFinal ? '已确认最终稿' : '运营确认最终稿'}</Button>
            </div>
          )}

          {/* 追问输入 */}
          {hasResult && !streaming && (
            <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
              <Input
                placeholder="告诉 AI 哪里需要调整..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onPressEnter={handleSendChat}
              />
              <Button onClick={handleSendChat} disabled={!chatInput.trim()}>
                发送
              </Button>
              <Button type="primary" onClick={handleStartReview}>
                开始逐轮预审
              </Button>
            </div>
          )}

          {/* 操作按钮 */}
          {finalDraft && confirmedFinal && !streaming && (
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

// ── 独立页面（保留完整 Step 1 选达人流程）────────────────────────────────────
export default function QianchuanWriterPage() {
  const { message } = App.useApp();
  const [kolId, setKolId] = useState<number | null>(null);
  const [personas, setPersonas] = useState<QianchuanWriterPersona[]>([]);
  const [personasLoading, setPersonasLoading] = useState(false);
  const [selectedPersona, setSelectedPersona] = useState<QianchuanWriterPersona | null>(null);

  useEffect(() => {
    setPersonasLoading(true);
    getPersonas()
      .then((data) => setPersonas(data))
      .catch((err: unknown) => {
        message.error(err instanceof Error ? err.message : '加载达人列表失败');
      })
      .finally(() => setPersonasLoading(false));
  }, [message]);

  if (kolId !== null) {
    return <QianchuanWriterModule kolId={kolId} />;
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">千川文案写作</h1>
          <p className="page-desc">选择达人 · 加载产品卖点 · 输入原版脚本 · AI 仿写</p>
        </div>
      </div>

      <Steps
        current={0}
        items={[
          { title: '选择达人' },
          { title: '加载产品' },
          { title: '输入脚本' },
          { title: '生成仿写' },
        ]}
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 1 · 选达人 */}
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
              maxHeight: 400,
              overflowY: 'auto',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--sp-2)' }}>
              人格档案
            </div>
            <div
              style={{
                fontSize: 13,
                color: 'var(--gray-700)',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.6,
              }}
            >
              {selectedPersona.soul_full || selectedPersona.soul_preview || '（暂无内容）'}
            </div>
            {selectedPersona.content_plan && (
              <>
                <div style={{ fontWeight: 600, fontSize: 13, marginTop: 'var(--sp-3)', marginBottom: 'var(--sp-2)', borderTop: '1px solid var(--border)', paddingTop: 'var(--sp-2)' }}>
                  内容规划
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: 'var(--gray-700)',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.6,
                  }}
                >
                  {selectedPersona.content_plan}
                </div>
              </>
            )}
          </div>
        )}
        <Button
          type="primary"
          disabled={!selectedPersona}
          onClick={() => selectedPersona && setKolId(selectedPersona.id)}
        >
          确认，去加载产品 →
        </Button>
      </div>
    </div>
  );
}
