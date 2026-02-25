import logging
import re
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, URLInputFile, MenuButtonWebApp, WebAppInfo
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from db.database import AsyncSessionLocal
from db.models import Product, PriceSnapshot
from config import TELEGRAM_BOT_TOKEN, WEBAPP_URL

logger = logging.getLogger("pp_parser.bot")
router = Router()


async def _get_latest_snapshot(session, product_id):
    result = await session.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _format_card(product: Product, snapshot: PriceSnapshot | None) -> str:
    lines = [f"\U0001f4e6 {product.name}"]
    if snapshot:
        if snapshot.price_original:
            lines.append(f"\U0001f3f7 Обычная цена: \u20ac{snapshot.price_original:.2f}")
        if snapshot.price_regular:
            lines.append(f"\U0001f4b0 Со скидкой: \u20ac{snapshot.price_regular:.2f}")
        if snapshot.price_wholesale:
            lines.append(f"\U0001f3ea Оптовая: \u20ac{snapshot.price_wholesale:.2f}")
    qty = product.stock_quantity or 0
    status = f"{qty} шт." if product.in_stock else "Нет в наличии"
    lines.append(f"\U0001f4ca На складе: {status}")
    lines.append(f"\U0001f517 {product.url}")
    return "\n".join(lines)


def _extract_urls_from_message(message: Message) -> list[str]:
    """Extract all tiendapadelpoint URLs from message text and entities."""
    urls = set()
    text = message.text or ""

    # 1. From entities (handles forwarded messages, hyperlinks, etc.)
    for entity in message.entities or []:
        if entity.type == "url":
            url = text[entity.offset:entity.offset + entity.length]
            if "tiendapadelpoint.com" in url:
                urls.add(url)
        elif entity.type == "text_link" and entity.url:
            if "tiendapadelpoint.com" in entity.url:
                urls.add(entity.url)

    # 2. From plain text (with or without protocol)
    for match in re.findall(r'(?:https?://)?(?:www\.)?tiendapadelpoint\.com\S*', text):
        urls.add(match)

    return list(urls)


def _extract_slug(raw_url: str) -> str:
    # Add scheme if missing so urlparse works correctly
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url
    parsed = urlparse(raw_url)
    return parsed.path.rstrip("/").rsplit("/", 1)[-1]


async def _send_product(message: Message, product: Product, snapshot: PriceSnapshot | None):
    text = _format_card(product, snapshot)
    if product.image_url:
        try:
            await message.answer_photo(URLInputFile(product.image_url), caption=text)
        except Exception:
            await message.answer(text)
    else:
        await message.answer(text)


@router.message(CommandStart())
async def handle_start(message: Message, bot: Bot):
    text = "Добро пожаловать! Я помогу найти товары для падель-тенниса."
    if WEBAPP_URL:
        text += "\n\nНажмите кнопку «Каталог» внизу, чтобы открыть магазин."
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="Каталог", web_app=WebAppInfo(url=WEBAPP_URL)),
        )
    text += "\n\nИли отправьте мне:\n• Ссылку на товар — получите карточку с ценами\n• Название — найду подходящие товары"
    await message.answer(text)


@router.message(F.text.contains("tiendapadelpoint.com"))
async def handle_url(message: Message):
    urls = _extract_urls_from_message(message)
    if not urls:
        await message.answer("Не удалось распознать ссылку.")
        return

    not_found = []
    async with AsyncSessionLocal() as session:
        for raw_url in urls:
            slug = _extract_slug(raw_url)
            if not slug:
                not_found.append(raw_url)
                continue
            result = await session.execute(
                select(Product)
                .options(selectinload(Product.brand))
                .where(Product.url.ilike(f"%{slug}%"))
                .limit(1)
            )
            product = result.scalar_one_or_none()
            if not product:
                not_found.append(raw_url)
                continue
            snapshot = await _get_latest_snapshot(session, product.id)
            await _send_product(message, product, snapshot)

    if not_found:
        await message.answer("Не найдены в базе:\n" + "\n".join(not_found))


@router.message()
async def handle_search(message: Message):
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Введите название товара (минимум 2 символа) или ссылку.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Product)
            .options(selectinload(Product.brand))
            .where(Product.name.ilike(f"%{query}%"))
            .order_by(Product.name)
            .limit(5)
        )
        products = result.scalars().all()

    if not products:
        await message.answer("Ничего не найдено.")
        return

    async with AsyncSessionLocal() as session:
        for product in products:
            snapshot = await _get_latest_snapshot(session, product.id)
            await _send_product(message, product, snapshot)


async def start_bot():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env")
        return
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Starting Telegram bot...")
    await dp.start_polling(bot)
