import os
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


@auth_bp.route("/users", methods=["GET"])
def list_users():
    result = supabase.table("profiles").select("id, full_name, email").execute()
    return jsonify(result.data), 200


RESET_REDIRECT_URL = os.environ.get("RESET_REDIRECT_URL", "http://localhost:5000/reset-password.html")
MIN_PASSWORD_LENGTH = 8


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Sends a password reset email. Always answers the same way so account existence isn't revealed."""
    body = request.get_json(force=True)
    email = body.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    try:
        supabase_auth.auth.reset_password_for_email(email, {"redirect_to": RESET_REDIRECT_URL})
    except Exception:
        pass

    return jsonify({"message": "If an account exists, a reset link has been sent."}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """Checks the emailed recovery token, then sets the new password."""
    body = request.get_json(force=True)
    token_hash = body.get("token_hash", "").strip()
    password = body.get("password", "")

    if not token_hash:
        return jsonify({"error": "This reset link is invalid or has expired. Request a new one."}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return jsonify({"error": "Password must include at least one letter and one number."}), 400

    # The token is single-use: verify_otp checks it and tells us which user it belongs to.
    try:
        result = supabase_auth.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
        user = result.user
    except Exception:
        return jsonify({"error": "This reset link is invalid or has expired. Request a new one."}), 400

    if user is None:
        return jsonify({"error": "This reset link is invalid or has expired. Request a new one."}), 400

    try:
        supabase.auth.admin.update_user_by_id(user.id, {"password": password})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"message": "Password updated."}), 200
