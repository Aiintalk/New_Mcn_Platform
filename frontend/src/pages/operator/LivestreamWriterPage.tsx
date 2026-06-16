/**
 * 直播脚本仿写页面（livestream-writer）
 *
 * 4 步工作流：
 *   Step 1 · 选达人     — 下拉选择
 *   Step 2 · 上传卖点   — 文件/粘贴 + 选卖点顺序
 *   Step 3 · 锁定对标   — 文件/粘贴 + 确认锁定
 *   Step 4 · 生成方案   — AI 流式生成 + 多轮迭代 + .txt 导出
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { Button, Select, Steps, message, Radio, Upload, Input, Spin } from 'antd';
import { UploadOutlined, DownloadOutlined, LockOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import {
  getLivestreamWriterConfig,
  getKolPersonas,
  parseFile,
  chatStream,
} from '../../api/livestreamWriter';
import type { Persona, SpOrder, LivestreamWriterConfig } from '../../types/livestreamWriter';

const { TextArea } = Input;

const SP_ORDER_OPTIONS: SpOrder[] = ['背书→机制→种草', '机制→背书→种草', '种草→背书→机制'];

function extractProductName(spText: string): string {
  const m = spText.match(/一句话总结[：:]\s*(.+)/);
  if (m) return m[1].trim().slice(0, 30);
  return '';
}

function countChars(text: string): number {
  return text.replace(/\s/g, '').length;
}

function extractScriptSection(content: string): string {
  const m = content.match(/### 四、直播讲解脚本([\s\S]*?)(?=### 五、|$)/);
  return m ? m[1] : '';
}

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/^### (.+)$/gm, '<h3 style="font-size:16px;font-weight:700;margin:20px 0 8px;color:#1d2939">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:18px;font-weight:700;margin:24px 0 10px;color:#1d2939">$2</h2>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p style="margin-bottom:10px">')
    .replace(/\n/g, '<br/>');
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.8, color: '#374151' }}
      dangerouslySetInnerHTML={{ __html: `<p style="margin-bottom:10px">${html}</p>` }}
    />
  );
}

export default function LivestreamWriterPage() {
  const [step, setStep] = useState(0);
  const [config, setConfig] = useState<LivestreamWriterConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);

  // Step 1
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null);

  // Step 2
  const [sellingPoints, setSellingPoints] = useState('');
  const [productName, setProductName] = useState('');
  const [spOrder, setSpOrder] = useState<SpOrder>('背书→机制→种草');
  const [spUploading, setSpUploading] = useState(false);

  // Step 3
  const [refScript, setRefScript] = useState('');
  const [refScriptLocked, setRefScriptLocked] = useState(false);
  const [refUploading, setRefUploading] = useState(false);

  // Step 4
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [streaming, setStreaming] = useState(false);
  const [userInput, setUserInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 加载配置和达人列表
  useEffect(() => {
    async function init() {
      try {
        const [cfg, kolResp] = await Promise.all([
          getLivestreamWriterConfig(),
          getKolPersonas(),
        ]);
        setConfig(cfg);
        setPersonas(kolResp.personas ?? []);
      } catch (e) {
        message.error('加载失败，请刷新重试');
      } finally {
        setConfigLoading(false);
      }
    }
    init();
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // 文件解析（卖点/对标）
  async function handleFileUpload(
    file: UploadFile,
    target: 'sp' | 'ref',
  ): Promise<boolean> {
    if (target === 'sp') setSpUploading(true);
    else setRefUploading(true);
    try {
      const result = await parseFile(file as unknown as File);
      if (target === 'sp') {
        setSellingPoints(result.text);
        const pName = extractProductName(result.text);
        if (pName) setProductName(pName);
      } else {
        setRefScript(result.text);
      }
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '文件解析失败');
    } finally {
      if (target === 'sp') setSpUploading(false);
      else setRefUploading(false);
    }
    return false; // 阻止默认上传行为
  }

  // 构建 Prompt
  function buildGeneratePrompt(): string {
    if (!config) return '';
    const refLength = countChars(refScript);
    return config.generate_prompt
      .replace(/{orderLabels}/g, spOrder)
      .replace(/{refLength}/g, String(refLength))
      .replace(/{sellingPoints}/g, sellingPoints)
      .replace(/{refScript}/g, refScript)
      .replace(/{personaSoul}/g, selectedPersona?.soul ?? '');
  }

  function buildIteratePrompt(): string {
    if (!config) return '';
    const refLength = countChars(refScript);
    return config.iterate_prompt
      .replace(/{orderLabels}/g, spOrder)
      .replace(/{refLength}/g, String(refLength))
      .replace(/{sellingPoints}/g, sellingPoints)
      .replace(/{refScript}/g, refScript)
      .replace(/{personaSoul}/g, selectedPersona?.soul ?? '');
  }

  // 首次生成的用户消息
  function buildFirstUserMessage(): string {
    const refLength = countChars(refScript);
    const pName = productName || '（未填写）';
    const pName2 = selectedPersona?.name ?? '（未选择）';
    return `直接输出完整的开播方案，不要提问。\n\n产品：${pName}\n卖点顺序：${spOrder}\n对标讲解脚本字数：${refLength}字，仿写的讲解脚本不能超过\n达人：${pName2}\n\n要求：\n1. 用${pName2}的真实经历和说话方式去讲这个产品，不要罗列卖点\n2. 痛点激发环节必须用提问句式戳到用户\n3. 讲解要有算账逻辑（帮观众算清楚省了多少）\n4. 逼单方式要匹配${pName2}的人设\n5. 七个模块全部输出，不要遗漏`;
  }

  // 流式调用核心
  async function streamChat(
    systemPrompt: string,
    newMessages: Array<{ role: 'user' | 'assistant'; content: string }>,
    isFirst: boolean,
  ) {
    setStreaming(true);
    const abort = new AbortController();
    abortRef.current = abort;

    // 加入 assistant 占位
    setChatMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const resp = await chatStream({
        messages: newMessages,
        systemPrompt,
        model: config?.model_id,
        createJob: isFirst,
        jobContext: isFirst ? {
          productName: productName || '',
          personaName: selectedPersona?.name ?? '',
          spOrder,
          refLength: countChars(refScript),
        } : undefined,
      });

      if (!resp.ok) throw new Error(`请求失败 ${resp.status}`);
      if (!resp.body) throw new Error('无响应体');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let accum = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        accum += chunk;
        setChatMessages(prev => {
          const copy = [...prev];
          copy[copy.length - 1] = { role: 'assistant', content: accum };
          return copy;
        });
      }

      // autoTrimIfTooLong 检查
      const scriptSection = extractScriptSection(accum);
      const targetMax = countChars(refScript);
      const actual = countChars(scriptSection);
      if (scriptSection && actual > targetMax) {
        const trimMsg = `脚本超字数了。当前约${actual}字，上限${targetMax}字，需要砍掉${actual - targetMax}字以上。\n请精简内容，删减冗余表达，压到${targetMax}字以内。直接输出压缩后的完整脚本+自检表，不要解释。`;
        const trimMessages = [...newMessages, { role: 'assistant' as const, content: accum }, { role: 'user' as const, content: trimMsg }];
        setChatMessages(prev => [...prev, { role: 'user', content: trimMsg }]);
        await streamChat(buildIteratePrompt(), trimMessages, false);
        return;
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        message.error(e instanceof Error ? e.message : 'AI 生成失败');
        setChatMessages(prev => prev.slice(0, -1));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  // 首次生成
  async function handleGenerate() {
    if (!selectedPersona || !sellingPoints.trim() || !refScript.trim()) {
      message.warning('请完成所有步骤后再生成');
      return;
    }
    const firstUserMsg = buildFirstUserMessage();
    const newMessages = [{ role: 'user' as const, content: firstUserMsg }];
    setChatMessages([{ role: 'user', content: firstUserMsg }]);
    await streamChat(buildGeneratePrompt(), newMessages, true);
  }

  // 多轮追问
  async function handleFollowUp() {
    if (!userInput.trim() || streaming) return;
    const userMsg = { role: 'user' as const, content: userInput.trim() };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setUserInput('');
    await streamChat(buildIteratePrompt(), newMessages, false);
  }

  // 导出 .txt
  function handleExport() {
    const lastAssistant = [...chatMessages].reverse().find(m => m.role === 'assistant');
    if (!lastAssistant) return;
    const blob = new Blob([lastAssistant.content], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `开播方案_${productName || '终稿'}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const hasOutput = chatMessages.some(m => m.role === 'assistant' && m.content);

  if (configLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      {/* 标题 */}
      <div className="page-header" style={{ marginBottom: 24 }}>
        <div>
          <h1 className="page-title">直播脚本仿写</h1>
          <p className="page-desc">选达人 · 上传卖点卡 · 锁定对标 · AI 生成7模块开播方案</p>
        </div>
      </div>

      {/* 步骤导航 */}
      <Steps
        current={step}
        onChange={setStep}
        style={{ marginBottom: 32 }}
        items={[
          { title: '选达人' },
          { title: '上传卖点' },
          { title: '锁定对标' },
          { title: '生成方案' },
        ]}
      />

      {/* Step 1 · 选达人 */}
      {step === 0 && (
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 16, fontWeight: 600 }}>选择达人</h3>
          <Select
            showSearch
            placeholder="请选择达人"
            style={{ width: '100%', maxWidth: 400 }}
            value={selectedPersona?.name}
            onChange={(name) => {
              const p = personas.find(p => p.name === name) ?? null;
              setSelectedPersona(p);
            }}
            options={personas.map(p => ({ label: p.name, value: p.name }))}
            filterOption={(input, option) =>
              (option?.label as string).toLowerCase().includes(input.toLowerCase())
            }
          />
          {selectedPersona && (
            <div style={{ marginTop: 16, padding: 16, background: 'var(--gray-50)', borderRadius: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
              <strong>达人风格预览：</strong>
              <p style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{selectedPersona.soul.slice(0, 200)}{selectedPersona.soul.length > 200 ? '...' : ''}</p>
            </div>
          )}
          <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
            <Button type="primary" disabled={!selectedPersona} onClick={() => setStep(1)}>
              下一步
            </Button>
          </div>
        </div>
      )}

      {/* Step 2 · 上传卖点 */}
      {step === 1 && (
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 16, fontWeight: 600 }}>上传产品卖点卡</h3>
          <Upload
            accept=".txt,.md,.docx,.pages"
            showUploadList={false}
            beforeUpload={(file) => { handleFileUpload(file as unknown as UploadFile, 'sp'); return false; }}
          >
            <Button icon={<UploadOutlined />} loading={spUploading}>
              上传文件（.txt/.md/.docx/.pages）
            </Button>
          </Upload>
          <div style={{ margin: '12px 0', color: 'var(--text-secondary)', fontSize: 13 }}>或直接粘贴卖点卡文本：</div>
          <TextArea
            rows={8}
            placeholder="粘贴产品卖点卡文本..."
            value={sellingPoints}
            onChange={(e) => {
              setSellingPoints(e.target.value);
              const pName = extractProductName(e.target.value);
              if (pName) setProductName(pName);
            }}
          />
          {productName && (
            <div style={{ marginTop: 8, color: 'var(--success)', fontSize: 13 }}>
              ✓ 识别到产品名：<strong>{productName}</strong>
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 8, fontWeight: 500 }}>卖点顺序：</div>
            <Radio.Group value={spOrder} onChange={e => setSpOrder(e.target.value)}>
              {SP_ORDER_OPTIONS.map(o => (
                <Radio.Button key={o} value={o}>{o}</Radio.Button>
              ))}
            </Radio.Group>
          </div>
          <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={() => setStep(0)}>上一步</Button>
            <Button type="primary" disabled={!sellingPoints.trim()} onClick={() => setStep(2)}>
              下一步
            </Button>
          </div>
        </div>
      )}

      {/* Step 3 · 锁定对标 */}
      {step === 2 && (
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 16, fontWeight: 600 }}>上传对标直播间文案</h3>
          {!refScriptLocked && (
            <>
              <Upload
                accept=".txt,.md,.docx,.pages"
                showUploadList={false}
                beforeUpload={(file) => { handleFileUpload(file as unknown as UploadFile, 'ref'); return false; }}
              >
                <Button icon={<UploadOutlined />} loading={refUploading}>
                  上传文件（.txt/.md/.docx/.pages）
                </Button>
              </Upload>
              <div style={{ margin: '12px 0', color: 'var(--text-secondary)', fontSize: 13 }}>或直接粘贴对标文案：</div>
              <TextArea
                rows={10}
                placeholder="粘贴对标直播间文案..."
                value={refScript}
                onChange={e => setRefScript(e.target.value)}
              />
            </>
          )}
          {refScript && (
            <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
              字数：<strong>{countChars(refScript)}</strong> 字（去空格）
              {refScriptLocked && <span style={{ marginLeft: 12, color: 'var(--success)' }}>✓ 已锁定</span>}
            </div>
          )}
          {!refScriptLocked && (
            <div style={{ marginTop: 12 }}>
              <Button
                icon={<LockOutlined />}
                type="default"
                disabled={!refScript.trim()}
                onClick={() => setRefScriptLocked(true)}
              >
                确认锁定对标
              </Button>
            </div>
          )}
          <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={() => { setRefScriptLocked(false); setStep(1); }}>上一步</Button>
            <Button type="primary" disabled={!refScriptLocked} onClick={() => setStep(3)}>
              开始仿写
            </Button>
          </div>
        </div>
      )}

      {/* Step 4 · 生成方案 */}
      {step === 3 && (
        <div>
          {/* 生成按钮 */}
          {chatMessages.length === 0 && (
            <div className="card" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                达人：<strong>{selectedPersona?.name}</strong> &nbsp;|&nbsp;
                产品：<strong>{productName || '（未识别）'}</strong> &nbsp;|&nbsp;
                卖点顺序：<strong>{spOrder}</strong> &nbsp;|&nbsp;
                对标字数：<strong>{countChars(refScript)}</strong> 字
              </p>
              <Button type="primary" size="large" loading={streaming} onClick={handleGenerate}>
                生成开播方案
              </Button>
            </div>
          )}

          {/* 对话区 */}
          {chatMessages.length > 0 && (
            <div
              style={{
                background: '#fff',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: 24,
                minHeight: 300,
                marginBottom: 16,
              }}
            >
              {chatMessages.map((msg, i) => (
                <div key={i} style={{ marginBottom: 20 }}>
                  {msg.role === 'user' ? (
                    <div style={{
                      background: 'var(--gray-50)',
                      borderRadius: 8,
                      padding: '10px 14px',
                      fontSize: 14,
                      color: 'var(--text-secondary)',
                      whiteSpace: 'pre-wrap',
                      maxWidth: '80%',
                    }}>
                      {msg.content}
                    </div>
                  ) : (
                    <div>
                      {msg.content
                        ? <SimpleMarkdown text={msg.content} />
                        : <Spin size="small" tip="AI 生成中..." />
                      }
                    </div>
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}

          {/* 操作栏 */}
          {chatMessages.length > 0 && (
            <div className="card" style={{ padding: 16 }}>
              <TextArea
                rows={3}
                placeholder="告诉 AI 哪里需要修改，或继续追问..."
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                disabled={streaming}
                onPressEnter={e => {
                  if (e.shiftKey) return;
                  e.preventDefault();
                  handleFollowUp();
                }}
              />
              <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Button onClick={() => setStep(2)}>上一步</Button>
                <div style={{ display: 'flex', gap: 8 }}>
                  {hasOutput && (
                    <Button icon={<DownloadOutlined />} onClick={handleExport}>
                      导出终稿 .txt
                    </Button>
                  )}
                  <Button
                    type="primary"
                    loading={streaming}
                    disabled={!userInput.trim()}
                    onClick={handleFollowUp}
                  >
                    发送
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
