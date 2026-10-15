"""FastAPI dependencies: the service container and the logged-in user."""
from __future__ import annotations

from fastapi import Depends, Request

from .errors import Forbidden, Unauthorized
from .security import read_token


def svc(request: Request):
    return request.app.state.svc


def admin_svc(request: Request):
    return request.app.state.admin


def current_user(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    claims = read_token(token, request.app.state.settings.jwt_secret) if token else None
    if not claims:
        raise Unauthorized("Please log in.")
    user = request.app.state.svc.db.one(
        "SELECT id, org_id, email, name, role, status, lang, track, level, created_at FROM users WHERE id = %s",
        (int(claims["sub"]),))
    if not user:
        raise Unauthorized("Account not found.")
    if user["status"] == "suspended":
        raise Unauthorized("This account is suspended.")
    return user


def student(user: dict = Depends(current_user)) -> dict:
    return user


def admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise Forbidden("Admins only.")
    return user
