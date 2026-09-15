from flask import Blueprint, request, jsonify
from config import supabase
from auth_utils import login_required, require_role

columns_bp = Blueprint("columns", __name__, url_prefix="/api/projects/<project_id>/columns")

# Expects a `columns` table: id, project_id, name, position (int, for ordering).


@columns_bp.route("", methods=["GET"])
@login_required
def list_columns(project_id):
    result = (
        supabase.table("columns")
        .select("*")
        .eq("project_id", project_id)
        .order("position")
        .execute()
    )
    return jsonify(result.data), 200


@columns_bp.route("", methods=["POST"])
@login_required
@require_role("leader")
def create_column(project_id):
    """Structural changes to the board (adding a column) are a
    Leader decision — keeps the board layout consistent for the
    whole team rather than each developer improvising their own."""
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "Column name is required"}), 400

    existing = supabase.table("columns").select("position").eq("project_id", project_id).execute()
    next_position = len(existing.data)

    column = supabase.table("columns").insert({
        "project_id": project_id,
        "name": name,
        "position": next_position,
    }).execute().data[0]

    return jsonify(column), 201


@columns_bp.route("/<column_id>", methods=["PATCH"])
@login_required
@require_role("leader")
def rename_column(project_id, column_id):
    body = request.get_json(force=True)
    updates = {}
    if "name" in body:
        updates["name"] = body["name"].strip()
    if "position" in body:
        updates["position"] = body["position"]

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    result = supabase.table("columns").update(updates).eq("id", column_id).execute()
    return jsonify(result.data[0]), 200


@columns_bp.route("/<column_id>", methods=["DELETE"])
@login_required
@require_role("leader")
def delete_column(project_id, column_id):
    supabase.table("columns").delete().eq("id", column_id).execute()
    return jsonify({"message": "Column deleted"}), 200
