"""从正式项目表读取内容分析可用的项目上下文。"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kol import Kol

from .domain import ProjectContextVersion, ProjectFact


@dataclass(frozen=True)
class ProjectContextLoad:
    """项目上下文与明确的数据缺口。"""

    context: ProjectContextVersion
    input_limited: bool
    limitation_codes: tuple[str, ...]
    project_name: str


def _optional_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_project_context(kol: object) -> ProjectContextLoad:
    """只映射当前正式字段；目标用户和经营方向缺失时保持空值。"""
    project_id = getattr(kol, "id", None)
    if type(project_id) is not int or project_id <= 0:
        raise ValueError("项目编号无效")
    project_name = _optional_text(getattr(kol, "name", None))
    if not project_name:
        raise ValueError("项目名称不能为空")
    persona = _optional_text(getattr(kol, "persona", None))
    content_plan = _optional_text(getattr(kol, "content_plan", None))
    if not persona or not content_plan:
        raise ValueError("项目上下文必须同时具备人设和内容规划")
    effective_at = getattr(kol, "updated_at", None)
    if (
        not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or effective_at.utcoffset() is None
    ):
        raise ValueError("项目上下文版本时间缺失或无时区")
    version_payload = {
        "project_id": str(project_id),
        "project_name": project_name,
        "persona": persona,
        "content_plan": content_plan,
        "updated_at": effective_at.isoformat(),
    }
    version = hashlib.sha256(
        json.dumps(
            version_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    facts = tuple(
        ProjectFact(key=key, value=value)
        for key, value in (
            ("project_persona", persona),
            ("content_plan", content_plan),
        )
        if value
    )
    limitation_codes = (
        "TARGET_USERS_MISSING",
        "OPERATING_DIRECTION_MISSING",
    )
    return ProjectContextLoad(
        context=ProjectContextVersion(
            project_id=str(project_id),
            version=version,
            effective_at=effective_at,
            project_persona=persona,
            target_users="",
            content_plan=content_plan,
            operating_direction="",
            confirmed_facts=facts,
        ),
        input_limited=True,
        limitation_codes=limitation_codes,
        project_name=project_name,
    )


class ProjectContextReader(Protocol):
    """执行服务读取已校验项目上下文的边界。"""

    async def load(self, project_id: str) -> ProjectContextLoad:
        ...


class SqlProjectContextReader:
    """从 kols 正式项目记录读取当前上下文。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, project_id: str) -> ProjectContextLoad:
        try:
            numeric_id = int(project_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("项目编号必须是整数文本") from exc
        row = await self._session.scalar(
            select(Kol).where(
                Kol.id == numeric_id,
                Kol.deleted_at.is_(None),
            )
        )
        if row is None:
            raise LookupError("项目不存在或未入驻")
        return build_project_context(row)
