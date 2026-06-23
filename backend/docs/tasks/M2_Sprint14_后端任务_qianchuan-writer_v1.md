# M2 Sprint 14 — 后端任务：千川文案写作（qianchuan-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_Sprint14_qianchuan-writer_需求文档.md`
> 对应分支：`migrate/qianchuan-writer`

---

## 一、范围（本次后端任务）

涵盖千川文案写作工具迁移的所有后端工作：
- Migration 030（qianchuan_writer_configs 表 + workspace_tools 注册 + 种子 Prompt）
- ORM 模型 QianchuanWriterConfig + 注册 __init__.py
- Prompt 渲染 service（独立模块，便于单测）
- operator_qianchuan_writer.py 6 个接口（kols/personas、parse-file、chat 流式、save-output、export-word、outputs）
- admin_qianchuan_writer.py 2 个接口（configs GET/PUT）
- main.py + conftest.py 注册
- 单测 8 + operator 集测 20 + admin 集测 9 全绿
- 全量回归通过（805 passed，2 failed 为预存 snappy 问题，非本次引入）

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | Migration 030（建表 + 种子 Prompt + workspace_tools）| `backend/migrations/030_qianchuan_writer.sql` | ✅ |
| B2 | ORM 模型 QianchuanWriterConfig | `backend/app/models/qianchuan_writer.py` | ✅ |
| B3 | 注册到 `models/__init__.py` | `backend/app/models/__init__.py` | ✅ |
| B4 | Prompt 渲染 service | `backend/app/services/qianchuan_writer_prompt.py` | ✅ |
| B5 | operator router 6 接口 | `backend/app/routers/operator_qianchuan_writer.py` | ✅ |
| B6 | admin router 2 接口 | `backend/app/routers/admin_qianchuan_writer.py` | ✅ |
| B7 | main.py 注册两个 router | `backend/app/main.py` | ✅ |
| B8 | conftest.py 加 AsyncSessionLocal patch | `backend/tests/conftest.py` | ✅ |
| B9 | 单元测试 8 用例 | `backend/tests/unit/services/test_qianchuan_writer_prompt.py` | ✅ |
| B10 | operator 集成测试 20 用例 | `backend/tests/integration/routers/test_operator_qianchuan_writer.py` | ✅ |
| B11 | admin 集成测试 9 用例 | `backend/tests/integration/routers/test_admin_qianchuan_writer.py` | ✅ |

## 三、API 设计

### 3.1 运营端接口（operator_qianchuan_writer.py）

| 接口 | 用途 |
|------|------|
| GET `/api/tools/qianchuan-writer/kols/personas` | Step 1 达人下拉（JOIN users 拿 creator_name）|
| POST `/api/tools/qianchuan-writer/parse-file` | Step 2 产品卖点卡文件解析（FormData，复用 file_parser.py）|
| POST `/api/tools/qianchuan-writer/chat` | Step 4 流式生成（yunwu adapter SSE）|
| POST `/api/tools/qianchuan-writer/save-output` | 保存到 outputs 表 + OperationLog |
| POST `/api/tools/qianchuan-writer/export-word` | 导出 .docx（StreamingResponse，不包信封）|
| GET `/api/tools/qianchuan-writer/outputs` | 历史记录（账号隔离 WHERE created_by=current_user.id）|

### 3.2 管理端接口（admin_qianchuan_writer.py）

| 接口 | 用途 |
|------|------|
| GET `/api/admin/qianchuan-writer/configs` | 读配置（通常 1 条 config_key='default'）|
| PUT `/api/admin/qianchuan-writer/configs/{config_key}` | 更新 system_prompt + ai_model_id + is_active |

### 3.3 chat 接口关键流程

```
1. 读 DB qianchuan_writer_configs WHERE config_key='default' AND is_active=true
2. 读 kols WHERE id=persona_id（persona + content_plan + name）
3. render_system_prompt(template, name, persona, content_plan)  ← 占位符替换
4. yunwu_adapter.chat_stream(messages, db, model_id, feature='qianchuan_writer_chat', user_id=current_user.id)
5. StreamingResponse media_type='text/plain'
6. BackgroundTask: 写 OperationLog（action='qianchuan_writer_chat'）
7. adapter finally 自动写 ai_call_logs
```

## 四、测试覆盖

### 4.1 单元测试（test_qianchuan_writer_prompt.py，8 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 占位符替换 | 4 | `{{name}}`/`{{soul}}`/`{{content_plan}}` 单独+组合替换 |
| 缺失 fallback | 2 | persona/content_plan 为空时不崩溃 |
| 多次出现 | 1 | 同一占位符多次出现全部替换 |
| 真实模板 | 1 | DB 种子 Prompt 实际渲染验证 |

### 4.2 operator 集成测试（test_operator_qianchuan_writer.py，20 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | 无 token / operator OK / admin OK / invalid token |
| personas | 3 | 空列表 / 有数据 / 含 creator_name 标签 |
| parse-file | 3 | 成功 / 不支持格式 / 空 file |
| chat | 4 | 成功 / AI 失败 / 缺 persona_id / 验 OperationLog 写入 |
| save-output | 3 | 成功 / 账号绑定校验 / 关联 task_id |
| export-word | 2 | 成功返回 docx / 文件名 URL 编码 |
| outputs | 2 | 分页 / 账号隔离（A 查不到 B 的）|

### 4.3 admin 集成测试（test_admin_qianchuan_writer.py，9 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | admin OK / operator forbidden / invalid / unauthenticated |
| GET configs | 1 | 返回种子配置 |
| PUT configs | 4 | 更新 Prompt / 更新 ai_model_id / 写 OperationLog / config_key 不存在 |

## 五、关键约定

- **Prompt 模板化**：DB 存 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符，后端 `render_system_prompt()` 渲染
- **正则一次性替换**：`re.compile(r"\{\{\s*(name|soul|content_plan)\s*\}\}")` 避免 soul 内容含 `{{name}}` 文本时二次替换
- **chat / save-output / export-word 三接口分离**：流式 / 写库 / 生成文件流各司其职，前端两按钮独立调用
- **outputs 账号隔离**：查询 `WHERE created_by=current_user.id AND deleted_at IS NULL`
- **export-word 例外**：返回 StreamingResponse，不走标准信封（红线 #1 例外）
- **workspace_tools 初始 status='dev'**：测试通过后管理端改 online
- **adapter 零改动**：yunwu/tikhub/oss/asr 四个 adapter 不碰
- **冻结区零触碰**：`app/core/`、`app/middlewares/` 不改

## 六、全量回归结果

- 单元测试：8/8 ✅
- 集成测试：29/29 ✅（operator 20 + admin 9）
- convention_guard：6/6 ✅（红线守卫全过）
- 全量 pytest：**805 passed / 2 failed / 1 skipped**
  - 2 failed 是 `test_livestream_writer_file_parser` 的 `.pages` 解析（`ModuleNotFoundError: No module named 'snappy'`），已 git stash 验证为基线预存问题，与本次改动无关

## 七、种子 Prompt 模板原文（DB 存储版本）

```
你是一个千川脚本仿写专家。任务：把原版脚本改写成「{{name}}」视角的仿写版本。

## {{name}} 人物档案
{{soul}}

## {{name}} 内容规划参考
{{content_plan}}

## 仿写铁律（必须严格执行）
1. 结构完全不变：句式结构、段落顺序、整体框架100%保留
2. 字数只能相同或更少，绝对不能更多
3. 开头99%原封不动：只有当原版开头出现的人物/产品与{{name}}身份直接冲突时，才最多换一两个字，其他情况一字不改
4. 产品全部替换：把原版中所有产品信息、卖点，替换成用户提供的「{{name}}产品卖点」里对应的卖点，只从用户给定的卖点中取，不自己编造、不添加
5. 人物视角换成{{name}}：原版里的其他网红/人物换成{{name}}本人的第一人称视角，结合人物档案中的真实经历做替换

直接输出仿写后的完整脚本，不要解释，不要加任何注释或标注。
```

**改造说明**：
- `${name}` → `{{name}}`（kols.name）
- `${selectedPersona.soul}` → `{{soul}}`（kols.persona 全文）
- 新增 `{{content_plan}}` 占位符（kols.content_plan）
- 原 `${product}`（前端传入的产品文本）不入 system_prompt，由前端组装到 messages 中
