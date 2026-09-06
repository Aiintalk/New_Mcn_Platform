# M2 Sprint27 后端开发验收：内容分析 Agent 飞书适配 v2（新增功能）

> 日期：2026-09-04
> 分支：`codex/content-analysis-agent-dev`
> 基线：`5cceb2f8e22cf0fa2ea7279f9e7fc669b590b0f3`
> 产品依据：外部只读需求文档 v1.8
> 结论：开发侧通过，等待主产品经理独立验收；不准入生产。

## 一、验收结论

已完成可注入的飞书只读内容适配、完整分页合同、字段映射、逐账号有/无内容派生、请求超时与失败隔离、标题与纯文本合同收敛，以及可追溯无内容日报。最终返修保证空日报不混入全局既有跨项目候选，并将自动入库项目适配门槛收敛为“至少一条合法理由”。内容分析专项 391/391 通过，专项覆盖率 91%；正式覆盖率门禁 2404 通过、1 跳过、0 失败，整体 80.5%，六层全部通过。

本结论不包含真实飞书鉴权/读取冒烟、任务配置最终联调、公共接口、数据库/迁移、调度、持久化、下游读取、真实项目或真实模型验收。

## 二、v1.8 条款—代码—测试覆盖矩阵

| v1.8 验收项 | 代码证据 | 测试证据 | 状态 |
|---|---|---|---|
| 多页完整读取与正常结束 | `feishu_adapter.py` 的 `_read_pages` | `test_feishu_reader_reads_all_pages_and_derives_per_account_results` | 已覆盖 |
| 部分账号有内容、部分账号零内容 | `FeishuContentReader._successful_results` | 同上 | 已覆盖 |
| 全部账号零内容并生成完整日报 | `NoContentDailySummary`、`ContentAnalysisEngine.run` | `test_complete_feishu_read_with_all_accounts_empty_has_atomic_empty_receipt`、`test_complete_empty_feishu_read_flows_through_engine_as_empty_daily` | 已覆盖 |
| 鉴权失败 | `_validate_source` | `test_feishu_reader_returns_explicit_failure_without_empty_status` | 已覆盖（模拟） |
| 必需字段、类型、空值、时间和数值 | `_REQUIRED_FIELDS`、`_plain_text`、`_timestamp`、`_metric` | `test_feishu_reader_rejects_invalid_required_identity_time_or_metric` | 已覆盖 |
| 游标中断、某页失败、分页未完成 | `_read_pages` 的游标与总数检查 | `test_feishu_reader_rejects_incomplete_or_inconsistent_pagination`、`test_feishu_reader_rejects_final_page_when_total_proves_incomplete` | 已覆盖 |
| 失败不生成无内容日报 | `FAILED` 派生与日报判定 | `test_failed_feishu_read_never_creates_empty_daily_receipt` | 已覆盖 |
| 飞书无同步状态字段 | `_record` 不读取状态 | `test_feishu_adapter_does_not_expose_visual_or_upstream_status_input` | 已覆盖 |
| 无播放链接仍完成文本分析 | 链接均可选；候选以稳定身份和转写追溯 | `test_text_analysis_and_library_candidate_do_not_require_playback_links` | 已覆盖 |
| 缺字幕保留统计但无法判断 | 引擎确定性缺字幕分支 | `test_missing_transcript_counts_content_but_is_deterministically_undetermined` | 已覆盖 |
| 删除视觉分析能力 | 领域枚举和输出对象删除视觉成员 | `test_feishu_adapter_does_not_expose_visual_or_upstream_status_input` 及专项回归 | 已覆盖 |
| 重复作品取最新采集值 | `deduplicate_contents` | `test_feishu_reader_deduplicates_a_work_using_latest_capture` | 已覆盖 |
| 同账号多项目复用且隔离 | 运行键级基础分析缓存、项目逐项判断 | `test_injected_async_analyzer_reuses_basic_analysis_but_seals_each_project` | 已覆盖 |
| 空日报不混入既有跨项目候选 | 项目日报构造分离全局既有池与本次新增 | `test_empty_daily_does_not_include_existing_cross_project_candidates` | 已覆盖 |
| 自动入库有一条合法适配理由即可 | `_library_candidate` 非空理由门槛 | `test_library_candidate_allows_one_valid_project_fit_dimension`、`test_library_candidate_requires_every_common_hard_gate[fit-reason]` | 已覆盖 |
| 时间窗口、分类、基准、候选、日报与跨项目回归 | 阶段一离线内核 | 内容分析专项全部 391 条 | 已覆盖 |

## 三、字段映射与状态推导

| 飞书字段 | 内部语义 |
|---|---|
| `SecUid` | 稳定账号编号 |
| `视频ID` | 稳定作品编号 |
| `视频标题` | 标题 |
| `字幕全文` | 转写，可空 |
| `发布时间` | 转为 `Asia/Shanghai` 的发布时间 |
| `同步时间` | 转为 `Asia/Shanghai` 的最新采集时间 |
| `点赞`、`评论`、`分享`、`收藏` | 四项当前互动；空值保留为空 |
| `播放链接` | 可选外部来源链接 |
| `内网播放` | 可选运营回看链接 |

播放量、视频类型和同步类型均被忽略。只有鉴权、字段清单、所有记录页和结束条件完整成功后，才按显式账号与窗口聚合：有记录为 `SUCCESS_WITH_CONTENT`，零记录为 `SUCCESS_WITHOUT_CONTENT`；所有异常均为 `FAILED`。

## 四、质量、安全与范围自审

- 错误输出只保留固定、可说明的失败类型，不泄露客户端异常、凭据、记录内容或本地路径。
- 客户端协议只有鉴权验证、字段读取和记录只读分页，不提供写入方法。
- 测试数据均为最小匿名合成内容；未下载或提交真实飞书整表、真实账号、项目、长转写或内网地址。
- 未新增依赖；未修改公共 API、数据库表、迁移、路由、前端或外部 PM 文档。
- 未发现仓库内可安全复用的真实飞书只读配置，真实冒烟等待后续联调环境提供“已配置但不暴露值”的客户端实例。
- 当前飞书字段清单不含业务来源平台；`ContentSource.PLATFORM_SYNC` 仅表示采集入口。本轮依作品编号/外部链接追溯，不猜测抖音等平台归属。

## 五、尚未覆盖与后续依赖

1. 真实飞书 SDK/HTTP 客户端、只读凭据、网络超时参数和 API 返回形态需在正式联调环境确认。
2. 正式联调还需确认来源平台的稳定常量或字段，才能在不猜测的前提下完成业务平台映射。
3. 任务配置模块需交付已勾选且必要配置通过的项目任务、账号集合、项目上下文和分析窗口；内容分析不自行选择项目。
4. 数据库落库、调度、重试队列、下游仿写读取、真实模型和真实项目验收均不在本切片。
5. 仓库完整 `tests/` 仍被既有 `tests/intake/conftest.py` 的非顶层 `pytest_plugins` 声明阻断；本轮未越界修改公共测试基础设施。

## 六、版本与发布状态

当前所有 v1.8 返修改动保持未暂存、未提交；未推送、未建合并请求、未合并、未部署、未发布，也未产生付费调用或生产操作。
