# M2 Sprint 16 — 前端任务：种草内容仿写（seeding-writer）

> 状态：**待派 subagent 实施**
> 对应需求文档：`docs/pm/M2_Sprint16_seeding-writer_需求文档.md`
> 对应分支：`migrate/seeding-writer`
> 参照样板：`frontend/docs/tasks/M2_Sprint15_前端任务_persona-writer_v1.md`（最接近的迁移）

---

## 一、范围（本次前端任务）

涵盖种草内容仿写工具迁移的所有前端工作：
- `types/seedingWriter.ts` 类型定义
- `api/seedingWriter.ts` 22 函数（20 运营端 + 2 管理端）
- `SeedingWriterPage.tsx` **4 步向导**主页面（新建）
- `SeedingWriterConfigTab.tsx` 管理端配置 Tab（6 Prompt + 2 模型 + Switch）
- `App.tsx` 加 `/workspace/seeding-writer` 路由
- `HomePage.tsx` 创作中心入口加卡片
- `WorkspaceConfigPage.tsx` Tab 注册
- `SeedingWriterPage.test.tsx` 20+ 用例全绿
- 全量回归通过，`tsc --noEmit` exit 0

---

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 类型定义 + API 层（22 函数）| `frontend/src/types/seedingWriter.ts` + `frontend/src/api/seedingWriter.ts` | ⏳ |
| F2 | 运营端 4 步向导主页面（新建）| `frontend/src/pages/operator/SeedingWriterPage.tsx` | ⏳ |
| F3 | 管理端配置 Tab | `frontend/src/pages/admin/SeedingWriterConfigTab.tsx` | ⏳ |
| F4 | App.tsx 加路由 `/workspace/seeding-writer` | `frontend/src/App.tsx` | ⏳ |
| F5 | HomePage.tsx 加创作中心入口卡片 | `frontend/src/pages/operator/HomePage.tsx` | ⏳ |
| F6 | WorkspaceConfigPage Tab 注册 | `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | ⏳ |
| F7 | 组件测试 20+ 用例 | `frontend/src/__tests__/components/pages/SeedingWriterPage.test.tsx` | ⏳ |
| F8 | 任务文档（本文件）| `frontend/docs/tasks/M2_Sprint16_前端任务_seeding-writer.md` | ⏳ |

---

## 三、SeedingWriterPage 实现要点

### 3.1 4 步向导业务逻辑（忠于需求文档 §四）

| Step | 用户操作 | 关键交互 |
|------|---------|---------|
| 1. 选达人 + 素材库 | 1a 下拉选达人（必选，显示 content_plan 预览）<br>1b 可选维护素材库（粘贴文本 / 抖音链接导入 / 删除）| 素材库面板折叠展开；3 个 type 按钮（种草爆款/对标种草/风格参考）|
| 2. 产品信息 | 2a 选已有产品 / 新建产品<br>2b 上传 PDF/Word/Excel/PPT AI 解析<br>2c AI 卖点讨论流式<br>2d 点"采用卖点到表单"<br>2e 填 6 字段表单 | productValid = name+sellingPoints 非空 + spApplied=true 才能下一步 |
| 3. 对标验证 | 3.1 粘贴抖音链接 → POST /fetch-video<br>3.2 ASR submit → 前端每 5s 轮询 poll（max 60 次）<br>3.3 文案确认（可修改）<br>3.4 自动 POST /analyze-structure 流式 | ASR 进度显示"已等待 N 秒" |
| 4. 种草仿写 | 4.1 选种草角度（沿用/自定义/AI 推荐）<br>4.2 POST /chat scene=writing 流式写作<br>4.3 字数校验（超字自动 trim）<br>4.4 多轮迭代 POST /chat scene=iteration<br>4.5 导出终稿（clipboard 复制）<br>4.6 保存历史 | 3 个动作按钮：保存 / .txt / .docx |

### 3.2 状态管理（useState 列表）

参照 persona-writer，扩展为 4 步状态：

```typescript
const [step, setStep] = useState(1)  // 1/2/3/4
// Step 1
const [personas, setPersonas] = useState<PersonaOption[]>([])
const [selectedPersonaId, setSelectedPersonaId] = useState<number | null>(null)
const [references, setReferences] = useState<Reference[]>([])
const [showRefForm, setShowRefForm] = useState(false)
const [refType, setRefType] = useState<'种草爆款' | '对标种草' | '风格参考'>('种草爆款')
const [refTitle, setRefTitle] = useState('')
const [refContent, setRefContent] = useState('')
const [refLikes, setRefLikes] = useState('')
// Step 2
const [products, setProducts] = useState<Product[]>([])
const [selectedProductId, setSelectedProductId] = useState<number | null>(null)
const [product, setProduct] = useState<ProductInfo>(emptyProduct)
const [spChat, setSpChat] = useState<ChatMsg[]>([])
const [spInput, setSpInput] = useState('')
const [spApplied, setSpApplied] = useState(false)
const [uploadingDoc, setUploadingDoc] = useState(false)
// Step 3
const [shareUrl, setShareUrl] = useState('')
const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)
const [transcript, setTranscript] = useState('')
const [transcriptConfirmed, setTranscriptConfirmed] = useState(false)
const [asrTaskId, setAsrTaskId] = useState('')
const [asrPolling, setAsrPolling] = useState(false)
const [structureAnalysis, setStructureAnalysis] = useState('')
// Step 4
const [topicMode, setTopicMode] = useState<'same' | 'custom' | 'ai' | null>(null)
const [customTopic, setCustomTopic] = useState('')
const [aiTopics, setAiTopics] = useState('')
const [chosenTopic, setChosenTopic] = useState('')
const [chatMessages, setChatMessages] = useState<ChatMsg[]>([])
const [chatInput, setChatInput] = useState('')
// Common
const [loading, setLoading] = useState('')
const [error, setError] = useState('')
```

### 3.3 ASR 轮询实现

```typescript
async function handleFetchVideoAndTranscribe() {
  setLoading('解析视频中...')
  const video = await fetchVideo(shareUrl)
  setVideoInfo(video)

  setLoading('上传视频并提交转录...')
  const { task_id } = await submitTranscribe(video.play_url)
  setAsrTaskId(task_id)

  setLoading('转录中，请稍候...')
  setAsrPolling(true)
  let attempts = 0
  while (attempts < 60) {
    await new Promise(r => setTimeout(r, 5000))
    attempts++
    setLoading(`转录中，请稍候...（已等待 ${attempts * 5} 秒）`)
    const result = await pollTranscribe(task_id)
    if (result.status === 'done') {
      setTranscript(result.text)
      setLoading('')
      break
    }
    if (result.status !== 'processing') {
      throw new Error('转录失败: ' + JSON.stringify(result))
    }
  }
  if (attempts >= 60) throw new Error('转录超时（5 分钟），请重试或手动粘贴文案')
  setAsrPolling(false)
}
```

### 3.4 文档上传（multipart 例外）

```typescript
async function handleUploadProductDoc(files: File[]) {
  setUploadingDoc(true)
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  // 注意：multipart 例外不走 request.ts，但要带 Authorization header
  const token = localStorage.getItem('token')
  const res = await fetch('/api/tools/seeding-writer/products/parse-document', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,  // 不要设 Content-Type，让浏览器自动加 multipart boundary
  })
  const data = await res.json()
  if (data.success) {
    setProduct({
      name: data.data.name || '',
      category: data.data.category || '',
      // ...其他字段
    })
    // 自动触发 AI 卖点讨论
    startSellingPointsChat(data.data._rawText, data.data)
  }
  setUploadingDoc(false)
}
```

### 3.5 AI 卖点讨论（流式）

```typescript
async function startSellingPointsChat(rawText: string, info: ProductInfo) {
  const userMsg = { role: 'user', content: `以下是产品资料原文：\n\n${rawText.slice(0, 4000)}\n\nAI 初步提取的产品信息：\n产品名：${info.name}\n品类：${info.category}\n价格：${info.price}\n目标人群：${info.targetAudience}\n\n请站在消费者角度，帮我找出最能打动人购买的3个核心卖点。` }
  const msgs = [userMsg]
  setSpChat(msgs); setSpApplied(false)

  await extractSellingPointsStream(
    { raw_text: rawText.slice(0, 4000), preliminary_info: info },
    (full: string) => setSpChat([...msgs, { role: 'assistant', content: full }])
  )
}

function handleApplySellingPoints() {
  const lastAssistant = [...spChat].reverse().find(m => m.role === 'assistant')
  if (!lastAssistant) return
  // 正则提取【最终卖点】
  const finalMatch = lastAssistant.content.match(/【最终卖点】([\s\S]*?)$/m)
  if (finalMatch) {
    setProduct(prev => ({ ...prev, sellingPoints: finalMatch[1].trim() }))
  } else {
    // fallback：提取数字列表
    const lines = lastAssistant.content.split('\n').filter(l => /^\d+[\.\、]/.test(l.trim()))
    if (lines.length > 0) {
      setProduct(prev => ({ ...prev, sellingPoints: lines.join('\n') }))
    }
  }
  setSpApplied(true)
}
```

### 3.6 字数校验（超字自动 trim）

```typescript
function countChineseChars(text: string): number {
  // 提取脚本正文（去掉自检表 markdown），统计非空白字符
  return extractScriptText(text).length
}

async function autoTrimIfTooLong(
  assistantText: string,
  targetMax: number,
  allMessages: ChatMsg[],
  systemPrompt: string,
  onUpdate: (msgs: ChatMsg[]) => void,
): Promise<string> {
  const actual = countChineseChars(assistantText)
  if (actual <= targetMax || targetMax <= 0) return assistantText

  const trimMsg: ChatMsg = {
    role: 'user',
    content: `脚本超字数了。当前约${actual}字，上限${targetMax}字，需要砍掉${actual - targetMax}字以上。请精简内容，压到${targetMax}字以内。直接输出压缩后的完整脚本+自检表，不要解释。`
  }
  const trimMessages = [...allMessages, trimMsg]
  onUpdate(trimMessages)
  let trimmedText = ''
  await chatStream(
    { scene: 'iteration', messages: trimMessages.map(m => ({ role: m.role, content: m.content })), /* ...其他参数 */ },
    (text: string) => {
      trimmedText = text
      onUpdate([...trimMessages, { role: 'assistant', content: text }])
    }
  )
  return trimmedText
}
```

### 3.7 素材库面板（折叠展开）

```tsx
{selectedPersonaId && (
  <Card title={`日常素材库维护（${references.length} 条）`} bordered={false}>
    <Space wrap>
      <Button onClick={() => { setRefType('种草爆款'); setShowRefForm(true) }}>上传种草爆款文案</Button>
      <Button onClick={() => { setRefType('对标种草'); setShowRefForm(true) }}>上传对标种草内容</Button>
      <Button onClick={() => { setRefType('风格参考'); setShowRefForm(true) }}>上传风格参考</Button>
      <Button onClick={() => setShowImportDouyinModal(true)}>从抖音链接导入</Button>
    </Space>

    {showRefForm && (
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label="标题（必填）"><Input value={refTitle} onChange={e => setRefTitle(e.target.value)} /></Form.Item>
        <Form.Item label="点赞数（选填）"><Input value={refLikes} onChange={e => setRefLikes(e.target.value)} /></Form.Item>
        <Form.Item label="正文（必填）"><Input.TextArea rows={6} value={refContent} onChange={e => setRefContent(e.target.value)} /></Form.Item>
        <Button type="primary" onClick={handleAddReference}>保存</Button>
      </Form>
    )}

    <List
      dataSource={references}
      renderItem={(ref, i) => (
        <List.Item actions={[<Button danger size="small" onClick={() => handleDeleteReference(ref.id)}>删除</Button>]}>
          <List.Item.Meta title={ref.title} description={`${ref.type || ''} · ${ref.likes ? (ref.likes / 10000).toFixed(1) + '万赞' : ''}`} />
        </List.Item>
      )}
    />
  </Card>
)}
```

### 3.8 产品库面板

```tsx
<Card title="产品信息" bordered={false}>
  <Space direction="vertical" style={{ width: '100%' }}>
    <Select
      style={{ width: '100%' }}
      placeholder="从团队产品库选已有产品（公司共享）"
      value={selectedProductId}
      onChange={handleSelectProduct}
      showSearch optionFilterProp="label"
      options={products.map(p => ({ label: p.name, value: p.id }))}
    />
    <input type="file" ref={fileInputRef} multiple accept=".pdf,.docx,.xlsx,.pptx,.txt,.md" hidden onChange={handleUploadProductDoc} />
    <Button icon={<UploadOutlined />} onClick={() => fileInputRef.current?.click()}>上传产品文档（AI 解析）</Button>

    <Form layout="vertical">
      <Form.Item label="产品名称 *"><Input value={product.name} onChange={e => setProduct({ ...product, name: e.target.value })} /></Form.Item>
      {/* 5 个字段：category / price / targetAudience / sellingPoints / scenario */}
    </Form>

    {spChat.length > 0 && (
      <Card type="inner" title="AI 卖点讨论" extra={<Button size="small" onClick={handleApplySellingPoints}>采用卖点到表单</Button>}>
        {/* chat 渲染 */}
      </Card>
    )}

    {spChat.length > 0 && !spApplied && (
      <Typography.Text type="danger">请先点击「采用卖点到表单」确认最终卖点，才能进入下一步</Typography.Text>
    )}

    <Button type="primary" disabled={!productValid || (spChat.length > 0 && !spApplied)} onClick={() => setStep(3)}>
      下一步：对标验证 →
    </Button>
  </Space>
</Card>
```

### 3.9 导出文件命名

```
种草脚本_${persona.name}_${product.name}_${topic || '终稿'}.txt
种草脚本_${persona.name}_${product.name}_${topic || '终稿'}.docx
```

- `.txt`：前端 Blob 下载（不走后端）
- `.docx`：调 `/api/tools/seeding-writer/export-word` 返回 StreamingResponse

### 3.10 CSS 规范

- 使用项目 CSS 变量（`var(--brand)` / `card` / `btn` 等）
- **禁止 Tailwind class**（项目未安装）
- 使用 Ant Design 5 组件（Steps / Select / Input.TextArea / Radio / Button / Upload / App.useApp）

---

## 四、SeedingWriterConfigTab 实现要点

参照 `PersonaWriterConfigTab.tsx` 模式，字段更丰富：

| 字段 | 组件 | 说明 |
|------|------|------|
| `sp_system_prompt` | TextArea rows=10 | 卖点提取系统 Prompt |
| `parse_product_prompt` | TextArea rows=8 | 文档解析 Prompt（固定 JSON 输出）|
| `structure_analysis_prompt` | TextArea rows=8 | 结构拆解 Prompt（light 模型）|
| `ai_recommend_prompt` | TextArea rows=8 | AI 推荐角度 Prompt（light 模型）|
| `writing_prompt` | TextArea rows=16 | 写作 Prompt（heavy 模型）|
| `iteration_prompt` | TextArea rows=12 | 迭代 Prompt（heavy 模型）|
| `light_model_id` | Select allowClear | 默认 claude-haiku-4-5（id=2）|
| `heavy_model_id` | Select allowClear | 默认 claude-opus-4-6（id=4）|
| `is_active` | Switch | 配置启用开关 |

调用：
- GET `/api/admin/seeding-writer/configs`（通常返回 1 条 config_key='default'）
- PUT `/api/admin/seeding-writer/configs/default`

Modal 使用 `destroyOnHidden`（antd 5，不用 `destroyOnClose`）。

---

## 五、API 层 22 函数

### 5.1 运营端 20 函数

| 函数 | 方法 | 路径 | 例外 |
|------|------|------|------|
| `getPersonas()` | GET | `/api/tools/seeding-writer/kols/personas` | — |
| `getReferences(kolId)` | GET | `/api/tools/seeding-writer/references?kol_id=X` | — |
| `createReference(body)` | POST | `/api/tools/seeding-writer/references` | — |
| `importReferenceFromDouyin(body)` | POST | `/api/tools/seeding-writer/references/import-from-douyin` | — |
| `deleteReference(id)` | DELETE | `/api/tools/seeding-writer/references/{id}` | — |
| `getProducts(page,pageSize,search)` | GET | `/api/tools/seeding-writer/products` | — |
| `createProduct(body)` | POST | `/api/tools/seeding-writer/products` | — |
| `updateProduct(id, body)` | PUT | `/api/tools/seeding-writer/products/{id}` | — |
| `deleteProduct(id)` | DELETE | `/api/tools/seeding-writer/products/{id}` | — |
| `parseProductDocument(files)` | POST | `/api/tools/seeding-writer/products/parse-document` | multipart（裸 fetch）|
| `extractSellingPointsStream(body, onChunk)` | POST | `/api/tools/seeding-writer/products/extract-selling-points` | SSE fetch |
| `fetchVideo(share_url)` | POST | `/api/tools/seeding-writer/fetch-video` | — |
| `submitTranscribe(play_url)` | POST | `/api/tools/seeding-writer/transcribe/submit` | — |
| `pollTranscribe(task_id)` | POST | `/api/tools/seeding-writer/transcribe/poll` | — |
| `analyzeStructureStream(body, onChunk)` | POST | `/api/tools/seeding-writer/analyze-structure` | SSE fetch |
| `aiRecommendStream(body, onChunk)` | POST | `/api/tools/seeding-writer/ai-recommend` | SSE fetch |
| `chatStream(body, onChunk)` | POST | `/api/tools/seeding-writer/chat` | SSE fetch |
| `saveOutput(body)` | POST | `/api/tools/seeding-writer/save-output` | — |
| `exportWord(body)` | POST | `/api/tools/seeding-writer/export-word` | Blob |
| `getOutputs(page,pageSize)` | GET | `/api/tools/seeding-writer/outputs` | — |

### 5.2 管理端 2 函数

| 函数 | 方法 | 路径 |
|------|------|------|
| `getConfigs()` | GET | `/api/admin/seeding-writer/configs` |
| `updateConfig(configKey, payload)` | PUT | `/api/admin/seeding-writer/configs/${configKey}` |

### 5.3 红线 #3 合规

所有 JSON 调用走 `request.ts`（`import { get, post, put, del } from './request'`）。例外：
- **SSE 4 个**：extractSellingPointsStream / analyzeStructureStream / aiRecommendStream / chatStream
- **multipart 1 个**：parseProductDocument（裸 fetch + FormData + Authorization header）
- **Blob 1 个**：exportWord

SSE fetch 调用前加注释 `// SSE 流式：resp.body.getReader()（例外不走 request.ts）`，确保 conventionGuard 扫描命中。

---

## 六、测试覆盖（SeedingWriterPage.test.tsx，20+ 用例）

### 6.1 SeedingWriterPage（17 用例）

| 用例 | 说明 |
|------|------|
| 4 步向导渲染 | 4 个 Step 标签可见 |
| Step 1 达人下拉 + 预览 | 列表渲染 + 选中后预览 |
| Step 1 素材库展开 | 点"上传种草爆款"展开表单 |
| Step 1 新增素材提交 | 调 createReference API + 刷新列表 |
| Step 1 抖音链接导入 | mock importReferenceFromDouyin |
| Step 1 删除素材 | 调 deleteReference API |
| Step 2 产品库列表 | getProducts mock + 列表渲染 |
| Step 2 上传文档 AI 解析 | mock parseProductDocument + 自动填表单 |
| Step 2 AI 卖点讨论流式 | mock extractSellingPointsStream |
| Step 2 采用卖点到表单 | 点按钮 + 正则提取【最终卖点】|
| Step 3 抖音链接解析 | fetchVideo mock |
| Step 3 ASR submit + poll | mock submitTranscribe + pollTranscribe（轮询 3 次后 done）|
| Step 3 文案确认 | textarea 显示 + 修改 |
| Step 3 结构拆解流式 | analyzeStructureStream mock |
| Step 4 三种选题模式切换 | 沿用/自定义/AI 推荐 Radio |
| Step 4 写作流式 + 字数校验 | chatStream scene=writing mock + autoTrim 触发 |
| Step 4 多轮迭代 | chatStream scene=iteration mock |
| 保存历史按钮 | 调 saveOutput API |
| 导出 .txt 按钮 | 触发 Blob 下载 |
| 导出 .docx 按钮 | 调 exportWord API |

### 6.2 SeedingWriterConfigTab（3 用例）

| 用例 | 说明 |
|------|------|
| ConfigTab 渲染 | 配置项加载 + 6 Prompt + 2 模型字段可见 |
| ConfigTab 编辑 Modal 打开 | 全字段可见 |
| ConfigTab 表单提交 | 调 updateConfig |

---

## 七、关键约定

- 所有 JSON 调用走 `request.ts`（红线 #3），例外：SSE 4 / multipart 1 / Blob 1
- TypeScript 类型检查通过（`npx tsc --noEmit` exit 0）
- antd 5 用 `destroyOnHidden` 不用 `destroyOnClose`
- antd `message` 用 `App.useApp()` hook（不用静态方法）
- 禁止 Tailwind class（项目未装）
- ASR 轮询 max 60 次 × 5s（5 分钟超时）+ 提示手动粘贴兜底
- multipart 上传不设 Content-Type（让浏览器自动加 boundary）
- 字数校验后置触发（首次生成完后判断超字，超字再 trim）
- 产品库 / 素材库公司共享语义（所有用户可见）

---

## 八、不在本次范围

- 产品库 Excel 批量导入（独立任务）
- 素材库全文搜索（按需迭代）
- 富文本编辑器（textarea 够用）
- 移动端适配（沿用桌面端布局）

---

## 九、DoD

- ✅ 22 函数 API 层全实现 + 红线 #3 合规
- ✅ 4 步向导全流程可走通
- ✅ 素材库 CRUD + 抖音链接导入可用
- ✅ 产品库 CRUD + 文档上传 + AI 卖点讨论可用
- ✅ ASR submit + poll 轮询 UX 正常
- ✅ 写作 + 字数校验 + 迭代可用
- ✅ ConfigTab 6 Prompt + 2 模型可配
- ✅ 组件测试 20+ 用例全绿
- ✅ 全量 vitest 回归（不引入新 fail）
- ✅ `npx tsc --noEmit` exit 0
- ✅ conventionGuard 通过
- ✅ `frontend/docs/README.md` 同步（API 层 + 服务配置章节）
