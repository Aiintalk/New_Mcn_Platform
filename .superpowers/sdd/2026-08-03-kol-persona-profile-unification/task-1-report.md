# Task 1：正式达人身份关联与权限隔离报告

## 范围

- 三张历史表新增可空 `kol_id`，引用 `kols.id`，删除达人时置空。
- 人格定位改为读取正式达人列表，并按当前运营与 `kol_id` 读取最新完成的入驻资料。
- 人格报告、输出记录和操作日志保留同一正式达人编号。
- 入驻分享链接与运营直发会话可选绑定正式达人，拒绝不存在或已删除的达人。

未修改前端、Task 2、README、PM 状态；未执行生产迁移、部署或推送。

## RED（实现前）

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/unit/models/test_models.py tests/integration/test_persona_profile_migration.py -q
```

完整结果：`4 failed, 52 passed in 1.96s`。

失败符合预期：三个 ORM 模型都缺少 `kol_id`，`055_kol_persona_profile_unification.sql` 不存在。

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/integration/routers/test_persona_identity_binding.py tests/integration/routers/test_intake_kol_binding.py -q
```

完整结果：`6 failed, 1 passed in 4.81s`。

失败符合预期：正式达人列表不存在；入驻会话、分享链接和人格报告无法保存 `kol_id`；生成链路未保留正式达人编号；无效达人仍能创建入驻记录。

## GREEN（最小实现后）

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/unit/models/test_models.py tests/integration/test_persona_profile_migration.py -q --no-cov
```

完整结果：`56 passed in 0.10s`。

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/integration/routers/test_persona_identity_binding.py tests/integration/routers/test_intake_kol_binding.py -q --no-cov
```

完整结果：`8 passed in 3.24s`。

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/integration/routers/test_persona.py -q --no-cov
```

完整结果：`25 passed in 5.77s`。

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/integration/test_convention_guard.py -q --no-cov
```

完整结果：`6 passed in 1.62s`。

另已通过 `git diff --check` 与受影响 Python 文件的 `compileall` 语法检查。

## 改动摘要

1. 新增幂等、非破坏的 055 迁移：重复执行安全，旧行保持 `NULL`，三张表都有 `ON DELETE SET NULL` 外键和索引。
2. 新增正式达人分页/搜索接口和按运营隔离的入驻资料接口；两类入驻资料在内存中合并，只返回最新完成记录，不暴露会话编号。
3. 人格生成强制接收有效的正式达人编号，并将编号写入报告、`outputs.content_json`、操作日志和报告详情。
4. 入驻链接与直发会话创建可选接收正式达人编号，并校验达人未删除。

## 风险与后续边界

- 055 仅在隔离测试 schema 内重复执行验证，尚未在生产数据库执行；生产迁移、部署和发布仍需 PM 授权。
- 历史未绑定记录保持 `NULL`，不会按姓名自动关联；因此它们不会出现在人格定位的可导入资料中，符合本期防串用边界。
- 正式档案字段自动写入、覆盖决策和五项事实提取属于后续 Task 2，不在本任务改动范围内。
