# MCN_Frontend_Agent — M1 Sprint 4 任务指令

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-07  
> 前置条件：Sprint 3 验收通过，后端 AI Key Pool API 已就绪  
> 完成后：回传 PM，等待测试 Claude 介入

---

## 必读文档

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Frontend_utf8_bom.md` ← 页面骨架
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 接口契约
3. `../project_docs/mcn_workspace_ui.jsx` ← 设计规范

---

## Sprint 4 目标

将 `/admin/config` → AI 配置 Tab 从占位状态升级为完整可用的 AI Key Pool 管理界面，包括：

- Key 列表的 CRUD（增删改查 + 测试）
- 模型列表的 CRUD（增删 + 启停 + 测试）
- 统计看板（负载率、Token 用量、趋势图）
- 筛选联动（服务商 × 状态 × 时间范围）

---

## 页面位置

```
/admin/config  →  ServiceConfigPage
  └─ Tabs
       ├─ AI 配置      (key=ai)   ← 本 Sprint 全量实现
       ├─ TikHub 配置  (key=tikhub)
       ├─ OSS 配置     (key=oss)
       └─ ASR 配置     (key=asr)
```

路由文件：`src/App.tsx`  
页面文件：`src/pages/admin/ServiceConfigPage.tsx`  
API 文件：`src/api/ai.ts`

---

## 组件结构

### AiConfigTab（主组件）

`ServiceConfigPage.tsx` 内部函数组件，当 `provider === 'ai'` 时渲染于 Tabs 卡片外侧。

**包含区域（从上到下）：**

```
AiConfigTab
├─ 筛选栏（服务商按钮组 + 状态下拉 + 时间范围下拉）
├─ 统计看板（5张 stat-card）
│    Key总数 / 负载率 / 模型数量 / Token用量 / 平均延迟
├─ 图表区（2列）
│    DonutChart（模型使用占比 SVG）
│    LineChart（Token 消耗趋势 SVG）
├─ Key 列表卡片
│    ├─ 表头 + "添加 Key" 按钮
│    └─ <table>
│         └─ <KeyRow> × N（每行独立状态）
├─ 模型列表卡片
│    ├─ 表头 + "添加模型" 按钮
│    └─ <table> × N
├─ Add Key Modal
├─ Edit Key Modal
└─ Add Model Modal
```

### KeyRow（子组件）

**文件位置：** `ServiceConfigPage.tsx` 顶部，`AiConfigTab` 之前定义。

**存在原因：** Key 秘钥的显示/隐藏（`revealed`）需要行级本地 state。若写在父组件，每次筛选导致 `AiConfigTab` 重渲染时 `revealed` 会被重置。提取为子组件后，只要 `key={k.id}` 稳定，本地 state 不受父级影响。

```typescript
interface KeyRowProps {
  k: AiKeyRecord;
  idx: number;
  testing: boolean;     // testingKeyId === k.id
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function KeyRow({ k, idx, testing, onTest, onEdit, onDelete }: KeyRowProps) {
  const [revealed, setRevealed] = useState(false);
  // ...
}
```

**列定义：**

| 列 | 字段 | 说明 |
|---|---|---|
| 序号 | idx + 1 | 筛选后序号 |
| 名称 | `k.label` | |
| 服务商 | `k.provider` | 英文值，直接展示 |
| Key 秘钥 | `k.api_key` | revealed ? 明文 : `••••••••` |
| Key 状态 | `k.status` + `k.last_tested_at` | 三态（见字段映射） |
| 并发 | `k.concurrency` / `k.max_concurrent` | |
| 测试时间 | `k.last_tested_at` + `k.last_latency_ms` | `MM-DD HH:mm · Nms` |
| 今日调用 | `k.today_calls` | |
| 总调用 | `k.total_calls` | |
| 操作 | 测试 / 编辑 / 删除 | |

### FansPanel（规划中）

> **状态：未实现，Sprint 5+ 排期**

粉丝数据面板，计划在 AI 配置 Tab 下方或独立 Tab 中展示 MCN 旗下红人的粉丝增长、互动率等聚合数据，数据源待后端设计后对齐接口。

---

## 接口调用清单

所有函数定义在 `src/api/ai.ts`，通过 `src/api/request.ts` 的 `get / post / patch / del` 封装调用。

### 统计接口

| 函数 | 方法 + 路径 | 调用时机 |
|---|---|---|
| `getAiStats(params?)` | `GET /api/admin/ai/stats` | 服务商或时间范围筛选变化时 |

请求参数：
```typescript
interface AiStatsParams {
  provider?: string;      // 服务商英文值，不传 = 全部
  start_date?: string;    // YYYY-MM-DD
  end_date?: string;
}
```

响应：`AiStatsResponse`（含 `summary` / `by_model` / `token_trend`）

### Key 接口

| 函数 | 方法 + 路径 | 调用时机 |
|---|---|---|
| `getAiKeys()` | `GET /api/admin/ai/keys` | 初始化、所有变更后 `reloadKeys()` |
| `createAiKey(body)` | `POST /api/admin/ai/keys` | 添加 Key 表单提交 |
| `updateAiKey(id, body)` | `PATCH /api/admin/ai/keys/{id}` | 编辑 Key 表单提交 |
| `deleteAiKey(id)` | `DELETE /api/admin/ai/keys/{id}` | 确认删除 |
| `testAiKey(id)` | `POST /api/admin/ai/keys/{id}/test` | 点击测试按钮 |

### 模型接口

| 函数 | 方法 + 路径 | 调用时机 |
|---|---|---|
| `getAiModels()` | `GET /api/admin/ai/models` | 初始化、所有变更后 `reloadModels()` |
| `createAiModel(body)` | `POST /api/admin/ai/models` | 添加模型表单提交 |
| `deleteAiModel(id)` | `DELETE /api/admin/ai/models/{id}` | 确认删除 |
| `updateAiModel(id, body)` | `PATCH /api/admin/ai/models/{id}` | 启用/停用切换 |
| `testAiModel(id)` | `POST /api/admin/ai/models/{id}/test` | 点击测试按钮 |

### 响应信封

后端统一返回 `{ success, data, code, message }` 信封，`request.ts` 已解包，调用层直接拿到 `data`。  
分页列表类型：`PagedData<T>` → `{ items: T[], pagination: { total, page, page_size } }`

> ⚠️ 注意：取列表数据用 `data.items ?? []`，不是 `data` 本身。

---

## 状态管理说明

### 筛选联动

```
providerFilter ('全部' | 'yunwu' | 'siliconflow' | 'glm')
statusFilter   ('全部' | '正常' | '未测试' | '停用')
timeRange      ('今日' | '近7天' | '近30天')
```

- `providerFilter` 变化 → 触发 `getAiStats` 重新请求（`useEffect` 依赖）
- `timeRange` 变化 → 同上
- `statusFilter` 变化 → 纯前端过滤 `filteredKeys`，不重新请求

**Key 过滤逻辑：**
```typescript
const filteredKeys = keys.filter(k => {
  if (providerFilter !== '全部' && k.provider !== providerFilter) return false;
  if (statusFilter === '正常'   && (k.status === 'disabled' || !k.last_tested_at))  return false;
  if (statusFilter === '未测试' && (k.status === 'disabled' || !!k.last_tested_at)) return false;
  if (statusFilter === '停用'   && k.status !== 'disabled')                          return false;
  return true;
});
```

**模型过滤逻辑：**
```typescript
const filteredModels = models.filter(m =>
  providerFilter === '全部' || m.provider === providerFilter,
);
```

### 测试状态

- `testingKeyId: number | null` — 当前正在测试的 Key id，对应行按钮显示"测试中..."并 disabled
- `testingModelId: number | null` — 同上，模型行
- 测试成功 → `message.success` + 调用 `reloadKeys()` / `reloadModels()`（用服务端最新数据更新 `last_tested_at`/`last_latency_ms`）
- 测试失败 → `message.error`，不刷新列表

### 刷新逻辑

**`reloadKeys()`** — 以下操作后调用：
- 添加 Key、编辑 Key、删除 Key
- 测试 Key 成功

**`reloadModels()`** — 以下操作后调用：
- 添加模型、删除模型、启停模型
- 测试模型成功

> 设计原则：所有变更后从后端重新拉取，不做乐观更新，避免前后端状态漂移。

### Modal 状态

```
addKeyOpen:     boolean           — 添加 Key 弹窗
editKey:        AiKeyRecord|null  — 编辑 Key 弹窗（null = 关闭）
addModelOpen:   boolean           — 添加模型弹窗
```

---

## 已知字段映射

### 服务商 provider 值

| 显示文字 | value（前端/后端存储值） | base_url 默认值 |
|---|---|---|
| 云雾 | `yunwu` | `https://yunwu.ai/v1` |
| 硅基流动 | `siliconflow` | `https://api.siliconflow.cn/v1` |
| GLM | `glm` | `https://open.bigmodel.cn/api/paas/v4` |

> ⚠️ Select.Option 的 `value` 属性必须为英文；显示文字（label）用中文。

### Key 状态（三态显示逻辑）

| 条件 | 状态标签 | 指示点颜色 |
|---|---|---|
| `k.status === 'disabled'` | 停用 | `var(--danger)` 红 |
| `!k.last_tested_at` | 未测试 | `var(--gray-300)` 灰 |
| 其他 | 正常 | `var(--success)` 绿 |

**`AiKeyRecord.status` 枚举：**
```typescript
status: 'active' | 'disabled'
```

**`service_status` 枚举（统计看板负载率卡片）：**

| 值 | 显示 | 颜色 |
|---|---|---|
| `healthy` | 正常 | `var(--success)` |
| `degraded` | 较忙 | `var(--warning, #FA8C16)` |
| `overloaded` | 超负载 | `var(--danger)` |
| `unavailable` | 不可用 | `var(--gray-400)` |

### 模型状态

**`AiModelItem.status` 枚举：**
```typescript
status: 'active' | 'inactive'
```

| 值 | 显示 | 操作按钮文字 |
|---|---|---|
| `active` | 启用（绿点） | 停用 |
| `inactive` | 停用（灰点） | 启用 |

### AiKeyRecord 字段名对照

| 前端字段 | 含义 | 旧名（已废弃） |
|---|---|---|
| `label` | Key 名称 | `name` |
| `api_key` | API 密钥 | `secret` |
| `max_concurrent` | 最大并发数 | `max_concurrency` |
| `concurrency` | 当前并发数 | — |
| `last_tested_at` | 最近测试时间 | — |
| `last_latency_ms` | 最近测试延迟 | — |

### AiModelItem 字段名对照

| 字段 | 含义 |
|---|---|
| `name` | 模型展示名称（如 `Claude Haiku 4.5`） |
| `model_id` | 调用 ID（如 `claude-haiku-4-5-20251001`） |
| `provider` | 服务商英文值 |
| `token_usage` | 累计 Token 用量 |
| `last_tested_at` | 最近测试时间 |
| `last_latency_ms` | 最近测试延迟 |

---

## 辅助函数

```typescript
// Token 格式化（null/undefined 安全）
function fmtTokens(n: number | null | undefined): string
// null/0 → '0'；>=1M → '1.2M'；>=1K → '1.2K'

// 时间格式化
function fmtTime(iso: string | null): string
// → 'MM-DD HH:mm'

// 日期范围计算（用于 stats 请求参数）
function getDateRange(range: string): { start_date: string; end_date: string }
```

---

## 验收标准

1. Key 列表从 `GET /api/admin/ai/keys` 加载，无 Mock 数据残留
2. 添加 / 编辑 / 删除 Key 均调用对应 API，操作后列表自动刷新
3. Key 秘钥眼睛按钮点击后明文可见，再次点击隐藏，切换筛选条件后不丢失
4. 模型列表从 `GET /api/admin/ai/models` 加载，增删启停均调用 API
5. 测试按钮（Key / 模型）执行期间显示"测试中..."并禁止重复点击
6. 测试成功后列表刷新，`测试时间` 列显示最新结果
7. 统计看板 5 张卡片数据来自 `GET /api/admin/ai/stats`，筛选变化后自动重新请求
8. 服务商下拉 value 均为英文（`yunwu` / `siliconflow` / `glm`）
9. 全项目 `npx tsc --noEmit` 零报错

---

## 完成后输出格式

```
# 前端 Claude 执行结果 — M1 Sprint 4
## 1. 本次任务
## 2. 完成内容（按功能列出）
## 3. 修改文件清单
## 4. 接口联调确认（每个 API 调用是否正常响应）
## 5. 自测结果
## 6. 未完成事项
## 7. 需要 PM 决策的问题
## 8. 建议下一步
```
