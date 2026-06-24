# M2 Sprint 16 — 种草内容仿写 测试报告

**日期：** 2026-06-24
**范围：** 新功能「种草内容仿写」（seeding-writer）完整迁移
**分支：** `migrate/seeding-writer`
**结果：** ✅ 新增 124 个测试全绿（后端 101 + 前端 23），无回归

---

## 一、测试总览

| 端 | 通过 | 失败 | 跳过 | 总计 | 新增（本次） |
|----|------|------|------|------|--------------|
| 后端 | 970 | 2 ⚠️ | 1 | 973 | 101 |
| 前端 | 180 | 0 | 0 | 180 | 23 |
| **合计** | **1150** | **2** | **1** | **1153** | **124** |

> ⚠️ 后端 2 个失败为 **预存在失败**（`test_livestream_writer_file_parser.py` 的 `.pages` 文件解析），与本次种草仿写无关——未动过 `livestream_writer` 任何代码。已在 main 分支历史中存在。

---

## 二、后端测试详情（101 新增）

### 2.1 新增测试文件

| 文件 | 用例数 | 覆盖范围 |
|------|--------|----------|
| `tests/unit/services/test_seeding_writer_prompt.py` | ~14 | 14 占位符渲染（含 `{{name}}...{{/name}}` 循环） |
| `tests/unit/services/test_document_parser.py` | ~12 | PDF/DOCX/XLSX/PPTX/TXT/MD 解析 + 异常路径 |
| `tests/integration/routers/test_operator_seeding_writer.py` | ~60 | 20 个运营端接口（4 步流程 + SSE 流式 + multipart 上传 + Blob 下载） |
| `tests/integration/routers/test_admin_seeding_writer.py` | ~15 | 2 个管理端接口（GET/PUT configs）+ 鉴权 |

### 2.2 覆盖率

```
app\services\seeding_writer_prompt.py    8   0   100%
app\routers\operator_seeding_writer.py  （被集成测试覆盖）
app\routers\admin_seeding_writer.py     （被集成测试覆盖）
app\models\seeding_writer.py            （被集成测试覆盖）
```

### 2.3 红线自检（CLAUDE.md 7 条）

| 红线 | 状态 | 说明 |
|------|------|------|
| #1 标准信封 | ✅ | 20 个 operator + 2 个 admin 接口全部 `success_response` / `error_response` |
| #2 OperationLog | ✅ | 凭证保存、配置更新等写操作均写日志 |
| #3 前端走 request.ts | ✅ | 16 个普通接口走 request.ts；4 个 SSE + 1 multipart + 1 Blob 是例外（有守卫白名单） |
| #4 契约同步 | ✅ | Base_API §23 + Base_Database §27 同步更新 |
| #5 README 更新 | ✅ | 根 README + backend/docs/README + frontend/docs/README 三处同步 |
| #6 AiCallLog 由 adapter 写 | ✅ | 流式调用全部走 yunwu.py 的 chat_stream，日志由 adapter finally 写 |
| #7 AsyncSessionLocal 注册 | ✅ | 新增 SSE 端点用 `get_db()`，不直接 import AsyncSessionLocal |

### 2.4 9 条一票否决项

无新增触发。

---

## 三、前端测试详情（23 新增）

### 3.1 测试文件

- `frontend/src/__tests__/components/pages/SeedingWriterPage.test.tsx` — 23 个用例

### 3.2 用例分布

| 区块 | 用例数 | 关键场景 |
|------|--------|----------|
| Step 1 · 选达人 + 素材库 | 6 | 4 步向导渲染 / 达人下拉 / 素材表单 / 保存 / 删除 / 抖音导入 |
| Step 2 · 产品信息 | 5 | 产品库加载 / 文档 AI 解析 / 卖点流式 / 采用卖点 / 必填校验 / 产品库选择填充 |
| Step 3 · 对标验证 | 2 | ASR submit + poll 5s 轮询 / 结构拆解流式 |
| Step 4 · 种草仿写 | 7 | 3 种选题模式 / 写作流式 / 多轮迭代 / 保存历史 / 导出 .txt / 导出 .docx |
| ConfigTab | 3 | 渲染 / 编辑 Modal 全字段 / 提交 updateConfig |

### 3.3 AntD 5 + Vitest 3 测试技巧

本次测试踩坑后总结的 4 条 AntD 测试模式，已写入测试代码注释：

1. **中文字符串按钮文本被 AntD 自动加空格**
   - 现象：`<Button>保存</Button>` 在 DOM 里渲染成 `保 存`（两字间一个空格）
   - 错误写法：`b.textContent === '保存'`
   - 正确写法：`/^保\s*存$/.test(b.textContent || '')`

2. **`vi.setConfig({ testTimeout })` 必须在 `it` 注册前调用**
   - 现象：在 `beforeEach` 里调用无效——`it` 注册时已用默认 5000ms 锁定
   - 正确写法：放在 `describe` 体内、`beforeEach` 之前
   - 场景：ASR_POLL_INTERVAL = 5000ms，默认 5s testTimeout 撞死

3. **多个 step 同时 in DOM 时 `openSelectAndPick` 要传 selectIndex**
   - 现象：Step 2 渲染时 Step 1 的 persona Select 仍在 DOM
   - 错误写法：`openSelectAndPick(user, /精华液/, 0)` 会再次打开 persona 下拉
   - 正确写法：`openSelectAndPick(user, /精华液/, 1)`（产品库 select 是第 1 个）

4. **列表 + Modal 同文案冲突**
   - 现象：ConfigTab 卡片列表有"文档解析 Prompt"，Modal 内也有"文档解析 Prompt（heavy 模型…）"
   - 错误写法：`screen.getByText(/文档解析 Prompt/)` 报 multiple elements
   - 正确写法：用更精确的正则 `screen.getByText(/文档解析 Prompt（heavy 模型/)`

---

## 四、关键问题修复记录

### 4.1 前端 13 个测试失败批量修复（同一 PR 内）

**初次运行：** 23 个用例 13 失败（43% 失败率）
**修复后：** 23 个用例 0 失败（100%）

**修复清单（7 处代码改动）：**

| # | 位置 | 改动 |
|---|------|------|
| 1 | `SeedingWriterPage.test.tsx` describe 顶部 | 加 `vi.setConfig({ testTimeout: 30000 })` |
| 2 | line 219（Test 4 保存按钮） | `=== '保存'` → `/^保\s*存$/` 正则 |
| 3 | line 267（Test 6 删除按钮） | `=== '删除'` → `/^删\s*除$/` 正则 |
| 4 | line 602（Test 15 发送按钮） | `=== '发送'` → `/^发\s*送$/` 正则 |
| 5 | line 770（Test 19 产品库 select） | `selectIndex=0` → `selectIndex=1` |
| 6 | line 856-858（Test 22 Modal 标签） | 模糊正则 → 加 `（heavy/light 模型` 精确匹配 |
| 7 | line 874（Test 23 Modal 保存按钮） | `=== '保存'` → `/^保\s*存$/` 正则 |

### 4.2 TypeScript 编译

```
npx tsc --noEmit  # exit 0，无错误
```

### 4.3 ASR 采样率适配参数缺失修复（BUG-032，E2E 走查期发现）

**发现时机**：v1 PR #7 已发后用户浏览器 E2E 走查；Step 3 对标验证输入抖音链接反馈：
```
ASR 状态异常: 41050008 UNSUPPORTED_SAMPLE_RATE
```

**根因**：
- 抖音原声音频采样率多为 44.1kHz（以及更高）
- 阿里云智能语音交互 filetrans 默认**仅支持 8k/16kHz**
- 旧架构 `Ai_Toolbox/0516_te/subtitle-extractor-web/lib/aliyun-asr.ts:51` 通过 `enable_sample_rate_adaptive: true` 让阿里云自动重采样
- 新架构 `app/adapters/asr.py` 实现 SubmitTask 时**漏了这个参数**

**修复**（1 行 + 重构）：

| 文件 | 改动 |
|------|------|
| `backend/app/adapters/asr.py` | 提取 `_build_task_dict(app_key, audio_url, language) -> dict` 函数（便于单测断言关键参数）+ 加 `"enable_sample_rate_adaptive": True` |
| `backend/tests/unit/services/test_asr_adapter.py` | 新增 `test_build_task_dict_includes_sample_rate_adaptive`（断言新参数 + appkey + file_link + version + language_hints 全部正确）|

**覆盖范围**：新架构所有 ASR 调用（seeding-writer Step 3 + 后续 tool_transcribe 切换）都走 `app/adapters/asr.py`，1 行修复全量生效。

**单测结果**：17/17 通过（`tests/unit/services/test_asr_adapter.py`）。

**防回归**：项目内任何 SubmitTask 必须通过 `_build_task_dict`，禁止裸构造 task dict。

**用户验收**：⚠️ 代码层已修复，用户浏览器 E2E 实际跑通验证中。

---

## 五、验收清单（DoD）

| 验收项 | 状态 | 证据 |
|--------|------|------|
| 后端 3 张表 + ORM | ✅ | `migrations/033_seeding_writer.sql` + `models/seeding_writer.py` |
| 后端 20 个 operator 接口 | ✅ | `routers/operator_seeding_writer.py` ~780 行 |
| 后端 2 个 admin 接口 | ✅ | `routers/admin_seeding_writer.py` |
| 后端 6 个 Prompt 模板 | ✅ | `services/seeding_writer_prompt.py` 14 占位符 |
| 后端文档解析器 | ✅ | `services/document_parser.py` PDF/DOCX/XLSX/PPTX/TXT |
| 前端 4 步向导页面 | ✅ | `pages/operator/SeedingWriterPage.tsx` 1412 行 |
| 前端 ConfigTab | ✅ | `pages/admin/SeedingWriterConfigTab.tsx` 283 行 |
| 前端 API 层 | ✅ | `api/seedingWriter.ts` 320 行 22 函数 |
| 前端类型定义 | ✅ | `types/seedingWriter.ts` 200 行 |
| 4 个外部 adapter 集成 | ✅ | yunwu / tikhub / oss / asr 全部接通 |
| 后端测试 101 新增 | ✅ | 970 / 973 通过（2 预存在失败无关） |
| 前端测试 23 新增 | ✅ | 180 / 180 通过 |
| 契约文档同步 | ✅ | Base_API §23 + Base_Database §27 |
| README 三处同步 | ✅ | 根 / backend / frontend |
| 红线 7 条 + 否决 9 条 | ✅ | 无触发 |

---

## 六、已知 warning（非阻塞）

| 来源 | warning | 影响 |
|------|---------|------|
| jsdom | `window.getComputedStyle(elt, pseudoElt)` not implemented | AntD Modal 滚动条测量，不影响测试断言 |
| jsdom | `navigateFetch` not implemented | Test 17 导出 .txt 触发 `<a>` click，已 mock appendChild，不影响断言 |

---

## 七、运行命令

```bash
# 后端
cd backend && source .venv311/Scripts/activate
pytest tests/unit/ tests/integration/ -v  # 970 passed
python scripts/run_coverage.py --gate     # 66.81%（达标）

# 前端
cd frontend
npx vitest run                            # 180 passed
npx tsc --noEmit                          # exit 0
```

---

## 八、后续留作独立任务

1. `tool_transcribe.py` 切换到 ASR（暂保留云雾 Whisper）
2. `service_credentials.secret_enc` 凭证加密（Sprint 3 债务）
3. `service_credentials` 软删改造（Sprint 3 债务）
4. 旧架构 `Ai_Toolbox/seeding-writer-web` 完全废弃后下线
5. 预存在的 livestream_writer `.pages` 解析失败 2 例（与本任务无关）
