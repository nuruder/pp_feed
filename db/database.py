import ssl as _ssl

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import make_url, text
from db.models import Base
from config import DATABASE_URL

# asyncpg doesn't understand 'sslmode' — translate to asyncpg's 'ssl' param
_url = make_url(DATABASE_URL)
_connect_args = {}

_sslmode = _url.query.get("sslmode")
if _sslmode:
    _url = _url.difference_update_query(["sslmode"])
    if _sslmode in ("require", "prefer", "verify-ca", "verify-full"):
        # Create a permissive SSL context (like sslmode=require)
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE
        _connect_args["ssl"] = _ctx

engine = create_async_engine(_url, echo=False, connect_args=_connect_args)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_db():
    """Drop all tables and recreate them."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def migrate():
    """Apply schema migrations (safe to re-run)."""
    async with engine.begin() as conn:
        # Indexes
        indexes = [
            ("ix_products_brand_id", "products", "brand_id"),
            ("ix_products_in_stock", "products", "in_stock"),
            ("ix_product_sizes_product_instock", "product_sizes", "product_id, in_stock"),
            ("ix_price_snapshots_product_ts", "price_snapshots", "product_id, timestamp DESC"),
        ]
        for name, table, columns in indexes:
            await conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})"
            ))

        # New columns
        columns = [
            ("products", "images", "JSONB"),
        ]
        for table, column, col_type in columns:
            await conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            ))


async def get_db():
    """FastAPI dependency for DB session."""
    async with AsyncSessionLocal() as session:
        yield session
