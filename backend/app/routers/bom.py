"""Authentication and user management."""
from datetime import datetime, timezone

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..security import (verify_password, hash_password, create_access_token,
                        generate_refresh_token, hash_refresh_token)
from ..config import settings
from ..ratelimit import allow, reset
from ..deps import get_current_user, require_role, audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenPair)
def login(body: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    # rate-limit by client IP to blunt password guessing
    client = request.client.host if request.client else "unknown"
    if not allow(f"login:{client}", settings.LOGIN_RATE_PER_MIN):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many login attempts. Please wait a minute and try again.")

    user = db.query(models.AppUser).filter_by(username=body.username).first()
    now = datetime.now(timezone.utc)

    # account lockout
    if user and user.locked_until:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(status.HTTP_423_LOCKED,
                                "Account temporarily locked due to failed logins. Try again later.")

    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        # count the failure + lock if over threshold
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    # success: clear counters, issue token pair
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    raw_refresh, token_hash = generate_refresh_token()
    db.add(models.RefreshToken(
        user_id=user.id, token_hash=token_hash, issued_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)))
    db.commit()
    reset(f"login:{client}")
    audit(db, user, "login", "user", str(user.id))
    return schemas.TokenPair(
        access_token=create_access_token(user.username, user.role, user.id),
        refresh_token=raw_refresh, role=user.role, username=user.username)


@router.post("/refresh", response_model=schemas.AccessToken)
def refresh(body: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new short-lived access token."""
    th = hash_refresh_token(body.refresh_token)
    rt = db.query(models.RefreshToken).filter_by(token_hash=th).first()
    now = datetime.now(timezone.utc)
    if not rt or rt.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    exp = rt.expires_at.replace(tzinfo=timezone.utc) if rt.expires_at.tzinfo is None else rt.expires_at
    if exp <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    user = db.get(models.AppUser, rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return schemas.AccessToken(
        access_token=create_access_token(user.username, user.role, user.id))


@router.post("/logout", status_code=204)
def logout(body: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """Revoke a refresh token (best-effort; always succeeds)."""
    th = hash_refresh_token(body.refresh_token)
    rt = db.query(models.RefreshToken).filter_by(token_hash=th).first()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return None


@router.post("/change-password", status_code=204)
def change_password(body: schemas.PasswordChange,
                    user: models.AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    # revoke all this user's refresh tokens so other sessions must re-auth
    for rt in db.query(models.RefreshToken).filter_by(user_id=user.id, revoked_at=None).all():
        rt.revoked_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, user, "change_password", "user", str(user.id))
    return None


@router.get("/me", response_model=schemas.UserRead)
def me(user: models.AppUser = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[schemas.UserRead])
def list_users(_: models.AppUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.query(models.AppUser).order_by(models.AppUser.username).all()


@router.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user(body: schemas.UserCreate, actor: models.AppUser = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    if db.query(models.AppUser).filter_by(username=body.username).first():
        raise HTTPException(409, f"username {body.username} already exists")
    if body.role not in ("admin", "planner", "supervisor", "procurement", "viewer"):
        raise HTTPException(422, "invalid role")
    u = models.AppUser(
        username=body.username, full_name=body.full_name, role=body.role,
        password_hash=hash_password(body.password),
        created_at=datetime.now(timezone.utc))
    db.add(u)
    db.commit()
    db.refresh(u)
    audit(db, actor, "create", "user", str(u.id), {"username": u.username, "role": u.role})
    return u


VALID_ROLES = ("admin", "planner", "supervisor", "procurement", "viewer")


@router.patch("/users/{user_id}", response_model=schemas.UserRead)
def update_user(user_id: int, body: schemas.UserUpdate,
                actor: models.AppUser = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    u = db.get(models.AppUser, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data:
        if data["role"] not in VALID_ROLES:
            raise HTTPException(422, "invalid role")
        # guard: don't let the last admin demote themselves out of admin
        if u.role == "admin" and data["role"] != "admin":
            admin_count = db.query(models.AppUser).filter_by(role="admin", is_active=True).count()
            if admin_count <= 1:
                raise HTTPException(409, "cannot remove the last active admin")
        u.role = data["role"]
    if "full_name" in data:
        u.full_name = data["full_name"]
    if "is_active" in data:
        u.is_active = data["is_active"]
    if data.get("password"):
        u.password_hash = hash_password(data["password"])
    db.commit()
    db.refresh(u)
    audit(db, actor, "update", "user", str(u.id),
          {k: v for k, v in data.items() if k != "password"})
    return u