"""日报/周报渲染和飞书文档幂等创建更新。"""
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as ca


SHANGHAI = ZoneInfo("Asia/Shanghai")
END = datetime(2026, 9, 5, tzinfo=SHANGHAI)


def envelope(*, weekly=False, finalize=False, test=False):
    return ca.ContentAnalysisTaskEnvelope(
        task_id=1,
        task_no="CA-1",
        task_code=ca.TaskCode.WEEKLY if weekly else ca.TaskCode.DAILY,
        run_type=ca.RunType.TEST if test else ca.RunType.AUTO,
        business_date=date(2026, 9, 4),
        window_start=datetime(2026, 8, 6, tzinfo=SHANGHAI) if weekly else datetime(2026, 9, 2, tzinfo=SHANGHAI),
        window_end=END,
        triggered_at=END,
        deadline_at=datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
        retry_of_task_id=None,
        trigger_source=ca.TriggerSource.SYSTEM,
        precheck=ca.DatabasePrecheck(ca.DatabasePrecheckStatus.READY),
        delivery_target=ca.DeliveryTarget(
            "root",
            "测试报告" if test else "content-analysis",
            scope=ca.DeliveryScope.TEST if test else ca.DeliveryScope.FORMAL,
        ),
        idempotency=ca.IdempotencyKeys("analysis", "result", "weekly-doc" if weekly else "daily-doc"),
        execution=(
            ca.WeeklyBatchFinalizeExecution(
                "week-1",
                2,
                ("1001", "1002"),
                "state-v1",
            )
            if finalize
            else
            ca.AccountExecution("account-001", ("1001", "1002"), "week-1", 2, 1)
            if weekly
            else ca.ProjectExecution("1001")
        ),
    )


class Gateway:
    def __init__(self):
        self.calls = []

    async def create_document(self, *, root_ref, relative_directory, document_key, title, section_key, markdown):
        self.calls.append(("create", root_ref, relative_directory, document_key, title, section_key, markdown))
        return ca.DeliveryIdentity(document_key, "doc-1", "https://feishu.cn/docx/doc-1")

    async def update_document(self, *, document_id, document_key, title, section_key, markdown):
        self.calls.append(("update", document_id, document_key, title, section_key, markdown))
        return ca.DeliveryIdentity(document_key, document_id, f"https://feishu.cn/docx/{document_id}")


@pytest.mark.asyncio
async def test_empty_daily_render_is_explicit_and_created_once() -> None:
    gateway = Gateway()
    delivery = ca.FeishuReportDelivery(gateway)
    payload = {
        "reports": {
            "1001": {
                "summary": "飞书读取成功；发布内容 0 条，人设机会 0 条，千川机会 0 条，内容库新增 0 条，跨项目机会新增 0 条",
                "daily_overview": {"content_count": 0},
                "persona_opportunities": [],
                "qianchuan_opportunities": [],
                "library_candidates": [],
                "cross_project_candidates": [],
                "sync_results": [{"account_id": "account-001", "status": "success_without_content"}],
                "no_content_summary": {
                    "read_succeeded": True,
                    "checked_account_ids": ["account-001"],
                    "coverage_window": {"start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00"},
                    "read_completed_at": "2026-09-05T00:00:00+08:00",
                },
            }
        }
    }

    identity = await delivery.deliver(envelope(), 77, payload, None)

    assert identity.document_id == "doc-1"
    call = gateway.calls[0]
    assert call[0] == "create"
    assert call[5] == "project:1001"
    assert all(text in call[6] for text in ("飞书读取成功", "发布内容：0", "人设机会：0", "内容库新增：0", "跨项目机会新增：0", "account-001"))


@pytest.mark.asyncio
async def test_weekly_account_updates_existing_shared_document_section() -> None:
    gateway = Gateway()
    delivery = ca.FeishuReportDelivery(gateway)
    env = envelope(weekly=True)
    existing = ca.DeliveryIdentity(env.idempotency.document_key, "doc-existing", "https://example.invalid/doc-existing")

    identity = await delivery.deliver(
        env,
        88,
        {
            "sec_uid": "account-001",
            "project_ids": ["1001", "1002"],
            "weekly_batch_id": "week-1",
            "batch_size": 2,
            "batch_position": 1,
            "content_count": 3,
            "analysis_failure_count": 0,
            "baseline": {"baseline": {"mean": 12.0, "median": 10.0, "sample_size": 3, "maximum": 20, "minimum": 6}},
            "limitations": [],
        },
        existing,
    )

    assert identity.document_id == "doc-existing"
    (account_call,) = gateway.calls
    assert account_call[0] == "update"
    assert account_call[4] == "account:account-001"
    assert "批次位置：1/2" in account_call[5]
    assert "关联项目：1001、1002" in account_call[5]
    assert "平均点赞：12.0" in account_call[5]
    assert "公司级周批汇总" not in account_call[5]


@pytest.mark.asyncio
async def test_weekly_report_uses_runtime_matched_projects_not_stale_envelope_scope() -> None:
    gateway = Gateway()
    delivery = ca.FeishuReportDelivery(gateway)
    env = envelope(weekly=True)

    await delivery.deliver(
        env,
        88,
        {
            "sec_uid": "account-001",
            "project_ids": ["1001"],
            "weekly_batch_id": "week-1",
            "batch_size": 2,
            "batch_position": 1,
            "content_count": 0,
            "analysis_failure_count": 0,
            "baseline": None,
            "limitations": [],
        },
        None,
    )

    account_markdown = gateway.calls[0][6]
    assert "关联项目：1001" in account_markdown
    assert "1002" not in account_markdown


@pytest.mark.asyncio
async def test_weekly_partial_update_exposes_identity_for_delivery_only_retry() -> None:
    class PartialGateway(Gateway):
        async def update_document(self, **kwargs):
            if kwargs["section_key"].startswith("account:"):
                raise RuntimeError("private partial write failure")
            return await super().update_document(**kwargs)

    env = envelope(weekly=True)
    existing = ca.DeliveryIdentity(
        env.idempotency.document_key,
        "doc-existing",
        "https://feishu.cn/docx/doc-existing",
    )
    payload = {
        "sec_uid": "account-001",
        "project_ids": ["1001", "1002"],
        "weekly_batch_id": "week-1",
        "batch_size": 2,
        "batch_position": 1,
        "content_count": 0,
        "analysis_failure_count": 0,
        "baseline": None,
        "limitations": [],
    }

    with pytest.raises(RuntimeError) as captured:
        await ca.FeishuReportDelivery(PartialGateway()).deliver(
            env,
            88,
            payload,
            existing,
        )

    assert captured.value.delivery_identity == existing


@pytest.mark.asyncio
async def test_weekly_batch_finalize_updates_only_terminal_company_summary() -> None:
    gateway = Gateway()
    env = envelope(weekly=True, finalize=True)
    existing = ca.DeliveryIdentity(
        env.idempotency.document_key,
        "doc-existing",
        "https://feishu.cn/docx/doc-existing",
    )
    payload = {
        "batch_summary": {
            "weekly_batch_id": "week-1",
            "selected_project_ids": ["1001", "1002"],
            "account_count": 2,
            "success_account_count": 0,
            "no_content_account_count": 0,
            "failed_account_count": 2,
            "pending_account_count": 0,
            "calculable_account_count": 0,
            "unavailable_reason": "本批次没有可计算账号",
            "failures": [
                {
                    "account_hash": "sha256:failed-account-hash",
                    "reason_code": "FEISHU_CONTENT_READ_FAILED",
                    "public_message": "账号周任务执行失败",
                }
            ],
            "account_results": [
                {
                    "account_hash": "sha256:failed-account-hash",
                    "status": "failed",
                    "project_ids": ["1001"],
                    "sample_count": None,
                    "mean_likes": None,
                    "median_likes": None,
                    "maximum_likes": None,
                    "minimum_likes": None,
                    "baseline_updated_at": None,
                    "unavailable_reason": "账号周任务执行失败",
                    "updated_at": "2026-09-05T01:00:00+08:00",
                }
            ],
        },
        "run_metadata": {
            "window_start": "2026-08-06T00:00:00+08:00",
            "window_end": "2026-09-05T00:00:00+08:00",
            "generated_at": "2026-09-05T02:00:00+08:00",
        },
    }

    identity = await ca.FeishuReportDelivery(gateway).deliver(
        env,
        99,
        payload,
        existing,
    )

    assert identity.document_id == "doc-existing"
    (call,) = gateway.calls
    assert call[0] == "update"
    assert call[4] == "batch-summary"
    assert all(
        text in call[5]
        for text in (
            "待处理账号：0",
            "可计算账号：0",
            "失败账号：2",
            "本批次没有可计算账号",
            "2026-08-06T00:00:00+08:00",
            "2026-09-05T00:00:00+08:00",
            "sha256:failed-account-hash",
            "样本数：不可计算",
            "2026-09-05T01:00:00+08:00",
        )
    )
    assert "account-a" not in call[5]


@pytest.mark.asyncio
async def test_weekly_batch_finalize_with_zero_accounts_renders_explicit_empty_scope() -> None:
    gateway = Gateway()
    env = replace(
        envelope(weekly=True, finalize=True),
        execution=ca.WeeklyBatchFinalizeExecution(
            "week-empty",
            0,
            ("1001", "1002"),
            "empty-state-v1",
        ),
    )

    await ca.FeishuReportDelivery(gateway).deliver(
        env,
        100,
        {
            "batch_summary": {
                "weekly_batch_id": "week-empty",
                "selected_project_ids": ["1001", "1002"],
                "account_count": 0,
                "success_account_count": 0,
                "no_content_account_count": 0,
                "failed_account_count": 0,
                "pending_account_count": 0,
                "calculable_account_count": 0,
                "failures": [],
                "account_results": [],
                "unavailable_reason": "本批次没有账号实例",
            },
            "run_metadata": {
                "window_start": "2026-08-06T00:00:00+08:00",
                "window_end": "2026-09-05T00:00:00+08:00",
                "generated_at": "2026-09-05T02:00:00+08:00",
            },
        },
        None,
    )

    markdown = gateway.calls[0][6]
    assert all(
        text in markdown
        for text in (
            "纳入项目：1001、1002",
            "去重账号：0",
            "成功账号：0",
            "无内容账号：0",
            "失败账号：0",
            "待处理账号：0",
            "可计算账号：0",
            "本批次没有账号实例",
        )
    )


@pytest.mark.asyncio
async def test_weekly_batch_finalize_renders_each_account_baseline_metrics() -> None:
    gateway = Gateway()
    env = envelope(weekly=True, finalize=True)

    await ca.FeishuReportDelivery(gateway).deliver(
        env,
        101,
        {
            "batch_summary": {
                "weekly_batch_id": "week-1",
                "selected_project_ids": ["1001", "1002"],
                "account_count": 2,
                "success_account_count": 2,
                "no_content_account_count": 0,
                "failed_account_count": 0,
                "pending_account_count": 0,
                "calculable_account_count": 1,
                "failures": [],
                "unavailable_reason": None,
                "account_results": [
                    {
                        "sec_uid": "account-available",
                        "status": "success",
                        "project_ids": ["1001", "1002"],
                        "sample_count": 3,
                        "mean_likes": 12.0,
                        "median_likes": 10.0,
                        "maximum_likes": 20,
                        "minimum_likes": 6,
                        "baseline_updated_at": "2026-09-05T04:00:00+08:00",
                        "unavailable_reason": None,
                        "updated_at": "2026-09-05T04:10:00+08:00",
                    },
                    {
                        "sec_uid": "account-unavailable",
                        "status": "success",
                        "project_ids": ["1001"],
                        "sample_count": 0,
                        "mean_likes": None,
                        "median_likes": None,
                        "maximum_likes": None,
                        "minimum_likes": None,
                        "baseline_updated_at": "2026-09-05T04:00:00+08:00",
                        "unavailable_reason": "窗口内没有可计算的人设点赞样本",
                        "updated_at": "2026-09-05T04:10:00+08:00",
                    },
                ],
            },
            "run_metadata": {
                "window_start": "2026-08-06T00:00:00+08:00",
                "window_end": "2026-09-05T00:00:00+08:00",
                "generated_at": "2026-09-05T05:00:00+08:00",
            },
        },
        None,
    )

    markdown = gateway.calls[0][6]
    assert all(
        text in markdown
        for text in (
            "可计算账号：1",
            "账号 account-available",
            "状态：成功",
            "关联项目：1001、1002",
            "样本数：3",
            "平均点赞：12.0",
            "中位点赞：10.0",
            "最高点赞：20",
            "最低点赞：6",
            "基准更新时间：2026-09-05T04:00:00+08:00",
            "账号 account-unavailable",
            "样本数：不可计算",
            "窗口内没有可计算的人设点赞样本",
        )
    )


@pytest.mark.asyncio
async def test_weekly_account_renders_window_update_time_and_unavailable_reason() -> None:
    gateway = Gateway()
    await ca.FeishuReportDelivery(gateway).deliver(
        envelope(weekly=True),
        88,
        {
            "sec_uid": "account-001",
            "project_ids": ["1001"],
            "weekly_batch_id": "week-1",
            "batch_size": 2,
            "batch_position": 1,
            "content_count": 0,
            "analysis_failure_count": 0,
            "baseline": {
                "baseline": None,
                "window_start": "2026-08-06T00:00:00+08:00",
                "window_end": "2026-09-05T00:00:00+08:00",
                "updated_at": "2026-09-05T01:00:00+08:00",
                "unavailable_reason": "窗口内没有可计算的人设点赞样本",
            },
            "limitations": [],
        },
        None,
    )

    markdown = gateway.calls[0][6]
    assert "统计窗口：2026-08-06T00:00:00+08:00 至 2026-09-05T00:00:00+08:00" in markdown
    assert "更新时间：2026-09-05T01:00:00+08:00" in markdown
    assert "不可计算原因：窗口内没有可计算的人设点赞样本" in markdown


@pytest.mark.asyncio
@pytest.mark.parametrize("weekly", (False, True))
async def test_test_report_is_visibly_marked_as_non_effective(weekly) -> None:
    gateway = Gateway()
    delivery = ca.FeishuReportDelivery(gateway)
    env = envelope(weekly=weekly, test=True)
    payload = (
        {
            "sec_uid": "account-001",
            "project_ids": ["1001", "1002"],
            "weekly_batch_id": "week-1",
            "batch_size": 2,
            "batch_position": 1,
            "content_count": 0,
            "analysis_failure_count": 0,
            "baseline": None,
            "limitations": [],
        }
        if weekly
        else {
            "reports": {
                "1001": {
                    "summary": "测试摘要",
                    "daily_overview": {"content_count": 0},
                    "sync_results": [],
                }
            }
        }
    )

    await delivery.deliver(env, 1, payload, None)

    call = gateway.calls[0]
    assert call[4].startswith("【测试】")
    assert "【测试结果，不生效】" in call[6]


@pytest.mark.asyncio
async def test_delivery_rejects_wrong_document_identity_or_test_directory() -> None:
    delivery = ca.FeishuReportDelivery(Gateway())
    with pytest.raises(ValueError, match="document_key"):
        await delivery.deliver(
            envelope(),
            1,
            {"reports": {"1001": {}}},
            ca.DeliveryIdentity("other", "doc", None),
        )
    with pytest.raises(ValueError, match="测试运行必须投递测试目录"):
        bad = replace(
            envelope(test=True),
            delivery_target=ca.DeliveryTarget("root", "正式目录"),
        )
        await delivery.deliver(bad, 1, {"reports": {"1001": {}}}, None)


@pytest.mark.asyncio
async def test_daily_renders_existing_library_state_and_operations_review_fallback() -> None:
    gateway = Gateway()
    item = {
        "stable_key": "platform_content_id:work-1",
        "in_library": True,
        "analysis": {
            "content": {
                "identity": {"platform_content_id": "work-1", "external_url": None},
                "operations_review_url": "https://internal.invalid/review/work-1",
                "published_at": "2026-09-04T08:00:00+08:00",
                "captured_at": "2026-09-05T00:00:00+08:00",
                "metrics": {
                    "like_count": 10,
                    "comment_count": 1,
                    "share_count": 1,
                    "favorite_count": 1,
                },
                "title": "匿名标题",
            },
            "category": "persona",
            "confidence": "medium",
            "opening": {"status": "unavailable", "unavailable_reason": "无"},
            "source_information": {
                "facts": [{"statement": "来源商品声称有匿名功效"}],
                "judgments": [{"statement": "表达顺序较清楚"}],
                "assumptions": [{"statement": "假设字幕没有漏字"}],
                "limitations": [{"statement": "没有商品证明材料"}],
                "source_constraints": [{"statement": "不得当作当前项目事实"}],
            },
            "topic": "匿名选题",
        },
        "assessment": {
            "fit_reasons": [],
            "confidence": "medium",
            "conclusion": "适配",
        },
    }
    await ca.FeishuReportDelivery(gateway).deliver(
        envelope(),
        1,
        {
            "reports": {
                "1001": {
                    "summary": "日报",
                    "daily_overview": {"content_count": 1},
                    "persona_opportunities": [item],
                    "qianchuan_opportunities": [],
                    "library_candidates": [],
                    "cross_project_candidates": [],
                    "sync_results": [],
                }
            }
        },
        None,
    )

    markdown = gateway.calls[0][6]
    assert "项目内容库入库状态：已入库或本次入库" in markdown
    assert "https://internal.invalid/review/work-1" in markdown
    assert "来源事实：来源商品声称有匿名功效" in markdown
    assert "来源判断：表达顺序较清楚" in markdown
    assert "来源假设：假设字幕没有漏字" in markdown
    assert "来源限制：没有商品证明材料" in markdown
    assert "来源适用边界：不得当作当前项目事实" in markdown
