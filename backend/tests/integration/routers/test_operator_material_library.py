"""
Integration tests for operator_material_library router.

Covers:
- Auth (2 scenarios: operator OK / no token)
- GET /kols (empty + with data)
- GET /kols/{id} (not found + with data)
- PUT /kols/{id}/profile (update persona + content_plan + writes OperationLog)
- POST /kols/{id}/references (create + invalid type)
- DELETE /kols/{id}/references/{id} (delete + not found)
- GET /kols/{id}/intake (no intake data)
"""
import pytest
from sqlalchemy import text
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from app.core.security import create_access_token
from app.models.user import User
from app.routers.operator_material_library import (
    MAX_VIDEO_UPLOAD_BYTES,
    _UPLOAD_READ_CHUNK_BYTES,
    _write_upload_to_temp_file,
)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_token(self, test_client):
        resp = await test_client.get("/api/tools/material-library/kols")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_operator_is_forbidden_for_every_material_route(
        self, test_client, test_session
    ):
        user = User(
            username=f"material_viewer_{uuid4().hex}",
            real_name="素材访客",
            password_hash="not-used-in-test",
            role="viewer",
            status="enabled",
            password_changed_at=datetime.now(timezone.utc),
        )
        test_session.add(user)
        await test_session.commit()
        token = create_access_token(
            user_id=int(user.id), username=user.username, role=user.role,
            token_version=int(user.token_version),
        )

        response = await test_client.get(
            "/api/tools/material-library/kols",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_must_change_initial_password_before_using_material_library(
        self, test_client, test_session
    ):
        user = User(
            username=f"material_initial_password_{uuid4().hex}",
            real_name="待改密运营",
            password_hash="not-used-in-test",
            role="operator",
            status="enabled",
            password_changed_at=None,
        )
        test_session.add(user)
        await test_session.commit()
        token = create_access_token(
            user_id=int(user.id), username=user.username, role=user.role,
            token_version=int(user.token_version),
        )

        response = await test_client.get(
            "/api/tools/material-library/kols",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /kols — 红人列表
# ---------------------------------------------------------------------------

class TestListKols:
    @pytest.mark.asyncio
    async def test_returns_list(self, test_client, operator_headers, test_session):
        # Ensure at least one kol exists
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('ListTestKol', 'signed')"
        ))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"]["items"], list)
        assert len(body["data"]["items"]) >= 1
        assert body["data"]["pagination"]["page"] == 1

    @pytest.mark.asyncio
    async def test_search_by_name(self, test_client, operator_headers, test_session):
        # Create a uniquely named kol
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('UniqueSearchKol_xyz', 'signed')"
        ))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/material-library/kols?search=UniqueSearchKol_xyz",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["items"]) >= 1
        assert any("UniqueSearchKol_xyz" in k["name"] for k in body["data"]["items"])

    @pytest.mark.asyncio
    async def test_list_has_summary_fields(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        body = resp.json()
        if len(body["data"]["items"]) > 0:
            kol = body["data"]["items"][0]
            for field in ("id", "name", "has_persona", "has_content_plan",
                          "reference_count", "has_intake"):
                assert field in kol

    @pytest.mark.asyncio
    async def test_list_paginates_and_returns_total(self, test_client, operator_headers, test_session):
        for index in range(3):
            await test_session.execute(text(
                "INSERT INTO kols (name, status) VALUES (:name, 'signed')"
            ), {"name": f"PagedMaterialKol_{uuid4().hex}_{index}"})
        await test_session.commit()

        response = await test_client.get(
            "/api/tools/material-library/kols?page=1&page_size=2",
            headers=operator_headers,
        )

        data = response.json()["data"]
        assert len(data["items"]) == 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2
        assert data["pagination"]["total"] >= 3


# ---------------------------------------------------------------------------
# GET /kols/{kol_id} — 红人详情
# ---------------------------------------------------------------------------

class TestGetKolDetail:
    @pytest.mark.asyncio
    async def test_not_found(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols/999999",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is False

    @pytest.mark.asyncio
    async def test_returns_detail(self, test_client, operator_headers, test_session):
        # Create a kol with persona
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('DetailTestKol', '这是soul.md内容', '这是内容规划', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'DetailTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.get(
            f"/api/tools/material-library/kols/{kol_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "DetailTestKol"
        assert body["data"]["persona"] == "这是soul.md内容"
        assert body["data"]["content_plan"] == "这是内容规划"
        assert "references" in body["data"]


# ---------------------------------------------------------------------------
# PUT /kols/{kol_id}/profile — 更新人格档案
# ---------------------------------------------------------------------------

class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_persona(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('ProfileTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'ProfileTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.put(
            f"/api/tools/material-library/kols/{kol_id}/profile",
            headers=operator_headers,
            json={"persona": "更新后的soul.md"},
        )
        body = resp.json()
        assert body["success"] is True
        assert "persona" in body["data"]["updated_fields"]

    @pytest.mark.asyncio
    async def test_update_writes_operation_log(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('LogTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'LogTestKol'"
        ))
        kol_id = result.scalar()

        await test_client.put(
            f"/api/tools/material-library/kols/{kol_id}/profile",
            headers=operator_headers,
            json={"content_plan": "更新内容规划"},
        )

        log_count = await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'material_library_update_profile'"
        ))
        assert int(log_count.scalar()) >= 1


# ---------------------------------------------------------------------------
# POST /kols/{kol_id}/references — 添加素材
# ---------------------------------------------------------------------------

class TestCreateReference:
    @pytest.mark.asyncio
    async def test_create_success(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('RefTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'RefTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={
                "title": "测试爆款文案",
                "likes": 9999,
                "source": "抖音",
                "type": "红人爆款文案",
                "content": "这是一条测试文案内容",
            },
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["title"] == "测试爆款文案"
        assert body["data"]["type"] == "红人爆款文案"
        assert body["data"]["likes"] == 9999

    @pytest.mark.asyncio
    async def test_create_invalid_type(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('InvalidTypeKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'InvalidTypeKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={
                "title": "测试",
                "type": "无效类型",
                "content": "内容",
            },
        )
        body = resp.json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# DELETE /kols/{kol_id}/references/{ref_id} — 删除素材
# ---------------------------------------------------------------------------

class TestDeleteReference:
    @pytest.mark.asyncio
    async def test_delete_success(self, test_client, operator_headers, test_session):
        # Setup: create kol + reference
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('DelRefKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'DelRefKol'"))
        kol_id = result.scalar()

        create_resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={"title": "待删除", "type": "风格参考", "content": "内容"},
        )
        ref_id = create_resp.json()["data"]["id"]

        # Delete
        resp = await test_client.delete(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('NotFoundDelKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'NotFoundDelKol'"))
        kol_id = result.scalar()

        resp = await test_client.delete(
            f"/api/tools/material-library/kols/{kol_id}/references/999999",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# GET /kols/{kol_id}/intake — 入驻问卷数据
# ---------------------------------------------------------------------------

class TestGetIntake:
    @pytest.mark.asyncio
    async def test_no_intake_data(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('NoIntakeKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'NoIntakeKol'"))
        kol_id = result.scalar()

        resp = await test_client.get(
            f"/api/tools/material-library/kols/{kol_id}/intake",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] is None


# ---------------------------------------------------------------------------
# 文档、视频和编辑（红人工作台旧版功能还原）
# ---------------------------------------------------------------------------

async def _create_material_kol(test_session, prefix: str) -> int:
    name = f"{prefix}_{uuid4().hex}"
    await test_session.execute(text(
        "INSERT INTO kols (name, status) VALUES (:name, 'signed')"
    ), {"name": name})
    await test_session.commit()
    return (await test_session.execute(text(
        "SELECT id FROM kols WHERE name = :name"
    ), {"name": name})).scalar_one()


async def _create_reference(test_client, operator_headers, kol_id: int) -> int:
    response = await test_client.post(
        f"/api/tools/material-library/kols/{kol_id}/references",
        headers=operator_headers,
        json={"title": "待补全素材", "type": "风格参考", "content": "初始正文"},
    )
    assert response.json()["success"] is True
    return response.json()["data"]["id"]


class TestMaterialDocumentAndVideo:
    @pytest.mark.asyncio
    async def test_video_temp_file_writer_reads_upload_in_fixed_chunks(self):
        """视频先逐块落临时文件，不能把上传流一次性读成整份内容。"""
        class ChunkedUpload:
            filename = "chunked.mp4"

            def __init__(self):
                self.read_sizes = []
                self.chunks = [b"one", b"two", b""]

            async def read(self, size):
                self.read_sizes.append(size)
                return self.chunks.pop(0)

        upload = ChunkedUpload()
        result = await _write_upload_to_temp_file(upload, max_bytes=100)
        assert result is not None
        temp_path, size = result
        try:
            assert size == 6
            assert temp_path.read_bytes() == b"onetwo"
            assert upload.read_sizes == [_UPLOAD_READ_CHUNK_BYTES] * 3
        finally:
            temp_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_document_returns_editable_text_and_metadata(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_material_kol(test_session, "ParseMaterialKol")

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/parse-document",
            headers=operator_headers,
            files={"file": ("脚本.txt", "这是可编辑的脚本文字。", "text/plain")},
        )

        body = response.json()
        assert body["success"] is True
        assert body["data"] == {
            "text": "这是可编辑的脚本文字。",
            "document_name": "脚本.txt",
            "document_type": "text/plain",
            "document_size": len("这是可编辑的脚本文字。".encode("utf-8")),
        }

    @pytest.mark.asyncio
    async def test_parse_document_rejects_oversize_before_parser_reads_again(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "OversizeDocumentMaterialKol")
        monkeypatch.setattr(
            "app.routers.operator_material_library.MAX_DOCUMENT_UPLOAD_BYTES", 4
        )

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/parse-document",
            headers=operator_headers,
            files={"file": ("脚本.txt", b"12345", "text/plain")},
        )

        assert response.json()["success"] is False
        assert "大小" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_edit_reference_persists_data_description_and_document_metadata(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_material_kol(test_session, "EditMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)

        response = await test_client.put(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}",
            headers=operator_headers,
            json={
                "title": "已编辑素材",
                "data_description": "点赞 3 万，转化稳定",
                "content": "运营修改后的正文",
                "document_name": "来源脚本.txt",
                "document_type": "text/plain",
                "document_size": 42,
            },
        )

        body = response.json()
        assert body["success"] is True
        assert body["data"]["data_description"] == "点赞 3 万，转化稳定"
        assert body["data"]["document_name"] == "来源脚本.txt"
        assert body["data"]["content"] == "运营修改后的正文"

    @pytest.mark.asyncio
    async def test_upload_then_playback_uses_private_object_key_and_short_url(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "VideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        uploaded_paths = []

        async def upload(key, path, *_args, **_kwargs):
            path = Path(path)
            assert path.exists()
            assert path.read_bytes() == b"video-binary"
            uploaded_paths.append(path)
            return key

        playback = AsyncMock(return_value="https://signed.example/video?expires=900")
        monkeypatch.setattr(
            "app.adapters.oss.upload_file_from_path", upload
        )
        monkeypatch.setattr(
            "app.adapters.oss.get_download_url", playback
        )

        upload_response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video",
            headers=operator_headers,
            files={"file": ("原片.mp4", b"video-binary", "video/mp4")},
        )
        upload_body = upload_response.json()
        assert upload_body["success"] is True
        assert upload_body["data"]["video_name"] == "原片.mp4"
        assert "video_oss_key" not in upload_body["data"]
        assert "url" not in upload_body["data"]

        playback_response = await test_client.get(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video/playback",
            headers=operator_headers,
        )
        assert playback_response.json()["data"] == {
            "url": "https://signed.example/video?expires=900",
            "expires_in": 900,
        }
        assert len(uploaded_paths) == 1
        assert playback.await_count == 1
        assert all(not path.exists() for path in uploaded_paths)

    @pytest.mark.asyncio
    async def test_video_rejects_declared_oversize_before_reading_full_file(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "OversizeVideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        upload = AsyncMock()
        monkeypatch.setattr("app.adapters.oss.upload_file_from_path", upload)

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video",
            headers={
                **operator_headers,
                "content-length": str(MAX_VIDEO_UPLOAD_BYTES + 1024 * 1024 + 1),
            },
            files={"file": ("原片.mp4", b"small-video", "video/mp4")},
        )

        assert response.json()["success"] is False
        assert "大小" in response.json()["message"]
        upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_video_stops_chunked_read_when_actual_file_exceeds_limit(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "ChunkLimitVideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        upload = AsyncMock()
        monkeypatch.setattr("app.adapters.oss.upload_file_from_path", upload)
        monkeypatch.setattr(
            "app.routers.operator_material_library.MAX_VIDEO_UPLOAD_BYTES", 4
        )

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video",
            headers=operator_headers,
            files={"file": ("原片.mp4", b"12345", "video/mp4")},
        )

        assert response.json()["success"] is False
        assert "大小" in response.json()["message"]
        upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_replacing_video_deletes_only_the_previous_private_object(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "ReplaceVideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        await test_session.execute(text(
            "UPDATE kol_references SET video_oss_key = :key WHERE id = :ref_id"
        ), {"key": "material-library/old/private.mp4", "ref_id": ref_id})
        await test_session.commit()
        upload = AsyncMock(side_effect=lambda key, *_args, **_kwargs: key)
        delete_object = AsyncMock()
        monkeypatch.setattr("app.adapters.oss.upload_file_from_path", upload)
        monkeypatch.setattr("app.adapters.oss.delete_file", delete_object)

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video",
            headers=operator_headers,
            files={"file": ("新原片.mp4", b"new-video-binary", "video/mp4")},
        )

        assert response.json()["success"] is True
        assert delete_object.await_count == 1
        assert delete_object.await_args.args[0] == "material-library/old/private.mp4"

    @pytest.mark.asyncio
    async def test_video_upload_failure_removes_temporary_file(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "FailedVideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        uploaded_paths = []

        async def upload(_key, path, *_args, **_kwargs):
            path = Path(path)
            assert path.exists()
            uploaded_paths.append(path)
            raise RuntimeError("OSS unavailable")

        monkeypatch.setattr("app.adapters.oss.upload_file_from_path", upload)

        response = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}/video",
            headers=operator_headers,
            files={"file": ("原片.mp4", b"video-binary", "video/mp4")},
        )

        assert response.json()["success"] is False
        assert uploaded_paths
        assert all(not path.exists() for path in uploaded_paths)

    @pytest.mark.asyncio
    async def test_reference_cannot_be_read_or_deleted_through_another_kol_path(
        self, test_client, operator_headers, test_session
    ):
        owner_kol_id = await _create_material_kol(test_session, "OwnerMaterialKol")
        other_kol_id = await _create_material_kol(test_session, "OtherMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, owner_kol_id)

        response = await test_client.delete(
            f"/api/tools/material-library/kols/{other_kol_id}/references/{ref_id}",
            headers=operator_headers,
        )
        assert response.json()["success"] is False

        detail_response = await test_client.get(
            f"/api/tools/material-library/kols/{owner_kol_id}", headers=operator_headers
        )
        all_refs = [ref for refs in detail_response.json()["data"]["references"].values() for ref in refs]
        assert any(ref["id"] == ref_id for ref in all_refs)

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_reference_then_deletes_its_video_object(
        self, test_client, operator_headers, test_session, monkeypatch
    ):
        kol_id = await _create_material_kol(test_session, "DeleteVideoMaterialKol")
        ref_id = await _create_reference(test_client, operator_headers, kol_id)
        await test_session.execute(text(
            "UPDATE kol_references SET video_oss_key = :key WHERE id = :ref_id"
        ), {"key": "material-library/test/private.mp4", "ref_id": ref_id})
        await test_session.commit()
        delete_object = AsyncMock()
        monkeypatch.setattr("app.adapters.oss.delete_file", delete_object)

        response = await test_client.delete(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}",
            headers=operator_headers,
        )

        assert response.json()["success"] is True
        assert delete_object.await_count == 1
        assert delete_object.await_args.args[0] == "material-library/test/private.mp4"
        assert delete_object.await_args.args[1] is test_session
        assert (await test_session.execute(text(
            "SELECT deleted_at FROM kol_references WHERE id = :ref_id"
        ), {"ref_id": ref_id})).scalar_one() is not None
