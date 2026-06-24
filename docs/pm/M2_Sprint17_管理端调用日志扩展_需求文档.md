# M2 Sprint 17 — 管理端调用日志扩展（用户列 + 功能列）需求文档

> **版本**：v1（方案 A 最小可用）
> **作者**：MCN_PM_Agent
> **日期**：2026-06-24
> **状态**：📝 待 PM 签收 → 待开工
> **预估**：~1 小时（不含 review + 测试 + 文档同步）

---

## 一、背景与目标

### 1.1 背景

管理员侧「调用日志」页面（`/admin/external-logs`）当前展示外部服务（AI / TikHub）调用明细，含 7 列：**服务 / 接口 / 状态 / 耗时 / Token入 / Token出 / 时间**。

**痛点**：当某条调用失败或异常时，管理员**看不到是哪个用户调的**、**也看不到是从哪个功能页面发起的**。排查只能凭时间戳 + endpoint 倒推，效率低。

### 1.2 目标

在调用日志页加两列：
1. **用户**：调用发起人的 username
2. **功能**：调用来源功能标识（如 `persona-positioning` / `seeding-writer` / `persona-writer`）

让管理员一眼定位"谁、在哪个功能、调了什么服务、结果如何"。

### 1.3 与已有字段的关系

| 字段 | 已有表 | 现状 |
|------|--------|------|
| `user_id` | `ai_call_logs / tikhub_call_logs / oss_call_logs / asr_call_logs`（4 张明细表） | ✅ 都有 |
| `feature` | `ai_call_logs` | ✅ 有；其他 3 张明细表没有 |
| `external_service_logs`（前端页面真正读的统一视图） | — | ❌ **两个都没有** |

**关键**：前端页面读的是 `external_service_logs`，不是 4 张明细表。所以本任务改 `external_service_logs` 即可，**不动其他 4 张明细表**。

---

## 二、范围

### 2.1 在范围（方案 A 最小可用）

| # | 改动 | 文件 |
|---|------|------|
| 1 | 数据库加 2 列 | `backend/migrations/034_external_logs_add_user_feature.sql`（新建） |
| 2 | ORM 加 2 字段 | `backend/app/models/log.py:22-42`（ExternalServiceLog） |
| 3 | API 返回 user_id + username + feature | `backend/app/routers/admin_logs.py:81-124` |
| 4 | 前端类型扩展 | `frontend/src/types/log.ts`（ExternalServiceLog） |
| 5 | 前端页面加 2 列 | `frontend/src/pages/admin/ExternalLogsPage.tsx` |
| 6 | 文档同步 | `backend/docs/base/MCN_M2_Base_Database.md` + `frontend/docs/README.md` |
| 7 | 测试 | 后端：1 个集成测试（admin_external_logs 含新字段）；前端：1 个组件测试（新列渲染） |

### 2.2 不在范围（留作后续）

| 项 | 原因 | 后续路径 |
|----|------|---------|
| **方案 B（写入端填实）**：改 adapter 写日志时传 user_id + feature | 工程量大（每个调用点要改），且方案 A 先搭框架更稳 | 独立任务 `M2_Sprint17_v2_调用日志写入端填实` |
| **ASR 日志接入 `external_service_logs`** | ASR 当前写 `asr_call_logs`（独立表），需要改 ASR adapter 双写或迁移；不在最小可用范围 | 独立任务 |
| **筛选/过滤**：按用户/功能筛选 | 用户没要求；当前页面筛选只有"服务+状态" | 视使用反馈再加 |
| **导出 CSV** | 同上 | 视使用反馈再加 |

### 2.3 数据回填策略

历史 `external_service_logs` 记录的 `user_id` 和 `feature` **都是 NULL**，页面显示「—」。

**不做强制回填**（无可靠来源推断历史数据归属）。新数据从方案 B 落地后开始有值。

---

## 三、详细方案

### 3.1 数据库 Migration（034）

**文件**：`backend/migrations/034_external_logs_add_user_feature.sql`（新建）

```sql
-- M2 Sprint 17：external_service_logs 加 user_id + feature 字段
-- 用于管理员调用日志页展示「调用用户」「调用功能」
-- 历史数据 NULL，显示「—」

ALTER TABLE external_service_logs
  ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS feature VARCHAR(64);

-- 按用户筛选索引（管理员排查高频）
CREATE INDEX IF NOT EXISTS idx_external_service_logs_user_id
  ON external_service_logs(user_id);

-- 按功能筛选索引
CREATE INDEX IF NOT EXISTS idx_external_service_logs_feature
  ON external_service_logs(feature);
```

**降级方案**：
```sql
ALTER TABLE external_service_logs
  DROP COLUMN IF EXISTS user_id,
  DROP COLUMN IF EXISTS feature;
DROP INDEX IF EXISTS idx_external_service_logs_user_id;
DROP INDEX IF EXISTS idx_external_service_logs_feature;
```

### 3.2 ORM 模型（`backend/app/models/log.py:22-42`）

在 `ExternalServiceLog` 类加两个字段：

```python
class ExternalServiceLog(Base):
    __tablename__ = "external_service_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    service = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    # ... 现有字段保持不变 ...
    
    # —— Sprint 17 新增（可空，历史数据为 NULL）——
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    feature = Column(String(64), nullable=True)  # persona-positioning / seeding-writer / ...
    
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

### 3.3 后端 API（`backend/app/routers/admin_logs.py:81-124`）

修改 `GET /api/admin/logs/external` 的 items 构造：

```python
# 在 session 内 JOIN users 拿 username（一次性查）
from app.models.user import User
from sqlalchemy.orm import selectinload

q = select(ExternalServiceLog).options(
    selectinload(ExternalServiceLog.user)  # 需要在 ORM 加 relationship
)
# ... 原有 filter / order / pagination ...

items = [
    {
        # ... 现有字段 ...
        "user_id": lg.user_id,
        "username": lg.user.username if lg.user else None,  # JOIN 出来的
        "feature": lg.feature,
        # ...
    }
    for lg in rows
]
```

**改动要点**：
- 加 `relationship("User")` 到 ExternalServiceLog（ORM 层）
- API 用 `selectinload` 一次性 JOIN users（避免 N+1）
- 返回 `user_id` + `username` + `feature` 三字段

### 3.4 前端类型（`frontend/src/types/log.ts`）

```typescript
export interface ExternalServiceLog {
  id: number;
  service: string;
  endpoint: string;  // action
  // ... 现有字段 ...
  
  // —— Sprint 17 新增 ——
  user_id: number | null;
  username: string | null;
  feature: string | null;
  
  created_at: string;
}
```

### 3.5 前端页面（`frontend/src/pages/admin/ExternalLogsPage.tsx`）

当前表头 7 列：服务 / 接口 / 状态 / 耗时 / Token入 / Token出 / 时间

**改造后 9 列**：服务 / 接口 / **用户** / **功能** / 状态 / 耗时 / Token入 / Token出 / 时间

```tsx
<thead><tr>
  <th>服务</th>
  <th>接口</th>
  <th>用户</th>          {/* 新增 */}
  <th>功能</th>          {/* 新增 */}
  <th>状态</th>
  <th>耗时</th>
  <th>Token入</th>
  <th>Token出</th>
  <th>时间</th>
</tr></thead>
<tbody>{data.items.map(l => (
  <tr key={l.id}>
    {/* 现有列 */}
    <td>...</td>
    <td>...{l.endpoint}</td>
    
    {/* 新增列 */}
    <td style={{fontSize:12,color:'var(--gray-500)'}}>
      {l.username ?? '—'}
    </td>
    <td style={{fontSize:12,color:'var(--gray-500)'}}>
      {l.feature ? <span className="badge badge-default">{l.feature}</span> : '—'}
    </td>
    
    {/* 现有列续 */}
    <td>...</td>
    ...
  </tr>
))}</tbody>
```

**样式约定**：
- 用户列：纯文本（灰色），NULL 显示「—」
- 功能列：用 badge 标签（与"服务"列 badge 风格一致），NULL 显示「—」
- feature 命名见 §3.6

### 3.6 feature 字段命名规范

对齐 `ai_call_logs.feature` 已有命名风格（kebab-case）：

| feature 值 | 含义 |
|-----------|------|
| `persona-positioning` | 人格定位 |
| `persona-writer` | 人设脚本仿写 |
| `tiktok-writer` | TikTok 脚本仿写 |
| `seeding-writer` | 种草内容仿写 |
| `livestream-writer` | 直播脚本仿写 |
| `qianchuan-writer` | 千川文案写作 |
| `selling-point-extractor` | 卖点提取 |
| `benchmark` | 对标分析 |
| `qianchuan-review` | 千川脚本复盘 |
| `qianchuan-edit-review` | 千川剪辑预审 |
| `qianchuan-preview` | 千川文案预审 |
| `qianchuan-collection` | 千川爆文合集 |
| `tiktok-review` | TT 内容复盘 |
| `livestream-review` | 直播间脚本复盘 |
| `persona-review` | 人设脚本复盘 |
| `kol-intake` | 红人入驻问卷 |

方案 A 阶段**只列规范，不强制写入端实现**（写入端在方案 B 落地）。

---

## 四、决策点（待 review）

| # | 决策项 | 推荐方案 | 备选 | 备注 |
|---|--------|---------|------|------|
| 1 | 字段命名 | `feature`（对齐 `ai_call_logs.feature`） | `tool_code` | 推荐 feature，与已有命名一致 |
| 2 | 「用户」列显示 | `username`（更友好，admin 一眼能认） | `user_id`（数字） / `username (id)` | 推荐 username；如需 user_id 可加 tooltip |
| 3 | 索引 | 加 user_id + feature 两个索引 | 不加索引 | 推荐加（管理员按用户/功能排查是高频操作） |
| 4 | ASR 是否顺手接入 | **不接入**（独立任务） | 双写 external_service_logs | 推荐不接入，保持方案 A 简洁 |
| 5 | 分支策略 | `feature/admin-logs-extend`（新分支，从 main 拉） | 复用当前 `migrate/seeding-writer` | 推荐新分支（与 seeding-writer 解耦） |

**以上 5 点如无异议按推荐方案开工；如有调整请直接在本节批注。**

---

## 五、测试计划

### 5.1 后端集成测试

**文件**：`backend/tests/integration/routers/test_admin_logs.py`（已存在，扩展）

新增测试：
- `test_external_logs_returns_user_and_feature_fields` —— 写入一条带 user_id + feature 的 ExternalServiceLog，调 API 验证返回的 items[0] 含 user_id / username / feature
- `test_external_logs_null_user_and_feature_render_as_null` —— 写入一条 user_id=None + feature=None，验证返回值字段为 None（不报错）

### 5.2 前端组件测试

**文件**：`frontend/src/__tests__/components/pages/ExternalLogsPage.test.tsx`（已存在或新建）

新增测试：
- 渲染含 user_id/feature 的记录，验证「用户」「功能」列显示正确
- 渲染 user_id/feature 为 null 的记录，验证显示「—」

### 5.3 回归测试

- 后端 `pytest tests/integration/routers/test_admin_logs.py` 全绿（不破坏现有 4 个测试）
- 前端 `npx vitest run` 全绿（180 个测试不受影响）

### 5.4 手动验收

1. 跑 migration 034，验证表结构含 user_id + feature
2. 启动前后端，进 admin 调用日志页，验证看到 9 列
3. 历史数据 user_id/feature 应显示「—」
4. 调一次 persona-positioning（生成新日志），刷新页面，验证新记录的 user_id/feature 仍是「—」（因为方案 A 没改写入端，预期 NULL）

---

## 六、文档同步清单

| # | 文件 | 改动 |
|---|------|------|
| 1 | `backend/docs/base/MCN_M2_Base_Database.md` | `external_service_logs` 表 schema 加 user_id + feature 字段说明 + §migration 清单加 034 |
| 2 | `backend/docs/base/MCN_M2_Base_API.md` | `GET /api/admin/logs/external` 返回字段加 user_id / username / feature |
| 3 | `backend/docs/README.md` | migrations 清单加 034 |
| 4 | `frontend/docs/README.md` | 调用日志页列从 7 改 9（加用户/功能） |
| 5 | `docs/pm/PM_记忆与状态_M2.md` | 加 Sprint 17 工作项子章节 |

---

## 七、实施顺序（TDD）

### Step 1：分支 + 数据库
1. `git checkout main && git pull && git checkout -b feature/admin-logs-extend`
2. 写 migration 034，跑迁移验证表结构
3. ORM 加 2 字段 + relationship
4. 启动后端验证模型加载无错

### Step 2：后端 API + 测试
1. 写集成测试（5.1 两个新测试）—— RED
2. 改 `admin_logs.py::admin_external_logs`（加 JOIN + 返回字段）—— GREEN
3. 跑测试全绿

### Step 3：前端类型 + UI + 测试
1. 改 `types/log.ts` 加 3 字段
2. 写组件测试（5.2 两个新测试）—— RED
3. 改 `ExternalLogsPage.tsx` 加 2 列 —— GREEN
4. 跑 vitest 全绿

### Step 4：手动验收 + 文档
1. 浏览器进调用日志页，验证 9 列渲染
2. 同步 5 份文档
3. commit + push + 发 PR

---

## 八、验收标准（DoD）

| 验收项 | 状态 |
|--------|------|
| Migration 034 落地，表结构含 user_id + feature + 2 个索引 | ☐ |
| `external_service_logs` ORM 加 2 字段 + User relationship | ☐ |
| `GET /api/admin/logs/external` 返回 user_id / username / feature 三字段 | ☐ |
| 前端 `ExternalServiceLog` 类型扩展 | ☐ |
| `ExternalLogsPage` 显示 9 列（含用户、功能） | ☐ |
| 历史数据 user_id/feature 显示「—」 | ☐ |
| 后端集成测试 2 个新用例通过 | ☐ |
| 前端组件测试 2 个新用例通过 | ☐ |
| 后端 pytest 整体不回归 | ☐ |
| 前端 vitest 整体不回归 | ☐ |
| 5 份文档同步（DB / API / 后端README / 前端README / PM记忆） | ☐ |
| CLAUDE.md 7 红线 + 9 一票否决项无新增触发 | ☐ |

---

## 九、CLAUDE.md 红线自检

| 红线 | 状态 | 说明 |
|------|------|------|
| ① 标准信封 | ✅ | API 继续用 `success_response`；非流式 |
| ② OperationLog | N/A | 本次为只读接口（GET），无用户写操作 |
| ③ 前端走 request.ts | ✅ | api/logs.ts 已用 `get`，不变 |
| ④ 契约同步 | ✅ | Base_API + Base_Database 都同步 |
| ⑤ README 更新 | ✅ | 前后端 README 都更新 |
| ⑥ AiCallLog 由 adapter 写 | N/A | 不涉及 AI adapter 改动 |
| ⑦ AsyncSessionLocal 注册 | ✅ | admin_logs.py 已用 AsyncSessionLocal，conftest patch 列表无需扩展 |

**9 条一票否决项**：无新增触发。

---

## 十、风险与影响面

| 风险 | 影响 | 缓解 |
|------|------|------|
| migration 034 跑失败 | 表结构未变，API/ORM 报字段不存在 | 提供 §3.1 降级 SQL；先在本地库测试 |
| 历史数据两列全空，用户看不到价值 | 用户体验"白搭两列" | §2.3 已声明预期；后续方案 B 落地数据填实 |
| `selectinload` JOIN 性能 | 大数据量时慢 | external_service_logs 当前规模小（千级），无性能问题；如需可加 user_id 索引（已加） |
| 前端 9 列太挤 | 表格横向溢出 | feature 用 badge 短文字；可后续加横向滚动或列宽自适应 |

---

## 十一、工作量估算

| 阶段 | 工作量 |
|------|--------|
| 数据库（migration + ORM） | 10 分钟 |
| 后端 API + 2 集成测试 | 20 分钟 |
| 前端类型 + UI + 2 组件测试 | 20 分钟 |
| 文档同步（5 份） | 15 分钟 |
| 手动验收 + commit + push + PR | 10 分钟 |
| **合计** | **~75 分钟** |

---

## 十二、后续任务（不在本次范围）

1. **方案 B 写入端填实**：改 yunwu/tikhub/oss/asr adapter 在写 `external_service_logs` 时填 user_id + feature；改所有 router 调 adapter 时显式传两个参数（~3-4 小时）
2. **ASR 接入 external_service_logs**：让 ASR 日志也能在调用日志页看到（~30 分钟）
3. **筛选/过滤**：调用日志页加"按用户"和"按功能"下拉筛选（~30 分钟）
4. **CSV 导出**：管理员可导出当前筛选结果（~1 小时）
