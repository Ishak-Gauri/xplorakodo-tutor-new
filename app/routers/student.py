"""Auth and student endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..deps import current_user, svc
from ..security import make_token
from ..service import public_user

router = APIRouter(prefix="/api")

Lang = Literal["en", "ne", "ja"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    lang: Lang = "en"
    org_id: int | None = None


class LoginIn(BaseModel):
    email: str = Field(max_length=160)
    password: str = Field(max_length=128)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    lang: Lang | None = None


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=128)


class PlacementIn(BaseModel):
    answers: list[int]


class SessionIn(BaseModel):
    kind: Literal["practice", "interview"] = "practice"
    topic_id: str | None = None


class AnswerIn(BaseModel):
    answer: str = Field(max_length=2000)
    latency_ms: int | None = Field(default=None, ge=0, le=3_600_000)


def _token_payload(request: Request, user: dict) -> dict:
    s = request.app.state.settings
    return {"token": make_token(user, s.jwt_secret, s.jwt_hours), "user": public_user(user)}


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, s=Depends(svc)):
    user = s.register(body.name, body.email, body.password, body.lang, body.org_id)
    return _token_payload(request, user)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, s=Depends(svc)):
    return _token_payload(request, s.login(body.email, body.password))


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.put("/me")
def update_me(body: ProfileIn, user=Depends(current_user), s=Depends(svc)):
    return public_user(s.update_profile(user, body.name, body.lang))


@router.post("/me/password")
def change_password(body: PasswordIn, user=Depends(current_user), s=Depends(svc)):
    s.change_password(user, body.current, body.new)
    return {"ok": True}


@router.get("/me/dashboard")
def dashboard(user=Depends(current_user), s=Depends(svc)):
    return s.dashboard(user)


@router.get("/me/heatmap")
def heatmap(user=Depends(current_user), s=Depends(svc)):
    return s.heatmap(user)


@router.get("/me/sessions")
def my_sessions(user=Depends(current_user), s=Depends(svc)):
    return s.history(user)


@router.get("/me/memories")
def my_memories(user=Depends(current_user), s=Depends(svc)):
    return s.memories(user)


@router.post("/me/certificate")
def claim_certificate(user=Depends(current_user), s=Depends(svc)):
    return s.claim_certificate(user)


@router.get("/topics")
def topics(kind: Literal["practice", "interview"] = "practice", user=Depends(current_user), s=Depends(svc)):
    return s.topics_payload(user, kind)


@router.post("/placement")
def start_placement(user=Depends(current_user), s=Depends(svc)):
    return s.start_placement(user)


@router.post("/placement/{attempt_id}")
def submit_placement(attempt_id: int, body: PlacementIn, user=Depends(current_user), s=Depends(svc)):
    return s.submit_placement(user, attempt_id, body.answers)


@router.post("/sessions")
def start_session(body: SessionIn, user=Depends(current_user), s=Depends(svc)):
    return s.start_session(user, body.kind, body.topic_id)


@router.get("/sessions/{session_id}")
def session_state(session_id: int, user=Depends(current_user), s=Depends(svc)):
    return s.session_state(user, session_id)


@router.post("/sessions/{session_id}/answer")
def answer(session_id: int, body: AnswerIn, user=Depends(current_user), s=Depends(svc)):
    return s.answer(user, session_id, body.answer, body.latency_ms)


@router.post("/sessions/{session_id}/abandon")
def abandon(session_id: int, user=Depends(current_user), s=Depends(svc)):
    return s.abandon(user, session_id)
