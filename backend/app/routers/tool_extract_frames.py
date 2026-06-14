"""
app/routers/tool_extract_frames.py

POST /api/tools/extract-frames
接收视频文件，用 ffmpeg 截帧，返回 base64 帧列表。
"""
import asyncio
import base64
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.response import success_response
from app.middlewares.auth import require_password_changed
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])

_TOTAL_TIMEOUT = 60  # 总截帧超时（秒）
_FRAME_TIMEOUT = 10  # 单帧 ffmpeg 超时（秒）


async def _extract_frames(
    video_path: str,
    count: int,
) -> tuple[list[dict], float]:
    """
    用 ffprobe 读时长，再逐帧 ffmpeg 截图，返回 (frames, duration)。
    frames: [{"time": float, "base64": "data:image/jpeg;base64,..."}]
    失败时抛 ValueError。
    """
    # 1. ffprobe 读时长
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=15)
    except asyncio.TimeoutError:
        raise ValueError("ffprobe 超时")

    duration_str = stdout.decode().strip()
    try:
        duration = float(duration_str)
    except ValueError:
        raise ValueError("无法读取视频时长")
    if duration <= 0:
        raise ValueError("无法读取视频时长")

    # 2. 计算截帧时间点：固定 0s/1s/2s + 剩余均匀分布
    fixed = [0.0, 1.0, 2.0]
    times: list[float] = [t for t in fixed if t < duration]
    if duration > 4 and count > len(times):
        remaining = count - len(times)
        step = (duration - 3.0) / (remaining + 1)
        for i in range(1, remaining + 1):
            t = min(3.0 + step * i, duration - 0.1)
            times.append(round(t, 1))
    times = times[:count]

    # 3. 逐帧截图
    tmp_dir = Path(f"/tmp/frames-{uuid.uuid4()}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict] = []

    try:
        for t in times:
            out_path = tmp_dir / f"frame_{t:.2f}.jpg"
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-ss", f"{t:.2f}",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "3",
                "-vf", "scale='min(720,iw)':-2",
                str(out_path),
                "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=_FRAME_TIMEOUT)
            except asyncio.TimeoutError:
                continue  # 跳过超时帧

            if out_path.exists():
                img_bytes = out_path.read_bytes()
                b64 = base64.b64encode(img_bytes).decode()
                frames.append({
                    "time": round(t, 1),
                    "base64": f"data:image/jpeg;base64,{b64}",
                })
                out_path.unlink(missing_ok=True)
    finally:
        # 清理临时目录（失败也忽略）
        try:
            video_file = Path(video_path)
            if video_file.exists():
                video_file.unlink()
            tmp_dir.rmdir()
        except Exception:
            pass

    return frames, round(duration, 1)


@router.post("/extract-frames")
async def extract_frames(
    file: UploadFile = File(...),
    count: int = Form(default=8),
    current_user: User = Depends(require_password_changed),
):
    """截帧接口：接收视频，返回 base64 帧列表和时长。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "请上传视频文件"})

    # 保存到临时文件
    ext = Path(file.filename).suffix or ".mp4"
    tmp_dir = Path(f"/tmp/frames-{uuid.uuid4()}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(tmp_dir / f"input{ext}")

    content = await file.read()
    Path(video_path).write_bytes(content)

    try:
        frames, duration = await asyncio.wait_for(
            _extract_frames(video_path, count),
            timeout=_TOTAL_TIMEOUT,
        )
    except (ValueError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=400, detail={"code": "EXTRACT_FAILED", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": f"截帧失败: {e}"})

    return success_response(data={"frames": frames, "duration": duration})
