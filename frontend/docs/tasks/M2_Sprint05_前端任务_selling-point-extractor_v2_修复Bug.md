# M2 Sprint 5 · 前端任务 · selling-point-extractor v2 · 修复Bug

> 状态：✅ 已完成（2026-06-13）
> 前序文档：`M2_Sprint05_前端任务_selling-point-extractor_v1.md`
> 修复类型：API 封装规范对齐

---

## 一、修复背景

后端 v2 将所有接口响应改为标准信封 `{success,code,message,data}`。前端需同步调整 API 调用层的响应解包方式。

---

## 二、修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/api/sellingPoint.ts` | saveHistory 从原生 fetch 改走 `post<>()`；deleteHistoryRecord 改走 `del<>()`；parseFile 手动解包 `.data` |

---

## 三、具体改动

### 3.1 saveHistory

```typescript
// Before：原生 fetch + 手动 token + 返回裸 JSON
export async function saveHistory(body) {
  const resp = await fetch(url, { ... });
  return resp.json(); // {success, id}
}

// After：走 request.ts 封装（自动 token + 错误处理 + 解包 .data）
export const saveHistory = (body) =>
  post<{ id: string }>(`${PREFIX}/history`, body);
```

### 3.2 deleteHistoryRecord

```typescript
// Before：原生 fetch
// After：走 del<>() 封装
export const deleteHistoryRecord = (id: string) =>
  del<null>(`${PREFIX}/history?id=${id}`);
```

### 3.3 parseFile（保留原生 fetch，手动解包）

FormData 无法走 `request.ts` 的 JSON 封装（Content-Type 不同），保留原生 fetch，但增加 `.data` 解包：

```typescript
const body = await resp.json();
return body.data; // 从标准信封中取出 {text, filename}
```

### 3.4 chatStream（不变）

流式响应必须走原生 fetch，无需改动。

---

## 四、兼容性

- `getHistoryList()` 和 `getHistoryRecord()` 已用 `get<>()` 封装，`handleResponse()` 自动解包 `.data`，无需改动
- `SellingPointPage.tsx` 消费方式不变（API 层已处理解包）
- 前端测试 71/71 通过

---

## 五、不涉及

- tiktok-writer 前端无需 v2 修复（`getPersonas()` 已通过 `get<>()` 解包，后端改标准响应后自动兼容）
