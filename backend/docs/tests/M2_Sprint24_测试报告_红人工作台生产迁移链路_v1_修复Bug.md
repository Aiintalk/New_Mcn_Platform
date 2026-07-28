# M2 Sprint 24 测试报告：红人工作台生产迁移链路 v1（修复 Bug）

## 结论

代码测试通过，可交 PM 独立验收；未执行生产数据库迁移，不能据此宣称 P0 线上已修复。

## 根因证据

1. `KolReference` ORM 会加载 050 新增的 8 个字段；详情接口查询完整实体，缺列时数据库直接失败。
2. 列表接口只统计旧字段，因此出现“列表 200、所有详情 500”的稳定差异。
3. 旧 `deploy/scripts/init-db.sh` 只执行 001，后续部署说明仅保留“手动执行新迁移”的注释。
4. 050 自身使用 `ADD COLUMN IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS`，可重复执行；真正缺口在部署链路。

## TDD 证据

- RED：后端新增测试最初因 `scripts.run_migrations` 不存在而收集失败；前端新增用例收到旧英文 `Invalid JSON response from server`。
- GREEN：实现账本执行器和中文诊断后对应测试通过。
- 隔离数据库额外证据：完整历史迁移在空 schema 执行到 030 后，031 因历史 seed 假定 `ai_models.id=2/4` 已存在而事务中止。该旧债未在本 P0 中扩范围修改，执行器明确用于既有库安全纳管与后续增量迁移。

## 覆盖场景

- 迁移文件稳定排序，两个同版本文件都保留。
- 已执行文件校验和漂移时拒绝继续。
- 既有库无账本且无显式基线时拒绝执行。
- 已人工执行的单文件可在结构核实后登记，不重放 SQL。
- seed 迁移第二次运行不重复写入。
- 050 前查询新字段稳定报列不存在。
- 050 后旧记录保留，新文档/视频字段可写。
- 050 第二次执行不报错、不改数据。
- 素材库详情、创建、编辑、视频上传/替换/删除和跨红人隔离。
- 前端非 JSON HTTP 500、`request.ts` 原有鉴权/权限/JSON 信封。
- `WorkspaceReferences` 加载、创建、编辑、文档解析、视频限制与播放地址。

## 最终命令与结果

所有命令均在 `feature/kol-workspace-function-optimization` 本地工作树执行，数据库连接为测试库。

| 范围 | 命令 | 结果 |
|---|---|---|
| 迁移执行器、050、素材库定向 | `pytest tests/unit/scripts tests/integration/migrations tests/integration/routers/test_operator_material_library.py -q --no-cov` | 38 passed |
| 前端请求层、素材库与工作台引用 | `npx vitest run src/__tests__/unit/api/request.test.ts src/__tests__/components/pages/WorkspaceReferences.test.tsx src/__tests__/components/pages/MaterialLibraryPage.test.tsx` | 3 files / 34 tests passed |
| 后端单元 + 集成全量 | `pytest tests/unit tests/integration -q --no-cov` | 1423 passed / 1 skipped / 15 warnings |
| 前端全量 | `npx vitest run` | 48 files / 455 tests passed |
| 前端生产构建 | `npm run build` | 成功 |
| 脚本静态检查 | `bash -n deploy/scripts/init-db.sh`、`python -m py_compile backend/scripts/run_migrations.py` | 成功 |
| 部署入口参数检查 | `PYTHON_BIN=backend/.venv/bin/python bash deploy/scripts/init-db.sh --help` | 成功，未连接或修改数据库 |

说明：

- 后端 15 条告警来自既有测试：1 条字符串转义弃用提示、14 条 TikHub 异步模拟对象未等待提示；本轮无失败。
- 前端全量测试仍会输出 jsdom 未实现浏览器布局/跳转能力、React 测试环境与 Router 未来版本提示；全部测试退出码为 0。
- 前端构建保留既有 `credentials.ts` 同时静态/动态导入的分包提示；构建产物成功生成。
