"""Auth dependencies: resolve the current user from the Bearer token, and a
role-requirement factory for protecting endpoints. Plus an audit helper.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .security import decode_token
from . import models

bearer = HTTPBearer(auto_error=False)

# role hierarchy: higher number = more privilege
ROLE_RANK = {"viewer": 0, "procurement": 1, "supervisor": 2, "planner": 3, "admin": 4}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.AppUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    user = db.get(models.AppUser, payload.get("uid"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_role(min_role: str):
    """Dependency factory: require at least `min_role` by hierarchy."""
    threshold = ROLE_RANK[min_role]

    def checker(user: models.AppUser = Depends(get_current_user)) -> models.AppUser:
        if ROLE_RANK.get(user.role, -1) < threshold:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires {min_role} role or higher (you are {user.role}).")
        return user

    return checker


def audit(db: Session, actor: models.AppUser | None, action: str,
          entity_type: str, entity_id: str | None = None, detail: dict | None = None) -> None:
    """Append an audit-log entry. Best-effort; never blocks the main action."""
    try:
        db.add(models.AuditLog(
            actor_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            action=action, entity_type=entity_type, entity_id=entity_id,
            detail=detail, at=datetime.now(timezone.utc)))
        db.commit()
    except Exception:
        db.rollback()
