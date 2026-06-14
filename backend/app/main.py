import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from app.routers.operator_benchmark import router as operator_benchmark_router
from app.routers.admin_benchmark import router as admin_benchmark_router
from app.routers.operator_tiktok_writer import router as operator_tiktok_writer_router
from app.routers.operator_selling_point import router as operator_selling_point_router
from app.routers.admin_selling_point import router as admin_selling_point_router
from app.routers.operator_qianchuan_review import router as operator_qianchuan_review_router
from app.routers.admin_tiktok_writer import router as admin_tiktok_writer_router
from app.routers.admin_qianchuan_review import router as admin_qianchuan_review_router
from app.routers.tool_extract_frames import router as tool_extract_frames_router
from app.routers.tool_transcribe import router as tool_transcribe_router
from app.routers.tool_chat_stream import router as tool_chat_stream_router
from app.routers.tool_export_word import router as tool_export_word_router
from app.routers.tool_qianchuan_edit_review import router as tool_qianchuan_edit_review_router


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
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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
app.include_router(operator_benchmark_router, prefix="/api")
app.include_router(admin_benchmark_router, prefix="/api")
app.include_router(operator_tiktok_writer_router, prefix="/api")
app.include_router(operator_selling_point_router, prefix="/api")
app.include_router(admin_selling_point_router, prefix="/api")
app.include_router(operator_qianchuan_review_router, prefix="/api")
app.include_router(admin_tiktok_writer_router, prefix="/api")
app.include_router(admin_qianchuan_review_router, prefix="/api")
app.include_router(tool_extract_frames_router, prefix="/api")
app.include_router(tool_transcribe_router, prefix="/api")
app.include_router(tool_chat_stream_router, prefix="/api")
app.include_router(tool_export_word_router, prefix="/api")
app.include_router(tool_qianchuan_edit_review_router, prefix="/api")
