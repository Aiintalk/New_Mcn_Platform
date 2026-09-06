"""飞书多维表格真实网络客户端的只读合同。"""
import json

import httpx
import pytest

import app.services.content_analysis as content_analysis


@pytest.mark.asyncio
async def test_http_client_authenticates_and_reads_fields_and_all_pages() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tenant_access_token/internal"):
            assert json.loads(request.content) == {
                "app_id": "app-id",
                "app_secret": "private-secret",
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )
        assert request.headers["Authorization"] == "Bearer tenant-token"
        if request.url.path.endswith("/fields"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [{"field_name": "SecUid"}, {"field_name": "视频ID"}],
                        "has_more": False,
                    },
                },
            )
        assert request.url.params.get("page_size") == "500"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [{"record_id": "rec-1", "fields": {}}],
                    "has_more": False,
                    "total": 1,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        client = content_analysis.HttpxFeishuReadonlyClient(
            http,
            content_analysis.FeishuAppCredentials(
                app_id="app-id",
                app_secret="private-secret",
            ),
        )
        await client.authorize_read("base-token", "table-id")
        fields = await client.list_field_names("base-token", "table-id")
        page = await client.list_records(
            "base-token",
            "table-id",
            page_token=None,
        )

    assert fields == ("SecUid", "视频ID")
    assert page.total == 1
    assert page.items[0]["record_id"] == "rec-1"
    assert len([item for item in requests if "auth" in item.url.path]) == 1


@pytest.mark.asyncio
async def test_http_client_rejects_api_failure_without_leaking_secret_or_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 999, "msg": "private-secret and personal content"},
        )

    credentials = content_analysis.FeishuAppCredentials(
        app_id="app-id",
        app_secret="private-secret",
    )
    assert "private-secret" not in repr(credentials)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        client = content_analysis.HttpxFeishuReadonlyClient(http, credentials)
        with pytest.raises(RuntimeError) as captured:
            await client.authorize_read("base-token", "table-id")

    assert "private-secret" not in str(captured.value)
    assert "personal content" not in str(captured.value)


@pytest.mark.asyncio
async def test_http_client_rejects_incomplete_field_pagination() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "token", "expire": 7200},
            )
        return httpx.Response(
            200,
            json={"code": 0, "data": {"items": [], "has_more": True}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
    ) as http:
        client = content_analysis.HttpxFeishuReadonlyClient(
            http,
            content_analysis.FeishuAppCredentials("app-id", "secret"),
        )
        with pytest.raises(RuntimeError, match="分页"):
            await client.list_field_names("base-token", "table-id")


def test_feishu_network_config_requires_injected_identifiers() -> None:
    with pytest.raises(ValueError, match="app_id"):
        content_analysis.FeishuAppCredentials("", "secret")
    with pytest.raises(ValueError, match="app_secret"):
        content_analysis.FeishuAppCredentials("app-id", "")
