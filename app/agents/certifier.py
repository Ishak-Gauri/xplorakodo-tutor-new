"""Certifier agent: closed-loop readiness certificate with a signed, QR-verifiable code."""
from __future__ import annotations

import secrets

from ..content import loc
from ..db import J, Database
from ..security import sign


class Certifier:
    name = "Certifier"

    def __init__(self, db: Database, secret: str):
        self.db, self.secret = db, secret

    def eligibility(self, user: dict, heat: dict, cfg: dict) -> dict:
        checks = [{"key": "placement", "ok": bool(user.get("level")), "detail": user.get("level") or "not taken"}]
        min_m, min_n = float(cfg["cert_min_mastery"]), int(cfg["cert_min_attempts"])
        for t in [t for t in heat["topics"] if t.get("track", "caregiving") == "caregiving"]:
            ta = heat["topic_avg"][t["id"]]
            ok = ta["avg"] is not None and ta["avg"] >= min_m and ta["n"] >= min_n
            checks.append({"key": f"topic:{t['id']}", "label": t["title"], "ok": ok,
                           "detail": f"{round((ta['avg'] or 0) * 100)}% over {ta['n']} answers (need {round(min_m * 100)}% and {min_n})"})
        iv = self.db.one(
            "SELECT avg_score FROM sessions WHERE user_id = %s AND kind = 'interview' AND passed "
            "ORDER BY avg_score DESC LIMIT 1", (user["id"],))
        checks.append({"key": "interview", "ok": iv is not None,
                       "detail": f"passed with {round(iv['avg_score'] * 100)}%" if iv else
                       f"pass a mock interview with {round(float(cfg['interview_pass']) * 100)}%"})
        return {"eligible": all(c["ok"] for c in checks), "checks": checks}

    def issue(self, user: dict, heat: dict, interview_score: float | None) -> dict:
        existing = self.db.one("SELECT * FROM certificates WHERE user_id = %s AND NOT revoked ORDER BY issued_at DESC LIMIT 1",
                               (user["id"],))
        if existing:
            return existing
        code = "XK-" + secrets.token_hex(4).upper() + "-" + secrets.token_hex(2).upper()
        care = [t for t in heat["topics"] if t.get("track", "caregiving") == "caregiving"]
        scores = {"topics": {t["title"]: heat["topic_avg"][t["id"]]["avg"] for t in care},
                  "overall": heat["overall"], "interview": interview_score, "jlpt": user.get("level")}
        signature = sign(self.secret, code, user["id"], user.get("level"), scores["overall"])
        return self.db.one(
            "INSERT INTO certificates(code, user_id, level, scores, signature) VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (code, user["id"], user.get("level"), J(scores), signature))

    def verify(self, code: str) -> dict | None:
        row = self.db.one(
            "SELECT c.*, u.name, o.name AS org FROM certificates c JOIN users u ON u.id = c.user_id "
            "LEFT JOIN organizations o ON o.id = u.org_id WHERE c.code = %s", (code,))
        if not row:
            return None
        expected = sign(self.secret, row["code"], row["user_id"], row["level"], row["scores"].get("overall"))
        return {"code": row["code"], "name": row["name"], "org": row["org"], "level": row["level"],
                "scores": row["scores"], "issued_at": row["issued_at"].isoformat(),
                "revoked": row["revoked"], "signature_valid": expected == row["signature"],
                "valid": (expected == row["signature"]) and not row["revoked"]}


def topic_title(t: dict, lang: str) -> str:
    return loc(t["title"], lang)
