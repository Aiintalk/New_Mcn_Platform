/**
 * 价值观仿写页面（values-writer）
 *
 * 4 步工作流：
 *   Step 1 · 选达人   — 仅独立页模式，工作台 Module 跳过
 *   Step 2 · 选价值观 — AI 提炼 + 可点击 Tag 多选（1-3 个）
 *   Step 3 · 情绪方向 — 可选调性输入 + 流式生成 + 可编辑
 *   Step 4 · 生成内容 — 流式写作 + 迭代优化 + 复制/导出
 */
import { useState, useEffect } from 'react';
import { Steps, Tag, Spin, Input, Select, App } from 'antd';
import {
  extractValues,
  emotionDirectionStream,
  writeStream,
  iterateStream,
} from '../../api/valuesWriter';
import { get } from '../../api/request';
import type { QianchuanWriterPersona } from '../../types/qianchuanWriter';

const { TextArea } = Input;

// ── helpers ──────────────────────────────────────────────────────────────────

function downloadTxt(content: string, filename = 'values-writer.txt'): void {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Module（工作台内嵌，从 Step 2 开始）───────────────────────────────────────

export function ValuesWriterModule({ kolId }: { kolId: number }) {
  const { message } = App.useApp();

  // Step tracking (2-4 inside module)
  const [currentStep, setCurrentStep] = useState(0); // 0=Step2, 1=Step3, 2=Step4

  // Step 2: value selection
  const [valuesLoading, setValuesLoading] = useState(false);
  const [valuesList, setValuesList] = useState<string[]>([]);
  const [selectedValues, setSelectedValues] = useState<string[]>([]);

  // Step 3: emotion direction
  const [tone, setTone] = useState('');
  const [emotionDirection, setEmotionDirection] = useState('');
  const [emotionStreaming, setEmotionStreaming] = useState(false);

  // Step 4: content generation
  const [productContext, setProductContext] = useState('');
  const [content, setContent] = useState('');
  const [contentStreaming, setContentStreaming] = useState(false);
  const [iterationInstruction, setIterationInstruction] = useState('');
  const [iterating, setIterating] = useState(false);

  // Load values on mount
  useEffect(() => {
    setValuesLoading(true);
    extractValues(kolId)
      .then((res) => {
        setValuesList(res.values ?? []);
      })
      .catch((err: unknown) => {
        message.error(err instanceof Error ? err.message : 'AI 提炼价值观失败');
      })
      .finally(() => setValuesLoading(false));
  }, [kolId, message]);

  function handleTagClick(val: string) {
    setSelectedValues((prev) => {
      if (prev.includes(val)) {
        return prev.filter((v) => v !== val);
      }
      if (prev.length >= 3) {
        message.warning('最多选择 3 个价值观');
        return prev;
      }
      return [...prev, val];
    });
  }

  async function handleGenerateEmotion() {
    setEmotionStreaming(true);
    setEmotionDirection('');
    try {
      await emotionDirectionStream(
        {
          kol_id: kolId,
          selected_values: selectedValues,
          ...(tone ? { tone } : {}),
        },
        (text) => setEmotionDirection(text),
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '生成情绪方向失败');
    } finally {
      setEmotionStreaming(false);
    }
  }

  async function handleWrite() {
    setContentStreaming(true);
    setContent('');
    try {
      await writeStream(
        {
          kol_id: kolId,
          selected_values: selectedValues,
          emotion_direction: emotionDirection,
          ...(productContext ? { product_context: productContext } : {}),
        },
        (text) => setContent(text),
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '生成内容失败');
    } finally {
      setContentStreaming(false);
    }
  }

  async function handleIterate() {
    if (!iterationInstruction.trim()) {
      message.warning('请输入迭代指令');
      return;
    }
    setIterating(true);
    try {
      await iterateStream(
        {
          kol_id: kolId,
          content,
          instruction: iterationInstruction,
        },
        (text) => setContent(text),
      );
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '迭代优化失败');
    } finally {
      setIterating(false);
    }
  }

  function handleCopy() {
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
      message.success('已复制到剪贴板');
    }).catch(() => {
      message.error('复制失败，请手动复制');
    });
  }

  const steps = [
    { title: '选价值观' },
    { title: '情绪方向' },
    { title: '生成内容' },
  ];

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 'var(--sp-4)' }}>
        <div>
          <h1 className="page-title">价值观仿写</h1>
          <p className="page-desc">基于达人价值观，生成真实有温度的内容</p>
        </div>
      </div>

      <Steps
        current={currentStep}
        items={steps}
        size="small"
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 2: 选价值观 */}
      {currentStep === 0 && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">选择价值观</h2>
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>
              已选 {selectedValues.length} / 3
            </span>
          </div>
          <div className="card-body">
            {valuesLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 0' }}>
                <Spin size="small" />
                <span style={{ color: 'var(--gray-400)', fontSize: 14 }}>AI 提炼中...</span>
              </div>
            ) : valuesList.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-text">暂未获取到价值观，请确认达人人设已完善</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
                {valuesList.map((val) => {
                  const isSelected = selectedValues.includes(val);
                  return (
                    <Tag
                      key={val}
                      color={isSelected ? 'blue' : 'default'}
                      onClick={() => handleTagClick(val)}
                      style={{
                        cursor: 'pointer',
                        fontSize: 14,
                        padding: '4px 14px',
                        borderRadius: 20,
                        userSelect: 'none',
                      }}
                    >
                      {val}
                    </Tag>
                  );
                })}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-primary"
                disabled={selectedValues.length === 0}
                onClick={() => setCurrentStep(1)}
              >
                确认，生成情绪方向 →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: 情绪方向 */}
      {currentStep === 1 && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">生成情绪方向</h2>
          </div>
          <div className="card-body">
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 8 }}>
                已选价值观：
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {selectedValues.map((val) => (
                  <Tag key={val} color="blue" style={{ borderRadius: 20 }}>
                    {val}
                  </Tag>
                ))}
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                情感基调（选填）
              </div>
              <TextArea
                rows={2}
                placeholder="如：轻松温暖、真实有力..."
                value={tone}
                onChange={(e) => setTone(e.target.value)}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>情绪方向</div>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={handleGenerateEmotion}
                  disabled={emotionStreaming}
                >
                  {emotionStreaming ? '生成中...' : '生成情绪方向'}
                </button>
              </div>
              <TextArea
                rows={6}
                placeholder="点击「生成情绪方向」，AI 将生成推荐内容；也可直接手动填写..."
                value={emotionDirection}
                onChange={(e) => setEmotionDirection(e.target.value)}
                disabled={emotionStreaming}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button className="btn btn-ghost" onClick={() => setCurrentStep(0)}>
                ← 返回
              </button>
              <button
                className="btn btn-primary"
                disabled={!emotionDirection.trim()}
                onClick={() => setCurrentStep(2)}
              >
                下一步：生成内容 →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: 生成内容 */}
      {currentStep === 2 && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">生成内容</h2>
          </div>
          <div className="card-body">
            {/* 摘要 */}
            <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg-page)', borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 6 }}>价值观：</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                {selectedValues.map((val) => (
                  <Tag key={val} color="blue" style={{ borderRadius: 20 }}>
                    {val}
                  </Tag>
                ))}
              </div>
              <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>情绪方向：</div>
              <div style={{ fontSize: 13, color: 'var(--gray-700)', whiteSpace: 'pre-wrap' }}>
                {emotionDirection}
              </div>
            </div>

            {/* 产品关联 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                产品关联（选填）
              </div>
              <Input
                placeholder="如：本期推广 XX 产品（选填）"
                value={productContext}
                onChange={(e) => setProductContext(e.target.value)}
              />
            </div>

            {/* 生成按钮 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <button className="btn btn-ghost" onClick={() => setCurrentStep(1)}>
                ← 返回
              </button>
              <button
                className="btn btn-primary"
                onClick={handleWrite}
                disabled={contentStreaming}
              >
                {contentStreaming ? '生成中...' : '开始生成'}
              </button>
            </div>

            {/* 内容区 */}
            <TextArea
              rows={12}
              placeholder="点击「开始生成」，AI 将流式输出内容..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={contentStreaming || iterating}
            />

            {/* 工具栏 */}
            {content && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                <button className="btn btn-ghost btn-sm" onClick={handleCopy}>
                  复制全文
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => downloadTxt(content)}
                >
                  导出 TXT
                </button>
              </div>
            )}

            {/* 迭代区 */}
            {content && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>迭代优化</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Input
                    placeholder="输入优化指令，如：加强情感共鸣，语气更真实..."
                    value={iterationInstruction}
                    onChange={(e) => setIterationInstruction(e.target.value)}
                    disabled={iterating || contentStreaming}
                  />
                  <button
                    className="btn btn-ghost"
                    onClick={handleIterate}
                    disabled={iterating || contentStreaming || !iterationInstruction.trim()}
                    style={{ flexShrink: 0 }}
                  >
                    {iterating ? '优化中...' : '优化'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 独立页面（包含 Step 1 选达人）────────────────────────────────────────────

export default function ValuesWriterPage() {
  const { message } = App.useApp();
  const [personas, setPersonas] = useState<QianchuanWriterPersona[]>([]);
  const [selectedKolId, setSelectedKolId] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    get<QianchuanWriterPersona[]>('/api/tools/qianchuan-writer/kols/personas')
      .then(setPersonas)
      .catch(() => {
        message.error('加载达人列表失败');
      });
  }, [message]);

  if (!confirmed || selectedKolId === null) {
    return (
      <div>
        <div className="page-header">
          <div>
            <h1 className="page-title">价值观仿写</h1>
            <p className="page-desc">基于达人价值观，生成真实有温度的内容</p>
          </div>
        </div>
        <div className="card" style={{ maxWidth: 500 }}>
          <div className="card-header">
            <h2 className="card-title">选择达人</h2>
          </div>
          <div className="card-body">
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>达人</div>
              <Select
                style={{ width: '100%' }}
                placeholder="请选择达人"
                value={selectedKolId ?? undefined}
                onChange={(val) => setSelectedKolId(val)}
                options={personas.map((p) => ({
                  value: p.id,
                  label: p.name,
                }))}
                showSearch
                filterOption={(input, option) =>
                  String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-primary"
                disabled={selectedKolId === null}
                onClick={() => setConfirmed(true)}
              >
                确认，开始仿写 →
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return <ValuesWriterModule kolId={selectedKolId} />;
}
