# M2 Sprint 7 · 前端任务 · qianchuan-edit-review v1

> 状态：✅ 已完成（2026-06-14）
> 需求文档：`docs/pm/M2_Sprint07_qianchuan-edit-review_需求文档.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/api/qianchuanEditReview.ts` | 新建 | 5 个 API 函数封装（截帧/转录/流式/导出/保存）|
| `src/pages/operator/QianChuanEditReviewPage.tsx` | 新建 | 千川剪辑预审主页面组件 |
| `src/App.tsx` | 修改 | 新增路由 `/workspace/qianchuan-edit-review` + import |

---

## 二、关键设计决策

| 决策 | 说明 |
|------|------|
| fetch 例外标注 | `extractFrames`、`transcribeVideo`（FormData 上传）、`chatStream`（SSE getReader）、`exportWord`（Blob 下载）保留原生 fetch，按红线 #3 标注例外；`saveOutput` 走 `request.ts` 的 `post()` |
| System Prompt 位置 | 硬编码在组件常量中，随 chatStream 请求传后端，不做管理端配置 |
| 截帧/转录分离 | 两个独立 API 调用，可单独重试；前端分别显示「截帧中...」「转录文案中...」状态 |
| 多模态消息构建 | 文案和帧图片在前端交错组装，格式：`[text: 原版时长+文案] + [text: 第Xs:] + [image_url: base64] × N` |
| 历史记录 | 本工具不做独立历史列表，保存后去产出中心查看 |
| 双侧面板 | 左侧「原版爆款」（绿色边框）、右侧「我方成片」（蓝色边框），复用 `renderSide()` 函数 |

---

## 三、API 封装（qianchuanEditReview.ts）

| 函数 | 请求方式 | 接口 | fetch 类型 |
|------|---------|------|-----------|
| `extractFrames(file, count=8)` | POST FormData | `/api/tools/extract-frames` | 原生 fetch（FormData 例外）|
| `transcribeVideo(file, language='zh')` | POST FormData | `/api/tools/transcribe` | 原生 fetch（FormData 例外）|
| `chatStream(messages, systemPrompt, model, maxTokens)` | POST JSON | `/api/tools/chat-stream` | 原生 fetch（SSE getReader 例外）|
| `exportWord(content, title)` | POST JSON | `/api/tools/export-word` | 原生 fetch（Blob 例外）|
| `saveOutput(body)` | POST JSON | `/api/tools/qianchuan-edit-review/outputs` | `request.ts` post()（标准路径）|

---

## 四、路由

- 路径：`/workspace/qianchuan-edit-review`
- 组件：`QianChuanEditReviewPage`
- 入口：WorkspacePage → 点击「千川剪辑预审」工具卡片（tool_code='qianchuan-edit-review'）

---

## 五、前端守卫合规

`src/__tests__/unit/api/conventionGuard.test.ts` 扫描 `src/api/*.ts` 中的裸 fetch 调用：

- `qianchuanEditReview.ts` 中 4 处原生 fetch 均已标注例外注释，守卫测试 PASS
- `saveOutput` 走 `request.ts`，不触发守卫

---

## 六、tsc 结果

- `npx tsc --noEmit`：**0 错误** ✅

---

## 七、功能测试结果

| 验证项 | 结果 |
|--------|------|
| 5 个接口全部注册（/openapi.json）| ✅ |
| 未鉴权返回 401 | ✅ |
| export-word 正常 Markdown → 36KB .docx | ✅ |
| export-word 空内容 → 400 INVALID_INPUT | ✅ |
| save-output 保存 → DB 写入 + OperationLog | ✅ |
| chat-stream 空 messages → 400 | ✅ |
| chat-stream 空 system_prompt → 400 | ✅ |
| transcribe 26MB 大文件 → 400 FILE_TOO_LARGE | ✅ |
| 前端路由 /workspace/qianchuan-edit-review 可访问 | ✅ |
