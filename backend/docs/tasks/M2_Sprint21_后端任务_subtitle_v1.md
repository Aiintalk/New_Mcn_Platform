# M2 Sprint 21 — 后端任务：字幕提取异步任务化 + 软删除

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-27
> **依赖需求**：`docs/pm/M2_Sprint21_subtitle_需求文档.md`
> **基线**：Sprint 19 字幕提取已合并（28+11 tests passing）

---

## 一、任务范围

| # | 任务 | 文件 |
|---|------|------|
| 1 | 加字段 + migration | `app/models/subtitle.py`、`migrations/044_subtitle_job_kind_and_soft_delete.sql`、`migrations/045_subtitle_item_meta.sql` |
| 2 | POST /extract 改异步 | `app/routers/operator_subtitle.py` |
| 3 | 新增 DELETE /batch/{job_code} 软删除 | `app/routers/operator_subtitle.py` |
| 4 | GET /batches + GET /batch/{job_code} 过滤 deleted_at | `app/routers/operator_subtitle.py` |
| 5 | _item_to_dict 扁平化 meta_json | `app/routers/operator_subtitle.py` |
| 6 | 测试更新 | `tests/integration/routers/test_operator_subtitle.py` |
| 7 | 契约更新 | `backend/docs/base/MCN_M2_Base_API.md` §25、`MCN_M2_Base_Database.md` §30 |

---

## 二、数据库变更

### Migration 044：subtitle_jobs 加 kind + deleted_at

```sql
ALTER TABLE subtitle_jobs ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'batch';
ALTER TABLE subtitle_jobs ADD COLUMN deleted_at TIMESTAMPTZ;
CREATE INDEX idx_subtitle_jobs_kind_deleted ON subtitle_jobs(kind, deleted_at);
```

### Migration 045：subtitle_items 加 meta_json

```sql
ALTER TABLE subtitle_items ADD COLUMN meta_json TEXT;
```

### ORM 模型变更（`app/models/subtitle.py`）

```python
class SubtitleJob(Base):
    # 新增
    kind = Column(String(16), nullable=False, default="batch")  # single / batch
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)

class SubtitleItem(Base):
    # 新增
    meta_json = Column(Text, nullable=True)  # 单条任务的视频元信息 JSON
```

---

## 三、API 端点变更

### 1. POST /extract（异步任务化）

**原行为**：同步等 ASR 完成 → 返回完整结果
**新行为**：
1. 生成 job_code（`_claim_unique_job_code`）
2. INSERT subtitle_jobs（kind='single', total=1, status='processing'）
3. INSERT subtitle_items（1 行，original_url 来自 share_text 或 `file://{file_url}`）
4. 写 OperationLog（action=`subtitle_extract`）
5. commit
6. `asyncio.create_task(_run_single_extract(job_id, user_id))`
7. 立即返回 `{job_code, status:'processing'}`

### 2. _run_single_extract(job_id, user_id) 后台执行

```python
async def _run_single_extract(job_id: int, user_id: int):
    async with AsyncSessionLocal() as db:
        job = await db.get(SubtitleJob, job_id)
        item = (await db.execute(select(SubtitleItem).where(SubtitleItem.job_id == job_id))).scalar_one()
        item.status = "processing"; job.phase = "running"
        await db.commit()
        try:
            if item.original_url.startswith("file://"):
                # file_url 模式：纯 ASR
                file_url = item.original_url[7:]
                text, title = await asr_adapter.transcribe(file_url, db, user_id), ""
                meta = {}
            else:
                # share_text 模式：tikhub + ASR + 视频元信息
                v = await tikhub_adapter.fetch_video_by_share_url(item.original_url, db, user_id)
                text = await asr_adapter.transcribe(v["audio_url"], db, user_id)
                title = v.get("title", "")
                meta = {k: v.get(k) for k in ("play_url","audio_url","cover_url","nickname","digg_count","aweme_id")}
            item.transcript = text; item.title = title
            item.meta_json = json.dumps(meta, ensure_ascii=False)
            item.status = "success"; job.status = "completed"; job.phase = "done"; job.success = 1
        except Exception as e:
            item.status = "failed"; item.error = str(e); job.status = "failed"; job.phase = "done"; job.failed = 1
        await db.commit()
```

### 3. 新增 DELETE /batch/{job_code}

```python
@router.delete("/batch/{job_code}")
async def delete_batch(job_code, current_user, db):
    job = await _get_owned_job(db, job_code, current_user)  # 含 deleted_at IS NULL 过滤
    if not job: raise HTTPException(404)
    job.deleted_at = datetime.now(tz=timezone.utc)
    session.add(OperationLog(action="subtitle_delete", target_type="subtitle_job", target_id=job.id, detail=json.dumps({"job_code": job_code}), user_id=current_user.id))
    await db.commit()
    return success_response(data={"job_code": job_code, "deleted": True})
```

### 4. _item_to_dict 扁平化 meta_json

```python
def _item_to_dict(item: SubtitleItem) -> dict:
    d = {常规字段}
    if item.meta_json:
        d.update(json.loads(item.meta_json))  # play_url/audio_url/cover_url/nickname/digg_count/aweme_id 扁平到顶层
    return d
```

### 5. GET /batches / GET /batch/{job_code} 过滤软删除

所有查询加 `SubtitleJob.deleted_at.is_(None)`。

---

## 四、测试更新

### `tests/integration/routers/test_operator_subtitle.py`

**重写**：
- 原 TestExtract 4 个同步测试 → 4 个异步测试（mock `_run_single_extract`，断言 job_code 返回 + DB 行）
- 新增 TestRunSingleExtract 4 个测试（直接调内部函数，覆盖 share_text/file_url/success/failed 路径）
- TestBatch::test_batch_create_success 的 OperationLog 断言改为 `EXISTS + detail::json->>'job_code' = :jc` 精确匹配（修隔离问题）

**新增测试用例**：
- test_extract_returns_job_code_and_creates_job
- test_extract_with_file_url_skips_tikhub
- test_run_single_extract_success_share_text
- test_run_single_extract_success_file_url
- test_run_single_extract_failure_records_error

**结果**：30/30 ✅

### `tests/unit/services/test_tikhub_adapter.py`

`test_fetch_video_by_share_url_audio_fallback_to_play` → 重命名为 `test_..._audio_empty_when_no_music`，断言 `audio_url == ""`（不再回退 video.play_addr）

---

## 五、契约更新

### `backend/docs/base/MCN_M2_Base_API.md` §25

- 表 25.2 运营端接口：7 个 → 8 个（加 DELETE /batch/{job_code}）
- POST /extract：改为"异步任务化 — Sprint 21"，Response.data 改为 `{job_code, status:'processing'}`
- GET /batch/{job_code}：查询条件加 `deleted_at IS NULL`；Response.items[0] 加扁平化字段（play_url/cover_url/nickname/digg_count/aweme_id）
- 新增 DELETE /batch/{job_code} 章节
- GET /batches：改为"历史记录列表（单条 + 批量统一）"

### `backend/docs/base/MCN_M2_Base_Database.md` §30

- §30.1 subtitle_jobs：加 `kind` + `deleted_at` 字段；索引加 `idx_subtitle_jobs_kind_deleted`
- §30.2 subtitle_items：加 `meta_json` 字段；附"API 输出说明"（meta_json 扁平化）

---

## 六、回归验证

```bash
cd backend && source .venv311/Scripts/activate
pytest tests/integration/routers/test_operator_subtitle.py -v
pytest tests/integration/routers/test_admin_subtitle.py -v
pytest tests/ --ignore=tests/intake -q  # 全量（排除 pre-existing 失败）
```

**通过标准**：字幕模块 30+11 全过，全量 1078 passed（pre-existing 11 failures 不影响）。
