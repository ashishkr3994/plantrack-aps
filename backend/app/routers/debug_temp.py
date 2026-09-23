"""TEMPORARY debug endpoint -- checks whether any users exist in the database.
No authentication required (that's the whole point: you're locked out).
Returns usernames and roles only, never password hashes.

DELETE THIS FILE once you've diagnosed the issue -- it's not meant to stay
in a real deployment.
"""
from fastapi import APIRouter
from sqlalchemy import text

from ..database import engine

router = APIRouter(prefix="/debug", tags=["debug-temporary"])


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
                {
                    "username": r[0], "role": r[1], "is_active": r[2],
                    "failed_login_count": r[3],
                    "locked_until": str(r[4]) if r[4] else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e), "hint": "Could not query app_user -- table may not exist, or DB is unreachable."}
