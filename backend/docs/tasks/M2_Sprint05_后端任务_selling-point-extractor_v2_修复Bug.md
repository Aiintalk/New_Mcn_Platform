# M2 Sprint 5 · 后端任务 · selling-point-extractor v2 · 修复Bug

> 状态：✅ 已完成（2026-06-13）
> 前序文档：`M2_Sprint05_后端任务_selling-point-extractor_v1.md`
> 修复类型：规范对齐（OperationLog + 标准响应格式 + 前端 API 封装）

---

## 一、修复背景

v1 版本经代码完整性检查，发现以下不符合项目规范的问题：

| # | 问题 | 违反规范 |
|---|------|----------|
| 1 | chat / parse-file / save / delete 无 OperationLog | 用户操作日志（迁移红线） |
| 2 | 5 个接口返回裸 dict（`{"text":...}` / `{"records":...}` / `{"success":True}`） | 一票否决项：响应必须 `{success,code,message,data}` |
| 3 | 前端 `sellingPoint.ts` 的 parseFile/saveHistory/deleteHistory 走原生 fetch | 前端规范：JSON 调用应走 `request.ts` 封装 |

---

## 二、修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/routers/operator_selling_point.py` | 加 `_get_ip`；5 个接口加 OperationLog；4 个非流式接口改 `success_response` |
| `frontend/src/api/sellingPoint.ts` | parseFile 解包 `.data`；saveHistory 改 `post<>()`；deleteHistory 改 `del<>()` |
| `backend/tests/integration/routers/test_operator_selling_point.py` | 全部断言适配 `.data` 嵌套；新增 TestResponseFormat（4 条）+ TestOperationLog（3 条） |
| `backend/tests/conftest.py` | `_SESSION_LOCAL_PATCH_TARGETS` 追加 selling-point router |

---

## 三、具体改动

### 3.1 OperationLog（4 个写操作 + 1 个后台任务）

| 接口 | action | target_type | 说明 |
|------|--------|-------------|------|
| POST /chat | `selling_point_chat` | tool | 后台任务，与 TaskJob 一起写入 |
| POST /parse-file | `selling_point_parse_file` | file | 含 filename + chars |
| POST /history | `selling_point_save_history` | output | target_id = output.id |
| DELETE /history | `selling_point_delete_history` | output | target_id = id |

### 3.2 标准响应格式

```python
# Before（5 处裸 return）
return {"text": text, "filename": file.filename}
return {"records": [...]}
return {"record": {...}}
return {"success": True, "id": str(output.id)}
return {"success": True}

# After
return success_response(data={"text": text, "filename": file.filename})
return success_response(data={"records": [...]})
return success_response(data={"record": {...}})
return success_response(data={"id": str(output.id)})
return success_response(data={"id": id})
```

### 3.3 前端 API 封装

```typescript
// Before：saveHistory / deleteHistory 走原生 fetch
const resp = await fetch(url, { ... });
return resp.json();

// After：走 request.ts 封装（自动处理 token + 错误 + 解包 .data）
export const saveHistory = (body) => post<{ id: string }>(`${PREFIX}/history`, body);
export const deleteHistoryRecord = (id: string) => del<null>(`${PREFIX}/history?id=${id}`);
```

- parseFile 保留原生 fetch（FormData 非 JSON），手动解包 `.data`
- chatStream 保留原生 fetch（流式必需）

---

## 四、测试

- 集成测试：27/27 通过（原 20 + 新增 7：4 条响应格式 + 3 条 OperationLog）
- 全量 368/368 通过，零回归
