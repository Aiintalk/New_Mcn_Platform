import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.seed import seed_initial_data
from app.services.kol_scheduler import tikhub_refresh_scheduler
from app.routers import health
from app.routers.auth import router as auth_router
from app.routers.admin_users import router as admin_users_router
from app.routers.workspace import router as workspace_router
from app.routers.admin_workspace import router as admin_workspace_router
from app.routers.tasks import router as tasks_router
from app.routers.outputs import router as outputs_router
from app.routers.files import router as files_router
from app.routers.admin_logs import router as admin_logs_router
from app.routers.admin_credentials import router as admin_credentials_router
from app.routers.admin_system import router as admin_system_router
from app.routers.admin_ai import router as admin_ai_router
from app.routers.admin_kols import router as admin_kols_router
from app.routers.intake_public import router as intake_public_router
from app.routers.operator_intake import router as operator_intake_router
from app.routers.operator_homepage import router as operator_homepage_router
from app.routers.admin_intake import router as admin_intake_router
from app.routers.operator_intake_direct import router as operator_intake_direct_router
from app.routers.persona import router as persona_router
from app.routers.admin_tikhub import router as admin_tikhub_router
from app.routers.admin_oss import router as admin_oss_router
from app.routers.admin_asr import router as admin_asr_router
from app.routers.operator_benchmark import router as operator_benchmark_router
from app.routers.admin_benchmark import router as admin_benchmark_router
from app.routers.operator_tiktok_writer import router as operator_tiktok_writer_router
from app.routers.operator_selling_point import router as operator_selling_point_router
from app.routers.admin_selling_point import router as admin_selling_point_router
from app.routers.operator_qianchuan_review import router as operator_qianchuan_review_router
from app.routers.admin_tiktok_writer import router as admin_tiktok_writer_router
from app.routers.admin_qianchuan_review import router as admin_qianchuan_review_router
from app.routers.admin_qianchuan_edit_review import router as admin_qianchuan_edit_review_router
from app.routers.tool_extract_frames import router as tool_extract_frames_router
from app.routers.tool_transcribe import router as tool_transcribe_router
from app.routers.tool_chat_stream import router as tool_chat_stream_router
from app.routers.tool_export_word import router as tool_export_word_router
from app.routers.tool_qianchuan_edit_review import router as tool_qianchuan_edit_review_router
from app.routers.operator_livestream_writer import router as operator_livestream_writer_router
from app.routers.admin_livestream_writer import router as admin_livestream_writer_router
from app.routers.operator_livestream_review import router as operator_livestream_review_router
from app.routers.admin_livestream_review import router as admin_livestream_review_router
from app.routers.operator_persona_review import router as operator_persona_review_router
from app.routers.admin_persona_review import router as admin_persona_review_router
from app.routers.operator_qianchuan_preview import router as operator_qianchuan_preview_router
from app.routers.admin_qianchuan_preview import router as admin_qianchuan_preview_router
from app.routers.operator_qianchuan_collection import router as operator_qianchuan_collection_router
from app.routers.operator_qianchuan_writer import router as operator_qianchuan_writer_router
from app.routers.admin_qianchuan_writer import router as admin_qianchuan_writer_router
from app.routers.operator_persona_writer import router as operator_persona_writer_router
from app.routers.admin_persona_writer import router as admin_persona_writer_router
from app.routers.operator_seeding_writer import router as operator_seeding_writer_router
from app.routers.admin_seeding_writer import router as admin_seeding_writer_router
from app.routers import operator_tiktok_review
from app.routers import admin_tiktok_review


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_initial_data()
    # 启动 KOL TikHub 定时刷新后台任务
    asyncio.create_task(tikhub_refresh_scheduler())
    yield


app = FastAPI(
    title="MCN Information System Platform",
    version="0.1.0",
    description="M1 Base API",
    lifespan=lifespan,
    redirect_slashes=False,
)


# ---------------------------------------------------------------------------
# Unified error handler — converts HTTPException to standard API envelope
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    All HTTPExceptions raised by auth middleware use detail={"code":..., "message":...}.
    Wrap them in the standard {success, code, message, data} envelope so the
    frontend request.ts can handle them uniformly.
    """
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = detail["code"]
        message = detail.get("message", str(exc.detail))
    else:
        code = "INTERNAL_ERROR"
        message = str(detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "code": code, "message": message, "data": None},
    )

# ---------------------------------------------------------------------------
# CORS (permissive for development; tighten in production)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Task-Id"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
app.include_router(admin_workspace_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(outputs_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(admin_logs_router, prefix="/api")
app.include_router(admin_credentials_router, prefix="/api")
app.include_router(admin_system_router, prefix="/api")
app.include_router(admin_ai_router, prefix="/api")
app.include_router(admin_kols_router, prefix="/api")
app.include_router(intake_public_router, prefix="/api")
app.include_router(operator_intake_router, prefix="/api")
app.include_router(operator_homepage_router, prefix="/api")
app.include_router(admin_intake_router, prefix="/api")
app.include_router(operator_intake_direct_router, prefix="/api")
app.include_router(persona_router)
app.include_router(admin_tikhub_router, prefix="/api")
app.include_router(admin_oss_router, prefix="/api")
app.include_router(admin_asr_router, prefix="/api")
app.include_router(operator_benchmark_router, prefix="/api")
app.include_router(admin_benchmark_router, prefix="/api")
app.include_router(operator_tiktok_writer_router, prefix="/api")
app.include_router(operator_selling_point_router, prefix="/api")
app.include_router(admin_selling_point_router, prefix="/api")
app.include_router(operator_qianchuan_review_router, prefix="/api")
app.include_router(admin_tiktok_writer_router, prefix="/api")
app.include_router(admin_qianchuan_review_router, prefix="/api")
app.include_router(admin_qianchuan_edit_review_router, prefix="/api")
app.include_router(tool_extract_frames_router, prefix="/api")
app.include_router(tool_transcribe_router, prefix="/api")
app.include_router(tool_chat_stream_router, prefix="/api")
app.include_router(tool_export_word_router, prefix="/api")
app.include_router(tool_qianchuan_edit_review_router, prefix="/api")
app.include_router(operator_livestream_writer_router, prefix="/api")
app.include_router(admin_livestream_writer_router, prefix="/api")
app.include_router(operator_livestream_review_router, prefix="/api")
app.include_router(admin_livestream_review_router, prefix="/api")
app.include_router(operator_persona_review_router, prefix="/api")
app.include_router(admin_persona_review_router, prefix="/api")
app.include_router(operator_qianchuan_preview_router, prefix="/api")
app.include_router(admin_qianchuan_preview_router, prefix="/api")
app.include_router(operator_qianchuan_collection_router, prefix="/api")
app.include_router(operator_tiktok_review.router, prefix="/api")
app.include_router(admin_tiktok_review.router, prefix="/api")
app.include_router(operator_qianchuan_writer_router, prefix="/api")
app.include_router(admin_qianchuan_writer_router, prefix="/api")
app.include_router(operator_persona_writer_router, prefix="/api")
app.include_router(admin_persona_writer_router, prefix="/api")
app.include_router(operator_seeding_writer_router, prefix="/api")
app.include_router(admin_seeding_writer_router, prefix="/api")
