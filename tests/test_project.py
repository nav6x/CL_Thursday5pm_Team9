import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
 
from flask import g
 
from app import app as flask_app
import routes.projects as projects
import auth_utils
 
 
class TestCreateProject(unittest.TestCase):
 
    def test_create_project_missing_name(self):
        with flask_app.test_request_context(
            "/api/projects",
            method="POST",
            json={"name": "   "},
        ):
            g.user = SimpleNamespace(id="user-1")
            response, status_code = projects.create_project.__wrapped__()
 
            expected = 400
            actual = status_code
            self.assertTrue(expected == actual)
 
            expected = "Project name is required"
            actual = response.get_json()["error"]
            self.assertTrue(expected == actual)

    def test_create_project_success(self):
        """Should insert the project, make the creator its Leader, and
        add three default columns in order."""
        created_project = {"id": "project-1", "name": "Sprint 2", "created_by": "user-1"}
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value \
            .execute.return_value.data = [created_project]
 
        with patch.object(projects, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects",
                method="POST",
                json={"name": "Sprint 2"},
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = projects.create_project.__wrapped__()
                data = response.get_json()
 
                expected = 201
                actual = status_code
                self.assertTrue(expected == actual)
 
                expected = "Sprint 2"
                actual = data["name"]
                self.assertTrue(expected == actual)
 
                insert_calls = mock_supabase.table.return_value.insert.call_args_list
                expected = 3
                actual = len(insert_calls)
                self.assertTrue(expected == actual)
 
                default_columns_payload = insert_calls[2].args[0]
                expected = ["To Do", "In Progress", "Done"]
                actual = [c["name"] for c in default_columns_payload]
                self.assertTrue(expected == actual)
 
 
class TestDeleteProject(unittest.TestCase):
 
    def test_developer_cannot_delete_project(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "developer",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1",
                method="DELETE",
            ):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = projects.delete_project.__wrapped__("project-1")
 
                expected = 403
                actual = status_code
                self.assertTrue(expected == actual)