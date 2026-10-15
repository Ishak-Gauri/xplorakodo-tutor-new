"""Run knowledge-base ingestion (and model retraining) as tracked jobs.

    python -m app.kb.ingest bundled
    python -m app.kb.ingest tatoeba wikipedia
    KAGGLE_USERNAME=... KAGGLE_KEY=... python -m app.kb.ingest kaggle --datasets owner/slug,owner2/slug2
    python -m app.kb.ingest retrain

The admin console starts the same jobs in a background thread and shows their progress.
"""
from __future__ import annotations

import os
import sys
import threading
import traceback

from ..db import J
from ..observability import traceable
from . import sources

SOURCES = ("bundled", "curriculum", "tatoeba", "wikipedia", "kaggle", "nepali", "retrain")
_lock = threading.Lock()


class Ingestor:
    def __init__(self, svc):
        self.svc = svc
        self.db = svc.db

    def _start(self, source: str, user_id: int | None) -> int:
        return self.db.scalar("INSERT INTO kb_ingest_runs(source, started_by) VALUES (%s,%s) RETURNING id", (source, user_id))

    def _log(self, run_id: int, msg: str) -> None:
        print(f"[kb:{run_id}] {msg}", flush=True)
        self.db.run("UPDATE kb_ingest_runs SET message = right(message || %s, 4000) WHERE id = %s", (msg + "\n", run_id))

    def _finish(self, run_id: int, added: int, error: str | None = None) -> None:
        self.db.run("UPDATE kb_ingest_runs SET status = %s, added = %s, finished_at = now(), "
                    "message = right(message || %s, 4000) WHERE id = %s",
                    ("error" if error else "done", added, (error or "finished") + "\n", run_id))

    @traceable(name="kb_ingest", run_type="chain")
    def run(self, source: str, user_id: int | None = None, options: dict | None = None) -> dict:
        if source not in SOURCES:
            raise ValueError(f"unknown source {source}")
        options = options or {}
        run_id = self._start(source, user_id)
        log = lambda m: self._log(run_id, m)  # noqa: E731
        added = 0
        try:
            with _lock:
                est = self.svc.leveler
                if source == "bundled":
                    docs = sources.bundled()
                elif source == "curriculum":
                    from ..seed import HANDBOOK
                    docs = sources.curriculum(HANDBOOK)
                elif source == "tatoeba":
                    docs = sources.tatoeba(est, per_level=int(options.get("per_level", 1500)), log=log)
                elif source == "wikipedia":
                    docs = sources.wikipedia(est, log=log)
                elif source == "kaggle":
                    slugs = options.get("datasets") or os.getenv("KAGGLE_DATASETS", "")
                    slugs = slugs if isinstance(slugs, list) else [s for s in slugs.split(",") if s.strip()]
                    docs = sources.kaggle(slugs or sources.KAGGLE_DEFAULTS, est, log=log)
                    docs = self._merge_known_words(docs, log)
                elif source == "nepali":
                    from .enrich import nepali
                    added = nepali(self.svc, limit=int(options.get("limit", 2000)), log=log)
                    self._finish(run_id, added)
                    return {"run_id": run_id, "added": added}
                else:  # retrain
                    from ..ml.registry import save_model
                    from ..ml.train import run as train_run
                    model, metrics = train_run(self.db, log=log)
                    row = save_model(self.db, model, metrics)
                    self.svc.reload_leveler()
                    self._finish(run_id, metrics.get("train_size", 0))
                    return {"run_id": run_id, "model_version": row["version"], "metrics": metrics}
                log(f"writing {len(docs)} documents (with embeddings) ...")
                added = self.svc.kb.upsert(docs, progress=lambda a, n: log(f"  {a}/{n}") if a % 2000 == 0 or a == n else None)
            self._finish(run_id, added)
            return {"run_id": run_id, "added": added}
        except Exception as e:
            traceback.print_exc()
            self._finish(run_id, added, f"error: {e}")
            return {"run_id": run_id, "error": str(e)}

    def _merge_known_words(self, docs: list[dict], log) -> list[dict]:
        """Words already in the bundled JLPT lists are merged (romaji, extra meanings) instead of duplicated."""
        vocab = [d for d in docs if d["kind"] == "vocab"]
        known = {(r["title"], r["level"]) for r in self.db.all(
            "SELECT title, level FROM kb_documents WHERE source = 'jlpt_vocab' AND title = ANY(%s)", ([d["title"] for d in vocab],))}
        merges, keep = [], []
        for d in docs:
            if d["kind"] == "vocab" and (d["title"], d["level"]) in known:
                m = d["meta"]
                extra = {k: v for k, v in {"romaji": m.get("romaji"), "kaggle_meaning": m.get("meaning")}.items() if v}
                extra["also_in"] = d["source"]
                merges.append((J(extra), d["title"], d["level"]))
            else:
                keep.append(d)
        if merges:
            with self.db.tx() as conn, conn.cursor() as cur:
                cur.executemany("UPDATE kb_documents SET meta = meta || %s WHERE source = 'jlpt_vocab' AND title = %s AND level = %s", merges)
        log(f"merged {len(merges)} rows into existing JLPT words; {len(keep)} new documents")
        return keep

    def start_background(self, source: str, user_id: int | None, options: dict | None = None) -> int:
        if self.db.scalar("SELECT COUNT(*) FROM kb_ingest_runs WHERE status = 'running' AND started_at > now() - interval '2 hours'"):
            raise RuntimeError("Another ingestion job is still running. Wait for it to finish.")
        t = threading.Thread(target=self.run, args=(source, user_id, options), daemon=True)
        t.start()
        return 0

    def runs(self, limit: int = 20) -> list[dict]:
        return self.db.all("SELECT r.id, r.source, r.status, r.added, r.message, r.started_at, r.finished_at, u.name AS started_by "
                           "FROM kb_ingest_runs r LEFT JOIN users u ON u.id = r.started_by ORDER BY r.id DESC LIMIT %s", (limit,))


def bootstrap_if_empty(svc) -> None:
    """On first start, load the bundled levels + curriculum into the knowledge base (in the background)."""
    ing = Ingestor(svc)

    def work():
        try:
            if not svc.kb.count("jlpt_vocab"):
                ing.run("bundled")
            if not svc.kb.count("curriculum"):
                ing.run("curriculum")
        except Exception:
            traceback.print_exc()

    threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    os.environ["XK_NO_AUTOAPP"] = "1"  # build the app once (not again on import)
    from ..main import build_service

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {}
    if "--datasets" in sys.argv:
        opts["datasets"] = sys.argv[sys.argv.index("--datasets") + 1]
        args = [a for a in args if a != opts["datasets"]]
    if "--per-level" in sys.argv:
        opts["per_level"] = sys.argv[sys.argv.index("--per-level") + 1]
        args = [a for a in args if a != opts["per_level"]]
    service = build_service()
    for src in args or ["bundled", "curriculum"]:
        print(src, Ingestor(service).run(src, None, opts))
