"""
Direct-call coverage tests for operator_benchmark.py（Round 2）。

Round 1 的 test_operator_benchmark.py 经 test_client（ASGITransport）跑端点，
coverage 对端点体追踪不稳定（尤其 fetch/history/export_word 的函数体）。
这里直接 await 端点函数（绕过 require_operator，传 current_user=operator_user），
稳定记录函数体覆盖。analyze 是 SSE 流（返回 StreamingResponse），不在此直测。
纯测试，不改生产代码。
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.models.benchmark import BenchmarkAnalysis
from app.routers.operator_benchmark import (
    ExportRequest,
    FetchRequest,
    export_word,
    fetch_account,
    get_history_detail,
    list_history,
)


@pytest.mark.asyncio
async def test_fetch_account_direct_ok(test_session, operator_user):
    """直调 fetch_account（mock tikhub）→ 返回 video 统计。"""
    with patch("app.routers.operator_benchmark.tikhub_adapter") as mock_th:
        mock_th.resolve_sec_user_id = AsyncMock(return_value={"sec_user_id": "sec1", "nickname": "KOL"})
        mock_th.get_user_profile = AsyncMock(return_value={"nickname": "KOL"})
        mock_th.fetch_user_videos = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        mock_th.get_top10_videos.return_value = [{"id": 1}]
        mock_th.get_recent_30day_videos.return_value = [{"id": 2}]
        mock_th.format_videos_text.return_value = "text"

        resp = await fetch_account(
            FetchRequest(input="douyin://abc"),
            db=test_session,
            current_user=operator_user,
        )
    assert resp.data["sec_user_id"] == "sec1"
    assert resp.data["total_videos"] == 2


@pytest.mark.asyncio
async def test_list_history_direct(test_session, operator_user):
    """直调 list_history → 自己的分析（按 created_by 过滤）。"""
    test_session.add(BenchmarkAnalysis(account_name="dc_hist", status="completed", created_by=operator_user.id))
    await test_session.commit()

    resp = await list_history(db=test_session, current_user=operator_user)
    names = [a["account_name"] for a in resp.data]
    assert "dc_hist" in names


@pytest.mark.asyncio
async def test_get_history_detail_direct(test_session, operator_user):
    """直调 get_history_detail → 完整字段。"""
    a = BenchmarkAnalysis(account_name="dc_hd", status="completed", profile_result="p", plan_result="pl", created_by=operator_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    resp = await get_history_detail(a.id, db=test_session, current_user=operator_user)
    assert resp.data["profile_result"] == "p"


@pytest.mark.asyncio
async def test_export_word_direct_not_ready(test_session, operator_user):
    """直调 export_word，status≠completed → 400 NOT_READY。"""
    a = BenchmarkAnalysis(account_name="dc_nr", status="generating", created_by=operator_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    with pytest.raises(Exception) as exc:
        await export_word(
            ExportRequest(analysis_id=a.id, type="profile"),
            db=test_session,
            current_user=operator_user,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_export_word_direct_no_content(test_session, operator_user, tmp_path):
    """直调 export_word，completed 但内容空 → 400 NO_CONTENT。"""
    a = BenchmarkAnalysis(account_name="dc_nc", status="completed", profile_result="", plan_result="x", created_by=operator_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    with pytest.raises(Exception) as exc:
        await export_word(
            ExportRequest(analysis_id=a.id, type="profile"),
            db=test_session,
            current_user=operator_user,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_export_word_direct_ok(test_session, operator_user, tmp_path):
    """直调 export_word，completed 有内容（mock generate_docx 返回 tmp 文件）→ FileResponse。"""
    a = BenchmarkAnalysis(account_name="dc_ok", status="completed", profile_result="profile text", created_by=operator_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    fake_file = tmp_path / "report.docx"
    fake_file.write_bytes(b"fake docx")

    with patch("app.routers.operator_benchmark.benchmark_report.generate_docx", return_value=str(fake_file)):
        result = await export_word(
            ExportRequest(analysis_id=a.id, type="profile"),
            db=test_session,
            current_user=operator_user,
        )
    assert result.status_code == 200
