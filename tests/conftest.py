"""Tests run against a real PostgreSQL + pgvector database (the schema is reset first).

    docker compose up -d db
    TEST_DATABASE_URL=postgresql://xk:xk@localhost:5432/xplorakodo_test pytest

The whole suite is skipped when the database is not reachable.
"""
import os

os.environ["XK_NO_AUTOAPP"] = "1"
os.environ["KB_BOOTSTRAP"] = "sync"
os.environ.pop("LANGSMITH_TRACING", None)

import pytest  # noqa: E402

TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql://xk:xk@localhost:5432/xplorakodo_test")


def _reset(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


@pytest.fixture(scope="session")
def settings():
    from app.config import Settings

    return Settings(database_url=TEST_URL, jwt_secret="test-secret-test-secret-test-secret-123", jwt_hours=1,
                    admin_email="admin@test.local", admin_password="AdminPass!1", admin_name="Test Admin",
                    llm_provider="mock", anthropic_model="", openai_model="", embedding_provider="hash",
                    public_base_url="https://tutor.example", seed_demo=True)


@pytest.fixture(scope="session")
def app(settings):
    try:
        _reset(TEST_URL)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"PostgreSQL not reachable at {TEST_URL}: {e}")
    from app.main import create_app

    application = create_app(settings)
    yield application
    application.state.svc.db.close()


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(autouse=True)
def _default_settings(request):
    """Every API test starts with default runtime settings (unit tests need no database)."""
    if "app" in request.fixturenames or "client" in request.fixturenames:
        request.getfixturevalue("app").state.svc.db.run("DELETE FROM settings")
    yield


_n = [0]


@pytest.fixture
def student(client):
    """A fresh student; returns (headers, user)."""
    _n[0] += 1
    r = client.post("/api/auth/register", json={"name": f"Student {_n[0]}", "email": f"s{_n[0]}_{os.getpid()}@test.local",
                                                 "password": "password123", "lang": "en"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]


@pytest.fixture
def admin_h(client, settings):
    r = client.post("/api/auth/login", json={"email": settings.admin_email, "password": settings.admin_password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
