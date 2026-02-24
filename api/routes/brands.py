from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Brand, Product
from api.schemas import BrandSchema

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.get("/", response_model=list[BrandSchema])
async def list_brands(db: AsyncSession = Depends(get_db)):
    """List all brands with product counts."""
    result = await db.execute(
        select(Brand, func.count(Product.id).label("cnt"))
        .outerjoin(Product)
        .group_by(Brand.id)
        .order_by(Brand.name)
    )
    rows = result.all()

    return [
        BrandSchema(id=brand.id, name=brand.name, products_count=cnt)
        for brand, cnt in rows
    ]


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
