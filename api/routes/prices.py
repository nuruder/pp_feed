from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import PriceSnapshot, Product, Brand, product_categories
from api.schemas import PriceSnapshotSchema, PaginatedPrices

router = APIRouter(prefix="/prices", tags=["Prices"])


@router.get("/history/{product_id}", response_model=list[PriceSnapshotSchema])
async def price_history(
    product_id: int,
    since: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Get price history for a product.

    - **since**: Only return snapshots after this timestamp
    - **limit**: Max number of snapshots to return
    """
    query = (
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.timestamp))
        .limit(limit)
    )
    if since:
        query = query.where(PriceSnapshot.timestamp >= since)

    result = await db.execute(query)
    snapshots = result.scalars().all()

    return [PriceSnapshotSchema.model_validate(s) for s in snapshots]


@router.get("/latest", response_model=PaginatedPrices)
async def latest_prices(
    category_id: int | None = None,
    product_type_id: int | None = None,
    brand_name: str | None = None,
    in_stock_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Get latest prices for all products (bulk endpoint).
    Useful for syncing with external systems.
    """
    query = select(Product).options(selectinload(Product.brand))

    if category_id is not None:
        query = query.join(product_categories).where(
            product_categories.c.category_id == category_id
        )
    if product_type_id is not None:
        query = query.where(Product.product_type_id == product_type_id)
    if brand_name:
        query = query.join(Brand).where(Brand.name.ilike(f"%{brand_name}%"))
    if in_stock_only:
        query = query.where(Product.in_stock.is_(True))

    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_q) or 0

    # Paginated query
    offset = (page - 1) * page_size
    query = query.order_by(Product.name).offset(offset).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().unique().all()

    items = []
    for product in products:
        snap_result = await db.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product.id)
            .order_by(desc(PriceSnapshot.timestamp))
            .limit(1)
        )
        latest = snap_result.scalar_one_or_none()

        items.append({
            "product_id": product.id,
            "external_id": product.external_id,
            "name": product.name,
            "brand": product.brand.name if product.brand else None,
            "price_regular": latest.price_regular if latest else None,
            "price_original": latest.price_original if latest else None,
            "price_special": latest.price_special if latest else None,
            "price_wholesale": latest.price_wholesale if latest else None,
            "price_without_tax": latest.price_without_tax if latest else None,
            "stock_quantity": product.stock_quantity or 0,
            "in_stock": product.in_stock or False,
            "last_updated": latest.timestamp.isoformat() if latest else None,
        })

    pages = (total + page_size - 1) // page_size if total else 0

    return PaginatedPrices(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
