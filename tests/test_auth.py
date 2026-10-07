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