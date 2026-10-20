"""Tests for the task activity / history log (activity.py and the routes that use it).

Written with unittest, so either of these works:
    python -m unittest tests.test_activity_log -v
    pytest tests/test_activity_log.py

Pure-logic tests (diffing, parsing, recording) need no database. The route tests use
small in-memory fakes in place of Supabase and call the view functions directly via
__wrapped__, so login is bypassed and the role is supplied by the test.

ActivityTestCase.setUp does all the isolation itself (fake databases, notifications
switched off, caches cleared), so this file does not depend on conftest.py.
"""
import os
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "dummy-anon-key")

import json
import unittest
from types import SimpleNamespace

from flask import g

import activity
import routes.tasks as tasks
from activity import (
    ASSIGNEES_CHANGED, COMMENT_ADDED, COMMENT_DELETED, DESCRIPTION_CHANGED,
    DUE_DATE_CHANGED, PRIORITY_CHANGED, STORY_POINTS_CHANGED, SUBTASK_ADDED,
    SUBTASK_COMPLETED, SUBTASK_REMOVED, SUBTASK_REOPENED, TAGS_CHANGED,
    TASK_CREATED, TASK_DELETED, TASK_MOVED, TASK_RENAMED,
)
from app import app as flask_app


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def pack(tags=None, due="", checklist=None, comments=None, desc=""):
    """Build a description string exactly the way board.js packTaskDescription does."""
    meta = {}
    if tags:
        meta["tags"] = tags
    if due:
        meta["due"] = due
    if checklist:
        meta["checklist"] = checklist
    if comments:
        meta["comments"] = comments
    if not meta:
        return desc
    return f"[meta:{json.dumps(meta, separators=(',', ':'))}]---{desc}"


def actions(events):
    return [e["action"] for e in events]


def diff_desc(old_desc, new_desc):
    return activity.diff_task_update({"description": old_desc}, {"description": new_desc})


class FakeQuery:
    """Chainable stand-in for a supabase query: every method returns itself,
    execute() returns the canned data, and every call is recorded."""

    def __init__(self, data):
        self._data = data
        self._single = False
        self.calls = []

    def __getattr__(self, method):
        def _call(*args, **kwargs):
            self.calls.append((method, args, kwargs))
            return self
        return _call

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        if self._single:
            # Like supabase-py 2.x: one row as a dict, or None (not a response) if no match.
            data = self._data
            if isinstance(data, list):
                data = data[0] if data else None
            return SimpleNamespace(data=data) if data is not None else None
        return SimpleNamespace(data=self._data)

    def args_of(self, method):
        return [(a, k) for m, a, k in self.calls if m == method]


class FakeSupabase:
    def __init__(self, **tables):
        self.tables = tables
        self.queries = []

    def table(self, name):
        q = FakeQuery(self.tables.get(name, []))
        q.table_name = name
        self.queries.append(q)
        return q

    def inserted(self, table):
        rows = []
        for q in self.queries:
            if q.table_name == table:
                for (args, _kw) in q.args_of("insert"):
                    rows.extend(args[0] if isinstance(args[0], list) else [args[0]])
        return rows


class Boom:
    """A database that always fails."""

    def table(self, name):
        raise RuntimeError("database is down")


ACTOR = SimpleNamespace(id="user-1", email="ada@x.com")

OLD_TASK = {
    "id": "task-1", "project_id": "project-1", "column_id": "col-todo", "name": "Login",
    "description": "", "priority": "medium", "story_points": 3, "created_by": "user-1",
}


class ActivityTestCase(unittest.TestCase):
    """Fake log database, leader role, notifications off, empty caches."""

    def setUp(self):
        self.log_db = FakeSupabase(
            columns=[{"id": "col-todo", "name": "To Do"}, {"id": "col-done", "name": "Done"}],
            profiles=[{"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"}],
        )
        self.replace(activity, "supabase", self.log_db)
        self.replace(tasks, "get_role_in_project", lambda uid, pid: "leader")

        # Notifications (if the routes have them) use their own database client:
        # switch them off so no test touches the network or writes notification rows.
        for name in ("notify_project", "create_notifications"):
            if hasattr(tasks, name):
                self.replace(tasks, name, lambda *a, **k: None)
        for name in ("display_name", "project_name"):
            if hasattr(tasks, name):
                self.replace(tasks, name, lambda *a, **k: "Someone")

        if hasattr(activity, "clear_caches"):      # only present if activity.py has the caching code
            activity.clear_caches()
            self.addCleanup(activity.clear_caches)

    def replace(self, obj, name, value):
        """Swap obj.name for value for the rest of this test, then put it back."""
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)

    def as_role(self, role):
        self.replace(tasks, "get_role_in_project", lambda uid, pid: role)

    def call(self, view, *args, method="PATCH", path="/api/projects/project-1/tasks/task-1", json_body=None):
        """Call a route function directly as ACTOR. Returns (response, status)."""
        with flask_app.test_request_context(path, method=method, json=json_body):
            g.user = ACTOR
            return view.__wrapped__(*args)

    def task_db(self, **tables):
        """Fake database for the routes' own queries (tasks.supabase)."""
        self.replace(tasks, "supabase", FakeSupabase(**tables))

    def logged(self):
        return self.log_db.inserted("task_activity")


# ---------------------------------------------------------------------------
# names and description parsing
# ---------------------------------------------------------------------------
class TestNames(ActivityTestCase):
    def test_strips_role_suffix(self):
        self.assertEqual(activity.clean_display_name("Ada Lovelace [Scrum Master]"), "Ada Lovelace")

    def test_falls_back_to_email_then_placeholder(self):
        self.assertEqual(activity.clean_display_name("", "ada@x.com"), "ada@x.com")
        self.assertEqual(activity.clean_display_name(None, None), "Someone")


class TestParseDescription(ActivityTestCase):
    def test_plain_text(self):
        self.assertEqual(activity.parse_description("  hello ")["desc"], "hello")

    def test_empty_and_none(self):
        self.assertEqual(activity.parse_description(None)["desc"], "")
        self.assertEqual(activity.parse_description("")["tags"], [])

    def test_meta_round_trip(self):
        raw = pack(["Bug"], "2026-10-20", [{"t": "a", "d": True}], [{"id": "1", "text": "hi"}], "body")
        parsed = activity.parse_description(raw)
        self.assertEqual(parsed["tags"], ["Bug"])
        self.assertEqual(parsed["due"], "2026-10-20")
        self.assertEqual(parsed["checklist"], [{"t": "a", "d": True}])
        self.assertEqual(parsed["comments"][0]["text"], "hi")
        self.assertEqual(parsed["desc"], "body")

    def test_legacy_tags_format(self):
        parsed = activity.parse_description("[tags:Frontend,Feature] Do the thing")
        self.assertEqual(parsed["tags"], ["Frontend", "Feature"])
        self.assertEqual(parsed["desc"], "Do the thing")

    def test_corrupt_meta_is_treated_as_plain_text(self):
        parsed = activity.parse_description("[meta:{not json}]---oops")
        self.assertEqual(parsed["tags"], [])


# ---------------------------------------------------------------------------
# diff_task_update: plain fields
# ---------------------------------------------------------------------------
class TestDiffPlainFields(ActivityTestCase):
    OLD = {"name": "Login", "priority": "medium", "story_points": 3, "column_id": "col-todo", "description": ""}

    def test_rename(self):
        events = activity.diff_task_update(self.OLD, {"name": "Login page"})
        self.assertEqual(events, [{"action": TASK_RENAMED, "details": {"from": "Login", "to": "Login page"}}])

    def test_priority_and_points(self):
        events = activity.diff_task_update(self.OLD, {"priority": "high", "story_points": 5})
        self.assertEqual(actions(events), [PRIORITY_CHANGED, STORY_POINTS_CHANGED])
        self.assertEqual(events[0]["details"], {"from": "medium", "to": "high"})
        self.assertEqual(events[1]["details"], {"from": 3, "to": 5})

    def test_unchanged_values_produce_no_events(self):
        same = {"name": "Login", "priority": "medium", "story_points": 3, "column_id": "col-todo"}
        self.assertEqual(activity.diff_task_update(self.OLD, same), [])

    def test_position_alone_is_ignored(self):
        self.assertEqual(activity.diff_task_update(self.OLD, {"position": 7}), [])

    def test_move_uses_column_names(self):
        names = {"col-todo": "To Do", "col-done": "Done"}
        events = activity.diff_task_update(self.OLD, {"column_id": "col-done"}, names)
        self.assertEqual(events, [{"action": TASK_MOVED, "details": {"from_column": "To Do", "to_column": "Done"}}])

    def test_move_to_same_column_is_not_logged(self):
        self.assertEqual(activity.diff_task_update(self.OLD, {"column_id": "col-todo"}), [])

    def test_move_with_unknown_column_names_still_logs(self):
        events = activity.diff_task_update(self.OLD, {"column_id": "col-x"})
        self.assertEqual(events[0]["details"], {"from_column": None, "to_column": None})


# ---------------------------------------------------------------------------
# diff_task_update: things packed inside `description`
# ---------------------------------------------------------------------------
class TestDiffDescriptionMeta(ActivityTestCase):
    def test_description_text_change(self):
        self.assertEqual(actions(diff_desc(pack(desc="old"), pack(desc="new"))), [DESCRIPTION_CHANGED])

    def test_meta_only_change_is_not_a_description_change(self):
        events = diff_desc(pack(desc="same"), pack(tags=["Bug"], desc="same"))
        self.assertEqual(actions(events), [TAGS_CHANGED])

    def test_legacy_tag_format_to_meta_format_is_not_a_phantom_change(self):
        self.assertEqual(diff_desc("[tags:Bug] same", pack(tags=["Bug"], desc="same")), [])

    def test_tags_added_and_removed(self):
        events = diff_desc(pack(tags=["Bug", "Design"]), pack(tags=["Design", "DevOps"]))
        self.assertEqual(events, [{"action": TAGS_CHANGED, "details": {"added": ["DevOps"], "removed": ["Bug"]}}])

    def test_tag_comparison_ignores_case(self):
        self.assertEqual(diff_desc(pack(tags=["bug"]), pack(tags=["Bug"])), [])

    def test_due_date_set_changed_and_cleared(self):
        self.assertEqual(diff_desc(pack(), pack(due="2026-10-20"))[0]["details"],
                         {"from": None, "to": "2026-10-20"})
        self.assertEqual(diff_desc(pack(due="2026-10-20"), pack(due="2026-10-25"))[0]["details"],
                         {"from": "2026-10-20", "to": "2026-10-25"})
        self.assertEqual(diff_desc(pack(due="2026-10-20"), pack())[0]["details"],
                         {"from": "2026-10-20", "to": None})

    def test_subtask_added_removed_completed_reopened(self):
        old = pack(checklist=[{"t": "write", "d": False}, {"t": "test", "d": True}, {"t": "ship", "d": False}])
        new = pack(checklist=[{"t": "write", "d": True}, {"t": "test", "d": False}, {"t": "review", "d": False}])
        events = diff_desc(old, new)
        self.assertEqual(sorted(actions(events)),
                         sorted([SUBTASK_COMPLETED, SUBTASK_REOPENED, SUBTASK_ADDED, SUBTASK_REMOVED]))
        by_action = {e["action"]: e["details"]["text"] for e in events}
        self.assertEqual(by_action, {
            SUBTASK_COMPLETED: "write", SUBTASK_REOPENED: "test",
            SUBTASK_ADDED: "review", SUBTASK_REMOVED: "ship",
        })

    def test_comment_added(self):
        new = pack(comments=[{"id": "1", "user_name": "Ada", "text": "Looks good"}])
        self.assertEqual(diff_desc(pack(), new), [{"action": COMMENT_ADDED, "details": {"text": "Looks good"}}])

    def test_comment_deleted_records_author(self):
        old = pack(comments=[{"id": "1", "user_name": "Ada", "text": "Oops"}])
        self.assertEqual(diff_desc(old, pack()),
                         [{"action": COMMENT_DELETED, "details": {"text": "Oops", "author": "Ada"}}])

    def test_long_comment_is_truncated(self):
        events = diff_desc(pack(), pack(comments=[{"id": "1", "text": "x" * 500}]))
        shown = events[0]["details"]["text"]
        self.assertLessEqual(len(shown), activity.TEXT_PREVIEW_LEN + 1)
        self.assertTrue(shown.endswith("…"))

    def test_identical_description_produces_nothing(self):
        d = pack(tags=["Bug"], due="2026-10-20", desc="x")
        self.assertEqual(diff_desc(d, d), [])

    def test_several_changes_in_one_save_become_several_events(self):
        old = pack(desc="a")
        new = pack(tags=["Bug"], due="2026-10-20", comments=[{"id": "9", "text": "hi"}], desc="b")
        self.assertEqual(set(actions(diff_desc(old, new))),
                         {DESCRIPTION_CHANGED, TAGS_CHANGED, DUE_DATE_CHANGED, COMMENT_ADDED})


class TestUnchangedItemsAreIgnored(ActivityTestCase):
    def test_unchanged_subtasks_and_comments_alongside_a_real_change(self):
        shared = dict(checklist=[{"t": "a", "d": False}], comments=[{"id": "1", "text": "hi"}])
        events = diff_desc(pack(desc="x", **shared), pack(desc="y", **shared))
        self.assertEqual(actions(events), [DESCRIPTION_CHANGED])


class TestDiffAssignees(ActivityTestCase):
    def test_added_and_removed(self):
        events = activity.diff_assignees({"u1": "Ada", "u2": "Bob"}, {"u2": "Bob", "u3": "Cy"})
        self.assertEqual(events, [{"action": ASSIGNEES_CHANGED, "details": {"added": ["Cy"], "removed": ["Ada"]}}])

    def test_no_change_no_event(self):
        self.assertEqual(activity.diff_assignees({"u1": "Ada"}, {"u1": "Ada"}), [])


# ---------------------------------------------------------------------------
# recording and name lookups
# ---------------------------------------------------------------------------
class TestRecordEvents(ActivityTestCase):
    def test_inserts_one_row_per_event(self):
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [
            activity.event(PRIORITY_CHANGED, **{"from": "low", "to": "high"}),
            activity.event(TASK_RENAMED, **{"from": "a", "to": "b"}),
        ])
        rows = self.logged()
        self.assertEqual([r["action"] for r in rows], [PRIORITY_CHANGED, TASK_RENAMED])
        self.assertEqual(rows[0], {
            "project_id": "p1", "task_id": "t1", "task_name": "Task", "actor_id": "u1",
            "actor_name": "Ada", "action": PRIORITY_CHANGED, "details": {"from": "low", "to": "high"},
        })

    def test_no_events_means_no_query(self):
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [])
        self.assertEqual(self.log_db.queries, [])

    def test_never_raises_when_the_insert_fails(self):
        self.replace(activity, "supabase", Boom())
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [activity.event(TASK_CREATED)])  # no exception

    def test_get_actor_name_uses_profile_and_strips_role(self):
        self.assertEqual(activity.get_actor_name(ACTOR), "Ada Lovelace")

    def test_get_actor_name_falls_back_to_email_if_lookup_fails(self):
        self.replace(activity, "supabase", Boom())
        self.assertEqual(activity.get_actor_name(ACTOR), "ada@x.com")


class TestProfileNames(ActivityTestCase):
    def test_no_ids_means_no_query(self):
        self.assertEqual(activity.profile_names([]), {})
        self.assertEqual(activity.profile_names([None]), {})
        self.assertEqual(self.log_db.queries, [])

    def test_role_suffix_is_stripped(self):
        self.assertEqual(activity.profile_names(["user-1"]), {"user-1": "Ada Lovelace"})


# ---------------------------------------------------------------------------
# routes: writing to the log
# ---------------------------------------------------------------------------
class TestUpdateTaskLogsActivity(ActivityTestCase):
    def setUp(self):
        super().setUp()
        self.replace(tasks, "_get_task_or_404", lambda tid: dict(OLD_TASK))
        self.task_db(tasks=[dict(OLD_TASK)])

    def patch(self, body):
        return self.call(tasks.update_task, "project-1", "task-1", json_body=body)

    def test_logs_each_changed_field_with_actor_and_task(self):
        _, status = self.patch({"priority": "high", "story_points": 8})
        self.assertEqual(status, 200)
        rows = self.logged()
        self.assertEqual([r["action"] for r in rows], [PRIORITY_CHANGED, STORY_POINTS_CHANGED])
        for r in rows:
            self.assertEqual((r["actor_id"], r["actor_name"]), ("user-1", "Ada Lovelace"))
            self.assertEqual((r["task_id"], r["project_id"], r["task_name"]), ("task-1", "project-1", "Login"))

    def test_move_logs_column_names(self):
        _, status = self.patch({"column_id": "col-done"})
        self.assertEqual(status, 200)
        rows = self.logged()
        self.assertEqual(rows[0]["action"], TASK_MOVED)
        self.assertEqual(rows[0]["details"], {"from_column": "To Do", "to_column": "Done"})

    def test_saving_without_changes_logs_nothing(self):
        _, status = self.patch({"name": "Login", "priority": "medium", "story_points": 3})
        self.assertEqual(status, 200)
        self.assertEqual(self.logged(), [])

    def test_rename_is_logged_under_the_new_name(self):
        self.patch({"name": "Login page"})
        self.assertEqual(self.logged()[0]["task_name"], "Login page")

    def test_rejected_update_logs_nothing(self):
        _, status = self.patch({"story_points": 99})
        self.assertEqual(status, 400)
        self.assertEqual(self.logged(), [])

    def test_a_broken_log_does_not_fail_the_save(self):
        self.replace(activity, "supabase", Boom())
        self.task_db(tasks=[dict(OLD_TASK, priority="high")])
        response, status = self.patch({"priority": "high"})
        self.assertEqual(status, 200)
        self.assertEqual(response.get_json()["priority"], "high")


class TestCreateTaskLogsActivity(ActivityTestCase):
    def create(self, body):
        return self.call(tasks.create_task, "project-1", method="POST",
                         path="/api/projects/project-1/tasks", json_body=body)

    def test_logs_creation_with_column_name(self):
        self.task_db(tasks=[dict(OLD_TASK)])
        _, status = self.create({"name": "Login", "column_id": "col-todo"})
        self.assertEqual(status, 201)
        rows = self.logged()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], TASK_CREATED)
        self.assertEqual(rows[0]["details"], {"column": "To Do"})
        self.assertEqual(rows[0]["task_id"], "task-1")

    def test_failed_validation_logs_nothing(self):
        self.task_db()
        _, status = self.create({"column_id": "col-todo"})
        self.assertEqual(status, 400)
        self.assertEqual(self.logged(), [])


class TestDeleteTaskLogsActivity(ActivityTestCase):
    def delete(self):
        return self.call(tasks.delete_task, "project-1", "task-1", method="DELETE")

    def test_leader_delete_is_logged_with_the_task_name(self):
        # the task name is found either via activity.task_name or tasks._get_task_or_404,
        # depending on how delete_task was written, so make both work
        self.log_db.tables["tasks"] = {"name": "Login"}
        self.replace(tasks, "_get_task_or_404", lambda tid: {"id": tid, "name": "Login"})
        self.task_db()
        _, status = self.delete()
        self.assertEqual(status, 200)
        self.assertEqual([(r["action"], r["task_name"]) for r in self.logged()], [(TASK_DELETED, "Login")])

    def test_developer_cannot_delete_and_nothing_is_logged(self):
        self.as_role("developer")
        _, status = self.delete()
        self.assertEqual(status, 403)
        self.assertEqual(self.logged(), [])


class TestSetAssigneesLogsActivity(ActivityTestCase):
    def assign(self, ids):
        return self.call(tasks.set_assignees, "project-1", "task-1", method="PUT",
                         path="/api/projects/project-1/tasks/task-1/assignees", json_body={"assignee_ids": ids})

    def test_logs_who_was_added_and_removed(self):
        self.log_db.tables["task_assignees"] = [{"user_id": "user-1"}]
        self.log_db.tables["profiles"] = [
            {"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"},
            {"id": "user-2", "full_name": "Bob Ray [QA Engineer]", "email": "bob@x.com"},
        ]
        self.log_db.tables["tasks"] = {"name": "Login"}
        self.task_db()
        _, status = self.assign(["user-2"])
        self.assertEqual(status, 200)
        rows = self.logged()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], ASSIGNEES_CHANGED)
        self.assertEqual(rows[0]["details"], {"added": ["Bob Ray"], "removed": ["Ada Lovelace"]})

    def test_resaving_the_same_assignees_logs_nothing(self):
        self.log_db.tables["task_assignees"] = [{"user_id": "user-1"}]
        self.task_db()
        _, status = self.assign(["user-1"])
        self.assertEqual(status, 200)
        self.assertEqual(self.logged(), [])


# ---------------------------------------------------------------------------
# routes: reading the log
# ---------------------------------------------------------------------------
ACTIVITY_ROWS = [
    {"id": "a2", "task_id": "task-1", "actor_id": "user-1", "actor_name": "Ada",
     "action": PRIORITY_CHANGED, "details": {"from": "low", "to": "high"}, "created_at": "2026-10-13T05:00:02+00:00"},
    {"id": "a1", "task_id": "task-1", "actor_id": "user-1", "actor_name": "Ada",
     "action": TASK_CREATED, "details": {"column": "To Do"}, "created_at": "2026-10-13T05:00:01+00:00"},
]


class TestListTaskActivity(ActivityTestCase):
    def fetch(self, role="developer", query="", rows=None):
        self.as_role(role)
        fake = FakeSupabase(task_activity=ACTIVITY_ROWS if rows is None else rows)
        self.replace(tasks, "supabase", fake)
        response, status = self.call(
            tasks.list_task_activity, "project-1", "task-1", method="GET",
            path=f"/api/projects/project-1/tasks/task-1/activity{query}")
        return response, status, fake

    def test_member_gets_the_rows(self):
        response, status, _ = self.fetch()
        self.assertEqual(status, 200)
        self.assertEqual(response.get_json(), ACTIVITY_ROWS)

    def test_any_member_role_can_read(self):
        for role in ("leader", "developer"):
            with self.subTest(role=role):
                _, status, _ = self.fetch(role=role)
                self.assertEqual(status, 200)

    def test_non_member_is_refused(self):
        _, status, fake = self.fetch(role=None)
        self.assertEqual(status, 403)
        self.assertEqual(fake.queries, [])

    def test_scoped_to_both_project_and_task(self):
        """Guards against reading another project's history by swapping ids in the URL."""
        _, _, fake = self.fetch()
        eq_calls = [a for a, _k in fake.queries[0].args_of("eq")]
        self.assertIn(("project_id", "project-1"), eq_calls)
        self.assertIn(("task_id", "task-1"), eq_calls)

    def test_newest_first(self):
        _, _, fake = self.fetch()
        self.assertEqual(fake.queries[0].args_of("order"), [(("created_at",), {"desc": True})])

    def test_default_page_is_fifty(self):
        _, _, fake = self.fetch()
        self.assertEqual(fake.queries[0].args_of("range"), [((0, 49), {})])

    def test_limit_is_clamped(self):
        _, _, fake = self.fetch(query="?limit=100000")
        self.assertEqual(fake.queries[0].args_of("range"), [((0, 199), {})])
        _, _, fake = self.fetch(query="?limit=0&offset=-5")
        self.assertEqual(fake.queries[0].args_of("range"), [((0, 0), {})])

    def test_offset_paging(self):
        _, _, fake = self.fetch(query="?limit=10&offset=20")
        self.assertEqual(fake.queries[0].args_of("range"), [((20, 29), {})])

    def test_non_numeric_paging_is_a_400(self):
        response, status, _ = self.fetch(query="?limit=abc")
        self.assertEqual(status, 400)
        self.assertIn("integers", response.get_json()["error"])

    def test_empty_history_is_an_empty_list(self):
        response, status, _ = self.fetch(rows=[])
        self.assertEqual(status, 200)
        self.assertEqual(response.get_json(), [])


# ---------------------------------------------------------------------------
# caching: a card move should not repeat the same lookups every time
# ---------------------------------------------------------------------------
@unittest.skipUnless(hasattr(activity, "clear_caches"), "activity.py has no caching code")
class TestLookupCaching(ActivityTestCase):
    def move(self):
        self.replace(tasks, "_get_task_or_404", lambda tid: dict(OLD_TASK))
        self.task_db(tasks=[dict(OLD_TASK)])
        _, status = self.call(tasks.update_task, "project-1", "task-1", json_body={"column_id": "col-done"})
        self.assertEqual(status, 200)

    def tables_queried(self):
        return [q.table_name for q in self.log_db.queries]

    def test_first_move_looks_up_names_then_logs(self):
        self.move()
        self.assertEqual(self.tables_queried(), ["columns", "profiles", "task_activity"])

    def test_second_move_only_writes_the_log_row(self):
        self.move()
        self.log_db.queries.clear()
        self.move()
        self.assertEqual(self.tables_queried(), ["task_activity"])
        row = self.logged()[0]
        self.assertEqual(row["details"], {"from_column": "To Do", "to_column": "Done"})
        self.assertEqual(row["actor_name"], "Ada Lovelace")

    def test_cache_expires(self):
        clock = [1000.0]
        self.replace(activity, "_now", lambda: clock[0])
        self.move()
        self.log_db.queries.clear()
        clock[0] += activity.CACHE_TTL_SECONDS + 1
        self.move()
        self.assertEqual(self.tables_queried(), ["columns", "profiles", "task_activity"])

    def test_failed_actor_lookup_is_not_cached(self):
        self.replace(activity, "supabase", Boom())
        self.assertEqual(activity.get_actor_name(ACTOR), "ada@x.com")
        self.replace(activity, "supabase", FakeSupabase(
            profiles=[{"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"}]))
        self.assertEqual(activity.get_actor_name(ACTOR), "Ada Lovelace")

    def test_only_uncached_columns_are_fetched(self):
        # like the real database, each fake answers only for the ids it is asked about
        self.replace(activity, "supabase", FakeSupabase(columns=[{"id": "col-todo", "name": "To Do"}]))
        activity.column_names(["col-todo"])

        second = FakeSupabase(columns=[{"id": "col-done", "name": "Done"}])
        self.replace(activity, "supabase", second)
        self.assertEqual(activity.column_names(["col-todo", "col-done"]),
                         {"col-todo": "To Do", "col-done": "Done"})
        self.assertEqual(second.queries[0].args_of("in_"), [(("id", ["col-done"]), {})])
