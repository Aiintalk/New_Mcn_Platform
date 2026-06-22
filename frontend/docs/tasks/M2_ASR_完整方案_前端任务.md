# M2 — 前端任务：ASR 完整方案

> 状态：**已完成**（PR #4 已提交待合并）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_ASR_完整方案_需求文档.md`
> 对应分支：`feature/asr-tab`

---

## 一、范围（本次前端任务）

涵盖 ASR Tab 从零到完整独立组件的所有前端工作：
- `api/asr.ts` 新建（3 统计函数 + 类型）
- `ServiceConfigPage.tsx` 新增 AsrConfigTab 组件（紫色主题，4 卡 + 2 图 + 3 子 Tab + ASR 专属表单）
- 主 ServiceConfigPage 函数改造：剥离 ASR 通用分支、加独立渲染、Modal 去 ASR Option
- 前端测试 12 用例（AsrConfigTab.test.tsx）全绿

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 新建 api/asr.ts（3 统计函数 + 类型） | `frontend/src/api/asr.ts` | ✅ |
| F2 | AsrDonutChart 组件（紫色 #722ED1） | `frontend/src/pages/admin/ServiceConfigPage.tsx` | ✅ |
| F3 | AsrLineChart 组件 | 同上 | ✅ |
| F4 | ASR_REGIONS 常量 | 同上 | ✅ |
| F5 | AsrConfigTab 组件完整实现 | 同上 | ✅ |
| F6 | 主 ServiceConfigPage load() 跳过 ASR | 同上 | ✅ |
| F7 | page-actions + 内容渲染加 `provider !== 'asr'` | 同上 | ✅ |
| F8 | Tab content 加 `{provider === 'asr' && <AsrConfigTab />}` | 同上 | ✅ |
| F9 | 新增 Key Modal 删除 ASR Option | 同上 | ✅ |
| F10 | PROVIDER_TABS 加 ASR | 同上 | ✅ |
| F11 | 前端测试 12 用例 | `frontend/src/__tests__/components/pages/AsrConfigTab.test.tsx` | ✅ |

## 三、AsrConfigTab 实现要点

### 3.1 表单字段（ASR 专属 6 字段）

| 字段 | 类型 | 校验 |
|------|------|------|
| 备注 (label) | Input | required（如 "上海生产环境"） |
| AppKey | Input | required（阿里云 ISI 项目 AppKey） |
| AccessKey ID | Input | required（LTAI... 开头） |
| AccessKey Secret | Input.Password | required |
| Region | Select | required，预设 cn-shanghai，选项 `华东2(上海)/华北2(北京)/华南1(深圳)` |
| 权重 | Number | 默认 10 |

### 3.2 提交时 secret_enc 拼接

```typescript
// 新增：两个字段合并为 secret_enc
api_key: `${v.access_key_id}\n${v.access_key_secret}`,
config: { app_key: v.app_key, region: v.region }

// 编辑（轮换密钥）：ID 和 Secret 必须同时填
if (v.access_key_id && v.access_key_secret) {
  payload.api_key = `${v.access_key_id}\n${v.access_key_secret}`;
} else if (v.access_key_id || v.access_key_secret) {
  message.warning('轮换密钥时 AccessKey ID 和 Secret 必须同时填写');
  return;  // 拦截
}
```

### 3.3 凭证列表列

`#` / 备注 / AppKey（前 8 位 + `****` 脱敏） / Region / 状态 / 权重 / 上次测试（时间 + 延迟） / 操作（测试/编辑/启停/删除）

### 3.4 统计 + 图表

- 4 卡：总调用 / 今日调用 / 平均延迟（橙 `#FF7A45`） / 活跃凭证（青 `#37C2C2`）
- AsrDonutChart：操作分布（submit/query），紫色 `#722ED1`
- AsrLineChart：近 7 天趋势，紫色 stroke
- ASR_COLORS 数组：`['#722ED1', '#9254DE', '#B37FEB', '#D3ADF7', '#EFDBFF']`

### 3.5 测试按钮实现

通过动态 import 调通用测试端点（后端按 provider 分支）：
```typescript
const { testOssCredential: testCred } = await import('../../api/credentials');
const r = await testCred(id);  // 后端会识别 provider=asr 走 ASR 测试逻辑
```

## 四、测试覆盖（AsrConfigTab.test.tsx，12 用例）

| 用例 | 说明 |
|------|------|
| renders empty state when no credentials | 凭证为空显示"暂无 ASR 凭证" |
| renders 4 stat cards with zeros when stats empty | 4 卡 label 都在；至少 2 个 0 |
| renders stat cards with real values from stats API | 模拟真实数据，验证 `2,345` / `78` / `210ms` / `2 / 4` |
| renders donut chart when operations data exists | 饼图渲染（"操作" 标签 + "submit" 名） |
| renders line chart when trend has >= 2 data points | 折线图渲染（日期标签可见） |
| renders 3 sub-tab labels | 凭证管理/操作统计/用户排行 3 个标签 |
| switches to operations sub-tab and loads operation details on click | 切到操作统计，懒加载，验证 80% / 95.0% |
| switches to users sub-tab and loads user ranking on click | 切到用户排行，懒加载，验证 username/role/calls |
| renders credential rows with masked AppKey and region when data exists | 凭证列表渲染，AppKey 前 8 位脱敏（`fvY8kxR6`），region 可见 |
| opens add modal and shows all ASR-specific fields | 新增弹窗显示 AppKey/AccessKey ID/Secret/Region |
| submits new credential with api_key assembled as id\nsecret | 填表 + 提交，验证 `api_key: 'LTAI1234\nsecret5678'`（关键：`\n` 真换行） |
| invokes testOssCredential when test button clicked | 测试按钮调 testOssCredential(id)（后端按 provider 分支） |

## 五、关键约定

- 所有 JSON 调用走 `request.ts`（红线 #3）
- TypeScript 类型检查通过（`npx tsc --noEmit` exit 0）
- 紫色主题（#722ED1）与 OSS 蓝色（#1890FF）视觉区分
- AsrConfigTab 用通用 credentials.ts 做 CRUD（provider='asr' 参数区分）
- AppKey 脱敏：前 8 位 + `****`（如 `fvY8kxR6****`）
- 表单初始化时 region 预设 cn-shanghai（`addForm.setFieldsValue({ region: 'cn-shanghai' })`）
- Region Select 显示中文 label（`华东2(上海)`），提交时用 value（`cn-shanghai`）
