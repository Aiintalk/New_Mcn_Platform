"""把飞书多维表格的完整只读结果映射为内容分析内部输入。"""
import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from .deterministic import deduplicate_contents
from .domain import (
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    SyncStatus,
)
from .engine import (
    AccountSyncResult,
    ReadSource,
    SyncCoverageWindow,
    SyncIssue,
    SyncIssueImpact,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class FeishuContentTableConfig:
    """非敏感的飞书多维表格定位；鉴权凭据由客户端自行注入。"""

    app_token: str
    table_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.app_token, str) or not self.app_token.strip():
            raise ValueError("app_token 必须是非空文本")
        if not isinstance(self.table_id, str) or not self.table_id.strip():
            raise ValueError("table_id 必须是非空文本")


@dataclass(frozen=True)
class FeishuRecordPage:
    """飞书客户端返回的一页记录及明确分页结束信息。"""

    items: tuple[Mapping[str, Any], ...]
    has_more: bool = False
    next_page_token: str | None = None
    total: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise ValueError("飞书分页记录必须是不可变元组")
        if any(not isinstance(item, Mapping) for item in self.items):
            raise ValueError("飞书分页记录必须是对象")
        if type(self.has_more) is not bool:
            raise ValueError("has_more 必须是原生布尔值")
        if self.next_page_token is not None and (
            not isinstance(self.next_page_token, str)
            or not self.next_page_token.strip()
        ):
            raise ValueError("下一页游标必须是非空文本或空值")
        if self.has_more and self.next_page_token is None:
            raise ValueError("仍有下一页时必须提供下一页游标")
        if self.total is not None and (type(self.total) is not int or self.total < 0):
            raise ValueError("记录总数必须是非负整数或空值")


class FeishuReadonlyClient(Protocol):
    """只读客户端边界；真实鉴权和网络实现由运行环境注入。"""

    async def authorize_read(self, app_token: str, table_id: str) -> None:
        """验证当前客户端能只读访问目标表。"""

        ...

    async def list_field_names(
        self,
        app_token: str,
        table_id: str,
    ) -> tuple[str, ...]:
        """返回目标表当前字段名。"""

        ...

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> FeishuRecordPage:
        """只读获取一页记录。"""

        ...


_REQUIRED_FIELDS = frozenset(
    {
        "SecUid",
        "视频ID",
        "视频标题",
        "字幕全文",
        "发布时间",
        "同步时间",
        "点赞",
        "评论",
        "分享",
        "收藏",
    }
)


class _FeishuReadFailure(RuntimeError):
    public_reason = "飞书读取失败"


class _FeishuAuthorizationFailure(_FeishuReadFailure):
    public_reason = "飞书只读鉴权失败"


class _FeishuFieldFailure(_FeishuReadFailure):
    public_reason = "飞书字段校验失败"


class _FeishuPaginationFailure(_FeishuReadFailure):
    public_reason = "飞书分页读取未完成"


class _FeishuTimeoutFailure(_FeishuReadFailure):
    public_reason = "飞书读取超时"


def _plain_text(value: object, field_name: str, *, optional: bool) -> str | None:
    if value is None or value == "":
        if optional:
            return None
        raise _FeishuFieldFailure(f"{field_name} 不能为空")
    if isinstance(value, str):
        result = value.strip()
    elif isinstance(value, Mapping):
        candidate = value.get("text")
        if not isinstance(candidate, str):
            raise _FeishuFieldFailure(f"{field_name} 类型错误")
        result = candidate.strip()
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        parts = [
            _plain_text(item, field_name, optional=False)
            for item in value
        ]
        result = "".join(item for item in parts if item).strip()
    else:
        raise _FeishuFieldFailure(f"{field_name} 类型错误")
    if not result:
        if optional:
            return None
        raise _FeishuFieldFailure(f"{field_name} 不能为空")
    return result


def _link(value: object, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        result = value.strip()
    elif isinstance(value, Mapping):
        candidate = value.get("link", value.get("url"))
        if not isinstance(candidate, str):
            raise _FeishuFieldFailure(f"{field_name} 类型错误")
        result = candidate.strip()
    else:
        raise _FeishuFieldFailure(f"{field_name} 类型错误")
    if not result:
        return None
    return result


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) in (int, float):
        numeric = float(value)
        if not isfinite(numeric):
            raise _FeishuFieldFailure(f"{field_name} 不是合法时间")
        seconds = numeric / 1000 if abs(numeric) >= 100_000_000_000 else numeric
        try:
            return datetime.fromtimestamp(seconds, tz=SHANGHAI)
        except (OverflowError, OSError, ValueError) as exc:
            raise _FeishuFieldFailure(f"{field_name} 不是合法时间") from exc
    if not isinstance(value, str) or not value.strip():
        raise _FeishuFieldFailure(f"{field_name} 不是合法时间")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise _FeishuFieldFailure(f"{field_name} 不是合法时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _FeishuFieldFailure(f"{field_name} 必须带时区")
    return parsed.astimezone(SHANGHAI)


def _metric(value: object, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if type(value) is int:
        result = value
    elif type(value) is float and isfinite(value) and value.is_integer():
        result = int(value)
    elif isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized.isdigit():
            raise _FeishuFieldFailure(f"{field_name} 不是非负整数")
        result = int(normalized)
    else:
        raise _FeishuFieldFailure(f"{field_name} 不是非负整数")
    if result < 0:
        raise _FeishuFieldFailure(f"{field_name} 不是非负整数")
    return result


def _record(raw_record: Mapping[str, Any]) -> ContentRecord:
    fields = raw_record.get("fields")
    if not isinstance(fields, Mapping):
        raise _FeishuFieldFailure("飞书记录 fields 必须是对象")
    return ContentRecord(
        account_id=_plain_text(fields.get("SecUid"), "SecUid", optional=False),
        source=ContentSource.PLATFORM_SYNC,
        identity=ContentIdentity(
            platform_content_id=_plain_text(
                fields.get("视频ID"),
                "视频ID",
                optional=False,
            ),
            external_url=_link(fields.get("播放链接"), "播放链接"),
        ),
        published_at=_timestamp(fields.get("发布时间"), "发布时间"),
        captured_at=_timestamp(fields.get("同步时间"), "同步时间"),
        metrics=EngagementMetrics(
            like_count=_metric(fields.get("点赞"), "点赞"),
            comment_count=_metric(fields.get("评论"), "评论"),
            share_count=_metric(fields.get("分享"), "分享"),
            favorite_count=_metric(fields.get("收藏"), "收藏"),
        ),
        title=_plain_text(fields.get("视频标题"), "视频标题", optional=True),
        transcript=_plain_text(fields.get("字幕全文"), "字幕全文", optional=True),
        operations_review_url=_link(fields.get("内网播放"), "内网播放"),
    )


class FeishuContentReader:
    """完整读取飞书后，按任务账号和窗口派生内部四态结果。"""

    def __init__(
        self,
        client: FeishuReadonlyClient,
        config: FeishuContentTableConfig,
        *,
        clock: Callable[[], datetime],
        request_timeout_seconds: float = 30,
        max_pages: int = 1000,
    ) -> None:
        if (
            type(request_timeout_seconds) not in (int, float)
            or not isfinite(request_timeout_seconds)
            or request_timeout_seconds <= 0
        ):
            raise ValueError("飞书单次只读请求超时必须是正数")
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("飞书分页上限必须是正整数")
        self._client = client
        self._config = config
        self._clock = clock
        self._request_timeout_seconds = float(request_timeout_seconds)
        self._max_pages = max_pages

    def _failed_results(
        self,
        account_ids: tuple[str, ...],
        coverage_window: SyncCoverageWindow,
        reason: str,
    ) -> tuple[AccountSyncResult, ...]:
        checked_at = self._checked_at()
        return tuple(
            AccountSyncResult(
                account_id=account_id,
                status=SyncStatus.FAILED,
                issue=SyncIssue(
                    affected_account_ids=(account_id,),
                    affected_window=coverage_window,
                    impact=SyncIssueImpact.CONTENT_UNAVAILABLE,
                    reason=reason,
                ),
                checked_at=checked_at,
                coverage_window=coverage_window,
                read_source=ReadSource.FEISHU,
            )
            for account_id in account_ids
        )

    def _checked_at(self) -> datetime:
        checked_at = self._clock()
        if (
            not isinstance(checked_at, datetime)
            or checked_at.tzinfo is None
            or checked_at.utcoffset() is None
        ):
            raise ValueError("飞书读取完成时间必须带时区")
        return checked_at.astimezone(SHANGHAI)

    @staticmethod
    def _validate_request(
        account_ids: tuple[str, ...],
        coverage_window: SyncCoverageWindow,
    ) -> None:
        if not isinstance(account_ids, tuple) or not account_ids:
            raise ValueError("任务账号必须是非空不可变元组")
        if any(
            not isinstance(account_id, str) or not account_id.strip()
            for account_id in account_ids
        ):
            raise ValueError("任务账号必须是非空文本")
        if any(account_id != account_id.strip() for account_id in account_ids):
            raise ValueError("任务账号不能包含首尾空格")
        if len(set(account_ids)) != len(account_ids):
            raise ValueError("任务账号不能重复")
        if not isinstance(coverage_window, SyncCoverageWindow):
            raise ValueError("分析窗口必须使用 SyncCoverageWindow")

    async def _validate_source(self) -> None:
        try:
            await asyncio.wait_for(
                self._client.authorize_read(
                    self._config.app_token,
                    self._config.table_id,
                ),
                timeout=self._request_timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise _FeishuTimeoutFailure from exc
        except Exception as exc:
            raise _FeishuAuthorizationFailure from exc
        try:
            field_names = await asyncio.wait_for(
                self._client.list_field_names(
                    self._config.app_token,
                    self._config.table_id,
                ),
                timeout=self._request_timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise _FeishuTimeoutFailure from exc
        except Exception as exc:
            raise _FeishuFieldFailure("字段清单读取失败") from exc
        if not isinstance(field_names, tuple) or any(
            not isinstance(item, str) for item in field_names
        ):
            raise _FeishuFieldFailure("字段清单类型错误")
        if _REQUIRED_FIELDS - set(field_names):
            raise _FeishuFieldFailure("缺少必需字段")

    async def _read_pages(self) -> tuple[Mapping[str, Any], ...]:
        records: list[Mapping[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        seen_record_ids: set[str] = set()
        expected_total: int | None = None
        page_count = 0
        while True:
            page_count += 1
            try:
                page = await asyncio.wait_for(
                    self._client.list_records(
                        self._config.app_token,
                        self._config.table_id,
                        page_token=page_token,
                    ),
                    timeout=self._request_timeout_seconds,
                )
            except (asyncio.TimeoutError, TimeoutError) as exc:
                raise _FeishuTimeoutFailure from exc
            except Exception as exc:
                raise _FeishuReadFailure from exc
            if not isinstance(page, FeishuRecordPage):
                raise _FeishuPaginationFailure("分页响应类型错误")
            if page.total is not None:
                if expected_total is None:
                    expected_total = page.total
                elif expected_total != page.total:
                    raise _FeishuPaginationFailure("分页记录总数不一致")
            for item in page.items:
                record_id = item.get("record_id")
                if not isinstance(record_id, str) or not record_id.strip():
                    raise _FeishuPaginationFailure("分页记录缺少稳定行编号")
                if record_id in seen_record_ids:
                    raise _FeishuPaginationFailure("分页记录出现重复行编号")
                seen_record_ids.add(record_id)
            records.extend(page.items)
            if not page.has_more:
                if page.next_page_token is not None:
                    raise _FeishuPaginationFailure("分页结束时仍返回下一页游标")
                if expected_total is not None and len(records) != expected_total:
                    raise _FeishuPaginationFailure("分页记录数量与总数不一致")
                return tuple(records)
            if page_count >= self._max_pages:
                raise _FeishuPaginationFailure("分页超过安全上限仍未结束")
            next_token = page.next_page_token
            if next_token is None or next_token in seen_tokens:
                raise _FeishuPaginationFailure("分页游标缺失或重复")
            seen_tokens.add(next_token)
            page_token = next_token

    @staticmethod
    def _map_records(
        raw_records: tuple[Mapping[str, Any], ...],
        checked_at: datetime,
        account_ids: tuple[str, ...],
        coverage_window: SyncCoverageWindow,
    ) -> tuple[ContentRecord, ...]:
        try:
            requested = set(account_ids)
            selected_records: list[Mapping[str, Any]] = []
            for raw_record in raw_records:
                fields = raw_record.get("fields")
                if not isinstance(fields, Mapping):
                    raise _FeishuFieldFailure("飞书记录 fields 必须是对象")
                account_id = _plain_text(
                    fields.get("SecUid"),
                    "SecUid",
                    optional=False,
                )
                if account_id not in requested:
                    continue
                published_at = _timestamp(fields.get("发布时间"), "发布时间")
                if (
                    coverage_window.start <= published_at < coverage_window.end
                ):
                    selected_records.append(raw_record)
            records = tuple(_record(item) for item in selected_records)
            if any(
                record.published_at > record.captured_at
                or record.captured_at > checked_at
                for record in records
            ):
                raise _FeishuFieldFailure("发布时间、采集时间或读取完成时间顺序错误")
            return records
        except (TypeError, ValueError, _FeishuFieldFailure) as exc:
            raise _FeishuFieldFailure("记录字段映射失败") from exc

    def _successful_results(
        self,
        records: tuple[ContentRecord, ...],
        account_ids: tuple[str, ...],
        coverage_window: SyncCoverageWindow,
        checked_at: datetime,
    ) -> tuple[AccountSyncResult, ...]:
        requested = set(account_ids)
        by_account: dict[str, list[ContentRecord]] = defaultdict(list)
        for record in records:
            if (
                record.account_id in requested
                and coverage_window.start <= record.published_at < coverage_window.end
            ):
                by_account[record.account_id].append(record)
        return tuple(
            AccountSyncResult(
                account_id=account_id,
                status=(
                    SyncStatus.SUCCESS_WITH_CONTENT
                    if contents
                    else SyncStatus.SUCCESS_WITHOUT_CONTENT
                ),
                contents=contents,
                checked_at=checked_at,
                coverage_window=coverage_window,
                read_source=ReadSource.FEISHU,
            )
            for account_id in account_ids
            for contents in (tuple(deduplicate_contents(by_account[account_id])),)
        )

    async def read_accounts(
        self,
        account_ids: tuple[str, ...],
        coverage_window: SyncCoverageWindow,
    ) -> tuple[AccountSyncResult, ...]:
        """完整读取成功才生成有内容或无内容结果，任何中断都返回失败。"""
        self._validate_request(account_ids, coverage_window)
        try:
            await self._validate_source()
            raw_records = await self._read_pages()
            checked_at = self._checked_at()
            records = self._map_records(
                raw_records,
                checked_at,
                account_ids,
                coverage_window,
            )
        except _FeishuReadFailure as exc:
            return self._failed_results(
                account_ids,
                coverage_window,
                exc.public_reason,
            )
        return self._successful_results(
            records,
            account_ids,
            coverage_window,
            checked_at,
        )
