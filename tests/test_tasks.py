import pytest
from types import SimpleNamespace
from flask import g

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