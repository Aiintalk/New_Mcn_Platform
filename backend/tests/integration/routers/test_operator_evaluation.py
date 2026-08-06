"""
Integration tests for operator_evaluation router (Phase 4 Task 6).

Covers:
- Auth (401 / 403 / 200 operator+admin)
- Test cases CRUD + soft delete
- Run trigger (mock adapter to avoid real AI / credentials)
- Run status / scores list
- Human label single-transaction atomicity
- Compare endpoint returns ComparisonReport structure
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text

from app.evaluation.models import (
    EvalCaseJob,
    EvalCaseResult,
    EvalDimension,
    EvalHumanLabel,
    EvalRun,
    EvalScore,
    EvalStrategy,
    EvalTestCase,
    EvalVersion,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


async def _seed_default_strategy(test_session):
    existing = (await test_session.execute(
        select(EvalStrategy).where(
            EvalStrategy.tool_code == "qianchuan-writer",
            EvalStrategy.name == "default",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing.id
    strategy = EvalStrategy(
        tool_code="qianchuan-writer",
        name="default",
        description="test default",
        test_case_selector={"all": True},
        dimension_weight_overrides={},
        rubric_selector={},
        is_active=True,
    )
    test_session.add(strategy)
    await test_session.commit()
    await test_session.refresh(strategy)
    return strategy.id


async def _seed_dimension(test_session, name="copy_quality", weight=0.4):
    dim = EvalDimension(
        tool_code="qianchuan-writer",
        name=name,
        display_name=name,
        description="test dim",
        default_weight=Decimal(str(weight)).quantize(Decimal("0.0001")),
        score_min=1,
        score_max=10,
        prompt_template=(
            "请评分。标准：{{rubric_text}}\n脚本：{{generated_output}}\n"
            "返回JSON：{\"score\":int, \"reasoning\":str, \"strengths\":[], \"weaknesses\":[]}"
        ),
        is_active=True,
    )
    test_session.add(dim)
    await test_session.commit()
    await test_session.refresh(dim)
    return dim.id


async def _seed_rubric(test_session, dimension_id, level=10, criteria="满分标准"):
    from app.evaluation.models import EvalRubric
    rubric = EvalRubric(
        dimension_id=dimension_id,
        level=level,
        criteria=criteria,
        scenario_tag=None,
        is_active=True,
    )
    test_session.add(rubric)
    await test_session.commit()
    return rubric.id


async def _seed_test_case(test_session, name="case1", tags=None):
    tc = EvalTestCase(
        tool_code="qianchuan-writer",
        name=name,
        description="test case",
        input_payload={
            "name": "达人A",
            "persona": "人设A",
            "content_plan": "计划A",
            "product_info": "产品A",
        },
        tags=list(tags or []),
        is_active=True,
    )
    test_session.add(tc)
    await test_session.commit()
    await test_session.refresh(tc)
    return tc.id


async def _seed_version(test_session, name="v1"):
    version = EvalVersion(
        tool_code="qianchuan-writer",
        name=name,
        description=None,
        config_payload={
            "system_prompt_template": "写一段 {{name}} {{persona}} {{content_plan}}",
            "model_id": "test-model",
            "provider": "yunwu",
        },
        parent_version_id=None,
        source_kol_id=None,
        auto_run_on_create=False,
        auto_run_tags=[],
        is_active=True,
    )
    test_session.add(version)
    await test_session.commit()
    await test_session.refresh(version)
    return version.id


async def _seed_run(
    test_session, version_id, strategy_id, *, name="run",
    status="completed", total_cases=1, completed_cases=1, failed_cases=0,
):
    run = EvalRun(
        version_id=version_id, strategy_id=strategy_id, name=name,
        trigger_type="manual", status=status, filter_tags=[],
        total_cases=total_cases, completed_cases=completed_cases,
        failed_cases=failed_cases, metadata_={},
    )
    test_session.add(run)
    await test_session.commit()
    await test_session.refresh(run)
    return run.id


async def _seed_job(test_session, run_id, test_case_id, status="pending"):
    job = EvalCaseJob(run_id=run_id, test_case_id=test_case_id, status=status)
    test_session.add(job)
    await test_session.commit()
    await test_session.refresh(job)
    return job.id


@pytest.fixture(autouse=True)
async def _setup(test_session):
    """Common setup: ensure default strategy + one dimension + rubric."""
    await _seed_default_strategy(test_session)


def _mock_adapter_chat(*, gen_output="生成文本", score_json=None):
    """Build a mock AsyncMock for YunwuAdapter.chat.

    Generates deterministic output: first call returns gen_output,
    subsequent calls return score JSON (so runner can use same chat for both).
    """
    score_json = score_json or '{"score": 8, "reasoning": "ok", "strengths": ["a"], "weaknesses": ["b"]}'
    state = {"count": 0}

    async def _chat(*args, **kwargs):
        state["count"] += 1
        messages = kwargs.get("messages") or (args[0] if args else None)
        # Heuristic: system message → generation; user message → scoring
        if messages and len(messages) > 0:
            role = messages[0].get("role", "system")
            if role == "system":
                return gen_output
        return score_json

    return AsyncMock(side_effect=_chat)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/evaluation/test-cases")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_can_access(self, test_client, admin_headers):
        # admin role should also pass require_operator (admin in [operator, admin])
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases",
            headers=operator_headers,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test cases CRUD
# ---------------------------------------------------------------------------


class TestTestCases:
    @pytest.mark.asyncio
    async def test_create_test_case(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/evaluation/test-cases",
            json={
                "name": "case-create",
                "input_payload": {"name": "k", "persona": "p"},
                "tags": ["core"],
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["name"] == "case-create"
        assert body["data"]["tags"] == ["core"]
        assert body["data"]["input_payload"]["persona"] == "p"

    @pytest.mark.asyncio
    async def test_create_writes_op_log(self, test_client, operator_headers, test_session):
        await test_client.post(
            "/api/operator/evaluation/test-cases",
            json={"name": "log-case", "input_payload": {}},
            headers=operator_headers,
        )
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_test_case_create'"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_list_pagination(self, test_client, operator_headers, test_session):
        for i in range(15):
            await _seed_test_case(test_session, name=f"p-case-{i:02d}")

        # page_size must be in {10, 20, 50}; test with 10
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases?page=1&page_size=10",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["pagination"]["page_size"] == 10
        assert body["data"]["pagination"]["total"] >= 15
        assert len(body["data"]["items"]) <= 10
        assert body["data"]["pagination"]["total_pages"] >= 2

    @pytest.mark.asyncio
    async def test_list_invalid_page_size_clamped(self, test_client, operator_headers):
        """page_size not in {10, 20, 50} should be clamped to 20."""
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases?page=1&page_size=2",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["data"]["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_update_test_case(self, test_client, operator_headers, test_session):
        tc_id = await _seed_test_case(test_session, name="update-case")
        resp = await test_client.put(
            f"/api/operator/evaluation/test-cases/{tc_id}",
            json={"name": "updated", "tags": ["new-tag"]},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "updated"
        assert body["data"]["tags"] == ["new-tag"]

    @pytest.mark.asyncio
    async def test_update_404(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/operator/evaluation/test-cases/999999",
            json={"name": "x"},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_test_case(self, test_client, operator_headers, test_session):
        tc_id = await _seed_test_case(test_session, name="del-case")
        resp = await test_client.delete(
            f"/api/operator/evaluation/test-cases/{tc_id}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

        # List should not include soft-deleted
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases",
            headers=operator_headers,
        )
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert "del-case" not in names

    @pytest.mark.asyncio
    async def test_get_test_case_single(self, test_client, operator_headers, test_session):
        tc_id = await _seed_test_case(test_session, name="single-tc")
        resp = await test_client.get(
            f"/api/operator/evaluation/test-cases/{tc_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["id"] == tc_id
        assert body["data"]["name"] == "single-tc"

    @pytest.mark.asyncio
    async def test_get_test_case_404(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/test-cases/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Versions (read-only)
# ---------------------------------------------------------------------------


class TestVersionsReadOnly:
    @pytest.mark.asyncio
    async def test_list_versions(self, test_client, operator_headers, test_session):
        await _seed_version(test_session, name="v-op-1")
        resp = await test_client.get(
            "/api/operator/evaluation/versions",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        names = [v["name"] for v in body["data"]]
        assert "v-op-1" in names


# ---------------------------------------------------------------------------
# Runs — trigger (mocked adapter) + status + scores
# ---------------------------------------------------------------------------


class TestRuns:
    @pytest.fixture(autouse=True)
    def _mock_enqueue(self):
        """trigger 现异步 enqueue 到 redis；mock 掉避免依赖/污染 redis（worker 不在测试内跑）。"""
        with patch("app.evaluation.services.scheduler.enqueue_case_job", new_callable=AsyncMock):
            yield

    @pytest.mark.asyncio
    async def test_trigger_run_mocked(self, test_client, operator_headers, test_session):
        """异步触发：建 run(pending) + jobs，立即返回（不执行）。"""
        dim_id = await _seed_dimension(test_session, name="run-dim")
        await _seed_rubric(test_session, dim_id, level=10)
        await _seed_test_case(test_session, name="run-case")
        version_id = await _seed_version(test_session, name="run-version")

        resp = await test_client.post(
            "/api/operator/evaluation/runs",
            json={"version_id": int(version_id), "filter_tags": []},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        run_data = body["data"]
        assert run_data["status"] == "pending"   # 异步：未执行，仍 pending
        assert run_data["version_id"] == version_id
        assert run_data["total_cases"] >= 1      # 解析到 test_case（跨测试库可能有累积，不强断精确值）

    @pytest.mark.asyncio
    async def test_trigger_run_no_version_id_400(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/evaluation/runs",
            json={"filter_tags": []},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_trigger_run_writes_op_log(self, test_client, operator_headers, test_session):
        dim_id = await _seed_dimension(test_session, name="log-run-dim")
        await _seed_rubric(test_session, dim_id, level=10)
        await _seed_test_case(test_session, name="log-run-case")
        version_id = await _seed_version(test_session, name="log-run-version")

        with patch(
            "app.evaluation.adapters.yunwu.YunwuAdapter.chat",
            new=_mock_adapter_chat(),
        ):
            await test_client.post(
                "/api/operator/evaluation/runs",
                json={"version_id": int(version_id)},
                headers=operator_headers,
            )

        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_run_trigger'"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_get_run_and_scores(self, test_client, operator_headers, test_session):
        """GET run 详情 + scores（直接 seed 一个 completed run + 评分，解耦于触发执行）。"""
        dim_id = await _seed_dimension(test_session, name="get-run-dim")
        tc_id = await _seed_test_case(test_session, name="get-run-case")
        version_id = await _seed_version(test_session, name="get-run-version")
        strategy_id = await _seed_default_strategy(test_session)

        run = EvalRun(
            version_id=version_id, strategy_id=strategy_id, name="get-run",
            trigger_type="manual", status="completed", filter_tags=[],
            total_cases=1, completed_cases=1, failed_cases=0, metadata_={},
        )
        test_session.add(run)
        await test_session.flush()
        cr = EvalCaseResult(
            run_id=run.id, test_case_id=tc_id, generated_output="out",
            output_payload={}, input_snapshot={},
        )
        test_session.add(cr)
        await test_session.flush()
        score = EvalScore(
            case_result_id=cr.id, dimension_id=dim_id, ai_score=Decimal("9.0"),
            ai_reasoning="good", weight_used=Decimal("0.5"),
        )
        test_session.add(score)
        await test_session.commit()
        run_id = run.id

        # GET run status
        resp = await test_client.get(
            f"/api/operator/evaluation/runs/{run_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["id"] == run_id
        assert body["data"]["status"] == "completed"

        # GET scores
        resp = await test_client.get(
            f"/api/operator/evaluation/runs/{run_id}/scores",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        scores = body["data"]
        assert len(scores) >= 1
        assert float(scores[0]["ai_score"]) == 9.0

    @pytest.mark.asyncio
    async def test_get_run_404(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/runs/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_run_eta(self, test_client, operator_headers, test_session):
        """get_run 返回 ETA：done job 平均耗时 × pending 数。"""
        from datetime import datetime, timedelta, timezone

        vid = await _seed_version(test_session, name="eta-v")
        sid = await _seed_default_strategy(test_session)
        tc1 = await _seed_test_case(test_session, name="eta-tc1")
        tc2 = await _seed_test_case(test_session, name="eta-tc2")
        tc3 = await _seed_test_case(test_session, name="eta-tc3")
        run_id = await _seed_run(test_session, vid, sid, name="eta-run", status="running")

        # 1 done（耗时 ~60s）+ 2 pending
        j_done = EvalCaseJob(run_id=run_id, test_case_id=tc1, status="done")
        j_done.started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        j_done.finished_at = datetime.now(timezone.utc)
        test_session.add(j_done)
        test_session.add(EvalCaseJob(run_id=run_id, test_case_id=tc2, status="pending"))
        test_session.add(EvalCaseJob(run_id=run_id, test_case_id=tc3, status="pending"))
        await test_session.commit()

        data = (await test_client.get(
            f"/api/operator/evaluation/runs/{run_id}", headers=operator_headers
        )).json()["data"]
        assert data["avg_case_duration_secs"] is not None   # ~60s
        assert 55 <= data["avg_case_duration_secs"] <= 65
        assert data["eta_secs"] is not None                  # 2 pending × ~60 = ~120s
        assert 110 <= data["eta_secs"] <= 130


class TestRunsList:
    """GET /runs 列表（分页 + status/version_id 过滤 + 权限 + 信封）。"""

    @pytest.mark.asyncio
    async def test_list_pagination(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="list-v")
        sid = await _seed_default_strategy(test_session)
        for i in range(15):
            await _seed_run(test_session, vid, sid, name=f"list-r-{i:02d}")

        resp = await test_client.get(
            "/api/operator/evaluation/runs?page=1&page_size=10",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        assert body["data"]["pagination"]["page_size"] == 10
        assert body["data"]["pagination"]["total"] >= 15
        assert len(body["data"]["items"]) <= 10
        assert body["data"]["pagination"]["total_pages"] >= 2
        # id 倒序（最新在前）
        ids = [it["id"] for it in body["data"]["items"]]
        assert ids == sorted(ids, reverse=True)

    @pytest.mark.asyncio
    async def test_list_status_filter(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="filt-v")
        sid = await _seed_default_strategy(test_session)
        await _seed_run(test_session, vid, sid, name="filt-pend", status="pending", total_cases=0, completed_cases=0)
        await _seed_run(test_session, vid, sid, name="filt-done", status="completed")

        resp = await test_client.get(
            "/api/operator/evaluation/runs?status=completed",
            headers=operator_headers,
        )
        body = resp.json()
        # 过滤生效：返回的都是 completed（DB 跨测试可能累积，只验过滤约束）
        assert all(it["status"] == "completed" for it in body["data"]["items"])
        assert "filt-done" in [it["name"] for it in body["data"]["items"]]

    @pytest.mark.asyncio
    async def test_list_version_filter(self, test_client, operator_headers, test_session):
        sid = await _seed_default_strategy(test_session)
        va = await _seed_version(test_session, name="vfa")
        vb = await _seed_version(test_session, name="vfb")
        await _seed_run(test_session, va, sid, name="run-vfa")
        await _seed_run(test_session, vb, sid, name="run-vfb")

        resp = await test_client.get(
            f"/api/operator/evaluation/runs?version_id={va}",
            headers=operator_headers,
        )
        body = resp.json()
        assert all(it["version_id"] == va for it in body["data"]["items"])
        assert "run-vfa" in [it["name"] for it in body["data"]["items"]]

    @pytest.mark.asyncio
    async def test_list_page_size_clamp(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/runs?page=1&page_size=2",
            headers=operator_headers,
        )
        assert resp.json()["data"]["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_list_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/evaluation/runs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_envelope(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/runs",
            headers=operator_headers,
        )
        body = resp.json()
        assert set(body.keys()) >= {"success", "code", "message", "data"}
        assert set(body["data"].keys()) >= {"items", "pagination"}
        assert set(body["data"]["pagination"].keys()) >= {"page", "page_size", "total", "total_pages"}


class TestRunsCancel:
    """POST /runs/{id}/cancel：pending job 标 cancelled + run 收尾 cancelled。worker 不参与。"""

    async def _job_statuses(self, test_session, run_id):
        rows = (await test_session.execute(
            text("SELECT status FROM eval_case_jobs WHERE run_id = :r ORDER BY id"),
            {"r": run_id},
        )).all()
        return [r[0] for r in rows]

    @pytest.mark.asyncio
    async def test_cancel_pending_run_marks_jobs_and_run(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="cancel-v")
        sid = await _seed_default_strategy(test_session)
        run_id = await _seed_run(test_session, vid, sid, name="cancel-run", status="pending", total_cases=3, completed_cases=0)
        # UNIQUE(run_id, test_case_id) → 每 job 一个独立 test_case
        for i in range(3):
            tc_id = await _seed_test_case(test_session, name=f"cancel-case-{i}")
            await _seed_job(test_session, run_id, tc_id, status="pending")

        resp = await test_client.post(
            f"/api/operator/evaluation/runs/{run_id}/cancel",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["status"] == "cancelled"
        assert body["data"]["finished_at"] is not None
        # pending jobs → cancelled
        assert all(s == "cancelled" for s in await self._job_statuses(test_session, run_id))

    @pytest.mark.asyncio
    async def test_cancel_writes_op_log(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="cancellog-v")
        sid = await _seed_default_strategy(test_session)
        run_id = await _seed_run(test_session, vid, sid, name="cancellog-run", status="running")
        await test_client.post(
            f"/api/operator/evaluation/runs/{run_id}/cancel",
            headers=operator_headers,
        )
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs WHERE action='evaluation_run_cancel'"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_cancel_only_pending_jobs_untouched_running_done(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="cancelmix-v")
        sid = await _seed_default_strategy(test_session)
        run_id = await _seed_run(test_session, vid, sid, name="cancelmix-run", status="running", total_cases=3, completed_cases=1)
        # UNIQUE(run_id, test_case_id) → 每 job 一个独立 test_case
        tc_pend = await _seed_test_case(test_session, name="cancelmix-pend")
        tc_run = await _seed_test_case(test_session, name="cancelmix-run")
        tc_done = await _seed_test_case(test_session, name="cancelmix-done")
        await _seed_job(test_session, run_id, tc_pend, status="pending")
        await _seed_job(test_session, run_id, tc_run, status="running")
        await _seed_job(test_session, run_id, tc_done, status="done")

        await test_client.post(
            f"/api/operator/evaluation/runs/{run_id}/cancel",
            headers=operator_headers,
        )
        statuses = await self._job_statuses(test_session, run_id)
        assert statuses.count("cancelled") == 1   # 只 pending → cancelled
        assert statuses.count("running") == 1     # 在跑的不动
        assert statuses.count("done") == 1         # 已完成的不动

    @pytest.mark.asyncio
    async def test_cancel_404(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/evaluation/runs/999999/cancel",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_terminal_409(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="cancel409-v")
        sid = await _seed_default_strategy(test_session)
        run_id = await _seed_run(test_session, vid, sid, name="cancel409-run", status="completed")
        resp = await test_client.post(
            f"/api/operator/evaluation/runs/{run_id}/cancel",
            headers=operator_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_no_token_401(self, test_client):
        resp = await test_client.post("/api/operator/evaluation/runs/1/cancel")
        assert resp.status_code == 401


class TestRunCaseResults:
    """GET /runs/{id}/case-results：case 生成结果（generated_output + 真实样本名）。"""

    @pytest.mark.asyncio
    async def test_returns_case_results_with_output(self, test_client, operator_headers, test_session):
        vid = await _seed_version(test_session, name="cr-v")
        sid = await _seed_default_strategy(test_session)
        tc_id = await _seed_test_case(test_session, name="真实样本A")
        run_id = await _seed_run(test_session, vid, sid, name="cr-run", status="completed")
        test_session.add(EvalCaseResult(
            run_id=run_id, test_case_id=tc_id, generated_output="这是 kimi 生成的文案",
            output_payload={"text": "..."}, input_snapshot={"name": "达人"},
        ))
        await test_session.commit()

        resp = await test_client.get(
            f"/api/operator/evaluation/runs/{run_id}/case-results",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        items = body["data"]
        assert any(it["generated_output"] == "这是 kimi 生成的文案" for it in items)
        assert any(it["test_case_name"] == "真实样本A" for it in items)  # join 出真实样本名

    @pytest.mark.asyncio
    async def test_case_results_404(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/evaluation/runs/999999/case-results",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_case_results_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/evaluation/runs/1/case-results")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Human label — single-transaction atomicity
# ---------------------------------------------------------------------------


class TestHumanLabel:
    @pytest.mark.asyncio
    async def test_submit_human_label_atomic(
        self, test_client, operator_headers, test_session
    ):
        """Human-label writes (① score update + ② history + ③ op_log) atomically.

        Within single db.commit: all three succeed together.
        """
        # Seed a complete chain: version + run + case_result + score
        dim_id = await _seed_dimension(test_session, name="hl-dim")
        version_id = await _seed_version(test_session, name="hl-version")
        tc_id = await _seed_test_case(test_session, name="hl-case")

        run = EvalRun(
            version_id=version_id,
            strategy_id=await _seed_default_strategy(test_session),
            name="hl-run",
            trigger_type="manual",
            status="completed",
            filter_tags=[],
            total_cases=1,
            completed_cases=1,
            failed_cases=0,
            metadata_={"resolved_scoring": {"model_id": "x", "provider": "yunwu", "adapter": "yunwu"}},
        )
        test_session.add(run)
        await test_session.flush()
        cr = EvalCaseResult(
            run_id=run.id,
            test_case_id=tc_id,
            generated_output="out",
            output_payload={},
            input_snapshot={},
        )
        test_session.add(cr)
        await test_session.flush()
        score = EvalScore(
            case_result_id=cr.id,
            dimension_id=dim_id,
            ai_score=Decimal("7.0"),
            ai_reasoning="",
            weight_used=Decimal("0.5"),
        )
        test_session.add(score)
        await test_session.commit()
        await test_session.refresh(score)

        # Submit human label
        resp = await test_client.put(
            f"/api/operator/evaluation/scores/{score.id}/human-label",
            json={"human_score": 9, "human_feedback": "非常好"},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        assert float(body["data"]["human_score"]) == 9.0
        assert body["data"]["human_feedback"] == "非常好"

        # Verify history row written
        history = (await test_session.execute(
            select(EvalHumanLabel).where(EvalHumanLabel.score_id == score.id)
        )).scalars().all()
        assert len(history) == 1
        assert float(history[0].new_score) == 9.0

        # Verify OperationLog written
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_human_label_submit'"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_human_label_404(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/operator/evaluation/scores/999999/human-label",
            json={"human_score": 5},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_human_label_can_be_overwritten(
        self, test_client, operator_headers, test_session
    ):
        """Second calibration overwrites first; both history rows kept."""
        dim_id = await _seed_dimension(test_session, name="hl2-dim")
        version_id = await _seed_version(test_session, name="hl2-version")
        tc_id = await _seed_test_case(test_session, name="hl2-case")

        run = EvalRun(
            version_id=version_id,
            strategy_id=await _seed_default_strategy(test_session),
            name="hl2-run",
            trigger_type="manual",
            status="completed",
            filter_tags=[],
            total_cases=1,
            completed_cases=1,
            failed_cases=0,
            metadata_={},
        )
        test_session.add(run)
        await test_session.flush()
        cr = EvalCaseResult(
            run_id=run.id, test_case_id=tc_id, generated_output="o",
            output_payload={}, input_snapshot={},
        )
        test_session.add(cr)
        await test_session.flush()
        score = EvalScore(
            case_result_id=cr.id, dimension_id=dim_id,
            ai_score=Decimal("5.0"), ai_reasoning="", weight_used=Decimal("0.5"),
        )
        test_session.add(score)
        await test_session.commit()
        await test_session.refresh(score)

        # First calibration
        await test_client.put(
            f"/api/operator/evaluation/scores/{score.id}/human-label",
            json={"human_score": 6},
            headers=operator_headers,
        )
        # Second calibration
        resp = await test_client.put(
            f"/api/operator/evaluation/scores/{score.id}/human-label",
            json={"human_score": 8},
            headers=operator_headers,
        )
        assert resp.json()["success"] is True
        assert float(resp.json()["data"]["human_score"]) == 8.0

        # History should have 2 rows
        history = (await test_session.execute(
            select(EvalHumanLabel).where(EvalHumanLabel.score_id == score.id)
        )).scalars().all()
        assert len(history) == 2


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


class TestCompare:
    @pytest.mark.asyncio
    async def test_compare_structure(self, test_client, operator_headers, test_session):
        """Compare endpoint returns ComparisonReport structure."""
        # Build two runs with one score each (same test_case → same dim)
        dim_id = await _seed_dimension(test_session, name="cmp-dim")
        version_id = await _seed_version(test_session, name="cmp-version")
        tc_id = await _seed_test_case(test_session, name="cmp-case")
        strategy_id = await _seed_default_strategy(test_session)

        # run_a: score 7
        run_a = EvalRun(
            version_id=version_id, strategy_id=strategy_id, name="a",
            trigger_type="manual", status="completed", filter_tags=[],
            total_cases=1, completed_cases=1, failed_cases=0, metadata_={},
        )
        run_b = EvalRun(
            version_id=version_id, strategy_id=strategy_id, name="b",
            trigger_type="manual", status="completed", filter_tags=[],
            total_cases=1, completed_cases=1, failed_cases=0, metadata_={},
        )
        test_session.add_all([run_a, run_b])
        await test_session.flush()

        cr_a = EvalCaseResult(run_id=run_a.id, test_case_id=tc_id, generated_output="oa",
                              output_payload={}, input_snapshot={})
        cr_b = EvalCaseResult(run_id=run_b.id, test_case_id=tc_id, generated_output="ob",
                              output_payload={}, input_snapshot={})
        test_session.add_all([cr_a, cr_b])
        await test_session.flush()
        test_session.add_all([
            EvalScore(case_result_id=cr_a.id, dimension_id=dim_id,
                      ai_score=Decimal("7.0"), ai_reasoning="", weight_used=Decimal("0.5")),
            EvalScore(case_result_id=cr_b.id, dimension_id=dim_id,
                      ai_score=Decimal("9.0"), ai_reasoning="", weight_used=Decimal("0.5")),
        ])
        await test_session.commit()

        resp = await test_client.get(
            f"/api/operator/evaluation/compare?run_a={run_a.id}&run_b={run_b.id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        data = body["data"]
        # Structure assertion
        assert data["run_a_id"] == run_a.id
        assert data["run_b_id"] == run_b.id
        assert "overall_avg_a" in data
        assert "overall_avg_b" in data
        assert "overall_delta" in data
        assert isinstance(data["dimension_deltas"], list)
        assert isinstance(data["case_deltas"], list)
        assert "summary" in data

        # run_b (9) - run_a (7) = +2 (improvement)
        assert data["overall_delta"] == pytest.approx(2.0, abs=0.01)
        # one case improved (same → up)
        assert data["summary"]["up"] == 1

    @pytest.mark.asyncio
    async def test_compare_run_not_found_404(self, test_client, operator_headers, test_session):
        version_id = await _seed_version(test_session, name="cmp-version-2")
        run = EvalRun(
            version_id=version_id,
            strategy_id=await _seed_default_strategy(test_session),
            name="existing",
            trigger_type="manual", status="completed", filter_tags=[],
            total_cases=0, completed_cases=0, failed_cases=0, metadata_={},
        )
        test_session.add(run)
        await test_session.commit()

        resp = await test_client.get(
            f"/api/operator/evaluation/compare?run_a={run.id}&run_b=999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Direct handler invocation tests
#
# Complements HTTP-layer integration tests by directly invoking handlers.
# coverage.py 5.x + SQLAlchemy async + greenlet interact such that code paths
# inside ASGITransport requests after the first `await db.X()` may not be
# traced (known tool issue affecting existing routers too). Direct invocation
# drives handler code synchronously and lets the tracer see it. Each test also
# asserts real business-logic invariants (e.g. OperationLog row is queued).
# ---------------------------------------------------------------------------


def _mock_db():
    db = MagicMock()
    db.added = []
    db.add = db.added.append
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def _make_request():
    req = MagicMock()
    req.headers = {"user-agent": "direct-call-test"}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _make_user(uid=88, username="direct-op", role="operator"):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.role = role
    return u


class TestHandlersDirectCall:
    """Directly invoke each operator handler to exercise business logic + coverage."""

    @pytest.mark.asyncio
    async def test_create_test_case_direct(self):
        from app.evaluation.routers.operator_evaluation import create_test_case
        from app.evaluation.schemas import TestCaseCreate

        db = _mock_db()
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 21
        db.flush.side_effect = _flush

        body = TestCaseCreate(name="direct-case", input_payload={"k": "v"}, tags=["t"])
        result = await create_test_case(body, _make_request(), db, _make_user())
        assert result.success is True
        assert any(type(o).__name__ == "OperationLog" for o in db.added)

    @pytest.mark.asyncio
    async def test_update_test_case_direct(self):
        from app.evaluation.routers.operator_evaluation import update_test_case
        from app.evaluation.schemas import TestCaseUpdate

        existing = EvalTestCase(
            tool_code="qianchuan-writer", name="upd-case",
            input_payload={}, tags=[], is_active=True,
        )
        existing.id = 22
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        body = TestCaseUpdate(name="new-name")
        result = await update_test_case(22, body, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.name == "new-name"

    @pytest.mark.asyncio
    async def test_delete_test_case_direct(self):
        from app.evaluation.routers.operator_evaluation import delete_test_case

        existing = EvalTestCase(
            tool_code="qianchuan-writer", name="del-case",
            input_payload={}, tags=[], is_active=True,
        )
        existing.id = 23
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        result = await delete_test_case(23, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.deleted_at is not None

    @pytest.mark.asyncio
    async def test_submit_human_label_direct(self):
        """Verify single-transaction atomicity via direct invocation."""
        from app.evaluation.routers.operator_evaluation import submit_human_label
        from app.evaluation.schemas import HumanLabelRequest

        score = EvalScore(
            case_result_id=1, dimension_id=1,
            ai_score=Decimal("5.0"), weight_used=Decimal("0.5"),
        )
        score.id = 24
        db = _mock_db()
        db.get = AsyncMock(return_value=score)

        body = HumanLabelRequest(human_score=Decimal("8.0"), human_feedback="good")
        result = await submit_human_label(24, body, _make_request(), db, _make_user())
        assert result.success is True
        assert float(score.human_score) == 8.0
        # Both EvalHumanLabel and OperationLog added in same commit
        types_added = {type(o).__name__ for o in db.added}
        assert "EvalHumanLabel" in types_added
        assert "OperationLog" in types_added
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_trigger_run_direct(self):
        """Directly invoke trigger_run handler (mocked scheduler)."""
        from app.evaluation.routers.operator_evaluation import trigger_run

        db = _mock_db()
        with patch(
            "app.evaluation.services.scheduler.trigger_run",
            new=AsyncMock(return_value=42),
        ):
            # Mock run returned by db.get
            mock_run = EvalRun(
                version_id=1, strategy_id=1, name="r",
                trigger_type="manual", status="pending", filter_tags=[],
                total_cases=0, completed_cases=0, failed_cases=0, metadata_={},
            )
            mock_run.id = 42
            db.get = AsyncMock(return_value=mock_run)

            body = {"version_id": 1, "filter_tags": []}
            result = await trigger_run(body, _make_request(), db, _make_user())
        assert result.success is True
        # OperationLog for evaluation_run_trigger queued before scheduler call
        assert any(
            type(o).__name__ == "OperationLog" and getattr(o, "action", "") == "evaluation_run_trigger"
            for o in db.added
        )

    @pytest.mark.asyncio
    async def test_trigger_run_missing_version_id_400(self):
        from app.evaluation.routers.operator_evaluation import trigger_run
        from fastapi import HTTPException

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await trigger_run({"filter_tags": []}, _make_request(), db, _make_user())
        assert exc.value.status_code == 400
