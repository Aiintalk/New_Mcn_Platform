"""
Unit tests for ORM models - column defaults, nullable constraints, types.
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy import BigInteger, Integer, String, Text, Boolean

from app.models.user import User
from app.models.workspace import WorkspaceTool
from app.models.task import TaskJob, TaskLog
from app.models.output import Output
from app.models.credential import ServiceCredential, Credential, AiModel
from app.models.kol_intake import (
    KolIntakeQuestion,
    KolIntakeConfig,
    KolIntakeLink,
    KolIntakeOperatorSession,
    KolIntakeSubmission,
)


def _get_columns(model_class) -> dict:
    return {c.key: c for c in model_class.__table__.columns}


def _get_column(model_class, col_name: str):
    columns = _get_columns(model_class)
    if col_name not in columns:
        raise KeyError(f"Column {col_name!r} not found on {model_class.__tablename__}")
    return columns[col_name]


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class TestUserModel:
    def test_default_role_is_operator(self):
        col = _get_column(User, "role")
        assert col.default is not None
        assert col.default.arg == "operator"

    def test_default_status_is_enabled(self):
        col = _get_column(User, "status")
        assert col.default is not None
        assert col.default.arg == "enabled"

    def test_default_token_version_is_zero(self):
        col = _get_column(User, "token_version")
        assert col.default is not None
        assert col.default.arg == 0

    def test_password_changed_at_is_nullable(self):
        col = _get_column(User, "password_changed_at")
        assert col.nullable is True

    def test_deleted_at_is_nullable(self):
        col = _get_column(User, "deleted_at")
        assert col.nullable is True

    def test_last_login_at_is_nullable(self):
        col = _get_column(User, "last_login_at")
        assert col.nullable is True

    def test_created_by_is_nullable(self):
        col = _get_column(User, "created_by")
        assert col.nullable is True

    def test_id_is_big_integer(self):
        col = _get_column(User, "id")
        assert isinstance(col.type, BigInteger)

    def test_tablename(self):
        assert User.__tablename__ == "users"


# ---------------------------------------------------------------------------
# WorkspaceTool model
# ---------------------------------------------------------------------------


class TestWorkspaceToolModel:
    def test_default_status_is_dev(self):
        col = _get_column(WorkspaceTool, "status")
        assert col.default is not None
        assert col.default.arg == "dev"

    def test_default_sort_order_is_zero(self):
        col = _get_column(WorkspaceTool, "sort_order")
        assert col.default is not None
        assert col.default.arg == 0

    def test_tool_code_is_unique(self):
        col = _get_column(WorkspaceTool, "tool_code")
        assert col.unique is True

    def test_tags_is_jsonb(self):
        col = _get_column(WorkspaceTool, "tags")
        assert isinstance(col.type, JSONB)

    def test_config_is_jsonb(self):
        col = _get_column(WorkspaceTool, "config")
        assert isinstance(col.type, JSONB)

    def test_tablename(self):
        assert WorkspaceTool.__tablename__ == "workspace_tools"


# ---------------------------------------------------------------------------
# TaskJob / TaskLog models
# ---------------------------------------------------------------------------


class TestTaskJobModel:
    def test_task_no_is_unique(self):
        col = _get_column(TaskJob, "task_no")
        assert col.unique is True

    def test_default_status_is_pending(self):
        col = _get_column(TaskJob, "status")
        assert col.default is not None
        assert col.default.arg == "pending"

    def test_input_payload_is_jsonb(self):
        col = _get_column(TaskJob, "input_payload")
        assert isinstance(col.type, JSONB)

    def test_tablename(self):
        assert TaskJob.__tablename__ == "task_jobs"


class TestTaskLogModel:
    def test_task_id_is_foreign_key(self):
        col = _get_column(TaskLog, "task_id")
        assert col.foreign_keys is not None

    def test_payload_is_jsonb(self):
        col = _get_column(TaskLog, "payload")
        assert isinstance(col.type, JSONB)

    def test_tablename(self):
        assert TaskLog.__tablename__ == "task_logs"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class TestOutputModel:
    def test_deleted_at_is_nullable(self):
        col = _get_column(Output, "deleted_at")
        assert col.nullable is True

    def test_content_json_is_jsonb(self):
        col = _get_column(Output, "content_json")
        assert isinstance(col.type, JSONB)

    def test_tablename(self):
        assert Output.__tablename__ == "outputs"


# ---------------------------------------------------------------------------
# Credential models
# ---------------------------------------------------------------------------


class TestServiceCredentialModel:
    def test_config_is_jsonb(self):
        col = _get_column(ServiceCredential, "config")
        assert isinstance(col.type, JSONB)

    def test_default_status_is_enabled(self):
        col = _get_column(ServiceCredential, "status")
        assert col.default is not None
        assert col.default.arg == "enabled"

    def test_secret_tail_is_not_nullable(self):
        col = _get_column(ServiceCredential, "secret_tail")
        assert col.nullable is False

    def test_tablename(self):
        assert ServiceCredential.__tablename__ == "service_credentials"


class TestCredentialModel:
    def test_tablename(self):
        assert Credential.__tablename__ == "credentials"


class TestAiModelModel:
    def test_model_id_is_unique(self):
        col = _get_column(AiModel, "model_id")
        assert col.unique is True

    def test_tablename(self):
        assert AiModel.__tablename__ == "ai_models"


# ---------------------------------------------------------------------------
# KolIntake models
# ---------------------------------------------------------------------------


class TestKolIntakeQuestionModel:
    def test_default_question_type_is_text(self):
        col = _get_column(KolIntakeQuestion, "question_type")
        assert col.default is not None
        assert col.default.arg == "text"

    def test_default_is_required_is_true(self):
        col = _get_column(KolIntakeQuestion, "is_required")
        assert col.default is not None
        assert col.default.arg is True

    def test_default_is_active_is_true(self):
        col = _get_column(KolIntakeQuestion, "is_active")
        assert col.default is not None
        assert col.default.arg is True

    def test_tablename(self):
        assert KolIntakeQuestion.__tablename__ == "kol_intake_questions"


class TestKolIntakeConfigModel:
    def test_config_key_is_unique(self):
        col = _get_column(KolIntakeConfig, "config_key")
        assert col.unique is True

    def test_system_prompt_is_nullable(self):
        col = _get_column(KolIntakeConfig, "system_prompt")
        assert col.nullable is True

    def test_tablename(self):
        assert KolIntakeConfig.__tablename__ == "kol_intake_configs"


class TestKolIntakeLinkModel:
    def test_token_is_unique(self):
        col = _get_column(KolIntakeLink, "token")
        assert col.unique is True

    def test_used_at_is_nullable(self):
        col = _get_column(KolIntakeLink, "used_at")
        assert col.nullable is True

    def test_submitted_at_is_nullable(self):
        col = _get_column(KolIntakeLink, "submitted_at")
        assert col.nullable is True

    def test_tablename(self):
        assert KolIntakeLink.__tablename__ == "kol_intake_links"


class TestKolIntakeSubmissionModel:
    def test_messages_is_jsonb(self):
        col = _get_column(KolIntakeSubmission, "messages")
        assert isinstance(col.type, JSONB)

    def test_default_report_status_is_pending(self):
        col = _get_column(KolIntakeSubmission, "report_status")
        assert col.default is not None
        assert col.default.arg == "pending"

    def test_ai_report_raw_is_jsonb(self):
        col = _get_column(KolIntakeSubmission, "ai_report_raw")
        assert isinstance(col.type, JSONB)

    def test_kol_downloaded_at_is_nullable(self):
        col = _get_column(KolIntakeSubmission, "kol_downloaded_at")
        assert col.nullable is True

    def test_link_id_is_unique(self):
        col = _get_column(KolIntakeSubmission, "link_id")
        assert col.unique is True

    def test_tablename(self):
        assert KolIntakeSubmission.__tablename__ == "kol_intake_submissions"


class TestKolIntakeOperatorSessionModel:
    def test_messages_is_jsonb(self):
        col = _get_column(KolIntakeOperatorSession, "messages")
        assert isinstance(col.type, JSONB)

    def test_default_report_status_is_pending(self):
        col = _get_column(KolIntakeOperatorSession, "report_status")
        assert col.default is not None
        assert col.default.arg == "pending"

    def test_tablename(self):
        assert KolIntakeOperatorSession.__tablename__ == "kol_intake_operator_sessions"
