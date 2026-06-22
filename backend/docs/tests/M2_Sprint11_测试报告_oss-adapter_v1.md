# M2 Sprint 11 — 测试报告：阿里云 OSS Adapter 接入 v1

> 日期：2026-06-18
> 测试范围：后端单元测试 + 连通性测试（默认跳过）+ 全量回归
> 对应任务单：`backend/docs/tasks/M2_Sprint11_后端任务_oss-adapter_v1.md`

---

## 一、改动范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/adapters/oss.py` | 重写 | Mock 占位 → 真实阿里云 OSS 实现（`upload_file` / `get_download_url` / `delete_file` / `_get_oss_credential` / `_make_bucket`）；字段映射与通用凭证 API 对齐（`label`=备注名，`config.access_key_id`=AK ID） |
| `backend/tests/unit/services/test_oss_adapter.py` | 新增 | 9 个单元测试（纯 mock） |
| `backend/tests/integration/test_oss_live.py` | 新增 | 连通性测试（`skipif` + `@pytest.mark.live`，默认跳过） |
| `backend/pytest.ini` | 修改 | 加 `markers = live: ...` |
| `backend/docs/tasks/M2_Sprint11_后端任务_oss-adapter_v1.md` | 新增 | PM 任务单 |
| `backend/docs/README.md` | 修改 | oss.py 注释：对象存储 → 真实接通 |
| `docs/pm/PM_记忆与状态_M2.md` | 修改 | Sprint 11 加 OSS adapter 条目 |

---

## 二、自动化测试结果

### 单元测试（adapter 层，纯 mock）

| 测试文件 | 通过 / 总计 |
|---------|------------|
| `tests/unit/services/test_oss_adapter.py` | 9 / 9 ✅ |

覆盖点：
- `upload_file`：成功路径（to_thread put_object + report_success）、失败路径（oss2 异常 → report_failure + 包装为 RuntimeError 传播）
- `get_download_url`：成功路径（to_thread sign_url + report_success）、失败路径
- `delete_file`：成功路径（to_thread delete_object + report_success）、失败路径
- `_get_oss_credential` 边界：config 缺 `bucket` / 缺 `endpoint` / 缺 `access_key_id` → 各自抛 KeyError（都在 try 块外，不 report_failure）

### 覆盖率

| 模块 | 覆盖率 | 门禁 | 状态 |
|------|--------|------|------|
| `app/adapters/oss.py` | **89%** | ≥ 60%（adapter 门禁） | ✅ PASS |

未覆盖行：`_make_bucket` 函数体（被 mock，不实际执行 oss2.Auth）+ `if result.status != 200` 防御性检查（oss2 在非 2xx 时会抛 OssError，正常不会到这里）。

### 连通性测试（默认跳过，本次已通过 ✅）

| 测试文件 | 默认状态 | 启用方式 |
|---------|---------|---------|
| `tests/integration/test_oss_live.py` | SKIPPED | `OSS_LIVE_TEST=1 + OSS_ACCESS_KEY_ID/SECRET/BUCKET env vars` |

启用前置条件：
1. 阿里云 OSS Bucket 已创建，RAM 子账号有读写权限
2. 设置环境变量（详见任务单 §7）：
   - `OSS_LIVE_TEST=1`
   - `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_BUCKET`
   - 可选：`OSS_ENDPOINT` / `OSS_REGION`

**本次执行结果**：✅ PASSED（2026-06-18，bucket=`aitoolboxte`，6.97 秒）

完整链路（已验证）：
1. 测试启动 → conftest 在 `mcn_test` 库 `create_all` 建表
2. live test 从 env 读凭证 → INSERT 到 `service_credentials` 表
3. `upload_file` → 真实 PUT 到 OSS bucket
4. `get_download_url` → 生成签名 URL
5. httpx GET 验证 → HTTP 200 + 内容字节一致
6. `delete_file` → DELETE 清理 OSS 对象
7. 测试结束 → conftest `drop_all` 清表（凭证自然消失）

设计要点：
- 凭证通过 env var 传入（**不写进代码、不写进 SQL 文件**）
- 测试内部动态插凭证，依赖 mcn_test 库 conftest 自动建表
- Secret 只在 shell 中存在，关 shell / unset 即消失

### 全量回归

```
4 failed, 692 passed, 1 skipped（OSS live test）, 4 errors
```

预存失败（与 OSS 改动无关）：
- `test_convention_guard.py::test_write_ops_have_operation_log` × 1 + `test_scan_summary` × 1：5 个其他 router（`admin_livestream_review`、`admin_persona_review`、`operator_livestream_review`、`operator_livestream_writer`、`operator_persona_review`）缺 OperationLog 写入（红线 #2）
- `test_livestream_writer_file_parser.py::test_pages_extracts_chinese_text` × 1 + `test_pages_filters_calendar_noise` × 1：缺 `snappy` Python 模块（.pages 文件压缩依赖，与 OSS 无关）
- `tests/concurrent/test_isolation.py` × 4 errors：同样缺 `snappy` 模块（collection 阶段失败）

预存 collection error（与 OSS 改动无关）：
- `tests/intake/conftest.py`：`pytest_plugins` 在非顶层 conftest（pytest 7+ 不再支持）

OSS 改动**零回归**：上述 4 failed + 4 errors 在 main 分支已存在，不在本次改动路径上。

---

## 三、API 验证

### OSS adapter 公开 API

| 函数 | 签名 | 行为 |
|------|------|------|
| `upload_file(oss_key, content, content_type, db)` | `async → str` | 上传 bytes 到 OSS，成功返回 oss_key，失败抛 RuntimeError |
| `get_download_url(oss_key, db, expires=3600)` | `async → str` | 生成签名下载 URL，默认 1h 过期 |
| `delete_file(oss_key, db)` | `async → None` | 删除 OSS 对象 |

### 凭证字段映射（service_credentials 表）

字段映射与通用凭证管理 API `/api/admin/config/credentials` 约定一致：

| 字段 | OSS 含义 |
|------|----------|
| `provider` | `'oss'` |
| `label` | **备注名**（人类可读，如 "杭州生产环境"，管理员自定义） |
| `secret_enc` | AccessKey Secret（Sprint 3 阶段明文） |
| `config.access_key_id` | AccessKey ID |
| `config.bucket` | OSS Bucket 名 |
| `config.endpoint` | OSS Endpoint（如 `oss-cn-hangzhou.aliyuncs.com`） |
| `config.region` | OSS Region（可选） |

---

## 四、用户配置凭证

### 方式 A：连通性测试（env var 注入，本次已用 ✅）

```bash
export OSS_LIVE_TEST=1
export OSS_ACCESS_KEY_ID=LTAI...
export OSS_ACCESS_KEY_SECRET=...
export OSS_BUCKET=your-bucket
# 可选
export OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com  # 默认值
export OSS_REGION=cn-hangzhou                      # 默认值

cd backend
.venv311/Scripts/python -m pytest tests/integration/test_oss_live.py -v -m live --override-ini="addopts="
```

Secret 只在 shell 中存在，不写进代码、不写进 SQL 文件、不进 git。

### 方式 B：生产部署（管理端 UI，待实现）

UI 接通后通过通用凭证管理 API：

```http
POST /api/admin/config/credentials
{
  "provider": "oss",
  "label": "杭州生产环境",
  "api_key": "<AccessKeySecret>",
  "weight": 1,
  "config": {
    "access_key_id": "<AccessKeyID>",
    "bucket": "<bucket-name>",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou"
  }
}
```

UI 入口（独立任务）：管理端 → 工具配置 → OSS 配置 Tab（参考 AI/TikHub 独立 Tab 模式）。

配置完成后跑连通性测试：
```bash
cd backend
OSS_LIVE_TEST=1 .venv311/Scripts/python -m pytest tests/integration/test_oss_live.py -v -m live --override-ini="addopts="
```

---

## 五、不在本次范围（留后续）

- 管理端 OSS 面板 UI（凭证 CRUD + 存储统计展示）
- `files.py` router 补 upload 接口（真正存 OSS，目前 router 仍写本地）
- 存储统计面板（基于 files 表 + 阿里云计量 API 结合）
- outputs 产出迁移到 OSS
- ASR 服务接入（用户后续单独排期）

---

## 六、风险与遗留

1. **`oss.py` 全局零调用方**：本次接通后实际调用要等 `files.py` router 改造（独立任务）。当前 OSS adapter 是"接通但不挂载"状态，零回归风险。
2. **secret_enc 明文存储**：Sprint 3 阶段所有 adapter 都用明文，Sprint 4 统一上 Fernet 加密。OSS adapter 跟随统一节奏，不在本任务单独处理。
3. **`files.py` router 仍写本地**：第 104 行硬编码 mock URL，未走 `get_download_url`。这是独立任务，不在本次范围。
