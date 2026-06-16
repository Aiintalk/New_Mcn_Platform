# M2 Sprint 08 — 前端开发验收 · 直播脚本仿写（livestream-writer）v1

> 节点：B+
> 创建日期：2026-06-15
> 验收状态：✅ 人工验证通过（2026-06-16）

---

## 一、交付文件清单

| 文件 | 状态 |
|------|------|
| `frontend/src/types/livestreamWriter.ts` | ✅ 新增 |
| `frontend/src/api/livestreamWriter.ts` | ✅ 新增（4个 API 函数）|
| `frontend/src/pages/operator/LivestreamWriterPage.tsx` | ✅ 新增（4步工作流）|
| `frontend/src/pages/admin/LivestreamWriterConfigTab.tsx` | ✅ 新增 |
| `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | ✅ 追加 Tab |
| `frontend/src/App.tsx` | ✅ 注册路由 |

---

## 二、TypeScript 编译

```
npx tsc --noEmit → 无错误
```

---

## 三、功能说明

### 工作流 4 步

| 步骤 | 功能 |
|------|------|
| Step 1 | 下拉选择达人（展示 soul 预览）|
| Step 2 | 上传卖点文件或粘贴；选卖点顺序（3种）；自动提取产品名 |
| Step 3 | 上传对标文案或粘贴；显示字数；确认锁定 |
| Step 4 | 生成开播方案（AI 流式）；多轮追问；autoTrimIfTooLong；导出 .txt |

### autoTrimIfTooLong

生成结束后自动检查讲解脚本字数，超出对标字数则自动追加压缩请求，透明进行。

### System Prompt 实时拉取

进入页面时调 GET `/api/tools/livestream-writer/config`，将 `generate_prompt` / `iterate_prompt` / `model_id` 存入 state，生成时直接注入动态变量后传给后端。

### 管理端配置 Tab

挂载在"工具配置"页（`WorkspaceConfigPage.tsx`），新增"直播脚本仿写"Tab，可编辑两条 Prompt（generate/iterate）和绑定 AI 模型。

---

## 四、待人工验证

1. 工具卡片点击跳转到 `/workspace/livestream-writer`
2. Step 1 达人下拉有数据
3. Step 2 文件上传解析正常
4. Step 3 对标锁定后不可修改
5. Step 4 首次生成输出 7 模块；autoTrimIfTooLong 在超字数时自动触发；多轮追问正常；导出 .txt 内容正确
6. 管理端"工具配置"→"直播脚本仿写" Tab 可显示和编辑配置
