import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import (
    Product, PriceSnapshot, Category, ProductSize,
    TgUser, Order, OrderItem, product_categories,
)
from api.schemas import (
    WebAppCategory, WebAppProductShort, WebAppProductDetail,
    OrderCreate, OrderSchema, OrderItemSchema, SizeSchema,
)

logger = logging.getLogger("pp_parser.webapp")
router = APIRouter(prefix="/webapp", tags=["Web App"])

# --- Margin filter constants ---
MIN_MARGIN_EUR = 5.0
MIN_MARGIN_PCT = 0.10


def _customer_price(price_regular: float, price_wholesale: float) -> float:
    """Price for customer = midpoint between wholesale and regular."""
    return round((price_wholesale + price_regular) / 2, 2)


def _has_margin(price_regular: float | None, price_wholesale: float | None) -> bool:
    """Check if product has enough margin to be listed."""
    if not price_regular or not price_wholesale:
        return False
    diff = price_regular - price_wholesale
    return diff >= MIN_MARGIN_EUR and diff / price_regular >= MIN_MARGIN_PCT


async def _get_latest_snapshot(db: AsyncSession, product_id: int) -> PriceSnapshot | None:
    result = await db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------- Categories ----------

@router.get("/categories", response_model=list[WebAppCategory])
async def webapp_categories(db: AsyncSession = Depends(get_db)):
    """Get categories that have marginal products."""
    result = await db.execute(
        select(Category).where(Category.level == 0).order_by(Category.name)
    )
    categories = result.scalars().all()

    items = []
    for cat in categories:
        # Count products in this category that have margin
        prod_result = await db.execute(
            select(Product.id)
            .join(product_categories)
            .where(product_categories.c.category_id == cat.id)
            .where(Product.in_stock.is_(True))
        )
        product_ids = [row[0] for row in prod_result.all()]

        count = 0
        for pid in product_ids:
            snap = await _get_latest_snapshot(db, pid)
            if snap and _has_margin(snap.price_regular, snap.price_wholesale):
                count += 1

        if count > 0:
            items.append(WebAppCategory(id=cat.id, name=cat.name, products_count=count))

    return items


# ---------- Products ----------

@router.get("/products", response_model=dict)
async def webapp_products(
    category_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get marginal products for the catalog."""
    query = (
        select(Product)
        .options(selectinload(Product.brand))
        .where(Product.in_stock.is_(True))
    )

    if category_id is not None:
        query = query.join(product_categories).where(
            product_categories.c.category_id == category_id
        )
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    query = query.order_by(Product.name)
    result = await db.execute(query)
    all_products = result.scalars().unique().all()

    # Filter by margin (requires latest snapshot)
    filtered = []
    for product in all_products:
        snap = await _get_latest_snapshot(db, product.id)
        if snap and _has_margin(snap.price_regular, snap.price_wholesale):
            filtered.append((product, snap))

    total = len(filtered)
    pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]

    items = []
    for product, snap in page_items:
        items.append(WebAppProductShort(
            id=product.id,
            name=product.name,
            image_url=product.image_url,
            price=_customer_price(snap.price_regular, snap.price_wholesale),
            price_old=snap.price_regular,
            in_stock=product.in_stock or False,
        ))

    return {"items": items, "total": total, "page": page, "pages": pages}


# ---------- Product detail ----------

@router.get("/products/{product_id}", response_model=WebAppProductDetail)
async def webapp_product_detail(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get single product with sizes."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.sizes))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    snap = await _get_latest_snapshot(db, product.id)
    if not snap or not _has_margin(snap.price_regular, snap.price_wholesale):
        raise HTTPException(404, "Product not available")

    return WebAppProductDetail(
        id=product.id,
        name=product.name,
        image_url=product.image_url,
        description=product.description,
        price=_customer_price(snap.price_regular, snap.price_wholesale),
        price_old=snap.price_regular,
        in_stock=product.in_stock or False,
        stock_quantity=product.stock_quantity or 0,
        sizes=[
            SizeSchema(
                size_label=s.size_label,
                in_stock=s.in_stock,
                quantity=s.quantity,
            )
            for s in product.sizes
        ],
    )


# ---------- Orders ----------

@router.post("/orders", response_model=OrderSchema)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create an order and notify manager."""
    if not data.items:
        raise HTTPException(400, "Order must have at least one item")

    # Upsert telegram user
    result = await db.execute(select(TgUser).where(TgUser.id == data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = TgUser(
            id=data.user_id,
            first_name=data.user_first_name,
            last_name=data.user_last_name,
            username=data.username,
            phone=data.customer_phone,
        )
        db.add(user)
        await db.flush()
    else:
        if data.customer_phone:
            user.phone = data.customer_phone

    # Build order items
    order_items = []
    total = 0.0

    for item in data.items:
        result = await db.execute(
            select(Product).where(Product.id == item.product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(400, f"Product {item.product_id} not found")

        snap = await _get_latest_snapshot(db, product.id)
        if not snap or not _has_margin(snap.price_regular, snap.price_wholesale):
            raise HTTPException(400, f"Product {product.name} is not available")

        price = _customer_price(snap.price_regular, snap.price_wholesale)
        order_items.append(OrderItem(
            product_id=product.id,
            size_label=item.size_label,
            quantity=item.quantity,
            price=price,
        ))
        total += price * item.quantity

    order = Order(
        user_id=data.user_id,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        total=round(total, 2),
        items=order_items,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order, attribute_names=["items"])

    # Load product names for response
    item_schemas = []
    for oi in order.items:
        result = await db.execute(select(Product.name).where(Product.id == oi.product_id))
        product_name = result.scalar_one()
        item_schemas.append(OrderItemSchema(
            product_id=oi.product_id,
            product_name=product_name,
            size_label=oi.size_label,
            quantity=oi.quantity,
            price=oi.price,
        ))

    # Notify manager via bot
    try:
        await _notify_manager(order, item_schemas, data)
    except Exception as e:
        logger.error("Failed to notify manager: %s", e)

    return OrderSchema(
        id=order.id,
        status=order.status,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        total=order.total,
        items=item_schemas,
        created_at=order.created_at,
    )


async def _notify_manager(order, items, data):
    """Send order notification to manager via Telegram."""
    from aiogram import Bot
    from config import TELEGRAM_BOT_TOKEN, MANAGER_CHAT_ID

    if not MANAGER_CHAT_ID:
        logger.warning("MANAGER_CHAT_ID not set, skipping notification")
        return

    lines = [
        f"\U0001f6d2 Новый заказ #{order.id}",
        f"\U0001f464 {order.customer_name}",
        f"\U0001f4de {order.customer_phone}",
    ]
    if data.username:
        lines.append(f"\U0001f4ac @{data.username}")

    lines.append("")
    for item in items:
        size_str = f" (р. {item.size_label})" if item.size_label else ""
        lines.append(
            f"  \u2022 {item.product_name}{size_str} "
            f"\u00d7{item.quantity} — \u20ac{item.price:.2f}"
        )

    lines.append(f"\n\U0001f4b0 Итого: \u20ac{order.total:.2f}")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(MANAGER_CHAT_ID, "\n".join(lines))
    finally:
        await bot.session.close()
