from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import ProductType, Product
from api.schemas import ProductTypeSchema, PaginatedProductTypes

router = APIRouter(prefix="/product-types", tags=["Product Types"])


@router.get("/", response_model=PaginatedProductTypes)
async def list_product_types(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all product types with product counts."""
    base = (
        select(ProductType, func.count(Product.id).label("cnt"))
        .outerjoin(Product)
        .group_by(ProductType.id)
    )
    if search:
        base = base.where(ProductType.name.ilike(f"%{search}%"))

    # Total count
    count_q = select(func.count()).select_from(select(ProductType.id).where(
        ProductType.name.ilike(f"%{search}%") if search else True
    ).subquery())
    total = await db.scalar(count_q) or 0

    # Paginated query
    offset = (page - 1) * page_size
    query = base.order_by(ProductType.name).offset(offset).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    pages = (total + page_size - 1) // page_size if total else 0

    return PaginatedProductTypes(
        items=[
            ProductTypeSchema(id=pt.id, name=pt.name, products_count=cnt)
            for pt, cnt in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


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
