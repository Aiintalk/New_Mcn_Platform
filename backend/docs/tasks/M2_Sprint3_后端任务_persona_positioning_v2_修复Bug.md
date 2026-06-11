# M2 Sprint3 后端任务 — 人格定位 v2 Bug 修复

> 修复日期：2026-06-11
> 关联任务：M2_Sprint3_persona_positioning_v2

---

## Bug 1：抖音分享链接解析失败

### 现象

运营端输入抖音分享文本（如 `长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/YQRFp7mNOeg/`），返回错误：

```
抖音号解析失败：TikHub resolve_sec_user_id failed: 'str' object has no attribute 'get'
```

### 根因（3 个问题叠加）

1. **未提取纯 URL**：用户粘贴的分享文本包含中文前缀，整个字符串被传给 TikHub API，导致 422 参数校验失败
2. **TikHub 响应格式理解错误**：`get_sec_user_id` 端点返回的 `data` 字段是**纯字符串**（sec_user_id），代码按 dict 解析 `.get("sec_user_id")` 报错
3. **短链接未解析**：`v.douyin.com` 短链接未先 follow redirect 拿到完整 `douyin.com/user/` URL

### 修复

文件：`app/adapters/tikhub.py`

- 新增 `_extract_douyin_url(text)` — 从混合文本中正则提取 URL
- 新增 `_resolve_short_url(url)` — follow redirect 解析短链接
- 修正 `resolve_sec_user_id()`：
  - 调用 `_extract_douyin_url` 提取纯 URL
  - 调用 `_resolve_short_url` 解析短链接后再传给 TikHub
  - `data.get("data")` 直接作为 sec_user_id 字符串，不再 `.get("sec_user_id")`
  - 复用已有的 `get_user_profile()` 获取昵称（`handler_user_profile_v2` 端点不支持 `sec_user_id` 参数，改用 `app/v3/handler_user_profile`）

### 验证

- 221/221 后端测试通过
- 前端手工验证：输入抖音分享链接 → 成功解析昵称 + 视频数据

---

## Bug 2：前端文件下载请求打到错误地址

### 现象

运营端下载问卷模板后，Word 打开报错："有无法读取的内容"。

### 根因

`frontend/src/api/persona.ts` 中直接用 `fetch` 的函数（下载模板、文件上传、SSE 生成、导出 Word）使用了**相对路径**：

```typescript
const BASE = '/api/persona';  // 缺少后端地址
```

请求打到了 Vite 前端服务器（5173 端口），返回的是 HTML 页面而非 .docx 文件。`request.ts` 中已配置 `BASE_URL = 'http://localhost:8000'`，但 `persona.ts` 未使用。

### 修复

文件：`frontend/src/api/persona.ts`

拆分两套路径常量：
- `API`（相对路径 `/api/persona`）→ 给 `request.ts` 的 `get/post/del` 用（内部已拼 `BASE_URL`）
- `FETCH_BASE`（完整路径 `http://localhost:8000/api/persona`）→ 给原生 `fetch` 用

```typescript
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const API = '/api/persona';                          // request.ts 封装用
const FETCH_BASE = `${BASE_URL}/api/persona`;        // 原生 fetch 用
```

修复过程中还修复了 URL 重复拼接问题（`post` 内部已拼 `BASE_URL`，不应再传完整 URL）。

### 影响范围

修复后以下函数均正确指向后端：
- `fetchDouyin()` / `getKolSubmissions()` / `getPersonaReports()` / `getPersonaReportDetail()` / `deletePersonaReport()` — 用 `API`
- `downloadQuestionnaireTemplate()` / `parseFile()` / `generatePersona()` / `optimizePersona()` / `exportPersonaWord()` — 用 `FETCH_BASE`

### 验证

- 71/71 前端测试通过
- 手工验证：下载问卷模板 → Word 正常打开

---

## Bug 3：历史记录按钮在任何步骤不可见 + 抽屉不渲染

### 现象

用户在任何步骤点击页面头部的"历史记录"按钮，抽屉不弹出，没有任何反应。

### 根因

1. "历史记录"按钮已从 Step 3 移到页面头部（所有步骤可见）
2. 但历史记录抽屉和优化对话 Overlay 的**渲染代码仍在 `{step === 3 && (...)}` 块内部**
3. 用户在 Step 1/2 点按钮时 `historyOpen=true`，但 DOM 不渲染抽屉

### 修复

文件：`frontend/src/pages/operator/PersonaPage.tsx`

将 `优化对话 Overlay` 和 `历史记录抽屉` 从 `{step === 3 && (...)}` 块内移到组件最外层，使其在任何步骤都能渲染。

### 验证

- 71/71 前端测试通过
- 手工验证：Step 1 点"历史记录"→ 抽屉正常弹出

---

## Bug 4：页面切换/刷新后 SSE 断连导致空报告被标记为 ready

### 现象

用户在 AI 生成过程中刷新页面或切换到其他页面，回来后历史记录显示报告状态为 `ready` 但内容为空（profile_result、plan_result、raw_output 长度均为 0）。

### 根因

1. 用户刷新/切走 → 前端 SSE 连接断开
2. 后端 `stream_generator` 的 `finally` 块执行 `_finalize_report(report_id, full_text, ...)`
3. 此时 AI 还在"思考"阶段，尚未输出任何 token，`full_text` 为空字符串
4. `_finalize_report` 不检查空内容，直接标记 `status="ready"`

### 修复

**后端** `app/routers/persona.py` — `_finalize_report` 增加空内容保护：

```python
if not raw_output.strip():
    report.status = "failed"
    report.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return
```

**前端** `PersonaPage.tsx` — 组件卸载时中止进行中的请求：

```typescript
useEffect(() => {
  return () => {
    abortRef.current?.abort();
    optimizeAbortRef.current?.abort();
  };
}, []);
```

**数据清理**：数据库中 2 条空内容报告已从 `ready` 改为 `failed`。

### 验证

- 221/221 后端测试通过
- 71/71 前端测试通过
- 手工验证：AI 生成中切走页面 → 后端继续生成 → 回来后通过"历史记录"可加载结果

---

## Bug 5：历史记录点击加载后无反应

### 现象

运营端人格定位页面，点击"历史记录"按钮打开抽屉后，点击某条历史记录（如"然然"），抽屉关闭但页面没有任何变化，内容不显示。

### 根因

`loadHistoryDetail()` 函数加载数据后只设置了 `profileResult`、`planResult` 和 `reportId`，但**没有切换步骤到 Step 3**。用户如果当前在 Step 1 或 Step 2，数据虽然加载了但 Step 3 的渲染块不显示。

### 修复

文件：`frontend/src/pages/operator/PersonaPage.tsx`

在 `loadHistoryDetail` 函数中增加 `setStep(3)`：

```typescript
async function loadHistoryDetail(id: number) {
    try {
      const detail = await getPersonaReportDetail(id);
      if (detail.profile_result) setProfileResult(detail.profile_result);
      if (detail.plan_result) setPlanResult(detail.plan_result);
      setReportId(id);
      setHistoryOpen(false);
      setStep(3);  // ← 新增：自动跳转到结果页
      message.success('已加载历史报告');
    } catch { message.error('加载详情失败'); }
}
```

### 验证

- 手工验证：Step 1 → 点击历史记录 → 点击某条 → 自动跳到 Step 3 显示内容

---

## Bug 6：产出中心点击预览内容为空

### 现象

运营端「产出中心」→「AI 产出」Tab，点击"然然 · 人格档案 + 内容规划"条目的「预览」按钮，弹窗显示"暂无内容预览"。

### 根因

1. 列表接口 `GET /api/outputs` 后端返回数据**不含 `content` 字段**（`include_content=False`）
2. 前端点击「预览」直接用列表数据 `setPreview(o)`，但 `o` 对象没有 `content` 属性
3. 预览 Modal 检查 `preview.content` 为 falsy，显示"暂无内容预览"

### 修复

文件：`frontend/src/pages/operator/OutputsPage.tsx`

1. 引入 `getOutput`（详情接口）
2. 点击预览时先用列表数据打开弹窗（即时响应），同时异步调 `getOutput(id)` 获取完整内容

```typescript
import { getOutputs, getOutput, deleteOutput } from '../../api/outputs';

// 预览按钮
onClick={() => {
  setPreview(o);  // 立即打开弹窗
  getOutput(o.id).then(detail => setPreview(detail)).catch(() => {});  // 异步加载内容
}}
```

### 验证

- 手工验证：产出中心 → 点击预览 → 弹窗显示完整的 AI 生成内容
