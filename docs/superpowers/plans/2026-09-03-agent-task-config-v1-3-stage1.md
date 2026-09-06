# 智能体任务配置 V1.3 阶段一实施计划

> **Spec：** `/Users/zhangchong/Desktop/codex_workspace/aiintalk_pm/docs/New_Mcn_Platform_Agents/智能体任务配置模块/智能体任务配置页面_完整需求.md`
>
> **Prototype：** `/Users/zhangchong/Desktop/codex_workspace/aiintalk_pm/docs/New_Mcn_Platform_Agents/智能体任务配置模块/智能体任务配置页面_前台设计.html`

**Goal：** 在现有管理端内交付仅管理员使用的内容分析任务配置与受控运行监控，复用 `TaskJob`、`TaskLog`、权限和请求层，不接真实智能体或生产调度。

**Architecture：** 新增 `agent_task_configs` 保存按 `agent_code` 隔离的持续项目范围；服务层统一计算入驻、必要配置、输入上下文、窗口、超时与重试；管理端路由只编排标准信封和操作日志；前端新增单页并保持现有任务页兼容 `not_run`。

**Tech Stack：** FastAPI、SQLAlchemy async、PostgreSQL JSONB、pytest；React 19、TypeScript、Ant Design、Vitest。

## Global Constraints

- 基线固定为 `36702cc965963e445e13e61e2c33e42cd3474132`，分支固定为 `feature/agent-task-config-v1-3-stage1`。
- 阶段一只显示 `content-analysis`，页面只含“任务与输入”“运行监控”。
- 项目池只含未软删且 `persona`、`content_plan` 均非空的项目；不得改变全局入驻规则。
- 阶段一仅管理员可访问路由与接口，operator 无项目级只读权限。
- `not_run` 独立于 `failed`、`cancelled`；只有 `failed` 可手动重试。
- 受控测试不得调用真实 Agent、`kol_scheduler`、外部服务，不得写 `Output`、日报或内容库。
- 阶段一当时仅保留“等待最终联调”的历史占位说明；Sprint28 组合联调已移除该占位，当前生产入口和状态合同不再使用它。
- 手动重试新建任务并继承项目、业务日期与窗口，重置自身 12 小时截止；平台内部重试沿用原任务和原截止。
- 所有 JSON API 走标准信封；前端走 `request.ts`；PUT/POST 写 `OperationLog`。
- 不暂存、不提交、不推送、不建 PR、不合并、不部署，不修改真实业务数据。

## Task 1：数据库与领域服务

**Files：**

- Create: `backend/migrations/058_agent_task_configs.sql`
- Create: `backend/app/models/agent_task_config.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/agent_task_config_service.py`
- Create: `backend/tests/integration/migrations/test_058_agent_task_configs.py`
- Create: `backend/tests/unit/services/test_agent_task_config_service.py`

1. 先写迁移结构、模型注册、项目资格/缺失原因/窗口计算/任务状态与重试测试，运行并确认因实现缺失失败。
2. 最小实现配置模型和纯领域函数：项目池只采用现有入驻口径；内容对标 `sec_uid` 是当前必要配置；其他上下文可缺失但标记输入受限。
3. 实现受控运行：合格项目日志流转 `pending → processing → success`；必要配置缺失直接 `not_run`；始终 `output_id=NULL`。
4. 实现超时收敛与手动重试：超时只处理当前内容分析的 `pending/processing`；重试只接受 `failed` 并新建记录。
5. 运行定向测试并自检没有真实外部调用、没有共享配置范围。

## Task 2：管理员后端接口

**Files：**

- Create: `backend/app/routers/admin_agent_tasks.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/routers/test_admin_agent_tasks.py`
- Modify: `backend/tests/integration/test_convention_guard.py`（仅当守卫需要显式路由登记）

1. 先写 direct-call 与 HTTP 权限测试，覆盖 overview、项目分页/三状态、输入详情、配置整体替换、运行筛选/详情、受控测试、重试、operator 拒绝和标准信封。
2. 运行新测试并记录因路由缺失失败。
3. 最小实现八个管理员接口，所有列表分页；写操作在提交前写 OperationLog，日志不含正文。
4. 监控查询先执行本智能体的 12 小时超时收敛；详情严格按 `agent_code`/`tool_code` 隔离。
5. 运行新路由测试、通用 tasks 路由回归和约定守卫。

## Task 3：前端数据合同与通用任务兼容

**Files：**

- Create: `frontend/src/types/agentTask.ts`
- Create: `frontend/src/api/agentTasks.ts`
- Create: `frontend/src/__tests__/unit/api/agentTasks.test.ts`
- Modify: `frontend/src/types/task.ts`
- Modify: `frontend/src/pages/admin/AdminTasksPage.tsx`
- Modify: `frontend/src/pages/operator/TasksPage.tsx`
- Modify/Create: 上述两页对应的任务状态回归测试

1. 先写请求路径、参数、响应解包与 `not_run` 显示测试，运行并确认失败。
2. 通过 `request.ts` 实现八个 API 调用和严格类型。
3. 在通用任务页新增 `not_run` 标签/筛选兼容，不改变其他五种状态行为。
4. 运行 API 单测和两端现有任务页回归。

## Task 4：管理员页面、路由与视觉样式

**Files：**

- Create: `frontend/src/pages/admin/AgentTaskConfigPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layouts/AdminLayout.tsx`
- Modify: `frontend/src/styles/admin.css`
- Create: `frontend/src/__tests__/components/pages/AgentTaskConfigPage.test.tsx`

1. 先写页面行为测试：只显示内容分析、仅两个页签、三种项目范围状态、保存选择、输入抽屉、筛选监控、详情、失败重试和受控测试。
2. 运行并确认组件/路由缺失的红灯。
3. 最小实现响应式单页，复用 Ant Design 与管理端 token；不显示其他智能体灰色入口。
4. 加入 `/admin/agent-tasks` 懒加载路由和管理员侧栏入口；不改运营端导航。
5. 运行页面、布局、路由及通用任务回归，然后执行 TypeScript 检查和生产构建。

## Task 5：独立评审、视觉验收与交付文档

**Files：**

- Modify: `backend/docs/README.md`
- Modify: `frontend/docs/README.md`
- Modify: `README.md`（仅新增模块/路由说明）
- Create: `backend/docs/tests/M2_智能体任务配置_V1.3阶段一_测试报告.md`

1. 对每个实现任务执行独立需求合规和代码质量评审，修复 Critical/Important 后复审。
2. 启动本地隔离服务，以受控夹具在 1440×900 和 1024×768 验证页面；保存截图证据，不写真实业务数据。
3. 运行后端定向、unit+integration 全量、覆盖率门禁；运行前端定向、全量覆盖率、类型检查、生产构建。
4. 对照正式需求逐项记录证据；既有 PM 状态文件冲突标记只列为文档收尾阻断，不顺手修复。
5. 汇总变更、契约、命令结果、截图、风险与 `git status`，停止等待 PM 验收。
