"""Admin console queries: KPIs, students, question bank, agent runs, settings, certificates, audit."""
from __future__ import annotations

from .content import SKILLS, loc
from .db import J, vec
from .errors import BadRequest, NotFound
from .security import hash_password
from .seed import question_text
from .service import USER_FIELDS, TutorService, _iso, public_user


def _rows(rows: list[dict]) -> list[dict]:
    return [{k: _iso(v) for k, v in r.items()} for r in rows]


class AdminService:
    def __init__(self, svc: TutorService):
        self.svc, self.db = svc, svc.db

    def audit(self, actor: dict, action: str, target: str | None = None, detail: dict | None = None) -> None:
        self.db.run("INSERT INTO audit_log(actor_id, action, target, detail) VALUES (%s,%s,%s,%s)",
                    (actor["id"], action, target, J(detail or {})))

    # ------------------------------------------------------------- overview
    def overview(self) -> dict:
        k = self.db.one(
            "SELECT (SELECT COUNT(*) FROM users WHERE role='student')::int AS students, "
            "(SELECT COUNT(DISTINCT user_id) FROM turns WHERE answered_at > now() - interval '7 days')::int AS active_7d, "
            "(SELECT COUNT(*) FROM sessions WHERE created_at::date = CURRENT_DATE)::int AS sessions_today, "
            "(SELECT COUNT(*) FROM turns WHERE score IS NOT NULL)::int AS answers, "
            "(SELECT AVG(score) FROM turns WHERE score IS NOT NULL)::float AS avg_score, "
            "(SELECT COALESCE(SUM(tokens),0) FROM token_usage WHERE day = CURRENT_DATE)::int AS tokens_today, "
            "(SELECT COUNT(*) FROM certificates WHERE NOT revoked)::int AS certificates, "
            "(SELECT COUNT(*) FROM memories)::int AS memories, "
            "(SELECT COUNT(*) FROM agent_runs WHERE status='blocked' AND created_at > now() - interval '1 day')::int AS blocked_24h, "
            "(SELECT AVG(duration_ms) FROM agent_runs WHERE created_at > now() - interval '1 day')::float AS run_ms")
        activity = self.db.all(
            "SELECT d::date AS day, COALESCE(x.answers,0)::int AS answers, x.avg FROM "
            "generate_series(CURRENT_DATE - 13, CURRENT_DATE, interval '1 day') d LEFT JOIN ("
            " SELECT answered_at::date AS day, COUNT(*) AS answers, AVG(score)::float AS avg FROM turns "
            " WHERE answered_at IS NOT NULL GROUP BY 1) x ON x.day = d::date ORDER BY d")
        levels = self.db.all("SELECT COALESCE(level,'Not placed') AS level, COUNT(*)::int AS n FROM users "
                             "WHERE role='student' GROUP BY 1 ORDER BY 1")
        topics = self.svc.content.topics("practice")
        mastery = {(r["topic_id"], r["skill"]): r for r in self.db.all(
            "SELECT q.topic_id, q.skill, AVG(t.score)::float AS avg, COUNT(*)::int AS n FROM turns t "
            "JOIN questions q ON q.id = t.question_id JOIN sessions s ON s.id = t.session_id "
            "WHERE t.score IS NOT NULL AND s.kind='practice' GROUP BY 1,2")}
        cohort = {"skills": SKILLS, "topics": [{"id": t["id"], "title": loc(t["title"], "en")} for t in topics],
                  "cells": {t["id"]: {s: ({"avg": round(mastery[(t["id"], s)]["avg"], 2), "n": mastery[(t["id"], s)]["n"]}
                                         if (t["id"], s) in mastery else None) for s in SKILLS} for t in topics}}
        graders = self.db.all("SELECT COALESCE(grader,'?') AS grader, COUNT(*)::int AS n FROM turns WHERE score IS NOT NULL GROUP BY 1")
        agents = self.db.all("SELECT agent, COUNT(*)::int AS n, AVG(duration_ms)::float AS ms, "
                             "SUM(CASE WHEN status <> 'ok' THEN 1 ELSE 0 END)::int AS issues FROM agent_events "
                             "WHERE run_id IN (SELECT id FROM agent_runs WHERE created_at > now() - interval '7 days') GROUP BY agent ORDER BY n DESC")
        hardest = self.db.all(
            "SELECT q.id, q.topic_id, q.skill, q.prompt->>'en' AS prompt, AVG(t.score)::float AS avg, COUNT(*)::int AS n "
            "FROM turns t JOIN questions q ON q.id = t.question_id WHERE t.score IS NOT NULL "
            "GROUP BY q.id HAVING COUNT(*) >= 1 ORDER BY AVG(t.score) ASC, COUNT(*) DESC LIMIT 6")
        return {"kpis": {**k, "avg_score": round(k["avg_score"], 2) if k["avg_score"] is not None else None,
                         "run_ms": int(k["run_ms"]) if k["run_ms"] else None},
                "activity": _rows(activity), "levels": levels, "cohort": cohort, "graders": graders,
                "agents": [{**a, "ms": round(a["ms"] or 0, 1)} for a in agents],
                "hardest": [{**h, "avg": round(h["avg"], 2)} for h in hardest],
                "settings": self.svc.settings.all(), "llm": self.svc.llm.name, "embedder": self.svc.embedder.name}

    # ------------------------------------------------------------- organizations
    def orgs(self) -> list[dict]:
        return _rows(self.db.all("SELECT o.id, o.name, o.created_at, COUNT(u.id)::int AS students FROM organizations o "
                                 "LEFT JOIN users u ON u.org_id = o.id AND u.role='student' GROUP BY o.id ORDER BY o.name"))

    def create_org(self, actor: dict, name: str) -> dict:
        row = self.db.one("INSERT INTO organizations(name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id, name", (name.strip(),))
        if not row:
            raise BadRequest("An institute with this name already exists.")
        self.audit(actor, "org.create", name)
        return row

    # ------------------------------------------------------------- students
    def students(self, q: str = "", org_id: int | None = None, level: str | None = None, page: int = 1, size: int = 20) -> dict:
        where, params = ["u.role = 'student'"], []
        if q:
            where.append("(u.name ILIKE %s OR u.email ILIKE %s)")
            params += [f"%{q}%", f"%{q}%"]
        if org_id:
            where.append("u.org_id = %s")
            params.append(org_id)
        if level:
            where.append("COALESCE(u.level,'Not placed') = %s")
            params.append(level)
        w = " AND ".join(where)
        total = self.db.scalar(f"SELECT COUNT(*) FROM users u WHERE {w}", params)
        rows = self.db.all(
            f"SELECT u.id, u.name, u.email, u.status, u.level, u.lang, u.created_at, u.last_login_at, o.name AS org, "
            f"(SELECT COUNT(*) FROM turns t WHERE t.user_id = u.id AND t.score IS NOT NULL)::int AS answers, "
            f"(SELECT AVG(score) FROM turns t WHERE t.user_id = u.id AND t.score IS NOT NULL)::float AS avg, "
            f"(SELECT MAX(answered_at) FROM turns t WHERE t.user_id = u.id) AS last_active, "
            f"EXISTS(SELECT 1 FROM certificates c WHERE c.user_id = u.id AND NOT c.revoked) AS certified "
            f"FROM users u LEFT JOIN organizations o ON o.id = u.org_id WHERE {w} ORDER BY u.id DESC LIMIT %s OFFSET %s",
            params + [size, (page - 1) * size])
        return {"total": total, "page": page, "size": size,
                "items": _rows([{**r, "avg": round(r["avg"], 2) if r["avg"] is not None else None} for r in rows])}

    def student_detail(self, user_id: int) -> dict:
        u = self.db.one(f"SELECT {USER_FIELDS} FROM users WHERE id = %s AND role='student'", (user_id,))
        if not u:
            raise NotFound("Student not found.")
        u_en = {**u, "lang": "en"}
        dash = self.svc.dashboard(u_en)
        placements = _rows(self.db.all("SELECT id, score, total, level, status, created_at FROM placement_attempts "
                                       "WHERE user_id = %s ORDER BY id DESC", (user_id,)))
        org = self.db.one("SELECT name FROM organizations WHERE id = %s", (u["org_id"],)) if u["org_id"] else None
        return {"user": {**public_user(u), "org": org["name"] if org else None,
                         "last_login_at": _iso(u["last_login_at"])},
                "dashboard": dash, "sessions": self.svc.history(u_en, 100), "memories": self.svc.memories(u_en),
                "placements": placements,
                "usage": _rows(self.db.all("SELECT day, tokens, calls FROM token_usage WHERE user_id = %s ORDER BY day DESC LIMIT 14", (user_id,)))}

    def create_student(self, actor: dict, name: str, email: str, password: str, lang: str, org_id: int | None) -> dict:
        u = self.svc.register(name, email, password, lang, org_id)
        self.audit(actor, "student.create", email)
        return public_user(u)

    def update_student(self, actor: dict, user_id: int, status: str | None, org_id: int | None, password: str | None,
                       level: str | None) -> dict:
        if not self.db.one("SELECT 1 FROM users WHERE id = %s AND role='student'", (user_id,)):
            raise NotFound("Student not found.")
        if status:
            self.db.run("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
        if org_id is not None:
            self.db.run("UPDATE users SET org_id = %s WHERE id = %s", (org_id or None, user_id))
        if password:
            self.db.run("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), user_id))
        if level:
            self.db.run("UPDATE users SET level = %s WHERE id = %s", (level, user_id))
        self.audit(actor, "student.update", str(user_id),
                   {"status": status, "org_id": org_id, "password_reset": bool(password), "level": level})
        return public_user(self.svc.get_user(user_id))

    # ------------------------------------------------------------- question bank
    def questions(self, topic_id: str | None = None, q: str = "", kind: str | None = None, status: str | None = None) -> list[dict]:
        where, params = ["TRUE"], []
        if status:
            where.append("q.status = %s")
            params.append(status)
        if topic_id:
            where.append("q.topic_id = %s")
            params.append(topic_id)
        if kind:
            where.append("t.kind = %s")
            params.append(kind)
        if q:
            where.append("(q.id ILIKE %s OR q.prompt::text ILIKE %s)")
            params += [f"%{q}%", f"%{q}%"]
        rows = self.db.all(
            "SELECT q.id, q.topic_id, t.kind, q.skill, q.difficulty, q.prompt, q.keywords, q.model_answer, q.probe, q.active, "
            "q.status, q.origin, q.sources, "
            "q.updated_at, (SELECT COUNT(*) FROM turns x WHERE x.question_id = q.id AND x.score IS NOT NULL)::int AS answers, "
            "(SELECT AVG(score) FROM turns x WHERE x.question_id = q.id)::float AS avg "
            f"FROM questions q JOIN topics t ON t.id = q.topic_id WHERE {' AND '.join(where)} ORDER BY t.position, length(q.id), q.id", params)
        return _rows([{**r, "avg": round(r["avg"], 2) if r["avg"] is not None else None} for r in rows])

    def save_question(self, actor: dict, data: dict, question_id: str | None = None) -> dict:
        if not self.svc.content.topic(data["topic_id"]):
            raise BadRequest("Unknown topic.")
        kw = [[k.strip() for k in g if k.strip()] for g in data["keywords"]]
        kw = [g for g in kw if g]
        if not kw:
            raise BadRequest("Add at least one keyword group (the deterministic grader needs it).")
        if not data["prompt"].get("en"):
            raise BadRequest("The English prompt is required.")
        qtext = question_text({"prompt": data["prompt"], "model_answer": data["model_answer"]})
        emb = vec(self.svc.embedder.embed(qtext))
        if question_id is None:
            qid = data.get("id") or self._next_id(data["topic_id"])
            if self.db.one("SELECT 1 FROM questions WHERE id = %s", (qid,)):
                raise BadRequest("A question with this id already exists.")
            self.db.run("INSERT INTO questions(id, topic_id, skill, difficulty, prompt, keywords, model_answer, probe, active, embedding) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                        (qid, data["topic_id"], data["skill"], data["difficulty"], J(data["prompt"]), J(kw),
                         J(data["model_answer"]), J(data["probe"]), data.get("active", True), emb))
            self.audit(actor, "question.create", qid)
        else:
            qid = question_id
            n = self.db.run("UPDATE questions SET topic_id=%s, skill=%s, difficulty=%s, prompt=%s, keywords=%s, model_answer=%s, "
                            "probe=%s, active=%s, embedding=%s::vector, updated_at=now() WHERE id=%s",
                            (data["topic_id"], data["skill"], data["difficulty"], J(data["prompt"]), J(kw),
                             J(data["model_answer"]), J(data["probe"]), data.get("active", True), emb, qid))
            if not n:
                raise NotFound("Question not found.")
            self.audit(actor, "question.update", qid)
        return self.questions(q=qid)[0]

    def _next_id(self, topic_id: str) -> str:
        prefix = "".join(p[0] for p in topic_id.split("_"))[:3]
        n = int(self.db.scalar("SELECT COUNT(*) FROM questions WHERE topic_id = %s", (topic_id,)) or 0) + 1
        while self.db.one("SELECT 1 FROM questions WHERE id = %s", (f"{prefix}{n}",)):
            n += 1
        return f"{prefix}{n}"

    def toggle_question(self, actor: dict, question_id: str, active: bool) -> dict:
        if not self.db.run("UPDATE questions SET active=%s, updated_at=now() WHERE id=%s", (active, question_id)):
            raise NotFound("Question not found.")
        self.audit(actor, "question.active" if active else "question.inactive", question_id)
        return {"id": question_id, "active": active}

    def test_grade(self, question_id: str, answer: str) -> dict:
        q = self.svc.content.question(question_id)
        if not q:
            raise NotFound("Question not found.")
        res = self.svc.tutor.deterministic.evaluate(q, answer, "en")
        return {"score": round(res["score"], 2), "feedback": res["feedback"]}

    # ------------------------------------------------------------- agent runs
    def runs(self, limit: int = 40, graph: str | None = None, status: str | None = None, user_id: int | None = None) -> list[dict]:
        where, params = ["TRUE"], []
        if graph:
            where.append("r.graph = %s")
            params.append(graph)
        if status:
            where.append("r.status = %s")
            params.append(status)
        if user_id:
            where.append("r.user_id = %s")
            params.append(user_id)
        rows = self.db.all(
            "SELECT r.id, r.graph, r.status, r.tokens, r.duration_ms, r.created_at, r.session_id, r.user_id, u.name AS user_name, "
            "(SELECT COUNT(*) FROM agent_events e WHERE e.run_id = r.id)::int AS steps "
            f"FROM agent_runs r LEFT JOIN users u ON u.id = r.user_id WHERE {' AND '.join(where)} ORDER BY r.id DESC LIMIT %s",
            params + [limit])
        return _rows(rows)

    def run_detail(self, run_id: int) -> dict:
        run = self.db.one("SELECT r.*, u.name AS user_name FROM agent_runs r LEFT JOIN users u ON u.id = r.user_id WHERE r.id = %s", (run_id,))
        if not run:
            raise NotFound("Run not found.")
        events = self.db.all("SELECT seq, agent, node, status, summary, detail, duration_ms AS ms FROM agent_events "
                             "WHERE run_id = %s ORDER BY seq", (run_id,))
        return {**{k: _iso(v) for k, v in run.items()}, "events": events}

    # ------------------------------------------------------------- settings
    def update_settings(self, actor: dict, changes: dict) -> dict:
        try:
            out = self.svc.settings.update(changes)
        except KeyError as e:
            raise BadRequest(f"Unknown setting {e}.") from None
        self.audit(actor, "settings.update", None, changes)
        return out

    # ------------------------------------------------------------- certificates & audit
    def certificates(self) -> list[dict]:
        return _rows(self.db.all("SELECT c.id, c.code, c.level, c.scores, c.revoked, c.issued_at, u.name, u.email "
                                 "FROM certificates c JOIN users u ON u.id = c.user_id ORDER BY c.id DESC"))

    def revoke(self, actor: dict, code: str, revoked: bool) -> dict:
        if not self.db.run("UPDATE certificates SET revoked = %s WHERE code = %s", (revoked, code)):
            raise NotFound("Certificate not found.")
        self.audit(actor, "certificate.revoke" if revoked else "certificate.restore", code)
        return {"code": code, "revoked": revoked}

    def audit_log(self, limit: int = 100) -> list[dict]:
        return _rows(self.db.all("SELECT a.id, a.action, a.target, a.detail, a.created_at, u.name AS actor FROM audit_log a "
                                 "LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.id DESC LIMIT %s", (limit,)))
