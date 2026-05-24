from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings

_engine = None
async_session_factory = None


def _init_engine():
    global _engine, async_session_factory
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _engine = create_async_engine(settings.database_url, echo=False, pool_size=20, max_overflow=10)
        async_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    _init_engine()
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
