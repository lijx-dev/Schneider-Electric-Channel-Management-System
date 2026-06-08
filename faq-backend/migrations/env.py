from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.db.base import Base
from app.models import certificate, guide, question, record, user  # noqa: F401

config = context.config


def _to_sync_database_url(url: str) -> str:
    if url.startswith("mysql+aiomysql://"):
        return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    if url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    if url.startswith("sqlite+aiosqlite:///:memory:"):
        return "sqlite:///:memory:"
    return url


def get_migration_database_url() -> str:
    if settings.DB_TYPE == "mysql":
        if not settings.DATABASE_URL:
            raise RuntimeError("Alembic 迁移要求在 MySQL 模式下配置 DATABASE_URL")
        return _to_sync_database_url(settings.DATABASE_URL)

    if settings.DB_TYPE == "sqlite":
        return "sqlite:///./faq_dev.db"

    if settings.DATABASE_URL:
        return _to_sync_database_url(settings.DATABASE_URL)

    raise RuntimeError(
        "Alembic 迁移要求使用持久化数据库。请配置 DATABASE_URL，或将 DB_TYPE 设为 sqlite/mysql。"
    )


config.set_main_option("sqlalchemy.url", get_migration_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
