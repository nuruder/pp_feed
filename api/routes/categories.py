from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import Category, product_categories
from api.schemas import CategoryShort, CategoryTree

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("/", response_model=list[CategoryShort])
async def list_categories(
    parent_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List categories. Without parent_id returns top-level categories.
    With parent_id returns children of that category.
    """
    query = select(Category)
    if parent_id is not None:
        query = query.where(Category.parent_id == parent_id)
    else:
        query = query.where(Category.parent_id.is_(None))
    query = query.order_by(Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    items = []
    for cat in categories:
        # Count children
        children_count = await db.scalar(
            select(func.count(Category.id)).where(Category.parent_id == cat.id)
        )
        # Count products via association table
        products_count = await db.scalar(
            select(func.count(product_categories.c.product_id))
            .where(product_categories.c.category_id == cat.id)
        )
        items.append(CategoryShort(
            id=cat.id,
            name=cat.name,
            url=cat.url,
            level=cat.level,
            parent_id=cat.parent_id,
            children_count=children_count or 0,
            products_count=products_count or 0,
        ))

    return items


@router.get("/tree", response_model=list[CategoryTree])
async def category_tree(db: AsyncSession = Depends(get_db)):
    """Get full category tree."""
    result = await db.execute(
        select(Category).options(selectinload(Category.children)).order_by(Category.name)
    )
    all_cats = result.scalars().unique().all()

    # Count products per category via association table
    product_counts = {}
    count_result = await db.execute(
        select(
            product_categories.c.category_id,
            func.count(product_categories.c.product_id),
        ).group_by(product_categories.c.category_id)
    )
    for cat_id, count in count_result.all():
        product_counts[cat_id] = count

    def build_tree(cat: Category) -> CategoryTree:
        return CategoryTree(
            id=cat.id,
            name=cat.name,
            url=cat.url,
            level=cat.level,
            products_count=product_counts.get(cat.id, 0),
            children=[build_tree(c) for c in sorted(cat.children, key=lambda x: x.name)],
        )

    top_level = [c for c in all_cats if c.parent_id is None]
    return [build_tree(c) for c in top_level]


@router.get("/{category_id}", response_model=CategoryShort)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single category by ID."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")

    children_count = await db.scalar(
        select(func.count(Category.id)).where(Category.parent_id == cat.id)
    )
    products_count = await db.scalar(
        select(func.count(product_categories.c.product_id))
        .where(product_categories.c.category_id == cat.id)
    )

    return CategoryShort(
        id=cat.id,
        name=cat.name,
        url=cat.url,
        level=cat.level,
        parent_id=cat.parent_id,
        children_count=children_count or 0,
        products_count=products_count or 0,
    )
