"""
Scrape product listings from category pages.
Extracts product data from datalayerDataGMT embedded JSON.

Test independently:
    python -m scraper.products
"""

import asyncio
import json
import logging
import re

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from config import BASE_URL, REQUEST_DELAY, CONCURRENT_PAGES
from db.database import AsyncSessionLocal, init_db
from db.models import Category, Brand, Product, ProductType

logger = logging.getLogger(__name__)


def extract_datalayer_products(html: str) -> list[dict]:
    """Extract product data from datalayerDataGMT JavaScript object."""
    products = []

    # Find the datalayerDataGMT object in script tags
    # Use a balanced brace approach since the JSON can be large
    marker = "datalayerDataGMT"
    idx = html.find(marker)
    if idx < 0:
        return products

    # Find the opening brace
    brace_start = html.find("{", idx)
    if brace_start < 0:
        return products

    # Find matching closing brace
    depth = 0
    end = brace_start
    for i in range(brace_start, min(brace_start + 500_000, len(html))):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    raw_json = html[brace_start:end]

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        logger.warning("Could not parse datalayerDataGMT JSON (%d chars)", len(raw_json))
        return products

    # Products can be in data.products_listed, data.products, or data.items
    # products_listed contains wrapped objects: [{"product": {...}}, ...]
    items = (
        data.get("products_listed")
        or data.get("products")
        or data.get("items")
        or []
    )
    if isinstance(items, dict):
        items = list(items.values())

    for raw_item in items:
        # Unwrap: products_listed wraps each item in {"product": {...}}
        item = raw_item.get("product", raw_item) if isinstance(raw_item, dict) else raw_item

        # Extract image URL from multiple possible locations
        image_url = (
            item.get("image")
            or item.get("image_url")
            or item.get("thumbnail")
            or item.get("thumb")
            or ""
        )
        # Check nested images object: {"images": {"main": "..."}}
        images = item.get("images", {})
        if not image_url and isinstance(images, dict):
            image_url = images.get("main") or images.get("thumb") or ""
        if not image_url and isinstance(images, list) and images:
            image_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")

        product = {
            "external_id": str(item.get("product_id", item.get("id", ""))),
            "name": item.get("name", ""),
            "url": item.get("url", ""),
            "image_url": image_url,
            "manufacturer": item.get("manufacturer", item.get("brand", "")),
            "category": item.get("category", ""),
            "model": str(item.get("model", "")),
            "price": _parse_price(item.get("price")),
            "base_price": _parse_price(item.get("base_price")),
            "special": _parse_price(item.get("special")),
            "stock": int(item.get("stock", item.get("quantity", 0)) or 0),
            "in_stock": "OutOfStock" not in str(item.get("availability", ""))
                if item.get("availability")
                else int(item.get("stock", item.get("quantity", 0)) or 0) > 0,
        }

        # Handle nested price objects like {"price": {"price": "391.36"}}
        prices = item.get("prices", {})
        if isinstance(prices, dict):
            if "price" in prices:
                p = prices["price"]
                product["price"] = _parse_price(p.get("price") if isinstance(p, dict) else p)
            if "base_price" in prices:
                p = prices["base_price"]
                product["base_price"] = _parse_price(p.get("price") if isinstance(p, dict) else p)
            if "special" in prices:
                p = prices["special"]
                product["special"] = _parse_price(p.get("price") if isinstance(p, dict) else p)

        if product["external_id"] and product["name"]:
            products.append(product)

    return products


def _parse_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        # Remove currency symbols, spaces, and handle comma as decimal
        cleaned = re.sub(r'[^\d.,]', '', value)
        if not cleaned:
            return None
        # Handle European format: 1.234,56
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        try:
            result = float(cleaned)
            return result if result > 0 else None
        except ValueError:
            return None
    if isinstance(value, dict):
        return _parse_price(value.get("price"))
    return None


def extract_image_urls_from_html(html: str) -> dict[str, str]:
    """
    Fallback: extract product images from product card <img> tags.
    Returns a dict mapping product URL → image URL.
    """
    soup = BeautifulSoup(html, "lxml")
    url_to_image = {}

    # Common product card selectors
    for card in soup.select(
        ".product-layout, .product-thumb, .product-card, "
        ".product-item, .product-grid .col, .j3-product"
    ):
        link = card.select_one("a[href]")
        img = card.select_one("img[src], img[data-src], img[data-lazy]")
        if link and img:
            href = link.get("href", "")
            img_src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy")
                or ""
            )
            # Skip placeholder/lazy-load base64 images
            if img_src and not img_src.startswith("data:") and href:
                url_to_image[href] = img_src

    return url_to_image


def find_pagination_urls(html: str, base_url: str) -> list[str]:
    """Find pagination links on the page."""
    soup = BeautifulSoup(html, "lxml")
    pages = set()

    # OpenCart pagination
    for link in soup.select(".pagination a, .page-link, a[href*='page=']"):
        href = link.get("href", "")
        if "page=" in href:
            pages.add(href)

    return sorted(pages)


async def scrape_category_products(
    client: httpx.AsyncClient,
    category_url: str,
) -> list[dict]:
    """Scrape all products from a category, handling pagination."""
    all_products = []
    seen_ids = set()

    # First page
    url = category_url
    page_num = 1

    while url:
        logger.info("  Page %d: %s", page_num, url)
        resp = None
        for attempt in range(1, 4):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                break
            except httpx.HTTPError as e:
                logger.warning("Attempt %d/3 failed for %s: %s", attempt, url, e)
                if attempt < 3:
                    await asyncio.sleep(REQUEST_DELAY * attempt)
        if resp is None or resp.status_code >= 400:
            logger.error("Failed to fetch %s after 3 attempts", url)
            break

        html = resp.text
        products = extract_datalayer_products(html)

        # Fill missing image URLs from product card HTML
        fallback_images = extract_image_urls_from_html(html)
        for p in products:
            if not p.get("image_url") and p.get("url") in fallback_images:
                p["image_url"] = fallback_images[p["url"]]

        new_count = 0
        for p in products:
            if p["external_id"] not in seen_ids:
                seen_ids.add(p["external_id"])
                all_products.append(p)
                new_count += 1

        logger.info("  Found %d products (%d new)", len(products), new_count)

        if new_count == 0:
            break

        # Check for next page
        pagination = find_pagination_urls(html, url)
        next_url = None
        for purl in pagination:
            # Find next page number
            m = re.search(r'page=(\d+)', purl)
            if m and int(m.group(1)) == page_num + 1:
                next_url = purl
                break

        url = next_url
        page_num += 1
        await asyncio.sleep(REQUEST_DELAY)

    return all_products


async def save_products(products: list[dict], category_id: int):
    """Save/update products in the database with many-to-many category link."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Load the category for this batch
            result = await session.execute(
                select(Category).where(Category.id == category_id)
            )
            category = result.scalar_one_or_none()

            for p in products:
                # Upsert brand (handle concurrent inserts via savepoint)
                # Upsert brand
                brand_id = None
                if p.get("manufacturer"):
                    result = await session.execute(
                        select(Brand).where(Brand.name == p["manufacturer"])
                    )
                    brand = result.scalar_one_or_none()
                    if not brand:
                        try:
                            async with session.begin_nested():
                                brand = Brand(name=p["manufacturer"])
                                session.add(brand)
                                await session.flush()
                        except IntegrityError:
                            result = await session.execute(
                                select(Brand).where(Brand.name == p["manufacturer"])
                            )
                            brand = result.scalar_one_or_none()
                    if brand:
                        brand_id = brand.id

                # Upsert product type
                product_type_id = None
                if p.get("category"):
                    result = await session.execute(
                        select(ProductType).where(ProductType.name == p["category"])
                    )
                    pt = result.scalar_one_or_none()
                    if not pt:
                        try:
                            async with session.begin_nested():
                                pt = ProductType(name=p["category"])
                                session.add(pt)
                                await session.flush()
                        except IntegrityError:
                            result = await session.execute(
                                select(ProductType).where(ProductType.name == p["category"])
                            )
                            pt = result.scalar_one_or_none()
                    if pt:
                        product_type_id = pt.id

                # Upsert product
                result = await session.execute(
                    select(Product).where(Product.external_id == p["external_id"])
                )
                product = result.scalar_one_or_none()
                if product:
                    product.name = p["name"]
                    product.url = p["url"]
                    if p.get("image_url"):
                        product.image_url = p["image_url"]
                    product.brand_id = brand_id
                    product.product_type_id = product_type_id
                    product.model = p.get("model")
                    product.stock_quantity = p.get("stock", 0)
                    product.in_stock = p.get("in_stock", False)
                    await session.refresh(product, ["categories"])
                    if category and category not in product.categories:
                        product.categories.append(category)
                else:
                    try:
                        async with session.begin_nested():
                            product = Product(
                                external_id=p["external_id"],
                                name=p["name"],
                                url=p["url"],
                                image_url=p.get("image_url"),
                                brand_id=brand_id,
                                product_type_id=product_type_id,
                                model=p.get("model"),
                                stock_quantity=p.get("stock", 0),
                                in_stock=p.get("in_stock", False),
                            )
                            session.add(product)
                            await session.flush()
                    except IntegrityError:
                        result = await session.execute(
                            select(Product).where(Product.external_id == p["external_id"])
                        )
                        product = result.scalar_one_or_none()
                        if product:
                            product.name = p["name"]
                            product.url = p["url"]
                            if p.get("image_url"):
                                product.image_url = p["image_url"]
                            product.brand_id = brand_id
                            product.product_type_id = product_type_id
                            product.model = p.get("model")
                            product.stock_quantity = p.get("stock", 0)
                            product.in_stock = p.get("in_stock", False)
                    if product and category:
                        await session.refresh(product, ["categories"])
                        if category not in product.categories:
                            product.categories.append(category)


async def scrape_all_categories():
    """Scrape products from all categories in the DB.

    Supports multiple URLs per category: loads URL list from categories.txt
    and merges products from all URLs into the same category.
    """
    await init_db()

    from scraper.categories import load_categories_from_file

    # Build mapping: canonical_url → list of all URLs
    file_cats = load_categories_from_file()
    url_map = {}  # canonical_url → [url1, url2, ...]
    for fc in file_cats:
        url_map[fc["urls"][0]] = fc["urls"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Category).where(Category.level > 0))
        categories = result.scalars().all()

        if not categories:
            # If no subcategories, use top-level
            result = await session.execute(select(Category))
            categories = result.scalars().all()

    logger.info("Scraping products from %d categories (%d concurrent)", len(categories), CONCURRENT_PAGES)

    semaphore = asyncio.Semaphore(CONCURRENT_PAGES)
    total_count = {"n": 0}

    async def _scrape_category(client, cat):
        async with semaphore:
            urls = url_map.get(cat.url, [cat.url])
            logger.info("Category: %s (%d URLs)", cat.name, len(urls))

            all_products = []
            seen_ids = set()
            for url in urls:
                products = await scrape_category_products(client, url)
                for p in products:
                    if p["external_id"] not in seen_ids:
                        seen_ids.add(p["external_id"])
                        all_products.append(p)

            if all_products:
                await save_products(all_products, cat.id)
                total_count["n"] += len(all_products)
            await asyncio.sleep(REQUEST_DELAY)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        timeout=30,
    ) as client:
        tasks = [_scrape_category(client, cat) for cat in categories]
        await asyncio.gather(*tasks)

    logger.info("Total products scraped: %d", total_count["n"])
    return total_count["n"]


async def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    total = await scrape_all_categories()
    logger.info("Done. %d products saved.", total)


if __name__ == "__main__":
    asyncio.run(run())
