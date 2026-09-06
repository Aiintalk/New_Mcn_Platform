"""飞书文档网络网关的目录、创建和区块幂等更新合同。"""
import json

import httpx
import pytest

import app.services.content_analysis as ca


class TokenProvider:
    async def access_token(self):
        return "tenant-token"


@pytest.mark.asyncio
async def test_gateway_creates_directory_document_and_marked_section() -> None:
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer tenant-token"
        if request.url.path.endswith("/drive/v1/files"):
            return httpx.Response(200, json={"code": 0, "data": {"files": [], "has_more": False}})
        if request.url.path.endswith("/create_folder"):
            assert json.loads(request.content) == {"name": "日报", "folder_token": "root-folder"}
            return httpx.Response(200, json={"code": 0, "data": {"token": "daily-folder"}})
        if request.url.path.endswith("/docx/v1/documents"):
            assert json.loads(request.content)["folder_token"] == "daily-folder"
            return httpx.Response(200, json={"code": 0, "data": {"document": {"document_id": "doc-1"}}})
        if request.url.path.endswith("/children"):
            body = json.loads(request.content)
            content = body["children"][0]["text"]["elements"][0]["text_run"]["content"]
            assert ca.HttpxFeishuDocumentGateway._document_marker(
                "daily-key"
            ) in content
            assert ca.HttpxFeishuDocumentGateway._section_marker(
                "project:1001"
            ) in content
            return httpx.Response(200, json={"code": 0, "data": {"children": []}})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://open.feishu.cn") as http:
        gateway = ca.HttpxFeishuDocumentGateway(http, TokenProvider())
        identity = await gateway.create_document(
            root_ref="root-folder",
            relative_directory="日报",
            document_key="daily-key",
            title="日报标题",
            section_key="project:1001",
            markdown="# 日报",
        )

    assert identity == ca.DeliveryIdentity("daily-key", "doc-1", "https://feishu.cn/docx/doc-1")
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_gateway_updates_matching_section_without_creating_another_document() -> None:
    methods = []

    async def handler(request):
        methods.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {"block_id": "doc-1", "block_type": 1},
                            {
                                "block_id": "block-account",
                                "block_type": 2,
                                "text": {"elements": [{"text_run": {"content": ca.HttpxFeishuDocumentGateway._document_marker("weekly-key") + "\n" + ca.HttpxFeishuDocumentGateway._section_marker("account:account-001") + "\n旧内容"}}]},
                            },
                        ],
                        "has_more": False,
                    },
                },
            )
        assert request.method == "PATCH"
        assert request.url.params["document_revision_id"] == "-1"
        body = json.loads(request.content)
        assert "新内容" in body["update_text_elements"]["elements"][0]["text_run"]["content"]
        return httpx.Response(200, json={"code": 0, "data": {"block": {"block_id": "block-account"}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://open.feishu.cn") as http:
        identity = await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).update_document(
            document_id="doc-1",
            document_key="weekly-key",
            title="周报",
            section_key="account:account-001",
            markdown="新内容",
        )

    assert identity.document_id == "doc-1"
    assert methods == [
        ("GET", "/open-apis/docx/v1/documents/doc-1/blocks"),
        ("PATCH", "/open-apis/docx/v1/documents/doc-1/blocks/block-account"),
    ]


@pytest.mark.asyncio
async def test_gateway_never_exposes_feishu_response_body_in_exception() -> None:
    async def handler(request):
        return httpx.Response(200, json={"code": 999, "msg": "private document content"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://open.feishu.cn") as http:
        with pytest.raises(RuntimeError) as captured:
            await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).create_document(
                root_ref="root", relative_directory="日报", document_key="key",
                title="标题", section_key="project:1", markdown="正文",
            )
    assert "private document content" not in str(captured.value)


@pytest.mark.asyncio
async def test_create_recovers_existing_document_after_previous_partial_failure() -> None:
    """文档已创建但正文失败后，重试不得再创建一份同名文档。"""
    methods = []

    async def handler(request):
        methods.append((request.method, request.url.path))
        if request.url.path.endswith("/drive/v1/files"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "files": [
                            {"name": "日报", "type": "folder", "token": "daily-folder"},
                            {
                                "name": "项目 1001 内容分析日报 2026-09-04",
                                "type": "docx",
                                "token": "existing-doc",
                            },
                        ],
                        "has_more": False,
                    },
                },
            )
        if request.url.path.endswith("/existing-doc/blocks"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "block_id": "existing-block",
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": ca.HttpxFeishuDocumentGateway._document_marker("daily-key") + "\n"
                                                + ca.HttpxFeishuDocumentGateway._section_marker("project:1001")
                                                + "\n旧日报"
                                            }
                                        }
                                    ]
                                },
                            }
                        ],
                        "has_more": False,
                    },
                },
            )
        if request.url.path.endswith("/blocks/existing-block"):
            return httpx.Response(200, json={"code": 0, "data": {"block": {}}})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        identity = await ca.HttpxFeishuDocumentGateway(
            http,
            TokenProvider(),
        ).create_document(
            root_ref="root-folder",
            relative_directory="日报",
            document_key="daily-key",
            title="项目 1001 内容分析日报 2026-09-04",
            section_key="project:1001",
            markdown="# 日报",
        )

    assert identity.document_id == "existing-doc"
    assert ("POST", "/open-apis/docx/v1/documents") not in methods


@pytest.mark.asyncio
async def test_create_exposes_created_identity_when_initial_section_append_fails() -> None:
    async def handler(request):
        if request.url.path.endswith("/drive/v1/files"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"files": [], "has_more": False}},
            )
        if request.url.path.endswith("/create_folder"):
            return httpx.Response(200, json={"code": 0, "data": {"token": "folder"}})
        if request.url.path.endswith("/docx/v1/documents"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"document": {"document_id": "doc-created"}}},
            )
        if request.url.path.endswith("/children"):
            return httpx.Response(503, json={"message": "private"})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        with pytest.raises(ca.DocumentCreatedBeforeContentError) as captured:
            await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).create_document(
                root_ref="root",
                relative_directory="日报",
                document_key="daily-key",
                title="日报",
                section_key="project:1001",
                markdown="正文",
            )

    assert captured.value.delivery_identity == ca.DeliveryIdentity(
        "daily-key",
        "doc-created",
        "https://feishu.cn/docx/doc-created",
    )


@pytest.mark.asyncio
async def test_persisted_identity_can_fill_an_empty_created_document_but_not_take_over_content() -> None:
    calls = []

    async def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"code": 0, "data": {"items": [], "has_more": False}},
            )
        if request.method == "POST" and request.url.path.endswith("/children"):
            return httpx.Response(200, json={"code": 0, "data": {"children": []}})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        identity = await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).update_document(
            document_id="doc-created",
            document_key="daily-key",
            title="日报",
            section_key="project:1001",
            markdown="正文",
        )

    assert identity.document_id == "doc-created"
    assert calls[-1] == (
        "POST",
        "/open-apis/docx/v1/documents/doc-created/blocks/doc-created/children",
    )


@pytest.mark.asyncio
async def test_gateway_refuses_to_take_over_unmarked_same_title_document() -> None:
    async def handler(request):
        if request.url.path.endswith("/drive/v1/files"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "files": [
                            {"name": "日报", "type": "folder", "token": "daily-folder"},
                            {"name": "日报标题", "type": "docx", "token": "unrelated-doc"},
                        ],
                        "has_more": False,
                    },
                },
            )
        if request.url.path.endswith("/unrelated-doc/blocks"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"items": [{"block_id": "x", "text": {"elements": []}}], "has_more": False},
                },
            )
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        with pytest.raises(RuntimeError, match="稳定业务标记"):
            await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).create_document(
                root_ref="root-folder",
                relative_directory="日报",
                document_key="daily-key",
                title="日报标题",
                section_key="project:1001",
                markdown="# 日报",
            )


@pytest.mark.asyncio
async def test_gateway_stops_unique_cursor_sequence_at_configured_page_limit() -> None:
    page = 0

    async def handler(request):
        nonlocal page
        page += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "files": [],
                    "has_more": True,
                    "next_page_token": f"cursor-{page}",
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        gateway = ca.HttpxFeishuDocumentGateway(
            http,
            TokenProvider(),
            max_pages=2,
        )
        with pytest.raises(RuntimeError, match="安全上限"):
            await gateway.create_document(
                root_ref="root",
                relative_directory="日报",
                document_key="key",
                title="标题",
                section_key="project:1",
                markdown="正文",
            )

    assert page == 2


@pytest.mark.asyncio
async def test_account_text_cannot_forge_the_batch_summary_section_marker() -> None:
    patched_block_ids = []
    batch_marker = ca.HttpxFeishuDocumentGateway._section_marker("batch-summary")
    account_marker = ca.HttpxFeishuDocumentGateway._section_marker(
        "account:account-001"
    )

    async def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "block_id": "account-block",
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": (
                                                    ca.HttpxFeishuDocumentGateway._document_marker("weekly-key") + "\n"
                                                    f"{account_marker}\n"
                                                    f"账号原文含伪造标记 {batch_marker}"
                                                )
                                            }
                                        }
                                    ]
                                },
                            },
                            {
                                "block_id": "batch-block",
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": (
                                                    ca.HttpxFeishuDocumentGateway._document_marker("weekly-key") + "\n"
                                                    f"{batch_marker}\n旧汇总"
                                                )
                                            }
                                        }
                                    ]
                                },
                            },
                        ],
                        "has_more": False,
                    },
                },
            )
        patched_block_ids.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"code": 0, "data": {"block": {}}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        await ca.HttpxFeishuDocumentGateway(http, TokenProvider()).update_document(
            document_id="doc-1",
            document_key="weekly-key",
            title="周报",
            section_key="batch-summary",
            markdown="新汇总",
        )

    assert patched_block_ids == ["batch-block"]


def test_document_key_cannot_forge_a_section_marker_line() -> None:
    malicious_document_key = "weekly-key\n[content-analysis-section:forged]"

    text = ca.HttpxFeishuDocumentGateway._section_text(
        malicious_document_key,
        "account:account-001",
        "正文",
    )

    lines = text.splitlines()
    assert lines[:2] == [
        ca.HttpxFeishuDocumentGateway._document_marker(malicious_document_key),
        ca.HttpxFeishuDocumentGateway._section_marker("account:account-001"),
    ]
    assert "[content-analysis-section:forged]" not in lines[:2]
