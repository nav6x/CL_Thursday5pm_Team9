import pytest
from unittest.mock import MagicMock
 
from app import app as flask_app
import routes.auth as auth


def test_signup_missing_email(monkeypatch):
    """Signup without an email should fail before hitting Supabase at all."""
    with flask_app.test_request_context(
        "/api/auth/signup",
        method="POST",
        json={"password": "hunter2", "full_name": "Jamie Chen"},
    ):
        response, status_code = auth.signup()
 
        assert status_code == 400
        assert response.get_json()["error"] == \
            "email, password, and full_name are required"

def test_signup_success(monkeypatch):
    """A fully valid signup should succeed and create the account."""
    mock_user = MagicMock(id="user-123")
    mock_result = MagicMock(user=mock_user)

    mock_supabase_auth = MagicMock()
    mock_supabase_auth.auth.sign_up.return_value = mock_result
    monkeypatch.setattr(auth, "supabase_auth", mock_supabase_auth)

    mock_supabase = MagicMock()
    monkeypatch.setattr(auth, "supabase", mock_supabase)

    with flask_app.test_request_context(
        "/api/auth/signup",
        method="POST",
        json={"email": "jamie@example.com", "password": "securepass", "full_name": "Jamie Chen"},
    ):
        response, status_code = auth.signup()

        assert status_code == 201
        assert response.get_json()["user_id"] == "user-123"

def test_signup_password_too_short():
    """Signup with a password under 6 characters should fail before
    hitting Supabase at all."""
    with flask_app.test_request_context(
        "/api/auth/signup",
        method="POST",
        json={"email": "jamie@example.com", "password": "abc12", "full_name": "Jamie Chen"},
    ):
        response, status_code = auth.signup()

        assert status_code == 400
        assert response.get_json()["error"] == \
            "Password must be at least 6 characters long"


def test_signup_password_exactly_six_chars(monkeypatch):
    """A password of exactly 6 characters is the boundary case — it
    should pass validation and proceed to call Supabase."""
    mock_user = MagicMock(id="user-123")
    mock_result = MagicMock(user=mock_user)

    mock_supabase_auth = MagicMock()
    mock_supabase_auth.auth.sign_up.return_value = mock_result
    monkeypatch.setattr(auth, "supabase_auth", mock_supabase_auth)

    mock_supabase = MagicMock()
    monkeypatch.setattr(auth, "supabase", mock_supabase)

    with flask_app.test_request_context(
        "/api/auth/signup",
        method="POST",
        json={"email": "jamie@example.com", "password": "abc123", "full_name": "Jamie Chen"},
    ):
        response, status_code = auth.signup()

        assert status_code == 201
        mock_supabase_auth.auth.sign_up.assert_called_once()