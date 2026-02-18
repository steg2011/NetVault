import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import Settings

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_session_factory = None


async def init_db(settings: Settings) -> None:
    """Initialize database engine and session factory."""
    global _engine, _session_factory

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized and tables created")


async def close_db() -> None:
    """Close database connections."""
    global _engine

    if _engine:
        await _engine.dispose()
        logger.info("Database connections closed")


def get_session_factory():
    """Return session factory for dependency injection."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


async def get_db_session() -> AsyncSession:
    """Dependency for FastAPI to get async database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
