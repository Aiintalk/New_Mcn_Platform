"""飞书项目—内容对标账号关系表的完整只读适配器。"""
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .feishu_adapter import (
    FeishuReadonlyClient,
    FeishuRecordPage,
    _plain_text,
    _timestamp,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
REQUIRED_FIELDS = frozenset(
    {
        "对标记录编号",
        "红人编号",
        "红人名称",
        "对标账号",
        "对标类型",
        "sec_uid",
        "同步状态",
        "最后同步时间",
    }
)


class FeishuRelationReadStatus(str, Enum):
    """关系事实源读取状态。"""

    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class FeishuRelationTableConfig:
    """由部署环境注入的关系表位置。"""

    app_token: str
    table_id: str

    def __post_init__(self) -> None:
        for field_name in ("app_token", "table_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} 必须是非空文本")


@dataclass(frozen=True)
class FeishuRelationRecord:
    """运行时有效的内容对标关系。"""

    relation_id: str
    project_id: str
    sec_uid: str
    project_name: str | None
    account_name: str | None
    source_updated_at: datetime


@dataclass(frozen=True)
class FeishuRelationReadResult:
    """完整读取或明确失败，不用空集合掩盖读取失败。"""

    status: FeishuRelationReadStatus
    checked_at: datetime
    relations: tuple[FeishuRelationRecord, ...] = ()
    error_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is FeishuRelationReadStatus.COMPLETE:
            if self.error_reason is not None:
                raise ValueError("完整关系读取不能携带错误")
        elif self.relations:
            raise ValueError("关系读取失败时不能携带关系")

    def for_project(self, project_id: str) -> tuple[FeishuRelationRecord, ...]:
        return tuple(item for item in self.relations if item.project_id == project_id)

    def for_account(self, sec_uid: str) -> tuple[FeishuRelationRecord, ...]:
        return tuple(item for item in self.relations if item.sec_uid == sec_uid)


class FeishuRelationReader:
    """完整读取关系表，只保留有效的内容对标关系。"""

    def __init__(
        self,
        client: FeishuReadonlyClient,
        config: FeishuRelationTableConfig,
        *,
        clock: Callable[[], datetime],
        request_timeout_seconds: float = 30,
        max_pages: int = 1000,
    ) -> None:
        if type(request_timeout_seconds) not in (int, float) or not isfinite(
            request_timeout_seconds
        ) or request_timeout_seconds <= 0:
            raise ValueError("飞书关系读取超时必须是正数")
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("飞书关系分页上限必须是正整数")
        self._client = client
        self._config = config
        self._clock = clock
        self._timeout = float(request_timeout_seconds)
        self._max_pages = max_pages

    def _checked_at(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("飞书关系读取完成时间必须带时区")
        return value.astimezone(SHANGHAI)

    async def _call(self, awaitable, reason: str):
        try:
            return await asyncio.wait_for(awaitable, timeout=self._timeout)
        except Exception as exc:
            raise RuntimeError(reason) from exc

    async def _records(self) -> tuple[Mapping[str, Any], ...]:
        records: list[Mapping[str, Any]] = []
        seen_tokens: set[str] = set()
        seen_ids: set[str] = set()
        token: str | None = None
        expected_total: int | None = None
        for _ in range(self._max_pages):
            page = await self._call(
                self._client.list_records(
                    self._config.app_token,
                    self._config.table_id,
                    page_token=token,
                ),
                "飞书关系记录读取失败",
            )
            if not isinstance(page, FeishuRecordPage):
                raise RuntimeError("飞书关系分页响应类型错误")
            if page.total is not None:
                if expected_total is None:
                    expected_total = page.total
                elif expected_total != page.total:
                    raise RuntimeError("飞书关系分页总数不一致")
            for item in page.items:
                record_id = item.get("record_id")
                if not isinstance(record_id, str) or not record_id.strip():
                    raise RuntimeError("飞书关系记录缺少稳定行编号")
                if record_id in seen_ids:
                    raise RuntimeError("飞书关系分页出现重复记录")
                seen_ids.add(record_id)
                records.append(item)
            if not page.has_more:
                if page.next_page_token is not None:
                    raise RuntimeError("飞书关系分页结束状态矛盾")
                if expected_total is not None and len(records) != expected_total:
                    raise RuntimeError("飞书关系分页未完整读取")
                return tuple(records)
            next_token = page.next_page_token
            if next_token is None or next_token in seen_tokens:
                raise RuntimeError("飞书关系分页游标中断")
            seen_tokens.add(next_token)
            token = next_token
        raise RuntimeError("飞书关系分页超过安全上限")

    @staticmethod
    def _map(raw_records: tuple[Mapping[str, Any], ...]) -> tuple[FeishuRelationRecord, ...]:
        relations: list[FeishuRelationRecord] = []
        seen: set[tuple[str, str]] = set()
        for raw in raw_records:
            fields = raw.get("fields")
            if not isinstance(fields, Mapping):
                raise ValueError("飞书关系 fields 必须是对象")
            relation_type = _plain_text(fields.get("对标类型"), "对标类型", optional=False)
            status = _plain_text(fields.get("同步状态"), "同步状态", optional=False)
            if relation_type != "内容对标" or status != "有效":
                continue
            project_id = _plain_text(fields.get("红人编号"), "红人编号", optional=False)
            sec_uid = _plain_text(fields.get("sec_uid"), "sec_uid", optional=False)
            key = (project_id, sec_uid)
            if key in seen:
                continue
            seen.add(key)
            relations.append(
                FeishuRelationRecord(
                    relation_id=_plain_text(
                        fields.get("对标记录编号"),
                        "对标记录编号",
                        optional=False,
                    ),
                    project_id=project_id,
                    sec_uid=sec_uid,
                    project_name=_plain_text(
                        fields.get("红人名称"),
                        "红人名称",
                        optional=True,
                    ),
                    account_name=_plain_text(
                        fields.get("对标账号"),
                        "对标账号",
                        optional=True,
                    ),
                    source_updated_at=_timestamp(
                        fields.get("最后同步时间"),
                        "最后同步时间",
                    ),
                )
            )
        return tuple(relations)

    async def read(self) -> FeishuRelationReadResult:
        try:
            await self._call(
                self._client.authorize_read(
                    self._config.app_token,
                    self._config.table_id,
                ),
                "飞书关系表只读鉴权失败",
            )
            fields = await self._call(
                self._client.list_field_names(
                    self._config.app_token,
                    self._config.table_id,
                ),
                "飞书关系字段读取失败",
            )
            if not isinstance(fields, tuple) or any(
                not isinstance(item, str) for item in fields
            ):
                raise RuntimeError("飞书关系字段清单类型错误")
            if REQUIRED_FIELDS - set(fields):
                raise RuntimeError("飞书关系表缺少必需字段")
            relations = self._map(await self._records())
        except Exception:
            return FeishuRelationReadResult(
                status=FeishuRelationReadStatus.FAILED,
                checked_at=self._checked_at(),
                error_reason="飞书关系表读取失败",
            )
        return FeishuRelationReadResult(
            status=FeishuRelationReadStatus.COMPLETE,
            checked_at=self._checked_at(),
            relations=relations,
        )
