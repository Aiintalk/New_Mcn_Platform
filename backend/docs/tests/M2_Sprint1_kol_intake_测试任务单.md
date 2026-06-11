# MCN Platform · M2 Sprint 1 测试任务单（kol-intake 红人入驻问卷）

> 测试范围：kol-intake 全部 23 个接口 + AI 对话 + 报告生成 + 下载权限 + 并发场景
> 测试时间：
> 测试人：
> 测试环境：本地开发环境

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 后端地址 | `http://localhost:8000` |
| 前端地址 | `http://localhost:5173` |
| 数据库 | PostgreSQL `mcn_m1` @ localhost:5432 |
| 测试账号 | admin（已改密）/ testop（operator，密码 Operator@123） |
| 前置条件 | AI Key Pool 至少有一条可用 AI Key；`kol_intake_configs` 已配置 `conversation_bridge` 和 `report_generation` |

---

## 第一章：公开接口（博主端）

### 1.1 链接校验

**前置：admin 登录，运营创建一个有效链接（`POST /api/operator/intake/links`）。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-PUB-001 | `GET /api/intake/{有效token}` | 200，返回 `{ valid: true, kol_name, already_submitted: false, existing_messages: [] }` | |
| KI-PUB-002 | `GET /api/intake/{不存在的token}` | 404 / LINK_NOT_FOUND | |
| KI-PUB-003 | `GET /api/intake/{已过期token}` | 410 / LINK_EXPIRED | |
| KI-PUB-004 | 重复访问同一有效链接 | 第二次 `used_at` 不再更新（幂等） | |
| KI-PUB-005 | 已提交的链接再次访问 | `already_submitted: true`，`existing_messages` 非空 | |

### 1.2 AI 对话

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-PUB-006 | `POST /api/intake/{token}/chat` 传 `messages: []` | 200，返回 AI 开场白（`reply` 非空，`role: "assistant"`） | |
| KI-PUB-007 | 传完整对话历史 `[{assistant, user, assistant, user}]` | 200，AI 返回追问或引导下一题 | |
| KI-PUB-008 | AI 未配置时（`conversation_bridge` 无记录或 AI Key 不可用） | 200，`reply: null, error: "AI对话暂未配置"` | |
| KI-PUB-009 | 不带 JWT Token 直接调用 chat | 200（公开接口，无需鉴权） | |
| KI-PUB-010 | 传空 body `{}` | 400 / VALIDATION_ERROR | |
| KI-PUB-011 | 已过期链接调用 chat | 410 / LINK_EXPIRED | |

### 1.3 提交与报告

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-PUB-012 | `POST /api/intake/{token}/submit` 传完整 messages | 200，返回 `{ submission_id, report_status: "generating" }` | |
| KI-PUB-013 | 重复提交同一链接 | 409 / ALREADY_SUBMITTED | |
| KI-PUB-014 | 已过期链接提交 | 410 / LINK_EXPIRED | |
| KI-PUB-015 | 提交后 `kol_intake_links.submitted_at` 有值 | DB 验证 | |

### 1.4 报告状态轮询

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-PUB-016 | `GET /api/intake/{token}/status`（刚提交） | `{ report_status: "generating", download_ready: false }` | |
| KI-PUB-017 | 等待 30-60 秒后再次查询 | `{ report_status: "ready", download_ready: true }` | |
| KI-PUB-018 | 报告生成失败时查询 | `{ report_status: "failed", download_ready: false }` | |

### 1.5 下载

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-PUB-019 | `GET /api/intake/{有效token}/download?format=docx`（报告已就绪） | 200，文件流，Content-Disposition 包含文件名 | |
| KI-PUB-020 | `GET /api/intake/{有效token}/download?format=pdf` | 200，PDF 文件流 | |
| KI-PUB-021 | 报告未就绪时下载 | 报告未就绪的错误响应 | |
| KI-PUB-022 | 已过期链接下载 | 410 / LINK_EXPIRED | |
| KI-PUB-023 | 首次下载后 `kol_downloaded_at` 有值 | DB 验证 | |
| KI-PUB-024 | 重复下载同一报告 | 正常返回文件（不报错） | |

---

## 第二章：运营端接口

### 2.1 链接管理

**前置：operator（testop）已登录。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-OP-001 | `POST /api/operator/intake/links` { kol_name: "测试博主", expires_hours: 24 } | 200，返回 `{ id, token, share_url, expires_at }` | |
| KI-OP-002 | expires_hours = 0 | 400 / VALIDATION_ERROR | |
| KI-OP-003 | expires_hours = 721（超过 720 上限） | 400 / VALIDATION_ERROR | |
| KI-OP-004 | kol_name 为空字符串 | 允许或返回 400（以实际实现为准） | |
| KI-OP-005 | 工具 `kol-intake` 状态为 offline 时创建链接 | 403 / TOOL_NOT_ONLINE | |
| KI-OP-006 | `GET /api/operator/intake/links` | 200，只返回当前 operator 创建的链接 | |
| KI-OP-007 | operator A 创建的链接，operator B 看不到 | 数据隔离验证 | |

### 2.2 提交记录

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-OP-008 | `GET /api/operator/intake/submissions` | 200，只返回当前 operator 的提交 | |
| KI-OP-009 | `GET /api/operator/intake/submissions/{id}`（自己的） | 200，含 `messages` 和 `ai_report` | |
| KI-OP-010 | `GET /api/operator/intake/submissions/{id}`（别人的） | 403 或 404 | |
| KI-OP-011 | 未登录调用运营端接口 | 401 / AUTH_TOKEN_MISSING | |

### 2.3 运营下载

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-OP-012 | 链接未过期且博主未下载 → 运营下载 | 403 / DOWNLOAD_NOT_ALLOWED | |
| KI-OP-013 | 链接已过期 → 运营下载 | 200，文件流 | |
| KI-OP-014 | 博主已下载 → 运营下载 | 200，文件流 | |
| KI-OP-015 | 运营首次下载后 `operator_downloaded_at` 有值 | DB 验证 | |

---

## 第三章：管理员接口

**前置：admin 已登录。**

### 3.1 题目管理

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-ADM-001 | `GET /api/admin/intake/questions` | 200，返回题目列表，按 order_num 排序 | |
| KI-ADM-002 | `POST /api/admin/intake/questions` 新增题目 | 201 或 200，创建成功 | |
| KI-ADM-003 | `PATCH /api/admin/intake/questions/{id}` 修改题目内容 | 200，更新成功 | |
| KI-ADM-004 | `DELETE /api/admin/intake/questions/{id}` | 200，软删除（`is_active=false`），记录仍在 DB | |
| KI-ADM-005 | `PUT /api/admin/intake/questions/reorder` 批量更新排序 | 200，order_num 更新 | |
| KI-ADM-006 | operator 调用题目管理接口 | 403 / PERMISSION_DENIED | |

### 3.2 AI 配置管理

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-ADM-007 | `GET /api/admin/intake/configs` | 200，返回两条配置（conversation_bridge + report_generation） | |
| KI-ADM-008 | `PUT /api/admin/intake/configs/conversation_bridge` 更新 system_prompt | 200，更新成功 | |
| KI-ADM-009 | `PUT /api/admin/intake/configs/report_generation` 更新 AI 模型 | 200，更新成功 | |
| KI-ADM-010 | `PUT /api/admin/intake/configs/invalid_key` | 404 或 400 | |

### 3.3 链接管理（admin 全量）

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-ADM-011 | `GET /api/admin/intake/links` | 200，返回全部用户的链接，含 operator 信息 | |
| KI-ADM-012 | operator 调用 admin 链接列表 | 403 / PERMISSION_DENIED | |

### 3.4 提交记录（admin 全量）

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-ADM-013 | `GET /api/admin/intake/submissions` | 200，返回全部提交，含 operator 信息 | |
| KI-ADM-014 | `GET /api/admin/intake/submissions/{id}` | 200，含 messages + ai_report | |
| KI-ADM-015 | `POST /api/admin/intake/submissions/{id}/regenerate` 重新生成 | 200，触发重新生成 | |
| KI-ADM-016 | 对不存在的 id regenerate | 404 / SUBMISSION_NOT_FOUND | |

---

## 第四章：AI 调用日志

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-LOG-001 | AI 对话后查看 `ai_call_logs` | 有记录，feature='kol_intake_chat'，tokens_in/tokens_out 有值 | |
| KI-LOG-002 | 报告生成后查看 `ai_call_logs` | 有记录，feature='kol_intake_report'，model 含 opus | |
| KI-LOG-003 | AI 调用失败时 | ai_call_logs 中 status='failed'，error_message 非空 | |

---

## 第五章：端到端完整流程

**从运营创建链接到博主下载报告的完整链路。**

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-E2E-001 | 运营生成链接 → 博主打开 → AI 对话 3 轮 → 提交 → 等待 → 轮询 ready → 下载 docx | 全流程跑通，文件正常 | |
| KI-E2E-002 | 同上，下载 PDF 格式 | PDF 文件正常 | |
| KI-E2E-003 | 运营查看提交详情 | 显示完整对话 + AI 报告 | |
| KI-E2E-004 | 链接过期后运营下载 | 下载成功 | |

---

## 第六章：并发与边界

| 编号 | 操作 | 预期结果 | 结果 |
|------|------|----------|------|
| KI-CON-001 | 20 并发同时访问同一有效链接 | 全部成功，`used_at` 只写入一次 | |
| KI-CON-002 | 20 并发同时提交同一链接 | 只有 1 个 200，其余 409 | |
| KI-CON-003 | 20 并发同时下载同一报告 | 全部成功 | |
| KI-CON-004 | 多个 operator 同时创建各自链接 | 各自独立，无数据混乱 | |

---

## 一票否决项（任一出现则整体不通过）

```
1. 公开接口（/api/intake/*）要求 JWT 鉴权
2. operator 能看到其他 operator 的链接或提交
3. AI Key 在接口响应中明文暴露
4. API 响应结构不是 { success, code, message, data }
5. 报告生成在请求响应链内同步执行（非 BackgroundTasks）
6. 物理删除任何数据（题目删除应是 is_active=false）
7. operator 能访问 /api/admin/intake/* 接口
8. 运营在博主下载前且链接有效期内能下载报告
9. 列表接口无分页
```

---

## 测试结果汇总模板

```
项目：MCN Information System Platform
阶段：M2 Sprint 1 — kol-intake
测试日期：
测试人：

总计：__ 项
通过：__ 项
失败：__ 项

一票否决项：无 / 有（描述）

失败项清单：
- 编号：xxx，失败原因：

结论：通过 / 不通过
```
