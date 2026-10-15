"""Helpers for creating in-app notifications.

Every function here is deliberately failure-tolerant: a problem while writing
a notification must never make the real action (creating a task, moving a
card, ...) fail, so errors are logged and swallowed.
"""
import json
import logging
import re

from config import supabase, maybe_one

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- names

def clean_name(full_name, fallback=""):
    """profiles.full_name stores the agile role as 'Jamie Chen [Developer]'.
    Strip that suffix so messages read 'Jamie Chen moved ...'."""
    name = (full_name or "").split("[")[0].strip()
    return name or fallback or "Someone"


def display_name(user_id):
    try:
        profile = maybe_one(
            supabase.table("profiles").select("full_name, email").eq("id", user_id)
        )
    except Exception:
        profile = None
    if not profile:
        return "Someone"
    return clean_name(profile.get("full_name"), (profile.get("email") or "").split("@")[0])


def project_name(project_id):
    try:
        project = maybe_one(supabase.table("projects").select("name").eq("id", project_id))
    except Exception:
        project = None
    return (project or {}).get("name") or "a project"


# ------------------------------------------------------------ creating

def create_notifications(user_ids, actor_id, type_, message, project_id=None, task_id=None):
    """Insert one notification per recipient. The person who performed the
    action never notifies themselves."""
    recipients = [u for u in dict.fromkeys(user_ids or []) if u and u != actor_id]
    if not recipients:
        return
    rows = [
        {
            "user_id": uid,
            "actor_id": actor_id,
            "project_id": project_id,
            "task_id": task_id,
            "type": type_,
            "message": message,
        }
        for uid in recipients
    ]
    try:
        supabase.table("notifications").insert(rows).execute()
    except Exception:
        log.warning("Could not write notifications (%s)", type_, exc_info=True)


def project_member_ids(project_id):
    try:
        rows = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", project_id)
            .execute()
            .data
            or []
        )
        return [r["user_id"] for r in rows]
    except Exception:
        return []


def notify_project(project_id, actor_id, type_, message, task_id=None, exclude=()):
    """Notify every member of a project except the actor (and `exclude`)."""
    try:
        skip = set(exclude or ())
        ids = [u for u in project_member_ids(project_id) if u not in skip]
    except Exception:
        log.warning("Could not load project members for notification", exc_info=True)
        return
    create_notifications(ids, actor_id, type_, message, project_id, task_id)


# ----------------------------------------------- description change diff
# Tags, due date, subtasks and comments are packed into tasks.description by
# the frontend (see parseTaskDescription / packTaskDescription in board.js).
# Without looking inside, every subtask tick or comment would look like a
# generic "task updated". These helpers mirror the JS parser.

_META_RE = re.compile(r"^\[meta:(\{[\s\S]*?\})\]---([\s\S]*)$")
_LEGACY_TAGS_RE = re.compile(r"^\[tags:([^\]]*)\]\s*([\s\S]*)$")


def parse_description(raw):
    raw = raw or ""
    match = _META_RE.match(raw)
    if match:
        try:
            meta = json.loads(match.group(1))
            if isinstance(meta, dict):
                return meta, match.group(2).strip()
        except ValueError:
            pass
    legacy = _LEGACY_TAGS_RE.match(raw)
    if legacy:
        tags = [t.strip() for t in legacy.group(1).split(",") if t.strip()]
        return {"tags": tags}, legacy.group(2).strip()
    return {}, raw.strip()


def _as_list(value):
    return value if isinstance(value, list) else []


def diff_description(old_raw, new_raw):
    """Returns (content_changed, new_comments).

    content_changed is True when the visible text, tags, due date or subtask
    wording changed. Ticking a subtask on/off and deleting a comment are NOT
    counted, so they stay quiet.
    """
    old_meta, old_text = parse_description(old_raw)
    new_meta, new_text = parse_description(new_raw)

    old_comment_ids = {
        c.get("id") for c in _as_list(old_meta.get("comments")) if isinstance(c, dict)
    }
    new_comments = [
        c for c in _as_list(new_meta.get("comments"))
        if isinstance(c, dict) and c.get("id") not in old_comment_ids
    ]

    def labels(meta):
        return [i.get("t") for i in _as_list(meta.get("checklist")) if isinstance(i, dict)]

    content_changed = (
        old_text != new_text
        or sorted(map(str, _as_list(old_meta.get("tags")))) != sorted(map(str, _as_list(new_meta.get("tags"))))
        or (old_meta.get("due") or "") != (new_meta.get("due") or "")
        or labels(old_meta) != labels(new_meta)
    )
    return content_changed, new_comments
