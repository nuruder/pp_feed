"""
FastAPI application — external API for accessing scraped data.

Run:
    uvicorn api.main:app --reload --port 8000

Docs:
    http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import init_db, get_db
from db.models import Product, Category, Brand, ProductType, PriceSnapshot
from api.schemas import StatsSchema
from api.routes.categories import router as categories_router
from api.routes.products import router as products_router
from api.routes.brands import router as brands_router
from api.routes.product_types import router as product_types_router
from api.routes.prices import router as prices_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="PadelPoint Parser API",
    description="API for accessing scraped product data from tiendapadelpoint.com",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(categories_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(brands_router, prefix="/api/v1")
app.include_router(product_types_router, prefix="/api/v1")
app.include_router(prices_router, prefix="/api/v1")


@app.get("/api/v1/stats", response_model=StatsSchema, tags=["Stats"])
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get overall statistics about the scraped data."""
    total_products = await db.scalar(select(func.count(Product.id))) or 0
    total_categories = await db.scalar(select(func.count(Category.id))) or 0
    total_brands = await db.scalar(select(func.count(Brand.id))) or 0
    total_product_types = await db.scalar(select(func.count(ProductType.id))) or 0

    # Count in-stock products (based on latest snapshot)
    # Subquery for latest snapshot per product
    latest_sub = (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.timestamp).label("max_ts"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )
    in_stock_count = await db.scalar(
        select(func.count(PriceSnapshot.id))
        .join(latest_sub, (
            (PriceSnapshot.product_id == latest_sub.c.product_id)
            & (PriceSnapshot.timestamp == latest_sub.c.max_ts)
        ))
        .where(PriceSnapshot.in_stock.is_(True))
    ) or 0

    # Last scrape time
    last_scrape = await db.scalar(
        select(PriceSnapshot.timestamp).order_by(desc(PriceSnapshot.timestamp)).limit(1)
    )

    return StatsSchema(
        total_products=total_products,
        total_categories=total_categories,
        total_brands=total_brands,
        total_product_types=total_product_types,
        in_stock_products=in_stock_count,
        last_scrape=last_scrape,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
