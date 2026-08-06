"""
Coverage-focused direct-await tests for app/routers/admin_ai.py.

Why direct await (not test_client)?
  coverage.py 经 httpx.ASGITransport 追踪 FastAPI 端点函数体不稳定（anyio task
  边界问题）。直接 `await endpoint(body=..., request=..., current_user=...,
  db=test_session)` 让端点代码在测试 task 内同步执行，coverage 稳定记录。
  参考 test_intake_public_report.py 的 TestEndpointHappyPaths 范式。

目标：把 admin_ai.py 行覆盖率从 48% 拉到 ≥75%（routers/ 目录过 70% 门禁留余量）。
覆盖：11 个端点 happy path + test_key/test_model 的 mock 分支 + ai_stats 4 个
service_status 分支 + by_model/token_trend 聚合 + query params（含非法日期回退）。

mock：
  - httpx.AsyncClient（test_key 的 200 / 非200 / 异常 三分支）
  - yunwu_adapter.chat（test_model 的 ok / 异常 双分支）
  - yunwu_adapter.get_queue_length（ai_stats 的 overloaded 分支触发；其他 stats
    测试也 patch 到 0 防止跨测试队列污染）

stats 不 mock SQL，seed 真实 AiCallLog/Credential/AiModel 走真聚合。
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.credential import AiModel, Credential
from app.models.log import AiCallLog
from app.routers.admin_ai import (
    CreateKeyRequest,
    CreateModelRequest,
    UpdateKeyRequest,
    UpdateModelRequest,
    ai_stats,
    create_key,
    create_model,
    delete_key,
    delete_model,
    list_keys,
    list_models,
    test_key as key_test_fn,
    test_model as model_test_fn,
    update_key,
    update_model)


# ---------------------------------------------------------------------------
# Cleanup fixture（autouse）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_ai_tables(test_session):
    """每个测试前后清空 ai_call_logs + credentials + ai_models，防泄漏/污染。

    参考 test_admin_ai.py 的 _cleanup_credentials_and_models 范式，本文件额外清
    ai_call_logs（stats 聚合依赖）。删除顺序遵循外键依赖（被引用表后删）：
    ai_call_logs（FK→credentials）→ credentials → ai_models。
    """
    await test_session.execute(delete(AiCallLog))
    await test_session.execute(delete(Credential))
    await test_session.execute(delete(AiModel))
    await test_session.commit()
    yield
    await test_session.execute(delete(AiCallLog))
    await test_session.execute(delete(Credential))
    await test_session.execute(delete(AiModel))
    await test_session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(*, forwarded_for: str | None = None) -> Request:
    """构造最小可用的 starlette Request，覆盖 _get_ip 的两个分支。

    - forwarded_for=None  → _get_ip 走 request.client.host 分支
    - forwarded_for="1.2.3.4, 5.6.7.8" → _get_ip 走 X-Forwarded-For 首段
    """
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request({
        "type": "http",
        "headers": headers,
        "client": ("127.0.0.1", 0),
    })


def _uuid_suffix() -> str:
    return uuid.uuid4().hex[:10]


# ---------------------------------------------------------------------------
# Keys CRUD — direct await
# ---------------------------------------------------------------------------


class TestKeysDirect:
    @pytest.mark.asyncio
    async def test_list_keys_direct(self, test_session, admin_user):
        """list_keys 直调 → items 含 seed 的 Credential（覆盖大段 raw SQL）。"""
        test_session.add(Credential(
            provider="yunwu", label="cov-list-dir", api_key="sk-list",
            base_url="https://yunwu.ai/v1",
        ))
        await test_session.commit()

        resp = await list_keys(current_user=admin_user, db=test_session)
        assert resp.success is True
        items = resp.data["items"]
        assert any(it["label"] == "cov-list-dir" for it in items)
        # 结构断言
        sample = items[0]
        for k in (
            "id", "provider", "label", "api_key", "base_url", "status",
            "active_requests", "concurrency", "max_concurrent", "max_users",
            "today_calls", "total_calls", "created_at", "updated_at",
        ):
            assert k in sample

    @pytest.mark.asyncio
    async def test_create_key_direct_with_explicit_base_url(
        self, test_session, admin_user,
    ):
        """create_key 显式 base_url → 走 body.base_url 分支。"""
        body = CreateKeyRequest(
            provider="yunwu", label="cov-create-dir", api_key="sk-create",
            base_url="https://yunwu.ai/v1", max_concurrent=7, max_users=15,
        )
        resp = await create_key(
            body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.message == "Key 添加成功"
        assert resp.data["label"] == "cov-create-dir"
        assert resp.data["base_url"] == "https://yunwu.ai/v1"
        assert resp.data["max_concurrent"] == 7
        assert resp.data["max_users"] == 15
        assert resp.data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_key_direct_default_base_url(self, test_session, admin_user):
        """不传 base_url → _DEFAULT_BASE_URLS[provider] 兜底。"""
        body = CreateKeyRequest(provider="glm", label="cov-glm", api_key="sk-glm")
        resp = await create_key(
            body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.data["base_url"] == "https://open.bigmodel.cn/api/paas/v4"

    @pytest.mark.asyncio
    async def test_create_key_direct_x_forwarded_for(self, test_session, admin_user):
        """覆盖 _get_ip 的 X-Forwarded-For 分支（取首段，去空白）。"""
        body = CreateKeyRequest(provider="yunwu", api_key="sk-xff")
        resp = await create_key(
            body=body,
            request=_make_request(forwarded_for="9.9.9.9, 8.8.8.8"),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_update_key_direct_ok(self, test_session, admin_user):
        c = Credential(provider="yunwu", label="cov-upd", api_key="sk-upd")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        body = UpdateKeyRequest(
            label="cov-upd-new", status="disabled", max_concurrent=10,
        )
        resp = await update_key(
            key_id=int(c.id), body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.data["label"] == "cov-upd-new"
        assert resp.data["status"] == "disabled"
        assert resp.data["max_concurrent"] == 10

    @pytest.mark.asyncio
    async def test_update_key_direct_empty_body_no_op(self, test_session, admin_user):
        """空 body（所有字段 None）→ if values 为假分支，不写 DB 仍返回。"""
        c = Credential(provider="yunwu", label="cov-noop", api_key="sk-noop")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        body = UpdateKeyRequest()  # 全部 None
        resp = await update_key(
            key_id=int(c.id), body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.data["label"] == "cov-noop"

    @pytest.mark.asyncio
    async def test_update_key_direct_not_found(self, test_session, admin_user):
        body = UpdateKeyRequest(label="x")
        resp = await update_key(
            key_id=999999, body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_key_direct_ok_then_not_found(
        self, test_session, admin_user,
    ):
        c = Credential(provider="yunwu", label="cov-del", api_key="sk-del")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)
        cid = int(c.id)

        resp = await delete_key(
            key_id=cid, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.message == "Key 已删除"

        # 二次删除 → not-found，同时验证 DB 真删了
        resp2 = await delete_key(
            key_id=cid, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp2.success is False
        assert resp2.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_key_direct_not_found(self, test_session, admin_user):
        resp = await delete_key(
            key_id=999999, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"


# ---------------------------------------------------------------------------
# test_key — 3 branches (200 ok / 非 200 error / httpx 异常)
# ---------------------------------------------------------------------------


class TestTestKeyDirect:
    @pytest.mark.asyncio
    async def test_test_key_direct_not_found(self, test_session, admin_user):
        """key_id 不存在 → error_response RESOURCE_NOT_FOUND（无需 mock httpx）。"""
        resp = await key_test_fn(
            key_id=999999, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_test_key_direct_ok(self, test_session, admin_user):
        """httpx 返回 200 → status=ok + 写 last_tested_at/latency + OperationLog。"""
        c = Credential(
            provider="yunwu", label="cov-test-ok", api_key="sk-test",
            base_url="https://yunwu.ai/v1",
        )
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # admin_ai.test_key 内部 `import httpx` 后访问 httpx.AsyncClient；
        # patch 模块级 httpx.AsyncClient 属性即可拦截。
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await key_test_fn(
                key_id=int(c.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["status"] == "ok"
        assert isinstance(resp.data["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_test_key_direct_non_200_with_error_message(
        self, test_session, admin_user,
    ):
        """非 200 + body.error.message → 覆盖 (body.get('error') or {}).get('message') 分支。"""
        c = Credential(provider="yunwu", label="cov-401", api_key="sk-x")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "invalid api key"}}
        mock_resp.text = "raw body"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await key_test_fn(
                key_id=int(c.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["status"] == "error"
        assert resp.data["error"] == "invalid api key"

    @pytest.mark.asyncio
    async def test_test_key_direct_non_200_without_error_field(
        self, test_session, admin_user,
    ):
        """非 200 + body 无 error.message → fallback 到 resp.text[:200]。

        覆盖 `(body.get('error') or {}).get('message') or resp.text[:200]` 的
        最终 fallback 分支。
        """
        c = Credential(provider="yunwu", label="cov-500", api_key="sk-y")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"unrelated": "shape"}
        mock_resp.text = "server broke"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await key_test_fn(
                key_id=int(c.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.data["status"] == "error"
        assert resp.data["error"] == "server broke"

    @pytest.mark.asyncio
    async def test_test_key_direct_httpx_exception(self, test_session, admin_user):
        """httpx 抛异常 → 业务层捕获返回 status=error。"""
        c = Credential(provider="yunwu", label="cov-err", api_key="sk-z")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = Exception("network down")
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await key_test_fn(
                key_id=int(c.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["status"] == "error"
        assert "network down" in resp.data["error"]


# ---------------------------------------------------------------------------
# Models CRUD — direct await
# ---------------------------------------------------------------------------


class TestModelsDirect:
    @pytest.mark.asyncio
    async def test_list_models_direct(self, test_session, admin_user):
        """list_models 直调 → items 含 seed 的 AiModel（覆盖大段 raw SQL）。"""
        mid = f"m-list-{_uuid_suffix()}"
        test_session.add(AiModel(name="cov-list-m", provider="yunwu", model_id=mid))
        await test_session.commit()

        resp = await list_models(current_user=admin_user, db=test_session)
        assert resp.success is True
        items = resp.data["items"]
        assert any(it["model_id"] == mid for it in items)
        sample = items[0]
        for k in (
            "id", "name", "provider", "model_id", "status",
            "total_calls", "total_tokens", "created_at", "updated_at",
        ):
            assert k in sample

    @pytest.mark.asyncio
    async def test_create_model_direct_ok(self, test_session, admin_user):
        mid = f"m-create-{_uuid_suffix()}"
        body = CreateModelRequest(name="cov-create-m", provider="yunwu", model_id=mid)
        resp = await create_model(
            body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.message == "模型添加成功"
        assert resp.data["model_id"] == mid
        assert resp.data["name"] == "cov-create-m"
        assert resp.data["status"] == "active"
        assert resp.data["id"] > 0

    @pytest.mark.asyncio
    async def test_create_model_direct_duplicate(self, test_session, admin_user):
        mid = f"m-dup-{_uuid_suffix()}"
        test_session.add(AiModel(name="first", provider="yunwu", model_id=mid))
        await test_session.commit()

        body = CreateModelRequest(name="second", provider="yunwu", model_id=mid)
        resp = await create_model(
            body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "VALIDATION_ERROR"
        assert mid in resp.message

    @pytest.mark.asyncio
    async def test_update_model_direct_ok(self, test_session, admin_user):
        m = AiModel(
            name="cov-upd-m", provider="yunwu",
            model_id=f"m-upd-{_uuid_suffix()}",
        )
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        body = UpdateModelRequest(name="cov-upd-m-new", status="disabled")
        resp = await update_model(
            model_id=int(m.id), body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.data["name"] == "cov-upd-m-new"
        assert resp.data["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_update_model_direct_empty_body_no_op(
        self, test_session, admin_user,
    ):
        """空 body（全部 None）→ 不写 DB 仍返回。"""
        m = AiModel(
            name="cov-noop-m", provider="yunwu",
            model_id=f"m-np-{_uuid_suffix()}",
        )
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        body = UpdateModelRequest()
        resp = await update_model(
            model_id=int(m.id), body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.data["name"] == "cov-noop-m"

    @pytest.mark.asyncio
    async def test_update_model_direct_not_found(self, test_session, admin_user):
        body = UpdateModelRequest(name="x")
        resp = await update_model(
            model_id=999999, body=body, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_model_direct_ok_then_not_found(
        self, test_session, admin_user,
    ):
        m = AiModel(
            name="cov-del-m", provider="yunwu",
            model_id=f"m-del-{_uuid_suffix()}",
        )
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)
        mid = int(m.id)

        resp = await delete_model(
            model_id=mid, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is True
        assert resp.message == "模型已删除"

        # 二次删除 → not-found
        resp2 = await delete_model(
            model_id=mid, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp2.success is False
        assert resp2.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_model_direct_not_found(self, test_session, admin_user):
        resp = await delete_model(
            model_id=999999, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"


# ---------------------------------------------------------------------------
# test_model — 2 branches (ok / chat 抛异常)
# ---------------------------------------------------------------------------


class TestTestModelDirect:
    @pytest.mark.asyncio
    async def test_test_model_direct_not_found(self, test_session, admin_user):
        resp = await model_test_fn(
            model_id=999999, request=_make_request(),
            current_user=admin_user, db=test_session,
        )
        assert resp.success is False
        assert resp.code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_test_model_direct_ok(self, test_session, admin_user):
        """mock yunwu_adapter.chat 不抛错 → status=ok + 写 last_tested_at + log。"""
        m = AiModel(
            name="cov-tm", provider="yunwu",
            model_id=f"tm-ok-{_uuid_suffix()}",
        )
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        with patch(
            "app.routers.admin_ai.yunwu_adapter.chat",
            new=AsyncMock(return_value="ok"),
        ):
            resp = await model_test_fn(
                model_id=int(m.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["status"] == "ok"
        assert isinstance(resp.data["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_test_model_direct_chat_exception(self, test_session, admin_user):
        """mock yunwu_adapter.chat 抛异常 → 业务层捕获，仍写 last_tested_at 并返回 error。"""
        m = AiModel(
            name="cov-tm-err", provider="yunwu",
            model_id=f"tm-err-{_uuid_suffix()}",
        )
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        with patch(
            "app.routers.admin_ai.yunwu_adapter.chat",
            new=AsyncMock(side_effect=RuntimeError("no available key")),
        ):
            resp = await model_test_fn(
                model_id=int(m.id), request=_make_request(),
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["status"] == "error"
        assert "no available key" in resp.data["error"]


# ---------------------------------------------------------------------------
# ai_stats — 4 service_status 分支 + by_model/token_trend 聚合 + query params
# ---------------------------------------------------------------------------
#
# service_status 决策树（admin_ai.py L644-651）：
#   if total_capacity == 0 or healthy_keys == 0      → unavailable
#   elif queue_length > 0 or current_active >= total_capacity → overloaded
#   elif healthy_keys / total_keys < 0.5              → degraded
#   else                                              → healthy
#
# 注意：healthy_keys 的 SQL 定义是 `status='active' AND active_requests < max_concurrent`，
# 即 active_requests 已达 max_concurrent 的 active key 不算 healthy；
# 且 current_active = SUM(active_requests) 跨所有 status（含 disabled），
# total_capacity = SUM(max_concurrent WHERE status='active')。


class TestAiStatsDirect:
    @pytest.mark.asyncio
    async def test_stats_no_keys_unavailable(self, test_session, admin_user):
        """无 credentials → total_capacity=0 → service_status=unavailable。"""
        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["summary"]["service_status"] == "unavailable"
        assert resp.data["summary"]["total_keys"] == 0
        assert resp.data["summary"]["total_capacity"] == 0

    @pytest.mark.asyncio
    async def test_stats_healthy(self, test_session, admin_user):
        """3 个 active + active_requests=0 的 credentials → ratio=1.0 → healthy。"""
        for i in range(3):
            test_session.add(Credential(
                provider="yunwu", label=f"cov-h-{i}", api_key=f"sk-h-{i}",
                status="active", active_requests=0, max_concurrent=5,
            ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        assert resp.data["summary"]["service_status"] == "healthy"
        assert resp.data["summary"]["healthy_keys"] == 3
        assert resp.data["summary"]["total_keys"] == 3
        assert resp.data["summary"]["total_capacity"] == 15

    @pytest.mark.asyncio
    async def test_stats_overloaded_by_queue(self, test_session, admin_user):
        """queue_length > 0 → overloaded（即使 active_requests 不超 capacity）。"""
        test_session.add(Credential(
            provider="yunwu", label="cov-ov", api_key="sk-ov",
            status="active", active_requests=0, max_concurrent=5,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=2,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        assert resp.data["summary"]["service_status"] == "overloaded"
        assert resp.data["summary"]["queue_length"] == 2

    @pytest.mark.asyncio
    async def test_stats_overloaded_by_current_active(self, test_session, admin_user):
        """current_active >= total_capacity → overloaded。

        构造：1 active cred（healthy，active_requests=2，max_concurrent=5）
        + 1 disabled cred（active_requests=10，max_concurrent 不计入 capacity）。
        → total_capacity=5, current_active=12 >= 5 → overloaded；healthy_keys=1 > 0
        不触发 unavailable。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-active", api_key="sk-a",
            status="active", active_requests=2, max_concurrent=5,
        ))
        test_session.add(Credential(
            provider="yunwu", label="cov-leak", api_key="sk-l",
            status="disabled", active_requests=10, max_concurrent=5,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        assert resp.data["summary"]["service_status"] == "overloaded"
        assert resp.data["summary"]["current_active"] == 12
        assert resp.data["summary"]["total_capacity"] == 5

    @pytest.mark.asyncio
    async def test_stats_degraded(self, test_session, admin_user):
        """healthy_keys/total_keys < 0.5 → degraded。

        构造：1 active（healthy=1）+ 2 disabled → ratio = 1/3 < 0.5。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-on", api_key="sk-on",
            status="active", active_requests=0, max_concurrent=5,
        ))
        for i in range(2):
            test_session.add(Credential(
                provider="yunwu", label=f"cov-off-{i}", api_key=f"sk-off-{i}",
                status="disabled", active_requests=0, max_concurrent=5,
            ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        assert resp.data["summary"]["service_status"] == "degraded"
        assert resp.data["summary"]["healthy_keys"] == 1
        assert resp.data["summary"]["total_keys"] == 3

    @pytest.mark.asyncio
    async def test_stats_by_model_and_token_trend_aggregation(
        self, test_session, admin_user,
    ):
        """seed AiCallLog 行 → 验证 by_model / token_trend / total_tokens / avg_latency。"""
        mid_a = f"stats-a-{_uuid_suffix()}"
        mid_b = f"stats-b-{_uuid_suffix()}"
        test_session.add(AiModel(name="modelA", provider="yunwu", model_id=mid_a))
        test_session.add(AiModel(name="modelB", provider="yunwu", model_id=mid_b))
        # credential 让 key summary 不走 unavailable 分支
        test_session.add(Credential(
            provider="yunwu", label="cov-stats", api_key="sk-stats",
            status="active", active_requests=0, max_concurrent=5,
        ))
        await test_session.commit()

        now = datetime.now(timezone.utc)
        # model_a：2 次调用，input+output 合计 50 (30+20)
        test_session.add(AiCallLog(
            user_id=int(admin_user.id), feature="cov1", model_id=mid_a,
            input_tokens=10, output_tokens=20, latency_ms=100, status="success",
            created_at=now,
        ))
        test_session.add(AiCallLog(
            user_id=int(admin_user.id), feature="cov2", model_id=mid_a,
            input_tokens=5, output_tokens=15, latency_ms=200, status="success",
            created_at=now,
        ))
        # model_b：1 次调用，合计 100
        test_session.add(AiCallLog(
            user_id=int(admin_user.id), feature="cov3", model_id=mid_b,
            input_tokens=40, output_tokens=60, latency_ms=150, status="success",
            created_at=now,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )

        summary = resp.data["summary"]
        assert summary["total_tokens"] == 50 + 100  # 150
        assert summary["avg_latency_ms"] == 150.0   # (100+200+150)/3

        # by_model：按 tokens DESC → b(100) 在 a(50) 前
        by_model = resp.data["by_model"]
        assert by_model[0]["model_id"] == mid_b
        assert by_model[0]["tokens"] == 100
        assert by_model[0]["requests"] == 1
        assert by_model[0]["name"] == "modelB"
        assert by_model[1]["model_id"] == mid_a
        assert by_model[1]["tokens"] == 50
        assert by_model[1]["requests"] == 2
        # pct：b 占 100/150 = 66.67 → round = 67
        assert by_model[0]["pct"] == 67
        assert by_model[1]["pct"] == 33

        # token_trend：全在同一天 → 1 行
        trend = resp.data["token_trend"]
        assert len(trend) == 1
        assert trend[0]["input_tokens"] == 10 + 5 + 40   # 55
        assert trend[0]["output_tokens"] == 20 + 15 + 60  # 95

    @pytest.mark.asyncio
    async def test_stats_query_params_provider_status_filter(
        self, test_session, admin_user,
    ):
        """provider + status 过滤 credentials → key summary 只算子集。

        覆盖 key_conditions/key_params/key_where 拼接的 if provider / if status 分支。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-yun", api_key="sk-yun",
            status="active", active_requests=0, max_concurrent=5,
        ))
        test_session.add(Credential(
            provider="glm", label="cov-glm", api_key="sk-glm",
            status="active", active_requests=0, max_concurrent=5,
        ))
        test_session.add(Credential(
            provider="yunwu", label="cov-yun-dis", api_key="sk-yun-dis",
            status="disabled", active_requests=0, max_concurrent=5,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                start_date="", end_date="",
                provider="yunwu", status="active",
                current_user=admin_user, db=test_session,
            )
        # 只算 yunwu + active → 1 个
        assert resp.data["summary"]["total_keys"] == 1
        assert resp.data["summary"]["healthy_keys"] == 1

    @pytest.mark.asyncio
    async def test_stats_query_params_valid_dates_parse(
        self, test_session, admin_user,
    ):
        """显式合法 YYYYMMDD → 覆盖 _parse_date 的 strptime 成功分支。

        用一个远古时间范围 → 当天的 log 不计入，total_tokens=0。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-date", api_key="sk-date",
            status="active", active_requests=0, max_concurrent=5,
        ))
        test_session.add(AiCallLog(
            user_id=int(admin_user.id), feature="cov", model_id="cov-model-x",
            input_tokens=10, output_tokens=10, latency_ms=50, status="success",
            created_at=datetime.now(timezone.utc),
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                start_date="20260101", end_date="20260102",
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        # 范围（2026-01-01 ~ 2026-01-02）之外的当天 log 不计入
        assert resp.data["summary"]["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_stats_invalid_date_falls_back(self, test_session, admin_user):
        """非法日期 → _parse_date ValueError 分支 → 回退默认 today/today+1。

        覆盖 `except ValueError: return fallback`。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-bad-date", api_key="sk-bd",
            status="active", active_requests=0, max_concurrent=5,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                start_date="not-a-date", end_date="also-bad",
                current_user=admin_user, db=test_session,
            )
        assert resp.success is True
        assert resp.data["summary"]["service_status"] in {
            "healthy", "degraded", "overloaded", "unavailable",
        }

    @pytest.mark.asyncio
    async def test_stats_by_model_model_missing_in_ai_models(
        self, test_session, admin_user,
    ):
        """by_model LEFT JOIN：log 引用的 model_id 在 ai_models 中无记录 → m.* 为 None。

        覆盖 by_model 中 r.name/provider 为 None 的情形，且 pct 在 total_tokens>0 时
        正常计算（log tokens / total tokens）。
        """
        test_session.add(Credential(
            provider="yunwu", label="cov-left", api_key="sk-l",
            status="active", active_requests=0, max_concurrent=5,
        ))
        await test_session.commit()

        now = datetime.now(timezone.utc)
        test_session.add(AiCallLog(
            user_id=int(admin_user.id), feature="cov", model_id="ghost-model",
            input_tokens=5, output_tokens=5, latency_ms=80, status="success",
            created_at=now,
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_ai.yunwu_adapter.get_queue_length", return_value=0,
        ):
            resp = await ai_stats(
                current_user=admin_user, db=test_session,
            )
        by_model = resp.data["by_model"]
        assert len(by_model) == 1
        assert by_model[0]["model_id"] == "ghost-model"
        assert by_model[0]["name"] is None
        assert by_model[0]["provider"] is None
        assert by_model[0]["tokens"] == 10
        assert by_model[0]["pct"] == 100  # 10/10 * 100
