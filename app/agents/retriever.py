"""Retriever agent: RAG over the five-level knowledge base (pgvector HNSW + exact word/kanji hits)."""
from __future__ import annotations

from ..kb.store import KnowledgeBase
from ..observability import traceable


class Retriever:
    name = "Retriever"

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    @traceable(name="kb_retrieve", run_type="retriever")
    def search(self, text: str, topic_id: str | None = None, levels: list[str] | None = None,
               kinds: list[str] | None = None, k: int = 4) -> list[dict]:
        rows = self.kb.search(text, levels=levels, kinds=kinds, k=k * 2)
        for r in rows:  # light re-rank: prefer the lesson's own topic
            r["rank"] = r["score"] + (0.08 if topic_id and (r.get("meta") or {}).get("topic_id") == topic_id else 0.0)
        rows.sort(key=lambda r: r["rank"], reverse=True)
        return rows[:k]
