"""TEMPORARY debug/seed endpoints -- no authentication required (that's the
whole point: the database has zero users and you're locked out).

GET  /debug/users  -> lists existing users (usernames/roles only, no hashes)
POST /debug/seed   -> creates the three default users if they don't exist yet,
                      using the app's own hash_password() function, so the
                      hash format is guaranteed correct -- no guessing.

DELETE THIS FILE once you've logged in successfully. It's not meant to stay
in a real deployment -- anyone who finds this URL could reseed your users.
"""
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import engine, get_db
from .. import models
from ..security import hash_password

router = APIRouter(prefix="/debug", tags=["debug-temporary"])

DEFAULT_USERS = [
    ("admin", "admin123", "admin"),
    ("planner", "planner123", "planner"),
    ("viewer", "viewer123", "viewer"),
]


@router.get("/users")
def debug_list_users():
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT username, role, is_active, failed_login_count, locked_until "
                "FROM app_user ORDER BY id"
            )).fetchall()
        return {
            "user_count": len(rows),
            "users": [
                {"username": r[0], "role": r[1], "is_active": r[2],
                 "failed_login_count": r[3],
                 "locked_until": str(r[4]) if r[4] else None}
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e), "hint": "Could not query app_user -- table may not exist, or DB is unreachable."}


@router.post("/seed")
def debug_seed_users():
    created = []
    skipped = []
    db: Session = next(get_db())
    try:
        for username, password, role in DEFAULT_USERS:
            existing = db.query(models.AppUser).filter_by(username=username).first()
            if existing:
                skipped.append(username)
                continue
            db.add(models.AppUser(
                username=username, role=role,
                password_hash=hash_password(password),
                is_active=True,
            ))
            created.append(username)
        db.commit()
        return {"created": created, "skipped_existing": skipped,
                "note": "Log in now with the credentials from your documentation, then delete this file."}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()
