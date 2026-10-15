from flask import Blueprint, request, jsonify, g
from config import supabase
from auth_utils import login_required

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

# Expects a `notifications` table — see notifications.sql.


@notifications_bp.route("", methods=["GET"])
@login_required
def list_notifications():
    """The caller's newest notifications plus their total unread count
    (the number shown on the bell)."""
    try:
        limit = max(1, min(int(request.args.get("limit", 30)), 100))
    except ValueError:
        limit = 30

    result = (
        supabase.table("notifications")
        .select("id, type, message, is_read, created_at, project_id, task_id, actor_id, projects(name)")
        .eq("user_id", g.user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    unread = (
        supabase.table("notifications")
        .select("id", count="exact")
        .eq("user_id", g.user.id)
        .eq("is_read", False)
        .execute()
    )
    return jsonify({
        "notifications": result.data or [],
        "unread_count": unread.count or 0,
    }), 200


@notifications_bp.route("/<notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    # Scoped to user_id so nobody can mark someone else's notifications.
    (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("user_id", g.user.id)
        .execute()
    )
    return jsonify({"message": "Marked as read"}), 200


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("user_id", g.user.id)
        .eq("is_read", False)
        .execute()
    )
    return jsonify({"message": "All notifications marked as read"}), 200