# M2 Sprint 4 · 后端任务 · tiktok-writer v2 · 修复Bug

> 状态：✅ 已完成（2026-06-13）
> 前序文档：`M2_Sprint04_后端任务_tiktok-writer_v1.md`
> 修复类型：规范对齐（OperationLog + 标准响应格式）

---

## 一、修复背景

v1 版本经代码完整性检查，发现以下不符合项目规范的问题：

| # | 问题 | 违反规范 |
|---|------|----------|
| 1 | chat / export-word 接口无 OperationLog | 用户操作日志（迁移红线） |
| 2 | get_kol_personas 返回裸 `{"personas": [...]}` | 一票否决项：响应必须 `{success,code,message,data}` |

---

## 二、修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/routers/operator_tiktok_writer.py` | 加 `_get_ip` helper；chat 后台任务加 OperationLog；export-word 加 OperationLog；personas 改 `success_response` |
| `backend/tests/integration/routers/test_operator_tiktok_writer.py` | personas 断言适配 `.data` 嵌套；新增 OperationLog 验证测试 |

---

## 三、具体改动

### 3.1 OperationLog（chat 后台任务）

chat 是流式接口，OperationLog 在 `BackgroundTask` 中与 TaskJob 一起写入：
- action: `tiktok_writer_chat`
- target_type: `tool`

### 3.2 OperationLog（export-word）

export-word 写 outputs 后、commit 前追加 OperationLog：
- action: `tiktok_export_word`
- target_type: `output`，target_id = output.id

### 3.3 标准响应（get_kol_personas）

```python
# Before
return {"personas": personas}

# After
return success_response(data={"personas": personas})
```

---

## 四、测试

- 全部 14 个测试通过（含新增 `test_export_writes_op_log`）
- 全量 368/368 通过，零回归
