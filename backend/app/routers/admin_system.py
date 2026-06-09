"""
app/routers/admin_system.py

管理员系统维护接口：
- POST /api/admin/system/ai-test      — 测试 AI Key 池连通性
- POST /api/admin/system/tikhub-test  — 测试 TikHub Key 池连通性
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import ai as ai_adapter
from app.adapters import tikhub as tikhub_adapter
from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.middlewares.auth import require_admin
from app.models.user import User

router = APIRouter(prefix="/admin/system", tags=["admin-system"])


@router.post("/ai-test", response_model=ApiResponse)
async def test_ai_connection(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试 AI Key 池连通性。
    发送一条简单消息，返回模型、延迟、回复内容。
    权限：admin + 已改密
    """
    result = await ai_adapter.test_connection(db)
    return success_response(data=result)


@router.post("/tikhub-test", response_model=ApiResponse)
async def test_tikhub_connection(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试 TikHub Key 池连通性。
    调用真实接口验证 Key 可用性。
    权限：admin + 已改密
    """
    result = await tikhub_adapter.test_connection(db)
    return success_response(data=result)
