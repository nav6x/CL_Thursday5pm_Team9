import pytest
from types import SimpleNamespace
from flask import g
from unittest.mock import MagicMock

from app import app as flask_app
import routes.tasks as tasks


def test_create_task_non_member(monkeypatch):
    """A user who is not part of the project should not be able to create a task."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: None
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "name": "Test task",
            "column_id": "column-1"
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.create_task.__wrapped__("project-1")

        assert status_code == 403
        assert response.get_json()["error"] == \
            "You are not a member of this project"


def test_create_task_missing_name(monkeypatch):
    """Creating a task without a name should fail."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "column_id": "column-1"
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.create_task.__wrapped__("project-1")

        assert status_code == 400
        assert response.get_json()["error"] == \
            "name and column_id are required"


def test_create_task_missing_column_id(monkeypatch):
    """Creating a task without a column should fail."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "name": "Test task"
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.create_task.__wrapped__("project-1")

        assert status_code == 400
        assert response.get_json()["error"] == \
            "name and column_id are required"


@pytest.mark.parametrize(
    "story_points",
    [-1, 11, "five"]
)
def test_create_task_invalid_story_points(monkeypatch, story_points):
    """Story points must be an integer between 0 and 10."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "name": "Test task",
            "column_id": "column-1",
            "story_points": story_points
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.create_task.__wrapped__("project-1")

        assert status_code == 400
        assert response.get_json()["error"] == \
            "story_points must be an integer from 0 to 10"


def test_update_task_not_found(monkeypatch):
    """Trying to update a task that does not exist should return 404."""

    monkeypatch.setattr(
        tasks,
        "_get_task_or_404",
        lambda task_id: None
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks/task-1",
        method="PATCH",
        json={
            "name": "Updated task"
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.update_task.__wrapped__(
            "project-1",
            "task-1"
        )

        assert status_code == 404
        assert response.get_json()["error"] == "Task not found"


def test_developer_cannot_delete_task(monkeypatch):
    """Only a leader should be allowed to delete tasks."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks/task-1",
        method="DELETE"
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.delete_task.__wrapped__(
            "project-1",
            "task-1"
        )

        assert status_code == 403
        assert response.get_json()["error"] == \
            "Only a Project Leader can delete tasks"


def test_developer_cannot_assign_tasks(monkeypatch):
    """Only a leader should be allowed to assign users to tasks."""

    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks/task-1/assignees",
        method="PUT",
        json={
            "assignee_ids": ["user-2"]
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.set_assignees.__wrapped__(
            "project-1",
            "task-1"
        )

        assert status_code == 403
        assert response.get_json()["error"] == \
            "Only a Project Leader can assign tasks"

def test_valid_developer_can_create_task(monkeypatch):
    """A valid developer should be able to create a task."""

    # Pretend the logged-in user is a developer
    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "developer"
    )

    # Fake task that Supabase would return after insertion
    created_task = {
        "id": "task-1",
        "project_id": "project-1",
        "column_id": "column-1",
        "name": "Write unit tests",
        "description": "Test the create task route",
        "priority": "high",
        "story_points": 3,
        "created_by": "user-1"
    }

    # Mock Supabase so no real database is changed
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        created_task
    ]

    monkeypatch.setattr(tasks, "supabase", mock_supabase)

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "name": "Write unit tests",
            "column_id": "column-1",
            "description": "Test the create task route",
            "priority": "high",
            "story_points": 3
        }
    ):
        g.user = SimpleNamespace(id="user-1")

        response, status_code = tasks.create_task.__wrapped__(
            "project-1"
        )

        assert status_code == 201

        data = response.get_json()

        assert data["name"] == "Write unit tests"
        assert data["column_id"] == "column-1"
        assert data["story_points"] == 3
        assert data["created_by"] == "user-1"


def test_valid_leader_can_create_task(monkeypatch):
    """A valid project leader should be able to create a task."""

    # Pretend the logged-in user is a leader
    monkeypatch.setattr(
        tasks,
        "get_role_in_project",
        lambda user_id, project_id: "leader"
    )

    created_task = {
        "id": "task-2",
        "project_id": "project-1",
        "column_id": "column-1",
        "name": "Create board layout",
        "description": "",
        "priority": "medium",
        "story_points": 5,
        "created_by": "leader-1"
    }

    # Mock Supabase
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        created_task
    ]

    monkeypatch.setattr(tasks, "supabase", mock_supabase)

    with flask_app.test_request_context(
        "/api/projects/project-1/tasks",
        method="POST",
        json={
            "name": "Create board layout",
            "column_id": "column-1",
            "story_points": 5
        }
    ):
        g.user = SimpleNamespace(id="leader-1")

        response, status_code = tasks.create_task.__wrapped__(
            "project-1"
        )

        assert status_code == 201

        data = response.get_json()

        assert data["name"] == "Create board layout"
        assert data["column_id"] == "column-1"
        assert data["story_points"] == 5
        assert data["created_by"] == "leader-1"