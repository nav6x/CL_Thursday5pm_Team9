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