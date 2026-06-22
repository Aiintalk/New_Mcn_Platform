# M2 — ASR 完整方案（阿里云智能语音交互）需求文档

> 文档状态：**已实施（补档）** —— 本文档在工作完成后补写，作为流程闭环与未来参考
> 完成日期：2026-06-22（PR #4 已提交待合并）
> 对应分支：`feature/asr-tab`
> 工作阶段：M2（非 Sprint 制，基础设施 + 管理 Tab）

---

## 一、功能概述

**功能名称**：ASR 语音识别 完整方案
**服务商**：阿里云智能语音交互（Intelligent Speech Interaction, ISI）— 录音文件识别（异步 API）
**分类**：基础设施 + 管理端配置
**管理路由**：`/admin/service-config`（ASR Tab）

**核心定位**：为平台接入阿里云录音文件识别能力，作为独立功能模块（**不改 `tool_transcribe.py`，继续用云雾 Whisper**）。包括：
1. ASR adapter（3 公开函数 + 5 helper），POP RPC 风格 + CommonRequest
2. 每次 adapter 调用产生 `asr_call_logs` 日志（submit / query 双操作分类）
3. 3 个 admin 统计接口（参照 OSS/ TikHub 范式）
4. 通用凭证测试端点扩 ASR 分支（调 `GetTaskResult` 用 probe TaskId，不依赖测试音频）
5. 前端 ASR Tab 完整复刻 OSS 范式：4 张统计卡 + 饼图 + 折线图 + 3 子 Tab + ASR 专属字段表单（AppKey/AccessKey ID/AccessKey Secret/Region）

**驱动场景**：
- 管理员配置/轮换 ASR 凭证（与 OSS 可共享同一 RAM AccessKey）
- 业务侧（未来）：录音文件转写、字幕生成等
- 管理端 ASR Tab 看到真实使用统计

---

## 二、功能需求

### 2.1 后端 Adapter（app/adapters/asr.py）

3 公开函数 + 5 内部 helper：

| 函数 | 签名 | 日志 operation |
|------|------|----------------|
| `submit_transcription(audio_url, db, user_id=None, language="zh-CN") → str` | 提交任务，返回 TaskId | `submit`（带 audio_url） |
| `query_transcription(task_id, db, user_id=None) → dict` | 查询任务，返回 {StatusText, StatusCode, Result?} | `query`（带 task_id） |
| `transcribe(audio_url, db, user_id=None, poll_interval=10, max_wait=600) → str` | 便捷封装：submit → 轮询 query → 返回文本 | 不直接写（由两个子调用各自写） |
| `_make_domain(region) → str` | filetrans 拼接 | — |
| `_make_client(ak_id, ak_secret, region) → AcsClient` | SDK 封装 | — |
| `_build_submit_request(...)` | POP RPC CommonRequest | — |
| `_build_query_request(task_id)` | POP RPC CommonRequest | — |
| `_get_asr_credential(db) → tuple` | 凭证池选取 | — |

每个公开函数在 `finally` 块写 AsrCallLog + commit。

### 2.2 后端统计接口（app/routers/admin_asr.py）

3 个 GET，权限 `admin`，参照 admin_oss.py：

| 路径 | 返回 |
|------|------|
| `GET /api/admin/asr/stats` | overview + operations[] + users[] + trend[] |
| `GET /api/admin/asr/operations` | 按 operation 聚合（submit/query） |
| `GET /api/admin/asr/users` | 按用户聚合 |

### 2.3 通用凭证测试端点扩展（admin_credentials.py）

`POST /api/admin/config/credentials/{id}/test` 支持 provider='asr' 分支：
- **不调 SubmitTask**（避免依赖测试音频文件）
- 改调 `GetTaskResult` 用固定 probe TaskId（`test-connectivity-probe-task-id`）
- 阿里云必返回业务错误（如 `41050010 TASK_EXPIRED`），只要不抛认证/签名异常，就认为连通 OK
- 写 `last_tested_at` + `last_latency_ms` + OperationLog

提取 `_record_test_outcome` 辅助函数消除 OSS/ASR 两个分支的重复代码。

### 2.4 前端 ASR Tab（ServiceConfigPage.tsx）

独立组件 `AsrConfigTab`，完整复刻 OSS 架构：
- 4 统计卡：总调用 / 今日调用 / 平均延迟 / 活跃凭证（**紫色主题 #722ED1** 与 OSS 蓝色区分）
- AsrDonutChart + AsrLineChart
- 3 子 Tab：凭证管理 / 操作统计 / 用户排行
- 凭证表单字段：备注 / AppKey / AccessKey ID / AccessKey Secret / Region（下拉 cn-shanghai/cn-beijing/cn-shenzhen） / 权重
- 凭证列表列：# / 备注 / AppKey（前 8 位 + **** 脱敏） / Region / 状态 / 权重 / 上次测试 / 操作
- 表单提交时 `api_key` 拼接为 `${access_key_id}\n${access_key_secret}`（secret_enc 格式）
- 编辑表单轮换密钥校验：AccessKey ID 和 Secret 必须同时填，否则 warning 拦截
- 通用"新增 Key"Modal 剥离 ASR Option（走独立 Tab）

---

## 三、数据模型

### 3.1 新建表 `asr_call_logs`（Migration 029）

```sql
CREATE TABLE asr_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES service_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       REFERENCES users(id) ON DELETE SET NULL,
  operation     VARCHAR(16)  NOT NULL,  -- submit / query
  status        VARCHAR(32)  NOT NULL,  -- success / fail
  latency_ms    INT,
  task_id       TEXT,                   -- ASR 任务 ID
  audio_url     TEXT,                   -- 仅 submit 记录
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
-- 5 索引：credential_id / user_id / operation / status / created_at DESC
```

### 3.2 凭证字段约定（service_credentials 中 provider='asr'）

- `config`：`{"app_key": "项目AppKey", "region": "cn-shanghai|cn-beijing|cn-shenzhen"}`
- `secret_enc`：`"access_key_id\naccess_key_secret"`（两行，与 OSS 单一 secret 不同）
- 共用 `last_tested_at` / `last_latency_ms`（Migration 028 已加）

---

## 四、接口契约

### 4.1 Base_API §10B（ASR 凭证与调用统计接口）

涵盖：3 个统计接口 + 通用凭证 CRUD（provider=asr 分支）+ 测试端点行为 + config / api_key 字段格式说明。

### 4.2 Base_Database §24

- asr_call_logs 表字段说明 / 索引 / 写入位置 / 凭证字段约定 / 迁移文件

---

## 五、前端契约

### 5.1 API 模块（api/asr.ts）

3 统计函数 + 类型定义（AsrStatsResponse / AsrOperationDetail / AsrUserDetail / AsrCredential 等）。CRUD 实际走通用 credentials.ts（API 层定义类型但函数不调用）。

### 5.2 ServiceConfigPage.tsx 集成

- `PROVIDER_TABS` 加 `{ key: 'asr', label: 'ASR 配置' }`
- 主 `load()` 函数加 `if (provider === 'asr') return;`（跳过通用加载）
- `page-actions` / 内容渲染区加 `provider !== 'asr'` 条件
- Tab content 区加 `{provider === 'asr' && <AsrConfigTab />}`
- 新增 Key Modal 删除 `<Select.Option value="asr">`

---

## 六、测试要求

| 维度 | 用例数 | 说明 |
|------|--------|------|
| 后端单元（test_asr_adapter.py） | 16 | 4 submit + 2 query + 4 transcribe（含超时/失败）+ 3 日志写入 + 3 凭证解析边界 |
| 后端集成（test_admin_asr.py） | 10 | 4 鉴权 + 2 stats + 2 operations + 2 users |
| 凭证测试端点（test_credentials.py 扩展） | 4 | ASR ok / ASR failure / missing_app_key / invalid_secret_format |
| 前端测试（AsrConfigTab.test.tsx） | 12 | 4 卡渲染 / 统计值 / 饼图 / 折线图 / 3 子 Tab / 切换加载 / AppKey 脱敏 / 新增表单 / api_key 拼接 / 测试按钮 |

全绿 + TypeScript 类型检查通过。

---

## 七、不在本次范围（留后续独立任务）

- **tool_transcribe 改造**：现在继续用云雾 Whisper。改造为 ASR（或凭证池路由）作为后续任务
- **TikHub adapter 日志写入 bug**：Sprint 11 OSS 任务时发现，独立修复
- **service_credentials.secret_enc 加密**：Sprint 3 债务。ASR 的 `access_key_id\naccess_key_secret` 同样明文（继承债务）
- **service_credentials 软删改造**：Sprint 3 债务
- **ASR 业务集成**：把 tool_transcribe 调用方（千川剪辑预审、TT 复盘）切到 ASR

---

## 八、验收标准

1. ✅ 管理员 ASR Tab 看到 4 张统计卡片、2 张图表、3 个子 Tab
2. ✅ 管理员可配置 ASR 凭证（AppKey + AccessKey ID + AccessKey Secret + Region + 权重）
3. ✅ 测试端点能验证 ASR 凭证连通性（不依赖外部音频文件）
4. ✅ ASR adapter 三函数完整实现：submit / query / transcribe
5. ✅ 每次 adapter 调用产生 asr_call_logs 记录
6. ✅ 凭证列表新增列：AppKey（脱敏）/ Region / 上次测试时间+延迟
7. ✅ 所有测试通过（后端 pytest + 前端 vitest）
8. ✅ 契约文档同步（Base_API §10B + Base_Database §24）
9. ✅ 前后端 README + 根 README 同步
10. ✅ PM 记忆与状态更新

---

## 九、关键技术决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | SDK | `aliyun-python-sdk-core>=2.13.12` + `CommonRequest` | 官方 Python demo 使用，轻量，HTTP 风格，与 oss2 兼容 |
| 2 | 端点 | `filetrans.cn-shanghai.aliyuncs.com` | 默认上海 region，CommonRequest 按 region 拼接 |
| 3 | API | `Action=SubmitTask` (POST) + `Action=GetTaskResult` (GET) | 录音文件识别两个核心 POP RPC action，API_VERSION 2018-08-17 |
| 4 | 凭证字段存储 | `config={app_key, region}`，`secret_enc="access_key_id\naccess_key_secret"` | 与 OSS 一致：config 放非敏感元数据，secret_enc 放密钥 |
| 5 | operation 分类 | `submit` / `query`（两条记录/完整 ASR 调用） | 便于统计两个 API 的延迟分布 |
| 6 | 轮询策略 | adapter 内 `transcribe()` 封装 submit→poll→result；`poll_interval=10s`，`max_wait=600s` | 业务侧一次调用拿结果，超时抛 RuntimeError |
| 7 | 测试端点 | 只调 `GetTaskResult` 用 probe TaskId（不调 SubmitTask） | 不依赖测试音频文件；probe TaskId 必返回业务错误但能验证 AK 签名 |
| 8 | 表名 | `asr_call_logs`（对齐 `oss_call_logs`） | 命名一致性 |
| 9 | 文件输入 | adapter 只接受 URL（本地文件需先上传 OSS 拿 URL） | 阿里云 ASR 只接受 URL；OSS 已接通 |
| 10 | tool_transcribe | 不改（保留云雾 Whisper） | 用户明确要求；作为后续独立任务 |

---

## 十、实施回顾（补档说明）

本功能作为完整方案一次性完成（PR #4），不像 OSS 那样分 3 个子任务递进。任务文档前后端各 1 份：
- `backend/docs/tasks/M2_ASR_完整方案_后端任务.md`
- `frontend/docs/tasks/M2_ASR_完整方案_前端任务.md`
