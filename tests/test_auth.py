import unittest
from unittest.mock import MagicMock, patch

from app import app as flask_app
import routes.auth as auth
import routes.tasks as tasks
from flask import g
from types import SimpleNamespace

class TestSignup(unittest.TestCase):

    def test_signup_missing_email(self):
        with flask_app.test_request_context(
            "/api/auth/signup",
            method="POST",
            json={"password": "hunter2", "full_name": "Jamie Chen"},
        ):
            response, status_code = auth.signup()

            expected = 400
            actual = status_code
            self.assertTrue(expected == actual)

            expected = "email, password, and full_name are required"
            actual = response.get_json()["error"]
            self.assertTrue(expected == actual)

    def test_signup_missing_password(self):
        with flask_app.test_request_context(
            "/api/auth/signup",
            method="POST",
            json={"email": "jamie@example.com", "full_name": "Jamie Chen"},
        ):
            response, status_code = auth.signup()

            expected = 400
            actual = status_code
            self.assertTrue(expected == actual)

            expected = "email, password, and full_name are required"
            actual = response.get_json()["error"]
            self.assertTrue(expected == actual)

    def test_signup_missing_full_name(self):
        with flask_app.test_request_context(
            "/api/auth/signup",
            method="POST",
            json={"email": "jamie@example.com", "password": "hunter2"},
        ):
            response, status_code = auth.signup()

            expected = 400
            actual = status_code
            self.assertTrue(expected == actual)

            expected = "email, password, and full_name are required"
            actual = response.get_json()["error"]
            self.assertTrue(expected == actual)

    def test_signup_success(self):
        """A valid signup should create the auth user, mirror it into
        profiles, and lowercase the email before using it."""
        fake_user = MagicMock()
        fake_user.id = "user-123"
        fake_auth_result = MagicMock()
        fake_auth_result.user = fake_user

        mock_supabase_auth = MagicMock()
        mock_supabase_auth.auth.sign_up.return_value = fake_auth_result
        mock_supabase = MagicMock()

        with patch.object(auth, "supabase_auth", mock_supabase_auth), \
                patch.object(auth, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/auth/signup",
                method="POST",
                json={
                    "email": "Jamie@Example.com",  # deliberately mixed case
                    "password": "hunter2",
                    "full_name": "Jamie Chen",
                },
            ):
                response, status_code = auth.signup()

                expected = 201
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "user-123"
                actual = response.get_json()["user_id"]
                self.assertTrue(expected == actual)

                expected = {"email": "jamie@example.com", "password": "hunter2"}
                actual = mock_supabase_auth.auth.sign_up.call_args.args[0]
                self.assertTrue(expected == actual)

    def test_signup_supabase_rejects(self):
        """If Supabase itself rejects the signup, surface a 400 rather
        than crashing."""
        mock_supabase_auth = MagicMock()
        mock_supabase_auth.auth.sign_up.side_effect = Exception("User already registered")

        with patch.object(auth, "supabase_auth", mock_supabase_auth):
            with flask_app.test_request_context(
                "/api/auth/signup",
                method="POST",
                json={
                    "email": "jamie@example.com",
                    "password": "hunter2",
                    "full_name": "Jamie Chen",
                },
            ):
                response, status_code = auth.signup()

                expected = 400
                actual = status_code
                self.assertTrue(expected == actual)

                expected = True
                actual = "already registered" in response.get_json()["error"]
                self.assertTrue(expected == actual)


class TestLogin(unittest.TestCase):

    def test_login_invalid_credentials(self):
        mock_supabase_auth = MagicMock()
        mock_supabase_auth.auth.sign_in_with_password.side_effect = Exception("Invalid login")

        with patch.object(auth, "supabase_auth", mock_supabase_auth):
            with flask_app.test_request_context(
                "/api/auth/login",
                method="POST",
                json={"email": "jamie@example.com", "password": "wrongpassword"},
            ):
                response, status_code = auth.login()

                expected = 401
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "Invalid email or password"
                actual = response.get_json()["error"]
                self.assertTrue(expected == actual)

    def test_login_success(self):
        fake_session = MagicMock()
        fake_session.access_token = "fake-jwt-token"
        fake_user = MagicMock()
        fake_user.id = "user-123"
        fake_user.email = "jamie@example.com"
        fake_result = MagicMock()
        fake_result.session = fake_session
        fake_result.user = fake_user

        mock_supabase_auth = MagicMock()
        mock_supabase_auth.auth.sign_in_with_password.return_value = fake_result

        with patch.object(auth, "supabase_auth", mock_supabase_auth):
            with flask_app.test_request_context(
                "/api/auth/login",
                method="POST",
                json={"email": "jamie@example.com", "password": "hunter2"},
            ):
                response, status_code = auth.login()
                data = response.get_json()

                expected = 200
                actual = status_code
                self.assertTrue(expected == actual)

                expected = "fake-jwt-token"
                actual = data["access_token"]
                self.assertTrue(expected == actual)

                expected = "user-123"
                actual = data["user"]["id"]
                self.assertTrue(expected == actual)

                expected = "jamie@example.com"
                actual = data["user"]["email"]
                self.assertTrue(expected == actual)

class TestUpdateTaskMoveColumn(unittest.TestCase):

    def test_developer_can_move_task_to_another_column(self):
        """A developer should be able to move a task between columns
        (e.g. 'In Progress' -> 'Done') even if they didn't create it
        and aren't assigned to it — this is the 'move-only' exception."""
        fake_task = {
            "id": "task-1",
            "project_id": "proj-1",
            "column_id": "col-todo",
            "created_by": "someone-else",
        }
        fake_updated_task = {**fake_task, "column_id": "col-done"}

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [fake_updated_task]

        with patch.object(tasks, "_get_task_or_404", lambda task_id: fake_task), \
                patch.object(tasks, "get_role_in_project", lambda user_id, project_id: "developer"), \
                patch.object(tasks, "_is_assignee", lambda task_id, user_id: False), \
                patch.object(tasks, "supabase", mock_supabase):

            with flask_app.test_request_context(
                "/api/projects/proj-1/tasks/task-1",
                method="PATCH",
                json={"column_id": "col-done"},
            ):
                g.user = SimpleNamespace(id="developer-user-id")
                response, status_code = tasks.update_task.__wrapped__("proj-1", "task-1")

                self.assertEqual(status_code, 200)
                self.assertEqual(response.get_json()["column_id"], "col-done")
                
if __name__ == "__main__":
    unittest.main()