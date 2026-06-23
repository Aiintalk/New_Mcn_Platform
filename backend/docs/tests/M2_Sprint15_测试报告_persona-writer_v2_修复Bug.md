# M2 Sprint 15 — 测试报告：人设脚本仿写 v2 修复 Bug（persona-writer）

> 状态：**通过**
> 测试日期：2026-06-23
> 对应任务文档：
> - 后端：`backend/docs/tasks/M2_Sprint15_后端任务_persona-writer_v2_修复Bug.md`
> - 前端：`frontend/docs/tasks/M2_Sprint15_前端任务_persona-writer_v2_修复Bug.md`
> 对应分支：`migrate/persona-writer`
> 测试执行人：MCN_PM_Agent

---

## 一、测试范围

本次 v2 迭代聚焦 E2E 验收期发现的 bug 修复 + 配套完善，测试覆盖：

1. **TikHub URL 清洗**（BUG-025）— 单元测试
2. **4 writer SQL 统一**（BUG-026）— 测试 fixture 修正 + 回归
3. **kols 唯一索引 + create_kol 预检查**（BUG-028）— 集成测试新建
4. **kols.status 默认值修复**（BUG-027）— 数据修复 + ORM 改动（回归覆盖）
5. **数据污染清理**（BUG-029）— 数据修复（无代码测试）
6. **ConfigTab 描述清理 + KolsPage content_plan UI**（BUG-030、BUG-031）— 前端 UI 微调（手动 E2E）

## 二、测试结果汇总

### 2.1 单元测试

| 测试文件 | 用例数 | 通过 | 失败 | 状态 |
|---------|-------|------|------|------|
| `tests/unit/services/test_tikhub_adapter.py` | 30（含新增 5）| 30 | 0 | ✅ |

**新增用例**：
- `test_clean_share_url_strips_query_params` — 脏 URL（含 14 个 tracking 参数）清洗
- `test_clean_share_url_preserves_clean_url` — 干净 URL 不变形
- `test_clean_share_url_query_only` — 纯 query URL 处理
- `test_clean_share_url_preserves_scheme` — https scheme 保留
- `test_fetch_video_by_share_url_cleans_dirty_redirect` — 集成回归（mock CapturingClient）

### 2.2 集成测试

| 测试文件 | 用例数 | 通过 | 失败 | 状态 |
|---------|-------|------|------|------|
| `tests/integration/routers/test_admin_kols.py`（新建）| 7 | 7 | 0 | ✅ |
| `tests/integration/routers/test_operator_persona_writer.py` | 全部 | 全部 | 0 | ✅ |
| `tests/integration/routers/test_operator_qianchuan_writer.py` | 全部 | 全部 | 0 | ✅ |
| `tests/integration/routers/test_livestream_writer.py` | 全部 | 全部 | 0 | ✅ |
| `tests/integration/routers/test_operator_tiktok_writer.py` | 全部 | 全部 | 0 | ✅ |

**test_admin_kols.py 新建 7 用例**：
- `test_create_success` — 基础新建成功
- `test_create_does_not_overwrite_existing` — INSERT 不覆盖已有红人（核心回归）
- `test_duplicate_douyin_id_returns_409` — 重复 douyin_id 返回 `RESOURCE_ALREADY_EXISTS`
- `test_duplicate_sec_uid_returns_409` — 重复 sec_uid 返回 `RESOURCE_ALREADY_EXISTS`
- `test_duplicate_after_soft_delete_succeeds` — 软删后可重建（部分唯一索引允许）
- `test_create_multiple_without_douyin_id_succeeds` — 空值可多条（不触发唯一约束）
- `test_create_requires_admin` — 鉴权（operator 403）

### 2.3 回归测试

| 测试范围 | 用例数 | 通过 | 失败 | 状态 |
|---------|-------|------|------|------|
| `test_admin_users.py` + `test_admin_tikhub.py` + `test_admin_oss.py` + `test_admin_asr.py` | 51 | 51 | 0 | ✅ |
| `test_convention_guard.py`（CLAUDE.md 7 红线）| 6 | 6 | 0 | ✅ |

### 2.4 前端测试

本次前端改动以 UI 微调为主（移除描述 div、加 TextArea、加 initialValue），未引入新交互逻辑。全量 `vitest run` 通过，`tsc --noEmit` exit 0。

## 三、关键测试场景验证

### 3.1 BUG-025 TikHub URL 清洗

**场景**：用户复制抖音 App 分享文本，含短链 `v.douyin.com/Jl9v-FrfwbQ/`
**期望**：解析成功，不再返回 400
**验证**：
- `_resolve_short_url` 返回 iesdouyin.com 长链（带 14 个 tracking 参数）
- `_clean_share_url` 清洗后只剩 scheme+netloc+path
- TikHub 端点接受清洗后 URL，返回正常视频信息

### 3.2 BUG-028 唯一索引 + 重复预检查

**场景**：用户尝试用已存在的 douyin_id 新建红人
**期望**：返回 `RESOURCE_ALREADY_EXISTS`（409），不写入数据库
**验证**：
- 后端预检查命中 → 返回 `success=false, code=RESOURCE_ALREADY_EXISTS, message="抖音号 xxx 已存在"`
- 数据库部分唯一索引兜底（并发竞态时 IntegrityError）

### 3.3 BUG-029 软删后可重建

**场景**：红人 A 软删后，用相同 douyin_id 新建红人 B
**期望**：创建成功（部分唯一索引只约束 `deleted_at IS NULL`）
**验证**：`test_duplicate_after_soft_delete_succeeds` 通过

### 3.4 BUG-027 status 默认值

**场景**：用户新建红人不选状态
**期望**：后端默认 `'signed'`，下拉立即可见
**验证**：
- 前端 Form initialValue="signed"（默认选中"签约中"）
- 后端 ORM default="signed"（兜底）
- 数据修复：现有 'active' → 'signed'

## 四、测试覆盖盲区与风险

### 4.1 数据库唯一索引未在测试库验证

**原因**：测试库用 `Base.metadata.create_all` 建表（CLAUDE.md 红线 #7），不跑 migration，因此测试库的 `kols` 表**没有唯一索引**。
**风险**：DB 层面的兜底（IntegrityError）未被自动化测试覆盖。
**缓解**：
- 后端预检查已覆盖正常场景
- 生产库已通过 migration 032 应用索引（已验证）
- 真实并发竞态发生概率低（admin 创建红人是低频操作）

### 4.2 前端 UI 改动无单测

**原因**：本次仅 3 处 UI 微调（删 div、加 TextArea、加 initialValue），无新交互逻辑。
**风险**：低。回归靠 `vitest` + `tsc` + 人工 E2E。
**缓解**：记录在任务文档 §六，后续若 KolsPage 抽组件或加富文本编辑，补对应单测。

### 4.3 E2E 联调待用户完成

本次测试报告覆盖自动化测试。完整 E2E 联调（用户在浏览器逐项验收）待用户执行，清单见任务 #62。

## 五、测试结论

| 维度 | 结论 |
|------|------|
| 单元测试 | ✅ 30/30 通过（含新增 5） |
| 集成测试 | ✅ 7/7 通过（新建 test_admin_kols） |
| 回归测试 | ✅ 57/57 通过（admin_users + admin_tikhub + admin_oss + admin_asr + convention_guard）|
| 契约同步 | ✅ Base_API / Base_Database / README 全部更新 |
| 覆盖盲区 | ⚠️ 测试库无唯一索引（设计权衡，非缺陷）|
| **整体** | **✅ 通过，可进入 PM 签收** |

## 六、测试命令清单

```bash
# 后端单测 + 集测
cd backend && source .venv311/Scripts/activate
python -m pytest tests/unit/services/test_tikhub_adapter.py -v
python -m pytest tests/integration/routers/test_admin_kols.py -v
python -m pytest tests/integration/test_convention_guard.py -v
python -m pytest tests/integration/routers/test_admin_users.py tests/integration/routers/test_admin_tikhub.py tests/integration/routers/test_admin_oss.py tests/integration/routers/test_admin_asr.py -v

# 前端
cd frontend
npx vitest run
npx tsc --noEmit
```
