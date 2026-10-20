"""Backend tests for the password reset routes.

Supabase is replaced with mocks, so these run with no network, no real
account and no emails sent. Run from the repo root:  pytest tests/test_reset_password.py
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import routes.auth as auth_module  # noqa: E402

GOOD_PASSWORD = "Sunrise2026"
FORGOT = "/api/auth/forgot-password"
RESET = "/api/auth/reset-password"


@pytest.fixture
def ctx(monkeypatch):
    """A test client plus the two fake Supabase clients the routes talk to."""
    fake_anon = MagicMock(name="supabase_auth")     # used for emails + verifying the token
    fake_service = MagicMock(name="supabase")       # used for the admin password update
    fake_anon.auth.verify_otp.return_value = SimpleNamespace(user=SimpleNamespace(id="user-123"))

    monkeypatch.setattr(auth_module, "supabase_auth", fake_anon)
    monkeypatch.setattr(auth_module, "supabase", fake_service)

    app = Flask(__name__)
    app.register_blueprint(auth_module.auth_bp)
    return SimpleNamespace(client=app.test_client(), anon=fake_anon, service=fake_service)


# ---------- POST /api/auth/forgot-password ----------

def test_forgot_requires_email(ctx):
    res = ctx.client.post(FORGOT, json={"email": "   "})
    assert res.status_code == 400
    ctx.anon.auth.reset_password_for_email.assert_not_called()


def test_forgot_sends_email_with_cleaned_address_and_redirect(ctx):
    res = ctx.client.post(FORGOT, json={"email": "  Kev@Example.COM "})
    assert res.status_code == 200
    ctx.anon.auth.reset_password_for_email.assert_called_once_with(
        "kev@example.com", {"redirect_to": auth_module.RESET_REDIRECT_URL}
    )


def test_forgot_redirect_points_at_the_reset_page(ctx):
    assert auth_module.RESET_REDIRECT_URL.endswith("/reset-password.html")


def test_forgot_does_not_reveal_whether_account_exists(ctx):
    ok = ctx.client.post(FORGOT, json={"email": "real@example.com"})
    ctx.anon.auth.reset_password_for_email.side_effect = Exception("User not found")
    missing = ctx.client.post(FORGOT, json={"email": "nobody@example.com"})

    assert ok.status_code == missing.status_code == 200
    assert ok.get_json() == missing.get_json()


# ---------- POST /api/auth/reset-password ----------

def test_reset_succeeds_with_valid_token_and_password(ctx):
    res = ctx.client.post(RESET, json={"token_hash": "abc123", "password": GOOD_PASSWORD})

    assert res.status_code == 200
    ctx.anon.auth.verify_otp.assert_called_once_with({"token_hash": "abc123", "type": "recovery"})
    ctx.service.auth.admin.update_user_by_id.assert_called_once_with(
        "user-123", {"password": GOOD_PASSWORD}
    )


@pytest.mark.parametrize("body", [
    {"password": GOOD_PASSWORD},                       # no token at all
    {"token_hash": "", "password": GOOD_PASSWORD},     # empty token
    {"token_hash": "   ", "password": GOOD_PASSWORD},  # blank token
])
def test_reset_rejects_missing_token(ctx, body):
    res = ctx.client.post(RESET, json=body)
    assert res.status_code == 400
    ctx.service.auth.admin.update_user_by_id.assert_not_called()


@pytest.mark.parametrize("password", [
    "",            # empty
    "Ab1",         # too short
    "Abcdef1",     # 7 characters, one short of the minimum
    "12345678",    # numbers only
    "abcdefgh",    # letters only
])
def test_reset_rejects_weak_passwords(ctx, password):
    res = ctx.client.post(RESET, json={"token_hash": "abc123", "password": password})
    assert res.status_code == 400
    assert "error" in res.get_json()
    ctx.service.auth.admin.update_user_by_id.assert_not_called()


def test_reset_accepts_exactly_minimum_length(ctx):
    res = ctx.client.post(RESET, json={"token_hash": "abc123", "password": "Abcdefg1"})  # 8 chars
    assert res.status_code == 200


def test_reset_rejects_invalid_or_expired_token(ctx):
    ctx.anon.auth.verify_otp.side_effect = Exception("Token has expired or is invalid")
    res = ctx.client.post(RESET, json={"token_hash": "bad", "password": GOOD_PASSWORD})

    assert res.status_code == 400
    assert "invalid or has expired" in res.get_json()["error"]
    ctx.service.auth.admin.update_user_by_id.assert_not_called()


def test_reset_rejects_token_that_returns_no_user(ctx):
    ctx.anon.auth.verify_otp.return_value = SimpleNamespace(user=None)
    res = ctx.client.post(RESET, json={"token_hash": "abc123", "password": GOOD_PASSWORD})

    assert res.status_code == 400
    ctx.service.auth.admin.update_user_by_id.assert_not_called()


def test_reset_link_cannot_be_reused(ctx):
    first = ctx.client.post(RESET, json={"token_hash": "abc123", "password": GOOD_PASSWORD})
    assert first.status_code == 200

    # Supabase rejects a recovery token once it has been used.
    ctx.anon.auth.verify_otp.side_effect = Exception("Token has expired or is invalid")
    second = ctx.client.post(RESET, json={"token_hash": "abc123", "password": "AnotherPass9"})

    assert second.status_code == 400
    assert ctx.service.auth.admin.update_user_by_id.call_count == 1  # only the first reset went through


def test_reset_reports_supabase_error_when_update_fails(ctx):
    ctx.service.auth.admin.update_user_by_id.side_effect = Exception("Password update failed")
    res = ctx.client.post(RESET, json={"token_hash": "abc123", "password": GOOD_PASSWORD})

    assert res.status_code == 400
    assert "Password update failed" in res.get_json()["error"]


def test_reset_uses_service_client_for_update_and_anon_client_for_verify(ctx):
    ctx.client.post(RESET, json={"token_hash": "abc123", "password": GOOD_PASSWORD})
    # The admin call must go through the service-role client, never the anon one.
    ctx.service.auth.admin.update_user_by_id.assert_called_once()
    ctx.anon.auth.admin.update_user_by_id.assert_not_called()


def test_reset_succeeds_with_valid_access_token(ctx):
    ctx.anon.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id="user-456"))
    res = ctx.client.post(RESET, json={"access_token": "valid-recovery-jwt", "password": GOOD_PASSWORD})

    assert res.status_code == 200
    ctx.anon.auth.get_user.assert_called_once_with("valid-recovery-jwt")
    ctx.service.auth.admin.update_user_by_id.assert_called_once_with(
        "user-456", {"password": GOOD_PASSWORD}
    )


def test_reset_rejects_invalid_access_token(ctx):
    ctx.anon.auth.get_user.side_effect = Exception("Invalid token")
    res = ctx.client.post(RESET, json={"access_token": "expired-jwt", "password": GOOD_PASSWORD})

    assert res.status_code == 400
    assert "invalid or has expired" in res.get_json()["error"]
    ctx.service.auth.admin.update_user_by_id.assert_not_called()
