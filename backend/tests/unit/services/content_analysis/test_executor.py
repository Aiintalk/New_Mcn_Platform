"""内容分析执行与只投递重试合同。"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as ca
from app.services.agent_task_execution_contract import build_task_envelope


SHANGHAI = ZoneInfo("Asia/Shanghai")
END = datetime(2026, 9, 5, tzinfo=SHANGHAI)


def envelope(*, weekly=False, run_type=ca.RunType.AUTO, project_ids=("1001", "1002")):
    execution = (
        ca.AccountExecution(
            sec_uid="account-001",
            project_ids=project_ids,
            weekly_batch_id="week-2026-09-05",
            batch_size=1,
            batch_position=1,
        )
        if weekly
        else ca.ProjectExecution("1001")
    )
    return ca.ContentAnalysisTaskEnvelope(
        task_id=1,
        task_no="CA-1",
        task_code=ca.TaskCode.WEEKLY if weekly else ca.TaskCode.DAILY,
        run_type=run_type,
        business_date=date(2026, 9, 4),
        window_start=datetime(2026, 8, 6, tzinfo=SHANGHAI) if weekly else datetime(2026, 9, 2, tzinfo=SHANGHAI),
        window_end=END,
        triggered_at=END,
        deadline_at=datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
        retry_of_task_id=None,
        trigger_source=ca.TriggerSource.SYSTEM,
        precheck=ca.DatabasePrecheck(
            ca.DatabasePrecheckStatus.READY,
            input_limited=True,
            limitation_codes=("TARGET_USERS_MISSING",),
        ),
        delivery_target=ca.DeliveryTarget(
            "root",
            "测试报告" if run_type is ca.RunType.TEST else "content-analysis",
            scope=(
                ca.DeliveryScope.TEST
                if run_type is ca.RunType.TEST
                else ca.DeliveryScope.FORMAL
            ),
        ),
        idempotency=ca.IdempotencyKeys("analysis", "result", "document"),
        execution=execution,
    )


def relation(project_id="1001", sec_uid="account-001"):
    return ca.FeishuRelationRecord(
        relation_id=f"relation-{project_id}-{sec_uid}",
        project_id=project_id,
        sec_uid=sec_uid,
        project_name=None,
        account_name=None,
        source_updated_at=END,
    )


class RelationReader:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def read(self):
        self.calls += 1
        return self.result


class ContentReader:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def read_accounts(self, account_ids, coverage_window):
        self.calls.append((account_ids, coverage_window))
        return self.results


def content(work_id="work-1", *, transcript="匿名转写", likes=10):
    return ca.ContentRecord(
        account_id="account-001",
        source=ca.ContentSource.PLATFORM_SYNC,
        identity=ca.ContentIdentity(platform_content_id=work_id),
        published_at=datetime(2026, 9, 3, 8, tzinfo=SHANGHAI),
        captured_at=datetime(2026, 9, 4, tzinfo=SHANGHAI),
        metrics=ca.EngagementMetrics(like_count=likes, comment_count=1, share_count=1, favorite_count=1),
        title="匿名标题",
        transcript=transcript,
    )


def sync_results(*contents):
    status = ca.SyncStatus.SUCCESS_WITH_CONTENT if contents else ca.SyncStatus.SUCCESS_WITHOUT_CONTENT
    return (
        ca.AccountSyncResult(
            account_id="account-001",
            status=status,
            contents=tuple(contents),
            checked_at=END,
            coverage_window=ca.SyncCoverageWindow(datetime(2026, 9, 2, tzinfo=SHANGHAI), END),
            read_source=ca.ReadSource.FEISHU,
        ),
    )


def failed_sync_results():
    coverage = ca.SyncCoverageWindow(
        datetime(2026, 9, 2, tzinfo=SHANGHAI),
        END,
    )
    return (
        ca.AccountSyncResult(
            account_id="account-001",
            status=ca.SyncStatus.FAILED,
            issue=ca.SyncIssue(
                affected_account_ids=("account-001",),
                affected_window=coverage,
                impact=ca.SyncIssueImpact.CONTENT_UNAVAILABLE,
                reason="飞书读取失败",
            ),
            checked_at=END,
            coverage_window=coverage,
            read_source=ca.ReadSource.FEISHU,
        ),
    )


class ContextReader:
    async def load(self, project_id):
        return ca.ProjectContextLoad(
            context=ca.ProjectContextVersion(
                project_id=project_id,
                version=f"context-{project_id}",
                effective_at=END,
                project_persona="项目人设",
                target_users="",
                content_plan="内容规划",
                operating_direction="",
            ),
            input_limited=True,
            limitation_codes=("TARGET_USERS_MISSING", "OPERATING_DIRECTION_MISSING"),
            project_name="匿名/项目",
        )


class Analyzer:
    def __init__(self):
        self.basic_calls = []
        self.project_calls = []

    async def analyze_content(self, item):
        self.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.PERSONA,
            confidence=ca.ConfidenceLevel.HIGH,
            opening=ca.OpeningAnnotation(status=ca.OpeningTagStatus.UNANNOTATED),
            topic="匿名选题",
            summary="匿名摘要",
        )

    async def assess_project(self, analysis, project_context):
        self.project_calls.append(project_context.project_id)
        return ca.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=False,
            confidence=ca.ConfidenceLevel.HIGH,
            conclusion="不进入候选但保留报告",
        )


class Store:
    def __init__(self):
        self.writes = []
        self.delivery_events = []
        self.payload = None
        self.history = None
        self.history_sequence = []
        self.history_calls = []
        self.library_mutation_lock_calls = 0
        self.persisted = None
        self.system_user_valid = True
        self.pending_manual_openings = ()
        self.pending_manual_opening_sequence = []
        self.weekly_finalize_summary = None
        self.delivery_identity = None
        self.internal_retry_valid = True
        self.internal_retry_validation_calls = []
        self.manual_retry_valid = True
        self.manual_retry_validation_calls = []
        self.manual_finalize_retry_valid = True
        self.manual_finalize_retry_validation_calls = []
        self.finalize_version_current = True
        self.finalize_version_validation_calls = []
        self.finalize_redelivery_valid = True
        self.finalize_redelivery_validation_calls = []
        self.manual_redelivery_valid = True
        self.manual_redelivery_validation_calls = []
        self.load_persisted_result_calls = 0
        self.analysis_guard_calls = []
        self.delivery_guard_calls = []
        self.analysis_guard_error = None

    async def validate_system_user(self, user_id):
        return self.system_user_valid

    async def validate_internal_retry_origin(self, env):
        self.internal_retry_validation_calls.append(env)
        return self.internal_retry_valid

    async def validate_manual_retry_origin(self, env):
        self.manual_retry_validation_calls.append(env)
        return self.manual_retry_valid

    async def validate_manual_finalize_retry_origin(self, env):
        self.manual_finalize_retry_validation_calls.append(env)
        return self.manual_finalize_retry_valid

    async def validate_current_finalize_version(self, env):
        self.finalize_version_validation_calls.append(env)
        return self.finalize_version_current

    async def validate_finalize_redelivery_origin(self, env, result_id):
        self.finalize_redelivery_validation_calls.append((env, result_id))
        return self.finalize_redelivery_valid

    async def validate_manual_redelivery_origin(self, env, result_id):
        self.manual_redelivery_validation_calls.append((env, result_id))
        return self.manual_redelivery_valid

    @asynccontextmanager
    async def analysis_guard(self, env):
        self.analysis_guard_calls.append(env.idempotency.analysis_key)
        if self.analysis_guard_error is not None:
            raise self.analysis_guard_error
        yield

    @asynccontextmanager
    async def delivery_guard(self, env):
        self.delivery_guard_calls.append(env.idempotency.document_key)
        yield

    async def load_pending_manual_openings(self, project_id):
        if self.pending_manual_opening_sequence:
            return self.pending_manual_opening_sequence.pop(0)
        return self.pending_manual_openings

    async def load_weekly_batch_finalize_summary(self, env):
        if self.weekly_finalize_summary is None:
            raise AssertionError("测试必须显式提供周批次终态汇总")
        return self.weekly_finalize_summary

    async def find_persisted_result(self, env):
        return self.persisted

    async def persist(self, env, write, created_by):
        self.writes.append((env, write, created_by))
        self.payload = dict(write.payload)
        self.persisted = ca.PersistedResult(
            77,
            88,
            env.idempotency.result_key,
            True,
            write.status,
        )
        return self.persisted

    async def load_result_payload(self, result_id):
        assert result_id == 77
        return self.payload

    async def load_persisted_result(self, env, result_id):
        self.load_persisted_result_calls += 1
        assert result_id == 77
        return ca.PersistedResult(77, 88, env.idempotency.result_key, False)

    async def load_daily_history(self, env, project_id, account_ids):
        self.history_calls.append((env, project_id, account_ids))
        if self.history_sequence:
            return self.history_sequence.pop(0)
        return self.history or ca.DailyHistoricalInputs()

    async def lock_library_mutations(self):
        self.library_mutation_lock_calls += 1

    async def load_delivery_identity(self, env):
        return self.delivery_identity

    async def record_delivery(self, env, result_id, *, status, identity=None, error=None):
        self.delivery_events.append((status, identity, error))
        if identity is not None:
            self.delivery_identity = identity


class Delivery:
    def __init__(self, *, fail=False, identity=None):
        self.fail = fail
        self.identity = identity
        self.calls = []

    async def deliver(self, env, result_id, payload, identity):
        self.calls.append((env, result_id, payload, identity))
        if self.fail:
            raise RuntimeError("private delivery failure")
        return self.identity or ca.DeliveryIdentity(
            env.idempotency.document_key,
            "doc-1",
            "https://feishu.cn/docx/doc-1",
        )


def executor(relations, contents, *, delivery=None, user_id=9, clock=lambda: END):
    analyzer = Analyzer()
    store = Store()
    deliverer = delivery or Delivery()
    service = ca.ContentAnalysisExecutor(
        relation_reader=RelationReader(relations),
        content_reader=ContentReader(contents),
        context_reader=ContextReader(),
        analyzer=analyzer,
        store=store,
        delivery=deliverer,
        system_user_id=user_id,
        clock=clock,
    )
    return service, analyzer, store, deliverer


@pytest.mark.asyncio
async def test_execute_uses_database_analysis_and_delivery_guards() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, _, store, _ = executor(relations, sync_results())

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert store.analysis_guard_calls == ["analysis"]
    assert store.delivery_guard_calls == ["document"]


@pytest.mark.asyncio
async def test_real_task_builder_lets_feishu_relation_choose_daily_account_input() -> None:
    """数据库预检不得在内容执行阶段取代飞书关系表。"""
    raw = build_task_envelope(
        task_id=81,
        task_no="CA-S28-FEISHU-RELATION-81",
        task_code="daily",
        run_type="auto",
        triggered_at=END,
        execution={"object_type": "project", "project_id": 1001},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="root",
        run_key="feishu-relation-run-81",
        internal_result_key="feishu-relation-result-81",
        document_key="feishu-relation-document-81",
    )
    env = ca.parse_task_config_envelope(raw)
    account_id = "feishu-relation-account"
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(sec_uid=account_id),),
    )
    account_results = (
        ca.AccountSyncResult(
            account_id=account_id,
            status=ca.SyncStatus.SUCCESS_WITHOUT_CONTENT,
            contents=(),
            checked_at=END,
            coverage_window=ca.SyncCoverageWindow(
                datetime(2026, 9, 2, tzinfo=SHANGHAI),
                END,
            ),
            read_source=ca.ReadSource.FEISHU,
        ),
    )
    service, analyzer, store, delivery = executor(relations, account_results)

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert outcome.summary.internal_result == "no_content"
    assert service._content_reader.calls[0][0] == (account_id,)
    assert analyzer.basic_calls == []
    assert len(store.writes) == 1
    assert len(delivery.calls) == 1


def finalize_envelope():
    return replace(
        envelope(weekly=True),
        task_id=3,
        task_no="CA-WEEKLY-FINALIZE-3",
        idempotency=ca.IdempotencyKeys(
            "weekly-finalize-analysis",
            "weekly-finalize-result",
            "document",
        ),
        execution=ca.WeeklyBatchFinalizeExecution(
            weekly_batch_id="week-2026-09-05",
            batch_size=2,
            project_ids=("1001", "1002"),
            finalize_version="state-v1",
        ),
    )


def test_execution_layer_summary_rejects_states_outside_closed_contract() -> None:
    with pytest.raises(ValueError, match="预检状态"):
        ca.ExecutionLayerSummary(
            precheck="arbitrary",
            relation="not_started",
            internal_result="not_started",
            delivery="not_started",
        )
    with pytest.raises(ValueError, match="失败阶段"):
        ca.ExecutionLayerSummary(
            precheck="ready",
            relation="complete",
            internal_result="success",
            delivery="success",
            failure_stage="arbitrary",
        )


@pytest.mark.asyncio
async def test_weekly_batch_finalize_only_reads_terminal_state_and_writes_summary() -> None:
    class ForbiddenReader:
        async def read(self):
            raise AssertionError("周批次收尾不得读取飞书")

        async def read_accounts(self, *args):
            raise AssertionError("周批次收尾不得读取飞书内容")

        async def load(self, *args):
            raise AssertionError("周批次收尾不得读取项目上下文")

    class ForbiddenAnalyzer:
        async def analyze_content(self, *args):
            raise AssertionError("周批次收尾不得调用模型")

        async def assess_project(self, *args):
            raise AssertionError("周批次收尾不得执行项目判断")

    store = Store()
    store.weekly_finalize_summary = {
        "weekly_batch_id": "week-2026-09-05",
        "finalize_version": "state-v1",
        "selected_project_ids": ["1001", "1002"],
        "account_count": 2,
        "success_account_count": 0,
        "no_content_account_count": 1,
        "failed_account_count": 1,
        "pending_account_count": 0,
        "failures": [
            {
                "sec_uid": "account-failed",
                "reason_code": "FEISHU_CONTENT_READ_FAILED",
                "public_message": "账号周任务执行失败",
            }
        ],
        "account_results": [],
        "unavailable_reason": "本批次没有可计算账号",
    }
    delivery = Delivery()
    service = ca.ContentAnalysisExecutor(
        relation_reader=ForbiddenReader(),
        content_reader=ForbiddenReader(),
        context_reader=ForbiddenReader(),
        analyzer=ForbiddenAnalyzer(),
        store=store,
        delivery=delivery,
        system_user_id=9,
        clock=lambda: END,
    )

    outcome = await service.execute(finalize_envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert len(store.writes) == 1
    write = store.writes[0][1]
    assert write.payload["batch_summary"]["pending_account_count"] == 0
    assert write.payload["finalize_version"] == "state-v1"
    assert write.source_receipts["task_jobs"]["finalize_version"] == "state-v1"
    assert write.library_items == ()
    assert write.cross_project_opportunities == ()
    assert write.account_baseline is None
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_stale_auto_weekly_finalize_is_rejected_before_summary_or_delivery() -> None:
    service, analyzer, store, delivery = executor(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        ),
        sync_results(content()),
    )
    store.finalize_version_current = False
    env = finalize_envelope()

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert store.finalize_version_validation_calls == [env]
    assert store.writes == []
    assert analyzer.basic_calls == []
    assert service._relation_reader.calls == 0
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_manual_finalize_retry_without_valid_failed_origin_is_rejected() -> None:
    service, analyzer, store, delivery = executor(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        ),
        sync_results(content()),
    )
    store.manual_finalize_retry_valid = False
    env = replace(
        finalize_envelope(),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=1,
        retry_mode=ca.RetryMode.FULL,
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert store.writes == []
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_valid_full_manual_finalize_retry_runs_summary_only() -> None:
    service, analyzer, store, delivery = executor(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        ),
        sync_results(content()),
    )
    store.weekly_finalize_summary = {
        "weekly_batch_id": "week-2026-09-05",
        "finalize_version": "state-v1",
        "selected_project_ids": ["1001", "1002"],
        "account_count": 2,
        "success_account_count": 1,
        "no_content_account_count": 1,
        "failed_account_count": 0,
        "pending_account_count": 0,
        "calculable_account_count": 1,
        "failures": [],
        "account_results": [],
        "unavailable_reason": None,
    }
    env = replace(
        finalize_envelope(),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=1,
        retry_mode=ca.RetryMode.FULL,
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert store.manual_finalize_retry_validation_calls == [env]
    assert len(store.writes) == 1
    assert analyzer.basic_calls == []
    assert service._relation_reader.calls == 0
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_delivery_only_retry_cannot_reenter_full_execute() -> None:
    service, analyzer, store, delivery = executor(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        ),
        sync_results(content()),
    )
    env = replace(
        finalize_envelope(),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=1,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert store.manual_finalize_retry_validation_calls == []
    assert store.writes == []
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_weekly_batch_finalize_with_zero_accounts_writes_empty_company_report() -> None:
    class ForbiddenReader:
        async def read(self):
            raise AssertionError("空周批次收尾不得读取飞书")

        async def read_accounts(self, *args):
            raise AssertionError("空周批次收尾不得读取飞书内容")

        async def load(self, *args):
            raise AssertionError("空周批次收尾不得读取项目上下文")

    class ForbiddenAnalyzer:
        async def analyze_content(self, *args):
            raise AssertionError("空周批次收尾不得调用模型")

        async def assess_project(self, *args):
            raise AssertionError("空周批次收尾不得执行项目判断")

    store = Store()
    store.weekly_finalize_summary = {
        "weekly_batch_id": "week-empty",
        "finalize_version": "empty-state-v1",
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
    }
    delivery = Delivery()
    service = ca.ContentAnalysisExecutor(
        relation_reader=ForbiddenReader(),
        content_reader=ForbiddenReader(),
        context_reader=ForbiddenReader(),
        analyzer=ForbiddenAnalyzer(),
        store=store,
        delivery=delivery,
        system_user_id=9,
        clock=lambda: END,
    )
    env = replace(
        finalize_envelope(),
        execution=ca.WeeklyBatchFinalizeExecution(
            weekly_batch_id="week-empty",
            batch_size=0,
            project_ids=("1001", "1002"),
            finalize_version="empty-state-v1",
        ),
    )

    outcome = await service.execute(env)

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert store.writes[0][1].payload["batch_summary"] == store.weekly_finalize_summary
    assert store.writes[0][1].library_items == ()
    assert store.writes[0][1].cross_project_opportunities == ()
    assert store.writes[0][1].account_baseline is None
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_duplicate_weekly_batch_finalize_reuses_immutable_result() -> None:
    service, _, store, delivery = executor(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        ),
        sync_results(),
    )
    store.weekly_finalize_summary = {
        "weekly_batch_id": "week-2026-09-05",
        "finalize_version": "state-v1",
        "selected_project_ids": ["1001", "1002"],
        "account_count": 2,
        "success_account_count": 1,
        "no_content_account_count": 1,
        "failed_account_count": 0,
        "pending_account_count": 0,
        "failures": [],
        "account_results": [],
        "unavailable_reason": None,
    }
    env = finalize_envelope()

    first, second = await asyncio.gather(
        service.execute(env),
        service.execute(env),
    )

    assert first.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert second.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert len(store.writes) == 1
    assert len(delivery.calls) == 2


@pytest.mark.asyncio
async def test_weekly_finalize_delivery_retry_does_not_repeat_batch_read_or_write() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    failed_delivery = Delivery(fail=True)
    service, analyzer, store, _ = executor(
        relations,
        sync_results(content()),
        delivery=failed_delivery,
    )
    store.weekly_finalize_summary = {
        "weekly_batch_id": "week-2026-09-05",
        "finalize_version": "state-v1",
        "selected_project_ids": ["1001", "1002"],
        "account_count": 2,
        "success_account_count": 1,
        "no_content_account_count": 0,
        "failed_account_count": 1,
        "pending_account_count": 0,
        "failures": [],
        "account_results": [],
        "unavailable_reason": None,
    }
    env = finalize_envelope()

    first = await service.execute(env)
    successful = Delivery()
    service._delivery = successful
    retry_env = replace(
        env,
        run_type=ca.RunType.RETRY,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        retry_of_task_id=env.task_id,
        trigger_source=ca.TriggerSource.SYSTEM,
    )
    retried = await service.redeliver(
        retry_env,
        77,
        ca.DeliveryIdentity("document", None, None),
    )

    assert first.overall_status is ca.ExecutionOverallStatus.FAILED
    assert first.summary.failure_stage == "delivery"
    assert retried.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert retried.summary.relation == "not_started"
    assert len(store.writes) == 1
    assert analyzer.basic_calls == []
    assert service._relation_reader.calls == 0
    assert len(successful.calls) == 1


@pytest.mark.asyncio
async def test_stale_weekly_finalize_delivery_retry_is_rejected_before_delivery() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))
    store.finalize_redelivery_valid = False
    env = replace(
        finalize_envelope(),
        run_type=ca.RunType.RETRY,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        retry_of_task_id=21,
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.redeliver(
        env,
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://feishu.cn/docx/doc-1"),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert outcome.internal_result_id is None
    assert store.finalize_redelivery_validation_calls == [(env, 77)]
    assert store.load_persisted_result_calls == 0
    assert store.analysis_guard_calls == [env.idempotency.analysis_key]
    assert analyzer.basic_calls == []
    assert delivery.calls == []

def test_saved_business_state_restores_all_stable_identity_aliases() -> None:
    payload = {
        "reports": {
            "1001": {
                "all_window_items": [
                    {
                        "stable_key": "platform_content_id:work-alias",
                        "candidate_rank": 2,
                        "is_opportunity": True,
                        "in_library": True,
                        "cross_project": False,
                        "analysis": {
                            "content": {
                                "identity": {
                                    "platform_content_id": "work-alias",
                                    "external_url": "https://example.invalid/work-alias",
                                }
                            }
                        },
                        "assessment": {
                            "priority": 1,
                            "conclusion": "适配匿名项目",
                            "confidence": "high",
                        },
                        "persona_relative_like": "above",
                    }
                ],
                "persona_opportunities": [],
                "qianchuan_opportunities": [],
                "library_candidates": [],
                "cross_project_candidates": [],
            }
        }
    }

    states = ca.SqlContentAnalysisStore._saved_states_from_payload(
        payload,
        "1001",
        set(),
    )

    assert {item.stable_key for item in states} == {
        "platform_content_id:work-alias",
        "external_url:https://example.invalid/work-alias",
    }
    assert all(item.is_opportunity and item.in_library for item in states)



@pytest.mark.asyncio
async def test_existing_library_refresh_uses_current_analysis_for_frozen_cross_projection() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
    )
    method = ca.ReusableMethod(
        name="问题前置法",
        description="先描述共同问题，再给出解法结构",
        method_key="problem-first",
        evidence=(
            ca.AnalysisEvidence(
                ca.EvidenceType.TRANSCRIPT,
                "匿名转写",
                "匿名转写",
            ),
        ),
        applicable_boundaries=(ca.SourceConstraint("只复用结构，不复用商品事实"),),
    )
    source_information = ca.SourceInformation()
    store.history = ca.DailyHistoricalInputs(
        saved_library_records=(
            ca.SavedLibraryRecord(
                project_id="1001",
                content_key="platform_content_id:work-1",
                identity_keys=("platform_content_id:work-1",),
                reusable_methods=(method,),
                source_information=source_information,
            ),
        ),
    )

    async def analyze(item):
        analyzer.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.PERSONA,
            confidence=ca.ConfidenceLevel.HIGH,
            opening=ca.OpeningAnnotation(status=ca.OpeningTagStatus.UNANNOTATED),
            topic="匿名选题",
            summary="匿名摘要",
            reusable_methods=(method,),
            source_information=source_information,
        )

    async def assess(analysis, project_context):
        analyzer.project_calls.append(project_context.project_id)
        return ca.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=True,
            confidence=ca.ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            cross_project_signals=(
                ca.CrossProjectSignal.NOVEL_CONTENT_METHOD,
                ca.CrossProjectSignal.SHARED_CONTENT_PROBLEM_SOLUTION,
            ),
            cross_project_scenarios=(ca.SourceConstraint("适用于同类问题教育"),),
        )

    analyzer.analyze_content = analyze
    analyzer.assess_project = assess

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert write.library_items == ()
    assert len(write.library_refreshes) == 1
    assert [item.method_key for item in write.cross_project_opportunities] == [
        "problem-first"
    ]
    assert len(write.payload["reports"]["1001"]["cross_project_candidates"]) == 1


@pytest.mark.asyncio
async def test_disabled_library_match_stays_out_of_daily_reuse_and_cross_projection() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
    )
    method = ca.ReusableMethod(
        name="问题前置法",
        description="先描述共同问题，再给出解法结构",
        method_key="problem-first",
        evidence=(
            ca.AnalysisEvidence(
                ca.EvidenceType.TRANSCRIPT,
                "匿名转写",
                "匿名转写",
            ),
        ),
        applicable_boundaries=(ca.SourceConstraint("只复用结构，不复用商品事实"),),
    )
    source_information = ca.SourceInformation()
    store.history = ca.DailyHistoricalInputs(
        saved_library_records=(
            ca.SavedLibraryRecord(
                project_id="1001",
                content_key="platform_content_id:work-1",
                identity_keys=("platform_content_id:work-1",),
                reusable_methods=(method,),
                source_information=source_information,
                available_for_reuse=False,
            ),
            ca.SavedLibraryRecord(
                project_id="1001",
                content_key="platform_content_id:work-2",
                reusable_methods=(method,),
                source_information=source_information,
                signals=(ca.CrossProjectSignal.NOVEL_CONTENT_METHOD,),
                scenarios=("适用于同类问题教育",),
            ),
            ca.SavedLibraryRecord(
                project_id="2002",
                content_key="platform_content_id:work-3",
                reusable_methods=(method,),
                source_information=source_information,
                signals=(
                    ca.CrossProjectSignal.SHARED_CONTENT_PROBLEM_SOLUTION,
                ),
                scenarios=("适用于同类问题教育",),
            ),
        ),
    )

    async def analyze(item):
        analyzer.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.PERSONA,
            confidence=ca.ConfidenceLevel.HIGH,
            opening=ca.OpeningAnnotation(status=ca.OpeningTagStatus.UNANNOTATED),
            topic="匿名选题",
            summary="匿名摘要",
            reusable_methods=(method,),
            source_information=source_information,
        )

    async def assess(analysis, project_context):
        analyzer.project_calls.append(project_context.project_id)
        return ca.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=True,
            confidence=ca.ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            cross_project_signals=(
                ca.CrossProjectSignal.NOVEL_CONTENT_METHOD,
                ca.CrossProjectSignal.SHARED_CONTENT_PROBLEM_SOLUTION,
            ),
            cross_project_scenarios=(ca.SourceConstraint("适用于同类问题教育"),),
        )

    analyzer.analyze_content = analyze
    analyzer.assess_project = assess

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    report_item = write.payload["reports"]["1001"]["all_window_items"][0]
    assert report_item["in_library"] is False
    assert report_item["cross_project"] is False
    assert write.library_items == ()
    assert len(write.library_refreshes) == 1
    assert write.cross_project_opportunities == ()
    assert write.payload["reports"]["1001"]["cross_project_candidates"] == []


@pytest.mark.asyncio
async def test_daily_reloads_availability_under_lock_before_freezing_result() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, _ = executor(
        relations,
        sync_results(content()),
    )
    method = ca.ReusableMethod(
        name="问题前置法",
        description="先描述共同问题，再给出解法结构",
        method_key="problem-first",
        evidence=(
            ca.AnalysisEvidence(
                ca.EvidenceType.TRANSCRIPT,
                "匿名转写",
                "匿名转写",
            ),
        ),
        applicable_boundaries=(ca.SourceConstraint("只复用结构，不复用商品事实"),),
    )
    source_information = ca.SourceInformation()

    def saved_records(*, current_available):
        return (
            ca.SavedLibraryRecord(
                project_id="1001",
                content_key="platform_content_id:work-1",
                identity_keys=("platform_content_id:work-1",),
                reusable_methods=(method,),
                source_information=source_information,
                available_for_reuse=current_available,
                signals=(ca.CrossProjectSignal.NOVEL_CONTENT_METHOD,),
                scenarios=("适用于同类问题教育",),
            ),
            ca.SavedLibraryRecord(
                project_id="2002",
                content_key="platform_content_id:work-2",
                reusable_methods=(method,),
                source_information=source_information,
                signals=(
                    ca.CrossProjectSignal.SHARED_CONTENT_PROBLEM_SOLUTION,
                ),
                scenarios=("适用于同类问题教育",),
            ),
        )

    store.history_sequence = [
        ca.DailyHistoricalInputs(
            saved_library_records=saved_records(current_available=True)
        ),
        ca.DailyHistoricalInputs(
            saved_library_records=saved_records(current_available=False)
        ),
    ]

    async def analyze(item):
        analyzer.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.PERSONA,
            confidence=ca.ConfidenceLevel.HIGH,
            opening=ca.OpeningAnnotation(status=ca.OpeningTagStatus.UNANNOTATED),
            topic="匿名选题",
            summary="匿名摘要",
            reusable_methods=(method,),
            source_information=source_information,
        )

    async def assess(analysis, project_context):
        analyzer.project_calls.append(project_context.project_id)
        return ca.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=True,
            confidence=ca.ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            cross_project_signals=(
                ca.CrossProjectSignal.NOVEL_CONTENT_METHOD,
                ca.CrossProjectSignal.SHARED_CONTENT_PROBLEM_SOLUTION,
            ),
            cross_project_scenarios=(ca.SourceConstraint("适用于同类问题教育"),),
        )

    analyzer.analyze_content = analyze
    analyzer.assess_project = assess

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert store.library_mutation_lock_calls == 1
    assert len(store.history_calls) == 2
    write = store.writes[0][1]
    report_item = write.payload["reports"]["1001"]["all_window_items"][0]
    assert report_item["in_library"] is False
    assert report_item["cross_project"] is False
    assert write.cross_project_opportunities == ()
    assert write.payload["reports"]["1001"]["cross_project_candidates"] == []


@pytest.mark.asyncio
async def test_daily_drops_new_candidate_when_same_identity_was_added_and_disabled_during_model() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, _ = executor(
        relations,
        sync_results(content()),
    )
    store.history_sequence = [
        ca.DailyHistoricalInputs(),
        ca.DailyHistoricalInputs(
            saved_library_records=(
                ca.SavedLibraryRecord(
                    project_id="1001",
                    content_key="platform_content_id:work-1",
                    identity_keys=("platform_content_id:work-1",),
                    reusable_methods=(),
                    source_information=ca.SourceInformation(),
                    available_for_reuse=False,
                ),
            ),
        ),
    ]

    async def assess(analysis, project_context):
        analyzer.project_calls.append(project_context.project_id)
        return ca.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=True,
            is_opportunity=True,
            priority=1,
            confidence=ca.ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            value_signals=(ca.CandidateValueSignal.NOVEL_TOPIC_OR_STRUCTURE,),
            fit_reasons=(
                ca.ProjectFitReason(
                    ca.ProjectFitDimension.PROJECT_PERSONA,
                    "符合匿名项目人设",
                ),
            ),
            recommended_action="进入项目内容库候选",
            decision_basis=("结构可复用",),
        )

    analyzer.assess_project = assess

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert write.library_items == ()
    assert write.payload["reports"]["1001"]["library_candidates"] == []


@pytest.mark.asyncio
async def test_complete_relation_without_valid_project_is_not_run_and_calls_nothing_else() -> None:
    relations = ca.FeishuRelationReadResult(ca.FeishuRelationReadStatus.COMPLETE, END)
    service, analyzer, store, delivery = executor(relations, ())

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.NOT_RUN
    assert outcome.task_status == "not_run"
    assert outcome.summary.relation == "not_run"
    assert outcome.to_result_summary(envelope()) == {
        "trigger_source": "system",
        "overall_status": "not_run",
        "precheck": "ready",
        "feishu_relation": "not_run",
        "internal_result": "not_started",
        "feishu_delivery": "not_started",
        "failure_stage": "relation",
        "reason_code": "FEISHU_RELATION_NOT_FOUND",
        "public_message": "飞书关系完整读取，但当前任务没有有效对标关系",
        "input_limited": False,
        "limitation_codes": [],
        "internal_result_id": None,
        "output_id": None,
        "delivery_identity": None,
    }
    assert analyzer.basic_calls == []
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_database_precheck_missing_is_not_run_but_technical_error_is_failed() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))
    missing = replace(
        envelope(),
        precheck=ca.DatabasePrecheck(ca.DatabasePrecheckStatus.MISSING),
    )
    error = replace(
        envelope(),
        precheck=ca.DatabasePrecheck(ca.DatabasePrecheckStatus.ERROR),
    )

    missing_outcome = await service.execute(missing)
    error_outcome = await service.execute(error)

    assert missing_outcome.overall_status is ca.ExecutionOverallStatus.NOT_RUN
    assert error_outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert error_outcome.summary.failure_stage == "precheck"
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_internal_retry_must_match_persisted_original_before_external_calls() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
    )
    store.internal_retry_valid = False
    retry_envelope = replace(
        envelope(),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=1,
        retry_mode=ca.RetryMode.FULL,
        trigger_source=ca.TriggerSource.SYSTEM,
    )

    outcome = await service.execute(retry_envelope)

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert outcome.summary.failure_stage == "system_config"
    assert store.internal_retry_validation_calls == [retry_envelope]
    assert service._relation_reader.calls == 0
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("weekly", (False, True))
async def test_manual_full_retry_must_match_failed_origin_before_external_calls(
    weekly,
) -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
    )
    store.manual_retry_valid = False
    retry_envelope = replace(
        envelope(weekly=weekly),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=99,
        retry_mode=ca.RetryMode.FULL,
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.execute(retry_envelope)

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert outcome.summary.failure_stage == "system_config"
    assert store.manual_retry_validation_calls == [retry_envelope]
    assert service._relation_reader.calls == 0
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_internal_delivery_retry_validates_original_before_loading_result() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, _, store, delivery = executor(relations, sync_results())
    store.internal_retry_valid = False
    retry_envelope = replace(
        envelope(),
        run_type=ca.RunType.RETRY,
        retry_of_task_id=1,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        trigger_source=ca.TriggerSource.SYSTEM,
    )

    outcome = await service.redeliver(
        retry_envelope,
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://feishu.cn/docx/doc-1"),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert outcome.summary.failure_stage == "delivery"
    assert outcome.summary.internal_result == "not_started"
    assert outcome.summary.delivery == "failed"
    assert store.load_persisted_result_calls == 0
    assert delivery.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("weekly", (False, True))
async def test_manual_delivery_retry_validates_failed_origin_before_loading_result(
    weekly,
) -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, _, store, delivery = executor(relations, sync_results())
    store.manual_redelivery_valid = False
    retry_envelope = replace(
        envelope(weekly=weekly),
        task_id=101,
        task_no="CA-MANUAL-REDELIVERY-101",
        run_type=ca.RunType.RETRY,
        retry_of_task_id=99,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        request_id="request-101",
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.redeliver(
        retry_envelope,
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://feishu.cn/docx/doc-1"),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert outcome.summary.failure_stage == "delivery"
    assert outcome.summary.internal_result == "not_started"
    assert store.manual_redelivery_validation_calls == [(retry_envelope, 77)]
    assert store.load_persisted_result_calls == 0
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_expired_manual_redelivery_still_validates_origin_before_result_read() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, _, store, delivery = executor(
        relations,
        sync_results(),
        clock=lambda: datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
    )
    store.manual_redelivery_valid = False
    retry_envelope = replace(
        envelope(),
        task_id=101,
        task_no="CA-MANUAL-REDELIVERY-EXPIRED",
        run_type=ca.RunType.RETRY,
        retry_of_task_id=99,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        request_id="request-expired",
        trigger_source=ca.TriggerSource.USER,
    )

    outcome = await service.redeliver(
        retry_envelope,
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://feishu.cn/docx/doc-1"),
    )

    assert outcome.summary.failure_stage == "delivery"
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"
    assert store.manual_redelivery_validation_calls == [(retry_envelope, 77)]
    assert store.load_persisted_result_calls == 0
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_invalid_system_service_account_stops_before_any_external_or_model_call() -> None:
    relation_reader = RelationReader(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        )
    )
    content_reader = ContentReader(sync_results(content()))
    analyzer = Analyzer()
    store = Store()
    store.system_user_valid = False
    delivery = Delivery()
    service = ca.ContentAnalysisExecutor(
        relation_reader=relation_reader,
        content_reader=content_reader,
        context_reader=ContextReader(),
        analyzer=analyzer,
        store=store,
        delivery=delivery,
        system_user_id=9,
        clock=lambda: END,
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "system_config"
    assert outcome.summary.reason_code == "SYSTEM_ACCOUNT_INVALID"
    assert relation_reader.calls == 0
    assert content_reader.calls == []
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_relation_failure_is_failed_and_never_becomes_empty_report() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.FAILED,
        END,
        error_reason="飞书关系表读取失败",
    )
    service, analyzer, store, delivery = executor(relations, ())

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "relation"
    assert store.writes == []


@pytest.mark.asyncio
async def test_content_read_failure_is_failed_and_never_becomes_empty_report() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, failed_sync_results())

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "content"
    assert outcome.summary.internal_result == "failed"
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_valid_relation_and_zero_content_persists_and_delivers_empty_daily() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results())

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert outcome.summary.internal_result == "no_content"
    assert outcome.summary.delivery == "success"
    assert outcome.summary.input_limited is True
    assert outcome.summary.limitation_codes == (
        "TARGET_USERS_MISSING",
        "OPERATING_DIRECTION_MISSING",
    )
    assert store.writes[0][1].status is ca.InternalResultStatus.NO_CONTENT
    report = store.writes[0][1].payload["reports"]["1001"]
    assert report["daily_overview"]["content_count"] == 0
    assert report["library_candidates"] == []
    assert report["cross_project_candidates"] == []
    metadata = store.writes[0][1].payload["run_metadata"]
    assert metadata["data_complete"] is False
    assert metadata["limitation_codes"] == [
        "TARGET_USERS_MISSING",
        "OPERATING_DIRECTION_MISSING",
    ]
    assert analyzer.basic_calls == []
    assert len(delivery.calls) == 1
    delivered_envelope = delivery.calls[0][0]
    assert delivered_envelope.delivery_target.relative_directory == (
        "项目日报/1001-匿名_项目"
    )
    assert store.writes[0][1].payload["run_metadata"]["project_name"] == "匿名/项目"


@pytest.mark.asyncio
async def test_task_config_test_directory_runs_without_falling_back_to_formal_scope() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, _, store, delivery = executor(relations, sync_results())

    outcome = await service.execute(envelope(run_type=ca.RunType.TEST))

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert store.writes[0][0].delivery_target.relative_directory == "测试报告"
    assert delivery.calls[0][0].delivery_target.relative_directory == "测试报告"


@pytest.mark.asyncio
async def test_daily_supplements_pending_manual_qianchuan_opening_outside_report_window() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results())
    store.pending_manual_openings = (
        ca.ManualOpeningCandidate(
            item_id=501,
            project_id=1001,
            title="人工标题",
            transcript="先说匿名问题，再给方法",
        ),
    )

    async def analyze(item):
        analyzer.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.QIANCHUAN,
            confidence=ca.ConfidenceLevel.MEDIUM,
            opening=ca.OpeningAnnotation(
                status=ca.OpeningTagStatus.AVAILABLE,
                kind=ca.OpeningKind.LANGUAGE,
                fragment="先说匿名问题",
                evidence=(
                    ca.AnalysisEvidence(
                        ca.EvidenceType.TRANSCRIPT,
                        "transcript:0-6",
                        "先说匿名问题",
                    ),
                ),
                applicable_boundaries=(
                    ca.SourceConstraint("只复用不依赖来源商品事实的开头结构"),
                ),
            ),
        )

    analyzer.analyze_content = analyze

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert len(write.manual_opening_updates) == 1
    assert write.manual_opening_updates[0].status == "available"
    assert write.manual_opening_updates[0].fragment == "先说匿名问题"
    assert write.payload["manual_opening_supplements"] == [
        {
            "item_id": 501,
            "project_id": 1001,
            "status": "available",
            "unavailable_reason": None,
        }
    ]


@pytest.mark.asyncio
async def test_daily_skips_manual_opening_disabled_while_model_is_running() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results())
    pending = ca.ManualOpeningCandidate(
        item_id=501,
        project_id=1001,
        title="人工标题",
        transcript="先说匿名问题，再给方法",
    )
    store.pending_manual_opening_sequence = [(pending,), ()]

    async def analyze(item):
        analyzer.basic_calls.append(item.identity.platform_content_id)
        return ca.BasicAnalysis(
            content=item,
            category=ca.ContentCategory.QIANCHUAN,
            confidence=ca.ConfidenceLevel.MEDIUM,
            opening=ca.OpeningAnnotation(
                status=ca.OpeningTagStatus.AVAILABLE,
                kind=ca.OpeningKind.LANGUAGE,
                fragment="先说匿名问题",
                evidence=(
                    ca.AnalysisEvidence(
                        ca.EvidenceType.TRANSCRIPT,
                        "transcript:0-6",
                        "先说匿名问题",
                    ),
                ),
                applicable_boundaries=(ca.SourceConstraint("只复用表达结构"),),
            ),
        )

    analyzer.analyze_content = analyze

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert write.manual_opening_updates == ()
    assert write.payload["manual_opening_supplements"] == []
    assert write.payload["manual_opening_failures"] == []
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_daily_drops_manual_opening_failure_when_item_is_disabled_during_model() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results())
    pending = ca.ManualOpeningCandidate(
        item_id=501,
        project_id=1001,
        title="人工标题",
        transcript="匿名正文",
    )
    store.pending_manual_opening_sequence = [(pending,), ()]

    async def fail_analysis(item):
        raise RuntimeError("private model failure")

    analyzer.analyze_content = fail_analysis

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert write.manual_opening_updates == ()
    assert write.payload["manual_opening_failures"] == []
    assert "MANUAL_OPENING_ANALYSIS_FAILED" not in write.payload["run_metadata"][
        "limitation_codes"
    ]
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_manual_opening_analysis_failure_keeps_item_unannotated() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, _ = executor(relations, sync_results())
    store.pending_manual_openings = (
        ca.ManualOpeningCandidate(
            item_id=501,
            project_id=1001,
            title="人工标题",
            transcript="匿名正文",
        ),
    )

    async def fail_analysis(item):
        raise RuntimeError("private model failure")

    analyzer.analyze_content = fail_analysis

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    write = store.writes[0][1]
    assert write.manual_opening_updates == ()
    assert write.payload["manual_opening_failures"] == [
        {
            "item_id": 501,
            "project_id": 1001,
            "reason_code": "MANUAL_OPENING_ANALYSIS_FAILED",
        }
    ]
    assert "MANUAL_OPENING_ANALYSIS_FAILED" in write.payload["run_metadata"][
        "limitation_codes"
    ]


@pytest.mark.asyncio
async def test_daily_execution_injects_saved_weekly_baseline_into_engine() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    current_content = replace(
        content(likes=10),
        published_at=datetime(2026, 9, 4, 8, tzinfo=SHANGHAI),
        captured_at=datetime(2026, 9, 4, 12, tzinfo=SHANGHAI),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(current_content),
    )
    store.history = ca.DailyHistoricalInputs(
        persona_baselines=(
            ca.WeeklyPersonaBaseline(
                account_id="account-001",
                window_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
                window_end=datetime(2026, 9, 4, tzinfo=SHANGHAI),
                baseline=ca.LikeBaseline(
                    mean=5,
                    median=5,
                    sample_size=2,
                    maximum=6,
                    minimum=4,
                ),
            ),
        ),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    report_item = store.writes[0][1].payload["reports"]["1001"]["items"][0]
    assert report_item["persona_relative_like"] == "above"
    assert store.history_calls[0][1:] == ("1001", ("account-001",))


@pytest.mark.asyncio
async def test_delivery_failure_preserves_result_and_redelivery_does_not_repeat_analysis() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    failed_delivery = Delivery(fail=True)
    service, analyzer, store, _ = executor(relations, sync_results(content()), delivery=failed_delivery)

    first = await service.execute(envelope())

    assert first.overall_status is ca.ExecutionOverallStatus.FAILED
    assert first.summary.failure_stage == "delivery"
    assert first.internal_result_id == 77
    basic_calls = list(analyzer.basic_calls)
    successful = Delivery()
    service._delivery = successful
    retried = await service.redeliver(envelope(), 77, ca.DeliveryIdentity("document", None, None))

    assert retried.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert retried.output_id == 88
    assert analyzer.basic_calls == basic_calls
    assert len(store.writes) == 1
    assert len(successful.calls) == 1


@pytest.mark.asyncio
async def test_partial_document_create_is_persisted_and_redelivery_reuses_same_document() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    partial_identity = ca.DeliveryIdentity(
        "document",
        "partial-doc",
        "https://feishu.cn/docx/partial-doc",
    )

    class PartialDelivery(Delivery):
        async def deliver(self, env, result_id, payload, identity):
            self.calls.append((env, result_id, payload, identity))
            raise ca.DocumentCreatedBeforeContentError(partial_identity)

    service, analyzer, store, _ = executor(
        relations,
        sync_results(content()),
        delivery=PartialDelivery(),
    )

    first = await service.execute(envelope())
    basic_calls = list(analyzer.basic_calls)
    successful = Delivery(identity=partial_identity)
    service._delivery = successful
    retried = await service.redeliver(envelope(), 77, partial_identity)

    assert first.overall_status is ca.ExecutionOverallStatus.FAILED
    assert first.delivery_identity == partial_identity
    assert store.delivery_identity == partial_identity
    assert retried.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert successful.calls[0][3] == partial_identity
    assert analyzer.basic_calls == basic_calls
    assert len(store.writes) == 1


@pytest.mark.asyncio
async def test_repeated_execute_reuses_saved_result_before_input_or_model_calls() -> None:
    relation_reader = RelationReader(
        ca.FeishuRelationReadResult(
            ca.FeishuRelationReadStatus.COMPLETE,
            END,
            relations=(relation(),),
        )
    )
    content_reader = ContentReader(sync_results(content()))
    analyzer = Analyzer()
    store = Store()
    delivery = Delivery()
    service = ca.ContentAnalysisExecutor(
        relation_reader=relation_reader,
        content_reader=content_reader,
        context_reader=ContextReader(),
        analyzer=analyzer,
        store=store,
        delivery=delivery,
        system_user_id=9,
        clock=lambda: END,
    )

    first = await service.execute(envelope())
    second = await service.execute(envelope())

    assert first.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert second.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert analyzer.basic_calls == ["work-1"]
    assert relation_reader.calls == 1
    assert len(content_reader.calls) == 1
    assert len(store.writes) == 1
    assert len(delivery.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_duplicate_execute_is_single_flight_for_model_analysis() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))
    original = analyzer.analyze_content

    async def yield_then_analyze(item):
        await asyncio.sleep(0)
        return await original(item)

    analyzer.analyze_content = yield_then_analyze

    outcomes = await asyncio.gather(
        service.execute(envelope()),
        service.execute(envelope()),
    )

    assert all(
        outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
        for outcome in outcomes
    )
    assert analyzer.basic_calls == ["work-1"]
    assert len(store.writes) == 1
    assert len(delivery.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_duplicate_execute_across_executor_instances_is_single_flight() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    relation_reader = RelationReader(relations)
    content_reader = ContentReader(sync_results(content()))
    analyzer = Analyzer()
    store = Store()
    delivery = Delivery()
    original = analyzer.analyze_content

    async def yield_then_analyze(item):
        await asyncio.sleep(0)
        return await original(item)

    analyzer.analyze_content = yield_then_analyze
    common = dict(
        relation_reader=relation_reader,
        content_reader=content_reader,
        context_reader=ContextReader(),
        analyzer=analyzer,
        store=store,
        delivery=delivery,
        system_user_id=9,
        clock=lambda: END,
    )
    services = (ca.ContentAnalysisExecutor(**common), ca.ContentAnalysisExecutor(**common))

    outcomes = await asyncio.gather(*(service.execute(envelope()) for service in services))

    assert all(item.overall_status is ca.ExecutionOverallStatus.SUCCESS for item in outcomes)
    assert analyzer.basic_calls == ["work-1"]
    assert len(store.writes) == 1


@pytest.mark.asyncio
async def test_local_single_flight_wait_is_bounded_by_envelope_deadline() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    relation_reader = RelationReader(relations)
    content_reader = ContentReader(sync_results(content()))
    analyzer = Analyzer()
    store = Store()
    delivery = Delivery()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    original = analyzer.analyze_content

    async def blocking_analysis(item):
        first_entered.set()
        await release_first.wait()
        return await original(item)

    analyzer.analyze_content = blocking_analysis
    common = dict(
        relation_reader=relation_reader,
        content_reader=content_reader,
        context_reader=ContextReader(),
        analyzer=analyzer,
        store=store,
        delivery=delivery,
        system_user_id=9,
    )
    holder = ca.ContentAnalysisExecutor(**common, clock=lambda: END)
    moments = iter(
        (
            datetime(2026, 9, 5, 11, 59, 59, 990000, tzinfo=SHANGHAI),
            envelope().deadline_at,
        )
    )
    waiter = ca.ContentAnalysisExecutor(**common, clock=lambda: next(moments))
    holder_task = asyncio.create_task(holder.execute(envelope()))
    await first_entered.wait()

    try:
        waiting_outcome = await waiter.execute(envelope())
    finally:
        release_first.set()
        await holder_task

    assert waiting_outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert waiting_outcome.summary.failure_stage == "deadline"
    assert waiting_outcome.summary.reason_code == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_redelivery_rejects_internal_result_from_another_result_key() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))
    store.load_persisted_result = lambda env, result_id: _foreign_result(result_id)

    outcome = await service.redeliver(
        envelope(),
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://example.invalid/doc-1"),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "delivery"
    assert delivery.calls == []


async def _foreign_result(result_id):
    return ca.PersistedResult(result_id, 99, "foreign-result", False)


@pytest.mark.asyncio
async def test_weekly_account_is_analyzed_once_for_multiple_sorted_projects() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation("1001"), relation("1002")),
    )
    weekly_sync = list(sync_results(content()))
    weekly_sync[0] = replace(
        weekly_sync[0],
        coverage_window=ca.SyncCoverageWindow(datetime(2026, 8, 6, tzinfo=SHANGHAI), END),
    )
    service, analyzer, store, delivery = executor(relations, tuple(weekly_sync))

    outcome = await service.execute(envelope(weekly=True))

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert analyzer.basic_calls == ["work-1"]
    assert analyzer.project_calls == []
    baseline = store.writes[0][1].account_baseline
    assert baseline.related_project_ids == ("1001", "1002")
    assert baseline.sample_count == 1
    metadata = store.writes[0][1].payload["run_metadata"]
    assert metadata["data_complete"] is False
    assert metadata["limitation_codes"] == [
        "TARGET_USERS_MISSING",
        "OPERATING_DIRECTION_MISSING",
    ]
    assert "batch_summary" not in store.writes[0][1].payload
    assert store.writes[0][1].payload["baseline"] == {
        "account_id": "account-001",
        "window_start": "2026-08-06T00:00:00+08:00",
        "window_end": "2026-09-05T00:00:00+08:00",
        "baseline": {
            "mean": 10.0,
            "median": 10.0,
            "sample_size": 1,
            "maximum": 10,
            "minimum": 10,
        },
        "status": "available",
        "updated_at": "2026-09-05T00:00:00+08:00",
        "unavailable_reason": None,
    }
    assert len(delivery.calls) == 1


@pytest.mark.asyncio
async def test_missing_system_service_account_fails_closed_before_external_calls() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(), user_id=None)

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "system_config"
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_expired_envelope_fails_before_external_calls_or_writes() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: datetime(2026, 9, 5, 12, 0, 1, tzinfo=SHANGHAI),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert store.analysis_guard_calls == []
    assert analyzer.basic_calls == []
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_exact_deadline_is_already_expired() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert store.analysis_guard_calls == []
    assert analyzer.basic_calls == []
    assert store.writes == []


@pytest.mark.asyncio
async def test_lock_wait_crossing_deadline_returns_closed_failure() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    moments = iter((END, envelope().deadline_at))
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: next(moments),
    )
    store.analysis_guard_error = TimeoutError("等待锁超时")

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert outcome.summary.reason_code == "DEADLINE_EXCEEDED"
    assert analyzer.basic_calls == []
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_finalize_redelivery_lock_timeout_does_not_read_unverified_result() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    env = replace(
        finalize_envelope(),
        run_type=ca.RunType.RETRY,
        retry_mode=ca.RetryMode.DELIVERY_ONLY,
        retry_of_task_id=3,
        trigger_source=ca.TriggerSource.SYSTEM,
    )
    moments = iter((env.deadline_at,))
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: next(moments),
    )
    store.analysis_guard_error = TimeoutError("等待锁超时")

    outcome = await service.redeliver(
        env,
        77,
        ca.DeliveryIdentity(
            "document",
            "doc-1",
            "https://feishu.cn/docx/doc-1",
        ),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert outcome.summary.reason_code == "DEADLINE_EXCEEDED"
    assert outcome.internal_result_id is None
    assert store.load_persisted_result_calls == 0
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_crossing_deadline_during_analysis_prevents_persistence_and_delivery() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    moments = iter(
        (
            END,
            END,
            datetime(2026, 9, 5, 12, 0, 1, tzinfo=SHANGHAI),
        )
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: next(moments),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert analyzer.basic_calls == ["work-1"]
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_weekly_all_content_analysis_failures_fail_the_account_instance() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation("1001"), relation("1002")),
    )
    weekly_sync = list(sync_results(content()))
    weekly_sync[0] = replace(
        weekly_sync[0],
        coverage_window=ca.SyncCoverageWindow(
            datetime(2026, 8, 6, tzinfo=SHANGHAI),
            END,
        ),
    )
    service, analyzer, store, delivery = executor(relations, tuple(weekly_sync))

    async def fail_analysis(item):
        raise RuntimeError("model unavailable")

    analyzer.analyze_content = fail_analysis

    outcome = await service.execute(envelope(weekly=True))

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "analysis_or_persistence"
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_daily_all_readable_content_analysis_failures_fail_the_project_instance() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))

    async def fail_analysis(item):
        raise RuntimeError("model unavailable")

    analyzer.analyze_content = fail_analysis

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "analysis_or_persistence"
    assert store.writes == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_daily_missing_transcript_is_not_mistaken_for_total_model_failure() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(
            replace(
                content(transcript=None),
                published_at=datetime(2026, 9, 4, 8, tzinfo=SHANGHAI),
                captured_at=datetime(2026, 9, 4, 12, tzinfo=SHANGHAI),
            )
        ),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert analyzer.basic_calls == []
    assert store.writes[0][1].payload["reports"]["1001"]["daily_overview"]["content_count"] == 1


@pytest.mark.asyncio
async def test_unexpected_relation_or_content_reader_exception_fails_closed() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))

    async def fail_relation():
        raise RuntimeError("private relation failure")

    service._relation_reader.read = fail_relation
    relation_outcome = await service.execute(envelope())
    assert relation_outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert relation_outcome.summary.failure_stage == "relation"

    service, analyzer, store, delivery = executor(relations, sync_results(content()))

    async def fail_content(account_ids, coverage_window):
        raise RuntimeError("private content failure")

    service._content_reader.read_accounts = fail_content
    content_outcome = await service.execute(envelope())
    assert content_outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert content_outcome.summary.failure_stage == "content"
    assert store.writes == []


@pytest.mark.asyncio
async def test_existing_result_redelivery_uses_saved_payload_and_status() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))
    saved_payload = {"reports": {"1001": {"summary": "已保存结果"}}}

    async def reuse(env, write, created_by):
        store.writes.append((env, write, created_by))
        store.payload = saved_payload
        return ca.PersistedResult(
            77,
            88,
            env.idempotency.result_key,
            False,
            ca.InternalResultStatus.NO_CONTENT,
        )

    store.persist = reuse

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.SUCCESS
    assert outcome.summary.internal_result == "no_content"
    assert delivery.calls[0][2] is saved_payload


@pytest.mark.asyncio
async def test_delivery_state_write_failure_does_not_escape_execution_boundary() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        delivery=Delivery(fail=True),
    )

    async def fail_record(*args, **kwargs):
        raise RuntimeError("delivery state unavailable")

    store.record_delivery = fail_record

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "delivery"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    (
        ca.DeliveryIdentity("document", None, "https://feishu.cn/docx/doc-1"),
        ca.DeliveryIdentity("document", "doc-1", None),
        ca.DeliveryIdentity("document", "doc-1", "https://example.invalid/docx/doc-1"),
        ca.DeliveryIdentity("document", "doc-1", "https://feishu.cn/docx/other"),
        ca.DeliveryIdentity("document", "doc-1", "javascript://feishu.cn/docx/doc-1"),
        ca.DeliveryIdentity("other", "doc-1", "https://feishu.cn/docx/doc-1"),
    ),
)
async def test_delivery_success_requires_complete_trusted_matching_identity(identity) -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        delivery=Delivery(identity=identity),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "delivery"
    assert store.delivery_events[-1][0] == "failed"


@pytest.mark.asyncio
async def test_crossing_deadline_during_delivery_fails_before_success_is_recorded() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    moments = iter(
        (
            END,
            END,
            END,
            datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
        )
    )
    service, analyzer, store, delivery = executor(
        relations,
        sync_results(content()),
        clock=lambda: next(moments),
    )

    outcome = await service.execute(envelope())

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "deadline"
    assert not any(event[0] == "success" for event in store.delivery_events)


@pytest.mark.asyncio
async def test_redelivery_store_lookup_failure_does_not_escape_execution_boundary() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results(content()))

    async def fail_lookup(env, result_id):
        raise RuntimeError("result unavailable")

    store.load_persisted_result = fail_lookup

    outcome = await service.redeliver(
        envelope(),
        77,
        ca.DeliveryIdentity("document", "doc-1", "https://example.invalid/doc-1"),
    )

    assert outcome.overall_status is ca.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "delivery"
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_weekly_relation_scope_mismatch_is_not_run_instead_of_silent_shrink() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation("1001"),),
    )
    weekly_sync = list(sync_results(content()))
    weekly_sync[0] = replace(
        weekly_sync[0],
        coverage_window=ca.SyncCoverageWindow(
            datetime(2026, 8, 6, tzinfo=SHANGHAI),
            END,
        ),
    )
    service, analyzer, store, delivery = executor(relations, tuple(weekly_sync))

    outcome = await service.execute(envelope(weekly=True))

    assert outcome.overall_status is ca.ExecutionOverallStatus.NOT_RUN
    assert outcome.summary.reason_code == "FEISHU_RELATION_SCOPE_MISMATCH"
    assert store.writes == []
    assert analyzer.basic_calls == []
    assert delivery.calls == []


@pytest.mark.asyncio
async def test_test_run_never_falls_back_to_formal_report_directory() -> None:
    relations = ca.FeishuRelationReadResult(
        ca.FeishuRelationReadStatus.COMPLETE,
        END,
        relations=(relation(),),
    )
    service, analyzer, store, delivery = executor(relations, sync_results())
    with pytest.raises(ValueError, match="目录命名空间"):
        ca.DeliveryTarget("root", "正式目录", scope=ca.DeliveryScope.TEST)
