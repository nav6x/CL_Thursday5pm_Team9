from flask import Blueprint, request, jsonify, g
from config import supabase, maybe_one   
from auth_utils import login_required, require_role

projects_bp = Blueprint("projects", __name__, url_prefix="/api/projects")

# Expects:
#   projects         — id, name, created_by, created_at
#   project_members  — id, project_id, user_id, role ('leader' | 'developer')
#   columns          — id, project_id, name, position
# Swap the table/column names in the queries below to match your own schema.


ROLE_MAP = {
    "leader": ("leader", "Project Leader"),
    "project_leader": ("leader", "Project Leader"),
    "scrum_master": ("leader", "Scrum Master"),
    "product_owner": ("leader", "Product Owner"),
    "developer": ("developer", "Developer"),
    "qa_engineer": ("developer", "QA Engineer"),
}


def extract_agile_role(full_name, default_db_role):
    if not full_name:
        return "", "Project Leader" if default_db_role == "leader" else "Developer"
    if "[" in full_name and full_name.endswith("]"):
        idx = full_name.rfind("[")
        role_label = full_name[idx + 1:-1].strip()
        clean_name = full_name[:idx].strip()
        return clean_name, role_label
    return full_name, "Project Leader" if default_db_role == "leader" else "Developer"


@projects_bp.route("", methods=["GET"])
@login_required
def list_my_projects():
    memberships = (
        supabase.table("project_members")
        .select("role, projects(id, name, created_at)")
        .eq("user_id", g.user.id)
        .execute()
    )
    # safe lookup — falls back to {} if the user has no profile row
    my_profile = maybe_one(supabase.table("profiles").select("full_name").eq("id", g.user.id)) or {}
    _, my_agile_role = extract_agile_role(my_profile.get("full_name") or "", "developer")

    projects = [
        {**m["projects"], "my_role": m.get("role", "developer"), "my_agile_role": my_agile_role}
        for m in (memberships.data or [])
        if m.get("projects")
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
        {"project_id": project["id"], "name": col_name, "position": i}
        for i, col_name in enumerate(default_columns)   
    ]).execute()

    return jsonify({**project, "my_role": "leader", "my_agile_role": "Project Leader"}), 201


@projects_bp.route("/<project_id>/members", methods=["GET"])
@login_required
def list_members(project_id):
    result = (
        supabase.table("project_members")
        .select("role, profiles(id, full_name, email)")
        .eq("project_id", project_id)
        .execute()
    )
    formatted = []
    for item in (result.data or []):
        p = item.get("profiles") or {}
        clean_name, agile_role = extract_agile_role(p.get("full_name") or "", item.get("role", "developer"))
        formatted.append({
            "role": item.get("role", "developer"),
            "agile_role": agile_role,
            "profiles": {
                "id": p.get("id"),
                "full_name": clean_name or p.get("email", ""),
                "email": p.get("email", ""),
            }
        })
    return jsonify(formatted), 200


@projects_bp.route("/<project_id>/members", methods=["POST"])
@login_required
@require_role("leader")
def add_member(project_id):
    body = request.get_json(force=True)
    raw_role = body.get("role", "developer")

    if raw_role not in ROLE_MAP:
        return jsonify({"error": "role must be one of: " + ", ".join(ROLE_MAP.keys())}), 400

    db_role, display_role = ROLE_MAP[raw_role]

    user_id = body.get("user_id")
    if user_id:
        
        profile = maybe_one(supabase.table("profiles").select("id, full_name, email").eq("id", user_id))
    else:
        email = body.get("email", "").strip().lower()
        if not email:
            return jsonify({"error": "email or user_id required"}), 400
        profile = maybe_one(supabase.table("profiles").select("id, full_name, email").eq("email", email))

    if not profile:
        return jsonify({"error": "No user found with that email — they need to sign up first"}), 404

    target_id = profile["id"]   
    existing = maybe_one(      
        supabase.table("project_members")
        .select("id")
        .eq("project_id", project_id)
        .eq("user_id", target_id)
    )
    if existing:   
        return jsonify({"message": "User is already a member of this project"}), 200

    supabase.table("project_members").insert({
        "project_id": project_id,
        "user_id": target_id,
        "role": db_role,
    }).execute()

    current_name = profile.get("full_name") or ""
    clean_name = current_name.split("[")[0].strip() if current_name else (profile.get("email") or "")
    new_name = f"{clean_name} [{display_role}]".strip()
    try:
        supabase.table("profiles").update({"full_name": new_name}).eq("id", target_id).execute()
    except Exception:
        pass

    return jsonify({"message": "Member added", "role": db_role, "agile_role": display_role}), 201


@projects_bp.route("/<project_id>/members/all", methods=["POST"])
@login_required
@require_role("leader")
def add_all_members(project_id):
    all_users = supabase.table("profiles").select("id").execute().data or []
    for u in all_users:
        existing = maybe_one(   
            supabase.table("project_members")
            .select("id")
            .eq("project_id", project_id)
            .eq("user_id", u["id"])
        )
        if not existing:
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
    raw_role = body.get("role", "developer")

    if raw_role not in ROLE_MAP:
        return jsonify({"error": "role must be one of: " + ", ".join(ROLE_MAP.keys())}), 400

    db_role, display_role = ROLE_MAP[raw_role]

    result = (
        supabase.table("project_members")
        .update({"role": db_role})
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Member not found"}), 404

    # safe lookup
    target_profile = maybe_one(supabase.table("profiles").select("full_name").eq("id", user_id))
    if target_profile:
        current_name = target_profile.get("full_name") or ""
        clean_name = current_name.split("[")[0].strip() if current_name else ""
        if clean_name:
            new_name = f"{clean_name} [{display_role}]".strip()
            try:
                supabase.table("profiles").update({"full_name": new_name}).eq("id", user_id).execute()
            except Exception:
                pass

    return jsonify({"role": db_role, "agile_role": display_role}), 200


@projects_bp.route("/<project_id>/members/<user_id>", methods=["DELETE"])
@login_required
@require_role("leader")
def remove_member(project_id, user_id):
    if user_id == g.user.id:
        return jsonify({"error": "Cannot remove yourself as project leader"}), 400

    supabase.table("project_members").delete().eq("project_id", project_id).eq("user_id", user_id).execute()
    return jsonify({"message": "Member removed"}), 200