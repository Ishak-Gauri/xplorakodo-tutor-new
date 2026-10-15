"""Admin console endpoints (role = admin)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import admin, admin_svc

router = APIRouter(prefix="/api/admin")


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class StudentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    lang: Literal["en", "ne", "ja"] = "en"
    org_id: int | None = None


class StudentUpdateIn(BaseModel):
    status: Literal["active", "suspended"] | None = None
    org_id: int | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    level: Literal["Pre-N5", "N5", "N4", "N3", "N2", "N1"] | None = None


class Text3(BaseModel):
    en: str = ""
    ne: str = ""
    ja: str = ""


class QuestionIn(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,24}$")
    topic_id: str
    skill: str = Field(min_length=2, max_length=40)
    difficulty: int = Field(ge=1, le=5)
    prompt: Text3
    keywords: list[list[str]]
    model_answer: Text3
    probe: Text3
    active: bool = True


class ActiveIn(BaseModel):
    active: bool


class RevokeIn(BaseModel):
    revoked: bool = True


class GradeTestIn(BaseModel):
    answer: str = Field(max_length=2000)


@router.get("/overview")
def overview(_=Depends(admin), a=Depends(admin_svc)):
    return a.overview()


@router.get("/orgs")
def orgs(_=Depends(admin), a=Depends(admin_svc)):
    return a.orgs()


@router.post("/orgs")
def create_org(body: OrgIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.create_org(me, body.name)


@router.get("/students")
def students(q: str = "", org_id: int | None = None, level: str | None = None, page: int = 1,
             _=Depends(admin), a=Depends(admin_svc)):
    return a.students(q, org_id, level, max(1, page))


@router.post("/students")
def create_student(body: StudentCreateIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.create_student(me, body.name, body.email, body.password, body.lang, body.org_id)


@router.get("/students/{user_id}")
def student_detail(user_id: int, _=Depends(admin), a=Depends(admin_svc)):
    return a.student_detail(user_id)


@router.patch("/students/{user_id}")
def update_student(user_id: int, body: StudentUpdateIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.update_student(me, user_id, body.status, body.org_id, body.password, body.level)


@router.get("/sessions/{session_id}")
def session(session_id: int, me=Depends(admin), a=Depends(admin_svc)):
    return a.svc.session_state(me, session_id)


@router.get("/topics")
def topics(_=Depends(admin), a=Depends(admin_svc)):
    from ..content import loc
    return [{"id": t["id"], "kind": t["kind"], "title": loc(t["title"], "en"), "active": t["active"]}
            for kind in ("practice", "interview") for t in a.svc.content.topics(kind, include_inactive=True)]


@router.get("/questions")
def questions(topic_id: str | None = None, q: str = "", kind: str | None = None, status: str | None = None,
              _=Depends(admin), a=Depends(admin_svc)):
    return a.questions(topic_id, q, kind, status)


@router.post("/questions")
def create_question(body: QuestionIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.save_question(me, body.model_dump())


@router.put("/questions/{question_id}")
def update_question(question_id: str, body: QuestionIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.save_question(me, body.model_dump(), question_id)


@router.patch("/questions/{question_id}")
def toggle_question(question_id: str, body: ActiveIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.toggle_question(me, question_id, body.active)


@router.post("/questions/{question_id}/test")
def test_question(question_id: str, body: GradeTestIn, _=Depends(admin), a=Depends(admin_svc)):
    return a.test_grade(question_id, body.answer)


@router.get("/runs")
def runs(graph: str | None = None, status: str | None = None, user_id: int | None = None, limit: int = 40,
         _=Depends(admin), a=Depends(admin_svc)):
    return a.runs(min(limit, 200), graph, status, user_id)


@router.get("/runs/{run_id}")
def run_detail(run_id: int, _=Depends(admin), a=Depends(admin_svc)):
    return a.run_detail(run_id)


@router.get("/settings")
def get_settings(_=Depends(admin), a=Depends(admin_svc)):
    return a.svc.settings.all()


@router.put("/settings")
def put_settings(body: dict, me=Depends(admin), a=Depends(admin_svc)):
    return a.update_settings(me, body)


@router.get("/certificates")
def certificates(_=Depends(admin), a=Depends(admin_svc)):
    return a.certificates()


@router.patch("/certificates/{code}")
def revoke(code: str, body: RevokeIn, me=Depends(admin), a=Depends(admin_svc)):
    return a.revoke(me, code, body.revoked)


@router.get("/audit")
def audit(_=Depends(admin), a=Depends(admin_svc)):
    return a.audit_log()
