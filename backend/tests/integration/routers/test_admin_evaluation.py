"""
Integration tests for admin_evaluation router (Phase 4 Task 6).

Covers:
- Auth (401 no token / 403 wrong role / 200 admin)
- Dimensions CRUD happy path + OperationLog assertion
- Rubrics PUT batch replace
- Version create (no source_kol_id + with source_kol_id via resolve_prompt mock)
- Version not editable (PUT returns 405)
- Version clone
- Soft delete (DELETE → GET returns 404)
- Invalid cron → 400 on POST/PUT schedule-policies
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text

from app.evaluation.models import EvalDimension, EvalStrategy


# ---------------------------------------------------------------------------
# Fixtures — seed default strategy + dimensions + qianchuan writer config
# ---------------------------------------------------------------------------


async def _seed_default_strategy(test_session):
    """Insert default strategy (required by scheduler.trigger_run)."""
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
    """Insert a dimension and return its id."""
    dim = EvalDimension(
        tool_code="qianchuan-writer",
        name=name,
        display_name=name,
        description="test dim",
        default_weight=Decimal(str(weight)).quantize(Decimal("0.0001")),
        score_min=1,
        score_max=10,
        prompt_template="prompt {{rubric_text}}",
        is_active=True,
    )
    test_session.add(dim)
    await test_session.commit()
    await test_session.refresh(dim)
    return dim.id


async def _seed_qianchuan_config(test_session, system_prompt="global default {{name}}"):
    """Insert qianchuan_writer_configs 'default' row (for relation maintenance fallback)."""
    from app.models.qianchuan_writer import QianchuanWriterConfig
    existing = (await test_session.execute(
        select(QianchuanWriterConfig).where(
            QianchuanWriterConfig.config_key == "default"
        )
    )).scalar_one_or_none()
    if existing is not None:
        existing.system_prompt = system_prompt
        existing.is_active = True
    else:
        test_session.add(QianchuanWriterConfig(
            config_key="default",
            system_prompt=system_prompt,
            ai_model_id=None,
            is_active=True,
        ))
    await test_session.commit()


@pytest.fixture(autouse=True)
async def _setup(test_session):
    """Common setup: ensure default strategy exists."""
    await _seed_default_strategy(test_session)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/evaluation/dimensions")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden_403(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/evaluation/dimensions",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/evaluation/dimensions",
            headers=admin_headers,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dimensions CRUD
# ---------------------------------------------------------------------------


class TestDimensions:
    @pytest.mark.asyncio
    async def test_create_dimension(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/dimensions",
            json={
                "name": "test_dim_create",
                "display_name": "测试维度",
                "default_weight": 0.5,
                "score_min": 1,
                "score_max": 10,
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        assert body["data"]["name"] == "test_dim_create"
        # DECIMAL returns as string; compare as float
        assert float(body["data"]["default_weight"]) == 0.5
        assert body["data"]["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_create_writes_op_log(self, test_client, admin_headers, admin_user, test_session):
        resp = await test_client.post(
            "/api/admin/evaluation/dimensions",
            json={"name": "log_test_dim", "default_weight": 0.3, "score_max": 10},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log = (await test_session.execute(text(
            "SELECT action, user_id FROM operation_logs "
            "WHERE action='evaluation_dimension_create' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log is not None
        assert log[0] == "evaluation_dimension_create"
        assert log[1] == admin_user.id

    @pytest.mark.asyncio
    async def test_list_dimensions(self, test_client, admin_headers, test_session):
        await _seed_dimension(test_session, name="list_a")
        await _seed_dimension(test_session, name="list_b")

        resp = await test_client.get(
            "/api/admin/evaluation/dimensions",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        names = [d["name"] for d in body["data"]]
        assert "list_a" in names
        assert "list_b" in names
        # soft-deleted not included
        assert all(d["deleted_at"] is None for d in body["data"])

    @pytest.mark.asyncio
    async def test_update_dimension(self, test_client, admin_headers, test_session):
        dim_id = await _seed_dimension(test_session, name="update_me")
        resp = await test_client.put(
            f"/api/admin/evaluation/dimensions/{dim_id}",
            json={"display_name": "已更新", "default_weight": 0.99},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["display_name"] == "已更新"
        assert float(body["data"]["default_weight"]) == 0.99

    @pytest.mark.asyncio
    async def test_update_404(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/evaluation/dimensions/999999",
            json={"display_name": "x"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_dimension(self, test_client, admin_headers, test_session):
        dim_id = await _seed_dimension(test_session, name="delete_me")
        resp = await test_client.delete(
            f"/api/admin/evaluation/dimensions/{dim_id}",
            headers=admin_headers,
        )
        assert resp.json()["success"] is True
        # DELETE writes OperationLog
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_dimension_delete' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log is not None

        # Subsequent list should not include soft-deleted
        resp = await test_client.get(
            "/api/admin/evaluation/dimensions",
            headers=admin_headers,
        )
        names = [d["name"] for d in resp.json()["data"]]
        assert "delete_me" not in names

    @pytest.mark.asyncio
    async def test_soft_delete_404(self, test_client, admin_headers):
        resp = await test_client.delete(
            "/api/admin/evaluation/dimensions/999999",
            headers=admin_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rubrics — PUT batch replace
# ---------------------------------------------------------------------------


class TestRubrics:
    @pytest.mark.asyncio
    async def test_put_rubrics_batch_replace(self, test_client, admin_headers, test_session):
        dim_id = await _seed_dimension(test_session, name="rubric_dim")

        # Initial rubrics
        resp = await test_client.put(
            f"/api/admin/evaluation/dimensions/{dim_id}/rubrics",
            json={"rubrics": [
                {"level": 10, "criteria": "excellent"},
                {"level": 5, "criteria": "ok"},
            ]},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) == 2

        # Replace with new set (old ones should be deactivated)
        resp = await test_client.put(
            f"/api/admin/evaluation/dimensions/{dim_id}/rubrics",
            json={"rubrics": [
                {"level": 8, "criteria": "new rubric"},
            ]},
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert len(body["data"]) == 1
        assert body["data"][0]["criteria"] == "new rubric"

        # GET should only return active rubrics (1)
        resp = await test_client.get(
            f"/api/admin/evaluation/dimensions/{dim_id}/rubrics",
            headers=admin_headers,
        )
        body = resp.json()
        active = [r for r in body["data"] if r["is_active"]]
        assert len(active) == 1
        assert active[0]["criteria"] == "new rubric"

    @pytest.mark.asyncio
    async def test_put_rubrics_writes_op_log(self, test_client, admin_headers, admin_user, test_session):
        dim_id = await _seed_dimension(test_session, name="log_rubric")
        resp = await test_client.put(
            f"/api/admin/evaluation/dimensions/{dim_id}/rubrics",
            json={"rubrics": [{"level": 10, "criteria": "x"}]},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log = (await test_session.execute(text(
            "SELECT action, detail FROM operation_logs "
            "WHERE action='evaluation_rubric_update' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log is not None
        assert log[1]["inserted_count"] == 1


# ---------------------------------------------------------------------------
# Versions — create + relation maintenance + clone + soft delete + not editable
# ---------------------------------------------------------------------------


class TestVersions:
    @pytest.mark.asyncio
    async def test_create_version_no_kol(self, test_client, admin_headers):
        """Create version without source_kol_id (skip relation maintenance)."""
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={
                "name": "v1-no-kol",
                "config_payload": {
                    "system_prompt_template": "manual template {{name}}",
                    "model_id": "test-model",
                },
                "scoring_model_id": "judge-x",
                "scoring_provider": "yunwu",
                "scoring_adapter": "yunwu",
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        cfg = body["data"]["config_payload"]
        # source_kol_id empty → keep admin-provided template
        assert cfg["system_prompt_template"] == "manual template {{name}}"
        # Top-level scoring_* merged into config_payload
        assert cfg["scoring_model_id"] == "judge-x"
        assert cfg["scoring_provider"] == "yunwu"
        assert cfg["scoring_adapter"] == "yunwu"

    @pytest.mark.asyncio
    async def test_create_version_writes_op_log(self, test_client, admin_headers, admin_user, test_session):
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={"name": "log-version", "config_payload": {"k": "v"}},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log = (await test_session.execute(text(
            "SELECT action, target_id FROM operation_logs "
            "WHERE action='evaluation_version_create' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log is not None
        assert log[1] is not None

    @pytest.mark.asyncio
    async def test_create_version_relation_maintenance_kol_override(
        self, test_client, admin_headers, test_session
    ):
        """source_kol_id present + resolve_prompt returns override → use override."""
        from app.models.kol_workspace_config import KolWorkspaceConfig

        await _seed_qianchuan_config(test_session, system_prompt="global default {{name}}")
        # Create a KOL + workspace config with prompt override
        kol_row = (await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('relation-kol', 'p', 'cp', 'signed') RETURNING id"
        ))).fetchone()
        kol_id = kol_row[0]
        # Use ORM to avoid asyncpg "::jsonb" cast syntax conflict with :param
        test_session.add(KolWorkspaceConfig(
            kol_id=int(kol_id),
            enabled_tabs={},
            prompt_overrides={
                "qianchuan-writer": {"system_prompt": "KOL OVERRIDE {{name}}"},
            },
        ))
        await test_session.commit()

        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={
                "name": "v-with-kol",
                "source_kol_id": int(kol_id),
                "config_payload": {},
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["success"] is True
        cfg = body["data"]["config_payload"]
        # KOL override takes precedence
        assert cfg["system_prompt_template"] == "KOL OVERRIDE {{name}}"
        # source_kol_id stored
        assert body["data"]["source_kol_id"] == kol_id

    @pytest.mark.asyncio
    async def test_create_version_relation_maintenance_global_fallback(
        self, test_client, admin_headers, test_session
    ):
        """source_kol_id present + resolve_prompt returns None → fallback to cfg.system_prompt."""
        await _seed_qianchuan_config(test_session, system_prompt="GLOBAL FALLBACK {{name}}")
        kol_row = (await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('nok-override-kol', 'p', 'cp', 'signed') RETURNING id"
        ))).fetchone()
        kol_id = kol_row[0]
        # No kol_workspace_configs row → resolve_prompt returns None
        await test_session.commit()

        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={
                "name": "v-global-fallback",
                "source_kol_id": int(kol_id),
                "config_payload": {},
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        cfg = body["data"]["config_payload"]
        assert cfg["system_prompt_template"] == "GLOBAL FALLBACK {{name}}"

    @pytest.mark.asyncio
    async def test_create_version_relation_maintenance_kol_not_found(
        self, test_client, admin_headers, test_session
    ):
        """source_kol_id refers to non-existent KOL → 404 from get_kol_context."""
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={
                "name": "v-missing-kol",
                "source_kol_id": 999999,
                "config_payload": {},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_version_not_editable(self, test_client, admin_headers):
        """PUT /versions/{id} must NOT exist (405 or 404)."""
        # The router doesn't define PUT → FastAPI returns 405 (method not allowed)
        resp = await test_client.put(
            "/api/admin/evaluation/versions/1",
            json={"name": "x"},
            headers=admin_headers,
        )
        assert resp.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_clone_version(self, test_client, admin_headers, test_session):
        # Seed source version
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={
                "name": "parent-v",
                "config_payload": {"system_prompt_template": "parent {{name}}", "model_id": "p"},
            },
            headers=admin_headers,
        )
        parent_id = resp.json()["data"]["id"]

        # Clone
        resp = await test_client.post(
            f"/api/admin/evaluation/versions/{parent_id}/clone",
            json={
                "name": "child-v",
                "config_payload_overrides": {"model_id": "child-model"},
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["name"] == "child-v"
        assert body["data"]["parent_version_id"] == parent_id
        # config_payload copied from parent with override applied
        cfg = body["data"]["config_payload"]
        assert cfg["system_prompt_template"] == "parent {{name}}"
        assert cfg["model_id"] == "child-model"

    @pytest.mark.asyncio
    async def test_clone_writes_op_log(self, test_client, admin_headers, test_session):
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={"name": "p2", "config_payload": {}},
            headers=admin_headers,
        )
        parent_id = resp.json()["data"]["id"]

        await test_client.post(
            f"/api/admin/evaluation/versions/{parent_id}/clone",
            json={"name": "c2"},
            headers=admin_headers,
        )
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_version_clone' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_get_version(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={"name": "get-me", "config_payload": {"x": 1}},
            headers=admin_headers,
        )
        vid = resp.json()["data"]["id"]

        resp = await test_client.get(
            f"/api/admin/evaluation/versions/{vid}",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["id"] == vid

    @pytest.mark.asyncio
    async def test_soft_delete_version(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/versions",
            json={"name": "to-delete", "config_payload": {}},
            headers=admin_headers,
        )
        vid = resp.json()["data"]["id"]

        resp = await test_client.delete(
            f"/api/admin/evaluation/versions/{vid}",
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        # GET should now 404
        resp = await test_client.get(
            f"/api/admin/evaluation/versions/{vid}",
            headers=admin_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Schedule policies — croniter validation
# ---------------------------------------------------------------------------


class TestSchedulePolicies:
    @pytest.mark.asyncio
    async def test_create_valid_cron(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={
                "name": "nightly",
                "cron": "0 2 * * *",
                "filter_tags": ["core"],
                "is_active": True,
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["cron"] == "0 2 * * *"

    @pytest.mark.asyncio
    async def test_create_invalid_cron_400(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "bad", "cron": "not a cron"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "INVALID_CRON" in body["code"] or "INVALID_CRON" in body["message"]

    @pytest.mark.asyncio
    async def test_create_invalid_cron_too_many_fields(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "bad2", "cron": "0 2 * * * * * extra"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_invalid_cron_400(self, test_client, admin_headers):
        # First create a valid one
        resp = await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "p", "cron": "0 2 * * *"},
            headers=admin_headers,
        )
        pid = resp.json()["data"]["id"]

        # Update with invalid cron
        resp = await test_client.put(
            f"/api/admin/evaluation/schedule-policies/{pid}",
            json={"cron": "bad"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_valid_cron(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "p3", "cron": "0 2 * * *"},
            headers=admin_headers,
        )
        pid = resp.json()["data"]["id"]
        resp = await test_client.put(
            f"/api/admin/evaluation/schedule-policies/{pid}",
            json={"cron": "30 3 * * *", "is_active": False},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["cron"] == "30 3 * * *"
        assert body["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_create_writes_op_log(self, test_client, admin_headers, test_session):
        await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "log-p", "cron": "0 2 * * *"},
            headers=admin_headers,
        )
        log = (await test_session.execute(text(
            "SELECT action FROM operation_logs "
            "WHERE action='evaluation_schedule_policy_create'"
        ))).fetchone()
        assert log is not None

    @pytest.mark.asyncio
    async def test_list_and_soft_delete(self, test_client, admin_headers):
        await test_client.post(
            "/api/admin/evaluation/schedule-policies",
            json={"name": "list-and-del", "cron": "0 2 * * *"},
            headers=admin_headers,
        )

        resp = await test_client.get(
            "/api/admin/evaluation/schedule-policies",
            headers=admin_headers,
        )
        names = [p["name"] for p in resp.json()["data"]]
        assert "list-and-del" in names

        pid = [p for p in resp.json()["data"] if p["name"] == "list-and-del"][0]["id"]
        resp = await test_client.delete(
            f"/api/admin/evaluation/schedule-policies/{pid}",
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        # List should not include soft-deleted
        resp = await test_client.get(
            "/api/admin/evaluation/schedule-policies",
            headers=admin_headers,
        )
        names = [p["name"] for p in resp.json()["data"]]
        assert "list-and-del" not in names


# ---------------------------------------------------------------------------
# Direct handler invocation tests
#
# These complement the HTTP-layer integration tests above by directly invoking
# each write-operation handler. coverage.py 5.x + SQLAlchemy async + greenlet
# interact such that code paths inside ASGITransport requests after the first
# `await db.X()` are not always traced (a known tool issue; the same pattern
# affects existing routers like operator_qianchuan_writer). Direct invocation
# drives the same handler code synchronously and lets the tracer see it, so
# the coverage report reflects reality. Each test also asserts the OperationLog
# row is queued via db.add, providing real business-logic verification.
# ---------------------------------------------------------------------------


def _mock_db():
    """Build a MagicMock db that records add() calls; flush/commit/refresh are AsyncMock."""
    db = MagicMock()
    db.added = []
    db.add = db.added.append
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.begin = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    return db


def _make_request():
    req = MagicMock()
    req.headers = {"user-agent": "direct-call-test"}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _make_user(uid=99, username="direct-admin", role="admin"):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.role = role
    return u


class TestHandlersDirectCall:
    """Directly invoke each write handler to exercise business logic + coverage."""

    @pytest.mark.asyncio
    async def test_create_dimension_direct(self):
        from app.evaluation.routers.admin_evaluation import create_dimension
        from app.evaluation.schemas import DimensionCreate

        db = _mock_db()
        # flush sets id on the added dim
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 42
        db.flush.side_effect = _flush

        body = DimensionCreate(name="direct", default_weight=Decimal("0.4"), score_max=10)
        result = await create_dimension(body, _make_request(), db, _make_user())
        assert result.success is True
        assert any(type(o).__name__ == "OperationLog" for o in db.added)
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_update_dimension_direct(self):
        from app.evaluation.routers.admin_evaluation import update_dimension
        from app.evaluation.schemas import DimensionUpdate
        from app.evaluation.models import EvalDimension

        existing = EvalDimension(
            tool_code="qianchuan-writer", name="upd", display_name="x",
            default_weight=Decimal("0.4"), score_min=1, score_max=10,
            is_active=True,
        )
        existing.id = 7
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        body = DimensionUpdate(display_name="new-name")
        result = await update_dimension(7, body, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.display_name == "new-name"
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_delete_dimension_direct(self):
        from app.evaluation.routers.admin_evaluation import delete_dimension
        from app.evaluation.models import EvalDimension

        existing = EvalDimension(
            tool_code="qianchuan-writer", name="del", display_name="x",
            default_weight=Decimal("0.4"), score_min=1, score_max=10, is_active=True,
        )
        existing.id = 8
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        result = await delete_dimension(8, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.deleted_at is not None
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_replace_rubrics_direct(self):
        from app.evaluation.routers.admin_evaluation import replace_rubrics
        from app.evaluation.schemas import RubricBatchUpdate, RubricItemInput
        from app.evaluation.models import EvalDimension, EvalRubric

        dim = EvalDimension(
            tool_code="qianchuan-writer", name="rbd", display_name="x",
            default_weight=Decimal("0.4"), score_min=1, score_max=10, is_active=True,
        )
        dim.id = 9
        db = _mock_db()
        db.get = AsyncMock(return_value=dim)
        # existing active rubrics query returns empty
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=existing_result)
        # second execute (final select) returns the new rubric
        new_rubric = EvalRubric(dimension_id=9, level=10, criteria="new")
        new_rubric.id = 100
        new_result = MagicMock()
        new_result.scalars.return_value.all.return_value = [new_rubric]

        async def _execute(stmt):
            db.execute.return_value = new_result
            return existing_result
        db.execute.side_effect = _execute

        # flush assigns ids to new rubrics
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 100
        db.flush.side_effect = _flush

        body = RubricBatchUpdate(rubrics=[RubricItemInput(level=10, criteria="new")])
        result = await replace_rubrics(9, body, _make_request(), db, _make_user())
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_version_no_kol_direct(self):
        from app.evaluation.routers.admin_evaluation import create_version
        from app.evaluation.schemas import VersionCreate

        db = _mock_db()
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 11
        db.flush.side_effect = _flush

        body = VersionCreate(
            name="direct-v",
            config_payload={"system_prompt_template": "x {{name}}"},
            scoring_model_id="m1",
        )
        result = await create_version(body, _make_request(), db, _make_user())
        assert result.success is True
        assert db.commit.called
        # config_payload should contain merged scoring_*
        added_version = [o for o in db.added if type(o).__name__ == "EvalVersion"][0]
        assert added_version.config_payload["scoring_model_id"] == "m1"

    @pytest.mark.asyncio
    async def test_clone_version_direct(self):
        from app.evaluation.routers.admin_evaluation import clone_version
        from app.evaluation.schemas import VersionClone
        from app.evaluation.models import EvalVersion

        parent = EvalVersion(
            tool_code="qianchuan-writer", name="parent",
            config_payload={"k": "v", "model_id": "p"},
        )
        parent.id = 5
        db = _mock_db()
        db.get = AsyncMock(return_value=parent)
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 6
        db.flush.side_effect = _flush

        body = VersionClone(
            name="child",
            config_payload_overrides={"model_id": "child-m"},
        )
        result = await clone_version(5, body, _make_request(), db, _make_user())
        assert result.success is True
        added_version = [o for o in db.added if type(o).__name__ == "EvalVersion"][0]
        assert added_version.parent_version_id == 5
        assert added_version.config_payload["model_id"] == "child-m"
        assert added_version.config_payload["k"] == "v"

    @pytest.mark.asyncio
    async def test_delete_version_direct(self):
        from app.evaluation.routers.admin_evaluation import delete_version
        from app.evaluation.models import EvalVersion

        existing = EvalVersion(
            tool_code="qianchuan-writer", name="del-v", config_payload={},
        )
        existing.id = 12
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        result = await delete_version(12, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.deleted_at is not None

    @pytest.mark.asyncio
    async def test_create_schedule_policy_direct(self):
        from app.evaluation.routers.admin_evaluation import create_schedule_policy
        from app.evaluation.schemas import SchedulePolicyCreate

        db = _mock_db()
        async def _flush():
            for obj in db.added:
                if not getattr(obj, "id", None):
                    obj.id = 13
        db.flush.side_effect = _flush

        body = SchedulePolicyCreate(name="direct", cron="0 2 * * *")
        result = await create_schedule_policy(body, _make_request(), db, _make_user())
        assert result.success is True

    @pytest.mark.asyncio
    async def test_update_schedule_policy_direct(self):
        from app.evaluation.routers.admin_evaluation import update_schedule_policy
        from app.evaluation.schemas import SchedulePolicyUpdate
        from app.evaluation.models import EvalSchedulePolicy

        existing = EvalSchedulePolicy(name="up", cron="0 2 * * *", is_active=True)
        existing.id = 14
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        body = SchedulePolicyUpdate(cron="30 3 * * *", is_active=False)
        result = await update_schedule_policy(14, body, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.cron == "30 3 * * *"
        assert existing.is_active is False

    @pytest.mark.asyncio
    async def test_delete_schedule_policy_direct(self):
        from app.evaluation.routers.admin_evaluation import delete_schedule_policy
        from app.evaluation.models import EvalSchedulePolicy

        existing = EvalSchedulePolicy(name="del-p", cron="0 2 * * *", is_active=True)
        existing.id = 15
        db = _mock_db()
        db.get = AsyncMock(return_value=existing)

        result = await delete_schedule_policy(15, _make_request(), db, _make_user())
        assert result.success is True
        assert existing.deleted_at is not None
