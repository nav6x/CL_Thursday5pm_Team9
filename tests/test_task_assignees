import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import g

from app import app as flask_app
import routes.tasks as tasks


PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"


def build_mock_supabase(task_rows, assignee_rows):
    """
    list_tasks makes two queries: one on `tasks` and one on `task_assignees`.
    Return a fake Supabase client that answers each with the rows we choose.
    """
    tasks_query = MagicMock()
    tasks_query.select.return_value.eq.return_value.order.return_value.execute.return_value.data = \
        task_rows

    assignees_query = MagicMock()
    assignees_query.select.return_value.in_.return_value.execute.return_value.data = \
        assignee_rows

    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = lambda name: {
        "tasks": tasks_query,
        "task_assignees": assignees_query,
    }[name]

    return mock_supabase, tasks_query, assignees_query


class TestListTasks(unittest.TestCase):

    def test_list_tasks_returns_all_tasks_for_the_project(self):
        """Listing tasks should return every task the query found."""

        task_rows = [
            {"id": "task-1", "name": "First task", "column_id": "column-1"},
            {"id": "task-2", "name": "Second task", "column_id": "column-2"},
        ]

        mock_supabase, _, _ = build_mock_supabase(task_rows, [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")
                data = response.get_json()

                expected = 200
                actual = status_code
                self.assertTrue(expected == actual)

                expected = ["task-1", "task-2"]
                actual = [t["id"] for t in data]
                self.assertTrue(expected == actual)

                expected = "First task"
                actual = data[0]["name"]
                self.assertTrue(expected == actual)

                expected = "column-2"
                actual = data[1]["column_id"]
                self.assertTrue(expected == actual)

    def test_list_tasks_empty_project_returns_empty_list(self):
        """A project with no tasks should return an empty list, not an error."""

        mock_supabase, _, _ = build_mock_supabase([], [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                expected = 200
                actual = status_code
                self.assertTrue(expected == actual)

                expected = []
                actual = response.get_json()
                self.assertTrue(expected == actual)

    def test_list_tasks_uses_placeholder_id_when_there_are_no_tasks(self):
        """With no tasks, the assignee lookup must still get a non-empty id list."""

        mock_supabase, _, assignees_query = build_mock_supabase([], [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                tasks.list_tasks.__wrapped__("project-1")

                assignees_query.select.return_value.in_.assert_called_once_with(
                    "task_id",
                    [PLACEHOLDER_UUID],
                )

    def test_list_tasks_only_queries_the_requested_project(self):
        """Tasks should be filtered by the project id from the URL."""

        mock_supabase, tasks_query, _ = build_mock_supabase([], [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                tasks.list_tasks.__wrapped__("project-1")

                tasks_query.select.return_value.eq.assert_called_once_with(
                    "project_id",
                    "project-1",
                )

    def test_list_tasks_orders_tasks_by_position(self):
        """Tasks should be requested in board order (by position)."""

        mock_supabase, tasks_query, _ = build_mock_supabase([], [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                tasks.list_tasks.__wrapped__("project-1")

                tasks_query.select.return_value.eq.return_value.order.assert_called_once_with(
                    "position",
                )

    def test_list_tasks_looks_up_assignees_for_every_task(self):
        """The assignee query should cover all of the listed tasks in one go."""

        task_rows = [
            {"id": "task-1", "name": "First task"},
            {"id": "task-2", "name": "Second task"},
        ]

        mock_supabase, _, assignees_query = build_mock_supabase(task_rows, [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                tasks.list_tasks.__wrapped__("project-1")

                assignees_query.select.return_value.in_.assert_called_once_with(
                    "task_id",
                    ["task-1", "task-2"],
                )

    def test_list_tasks_task_without_assignees_gets_empty_list(self):
        """A task nobody is assigned to should have an empty assignees list."""

        task_rows = [
            {"id": "task-1", "name": "Unassigned task"}
        ]

        mock_supabase, _, _ = build_mock_supabase(task_rows, [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                expected = 200
                actual = status_code
                self.assertTrue(expected == actual)

                expected = []
                actual = response.get_json()[0]["assignees"]
                self.assertTrue(expected == actual)

    def test_list_tasks_attaches_assignee_to_its_task(self):
        """An assignee should show up on the task they are assigned to."""

        task_rows = [
            {"id": "task-1", "name": "Assigned task"}
        ]

        assignee_rows = [
            {
                "task_id": "task-1",
                "profiles": {
                    "id": "user-2",
                    "full_name": "Dan Dev",
                },
            }
        ]

        mock_supabase, _, _ = build_mock_supabase(
            task_rows,
            assignee_rows,
        )

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                expected = 200
                actual = status_code
                self.assertTrue(expected == actual)

                expected = [
                    {"id": "user-2", "full_name": "Dan Dev"}
                ]
                actual = response.get_json()[0]["assignees"]
                self.assertTrue(expected == actual)

    def test_list_tasks_task_can_have_multiple_assignees(self):
        """Every assignee of a task should be listed, in the order returned."""

        task_rows = [
            {"id": "task-1", "name": "Shared task"}
        ]

        assignee_rows = [
            {
                "task_id": "task-1",
                "profiles": {
                    "id": "user-2",
                    "full_name": "Dan Dev",
                },
            },
            {
                "task_id": "task-1",
                "profiles": {
                    "id": "user-3",
                    "full_name": "Dee Dev",
                },
            },
        ]

        mock_supabase, _, _ = build_mock_supabase(
            task_rows,
            assignee_rows,
        )

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                assignees = response.get_json()[0]["assignees"]

                expected = ["user-2", "user-3"]
                actual = [a["id"] for a in assignees]
                self.assertTrue(expected == actual)

    def test_list_tasks_assignees_only_go_on_their_own_task(self):
        """Assignees must not be mixed up between tasks."""

        task_rows = [
            {"id": "task-1", "name": "First task"},
            {"id": "task-2", "name": "Second task"},
            {"id": "task-3", "name": "Third task"},
        ]

        assignee_rows = [
            {
                "task_id": "task-1",
                "profiles": {
                    "id": "user-2",
                    "full_name": "Dan Dev",
                },
            },
            {
                "task_id": "task-2",
                "profiles": {
                    "id": "user-3",
                    "full_name": "Dee Dev",
                },
            },
        ]

        mock_supabase, _, _ = build_mock_supabase(
            task_rows,
            assignee_rows,
        )

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                by_id = {
                    t["id"]: t
                    for t in response.get_json()
                }

                expected = ["user-2"]
                actual = [a["id"] for a in by_id["task-1"]["assignees"]]
                self.assertTrue(expected == actual)

                expected = ["user-3"]
                actual = [a["id"] for a in by_id["task-2"]["assignees"]]
                self.assertTrue(expected == actual)

                expected = []
                actual = by_id["task-3"]["assignees"]
                self.assertTrue(expected == actual)

    def test_list_tasks_same_person_can_be_assigned_to_several_tasks(self):
        """One person assigned to two tasks should appear on both."""

        task_rows = [
            {"id": "task-1", "name": "First task"},
            {"id": "task-2", "name": "Second task"},
        ]

        assignee_rows = [
            {
                "task_id": "task-1",
                "profiles": {
                    "id": "user-2",
                    "full_name": "Dan Dev",
                },
            },
            {
                "task_id": "task-2",
                "profiles": {
                    "id": "user-2",
                    "full_name": "Dan Dev",
                },
            },
        ]

        mock_supabase, _, _ = build_mock_supabase(
            task_rows,
            assignee_rows,
        )

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                for task in response.get_json():
                    expected = ["user-2"]
                    actual = [a["id"] for a in task["assignees"]]
                    self.assertTrue(expected == actual)

    def test_list_tasks_keeps_original_task_fields(self):
        """Adding assignees should not change or drop the task's own fields."""

        task_rows = [
            {
                "id": "task-1",
                "project_id": "project-1",
                "column_id": "column-1",
                "name": "Write report",
                "description": "Draft it",
                "priority": "high",
                "story_points": 5,
                "created_by": "user-1",
            }
        ]

        mock_supabase, _, _ = build_mock_supabase(task_rows, [])

        with patch.object(tasks, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/tasks",
                method="GET",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = tasks.list_tasks.__wrapped__("project-1")

                task = response.get_json()[0]

                expected = "Write report"
                actual = task["name"]
                self.assertTrue(expected == actual)

                expected = "Draft it"
                actual = task["description"]
                self.assertTrue(expected == actual)

                expected = "high"
                actual = task["priority"]
                self.assertTrue(expected == actual)

                expected = 5
                actual = task["story_points"]
                self.assertTrue(expected == actual)

                expected = "user-1"
                actual = task["created_by"]
                self.assertTrue(expected == actual)

                expected = "project-1"
                actual = task["project_id"]
                self.assertTrue(expected == actual)

                expected = "column-1"
                actual = task["column_id"]
                self.assertTrue(expected == actual)


if __name__ == "__main__":
    unittest.main()