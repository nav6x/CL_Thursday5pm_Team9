"""Tests for the task activity / history log.

Pure-logic tests (diffing, parsing, recording) need no database. The route tests
use small in-memory fakes in place of Supabase, in the same spirit as the other
test files: they call the view functions directly via __wrapped__, so auth is
bypassed and the role is supplied by monkeypatching get_role_in_project.

conftest.py replaces activity.supabase with a harmless mock for every test; the
route tests below swap in their own FakeSupabase so they can inspect what was
written to `task_activity`.
"""
import json
from types import SimpleNamespace

import pytest
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


@pytest.fixture
def log_db(monkeypatch):
    """A fake DB for the activity module (columns/profiles lookups + log inserts)."""
    fake = FakeSupabase(
        columns=[{"id": "col-todo", "name": "To Do"}, {"id": "col-done", "name": "Done"}],
        profiles=[{"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"}],
    )
    monkeypatch.setattr(activity, "supabase", fake)
    return fake


@pytest.fixture
def as_leader(monkeypatch):
    monkeypatch.setattr(tasks, "get_role_in_project", lambda uid, pid: "leader")


def request_ctx(method="PATCH", path="/api/projects/project-1/tasks/task-1", json_body=None, **kw):
    ctx = flask_app.test_request_context(path, method=method, json=json_body, **kw)
    return ctx


ACTOR = SimpleNamespace(id="user-1", email="ada@x.com")


# ---------------------------------------------------------------------------
# clean_display_name / parse_description
# ---------------------------------------------------------------------------
class TestNames:
    def test_strips_role_suffix(self):
        assert activity.clean_display_name("Ada Lovelace [Scrum Master]") == "Ada Lovelace"

    def test_falls_back_to_email_then_placeholder(self):
        assert activity.clean_display_name("", "ada@x.com") == "ada@x.com"
        assert activity.clean_display_name(None, None) == "Someone"


class TestParseDescription:
    def test_plain_text(self):
        assert activity.parse_description("  hello ")["desc"] == "hello"

    def test_empty_and_none(self):
        assert activity.parse_description(None)["desc"] == ""
        assert activity.parse_description("")["tags"] == []

    def test_meta_round_trip(self):
        raw = pack(["Bug"], "2026-10-20", [{"t": "a", "d": True}], [{"id": "1", "text": "hi"}], "body")
        parsed = activity.parse_description(raw)
        assert parsed["tags"] == ["Bug"]
        assert parsed["due"] == "2026-10-20"
        assert parsed["checklist"] == [{"t": "a", "d": True}]
        assert parsed["comments"][0]["text"] == "hi"
        assert parsed["desc"] == "body"

    def test_legacy_tags_format(self):
        parsed = activity.parse_description("[tags:Frontend,Feature] Do the thing")
        assert parsed["tags"] == ["Frontend", "Feature"]
        assert parsed["desc"] == "Do the thing"

    def test_corrupt_meta_is_treated_as_plain_text(self):
        parsed = activity.parse_description("[meta:{not json}]---oops")
        assert parsed["tags"] == []


# ---------------------------------------------------------------------------
# diff_task_update: plain fields
# ---------------------------------------------------------------------------
class TestDiffPlainFields:
    OLD = {"name": "Login", "priority": "medium", "story_points": 3, "column_id": "col-todo", "description": ""}

    def test_rename(self):
        events = activity.diff_task_update(self.OLD, {"name": "Login page"})
        assert events == [{"action": TASK_RENAMED, "details": {"from": "Login", "to": "Login page"}}]

    def test_priority_and_points(self):
        events = activity.diff_task_update(self.OLD, {"priority": "high", "story_points": 5})
        assert actions(events) == [PRIORITY_CHANGED, STORY_POINTS_CHANGED]
        assert events[0]["details"] == {"from": "medium", "to": "high"}
        assert events[1]["details"] == {"from": 3, "to": 5}

    def test_unchanged_values_produce_no_events(self):
        same = {"name": "Login", "priority": "medium", "story_points": 3, "column_id": "col-todo"}
        assert activity.diff_task_update(self.OLD, same) == []

    def test_position_alone_is_ignored(self):
        assert activity.diff_task_update(self.OLD, {"position": 7}) == []

    def test_move_uses_column_names(self):
        names = {"col-todo": "To Do", "col-done": "Done"}
        events = activity.diff_task_update(self.OLD, {"column_id": "col-done"}, names)
        assert events == [{"action": TASK_MOVED, "details": {"from_column": "To Do", "to_column": "Done"}}]

    def test_move_to_same_column_is_not_logged(self):
        assert activity.diff_task_update(self.OLD, {"column_id": "col-todo"}) == []

    def test_move_with_unknown_column_names_still_logs(self):
        events = activity.diff_task_update(self.OLD, {"column_id": "col-x"})
        assert events[0]["details"] == {"from_column": None, "to_column": None}


# ---------------------------------------------------------------------------
# diff_task_update: things packed inside `description`
# ---------------------------------------------------------------------------
class TestDiffDescriptionMeta:
    def test_description_text_change(self):
        assert actions(diff_desc(pack(desc="old"), pack(desc="new"))) == [DESCRIPTION_CHANGED]

    def test_meta_only_change_is_not_a_description_change(self):
        events = diff_desc(pack(desc="same"), pack(tags=["Bug"], desc="same"))
        assert actions(events) == [TAGS_CHANGED]

    def test_legacy_tag_format_to_meta_format_is_not_a_phantom_change(self):
        events = diff_desc("[tags:Bug] same", pack(tags=["Bug"], desc="same"))
        assert events == []

    def test_tags_added_and_removed(self):
        events = diff_desc(pack(tags=["Bug", "Design"]), pack(tags=["Design", "DevOps"]))
        assert events == [{"action": TAGS_CHANGED, "details": {"added": ["DevOps"], "removed": ["Bug"]}}]

    def test_tag_comparison_ignores_case(self):
        assert diff_desc(pack(tags=["bug"]), pack(tags=["Bug"])) == []

    def test_due_date_set_changed_and_cleared(self):
        assert diff_desc(pack(), pack(due="2026-10-20"))[0]["details"] == {"from": None, "to": "2026-10-20"}
        assert diff_desc(pack(due="2026-10-20"), pack(due="2026-10-25"))[0]["details"] == {"from": "2026-10-20", "to": "2026-10-25"}
        assert diff_desc(pack(due="2026-10-20"), pack())[0]["details"] == {"from": "2026-10-20", "to": None}

    def test_subtask_added_removed_completed_reopened(self):
        old = pack(checklist=[{"t": "write", "d": False}, {"t": "test", "d": True}, {"t": "ship", "d": False}])
        new = pack(checklist=[{"t": "write", "d": True}, {"t": "test", "d": False}, {"t": "review", "d": False}])
        events = diff_desc(old, new)
        assert sorted(actions(events)) == sorted([SUBTASK_COMPLETED, SUBTASK_REOPENED, SUBTASK_ADDED, SUBTASK_REMOVED])
        by_action = {e["action"]: e["details"]["text"] for e in events}
        assert by_action == {
            SUBTASK_COMPLETED: "write", SUBTASK_REOPENED: "test",
            SUBTASK_ADDED: "review", SUBTASK_REMOVED: "ship",
        }

    def test_comment_added(self):
        new = pack(comments=[{"id": "1", "user_name": "Ada", "text": "Looks good"}])
        events = diff_desc(pack(), new)
        assert events == [{"action": COMMENT_ADDED, "details": {"text": "Looks good"}}]

    def test_comment_deleted_records_author(self):
        old = pack(comments=[{"id": "1", "user_name": "Ada", "text": "Oops"}])
        events = diff_desc(old, pack())
        assert events == [{"action": COMMENT_DELETED, "details": {"text": "Oops", "author": "Ada"}}]

    def test_long_comment_is_truncated(self):
        long_text = "x" * 500
        events = diff_desc(pack(), pack(comments=[{"id": "1", "text": long_text}]))
        shown = events[0]["details"]["text"]
        assert len(shown) <= activity.TEXT_PREVIEW_LEN + 1 and shown.endswith("…")

    def test_identical_description_produces_nothing(self):
        d = pack(tags=["Bug"], due="2026-10-20", desc="x")
        assert diff_desc(d, d) == []

    def test_several_changes_in_one_save_become_several_events(self):
        old = pack(desc="a")
        new = pack(tags=["Bug"], due="2026-10-20", comments=[{"id": "9", "text": "hi"}], desc="b")
        assert set(actions(diff_desc(old, new))) == {DESCRIPTION_CHANGED, TAGS_CHANGED, DUE_DATE_CHANGED, COMMENT_ADDED}


class TestDiffAssignees:
    def test_added_and_removed(self):
        events = activity.diff_assignees({"u1": "Ada", "u2": "Bob"}, {"u2": "Bob", "u3": "Cy"})
        assert events == [{"action": ASSIGNEES_CHANGED, "details": {"added": ["Cy"], "removed": ["Ada"]}}]

    def test_no_change_no_event(self):
        assert activity.diff_assignees({"u1": "Ada"}, {"u1": "Ada"}) == []


# ---------------------------------------------------------------------------
# record_events
# ---------------------------------------------------------------------------
class TestRecordEvents:
    def test_inserts_one_row_per_event(self, log_db):
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [
            activity.event(PRIORITY_CHANGED, **{"from": "low", "to": "high"}),
            activity.event(TASK_RENAMED, **{"from": "a", "to": "b"}),
        ])
        rows = log_db.inserted("task_activity")
        assert [r["action"] for r in rows] == [PRIORITY_CHANGED, TASK_RENAMED]
        assert rows[0] == {
            "project_id": "p1", "task_id": "t1", "task_name": "Task", "actor_id": "u1",
            "actor_name": "Ada", "action": PRIORITY_CHANGED, "details": {"from": "low", "to": "high"},
        }

    def test_no_events_means_no_query(self, log_db):
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [])
        assert log_db.queries == []

    def test_never_raises_when_the_insert_fails(self, monkeypatch):
        class Boom:
            def table(self, name):
                raise RuntimeError("relation task_activity does not exist")
        monkeypatch.setattr(activity, "supabase", Boom())
        activity.record_events("p1", "t1", "Task", "u1", "Ada", [activity.event(TASK_CREATED)])  # no exception

    def test_get_actor_name_uses_profile_and_strips_role(self, log_db):
        assert activity.get_actor_name(ACTOR) == "Ada Lovelace"

    def test_get_actor_name_falls_back_to_email_if_lookup_fails(self, monkeypatch):
        class Boom:
            def table(self, name):
                raise RuntimeError("down")
        monkeypatch.setattr(activity, "supabase", Boom())
        assert activity.get_actor_name(ACTOR) == "ada@x.com"


# ---------------------------------------------------------------------------
# routes: writing to the log
# ---------------------------------------------------------------------------
OLD_TASK = {
    "id": "task-1", "project_id": "project-1", "column_id": "col-todo", "name": "Login",
    "description": "", "priority": "medium", "story_points": 3, "created_by": "user-1",
}


class TestUpdateTaskLogsActivity:
    def setup_update(self, monkeypatch, log_db, updated_row=None):
        monkeypatch.setattr(tasks, "_get_task_or_404", lambda tid: dict(OLD_TASK))
        monkeypatch.setattr(tasks, "supabase", FakeSupabase(tasks=[updated_row or dict(OLD_TASK)]))

    def test_logs_each_changed_field_with_actor_and_task(self, monkeypatch, log_db, as_leader):
        self.setup_update(monkeypatch, log_db)
        with request_ctx(json_body={"priority": "high", "story_points": 8}):
            g.user = ACTOR
            _, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 200
        rows = log_db.inserted("task_activity")
        assert [r["action"] for r in rows] == [PRIORITY_CHANGED, STORY_POINTS_CHANGED]
        assert all(r["actor_id"] == "user-1" and r["actor_name"] == "Ada Lovelace" for r in rows)
        assert all(r["task_id"] == "task-1" and r["project_id"] == "project-1" and r["task_name"] == "Login" for r in rows)

    def test_move_logs_column_names(self, monkeypatch, log_db, as_leader):
        self.setup_update(monkeypatch, log_db)
        with request_ctx(json_body={"column_id": "col-done"}):
            g.user = ACTOR
            _, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 200
        rows = log_db.inserted("task_activity")
        assert rows[0]["action"] == TASK_MOVED
        assert rows[0]["details"] == {"from_column": "To Do", "to_column": "Done"}

    def test_saving_without_changes_logs_nothing(self, monkeypatch, log_db, as_leader):
        self.setup_update(monkeypatch, log_db)
        with request_ctx(json_body={"name": "Login", "priority": "medium", "story_points": 3}):
            g.user = ACTOR
            _, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 200
        assert log_db.inserted("task_activity") == []

    def test_rename_is_logged_under_the_new_name(self, monkeypatch, log_db, as_leader):
        self.setup_update(monkeypatch, log_db)
        with request_ctx(json_body={"name": "Login page"}):
            g.user = ACTOR
            tasks.update_task.__wrapped__("project-1", "task-1")
        assert log_db.inserted("task_activity")[0]["task_name"] == "Login page"

    def test_rejected_update_logs_nothing(self, monkeypatch, log_db, as_leader):
        self.setup_update(monkeypatch, log_db)
        with request_ctx(json_body={"story_points": 99}):
            g.user = ACTOR
            _, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 400
        assert log_db.inserted("task_activity") == []

    def test_a_broken_log_does_not_fail_the_save(self, monkeypatch, as_leader):
        class Boom:
            def table(self, name):
                raise RuntimeError("log table missing")
        monkeypatch.setattr(activity, "supabase", Boom())
        monkeypatch.setattr(tasks, "_get_task_or_404", lambda tid: dict(OLD_TASK))
        monkeypatch.setattr(tasks, "supabase", FakeSupabase(tasks=[dict(OLD_TASK, priority="high")]))
        with request_ctx(json_body={"priority": "high"}):
            g.user = ACTOR
            response, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 200
        assert response.get_json()["priority"] == "high"


class TestCreateTaskLogsActivity:
    def test_logs_creation_with_column_name(self, monkeypatch, log_db, as_leader):
        monkeypatch.setattr(tasks, "supabase", FakeSupabase(tasks=[dict(OLD_TASK)]))
        with request_ctx(method="POST", path="/api/projects/project-1/tasks",
                         json_body={"name": "Login", "column_id": "col-todo"}):
            g.user = ACTOR
            _, status = tasks.create_task.__wrapped__("project-1")
        assert status == 201
        rows = log_db.inserted("task_activity")
        assert len(rows) == 1
        assert rows[0]["action"] == TASK_CREATED
        assert rows[0]["details"] == {"column": "To Do"}
        assert rows[0]["task_id"] == "task-1"

    def test_failed_validation_logs_nothing(self, monkeypatch, log_db, as_leader):
        monkeypatch.setattr(tasks, "supabase", FakeSupabase())
        with request_ctx(method="POST", path="/api/projects/project-1/tasks", json_body={"column_id": "col-todo"}):
            g.user = ACTOR
            _, status = tasks.create_task.__wrapped__("project-1")
        assert status == 400
        assert log_db.inserted("task_activity") == []


class TestDeleteTaskLogsActivity:
    def test_leader_delete_is_logged_with_the_task_name(self, monkeypatch, log_db, as_leader):
        log_db.tables["tasks"] = {"name": "Login"}
        monkeypatch.setattr(tasks, "_get_task_or_404", lambda tid: {"id": tid, "name": "Login"})
        monkeypatch.setattr(tasks, "supabase", FakeSupabase())
        with request_ctx(method="DELETE"):
            g.user = ACTOR
            _, status = tasks.delete_task.__wrapped__("project-1", "task-1")
        assert status == 200
        rows = log_db.inserted("task_activity")
        assert [(r["action"], r["task_name"]) for r in rows] == [(TASK_DELETED, "Login")]

    def test_developer_cannot_delete_and_nothing_is_logged(self, monkeypatch, log_db):
        monkeypatch.setattr(tasks, "get_role_in_project", lambda uid, pid: "developer")
        with request_ctx(method="DELETE"):
            g.user = ACTOR
            _, status = tasks.delete_task.__wrapped__("project-1", "task-1")
        assert status == 403
        assert log_db.inserted("task_activity") == []


class TestSetAssigneesLogsActivity:
    def test_logs_who_was_added_and_removed(self, monkeypatch, log_db, as_leader):
        log_db.tables["task_assignees"] = [{"user_id": "user-1"}]
        log_db.tables["profiles"] = [
            {"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"},
            {"id": "user-2", "full_name": "Bob Ray [QA Engineer]", "email": "bob@x.com"},
        ]
        log_db.tables["tasks"] = {"name": "Login"}
        monkeypatch.setattr(tasks, "supabase", FakeSupabase())
        with request_ctx(method="PUT", path="/api/projects/project-1/tasks/task-1/assignees",
                         json_body={"assignee_ids": ["user-2"]}):
            g.user = ACTOR
            _, status = tasks.set_assignees.__wrapped__("project-1", "task-1")
        assert status == 200
        rows = log_db.inserted("task_activity")
        assert len(rows) == 1
        assert rows[0]["action"] == ASSIGNEES_CHANGED
        assert rows[0]["details"] == {"added": ["Bob Ray"], "removed": ["Ada Lovelace"]}

    def test_resaving_the_same_assignees_logs_nothing(self, monkeypatch, log_db, as_leader):
        log_db.tables["task_assignees"] = [{"user_id": "user-1"}]
        monkeypatch.setattr(tasks, "supabase", FakeSupabase())
        with request_ctx(method="PUT", json_body={"assignee_ids": ["user-1"]}):
            g.user = ACTOR
            _, status = tasks.set_assignees.__wrapped__("project-1", "task-1")
        assert status == 200
        assert log_db.inserted("task_activity") == []


# ---------------------------------------------------------------------------
# routes: reading the log
# ---------------------------------------------------------------------------
ACTIVITY_ROWS = [
    {"id": "a2", "task_id": "task-1", "actor_id": "user-1", "actor_name": "Ada",
     "action": PRIORITY_CHANGED, "details": {"from": "low", "to": "high"}, "created_at": "2026-10-13T05:00:02+00:00"},
    {"id": "a1", "task_id": "task-1", "actor_id": "user-1", "actor_name": "Ada",
     "action": TASK_CREATED, "details": {"column": "To Do"}, "created_at": "2026-10-13T05:00:01+00:00"},
]


class TestListTaskActivity:
    def call(self, monkeypatch, role="developer", query="", rows=None):
        monkeypatch.setattr(tasks, "get_role_in_project", lambda uid, pid: role)
        fake = FakeSupabase(task_activity=rows if rows is not None else ACTIVITY_ROWS)
        monkeypatch.setattr(tasks, "supabase", fake)
        with request_ctx(method="GET", path=f"/api/projects/project-1/tasks/task-1/activity{query}"):
            g.user = ACTOR
            response, status = tasks.list_task_activity.__wrapped__("project-1", "task-1")
        return response, status, fake

    def test_member_gets_the_rows(self, monkeypatch):
        response, status, _ = self.call(monkeypatch)
        assert status == 200
        assert response.get_json() == ACTIVITY_ROWS

    def test_any_member_role_can_read(self, monkeypatch):
        for role in ("leader", "developer"):
            _, status, _ = self.call(monkeypatch, role=role)
            assert status == 200

    def test_non_member_is_refused(self, monkeypatch):
        response, status, fake = self.call(monkeypatch, role=None)
        assert status == 403
        assert fake.queries == []

    def test_scoped_to_both_project_and_task(self, monkeypatch):
        """Guards against reading another project's history by swapping ids in the URL."""
        _, _, fake = self.call(monkeypatch)
        q = fake.queries[0]
        eq_calls = [a for a, _k in q.args_of("eq")]
        assert ("project_id", "project-1") in eq_calls
        assert ("task_id", "task-1") in eq_calls

    def test_newest_first(self, monkeypatch):
        _, _, fake = self.call(monkeypatch)
        assert fake.queries[0].args_of("order") == [(("created_at",), {"desc": True})]

    def test_default_page_is_fifty(self, monkeypatch):
        _, _, fake = self.call(monkeypatch)
        assert fake.queries[0].args_of("range") == [((0, 49), {})]

    def test_limit_is_clamped(self, monkeypatch):
        _, _, fake = self.call(monkeypatch, query="?limit=100000")
        assert fake.queries[0].args_of("range") == [((0, 199), {})]
        _, _, fake = self.call(monkeypatch, query="?limit=0&offset=-5")
        assert fake.queries[0].args_of("range") == [((0, 0), {})]

    def test_offset_paging(self, monkeypatch):
        _, _, fake = self.call(monkeypatch, query="?limit=10&offset=20")
        assert fake.queries[0].args_of("range") == [((20, 29), {})]

    def test_non_numeric_paging_is_a_400(self, monkeypatch):
        response, status, _ = self.call(monkeypatch, query="?limit=abc")
        assert status == 400
        assert "integers" in response.get_json()["error"]

    def test_empty_history_is_an_empty_list(self, monkeypatch):
        response, status, _ = self.call(monkeypatch, rows=[])
        assert status == 200
        assert response.get_json() == []


# ---------------------------------------------------------------------------
# caching: a card move should not repeat the same lookups every time
# ---------------------------------------------------------------------------
class TestLookupCaching:
    def move(self, monkeypatch):
        monkeypatch.setattr(tasks, "get_role_in_project", lambda uid, pid: "leader")
        monkeypatch.setattr(tasks, "_get_task_or_404", lambda tid: dict(OLD_TASK))
        monkeypatch.setattr(tasks, "supabase", FakeSupabase(tasks=[dict(OLD_TASK)]))
        with request_ctx(json_body={"column_id": "col-done"}):
            g.user = ACTOR
            _, status = tasks.update_task.__wrapped__("project-1", "task-1")
        assert status == 200

    def test_first_move_looks_up_names_then_logs(self, monkeypatch, log_db):
        self.move(monkeypatch)
        assert [q.table_name for q in log_db.queries] == ["columns", "profiles", "task_activity"]

    def test_second_move_only_writes_the_log_row(self, monkeypatch, log_db):
        self.move(monkeypatch)
        log_db.queries.clear()
        self.move(monkeypatch)
        assert [q.table_name for q in log_db.queries] == ["task_activity"]
        assert log_db.inserted("task_activity")[0]["details"] == {"from_column": "To Do", "to_column": "Done"}
        assert log_db.inserted("task_activity")[0]["actor_name"] == "Ada Lovelace"

    def test_cache_expires(self, monkeypatch, log_db):
        clock = [1000.0]
        monkeypatch.setattr(activity, "_now", lambda: clock[0])
        self.move(monkeypatch)
        log_db.queries.clear()
        clock[0] += activity.CACHE_TTL_SECONDS + 1
        self.move(monkeypatch)
        assert [q.table_name for q in log_db.queries] == ["columns", "profiles", "task_activity"]

    def test_failed_actor_lookup_is_not_cached(self, monkeypatch):
        class Boom:
            def table(self, name):
                raise RuntimeError("down")
        monkeypatch.setattr(activity, "supabase", Boom())
        assert activity.get_actor_name(ACTOR) == "ada@x.com"
        fake = FakeSupabase(profiles=[{"id": "user-1", "full_name": "Ada Lovelace [Developer]", "email": "ada@x.com"}])
        monkeypatch.setattr(activity, "supabase", fake)
        assert activity.get_actor_name(ACTOR) == "Ada Lovelace"

    def test_only_uncached_columns_are_fetched(self, monkeypatch):
        # like the real database, each fake answers only for the ids it is asked about
        first = FakeSupabase(columns=[{"id": "col-todo", "name": "To Do"}])
        monkeypatch.setattr(activity, "supabase", first)
        activity.column_names(["col-todo"])

        second = FakeSupabase(columns=[{"id": "col-done", "name": "Done"}])
        monkeypatch.setattr(activity, "supabase", second)
        assert activity.column_names(["col-todo", "col-done"]) == {"col-todo": "To Do", "col-done": "Done"}
        assert second.queries[0].args_of("in_") == [(("id", ["col-done"]), {})]


# ---------------------------------------------------------------------------
# things that did NOT change must not be reported
# ---------------------------------------------------------------------------
class TestUnchangedItemsAreIgnored:
    def test_unchanged_subtasks_and_comments_alongside_a_real_change(self):
        shared = dict(checklist=[{"t": "a", "d": False}], comments=[{"id": "1", "text": "hi"}])
        events = diff_desc(pack(desc="x", **shared), pack(desc="y", **shared))
        assert actions(events) == [DESCRIPTION_CHANGED]


class TestProfileNames:
    def test_no_ids_means_no_query(self, log_db):
        assert activity.profile_names([]) == {}
        assert activity.profile_names([None]) == {}
        assert log_db.queries == []

    def test_role_suffix_is_stripped(self, log_db):
        assert activity.profile_names(["user-1"]) == {"user-1": "Ada Lovelace"}