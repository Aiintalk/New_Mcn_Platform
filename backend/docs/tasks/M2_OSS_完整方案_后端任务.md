# M2 — 后端任务：OSS 完整方案

> 状态：**已完成**（PR #3 已合并到 main）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_OSS_完整方案_需求文档.md`
> 对应分支：`feature/oss-adapter`（已合并）
> 前置任务：`M2_Sprint11_后端任务_oss-adapter_v1.md`（v1 仅后端接通）

---

## 一、范围（本次后端任务）

涵盖 OSS 从 Mock 到完整可用的所有后端工作：
- Migration 027（oss_call_logs 表）+ Migration 028（service_credentials 扩字段）
- ORM 模型 OssCallLog + ServiceCredential 扩 2 字段
- OSS adapter 3 函数真实接通（upload/download/delete）+ finally 块写日志
- admin_oss.py 3 个统计接口
- admin_credentials.py 测试端点 OSS 分支（调 get_bucket_info）
- files.py router 造调用场景（POST 上传 / GET download-url / DELETE）
- main.py 注册 admin_oss router
- 单测 + 集测 + 凭证测试全绿

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | Migration 027 | `backend/migrations/027_oss_call_logs.sql` | ✅ |
| B2 | Migration 028 | `backend/migrations/028_service_credentials_test_fields.sql` | ✅ |
| B3 | ORM 模型 OssCallLog + ServiceCredential 扩字段 | `backend/app/models/oss_call_log.py`, `credential.py` | ✅ |
| B4 | 注册 OssCallLog 到 `models/__init__.py` | `backend/app/models/__init__.py` | ✅ |
| B5 | OSS adapter 3 函数真实接通 | `backend/app/adapters/oss.py` | ✅ |
| B6 | admin_oss.py 3 统计接口 | `backend/app/routers/admin_oss.py` | ✅ |
| B7 | admin_credentials.py 测试端点 OSS 分支 + last_tested_at/last_latency_ms 写入 | `backend/app/routers/admin_credentials.py` | ✅ |
| B8 | files.py 改造（POST/GET/DELETE 调真 adapter） | `backend/app/routers/files.py` | ✅ |
| B9 | main.py 注册 router | `backend/app/main.py` | ✅ |
| B10 | 单元测试 14 用例 | `backend/tests/unit/services/test_oss_adapter.py` | ✅ |
| B11 | 集成测试 10 用例 | `backend/tests/integration/routers/test_admin_oss.py` | ✅ |
| B12 | 凭证测试 4 用例（OSS 分支） | `backend/tests/integration/routers/test_credentials.py` | ✅ |
| B13 | 文档同步（Base_API §10A + Base_Database §22/§23 + README） | 多处 | ✅ |

## 三、API 设计

### 3.1 统计接口（admin_oss.py）

```python
@router.get("/admin/oss/stats")        # → overview + operations + users + trend
@router.get("/admin/oss/operations")   # → 按 operation 聚合 + success_rate
@router.get("/admin/oss/users")        # → 按 user 聚合（支持 start_date/end_date/limit）
```

权限：`require_admin`。SQL 模板参照 admin_tikhub.py，字段 endpoint→operation，无 platform 维度。

### 3.2 测试端点扩展（admin_credentials.py::test_credential）

provider='oss' 分支流程：
```
读 cred → 解析 config.access_key_id/bucket/endpoint + secret_enc
→ _make_bucket(ak_id, ak_secret, endpoint, bucket)
→ asyncio.to_thread(bucket.get_bucket_info)  # 在 DB session 外调用
→ 成功：写 last_tested_at + last_latency_ms + OperationLog，返回 {status:ok, latency_ms, bucket, location, creation_date}
→ 失败：写同样字段 + error_msg，返回 {status:error, latency_ms, error}
```

## 四、测试覆盖

### 4.1 单元测试（test_oss_adapter.py，14 用例）

| 用例 | 说明 |
|------|------|
| test_upload_file_writes_call_log_success | mock bucket.put_object 成功，验证 OssCallLog(operation=upload, status=success) |
| test_upload_file_writes_call_log_failure | mock 抛异常，验证 status=fail + error_message |
| test_upload_file_no_user_id | user_id=None（系统调用），验证 user_id 字段为 NULL |
| test_get_download_url_* | download 版本同上 3 个用例 |
| test_delete_file_* | delete 版本同上 3 个用例 |
| test_get_oss_credential_* | 凭证池选取边界（无凭证/credential_id 解析） |
| 等 | |

### 4.2 集成测试（test_admin_oss.py，10 用例）

- TestAdminOssAuth：4 个鉴权（unauthorized / operator / invalid token / admin OK）
- TestOssStats：empty + with_data（shape-based 断言，因 test_session 不回滚）
- TestOssOperations：empty + with_data
- TestOssUsers：empty + with_data

### 4.3 凭证测试（test_credentials.py，4 OSS 用例）

- test_test_credential_oss_ok：mock _make_bucket.get_bucket_info 成功
- test_test_credential_oss_failure：mock 抛异常
- test_test_credential_unsupported_provider：provider='unknown'，预期 VALIDATION_ERROR
- test_test_credential_oss_missing_fields：config 缺 bucket/endpoint，预期 VALIDATION_ERROR

## 五、关键约定

- 日志写入位置在 adapter `finally` 块（仿 yunwu.py AiCallLog 模式），router 不重复写
- `oss_call_logs.operation` 取值 upload/download/delete（短字符串）
- `last_tested_at/last_latency_ms` 通用字段，ASR/AI 测试端点复用
- POST /files 大小校验用流式读取（64KB chunk），避免一次性加载
- DELETE /files OSS 清理失败**不阻塞软删**（已软删，失败仅日志记录）
