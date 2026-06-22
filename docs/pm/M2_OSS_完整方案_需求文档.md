# M2 — OSS 完整方案（阿里云对象存储）需求文档

> 文档状态：**已实施（补档）** —— 本文档在工作完成后补写，作为流程闭环与未来参考
> 完成日期：2026-06-22（PR #3 已合并到 main）
> 对应分支：`feature/oss-adapter`（已合并）
> 工作阶段：M2（非 Sprint 制，基础设施 + 管理 Tab）

---

## 一、功能概述

**功能名称**：OSS 对象存储 完整方案
**服务商**：阿里云 OSS（对象存储）
**分类**：基础设施 + 管理端配置
**管理路由**：`/admin/service-config`（OSS Tab）

**核心定位**：把 OSS 从 M1 起的 Mock 占位（`get_download_url` 返假 URL，`upload_file` 抛 `NotImplementedError`）改造为：
1. 真实接通阿里云 OSS 的 adapter（上传/下载/删除）
2. 每次 adapter 调用产生 `oss_call_logs` 日志（统计基础）
3. 3 个 admin 统计接口（参照 TikHub 范式）
4. 通用凭证测试端点扩 OSS 分支（调 `bucket.get_bucket_info` 轻量验证）
5. 前端 OSS Tab 完整复刻 TikHub：4 张统计卡 + 操作分布饼图 + 7 天趋势折线图 + 3 子 Tab（凭证管理/操作统计/用户排行）+ OSS 专属字段表单（AccessKey ID/Secret/Bucket/Endpoint）

**驱动场景**：
- 管理员配置/轮换 OSS 凭证
- 业务 router（files / outputs）通过 adapter 上传/下载/删除 OSS 文件
- 管理端 OSS Tab 看到真实使用统计

---

## 二、功能需求

### 2.1 后端 Adapter（app/adapters/oss.py）

3 公开函数 + 2 内部 helper：

| 函数 | 签名 | 日志 operation |
|------|------|----------------|
| `upload_file(oss_key, content, content_type, db, user_id=None) → str` | 真实 `bucket.put_object` | `upload` |
| `get_download_url(oss_key, db, expires=3600) → str` | 签名 URL（1h 有效） | `download` |
| `delete_file(oss_key, db) → None` | `bucket.delete_object` | `delete` |
| `_get_oss_credential(db) → tuple` | 凭证池选取 | — |
| `_make_bucket(ak_id, ak_secret, endpoint, bucket) → Bucket` | oss2 SDK 封装 | — |

每个公开函数在 `finally` 块写 OssCallLog + commit，确保成功/失败都留痕（仿 yunwu AiCallLog 模式）。

### 2.2 后端统计接口（app/routers/admin_oss.py）

3 个 GET，权限 `admin`，参照 admin_tikhub.py：

| 路径 | 返回 |
|------|------|
| `GET /api/admin/oss/stats` | overview（总调用/今日/平均延迟/活跃凭证）+ operations[] + users[] + trend[] |
| `GET /api/admin/oss/operations` | 按 operation 聚合：calls / percentage / avg_latency_ms / success_rate |
| `GET /api/admin/oss/users` | 按用户聚合：user_id / username / role / calls / last_called_at |

### 2.3 通用凭证测试端点扩展（admin_credentials.py）

`POST /api/admin/config/credentials/{id}/test` 支持 provider='oss' 分支：
- 调 `bucket.get_bucket_info()` 最轻量验证（比 list_objects 更省）
- 成功/失败都写 `last_tested_at` + `last_latency_ms`（通用字段）
- 写 OperationLog

### 2.4 造调用场景（app/routers/files.py）

OSS adapter 接通后**无任何 router 调用方** → 统计永远为 0。必须造调用场景：
- `POST /api/files`：上传到 OSS（50MB 限制，oss_key 命名 `uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}`）
- `GET /api/files/{id}/download-url`：改真（调 adapter）
- `DELETE /api/files/{id}`：软删数据库 + OSS 清理（失败不阻塞软删）

### 2.5 前端 OSS Tab（ServiceConfigPage.tsx）

独立组件 `OssConfigTab`，完整复刻 TikHub 架构：
- 4 统计卡：总调用 / 今日调用 / 平均延迟 / 活跃凭证（蓝色主题 #1890FF）
- OssDonutChart（操作分布）+ OssLineChart（7 天趋势）
- 3 子 Tab：凭证管理 / 操作统计 / 用户排行
- 凭证表单字段：AccessKey ID / AccessKey Secret / Bucket / Endpoint / 权重（+ 备注 label）
- 凭证列表列：备注 / Bucket / Endpoint / 状态 / 权重 / 上次测试 / 操作
- 测试按钮调真后端接口（不再误调 AI Key 测试）
- 通用"新增 Key"Modal 剥离 OSS Option（走独立 Tab）

---

## 三、数据模型

### 3.1 新建表 `oss_call_logs`（Migration 027）

```sql
CREATE TABLE oss_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES service_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       REFERENCES users(id) ON DELETE SET NULL,
  operation     VARCHAR(16)  NOT NULL,  -- upload / download / delete
  status        VARCHAR(32)  NOT NULL,  -- success / fail
  latency_ms    INT,
  oss_key       TEXT,
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
-- 5 索引：credential_id / user_id / operation / status / created_at DESC
```

### 3.2 扩展表 `service_credentials`（Migration 028）

```sql
ALTER TABLE service_credentials
  ADD COLUMN IF NOT EXISTS last_tested_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_latency_ms INTEGER;
```

字段**通用**（不限定 provider='oss'），ASR/AI 等其他 provider 测试端点可复用。

---

## 四、接口契约

### 4.1 Base_API §10A（OSS 凭证与调用统计接口）

涵盖：3 个统计接口 + 通用凭证 CRUD（provider=oss 分支）+ 测试端点行为 + 文件接口（POST /files 上传 / GET download-url / DELETE）。

### 4.2 Base_Database §22 + §23

- §22 oss_call_logs 表字段说明 / 索引 / 写入位置 / 迁移文件
- §23 service_credentials 扩展字段说明 / 通用性 / 迁移文件

---

## 五、前端契约

### 5.1 类型（types/credential.ts）

`ServiceCredential` 扩字段：`last_tested_at: string | null` + `last_latency_ms: number | null`。

### 5.2 API 模块（api/oss.ts）

3 统计函数 + 类型定义（OssStatsResponse / OssOperationDetail / OssUserDetail）。凭证 CRUD 走通用 credentials.ts。

---

## 六、测试要求

| 维度 | 用例数 | 说明 |
|------|--------|------|
| 后端单元（test_oss_adapter.py） | 14 | upload/delete/download 成功写日志 / upload 失败写日志 / user_id=None / 等 |
| 后端集成（test_admin_oss.py） | 10 | 4 鉴权 + 2 stats + 2 operations + 2 users |
| 凭证测试端点 | 4 | OSS ok / OSS failure / 非支持 provider / 字段缺失 |
| 前端测试（OssConfigTab.test.tsx） | 12 | 4 卡渲染 / 统计值 / 饼图 / 折线图 / 3 子 Tab / 切换加载 / 凭证 CRUD / 测试按钮 |

全绿 + TypeScript 类型检查通过。

---

## 七、不在本次范围（留后续独立任务）

- **TikHub adapter 日志写入 bug**：TikHub adapter 调用时不写 `tikhub_call_logs`，导致 TikHub Tab 统计不准。规模大，独立任务
- **service_credentials.secret_enc 加密**：Sprint 3 债务，目前明文存储
- **service_credentials 软删改造**：Sprint 3 债务，目前物理删除
- **outputs 产出迁移到 OSS**：业务侧改造，独立任务

---

## 八、验收标准

1. ✅ 管理员 OSS Tab 看到 4 张统计卡片、2 张图表、3 个子 Tab
2. ✅ 管理员可配置 OSS 凭证（AccessKey ID/Secret/Bucket/Endpoint + 权重）
3. ✅ 测试端点验证 OSS 凭证连通性（`bucket.get_bucket_info`）
4. ✅ OSS adapter 三函数完整实现，每次调用产生 oss_call_logs 记录
5. ✅ 凭证列表新增列：上次测试时间 + 延迟
6. ✅ 所有测试通过（后端 pytest + 前端 vitest）
7. ✅ 契约文档同步（Base_API §10A + Base_Database §22/§23）
8. ✅ 前后端 README + 根 README 同步
9. ✅ PM 记忆与状态更新

---

## 九、实施回顾（补档说明）

本功能实际经历 3 个递进子任务，全部合入 PR #3：
1. **阿里云 OSS Adapter 后端接通**（v1，仅后端真实接通 + 连通性测试）
2. **OSS 配置前端 UI 完善**（前端独立 Tab + 连通性测试端点）
3. **OSS 使用显示完整对齐 TikHub**（建 oss_call_logs + 统计接口 + files router + 4 卡 + 2 图 + 3 子 Tab）

任务文档分散在 `backend/docs/tasks/M2_Sprint11_后端任务_oss-adapter_v1.md`（仅 v1）+ 本方案新增的综合任务文档。前端无历史任务文档，本次补齐。
