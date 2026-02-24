from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Brand, Product
from api.schemas import BrandSchema, PaginatedBrands

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.get("/", response_model=PaginatedBrands)
async def list_brands(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all brands with product counts."""
    base = (
        select(Brand, func.count(Product.id).label("cnt"))
        .outerjoin(Product)
        .group_by(Brand.id)
    )
    if search:
        base = base.where(Brand.name.ilike(f"%{search}%"))

    # Total count
    count_q = select(func.count()).select_from(select(Brand.id).where(
        Brand.name.ilike(f"%{search}%") if search else True
    ).subquery())
    total = await db.scalar(count_q) or 0

    # Paginated query
    offset = (page - 1) * page_size
    query = base.order_by(Brand.name).offset(offset).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    pages = (total + page_size - 1) // page_size if total else 0

    return PaginatedBrands(
        items=[
            BrandSchema(id=brand.id, name=brand.name, products_count=cnt)
            for brand, cnt in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{brand_id}", response_model=BrandSchema)
async def get_brand(brand_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single brand."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(404, "Brand not found")

    products_count = await db.scalar(
        select(func.count(Product.id)).where(Product.brand_id == brand.id)
    )
    return BrandSchema(id=brand.id, name=brand.name, products_count=products_count or 0)
