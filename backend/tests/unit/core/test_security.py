"""Unit tests for app.core.security — JWT creation and verification."""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, verify_token


class TestCreateAccessToken:
    def test_create_access_token_valid_payload_returns_signed_jwt(self):
        token = create_access_token(user_id=1, username="admin", role="admin", token_version=0)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_access_token_contains_all_fields(self):
        token = create_access_token(user_id=42, username="test", role="operator", token_version=3)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["username"] == "test"
        assert payload["role"] == "operator"
        assert payload["token_version"] == 3
        assert "exp" in payload

    def test_create_access_token_expiry_matches_settings(self):
        before = datetime.now(tz=timezone.utc)
        token = create_access_token(user_id=1, username="a", role="a", token_version=0)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        expected = before + timedelta(hours=settings.jwt_expire_hours)
        # Allow 60s tolerance
        assert abs((exp - expected).total_seconds()) < 60


class TestVerifyToken:
    def test_verify_token_valid_token_returns_payload(self):
        token = create_access_token(user_id=1, username="admin", role="admin", token_version=0)
        payload = verify_token(token)
        assert payload["sub"] == "1"
        assert payload["username"] == "admin"

    def test_verify_token_expired_token_raises_401(self):
        expired_payload = {
            "sub": "1",
            "username": "admin",
            "role": "admin",
            "token_version": 0,
            "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=ALGORITHM)
        with pytest.raises(Exception) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_token_invalid_signature_raises_401(self):
        payload = {"sub": "1", "username": "x", "role": "x", "token_version": 0, "exp": 9999999999}
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
        with pytest.raises(Exception) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_token_malformed_token_raises_401(self):
        with pytest.raises(Exception) as exc_info:
            verify_token("not.a.valid.token")
        assert exc_info.value.status_code == 401

    def test_verify_token_error_code_is_AUTH_TOKEN_EXPIRED(self):
        with pytest.raises(Exception) as exc_info:
            verify_token("garbage")
        assert exc_info.value.detail["code"] == "AUTH_TOKEN_EXPIRED"
