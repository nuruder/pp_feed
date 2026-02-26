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
from db.models import Product, ProductType, ProductSize, PriceSnapshot
from sqlalchemy.exc import IntegrityError
from scraper.auth import load_cookies

logger = logging.getLogger(__name__)


async def extract_product_details(page: Page) -> dict:
    """Extract all product details from a rendered product page."""
    details = {
        "description": None,
        "category": None,
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
        logger.debug("datalayer keys: %s", list(datalayer.keys()) if isinstance(datalayer, dict) else type(datalayer))

        item = None

        # Product detail pages: data is in product_details.product
        pd = datalayer.get("product_details")
        if isinstance(pd, dict) and pd.get("product"):
            item = pd["product"]
            logger.debug("Found product in product_details.product")

        # Category/listing pages: data is in products_listed / products / items
        if not item:
            products = (
                datalayer.get("products_listed")
                or datalayer.get("products")
                or datalayer.get("items")
                or []
            )
            if isinstance(products, dict):
                products = list(products.values())

            # Also try singular keys
            if not products:
                single = datalayer.get("product_detail") or datalayer.get("product")
                if single:
                    products = [single]

            if products:
                raw_item = products[0] if isinstance(products, list) else products
                # Unwrap {"product": {...}} wrapper
                item = raw_item.get("product", raw_item) if isinstance(raw_item, dict) else raw_item

        if item and isinstance(item, dict):
            logger.debug("datalayer item keys: %s", list(item.keys()))
            # Category / product type
            if item.get("category"):
                details["category"] = item["category"]
            prices = item.get("prices", {})
            # Extract without_tax from nested price object: prices.price.without_tax
            without_tax = None
            price_obj = prices.get("price")
            if isinstance(price_obj, dict):
                without_tax = _extract_price(price_obj.get("without_tax"))
            if without_tax is None:
                without_tax = _extract_price(item.get("price_without_tax"))

            details["prices"] = {
                "regular": _extract_price(prices.get("price") or item.get("price")),
                "original": _extract_price(prices.get("base_price") or item.get("base_price")),
                "special": _extract_price(prices.get("special") or item.get("special")),
                "without_tax": without_tax,
            }
            # availability can be full URL like "https://schema.org/OutOfStock"
            availability = str(item.get("availability", ""))
            details["stock"] = {
                "quantity": int(item.get("stock", item.get("quantity", 0)) or 0),
                "in_stock": "OutOfStock" not in availability,
            }
        else:
            logger.debug("datalayer found but no product data in it")
    else:
        logger.debug("No datalayerDataGMT on page")

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

    # --- Prices from DOM (fallback / more accurate for visual prices) ---
    price_selectors = {
        "regular": [
            ".product-price", ".price-new", "#product-price", ".special-price",
            ".autocalc-product-price", ".price .price-new", "[data-price]",
            "span.price", ".product-info .price", "#content .price",
            ".j3-product-price .price-new", ".j3-product-price span",
        ],
        "original": [
            ".price-old", ".price-original", "del", ".old-price", "s",
            ".price .price-old", ".j3-product-price .price-old",
        ],
    }

    # If no prices from datalayer, also try a broad approach
    if not details["prices"].get("regular"):
        # Try to extract all prices from the price container
        try:
            price_container = await page.evaluate("""
                () => {
                    const selectors = [
                        '.price', '#product .price', '.product-info .price',
                        '.j3-product-price', '.product-price-group',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.textContent.trim()) {
                            return el.innerHTML;
                        }
                    }
                    return null;
                }
            """)
            if price_container:
                logger.debug("Price container HTML: %s", price_container[:300])
        except Exception:
            pass

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
                        logger.debug("Price %s from DOM (%s): %s", price_type, sel, parsed)
                        break
            except Exception:
                continue

    # --- Structured data / meta fallback for prices ---
    if not details["prices"].get("regular"):
        try:
            meta_price = await page.evaluate("""
                () => {
                    // JSON-LD
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of scripts) {
                        try {
                            const data = JSON.parse(s.textContent);
                            const offers = data.offers || (data['@graph'] || []).find(x => x.offers)?.offers;
                            if (offers) {
                                const price = offers.price || (offers[0] && offers[0].price);
                                if (price) return {price: String(price), currency: offers.priceCurrency || ''};
                            }
                        } catch(e) {}
                    }
                    // og:price / product:price
                    const meta = document.querySelector('meta[property="product:price:amount"], meta[property="og:price:amount"]');
                    if (meta) return {price: meta.content, currency: ''};
                    // itemprop price
                    const itemprop = document.querySelector('[itemprop="price"]');
                    if (itemprop) {
                        const v = itemprop.content || itemprop.textContent;
                        if (v) return {price: v.trim(), currency: ''};
                    }
                    return null;
                }
            """)
            if meta_price:
                parsed = _parse_price_text(meta_price["price"])
                if parsed:
                    details["prices"]["regular"] = parsed
                    logger.debug("Price from structured data: %s", parsed)
        except Exception:
            pass

    # --- Gallery images ---
    try:
        gallery_images = await page.evaluate("""
            () => {
                const urls = new Set();

                // 1. Dedicated gallery/carousel selectors (OpenCart, common themes)
                const gallerySelectors = [
                    '.product-image a[href]',
                    '.product-gallery a[href]',
                    '.thumbnails a[href]',
                    '.image-additional a[href]',
                    '.product-images a[href]',
                    '.swiper-slide a[href]',
                    '.product-thumb-list a[href]',
                    '.fotorama a[href], .fotorama img[src]',
                    '.owl-carousel .item a[href]',
                    '.product-thumbs a[href]',
                    '#image-gallery a[href]',
                ];
                for (const sel of gallerySelectors) {
                    document.querySelectorAll(sel).forEach(el => {
                        const href = el.href || el.getAttribute('href') || '';
                        if (href && !href.startsWith('data:') && !href.startsWith('javascript:')
                            && (href.includes('.jpg') || href.includes('.jpeg') || href.includes('.png')
                                || href.includes('.webp') || href.includes('/image/'))) {
                            urls.add(href);
                        }
                    });
                }

                // 2. Thumbnail images if no links found
                if (urls.size === 0) {
                    const thumbSelectors = [
                        '.product-image img',
                        '.product-gallery img',
                        '.thumbnails img',
                        '.image-additional img',
                        '.product-images img',
                    ];
                    for (const sel of thumbSelectors) {
                        document.querySelectorAll(sel).forEach(img => {
                            const src = img.getAttribute('data-zoom-image')
                                || img.getAttribute('data-large')
                                || img.getAttribute('data-src')
                                || img.src || '';
                            if (src && !src.startsWith('data:')) {
                                urls.add(src);
                            }
                        });
                    }
                }

                // 3. Main product image (always include)
                const mainSelectors = [
                    '.product-image > a > img',
                    '#product-image',
                    '.main-image img',
                    '[itemprop="image"]',
                ];
                for (const sel of mainSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const src = el.getAttribute('data-zoom-image')
                            || el.closest('a')?.href
                            || el.getAttribute('data-large')
                            || el.src || '';
                        if (src && !src.startsWith('data:')) {
                            urls.add(src);
                        }
                    }
                }

                return [...urls];
            }
        """)
        if gallery_images:
            details["images"] = gallery_images
            logger.debug("Found %d gallery images", len(gallery_images))
    except Exception as e:
        logger.debug("Gallery extraction error: %s", e)

    # --- Sizes/Options ---
    # Extract all options from the page via JS (handles dynamically rendered elements)
    try:
        raw_options = await page.evaluate("""
            () => {
                const results = [];

                // 1. All select dropdowns with options
                document.querySelectorAll('select').forEach(sel => {
                    const id = sel.id || '';
                    const name = sel.name || '';
                    // Only product option selects (not quantity, currency, etc.)
                    if (id.includes('option') || name.includes('option') ||
                        sel.closest('.product-options, .form-group, #product, .product-info')) {
                        Array.from(sel.options).forEach(o => {
                            if (o.value && o.value !== '') {
                                results.push({
                                    type: 'select',
                                    selector_id: id,
                                    value: o.value,
                                    label: o.textContent.trim(),
                                    disabled: o.disabled,
                                });
                            }
                        });
                    }
                });

                // 2. Radio buttons for options
                document.querySelectorAll('input[type="radio"]').forEach(radio => {
                    const name = radio.name || '';
                    if (name.includes('option')) {
                        const label = radio.closest('label') ||
                                      document.querySelector(`label[for="${radio.id}"]`);
                        results.push({
                            type: 'radio',
                            selector_id: name,
                            value: radio.value,
                            label: label ? label.textContent.trim() : radio.value,
                            disabled: radio.disabled,
                        });
                    }
                });

                // 3. Button groups for sizes (some themes use buttons instead of selects)
                document.querySelectorAll('.option-value button, .product-options button, .size-btn').forEach(btn => {
                    const text = btn.textContent.trim();
                    if (text && text.length < 20) {
                        results.push({
                            type: 'button',
                            selector_id: 'button-group',
                            value: text,
                            label: text,
                            disabled: btn.disabled || btn.classList.contains('disabled'),
                        });
                    }
                });

                return results;
            }
        """)

        if raw_options:
            logger.debug("Found %d raw options on page", len(raw_options))
            for opt in raw_options:
                label = opt["label"]
                # Check if out of stock marker in label
                oos = ("---" in label or
                       "out of stock" in label.lower() or
                       "agotad" in label.lower() or
                       "esgotad" in label.lower() or
                       "no disponible" in label.lower())
                # Clean label
                clean_label = re.sub(
                    r'\s*[-–]\s*(out of stock|agotad[oa]|esgotad[oa]|no disponible).*',
                    '', label, flags=re.IGNORECASE
                ).strip().lstrip("-").strip()
                # Skip placeholder options like "--- Please Select ---"
                if clean_label and clean_label != "---" and not clean_label.startswith("---"):
                    details["sizes"].append({
                        "label": clean_label,
                        "in_stock": not oos and not opt.get("disabled", False),
                    })
    except Exception as e:
        logger.debug("Options extraction error: %s", e)

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
        # Wait for DOM content first, then try networkidle with shorter timeout
        await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass  # networkidle can timeout on pages with persistent connections
        # Give dynamic content extra time to render
        await asyncio.sleep(2)
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

            # Update gallery images
            if details.get("images"):
                product.images = details["images"]

            # Update product type from datalayer category
            if details.get("category"):
                result = await session.execute(
                    select(ProductType).where(ProductType.name == details["category"])
                )
                pt = result.scalar_one_or_none()
                if not pt:
                    try:
                        async with session.begin_nested():
                            pt = ProductType(name=details["category"])
                            session.add(pt)
                            await session.flush()
                    except IntegrityError:
                        result = await session.execute(
                            select(ProductType).where(ProductType.name == details["category"])
                        )
                        pt = result.scalar_one_or_none()
                if pt:
                    product.product_type_id = pt.id

            # Sync sizes: add new, update existing, delete removed
            result = await session.execute(
                select(ProductSize).where(ProductSize.product_id == product.id)
            )
            old_sizes = result.scalars().all()
            existing = {s.size_label: s for s in old_sizes}
            new_labels = {sz["label"] for sz in details.get("sizes", [])}

            # Delete sizes no longer present
            for label, size_obj in existing.items():
                if label not in new_labels:
                    await session.delete(size_obj)

            # Add or update
            for sz in details.get("sizes", []):
                if sz["label"] in existing:
                    existing[sz["label"]].in_stock = sz["in_stock"]
                else:
                    session.add(ProductSize(
                        product_id=product.id,
                        size_label=sz["label"],
                        in_stock=sz["in_stock"],
                    ))

            # Update stock on product
            prices = details.get("prices", {})
            stock = details.get("stock", {})
            product.stock_quantity = stock.get("quantity", 0)
            product.in_stock = stock.get("in_stock", False)

            # Price snapshot
            if details.get("is_authenticated"):
                # Update latest snapshot with wholesale price
                result = await session.execute(
                    select(PriceSnapshot)
                    .where(PriceSnapshot.product_id == product.id)
                    .order_by(PriceSnapshot.timestamp.desc())
                    .limit(1)
                )
                snapshot = result.scalar_one_or_none()
                if snapshot:
                    snapshot.price_wholesale = prices.get("regular")
                else:
                    # No existing snapshot — create one with all data
                    session.add(PriceSnapshot(
                        product_id=product.id,
                        timestamp=datetime.utcnow(),
                        price_wholesale=prices.get("regular"),
                        price_regular=prices.get("regular"),
                        price_original=prices.get("original"),
                        price_special=prices.get("special"),
                        price_without_tax=prices.get("without_tax"),
                        stock_quantity=stock.get("quantity", 0),
                        in_stock=stock.get("in_stock", False),
                    ))
            else:
                session.add(PriceSnapshot(
                    product_id=product.id,
                    timestamp=datetime.utcnow(),
                    price_regular=prices.get("regular"),
                    price_original=prices.get("original"),
                    price_special=prices.get("special"),
                    price_without_tax=prices.get("without_tax"),
                    stock_quantity=stock.get("quantity", 0),
                    in_stock=stock.get("in_stock", False),
                ))


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

    total = len(products)
    counter = {"done": 0}

    async def _worker(context, chunk):
        """Process a chunk of products, creating a fresh page for each."""
        for product in chunk:
            counter["done"] += 1
            logger.info("[%d/%d] %s", counter["done"], total, product.name)
            page = None
            try:
                page = await context.new_page()
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
            except Exception as e:
                logger.error("Worker error for %s: %s", product.name, e)
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
            await asyncio.sleep(REQUEST_DELAY)

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

        # Split products into chunks, one per concurrent page
        n = min(CONCURRENT_PAGES, len(products))
        chunks = [products[i::n] for i in range(n)]

        # Run workers in parallel, each creates/closes pages per product
        workers = [_worker(context, chunk) for chunk in chunks]

        await asyncio.gather(*workers)
        await browser.close()

    logger.info("Done scraping details")


async def run():
    debug = "--debug" in sys.argv
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    auth = "--auth" in sys.argv
    url = None
    for i, arg in enumerate(sys.argv):
        if arg == "--url" and i + 1 < len(sys.argv):
            url = sys.argv[i + 1]

    if url:
        # Single product test
        await init_db()
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            # --- Guest price ---
            guest_ctx = await browser.new_context(user_agent=ua)
            guest_page = await guest_ctx.new_page()
            guest_details = await scrape_product_detail(guest_page, url, False)

            if debug:
                # Dump options/selects diagnostics
                print("\n=== DEBUG: Page options diagnostics ===")
                try:
                    options_diag = await guest_page.evaluate("""
                        () => {
                            const result = {};
                            // All selects
                            const selects = [];
                            document.querySelectorAll('select').forEach(sel => {
                                const opts = Array.from(sel.options).map(o => ({
                                    value: o.value, text: o.textContent.trim(),
                                    disabled: o.disabled
                                }));
                                selects.push({
                                    id: sel.id, name: sel.name,
                                    class: sel.className,
                                    parent: sel.parentElement ? sel.parentElement.className : '',
                                    options: opts
                                });
                            });
                            if (selects.length) result.selects = selects;
                            // All radio buttons
                            const radios = [];
                            document.querySelectorAll('input[type="radio"]').forEach(r => {
                                const label = r.closest('label') ||
                                              document.querySelector(`label[for="${r.id}"]`);
                                radios.push({
                                    name: r.name, value: r.value, id: r.id,
                                    label: label ? label.textContent.trim() : ''
                                });
                            });
                            if (radios.length) result.radios = radios;
                            // Elements with "option" in class/id
                            const optionEls = [];
                            document.querySelectorAll('[class*="option"], [id*="option"]').forEach(el => {
                                optionEls.push({
                                    tag: el.tagName, id: el.id,
                                    class: el.className,
                                    text: el.textContent.trim().substring(0, 200)
                                });
                            });
                            if (optionEls.length) result.option_elements = optionEls;
                            return result;
                        }
                    """)
                    print(json.dumps(options_diag, indent=2, ensure_ascii=False, default=str))
                except Exception as e:
                    print(f"Options diagnostics error: {e}")
                print("=== END DEBUG ===\n")

            await guest_ctx.close()

            # --- Auth price (if --auth) ---
            auth_details = None
            if auth:
                cookies = load_cookies()
                if cookies:
                    auth_ctx = await browser.new_context(user_agent=ua)
                    await auth_ctx.add_cookies(cookies)
                    auth_page = await auth_ctx.new_page()
                    auth_details = await scrape_product_detail(auth_page, url, True)

                    if debug:
                        print("\n=== DEBUG: Auth page diagnostics ===")
                        try:
                            diag = await auth_page.evaluate("""
                                () => {
                                    const result = {};
                                    if (typeof datalayerDataGMT !== 'undefined') {
                                        result.datalayer = datalayerDataGMT;
                                    }
                                    const priceTexts = [];
                                    document.querySelectorAll(
                                        '.price, .product-price, .price-new, .price-old, ' +
                                        '[data-price], .special-price, span.price'
                                    ).forEach(el => {
                                        const t = el.textContent.trim();
                                        if (t) priceTexts.push({selector: el.className || el.tagName, text: t.substring(0, 100)});
                                    });
                                    if (priceTexts.length) result.visible_prices = priceTexts;
                                    return result;
                                }
                            """)
                            print(json.dumps(diag, indent=2, ensure_ascii=False, default=str))
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        print("=== END DEBUG ===\n")

                    await auth_ctx.close()
                else:
                    print("No cookies found. Run: python run.py auth login")

            # --- Build combined output ---
            if guest_details:
                output = {
                    "url": url,
                    "prices": {
                        "regular": guest_details["prices"].get("regular"),
                        "original": guest_details["prices"].get("original"),
                        "special": guest_details["prices"].get("special"),
                        "without_tax": guest_details["prices"].get("without_tax"),
                        "wholesale": (
                            auth_details["prices"].get("regular")
                            if auth_details else None
                        ),
                    },
                    "stock": guest_details.get("stock"),
                    "sizes": guest_details.get("sizes"),
                    "description": guest_details.get("description"),
                }
                print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
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
