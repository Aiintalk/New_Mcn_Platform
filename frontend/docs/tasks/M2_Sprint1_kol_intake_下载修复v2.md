# 前端任务单 · kol-intake 下载报告修复 v2

> 问题：点击「下载 Word / 下载 PDF」报错 AUTH_TOKEN_MISSING
>
> 根因：`window.open` 打开新标签页时浏览器不携带任何 header，
> `?token=` query 参数理论可行但实测失效（浏览器 / 编码兼容性问题）。
>
> 修复方案：改用 `fetch` + Blob 下载，走 `Authorization` header 鉴权，
> 与其他所有 API 调用保持一致，不依赖 URL token 机制。
>
> 涉及文件：`src/pages/operator/OperatorIntakeChatPage.tsx`（仅改这一个文件）

---

## 改动说明

### 第 1 步 — 新增 import

在文件头部现有 imports 后添加：

```tsx
import { useAuthStore } from '../../store/authStore';
```

### 第 2 步 — 替换 handleDownload

**改前**（第 265-268 行）：
```tsx
function handleDownload(format: 'docx' | 'pdf') {
  if (!sessionId) return;
  window.open(getDirectDownloadUrl(sessionId, format), '_blank');
}
```

**改后**：
```tsx
async function handleDownload(format: 'docx' | 'pdf') {
  if (!sessionId) return;
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
  const token = useAuthStore.getState().token;
  if (!token) { message.error('请重新登录后再试'); return; }
  try {
    const res = await fetch(
      `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({ message: '下载失败' }));
      message.error(body.message || '下载失败');
      return;
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `入驻报告.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } catch {
    message.error('下载失败，请重试');
  }
}
```

### 第 3 步 — 清理无用 import

从 `intakeDirect` 的 import 列表中删除 `getDirectDownloadUrl`（不再使用）：

```tsx
// 改前
import {
  startDirectSession, submitDirect,
  getDirectStatus, getDirectDownloadUrl, bridgeOperatorDirect,
} from '../../api/intakeDirect';

// 改后
import {
  startDirectSession, submitDirect,
  getDirectStatus, bridgeOperatorDirect,
} from '../../api/intakeDirect';
```

---

## 改动量

3 处改动，约 20 行，后端无需改动。

---

## 验证

| 验证点 | 预期 |
|--------|------|
| 点击「下载 Word」 | 浏览器直接下载 `.docx` 文件，无报错 |
| 点击「下载 PDF」 | 浏览器直接下载 `.pdf` 文件，无报错 |
| 报告未生成时点击 | 提示「报告尚未生成」 |
| 未登录时点击 | 提示「请重新登录后再试」 |
