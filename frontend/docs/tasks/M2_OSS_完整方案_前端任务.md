# M2 — 前端任务：OSS 完整方案

> 状态：**已完成**（PR #3 已合并到 main）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_OSS_完整方案_需求文档.md`
> 对应分支：`feature/oss-adapter`（已合并）

---

## 一、范围（本次前端任务）

涵盖 OSS Tab 从通用凭证模型到完整独立组件的所有前端工作：
- `api/oss.ts` 新建（3 统计函数 + 类型）
- `types/credential.ts` 扩字段（last_tested_at/last_latency_ms）
- `ServiceConfigPage.tsx` 新增 OssConfigTab 组件（4 卡 + 2 图 + 3 子 Tab + OSS 专属表单）
- 主 ServiceConfigPage 函数改造：剥离 OSS 通用分支、加独立渲染、Modal 去 OSS Option
- 前端测试 12 用例（OssConfigTab.test.tsx）全绿

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 新建 api/oss.ts | `frontend/src/api/oss.ts` | ✅ |
| F2 | ServiceCredential 类型扩字段 | `frontend/src/types/credential.ts` | ✅ |
| F3 | OssDonutChart 组件（复制 TikHubDonutChart） | `frontend/src/pages/admin/ServiceConfigPage.tsx` | ✅ |
| F4 | OssLineChart 组件 | 同上 | ✅ |
| F5 | OssConfigTab 组件完整实现 | 同上 | ✅ |
| F6 | 主 ServiceConfigPage load() 跳过 OSS | 同上 | ✅ |
| F7 | page-actions + 内容渲染加 `provider !== 'oss'` | 同上 | ✅ |
| F8 | Tab content 加 `{provider === 'oss' && <OssConfigTab />}` | 同上 | ✅ |
| F9 | 新增 Key Modal 删除 OSS Option | 同上 | ✅ |
| F10 | PROVIDER_TABS 加 OSS | 同上 | ✅ |
| F11 | 前端测试 12 用例 | `frontend/src/__tests__/components/pages/OssConfigTab.test.tsx` | ✅ |

## 三、OssConfigTab 实现要点

### 3.1 表单字段（OSS 专属 7 字段）

| 字段 | 类型 | 校验 |
|------|------|------|
| 备注 (label) | Input | required |
| AccessKey ID | Input | required |
| AccessKey Secret | Input.Password | required |
| Bucket | Input | required |
| Endpoint | Input | required（如 `oss-cn-hangzhou.aliyuncs.com`）|
| Region | Select | 可选（从 endpoint 推断或手选） |
| 权重 | Number | 默认 10 |

### 3.2 凭证列表列

`#` / 备注 / Bucket / Endpoint（脱敏）/ 状态 / 今日调用 / 累计调用 / 上次测试 / 权重 / 操作（测试/编辑/启停/删除）

### 3.3 统计 + 图表

- 4 卡：总调用 / 今日调用 / 平均延迟 / 活跃凭证（蓝色主题 `#1890FF`）
- OssDonutChart：操作分布（upload/download/delete），饼图中心显示"操作"
- OssLineChart：近 7 天调用趋势折线图（数据点 ≥2 才渲染）

### 3.4 子 Tab 切换

3 个子 Tab 凭证管理/操作统计/用户排行通过 `handlePanelSwitch(tab)` 触发懒加载（不用 useEffect），便于测试。

## 四、测试覆盖（OssConfigTab.test.tsx，12 用例）

| 用例 | 说明 |
|------|------|
| renders empty state when no credentials | 凭证为空显示"暂无 OSS 凭证" |
| renders 4 stat cards with zeros when stats empty | 4 卡 label 都在；至少 2 个 0 |
| renders stat cards with real values from stats API | 模拟真实数据，验证千分位/单位（1234 / 56 / 120ms / 2 / 3） |
| renders donut chart when operations data exists | 饼图渲染（操作 + operation 名） |
| renders line chart when trend has >= 2 data points | 折线图渲染（日期标签可见） |
| renders 3 sub-tab labels | 凭证管理/操作统计/用户排行 3 个标签 |
| switches to operations sub-tab and loads operation details on click | 切到操作统计，懒加载详情，验证 success_rate 百分比 |
| switches to users sub-tab and loads user ranking on click | 切到用户排行，懒加载，验证 username/role/calls |
| renders credential rows with bucket and endpoint when data exists | 凭证列表渲染（label/bucket/endpoint） |
| opens add modal and shows all OSS-specific fields | 新增弹窗显示所有 OSS 必备字段 |
| submits new credential with config field correctly assembled | 填表 + 提交，验证 createCredential 调用参数（provider=oss, api_key=secret, config 含 access_key_id/bucket） |
| invokes testOssCredential when test button clicked | 测试按钮调 testOssCredential(id) |

## 五、关键约定

- 所有 JSON 调用走 `request.ts`（红线 #3）
- TypeScript 类型检查通过（`npx tsc --noEmit` exit 0）
- 颜色主题蓝色（#1890FF）与 TikHub 同色系，与 ASR 紫色（#722ED1）区分
- 图表组件复制 TikHub 版本改名（字段差异：endpoint→operation）
- AppKey/Secret 脱敏显示：AccessKey ID 显示前 12 位 + `****`
