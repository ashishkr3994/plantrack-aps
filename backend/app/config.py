"""Application configuration, read from environment.

Production safety: in production the JWT secret MUST be provided via the
environment; the app refuses to start with the insecure development default.
"""
from __future__ import annotations
import os
import sys

DEV_SECRET = "dev-secret-change-in-production"


class Settings:
    # ---- environment ----
    # "development" | "production". Controls fail-fast checks and error verbosity.
    ENVIRONMENT: str = os.environ.get("PLANTRACK_ENV", "development").lower()

    # ---- database ----
    # Standard libpq env vars (PGHOST, PGUSER, ...) are honoured by the driver.
    # DATABASE_URL takes precedence when set. Render (and others) hand out URLs
    # starting with postgresql:// — normalise to the psycopg driver the app uses.
    DATABASE_URL: str = (
        os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://plantrack:plantrack@localhost:5432/plantrack",
        )
        .replace("postgresql+psycopg://", "postgresql+psycopg://")
        .replace("postgres://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )

    # ---- auth ----
    SECRET_KEY: str = os.environ.get("PLANTRACK_SECRET_KEY", DEV_SECRET)
    ACCESS_TOKEN_TTL_MIN: int = int(os.environ.get("PLANTRACK_TOKEN_TTL_MIN", "30"))
    REFRESH_TOKEN_TTL_DAYS: int = int(os.environ.get("PLANTRACK_REFRESH_TTL_DAYS", "14"))
    MAX_FAILED_LOGINS: int = int(os.environ.get("PLANTRACK_MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES: int = int(os.environ.get("PLANTRACK_LOCKOUT_MINUTES", "15"))
    LOGIN_RATE_PER_MIN: int = int(os.environ.get("PLANTRACK_LOGIN_RATE_PER_MIN", "10"))

    # ---- CORS ----
    ALLOWED_ORIGINS: list[str] = [
        o.strip() for o in os.environ.get("PLANTRACK_ALLOWED_ORIGINS", "*").split(",") if o.strip()
    ]

    # ---- observability ----
    SENTRY_DSN: str = os.environ.get("SENTRY_DSN", "")

    # ---- solver ----
    SOLVER_DEFAULT_TIME_BUDGET_S: int = int(os.environ.get("SOLVER_DEFAULT_TIME_BUDGET_S", "20"))

    API_TITLE: str = "PlanTrack APS API"
    API_VERSION: str = "0.1.0"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate(self) -> list[str]:
        """Return a list of fatal misconfigurations for the current environment."""
        problems: list[str] = []
        if self.is_production:
            if self.SECRET_KEY == DEV_SECRET or not self.SECRET_KEY:
                problems.append(
                    "PLANTRACK_SECRET_KEY must be set to a strong secret in production "
                    "(the development default is insecure).")
            # Wildcard CORS only matters when a separate browser origin calls the
            # API. If the UI is served same-origin (PLANTRACK_STATIC_DIR set),
            # there is no cross-origin request and wildcard is harmless.
            serving_spa = bool(os.environ.get("PLANTRACK_STATIC_DIR"))
            if "*" in self.ALLOWED_ORIGINS and not serving_spa:
                problems.append(
                    "PLANTRACK_ALLOWED_ORIGINS must list explicit origins in production "
                    "(wildcard CORS is unsafe when the UI is on a different origin).")
            if "plantrack:plantrack@localhost" in self.DATABASE_URL:
                problems.append("DATABASE_URL still points at the local dev database.")
        return problems


settings = Settings()


def enforce_production_safety() -> None:
    """Abort startup if production is misconfigured. Called from app startup."""
    problems = settings.validate()
    if problems:
        msg = "Refusing to start in production due to insecure configuration:\n  - " + \
              "\n  - ".join(problems)
        print(msg, file=sys.stderr)
        raise RuntimeError(msg)

