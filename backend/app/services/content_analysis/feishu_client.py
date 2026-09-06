"""可注入 HTTP 会话的飞书多维表格只读网络客户端。"""
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from time import monotonic
from typing import Any

import httpx

from .feishu_adapter import FeishuRecordPage


def _non_empty(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空文本")


@dataclass(frozen=True)
class FeishuAppCredentials:
    """运行环境注入的飞书自建应用凭据，字符串展示时隐藏密钥。"""

    app_id: str
    app_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        _non_empty(self.app_id, "app_id")
        _non_empty(self.app_secret, "app_secret")


class HttpxFeishuReadonlyClient:
    """通过飞书开放平台读取多维表格字段和记录。"""

    def __init__(
        self,
        http: httpx.AsyncClient,
        credentials: FeishuAppCredentials,
    ) -> None:
        if not isinstance(credentials, FeishuAppCredentials):
            raise ValueError("credentials 类型错误")
        self._http = http
        self._credentials = credentials
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @staticmethod
    def _payload(response: httpx.Response, operation: str) -> Mapping[str, Any]:
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"飞书{operation}网络响应无效") from exc
        if not isinstance(payload, Mapping) or payload.get("code") != 0:
            raise RuntimeError(f"飞书{operation}失败")
        return payload

    async def _token(self) -> str:
        if self._access_token and monotonic() < self._expires_at:
            return self._access_token
        async with self._token_lock:
            if self._access_token and monotonic() < self._expires_at:
                return self._access_token
            try:
                response = await self._http.post(
                    "/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self._credentials.app_id,
                        "app_secret": self._credentials.app_secret,
                    },
                )
            except httpx.HTTPError as exc:
                raise RuntimeError("飞书只读鉴权网络失败") from exc
            payload = self._payload(response, "只读鉴权")
            token = payload.get("tenant_access_token")
            expire = payload.get("expire")
            if not isinstance(token, str) or not token.strip():
                raise RuntimeError("飞书只读鉴权响应缺少访问令牌")
            if type(expire) not in (int, float) or not isfinite(expire) or expire <= 0:
                raise RuntimeError("飞书只读鉴权响应缺少有效期限")
            self._access_token = token
            self._expires_at = monotonic() + max(float(expire) - 60.0, 1.0)
            return token

    async def _get(
        self,
        path: str,
        *,
        params: Mapping[str, object],
        operation: str,
    ) -> Mapping[str, Any]:
        token = await self._token()
        try:
            response = await self._http.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"飞书{operation}网络失败") from exc
        payload = self._payload(response, operation)
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise RuntimeError(f"飞书{operation}响应缺少数据")
        return data

    async def authorize_read(self, app_token: str, table_id: str) -> None:
        _non_empty(app_token, "app_token")
        _non_empty(table_id, "table_id")
        await self._token()

    async def access_token(self) -> str:
        """供同一飞书应用的文档写入网关复用短期访问令牌。"""
        return await self._token()

    async def list_field_names(
        self,
        app_token: str,
        table_id: str,
    ) -> tuple[str, ...]:
        _non_empty(app_token, "app_token")
        _non_empty(table_id, "table_id")
        fields: list[str] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, object] = {"page_size": 100}
            if page_token is not None:
                params["page_token"] = page_token
            data = await self._get(
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                params=params,
                operation="字段读取",
            )
            items = data.get("items")
            if not isinstance(items, list):
                raise RuntimeError("飞书字段读取响应类型错误")
            for item in items:
                if not isinstance(item, Mapping) or not isinstance(
                    item.get("field_name"),
                    str,
                ):
                    raise RuntimeError("飞书字段读取响应类型错误")
                fields.append(item["field_name"])
            has_more = data.get("has_more", False)
            if type(has_more) is not bool:
                raise RuntimeError("飞书字段分页状态错误")
            next_token = data.get("page_token")
            if not has_more:
                if next_token not in (None, ""):
                    raise RuntimeError("飞书字段分页结束状态错误")
                return tuple(fields)
            if (
                not isinstance(next_token, str)
                or not next_token.strip()
                or next_token in seen_tokens
            ):
                raise RuntimeError("飞书字段分页未完整结束")
            seen_tokens.add(next_token)
            page_token = next_token

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> FeishuRecordPage:
        _non_empty(app_token, "app_token")
        _non_empty(table_id, "table_id")
        params: dict[str, object] = {"page_size": 500}
        if page_token is not None:
            _non_empty(page_token, "page_token")
            params["page_token"] = page_token
        data = await self._get(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params=params,
            operation="记录读取",
        )
        items = data.get("items")
        if not isinstance(items, list):
            raise RuntimeError("飞书记录分页响应类型错误")
        has_more = data.get("has_more", False)
        next_token = data.get("page_token")
        total = data.get("total")
        try:
            return FeishuRecordPage(
                items=tuple(items),
                has_more=has_more,
                next_page_token=next_token,
                total=total,
            )
        except ValueError as exc:
            raise RuntimeError("飞书记录分页响应不完整") from exc
