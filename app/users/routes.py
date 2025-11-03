# app/users/routes.py
from functools import wraps
from flask import (
    Blueprint, request, jsonify, render_template, session,
    redirect, url_for, flash
)
from sqlalchemy import func
from app.models import db, User
import os

users_bp = Blueprint("users_bp", __name__)

# ------------- ADMIN CONFIG -----------------
ADMIN_EMAILS = {e.strip().lower() for e in (os.getenv("ADMIN_EMAILS") or "").split(",")}

def is_session_admin():
    info = session.get("user") or {}
    email = (info.get("email") or info.get("preferred_username") or "").lower()
    session_roles = [r.lower() for r in session.get("roles", [])]
    session_role = (session.get("role") or "").lower()
    return (
        session_role == "admin"
        or "admin" in session_roles
        or (email and email in ADMIN_EMAILS)
    )

def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        me = current_db_user()
        if me and me.status == "active" and (me.role or "").lower() == "admin":
            return f(*args, **kwargs)
        if is_session_admin():
            return f(*args, **kwargs)
        return jsonify({"error": "Forbidden (admin only)"}), 403
    return wrapper

def current_db_user():
    """Return the DB user row for the currently signed-in O365 user (or None)."""
    info = session.get("user")
    if not info:
        return None
    email = (info.get("email") or info.get("preferred_username") or "").strip()
    if not email:
        return None
    return User.query.filter(func.lower(User.email) == email.lower()).first()

def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            # Adjust endpoint if your login view function name differs
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper

# ----------------- UI Page -----------------

@users_bp.get("/")  # http://localhost:5000/users/
@require_login
@require_admin
def users_page():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users)

# ----------------- JSON API -----------------

@users_bp.get("/api")
@require_login
@require_admin
def list_users_api():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.as_dict() for u in users])

@users_bp.post("/api")
@require_login
@require_admin
def create_user_api():
    # Accept both JSON and form posts (from the HTML form)
    if request.is_json:
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        role = (data.get("role") or "user").lower()
        status = (data.get("status") or "active").lower()
        wants_json = True
    else:
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        role = (request.form.get("role") or "user").lower()
        status = (request.form.get("status") or "active").lower()
        wants_json = False

    # Validate
    if not name or not email:
        if wants_json:
            return jsonify({"error": "name and email required"}), 400
        flash("Name and email are required.", "error")
        return redirect(url_for("users_bp.users_page"))

    if role not in ("admin", "basicuser"):
        if wants_json:
            return jsonify({"error": "role must be 'admin' or 'basicuser'"}), 400
        flash("Role must be admin or basicuser.", "error")
        return redirect(url_for("users_bp.users_page"))

    if status not in ("active", "deactivated"):
        if wants_json:
            return jsonify({"error": "status must be 'active' or 'deactivated'"}), 400
        flash("Status must be active or deactivated.", "error")
        return redirect(url_for("users_bp.users_page"))

    # Duplicate email (case-insensitive)
    if User.query.filter(func.lower(User.email) == email.lower()).first():
        if wants_json:
            return jsonify({"error": "email already exists"}), 400
        flash("A user with that email already exists.", "error")
        return redirect(url_for("users_bp.users_page"))

    u = User(name=name, email=email, role=role, status=status)
    db.session.add(u)
    db.session.commit()

    if wants_json:
        return jsonify(u.as_dict()), 201
    flash("User created.", "success")
    return redirect(url_for("users_bp.users_page"))

@users_bp.put("/api/<int:user_id>")
@require_login
@require_admin
def update_user_api(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data and data["name"]:
        u.name = data["name"]
    if "email" in data and data["email"]:
        new_email = data["email"].strip()
        # prevent duplicates, case-insensitive
        exists = User.query.filter(
            func.lower(User.email) == new_email.lower(),
            User.id != u.id
        ).first()
        if exists:
            return jsonify({"error": "email already exists"}), 400
        u.email = new_email
    if "role" in data and data["role"]:
        role = data["role"].lower()
        if role not in ("admin", "basicuser"):
            return jsonify({"error": "role must be 'admin' or 'basicuser'"}), 400
        u.role = role
    if "status" in data and data["status"]:
        status = data["status"].lower()
        if status not in ("active", "deactivated"):
            return jsonify({"error": "status must be 'active' or 'deactivated'"}), 400
        u.status = status

    db.session.commit()
    return jsonify(u.as_dict())

@users_bp.delete("/api/<int:user_id>")
@require_login
@require_admin
def delete_user_api(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({"error": "not found"}), 404
    db.session.delete(u)
    db.session.commit()
    return jsonify({"ok": True})

@users_bp.post("/api/<int:user_id>/deactivate")
@require_login
@require_admin
def deactivate_user_api(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({"error": "not found"}), 404
    u.status = "deactivated"
    db.session.commit()
    return jsonify(u.as_dict())

@users_bp.post("/api/<int:user_id>/reactivate")
@require_login
@require_admin
def reactivate_user_api(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({"error": "not found"}), 404
    u.status = "active"
    db.session.commit()
    return jsonify(u.as_dict())





