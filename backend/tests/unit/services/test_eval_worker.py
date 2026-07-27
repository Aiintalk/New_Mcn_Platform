"""
app/evaluation/worker.py 单测（Phase 1：redis 配置解析 + ping 冒烟任务）。

注：真实 enqueue→worker 消费的全链路冒烟已手动验证（见 plan Phase 1）；
本文件固化"REDIS_URL 解析正确 + ping 行为正确"，不依赖 redis 在线。
"""
import pytest

from app.evaluation.worker import WorkerSettings, eval_redis_settings, ping


def test_redis_settings_default(monkeypatch):
    """无 REDIS_URL → 默认 localhost:6379/0。"""
    monkeypatch.delenv("REDIS_URL", raising=False)
    s = eval_redis_settings()
    assert s.host == "localhost"
    assert s.port == 6379
    assert s.database == 0
    assert s.password is None


def test_redis_settings_full_url(monkeypatch):
    """带密码/自定义 host:port/db 的 REDIS_URL 正确解析。"""
    monkeypatch.setenv("REDIS_URL", "redis://:secret@redis-host:6380/2")
    s = eval_redis_settings()
    assert s.host == "redis-host"
    assert s.port == 6380
    assert s.database == 2
    assert s.password == "secret"


async def test_ping_returns_argument():
    """ping 冒烟任务原样回显。"""
    assert await ping({}, "eval-smoke") == "pong: eval-smoke"
    assert await ping({}) == "pong: world"


def test_worker_settings_basics():
    """WorkerSettings 关键配置：注册 ping、并发上限=2、重试=3。"""
    assert ping in WorkerSettings.functions
    assert WorkerSettings.max_jobs == 2      # 一期并发上限（已确认）
    assert WorkerSettings.max_tries == 3
    assert WorkerSettings.job_timeout == 900


# ---------------------------------------------------------------------------
# run 聚合 + case-job stub 执行（DB 逻辑，用 test_session）
# ---------------------------------------------------------------------------
import uuid  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.evaluation.constants import (  # noqa: E402
    EVAL_TOOL_QIANCHUAN_WRITER,
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
)
from app.evaluation.models import (  # noqa: E402
    EvalCaseJob,
    EvalCaseResult,
    EvalDimension,
    EvalHumanLabel,
    EvalJudgeModel,
    EvalRubric,
    EvalRun,
    EvalSchedulePolicy,
    EvalScore,
    EvalStrategy,
    EvalTestCase,
    EvalVersion,
)
from app.evaluation.services.runner import execute_case  # noqa: E402
from app.evaluation.worker import aggregate_run_progress, recover_pending_jobs, run_case_job_logic  # noqa: E402


@pytest_asyncio.fixture
async def _isolate(test_session: AsyncSession):
    """清理 eval_* 表（含 case_jobs）。"""
    for m in (
        EvalHumanLabel, EvalScore, EvalCaseResult, EvalCaseJob, EvalRun,
        EvalRubric, EvalDimension, EvalTestCase, EvalStrategy, EvalVersion,
        EvalSchedulePolicy, EvalJudgeModel,
    ):
        await test_session.execute(delete(m))
    await test_session.commit()
    yield


async def _make_run(test_session, total_cases: int) -> EvalRun:
    """建一条 pending run（+ strategy + version 满足 FK）。"""
    v = EvalVersion(tool_code=EVAL_TOOL_QIANCHUAN_WRITER, name=f"v{uuid.uuid4().hex[:6]}",
                    config_payload={}, is_active=True)
    s = EvalStrategy(tool_code=EVAL_TOOL_QIANCHUAN_WRITER, name=f"s{uuid.uuid4().hex[:6]}",
                     test_case_selector={}, dimension_weight_overrides={}, rubric_selector={},
                     is_active=True)
    test_session.add_all([v, s])
    await test_session.flush()
    run = EvalRun(version_id=v.id, strategy_id=s.id, name="t", trigger_type="manual",
                  status=RUN_STATUS_PENDING, filter_tags=[], total_cases=total_cases,
                  completed_cases=0, failed_cases=0, metadata_={})
    test_session.add(run)
    await test_session.commit()
    await test_session.refresh(run)
    return run


async def _make_job(test_session, run_id: int) -> EvalCaseJob:
    tc = EvalTestCase(tool_code=EVAL_TOOL_QIANCHUAN_WRITER, name=f"tc{uuid.uuid4().hex[:6]}",
                      input_payload={}, tags=[], is_active=True)
    test_session.add(tc)
    await test_session.flush()
    job = EvalCaseJob(run_id=run_id, test_case_id=tc.id, status=JOB_STATUS_PENDING)
    test_session.add(job)
    await test_session.commit()
    await test_session.refresh(job)
    return job


async def _reload(test_session, model_cls, oid):
    """重读：aggregate 用裸 SQL UPDATE 绕过 ORM，conftest expire_on_commit=False，
    用 populate_existing=True 强制覆盖缓存实例，async 安全（避免属性同步 lazy-load 触发 MissingGreenlet）。"""
    stmt = select(model_cls).where(model_cls.id == oid).execution_options(populate_existing=True)
    return (await test_session.execute(stmt)).scalars().one()


class TestAggregateRunProgress:
    async def test_success_increments_completed(self, test_session, _isolate):
        run = await _make_run(test_session, 2)
        await aggregate_run_progress(test_session, run.id, success=True)
        run = await _reload(test_session, EvalRun, run.id)
        assert run.completed_cases == 1
        assert run.failed_cases == 0
        assert run.status == RUN_STATUS_PENDING  # 未全部终态，仍 pending

    async def test_failure_increments_failed(self, test_session, _isolate):
        run = await _make_run(test_session, 2)
        await aggregate_run_progress(test_session, run.id, success=False)
        run = await _reload(test_session, EvalRun, run.id)
        assert run.failed_cases == 1
        assert run.completed_cases == 0

    async def test_finalizes_completed_when_all_terminal(self, test_session, _isolate):
        run = await _make_run(test_session, 2)
        await aggregate_run_progress(test_session, run.id, success=True)
        await aggregate_run_progress(test_session, run.id, success=True)
        run = await _reload(test_session, EvalRun, run.id)
        assert run.completed_cases == 2
        assert run.status == RUN_STATUS_COMPLETED
        assert run.finished_at is not None

    async def test_finalizes_failed_when_all_failed(self, test_session, _isolate):
        run = await _make_run(test_session, 2)
        await aggregate_run_progress(test_session, run.id, success=False)
        await aggregate_run_progress(test_session, run.id, success=False)
        run = await _reload(test_session, EvalRun, run.id)
        assert run.failed_cases == 2
        assert run.status == RUN_STATUS_FAILED


class TestRunCaseJobLogic:
    async def test_stub_marks_done_and_aggregates(self, test_session, _isolate):
        run = await _make_run(test_session, 1)
        job = await _make_job(test_session, run.id)

        result = await run_case_job_logic(test_session, job.id)
        assert "done" in result

        job = await _reload(test_session, EvalCaseJob, job.id)
        assert job.status == JOB_STATUS_DONE
        assert job.attempts == 1
        assert job.started_at is not None
        assert job.finished_at is not None
        run = await _reload(test_session, EvalRun, run.id)
        assert run.completed_cases == 1
        assert run.status == RUN_STATUS_COMPLETED  # 全部 case 终态 → completed

    async def test_idempotent_skips_terminal_job(self, test_session, _isolate):
        """job 已终态 → 再次 run_case_job_logic 跳过，不重复聚合（防 over-counting）。"""
        run = await _make_run(test_session, 1)
        job = await _make_job(test_session, run.id)
        await run_case_job_logic(test_session, job.id)             # 第一次：done + completed=1
        result = await run_case_job_logic(test_session, job.id)    # 第二次：应跳过
        assert "already terminal" in result
        run = await _reload(test_session, EvalRun, run.id)
        assert run.completed_cases == 1                            # 没有重复 +1

    async def test_failure_marks_failed_and_aggregates(self, test_session, _isolate):
        """execute 抛错 → job failed + run failed_cases+1 + re-raise（保证 run 收尾）。"""
        run = await _make_run(test_session, 1)
        job = await _make_job(test_session, run.id)

        async def _boom(db, jid):
            raise RuntimeError("generate failed")

        with pytest.raises(RuntimeError, match="generate failed"):
            await run_case_job_logic(test_session, job.id, execute=_boom)

        job = await _reload(test_session, EvalCaseJob, job.id)
        assert job.status == JOB_STATUS_FAILED
        assert job.last_error is not None
        run = await _reload(test_session, EvalRun, run.id)
        assert run.failed_cases == 1
        assert run.status == RUN_STATUS_FAILED   # 全部 failed → run failed


class TestRecoverPendingJobs:
    async def test_resets_stale_running_and_reenqueues_pending(self, test_session, _isolate):
        """卡死 running（超时）→ 重置 pending；所有 pending 重新入队（mock enqueue）。"""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        run = await _make_run(test_session, 2)
        j1 = await _make_job(test_session, run.id)   # pending
        j2 = await _make_job(test_session, run.id)   # 设成卡死 running
        j2.status = "running"
        j2.started_at = datetime.now(timezone.utc) - timedelta(days=1)
        await test_session.commit()

        enqueued: list[int] = []

        async def _enq(jid):
            enqueued.append(jid)

        with patch("app.evaluation.worker.enqueue_case_job", new=_enq):
            n = await recover_pending_jobs(test_session)
        assert n == 2  # j1(pending) + j2(被重置成 pending)
        j2r = await _reload(test_session, EvalCaseJob, j2.id)
        assert j2r.status == "pending"           # 卡死 running 被重置
        assert set(enqueued) == {j1.id, j2.id}   # 都重投

    async def test_skips_fresh_running(self, test_session, _isolate):
        """刚起的 running（未超阈值）不被重置，避免误重投还在跑的 job。"""
        from datetime import datetime, timezone
        from unittest.mock import patch

        run = await _make_run(test_session, 1)
        j = await _make_job(test_session, run.id)
        j.status = "running"
        j.started_at = datetime.now(timezone.utc)   # 刚起，未超时
        await test_session.commit()

        async def _enq(jid):
            raise AssertionError("不应重投 fresh running")

        with patch("app.evaluation.worker.enqueue_case_job", new=_enq):
            n = await recover_pending_jobs(test_session)
        assert n == 0                               # 无 pending 可重投
        jr = await _reload(test_session, EvalCaseJob, j.id)
        assert jr.status == "running"               # 未被重置


# ---------------------------------------------------------------------------
# execute_case 接线（Phase 3）：run_case_job_logic(execute=execute_case) 端到端
# ---------------------------------------------------------------------------


async def _make_dim_with_rubrics(test_session):
    """建一条 active 维度 + default 变体 rubric（供 execute_case 评分）。"""
    dim = EvalDimension(
        tool_code=EVAL_TOOL_QIANCHUAN_WRITER,
        name=f"dim{uuid.uuid4().hex[:6]}",
        display_name="dim",
        default_weight=0.4,
        score_min=1,
        score_max=10,
        prompt_template="评分 {{rubric_text}} 被评：{{generated_output}}",
        is_active=True,
    )
    test_session.add(dim)
    await test_session.flush()
    test_session.add(
        EvalRubric(
            dimension_id=dim.id, level=8, criteria="good",
            scenario_tag=None, is_active=True,
        )
    )
    await test_session.commit()
    await test_session.refresh(dim)
    return dim


def _ok_score_json(score=8):
    import json as _json
    return _json.dumps({"score": score, "reasoning": "ok", "strengths": [], "weaknesses": []})


class TestExecuteCaseWiring:
    """run_case_job_logic(execute=execute_case)：真实执行接线端到端。

    mock get_adapter → execute_case 经 adapter.chat 生成+评分。
    验证：job→done + run.completed+1 + run 收尾 completed + case_result/scores 落库。
    """

    async def test_success_persists_and_finalizes(self, test_session, _isolate):
        from unittest.mock import AsyncMock, patch
        from app.evaluation.services import runner as runner_mod

        run = await _make_run(test_session, 1)
        run_id = run.id
        await _make_dim_with_rubrics(test_session)
        job = await _make_job(test_session, run_id)
        job_id = job.id  # 调用前捕获 int（失败路径 rollback 会 expire ORM 对象）

        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = _ok_score_json(9)
        with patch.object(runner_mod, "get_adapter", return_value=mock_adapter):
            result = await run_case_job_logic(
                test_session, job_id, execute=execute_case
            )

        assert "done" in result
        job = await _reload(test_session, EvalCaseJob, job_id)
        assert job.status == JOB_STATUS_DONE
        assert job.started_at is not None
        assert job.finished_at is not None
        run = await _reload(test_session, EvalRun, run_id)
        assert run.completed_cases == 1
        assert run.failed_cases == 0
        assert run.status == RUN_STATUS_COMPLETED  # 全部 case 终态 → completed

        crs = (await test_session.execute(select(EvalCaseResult))).scalars().all()
        assert len(crs) == 1
        scs = (await test_session.execute(select(EvalScore))).scalars().all()
        assert len(scs) == 1  # 1 维 → 1 score
        assert float(scs[0].ai_score) == 9.0

    async def test_failure_marks_failed_and_aggregates(self, test_session, _isolate):
        """execute_case 抛错（LLM down）→ job failed + last_error + run.failed+1 + 收尾 failed。"""
        from unittest.mock import AsyncMock, patch
        from app.evaluation.services import runner as runner_mod

        run = await _make_run(test_session, 1)
        run_id = run.id
        await _make_dim_with_rubrics(test_session)
        job = await _make_job(test_session, run_id)
        job_id = job.id  # 调用前捕获 int（rollback 会 expire ORM 对象，事后同步读 .id 触发 MissingGreenlet）

        mock_adapter = AsyncMock()
        mock_adapter.chat.side_effect = RuntimeError("llm down")
        with patch.object(runner_mod, "get_adapter", return_value=mock_adapter):
            with pytest.raises(RuntimeError, match="llm down"):
                await run_case_job_logic(
                    test_session, job_id, execute=execute_case
                )

        job = await _reload(test_session, EvalCaseJob, job_id)
        assert job.status == JOB_STATUS_FAILED
        assert job.last_error is not None
        assert "llm down" in job.last_error
        run = await _reload(test_session, EvalRun, run_id)
        assert run.failed_cases == 1
        assert run.completed_cases == 0
        assert run.status == RUN_STATUS_FAILED  # 全部 failed → run failed
        # 失败不落 case_result（无半成品）
        crs = (await test_session.execute(select(EvalCaseResult))).scalars().all()
        assert len(crs) == 0

