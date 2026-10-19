from flask import Blueprint, request, jsonify, g
from config import supabase, maybe_one
from auth_utils import login_required, get_role_in_project
from notifications_utils import create_notifications, notify_project, diff_description, display_name, project_name
import activity

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/projects/<project_id>/tasks")


def _is_assignee(task_id, user_id):
    result = maybe_one(
        supabase.table("task_assignees")
        .select("user_id")
        .eq("task_id", task_id)
        .eq("user_id", user_id)
    )
    return result is not None


def _get_task_or_404(task_id):
    return maybe_one(supabase.table("tasks").select("*").eq("id", task_id))


def _safely(fn, default=None):
    try:
        return fn()
    except Exception:
        activity.logger.exception("Activity logging step failed")
        return default


def _log(project_id, task_id, task_name, events):
    """Record events as the current user. Never raises."""
    if not events:
        return
    actor_name = _safely(lambda: activity.get_actor_name(g.user), "Someone")
    activity.record_events(project_id, task_id, task_name, g.user.id, actor_name, events)

@tasks_bp.route("", methods=["GET"])
@login_required
def list_tasks(project_id):
    """All tasks for a project, each with its assignees attached,
    ready for the board to group by column_id on the frontend."""
    tasks = supabase.table("tasks").select("*").eq("project_id", project_id).order("position").execute().data

    assignee_rows = (
        supabase.table("task_assignees")
        .select("task_id, profiles(id, full_name)")
        .in_("task_id", [t["id"] for t in tasks] or ["00000000-0000-0000-0000-000000000000"])
        .execute()
    )
    assignees_by_task = {}
    for row in (assignee_rows.data or []):
        if row.get("profiles"):
            assignees_by_task.setdefault(row["task_id"], []).append(row["profiles"])

    for task in tasks:
        task["assignees"] = assignees_by_task.get(task["id"], [])

    return jsonify(tasks), 200


@tasks_bp.route("", methods=["POST"])
@login_required
def create_task(project_id):
    """Both Leaders and Developers can create tasks — anyone on the
    team should be able to add a sticky note to the board."""
    role = get_role_in_project(g.user.id, project_id)
    if role is None:
        return jsonify({"error": "You are not a member of this project"}), 403

    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    column_id = body.get("column_id")
    if not name or not column_id:
        return jsonify({"error": "name and column_id are required"}), 400

    story_points = body.get("story_points", 0)
    if not isinstance(story_points, int) or not (0 <= story_points <= 10):
        return jsonify({"error": "story_points must be an integer from 0 to 10"}), 400

    task = supabase.table("tasks").insert({
        "project_id": project_id,
        "column_id": column_id,
        "name": name,
        "description": body.get("description", ""),
        "priority": body.get("priority", "medium"),
        "story_points": story_points,
        "created_by": g.user.id,
    }).execute().data[0]

    assignee_ids = body.get("assignee_ids", [])
    valid_uids = list(dict.fromkeys([uid for uid in assignee_ids if uid]))
    if valid_uids:
        supabase.table("task_assignees").insert([
            {"task_id": task["id"], "user_id": uid} for uid in valid_uids
        ]).execute()

    column_name = _safely(lambda: activity.column_names([column_id]).get(column_id))
    _log(project_id, task["id"], task["name"], [activity.event(activity.TASK_CREATED, column=column_name)])

    try:
        actor = display_name(g.user.id)
        pname = project_name(project_id)
        notify_project(
            project_id, g.user.id, "task_created",
            f'{actor} created task "{name}" in "{pname}"',
            task_id=task["id"]
        )
        if valid_uids:
            create_notifications(
                valid_uids, g.user.id, "task_assigned",
                f'{actor} assigned you to "{name}"',
                project_id=project_id, task_id=task["id"]
            )
    except Exception:
        pass

    return jsonify(task), 201


@tasks_bp.route("/<task_id>", methods=["PATCH"])
@login_required
def update_task(project_id, task_id):
    """Permission split for edits:
    - Leader: can edit anything on any task.
    - Developer: can only move a task (column_id) or edit it if
      they created it or are assigned to it — this is what lets
      'whoever's working on it' update status without needing the
      Leader to do it for them, without letting a Developer rewrite
      someone else's unrelated task.
    """
    task = _get_task_or_404(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    role = get_role_in_project(g.user.id, project_id)
    if role is None:
        return jsonify({"error": "You are not a member of this project"}), 403

    body = request.get_json(force=True)
    is_owner_or_assignee = (
        task["created_by"] == g.user.id or _is_assignee(task_id, g.user.id)
    )
    is_move_only = set(body.keys()) <= {"column_id", "position"}

    if role != "leader" and not (is_move_only or is_owner_or_assignee):
        return jsonify({
            "error": "Developers can only move tasks, or edit tasks they created or are assigned to"
        }), 403

    updates = {}
    for field in ("name", "description", "priority", "story_points", "column_id", "position"):
        if field in body:
            updates[field] = body[field]

    if "story_points" in updates:
        sp = updates["story_points"]
        if not isinstance(sp, int) or not (0 <= sp <= 10):
            return jsonify({"error": "story_points must be an integer from 0 to 10"}), 400

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    events = _safely(lambda: activity.diff_task_update(
        task,
        updates,
        activity.column_names([task.get("column_id"), updates.get("column_id")]) if "column_id" in updates else None,
    ), [])

    result = supabase.table("tasks").update(updates).eq("id", task_id).execute()

    _log(project_id, task_id, updates.get("name", task.get("name")), events)

    try:
        actor = display_name(g.user.id)
        task_name = task.get("name") or updates.get("name") or "a task"
        if "column_id" in updates and updates["column_id"] != task.get("column_id"):
            notify_project(
                project_id, g.user.id, "task_moved",
                f'{actor} moved "{task_name}"',
                task_id=task_id
            )
        if "description" in updates:
            content_changed, new_comments = diff_description(task.get("description", ""), updates["description"])
            for comment in new_comments:
                notify_project(
                    project_id, g.user.id, "task_commented",
                    f'{actor} commented on "{task_name}"',
                    task_id=task_id
                )
            if content_changed:
                notify_project(
                    project_id, g.user.id, "task_updated",
                    f'{actor} updated "{task_name}"',
                    task_id=task_id
                )
        elif any(k in updates for k in ("name", "priority", "story_points")):
            notify_project(
                project_id, g.user.id, "task_updated",
                f'{actor} updated "{task_name}"',
                task_id=task_id
            )
    except Exception:
        pass

    return jsonify(result.data[0]), 200


@tasks_bp.route("/<task_id>", methods=["DELETE"])
@login_required
def delete_task(project_id, task_id):
    role = get_role_in_project(g.user.id, project_id)
    if role != "leader":
        return jsonify({"error": "Only a Project Leader can delete tasks"}), 403

    task = _get_task_or_404(task_id)
    task_name = task.get("name") if task else None

    supabase.table("tasks").delete().eq("id", task_id).execute()

    if task_name is not None:
        _log(project_id, task_id, task_name, [activity.event(activity.TASK_DELETED)])

    try:
        if task:
            actor = display_name(g.user.id)
            notify_project(
                project_id, g.user.id, "task_deleted",
                f'{actor} deleted task "{task.get("name")}"',
                task_id=task_id
            )
    except Exception:
        pass

    return jsonify({"message": "Task deleted"}), 200


@tasks_bp.route("/<task_id>/assignees", methods=["PUT"])
@login_required
def set_assignees(project_id, task_id):
    """Replaces the full assignee list for a task. Restricted to
    Leaders, since deciding who works on what is a lead call."""
    role = get_role_in_project(g.user.id, project_id)
    if role != "leader":
        return jsonify({"error": "Only a Project Leader can assign tasks"}), 403

    body = request.get_json(force=True)
    assignee_ids = body.get("assignee_ids", [])
    valid_uids = list(dict.fromkeys([uid for uid in assignee_ids if uid]))

    old_ids = _safely(lambda: activity.assignee_ids(task_id))

    try:
        supabase.table("task_assignees").delete().eq("task_id", task_id).execute()
        if valid_uids:
            supabase.table("task_assignees").insert([
                {"task_id": task_id, "user_id": uid} for uid in valid_uids
            ]).execute()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if old_ids is not None:
        def _log_assignee_change():
            names = activity.profile_names(list(old_ids) + valid_uids)
            events = activity.diff_assignees(
                {u: names.get(u, "Unknown user") for u in old_ids},
                {u: names.get(u, "Unknown user") for u in valid_uids},
            )
            _log(project_id, task_id, activity.task_name(task_id), events)
        _safely(_log_assignee_change)

    return jsonify({"message": "Assignees updated"}), 200

@tasks_bp.route("/<task_id>/activity", methods=["GET"])
@login_required
def list_task_activity(project_id, task_id):
    """Newest-first history of changes to one task. Any project member can
    read it. Rows are matched on BOTH project_id and task_id, so a member of
    project A can't read project B's history by swapping ids in the URL.
    Query params: limit (1-200, default 50), offset (default 0)."""
    role = get_role_in_project(g.user.id, project_id)
    if role is None:
        return jsonify({"error": "You are not a member of this project"}), 403

    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    rows = (
        supabase.table("task_activity")
        .select("id, task_id, actor_id, actor_name, action, details, created_at")
        .eq("project_id", project_id)
        .eq("task_id", task_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data
    ) or []
    return jsonify(rows), 200
