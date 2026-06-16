import { useState, useRef, useEffect } from 'react'
import { Button, message } from 'antd'
import { DownloadOutlined, SaveOutlined } from '@ant-design/icons'
import {
  extractFrames,
  transcribeVideo,
  chatStream,
  exportWord,
  saveOutput,
  getConfig,
  type Frame,
} from '../../api/qianchuanEditReview'

const SYSTEM_PROMPT = `你是千川广告剪辑预审专家。视频已经拍完，现在是剪辑阶段。你会同时看到两条视频的**文案转录**和**关键帧截图**（标注了时间戳）。

结合文案和画面一起分析，对比「原版爆款」和「我方版本」，给出剪辑层面的优化建议。

严格限制：文案内容、拍摄角度、演员表演已经无法修改。只提以下剪辑能做的调整：
- 删减/压缩片段（砍掉哪一段，精确到哪句话、第几秒）
- 调整片段顺序（把哪段提前/延后）
- 节奏调整（哪里加快/放慢、转场节奏）
- 字幕/花字建议（哪里加强调字幕、什么样式）
- BGM/音效建议
- 开头剪辑（前3秒怎么剪更抓人）
- **画面插入建议**（在哪个位置插入什么类型的画面，如产品特写、使用效果、对比画面、文字卡片、用户评价截图等）

## 输出格式

### 开头剪辑（前三秒）
原版开头：[画面+文案怎么切入]
我方开头：[画面+文案怎么切入]
剪辑建议：[具体怎么改，比如从第X秒切入、插入什么画面]

### 时长与删减
原版约X秒 vs 我方约X秒，[需要砍掉哪些段落，精确到第几秒到第几秒]

### 节奏问题
[哪里拖沓需要加速、哪里信息太密需要留白、转场是否流畅]

### 画面插入建议
[在第X秒处插入什么画面（产品特写/效果对比/使用场景/文字卡片等），为什么要插]

### 核心问题 Top 3
1. [一句话，限定在剪辑+画面插入能改的范围]
2. [一句话]
3. [一句话]

### 剪辑修改清单
1. [具体操作：剪什么/插什么/调什么]
2. [具体操作]
3. [具体操作]
4. [如有需要继续]

要求：每句话都要有信息量，不要废话。所有建议必须是剪辑师能直接执行的，不要说"重拍""重写文案"。`

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/### (.*)/g, '<h3 style="font-weight:bold;font-size:14px;margin:16px 0 4px">$1</h3>')
    .replace(/## (.*)/g, '<h2 style="font-weight:bold;font-size:16px;margin:20px 0 8px">$1</h2>')
    .replace(/# (.*)/g, '<h1 style="font-weight:bold;font-size:18px;margin:24px 0 8px">$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '<br/>• ')
    .replace(/\n(\d+)\. /g, '<br/>$1. ')
    .replace(/\n\n/g, '</p><p style="margin-top:8px">')
    .replace(/\n/g, '<br/>')
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.7 }}
      dangerouslySetInnerHTML={{ __html: `<p>${html}</p>` }}
    />
  )
}

interface VideoSide {
  file: File | null
  transcript: string
  frames: Frame[]
  duration: number
}

const EMPTY_SIDE: VideoSide = { file: null, transcript: '', frames: [], duration: 0 }

export default function QianChuanEditReviewPage() {
  const [original, setOriginal] = useState<VideoSide>({ ...EMPTY_SIDE })
  const [ours, setOurs] = useState<VideoSide>({ ...EMPTY_SIDE })
  const [processing, setProcessing] = useState<Record<string, string>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [report, setReport] = useState('')
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activePrompt, setActivePrompt] = useState(SYSTEM_PROMPT)
  const reportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getConfig().then(cfg => {
      if (cfg.system_prompt) setActivePrompt(cfg.system_prompt)
    }).catch(() => {/* 读取失败沿用内置 Prompt */})
  }, [])

  async function processVideo(side: 'original' | 'ours') {
    const data = side === 'original' ? original : ours
    const setter = side === 'original' ? setOriginal : setOurs
    if (!data.file) { message.error('请先上传视频文件'); return }

    setProcessing(prev => ({ ...prev, [side]: '截帧中...' }))

    try {
      const frameResult = await extractFrames(data.file, 8)
      setter(prev => ({ ...prev, frames: frameResult.frames, duration: frameResult.duration }))

      setProcessing(prev => ({ ...prev, [side]: '转录文案中...' }))
      const transResult = await transcribeVideo(data.file, 'zh')
      setter(prev => ({ ...prev, transcript: transResult.text }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : '处理失败')
    } finally {
      setProcessing(prev => { const n = { ...prev }; delete n[side]; return n })
    }
  }

  function buildMessage() {
    const parts: Array<{ type: string; text?: string; image_url?: { url: string } }> = []

    let text = `## 原版爆款素材\n**时长**：${original.duration ? `${original.duration}秒` : '未知'}\n**文案**：\n${original.transcript || '未提供'}\n\n`
    if (original.frames.length > 0) {
      text += `**原版关键帧**（${original.frames.length}帧）：\n`
      parts.push({ type: 'text', text })
      original.frames.forEach(f => {
        parts.push({ type: 'text', text: `原版 第${f.time}秒：` })
        parts.push({ type: 'image_url', image_url: { url: f.base64 } })
      })
    } else {
      parts.push({ type: 'text', text })
    }

    text = `\n---\n\n## 我方版本（已拍摄完成）\n**时长**：${ours.duration ? `${ours.duration}秒` : '未知'}\n**文案**：\n${ours.transcript || '未提供'}\n\n`
    if (ours.frames.length > 0) {
      text += `**我方关键帧**（${ours.frames.length}帧）：\n`
      parts.push({ type: 'text', text })
      ours.frames.forEach(f => {
        parts.push({ type: 'text', text: `我方 第${f.time}秒：` })
        parts.push({ type: 'image_url', image_url: { url: f.base64 } })
      })
    } else {
      parts.push({ type: 'text', text })
    }

    return parts
  }

  async function analyze() {
    if (!original.transcript && !ours.transcript && original.frames.length === 0 && ours.frames.length === 0) {
      message.error('请先处理视频（截帧+转录）再预审')
      return
    }
    setAnalyzing(true)
    setReport('')

    try {
      const resp = await chatStream(
        [{ role: 'user', content: buildMessage() }],
        activePrompt,
        'gpt-4o',
        8000,
      )
      if (!resp.ok) throw new Error('AI 分析请求失败')

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应')

      const decoder = new TextDecoder()
      let fullText = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        fullText += decoder.decode(value, { stream: true })
        setReport(fullText)
      }
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '分析出错')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleExportWord() {
    if (!report) return
    setExporting(true)
    try {
      const blob = await exportWord(report, '千川剪辑预审报告')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `千川剪辑预审_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

  async function handleSave() {
    if (!report) return
    setSaving(true)
    try {
      await saveOutput({
        title: `千川剪辑预审_${new Date().toISOString().slice(0, 10)}`,
        report,
        original_duration: original.duration,
        ours_duration: ours.duration,
        original_frame_count: original.frames.length,
        ours_frame_count: ours.frames.length,
      })
      message.success('报告已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  function renderSide(side: 'original' | 'ours') {
    const data = side === 'original' ? original : ours
    const setter = side === 'original' ? setOriginal : setOurs
    const label = side === 'original' ? '原版爆款' : '我方成片'
    const isProcessing = !!processing[side]
    const statusText = processing[side] || ''

    const colors = side === 'original'
      ? { border: '#6ee7b7', dot: '#10b981', text: '#065f46', btn: '#059669' }
      : { border: '#93c5fd', dot: '#3b82f6', text: '#1e3a8a', btn: '#2563eb' }

    return (
      <div style={{ flex: 1, border: `2px solid ${colors.border}`, borderRadius: 12, padding: 20, background: '#fff' }}>
        <h2 style={{ color: colors.text, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 12, height: 12, borderRadius: '50%', background: colors.dot, display: 'inline-block' }} />
          {label}
        </h2>

        <div style={{ marginBottom: 12 }}>
          <div
            style={{ border: '2px dashed #d1d5db', borderRadius: 8, padding: 16, textAlign: 'center', cursor: 'pointer', background: '#fafafa' }}
            onClick={() => document.getElementById(`file-${side}`)?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              const f = e.dataTransfer.files[0]
              if (f && f.type.startsWith('video/')) setter(prev => ({ ...prev, file: f, transcript: '', frames: [], duration: 0 }))
            }}
          >
            <input
              id={`file-${side}`} type="file" accept="video/*" style={{ display: 'none' }}
              onChange={e => {
                const f = e.target.files?.[0] || null
                if (f) setter(prev => ({ ...prev, file: f, transcript: '', frames: [], duration: 0 }))
                else setter({ ...EMPTY_SIDE })
              }}
            />
            {data.file ? (
              <div style={{ fontSize: 13, color: '#374151' }}>
                {data.file.name} <span style={{ color: '#9ca3af' }}>({(data.file.size / 1024 / 1024).toFixed(1)}MB)</span>
                {data.duration > 0 && <span style={{ color: '#9ca3af' }}> · {data.duration}秒</span>}
                <button style={{ marginLeft: 8, color: '#f87171', background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={e => { e.stopPropagation(); setter({ ...EMPTY_SIDE }) }}>✕</button>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: '#9ca3af' }}>拖入或点击上传视频（最大25MB）</div>
            )}
          </div>

          {data.file && (
            <Button type="primary" block style={{ marginTop: 8, background: isProcessing ? '#9ca3af' : colors.btn }}
              disabled={isProcessing} onClick={() => processVideo(side)}>
              {isProcessing ? statusText : data.frames.length > 0 ? '重新处理' : '截帧 + 提取文案'}
            </Button>
          )}
        </div>

        {data.frames.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>已提取 {data.frames.length} 帧截图</div>
            <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 4 }}>
              {data.frames.slice(0, 5).map((f, i) => (
                <img key={i} src={f.base64} alt={`${f.time}s`}
                  style={{ height: 48, borderRadius: 4, border: '1px solid #e5e7eb', flexShrink: 0 }} title={`${f.time}秒`} />
              ))}
              {data.frames.length > 5 && (
                <div style={{ height: 48, width: 48, borderRadius: 4, border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: '#9ca3af', flexShrink: 0 }}>
                  +{data.frames.length - 5}
                </div>
              )}
            </div>
          </div>
        )}

        <div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>文案内容</div>
          <textarea
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, height: 112, resize: 'vertical', boxSizing: 'border-box', outline: 'none', fontFamily: 'inherit' }}
            placeholder="点击上方按钮自动提取，或直接粘贴文案..."
            value={data.transcript}
            onChange={e => setter(prev => ({ ...prev, transcript: e.target.value }))}
          />
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 'bold', color: '#1f2937', margin: 0 }}>千川剪辑预审</h1>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>上传两个视频，AI看画面+文案，给出剪辑和画面插入建议</p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        {renderSide('original')}
        {renderSide('ours')}
      </div>

      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <Button type="primary" size="large"
          style={{ padding: '0 32px', height: 48, fontSize: 16, fontWeight: 'bold', background: analyzing ? '#9ca3af' : 'linear-gradient(to right, #2563eb, #4f46e5)', border: 'none' }}
          disabled={analyzing} onClick={analyze}>
          {analyzing ? '正在预审...' : '开始预审'}
        </Button>
      </div>

      {report && (
        <div ref={reportRef} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 17, fontWeight: 'bold', color: '#1f2937', margin: 0 }}>剪辑预审报告</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button icon={<DownloadOutlined />}
                style={{ background: exporting ? '#9ca3af' : '#16a34a', color: '#fff', border: 'none' }}
                disabled={exporting} onClick={handleExportWord}>
                {exporting ? '导出中...' : '导出 Word'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" disabled={saving} onClick={handleSave}>
                {saving ? '保存中...' : '保存报告'}
              </Button>
            </div>
          </div>
          <div style={{ borderTop: '1px solid #f3f4f6', paddingTop: 16 }}>
            <SimpleMarkdown text={report} />
          </div>
        </div>
      )}
    </div>
  )
}
