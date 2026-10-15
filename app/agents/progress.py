"""Progress agent: turns graded answers into skill mastery and the topic x skill heatmap (pure SQL)."""
from __future__ import annotations

from ..content import SKILLS, loc
from ..db import Database

WEAK_BELOW = 0.6


class Progress:
    name = "Progress"

    def __init__(self, db: Database):
        self.db = db

    def aggregates(self, user_id: int) -> list[dict]:
        return self.db.all(
            "SELECT q.topic_id, q.skill, AVG(t.score)::float AS avg, COUNT(*)::int AS n, MAX(t.answered_at) AS last_at "
            "FROM turns t JOIN sessions s ON s.id = t.session_id JOIN questions q ON q.id = t.question_id "
            "WHERE t.user_id = %s AND t.score IS NOT NULL AND s.kind = 'practice' "
            "GROUP BY q.topic_id, q.skill", (user_id,))

    def question_history(self, user_id: int) -> dict[str, dict]:
        rows = self.db.all(
            "SELECT question_id, COUNT(*)::int AS n, (ARRAY_AGG(score ORDER BY answered_at DESC))[1]::float AS last_score, "
            "MAX(answered_at) AS last_at FROM turns WHERE user_id = %s AND score IS NOT NULL GROUP BY question_id",
            (user_id,))
        return {r["question_id"]: r for r in rows}

    def heatmap(self, user_id: int, topics: list[dict], lang: str = "en") -> dict:
        agg = {(r["topic_id"], r["skill"]): r for r in self.aggregates(user_id)}
        cells, weakest, total, n_all = {}, [], 0.0, 0
        for t in topics:
            cells[t["id"]] = {}
            for skill in SKILLS:
                row = agg.get((t["id"], skill))
                if row is None:
                    cells[t["id"]][skill] = None
                    continue
                cells[t["id"]][skill] = {"avg": round(row["avg"], 2), "n": row["n"]}
                total += row["avg"] * row["n"]
                n_all += row["n"]
                if row["avg"] < WEAK_BELOW:
                    weakest.append({"topic": t["id"], "skill": skill, "avg": round(row["avg"], 2)})
        weakest.sort(key=lambda w: w["avg"])
        topic_avg = {}
        for t in topics:
            vals = [(c["avg"], c["n"]) for c in cells[t["id"]].values() if c]
            n = sum(v[1] for v in vals)
            topic_avg[t["id"]] = {"avg": round(sum(a * k for a, k in vals) / n, 2) if n else None, "n": n}
        return {"skills": SKILLS,
                "topics": [{"id": t["id"], "title": loc(t["title"], lang), "track": t.get("track", "caregiving"),
                            "jlpt_level": t.get("jlpt_level")} for t in topics],
                "cells": cells, "weakest": weakest, "topic_avg": topic_avg,
                "overall": round(total / n_all, 2) if n_all else None, "answers": n_all}
