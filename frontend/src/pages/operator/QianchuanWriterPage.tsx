/**
 * 千川文案写作页面（qianchuan-writer）
 *
 * 4 步工作流：
 *   Step 1 · 选达人   — 下拉选达人 + 预览 soul 前 400 字
 *   Step 2 · 加载产品 — 上传文件 OR 粘贴模式 + 展示解析结果
 *   Step 3 · 输入脚本 — 粘贴原版脚本 + 实时去空白字数
 *   Step 4 · 生成仿写 — 流式输出 + 多轮追问 + 保存/导出
 */
import { useState, useEffect, useRef } from 'react';
import { Button, Input, Select, Steps, Upload, App } from 'antd';
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

const { TextArea } = Input;

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
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

  // Step 2
  const [productText, setProductText] = useState('');
  const [productName, setProductName] = useState('');
  const [pasteMode, setPasteMode] = useState(false);
  const [pasteText, setPasteText] = useState('');

  // Step 3
  const [originalScript, setOriginalScript] = useState('');

  // Step 4
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamDisplay, setStreamDisplay] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到聊天底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, streamDisplay]);

  // Step 2: 文件上传配置
  const uploadProps: UploadProps = {
    accept: '.txt,.md,.docx,.pdf,.xlsx,.pptx',
    showUploadList: false,
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options;
      try {
        const result = await parseFile(file as File);
        setProductText(result.text);
        onSuccess?.(result);
        message.success(`解析成功，${result.word_count} 字`);
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : '文件解析失败';
        message.error(errMsg);
        onError?.(new Error(errMsg));
      }
    },
  };

  // Step 2: 拖拽上传
  function handleDrop(e: React.DragEvent): void {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    parseFile(file)
      .then((result) => {
        setProductText(result.text);
        message.success(`解析成功，${result.word_count} 字`);
      })
      .catch((err: unknown) => {
        message.error(err instanceof Error ? err.message : '文件解析失败');
      });
  }

  // Step 4: 生成仿写
  async function handleGenerate(): Promise<void> {
    if (!selectedPersona || !productText.trim() || !originalScript.trim()) return;
    setCurrentStep(4);
    setStreaming(true);
    setStreamDisplay('');

    const userMsg = `原版脚本如下，请按仿写规则输出${selectedPersona.name}版本：\n\n${originalScript}`;
    const newMessages: ChatMsg[] = [{ role: 'user', content: userMsg }];
    setChatMessages(newMessages);

    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: userMsg }],
        persona_id: selectedPersona.id,
        kol_id: kolId,
        create_job: true,
        job_context: {
          product_name: productName,
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
    if (!chatInput.trim() || !selectedPersona || streaming) return;
    const userMsg: ChatMsg = { role: 'user', content: chatInput };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput('');
    setStreaming(true);
    setStreamDisplay('');

    try {
      const apiMessages: QianchuanChatMessage[] = newMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const resp = await chatStream({
        messages: apiMessages,
        persona_id: selectedPersona.id,
        kol_id: kolId,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, (text) => setStreamDisplay(text));
      setChatMessages([...newMessages, { role: 'assistant', content: full }]);
      setStreamDisplay('');
    } catch (err: unknown) {
      message.error(err instanceof Error ? `修改失败：${err.message}` : '修改失败');
    } finally {
      setStreaming(false);
    }
  }

  // Step 4: 保存历史
  async function handleSave(): Promise<void> {
    const lastAssistant = [...chatMessages].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant || !selectedPersona) return;
    try {
      const title = `千川仿写_${selectedPersona.name}_${productName || '终稿'}`;
      await saveOutput({
        title,
        content: lastAssistant.content,
        product_name: productName || null,
      });
      message.success('已保存到历史记录');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    }
  }

  // Step 4: 导出 .txt
  function handleExportTxt(): void {
    const lastAssistant = [...chatMessages].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant || !selectedPersona) return;
    const filename = `千川仿写_${selectedPersona.name}_${productName || '终稿'}.txt`;
    downloadBlob(lastAssistant.content, filename, 'text/plain;charset=utf-8');
    message.success('终稿 .txt 已下载');
  }

  // Step 4: 导出 .docx
  async function handleExportDocx(): Promise<void> {
    const lastAssistant = [...chatMessages].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant || !selectedPersona) return;
    try {
      const filename = `千川仿写_${selectedPersona.name}_${productName || '终稿'}`;
      const blob = await exportWord({
        content: lastAssistant.content,
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

  const step2Ok = productText.trim().length > 0;
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

      {/* Step 2 · 加载产品 */}
      {currentStep >= 2 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · 加载产品卖点</h3>

          {!productText && !pasteMode && (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              style={{
                border: '2px dashed var(--brand-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--sp-8)',
                textAlign: 'center',
                cursor: 'pointer',
                background: 'var(--brand-light)',
              }}
            >
              <Upload {...uploadProps}>
                <div>
                  <UploadOutlined style={{ fontSize: 32, color: 'var(--brand)', marginBottom: 'var(--sp-2)' }} />
                  <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--gray-700)' }}>
                    点击上传或拖拽卖点卡
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 'var(--sp-1)' }}>
                    支持 .txt .md .docx .pdf .xlsx .pptx
                  </div>
                </div>
              </Upload>
              <div style={{ fontSize: 12, color: 'var(--gray-400)', margin: 'var(--sp-3) 0' }}>—— 或者 ——</div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setPasteMode(true);
                }}
              >
                直接粘贴文本
              </button>
            </div>
          )}

          {!productText && pasteMode && (
            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                <label style={{ fontWeight: 500, fontSize: 13 }}>粘贴产品卖点</label>
                <button className="btn btn-ghost btn-sm" onClick={() => setPasteMode(false)}>
                  返回上传
                </button>
              </div>
              <TextArea
                rows={6}
                placeholder="把产品卖点卡粘贴到这里..."
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
              />
              <Button
                type="primary"
                disabled={!pasteText.trim()}
                onClick={() => {
                  setProductText(pasteText.trim());
                  setPasteMode(false);
                  setPasteText('');
                }}
                style={{ marginTop: 'var(--sp-2)' }}
              >
                确认
              </Button>
            </div>
          )}

          {productText && (
            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                <label style={{ fontWeight: 500, fontSize: 13 }}>产品名称（可选）</label>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setProductText('');
                    setProductName('');
                  }}
                >
                  清空重来
                </button>
              </div>
              <Input
                placeholder="用于导出文件命名，可不填"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                style={{ marginBottom: 'var(--sp-2)' }}
              />
              <div
                style={{
                  background: 'var(--gray-50)',
                  padding: 'var(--sp-3)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  color: 'var(--gray-600)',
                  maxHeight: 300,
                  overflowY: 'auto',
                  whiteSpace: 'pre-wrap',
                  marginBottom: 'var(--sp-3)',
                }}
              >
                {productText}
              </div>
              {currentStep === 2 && (
                <Button type="primary" disabled={!step2Ok} onClick={() => setCurrentStep(3)}>
                  下一步：输入原版脚本 →
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Step 3 · 输入脚本 */}
      {currentStep >= 3 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · 输入原版脚本</h3>
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
              disabled={!step3Ok || streaming}
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
        <div className="card">
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
            </div>
          )}

          {/* 操作按钮 */}
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
      <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
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
