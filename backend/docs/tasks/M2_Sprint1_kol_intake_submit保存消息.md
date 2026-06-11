# 后端任务单 · kol-intake 运营直发 submit 接口保存对话消息

> 问题：
> 运营直发采用「前端主导题目流程 + AI 只生成过渡语」的新架构，
> 前端调用 `/bridge` 接口，而 bridge 不保存对话记录到数据库。
> 提交时 `session.messages` 为空，导致报告生成时 AI 看不到任何问答内容，
> 报告输出"目前还没有拿到完整的对话记录"。
>
> 修复：`/submit` 接口接收前端传来的完整 messages，存入 session，
> 报告生成代码不需要改动。
>
> 涉及文件：`backend/app/routers/operator_intake_direct.py`

---

## 改动 1 — 新增 SubmitBody 模型

在 `ChatRequest` 模型附近（第 117 行区域）添加：

```python
class SubmitBody(BaseModel):
    messages: list[dict] = []
```

---

## 改动 2 — submit 接口接收并保存 messages

**改前**（第 288-309 行）：

```python
@router.post("/{session_id}/submit")
async def session_submit(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提交会话，异步触发报告生成。"""
    session = await _get_own_session(session_id, current_user, db)

    if session.report_status != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "VALIDATION_ERROR", "message": "会话已提交，不可重复提交"},
        )

    await db.execute(
        update(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.id == session_id)
        .values(report_status="generating", updated_at=datetime.now(timezone.utc))
    )
    await db.commit()
```

**改后**：

```python
@router.post("/{session_id}/submit")
async def session_submit(
    session_id: int,
    body: SubmitBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提交会话，异步触发报告生成。同时保存完整对话消息供报告生成使用。"""
    session = await _get_own_session(session_id, current_user, db)

    if session.report_status != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "VALIDATION_ERROR", "message": "会话已提交，不可重复提交"},
        )

    await db.execute(
        update(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.id == session_id)
        .values(
            messages=body.messages if body.messages else (session.messages or []),
            report_status="generating",
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
```

---

## 改动汇总

| # | 改动 |
|---|------|
| 1 | 新增 `SubmitBody(messages: list[dict] = [])` |
| 2 | submit 接口签名增加 `body: SubmitBody` |
| 3 | `.values()` 增加 `messages=body.messages if body.messages else ...` |

**改动量**：约 10 行，重启后端生效。

---

## 说明

- `session.messages` 的数据结构是 `[{"role": "assistant/user", "content": "..."}]`
- 前端 messages 的 `ts` 字段（时间戳）会被存入 DB 但不影响报告生成，报告生成代码只读 `role` 和 `content`
- 如果前端传来空 messages，保持原有 session.messages 不变（向后兼容 `/chat` 模式）

---

## 验收

| 验证点 | 预期 |
|--------|------|
| 完成问答后提交 | session.messages 有 N 条记录（约 48 条，24问+24答+过渡语） |
| 报告生成后内容 | 报告包含真实红人信息，不出现"暂无对话记录" |
| 重复提交 | 仍返回 409 VALIDATION_ERROR |
