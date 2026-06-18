# M2 Sprint 11 — 后端任务：阿里云 OSS Adapter 接入 v1

> 状态：进行中
> 起始日期：2026-06-18
> 对应分支：`feature/oss-adapter`

---

## 一、背景

`backend/app/adapters/oss.py` 从 M1 起就是 Mock 占位：
- `get_download_url` 返回假 URL（`https://mock-oss.example.com/...`）
- `upload_file` 直接 `raise NotImplementedError`

`files` 表预留了 `oss_key` 字段但从未真正接通 OSS。

**本任务目标**：先做**后端接通验证**，证明能真实连阿里云 OSS 完成上传/下载/删除。凭证由用户后续配置（写入 `service_credentials` 表，`provider="oss"`）。

## 二、不在本次范围

- 管理端 OSS 面板 UI（凭证 CRUD + 统计展示）
- `files.py` router 补 upload 接口（真正存 OSS）
- 存储统计面板（基于 files 表 + 阿里云计量 API）
- outputs 产出迁移到 OSS

## 三、接通条件（已成熟）

- `oss2>=2.18.0` 已装（`requirements.txt:10`）
- `oss.py` 全局**零调用方**（实现零回归风险）
- 凭证机制成熟，可直接复用 `tikhub.py` 范式
- `service_credentials` 表支持 `provider="oss"`，`.env.example` 已预留 5 个 OSS 环境变量

## 四、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | 重写 OSS adapter（真实实现） | `backend/app/adapters/oss.py` | ⏳ |
| B2 | 单元测试（8 个，纯 mock） | `backend/tests/unit/services/test_oss_adapter.py` | ⏳ |
| B3 | 连通性测试（skipif + 真实 OSS） | `backend/tests/integration/test_oss_live.py` | ⏳ |
| B4 | pytest.ini 加 markers | `backend/pytest.ini` | ⏳ |
| B5 | 全量回归 + 覆盖率门禁 | — | ⏳ |
| B6 | 文档更新（README + PM 记忆 + 测试报告） | 多处 | ⏳ |

## 五、API 设计

### 函数清单（3 公开 + 2 内部）

| 函数 | 签名 | 说明 |
|------|------|------|
| `upload_file(oss_key, content, content_type, db)` | `→ str` | 真实 `bucket.put_object`，返回 oss_key |
| `get_download_url(oss_key, db, expires=3600)` | `→ str` | `bucket.sign_url('GET', key, expires)` |
| `delete_file(oss_key, db)` | `→ None` | `bucket.delete_object`（新增） |
| `_get_oss_credential(db)` | `→ (cred_id, ak_id, ak_secret, bucket, endpoint)` | 内部 helper |
| `_make_bucket(ak_id, ak_secret, endpoint, bucket)` | `→ oss2.Bucket` | 工厂函数（便于 mock） |

### 凭证字段映射

| `service_credentials` 字段 | OSS 含义 |
|----|----|
| `provider` | `"oss"` |
| `label` | AccessKey ID |
| `secret_enc` | AccessKey Secret（Sprint 3 阶段明文） |
| `config.bucket` | OSS Bucket 名 |
| `config.endpoint` | OSS Endpoint（如 `oss-cn-hangzhou.aliyuncs.com`） |
| `config.region` | OSS Region（如 `cn-hangzhou`，可选） |

### 关键设计点

- `oss2` 是同步库 → 全部用 `asyncio.to_thread` 包装，不阻塞事件循环
- `_get_oss_credential` 在 try **外**（凭证缺失/config 缺字段时直接抛，无法 report_failure 因为没 cred_id）
- oss2 操作在 try **内**（失败 → report_failure + 异常传播）
- 复用 `credential_selector.py` 的 `pick_credential` / `report_success` / `report_failure`（cooldown 机制）

## 六、测试策略

### 单元测试（无凭证可跑，CI 主路径）

8 个测试覆盖 3 函数 × 成功/失败 + helper + 边界，**adapter 覆盖率 ≥ 60%**（adapter 门禁）。

Mock 策略：`@patch("app.adapters.oss._get_oss_credential")` + `@patch("app.adapters.oss._make_bucket")` + `@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)` + `@patch("app.adapters.oss.report_success/failure", new_callable=AsyncMock)`

### 连通性测试（需凭证）

```python
pytestmark = pytest.mark.skipif(
    not os.getenv("OSS_ACCESS_KEY_ID") and not <db has oss credential>,
    reason="...",
)

@pytest.mark.live
async def test_oss_upload_download_delete_round_trip():
    # 1. upload b"hello oss live test" → 返回 oss_key
    # 2. get_download_url → httpx GET 断言 200 + 内容一致
    # 3. delete_file 清理
```

**位置**：`backend/tests/integration/test_oss_live.py`（**不在** `routers/` 子目录，避开 `test_convention_guard.py` 扫描）

**覆盖率影响**：无凭证时 `skipif` 自动跳过，不计入分母。

## 七、用户配置凭证（任务完成后用户自己执行）

```sql
INSERT INTO service_credentials
  (provider, label, secret_enc, secret_tail, status, weight, config)
VALUES (
  'oss',
  '<AccessKeyID>',                    -- label = AccessKey ID
  '<AccessKeySecret>',                -- secret_enc = AccessKey Secret（当前明文，Sprint 4 加密）
  '<Secret末4位>',                    -- secret_tail，UI 展示用
  'enabled',
  1,
  '{"bucket": "<bucket-name>", "endpoint": "oss-cn-hangzhou.aliyuncs.com", "region": "cn-hangzhou"}'
);
```

连通性测试还需在环境变量设 `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET`（或从 `service_credentials` 表读凭证 —— **推荐**后者，与生产同路径）。

## 八、验收标准

- [ ] `pytest tests/unit/services/test_oss_adapter.py -v` 8/8 通过
- [ ] `app/adapters/oss.py` 覆盖率 ≥ 60%
- [ ] `pytest tests/ -v` 全量回归不破坏现有测试
- [ ] 配凭证后 `pytest tests/integration/test_oss_live.py -v -m live` 通过
- [ ] 文档更新：`backend/docs/README.md`（oss.py 状态 Mock→真实）+ PM 记忆 + 测试报告
- [ ] commit + push + 发 PR（不直接推 main）

## 九、风险点

1. **`asyncio.to_thread` 的 mock**：必须用 `@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)`
2. **`_get_oss_credential` 边界**：config 缺 `bucket`/`endpoint` 会 `KeyError`，在 try 外直接传播（不 report_failure）
3. **`oss2` 异常类型**：`put_object` 失败抛 `oss2.exceptions.OssError` 子类，`except Exception` 兜底足够
4. **report_failure 内部异常**：测试 mock 掉 report_failure 避免干扰
5. **连通性测试凭证来源**：推荐从 `service_credentials` 表读（与生产同路径），而非环境变量
