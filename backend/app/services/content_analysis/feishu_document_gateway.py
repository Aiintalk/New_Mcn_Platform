"""飞书新版文档的目录、文档和业务区块网络网关。"""
from collections.abc import Mapping
import hashlib
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .executor import DeliveryIdentity


class FeishuTokenProvider(Protocol):
    async def access_token(self) -> str: ...


class DocumentCreatedBeforeContentError(RuntimeError):
    """文档已创建但首个业务区块失败；携带可持久化的稳定身份。"""

    def __init__(self, delivery_identity: DeliveryIdentity) -> None:
        super().__init__("飞书报告文档已创建但正文写入失败")
        self.delivery_identity = delivery_identity


class HttpxFeishuDocumentGateway:
    """使用稳定业务标记创建或更新一个文本区块。"""

    def __init__(
        self,
        http: httpx.AsyncClient,
        token_provider: FeishuTokenProvider,
        *,
        max_pages: int = 1000,
    ) -> None:
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("飞书报告分页上限必须是正整数")
        self._http = http
        self._token_provider = token_provider
        self._max_pages = max_pages

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json: Mapping[str, object] | None = None,
        operation: str,
    ) -> Mapping[str, Any]:
        token = await self._token_provider.access_token()
        try:
            response = await self._http.request(
                method,
                path,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"飞书{operation}网络响应无效") from exc
        if not isinstance(payload, Mapping) or payload.get("code") != 0:
            raise RuntimeError(f"飞书{operation}失败")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise RuntimeError(f"飞书{operation}响应缺少数据")
        return data

    async def _ensure_directory(self, root_ref: str, relative: str) -> str:
        current = root_ref
        for part in PurePosixPath(relative).parts:
            token: str | None = None
            page_token: str | None = None
            for _ in range(self._max_pages):
                params: dict[str, object] = {
                    "folder_token": current,
                    "page_size": 200,
                }
                if page_token:
                    params["page_token"] = page_token
                data = await self._request(
                    "GET",
                    "/open-apis/drive/v1/files",
                    params=params,
                    operation="报告目录读取",
                )
                files = data.get("files")
                if not isinstance(files, list):
                    raise RuntimeError("飞书报告目录响应类型错误")
                match = next(
                    (
                        item
                        for item in files
                        if isinstance(item, Mapping)
                        and item.get("name") == part
                        and item.get("type") == "folder"
                        and isinstance(item.get("token"), str)
                    ),
                    None,
                )
                if match is not None:
                    token = match["token"]
                    break
                has_more = data.get("has_more", False)
                if type(has_more) is not bool:
                    raise RuntimeError("飞书报告目录分页状态错误")
                if not has_more:
                    break
                next_token = data.get("next_page_token") or data.get("page_token")
                if not isinstance(next_token, str) or next_token == page_token:
                    raise RuntimeError("飞书报告目录分页未完成")
                page_token = next_token
            else:
                raise RuntimeError("飞书报告目录分页超过安全上限")
            if token is None:
                created = await self._request(
                    "POST",
                    "/open-apis/drive/v1/files/create_folder",
                    json={"name": part, "folder_token": current},
                    operation="报告目录创建",
                )
                token = created.get("token")
                if not isinstance(token, str) or not token.strip():
                    raise RuntimeError("飞书报告目录创建响应缺少目录身份")
            current = token
        return current

    @staticmethod
    def _document_marker(document_key: str) -> str:
        digest = hashlib.sha256(document_key.encode("utf-8")).hexdigest()
        return f"[content-analysis-document:{digest}]"

    @staticmethod
    def _section_marker(section_key: str) -> str:
        digest = hashlib.sha256(section_key.encode("utf-8")).hexdigest()
        return f"[content-analysis-section:{digest}]"

    @staticmethod
    def _section_text(document_key: str, section_key: str, markdown: str) -> str:
        return (
            f"{HttpxFeishuDocumentGateway._document_marker(document_key)}\n"
            f"{HttpxFeishuDocumentGateway._section_marker(section_key)}\n{markdown}"
        )

    async def _find_document(
        self,
        folder_token: str,
        title: str,
        document_key: str,
    ) -> str | None:
        matches: list[str] = []
        page_token: str | None = None
        seen: set[str] = set()
        for _ in range(self._max_pages):
            params: dict[str, object] = {
                "folder_token": folder_token,
                "page_size": 200,
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._request(
                "GET",
                "/open-apis/drive/v1/files",
                params=params,
                operation="报告文档查重",
            )
            files = data.get("files")
            if not isinstance(files, list):
                raise RuntimeError("飞书报告文档查重响应类型错误")
            matches.extend(
                item["token"]
                for item in files
                if isinstance(item, Mapping)
                and item.get("name") == title
                and item.get("type") == "docx"
                and isinstance(item.get("token"), str)
                and item["token"].strip()
            )
            has_more = data.get("has_more", False)
            if type(has_more) is not bool:
                raise RuntimeError("飞书报告文档查重分页状态错误")
            if not has_more:
                break
            next_token = data.get("next_page_token") or data.get("page_token")
            if (
                not isinstance(next_token, str)
                or not next_token.strip()
                or next_token in seen
            ):
                raise RuntimeError("飞书报告文档查重分页未完成")
            seen.add(next_token)
            page_token = next_token
        else:
            raise RuntimeError("飞书报告文档查重分页超过安全上限")
        unique = tuple(dict.fromkeys(matches))
        if len(unique) > 1:
            raise RuntimeError("飞书报告目录存在多个同名文档，无法安全重试")
        if not unique:
            return None
        document_id = unique[0]
        marker = self._document_marker(document_key)
        if not any(
            self._block_text(block).splitlines()
            and self._block_text(block).splitlines()[0].strip() == marker
            for block in await self._blocks(document_id)
        ):
            raise RuntimeError("飞书报告同名文档缺少匹配的稳定业务标记")
        return document_id

    async def _append_section(
        self,
        document_id: str,
        document_key: str,
        section_key: str,
        markdown: str,
    ) -> None:
        content = self._section_text(document_key, section_key, markdown)
        await self._request(
            "POST",
            f"/open-apis/docx/v1/documents/{quote(document_id, safe='')}/blocks/"
            f"{quote(document_id, safe='')}/children",
            params={"document_revision_id": -1},
            json={
                "children": [
                    {
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {"text_run": {"content": content}}
                            ]
                        },
                    }
                ],
                "index": 0,
            },
            operation="报告正文创建",
        )

    async def create_document(
        self,
        *,
        root_ref: str,
        relative_directory: str,
        document_key: str,
        title: str,
        section_key: str,
        markdown: str,
    ) -> DeliveryIdentity:
        folder_token = await self._ensure_directory(root_ref, relative_directory)
        existing_document_id = await self._find_document(
            folder_token,
            title,
            document_key,
        )
        if existing_document_id is not None:
            return await self.update_document(
                document_id=existing_document_id,
                document_key=document_key,
                title=title,
                section_key=section_key,
                markdown=markdown,
            )
        data = await self._request(
            "POST",
            "/open-apis/docx/v1/documents",
            json={"title": title, "folder_token": folder_token},
            operation="报告文档创建",
        )
        document = data.get("document")
        if not isinstance(document, Mapping) or not isinstance(
            document.get("document_id"),
            str,
        ):
            raise RuntimeError("飞书报告文档创建响应缺少文档身份")
        document_id = document["document_id"]
        identity = DeliveryIdentity(
            document_key,
            document_id,
            f"https://feishu.cn/docx/{document_id}",
        )
        try:
            await self._append_section(
                document_id,
                document_key,
                section_key,
                markdown,
            )
        except Exception as exc:
            raise DocumentCreatedBeforeContentError(identity) from exc
        return identity

    @staticmethod
    def _block_text(block: Mapping[str, Any]) -> str:
        text = block.get("text")
        if not isinstance(text, Mapping):
            return ""
        elements = text.get("elements")
        if not isinstance(elements, list):
            return ""
        return "".join(
            str(element.get("text_run", {}).get("content", ""))
            for element in elements
            if isinstance(element, Mapping)
            and isinstance(element.get("text_run"), Mapping)
        )

    async def _blocks(self, document_id: str) -> tuple[Mapping[str, Any], ...]:
        blocks: list[Mapping[str, Any]] = []
        page_token: str | None = None
        seen: set[str] = set()
        for _ in range(self._max_pages):
            params: dict[str, object] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = await self._request(
                "GET",
                f"/open-apis/docx/v1/documents/{quote(document_id, safe='')}/blocks",
                params=params,
                operation="报告区块读取",
            )
            items = data.get("items")
            if not isinstance(items, list) or any(
                not isinstance(item, Mapping) for item in items
            ):
                raise RuntimeError("飞书报告区块响应类型错误")
            blocks.extend(items)
            has_more = data.get("has_more", False)
            if type(has_more) is not bool:
                raise RuntimeError("飞书报告区块分页状态错误")
            if not has_more:
                return tuple(blocks)
            next_token = data.get("page_token")
            if (
                not isinstance(next_token, str)
                or not next_token.strip()
                or next_token in seen
            ):
                raise RuntimeError("飞书报告区块分页未完成")
            seen.add(next_token)
            page_token = next_token
        raise RuntimeError("飞书报告区块分页超过安全上限")

    async def update_document(
        self,
        *,
        document_id: str,
        document_key: str,
        title: str,
        section_key: str,
        markdown: str,
    ) -> DeliveryIdentity:
        blocks = await self._blocks(document_id)
        document_marker = self._document_marker(document_key)
        if not any(
            self._block_text(item).splitlines()
            and self._block_text(item).splitlines()[0].strip() == document_marker
            for item in blocks
        ):
            if any(self._block_text(item).strip() for item in blocks):
                raise RuntimeError("飞书报告文档身份与稳定业务键不匹配")
            await self._append_section(
                document_id,
                document_key,
                section_key,
                markdown,
            )
            return DeliveryIdentity(
                document_key,
                document_id,
                f"https://feishu.cn/docx/{document_id}",
            )
        marker = self._section_marker(section_key)
        block = next(
            (
                item
                for item in blocks
                if len(self._block_text(item).splitlines()) >= 2
                and self._block_text(item).splitlines()[1].strip() == marker
            ),
            None,
        )
        if block is None:
            await self._append_section(
                document_id,
                document_key,
                section_key,
                markdown,
            )
        else:
            block_id = block.get("block_id")
            if not isinstance(block_id, str) or not block_id.strip():
                raise RuntimeError("飞书报告区块缺少稳定身份")
            await self._request(
                "PATCH",
                f"/open-apis/docx/v1/documents/{quote(document_id, safe='')}/blocks/"
                f"{quote(block_id, safe='')}",
                params={"document_revision_id": -1},
                json={
                    "update_text_elements": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": self._section_text(
                                        document_key,
                                        section_key,
                                        markdown,
                                    )
                                }
                            }
                        ]
                    }
                },
                operation="报告区块更新",
            )
        return DeliveryIdentity(
            document_key,
            document_id,
            f"https://feishu.cn/docx/{document_id}",
        )
