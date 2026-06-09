# MCN_PM_Agent — 项目记忆与当前状态

> 最后更新：2026-06-06（第二次更新）  
> 更新角色：MCN_PM_Agent

---

## 一、项目基本信息

- **项目名**：MCN Information System Platform
- **当前阶段**：M1 基层搭建
- **工作目录**：`D:\2026年工作\AI相关\AI工具箱新架构方案\mcn-platform\`
- **数据库**：PostgreSQL 18.4 @ localhost:5432，用户 postgres，密码 admin123，数据库 `mcn_m1`（旧库 `mcn_platform` 保留不动）
- **psql 路径**：`D:\ProtgreSQL\bin\psql.exe`
- **后端地址**：`http://localhost:8000`（uvicorn，Python FastAPI）
- **前端地址**：`http://localhost:5173`（Vite + React + TS）
- **测试账号**：admin（密码已改密）/ testop（operator，密码 Operator@123）

---

## 二、Sprint 进度总览

| Sprint | 后端 | 前端 | 运维 | 说明 |
|---|---|---|---|---|
| Sprint 0 | ✅ 通过 | ✅ 通过 | ✅ 通过 | 三端初始化 |
| Sprint 1 | ✅ 通过 | ✅ 通过 + 联调 ✅ | ✅ 通过 | JWT + 用户管理 + 登录页 |
| Sprint 2 | ✅ 通过 | ✅ 通过 | — | 工作台 API + 页面实现 |
| Sprint 3 | 🟡 待执行 | 🟡 待执行 | — | 任务/产出/文件/日志/密钥池 |
| Sprint 4 | ⏸ 未开始 | ⏸ 未开始 | ⏸ 待命 | 测试服部署（本地验收后启动）|

---

## 三、Sprint 2 遗留热修复（已完成）

- `GET /api/workspace/tools` 已修正为返回 `status IN ('online', 'dev')` 共 5 个工具
- 前端 `/workspace` 已确认展示 5 张工具卡片（1 online 可点击，4 dev 置灰）

---

## 四、决策问题状态（D001–D008）

| 编号 | 问题 | 状态 | 决策内容 |
|---|---|---|---|
| D001 | 前端设计文档载体 | ✅ 已确认 | `mcn_workspace_ui.jsx` 即为前端设计文档 |
| D002 | 数据库契约冲突 | ✅ 已确认 | 以 Base_Database.md 为准，新建 `mcn_m1` 独立数据库 |
| D002-D | 表名冲突 | ✅ 已确认 | 方案C：新建独立数据库 `mcn_m1` |
| D003 | OSS 接入深度 | ✅ 已确认 | Mock URL（真实接入待 OSS 凭证就绪后实现；结构/SDK 在 Sprint 3 预装）|
| D004-AI | AI adapter 深度 | ✅ 已确认 | **打通链路**：Key 池选 Key → httpx POST yunwu.ai → `chat()` 真实实现 + `/api/admin/system/ai-test` 测试接口 |
| D004-TikHub | TikHub adapter 深度 | ✅ 已确认 | Key 池轮询 + 3 个真实接口（用户信息/粉丝/直播商品）+ `/api/admin/system/tikhub-test` 测试接口 |
| D004-OSS/ASR | OSS/ASR adapter | ✅ 已确认 | OSS: 结构预留 + `oss2` SDK 预装，`get_download_url()` 返回 Mock；ASR: 后续 Sprint |
| D005 | 数据库迁移工具 | ✅ 已确认 | 继续 SQL 脚本；Sprint 3 DDL：`ADD COLUMN config JSONB` + `kols.tikhub_raw JSONB` |
| D006 | 测试服部署时机 | 🟡 **待确认** | PM 建议：本地验收后 Sprint 4 |
| D007 | admin seed 策略 | 🟡 **待确认** | PM 建议：当前实现不变（env 变量 seed，首登改密）|
| D008 | 工具列表返回范围 | ✅ 已确认 | 返回 online + dev，offline 过滤 |
| D009 | Key 存储位置 | ✅ 已确认 | 存 DB（service_credentials 表），Key 池轮询，不依赖 .env 单 Key |
| — | kols.tikhub_raw | ✅ 已确认 | Sprint 3 加 JSONB 字段，TikHub 原始响应先完整存储再提取结构化字段 |

---

## 五、技术信息补充（用于 Sprint 3 adapter 实现）

### Key Pool 架构
- **service_credentials 表**：存储所有外部服务 Key，新增 `config JSONB` 字段
- **CredentialSelector**（`app/services/credential_selector.py`）：
  - `pick_credential(provider, db, model=None)` — 加权随机选 Key
  - `report_success(credential_id, db)` — 归零 fail_count，quota_used += 1
  - `report_failure(credential_id, db)` — fail_count += 1；≥3 次冷却 5 分钟
- **config JSONB 示例**（AI）：`{"model": "claude-haiku-4-5-20251001", "base_url": "https://yunwu.ai/v1", "max_tokens": 4096}`

### TikHub 接口信息
- **Base URL**：`https://api.tikhub.io`
- **认证**：`Authorization: Bearer {api_key}`
- **配置来源**：DB system_configs（tikhub_api_key / tikhub_base_url）或环境变量
- **接口 1**：`GET /api/v1/douyin/app/v3/handler_user_profile`，参数 `sec_user_id`，返回 nickname/uid/room_id/unique_id
- **接口 2**：`POST /api/v1/douyin/index/fetch_daren_great_user_fans_info`，参数 `user_id`（数字型 uid）
- **接口 3**：`GET /api/v1/douyin/web/fetch_live_room_product_result`，参数 room_id/author_id/limit=100，返回 data.promotions
- **原始数据方案**：TikHub 返回数据先完整存入 `kols.tikhub_raw JSONB`，再提取已确认字段写入结构化列

### AI 接口信息
- **Endpoint**：`https://yunwu.ai/v1/chat/completions`（OpenAI 兼容代理）
- **模型**：`claude-haiku-4-5-20251001`（可切换）
- **SDK**：无，直接 `httpx POST`
- **并发限制**：`Semaphore(3)`
- **Timeout**：120s
- **配置优先级**：DB system_configs（租户级）> .env > 代码默认值
- **M1 目标**：打通链路，实现通用 `chat()` 方法 + 管理后台 AI 连通性测试接口
- **⚠️ 安全提示**：`.env` 中 `LLM_API_KEY` 需加入 `.gitignore`，不能明文入库

---

## 六、Sprint 3 待生成/更新内容

Sprint 3 任务文件已更新完毕：

- [x] `docs/tasks/backend/M1_Sprint3.md` — 已更新（含 Key Pool + 真实 AI/TikHub + 原有任务/产出/文件/日志/密钥池 API）
- [ ] `docs/tasks/frontend/M1_Sprint3.md` — 待执行（Mock 替换真实 API + 管理员功能页完整实现，含新增 `/admin/system` AI 测试面板）

---

## 七、任务文件目录

```
mcn-platform/
├── docs/tasks/backend/
│   ├── M1_Sprint0.md   ✅ 已执行
│   ├── M1_Sprint1.md   ✅ 已执行
│   ├── M1_Sprint2.md   ✅ 已执行
│   └── M1_Sprint3.md   🟡 待更新（D003-D007 确认后补充 AI/TikHub）
├── docs/tasks/frontend/
│   ├── M1_Sprint0.md   ✅ 已执行
│   ├── M1_Sprint1.md   ✅ 已执行
│   ├── M1_Sprint2.md   ✅ 已执行
│   └── M1_Sprint3.md   🟡 待执行
└── docs/tasks/deploy/
    ├── M1_Sprint0.md   ✅ 已执行
    └── M1_Sprint1.md   ✅ 已执行
```

---

## 八、下一步工作清单

1. **下发后端 Sprint 3**（指令文件已就绪：`docs/tasks/backend/M1_Sprint3.md`）
   - Step 0：执行 DDL（config JSONB + tikhub_raw JSONB）
   - Step 1-4：CredentialSelector + AI/TikHub/OSS adapter
   - Step 5：管理员系统测试接口
   - Step 6-11：任务/产出/文件/日志/密钥池 API + 路由注册
   - Step 12：.env.example 补充
2. **后端完成后**：向 DB 注入测试用 AI Key（provider=ai，config 含 model/base_url）
3. **向 DB 注入测试用 TikHub Key**（provider=tikhub，config 含 base_url）
4. **执行 `/api/admin/system/ai-test` 验证 AI 链路**
5. **执行 `/api/admin/system/tikhub-test` 验证 TikHub 链路**
6. **下发前端 Sprint 3**（Mock → 真实 API + 管理员功能页）
7. **Sprint 3 联调通过后**：安排测试 Claude 执行 Base_Acceptance 全量用例
8. **全量验收通过后**：启动 Sprint 4 测试服部署
9. **待用户提供**：阿里云 OSS bucket/region/access_key → 实现 OSS 真实接入
