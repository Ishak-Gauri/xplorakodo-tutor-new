"""Knowledge base, Ask Sensei, Leveler model, Course Factory and observability endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import observability
from ..db import J
from ..deps import admin, current_user, svc
from ..errors import BadRequest, NotFound
from ..kb.ingest import SOURCES
from ..kb.store import LEVELS

router = APIRouter(prefix="/api")

Level = Literal["N5", "N4", "N3", "N2", "N1"]


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=1500)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class IngestIn(BaseModel):
    source: str
    datasets: str | None = Field(default=None, max_length=1000)
    per_level: int | None = Field(default=None, ge=50, le=10000)


class FactoryIn(BaseModel):
    topic_id: str
    count: int = Field(default=5, ge=1, le=10)
    focus: Literal["mixed", "vocab", "grammar"] = "mixed"
    level: Level | None = None


def _iso_rows(rows):
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} for r in rows]


# ----------------------------------------------------------------- students
@router.post("/ask")
def ask(body: AskIn, user=Depends(current_user), s=Depends(svc)):
    return s.ask.ask(user, body.message)


@router.get("/ask/history")
def ask_history(user=Depends(current_user), s=Depends(svc)):
    return s.ask.history(user)


@router.delete("/ask/history")
def ask_clear(user=Depends(current_user), s=Depends(svc)):
    s.ask.clear(user)
    return {"ok": True}


@router.get("/kb/browse")
def kb_browse(level: Level | None = None, kind: str | None = None, q: str = "", page: int = 1,
              _=Depends(current_user), s=Depends(svc)):
    out = s.kb.browse(level, kind, q.strip()[:100], max(1, page))
    out["items"] = _iso_rows(out["items"])
    return out


@router.get("/kb/search")
def kb_search(q: str, level: Level | None = None, _=Depends(current_user), s=Depends(svc)):
    if not q.strip():
        raise BadRequest("Type something to search.")
    levels = LEVELS[: LEVELS.index(level) + 1] if level else None
    rows = s.retriever.search(q.strip()[:300], levels=levels, k=12)
    return _iso_rows(rows)


@router.get("/kb/stats")
def kb_stats(_=Depends(current_user), s=Depends(svc)):
    return s.kb.stats()


@router.post("/level")
def estimate_level(body: TextIn, _=Depends(current_user), s=Depends(svc)):
    return s.leveler.estimate(body.text)


# ----------------------------------------------------------------- admin: knowledge base
@router.get("/admin/kb/runs")
def kb_runs(_=Depends(admin), s=Depends(svc)):
    return _iso_rows(s.ingestor.runs())


@router.post("/admin/kb/ingest")
def kb_ingest(body: IngestIn, me=Depends(admin), s=Depends(svc)):
    if body.source not in SOURCES:
        raise BadRequest(f"Unknown source. Use one of: {', '.join(SOURCES)}.")
    opts = {k: v for k, v in {"datasets": body.datasets, "per_level": body.per_level}.items() if v}
    try:
        s.ingestor.start_background(body.source, me["id"], opts)
    except RuntimeError as e:
        raise BadRequest(str(e)) from None
    s.db.run("INSERT INTO audit_log(actor_id, action, target, detail) VALUES (%s,'kb.ingest',%s,%s)", (me["id"], body.source, J(opts)))
    return {"started": body.source}


# ----------------------------------------------------------------- admin: model
@router.get("/admin/model")
def model_info(_=Depends(admin), s=Depends(svc)):
    versions = s.db.all("SELECT version, active, trained_at, metrics->>'accuracy' AS accuracy, metrics->>'within_one' AS within_one, "
                        "metrics->>'macro_f1' AS macro_f1, metrics->>'train_size' AS train_size FROM ml_models "
                        "WHERE name = 'jlpt_level' ORDER BY version DESC LIMIT 20")
    info = s.model_info
    return {"active": {**info, "trained_at": info.get("trained_at")}, "versions": _iso_rows(versions)}


@router.post("/admin/model/predict")
def model_predict(body: TextIn, _=Depends(admin), s=Depends(svc)):
    return s.leveler.estimate(body.text)


@router.post("/admin/model/activate/{version}")
def model_activate(version: int, me=Depends(admin), s=Depends(svc)):
    with s.db.tx() as conn:
        if not conn.execute("SELECT 1 FROM ml_models WHERE name='jlpt_level' AND version=%s", (version,)).fetchone():
            raise NotFound("Model version not found.")
        conn.execute("UPDATE ml_models SET active = (version = %s) WHERE name = 'jlpt_level'", (version,))
    return s.reload_leveler()


# ----------------------------------------------------------------- admin: course factory
@router.post("/admin/factory")
def factory(body: FactoryIn, me=Depends(admin), s=Depends(svc)):
    out = s.factory.generate(me, body.topic_id, body.count, body.focus, body.level)
    s.db.run("INSERT INTO audit_log(actor_id, action, target, detail) VALUES (%s,'factory.generate',%s,%s)",
             (me["id"], body.topic_id, J({"count": body.count, "level": out["level"], "drafts": [d["id"] for d in out["drafts"]]})))
    return out


@router.post("/admin/questions/{question_id}/publish")
def publish(question_id: str, me=Depends(admin), s=Depends(svc)):
    if not s.db.run("UPDATE questions SET status='published', active=true, updated_at=now() WHERE id=%s", (question_id,)):
        raise NotFound("Question not found.")
    s.db.run("INSERT INTO audit_log(actor_id, action, target) VALUES (%s,'question.publish',%s)", (me["id"], question_id))
    return {"id": question_id, "status": "published"}


@router.delete("/admin/questions/{question_id}")
def delete_draft(question_id: str, me=Depends(admin), s=Depends(svc)):
    if not s.db.run("DELETE FROM questions WHERE id=%s AND status='draft'", (question_id,)):
        raise BadRequest("Only drafts can be deleted. Hide published questions instead.")
    s.db.run("INSERT INTO audit_log(actor_id, action, target) VALUES (%s,'question.delete_draft',%s)", (me["id"], question_id))
    return {"id": question_id, "deleted": True}


# ----------------------------------------------------------------- observability
@router.get("/admin/observability")
def obs(_=Depends(admin), s=Depends(svc)):
    return {"langsmith": observability.status(), "llm": s.llm.name, "llm_model": getattr(s.llm, "model", None),
            "embedder": s.embedder.name, "engine": "langgraph", "leveler": s.model_info.get("source"),
            "kb_documents": s.kb.count()}
