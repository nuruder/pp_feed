"""
Scrape the full category tree from the site navigation menu.
Uses Playwright to render JS-dependent navigation.

Test independently:
    python -m scraper.categories
"""

import asyncio
import logging
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from sqlalchemy import select

from config import BASE_URL, PAGE_TIMEOUT
from db.database import AsyncSessionLocal, init_db
from db.models import Category

logger = logging.getLogger(__name__)

SITE_ROOT = "https://www.tiendapadelpoint.com"

# Known top-level category slugs
TOP_SLUGS = [
    "padel-rackets",
    "padel-shoes",
    "padel-bags-backpacks",
    "padel-clothing",
    "padel-balls",
    "padel-accessories",
    "other-sports",
    "flash-point",
]


def classify_category(href: str) -> tuple[str | None, bool]:
    """
    Returns (top_slug_match, is_subcategory).
    """
    path = urlparse(href).path.rstrip("/")
    segments = [s for s in path.split("/") if s]
    # e.g. ["en", "padel-shoes"] or ["en", "padel-shoes", "zapatillas-de-padel-adidas-en"]

    if len(segments) < 2:
        return None, False

    for slug in TOP_SLUGS:
        # Top-level categories may have slight URL variations
        # e.g. "padel-rackets-en" matches "padel-rackets"
        seg1 = segments[1]
        if seg1 == slug or seg1.startswith(slug + "-") or seg1.startswith(slug.replace("-", "")):
            is_sub = len(segments) == 3
            if len(segments) > 3:
                return None, False  # Too deep, likely a product or sub-sub
            return slug, is_sub

    return None, False


async def scrape_category_tree() -> list[dict]:
    """Extract full category tree from the nav menu only (not product links)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        )

        logger.info("Loading main page: %s", BASE_URL)
        await page.goto(BASE_URL, timeout=PAGE_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # Extract links ONLY from navigation menu areas
        nav_links = await page.evaluate("""
            () => {
                const links = [];
                // Target only nav/menu containers, not product grids
                const navSelectors = [
                    'nav a', '#menu a', '.main-menu a', '.navbar a',
                    '.mega-menu a', '.dropdown-menu a', '.nav-item a',
                    'header a', '.top-menu a',
                ];
                const seen = new Set();
                for (const sel of navSelectors) {
                    document.querySelectorAll(sel).forEach(a => {
                        const href = a.href;
                        const text = a.textContent.trim();
                        if (href && text && href.includes('/en/') && !seen.has(href)) {
                            seen.add(href);
                            links.push({href, text});
                        }
                    });
                }
                return links;
            }
        """)
        logger.info("Found %d navigation links", len(nav_links))

        # Also get product URLs from datalayerDataGMT to EXCLUDE them
        product_urls = await page.evaluate("""
            () => {
                try {
                    if (typeof datalayerDataGMT !== 'undefined') {
                        const products = datalayerDataGMT.products || [];
                        return (Array.isArray(products) ? products : Object.values(products))
                            .map(p => p.url).filter(Boolean);
                    }
                } catch(e) {}
                return [];
            }
        """)
        product_url_set = set(product_urls)

        # Build category tree
        top_categories = {}

        for link in nav_links:
            href = link["href"]
            name = link["text"]

            # Skip product URLs
            if href in product_url_set:
                continue
            # Skip utility pages
            if any(x in href for x in ["index.php", "account", "checkout", "wishlist", "information"]):
                continue

            top_slug, is_sub = classify_category(href)
            if not top_slug:
                continue

            if top_slug not in top_categories:
                top_categories[top_slug] = {"name": None, "url": None, "children": {}}

            if is_sub:
                if href not in top_categories[top_slug]["children"]:
                    top_categories[top_slug]["children"][href] = name
            else:
                if not top_categories[top_slug]["name"]:
                    top_categories[top_slug]["name"] = name
                    top_categories[top_slug]["url"] = href

        # Visit each category page to find subcategories not in the nav menu
        for slug, cat_data in top_categories.items():
            if not cat_data["url"]:
                cat_data["url"] = f"{SITE_ROOT}/en/{slug}"
                cat_data["name"] = slug.replace("-", " ").title()

            logger.info("Visiting category: %s (%s)", cat_data["name"], cat_data["url"])
            try:
                await page.goto(cat_data["url"], timeout=PAGE_TIMEOUT)
                await page.wait_for_load_state("networkidle")

                # Get product URLs on this page to exclude them
                page_product_urls = set(await page.evaluate("""
                    () => {
                        try {
                            if (typeof datalayerDataGMT !== 'undefined') {
                                const products = datalayerDataGMT.products || [];
                                return (Array.isArray(products) ? products : Object.values(products))
                                    .map(p => p.url).filter(Boolean);
                            }
                        } catch(e) {}
                        return [];
                    }
                """))

                # Get subcategory links from the page content
                # Look specifically in sidebar/refinement areas, not product grid
                sub_links = await page.evaluate("""
                    () => {
                        const links = [];
                        const selectors = [
                            '#column-left a', '.list-group a', '.refine-category a',
                            '.category-list a', '.subcategory a',
                            '.j3-subcategories a', '.module-category a',
                            // Also try nav links again on the category page
                            'nav a', '#menu a', '.mega-menu a', '.dropdown-menu a',
                        ];
                        const seen = new Set();
                        for (const sel of selectors) {
                            document.querySelectorAll(sel).forEach(a => {
                                const href = a.href;
                                const text = a.textContent.trim();
                                if (href && text && href.includes('/en/') && !seen.has(href)) {
                                    seen.add(href);
                                    links.push({href, text});
                                }
                            });
                        }
                        return links;
                    }
                """)

                for link in sub_links:
                    href = link["href"]
                    name = link["text"]

                    if href in page_product_urls:
                        continue
                    if any(x in href for x in ["index.php", "account", "checkout"]):
                        continue

                    sub_slug, is_sub = classify_category(href)
                    if sub_slug == slug and is_sub:
                        if href not in cat_data["children"]:
                            cat_data["children"][href] = name

            except Exception as e:
                logger.warning("Failed to load category page %s: %s", cat_data["url"], e)

            await asyncio.sleep(0.5)

        await browser.close()

    # Convert to tree structure
    tree = []
    for slug in TOP_SLUGS:
        if slug not in top_categories:
            continue
        cat_data = top_categories[slug]
        entry = {
            "name": cat_data["name"],
            "url": cat_data["url"],
            "children": [
                {"name": name, "url": url, "children": []}
                for url, name in sorted(cat_data["children"].items(), key=lambda x: x[1])
            ],
        }
        tree.append(entry)

    return tree


async def save_categories(tree: list[dict]):
    """Persist category tree to database."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for top in tree:
                parent = await _upsert_category(session, top["name"], top["url"], None, 0)
                for child in top.get("children", []):
                    await _upsert_category(session, child["name"], child["url"], parent.id, 1)


async def _upsert_category(
    session, name: str, url: str, parent_id: int | None, level: int
) -> Category:
    result = await session.execute(select(Category).where(Category.url == url))
    cat = result.scalar_one_or_none()
    if cat:
        cat.name = name
        cat.parent_id = parent_id
        cat.level = level
    else:
        cat = Category(name=name, url=url, parent_id=parent_id, level=level)
        session.add(cat)
        await session.flush()
    return cat


async def run():
    """Entry point for standalone testing."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    await init_db()

    tree = await scrape_category_tree()

    total_sub = sum(len(c["children"]) for c in tree)
    logger.info("Found %d top categories, %d subcategories", len(tree), total_sub)

    for cat in tree:
        logger.info("  %s (%d subcats)", cat["name"], len(cat["children"]))
        for sc in cat["children"]:
            logger.info("    - %s  [%s]", sc["name"], sc["url"])

    await save_categories(tree)
    logger.info("Categories saved to database")


if __name__ == "__main__":
    asyncio.run(run())
