"""Task activity / history log.

Every change to a task is recorded as a row in `task_activity` (see
supabase/task_activity.sql). The routes in routes/tasks.py call into this module;
nothing here is exposed over HTTP directly.

Two rules shape this module:

1. Logging must never break the action being logged. `record_events` swallows
   and logs any error, so a missing table or a Supabase hiccup costs us a log
   line, not a failed task save.
2. The frontend packs tags, due date, subtasks and comments into the task's
   `description` string (see parseTaskDescription in static/js/board.js). To
   report "due date changed" or "comment added" rather than just "description
   edited", `parse_description` mirrors that format and `diff_task_update`
   compares the parsed pieces.
"""
import json
import logging
import re

from config import supabase, maybe_one

logger = logging.getLogger(__name__)

# --- action names (stored in task_activity.action) --------------------------
TASK_CREATED = "task_created"
TASK_DELETED = "task_deleted"
TASK_RENAMED = "task_renamed"
DESCRIPTION_CHANGED = "description_changed"
PRIORITY_CHANGED = "priority_changed"
STORY_POINTS_CHANGED = "story_points_changed"
TASK_MOVED = "task_moved"
TAGS_CHANGED = "tags_changed"
DUE_DATE_CHANGED = "due_date_changed"
SUBTASK_ADDED = "subtask_added"
SUBTASK_REMOVED = "subtask_removed"
SUBTASK_COMPLETED = "subtask_completed"
SUBTASK_REOPENED = "subtask_reopened"
COMMENT_ADDED = "comment_added"
COMMENT_DELETED = "comment_deleted"
ASSIGNEES_CHANGED = "assignees_changed"

TEXT_PREVIEW_LEN = 140

_META_RE = re.compile(r"^\[meta:(\{[\s\S]*?\})\]---([\s\S]*)$")
_TAGS_RE = re.compile(r"^\[tags:([^\]]*)\]\s*([\s\S]*)$")


def event(action, **details):
    return {"action": action, "details": details}


def _preview(text):
    text = (text or "").strip()
    if len(text) > TEXT_PREVIEW_LEN:
        return text[:TEXT_PREVIEW_LEN].rstrip() + "…"
    return text


def clean_display_name(full_name, email=""):
    """profiles.full_name carries a trailing '[Role]' (see routes/projects.py);
    strip it so the log shows just the person's name."""
    name = (full_name or "").split("[")[0].strip()
    return name or (email or "").strip() or "Someone"


def get_actor_name(user):
    """Best-effort display name for the authenticated user (g.user)."""
    email = getattr(user, "email", "") or ""
    try:
        profile = maybe_one(
            supabase.table("profiles").select("full_name").eq("id", user.id)
        ) or {}
        return clean_display_name(profile.get("full_name"), email)
    except Exception:
        return clean_display_name("", email)


def parse_description(raw):
    """Python port of parseTaskDescription() in static/js/board.js."""
    empty = {"tags": [], "due": "", "checklist": [], "comments": [], "desc": ""}
    if not raw:
        return empty

    m = _META_RE.match(raw)
    if m:
        try:
            meta = json.loads(m.group(1))
            return {
                "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
                "due": meta.get("due") or "",
                "checklist": meta.get("checklist") if isinstance(meta.get("checklist"), list) else [],
                "comments": meta.get("comments") if isinstance(meta.get("comments"), list) else [],
                "desc": (m.group(2) or "").strip(),
            }
        except (ValueError, AttributeError):
            pass

    m = _TAGS_RE.match(raw)
    if m:
        tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
        return {**empty, "tags": tags, "desc": m.group(2).strip()}

    return {**empty, "desc": raw.strip()}


def _diff_description(old_raw, new_raw):
    old, new = parse_description(old_raw), parse_description(new_raw)
    events = []

    if old["desc"] != new["desc"]:
        events.append(event(DESCRIPTION_CHANGED))

    old_tags = {str(t).lower(): str(t) for t in old["tags"]}
    new_tags = {str(t).lower(): str(t) for t in new["tags"]}
    added = [new_tags[k] for k in new_tags if k not in old_tags]
    removed = [old_tags[k] for k in old_tags if k not in new_tags]
    if added or removed:
        events.append(event(TAGS_CHANGED, added=added, removed=removed))

    if (old["due"] or "") != (new["due"] or ""):
        events.append(event(DUE_DATE_CHANGED, **{"from": old["due"] or None, "to": new["due"] or None}))

    old_items = {str(i.get("t", "")): bool(i.get("d")) for i in old["checklist"] if isinstance(i, dict)}
    new_items = {str(i.get("t", "")): bool(i.get("d")) for i in new["checklist"] if isinstance(i, dict)}
    for text, done in new_items.items():
        if text not in old_items:
            events.append(event(SUBTASK_ADDED, text=_preview(text)))
        elif done != old_items[text]:
            events.append(event(SUBTASK_COMPLETED if done else SUBTASK_REOPENED, text=_preview(text)))
    for text in old_items:
        if text not in new_items:
            events.append(event(SUBTASK_REMOVED, text=_preview(text)))

    old_comments = {str(c.get("id")): c for c in old["comments"] if isinstance(c, dict)}
    new_comments = {str(c.get("id")): c for c in new["comments"] if isinstance(c, dict)}
    for cid, c in new_comments.items():
        if cid not in old_comments:
            events.append(event(COMMENT_ADDED, text=_preview(c.get("text"))))
    for cid, c in old_comments.items():
        if cid not in new_comments:
            events.append(event(COMMENT_DELETED, text=_preview(c.get("text")), author=c.get("user_name") or None))

    return events


def diff_task_update(old_task, updates, column_names=None):
    """Compare a task row with the PATCH `updates` about to be applied and
    return a list of events describing what actually changed. Fields that are
    sent but unchanged produce no event, and `position` alone is ignored (it
    changes on every drag without meaning anything to a reader).

    column_names: {column_id: name}, used to word "moved" events.
    """
    column_names = column_names or {}
    events = []

    if "name" in updates and updates["name"] != old_task.get("name"):
        events.append(event(TASK_RENAMED, **{"from": old_task.get("name"), "to": updates["name"]}))

    if "priority" in updates and updates["priority"] != old_task.get("priority"):
        events.append(event(PRIORITY_CHANGED, **{"from": old_task.get("priority"), "to": updates["priority"]}))

    if "story_points" in updates and updates["story_points"] != old_task.get("story_points"):
        events.append(event(STORY_POINTS_CHANGED, **{"from": old_task.get("story_points"), "to": updates["story_points"]}))

    if "column_id" in updates and updates["column_id"] != old_task.get("column_id"):
        events.append(event(
            TASK_MOVED,
            from_column=column_names.get(old_task.get("column_id")),
            to_column=column_names.get(updates["column_id"]),
        ))

    if "description" in updates and updates["description"] != old_task.get("description"):
        events.extend(_diff_description(old_task.get("description"), updates["description"]))

    return events


def diff_assignees(old_people, new_people):
    """old_people/new_people: {user_id: display_name}. Returns [] or one event."""
    added = [new_people[uid] for uid in new_people if uid not in old_people]
    removed = [old_people[uid] for uid in old_people if uid not in new_people]
    if not (added or removed):
        return []
    return [event(ASSIGNEES_CHANGED, added=added, removed=removed)]


# --- read helpers (all DB access for the log lives in this module) ----------

def column_names(column_ids):
    """{column_id: name} for the given ids."""
    ids = [c for c in dict.fromkeys(column_ids) if c]
    if not ids:
        return {}
    rows = supabase.table("columns").select("id, name").in_("id", ids).execute().data or []
    return {r["id"]: r["name"] for r in rows}


def assignee_ids(task_id):
    rows = supabase.table("task_assignees").select("user_id").eq("task_id", task_id).execute().data or []
    return [r["user_id"] for r in rows]


def profile_names(user_ids):
    """{user_id: display name} for the given ids."""
    ids = [u for u in dict.fromkeys(user_ids) if u]
    if not ids:
        return {}
    rows = supabase.table("profiles").select("id, full_name, email").in_("id", ids).execute().data or []
    return {r["id"]: clean_display_name(r.get("full_name"), r.get("email")) for r in rows}


def task_name(task_id):
    """Current name of a task, or None if it doesn't exist."""
    row = maybe_one(supabase.table("tasks").select("name").eq("id", task_id))
    return row.get("name") if row else None


def record_events(project_id, task_id, task_name, actor_id, actor_name, events):
    """Insert one task_activity row per event. Never raises."""
    if not events:
        return
    try:
        supabase.table("task_activity").insert([
            {
                "project_id": project_id,
                "task_id": task_id,
                "task_name": task_name,
                "actor_id": actor_id,
                "actor_name": actor_name,
                "action": e["action"],
                "details": e.get("details") or {},
            }
            for e in events
        ]).execute()
    except Exception:
        logger.exception("Could not record task activity (task %s)", task_id)