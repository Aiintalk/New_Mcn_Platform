"""飞书项目—内容对标账号关系的运行时事实源合同。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIELDS = (
    "对标记录编号",
    "红人编号",
    "红人名称",
    "对标账号",
    "对标类型",
    "sec_uid",
    "同步状态",
    "最后同步时间",
)


def relation_row(
    record_id: str,
    *,
    project_id: str = "1001",
    sec_uid: str = "account-001",
    relation_type: str = "内容对标",
    status: str = "有效",
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "fields": {
            "对标记录编号": f"relation-{record_id}",
            "红人编号": project_id,
            "红人名称": "仅用于显示的匿名项目",
            "对标账号": "仅用于显示的匿名账号",
            "对标类型": relation_type,
            "sec_uid": sec_uid,
            "同步状态": status,
            "最后同步时间": "2026-09-05T00:00:00+08:00",
        },
    }


class Client:
    def __init__(self, pages, *, fields=FIELDS, fail=False):
        self.pages = pages
        self.fields = fields
        self.fail = fail
        self.tokens: list[str | None] = []

    async def authorize_read(self, app_token, table_id):
        if self.fail:
            raise PermissionError("private")

    async def list_field_names(self, app_token, table_id):
        return self.fields

    async def list_records(self, app_token, table_id, *, page_token):
        self.tokens.append(page_token)
        value = self.pages[page_token]
        if isinstance(value, Exception):
            raise value
        return value


def page(*items, more=False, token=None, total=None):
    return content_analysis.FeishuRecordPage(
        items=items,
        has_more=more,
        next_page_token=token,
        total=total,
    )


def reader(client):
    return content_analysis.FeishuRelationReader(
        client,
        content_analysis.FeishuRelationTableConfig("base", "relations"),
        clock=lambda: datetime(2026, 9, 5, 0, 5, tzinfo=SHANGHAI),
    )


@pytest.mark.asyncio
async def test_relation_reader_uses_full_table_and_stable_ids_only() -> None:
    client = Client(
        {
            None: page(
                relation_row("1"),
                relation_row("2", sec_uid="account-ignored", status="停用"),
                more=True,
                token="next",
                total=4,
            ),
            "next": page(
                relation_row("3", project_id="1002", sec_uid="account-002"),
                relation_row("4", relation_type="直播对标"),
                total=4,
            ),
        }
    )

    result = await reader(client).read()

    assert result.status is content_analysis.FeishuRelationReadStatus.COMPLETE
    assert result.checked_at == datetime(2026, 9, 5, 0, 5, tzinfo=SHANGHAI)
    assert client.tokens == [None, "next"]
    assert [(item.project_id, item.sec_uid) for item in result.relations] == [
        ("1001", "account-001"),
        ("1002", "account-002"),
    ]
    assert result.for_project("1001") == (result.relations[0],)
    assert result.for_account("account-002") == (result.relations[1],)


@pytest.mark.asyncio
async def test_complete_relation_read_can_truthfully_return_no_valid_relations() -> None:
    result = await reader(
        Client({None: page(relation_row("1", status="停用"))})
    ).read()

    assert result.status is content_analysis.FeishuRelationReadStatus.COMPLETE
    assert result.relations == ()
    assert result.error_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client",
    (
        Client({None: page()}, fields=FIELDS[:-1]),
        Client({None: page()}, fail=True),
        Client({None: RuntimeError("private row")}),
        Client({None: page(more=True, token="next"), "next": page(more=True, token="next")}),
    ),
)
async def test_relation_failure_is_not_reported_as_no_relations(client) -> None:
    result = await reader(client).read()

    assert result.status is content_analysis.FeishuRelationReadStatus.FAILED
    assert result.relations == ()
    assert result.error_reason
    assert "private" not in result.error_reason


@pytest.mark.asyncio
async def test_invalid_stable_relation_field_fails_complete_read() -> None:
    invalid = relation_row("1")
    invalid["fields"]["最后同步时间"] = "not-a-time"

    result = await reader(Client({None: page(invalid)})).read()

    assert result.status is content_analysis.FeishuRelationReadStatus.FAILED
    assert result.relations == ()


@pytest.mark.asyncio
async def test_relation_checked_at_is_captured_after_read_completes() -> None:
    completed_at = datetime(2026, 9, 5, 0, 9, tzinfo=SHANGHAI)
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return completed_at

    result = await content_analysis.FeishuRelationReader(
        Client({None: page(relation_row("1"))}),
        content_analysis.FeishuRelationTableConfig("base", "relations"),
        clock=clock,
    ).read()

    assert calls == 1
    assert result.checked_at == completed_at
