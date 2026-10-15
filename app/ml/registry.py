"""Model registry in PostgreSQL (Render's disk is ephemeral, so retrained models live in the database)."""
from __future__ import annotations

from ..db import J, Database
from .level_model import LevelEstimator, Lexicon, SoftmaxModel

NAME = "jlpt_level"


def save_model(db: Database, model: SoftmaxModel, metrics: dict, activate: bool = True) -> dict:
    with db.tx() as conn:
        version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 AS v FROM ml_models WHERE name = %s", (NAME,)).fetchone()["v"]
        if activate:
            conn.execute("UPDATE ml_models SET active = false WHERE name = %s", (NAME,))
        row = conn.execute("INSERT INTO ml_models(name, version, data, metrics, active) VALUES (%s,%s,%s,%s,%s) "
                           "RETURNING id, name, version, active, trained_at",
                           (NAME, version, model.to_bytes(), J(metrics), activate)).fetchone()
    return row


def load_estimator(db: Database | None) -> tuple[LevelEstimator, dict]:
    """The active model from the database if there is one, otherwise the bundled model."""
    if db is not None:
        row = db.one("SELECT version, data, metrics, trained_at FROM ml_models WHERE name = %s AND active "
                     "ORDER BY version DESC LIMIT 1", (NAME,))
        if row:
            return LevelEstimator(SoftmaxModel.from_bytes(bytes(row["data"])), Lexicon.from_bundled()), \
                {"version": row["version"], "metrics": row["metrics"], "trained_at": row["trained_at"].isoformat(), "source": "database"}
    est = LevelEstimator.load_default()
    return est, {"version": 0, "metrics": est.model.meta.get("metrics", {}), "trained_at": est.model.meta.get("trained_at"),
                 "source": "bundled"}
