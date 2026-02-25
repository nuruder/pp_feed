from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
COOKIES_PATH = BASE_DIR / "data" / "cookies.json"
LOGS_DIR = BASE_DIR / "data" / "logs"
CATEGORIES_FILE = BASE_DIR / "categories.txt"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://padelpoint:padelpoint@localhost:5432/padelpoint",
)

BASE_URL = "https://www.tiendapadelpoint.com/en"
LOGIN_URL = f"{BASE_URL}/index.php?route=account/login"

# Credentials (set via .env or environment)
PP_EMAIL = os.getenv("PP_EMAIL", "")
PP_PASSWORD = os.getenv("PP_PASSWORD", "")

# 2Captcha
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")

# Scraper settings
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))  # seconds between requests
CONCURRENT_PAGES = int(os.getenv("CONCURRENT_PAGES", "3"))
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "30000"))  # ms

# Telegram bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MANAGER_CHAT_ID = int(os.getenv("MANAGER_CHAT_ID", "0"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Schedule: hours in 24h format
SCHEDULE_HOURS = [1]  # 01:00
