from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as db_session


def _sqlite_file_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _local_test_db_path(name: str) -> Path:
    path = Path(__file__).resolve().parents[1] / "tmp" / f"{name}_{uuid4().hex}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.asyncio
async def test_init_db_auto_creates_schema_for_local_sqlite(monkeypatch):
    db_path = _local_test_db_path("local")
    engine = create_async_engine(_sqlite_file_url(db_path), echo=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(db_session, "_should_auto_initialize_schema", lambda: True)

    try:
        await db_session.init_db()

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            assert result.scalar_one() == "users"
    finally:
        await engine.dispose()
        db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_init_db_does_not_create_tables_when_using_migration_only_startup(
    monkeypatch,
):
    db_path = _local_test_db_path("release")
    engine = create_async_engine(_sqlite_file_url(db_path), echo=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "_should_auto_initialize_schema", lambda: False)

    heads = sorted(db_session._load_expected_alembic_heads())

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            for head in heads:
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                    {"version_num": head},
                )

        await db_session.init_db()

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            assert result.scalar() is None
    finally:
        await engine.dispose()
        db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_init_db_requires_alembic_version_for_migration_only_startup(
    monkeypatch,
):
    db_path = _local_test_db_path("missing_version")
    engine = create_async_engine(_sqlite_file_url(db_path), echo=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "_should_auto_initialize_schema", lambda: False)

    try:
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            await db_session.init_db()
    finally:
        await engine.dispose()
        db_path.unlink(missing_ok=True)


def test_mysql_aiomysql_engine_disables_pool_pre_ping(monkeypatch):
    captured = {}

    def fake_create_async_engine(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(db_session.settings, "DB_TYPE", "mysql")
    monkeypatch.setattr(
        db_session.settings,
        "DATABASE_URL",
        "mysql+aiomysql://user:pass@example.com:3306/faq",
    )
    monkeypatch.setattr(db_session, "create_async_engine", fake_create_async_engine)

    db_session._build_engine()

    assert captured["database_url"] == "mysql+aiomysql://user:pass@example.com:3306/faq"
    assert captured["kwargs"]["pool_pre_ping"] is False
