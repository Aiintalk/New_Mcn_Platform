# M2 Sprint 15 — 后端开发验收：人设脚本仿写 v2 修复 Bug（persona-writer）

> 验收状态：**通过**
> 验收日期：2026-06-23
> 验收人：MCN_PM_Agent
> 对应任务文档：`backend/docs/tasks/M2_Sprint15_后端任务_persona-writer_v2_修复Bug.md`
> 对应测试报告：`backend/docs/tests/M2_Sprint15_测试报告_persona-writer_v2_修复Bug.md`
> 对应分支：`migrate/persona-writer`
> 本次迭代类型：修复Bug（v2）

---

## 一、验收范围

对本次 v2 迭代的后端改动逐项验收，确认：
1. BUG 已修复且根因消除（非表面缓解）
2. 无新增回归
3. 契约文档同步到位
4. 符合 CLAUDE.md 7 条红线 + 9 条一票否决项

## 二、逐 BUG 验收

### BUG-025 TikHub 400 错误（P1）

| 验收项 | 结果 |
|-------|------|
| 根因定位 | ✅ `_resolve_short_url` 返回含 14 个 tracking 参数的脏 URL，TikHub 端点拒绝 |
| 修复方案 | ✅ 新增 `_clean_share_url`，urlsplit 后丢弃 query/fragment |
| 单测覆盖 | ✅ 4 纯函数测试 + 1 集成回归（mock CapturingClient）|
| 契约影响 | ✅ 不改 API 契约（adapter 内部实现）|
| **结论** | **✅ 通过** |

### BUG-026 4 writer SQL 不一致（P1）

| 验收项 | 结果 |
|-------|------|
| 根因定位 | ✅ persona/qianchuan 过滤 `status='active'`（已废弃），livestream/tiktok 无 status 过滤 |
| 修复方案 | ✅ 4 writer 统一为 `status IN ('signed','pending_renewal')` |
| 测试 fixture 修正 | ✅ 4 个集测文件的 INSERT 语句 `'active'` → `'signed'`（10 处）|
| 契约同步 | ✅ M2_Base_API §13.4 / §16.3 / §21.1 / §22.1 四处更新 |
| **结论** | **✅ 通过** |

### BUG-027 kols.status 默认值错误（P1）

| 验收项 | 结果 |
|-------|------|
| 根因定位 | ✅ ORM `Kol.status` default `'active'`（已废弃），新 SQL 过滤掉 |
| 修复方案 | ✅ 三层修复：ORM default → 'signed'；前端 Form initialValue='signed'；数据修复现有 'active' → 'signed' |
| 数据修复 | ✅ id=5、6、7 已修正为 'signed'（asyncpg 直连验证）|
| 契约同步 | ✅ M1_Base_Database §6.2 status 描述修正 + 加默认值说明 |
| **结论** | **✅ 通过** |

### BUG-028 红人重复创建无防护（P2）

| 验收项 | 结果 |
|-------|------|
| 根因定位 | ✅ kols.douyin_id / sec_uid 无 UNIQUE 约束，create_kol 无预检查 |
| 修复方案 | ✅ Migration 032 部分唯一索引 + create_kol 预检查 + 新增 ErrorCode |
| 索引设计 | ✅ 参照 idx_users_username 模式（partial WHERE deleted_at IS NULL）|
| 集成测试 | ✅ test_admin_kols.py 7 用例全过（含不覆盖、重复拒绝、软删后重建）|
| 契约同步 | ✅ M1_Base_Database §6.3（新建）+ M1_Base_API §3 错误码表 |
| **结论** | **✅ 通过** |

### BUG-029 数据污染（P1）

| 验收项 | 结果 |
|-------|------|
| 根因定位 | ✅ `_e2e_seed_personas.py`（gitignored 一次性脚本）UPDATE 了 name/persona 但未改其他字段 |
| 修复方案 | ✅ 软删 id=3、id=4，用户通过 UI 重建（用户已确认"软删 + 重建"方案）|
| 数据修复 | ✅ id=3、id=4 已设 deleted_at（asyncpg 直连验证）|
| 二次防护 | ✅ BUG-028 的唯一索引防止未来再次发生字段错乱（douyin_id 唯一）|
| **结论** | **✅ 通过** |

## 三、CLAUDE.md 红线自检

| 红线 | 状态 | 说明 |
|------|------|------|
| 1. 非流式接口返回标准信封 | ✅ | create_kol 用 error_response；统计接口用 success_response |
| 2. 用户写操作写 OperationLog | ✅ | create_kol 已有 OperationLog（v1 实现，本次未改）|
| 3. 前端走 request.ts | N/A | 本次后端改动不涉及前端 API |
| 4. 改接口/表同步契约 | ✅ | Base_API + Base_Database + README 全部同步 |
| 5. 功能完成更新 README | ✅ | backend/docs/README.md migrations 031→032 |
| 6. AiCallLog 由 adapter 写 | N/A | 本次不涉及 AI 调用 |
| 7. AsyncSessionLocal 注册 | ✅ | admin_kols 已在 conftest patch 列表（v1 已加）|

## 四、一票否决项自检（9 条）

| 否决项 | 状态 |
|-------|------|
| 自主注册 | ✅ 未涉及 |
| 越权 | ✅ create_kol 鉴权 require_admin |
| 看他人数据 | ✅ 不涉及 |
| 明文密钥 | ✅ 不涉及 |
| 响应结构错 | ✅ 标准信封 |
| 无 JWT 拿数据 | ✅ 鉴权完整 |
| 前端直连外部 | ✅ 不涉及 |
| 物理删除 | ✅ 用软删（deleted_at）|
| 列表无分页 | ✅ 不涉及（list_kols 已有分页）|

## 五、验收结论

| 维度 | 结论 |
|------|------|
| 5 个 BUG 全部根因修复 | ✅ |
| 无新增回归（51 + 6 回归全过）| ✅ |
| 契约文档同步完整 | ✅ |
| CLAUDE.md 7 红线 + 9 否决项无违反 | ✅ |
| 测试报告（自动化）通过 | ✅ |
| **整体** | **✅ 验收通过，建议 PM 签收** |

## 六、遗留与建议

1. **admin/kols API 完整契约章节**：M1_Base_API 缺整章（历史债务），建议独立任务补全
2. **运营添加红人权限**：当前仅 admin，运营走 kol-intake 问卷流程；若需运营直接添加，独立任务
3. **DB 唯一索引测试库验证**：测试库 metadata.create_all 不跑 migration，索引兜底未自动化覆盖；生产已应用，建议后续加 e2e 测试或 migration 验证脚本

## 七、签收

- 验收人：MCN_PM_Agent
- 验收日期：2026-06-23
- 下一步：合并入 PR #6 推送，待用户 GitHub 合并
