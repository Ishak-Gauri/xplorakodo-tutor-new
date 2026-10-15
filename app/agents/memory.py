"""Smriti, the memory agent: lifetime learning memory in pgvector.

Every graded answer becomes a memory ("struggle" or "mastery") with an embedding. Before
grading, the tutor recalls the most similar past attempts of THIS student (cosine distance,
`<=>`), so feedback can say "you found this hard last week" and the router can re-ask weak items.
"""
from __future__ import annotations

from ..db import Database, vec

STRUGGLE_BELOW = 0.6


class Memory:
    name = "Smriti"

    def __init__(self, db: Database, embedder):
        self.db, self.embedder = db, embedder

    def recall(self, user_id: int, text: str, k: int = 3, min_similarity: float = 0.15) -> list[dict]:
        q = vec(self.embedder.embed(text))
        # Exact search inside one student's memories (filter first, then rank by distance).
        rows = self.db.all(
            "WITH mine AS MATERIALIZED (SELECT id, kind, topic_id, skill, question_id, score, text, embedding, created_at "
            "  FROM memories WHERE user_id = %s) "
            "SELECT id, kind, topic_id, skill, question_id, score, text, created_at, "
            "       1 - (embedding <=> %s::vector) AS similarity "
            "FROM mine ORDER BY embedding <=> %s::vector LIMIT %s",
            (user_id, q, q, k))
        return [r for r in rows if r["similarity"] >= min_similarity]

    def store(self, user_id: int, *, topic_id: str, skill: str, question_id: str, score: float,
              question_text: str, answer: str) -> dict:
        kind = "struggle" if score < STRUGGLE_BELOW else "mastery"
        text = f"[{kind}] {question_text} | answer: {answer[:300]} | score {score:.2f}"
        row = self.db.one(
            "INSERT INTO memories(user_id, kind, topic_id, skill, question_id, score, text, embedding) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector) RETURNING id, kind",
            (user_id, kind, topic_id, skill, question_id, score, text, vec(self.embedder.embed(text))))
        return row

    def timeline(self, user_id: int, limit: int = 30) -> list[dict]:
        return self.db.all(
            "SELECT id, kind, topic_id, skill, question_id, score, text, created_at FROM memories "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
