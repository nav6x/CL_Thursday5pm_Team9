"""
Task assignee tests, written with unittest (expected / actual / assertTrue style).

Each test calls a route function directly (via __wrapped__, which skips the @login_required
check) with a fake Supabase client, then checks the response and the database calls made.

Classes:
  TestListTasks                 - assignees are attached to the right tasks
  TestSetAssignees              - Leaders replace a task's assignee list
  TestCreateTaskAssignees       - assignee_ids supplied when a task is created
  TestUpdateTaskAssignees       - being an assignee lets a Developer edit a task
  TestIsAssignee                - the lookup itself

tests/test_tasks.py checks the same area end to end (real login and permission checks and a
fake database). These tests check the individual database calls each route makes.

Run from the repository root (the folder containing Test_Branch/ and tests/):

    python -m unittest tests.test_task_assignees -v
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Sets up the import paths and dummy Supabase credentials, so this file works with
# `python -m unittest` as well as pytest (unittest does not load conftest.py by itself).
import tests.conftest  # noqa: F401

from flask import g

from app import app as flask_app
import routes.tasks as tasks


PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"


class TaskTestCase(unittest.TestCase):

    def check(self, expected, actual):
        """Same as assertTrue(expected == actual), but says what the two values were."""
        self.assertTrue(expected == actual, f"expected {expected!r} but got {actual!r}")


# ---------------------------------------------------------------------------
# 1. list_tasks: assignees attached to tasks
# ---------------------------------------------------------------------------
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


class TestListTasks(TaskTestCase):

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
                self.check(expected, actual)

                expected = ["task-1", "task-2"]
                actual = [t["id"] for t in data]
                self.check(expected, actual)

                expected = "First task"
                actual = data[0]["name"]
                self.check(expected, actual)

                expected = "column-2"
                actual = data[1]["column_id"]
                self.check(expected, actual)

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
                self.check(expected, actual)

                expected = []
                actual = response.get_json()
                self.check(expected, actual)

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
                self.check(expected, actual)

                expected = []
                actual = response.get_json()[0]["assignees"]
                self.check(expected, actual)

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
                self.check(expected, actual)

                expected = [
                    {"id": "user-2", "full_name": "Dan Dev"}
                ]
                actual = response.get_json()[0]["assignees"]
                self.check(expected, actual)

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
                self.check(expected, actual)

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
                self.check(expected, actual)

                expected = ["user-3"]
                actual = [a["id"] for a in by_id["task-2"]["assignees"]]
                self.check(expected, actual)

                expected = []
                actual = by_id["task-3"]["assignees"]
                self.check(expected, actual)

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
                    with self.subTest(task=task["id"]):
                        expected = ["user-2"]
                        actual = [a["id"] for a in task["assignees"]]
                        self.check(expected, actual)

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

                for field, expected in [
                    ("name", "Write report"),
                    ("description", "Draft it"),
                    ("priority", "high"),
                    ("story_points", 5),
                    ("created_by", "user-1"),
                    ("project_id", "project-1"),
                    ("column_id", "column-1"),
                ]:
                    with self.subTest(field=field):
                        actual = task[field]
                        self.check(expected, actual)


# ---------------------------------------------------------------------------
# 2. set_assignees: Leaders replace the assignee list
# ---------------------------------------------------------------------------
def call_set_assignees(role, body, task_id="task-1"):
    """Run set_assignees as a user with the given role; return (response, status_code, mock_supabase)."""
    mock_supabase = MagicMock()

    with patch.object(tasks, "supabase", mock_supabase), \
            patch.object(tasks, "get_role_in_project", return_value=role):
        with flask_app.test_request_context(
            f"/api/projects/project-1/tasks/{task_id}/assignees",
            method="PUT",
            json=body,
        ):
            g.user = SimpleNamespace(id="user-1")
            response, status_code = tasks.set_assignees.__wrapped__("project-1", task_id)

    return response, status_code, mock_supabase


class TestSetAssignees(TaskTestCase):

    def test_set_assignees_developer_cannot_assign(self):
        """Deciding who works on what is a Leader call, so developers are refused."""

        response, status_code, _ = call_set_assignees("developer", {"assignee_ids": ["user-2"]})

        expected = 403
        actual = status_code
        self.check(expected, actual)

        expected = "Only a Project Leader can assign tasks"
        actual = response.get_json()["error"]
        self.check(expected, actual)

    def test_set_assignees_non_member_cannot_assign(self):
        """Someone with no role in the project is refused as well."""

        response, status_code, _ = call_set_assignees(None, {"assignee_ids": ["user-2"]})

        expected = 403
        actual = status_code
        self.check(expected, actual)

        expected = "Only a Project Leader can assign tasks"
        actual = response.get_json()["error"]
        self.check(expected, actual)

    def test_set_assignees_refused_request_does_not_touch_the_database(self):
        """A 403 must happen before any delete or insert."""

        _, _, mock_supabase = call_set_assignees("developer", {"assignee_ids": ["user-2"]})

        mock_supabase.table.assert_not_called()

    def test_set_assignees_leader_gets_a_success_message(self):
        """A Leader's request should succeed."""

        response, status_code, _ = call_set_assignees("leader", {"assignee_ids": ["user-2"]})

        expected = 200
        actual = status_code
        self.check(expected, actual)

        expected = {"message": "Assignees updated"}
        actual = response.get_json()
        self.check(expected, actual)

    def test_set_assignees_clears_the_old_list_for_that_task_only(self):
        """The old assignees are deleted, filtered by this task's id."""

        _, _, mock_supabase = call_set_assignees(
            "leader", {"assignee_ids": ["user-2"]}, task_id="task-7"
        )

        table = mock_supabase.table.return_value
        table.delete.return_value.eq.assert_called_once_with("task_id", "task-7")

    def test_set_assignees_inserts_one_row_per_assignee(self):
        """Each person in the new list gets a (task_id, user_id) row."""

        _, _, mock_supabase = call_set_assignees("leader", {"assignee_ids": ["user-2", "user-3"]})

        table = mock_supabase.table.return_value
        table.insert.assert_called_once_with([
            {"task_id": "task-1", "user_id": "user-2"},
            {"task_id": "task-1", "user_id": "user-3"},
        ])

    def test_set_assignees_works_on_the_task_assignees_table(self):
        """Both the delete and the insert must hit task_assignees, nothing else."""

        _, _, mock_supabase = call_set_assignees("leader", {"assignee_ids": ["user-2"]})

        expected = {"task_assignees"}
        actual = {call.args[0] for call in mock_supabase.table.call_args_list}
        self.check(expected, actual)

    def test_set_assignees_deletes_the_old_rows_before_inserting_the_new_ones(self):
        """Replacing means delete first; inserting first would then delete the new rows too."""

        _, _, mock_supabase = call_set_assignees("leader", {"assignee_ids": ["user-2"]})

        names = [call[0] for call in mock_supabase.table.return_value.method_calls]

        self.assertTrue(
            names.index("delete") < names.index("insert"),
            f"expected delete before insert, but the calls were {names}",
        )

    def test_set_assignees_empty_list_clears_everyone_without_inserting(self):
        """An empty list means 'unassign everyone': delete, but nothing to insert."""

        _, status_code, mock_supabase = call_set_assignees("leader", {"assignee_ids": []})

        table = mock_supabase.table.return_value

        expected = 200
        actual = status_code
        self.check(expected, actual)

        table.delete.assert_called_once()
        table.insert.assert_not_called()

    def test_set_assignees_missing_list_is_treated_as_empty(self):
        """Leaving out assignee_ids behaves like an empty list."""

        _, status_code, mock_supabase = call_set_assignees("leader", {})

        table = mock_supabase.table.return_value

        expected = 200
        actual = status_code
        self.check(expected, actual)

        table.delete.assert_called_once()
        table.insert.assert_not_called()


# ---------------------------------------------------------------------------
# 3. create_task: assignee_ids supplied at creation time
# ---------------------------------------------------------------------------
CREATED_TASK = {
    "id": "task-9",
    "project_id": "project-1",
    "name": "New task",
    "column_id": "column-1",
}


def call_create_task(role, body):
    """Run create_task as a user with the given role; return (response, status_code, mock_supabase)."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [CREATED_TASK]

    with patch.object(tasks, "supabase", mock_supabase), \
            patch.object(tasks, "get_role_in_project", return_value=role):
        with flask_app.test_request_context(
            "/api/projects/project-1/tasks",
            method="POST",
            json=body,
        ):
            g.user = SimpleNamespace(id="user-1")
            response, status_code = tasks.create_task.__wrapped__("project-1")

    return response, status_code, mock_supabase


class TestCreateTaskAssignees(TaskTestCase):

    def test_create_task_with_assignees_saves_them_against_the_new_task(self):
        """The assignee rows must use the id of the task that was just created."""

        body = {"name": "New task", "column_id": "column-1", "assignee_ids": ["user-2", "user-3"]}

        _, status_code, mock_supabase = call_create_task("developer", body)

        expected = 201
        actual = status_code
        self.check(expected, actual)

        insert_calls = mock_supabase.table.return_value.insert.call_args_list

        expected = 2
        actual = len(insert_calls)
        self.check(expected, actual)

        expected = [
            {"task_id": "task-9", "user_id": "user-2"},
            {"task_id": "task-9", "user_id": "user-3"},
        ]
        actual = insert_calls[1].args[0]
        self.check(expected, actual)

    def test_create_task_saves_assignees_in_the_task_assignees_table(self):
        """First the task goes into `tasks`, then the assignees into `task_assignees`."""

        body = {"name": "New task", "column_id": "column-1", "assignee_ids": ["user-2"]}

        _, _, mock_supabase = call_create_task("leader", body)

        expected = ["tasks", "task_assignees"]
        actual = [call.args[0] for call in mock_supabase.table.call_args_list]
        self.check(expected, actual)

    def test_create_task_without_assignees_makes_only_one_insert(self):
        """No assignee_ids means no task_assignees query at all."""

        body = {"name": "New task", "column_id": "column-1"}

        _, status_code, mock_supabase = call_create_task("developer", body)

        expected = 201
        actual = status_code
        self.check(expected, actual)

        expected = 1
        actual = mock_supabase.table.return_value.insert.call_count
        self.check(expected, actual)

    def test_create_task_with_an_empty_assignee_list_makes_only_one_insert(self):
        """An empty list is the same as none."""

        body = {"name": "New task", "column_id": "column-1", "assignee_ids": []}

        _, _, mock_supabase = call_create_task("developer", body)

        expected = 1
        actual = mock_supabase.table.return_value.insert.call_count
        self.check(expected, actual)

    def test_create_task_non_member_cannot_create_or_assign(self):
        """A refused request must not insert the task or any assignees."""

        body = {"name": "New task", "column_id": "column-1", "assignee_ids": ["user-2"]}

        response, status_code, mock_supabase = call_create_task(None, body)

        expected = 403
        actual = status_code
        self.check(expected, actual)

        expected = "You are not a member of this project"
        actual = response.get_json()["error"]
        self.check(expected, actual)

        mock_supabase.table.assert_not_called()


# ---------------------------------------------------------------------------
# 4. update_task: being an assignee lets a Developer edit a task
#    (_get_task_or_404 and _is_assignee are replaced so these tests check only the
#    permission decision; the real _is_assignee is tested in section 5)
# ---------------------------------------------------------------------------
SOMEONE_ELSES_TASK = {
    "id": "task-1",
    "name": "Old name",
    "column_id": "column-1",
    "created_by": "user-9",
}


def call_update_task(role, body, task, is_assignee):
    """Run update_task as user-1; return (response, status_code, mock_supabase)."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value \
        .execute.return_value.data = [{**task, **body}]

    with patch.object(tasks, "supabase", mock_supabase), \
            patch.object(tasks, "get_role_in_project", return_value=role), \
            patch.object(tasks, "_get_task_or_404", return_value=task), \
            patch.object(tasks, "_is_assignee", return_value=is_assignee):
        with flask_app.test_request_context(
            "/api/projects/project-1/tasks/task-1",
            method="PATCH",
            json=body,
        ):
            g.user = SimpleNamespace(id="user-1")
            response, status_code = tasks.update_task.__wrapped__("project-1", "task-1")

    return response, status_code, mock_supabase


class TestUpdateTaskAssignees(TaskTestCase):

    def test_update_task_assignee_can_edit_the_task(self):
        """A developer who is assigned to a task (but did not create it) may edit it."""

        _, status_code, mock_supabase = call_update_task(
            "developer", {"name": "New name"}, SOMEONE_ELSES_TASK, is_assignee=True
        )

        expected = 200
        actual = status_code
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_called_once_with({"name": "New name"})

    def test_update_task_developer_who_is_not_an_assignee_cannot_edit(self):
        """Not the creator and not assigned: editing is refused and nothing is written."""

        response, status_code, mock_supabase = call_update_task(
            "developer", {"name": "New name"}, SOMEONE_ELSES_TASK, is_assignee=False
        )

        expected = 403
        actual = status_code
        self.check(expected, actual)

        expected = "Developers can only move tasks, or edit tasks they created or are assigned to"
        actual = response.get_json()["error"]
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_not_called()

    def test_update_task_creator_can_edit_even_if_not_assigned(self):
        """Creating a task is enough to edit it; assignment is not required."""

        own_task = {**SOMEONE_ELSES_TASK, "created_by": "user-1"}

        _, status_code, mock_supabase = call_update_task(
            "developer", {"name": "New name"}, own_task, is_assignee=False
        )

        expected = 200
        actual = status_code
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_called_once_with({"name": "New name"})

    def test_update_task_developer_who_is_not_an_assignee_can_still_move_the_task(self):
        """Moving a card between columns is open to every developer."""

        _, status_code, mock_supabase = call_update_task(
            "developer", {"column_id": "column-2"}, SOMEONE_ELSES_TASK, is_assignee=False
        )

        expected = 200
        actual = status_code
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_called_once_with({"column_id": "column-2"})

    def test_update_task_a_move_mixed_with_an_edit_needs_assignee_rights(self):
        """Sending a name along with the move makes it an edit, not just a move."""

        _, status_code, mock_supabase = call_update_task(
            "developer", {"column_id": "column-2", "name": "Sneaky"},
            SOMEONE_ELSES_TASK, is_assignee=False
        )

        expected = 403
        actual = status_code
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_not_called()

    def test_update_task_leader_can_edit_without_being_assigned(self):
        """Leaders can edit anything on any task."""

        _, status_code, mock_supabase = call_update_task(
            "leader", {"name": "New name"}, SOMEONE_ELSES_TASK, is_assignee=False
        )

        expected = 200
        actual = status_code
        self.check(expected, actual)

        mock_supabase.table.return_value.update.assert_called_once_with({"name": "New name"})

    def test_update_task_ignores_fields_that_are_not_on_the_allowed_list(self):
        """Assignees cannot rewrite who created the task or which project it belongs to."""

        _, _, mock_supabase = call_update_task(
            "developer", {"name": "New name", "created_by": "me", "project_id": "other"},
            SOMEONE_ELSES_TASK, is_assignee=True
        )

        mock_supabase.table.return_value.update.assert_called_once_with({"name": "New name"})


# ---------------------------------------------------------------------------
# 5. _is_assignee: the lookup itself
# ---------------------------------------------------------------------------
def mock_assignee_lookup(result):
    """A fake Supabase client whose maybe_single().execute() returns `result`."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .maybe_single.return_value.execute.return_value = result
    return mock_supabase


class TestIsAssignee(TaskTestCase):

    def test_is_assignee_true_when_a_matching_row_exists(self):
        """A row for (task, user) means the user is assigned."""

        mock_supabase = mock_assignee_lookup(SimpleNamespace(data={"user_id": "user-1"}))

        with patch.object(tasks, "supabase", mock_supabase):
            expected = True
            actual = tasks._is_assignee("task-1", "user-1")
            self.check(expected, actual)

    def test_is_assignee_false_when_the_row_has_no_data(self):
        """A response with no data means the user is not assigned."""

        mock_supabase = mock_assignee_lookup(SimpleNamespace(data=None))

        with patch.object(tasks, "supabase", mock_supabase):
            expected = False
            actual = tasks._is_assignee("task-1", "user-2")
            self.check(expected, actual)

    def test_is_assignee_looks_in_task_assignees_for_both_the_task_and_the_user(self):
        """The lookup must filter on BOTH ids, or anyone assigned anywhere would pass."""

        mock_supabase = MagicMock()

        with patch.object(tasks, "supabase", mock_supabase):
            tasks._is_assignee("task-1", "user-1")

        mock_supabase.table.assert_called_once_with("task_assignees")

        first_eq = mock_supabase.table.return_value.select.return_value.eq
        first_eq.assert_called_once_with("task_id", "task-1")
        first_eq.return_value.eq.assert_called_once_with("user_id", "user-1")

    @unittest.expectedFailure
    def test_is_assignee_false_when_the_database_library_returns_none_for_no_match(self):
        """
        KNOWN ISSUE (expected failure): the real Supabase library returns None - not a response
        object - when maybe_single() finds no row, so `result.data` raises AttributeError. The
        test above uses a response with data=None, which hides that. This is the faithful version.
        When the code is fixed, unittest reports an "unexpected success": remove
        @unittest.expectedFailure then.
        """

        mock_supabase = mock_assignee_lookup(None)

        with patch.object(tasks, "supabase", mock_supabase):
            expected = False
            actual = tasks._is_assignee("task-1", "user-2")
            self.check(expected, actual)


if __name__ == "__main__":
    unittest.main()
    