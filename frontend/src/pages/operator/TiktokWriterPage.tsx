/**
 * TikTok 脚本仿写页面（tiktok-writer）
 *
 * 5 步工作流：
 *   Step 1 · Source      — 粘贴链接 / 文案 / 点赞数
 *   Step 2 · Validate    — AI 评估 Opening Hook + 选择人设
 *   Step 3 · Structure   — AI 分析结构，解析 Opening
 *   Step 4 · Rewrite     — AI 仿写 Body + 多轮迭代
 *   Step 5 · Export      — 编辑 finalBody + 导出 Word
 */
import { useState, useEffect } from 'react';
import { Button, Input, Select, Steps, message, Radio, Alert } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { chatStream, exportWord, getPersonas, getTiktokWriterConfig, type TiktokWriterConfig } from '../../api/tiktokWriter';
import type { Persona, StepState } from '../../types/tiktokWriter';

const { TextArea } = Input;

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function buildHookEvalPrompt(): string {
  return `You are a TikTok content strategist. Evaluate the opening hook of this TikTok script.

The "opening" is the first 1-3 sentences that grab attention.

Your task:
1. Identify the exact opening (first 1-3 sentences)
2. Rate if this opening would make a general audience stop scrolling and keep watching
3. Answer with PASS or FAIL

Format your response EXACTLY like this:
OPENING: [copy the exact opening sentences here]
---
VERDICT: [PASS or FAIL]
REASON: [1-2 sentences explaining why]`;
}

function buildStructurePrompt(): string {
  return `You are a TikTok script structure analyst. Analyze this TikTok script and break it into clear structural sections.

CRITICAL TASK: You must clearly separate the OPENING (hook) from the BODY.

Format your response EXACTLY like this:

===OPENING_START===
[paste the exact opening sentences here, word for word, no changes]
===OPENING_END===

===STRUCTURE===
1. Opening hook: [describe the technique used]
2. [Section name]: [describe what happens]
3. [Section name]: [describe what happens]
...
===STRUCTURE_END===

===NOTES===
- Key storytelling techniques used
- Tone and pacing observations
===NOTES_END===`;
}

function buildRewritePrompt(
  mode: 'ai' | 'user',
  originalWordCount: number,
  openingWordCount: number,
  structureAnalysis: string,
  persona: Persona | null,
  userIdeas: string,
): string {
  const bodyLimit = originalWordCount - openingWordCount;
  const personaContext = persona
    ? `\n\nCreator persona (light reference only):\nName: ${persona.name}\nStyle: ${persona.soul.slice(0, 500)}`
    : '';

  if (mode === 'ai') {
    return `You are a TikTok script rewriter. Your job is to rewrite ONLY the body of a TikTok script.

IRON RULES — VIOLATING ANY OF THESE IS A FAILURE:
1. DO NOT output the opening. The opening is handled separately and must not appear in your output.
2. Your output word count MUST be LESS than or equal to ${originalWordCount} words total (opening + your body combined). The opening is ${openingWordCount} words, so your body must be ≤ ${bodyLimit} words.
3. The content must be DIFFERENTIATED — not a paraphrase, not a synonym swap. Bring fresh angles, new examples, or unique perspective.
4. Maintain the SAME structure and flow as the original body.
5. The tone should feel natural, engaging, and native-level English for TikTok.
6. Do NOT be generic or mediocre. Every sentence should earn its place.

Output ONLY the rewritten body text. No headers, no labels, no explanations.${personaContext}

ORIGINAL STRUCTURE FOR REFERENCE:
${structureAnalysis}`;
  }

  return `You are a TikTok script rewriter. Your job is to rewrite ONLY the body of a TikTok script, incorporating the user's creative direction.

IRON RULES — VIOLATING ANY OF THESE IS A FAILURE:
1. DO NOT output the opening. The opening is handled separately and must not appear in your output.
2. Your output word count MUST be LESS than or equal to ${originalWordCount} words total (opening + your body combined). The opening is ${openingWordCount} words, so your body must be ≤ ${bodyLimit} words.
3. The USER'S IDEAS take priority. The reference script is secondary.
4. Maintain the SAME structure and flow as the original body.
5. The tone should feel natural, engaging, and native-level English for TikTok.

Output ONLY the rewritten body text. No headers, no labels, no explanations.${personaContext}

ORIGINAL STRUCTURE FOR REFERENCE:
${structureAnalysis}

USER'S CREATIVE DIRECTION:
${userIdeas}`;
}

function buildIteratePrompt(lockedOpening: string, aiBody: string, bodyLimit: number): string {
  return `You are revising a TikTok script body based on user feedback.

IRON RULES:
1. DO NOT include the opening in your output. Opening is: "${lockedOpening}"
2. Word count of your body must be ≤ ${bodyLimit} words.
3. Apply the user's feedback precisely.
4. Output ONLY the revised body text, nothing else.

Current body being revised:
${aiBody}`;
}

function extractOpening(aiOutput: string, transcript: string): { opening: string; body: string } {
  const startTag = '===OPENING_START===';
  const endTag = '===OPENING_END===';
  const startIdx = aiOutput.indexOf(startTag);
  const endIdx = aiOutput.indexOf(endTag);

  if (startIdx !== -1 && endIdx !== -1) {
    const opening = aiOutput.slice(startIdx + startTag.length, endIdx).trim();
    const pos = transcript.indexOf(opening);
    if (pos !== -1) {
      return { opening, body: transcript.slice(pos + opening.length).trim() };
    }
    const openWc = wordCount(opening);
    const words = transcript.split(/\s+/);
    return { opening, body: words.slice(openWc).join(' ') };
  }
  const sentences = transcript.split(/(?<=[.!?])\s+/);
  const opening = sentences.slice(0, 2).join(' ');
  return { opening, body: sentences.slice(2).join(' ') };
}

async function readStream(resp: Response, onChunk: (chunk: string) => void): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onChunk(chunk);
  }
  return full;
}

const INITIAL_STATE: StepState = {
  tiktokUrl: '',
  transcript: '',
  likesCount: '',
  selectedPersona: null,
  hookEvaluation: '',
  hookVerdict: null,
  lockedOpening: '',
  structureAnalysis: '',
  aiBody: '',
  finalBody: '',
  rewriteMode: 'ai',
  userIdeas: '',
  chatMessages: [],
  isStreaming: false,
  currentStep: 1,
};

export default function TiktokWriterPage() {
  const [state, setState] = useState<StepState>(INITIAL_STATE);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personasLoaded, setPersonasLoaded] = useState(false);
  const [iterateInput, setIterateInput] = useState('');
  const [streamBuffer, setStreamBuffer] = useState('');
  const [toolConfig, setToolConfig] = useState<TiktokWriterConfig | null>(null);

  function update(patch: Partial<StepState>) {
    setState(prev => ({ ...prev, ...patch }));
  }

  useEffect(() => {
    getTiktokWriterConfig()
      .then(setToolConfig)
      .catch(() => {}); // 加载失败静默处理，fallback 到前端硬编码 Prompt
  }, []);

  const likesNum = parseInt(state.likesCount.replace(/,/g, ''), 10);
  const likesOk = !isNaN(likesNum) && likesNum >= 100_000;
  const step1Ok = state.transcript.trim().length > 0 && likesOk;

  async function handleEvaluateHook() {
    update({ isStreaming: true, hookEvaluation: '', hookVerdict: null });
    setStreamBuffer('');
    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: state.transcript }],
        systemPrompt: toolConfig?.hook_eval_prompt ?? buildHookEvalPrompt(),
        model: toolConfig?.model_id,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      const verdict = full.includes('VERDICT: PASS') ? 'PASS' : 'FAIL';
      update({ hookEvaluation: full, hookVerdict: verdict, isStreaming: false });
      setStreamBuffer('');
    } catch (e) {
      message.error(`评估失败：${e}`);
      update({ isStreaming: false });
    }
  }

  async function loadPersonas() {
    if (personasLoaded) return;
    try {
      const data = await getPersonas();
      setPersonas(data.personas);
      setPersonasLoaded(true);
    } catch {
      message.error('加载人设列表失败');
    }
  }

  async function handleAnalyzeStructure() {
    update({ isStreaming: true, structureAnalysis: '', lockedOpening: '' });
    setStreamBuffer('');
    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: state.transcript }],
        systemPrompt: toolConfig?.structure_prompt ?? buildStructurePrompt(),
        model: toolConfig?.model_id,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      const { opening } = extractOpening(full, state.transcript);
      update({ structureAnalysis: full, lockedOpening: opening, isStreaming: false, currentStep: 4 });
      setStreamBuffer('');
    } catch (e) {
      message.error(`结构分析失败：${e}`);
      update({ isStreaming: false });
    }
  }

  async function handleGenerateBody() {
    const originalWc = wordCount(state.transcript);
    const openingWc = wordCount(state.lockedOpening);
    const bodyText = state.transcript
      .slice(state.transcript.indexOf(state.lockedOpening) + state.lockedOpening.length)
      .trim();

    const systemPrompt = buildRewritePrompt(
      state.rewriteMode, originalWc, openingWc, state.structureAnalysis,
      state.selectedPersona, state.userIdeas,
    );
    const userContent = state.rewriteMode === 'ai'
      ? `Here is the original body (without opening):\n\n${bodyText}`
      : `Here is the original body (without opening):\n\n${bodyText}\n\nMy ideas:\n${state.userIdeas}`;

    update({ isStreaming: true, aiBody: '' });
    setStreamBuffer('');
    try {
      const resp = await chatStream({
        messages: [{ role: 'user', content: userContent }],
        systemPrompt,
        createJob: true,
        jobContext: {
          tiktokUrl: state.tiktokUrl,
          likesCount: state.likesCount,
          selectedPersonaName: state.selectedPersona?.name ?? '',
        },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      update({
        aiBody: full,
        chatMessages: [{ role: 'user', content: userContent }, { role: 'assistant', content: full }],
        isStreaming: false,
      });
      setStreamBuffer('');
    } catch (e) {
      message.error(`生成失败：${e}`);
      update({ isStreaming: false });
    }
  }

  async function handleIterate() {
    if (!iterateInput.trim()) return;
    const originalWc = wordCount(state.transcript);
    const openingWc = wordCount(state.lockedOpening);
    const bodyLimit = originalWc - openingWc;
    const newMessages = [...state.chatMessages, { role: 'user' as const, content: iterateInput }];

    update({ isStreaming: true });
    setStreamBuffer('');
    setIterateInput('');
    try {
      const resp = await chatStream({
        messages: newMessages,
        systemPrompt: buildIteratePrompt(state.lockedOpening, state.aiBody, bodyLimit),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const full = await readStream(resp, chunk => setStreamBuffer(prev => prev + chunk));
      update({
        aiBody: full,
        chatMessages: [...newMessages, { role: 'assistant', content: full }],
        isStreaming: false,
      });
      setStreamBuffer('');
    } catch (e) {
      message.error(`修改失败：${e}`);
      update({ isStreaming: false });
    }
  }

  async function handleExport() {
    const content = `${state.lockedOpening}\n\n${state.finalBody || state.aiBody}`;
    try {
      const blob = await exportWord({
        personaName: state.selectedPersona?.name ?? 'TikTok',
        topic: state.tiktokUrl,
        content,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const date = new Date().toISOString().slice(0, 10);
      a.download = `TikTok_Script_${state.selectedPersona?.name ?? 'TikTok'}_${date}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('Word 文档已下载，已保存至产出中心');
    } catch (e) {
      message.error(`导出失败：${e}`);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 'var(--sp-6)' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">TikTok 脚本仿写</h1>
          <p className="page-desc">分析 TikTok 视频结构，AI 仿写新 Body，支持多轮迭代</p>
        </div>
      </div>

      <Steps
        current={state.currentStep - 1}
        items={[
          { title: 'Source' }, { title: 'Validate' }, { title: 'Structure' },
          { title: 'Rewrite' }, { title: 'Export' },
        ]}
        style={{ marginBottom: 'var(--sp-6)' }}
      />

      {/* Step 1 */}
      {state.currentStep >= 1 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 1 · Source</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>TikTok 视频链接</label>
            <Input
              placeholder="https://www.tiktok.com/@..."
              value={state.tiktokUrl}
              onChange={e => update({ tiktokUrl: e.target.value })}
            />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>视频文案 *</label>
            <TextArea rows={8} placeholder="粘贴视频完整文案..." value={state.transcript}
              onChange={e => update({ transcript: e.target.value })} />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>点赞数 *（需 ≥ 100,000）</label>
            <Input placeholder="200000" value={state.likesCount}
              onChange={e => update({ likesCount: e.target.value })}
              style={{ width: 200 }}
              status={state.likesCount && !likesOk ? 'error' : undefined} />
            {state.likesCount && !likesOk && (
              <div style={{ color: 'var(--red-500)', fontSize: 12, marginTop: 4 }}>点赞数需 ≥ 100,000</div>
            )}
          </div>
          <Button type="primary" disabled={!step1Ok} onClick={() => update({ currentStep: 2 })}>
            Continue →
          </Button>
        </div>
      )}

      {/* Step 2 */}
      {state.currentStep >= 2 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 2 · Validate Opening Hook</h3>
          <Button type="primary" loading={state.isStreaming} onClick={handleEvaluateHook}
            style={{ marginBottom: 'var(--sp-3)' }}>
            Evaluate Opening Hook
          </Button>
          {(state.hookEvaluation || streamBuffer) && (
            <div style={{ background: 'var(--gray-50)', padding: 'var(--sp-3)', borderRadius: 8,
              fontFamily: 'monospace', whiteSpace: 'pre-wrap', marginBottom: 'var(--sp-3)' }}>
              {state.isStreaming ? streamBuffer : state.hookEvaluation}
            </div>
          )}
          {state.hookVerdict && (
            <Alert type={state.hookVerdict === 'PASS' ? 'success' : 'warning'}
              message={`Verdict: ${state.hookVerdict}`} style={{ marginBottom: 'var(--sp-3)' }} />
          )}
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>创作者人设（可选）</label>
            <Select style={{ width: '100%' }} placeholder="选择人设（可跳过）" allowClear
              onDropdownVisibleChange={open => open && loadPersonas()}
              options={personas.map(p => ({ value: p.name, label: p.name }))}
              onChange={val => update({ selectedPersona: personas.find(p => p.name === val) ?? null })} />
          </div>
          <Button type="primary" disabled={!state.hookVerdict} onClick={() => update({ currentStep: 3 })}>
            Continue →
          </Button>
        </div>
      )}

      {/* Step 3 */}
      {state.currentStep >= 3 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 3 · Analyze Structure</h3>
          <Button type="primary" loading={state.isStreaming} onClick={handleAnalyzeStructure}
            style={{ marginBottom: 'var(--sp-3)' }}>
            Analyze Structure
          </Button>
          {(state.structureAnalysis || (state.isStreaming && streamBuffer)) && (
            <div style={{ background: 'var(--gray-50)', padding: 'var(--sp-3)', borderRadius: 8,
              fontFamily: 'monospace', whiteSpace: 'pre-wrap', fontSize: 12, marginBottom: 'var(--sp-3)' }}>
              {state.isStreaming ? streamBuffer : state.structureAnalysis}
            </div>
          )}
          {state.lockedOpening && (
            <Alert type="info" message="Opening Locked"
              description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{state.lockedOpening}</pre>}
              style={{ marginBottom: 'var(--sp-3)' }} />
          )}
        </div>
      )}

      {/* Step 4 */}
      {state.currentStep >= 4 && (
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 4 · Rewrite Body</h3>
          <Radio.Group value={state.rewriteMode}
            onChange={e => update({ rewriteMode: e.target.value })}
            style={{ marginBottom: 'var(--sp-3)' }}>
            <Radio.Button value="ai">AI 直写</Radio.Button>
            <Radio.Button value="user">提供方向</Radio.Button>
          </Radio.Group>
          {state.rewriteMode === 'user' && (
            <TextArea rows={3} placeholder="描述你的创作方向..." value={state.userIdeas}
              onChange={e => update({ userIdeas: e.target.value })}
              style={{ marginBottom: 'var(--sp-3)' }} />
          )}
          <Button type="primary" loading={state.isStreaming} icon={<ReloadOutlined />}
            onClick={handleGenerateBody} style={{ marginBottom: 'var(--sp-3)' }}>
            Generate Body
          </Button>
          {(state.aiBody || (state.isStreaming && streamBuffer)) && (
            <>
              <div style={{ background: 'var(--gray-50)', padding: 'var(--sp-3)', borderRadius: 8,
                whiteSpace: 'pre-wrap', marginBottom: 'var(--sp-3)', minHeight: 120 }}>
                {state.isStreaming ? streamBuffer : state.aiBody}
              </div>
              {!state.isStreaming && state.aiBody && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 'var(--sp-3)' }}>
                  <Input placeholder="告诉 AI 如何修改..." value={iterateInput}
                    onChange={e => setIterateInput(e.target.value)} onPressEnter={handleIterate} />
                  <Button onClick={handleIterate} disabled={!iterateInput.trim()}>修改</Button>
                </div>
              )}
              {!state.isStreaming && state.aiBody && (
                <Button type="primary" onClick={() => update({ finalBody: state.aiBody, currentStep: 5 })}>
                  Use This Body →
                </Button>
              )}
            </>
          )}
        </div>
      )}

      {/* Step 5 */}
      {state.currentStep >= 5 && (
        <div className="card">
          <h3 style={{ marginBottom: 'var(--sp-3)' }}>Step 5 · Export</h3>
          <div style={{ marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Final Body（可直接编辑）</label>
            <TextArea rows={12} value={state.finalBody || state.aiBody}
              onChange={e => update({ finalBody: e.target.value })} />
          </div>
          <div style={{ marginBottom: 'var(--sp-3)', color: 'var(--gray-500)', fontSize: 12 }}>
            完整脚本词数：{wordCount(`${state.lockedOpening}\n\n${state.finalBody || state.aiBody}`)} words
          </div>
          <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={handleExport}>
            Export Word Document
          </Button>
        </div>
      )}
    </div>
  );
}
