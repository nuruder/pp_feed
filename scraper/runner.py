"""
Orchestrator for scraping runs.

Two modes:
  - full:  Categories → Product listings → Details (guest) → Details (auth)
  - quick: Price + stock update only (guest + auth)

Test independently:
    python -m scraper.runner full
    python -m scraper.runner quick
"""

import asyncio
import logging
import sys
from datetime import datetime

from db.database import init_db
from scraper.categories import run as run_categories
from scraper.products import scrape_all_categories
from scraper.details import scrape_all_details
from scraper.auth import check_session_valid, load_cookies

logger = logging.getLogger(__name__)


async def full_run():
    """Complete scrape: categories, products, details (guest + auth)."""
    start = datetime.utcnow()
    logger.info("=== FULL RUN started at %s ===", start)

    await init_db()

    # Step 1: Categories
    logger.info("--- Step 1: Scraping categories ---")
    await run_categories()

    # Step 2: Product listings
    logger.info("--- Step 2: Scraping product listings ---")
    total = await scrape_all_categories()
    logger.info("Found %d products total", total)

    # Step 3: Guest details (prices, sizes, descriptions)
    logger.info("--- Step 3: Scraping product details (guest) ---")
    await scrape_all_details(authenticated=False)

    # Step 4: Authenticated details (wholesale prices)
    logger.info("--- Step 4: Scraping product details (authenticated) ---")
    cookies = load_cookies()
    if cookies and await check_session_valid(cookies):
        await scrape_all_details(authenticated=True)
    else:
        logger.warning("No valid session. Skipping authenticated scrape.")
        logger.warning("Run: python -m scraper.auth login")

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info("=== FULL RUN completed in %.1f seconds ===", elapsed)


async def quick_run():
    """Quick update: prices and stock only (no new products/descriptions)."""
    start = datetime.utcnow()
    logger.info("=== QUICK RUN started at %s ===", start)

    await init_db()

    # Guest prices
    logger.info("--- Updating prices (guest) ---")
    await scrape_all_details(authenticated=False)

    # Auth prices
    logger.info("--- Updating prices (authenticated) ---")
    cookies = load_cookies()
    if cookies and await check_session_valid(cookies):
        await scrape_all_details(authenticated=True)
    else:
        logger.warning("No valid session. Skipping authenticated scrape.")
        logger.warning("Run: python -m scraper.auth login")

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info("=== QUICK RUN completed in %.1f seconds ===", elapsed)


async def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "full":
        await full_run()
    elif mode == "quick":
        await quick_run()
    else:
        logger.error("Unknown mode: %s. Use 'full' or 'quick'.", mode)


if __name__ == "__main__":
    asyncio.run(run())
