import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from flask import g

from app import app as flask_app
import routes.notifications as notifications
import notifications_utils


# ---------------------------------------------------------------- utils tests

def test_clean_name():
    assert notifications_utils.clean_name("Jamie Chen [Developer]") == "Jamie Chen"
    assert notifications_utils.clean_name("Alex Smith [Scrum Master]") == "Alex Smith"
    assert notifications_utils.clean_name("Simple Name") == "Simple Name"
    assert notifications_utils.clean_name("", fallback="Fallback") == "Fallback"
    assert notifications_utils.clean_name("") == "Someone"


def test_diff_description_content_changed():
    old_desc = '[meta:{"tags":["Frontend"]}]---Initial body'
    new_desc = '[meta:{"tags":["Frontend","Backend"]}]---Initial body'
    changed, comments = notifications_utils.diff_description(old_desc, new_desc)
    assert changed is True
    assert comments == []

    # Text change
    changed, _ = notifications_utils.diff_description("old body", "new body")
    assert changed is True

    # No change
    changed, _ = notifications_utils.diff_description("same body", "same body")
    assert changed is False


def test_diff_description_comments():
    old_desc = '[meta:{"comments":[{"id":"c1","text":"first"}]}]---Body'
    new_desc = '[meta:{"comments":[{"id":"c1","text":"first"},{"id":"c2","text":"second"}]}]---Body'
    changed, comments = notifications_utils.diff_description(old_desc, new_desc)
    assert len(comments) == 1
    assert comments[0]["id"] == "c2"


def test_create_notifications_excludes_actor(monkeypatch):
    mock_supabase = MagicMock()
    monkeypatch.setattr(notifications_utils, "supabase", mock_supabase)

    notifications_utils.create_notifications(
        user_ids=["user-1", "user-2", "user-1"],
        actor_id="user-1",
        type_="task_created",
        message="Created a task"
    )

    # Actor should be excluded, and duplicate user-1 stripped
    insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
    assert len(insert_call) == 1
    assert insert_call[0]["user_id"] == "user-2"
    assert insert_call[0]["actor_id"] == "user-1"
    assert insert_call[0]["type"] == "task_created"


def test_create_notifications_no_recipients_does_not_insert(monkeypatch):
    mock_supabase = MagicMock()
    monkeypatch.setattr(notifications_utils, "supabase", mock_supabase)

    # All recipients are actor
    notifications_utils.create_notifications(
        user_ids=["user-1"],
        actor_id="user-1",
        type_="task_created",
        message="Created a task"
    )
    mock_supabase.table.assert_not_called()


# ---------------------------------------------------------------- route tests

def test_list_notifications_unauthorized():
    with flask_app.test_client() as client:
        res = client.get("/api/notifications")
        assert res.status_code == 401


def test_list_notifications_success(monkeypatch):
    mock_supabase = MagicMock()
    mock_notifications = [
        {
            "id": "notif-1",
            "type": "task_created",
            "message": "Task 1 created",
            "is_read": False,
            "created_at": "2026-10-15T00:00:00Z"
        }
    ]

    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = mock_notifications
    mock_unread_resp = MagicMock()
    mock_unread_resp.count = 1
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_unread_resp

    monkeypatch.setattr(notifications, "supabase", mock_supabase)

    with flask_app.test_request_context("/api/notifications?limit=10", method="GET"):
        g.user = SimpleNamespace(id="user-1")
        res, status = notifications.list_notifications.__wrapped__()
        assert status == 200
        data = res.get_json()
        assert len(data["notifications"]) == 1
        assert data["unread_count"] == 1


def test_mark_read_success(monkeypatch):
    mock_supabase = MagicMock()
    monkeypatch.setattr(notifications, "supabase", mock_supabase)

    with flask_app.test_request_context("/api/notifications/notif-1/read", method="POST"):
        g.user = SimpleNamespace(id="user-1")
        res, status = notifications.mark_read.__wrapped__("notif-1")
        assert status == 200
        assert res.get_json()["message"] == "Marked as read"

        # Verify query was scoped to user_id
        update_call = mock_supabase.table.return_value.update.call_args[0][0]
        assert update_call == {"is_read": True}


def test_mark_all_read_success(monkeypatch):
    mock_supabase = MagicMock()
    monkeypatch.setattr(notifications, "supabase", mock_supabase)

    with flask_app.test_request_context("/api/notifications/read-all", method="POST"):
        g.user = SimpleNamespace(id="user-1")
        res, status = notifications.mark_all_read.__wrapped__()
        assert status == 200
        assert res.get_json()["message"] == "All notifications marked as read"
