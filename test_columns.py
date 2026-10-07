
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