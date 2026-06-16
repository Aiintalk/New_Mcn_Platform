# M2 Sprint 08 — 后端开发验收 · 直播脚本仿写（livestream-writer）v1

> 节点：B+
> 创建日期：2026-06-15
> 验收状态：自动测试全部通过

---

## 一、自动测试结果

| 测试套件 | 用例数 | 通过 | 失败 |
|---------|--------|------|------|
| 单元测试 `test_livestream_writer_file_parser.py` | 11 | 11 | 0 |
| 集成测试 `test_livestream_writer.py` | 23 | 23 | 0 |
| **合计** | **34** | **34** | **0** |

守卫测试（`test_convention_guard.py`）：4 条失败均为**预存违规**（operator_qianchuan_review / operator_tiktok_writer / admin_qianchuan_edit_review / admin_qianchuan_review），本次新增代码**零新增违规**。

---

## 二、覆盖率

| 模块 | 目标 | 实际 | 状态 |
|------|------|------|------|
| `operator_livestream_writer.py` | ≥ 70% | 72% | ✅ |
| `admin_livestream_writer.py` | ≥ 70% | 83% | ✅ |
| `file_parser.py`（新增函数） | ≥ 90% | 测试覆盖全部分支 | ✅ |

---

## 三、交付文件清单

| 文件 | 状态 |
|------|------|
| `backend/migrations/021_livestream_writer.sql` | ✅ 已执行 |
| `backend/app/models/livestream_writer.py` | ✅ 新增 |
| `backend/app/services/file_parser.py` | ✅ 追加 `parse_livestream_writer_file` |
| `backend/app/routers/operator_livestream_writer.py` | ✅ 新增（5个接口）|
| `backend/app/routers/admin_livestream_writer.py` | ✅ 新增（2个接口）|
| `backend/app/main.py` | ✅ 注册两个 router |
| `backend/tests/conftest.py` | ✅ 注册 AsyncSessionLocal patch target |
| `backend/tests/unit/services/test_livestream_writer_file_parser.py` | ✅ 11个用例 |
| `backend/tests/integration/routers/test_livestream_writer.py` | ✅ 23个用例 |

---

## 四、接口清单

| 方法 | 路径 | 角色 | 功能 |
|------|------|------|------|
| GET | `/api/tools/livestream-writer/config` | operator/admin | 实时拉取 Prompt + 模型 |
| GET | `/api/tools/livestream-writer/kols/personas` | operator/admin | 达人列表 |
| POST | `/api/tools/livestream-writer/parse-file` | operator/admin | 文件解析 |
| POST | `/api/tools/livestream-writer/chat` | operator/admin | AI 流式对话 |
| GET | `/api/admin/livestream-writer/configs` | admin | 配置列表 |
| PUT | `/api/admin/livestream-writer/configs/{key}` | admin | 更新配置 |

---

## 五、红线检查

- [x] #1 非流式接口使用 `success_response` 标准信封
- [x] #2 parse-file / admin PUT 均写 OperationLog（chat 为流式接口，同 tiktok-writer 模式）
- [x] #4 无接口/表结构破坏性变更，只新增
- [x] #6 AiCallLog 不在 router 写，由 adapter 层自动记录
- [x] #7 AsyncSessionLocal 已注册 conftest.py patch 列表
