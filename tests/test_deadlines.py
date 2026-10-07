
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import g

from app import app as flask_app
import routes.tasks as tasks


DUE_DATE_DESCRIPTION = '[meta:{"due":"2026-12-25","tags":["Feature"]}]---Wrap up Sprint 1'


class TestCreateTaskWithDueDate(unittest.TestCase):

    def test_due_date_round_trips_through_create(self):
        """Whatever due-date-carrying description string the frontend
        sends should come back unchanged — the backend must not
        validate, reformat, or strip it, since it has no concept of
        what's inside that string."""
        with patch.object(tasks, "get_role_in_project", lambda user_id, project_id: "developer"):
            created_task = {
                "id": "task-1",
                "project_id": "project-1",
                "column_id": "column-1",
                "name": "Wrap up Sprint 1",
                "description": DUE_DATE_DESCRIPTION,
                "priority": "medium",
                "story_points": 2,
                "created_by": "user-1",
            }
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.insert.return_value \
                .execute.return_value.data = [created_task]

            with patch.object(tasks, "supabase", mock_supabase):
                with flask_app.test_request_context(
                    "/api/projects/project-1/tasks",
                    method="POST",
                    json={
                        "name": "Wrap up Sprint 1",
                        "column_id": "column-1",
                        "description": DUE_DATE_DESCRIPTION,
                        "story_points": 2,
                    },
                ):
                    g.user = SimpleNamespace(id="user-1")
                    response, status_code = tasks.create_task.__wrapped__("project-1")
                    data = response.get_json()

                    expected = 201
                    actual = status_code
                    self.assertTrue(expected == actual)

                    expected = DUE_DATE_DESCRIPTION
                    actual = data["description"]
                    self.assertTrue(expected == actual)


class TestUpdateTaskDueDate(unittest.TestCase):

    def test_owner_can_set_due_date(self):
        """The task's creator should be able to add/change a due date
        even though they're a Developer, not a Leader — update_task's
        owner-or-assignee rule should allow it."""
        task = {
            "id": "task-1",
            "project_id": "project-1",
            "column_id": "column-1",
            "created_by": "user-1",
        }

        with patch.object(tasks, "_get_task_or_404", lambda task_id: task), \
                patch.object(tasks, "get_role_in_project", lambda user_id, project_id: "developer"), \
                patch.object(tasks, "_is_assignee", lambda task_id, user_id: False):

            updated_task = {**task, "description": DUE_DATE_DESCRIPTION}
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.update.return_value.eq.return_value \
                .execute.return_value.data = [updated_task]

            with patch.object(tasks, "supabase", mock_supabase):
                with flask_app.test_request_context(
                    "/api/projects/project-1/tasks/task-1",
                    method="PATCH",
                    json={"description": DUE_DATE_DESCRIPTION},
                ):
                    g.user = SimpleNamespace(id="user-1")  # same as created_by
                    response, status_code = tasks.update_task.__wrapped__("project-1", "task-1")
                    data = response.get_json()

                    expected = 200
                    actual = status_code
                    self.assertTrue(expected == actual)

                    expected = DUE_DATE_DESCRIPTION
                    actual = data["description"]
                    self.assertTrue(expected == actual)

    def test_non_owner_developer_cannot_set_due_date(self):
        """A Developer who neither created nor is assigned to the task
        should be blocked from setting a due date, same as any other
        description edit — changing a deadline isn't a 'move', so the
        move-only exception doesn't apply here."""
        task = {
            "id": "task-1",
            "project_id": "project-1",
            "column_id": "column-1",
            "created_by": "someone-else",
        }

        with patch.object(tasks, "_get_task_or_404", lambda task_id: task), \
                patch.object(tasks, "get_role_in_project", lambda user_id, project_id: "developer"), \
                patch.object(tasks, "_is_assignee", lambda task_id, user_id: False):

            with flask_app.test_request_context(
                "/api/projects/project-1/tasks/task-1",
                method="PATCH",
                json={"description": DUE_DATE_DESCRIPTION},
            ):
                g.user = SimpleNamespace(id="user-1")  # not the creator, not an assignee
                response, status_code = tasks.update_task.__wrapped__("project-1", "task-1")

                expected = 403
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "Developers can only move tasks, or edit tasks they created or are assigned to"
                actual = response.get_json()["error"]
                self.assertTrue(expected == actual)

    def test_leader_can_set_due_date_on_any_task(self):
        """A Leader should be able to set a due date regardless of who
        created the task."""
        task = {
            "id": "task-1",
            "project_id": "project-1",
            "column_id": "column-1",
            "created_by": "someone-else",
        }

        with patch.object(tasks, "_get_task_or_404", lambda task_id: task), \
                patch.object(tasks, "get_role_in_project", lambda user_id, project_id: "leader"), \
                patch.object(tasks, "_is_assignee", lambda task_id, user_id: False):

            updated_task = {**task, "description": DUE_DATE_DESCRIPTION}
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.update.return_value.eq.return_value \
                .execute.return_value.data = [updated_task]

            with patch.object(tasks, "supabase", mock_supabase):
                with flask_app.test_request_context(
                    "/api/projects/project-1/tasks/task-1",
                    method="PATCH",
                    json={"description": DUE_DATE_DESCRIPTION},
                ):
                    g.user = SimpleNamespace(id="leader-1")
                    response, status_code = tasks.update_task.__wrapped__("project-1", "task-1")
                    data = response.get_json()

                    expected = 200
                    actual = status_code
                    self.assertTrue(expected == actual)

                    expected = DUE_DATE_DESCRIPTION
                    actual = data["description"]
                    self.assertTrue(expected == actual)


if __name__ == "__main__":
    unittest.main()