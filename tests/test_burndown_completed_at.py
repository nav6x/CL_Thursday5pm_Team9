"""Tests for SCRUM-122 (burndown chart): recording when a task is completed.

The burndown chart's "actual remaining points" line depends on each task's
completed_at timestamp, so these tests check that update_task sets and clears
it correctly. Supabase is mocked, so no real database is touched.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import g

from app import app as flask_app
import routes.tasks as tasks


TODO_COL = "col-todo"
IN_PROGRESS_COL = "col-in-progress"
DONE_COL = "col-done"


def _patch_update_route(monkeypatch, existing_task):
    """Set up everything update_task needs, and return the mocked Supabase
    client so a test can inspect what was saved."""
    monkeypatch.setattr(tasks, "_get_task_or_404", lambda task_id: existing_task)
    monkeypatch.setattr(tasks, "get_role_in_project", lambda user_id, project_id: "leader")
    monkeypatch.setattr(tasks, "_is_done_column", lambda column_id: column_id == DONE_COL)

    # Side effects that aren't under test: activity log and notifications
    monkeypatch.setattr(tasks, "_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "display_name", lambda user_id: "Tester")
    monkeypatch.setattr(tasks, "notify_project", lambda *args, **kwargs: None)

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {**existing_task}
    ]
    monkeypatch.setattr(tasks, "supabase", mock_supabase)
    return mock_supabase


def _saved_updates(mock_supabase):
    """The dictionary that update_task passed to supabase.table('tasks').update(...)."""
    return mock_supabase.table.return_value.update.call_args[0][0]


def _move_task(body):
    with flask_app.test_request_context(
        "/api/projects/project-1/tasks/task-1", method="PATCH", json=body
    ):
        g.user = SimpleNamespace(id="user-1")
        return tasks.update_task.__wrapped__("project-1", "task-1")


def _task(column_id, completed_at=None):
    return {
        "id": "task-1",
        "project_id": "project-1",
        "column_id": column_id,
        "name": "Build burndown chart",
        "story_points": 3,
        "created_by": "user-1",
        "completed_at": completed_at,
    }


def test_moving_task_into_done_records_completed_at(monkeypatch):
    """AC4: moving a task to Done stamps the current time, so the chart
    knows which day the points were burned down."""
    mock_supabase = _patch_update_route(monkeypatch, _task(IN_PROGRESS_COL))

    before = datetime.now(timezone.utc)
    _, status_code = _move_task({"column_id": DONE_COL})
    after = datetime.now(timezone.utc)

    assert status_code == 200
    saved = _saved_updates(mock_supabase)
    assert saved["column_id"] == DONE_COL

    completed_at = datetime.fromisoformat(saved["completed_at"])
    assert before <= completed_at <= after
    assert completed_at.tzinfo is not None  # stored in UTC, not local time


def test_moving_task_out_of_done_clears_completed_at(monkeypatch):
    """A task dragged back out of Done is no longer finished, so its points
    must count as remaining again."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    mock_supabase = _patch_update_route(monkeypatch, _task(DONE_COL, completed_at=old_time))

    _, status_code = _move_task({"column_id": IN_PROGRESS_COL})

    assert status_code == 200
    assert "completed_at" in _saved_updates(mock_supabase)
    assert _saved_updates(mock_supabase)["completed_at"] is None


def test_moving_between_unfinished_columns_does_not_touch_completed_at(monkeypatch):
    """To Do -> In Progress isn't a completion, so completed_at is left alone."""
    mock_supabase = _patch_update_route(monkeypatch, _task(TODO_COL))

    _, status_code = _move_task({"column_id": IN_PROGRESS_COL})

    assert status_code == 200
    assert "completed_at" not in _saved_updates(mock_supabase)


def test_reordering_within_done_keeps_original_completed_at(monkeypatch):
    """Dragging a task to a new position inside Done must not reset the day
    it was completed, or the burndown history would shift."""
    old_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    mock_supabase = _patch_update_route(monkeypatch, _task(DONE_COL, completed_at=old_time))

    _, status_code = _move_task({"column_id": DONE_COL, "position": 2})

    assert status_code == 200
    assert "completed_at" not in _saved_updates(mock_supabase)


def test_editing_task_name_does_not_set_completed_at(monkeypatch):
    """Only column moves affect completion; renaming a task doesn't."""
    mock_supabase = _patch_update_route(monkeypatch, _task(IN_PROGRESS_COL))

    _, status_code = _move_task({"name": "Renamed task"})

    assert status_code == 200
    assert "completed_at" not in _saved_updates(mock_supabase)


@pytest.mark.parametrize(
    "column_name, expected",
    [
        ("Done", True),
        ("done", True),
        ("Completed", True),
        ("Done ✅", True),
        ("In Progress", False),
        ("To Do", False),
        ("", False),
    ],
)
def test_is_done_column_matches_board_naming(monkeypatch, column_name, expected):
    """The backend must agree with the board on which column counts as Done
    (any name containing 'done' or 'complete', ignoring case)."""
    monkeypatch.setattr(tasks, "maybe_one", lambda query: {"name": column_name})
    monkeypatch.setattr(tasks, "supabase", MagicMock())

    assert tasks._is_done_column("some-column-id") is expected


def test_is_done_column_handles_missing_column_id(monkeypatch):
    """A task with no column shouldn't crash or hit the database."""
    mock_supabase = MagicMock()
    monkeypatch.setattr(tasks, "supabase", mock_supabase)

    assert tasks._is_done_column(None) is False
    mock_supabase.table.assert_not_called()
