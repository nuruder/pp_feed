from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import ProductType, Product
from api.schemas import ProductTypeSchema

router = APIRouter(prefix="/product-types", tags=["Product Types"])


@router.get("/", response_model=list[ProductTypeSchema])
async def list_product_types(db: AsyncSession = Depends(get_db)):
    """List all product types with product counts."""
    result = await db.execute(
        select(ProductType, func.count(Product.id).label("cnt"))
        .outerjoin(Product)
        .group_by(ProductType.id)
        .order_by(ProductType.name)
    )
    rows = result.all()

    return [
        ProductTypeSchema(id=pt.id, name=pt.name, products_count=cnt)
        for pt, cnt in rows
    ]


@router.get("/{product_type_id}", response_model=ProductTypeSchema)
async def get_product_type(product_type_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single product type."""
    result = await db.execute(select(ProductType).where(ProductType.id == product_type_id))
    pt = result.scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Product type not found")

    products_count = await db.scalar(
        select(func.count(Product.id)).where(Product.product_type_id == pt.id)
    )
    return ProductTypeSchema(id=pt.id, name=pt.name, products_count=products_count or 0)
