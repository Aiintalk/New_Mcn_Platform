"""v1.8 飞书只读内容适配器的字段、分页与执行状态合同。"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")
WINDOW = content_analysis.SyncCoverageWindow(
    start=datetime(2026, 9, 1, tzinfo=SHANGHAI),
    end=datetime(2026, 9, 4, tzinfo=SHANGHAI),
)
CHECKED_AT = datetime(2026, 9, 4, 0, 5, tzinfo=SHANGHAI)
REQUIRED_FIELDS = (
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
    "博主",
    "播放链接",
    "内网播放",
)


def row(
    work_id: str,
    *,
    account_id: str = "account-001",
    published_at: int = 1788278400000,
    captured_at: int = 1788451200000,
    transcript: str | None = "先说问题，再给方法",
    external_url: str | None = None,
    review_url: str | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "SecUid": account_id,
        "视频ID": work_id,
        "视频标题": [{"text": "匿名标题"}],
        "字幕全文": transcript,
        "发布时间": published_at,
        "同步时间": captured_at,
        "点赞": "12",
        "评论": 3.0,
        "分享": "",
        "收藏": None,
        "播放": 999999,
        "视频类型": "人设",
        "同步类型": "成功",
    }
    if external_url is not None:
        fields["播放链接"] = {"link": external_url, "text": "查看原内容"}
    if review_url is not None:
        fields["内网播放"] = review_url
    return {"record_id": f"record-{work_id}", "fields": fields}


class FakeFeishuClient:
    def __init__(
        self,
        pages: dict[str | None, object],
        *,
        fields: tuple[str, ...] = REQUIRED_FIELDS,
        auth_error: Exception | None = None,
        fields_error: Exception | None = None,
    ) -> None:
        self.pages = pages
        self.fields = fields
        self.auth_error = auth_error
        self.fields_error = fields_error
        self.page_tokens: list[str | None] = []

    async def authorize_read(self, app_token: str, table_id: str) -> None:
        assert app_token == "base-token"
        assert table_id == "table-id"
        if self.auth_error:
            raise self.auth_error

    async def list_field_names(
        self,
        app_token: str,
        table_id: str,
    ) -> tuple[str, ...]:
        if self.fields_error:
            raise self.fields_error
        return self.fields

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> object:
        self.page_tokens.append(page_token)
        value = self.pages[page_token]
        if isinstance(value, Exception):
            raise value
        return value


def page(
    *items: dict[str, object],
    has_more: bool = False,
    next_page_token: str | None = None,
    total: int | None = None,
) -> object:
    return content_analysis.FeishuRecordPage(
        items=items,
        has_more=has_more,
        next_page_token=next_page_token,
        total=total,
    )


def reader(
    client: FakeFeishuClient,
    *,
    request_timeout_seconds: float = 1,
    max_pages: int = 1000,
) -> object:
    return content_analysis.FeishuContentReader(
        client,
        content_analysis.FeishuContentTableConfig(
            app_token="base-token",
            table_id="table-id",
        ),
        clock=lambda: CHECKED_AT,
        request_timeout_seconds=request_timeout_seconds,
        max_pages=max_pages,
    )


@pytest.mark.asyncio
async def test_feishu_reader_reads_all_pages_and_derives_per_account_results() -> None:
    client = FakeFeishuClient(
        {
            None: page(
                row(
                    "work-001",
                    external_url="https://example.invalid/work-001",
                    review_url="https://internal.invalid/work-001",
                ),
                has_more=True,
                next_page_token="page-2",
                total=2,
            ),
            "page-2": page(
                row("work-002", account_id="account-002"),
                total=2,
            ),
        }
    )

    results = await reader(client).read_accounts(
        ("account-001", "account-002", "account-empty"),
        WINDOW,
    )

    assert client.page_tokens == [None, "page-2"]
    assert [item.account_id for item in results] == [
        "account-001",
        "account-002",
        "account-empty",
    ]
    assert [item.status for item in results] == [
        content_analysis.SyncStatus.SUCCESS_WITH_CONTENT,
        content_analysis.SyncStatus.SUCCESS_WITH_CONTENT,
        content_analysis.SyncStatus.SUCCESS_WITHOUT_CONTENT,
    ]
    first = results[0].contents[0]
    assert first.title == "匿名标题"
    assert first.identity.external_url == "https://example.invalid/work-001"
    assert first.operations_review_url == "https://internal.invalid/work-001"
    assert first.metrics.like_count == 12
    assert first.metrics.comment_count == 3
    assert first.metrics.share_count is None
    assert first.metrics.favorite_count is None
    assert first.metrics.play_count is None
    assert first.published_at.tzinfo == SHANGHAI
    assert first.captured_at.tzinfo == SHANGHAI
    assert not hasattr(first, "sync_status")
    assert all(item.checked_at == CHECKED_AT for item in results)
    assert all(item.coverage_window == WINDOW for item in results)
    assert all(item.read_source == content_analysis.ReadSource.FEISHU for item in results)


@pytest.mark.asyncio
async def test_feishu_reader_all_accounts_empty_only_after_complete_page_end() -> None:
    results = await reader(FakeFeishuClient({None: page()})).read_accounts(
        ("account-001", "account-002"),
        WINDOW,
    )

    assert all(
        item.status == content_analysis.SyncStatus.SUCCESS_WITHOUT_CONTENT
        for item in results
    )
    assert all(item.contents == () and item.issue is None for item in results)


@pytest.mark.asyncio
async def test_feishu_reader_deduplicates_a_work_using_latest_capture() -> None:
    older = row("work-001", captured_at=1788364800000)
    newer = row("work-001", captured_at=1788451200000)
    newer["record_id"] = "record-work-001-newer"
    newer["fields"]["点赞"] = 99

    results = await reader(
        FakeFeishuClient({None: page(older, newer)})
    ).read_accounts(("account-001",), WINDOW)

    assert len(results[0].contents) == 1
    assert results[0].contents[0].metrics.like_count == 99
    assert results[0].contents[0].captured_at == datetime(
        2026,
        9,
        4,
        tzinfo=SHANGHAI,
    )


@pytest.mark.asyncio
async def test_feishu_reader_keeps_missing_transcript_and_optional_links() -> None:
    results = await reader(
        FakeFeishuClient({None: page(row("work-001", transcript=None))})
    ).read_accounts(("account-001",), WINDOW)

    content = results[0].contents[0]
    assert content.transcript is None
    assert content.identity.external_url is None
    assert content.operations_review_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "reason_fragment"),
    (
        (
            FakeFeishuClient(
                {None: page()},
                auth_error=PermissionError("secret must not leak"),
            ),
            "鉴权失败",
        ),
        (
            FakeFeishuClient(
                {None: page()},
                fields=tuple(name for name in REQUIRED_FIELDS if name != "视频ID"),
            ),
            "字段校验失败",
        ),
        (
            FakeFeishuClient(
                {None: page()},
                fields=tuple(
                    name for name in REQUIRED_FIELDS if name != "播放链接"
                ),
            ),
            "字段校验失败",
        ),
        (
            FakeFeishuClient({None: TimeoutError("private timeout detail")}),
            "读取超时",
        ),
        (
            FakeFeishuClient({None: RuntimeError("private transport detail")}),
            "读取失败",
        ),
    ),
)
async def test_feishu_reader_returns_explicit_failure_without_empty_status(
    client: FakeFeishuClient,
    reason_fragment: str,
) -> None:
    results = await reader(client).read_accounts(
        ("account-001", "account-002"),
        WINDOW,
    )

    assert all(item.status == content_analysis.SyncStatus.FAILED for item in results)
    assert all(item.contents == () for item in results)
    assert all(item.issue is not None for item in results)
    assert all(reason_fragment in item.issue.reason for item in results)
    assert all("private" not in item.issue.reason for item in results)


class HangingFeishuClient(FakeFeishuClient):
    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> object:
        await asyncio.Event().wait()


class EndlessCursorFeishuClient(FakeFeishuClient):
    def __init__(self) -> None:
        super().__init__({})
        self.call_count = 0

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> object:
        self.call_count += 1
        return page(has_more=True, next_page_token=f"page-{self.call_count}")


@pytest.mark.asyncio
async def test_feishu_reader_enforces_timeout_for_a_hanging_page() -> None:
    results = await reader(
        HangingFeishuClient({}),
        request_timeout_seconds=0.001,
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert results[0].issue.reason == "飞书读取超时"


@pytest.mark.asyncio
async def test_feishu_reader_enforces_timeout_for_endless_unique_cursors() -> None:
    client = EndlessCursorFeishuClient()

    results = await reader(client, max_pages=3).read_accounts(
        ("account-001",),
        WINDOW,
    )

    assert client.call_count == 3
    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert results[0].issue.reason == "飞书分页读取未完成"


class SlowTwoPageFeishuClient(FakeFeishuClient):
    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> object:
        await asyncio.sleep(0.03)
        return await super().list_records(
            app_token,
            table_id,
            page_token=page_token,
        )


@pytest.mark.asyncio
async def test_each_timely_page_is_not_mistaken_for_whole_read_timeout() -> None:
    client = SlowTwoPageFeishuClient(
        {
            None: page(
                row("work-001"),
                has_more=True,
                next_page_token="page-2",
                total=2,
            ),
            "page-2": page(row("work-002"), total=2),
        }
    )

    results = await reader(
        client,
        request_timeout_seconds=0.05,
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.SUCCESS_WITH_CONTENT
    assert len(results[0].contents) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken_page",
    (
        lambda: page(has_more=False, next_page_token="unexpected-token"),
        lambda: page(has_more=True, next_page_token="same-token"),
    ),
)
async def test_feishu_reader_rejects_incomplete_or_inconsistent_pagination(
    broken_page,
) -> None:
    client = FakeFeishuClient(
        {
            None: page(has_more=True, next_page_token="same-token"),
            "same-token": broken_page(),
        }
    )

    results = await reader(client).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert "分页" in results[0].issue.reason


@pytest.mark.asyncio
async def test_feishu_reader_rejects_final_page_when_total_proves_incomplete() -> None:
    results = await reader(
        FakeFeishuClient({None: page(row("work-001"), total=2)})
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert "分页" in results[0].issue.reason


@pytest.mark.asyncio
async def test_feishu_reader_rejects_duplicate_record_ids_across_pages() -> None:
    first = row("work-001", account_id="account-unrelated")
    duplicate = row("work-002", account_id="account-unrelated")
    duplicate["record_id"] = first["record_id"]
    client = FakeFeishuClient(
        {
            None: page(first, has_more=True, next_page_token="page-2", total=2),
            "page-2": page(duplicate, total=2),
        }
    )

    results = await reader(client).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert results[0].issue.reason == "飞书分页读取未完成"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_row",
    (
        row(
            "work-future-capture",
            captured_at=1788710400000,
        ),
        row(
            "work-published-after-capture",
            published_at=1788278400000,
            captured_at=1788192000000,
        ),
    ),
)
async def test_feishu_reader_rejects_impossible_content_time_order(
    invalid_row: dict[str, object],
) -> None:
    results = await reader(
        FakeFeishuClient({None: page(invalid_row)})
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert results[0].issue.reason == "飞书字段校验失败"


@pytest.mark.asyncio
async def test_invalid_rows_outside_task_scope_do_not_fail_requested_content() -> None:
    valid = row("work-valid")
    unrelated = row("work-unrelated", account_id="account-unrelated")
    unrelated["fields"]["点赞"] = -1
    outside_window = row(
        "work-old",
        published_at=1787673600000,
        captured_at=1787760000000,
    )
    outside_window["fields"]["点赞"] = -1
    unrelated_bad_time = row("work-unrelated-time", account_id="account-unrelated")
    unrelated_bad_time["fields"]["发布时间"] = "not-a-time"

    results = await reader(
        FakeFeishuClient(
            {None: page(valid, unrelated, outside_window, unrelated_bad_time)}
        )
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.SUCCESS_WITH_CONTENT
    assert tuple(
        item.identity.platform_content_id for item in results[0].contents
    ) == ("work-valid",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid"),
    (
        ("SecUid", ""),
        ("视频ID", None),
        ("视频标题", 42),
        ("字幕全文", {"unexpected": "shape"}),
        ("发布时间", "2026-09-02 08:00:00"),
        ("同步时间", True),
        ("点赞", -1),
        ("评论", 1.5),
        ("分享", False),
        ("收藏", "not-a-number"),
    ),
)
async def test_feishu_reader_rejects_invalid_required_identity_time_or_metric(
    field_name: str,
    invalid: object,
) -> None:
    invalid_row = row("work-001")
    invalid_row["fields"][field_name] = invalid

    results = await reader(
        FakeFeishuClient({None: page(invalid_row)})
    ).read_accounts(("account-001",), WINDOW)

    assert results[0].status == content_analysis.SyncStatus.FAILED
    assert "字段校验失败" in results[0].issue.reason


def test_feishu_table_config_rejects_empty_identifiers() -> None:
    with pytest.raises(ValueError, match="app_token"):
        content_analysis.FeishuContentTableConfig("", "table-id")
    with pytest.raises(ValueError, match="table_id"):
        content_analysis.FeishuContentTableConfig("base-token", "")
    with pytest.raises(ValueError, match="超时"):
        reader(FakeFeishuClient({None: page()}), request_timeout_seconds=0)
    with pytest.raises(ValueError, match="分页上限"):
        reader(FakeFeishuClient({None: page()}), max_pages=0)


def test_feishu_page_contract_rejects_mutable_items_and_invalid_cursor() -> None:
    with pytest.raises(ValueError, match="不可变元组"):
        content_analysis.FeishuRecordPage(items=[])
    with pytest.raises(ValueError, match="下一页游标"):
        content_analysis.FeishuRecordPage(items=(), has_more=True)
    with pytest.raises(ValueError, match="总数"):
        content_analysis.FeishuRecordPage(items=(), total=True)


@pytest.mark.asyncio
async def test_feishu_reader_rejects_noncanonical_task_account_ids() -> None:
    with pytest.raises(ValueError, match="首尾空格"):
        await reader(FakeFeishuClient({None: page()})).read_accounts(
            (" account-001 ",),
            WINDOW,
        )


def test_feishu_adapter_does_not_expose_visual_or_upstream_status_input() -> None:
    assert "MediaReadResult" not in content_analysis.__all__
    assert "MediaReadStatus" not in content_analysis.__all__
    assert {item.value for item in content_analysis.OpeningKind} == {"language"}
    assert {item.value for item in content_analysis.EvidenceType} == {
        "title",
        "transcript",
        "metadata",
    }
    assert {item.value for item in content_analysis.CandidateValueSignal} == {
        "early_data_strength",
        "relative_benchmark_outperformance",
        "novel_topic_or_structure",
        "clear_traffic_hook",
        "reusable_conversion_structure",
    }
