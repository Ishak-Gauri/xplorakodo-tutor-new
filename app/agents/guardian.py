"""Guardian agent: kill switch, account status, per-student daily token budget (persistent),
and a prompt-injection scan of every answer before it reaches a model."""
from __future__ import annotations

import re

from ..db import Database
from ..errors import BudgetExceeded
from ..settings_store import SettingsStore

INJECTION = re.compile(
    r"(ignore\s+(all\s+|the\s+|any\s+)?(previous|above|prior|earlier)\s+(instructions?|prompts?|rules?)"
    r"|disregard\s+(the|all|your)|system\s+prompt|you\s+are\s+now|act\s+as\s+(an?\s+)?(admin|grader|system)"
    r"|(give|award|set)\s+(me\s+)?(a\s+)?(full\s+marks|score\s+of|100%|perfect\s+score)|score\s*[:=]\s*1(\.0)?\b"
    r"|以前の指示を無視|前の指示を無視|पहिलेका\s*निर्देशन)",
    re.IGNORECASE,
)


class Guardian:
    name = "Guardian"

    def __init__(self, db: Database, settings: SettingsStore):
        self.db, self.settings = db, settings

    def used_today(self, user_id: int) -> int:
        return int(self.db.scalar("SELECT tokens FROM token_usage WHERE user_id=%s AND day=CURRENT_DATE", (user_id,)) or 0)

    def check(self, user: dict) -> dict:
        cfg = self.settings.all()
        if cfg["kill_switch"]:
            raise BudgetExceeded("The tutor is paused by an administrator.", "kill_switch")
        if user.get("status") == "suspended":
            raise BudgetExceeded("This account is suspended. Contact your institute.", "suspended")
        budget = int(cfg["daily_token_budget"])
        used = self.used_today(user["id"])
        if used >= budget:
            raise BudgetExceeded("Daily practice budget reached. Please continue tomorrow.", "budget")
        return {"budget": budget, "used": used, "remaining": budget - used,
                "share_left": round((budget - used) / budget, 3) if budget else 0.0}

    @staticmethod
    def scan(text: str) -> list[str]:
        flags = []
        if INJECTION.search(text or ""):
            flags.append("prompt_injection")
        if len(text or "") > 1500:
            flags.append("very_long")
        return flags

    def spend(self, user_id: int, tokens: int) -> None:
        self.db.run(
            "INSERT INTO token_usage(user_id, day, tokens, calls) VALUES (%s, CURRENT_DATE, %s, 1) "
            "ON CONFLICT (user_id, day) DO UPDATE SET tokens = token_usage.tokens + EXCLUDED.tokens, "
            "calls = token_usage.calls + 1", (user_id, int(tokens)))
