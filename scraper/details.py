"""
Scrape detailed product information using Playwright.
Handles dynamic content: sizes, full descriptions, authenticated prices.

Test independently:
    python -m scraper.details [--url URL] [--auth]
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime

from playwright.async_api import async_playwright, Page
from sqlalchemy import select

from config import BASE_URL, REQUEST_DELAY, PAGE_TIMEOUT, CONCURRENT_PAGES
from db.database import AsyncSessionLocal, init_db
from db.models import Product, ProductSize, PriceSnapshot
from scraper.auth import load_cookies

logger = logging.getLogger(__name__)


async def extract_product_details(page: Page) -> dict:
    """Extract all product details from a rendered product page."""
    details = {
        "description": None,
        "sizes": [],
        "prices": {},
        "stock": {},
    }

    # --- datalayerDataGMT ---
    try:
        datalayer = await page.evaluate("""
            () => {
                if (typeof datalayerDataGMT !== 'undefined') return datalayerDataGMT;
                return null;
            }
        """)
    except Exception:
        datalayer = None

    if datalayer:
        products = (
            datalayer.get("products_listed")
            or datalayer.get("products")
            or datalayer.get("items")
            or []
        )
        if isinstance(products, dict):
            products = list(products.values())
        if products:
            raw_item = products[0] if isinstance(products, list) else products
            # Unwrap {"product": {...}} wrapper
            item = raw_item.get("product", raw_item) if isinstance(raw_item, dict) else raw_item
            prices = item.get("prices", {})
            details["prices"] = {
                "regular": _extract_price(prices.get("price") or item.get("price")),
                "original": _extract_price(prices.get("base_price") or item.get("base_price")),
                "special": _extract_price(prices.get("special") or item.get("special")),
                "without_tax": _extract_price(item.get("price_without_tax")),
            }
            details["stock"] = {
                "quantity": int(item.get("stock", item.get("quantity", 0)) or 0),
                "in_stock": str(item.get("availability", "")) != "OutOfStock",
            }

    # --- Description ---
    description_selectors = [
        "#tab-description",
        ".product-description",
        '[itemprop="description"]',
        ".description",
        "#content .tab-content .tab-pane:first-child",
    ]
    for sel in description_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                details["description"] = await el.inner_text()
                break
        except Exception:
            continue

    # --- Prices from DOM (more accurate for visual prices) ---
    price_selectors = {
        "regular": [".product-price", ".price-new", "#product-price", ".special-price"],
        "original": [".price-old", ".price-original", "del", ".old-price", "s"],
    }
    for price_type, selectors in price_selectors.items():
        if details["prices"].get(price_type) is not None:
            continue
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    text = await el.inner_text()
                    parsed = _parse_price_text(text)
                    if parsed:
                        details["prices"][price_type] = parsed
                        break
            except Exception:
                continue

    # --- Sizes/Options ---
    # Try select dropdowns
    option_selectors = [
        "select[id^='input-option']",
        "select.form-control[name^='option']",
        "#product select",
    ]
    for sel in option_selectors:
        try:
            select_el = page.locator(sel).first
            if await select_el.is_visible(timeout=2000):
                options = await select_el.evaluate("""
                    (el) => Array.from(el.options)
                        .filter(o => o.value)
                        .map(o => ({
                            value: o.value,
                            label: o.textContent.trim(),
                            disabled: o.disabled
                        }))
                """)
                for opt in options:
                    label = opt["label"]
                    # Check if out of stock marker in label
                    oos = "---" in label or "out of stock" in label.lower() or "agotad" in label.lower()
                    # Clean label
                    clean_label = re.sub(r'\s*[-–]\s*(out of stock|agotad[oa]|no disponible).*', '', label, flags=re.IGNORECASE).strip()
                    details["sizes"].append({
                        "label": clean_label,
                        "in_stock": not oos and not opt.get("disabled", False),
                    })
                if details["sizes"]:
                    break
        except Exception:
            continue

    # Try radio buttons / button groups for sizes
    if not details["sizes"]:
        radio_selectors = [
            ".product-options .radio label",
            ".option-value label",
            "input[type='radio'][name^='option'] + label",
        ]
        for sel in radio_selectors:
            try:
                labels = page.locator(sel)
                count = await labels.count()
                for i in range(count):
                    text = await labels.nth(i).inner_text()
                    text = text.strip()
                    if text:
                        details["sizes"].append({
                            "label": text,
                            "in_stock": True,  # Assume in stock unless marked
                        })
                if details["sizes"]:
                    break
            except Exception:
                continue

    return details


def _extract_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("price", value.get("amount"))
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        return _parse_price_text(value)
    return None


def _parse_price_text(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


async def scrape_product_detail(
    page: Page,
    product_url: str,
    is_authenticated: bool = False,
) -> dict | None:
    """Navigate to product page and extract details."""
    try:
        await page.goto(product_url, timeout=PAGE_TIMEOUT)
        await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
        # Give dynamic content extra time
        await asyncio.sleep(1)
    except Exception as e:
        logger.error("Failed to load %s: %s", product_url, e)
        return None

    details = await extract_product_details(page)
    details["url"] = product_url
    details["is_authenticated"] = is_authenticated
    return details


async def save_product_details(external_id: str, details: dict):
    """Save product details and price snapshot to database."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(Product).where(Product.external_id == external_id)
            )
            product = result.scalar_one_or_none()
            if not product:
                logger.warning("Product %s not found in DB", external_id)
                return

            # Update description if we got one
            if details.get("description"):
                product.description = details["description"]

            # Update sizes
            if details.get("sizes"):
                # Remove old sizes
                result = await session.execute(
                    select(ProductSize).where(ProductSize.product_id == product.id)
                )
                old_sizes = result.scalars().all()
                existing = {s.size_label: s for s in old_sizes}

                for sz in details["sizes"]:
                    if sz["label"] in existing:
                        existing[sz["label"]].in_stock = sz["in_stock"]
                    else:
                        session.add(ProductSize(
                            product_id=product.id,
                            size_label=sz["label"],
                            in_stock=sz["in_stock"],
                        ))

            # Create price snapshot
            prices = details.get("prices", {})
            stock = details.get("stock", {})

            if details.get("is_authenticated"):
                # Update wholesale price on latest snapshot or create new
                snapshot = PriceSnapshot(
                    product_id=product.id,
                    timestamp=datetime.utcnow(),
                    price_wholesale=prices.get("regular"),
                    price_regular=prices.get("regular"),
                    price_original=prices.get("original"),
                    price_special=prices.get("special"),
                    price_without_tax=prices.get("without_tax"),
                    stock_quantity=stock.get("quantity", 0),
                    in_stock=stock.get("in_stock", False),
                )
            else:
                snapshot = PriceSnapshot(
                    product_id=product.id,
                    timestamp=datetime.utcnow(),
                    price_regular=prices.get("regular"),
                    price_original=prices.get("original"),
                    price_special=prices.get("special"),
                    price_without_tax=prices.get("without_tax"),
                    stock_quantity=stock.get("quantity", 0),
                    in_stock=stock.get("in_stock", False),
                )

            session.add(snapshot)


async def scrape_all_details(authenticated: bool = False, limit: int = 0):
    """Scrape details for all products in DB."""
    await init_db()

    async with AsyncSessionLocal() as session:
        query = select(Product)
        if limit:
            query = query.limit(limit)
        result = await session.execute(query)
        products = result.scalars().all()

    logger.info("Scraping details for %d products (auth=%s)", len(products), authenticated)

    cookies = None
    if authenticated:
        cookies = load_cookies()
        if not cookies:
            logger.error("No cookies available. Run: python -m scraper.auth login")
            return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        )
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        for i, product in enumerate(products):
            logger.info("[%d/%d] %s", i + 1, len(products), product.name)
            details = await scrape_product_detail(page, product.url, authenticated)
            if details:
                await save_product_details(product.external_id, details)
                logger.info(
                    "  Prices: reg=%s orig=%s special=%s | Stock: %s | Sizes: %d",
                    details["prices"].get("regular"),
                    details["prices"].get("original"),
                    details["prices"].get("special"),
                    details["stock"].get("quantity"),
                    len(details.get("sizes", [])),
                )
            await asyncio.sleep(REQUEST_DELAY)

        await browser.close()

    logger.info("Done scraping details")


async def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    auth = "--auth" in sys.argv
    url = None
    for i, arg in enumerate(sys.argv):
        if arg == "--url" and i + 1 < len(sys.argv):
            url = sys.argv[i + 1]

    if url:
        # Single product test
        await init_db()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            if auth:
                cookies = load_cookies()
                if cookies:
                    await context.add_cookies(cookies)
            page = await context.new_page()

            details = await scrape_product_detail(page, url, auth)
            if details:
                print(json.dumps(details, indent=2, ensure_ascii=False, default=str))
            else:
                print("Failed to scrape product")

            await browser.close()
    else:
        limit = 5  # Default to 5 products for testing
        for i, arg in enumerate(sys.argv):
            if arg == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
            elif arg == "--all":
                limit = 0

        await scrape_all_details(authenticated=auth, limit=limit)


if __name__ == "__main__":
    asyncio.run(run())
