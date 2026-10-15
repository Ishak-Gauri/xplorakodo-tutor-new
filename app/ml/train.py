"""Train and evaluate the JLPT level classifier.

    python -m app.ml.train                 # bundled data only -> data/models/jlpt_level.npz
    python -m app.ml.train --db            # + Tatoeba / Kaggle rows ingested into kb_documents, saved to ml_models

Data: N5-N1 vocabulary and kanji lists, grammar example sentences, and (when ingested) Tatoeba sentences
weakly labelled by the lexicon (level of their hardest known word). Stratified 85/15 split; the report
includes accuracy, macro-F1, within-one-level accuracy and a confusion matrix.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np

from .level_model import DATA, LEVELS, Lexicon, SoftmaxModel


def bundled_examples() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for name in ("vocab", "kanji"):
        with gzip.open(DATA / "kb" / f"{name}.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                rows.append((r["title"], LEVELS.index(r["level"]), name))
    for g in json.loads((DATA / "kb" / "grammar.json").read_text(encoding="utf-8")):
        rows.append((g["ja"], LEVELS.index(g["level"]), "grammar"))
    return rows


def db_examples(db, limit_per_level: int = 4000) -> list[tuple[str, int, str]]:
    """Ingested training data. Non-commercial (NC) licences are excluded unless ALLOW_NC_TRAINING=true."""
    import os

    nc = "" if os.getenv("ALLOW_NC_TRAINING", "").lower() in ("1", "true", "yes") else " AND license NOT ILIKE '%%NonCommercial%%' AND license NOT ILIKE '%%BY-NC%%'"
    rows = []
    for lv in LEVELS:
        for r in db.all("SELECT text, meta FROM kb_documents WHERE kind = 'sentence' AND level = %s AND "
                        "(meta->>'level_from' IS NULL OR meta->>'level_from' <> 'leveler' OR source = 'tatoeba')" + nc +
                        " ORDER BY id LIMIT %s", (lv, limit_per_level)):
            ja = (r["meta"] or {}).get("ja") or r["text"]
            rows.append((ja, LEVELS.index(lv), "sentence"))
        for r in db.all("SELECT title FROM kb_documents WHERE source LIKE 'kaggle%%' AND kind = 'vocab' "
                        "AND meta->>'level_from' = 'dataset' AND level = %s" + nc + " LIMIT %s", (lv, limit_per_level)):
            rows.append((r["title"], LEVELS.index(lv), "kaggle"))
    return rows


def split(rows, test_share=0.15, seed=11):
    rng = np.random.default_rng(seed)
    train, test = [], []
    for lv in range(len(LEVELS)):
        group = [r for r in rows if r[1] == lv]
        rng.shuffle(group)
        k = max(1, int(len(group) * test_share))
        test += group[:k]
        train += group[k:]
    return train, test


def evaluate(model: SoftmaxModel, rows) -> dict:
    cm = np.zeros((len(LEVELS), len(LEVELS)), dtype=int)
    for text, y, _ in rows:
        cm[y, int(np.argmax(model.predict_proba(text)))] += 1
    n = cm.sum()
    acc = np.trace(cm) / n if n else 0
    within1 = sum(cm[i, j] for i in range(5) for j in range(5) if abs(i - j) <= 1) / n if n else 0
    f1s = []
    for k in range(len(LEVELS)):
        tp = cm[k, k]
        prec = tp / cm[:, k].sum() if cm[:, k].sum() else 0
        rec = tp / cm[k, :].sum() if cm[k, :].sum() else 0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0)
    majority = cm.sum(axis=1).max() / n if n else 0
    return {"n": int(n), "accuracy": round(float(acc), 4), "within_one": round(float(within1), 4),
            "macro_f1": round(float(np.mean(f1s)), 4), "f1": {LEVELS[i]: round(float(f), 3) for i, f in enumerate(f1s)},
            "majority_baseline": round(float(majority), 4), "confusion": cm.tolist(), "labels": LEVELS}


def sentence_eval(model: SoftmaxModel) -> dict:
    """Held-out sentence check: the hybrid estimator on the JLPT topics' Japanese model answers."""
    from .level_model import LevelEstimator

    est = LevelEstimator(model, Lexicon.from_bundled())
    lessons = json.loads((DATA / "lessons.json").read_text(encoding="utf-8"))
    n = ok = w1 = 0
    for t in lessons["topics"]:
        if t.get("track") != "jlpt":
            continue
        for q in t["questions"]:
            r = est.estimate(q["model_answer"].get("ja", ""))
            if not r["level"]:
                continue
            p, y = LEVELS.index(r["level"]), q["difficulty"] - 1
            n, ok, w1 = n + 1, ok + (p == y), w1 + (abs(p - y) <= 1)
    return {"n": n, "accuracy": round(ok / n, 3) if n else None, "within_one": round(w1 / n, 3) if n else None}


def run(db=None, epochs: int = 3, log=print) -> tuple[SoftmaxModel, dict]:
    t0 = time.time()
    rows = bundled_examples()
    if db is not None:
        lex = Lexicon.from_bundled()
        extra = db_examples(db)
        log(f"database examples: {len(extra)}")
        rows += extra
        del lex
    train, test = split(rows)
    log(f"training on {len(train)} examples, testing on {len(test)}")
    model = SoftmaxModel.train([r[0] for r in train], [r[1] for r in train], epochs=epochs, log=log)
    metrics = evaluate(model, test)
    by_source: dict[str, dict] = {}
    for src in sorted({r[2] for r in test}):
        sub = [r for r in test if r[2] == src]
        if len(sub) >= 10:
            by_source[src] = {k: v for k, v in evaluate(model, sub).items() if k in ("n", "accuracy", "within_one")}
    metrics.update({"by_source": by_source, "train_size": len(train), "epochs": epochs,
                    "seconds": round(time.time() - t0, 1),
                    "sources": sorted({r[2] for r in rows})})
    metrics["sentence_eval"] = sentence_eval(model)
    model.meta = {"metrics": metrics, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    log(f"accuracy {metrics['accuracy']}, within-one {metrics['within_one']}, macro-F1 {metrics['macro_f1']} "
        f"(majority baseline {metrics['majority_baseline']})")
    return model, metrics


if __name__ == "__main__":
    use_db = "--db" in sys.argv
    database = None
    if use_db:
        from ..config import get_settings
        from ..db import Database

        database = Database(get_settings().database_url)
    m, met = run(database)
    out = DATA / "models" / "jlpt_level.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(m.to_bytes())
    print(json.dumps({k: v for k, v in met.items() if k != "confusion"}, indent=1))
    print("saved", out, f"{out.stat().st_size / 1e6:.1f} MB")
    if database is not None:
        from .registry import save_model

        save_model(database, m, met)
        print("saved to ml_models")
