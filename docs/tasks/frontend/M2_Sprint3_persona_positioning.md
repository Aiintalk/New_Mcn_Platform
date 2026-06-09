# MCN_Frontend_Agent — M2 Sprint 3 任务指令（人格定位迁移）

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-09  
> 前置条件：后端 M2 Sprint 3 接口联调完成
> 完成后：回传 PM

---

## M2 Sprint 3 目标

将旧架构 `persona-positioning`（Next.js 独立应用）**1:1 迁移**到新架构（React + Vite）。  
UI 交互、功能逻辑完全保留，适配新架构的路由、鉴权、API 调用方式。

旧架构页面路径（仅供参考，不修改）：  
`D:\2026年工作\AI相关\AI工具箱新架构方案\AI工具箱网站\Ai_Toolbox\persona-positioning\app\page.tsx`

---

## 一、新增文件清单

```
frontend/src/
├── pages/operator/
│   └── PersonaPage.tsx          # 主页面（三步向导）
├── api/
│   └── persona.ts               # API 调用层
└── types/
    └── persona.ts               # TypeScript 类型定义
```

---

## 二、类型定义（types/persona.ts）

```typescript
export interface UploadedFile {
  name: string;
  text: string;
  status: 'uploading' | 'done' | 'error';
}

export interface FetchDouyinResult {
  nickname: string;
  sec_user_id: string;
  total_videos: number;
  top10_count: number;
  recent30_count: number;
  top10_text: string;
  recent30_text: string;
}

export interface PersonaReport {
  id: number;
  influencer_name: string | null;
  douyin_nickname: string | null;
  status: 'pending' | 'generating' | 'ready' | 'failed';
  created_at: string;
}

export type PersonaStep = 1 | 2 | 3;
export type PersonaTab = 'profile' | 'plan';
```

---

## 三、API 层（api/persona.ts）

所有请求均携带 `Authorization: Bearer {token}`（使用 `useAuthStore.getState().token`）。

```typescript
const BASE = '/api/persona';

// 解析抖音账号
export async function fetchDouyin(url: string): Promise<FetchDouyinResult>

// 解析上传文件 → 返回提取文本
export async function parseFile(file: File): Promise<{ text: string }>

// 下载问卷模板（fetch + Blob，触发浏览器下载）
export async function downloadQuestionnaireTemplate(): Promise<void>

// SSE 流式生成，返回 { stream: ReadableStream, reportId: number | null }
export async function generatePersona(params: {
  influencer_info: string;
  top10_content?: string;
  supplement_text?: string;
  benchmark_text?: string;
  douyin_id?: string;
  douyin_nickname?: string;
  recent30_text?: string;
  questionnaire_files?: Array<{ filename: string; text: string }>;
  supplement_files?: Array<{ filename: string; text: string }>;
  benchmark_profile_files?: Array<{ filename: string; text: string }>;
  benchmark_plan_files?: Array<{ filename: string; text: string }>;
}): Promise<{ reader: ReadableStreamDefaultReader<Uint8Array>; reportId: number | null }>

// 导出 Word（fetch + Blob 下载，与 kol-intake 一致）
export async function exportPersonaWord(params: {
  report_id: number;
  type: 'profile' | 'plan';
  influencer_name?: string;
}): Promise<void>

// 历史报告列表
export async function getPersonaReports(): Promise<PersonaReport[]>
```

**关键实现细节：**

`generatePersona` 实现：
```typescript
const res = await fetch(`${BASE}/generate`, { method: 'POST', headers: {...}, body: ... });
const reportId = res.headers.get('X-Report-Id');  // 从响应 Header 取
const reader = res.body!.getReader();
return { reader, reportId: reportId ? Number(reportId) : null };
```

`exportPersonaWord` 实现：使用 fetch + Blob + 动态 `<a>` 标签下载（与 kol-intake 一致，不用 window.open）。

---

## 四、主页面（pages/operator/PersonaPage.tsx）

### 4.1 整体结构

完全复刻旧架构交互，适配新架构样式变量和组件规范。

```typescript
type PersonaStep = 1 | 2 | 3;
type PersonaTab = 'profile' | 'plan';

// 状态
const [step, setStep] = useState<PersonaStep>(1);

// Step 1 状态
const [douyinId, setDouyinId] = useState('');
const [fetchingDy, setFetchingDy] = useState(false);
const [fetchDyError, setFetchDyError] = useState('');
const [top10Content, setTop10Content] = useState('');
const [recent30Content, setRecent30Content] = useState('');
const [fetchDyResult, setFetchDyResult] = useState<FetchDouyinResult | null>(null);
const [influencerFiles, setInfluencerFiles] = useState<UploadedFile[]>([]);
const [supplementNotes, setSupplementNotes] = useState('');
const [supplementFiles, setSupplementFiles] = useState<UploadedFile[]>([]);

// Step 2 状态
const [benchmarkProfileFiles, setBenchmarkProfileFiles] = useState<UploadedFile[]>([]);
const [benchmarkPlanFiles, setBenchmarkPlanFiles] = useState<UploadedFile[]>([]);

// Step 3 状态
const [activeTab, setActiveTab] = useState<PersonaTab>('profile');
const [profileResult, setProfileResult] = useState('');
const [planResult, setPlanResult] = useState('');
const [loading, setLoading] = useState(false);
const [exporting, setExporting] = useState(false);
const [reportId, setReportId] = useState<number | null>(null);
const abortRef = useRef<AbortController | null>(null);
```

---

### 4.2 Step 1 — 填写达人资料

**子区块 A：抖音号解析**
- 输入框：placeholder="输入抖音号或主页链接（选填）"
- 按钮「解析（必点）」：点击调用 `fetchDouyin(douyinId)`
- 解析中：按钮 loading 状态，禁用
- 解析成功：显示绿色提示 `✅ 已解析：{nickname}，共 {total_videos} 个视频，抓取 TOP{top10_count} 条`
- 解析失败：显示红色错误文本
- 保存 `top10_text` 和 `recent30_text` 到 state

**子区块 B：达人资料文件上传（必填至少一个）**
- 按钮「下载问卷模板」→ 调用 `downloadQuestionnaireTemplate()`（fetch + Blob 下载）
- 文件上传区（支持 .docx / .pdf / .txt / .md，可多选）
- 上传时实时调用 `parseFile(file)` → 提取文本存入 `influencerFiles`
- 显示文件列表：文件名 + 状态（上传中 / 完成 / 失败）+ 删除按钮

**子区块 C：补充信息（选填）**
- Textarea：补充备注，placeholder="输入补充说明..."
- 文件上传区：同上

**「下一步」按钮条件（与旧架构一致）：**
```typescript
const hasInfluencerData = influencerFiles.some(f => f.status === 'done');
const hasParsedDouyin = !douyinId.trim() || !!fetchDyResult;
const canGoStep2 = hasInfluencerData && hasParsedDouyin;
```

---

### 4.3 Step 2 — 上传对标资料（可跳过）

**说明文字**：「上传同赛道已验证成功的达人方案，AI 会参照对标风格为目标达人定制方案。没有对标资料可跳过。」

**子区块 A：对标人格档案**
- 文件上传区，支持多个，文件名前缀提示"对标人格档案"

**子区块 B：对标内容规划**
- 文件上传区，支持多个，文件名前缀提示"对标内容规划"

**底部按钮：**
- 「上一步」← 返回 Step 1
- 「跳过，直接生成」→ 调用 `handleGenerate()`
- 「下一步，开始生成」→ 调用 `handleGenerate()`（有文件时显示此按钮，无文件时显示"跳过"）

---

### 4.4 Step 3 — 生成结果展示

**进入 Step 3 时自动触发 `handleGenerate()`：**

```typescript
const handleGenerate = async () => {
  const influencerInfo = buildInfluencerInfo();  // 合并所有达人文件文本
  if (!influencerInfo.trim()) { message.error('请上传达人资料文档'); return; }

  setLoading(true);
  setProfileResult('');
  setPlanResult('');
  setStep(3);
  setActiveTab('profile');

  try {
    const supplementText = buildSupplementText();
    const benchmarkText = buildBenchmarkText();

    const { reader, reportId: rid } = await generatePersona({
      influencer_info: influencerInfo,
      top10_content: top10Content || undefined,
      supplement_text: supplementText || undefined,
      benchmark_text: benchmarkText || undefined,
      douyin_id: douyinId || undefined,
      douyin_nickname: fetchDyResult?.nickname || undefined,
      recent30_text: recent30Content || undefined,
      questionnaire_files: influencerFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
      supplement_files: supplementFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
      benchmark_profile_files: benchmarkProfileFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
      benchmark_plan_files: benchmarkPlanFiles.filter(f => f.status === 'done').map(f => ({ filename: f.name, text: f.text })),
    });

    setReportId(rid);

    const decoder = new TextDecoder();
    let fullText = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      fullText += decoder.decode(value, { stream: true });
      const parts = fullText.split('===SPLIT===');
      setProfileResult(parts[0].trim());
      if (parts.length > 1) setPlanResult(parts[1].trim());
    }
  } catch (err) {
    if (err instanceof Error && err.name !== 'AbortError') {
      message.error('生成出错，请重试');
    }
  } finally {
    setLoading(false);
  }
};
```

**两 Tab 展示：**
- Tab 切换：「人格档案」 / 「内容规划」
- 内容区：`<pre style={{ whiteSpace: 'pre-wrap' }}>{activeTab === 'profile' ? profileResult : planResult}</pre>`
- 生成中：显示 loading 动画 + 已流入内容（实时更新）

**每个 Tab 的按钮：**
- 「导出 Word」按钮：
  ```typescript
  const handleExportWord = async (type: 'profile' | 'plan') => {
    if (!reportId) { message.error('请等待生成完成'); return; }
    setExporting(true);
    try {
      await exportPersonaWord({
        report_id: reportId,
        type,
        influencer_name: fetchDyResult?.nickname || '达人',
      });
    } catch {
      message.error('导出失败');
    } finally {
      setExporting(false);
    }
  };
  ```
- 「复制」按钮：`navigator.clipboard.writeText(activeTab === 'profile' ? profileResult : planResult)`

**底部按钮：**
- 「重新开始」→ 重置所有状态，回到 Step 1

---

### 4.5 数据汇总函数

```typescript
const buildInfluencerInfo = () =>
  influencerFiles
    .filter(f => f.status === 'done' && f.text)
    .map(f => `=== ${f.name} ===\n${f.text}`)
    .join('\n\n');

const buildSupplementText = () => {
  const parts: string[] = [];
  if (supplementNotes.trim()) parts.push(`=== 运营补充说明 ===\n${supplementNotes.trim()}`);
  const fileText = supplementFiles
    .filter(f => f.status === 'done' && f.text)
    .map(f => `=== ${f.name} ===\n${f.text}`)
    .join('\n\n');
  if (fileText) parts.push(fileText);
  return parts.join('\n\n');
};

const buildBenchmarkText = () => {
  const parts: string[] = [];
  const profileText = benchmarkProfileFiles
    .filter(f => f.status === 'done' && f.text)
    .map(f => `=== 对标人格档案：${f.name} ===\n${f.text}`)
    .join('\n\n');
  const planText = benchmarkPlanFiles
    .filter(f => f.status === 'done' && f.text)
    .map(f => `=== 对标内容规划：${f.name} ===\n${f.text}`)
    .join('\n\n');
  if (profileText) parts.push(profileText);
  if (planText) parts.push(planText);
  return parts.join('\n\n');
};
```

---

### 4.6 步骤指示器

与旧架构一致：三个圆形步骤节点 + 连接线，当前步骤高亮（紫色），已完成步骤显示 ✓，可点击已完成步骤回退。

---

## 五、路由注册

在 `frontend/src/App.tsx`（或路由配置文件）中注册路由：

```typescript
<Route path="/persona" element={<PersonaPage />} />
```

路由需在登录守卫（PrivateRoute 或类似）内，非鉴权页面不可访问。

---

## 六、导航菜单

**运营端 — 创作中心**

找到运营端「创作中心」菜单的子菜单配置，参照现有条目添加：
```typescript
{ key: 'persona', label: '人格定位', icon: <某个图标 />, path: '/persona' }
```
> 所有运营端新增功能统一放入「创作中心」，不单独新增顶级菜单项。

**管理端 — 工具配置**

找到管理端「工具配置」→「功能配置」页面，在 `persona-positioning` 工具卡片中添加：
- AI 模型选择（下拉，绑定 `persona_generation` 配置的 `ai_model_id`）
- Prompt 配置（Textarea，绑定 `persona_generation` 配置的 `system_prompt`）
- 保存按钮 → 调用 `PUT /api/admin/intake/configs/persona_generation`

> 所有功能的 AI 模型和 Prompt 配置统一在管理端「工具配置」内管理，不新建独立配置页面。

---

## 七、样式规范

- 使用项目现有 CSS 变量（`var(--brand)`, `var(--bg-card)`, `var(--border)` 等）
- 不引入新的 CSS 框架（旧架构用 Tailwind，新架构用 CSS 变量）
- 按钮使用现有 `.btn .btn-primary .btn-ghost` class
- 文件上传区域样式参照旧架构交互，背景 `var(--bg-page)`，边框 dashed

---

## 八、注意事项

1. **文件上传并发**：多文件上传时逐个 `parseFile()`，每个文件独立状态（uploading/done/error），不要全部等待再更新。

2. **SSE 流读取**：使用 `ReadableStreamDefaultReader`，注意处理 AbortController 取消（`abortRef.current?.abort()`）。

3. **`===SPLIT===` 分隔**：流式读取时每次 chunk 后执行 `fullText.split('===SPLIT===')`，前半为 profileResult，后半为 planResult，实时更新两个 state。

4. **reportId 时机**：`report_id` 从 HTTP 响应 Header `X-Report-Id` 获取，在开始读 stream 前已拿到，直接 `setReportId(rid)`。

5. **导出按钮禁用逻辑**：`loading` 或 `!reportId` 时禁用导出按钮（生成完成后才能导出）。

6. **问卷模板下载**：调用 `GET /api/persona/questionnaire-template`，fetch + Blob 方式，filename = `达人入职信息采集表.docx`。

---

## 九、验收标准

1. Step 1：
   - 输入抖音号点击「解析」→ 显示 nickname 和视频数量
   - 上传 .docx / .pdf / .txt 文件 → 显示「完成」状态
   - 点击「下载问卷模板」→ 浏览器下载 Word 文件
   - 未上传达人文件时「下一步」按钮不可点击

2. Step 2：
   - 上传对标文件后显示文件名和状态
   - 「跳过」和「下一步，开始生成」按钮均可触发生成

3. Step 3：
   - 进入即开始 SSE 流式生成，内容实时展示
   - 「人格档案」和「内容规划」两 Tab 分别显示对应内容
   - 生成完成后「导出 Word」按钮可用 → 下载对应 Word 文件
   - 「复制」按钮可用
   - 「重新开始」回到 Step 1，清空所有状态

4. 页面在侧边栏导航可访问，非登录状态跳转至登录页
