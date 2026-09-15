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
    """Only a Project Leader can add teammates to the project."""
    body = request.get_json(force=True)
    email = body.get("email", "").strip().lower()
    role = body.get("role", "developer")

    if role not in ("leader", "developer"):
        return jsonify({"error": "role must be 'leader' or 'developer'"}), 400

    profile = (
        supabase.table("profiles").select("id").eq("email", email).maybe_single().execute()
    )
    if not profile.data:
        return jsonify({"error": "No user found with that email — they need to sign up first"}), 404

    supabase.table("project_members").insert({
        "project_id": project_id,
        "user_id": profile.data["id"],
        "role": role,
    }).execute()

    return jsonify({"message": "Member added"}), 201
