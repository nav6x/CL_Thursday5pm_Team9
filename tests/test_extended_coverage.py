"""
Extended test suite designed to maximize backend code coverage across:
- app.py (health, page routes, 404 & 500 error handlers)
- auth_utils.py (login_required, get_role_in_project, require_role)
- routes/columns.py (list_columns, rename with position)
- routes/notifications.py (invalid limit fallback)
- routes/projects.py (list_my_projects, list_members, add/update/delete member, add_all, update/delete project)
- routes/tasks.py (delete_task, set_assignees, list_task_activity)
- routes/auth.py (MFA enroll, confirm, status, unenroll, verify-login)
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g, jsonify

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app as main_app
import auth_utils
import routes.columns as columns
import routes.notifications as notifications
import routes.projects as projects
import routes.tasks as tasks
import routes.auth as auth_module


# ============================================================================
# 1. app.py (Health, Page Serving, Error Handlers)
# ============================================================================

def test_app_health():
    client = main_app.app.test_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_app_page_routes():
    client = main_app.app.test_client()
    for route in ["/", "/index.html", "/board.html", "/reset-password.html"]:
        res = client.get(route)
        assert res.status_code == 200


def test_app_404_error_handler():
    client = main_app.app.test_client()
    res = client.get("/api/non-existent-route-404")
    assert res.status_code == 404
    assert res.get_json() == {"error": "That endpoint doesn't exist"}


def test_app_500_error_handler():
    test_app = Flask(__name__)

    @test_app.route("/crash")
    def crash():
        raise RuntimeError("Database connection crashed")

    test_app.register_error_handler(500, main_app.server_error)
    client = test_app.test_client()
    res = client.get("/crash")
    assert res.status_code == 500
    assert "Database connection crashed" in res.get_json()["error"]


# ============================================================================
# 2. auth_utils.py (login_required, get_role_in_project, require_role)
# ============================================================================

def test_login_required_missing_header():
    @auth_utils.login_required
    def dummy():
        return jsonify({"ok": True}), 200

    test_app = Flask(__name__)
    with test_app.test_request_context("/"):
        res, code = dummy()
        assert code == 401
        assert "Missing or invalid Authorization header" in res.get_json()["error"]


def test_login_required_invalid_token(monkeypatch):
    fake_auth = MagicMock()
    fake_auth.auth.get_user.side_effect = Exception("Expired token")
    monkeypatch.setattr(auth_utils, "supabase_auth", fake_auth)

    @auth_utils.login_required
    def dummy():
        return jsonify({"ok": True}), 200

    test_app = Flask(__name__)
    with test_app.test_request_context("/", headers={"Authorization": "Bearer bad-token"}):
        res, code = dummy()
        assert code == 401
        assert "Invalid or expired session" in res.get_json()["error"]


def test_login_required_no_user_on_token(monkeypatch):
    fake_auth = MagicMock()
    fake_auth.auth.get_user.return_value = SimpleNamespace(user=None)
    monkeypatch.setattr(auth_utils, "supabase_auth", fake_auth)

    @auth_utils.login_required
    def dummy():
        return jsonify({"ok": True}), 200

    test_app = Flask(__name__)
    with test_app.test_request_context("/", headers={"Authorization": "Bearer token-with-no-user"}):
        res, code = dummy()
        assert code == 401
        assert "Invalid or expired session" in res.get_json()["error"]


def test_login_required_valid_token(monkeypatch):
    fake_auth = MagicMock()
    fake_user = SimpleNamespace(id="user-123", email="user@example.com")
    fake_auth.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    monkeypatch.setattr(auth_utils, "supabase_auth", fake_auth)

    @auth_utils.login_required
    def dummy():
        return jsonify({"user_id": g.user.id}), 200

    test_app = Flask(__name__)
    with test_app.test_request_context("/", headers={"Authorization": "Bearer valid-token"}):
        res, code = dummy()
        assert code == 200
        assert res.get_json()["user_id"] == "user-123"


def test_get_role_in_project_roles(monkeypatch):
    for role in ["leader", "project_leader", "scrum_master", "product_owner"]:
        monkeypatch.setattr(auth_utils, "maybe_one", lambda query: {"role": role})
        assert auth_utils.get_role_in_project("u1", "p1") == "leader"

    monkeypatch.setattr(auth_utils, "maybe_one", lambda query: {"role": "qa_engineer"})
    assert auth_utils.get_role_in_project("u1", "p1") == "qa_engineer"

    monkeypatch.setattr(auth_utils, "maybe_one", lambda query: {"role": "developer"})
    assert auth_utils.get_role_in_project("u1", "p1") == "developer"


def test_get_role_in_project_fallback_creator(monkeypatch):
    # First call for project_members returns None, second call for projects returns created_by
    calls = []
    def fake_maybe_one(query):
        calls.append(query)
        if len(calls) == 1:
            return None
        return {"created_by": "creator-123"}

    monkeypatch.setattr(auth_utils, "maybe_one", fake_maybe_one)
    assert auth_utils.get_role_in_project("creator-123", "p1") == "leader"

    calls.clear()
    assert auth_utils.get_role_in_project("other-user", "p1") is None


def test_require_role_decorator(monkeypatch):
    test_app = Flask(__name__)

    @auth_utils.require_role("leader")
    def dummy(project_id=None):
        return jsonify({"ok": True}), 200

    # Missing project_id
    with test_app.test_request_context("/"):
        g.user = SimpleNamespace(id="u1")
        res, code = dummy()
        assert code == 400
        assert "project_id is required" in res.get_json()["error"]

    # Non-member
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda uid, pid: None)
    with test_app.test_request_context("/"):
        g.user = SimpleNamespace(id="u1")
        res, code = dummy("p1")
        assert code == 403
        assert "not a member" in res.get_json()["error"]

    # Role not allowed
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda uid, pid: "developer")
    with test_app.test_request_context("/"):
        g.user = SimpleNamespace(id="u1")
        res, code = dummy("p1")
        assert code == 403
        assert "requires role: leader" in res.get_json()["error"]

    # Success
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda uid, pid: "leader")
    with test_app.test_request_context("/"):
        g.user = SimpleNamespace(id="u1")
        res, code = dummy("p1")
        assert code == 200
        assert res.get_json()["ok"] is True


# ============================================================================
# 3. routes/columns.py (list_columns, rename position)
# ============================================================================

def test_columns_list_and_position_rename(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value \
        .execute.return_value.data = [{"id": "c1", "name": "To Do", "position": 0}]

    monkeypatch.setattr(columns, "supabase", mock_supabase)
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda u, p: "leader")

    test_app = Flask(__name__)
    with test_app.test_request_context("/api/projects/p1/columns"):
        g.user = SimpleNamespace(id="u1")
        res, code = columns.list_columns.__wrapped__("p1")
        assert code == 200
        assert res.get_json()[0]["name"] == "To Do"

    # Rename with position
    mock_supabase.table.return_value.update.return_value.eq.return_value \
        .execute.return_value.data = [{"id": "c1", "position": 2}]
    with test_app.test_request_context("/api/projects/p1/columns/c1", method="PATCH", json={"position": 2}):
        g.user = SimpleNamespace(id="u1")
        res, code = columns.rename_column.__wrapped__("p1", "c1")
        assert code == 200
        assert res.get_json()["position"] == 2


# ============================================================================
# 4. routes/notifications.py (invalid limit fallback)
# ============================================================================

def test_notifications_invalid_limit(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value \
        .execute.return_value.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .execute.return_value.count = 0

    monkeypatch.setattr(notifications, "supabase", mock_supabase)

    test_app = Flask(__name__)
    with test_app.test_request_context("/api/notifications?limit=invalid_int"):
        g.user = SimpleNamespace(id="u1")
        res, code = notifications.list_notifications.__wrapped__()
        assert code == 200
        assert res.get_json()["unread_count"] == 0


# ============================================================================
# 5. routes/projects.py (list_my_projects, members, project management)
# ============================================================================

def test_projects_list_my_projects(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"role": "developer", "projects": {"id": "p1", "name": "Sprint 1", "created_at": "2026-10-01"}}
    ]
    monkeypatch.setattr(projects, "supabase", mock_supabase)
    monkeypatch.setattr(projects, "maybe_one", lambda q: {"full_name": "Alice [QA Engineer]"})

    test_app = Flask(__name__)
    with test_app.test_request_context("/api/projects"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.list_my_projects.__wrapped__()
        assert code == 200
        data = res.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Sprint 1"
        assert data[0]["my_agile_role"] == "QA Engineer"


def test_projects_list_members(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"role": "leader", "profiles": {"id": "u1", "full_name": "Bob [Project Leader]", "email": "bob@example.com"}}
    ]
    monkeypatch.setattr(projects, "supabase", mock_supabase)

    test_app = Flask(__name__)
    with test_app.test_request_context("/api/projects/p1/members"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.list_members.__wrapped__("p1")
        assert code == 200
        members = res.get_json()
        assert members[0]["agile_role"] == "Project Leader"
        assert members[0]["profiles"]["full_name"] == "Bob"


def test_projects_add_member_validation_and_success(monkeypatch):
    test_app = Flask(__name__)
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda u, p: "leader")

    # Invalid role
    with test_app.test_request_context("/api/projects/p1/members", method="POST", json={"role": "superman"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_member.__wrapped__("p1")
        assert code == 400
        assert "role must be one of" in res.get_json()["error"]

    # Missing email and user_id
    with test_app.test_request_context("/api/projects/p1/members", method="POST", json={"role": "developer"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_member.__wrapped__("p1")
        assert code == 400
        assert "email or user_id required" in res.get_json()["error"]

    # Non existent email
    monkeypatch.setattr(projects, "maybe_one", lambda q: None)
    with test_app.test_request_context("/api/projects/p1/members", method="POST", json={"email": "nobody@example.com"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_member.__wrapped__("p1")
        assert code == 404

    # Already a member
    calls = []
    def fake_maybe_one(q):
        calls.append(q)
        if len(calls) == 1:
            return {"id": "target-u", "email": "target@example.com", "full_name": "Target User"}
        return {"id": "membership-1"}

    monkeypatch.setattr(projects, "maybe_one", fake_maybe_one)
    with test_app.test_request_context("/api/projects/p1/members", method="POST", json={"email": "target@example.com"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_member.__wrapped__("p1")
        assert code == 200
        assert "already a member" in res.get_json()["message"]

    # Success adding new member
    calls.clear()
    def fake_maybe_one_new(q):
        calls.append(q)
        if len(calls) == 1:
            return {"id": "target-u", "email": "target@example.com", "full_name": "Target User"}
        return None

    mock_supabase = MagicMock()
    monkeypatch.setattr(projects, "supabase", mock_supabase)
    monkeypatch.setattr(projects, "maybe_one", fake_maybe_one_new)
    monkeypatch.setattr(projects, "display_name", lambda u: "Admin")
    monkeypatch.setattr(projects, "project_name", lambda p: "Project Alpha")
    monkeypatch.setattr(projects, "create_notifications", lambda *args, **kwargs: None)

    with test_app.test_request_context("/api/projects/p1/members", method="POST", json={"email": "target@example.com", "role": "developer"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_member.__wrapped__("p1")
        assert code == 201
        assert res.get_json()["message"] == "Member added"


def test_projects_add_all_members(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [{"id": "u2"}, {"id": "u3"}]
    monkeypatch.setattr(projects, "supabase", mock_supabase)
    monkeypatch.setattr(projects, "maybe_one", lambda q: None)
    monkeypatch.setattr(projects, "display_name", lambda u: "Admin")
    monkeypatch.setattr(projects, "project_name", lambda p: "Project Alpha")
    monkeypatch.setattr(projects, "create_notifications", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda u, p: "leader")

    test_app = Flask(__name__)
    with test_app.test_request_context("/api/projects/p1/members/all", method="POST"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.add_all_members.__wrapped__("p1")
        assert code == 200
        assert "All workspace users added" in res.get_json()["message"]


def test_projects_update_and_delete_project(monkeypatch):
    test_app = Flask(__name__)
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda u, p: "leader")

    # Update empty name
    with test_app.test_request_context("/api/projects/p1", method="PATCH", json={"name": "   "}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_project.__wrapped__("p1")
        assert code == 400

    # Update not found
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []
    monkeypatch.setattr(projects, "supabase", mock_supabase)
    with test_app.test_request_context("/api/projects/p1", method="PATCH", json={"name": "New Alpha"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_project.__wrapped__("p1")
        assert code == 404

    # Update success
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"id": "p1", "name": "New Alpha"}]
    with test_app.test_request_context("/api/projects/p1", method="PATCH", json={"name": "New Alpha"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_project.__wrapped__("p1")
        assert code == 200
        assert res.get_json()["name"] == "New Alpha"

    # Delete project
    with test_app.test_request_context("/api/projects/p1", method="DELETE"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.delete_project.__wrapped__("p1")
        assert code == 200
        assert res.get_json()["message"] == "Project deleted"


def test_projects_update_and_remove_member(monkeypatch):
    test_app = Flask(__name__)
    monkeypatch.setattr(auth_utils, "get_role_in_project", lambda u, p: "leader")

    # Update member invalid role
    with test_app.test_request_context("/api/projects/p1/members/u2", method="PATCH", json={"role": "bad_role"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_member.__wrapped__("p1", "u2")
        assert code == 400

    # Update member not found
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    monkeypatch.setattr(projects, "supabase", mock_supabase)
    with test_app.test_request_context("/api/projects/p1/members/u2", method="PATCH", json={"role": "developer"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_member.__wrapped__("p1", "u2")
        assert code == 404

    # Update member success
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "m1"}]
    monkeypatch.setattr(projects, "maybe_one", lambda q: {"full_name": "Dave [Developer]"})
    monkeypatch.setattr(projects, "display_name", lambda u: "Admin")
    monkeypatch.setattr(projects, "project_name", lambda p: "Project Alpha")
    monkeypatch.setattr(projects, "create_notifications", lambda *args, **kwargs: None)
    with test_app.test_request_context("/api/projects/p1/members/u2", method="PATCH", json={"role": "qa_engineer"}):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.update_member.__wrapped__("p1", "u2")
        assert code == 200
        assert res.get_json()["agile_role"] == "QA Engineer"

    # Remove self as leader
    with test_app.test_request_context("/api/projects/p1/members/u1", method="DELETE"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.remove_member.__wrapped__("p1", "u1")
        assert code == 400
        assert "Cannot remove yourself" in res.get_json()["error"]

    # Remove another member success
    with test_app.test_request_context("/api/projects/p1/members/u2", method="DELETE"):
        g.user = SimpleNamespace(id="u1")
        res, code = projects.remove_member.__wrapped__("p1", "u2")
        assert code == 200
        assert res.get_json()["message"] == "Member removed"


# ============================================================================
# 6. routes/tasks.py (delete_task, set_assignees, activity)
# ============================================================================

def test_tasks_delete_and_assignees(monkeypatch):
    test_app = Flask(__name__)

    # Developer cannot delete task
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: "developer")
    with test_app.test_request_context("/api/projects/p1/tasks/t1", method="DELETE"):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.delete_task.__wrapped__("p1", "t1")
        assert code == 403

    # Leader can delete task
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: "leader")
    monkeypatch.setattr(tasks, "_get_task_or_404", lambda tid: {"name": "Write documentation"})
    monkeypatch.setattr(tasks, "_log", lambda *a: None)
    monkeypatch.setattr(tasks, "display_name", lambda u: "Leader")
    monkeypatch.setattr(tasks, "notify_project", lambda *a, **k: None)
    mock_supabase = MagicMock()
    monkeypatch.setattr(tasks, "supabase", mock_supabase)
    with test_app.test_request_context("/api/projects/p1/tasks/t1", method="DELETE"):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.delete_task.__wrapped__("p1", "t1")
        assert code == 200
        assert res.get_json()["message"] == "Task deleted"

    # Developer cannot set assignees
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: "developer")
    with test_app.test_request_context("/api/projects/p1/tasks/t1/assignees", method="PUT", json={"assignee_ids": ["u2"]}):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.set_assignees.__wrapped__("p1", "t1")
        assert code == 403

    # Leader can set assignees
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: "leader")
    monkeypatch.setattr(tasks, "_safely", lambda f: f())
    with test_app.test_request_context("/api/projects/p1/tasks/t1/assignees", method="PUT", json={"assignee_ids": ["u2", "u3"]}):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.set_assignees.__wrapped__("p1", "t1")
        assert code == 200
        assert res.get_json()["message"] == "Assignees updated"


def test_tasks_list_activity(monkeypatch):
    test_app = Flask(__name__)

    # Non member
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: None)
    with test_app.test_request_context("/api/projects/p1/tasks/t1/activity"):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.list_task_activity.__wrapped__("p1", "t1")
        assert code == 403

    # Invalid limit/offset
    monkeypatch.setattr(tasks, "get_role_in_project", lambda u, p: "developer")
    with test_app.test_request_context("/api/projects/p1/tasks/t1/activity?limit=abc"):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.list_task_activity.__wrapped__("p1", "t1")
        assert code == 400

    # Valid activity history
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value \
        .execute.return_value.data = [{"action": "TASK_CREATED", "actor_name": "Alice"}]
    monkeypatch.setattr(tasks, "supabase", mock_supabase)

    with test_app.test_request_context("/api/projects/p1/tasks/t1/activity?limit=10&offset=0"):
        g.user = SimpleNamespace(id="u1")
        res, code = tasks.list_task_activity.__wrapped__("p1", "t1")
        assert code == 200
        assert res.get_json()[0]["actor_name"] == "Alice"


# ============================================================================
# 7. routes/auth.py (MFA endpoints)
# ============================================================================

def test_auth_mfa_endpoints(monkeypatch):
    test_app = Flask(__name__)
    fake_auth = MagicMock()
    monkeypatch.setattr(auth_module, "supabase_auth", fake_auth)

    # 1. enroll
    fake_auth.auth._request.return_value.json.return_value = {"id": "factor-123", "totp": {"qr_code": "<svg>"}}
    with test_app.test_request_context("/api/auth/mfa/enroll", method="POST", headers={"Authorization": "Bearer tok"}):
        res, code = auth_module.enroll_mfa.__wrapped__()
        assert code == 200
        assert res.get_json()["id"] == "factor-123"

    # 2. confirm enrollment validation
    with test_app.test_request_context("/api/auth/mfa/confirm-enrollment", method="POST", headers={"Authorization": "Bearer tok"}, json={}):
        res, code = auth_module.confirm_mfa_enrollment.__wrapped__()
        assert code == 400

    fake_auth.auth._request.side_effect = [
        SimpleNamespace(json=lambda: {"id": "chal-1"}),
        SimpleNamespace(json=lambda: {"access_token": "new-tok"}),
    ]
    with test_app.test_request_context("/api/auth/mfa/confirm-enrollment", method="POST", headers={"Authorization": "Bearer tok"}, json={"factor_id": "f1", "code": "123456"}):
        res, code = auth_module.confirm_mfa_enrollment.__wrapped__()
        assert code == 200
        assert "successfully enabled" in res.get_json()["message"]

    # 3. status
    fake_auth.auth._request.side_effect = None
    fake_auth.auth._request.return_value.json.return_value = {
        "factors": [{"id": "f1", "factor_type": "totp", "status": "verified"}]
    }
    with test_app.test_request_context("/api/auth/mfa/status", method="GET", headers={"Authorization": "Bearer tok"}):
        res, code = auth_module.mfa_status.__wrapped__()
        assert code == 200
        assert res.get_json()["enabled"] is True

    # 4. unenroll
    with test_app.test_request_context("/api/auth/mfa/unenroll", method="POST", headers={"Authorization": "Bearer tok"}, json={"factor_id": "f1"}):
        res, code = auth_module.unenroll_mfa.__wrapped__()
        assert code == 200
        assert res.get_json()["message"] == "Two-factor authentication disabled"

    # 5. verify-mfa-login
    with test_app.test_request_context("/api/auth/mfa/verify-login", method="POST", json={"factor_id": "f1", "temp_token": "tok"}):
        res, code = auth_module.verify_mfa_login()
        assert code == 400
        assert "code are required" in res.get_json()["error"]

    fake_auth.auth._request.side_effect = [
        SimpleNamespace(json=lambda: {"id": "chal-1"}),
        SimpleNamespace(json=lambda: {"access_token": "verified-jwt", "user": {"id": "u1", "email": "test@example.com"}}),
    ]
    with test_app.test_request_context("/api/auth/mfa/verify-login", method="POST", json={"factor_id": "f1", "temp_token": "tok", "code": "654321"}):
        res, code = auth_module.verify_mfa_login()
        assert code == 200
        assert res.get_json()["access_token"] == "verified-jwt"
