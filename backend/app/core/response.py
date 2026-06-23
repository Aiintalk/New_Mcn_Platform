from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Error code constants — kept in sync with MCN_M1_Base_API 第 3 节
# ---------------------------------------------------------------------------

class ErrorCode:
    OK = "OK"

    # 400
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # 401
    AUTH_INVALID_PASSWORD = "AUTH_INVALID_PASSWORD"
    AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"

    # 403
    AUTH_USER_DISABLED = "AUTH_USER_DISABLED"
    AUTH_FORCE_CHANGE_PASSWORD = "AUTH_FORCE_CHANGE_PASSWORD"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOOL_NOT_ONLINE = "TOOL_NOT_ONLINE"

    # 404
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    OUTPUT_NOT_FOUND = "OUTPUT_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"

    # 409
    USERNAME_ALREADY_EXISTS = "USERNAME_ALREADY_EXISTS"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"

    # 500
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # 502
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"


# ---------------------------------------------------------------------------
# Unified response model
# ---------------------------------------------------------------------------

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    code: str
    message: str
    data: Optional[T] = None


def success_response(data: T = None, message: str = "success") -> ApiResponse[T]:
    """Build a successful API response."""
    return ApiResponse(success=True, code=ErrorCode.OK, message=message, data=data)


def error_response(code: str, message: str) -> ApiResponse[None]:
    """Build an error API response."""
    return ApiResponse(success=False, code=code, message=message, data=None)
