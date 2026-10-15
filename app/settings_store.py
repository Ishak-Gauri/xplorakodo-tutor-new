"""Runtime settings an admin can change from the console. Stored in the `settings` table."""
from __future__ import annotations

from .db import J, Database

DEFAULTS: dict = {
    "kill_switch": False,              # pause every tutor/interview call
    "daily_token_budget": 20000,       # per student per day (LLM tokens, estimated for mock)
    "session_questions": 5,            # questions per practice session (drawn per student)
    "interview_questions": 5,          # questions per mock interview
    "interview_pass": 0.7,             # average score needed to pass the interview proctor
    "cert_min_mastery": 0.7,           # every practice topic must reach this average
    "cert_min_attempts": 2,            # ...with at least this many graded answers per topic
    "llm_min_budget_share": 0.2,       # below this share of budget left, route grading to the deterministic grader
    # AIQ router: L = NB(t) - sum(lambda_k * C_k(t))
    "router": {
        "w_gap": 0.7, "w_novelty": 0.15, "w_spacing": 0.15,
        "lambda_cost": 0.3, "lambda_repeat": 0.1, "lambda_fit": 0.15,
    },
}

EDITABLE = set(DEFAULTS)


class SettingsStore:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> dict:
        stored = {r["key"]: r["value"] for r in self.db.all("SELECT key, value FROM settings")}
        out = {}
        for k, default in DEFAULTS.items():
            v = stored.get(k, default)
            if isinstance(default, dict) and isinstance(v, dict):
                v = {**default, **v}
            out[k] = v
        return out

    def get(self, key: str):
        return self.all()[key]

    def update(self, changes: dict) -> dict:
        current = self.all()
        for k, v in changes.items():
            if k not in EDITABLE:
                raise KeyError(k)
            if isinstance(DEFAULTS[k], dict):
                v = {**current[k], **{kk: float(vv) for kk, vv in v.items() if kk in DEFAULTS[k]}}
            elif isinstance(DEFAULTS[k], bool):
                v = bool(v)
            elif isinstance(DEFAULTS[k], int):
                v = int(v)
            elif isinstance(DEFAULTS[k], float):
                v = float(v)
            self.db.run(
                "INSERT INTO settings(key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (k, J(v)),
            )
        return self.all()
