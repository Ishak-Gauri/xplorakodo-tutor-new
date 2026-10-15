"""Nepali enrichment: add Nepali meanings to vocabulary and kanji that only have English (uses the LLM).

None of the public JLPT datasets include Nepali, so this job translates the English meanings in batches,
easiest level first, and stores them in meta.ne and in the searchable text.
"""
from __future__ import annotations

import time

from ..db import J, vec
from ..observability import traceable

SYSTEM = ("You translate the English meanings of Japanese words into simple, natural Nepali (Devanagari) for "
          "Nepali learners of Japanese. Keep each translation short (1-6 words), use everyday Nepali, and keep "
          "the part of speech (verbs as verbs). Reply as JSON: {\"items\": [{\"i\": <number>, \"ne\": \"<Nepali>\"}]}.")
ORDER = "CASE level WHEN 'N5' THEN 1 WHEN 'N4' THEN 2 WHEN 'N3' THEN 3 WHEN 'N2' THEN 4 WHEN 'N1' THEN 5 ELSE 6 END"


def parse_items(data) -> dict[int, str]:
    """Accept the shapes models actually return: {"items": [{"i":0,"ne":".."}]}, [[0, ".."]], {"0": ".."}, a bare list ..."""
    out: dict[int, str] = {}
    items = data.get("items", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = [[k, v] for k, v in items.items()]
    if not isinstance(items, list):
        return out
    for pos, x in enumerate(items):
        i, ne = None, None
        if isinstance(x, dict):
            i, ne = x.get("i", x.get("index", x.get("id"))), x.get("ne", x.get("nepali", x.get("translation")))
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            i, ne = x[0], x[1]
        elif isinstance(x, str):
            i, ne = pos, x
        try:
            i = int(str(i).strip().rstrip("."))
        except (TypeError, ValueError):
            continue
        if isinstance(ne, str) and ne.strip():
            out[i] = ne.strip()
    return out


@traceable(name="nepali_enrichment", run_type="chain")
def nepali(svc, limit: int = 2000, batch: int = 60, log=print) -> int:
    if not getattr(svc.llm, "is_llm", False):
        raise RuntimeError("Nepali enrichment needs an LLM: set OPENAI_API_KEY (and LLM_PROVIDER=openai).")
    rows = svc.db.all(
        "SELECT id, title, text, meta, kind FROM kb_documents WHERE kind IN ('vocab', 'kanji') AND NOT (meta ? 'ne') "
        f"ORDER BY {ORDER}, id LIMIT %s", (limit,))
    log(f"{len(rows)} entries without Nepali (limit {limit})")
    done, tokens = 0, 0
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        items = []
        for i, r in enumerate(chunk):
            m = r["meta"] or {}
            en = m.get("meaning") or ", ".join(m.get("meanings") or []) or r["text"]
            items.append(f"{i}. {r['title']} ({m.get('reading', '')}): {en[:120]}")
        try:
            data, used = svc.llm.complete_json(SYSTEM, "\n".join(items), 2000)
        except Exception as e:
            log(f"  batch {start // batch + 1} failed: {e}")
            continue
        tokens += used
        ne = parse_items(data)
        if not ne:
            log(f"  batch {start // batch + 1}: no usable translations in the reply, skipped")
            continue
        updates = []
        for i, r in enumerate(chunk):
            if i in ne and ne[i]:
                text = f"{r['text']} / नेपाली: {ne[i]}"
                updates.append((J({"ne": ne[i]}), text, vec(svc.embedder.embed(f"{r['title']} {text}")), r["id"]))
        for attempt in (1, 2, 3):  # a dropped database connection is retried on a fresh one
            try:
                with svc.db.tx() as conn, conn.cursor() as cur:
                    cur.executemany("UPDATE kb_documents SET meta = meta || %s, text = %s, embedding = %s::vector "
                                    "WHERE id = %s", updates)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise
                log(f"  database write failed ({type(e).__name__}); retrying ...")
                time.sleep(2 * attempt)
        done += len(updates)
        log(f"  {done}/{len(rows)} translated ({tokens} tokens)")
    return done
