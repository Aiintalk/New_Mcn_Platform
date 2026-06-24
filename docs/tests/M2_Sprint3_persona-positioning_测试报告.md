# M2 Sprint 3 — 人格定位（persona-positioning）测试报告

**日期**：2026-06-11（功能完成）/ 2026-06-24 补遗整理
**范围**：旧架构 `persona-positioning-web` → 新架构迁移完整测试
**分支**：Sprint 3 期间主开发分支（已并入 main）
**结果**：✅ 后端 221/221 通过 + 前端 71/71 通过 + 6 个 v2 Bug 全部修复 + 手工 E2E 三步流程全通

---

## 一、测试总览

| 端 | 通过 | 失败 | 跳过 | 总计 |
|----|------|------|------|------|
| 后端单测 + 集成 | 221 | 0 | 0 | 221 |
| 前端单测（vitest） | 71 | 0 | 0 | 71 |
| 手工 E2E | ✅ | — | — | 三步流程全通 |
| **合计** | **292** | **0** | **0** | **292** |

> ℹ️ Sprint 3 期间项目尚处于早期，未引入 Playwright E2E（Sprint 16 v3 才引入）。
> 本报告的 E2E 指人工浏览器走查。

---

## 二、后端测试详情（221 个）

### 2.1 覆盖范围

| 模块 | 覆盖内容 |
|------|---------|
| `routers/persona.py` | 10 个 API（fetch-douyin / parse-file / generate SSE / export-word / reports list / report detail / kol-submissions / optimize SSE / delete / questionnaire-template） |
| `services/file_parser.py` | .docx / .pdf / .txt / .md 解析 + 8000 字符截断 + 异常路径 |
| `services/persona_docx.py` | Markdown → docx（标题/列表/引用/粗体/空段落） |
| `adapters/tikhub.py` | `resolve_sec_user_id`（URL 提取 + 短链解析）+ `fetch_user_videos`（分页） |
| `adapters/yunwu.py` | `chat_stream`（SSE + 凭证池 + finally 写 AiCallLog） |
| `models/persona_report.py` | ORM 字段映射 |
| 产出双写 | generate 后台任务写 `outputs` 表 |
| 鉴权 | unauthorized 401 / operator / admin / 越权访问 |

### 2.2 覆盖率（关键文件）

```
app\routers\persona.py               （被集成测试覆盖）
app\services\file_parser.py          （被单测覆盖）
app\services\persona_docx.py         （被单测覆盖）
app\adapters\tikhub.py               （被集成测试覆盖）
app\adapters\yunwu.py                （被集成测试覆盖）
app\models\persona_report.py         （被集成测试覆盖）
```

### 2.3 红线自检（CLAUDE.md 7 条）

| 红线 | 状态 | 说明 |
|------|------|------|
| #1 标准信封 | ✅ | 8 个普通接口走 `success_response` / `error_response`；2 个 SSE + 1 个 Blob 下载是例外 |
| #2 OperationLog | ✅ | generate（后台任务 action=`generate_persona_report`）/ export-word（action=`export_persona_word`）/ delete（action=`delete_persona_report`）三处均写 |
| #3 前端走 request.ts | ✅ | 普通接口走 request.ts；SSE/Blob/multipart 4 个函数走原生 fetch（有守卫白名单） |
| #4 契约同步 | ✅ | Base_API §1.3（persona 接口）+ §9（TikHub 凭证池）+ Base_Database §8 同步 |
| #5 README 更新 | ✅ | 根 README + backend/docs/README + frontend/docs/README 三处同步 |
| #6 AiCallLog 由 adapter 写 | ✅ | `yunwu.chat_stream()` finally 自动写（feature=`persona_generation` / `persona_optimize`） |
| #7 AsyncSessionLocal 注册 | ✅ | persona router 用 `get_db()`，不直接 import AsyncSessionLocal，conftest patch 列表无需扩展 |

### 2.4 9 条一票否决项

无新增触发。

---

## 三、前端测试详情（71 个）

### 3.1 Sprint 3 期间前端测试总数

Sprint 3 完成时前端单测 71/71 通过（含本次新增 + 历史遗留）。后续 Sprint 持续累加，至 Sprint 16 已达 180。

### 3.2 本次新增覆盖

| 文件 | 覆盖内容 |
|------|---------|
| `pages/operator/PersonaPage.tsx` | 三步向导渲染 / Step 1 抖音号解析 + KOL 导入 / Step 2 对标上传 / Step 3 SSE 流 + Tab 切换 + 导出按钮 / 优化对话 Overlay / 历史抽屉 |
| `api/persona.ts` | 10 个函数（含 SSE reader 返回 / Header 取 reportId / Blob 下载路径常量拆分） |
| `types/persona.ts` | UploadedFile / FetchDouyinResult / PersonaReport / PersonaReportDetail / KolSubmission / PersonaStep / PersonaTab |

### 3.3 关键交互验证

| 场景 | 验证点 |
|------|-------|
| Step 1 → Step 2 切换 | `canGoStep2 = hasInfluencerData && hasParsedDouyin` 条件正确 |
| Step 3 SSE 流读取 | `===SPLIT===` 拆分实时更新 profileResult / planResult |
| `X-Report-Id` Header | 开始读 stream 前已拿到 reportId |
| 卸载中止 SSE | `useEffect` cleanup 调 `abortRef.current?.abort()` |
| 历史加载 | `loadHistoryDetail` 加 `setStep(3)` |
| Word 导出 | Blob 下载 + UTF-8 文件名 |
| 优化对话 | 多轮 messages 累加 + 「采纳」替换 |

---

## 四、关键 Bug 修复记录（v2，6 个）

### 4.1 Bug 1：抖音分享链接解析失败

**现象**：运营端粘贴抖音分享文本（如 `长按复制此条消息... https://v.douyin.com/YQRFp7mNOeg/`），返回：
```
抖音号解析失败：TikHub resolve_sec_user_id failed: 'str' object has no attribute 'get'
```

**根因（3 个问题叠加）**：
1. 未从混合文本提取纯 URL → 整段文本传给 TikHub → 422 校验失败
2. TikHub `get_sec_user_id` 端点的 `data` 字段是**纯字符串**（sec_user_id），代码按 dict 解析 `.get("sec_user_id")` 报错
3. `v.douyin.com` 短链接未先 follow redirect 拿完整 URL

**修复**（`app/adapters/tikhub.py`）：
- 新增 `_extract_douyin_url(text)` — 正则提取 URL
- 新增 `_resolve_short_url(url)` — follow redirect 解析短链
- `resolve_sec_user_id()` 三步串：提取 URL → 解析短链 → 调 TikHub（`data` 直接作为字符串）
- 复用 `get_user_profile()` 拿昵称（端点改为 `app/v3/handler_user_profile`）

**验证**：221/221 后端通过；前端手工输入分享链接成功解析。

---

### 4.2 Bug 2：前端文件下载请求打到错误地址

**现象**：下载问卷模板后，Word 打开报错"有无法读取的内容"。

**根因**：`frontend/src/api/persona.ts` 原生 fetch 函数用了相对路径 `/api/persona`，请求打到 Vite 前端服务器（5173）返回 HTML 而非 .docx。`request.ts` 有 `BASE_URL='http://localhost:8000'` 但 persona.ts 未用。

**修复**（`frontend/src/api/persona.ts`）：
```typescript
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const API = '/api/persona';                          // request.ts 封装用
const FETCH_BASE = `${BASE_URL}/api/persona`;        // 原生 fetch 用
```

- `fetchDouyin()` / `getKolSubmissions()` / `getPersonaReports()` / `getPersonaReportDetail()` / `deletePersonaReport()` → 用 `API`
- `downloadQuestionnaireTemplate()` / `parseFile()` / `generatePersona()` / `optimizePersona()` / `exportPersonaWord()` → 用 `FETCH_BASE`

**验证**：71/71 前端通过；手工下载问卷模板 Word 正常打开。

---

### 4.3 Bug 3：历史记录按钮在任何步骤不可见 + 抽屉不渲染

**现象**：Step 1/2 点击头部"历史记录"按钮，无任何反应。

**根因**：
1. 历史按钮从 Step 3 移到页面头部（所有步骤可见）
2. 但抽屉 + 优化 Overlay 的渲染代码仍在 `{step === 3 && (...)}` 块内
3. Step 1/2 时 `historyOpen=true` 但 DOM 不渲染

**修复**（`PersonaPage.tsx`）：将历史抽屉 + 优化 Overlay 从 `{step === 3 && (...)}` 块内移到组件最外层。

**验证**：71/71 前端通过；Step 1 点"历史记录" → 抽屉正常弹出。

---

### 4.4 Bug 4：页面切换/刷新后 SSE 断连导致空报告被标记 ready

**现象**：用户在 AI 生成中刷新或切走，回来看到历史记录状态为 `ready` 但内容为空（profile_result / plan_result / raw_output 长度均为 0）。

**根因**：
1. 用户刷新/切走 → 前端 SSE 断开
2. 后端 `stream_generator` 的 `finally` 块执行 `_finalize_report(report_id, full_text, ...)`
3. AI 还在"思考"阶段未输出 token，`full_text` 为空
4. `_finalize_report` 不检查空内容直接标 `status="ready"`

**修复**：

**后端**（`app/routers/persona.py`）— 空内容保护：
```python
if not raw_output.strip():
    report.status = "failed"
    report.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return
```

**前端**（`PersonaPage.tsx`）— 卸载中止：
```typescript
useEffect(() => {
  return () => {
    abortRef.current?.abort();
    optimizeAbortRef.current?.abort();
  };
}, []);
```

**数据清理**：数据库中 2 条空内容报告从 `ready` 改为 `failed`。

**验证**：221/221 + 71/71；手工生成中切走页面 → 后端继续 → 回来通过历史记录加载结果。

---

### 4.5 Bug 5：历史记录点击加载后无反应

**现象**：历史抽屉点击某条记录后，抽屉关闭但页面无变化。

**根因**：`loadHistoryDetail()` 只 set 了 profileResult / planResult / reportId，**没有 setStep(3)**。Step 1/2 状态下 Step 3 渲染块不显示。

**修复**（`PersonaPage.tsx`）：
```typescript
async function loadHistoryDetail(id: number) {
  try {
    const detail = await getPersonaReportDetail(id);
    if (detail.profile_result) setProfileResult(detail.profile_result);
    if (detail.plan_result) setPlanResult(detail.plan_result);
    setReportId(id);
    setHistoryOpen(false);
    setStep(3);  // ← 新增
    message.success('已加载历史报告');
  } catch { message.error('加载详情失败'); }
}
```

**验证**：Step 1 → 点击历史 → 点某条 → 自动跳 Step 3 显示内容。

---

### 4.6 Bug 6：产出中心点击预览内容为空

**现象**：运营端「产出中心 → AI 产出」点击"XX · 人格档案 + 内容规划"的「预览」，弹窗显示"暂无内容预览"。

**根因**：
1. `GET /api/outputs` 列表接口 `include_content=False`，返回不含 `content` 字段
2. 前端点击预览直接用列表数据 `setPreview(o)`，但 `o` 无 `content` 属性
3. 预览 Modal 检查 `preview.content` falsy 显示空提示

**修复**（`frontend/src/pages/operator/OutputsPage.tsx`）：
```typescript
import { getOutputs, getOutput, deleteOutput } from '../../api/outputs';

onClick={() => {
  setPreview(o);                                          // 立即开 Modal
  getOutput(o.id).then(detail => setPreview(detail))      // 异步加载完整内容
    .catch(() => {});
}}
```

**验证**：产出中心点预览 → 弹窗显示完整 AI 生成内容。

---

## 五、TypeScript 编译

```
npx tsc --noEmit  # exit 0，无错误
```

---

## 六、手工 E2E 走查（Sprint 3 期间）

> Sprint 3 期间未引入 Playwright，走查靠人工浏览器操作。

| 步骤 | 操作 | 预期 | 结果 |
|------|------|------|------|
| 1 | 进入 `/workspace/persona-positioning` | 显示三步向导 Step 1 | ✅ |
| 2 | 输入抖音分享链接 + 点「解析」 | 显示昵称 + TOP10/最近30 视频数 | ✅ |
| 3 | 从 KOL 入驻下拉选一条 | 自动填入达人资料 | ✅ |
| 4 | 上传 .docx 问卷文件 | 显示"完成"状态 | ✅ |
| 5 | 点「下载问卷模板」 | 浏览器下载 .docx，Word 能打开 | ✅ |
| 6 | Step 1 → 「下一步」 | 进入 Step 2 | ✅ |
| 7 | 上传对标资料 → 「下一步，开始生成」 | 进入 Step 3 触发 SSE 流 | ✅ |
| 8 | SSE 流式内容实时显示 | 双 Tab（档案/规划）内容实时更新 | ✅ |
| 9 | 流完成后 → 「导出 Word」 | 下载两份 .docx，Word 能打开 | ✅ |
| 10 | 点「优化人格档案」 → 输入修改意见 → 发送 | AI 流式回复 → 「采纳」替换当前内容 | ✅ |
| 11 | 点头部「历史记录」 → 选一条 | 自动跳 Step 3 加载内容 | ✅ |
| 12 | 历史抽屉删除一条 | 软删成功，列表刷新 | ✅ |
| 13 | 进入「产出中心 → AI 产出」 | 看到刚生成的报告条目 | ✅ |
| 14 | 产出中心点「预览」 | 弹窗显示完整 AI 内容 | ✅ |
| 15 | 生成中切走页面再回来 | 后端继续生成，历史记录可加载 | ✅ |

---

## 七、验收清单（DoD）

| 验收项 | 状态 | 证据 |
|--------|------|------|
| Migration 008 + 索引 + trigger | ✅ | `migrations/008_persona_positioning.sql` |
| `PersonaReport` ORM + `__init__` 注册 | ✅ | `models/persona_report.py` |
| `file_parser.py` 支持 4 种格式 | ✅ | `services/file_parser.py` |
| `persona_docx.py` Markdown → Word | ✅ | `services/persona_docx.py` |
| 10 个 API + 鉴权 | ✅ | `routers/persona.py` |
| 前端三步向导 + 优化对话 + 历史抽屉 | ✅ | `pages/operator/PersonaPage.tsx`（546 行） |
| 前端路由 + 创作中心菜单 | ✅ | `/workspace/persona-positioning` |
| TikHub adapter 扩展 | ✅ | `resolve_sec_user_id` + `fetch_user_videos` |
| yunwu adapter 扩展 | ✅ | `chat_stream`（SSE + 自动写 AiCallLog） |
| 产出双写 outputs 表 | ✅ | generate 后台任务同步写 |
| 管理端配置入口 | ✅ | 「工具配置 → 人格定位」 |
| workspace_tools 注册 | ✅ | migration 008 INSERT |
| 后端测试 221/221 | ✅ | pytest 全绿 |
| 前端测试 71/71 | ✅ | vitest 全绿 |
| TypeScript 编译 | ✅ | `tsc --noEmit` exit 0 |
| 6 个 v2 Bug 全修复 | ✅ | 见 §四 |
| 契约文档同步 | ✅ | Base_API §1.3 + §9 + Base_Database §8 |
| README 三处同步 | ✅ | 根 / backend / frontend |
| 红线 7 条 + 否决 9 条 | ✅ | 无触发 |

---

## 八、已知问题（非阻塞）

| 来源 | 问题 | 影响 | 后续 |
|------|------|------|------|
| Sprint 17 走查 | TikHub Cloudflare gateway 间歇性 502（~40% 失败率） | 抖音号解析偶发失败 | 独立任务加 retry |
| Sprint 3 已知 | 历史列表限 50 条 | 超过看不到旧记录 | 可后续加分页 |
| Sprint 3 债务 | `service_credentials.secret_enc` 明文 | 凭证安全风险 | 后续加密 |
| Sprint 3 已知 | Word 文件本地存储 | 跨实例不可用 | 后续上 OSS |

---

## 九、运行命令

```bash
# 后端单测 + 集成
cd backend && source .venv311/Scripts/activate    # Windows
pytest tests/ -v                                    # 221 通过
python scripts/run_coverage.py --gate              # 覆盖率门禁

# 前端单测
cd frontend
npx vitest run                                      # 71 通过（Sprint 3 时点）
npx tsc --noEmit                                    # exit 0

# 手工 E2E（启动服务后浏览器操作）
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
# 浏览器访问 http://localhost:5175/workspace/persona-positioning
```

---

## 十、后续留作独立任务

1. **TikHub 502 重试机制**：adapter 层加 retry（max 3 次，指数退避）— Sprint 17 已确认根因是 Cloudflare gateway
2. **Playwright E2E 补齐**：Sprint 3 期间未引入，Sprint 16 v3 已引入，可补 3-5 个关键路径
3. **历史记录分页**：超 50 条后的浏览方案
4. **`service_credentials.secret_enc` 加密**：Sprint 3 债务
5. **Word 文件上 OSS**：当前本地存储，迁移后跨实例可用
6. **对标分析下拉选择**：对标分析模块迁移时再加
7. **同步到素材库**：素材库模块迁移时再加
