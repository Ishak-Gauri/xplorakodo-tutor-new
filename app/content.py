"""Curriculum access (topics, questions, placement items) backed by PostgreSQL.

The JSON files in data/ are only the *seed*; after the first start the database is the
source of truth, and admins edit questions from the console.
"""
from __future__ import annotations

from .db import Database

SKILLS = ["vocabulary", "grammar", "comprehension", "recall"]
LANGS = ("en", "ne", "ja")


def loc(value, lang: str) -> str:
    """Pick the text for a language from {"en":..,"ne":..,"ja":..}; fall back to English."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(iter(value.values()), "")
    return value or ""


class Content:
    def __init__(self, db: Database):
        self.db = db

    # topics
    def topics(self, kind: str = "practice", include_inactive: bool = False) -> list[dict]:
        sql = "SELECT * FROM topics WHERE kind = %s" + ("" if include_inactive else " AND active") + " ORDER BY position, id"
        return self.db.all(sql, (kind,))

    def topic(self, topic_id: str) -> dict | None:
        return self.db.one("SELECT * FROM topics WHERE id = %s", (topic_id,))

    # questions
    def question(self, question_id: str) -> dict | None:
        return self.db.one(
            "SELECT id, topic_id, skill, difficulty, prompt, keywords, model_answer, probe, active "
            "FROM questions WHERE id = %s", (question_id,))

    def questions_for_topic(self, topic_id: str) -> list[dict]:
        return self.db.all(
            "SELECT id, topic_id, skill, difficulty, prompt, keywords, model_answer, probe "
            "FROM questions WHERE topic_id = %s AND active ORDER BY length(id), id", (topic_id,))

    def topic_skills(self) -> list[str]:
        return SKILLS
