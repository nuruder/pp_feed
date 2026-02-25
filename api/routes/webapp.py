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
MIN_MARGIN_PCT = 0.05


def _customer_price(price_regular: float, price_wholesale: float) -> float:
    """Price for customer = midpoint between wholesale and regular."""
    return round((price_wholesale + price_regular) / 2, 2)


def _has_margin(price_regular: float | None, price_wholesale: float | None) -> bool:
    """Check if product has enough margin to be listed."""
    if not price_regular or not price_wholesale:
        return False
    diff = price_regular - price_wholesale
    return diff >= MIN_MARGIN_EUR and diff / price_regular >= MIN_MARGIN_PCT


def _marginal_subquery():
    """
    Subquery returning (product_id, price_regular, price_wholesale)
    for products whose latest snapshot passes the margin filter.
    Single SQL instead of N+1 queries.
    """
    # Step 1: rank snapshots per product by timestamp (newest first)
    ranked = (
        select(
            PriceSnapshot.product_id,
            PriceSnapshot.price_regular,
            PriceSnapshot.price_wholesale,
            func.row_number().over(
                partition_by=PriceSnapshot.product_id,
                order_by=desc(PriceSnapshot.timestamp),
            ).label("rn"),
        )
        .where(PriceSnapshot.price_regular.isnot(None))
        .where(PriceSnapshot.price_wholesale.isnot(None))
        .subquery()
    )

    # Step 2: keep only latest (rn=1) + margin filter
    marginal = (
        select(
            ranked.c.product_id,
            ranked.c.price_regular,
            ranked.c.price_wholesale,
        )
        .where(ranked.c.rn == 1)
        .where(
            (ranked.c.price_regular - ranked.c.price_wholesale) >= MIN_MARGIN_EUR
        )
        .where(
            (ranked.c.price_regular - ranked.c.price_wholesale)
            / ranked.c.price_regular >= MIN_MARGIN_PCT
        )
        .subquery()
    )

    return marginal


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
    """Get categories that have marginal products (single SQL query)."""
    marginal = _marginal_subquery()

    query = (
        select(
            Category.id,
            Category.name,
            func.count(marginal.c.product_id).label("cnt"),
        )
        .join(product_categories, product_categories.c.category_id == Category.id)
        .join(Product, Product.id == product_categories.c.product_id)
        .join(marginal, marginal.c.product_id == Product.id)
        .where(Category.level == 0)
        .where(Product.in_stock.is_(True))
        .group_by(Category.id, Category.name)
        .having(func.count(marginal.c.product_id) > 0)
        .order_by(Category.name)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        WebAppCategory(id=row.id, name=row.name, products_count=row.cnt)
        for row in rows
    ]


# ---------- Products ----------

@router.get("/products", response_model=dict)
async def webapp_products(
    category_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get marginal products for the catalog (single SQL query)."""
    marginal = _marginal_subquery()

    query = (
        select(
            Product.id,
            Product.name,
            Product.image_url,
            Product.in_stock,
            marginal.c.price_regular,
            marginal.c.price_wholesale,
        )
        .join(marginal, marginal.c.product_id == Product.id)
        .where(Product.in_stock.is_(True))
    )

    if category_id is not None:
        query = query.join(product_categories).where(
            product_categories.c.category_id == category_id
        )
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))

    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_q) or 0

    # Paginate at SQL level
    offset = (page - 1) * page_size
    query = query.order_by(Product.name).offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = [
        WebAppProductShort(
            id=row.id,
            name=row.name,
            image_url=row.image_url,
            price=_customer_price(row.price_regular, row.price_wholesale),
            price_old=row.price_regular,
            in_stock=row.in_stock or False,
        )
        for row in rows
    ]

    pages = math.ceil(total / page_size) if total else 0
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

    # Load product info for response/notification
    item_schemas = []
    wholesale_prices = {}  # product_id -> wholesale price
    product_urls = {}      # product_id -> url
    for oi in order.items:
        result = await db.execute(
            select(Product.name, Product.url).where(Product.id == oi.product_id)
        )
        row = result.one()
        item_schemas.append(OrderItemSchema(
            product_id=oi.product_id,
            product_name=row.name,
            size_label=oi.size_label,
            quantity=oi.quantity,
            price=oi.price,
        ))
        product_urls[oi.product_id] = row.url
        snap = await _get_latest_snapshot(db, oi.product_id)
        if snap and snap.price_wholesale:
            wholesale_prices[oi.product_id] = snap.price_wholesale

    # Notify manager via bot
    try:
        await _notify_manager(order, item_schemas, data, wholesale_prices, product_urls)
    except Exception as e:
        logger.error("Failed to notify manager: %s", e, exc_info=True)

    return OrderSchema(
        id=order.id,
        status=order.status,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        total=order.total,
        items=item_schemas,
        created_at=order.created_at,
    )


@router.get("/test-notify")
async def test_notify():
    """Debug endpoint: test sending a message to MANAGER_CHAT_ID. Remove after debugging."""
    from aiogram import Bot
    from config import TELEGRAM_BOT_TOKEN, MANAGER_CHAT_ID

    info = {
        "token_set": bool(TELEGRAM_BOT_TOKEN),
        "token_preview": TELEGRAM_BOT_TOKEN[:10] + "..." if TELEGRAM_BOT_TOKEN else "",
        "chat_id": MANAGER_CHAT_ID,
    }

    if not TELEGRAM_BOT_TOKEN or not MANAGER_CHAT_ID:
        return {**info, "error": "TELEGRAM_BOT_TOKEN or MANAGER_CHAT_ID not set"}

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        result = await bot.send_message(MANAGER_CHAT_ID, "Test notification from PadelPoint Web App")
        return {**info, "success": True, "message_id": result.message_id}
    except Exception as e:
        return {**info, "success": False, "error": str(e)}
    finally:
        await bot.session.close()


async def _notify_manager(order, items, data, wholesale_prices=None, product_urls=None):
    """Send order notification to manager via Telegram (HTML)."""
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from config import TELEGRAM_BOT_TOKEN, MANAGER_CHAT_ID

    wholesale_prices = wholesale_prices or {}
    product_urls = product_urls or {}

    if not MANAGER_CHAT_ID:
        logger.warning("MANAGER_CHAT_ID not set, skipping notification")
        return

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping notification")
        return

    lines = [
        f"\U0001f6d2 Новый заказ #{order.id}",
        f"\U0001f464 {order.customer_name}",
        f"\U0001f4de {order.customer_phone}",
    ]
    if data.username:
        lines.append(f"\U0001f4ac @{data.username}")

    lines.append("")
    total_wholesale = 0.0
    for item in items:
        size_str = f" (р. {item.size_label})" if item.size_label else ""
        ws = wholesale_prices.get(item.product_id)
        ws_str = f" (опт \u20ac{ws:.2f})" if ws else ""
        url = product_urls.get(item.product_id)
        name_html = f'<a href="{url}">{item.product_name}</a>' if url else item.product_name
        lines.append(
            f"  \u2022 {name_html}{size_str} "
            f"\u00d7{item.quantity} \u2014 \u20ac{item.price:.2f}{ws_str}"
        )
        if ws:
            total_wholesale += ws * item.quantity

    margin = order.total - total_wholesale
    lines.append(f"\n\U0001f4b0 Итого: \u20ac{order.total:.2f}")
    if total_wholesale > 0:
        lines.append(f"\U0001f4c8 Маржа: \u20ac{margin:.2f}")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            MANAGER_CHAT_ID, "\n".join(lines), parse_mode=ParseMode.HTML,
        )
        logger.info("Order #%d notification sent to chat %s", order.id, MANAGER_CHAT_ID)
    finally:
        await bot.session.close()
