"""
Orchestrator for scraping runs.

Single flow:
  1. Sync categories from categories.txt → DB
  2. Scrape product listings from all categories
  3. Scrape product details (guest — prices, stock, sizes, descriptions)
  4. Authenticate → scrape product details (wholesale prices)

Test independently:
    python -m scraper.runner
"""

import asyncio
import logging
import sys
from datetime import datetime

from db.database import init_db
from scraper.categories import sync_categories
from scraper.products import scrape_all_categories
from scraper.details import scrape_all_details
from scraper.auth import ensure_authenticated, check_session_valid, load_cookies

logger = logging.getLogger(__name__)


async def run_scrape():
    """Complete scrape: categories → products → guest details → auth details."""
    start = datetime.utcnow()
    logger.info("=== SCRAPE started at %s ===", start)

    await init_db()

    # Step 1: Sync categories from file
    logger.info("--- Step 1: Syncing categories from file ---")
    categories = await sync_categories()
    if not categories:
        logger.error("No categories to scrape. Check categories.txt")
        return
    logger.info("Synced %d categories", len(categories))

    # Step 2: Scrape product listings
    logger.info("--- Step 2: Scraping product listings ---")
    total = await scrape_all_categories()
    logger.info("Found %d products total", total)

    # Step 3: Guest details (prices, sizes, descriptions, stock)
    logger.info("--- Step 3: Scraping product details (guest) ---")
    await scrape_all_details(authenticated=False)

    # Step 4: Authenticated details (wholesale prices)
    logger.info("--- Step 4: Authenticating and scraping wholesale prices ---")
    cookies = load_cookies()
    if cookies and await check_session_valid(cookies):
        logger.info("Using saved session")
    else:
        logger.info("Attempting login...")
        cookies = await ensure_authenticated()

    if cookies:
        await scrape_all_details(authenticated=True)
    else:
        logger.warning("Authentication failed. Skipping wholesale prices.")
        logger.warning("Run: python run.py auth login")

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info("=== SCRAPE completed in %.1f seconds ===", elapsed)


async def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    await run_scrape()


if __name__ == "__main__":
    asyncio.run(run())
