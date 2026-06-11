"""Unit tests for app.core.response — ApiResponse, success_response, error_response, ErrorCode."""
from app.core.response import ApiResponse, ErrorCode, error_response, success_response


class TestSuccessResponse:
    def test_success_response_returns_correct_structure(self):
        resp = success_response(data={"key": "value"})
        assert resp.success is True
        assert resp.code == ErrorCode.OK
        assert resp.message == "success"
        assert resp.data == {"key": "value"}

    def test_success_response_without_data(self):
        resp = success_response()
        assert resp.data is None

    def test_success_response_custom_message(self):
        resp = success_response(data=None, message="密码修改成功，请重新登录")
        assert resp.message == "密码修改成功，请重新登录"

    def test_success_response_with_list_data(self):
        resp = success_response(data=[1, 2, 3])
        assert resp.data == [1, 2, 3]


class TestErrorResponse:
    def test_error_response_returns_correct_structure(self):
        resp = error_response(ErrorCode.VALIDATION_ERROR, "参数错误")
        assert resp.success is False
        assert resp.code == ErrorCode.VALIDATION_ERROR
        assert resp.message == "参数错误"
        assert resp.data is None

    def test_error_response_auth_code(self):
        resp = error_response(ErrorCode.AUTH_TOKEN_EXPIRED, "Token 过期")
        assert resp.code == "AUTH_TOKEN_EXPIRED"


class TestErrorCode:
    def test_all_error_codes_are_strings(self):
        for attr in dir(ErrorCode):
            if attr.startswith("_"):
                continue
            value = getattr(ErrorCode, attr)
            if isinstance(value, str):
                assert isinstance(value, str)

    def test_key_error_codes_exist(self):
        assert ErrorCode.OK == "OK"
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.AUTH_TOKEN_MISSING == "AUTH_TOKEN_MISSING"
        assert ErrorCode.AUTH_TOKEN_EXPIRED == "AUTH_TOKEN_EXPIRED"
        assert ErrorCode.PERMISSION_DENIED == "PERMISSION_DENIED"
        assert ErrorCode.USERNAME_ALREADY_EXISTS == "USERNAME_ALREADY_EXISTS"


class TestApiResponseModel:
    def test_api_response_serializes_correctly(self):
        resp = ApiResponse(success=True, code="OK", message="success", data={"id": 1})
        d = resp.model_dump()
        assert d["success"] is True
        assert d["data"]["id"] == 1

    def test_api_response_data_defaults_to_none(self):
        resp = ApiResponse(success=False, code="ERR", message="error")
        assert resp.data is None
