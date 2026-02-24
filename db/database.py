from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import make_url
from db.models import Base
from config import DATABASE_URL

# asyncpg doesn't understand 'sslmode' — strip it from query params
_url = make_url(DATABASE_URL)
if _url.query.get("sslmode"):
    _url = _url.difference_update_query(["sslmode"])

engine = create_async_engine(_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency for DB session."""
    async with AsyncSessionLocal() as session:
        yield session
