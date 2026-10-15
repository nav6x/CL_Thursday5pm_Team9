import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import g
from app import app as flask_app
import routes.projects as projects
import routes.auth as auth


class TestProjectsOverview(unittest.TestCase):

    def test_overview_unauthorized_without_login(self):
        with flask_app.test_client() as client:
            resp = client.get("/api/projects/overview")
            self.assertEqual(resp.status_code, 401)

    def test_overview_empty_projects(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.execute.return_value.data = []

        with patch.object(projects, "supabase", mock_supabase):
            with flask_app.test_request_context("/api/projects/overview", method="GET"):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = projects.projects_overview.__wrapped__()
                data = response.get_json()

                self.assertEqual(status_code, 200)
                self.assertEqual(data["total_projects"], 0)
                self.assertEqual(data["projects"], [])

    def test_overview_with_projects_and_members(self):
        mock_projects = [
            {"id": "p-1", "name": "Alpha Project", "created_at": "2026-01-01", "created_by": "user-1"},
            {"id": "p-2", "name": "Beta Project", "created_at": "2026-02-01", "created_by": "user-2"},
        ]
        mock_members = [
            {
                "project_id": "p-1",
                "user_id": "user-1",
                "role": "leader",
                "profiles": {"id": "user-1", "full_name": "Alice [Project Leader]", "email": "alice@example.com"},
            },
            {
                "project_id": "p-1",
                "user_id": "user-2",
                "role": "developer",
                "profiles": {"id": "user-2", "full_name": "Bob [Developer]", "email": "bob@example.com"},
            },
            {
                "project_id": "p-2",
                "user_id": "user-2",
                "role": "leader",
                "profiles": {"id": "user-2", "full_name": "Bob [Scrum Master]", "email": "bob@example.com"},
            },
        ]

        def fake_table(name):
            mock_t = MagicMock()
            if name == "projects":
                mock_t.select.return_value.execute.return_value.data = mock_projects
            elif name == "project_members":
                mock_t.select.return_value.execute.return_value.data = mock_members
            return mock_t

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = fake_table

        with patch.object(projects, "supabase", mock_supabase):
            with flask_app.test_request_context("/api/projects/overview", method="GET"):
                g.user = SimpleNamespace(id="user-1")
                response, status_code = projects.projects_overview.__wrapped__()
                data = response.get_json()

                self.assertEqual(status_code, 200)
                self.assertEqual(data["total_projects"], 2)

                p1 = next(p for p in data["projects"] if p["id"] == "p-1")
                self.assertEqual(p1["name"], "Alpha Project")
                self.assertEqual(p1["member_count"], 2)
                self.assertTrue(p1["is_member"])
                self.assertEqual(p1["my_role"], "leader")
                self.assertEqual(p1["my_agile_role"], "Project Leader")
                self.assertEqual(len(p1["members"]), 2)
                self.assertEqual(p1["members"][0]["full_name"], "Alice")
                self.assertEqual(p1["members"][1]["full_name"], "Bob")

                p2 = next(p for p in data["projects"] if p["id"] == "p-2")
                self.assertEqual(p2["name"], "Beta Project")
                self.assertEqual(p2["member_count"], 1)
                self.assertFalse(p2["is_member"])
                self.assertIsNone(p2["my_role"])


class TestAuthUsersProjectAccess(unittest.TestCase):

    def test_list_users_with_project_counts_and_access(self):
        mock_profiles = [
            {"id": "u-1", "full_name": "Alice", "email": "alice@test.com"},
            {"id": "u-2", "full_name": "Bob", "email": "bob@test.com"},
        ]
        mock_memberships = [
            {"user_id": "u-1", "role": "leader", "projects": {"id": "p-1", "name": "Alpha"}},
            {"user_id": "u-1", "role": "developer", "projects": {"id": "p-2", "name": "Beta"}},
            {"user_id": "u-2", "role": "developer", "projects": {"id": "p-2", "name": "Beta"}},
        ]

        def fake_table(name):
            mock_t = MagicMock()
            if name == "profiles":
                mock_t.select.return_value.execute.return_value.data = mock_profiles
            elif name == "project_members":
                mock_t.select.return_value.execute.return_value.data = mock_memberships
            return mock_t

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = fake_table

        with patch.object(auth, "supabase", mock_supabase):
            with flask_app.test_request_context("/api/auth/users", method="GET"):
                response, status_code = auth.list_users()
                data = response.get_json()

                self.assertEqual(status_code, 200)
                self.assertEqual(len(data), 2)

                u1 = next(u for u in data if u["id"] == "u-1")
                self.assertEqual(u1["project_count"], 2)
                self.assertEqual(len(u1["projects"]), 2)
                self.assertEqual(u1["projects"][0]["name"], "Alpha")

                u2 = next(u for u in data if u["id"] == "u-2")
                self.assertEqual(u2["project_count"], 1)
                self.assertEqual(len(u2["projects"]), 1)
                self.assertEqual(u2["projects"][0]["name"], "Beta")

    def test_list_users_graceful_fallback_when_error(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "u-1", "full_name": "Alice", "email": "alice@test.com"}]),
            Exception("Database connection failure"),
        ]

        with patch.object(auth, "supabase", mock_supabase):
            with flask_app.test_request_context("/api/auth/users", method="GET"):
                response, status_code = auth.list_users()
                data = response.get_json()

                self.assertEqual(status_code, 200)
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["project_count"], 0)
                self.assertEqual(data[0]["projects"], [])


if __name__ == "__main__":
    unittest.main()
