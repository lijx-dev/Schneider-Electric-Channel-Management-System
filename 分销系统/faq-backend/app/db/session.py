"""Database session management."""
from pathlib import Path
from typing import AsyncGenerator

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "migrations"


def get_database_url() -> str:
    if settings.DB_TYPE == "mysql":
        if not settings.DATABASE_URL:
            raise RuntimeError("DB_TYPE=mysql requires DATABASE_URL")
        logger.info("database_mode", mode="mysql")
        return settings.DATABASE_URL

    if settings.DB_TYPE == "sqlite":
        logger.info("database_mode", mode="sqlite_file")
        return "sqlite+aiosqlite:///./faq_dev.db"

    if settings.DB_TYPE == "memory":
        if settings.is_production:
            raise RuntimeError("Production cannot use the in-memory database mode")
        logger.info("database_mode", mode="sqlite_memory")
        return "sqlite+aiosqlite:///:memory:"

    if settings.DATABASE_URL:
        db_type = "sqlite_file" if "sqlite" in settings.DATABASE_URL else "mysql"
        logger.info("database_mode", mode=db_type, note="legacy_config")
        return settings.DATABASE_URL

    if settings.is_production:
        raise RuntimeError("Production database configuration is missing")

    logger.info("database_mode", mode="sqlite_memory", note="default_fallback")
    return "sqlite+aiosqlite:///:memory:"


def _build_engine():
    database_url = get_database_url()
    pool_size = getattr(settings, "DB_POOL_SIZE", 10)
    max_overflow = getattr(settings, "DB_MAX_OVERFLOW", 20)
    pool_recycle = getattr(settings, "DB_POOL_RECYCLE", 1800)
    engine_kwargs = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
    }

    if database_url.startswith("mysql"):
        # SQLAlchemy 2.x 的 pool_pre_ping 对 mysql+aiomysql 同样生效：
        # 取连接前先 ping，避免容器重启/网络波动后复用死连接导致偶发
        # OperationalError（如 "Lost connection to MySQL server"）。不可置 False。
        engine_kwargs.update(
            {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_recycle": pool_recycle,
            }
        )
        logger.info(
            "database_pool_configured",
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
        )

    return create_async_engine(database_url, **engine_kwargs)


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def _should_auto_initialize_schema() -> bool:
    return not settings.is_production and engine.url.drivername.startswith("sqlite")


def _load_expected_alembic_heads() -> set[str]:
    if not ALEMBIC_INI_PATH.exists() or not MIGRATIONS_PATH.exists():
        raise RuntimeError(
            "Alembic assets are missing from the runtime image. "
            "Copy alembic.ini and migrations/ into the deployment artifact before startup."
        )

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    script = ScriptDirectory.from_config(config)
    heads = {revision for revision in script.get_heads() if revision}

    if not heads:
        raise RuntimeError("No Alembic head revision was found in migrations/")

    return heads


async def _ensure_schema_is_current() -> None:
    expected_heads = _load_expected_alembic_heads()

    async with engine.connect() as conn:
        try:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        except Exception as exc:
            raise RuntimeError(
                "Database schema is not managed by Alembic yet. "
                "Run `alembic upgrade head` before starting the app."
            ) from exc

        current_heads = {revision for revision in result.scalars().all() if revision}

    if current_heads != expected_heads:
        raise RuntimeError(
            "Database schema revision mismatch. "
            f"Current={sorted(current_heads) or ['<none>']}, expected={sorted(expected_heads)}. "
            "Run `alembic upgrade head` before starting the app."
        )

    logger.info("database_schema_verified", current_heads=sorted(current_heads))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    if _should_auto_initialize_schema():
        from app.db.base import Base
        from app.models import certificate, energy, energy_product, guide, knowledge, lottery, monthly, question, recognition, record, user  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("database_initialized", strategy="dev_create_all")
        return

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    await _ensure_schema_is_current()
    logger.info("database_initialized", strategy="migration_only")


async def close_db() -> None:
    await engine.dispose()
    logger.info("database_closed")
