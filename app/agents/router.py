"""AIQ Router: deterministic decisions, LLMs only as callable assets.

Every routing choice maximises a Lagrangian of the Net Benefit of an option:

    L_k = NB_k(t) - sum_j lambda_j * C_jk(t)

    NB_k  = w_gap * learning gap  +  w_novelty * unseen share  +  w_spacing * review due
    C_cost   = expected tokens of a session / tokens left today
    C_repeat = 1 if the student just practised this topic
    C_fit    = distance between the topic's difficulty and the student's level

Same inputs, same output: no sampling, so a decision can be replayed and explained.
The full candidate table is stored with the session and shown in the UI ("why this topic?").
Weights and lambdas are editable by an admin (settings.router).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

# Question/topic difficulty 1..5 = JLPT N5..N1. A student's level maps to the difficulty they should work at.
LEVEL_TARGET = {None: 1.3, "Pre-N5": 1.0, "N5": 1.4, "N4": 2.2, "N3": 3.1, "N2": 4.0, "N1": 4.8,
                "N5-Foundation": 1.0, "N4-Ready": 2.2}  # last two: labels used by v3.0
UNPRACTISED_GAP = 0.35      # prior "gap" for a topic with no data
UNPRACTISED_SPACING = 0.5   # neutral review-due value for a topic with no data
TOKENS_PER_QUESTION = 350


def _hours_since(ts) -> float | None:
    if ts is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600)


class Router:
    name = "AIQ Router"

    # ---- which topic -----------------------------------------------------------
    def select_topic(self, *, topics: list[dict], questions_by_topic: dict[str, list[dict]], aggregates: list[dict],
                     history: dict[str, dict], last_topic: str | None, level: str | None,
                     tokens_left: int, session_size: int, weights: dict) -> dict:
        target = LEVEL_TARGET.get(level, 1.5)
        by_topic: dict[str, list[dict]] = {}
        for r in aggregates:
            by_topic.setdefault(r["topic_id"], []).append(r)
        candidates = []
        for pos, t in enumerate(topics):
            qs = questions_by_topic.get(t["id"], [])
            if not qs:
                continue
            rows = by_topic.get(t["id"], [])
            n = sum(r["n"] for r in rows)
            mastery = sum(r["avg"] * r["n"] for r in rows) / n if n else None
            gap = (1 - mastery) if mastery is not None else UNPRACTISED_GAP
            novelty = sum(1 for q in qs if q["id"] not in history) / len(qs)
            last = max((r["last_at"] for r in rows if r["last_at"]), default=None)
            hours = _hours_since(last)
            spacing = UNPRACTISED_SPACING if hours is None else 1 - math.exp(-hours / 24)
            avg_diff = sum(q["difficulty"] for q in qs) / len(qs)
            exp_tokens = session_size * TOKENS_PER_QUESTION * (0.8 + 0.2 * avg_diff)
            c_cost = min(1.0, exp_tokens / max(1, tokens_left))
            c_repeat = 1.0 if t["id"] == last_topic else 0.0
            c_fit = abs(avg_diff - target) / 2
            nb = weights["w_gap"] * gap + weights["w_novelty"] * novelty + weights["w_spacing"] * spacing
            lag = nb - weights["lambda_cost"] * c_cost - weights["lambda_repeat"] * c_repeat - weights["lambda_fit"] * c_fit
            candidates.append({
                "topic_id": t["id"], "position": pos,
                "mastery": None if mastery is None else round(mastery, 3), "answers": n,
                "gain": {"gap": round(gap, 3), "novelty": round(novelty, 3), "spacing": round(spacing, 3)},
                "constraints": {"cost": round(c_cost, 3), "repeat": c_repeat, "fit": round(c_fit, 3)},
                "nb": round(nb, 4), "L": round(lag, 4),
            })
        candidates.sort(key=lambda c: (-c["L"], c["position"]))
        best = candidates[0]
        reason = "weak_spot" if best["mastery"] is not None and best["mastery"] < 0.6 else \
            "new_material" if best["mastery"] is None else "review_due"
        return {"topic_id": best["topic_id"], "reason": reason, "candidates": candidates,
                "formula": "L = NB(t) - Σ λk·Ck(t)", "weights": weights, "level_target": target}

    # ---- which questions, for THIS student --------------------------------------
    def build_pool(self, *, user_id: int, session_no: int, questions: list[dict], history: dict[str, dict],
                   skill_avg: dict[str, float], level: str | None, size: int) -> dict:
        target = LEVEL_TARGET.get(level, 1.5)
        rng = random.Random(f"{user_id}:{session_no}")      # different per student and per session
        scored = []
        for q in questions:
            h = history.get(q["id"])
            if h is None:
                base, state = 1.0, "unseen"
            elif h["last_score"] < 0.6:
                base, state = 1.4, "retry_weak"   # failed before: re-ask first (retrieval practice)
            elif h["last_score"] < 0.8:
                base, state = 0.45, "consolidate"
            else:
                base, state = 0.1, "mastered"
            weakness = 1 - skill_avg.get(q["skill"], 0.5)
            fit = abs(q["difficulty"] - target)
            jitter = rng.random() * 0.3
            score = base + 0.35 * weakness - 0.25 * fit + jitter
            scored.append({"id": q["id"], "skill": q["skill"], "difficulty": q["difficulty"], "state": state,
                           "score": round(score, 3)})
        scored.sort(key=lambda s: -s["score"])
        return {"pool": [s["id"] for s in scored[:size]], "ranked": scored}

    def next_question(self, remaining: list[dict], skill_avg: dict[str, float], level: str | None) -> dict | None:
        if not remaining:
            return None
        target = LEVEL_TARGET.get(level, 1.5)
        # Ask the weakest skill first; ties keep the pool order.
        return max(enumerate(remaining),
                   key=lambda iq: ((1 - skill_avg.get(iq[1]["skill"], 0.5)) - 0.25 * abs(iq[1]["difficulty"] - target), -iq[0]))[1]

    # ---- which grader -------------------------------------------------------------
    @staticmethod
    def select_grader(llm, share_left: float, min_share: float) -> tuple[bool, str]:
        if not getattr(llm, "is_llm", False):
            return False, "No LLM configured: deterministic grader."
        if share_left < min_share:
            return False, f"Budget share left {share_left:.0%} < {min_share:.0%}: routed to deterministic grader."
        return True, f"LLM ({llm.name}) selected; budget share left {share_left:.0%}."
