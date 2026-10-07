
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
 
from flask import g
 
from app import app as flask_app
import routes.columns as columns
import auth_utils
 
 
class TestCreateColumn(unittest.TestCase):
 
    def test_developer_cannot_create_column(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "developer",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns",
                method="POST",
                json={"name": "Blocked"},
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = columns.create_column.__wrapped__("project-1")
 
                expected = 403
                actual = status_code
                self.assertTrue(expected == actual)
 
                expected = True
                actual = "requires role" in response.get_json()["error"]
                self.assertTrue(expected == actual)


    def test_non_member_cannot_create_column(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: None,
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns",
                method="POST",
                json={"name": "Blocked"},
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = columns.create_column.__wrapped__("project-1")
 
                expected = 403
                actual = status_code
                self.assertTrue(expected == actual)
 
                expected = "You are not a member of this project"
                actual = response.get_json()["error"]
                self.assertTrue(expected == actual)

    def test_create_column_missing_name(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "leader",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns",
                method="POST",
                json={"name": "   "},
            ):
                g.user = SimpleNamespace(id="leader-1")
                response, status_code = columns.create_column.__wrapped__("project-1")

                expected = 400
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "Column name is required"
                actual = response.get_json()["error"]
                self.assertTrue(expected == actual)

    def test_leader_can_create_column(self):
        """New column's position should be appended after however many
        already exist."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                {"position": 0}, {"position": 1}, {"position": 2},
            ]
        created_column = {
            "id": "col-4", "project_id": "project-1",
            "name": "Blocked", "position": 3,
        }
        mock_supabase.table.return_value.insert.return_value \
            .execute.return_value.data = [created_column]

        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "leader",
        ), patch.object(columns, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns",
                method="POST",
                json={"name": "Blocked"},
            ):
                g.user = SimpleNamespace(id="leader-1")
                response, status_code = columns.create_column.__wrapped__("project-1")
                data = response.get_json()

                expected = 201
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "Blocked"
                actual = data["name"]
                self.assertTrue(expected == actual)

                expected = 3
                actual = data["position"]
                self.assertTrue(expected == actual)


class TestRenameColumn(unittest.TestCase):

    def test_rename_column_nothing_to_update(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "leader",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns/col-1",
                method="PATCH",
                json={},
            ):
                g.user = SimpleNamespace(id="leader-1")
                response, status_code = columns.rename_column.__wrapped__(
                    "project-1", "col-1"
                )

                expected = 400
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "Nothing to update"
                actual = response.get_json()["error"]
                self.assertTrue(expected == actual)


class TestDeleteColumn(unittest.TestCase):

    def test_developer_cannot_delete_column(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "developer",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns/col-1",
                method="DELETE",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = columns.delete_column.__wrapped__(
                    "project-1", "col-1"
                )

                expected = 403
                actual = status_code
                self.assertTrue(expected == actual)


if __name__ == "__main__":
    unittest.main()