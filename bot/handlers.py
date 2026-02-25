import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo

from config import TELEGRAM_BOT_TOKEN, WEBAPP_URL

logger = logging.getLogger("pp_parser.bot")
router = Router()


@router.message(CommandStart())
async def handle_start(message: Message, bot: Bot):
    text = "Добро пожаловать! Я помогу найти товары для падела."
    if WEBAPP_URL:
        text += "\n\nНажмите кнопку «Каталог» внизу, чтобы открыть магазин."
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="Каталог", web_app=WebAppInfo(url=WEBAPP_URL)),
        )
    await message.answer(text)


async def start_bot():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env")
        return
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Starting Telegram bot...")
    await dp.start_polling(bot)
