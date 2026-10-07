from flask import Blueprint, request, jsonify, g
from config import supabase
from auth_utils import login_required, get_role_in_project

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/projects/<project_id>/tasks")

# Expects:
#   tasks           — id, project_id, column_id, name, description, priority
#                     ('high'|'medium'|'low'), story_points (int 0-10),
#                     created_by, position, created_at
#   task_assignees  — task_id, user_id (composite key, many-to-many join table)


def _is_assignee(task_id, user_id):
    result = (
        supabase.table("task_assignees")
        .select("user_id")
        .eq("task_id", task_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data is not None


def _get_task_or_404(task_id):
    result = supabase.table("tasks").select("*").eq("id", task_id).maybe_single().execute()
    return result.data


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
    for row in assignee_rows.data:
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
    if assignee_ids:
        supabase.table("task_assignees").insert([
            {"task_id": task["id"], "user_id": uid} for uid in assignee_ids
        ]).execute()

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

    result = supabase.table("tasks").update(updates).eq("id", task_id).execute()
    return jsonify(result.data[0]), 200


@tasks_bp.route("/<task_id>", methods=["DELETE"])
@login_required
def delete_task(project_id, task_id):
    role = get_role_in_project(g.user.id, project_id)
    if role != "leader":
        return jsonify({"error": "Only a Project Leader can delete tasks"}), 403

    supabase.table("tasks").delete().eq("id", task_id).execute()
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

    supabase.table("task_assignees").delete().eq("task_id", task_id).execute()
    if assignee_ids:
        supabase.table("task_assignees").insert([
            {"task_id": task_id, "user_id": uid} for uid in assignee_ids
        ]).execute()

    return jsonify({"message": "Assignees updated"}), 200
