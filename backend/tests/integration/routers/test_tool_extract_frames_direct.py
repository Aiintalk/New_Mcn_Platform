"""
Direct-call coverage tests for tool_extract_frames.py。

直调 extract_frames 端点，patch shutil.which / _extract_frames，
覆盖 ffmpeg-missing / 空文件 / ValueError / TimeoutError / success /
internal-error 路径。`import shutil` 在函数内 → patch 全局 `shutil.which`。
"""
import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.routers.tool_extract_frames import extract_frames


class _FakeUploadFile:
    """伪造 starlette UploadFile（直调端点不依赖 Request 解析）。"""
    def __init__(self, filename: str, content: bytes = b"x"):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_extract_frames_ffmpeg_missing(operator_user):
    """shutil.which 找不到 ffprobe → 503。"""
    with patch("shutil.which", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await extract_frames(
                file=_FakeUploadFile("v.mp4"), count=8, current_user=operator_user,
            )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "DEPENDENCY_MISSING"


@pytest.mark.asyncio
async def test_extract_frames_empty_filename(operator_user):
    """filename 为空 → 400 INVALID_INPUT。"""
    with patch("shutil.which", return_value="/usr/bin/ffprobe"):
        with pytest.raises(HTTPException) as exc:
            await extract_frames(
                file=_FakeUploadFile(""), count=8, current_user=operator_user,
            )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_extract_frames_value_error_to_400(operator_user):
    """_extract_frames 抛 ValueError → 400 EXTRACT_FAILED。"""

    async def _boom(*a, **kw):
        raise ValueError("ffprobe 超时")

    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("app.routers.tool_extract_frames._extract_frames", new=_boom):
        with pytest.raises(HTTPException) as exc:
            await extract_frames(
                file=_FakeUploadFile("v.mp4", b"data"), count=8, current_user=operator_user,
            )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "EXTRACT_FAILED"
    assert "ffprobe" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_extract_frames_timeout_to_400(operator_user):
    """_extract_frames 抛 asyncio.TimeoutError → 400 EXTRACT_FAILED。"""

    async def _boom(*a, **kw):
        raise asyncio.TimeoutError()

    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("app.routers.tool_extract_frames._extract_frames", new=_boom):
        with pytest.raises(HTTPException) as exc:
            await extract_frames(
                file=_FakeUploadFile("v.mp4", b"data"), count=8, current_user=operator_user,
            )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "EXTRACT_FAILED"


@pytest.mark.asyncio
async def test_extract_frames_internal_error_to_500(operator_user):
    """_extract_frames 抛其他异常 → 500 INTERNAL_ERROR。"""

    async def _boom(*a, **kw):
        raise RuntimeError("boom")

    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("app.routers.tool_extract_frames._extract_frames", new=_boom):
        with pytest.raises(HTTPException) as exc:
            await extract_frames(
                file=_FakeUploadFile("v.mp4", b"data"), count=8, current_user=operator_user,
            )
    assert exc.value.status_code == 500
    assert exc.value.detail["code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_extract_frames_success(operator_user):
    """_extract_frames 返回 (frames, duration) → 信封 data。"""

    async def _ok(*a, **kw):
        return ([{"time": 0.0, "base64": "data:image/jpeg;base64,AAA"}], 5.0)

    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("app.routers.tool_extract_frames._extract_frames", new=_ok):
        resp = await extract_frames(
            file=_FakeUploadFile("v.mp4", b"data"), count=8, current_user=operator_user,
        )
    assert resp.data["duration"] == 5.0
    assert len(resp.data["frames"]) == 1
    assert resp.data["frames"][0]["time"] == 0.0


# ---------------------------------------------------------------------------
# _extract_frames helper：覆盖 ffprobe 时长解析失败 / duration<=0 / 成功路径 +
# ffmpeg 单帧超时跳过 / finally 清理。
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_helper_invalid_duration_string():
    """ffprobe 输出无法 float → ValueError「无法读取视频时长」。"""
    from app.routers.tool_extract_frames import _extract_frames

    class _Proc:
        async def communicate(self):
            return (b"not-a-number", b"")

    async def _fake_subprocess(*a, **kw):
        return _Proc()

    with patch("app.routers.tool_extract_frames.asyncio.create_subprocess_exec",
               new=_fake_subprocess):
        with pytest.raises(ValueError) as exc:
            await _extract_frames("/tmp/nonexistent_xxx.mp4", count=4)
    assert "无法读取视频时长" in str(exc.value)


@pytest.mark.asyncio
async def test_helper_zero_duration():
    """duration=0 → ValueError。"""
    from app.routers.tool_extract_frames import _extract_frames

    class _Proc:
        async def communicate(self):
            return (b"0", b"")

    async def _fake_subprocess(*a, **kw):
        return _Proc()

    with patch("app.routers.tool_extract_frames.asyncio.create_subprocess_exec",
               new=_fake_subprocess):
        with pytest.raises(ValueError):
            await _extract_frames("/tmp/nonexistent_xxx.mp4", count=4)


@pytest.mark.asyncio
async def test_helper_success_with_short_video(tmp_path):
    """短视频（duration < 4）→ 只取固定帧（0/1/2 < duration），ffmpeg 截图 + finally 清理。

    用 tmp_path 模拟 video_path / 输出目录；mock subprocess 返回成功 communicate；
    让 ffmpeg 真实写入一个临时 jpg，验证 frames 收集。
    """
    from pathlib import Path
    from app.routers.tool_extract_frames import _extract_frames

    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake")

    class _ProbeProc:
        async def communicate(self):
            return (b"2.5", b"")  # duration=2.5s → 取 [0.0, 1.0, 2.0] 都 < 2.5

    class _FfmpegProc:
        async def communicate(self):
            return (b"", b"")

    call_count = {"n": 0}

    async def _fake_subprocess(*args, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _ProbeProc()
        # ffmpeg 调用：args 形如 ['ffmpeg','-ss',t,'-i',video,...,str(out_path),'-y',...]
        # 找到 .jpg 结尾的参数（即 out_path）写入假图像
        for a in args:
            if isinstance(a, str) and a.endswith(".jpg"):
                Path(a).parent.mkdir(parents=True, exist_ok=True)
                Path(a).write_bytes(b"\xff\xd8\xff\xe0fakejpg\xff\xd9")
                break
        return _FfmpegProc()

    with patch("app.routers.tool_extract_frames.asyncio.create_subprocess_exec",
               new=_fake_subprocess):
        frames, duration = await _extract_frames(str(video), count=8)

    assert duration == 2.5
    assert len(frames) > 0
    assert all("base64" in f for f in frames)
