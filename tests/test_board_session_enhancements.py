"""
Tests for all session enhancements added to Scrumptious:
- Backend:
  - Column rename endpoint (PATCH /api/projects/<id>/columns/<id>)
  - Column delete endpoint (DELETE /api/projects/<id>/columns/<id>)
  - Dynamic password reset redirect URL resolution based on host headers
- Frontend (board.html, board.js, style.css):
  - Toolbar quick filters (Assignee: All / My Tasks, Due Date: All / Overdue)
  - Task Modal redesign (clean title without [TASK] badge, single close action in sticky footer)
  - Story points restoration (input field in modal, story-points class on cards)
  - Card quick-move arrow buttons (left and right directional moves)
  - Column management controls (rename and delete buttons for leaders)
  - Burndown chart modal (stat counters, SVG chart, and modal overlay)
  - Docked sidebar sprint progress widget directly above the footer
  - board.js variable safety (activeFilterAssignee, activeFilterDue)
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import re
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask, g

import auth_utils
from app import app as flask_app
import routes.columns as columns
import routes.auth as auth_module
BOARD_HTML = (PROJECT_ROOT / "board.html").read_text(encoding="utf-8")
BOARD_JS = (PROJECT_ROOT / "static/js/board.js").read_text(encoding="utf-8")
STYLE_CSS = (PROJECT_ROOT / "static/css/style.css").read_text(encoding="utf-8")


class TestColumnBackendEndpoints(unittest.TestCase):
    """Verify backend endpoints for column rename and column delete."""

    def test_leader_can_rename_column(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{"id": "col-1", "name": "QA / Testing"}]

        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "leader",
        ), patch.object(columns, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns/col-1",
                method="PATCH",
                json={"name": "QA / Testing"},
            ):
                g.user = SimpleNamespace(id="leader-1")
                response, status_code = columns.rename_column.__wrapped__(
                    "project-1", "col-1"
                )

                self.assertEqual(status_code, 200)
                data = response.get_json()
                self.assertEqual(data["name"], "QA / Testing")

    def test_developer_cannot_rename_column(self):
        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "developer",
        ):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns/col-1",
                method="PATCH",
                json={"name": "QA / Testing"},
            ):
                g.user = SimpleNamespace(id="dev-1")
                response, status_code = columns.rename_column.__wrapped__(
                    "project-1", "col-1"
                )

                self.assertEqual(status_code, 403)
                self.assertIn("requires role", response.get_json()["error"])

    def test_leader_can_delete_column(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.delete.return_value.eq.return_value \
            .execute.return_value.data = [{"id": "col-1"}]

        with patch.object(
            auth_utils, "get_role_in_project",
            lambda user_id, project_id: "leader",
        ), patch.object(columns, "supabase", mock_supabase):
            with flask_app.test_request_context(
                "/api/projects/project-1/columns/col-1",
                method="DELETE",
            ):
                g.user = SimpleNamespace(id="leader-1")
                response, status_code = columns.delete_column.__wrapped__(
                    "project-1", "col-1"
                )

                self.assertEqual(status_code, 200)
                self.assertEqual(response.get_json()["message"], "Column deleted")


class TestPasswordResetRedirectUrl(unittest.TestCase):
    """Verify dynamic password reset redirect URL resolution."""

    def test_dynamic_redirect_url_for_deployed_host(self):
        fake_anon = MagicMock()
        fake_service = MagicMock()
        with patch.object(auth_module, "supabase_auth", fake_anon), \
             patch.object(auth_module, "supabase", fake_service):
            test_app = Flask(__name__)
            test_app.register_blueprint(auth_module.auth_bp)
            client = test_app.test_client()

            res = client.post(
                "/api/auth/forgot-password",
                json={"email": "alice@example.com"},
                headers={
                    "Host": "scrumptious-app.onrender.com",
                    "X-Forwarded-Proto": "https",
                },
            )
            self.assertEqual(res.status_code, 200)
            fake_anon.auth.reset_password_for_email.assert_called_once_with(
                "alice@example.com",
                {"redirect_to": "https://scrumptious-app.onrender.com/reset-password.html"},
            )


class TestBoardUILayoutAndComponents(unittest.TestCase):
    """Verify board template and layout enhancements."""

    def test_board_toolbar_and_filters_exist(self):
        """The separate toolbar contains both assignee and due date quick filters."""
        self.assertIn('class="board-toolbar"', BOARD_HTML)
        self.assertIn('data-filter-assignee="all"', BOARD_HTML)
        self.assertIn('data-filter-assignee="my_tasks"', BOARD_HTML)
        self.assertIn('data-filter-due="all"', BOARD_HTML)
        self.assertIn('data-filter-due="overdue"', BOARD_HTML)

    def test_task_modal_has_no_redundant_badge_or_double_close_button(self):
        """Task modal header has clean title, no [TASK] badge, and no broken header close button."""
        # Check taskModal title
        self.assertIn('id="modalTitle"', BOARD_HTML)
        self.assertIn('Edit Task', BOARD_HTML)
        # Ensure redundant [TASK] text is removed
        self.assertNotIn('[TASK]', BOARD_HTML)
        # Check task modal footer actions
        self.assertIn('id="cancelTaskBtn"', BOARD_HTML)
        self.assertIn('class="task-modal-footer"', BOARD_HTML)
        self.assertIn('class="task-modal-body"', BOARD_HTML)

    def test_story_points_elements_configured(self):
        """Modal has story points input and board.js renders points badges."""
        self.assertIn('id="taskPoints"', BOARD_HTML)
        self.assertIn('Story Points', BOARD_HTML)
        self.assertIn('story-points', BOARD_JS)
        self.assertIn('story-points', STYLE_CSS)

    def test_burndown_modal_components(self):
        """Burndown modal has stat cards, SVG chart, and modal overlay."""
        self.assertIn('id="burndownModalOverlay"', BOARD_HTML)
        self.assertIn('id="burndownSvg"', BOARD_HTML)
        self.assertIn('id="bdTotalPoints"', BOARD_HTML)
        self.assertIn('id="bdCompletedPoints"', BOARD_HTML)
        self.assertIn('id="bdRemainingPoints"', BOARD_HTML)
        self.assertIn('id="closeBurndownModalBtn"', BOARD_HTML)

    def test_sidebar_sprint_progress_docking(self):
        """Sidebar sprint progress is docked right above the sidebar-footer."""
        self.assertIn('id="sprintSummaryBar"', BOARD_HTML)
        self.assertIn('id="metricProgressPercent"', BOARD_HTML)
        self.assertIn('id="metricProgressFill"', BOARD_HTML)
        # Verify it appears immediately before sidebar-footer
        progress_pos = BOARD_HTML.index('id="sprintSummaryBar"')
        footer_pos = BOARD_HTML.index('class="sidebar-footer"')
        self.assertTrue(progress_pos < footer_pos)

    def test_board_js_filter_variables_declared(self):
        """Variables activeFilterAssignee and activeFilterDue must be declared in board.js."""
        self.assertRegex(BOARD_JS, r'let\s+activeFilterAssignee\s*=\s*["\']all["\'];')
        self.assertRegex(BOARD_JS, r'let\s+activeFilterDue\s*=\s*["\']all["\'];')

    def test_card_quick_move_arrows_in_board_js(self):
        """Card quick move buttons are rendered for fast column transitions."""
        self.assertIn('card-move-btn', BOARD_JS)
        self.assertIn('data-target-col', BOARD_JS)
        self.assertIn('←', BOARD_JS)
        self.assertIn('→', BOARD_JS)

    def test_column_action_buttons_in_board_js(self):
        """Leader column actions (rename, delete) are rendered in column headers."""
        self.assertIn('data-col-action="rename"', BOARD_JS)
        self.assertIn('data-col-action="delete"', BOARD_JS)
        self.assertIn('col-action-btn', BOARD_JS)


if __name__ == "__main__":
    unittest.main()
