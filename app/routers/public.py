"""Unauthenticated endpoints: health, institute list for sign-up, certificate verification + QR."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..deps import svc
from ..errors import NotFound

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request, s=Depends(svc)):
    db_ok = s.db.scalar("SELECT 1") == 1
    vector = s.db.scalar("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    return {"ok": db_ok, "db": "postgresql", "pgvector": vector, "grader": s.llm.name, "embedder": s.embedder.name}


@router.get("/public/orgs")
def public_orgs(s=Depends(svc)):
    return s.db.all("SELECT id, name FROM organizations ORDER BY name")


@router.get("/verify/{code}")
def verify(code: str, s=Depends(svc)):
    result = s.certifier.verify(code.strip().upper())
    if not result:
        raise NotFound("No certificate with this code.")
    return result


@router.get("/verify/{code}/qr.svg")
def qr(code: str, request: Request, s=Depends(svc)):
    import qrcode
    import qrcode.image.svg

    if not s.certifier.verify(code.strip().upper()):
        raise NotFound("No certificate with this code.")
    base = request.app.state.settings.public_base_url or str(request.base_url).rstrip("/")
    img = qrcode.make(f"{base}/verify/{code.strip().upper()}", image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return Response(img.to_string(), media_type="image/svg+xml")
