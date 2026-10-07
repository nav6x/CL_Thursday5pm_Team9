from functools import wraps
from flask import request, jsonify, g
from config import supabase, supabase_auth, maybe_one


def login_required(f):
    """Verifies the Supabase JWT sent from the frontend and attaches
    the authenticated user to `g.user` for the route to use."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            user_response = supabase_auth.auth.get_user(token)
            g.user = user_response.user
            if g.user is None:
                raise ValueError("No user on token")
        except Exception:
            return jsonify({"error": "Invalid or expired session"}), 401

        return f(*args, **kwargs)
    return wrapper


def get_role_in_project(user_id, project_id):
    """Looks up the caller's role for a specific project. Returns
    None if they aren't a member at all (treated as no access)."""
    result = maybe_one(
        supabase.table("project_members")
        .select("role")
        .eq("user_id", user_id)
        .eq("project_id", project_id)
    )
    return result["role"] if result else None


def require_role(*allowed_roles):
    """Route decorator for project-scoped endpoints. Expects the
    route to accept a `project_id` URL parameter. Use like:

        @require_role("leader")
        def delete_column(project_id, column_id): ...

    Must be applied AFTER @login_required (i.e. listed below it),
    so g.user already exists when this runs.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            project_id = kwargs.get("project_id") or request.view_args.get("project_id")
            if not project_id:
                return jsonify({"error": "project_id is required for this action"}), 400

            role = get_role_in_project(g.user.id, project_id)
            if role is None:
                return jsonify({"error": "You are not a member of this project"}), 403
            if role not in allowed_roles:
                return jsonify({"error": f"This action requires role: {', '.join(allowed_roles)}"}), 403

            g.role = role
            return f(*args, **kwargs)
        return wrapper
    return decorator
