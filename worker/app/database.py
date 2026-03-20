"""
Async SQLAlchemy engine and session factory.

Provides the database connection pool shared by FastAPI request handlers
and ARQ background jobs. Connects to Neon Postgres via asyncpg.
Implements PRD Section 8 (Shared Infrastructure).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_engine(database_url: str):
    """Create an async SQLAlchemy engine from DATABASE_URL.

    Connection pool: 5 baseline + 15 overflow = 20 max connections.
    The URL is rewritten from postgresql:// to postgresql+asyncpg://
    for the asyncpg driver.

    Args:
        database_url: Postgres connection string.

    Returns:
        AsyncEngine configured for Neon Postgres.
    """
    import ssl as _ssl

    url = database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Strip query params (sslmode, channel_binding) — asyncpg doesn't accept them as URL params
    if "?" in url:
        url = url.split("?")[0]
    ssl_ctx = _ssl.create_default_context()
    return create_async_engine(
        url, pool_size=5, max_overflow=15, echo=False, connect_args={"ssl": ssl_ctx}
    )


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine.

    Args:
        engine: AsyncEngine to bind sessions to.

    Returns:
        async_sessionmaker producing AsyncSession instances.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
