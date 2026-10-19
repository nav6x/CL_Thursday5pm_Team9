import os
from flask import Blueprint, request, jsonify
from config import supabase, supabase_auth
from auth_utils import login_required

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
    try:
        supabase.table("profiles").insert({
            "id": result.user.id,
            "full_name": full_name,
            "email": email,
        }).execute()
    except Exception:
        pass

    return jsonify({
        "message": "Account created! Please check your email and click the confirmation link before logging in.",
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
    except Exception as e:
        error_msg = str(e)
        if "email not confirmed" in error_msg.lower():
            return jsonify({
                "error": "Email not confirmed. Please check your inbox and verify your email before logging in."
            }), 401
        return jsonify({"error": "Invalid email or password"}), 401

    # Check if user has an active TOTP Two-Factor Authentication factor
    factors = getattr(result.user, "factors", None)
    if not factors:
        try:
            admin_user = supabase.auth.admin.get_user_by_id(result.user.id)
            factors = getattr(admin_user.user, "factors", None) or []
        except Exception:
            factors = []

    verified_mfa = [
        f for f in factors
        if (getattr(f, "status", None) == "verified" or (isinstance(f, dict) and f.get("status") == "verified"))
        and (getattr(f, "factor_type", None) == "totp" or (isinstance(f, dict) and f.get("factor_type") == "totp"))
    ]

    if verified_mfa:
        factor_id = verified_mfa[0].id if hasattr(verified_mfa[0], "id") else verified_mfa[0]["id"]
        return jsonify({
            "mfa_required": True,
            "factor_id": factor_id,
            "temp_token": result.session.access_token,
            "user": {"id": result.user.id, "email": result.user.email},
        }), 200

    return jsonify({
        "access_token": result.session.access_token,
        "user": {"id": result.user.id, "email": result.user.email},
    }), 200


@auth_bp.route("/mfa/verify-login", methods=["POST"])
def verify_mfa_login():
    """Verifies a 6-digit TOTP code during the login flow and returns the full session."""
    body = request.get_json(force=True)
    temp_token = body.get("temp_token")
    factor_id = body.get("factor_id")
    code = body.get("code", "").strip()

    if not temp_token or not factor_id or not code:
        return jsonify({"error": "temp_token, factor_id, and code are required"}), 400

    try:
        challenge_res = supabase_auth.auth._request(
            "POST",
            f"factors/{factor_id}/challenge",
            jwt=temp_token,
        )
        challenge_id = challenge_res.json().get("id")

        verify_res = supabase_auth.auth._request(
            "POST",
            f"factors/{factor_id}/verify",
            jwt=temp_token,
            body={"challenge_id": challenge_id, "code": code},
        )
        data = verify_res.json()
        if "access_token" not in data:
            return jsonify({"error": "Invalid verification code. Please try again."}), 401

        return jsonify({
            "access_token": data["access_token"],
            "user": data.get("user", {}),
        }), 200
    except Exception:
        return jsonify({"error": "Invalid verification code. Please try again."}), 401


@auth_bp.route("/mfa/enroll", methods=["POST"])
@login_required
def enroll_mfa():
    """Generates a new TOTP factor (QR code SVG & secret key) for the authenticated user."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1]

    try:
        res = supabase_auth.auth._request(
            "POST",
            "factors",
            jwt=token,
            body={"factor_type": "totp", "issuer": "Scrumptious", "friendly_name": "Authenticator App"},
        )
        data = res.json()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.route("/mfa/confirm-enrollment", methods=["POST"])
@login_required
def confirm_mfa_enrollment():
    """Validates the first 6-digit code after scanning to activate 2FA on the account."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1]
    body = request.get_json(force=True)
    factor_id = body.get("factor_id")
    code = body.get("code", "").strip()

    if not factor_id or not code:
        return jsonify({"error": "factor_id and code are required"}), 400

    try:
        challenge_res = supabase_auth.auth._request(
            "POST",
            f"factors/{factor_id}/challenge",
            jwt=token,
        )
        challenge_id = challenge_res.json().get("id")

        verify_res = supabase_auth.auth._request(
            "POST",
            f"factors/{factor_id}/verify",
            jwt=token,
            body={"challenge_id": challenge_id, "code": code},
        )
        data = verify_res.json()
        return jsonify({
            "message": "Two-factor authentication successfully enabled!",
            "access_token": data.get("access_token", token),
        }), 200
    except Exception:
        return jsonify({"error": "Invalid code. Please check your authenticator app and try again."}), 400


@auth_bp.route("/mfa/unenroll", methods=["POST"])
@login_required
def unenroll_mfa():
    """Disables Two-Factor Authentication by unenrolling the TOTP factor."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1]
    body = request.get_json(force=True) if request.data else {}
    factor_id = body.get("factor_id")

    try:
        if not factor_id:
            user_data = supabase_auth.auth._request("GET", "user", jwt=token).json()
            factors = user_data.get("factors", [])
            totp = [f for f in factors if f.get("factor_type") == "totp" and f.get("status") == "verified"]
            if not totp:
                return jsonify({"message": "Two-factor authentication is not enabled"}), 200
            factor_id = totp[0]["id"]

        supabase_auth.auth._request("DELETE", f"factors/{factor_id}", jwt=token)
        return jsonify({"message": "Two-factor authentication disabled"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.route("/mfa/status", methods=["GET"])
@login_required
def mfa_status():
    """Checks whether 2FA is currently active for the logged in user."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1]
    try:
        user_data = supabase_auth.auth._request("GET", "user", jwt=token).json()
        factors = user_data.get("factors", [])
        verified_totp = [f for f in factors if f.get("factor_type") == "totp" and f.get("status") == "verified"]
        return jsonify({
            "enabled": len(verified_totp) > 0,
            "factor_id": verified_totp[0]["id"] if verified_totp else None,
        }), 200
    except Exception as e:
        return jsonify({"enabled": False, "error": str(e)}), 200


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    body = request.get_json(force=True)
    email = body.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    try:
        supabase_auth.auth.resend({"type": "signup", "email": email})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"message": "Verification email resent. Please check your inbox."}), 200


@auth_bp.route("/users", methods=["GET"])
def list_users():
    result = supabase.table("profiles").select("id, full_name, email").execute()
    users = result.data or []
    try:
        memberships_res = (
            supabase.table("project_members")
            .select("user_id, role, projects(id, name)")
            .execute()
        )
        user_projects = {}
        for m in (memberships_res.data or []):
            uid = m.get("user_id")
            proj = m.get("projects")
            if not uid or not proj:
                continue
            if uid not in user_projects:
                user_projects[uid] = []
            db_role = m.get("role", "developer")
            user_projects[uid].append({
                "id": proj.get("id"),
                "name": proj.get("name"),
                "role": db_role,
            })
        for u in users:
            uid = u.get("id")
            projs = user_projects.get(uid, [])
            u["project_count"] = len(projs)
            u["projects"] = projs
    except Exception:
        for u in users:
            u.setdefault("project_count", 0)
            u.setdefault("projects", [])
    return jsonify(users), 200


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
