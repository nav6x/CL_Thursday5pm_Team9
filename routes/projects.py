from flask import Blueprint, request, jsonify, g
from config import supabase
from auth_utils import login_required, require_role

projects_bp = Blueprint("projects", __name__, url_prefix="/api/projects")

# Expects:
#   projects         — id, name, created_by, created_at
#   project_members  — id, project_id, user_id, role ('leader' | 'developer')
#   columns          — id, project_id, name, position
# Swap the table/column names in the queries below to match your own schema.


@projects_bp.route("", methods=["GET"])
@login_required
def list_my_projects():
    """Every project the logged-in user belongs to, with their role in each."""
    memberships = (
        supabase.table("project_members")
        .select("role, projects(id, name, created_at)")
        .eq("user_id", g.user.id)
        .execute()
    )
    projects = [
        {**m["projects"], "my_role": m["role"]}
        for m in memberships.data
    ]
    return jsonify(projects), 200


@projects_bp.route("", methods=["POST"])
@login_required
def create_project():
    """Anyone can start a new project. The creator automatically
    becomes its Project Leader — someone has to be, and it should
    default to whoever set it up."""
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    project = supabase.table("projects").insert({
        "name": name,
        "created_by": g.user.id,
    }).execute().data[0]

    supabase.table("project_members").insert({
        "project_id": project["id"],
        "user_id": g.user.id,
        "role": "leader",
    }).execute()

    # Give new projects a sensible default set of columns to start from
    # — the client can still add/rename/delete freely afterward.
    default_columns = ["To Do", "In Progress", "Done"]
    supabase.table("columns").insert([
        {"project_id": project["id"], "name": name, "position": i}
        for i, name in enumerate(default_columns)
    ]).execute()

    return jsonify(project), 201


@projects_bp.route("/<project_id>/members", methods=["GET"])
@login_required
def list_members(project_id):
    result = (
        supabase.table("project_members")
        .select("role, profiles(id, full_name, email)")
        .eq("project_id", project_id)
        .execute()
    )
    return jsonify(result.data), 200


@projects_bp.route("/<project_id>/members", methods=["POST"])
@login_required
@require_role("leader")
def add_member(project_id):
    body = request.get_json(force=True)
    role = body.get("role", "developer")

    if role not in ("leader", "developer"):
        return jsonify({"error": "role must be 'leader' or 'developer'"}), 400

    user_id = body.get("user_id")
    if user_id:
        profile = supabase.table("profiles").select("id").eq("id", user_id).maybe_single().execute()
    else:
        email = body.get("email", "").strip().lower()
        if not email:
            return jsonify({"error": "email or user_id required"}), 400
        profile = supabase.table("profiles").select("id").eq("email", email).maybe_single().execute()

    if not profile.data:
        return jsonify({"error": "No user found with that email — they need to sign up first"}), 404

    target_id = profile.data["id"]
    existing = (
        supabase.table("project_members")
        .select("id")
        .eq("project_id", project_id)
        .eq("user_id", target_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        return jsonify({"message": "User is already a member of this project"}), 200

    supabase.table("project_members").insert({
        "project_id": project_id,
        "user_id": target_id,
        "role": role,
    }).execute()

    return jsonify({"message": "Member added"}), 201


@projects_bp.route("/<project_id>/members/all", methods=["POST"])
@login_required
@require_role("leader")
def add_all_members(project_id):
    all_users = supabase.table("profiles").select("id").execute().data or []
    for u in all_users:
        existing = (
            supabase.table("project_members")
            .select("id")
            .eq("project_id", project_id)
            .eq("user_id", u["id"])
            .maybe_single()
            .execute()
        )
        if not existing.data:
            supabase.table("project_members").insert({
                "project_id": project_id,
                "user_id": u["id"],
                "role": "developer",
            }).execute()

    return jsonify({"message": "All workspace users added to project"}), 200


@projects_bp.route("/<project_id>", methods=["PATCH"])
@login_required
@require_role("leader")
def update_project(project_id):
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    result = supabase.table("projects").update({"name": name}).eq("id", project_id).execute()
    if not result.data:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(result.data[0]), 200


@projects_bp.route("/<project_id>", methods=["DELETE"])
@login_required
@require_role("leader")
def delete_project(project_id):
    supabase.table("projects").delete().eq("id", project_id).execute()
    return jsonify({"message": "Project deleted"}), 200


@projects_bp.route("/<project_id>/members/<user_id>", methods=["PATCH"])
@login_required
@require_role("leader")
def update_member(project_id, user_id):
    body = request.get_json(force=True)
    role = body.get("role")
    if role not in ("leader", "developer"):
        return jsonify({"error": "role must be 'leader' or 'developer'"}), 400

    result = (
        supabase.table("project_members")
        .update({"role": role})
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Member not found"}), 404
    return jsonify(result.data[0]), 200


@projects_bp.route("/<project_id>/members/<user_id>", methods=["DELETE"])
@login_required
@require_role("leader")
def remove_member(project_id, user_id):
    if user_id == g.user.id:
        return jsonify({"error": "Cannot remove yourself as project leader"}), 400

    supabase.table("project_members").delete().eq("project_id", project_id).eq("user_id", user_id).execute()
    return jsonify({"message": "Member removed"}), 200
