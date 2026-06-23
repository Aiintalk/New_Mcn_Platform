# M2 Sprint 15 — 后端任务：人设脚本仿写 v2 修复 Bug（persona-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-23
> 对应需求文档：`docs/pm/M2_Sprint15_persona-writer_需求文档.md`
> 上一份：`backend/docs/tasks/M2_Sprint15_后端任务_persona-writer_v1.md`
> 对应分支：`migrate/persona-writer`
> 本次迭代类型：修复Bug（v2）

---

## 一、范围（本次后端 v2 迭代）

v1 已完成 persona-writer 主体迁移。本次 v2 聚焦 **E2E 验收期发现的后端 bug + 数据修复 + 契约同步**，共 5 项后端改动：

1. TikHub 400 错误修复（URL 未清洗 tracking 参数）
2. 4 writer 下拉 SQL 不一致统一
3. kols 表唯一索引 + create_kol 重复预检查（migration 032）
4. kols.status 默认值修正（active → signed）
5. 数据污染清理（id=3、id=4 字段错乱软删）+ 契约文档同步

## 二、BUG 清单

| BUG ID | 严重度 | 问题 | 根因 | 修复文件 |
|--------|-------|------|------|---------|
| BUG-025 | P1 | 对标验证点击抖音解析报 400 | `_resolve_short_url` 返回的 iesdouyin.com 链接带 14 个 tracking 参数（share_sign/ts/from_aid 等），TikHub 端点原样转发拒绝 | `app/adapters/tikhub.py`（新增 `_clean_share_url`）|
| BUG-026 | P1 | persona/qianchuan 下拉只看到部分红人；livestream/tiktok 下拉看到已解约红人 | 4 个 writer 的 `/kols/personas` SQL 不一致：persona/qianchuan 过滤 `status='active'`（已废弃值），livestream/tiktok 无 status 过滤 | 4 个 operator_*_writer.py 统一为 `status IN ('signed','pending_renewal')` |
| BUG-027 | P1 | 新建红人后下拉看不到 | ORM `Kol.status` 默认 `'active'`（已废弃），被新 SQL 过滤 | `app/models/kol.py:27` default 改为 `'signed'`；数据修复：现有 `'active'` → `'signed'` |
| BUG-028 | P2 | 同一个 douyin_id 可重复创建红人 | `kols.douyin_id` / `sec_uid` 无 UNIQUE 约束，`create_kol` 也无预检查 | migration 032 部分唯一索引 + `admin_kols.py` 加预检查 + `response.py` 新增 `RESOURCE_ALREADY_EXISTS` |
| BUG-029 | P1 | 红人列表 id=3 孙静（原搭搭）、id=4 陶然（原小A）头像/douyin_id 与名字不匹配 | `_e2e_seed_personas.py`（gitignored 一次性脚本）UPDATE 了 name/persona/content_plan 但未改其他字段 | 数据修复：软删 id=3、id=4（`deleted_at=NOW()`），用户 UI 重建 |

## 三、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | TikHub URL 清洗（`_clean_share_url`）| `backend/app/adapters/tikhub.py` | ✅ |
| B2 | TikHub 单测扩展（4 纯函数 + 1 回归）| `backend/tests/unit/services/test_tikhub_adapter.py` | ✅ |
| B3 | 4 writer SQL 统一 `status IN ('signed','pending_renewal')` | 4 个 `operator_*_writer.py` | ✅ |
| B4 | 4 writer 测试 fixture 修正（`'active'` → `'signed'`）| 4 个 `test_operator_*_writer.py` + `test_livestream_writer.py` | ✅ |
| B5 | Migration 032 部分唯一索引（douyin_id + sec_uid）| `backend/migrations/032_kols_unique_douyin_id.sql` | ✅ |
| B6 | ErrorCode 加 `RESOURCE_ALREADY_EXISTS`（409）| `backend/app/core/response.py` | ✅ |
| B7 | `create_kol` 重复预检查（douyin_id + sec_uid）| `backend/app/routers/admin_kols.py` | ✅ |
| B8 | ORM `Kol.status` default 改为 `'signed'` | `backend/app/models/kol.py:27` | ✅ |
| B9 | 新建 test_admin_kols 集成测试（7 用例）| `backend/tests/integration/routers/test_admin_kols.py` | ✅ |
| B10 | 数据修复：软删 id=3、id=4 + status active→signed | DB（asyncpg 直连）| ✅ |
| B11 | 契约同步：Base_Database §6.2/6.3 + Base_API §3 + Base_API §13.4/16.3/21.1/22.1 + backend README | 4 个文档 | ✅ |
| B12 | 任务文档（本文件）| 本文件 | ✅ |

## 四、实现要点

### 4.1 `_clean_share_url` 设计

```python
def _clean_share_url(url: str) -> str:
    """清洗抖音分享链接：丢弃所有 query 参数，只保留 scheme/netloc/path。"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
```

调用点在 `fetch_video_by_share_url` 内，紧跟 `_resolve_short_url` 之后：
```python
full_url = await _resolve_short_url(url)
full_url = _clean_share_url(full_url)  # 新增
```

### 4.2 Migration 032 部分唯一索引

参照 `001_init.sql:28 idx_users_username` 模式（`WHERE deleted_at IS NULL`）：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_kols_douyin_id_unique
  ON kols(douyin_id)
  WHERE deleted_at IS NULL AND douyin_id IS NOT NULL AND douyin_id <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_kols_sec_uid_unique
  ON kols(sec_uid)
  WHERE deleted_at IS NULL AND sec_uid IS NOT NULL AND sec_uid <> '';
```

设计要点：
- 部分索引（partial index）排除软删记录，允许软删后用相同 douyin_id 重建
- 排除 NULL 和空字符串，允许多条未填 douyin_id 的红人共存
- `IF NOT EXISTS` 保证幂等

### 4.3 create_kol 预检查模式

参照 `admin_users.py:206-210` 的 USERNAME_ALREADY_EXISTS 预检查：

```python
if body.douyin_id:
    existing = (await db.execute(
        select(Kol).where(
            Kol.douyin_id == body.douyin_id,
            Kol.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing:
        return error_response(
            ErrorCode.RESOURCE_ALREADY_EXISTS,
            f"抖音号 {body.douyin_id} 已存在（红人：{existing.name}）",
        )
```

**双保险**：前端友好错误 + DB 索引兜底（防止并发插入竞态）。

### 4.4 数据修复

一次性 SQL（不入 migration，migration 只管 schema）：
```sql
UPDATE kols SET deleted_at = NOW(), updated_at = NOW()
WHERE id IN (3, 4) AND deleted_at IS NULL;

UPDATE kols SET status = 'signed', updated_at = NOW()
WHERE status = 'active' AND deleted_at IS NULL;
```

## 五、测试

### 5.1 TikHub 单测扩展（test_tikhub_adapter.py）

新增 5 个用例（30/30 全过）：
- `test_clean_share_url_strips_query_params`（脏 URL）
- `test_clean_share_url_preserves_clean_url`（干净 URL）
- `test_clean_share_url_query_only`（纯 query）
- `test_clean_share_url_preserves_scheme`（https scheme）
- `test_fetch_video_by_share_url_cleans_dirty_redirect`（集成回归）

### 5.2 test_admin_kols.py 新建（7 用例全过）

- `test_create_success`
- `test_create_does_not_overwrite_existing`（验证 INSERT 不覆盖）
- `test_duplicate_douyin_id_returns_409`
- `test_duplicate_sec_uid_returns_409`
- `test_duplicate_after_soft_delete_succeeds`（软删后可重建）
- `test_create_multiple_without_douyin_id_succeeds`（空值可多条）
- `test_create_requires_admin`（鉴权）

### 5.3 回归测试

- `test_admin_users.py` + `test_admin_tikhub.py` + `test_admin_oss.py` + `test_admin_asr.py`：51/51 全过
- `test_convention_guard.py`：6/6 全过（无新增红线违反）
- 4 writer 集测：所有 fixture 改 `'signed'` 后全过

## 六、契约与文档同步

| 文档 | 章节 | 改动 |
|------|------|------|
| `MCN_M1_Base_Database.md` | §6.2 | kols.status 修正为 `signed/pending_renewal/terminated` + 加默认值说明 |
| `MCN_M1_Base_Database.md` | §6.3（新建）| 加部分唯一索引说明（idx_kols_douyin_id_unique + idx_kols_sec_uid_unique）|
| `MCN_M1_Base_API.md` | §3 错误码表 | 加 `RESOURCE_ALREADY_EXISTS`（409）|
| `MCN_M2_Base_API.md` | §13.4 / §16.3 / §21.1 / §22.1 | 4 writer SQL 统一为 `status IN ('signed','pending_renewal')` |
| `backend/docs/README.md` | line 151 | migrations 编号 031 → 032 |

## 七、决策点

1. **Migration 编号选 032**：029 已被 ASR 占用（独立分支），031 是 persona-writer，本次顺位 032
2. **唯一索引用 partial 而非全表**：参照 `idx_users_username` 惯例，支持软删后重建（业务上可能"原红人解约后又回来"）
3. **create_kol 预检查 + DB 索引双保险**：预检查返回友好错误，DB 索引兜底并发竞态
4. **数据修复不入 migration**：migration 只管 schema，数据修复用一次性 SQL（asyncpg 直连）
5. **`RESOURCE_ALREADY_EXISTS` 通用而非 `KOL_ALREADY_EXISTS`**：未来其他资源（如 credentials）可复用

## 八、不在本次范围

- admin/kols 完整 API 章节契约（M1_Base_API 缺失整章，属历史债务，独立任务）
- tool_transcribe 切到 ASR（独立任务）
- service_credentials.secret_enc 加密（Sprint 3 债务）
- 前端 KolsPage 新建表单的 status Select 完善（本次仅加 initialValue，未来若需"草稿/审核中"等状态可扩展）
