"""FastAPI app.  Run:  uvicorn app.main:app --reload   then open http://localhost:8000

On start it migrates PostgreSQL (pgvector schema), seeds content + admin, and serves the SPA.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .admin import AdminService
from .config import Settings, get_settings
from .db import Database
from .embeddings import make_embedder
from .errors import BadRequest, BudgetExceeded, Forbidden, NotFound, Unauthorized
from .llm import make_llm
from .routers import admin as admin_routes
from .routers import public as public_routes
from .routers import student as student_routes
from .flows import AskFlow, FactoryFlow
from .kb.ingest import Ingestor, bootstrap_if_empty
from .routers import kb as kb_routes
from .seed import seed_content, seed_users
from .service import TutorService

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("xplorakodo")


def create_app(settings: Settings | None = None, llm=None, db: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    print("[startup] connecting to PostgreSQL...", flush=True)
    db = db or Database(settings.database_url)
    applied = db.migrate()
    if applied:
        log.warning("applied migrations: %s", applied)
    embedder = make_embedder(settings.embedding_provider)
    print("[startup] database migrated; seeding content...", flush=True)
    stats = seed_content(db, embedder)
    seed_users(db, settings)
    print(f"[startup] ready: {stats}", flush=True)

    svc = TutorService(db, llm or make_llm(settings), embedder, settings.jwt_secret)
    svc.ask = AskFlow(svc)
    svc.factory = FactoryFlow(svc)
    svc.ingestor = Ingestor(svc)
    mode = os.getenv("KB_BOOTSTRAP", "background")
    if mode == "sync":
        for src in ("bundled", "curriculum"):
            if not svc.kb.count("jlpt_vocab" if src == "bundled" else "curriculum"):
                svc.ingestor.run(src)
    elif mode != "off":
        bootstrap_if_empty(svc)
    app = FastAPI(title="XploraKodo Tutor", version="3.1.0")
    app.state.settings = settings
    app.state.svc = svc
    app.state.admin = AdminService(svc)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    def _err(status: int):
        async def handler(_, e):
            body = {"detail": str(e)}
            if isinstance(e, BudgetExceeded):
                body["code"] = e.code
            return JSONResponse(body, status_code=status)
        return handler

    app.add_exception_handler(NotFound, _err(404))
    app.add_exception_handler(BadRequest, _err(400))
    app.add_exception_handler(Unauthorized, _err(401))
    app.add_exception_handler(Forbidden, _err(403))
    app.add_exception_handler(BudgetExceeded, _err(429))

    @app.exception_handler(RequestValidationError)
    async def _validation(_, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:])
        return JSONResponse({"detail": f"{field}: {first.get('msg', 'invalid')}" if field else "Invalid request."}, status_code=422)

    app.include_router(public_routes.router)
    app.include_router(student_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(kb_routes.router)

    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Client-side routes (/login, /app/..., /admin/..., /verify/...) all load the SPA shell."""
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def build_service() -> TutorService:
    """The service without the web app (for CLI jobs such as `python -m app.kb.ingest`)."""
    os.environ.setdefault("KB_BOOTSTRAP", "off")
    return create_app().state.svc


# Tests set XK_NO_AUTOAPP=1 and build their own app against a test database.
app = None if os.getenv("XK_NO_AUTOAPP") else create_app()
