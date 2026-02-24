from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import Product, Brand, Category, PriceSnapshot, ProductSize, product_categories
from api.schemas import (
    ProductShort, ProductDetail, PaginatedProducts,
    PriceSnapshotSchema, SizeSchema, BrandSchema, CategoryShort,
)

router = APIRouter(prefix="/products", tags=["Products"])


def _build_product_short(product: Product, latest: PriceSnapshot | None) -> ProductShort:
    return ProductShort(
        id=product.id,
        external_id=product.external_id,
        name=product.name,
        url=product.url,
        image_url=product.image_url,
        brand=product.brand.name if product.brand else None,
        categories=[c.name for c in product.categories],
        in_stock=latest.in_stock if latest else False,
        price_regular=latest.price_regular if latest else None,
        price_original=latest.price_original if latest else None,
        price_wholesale=latest.price_wholesale if latest else None,
    )


async def _get_latest_snapshot(db: AsyncSession, product_id: int) -> PriceSnapshot | None:
    result = await db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/", response_model=PaginatedProducts)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category_id: int | None = None,
    brand_id: int | None = None,
    brand_name: str | None = None,
    in_stock: bool | None = None,
    search: str | None = None,
    sort_by: str = Query("name", pattern="^(name|price|updated)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    List products with filters and pagination.

    - **category_id**: Filter by category (via many-to-many)
    - **brand_id** / **brand_name**: Filter by brand
    - **in_stock**: Filter by availability (requires price snapshots)
    - **search**: Search by product name
    - **sort_by**: name, price, updated
    """
    query = (
        select(Product)
        .options(selectinload(Product.brand), selectinload(Product.categories))
    )

    if category_id is not None:
        query = query.join(product_categories).where(
            product_categories.c.category_id == category_id
        )
    if brand_id is not None:
        query = query.where(Product.brand_id == brand_id)
    if brand_name:
        query = query.join(Brand).where(Brand.name.ilike(f"%{brand_name}%"))
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Sorting
    if sort_by == "name":
        order = Product.name.asc() if sort_dir == "asc" else Product.name.desc()
    elif sort_by == "updated":
        order = Product.updated_at.desc() if sort_dir == "desc" else Product.updated_at.asc()
    else:
        order = Product.name.asc()
    query = query.order_by(order)

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().unique().all()

    # Get latest prices
    items = []
    for product in products:
        latest = await _get_latest_snapshot(db, product.id)

        # Apply in_stock filter (post-fetch since it depends on snapshots)
        if in_stock is not None:
            if latest is None and in_stock:
                continue
            if latest and latest.in_stock != in_stock:
                continue

        items.append(_build_product_short(product, latest))

    pages = (total + page_size - 1) // page_size if total else 0

    return PaginatedProducts(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Get full product details including sizes and price history."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.categories),
            selectinload(Product.sizes),
            selectinload(Product.price_snapshots),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    # Sort price history desc
    snapshots = sorted(product.price_snapshots, key=lambda s: s.timestamp, reverse=True)

    brand_schema = None
    if product.brand:
        brand_products_count = await db.scalar(
            select(func.count(Product.id)).where(Product.brand_id == product.brand.id)
        )
        brand_schema = BrandSchema(
            id=product.brand.id,
            name=product.brand.name,
            products_count=brand_products_count or 0,
        )

    cat_schemas = []
    for cat in product.categories:
        cat_schemas.append(CategoryShort(
            id=cat.id,
            name=cat.name,
            url=cat.url,
            level=cat.level,
            parent_id=cat.parent_id,
        ))

    return ProductDetail(
        id=product.id,
        external_id=product.external_id,
        name=product.name,
        url=product.url,
        image_url=product.image_url,
        description=product.description,
        model=product.model,
        brand=brand_schema,
        categories=cat_schemas,
        sizes=[
            SizeSchema(
                size_label=s.size_label,
                in_stock=s.in_stock,
                quantity=s.quantity,
            )
            for s in product.sizes
        ],
        latest_price=PriceSnapshotSchema.model_validate(snapshots[0]) if snapshots else None,
        price_history=[PriceSnapshotSchema.model_validate(s) for s in snapshots[:50]],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("/by-external/{external_id}", response_model=ProductDetail)
async def get_product_by_external_id(external_id: str, db: AsyncSession = Depends(get_db)):
    """Get product by its external site ID."""
    result = await db.execute(
        select(Product)
        .where(Product.external_id == external_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.categories),
            selectinload(Product.sizes),
            selectinload(Product.price_snapshots),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    # Reuse the same logic
    return await get_product(product.id, db)
