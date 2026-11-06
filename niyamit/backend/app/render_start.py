"""Single-process, synthetic-demo startup for Render Free. Run: python -m app.render_start."""
from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app import models  # registers every application table
from app.config import settings
from app.db import Base, SessionLocal, engine


def protect_app_tables() -> None:
    """Keep Supabase browser roles out; application authorization remains in the API.

    This is deliberately limited to our tables, never Supabase's auth/storage schemas.
    Disable the project's Data API before first deployment as an additional boundary.
    The server connection must use the trusted postgres session-pooler role.
    """
    with engine.begin() as conn:
        browser_roles = conn.scalars(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")).all()
        quote = conn.dialect.identifier_preparer.quote_identifier
        for name in [*Base.metadata.tables, "alembic_version"]:
            table = '"public".' + quote(name)
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"REVOKE ALL ON TABLE {table} FROM PUBLIC"))
            for role in browser_roles:
                conn.execute(text(f"REVOKE ALL ON TABLE {table} FROM {quote(role)}"))


def prepare() -> None:
    settings.validate_for_startup()
    if not settings.demo_mode or settings.is_production:
        raise RuntimeError("This Render Free profile supports synthetic demos only.")
    if settings.storage_provider != "supabase" or not settings.tasks_eager:
        raise RuntimeError("Render Free requires STORAGE_PROVIDER=supabase and TASKS_EAGER=true.")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    protect_app_tables()
    with SessionLocal() as db:
        empty = db.scalar(select(models.Clinic.id).limit(1)) is None
    if empty:
        from app.seed import seed

        seed()  # synthetic fixtures; no --force and no private access links printed
    logging.getLogger(__name__).info("Render demo database ready")


if __name__ == "__main__":
    prepare()
    port = str(int(os.environ.get("PORT", "10000")))
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port,
                          "--workers", "1", "--no-proxy-headers"])
