"""Knowledge base: documents for every JLPT level in PostgreSQL + pgvector, with level-aware search."""
from __future__ import annotations

from ..db import J, Database, vec

LEVELS = ["N5", "N4", "N3", "N2", "N1"]
STUDENT_LEVELS = ["Pre-N5", "N5", "N4", "N3", "N2", "N1"]


def levels_up_to(student_level: str | None, stretch: int = 1) -> list[str]:
    """Levels a student should see: everything up to their level plus `stretch` levels above it."""
    if student_level not in STUDENT_LEVELS:
        idx = 1
    else:
        idx = max(1, STUDENT_LEVELS.index(student_level))
    top = min(len(LEVELS), idx + stretch)
    return LEVELS[:top]


class KnowledgeBase:
    def __init__(self, db: Database, embedder):
        self.db, self.embedder = db, embedder

    # ------------------------------------------------------------------ write
    def upsert(self, docs: list[dict], batch: int = 500, progress=None) -> int:
        """Insert or update documents (unique on source + ext_id). Returns how many were written."""
        written = 0
        for start in range(0, len(docs), batch):
            chunk = docs[start:start + batch]
            vectors = self.embedder.embed_many([f"{d['title']} {d['text']}"[:2000] for d in chunk])
            rows = [(d["source"], d["ext_id"], d["kind"], d.get("level"), d["title"][:300], d["text"][:4000],
                     d["license"], d.get("url"), J(d.get("meta", {})), vec(v)) for d, v in zip(chunk, vectors)]
            with self.db.tx() as conn, conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO kb_documents(source, ext_id, kind, level, title, text, license, url, meta, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector) ON CONFLICT (source, ext_id) DO UPDATE SET "
                    "kind = EXCLUDED.kind, level = EXCLUDED.level, title = EXCLUDED.title, text = EXCLUDED.text, "
                    "license = EXCLUDED.license, url = EXCLUDED.url, meta = EXCLUDED.meta, embedding = EXCLUDED.embedding",
                    rows)
            written += len(rows)
            if progress:
                progress(written, len(docs))
        return written

    def count(self, source: str | None = None) -> int:
        if source:
            return int(self.db.scalar("SELECT COUNT(*) FROM kb_documents WHERE source = %s", (source,)) or 0)
        return int(self.db.scalar("SELECT COUNT(*) FROM kb_documents") or 0)

    # ------------------------------------------------------------------ read
    def search(self, query: str, levels: list[str] | None = None, kinds: list[str] | None = None,
               k: int = 5, include_general: bool = True) -> list[dict]:
        """Semantic search (cosine, HNSW) with level/kind filters, plus exact title hits first."""
        q = vec(self.embedder.embed(query))
        where, params = [], []
        if levels:
            where.append("(level = ANY(%s)" + (" OR level IS NULL)" if include_general else ")"))
            params.append(levels)
        if kinds:
            where.append("kind = ANY(%s)")
            params.append(kinds)
        w = ("WHERE " + " AND ".join(where)) if where else ""
        with self.db.tx() as conn:
            for setting in ("SET LOCAL hnsw.ef_search = 200", "SET LOCAL hnsw.iterative_scan = 'relaxed_order'"):
                try:
                    with conn.transaction():  # savepoint: an unknown setting (older pgvector) must not abort the query
                        conn.execute(setting)
                except Exception:
                    pass
            rows = conn.execute(
                "SELECT id, source, kind, level, title, text, license, url, meta, 1 - (embedding <=> %s::vector) AS score "
                f"FROM kb_documents {w} ORDER BY embedding <=> %s::vector LIMIT %s", [q] + params + [q, k * 3]).fetchall()
        exact = self.lookup_titles(query, levels)
        seen, out = set(), []
        for r in exact + rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append({**r, "score": round(float(r.get("score", 1.0)), 3)})
        return out[:k]

    def lookup_titles(self, text: str, levels: list[str] | None = None, limit: int = 3) -> list[dict]:
        """Exact matches for Japanese words or kanji that appear in the query."""
        import re

        tokens = [t for t in re.findall(r"[぀-ヿ一-鿿々ー]{1,8}", text or "")]
        if not tokens:
            return []
        cands = set()
        for t in tokens:
            for n in range(min(len(t), 6), 0, -1):
                for i in range(len(t) - n + 1):
                    piece = t[i:i + n]
                    # single kana are noise; single kanji are meaningful
                    if n >= 2 or re.match(r"[\u4E00-\u9FFF]", piece):
                        cands.add(piece)
        rows = self.db.all(
            "SELECT id, source, kind, level, title, text, license, url, meta, 1.0 AS score FROM kb_documents "
            "WHERE title = ANY(%s) AND kind IN ('vocab','kanji','grammar') ORDER BY length(title) DESC LIMIT %s",
            (list(cands), limit * 3))
        if levels:
            rows = [r for r in rows if r["level"] in levels or r["level"] is None] or rows
        return rows[:limit]

    def browse(self, level: str | None, kind: str | None, q: str = "", page: int = 1, size: int = 30) -> dict:
        where, params = ["TRUE"], []
        if level:
            where.append("level = %s")
            params.append(level)
        if kind:
            where.append("kind = %s")
            params.append(kind)
        if q:
            where.append("(title ILIKE %s OR text ILIKE %s)")
            params += [f"%{q}%", f"%{q}%"]
        w = " AND ".join(where)
        total = int(self.db.scalar(f"SELECT COUNT(*) FROM kb_documents WHERE {w}", params) or 0)
        rows = self.db.all(f"SELECT id, source, kind, level, title, text, license, url, meta FROM kb_documents WHERE {w} "
                           "ORDER BY CASE level WHEN 'N5' THEN 1 WHEN 'N4' THEN 2 WHEN 'N3' THEN 3 WHEN 'N2' THEN 4 "
                           "WHEN 'N1' THEN 5 ELSE 6 END, kind, id LIMIT %s OFFSET %s", params + [size, (page - 1) * size])
        return {"total": total, "page": page, "size": size, "items": rows}

    def stats(self) -> dict:
        by = self.db.all("SELECT COALESCE(level, 'general') AS level, kind, source, COUNT(*)::int AS n "
                         "FROM kb_documents GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
        lic = self.db.all("SELECT source, license, COUNT(*)::int AS n FROM kb_documents GROUP BY 1, 2 ORDER BY 1")
        for r in lic:
            r["noncommercial"] = "noncommercial" in r["license"].lower() or "by-nc" in r["license"].lower()
        ne = int(self.db.scalar("SELECT COUNT(*) FROM kb_documents WHERE kind IN ('vocab','kanji') AND meta ? 'ne'") or 0)
        return {"total": sum(r["n"] for r in by), "rows": by, "licenses": lic, "nepali": ne}
