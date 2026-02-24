"""
Load categories from categories.txt and upsert into the database.

File format (one category per line):
    Name, https://example.com/category-url

Lines starting with # and empty lines are ignored.

Test independently:
    python -m scraper.categories
"""

import asyncio
import logging

from sqlalchemy import select

from config import CATEGORIES_FILE
from db.database import AsyncSessionLocal, init_db
from db.models import Category

logger = logging.getLogger(__name__)


def load_categories_from_file() -> list[dict]:
    """Read categories from the txt file."""
    if not CATEGORIES_FILE.exists():
        logger.error("Categories file not found: %s", CATEGORIES_FILE)
        return []

    categories = []
    for line_num, line in enumerate(CATEGORIES_FILE.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split on first comma: "Name, URL"
        parts = line.split(",", 1)
        if len(parts) != 2:
            logger.warning("Line %d: invalid format (expected 'Name, URL'): %s", line_num, line)
            continue

        name = parts[0].strip()
        url = parts[1].strip()

        if not name or not url:
            logger.warning("Line %d: empty name or URL: %s", line_num, line)
            continue

        categories.append({"name": name, "url": url})

    return categories


async def save_categories(categories: list[dict]):
    """Upsert categories into the database."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for cat in categories:
                result = await session.execute(
                    select(Category).where(Category.url == cat["url"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.name = cat["name"]
                    existing.level = 0
                    logger.info("  Updated: %s", cat["name"])
                else:
                    session.add(Category(
                        name=cat["name"],
                        url=cat["url"],
                        parent_id=None,
                        level=0,
                    ))
                    logger.info("  Added: %s", cat["name"])


async def sync_categories() -> list[dict]:
    """Load categories from file and sync to database. Returns the list."""
    categories = load_categories_from_file()
    if not categories:
        logger.warning("No categories loaded from %s", CATEGORIES_FILE)
        return []

    logger.info("Loaded %d categories from %s", len(categories), CATEGORIES_FILE)
    await save_categories(categories)
    return categories


async def run():
    """Entry point for standalone testing."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    await init_db()

    categories = await sync_categories()
    logger.info("Done. %d categories synced to database.", len(categories))


if __name__ == "__main__":
    asyncio.run(run())
