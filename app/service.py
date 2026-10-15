"""Supervisor: wires the agent council into graphs and exposes the use-cases the API needs.

LangGraph graphs run the tutor (app/flows.py adds Ask Sensei and the Course Factory):

  start_session:  guardian → router.topic → smriti.recall → router.pool → supervisor.open
  answer:         guardian → leveler.answer → router.grader → smriti.recall → retriever.rag → tutor.grade
                  → guardian.meter → progress.record → smriti.store → router.next → certifier.check

Each run is traced to LangSmith (when enabled) and to agent_runs / agent_events, and returned to the UI.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .agents.certifier import Certifier
from .agents.graph import END, START, StateGraph, halted, save_trace
from .agents.guardian import Guardian
from .agents.memory import Memory
from .agents.progress import Progress
from .agents.leveler import Leveler
from .agents.retriever import Retriever
from .agents.router import Router
from .agents.tutor import Tutor
from .content import Content, loc
from .db import J, Database
from .kb.store import KnowledgeBase, levels_up_to
from .ml.registry import load_estimator
from .errors import BadRequest, BudgetExceeded, NotFound, Unauthorized
from .llm import MockLLM
from .security import hash_password, verify_password
from .settings_store import SettingsStore

JLPT = {1: "N5", 2: "N4", 3: "N3", 4: "N2", 5: "N1"}
LEVELS = ["Pre-N5", "N5", "N4", "N3", "N2", "N1"]


def jlpt_level(by_level: dict[int, list[bool]]) -> str:
    """Highest JLPT level passed in a row from N5 upward; a level is passed with at least 2 of its 3 items."""
    level = "Pre-N5"
    for d in range(1, 6):
        answers = by_level.get(d, [])
        if not answers or sum(answers) < max(1, (2 * len(answers) + 2) // 3):
            break
        level = JLPT[d]
    return level


def next_level(level: str | None) -> str | None:
    if level not in LEVELS:
        return "N5"
    i = LEVELS.index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


USER_FIELDS = "id, org_id, email, name, role, status, lang, track, level, created_at, last_login_at"


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def public_user(u: dict) -> dict:
    return {k: _iso(u[k]) for k in ("id", "org_id", "email", "name", "role", "status", "lang", "track", "level", "created_at") if k in u}


class TutorService:
    def __init__(self, db: Database, llm, embedder, cert_secret: str):
        self.db = db
        self.content = Content(db)
        self.settings = SettingsStore(db)
        self.llm = llm
        self.embedder = embedder
        self.guardian = Guardian(db, self.settings)
        self.memory = Memory(db, embedder)
        self.kb = KnowledgeBase(db, embedder)
        self.retriever = Retriever(self.kb)
        self.leveler: Leveler | None = None
        self.model_info: dict = {}
        self.reload_leveler()
        self.progress = Progress(db)
        self.router = Router()
        self.tutor = Tutor(MockLLM(), llm)
        self.certifier = Certifier(db, cert_secret)
        self.start_graph = self._build_start_graph()
        self.answer_graph = self._build_answer_graph()

    def reload_leveler(self) -> dict:
        """Load the active JLPT level model (database registry first, bundled file otherwise)."""
        estimator, info = load_estimator(self.db)
        self.leveler, self.model_info = Leveler(estimator), info
        return info

    # =========================================================== users
    def register(self, name: str, email: str, password: str, lang: str, org_id: int | None) -> dict:
        email = email.strip().lower()
        if self.db.one("SELECT 1 FROM users WHERE email = %s", (email,)):
            raise BadRequest("An account with this email already exists.")
        if org_id and not self.db.one("SELECT 1 FROM organizations WHERE id = %s", (org_id,)):
            raise BadRequest("Unknown institute.")
        return self.db.one(
            f"INSERT INTO users(email, password_hash, name, lang, org_id) VALUES (%s,%s,%s,%s,%s) RETURNING {USER_FIELDS}",
            (email, hash_password(password), name.strip(), lang, org_id))

    def login(self, email: str, password: str) -> dict:
        row = self.db.one("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))
        if not row or not verify_password(password, row["password_hash"]):
            raise Unauthorized("Wrong email or password.")
        if row["status"] == "suspended":
            raise Unauthorized("This account is suspended. Contact your institute.")
        self.db.run("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
        return row

    def get_user(self, user_id: int) -> dict:
        u = self.db.one(f"SELECT {USER_FIELDS} FROM users WHERE id = %s", (user_id,))
        if not u:
            raise NotFound("User not found.")
        return u

    def update_profile(self, user: dict, name: str | None, lang: str | None) -> dict:
        self.db.run("UPDATE users SET name = COALESCE(%s, name), lang = COALESCE(%s, lang) WHERE id = %s",
                    (name.strip() if name else None, lang, user["id"]))
        return self.get_user(user["id"])

    def change_password(self, user: dict, current: str, new: str) -> None:
        row = self.db.one("SELECT password_hash FROM users WHERE id = %s", (user["id"],))
        if not verify_password(current, row["password_hash"]):
            raise BadRequest("Current password is wrong.")
        self.db.run("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(new), user["id"]))

    # =========================================================== placement
    def start_placement(self, user: dict) -> dict:
        """A different test for every student: stratified by difficulty, avoiding items seen before."""
        pending = self.db.one("SELECT * FROM placement_attempts WHERE user_id = %s AND status = 'pending' "
                              "ORDER BY id DESC LIMIT 1", (user["id"],))
        if pending:
            return self._placement_payload(pending, user["lang"])
        seen = {i for r in self.db.all("SELECT item_ids FROM placement_attempts WHERE user_id = %s", (user["id"],))
                for i in r["item_ids"]}
        items = self.db.all("SELECT id, difficulty FROM placement_items WHERE active")
        n_prev = len(self.db.all("SELECT 1 FROM placement_attempts WHERE user_id = %s", (user["id"],)))
        rng = random.Random(f"placement:{user['id']}:{n_prev}")
        mix = {1: 3, 2: 3, 3: 3, 4: 3, 5: 3}   # 3 items each for N5, N4, N3, N2, N1
        chosen: list[int] = []
        for diff, k in mix.items():
            pool = [i["id"] for i in items if i["difficulty"] == diff]
            fresh = [i for i in pool if i not in seen]
            rng.shuffle(fresh)
            rest = [i for i in pool if i in seen]
            rng.shuffle(rest)
            chosen += (fresh + rest)[:k]
        rng.shuffle(chosen)
        row = self.db.one("INSERT INTO placement_attempts(user_id, item_ids, total) VALUES (%s,%s,%s) RETURNING *",
                          (user["id"], chosen, len(chosen)))
        return self._placement_payload(row, user["lang"])

    def _placement_payload(self, attempt: dict, lang: str) -> dict:
        rows = {r["id"]: r for r in self.db.all("SELECT id, q, options, difficulty FROM placement_items WHERE id = ANY(%s)",
                                               (attempt["item_ids"],))}
        return {"attempt_id": attempt["id"], "total": attempt["total"],
                "questions": [{"id": i, "q": loc(rows[i]["q"], lang), "difficulty": rows[i]["difficulty"],
                               "options": [loc(o, lang) for o in rows[i]["options"]]} for i in attempt["item_ids"]]}

    def submit_placement(self, user: dict, attempt_id: int, answers: list[int]) -> dict:
        att = self.db.one("SELECT * FROM placement_attempts WHERE id = %s AND user_id = %s", (attempt_id, user["id"]))
        if not att:
            raise NotFound("Placement attempt not found.")
        if att["status"] == "done":
            raise BadRequest("This placement test was already submitted.")
        if len(answers) != att["total"]:
            raise BadRequest(f"Expected {att['total']} answers.")
        key = {r["id"]: r for r in self.db.all("SELECT id, answer, difficulty FROM placement_items WHERE id = ANY(%s)",
                                              (att["item_ids"],))}
        correct = [a == key[i]["answer"] for a, i in zip(answers, att["item_ids"])]
        score = sum(correct)
        by_level: dict[int, list[bool]] = {}
        for ok, i in zip(correct, att["item_ids"]):
            by_level.setdefault(key[i]["difficulty"], []).append(ok)
        level = jlpt_level(by_level)
        with self.db.tx() as conn:
            conn.execute("UPDATE placement_attempts SET answers=%s, score=%s, level=%s, status='done', finished_at=now() "
                         "WHERE id=%s", (answers, score, level, attempt_id))
            conn.execute("UPDATE users SET level = %s WHERE id = %s", (level, user["id"]))
        return {"score": score, "total": att["total"], "level": level, "next_level": next_level(level),
                "by_level": [{"level": JLPT[d], "correct": sum(v), "total": len(v)} for d, v in sorted(by_level.items())],
                "review": [{"id": i, "correct": ok} for ok, i in zip(correct, att["item_ids"])]}

    # =========================================================== topics
    def topics_payload(self, user: dict, kind: str = "practice") -> list[dict]:
        topics = self.content.topics(kind)
        counts = {r["topic_id"]: r["n"] for r in self.db.all(
            "SELECT topic_id, COUNT(*)::int AS n FROM questions WHERE active GROUP BY topic_id")}
        heat = self.progress.heatmap(user["id"], self.content.topics("practice"), user["lang"]) if kind == "practice" else None
        out = []
        for t in topics:
            item = {"id": t["id"], "kind": t["kind"], "title": loc(t["title"], user["lang"]),
                    "summary": loc(t["summary"], user["lang"]) if t["summary"] else "",
                    "vocab": t["vocab"], "questions": counts.get(t["id"], 0),
                    "track": t.get("track", "caregiving"), "jlpt_level": t.get("jlpt_level")}
            if heat:
                item["mastery"] = heat["topic_avg"].get(t["id"])
            out.append(item)
        return out

    # =========================================================== start session graph
    def _build_start_graph(self) -> StateGraph:
        g = StateGraph("start_session")

        def guard(s):
            budget = self.guardian.check(s["user"])
            return {"budget": budget}, f"Allowed. {budget['remaining']} of {budget['budget']} tokens left today.", budget

        def pick_topic(s):
            if s.get("topic_id"):
                t = self.content.topic(s["topic_id"])
                if not t or t["kind"] != s["kind"] or not t["active"]:
                    raise BadRequest("Unknown topic.")
                if s["kind"] == "practice":
                    preview = self._route_topic(s["user"], s["budget"])
                    preview["chosen_by"] = "student"
                    preview["topic_id"] = t["id"]
                    return {"topic": t, "decision": preview}, f"Student chose '{loc(t['title'], 'en')}'.", {"chosen_by": "student"}
                return {"topic": t, "decision": {"chosen_by": "student", "topic_id": t["id"]}}, \
                    f"Interview scenario '{loc(t['title'], 'en')}'.", {}
            decision = self._route_topic(s["user"], s["budget"])
            decision["chosen_by"] = "router"
            t = self.content.topic(decision["topic_id"])
            top = decision["candidates"][:3]
            return {"topic": t, "decision": decision}, \
                f"Chose '{loc(t['title'], 'en')}' ({decision['reason']}), L={top[0]['L']}.", {"top3": top}

        def recall(s):
            mems = self.memory.recall(s["user"]["id"], loc(s["topic"]["title"], "en") + " " +
                                      " ".join(v.get("jp", "") for v in s["topic"]["vocab"]), k=3)
            return {"topic_memories": mems}, f"Recalled {len(mems)} related memories.", \
                {"memories": [{"kind": m["kind"], "similarity": round(m["similarity"], 3)} for m in mems]}

        def pool(s):
            user, topic = s["user"], s["topic"]
            questions = self.content.questions_for_topic(topic["id"])
            history = self.progress.question_history(user["id"])
            skill_avg = self._skill_avg(user["id"], topic["id"])
            session_no = int(self.db.scalar("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user["id"],)) or 0)
            cfg = self.settings.all()
            size = int(cfg["interview_questions"] if s["kind"] == "interview" else cfg["session_questions"])
            built = self.router.build_pool(user_id=user["id"], session_no=session_no, questions=questions, history=history,
                                           skill_avg=skill_avg, level=user.get("level"), size=size)
            if not built["pool"]:
                raise BadRequest("This topic has no active questions yet.")
            states = {}
            for r in built["ranked"][:size]:
                states[r["state"]] = states.get(r["state"], 0) + 1
            return {"pool": built["pool"], "questions": {q["id"]: q for q in questions}, "skill_avg": skill_avg}, \
                f"Drew {len(built['pool'])} of {len(questions)} questions for this student (" + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in states.items()) + ").", \
                {"pool": built["ranked"][:size]}

        def open_session(s):
            user = s["user"]
            first = self.router.next_question([s["questions"][i] for i in s["pool"]], s["skill_avg"], user.get("level"))
            decision = {**s["decision"], "memories": [{"kind": m["kind"], "text": m["text"], "similarity": round(m["similarity"], 3)}
                                                     for m in s["topic_memories"]]}
            with self.db.tx() as conn:
                conn.execute("UPDATE sessions SET status = 'abandoned', finished_at = now() "
                             "WHERE user_id = %s AND status = 'active' AND kind = %s", (user["id"], s["kind"]))
                sid = conn.execute(
                    "INSERT INTO sessions(user_id, kind, topic_id, question_ids, decision) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (user["id"], s["kind"], s["topic"]["id"], s["pool"], J(decision))).fetchone()["id"]
                conn.execute("INSERT INTO turns(session_id, user_id, question_id, idx) VALUES (%s,%s,%s,1)",
                             (sid, user["id"], first["id"]))
            return {"session_id": sid}, f"Opened session #{sid}; first question {first['id']} ({first['skill']}).", {}

        g.add_node("guardian.check", "Guardian", guard)
        g.add_node("router.topic", "AIQ Router", pick_topic)
        g.add_node("smriti.recall", "Smriti", recall)
        g.add_node("router.pool", "AIQ Router", pool)
        g.add_node("supervisor.open", "Supervisor", open_session)
        g.add_edge(START, "guardian.check")
        g.add_conditional("guardian.check", halted, {"stop": END, "go": "router.topic"})
        g.add_edge("router.topic", "smriti.recall")
        g.add_edge("smriti.recall", "router.pool")
        g.add_edge("router.pool", "supervisor.open")
        g.add_edge("supervisor.open", END)
        return g

    def _route_topic(self, user: dict, budget: dict) -> dict:
        topics = self.content.topics("practice")
        qbt = {t["id"]: self.content.questions_for_topic(t["id"]) for t in topics}
        last = self.db.one("SELECT topic_id FROM sessions WHERE user_id = %s AND kind = 'practice' ORDER BY id DESC LIMIT 1",
                           (user["id"],))
        cfg = self.settings.all()
        decision = self.router.select_topic(
            topics=topics, questions_by_topic=qbt, aggregates=self.progress.aggregates(user["id"]),
            history=self.progress.question_history(user["id"]), last_topic=last["topic_id"] if last else None,
            level=user.get("level"), tokens_left=budget["remaining"], session_size=int(cfg["session_questions"]),
            weights=cfg["router"])
        decision["titles"] = {t["id"]: loc(t["title"], user.get("lang", "en")) for t in topics}
        return decision

    def _skill_avg(self, user_id: int, topic_id: str) -> dict[str, float]:
        return {r["skill"]: r["avg"] for r in self.progress.aggregates(user_id) if r["topic_id"] == topic_id}

    def start_session(self, user: dict, kind: str = "practice", topic_id: str | None = None) -> dict:
        state, trace = self.start_graph.run({"user": user, "kind": kind, "topic_id": topic_id},
                                            metadata={"user_id": user["id"], "kind": kind})
        run_id = save_trace(self.db, trace, user["id"], state.get("session_id"))
        if state.get("error"):
            raise state["error"]
        if state.get("halt"):
            raise state["halt"]
        out = self.session_state(user, state["session_id"])
        out["trace"] = trace.public(run_id)
        return out

    # =========================================================== answer graph
    def _build_answer_graph(self) -> StateGraph:
        g = StateGraph("answer")

        def guard(s):
            budget = self.guardian.check(s["user"])
            flags = self.guardian.scan(s["text"])
            return {"budget": budget, "flags": flags}, \
                f"Allowed; {budget['remaining']} tokens left." + (f" Flags: {', '.join(flags)}." if flags else " No flags."), \
                {**budget, "flags": flags}

        def level_answer(s):
            r = self.leveler.estimate(s["text"])
            if not r["japanese"]:
                return {"answer_level": None}, "Answer has no Japanese; level not estimated.", {}
            return {"answer_level": r["level"]}, \
                f"Student's Japanese reads as JLPT {r['level']} ({r['confidence']:.0%}, {r['method']}).", \
                {"level": r["level"], "probs": r["probs"], "hardest": r["hardest"]}

        def grader(s):
            use_llm, why = self.router.select_grader(self.llm, s["budget"]["share_left"],
                                                     float(self.settings.get("llm_min_budget_share")))
            return {"use_llm": use_llm}, why, {"use_llm": use_llm}

        def recall(s):
            q = s["question"]
            mems = self.memory.recall(s["user"]["id"], q["prompt"].get("en", "") + " " + s["text"], k=3)
            return {"memories": mems}, f"{len(mems)} similar past attempts" + (
                f"; closest is a {mems[0]['kind']} (sim {mems[0]['similarity']:.2f})." if mems else "."), \
                {"memories": [{"kind": m["kind"], "question_id": m["question_id"], "score": m["score"],
                               "similarity": round(m["similarity"], 3)} for m in mems]}

        def rag(s):
            q = s["question"]
            levels = levels_up_to(s["user"].get("level"))
            chunks = self.retriever.search(q["prompt"].get("en", "") + " " + loc(q["model_answer"], "en"), q["topic_id"],
                                           levels=levels, k=3)
            return {"knowledge": chunks}, f"Retrieved {len(chunks)} knowledge-base documents (levels ≤ {levels[-1]}).", \
                {"chunks": [{"source": c["source"], "level": c["level"], "score": c["score"], "text": c["text"][:140]} for c in chunks]}

        def grade(s):
            persona = "proctor" if s["session"]["kind"] == "interview" else "tutor"
            res = self.tutor.grade(s["question"], s["text"], s["user"]["lang"], persona=persona, use_llm=s["use_llm"],
                                   memories=s["memories"], knowledge=s["knowledge"], flags=s["flags"])
            return {"result": res, "tokens": s["tokens"] + int(res.get("tokens", 0))}, \
                f"{'Interview Proctor' if persona == 'proctor' else 'Kaigo Sensei'} scored {res['score']:.2f} via {res['grader']}.", \
                {"score": round(res["score"], 3), "grader": res["grader"], "memory_note": res.get("memory_note")}

        def meter(s):
            self.guardian.spend(s["user"]["id"], s["tokens"])
            return {}, f"Charged {s['tokens']} tokens to today's budget.", {"tokens": s["tokens"]}

        def record(s):
            res, q = s["result"], s["question"]
            self.db.run("UPDATE turns SET answer=%s, score=%s, feedback=%s, probe=%s, grader=%s, flags=%s, latency_ms=%s, "
                        "answer_level=%s, answered_at=now() WHERE id=%s",
                        (s["text"], res["score"], res["feedback"], loc(q["probe"], s["user"]["lang"]), res["grader"],
                         J(s["flags"]), s.get("latency_ms"), s.get("answer_level"), s["turn"]["id"]))
            return {}, f"Recorded {q['skill']} score {res['score']:.2f} for {q['topic_id']}.", {}

        def store(s):
            q = s["question"]
            m = self.memory.store(s["user"]["id"], topic_id=q["topic_id"], skill=q["skill"], question_id=q["id"],
                                  score=s["result"]["score"], question_text=q["prompt"].get("en", ""), answer=s["text"])
            return {}, f"Stored a '{m['kind']}' memory (#{m['id']}) with its embedding.", {"kind": m["kind"]}

        def next_q(s):
            sess, user = s["session"], s["user"]
            answered = {r["question_id"] for r in self.db.all("SELECT question_id FROM turns WHERE session_id = %s", (sess["id"],))}
            remaining_ids = [i for i in sess["question_ids"] if i not in answered]
            remaining = [q for q in (self.content.question(i) for i in remaining_ids) if q and q["active"]]
            skill_avg = self._skill_avg(user["id"], sess["topic_id"])
            nxt = self.router.next_question(remaining, skill_avg, user.get("level"))
            if nxt:
                self.db.run("INSERT INTO turns(session_id, user_id, question_id, idx) VALUES (%s,%s,%s,%s)",
                            (sess["id"], user["id"], nxt["id"], len(answered) + 1))
                return {"done": False}, f"Next: {nxt['id']} ({nxt['skill']}), weakest skill first.", {"next": nxt["id"]}
            avg = float(self.db.scalar("SELECT AVG(score) FROM turns WHERE session_id = %s AND score IS NOT NULL", (sess["id"],)) or 0)
            passed = avg >= float(self.settings.get("interview_pass")) if sess["kind"] == "interview" else None
            self.db.run("UPDATE sessions SET status='done', finished_at=now(), avg_score=%s, passed=%s WHERE id=%s",
                        (avg, passed, sess["id"]))
            return {"done": True}, f"Session complete, average {avg:.2f}" + (
                f", interview {'PASSED' if passed else 'not passed'}." if passed is not None else "."), {"avg": round(avg, 3)}

        def cert_check(s):
            user = self.get_user(s["user"]["id"])
            heat = self.progress.heatmap(user["id"], self.content.topics("practice"))
            elig = self.certifier.eligibility(user, heat, self.settings.all())
            ok = sum(1 for c in elig["checks"] if c["ok"])
            return {"eligibility": elig}, f"Certificate readiness {ok}/{len(elig['checks'])} checks" + (
                " - ELIGIBLE." if elig["eligible"] else "."), {"eligible": elig["eligible"]}

        g.add_node("guardian.check", "Guardian", guard)
        g.add_node("leveler.answer", "Leveler", level_answer)
        g.add_node("router.grader", "AIQ Router", grader)
        g.add_node("smriti.recall", "Smriti", recall)
        g.add_node("retriever.rag", "Retriever", rag)
        g.add_node("tutor.grade", "Tutor", grade)
        g.add_node("guardian.meter", "Guardian", meter)
        g.add_node("progress.record", "Progress", record)
        g.add_node("smriti.store", "Smriti", store)
        g.add_node("router.next", "AIQ Router", next_q)
        g.add_node("certifier.check", "Certifier", cert_check)
        g.add_edge(START, "guardian.check")
        g.add_conditional("guardian.check", halted, {"stop": END, "go": "leveler.answer"})
        g.add_edge("leveler.answer", "router.grader")
        g.add_edge("router.grader", "smriti.recall")
        g.add_edge("smriti.recall", "retriever.rag")
        g.add_edge("retriever.rag", "tutor.grade")
        g.add_edge("tutor.grade", "guardian.meter")
        g.add_edge("guardian.meter", "progress.record")
        g.add_edge("progress.record", "smriti.store")
        g.add_edge("smriti.store", "router.next")
        g.add_conditional("router.next", lambda s: "done" if s.get("done") else "more", {"done": "certifier.check", "more": END})
        g.add_edge("certifier.check", END)
        return g

    def _own_session(self, user: dict, session_id: int) -> dict:
        sess = self.db.one("SELECT * FROM sessions WHERE id = %s", (session_id,))
        if not sess or (sess["user_id"] != user["id"] and user["role"] != "admin"):
            raise NotFound("Session not found.")
        return sess

    def answer(self, user: dict, session_id: int, text: str, latency_ms: int | None = None) -> dict:
        sess = self._own_session(user, session_id)
        if sess["user_id"] != user["id"]:
            raise BadRequest("Only the student can answer.")
        if sess["status"] != "active":
            raise BadRequest("This session is finished. Start a new one.")
        if not text or not text.strip():
            raise BadRequest("Answer is empty.")
        turn = self.db.one("SELECT * FROM turns WHERE session_id = %s AND answer IS NULL ORDER BY idx DESC LIMIT 1", (session_id,))
        if not turn:
            raise BadRequest("No open question in this session.")
        question = self.content.question(turn["question_id"])
        user = self.get_user(user["id"])
        state, trace = self.answer_graph.run({"user": user, "session": sess, "turn": turn, "question": question,
                                              "text": text.strip(), "latency_ms": latency_ms},
                                             metadata={"user_id": user["id"], "session_id": session_id, "question_id": question["id"]})
        run_id = save_trace(self.db, trace, user["id"], session_id)
        if state.get("error"):
            raise state["error"]
        if state.get("halt"):
            raise state["halt"]
        res = state["result"]
        out = self.session_state(user, session_id)
        out["result"] = {"score": round(res["score"], 2), "feedback": res["feedback"], "skill": question["skill"],
                         "probe": loc(question["probe"], user["lang"]), "grader": res["grader"],
                         "memory_note": res.get("memory_note"), "answer_level": state.get("answer_level"),
                         "model_answer": loc(question["model_answer"], user["lang"]) if res["score"] < 0.8 else None}
        out["eligibility"] = state.get("eligibility")
        out["trace"] = trace.public(run_id)
        return out

    def abandon(self, user: dict, session_id: int) -> dict:
        sess = self._own_session(user, session_id)
        if sess["status"] == "active":
            self.db.run("UPDATE sessions SET status='abandoned', finished_at=now() WHERE id=%s", (session_id,))
        return {"ok": True}

    def session_state(self, user: dict, session_id: int) -> dict:
        sess = self._own_session(user, session_id)
        owner = self.get_user(sess["user_id"])
        lang = user["lang"] if user["id"] == owner["id"] else "en"
        topic = self.content.topic(sess["topic_id"])
        turns = self.db.all("SELECT * FROM turns WHERE session_id = %s ORDER BY idx", (session_id,))
        history, current = [], None
        for t in turns:
            q = self.content.question(t["question_id"])
            if t["answer"] is None:
                current = {"id": q["id"], "skill": q["skill"], "difficulty": q["difficulty"],
                           "prompt": loc(q["prompt"], lang), "prompt_en": q["prompt"].get("en", ""),
                           "prompt_ja": q["prompt"].get("ja", ""), "index": t["idx"], "total": len(sess["question_ids"])}
            else:
                history.append({"index": t["idx"], "question_id": q["id"], "question": loc(q["prompt"], lang),
                                "skill": q["skill"], "answer": t["answer"], "score": round(t["score"], 2),
                                "feedback": t["feedback"], "probe": t["probe"], "grader": t["grader"],
                                "flags": t["flags"], "latency_ms": t["latency_ms"], "answer_level": t.get("answer_level")})
        return {"session_id": sess["id"], "kind": sess["kind"], "status": sess["status"],
                "topic": {"id": topic["id"], "title": loc(topic["title"], lang),
                          "summary": loc(topic["summary"], lang) if topic["summary"] else "", "vocab": topic["vocab"]},
                "total": len(sess["question_ids"]), "answered": len(history), "question": current, "history": history,
                "avg_score": None if sess["avg_score"] is None else round(sess["avg_score"], 2), "passed": sess["passed"],
                "decision": sess["decision"], "created_at": _iso(sess["created_at"])}

    # =========================================================== dashboard & progress
    def heatmap(self, user: dict) -> dict:
        return self.progress.heatmap(user["id"], self.content.topics("practice"), user["lang"])

    def streak(self, user_id: int) -> int:
        days = {r["d"] for r in self.db.all(
            "SELECT DISTINCT (answered_at AT TIME ZONE 'UTC')::date AS d FROM turns WHERE user_id = %s AND answered_at IS NOT NULL",
            (user_id,))}
        n, d = 0, date.today()
        if d not in days:
            d -= timedelta(days=1)
        while d in days:
            n += 1
            d -= timedelta(days=1)
        return n

    def dashboard(self, user: dict) -> dict:
        user = self.get_user(user["id"])
        heat = self.heatmap(user)
        cfg = self.settings.all()
        stats = self.db.one(
            "SELECT COUNT(DISTINCT s.id)::int AS sessions, COUNT(t.score)::int AS answers, AVG(t.score)::float AS avg, "
            "AVG(t.latency_ms)::float AS latency FROM sessions s LEFT JOIN turns t ON t.session_id = s.id WHERE s.user_id = %s",
            (user["id"],))
        used = self.guardian.used_today(user["id"])
        active = self.db.all("SELECT id, kind, topic_id, question_ids, created_at FROM sessions WHERE user_id = %s AND status='active' "
                             "ORDER BY id DESC", (user["id"],))
        recent = self.db.all(
            "SELECT s.id, s.kind, s.topic_id, s.status, s.avg_score, s.passed, s.created_at, "
            "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id AND t.score IS NOT NULL)::int AS answered "
            "FROM sessions s WHERE s.user_id = %s ORDER BY s.id DESC LIMIT 8", (user["id"],))
        titles = {t["id"]: loc(t["title"], user["lang"]) for t in self.content.topics("practice") + self.content.topics("interview")}
        recommendation = None
        try:
            budget = self.guardian.check(user)
            rec = self._route_topic(user, budget)
            recommendation = {"topic_id": rec["topic_id"], "title": titles.get(rec["topic_id"]), "reason": rec["reason"],
                              "candidates": [{**c, "title": titles.get(c["topic_id"])} for c in rec["candidates"]]}
        except BudgetExceeded as e:
            recommendation = {"blocked": str(e), "code": e.code}
        cert = self.db.one("SELECT code, issued_at, revoked FROM certificates WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user["id"],))
        return {
            "user": public_user(user),
            "stats": {"sessions": stats["sessions"], "answers": stats["answers"],
                      "avg": round(stats["avg"], 2) if stats["avg"] is not None else None,
                      "latency_ms": int(stats["latency"]) if stats["latency"] else None,
                      "streak": self.streak(user["id"]), "tokens_today": used, "budget": int(cfg["daily_token_budget"])},
            "heatmap": heat,
            "recommendation": recommendation,
            "active": [{"id": a["id"], "kind": a["kind"], "topic_id": a["topic_id"], "title": titles.get(a["topic_id"]),
                        "total": len(a["question_ids"])} for a in active],
            "recent": [{**r, "title": titles.get(r["topic_id"]), "created_at": _iso(r["created_at"]),
                        "avg_score": None if r["avg_score"] is None else round(r["avg_score"], 2)} for r in recent],
            "eligibility": self.certifier.eligibility(user, heat, cfg),
            "certificate": {**cert, "issued_at": _iso(cert["issued_at"])} if cert else None,
        }

    def history(self, user: dict, limit: int = 50) -> list[dict]:
        titles = {t["id"]: loc(t["title"], user["lang"]) for t in self.content.topics("practice") + self.content.topics("interview")}
        rows = self.db.all(
            "SELECT s.id, s.kind, s.topic_id, s.status, s.avg_score, s.passed, s.created_at, s.finished_at, "
            "array_length(s.question_ids, 1) AS total, "
            "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id AND t.score IS NOT NULL)::int AS answered "
            "FROM sessions s WHERE s.user_id = %s ORDER BY s.id DESC LIMIT %s", (user["id"], limit))
        return [{**r, "title": titles.get(r["topic_id"]), "created_at": _iso(r["created_at"]),
                 "finished_at": _iso(r["finished_at"]),
                 "avg_score": None if r["avg_score"] is None else round(r["avg_score"], 2)} for r in rows]

    def memories(self, user: dict) -> list[dict]:
        return [{**m, "created_at": _iso(m["created_at"])} for m in self.memory.timeline(user["id"], 40)]

    # =========================================================== certificates
    def claim_certificate(self, user: dict) -> dict:
        user = self.get_user(user["id"])
        heat = self.progress.heatmap(user["id"], self.content.topics("practice"), "en")
        elig = self.certifier.eligibility(user, heat, self.settings.all())
        if not elig["eligible"]:
            raise BadRequest("Not eligible yet: " + "; ".join(c.get("label", c["key"]) for c in elig["checks"] if not c["ok"]))
        best = self.db.scalar("SELECT MAX(avg_score) FROM sessions WHERE user_id = %s AND kind='interview' AND passed", (user["id"],))
        cert = self.certifier.issue(user, heat, round(best, 2) if best is not None else None)
        return {"code": cert["code"], "issued_at": _iso(cert["issued_at"])}
