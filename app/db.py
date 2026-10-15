"""PostgreSQL access: a small connection pool, query helpers and the migration runner.

Uses psycopg 3. Vectors are sent as text literals and cast with ::vector, so the
pgvector Python package is not needed; only the `vector` extension in the database.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def vec(values: Sequence[float]) -> str:
    """Python list -> pgvector text literal, e.g. '[0.1,0.2]'. Use with %s::vector."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def J(value: Any) -> Jsonb:
    """Wrap a dict/list so psycopg sends it as JSONB."""
    return Jsonb(value)


class Database:
    def __init__(self, url: str, min_size: int = 1, max_size: int = 8):
        self.url = url
        # Neon/Render close idle or long-lived connections, so: test each connection before handing it out,
        # drop idle ones after 4 minutes, recycle every 30 minutes and keep TCP alive.
        self.pool = ConnectionPool(
            url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": True,
                    "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5},
            check=ConnectionPool.check_connection,
            max_idle=240,
            max_lifetime=1800,
            open=True,
            timeout=20,
        )

    def close(self) -> None:
        self.pool.close()

    # ---- helpers -------------------------------------------------------------
    @contextmanager
    def tx(self) -> Iterator[Any]:
        """A connection inside one transaction: everything commits together or not at all."""
        with self.pool.connection() as conn:
            with conn.transaction():
                yield conn

    def all(self, sql: str, params: Sequence | dict | None = None) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: Sequence | dict | None = None) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence | dict | None = None) -> Any:
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def run(self, sql: str, params: Sequence | dict | None = None) -> int:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).rowcount

    # ---- migrations ----------------------------------------------------------
    def migrate(self) -> list[str]:
        """Apply new migrations. Uses a transaction-scoped advisory lock (pg_advisory_xact_lock), which is
        released automatically at COMMIT/ROLLBACK, so it also works through Neon's pooled (-pooler) endpoint."""
        applied: list[str] = []
        with self.pool.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(727001)")  # one app instance migrates at a time
                    if conn.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (path.name,)).fetchone():
                        continue  # another instance applied it while we waited
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,))
                applied.append(path.name)
        return applied
