from flask import Blueprint, request, jsonify
from config import supabase, supabase_auth

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Expects a `profiles` table with columns: id (uuid, matches auth.users.id),
# full_name (text), email (text). Adjust the .insert() call below if your
# column names differ.


@auth_bp.route("/signup", methods=["POST"])
def signup():
    body = request.get_json(force=True)
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    full_name = body.get("full_name", "").strip()

    if not email or not password or not full_name:
        return jsonify({"error": "email, password, and full_name are required"}), 400

    try:
        result = supabase_auth.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if result.user is None:
        return jsonify({"error": "Signup failed"}), 400

    # Mirror the new user into our own profiles table so we can join
    # on it elsewhere (project_members, tasks.created_by, etc.)
    supabase.table("profiles").insert({
        "id": result.user.id,
        "full_name": full_name,
        "email": email,
    }).execute()

    return jsonify({
        "message": "Account created. Check your email to confirm, then log in.",
        "user_id": result.user.id,
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json(force=True)
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    try:
        result = supabase_auth.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except Exception:
        return jsonify({"error": "Invalid email or password"}), 401

    return jsonify({
        "access_token": result.session.access_token,
        "user": {"id": result.user.id, "email": result.user.email},
    }), 200
