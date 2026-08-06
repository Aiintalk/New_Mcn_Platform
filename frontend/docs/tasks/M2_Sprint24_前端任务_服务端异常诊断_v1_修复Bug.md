# M2 Sprint 24 前端任务：服务端异常诊断 v1（修复 Bug）

## 目标

当后端返回 HTTP 5xx 且正文不是 JSON 时，给运营展示可行动的中文诊断，不再直接显示 `Invalid JSON response from server`。

## 约束

- 只改共享 `request.ts` 的非 JSON 异常分支。
- 保留 HTTP 状态码，提示检查服务日志和数据库迁移。
- 不掩盖后端问题，不把前端提示当作 P0 根因修复。
- 正常 JSON 信封、鉴权跳转和权限提示行为保持不变。

## 验收

`request.test.ts` 新增非 JSON HTTP 500 用例，原有请求、鉴权和错误信封用例全部通过。
